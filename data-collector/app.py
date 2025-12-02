import os
import json
import redis
from flask import Flask, request, jsonify
from pathlib import Path
from datetime import datetime
import csv

app = Flask(__name__)

# 環境変数
REDIS_URL = os.environ.get('REDIS_URL', 'redis://redis:6379')
OUTPUT_DIR = os.environ.get('OUTPUT_DIR', '/shared/training_data')

# Redis接続
redis_client = redis.from_url(REDIS_URL, decode_responses=False)

def ensure_directory(path):
    """ディレクトリが存在しない場合は作成"""
    Path(path).mkdir(parents=True, exist_ok=True)

def save_images_from_redis(exp_dir, step, redis_keys):
    """
    Redisから画像を取得してファイルに保存
    
    Args:
        exp_dir: Path - 実験ディレクトリ
        step: int - ステップ番号
        redis_keys: dict - Redis保存キーの辞書
    
    Returns:
        list - 保存されたファイルパスのリスト
    """
    images_dir = exp_dir / 'images'
    ensure_directory(images_dir)
    
    saved_files = []
    
    for img_type, redis_key in redis_keys.items():
        try:
            # Redisから画像データを取得
            img_bytes = redis_client.get(redis_key)
            
            if img_bytes:
                # ファイルに保存
                img_path = images_dir / f"step_{step:04d}_{img_type}.png"
                with open(img_path, 'wb') as f:
                    f.write(img_bytes)
                
                saved_files.append(str(img_path))
                print(f"[data-collector] Saved: {img_path}")
            else:
                print(f"[data-collector] Warning: No data in Redis for key '{redis_key}'")
                
        except Exception as e:
            print(f"[data-collector] Error saving {img_type}: {e}")
    
    return saved_files

def append_to_states_csv(exp_dir, step, state):
    """
    states.csvに状態データを追記
    
    Args:
        exp_dir: Path - 実験ディレクトリ
        step: int - ステップ番号
        state: dict - 状態データ
    """
    states_csv = exp_dir / 'states.csv'
    
    # ヘッダー定義
    headers = [
        'step', 'time', 'pressure', 'flow', 'valve_setting',
        'upstream_pressure', 'downstream_pressure',
        'target_pressure', 'target_flow'
    ]
    
    # ファイルが存在しない場合はヘッダーを書き込み
    file_exists = states_csv.exists()
    
    with open(states_csv, 'a', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        
        if not file_exists:
            writer.writeheader()
        
        # データ行を書き込み
        row = {
            'step': step,
            'time': state.get('time', 0),
            'pressure': state.get('pressure', 0.0),
            'flow': state.get('flow', 0.0),
            'valve_setting': state.get('valve_setting', 0.0),
            'upstream_pressure': state.get('upstream_pressure', 0.0),
            'downstream_pressure': state.get('downstream_pressure', 0.0),
            'target_pressure': state.get('target_pressure', 0.0),
            'target_flow': state.get('target_flow', 0.0)
        }
        
        writer.writerow(row)
    
    print(f"[data-collector] Appended to states.csv: step={step}")

def append_to_actions_csv(exp_dir, step, time, action):
    """
    actions.csvにアクションデータを追記
    
    Args:
        exp_dir: Path - 実験ディレクトリ
        step: int - ステップ番号
        time: float - シミュレーション時刻
        action: float - アクション値
    """
    actions_csv = exp_dir / 'actions.csv'
    
    headers = ['step', 'time', 'action']
    
    file_exists = actions_csv.exists()
    
    with open(actions_csv, 'a', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        
        if not file_exists:
            writer.writeheader()
        
        row = {
            'step': step,
            'time': time,
            'action': action
        }
        
        writer.writerow(row)
    
    print(f"[data-collector] Appended to actions.csv: step={step}, action={action:.4f}")

def append_to_prompts_jsonl(exp_dir, step, prompt):
    """
    prompts.jsonlにプロンプトを追記
    
    Args:
        exp_dir: Path - 実験ディレクトリ
        step: int - ステップ番号
        prompt: str - プロンプトテキスト
    """
    prompts_jsonl = exp_dir / 'prompts.jsonl'
    
    with open(prompts_jsonl, 'a') as f:
        data = {
            "step": step,
            "prompt": prompt
        }
        f.write(json.dumps(data) + '\n')
    
    print(f"[data-collector] Appended to prompts.jsonl: step={step}")

def update_trajectory_json(exp_dir, exp_id, step, controller, control_mode=None):
    """
    trajectory.jsonを更新
    
    Args:
        exp_dir: Path - 実験ディレクトリ
        exp_id: str - 実験ID
        step: int - 現在のステップ番号
        controller: str - コントローラ名
        control_mode: str - 制御モード（オプション）
    """
    trajectory_json = exp_dir / 'trajectory.json'
    
    # 既存のデータを読み込み（存在する場合）
    if trajectory_json.exists():
        with open(trajectory_json, 'r') as f:
            trajectory_data = json.load(f)
    else:
        # 新規作成
        trajectory_data = {
            "exp_id": exp_id,
            "controller": controller,
            "created_at": datetime.now().isoformat()
        }
        
        if control_mode:
            trajectory_data["control_mode"] = control_mode
    
    # 更新
    trajectory_data["last_step"] = step
    trajectory_data["updated_at"] = datetime.now().isoformat()
    
    # 保存
    with open(trajectory_json, 'w') as f:
        json.dump(trajectory_data, f, indent=2)
    
    print(f"[data-collector] Updated trajectory.json: last_step={step}")

@app.route('/collect', methods=['POST'])
def collect():
    """
    学習データ収集エンドポイント
    
    Request:
    {
        "exp_id": "exp_001_vla",
        "step": 42,
        "redis_keys": {
            "system_ui": "exp_001_vla:step_42:system_ui",
            "valve_detail": "exp_001_vla:step_42:valve_detail",
            "flow_dashboard": "exp_001_vla:step_42:flow_dashboard",
            "comparison": "exp_001_vla:step_42:comparison"
        },
        "state": {
            "time": 151200,
            "pressure": 28.5,
            "flow": 95.3,
            "valve_setting": 0.45,
            "upstream_pressure": 50.2,
            "downstream_pressure": 28.5,
            "target_pressure": 30.0,
            "target_flow": 100.0
        },
        "action": 0.47,
        "prompt": "Regulate pressure...",
        "controller": "simple_dnn",
        "control_mode": "pressure"  // オプション
    }
    
    Response:
    {
        "status": "saved",
        "saved_files": [...]
    }
    """
    try:
        data = request.json
        
        # 必須パラメータの取得
        exp_id = data.get('exp_id', 'unknown')
        step = data.get('step', 0)
        redis_keys = data.get('redis_keys', {})
        state = data.get('state', {})
        action = data.get('action', 0.0)
        prompt = data.get('prompt', '')
        controller = data.get('controller', 'unknown')
        control_mode = data.get('control_mode')
        
        # 実験ディレクトリの作成
        exp_dir = Path(OUTPUT_DIR) / exp_id
        ensure_directory(exp_dir)
        
        # 1. 画像の保存
        saved_files = save_images_from_redis(exp_dir, step, redis_keys)
        
        # 2. states.csvへの追記
        append_to_states_csv(exp_dir, step, state)
        
        # 3. actions.csvへの追記
        append_to_actions_csv(exp_dir, step, state.get('time', 0), action)
        
        # 4. prompts.jsonlへの追記
        append_to_prompts_jsonl(exp_dir, step, prompt)
        
        # 5. trajectory.jsonの更新
        update_trajectory_json(exp_dir, exp_id, step, controller, control_mode)
        
        return jsonify({
            "status": "saved",
            "saved_files": saved_files,
            "exp_id": exp_id,
            "step": step
        }), 200
        
    except Exception as e:
        print(f"[data-collector] Error in /collect: {e}")
        import traceback
        traceback.print_exc()
        
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500

@app.route('/health', methods=['GET'])
def health():
    """ヘルスチェックエンドポイント"""
    return jsonify({
        "status": "healthy",
        "output_dir": OUTPUT_DIR,
        "redis_connected": redis_client.ping()
    })

@app.route('/experiments', methods=['GET'])
def list_experiments():
    """
    保存されている実験一覧を取得
    
    Response:
    {
        "experiments": [
            {
                "exp_id": "exp_001_vla",
                "last_step": 999,
                "controller": "simple_dnn",
                "created_at": "2025-11-24T00:00:00"
            },
            ...
        ]
    }
    """
    try:
        training_dir = Path(OUTPUT_DIR)
        
        if not training_dir.exists():
            return jsonify({"experiments": []})
        
        experiments = []
        
        for exp_dir in training_dir.iterdir():
            if exp_dir.is_dir():
                trajectory_file = exp_dir / 'trajectory.json'
                
                if trajectory_file.exists():
                    with open(trajectory_file, 'r') as f:
                        trajectory_data = json.load(f)
                    
                    experiments.append({
                        "exp_id": trajectory_data.get('exp_id', exp_dir.name),
                        "last_step": trajectory_data.get('last_step', 0),
                        "controller": trajectory_data.get('controller', 'unknown'),
                        "control_mode": trajectory_data.get('control_mode', 'unknown'),
                        "created_at": trajectory_data.get('created_at', 'unknown'),
                        "updated_at": trajectory_data.get('updated_at', 'unknown')
                    })
        
        # ステップ数でソート
        experiments.sort(key=lambda x: x.get('last_step', 0), reverse=True)
        
        return jsonify({
            "experiments": experiments,
            "total": len(experiments)
        })
        
    except Exception as e:
        print(f"[data-collector] Error in /experiments: {e}")
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500

@app.route('/experiment/<exp_id>', methods=['GET'])
def get_experiment_info(exp_id):
    """
    特定の実験の詳細情報を取得
    
    Response:
    {
        "exp_id": "exp_001_vla",
        "trajectory": {...},
        "total_images": 4000,
        "total_states": 1000,
        "total_actions": 1000
    }
    """
    try:
        exp_dir = Path(OUTPUT_DIR) / exp_id
        
        if not exp_dir.exists():
            return jsonify({
                "status": "error",
                "message": f"Experiment '{exp_id}' not found"
            }), 404
        
        # trajectory.jsonを読み込み
        trajectory_file = exp_dir / 'trajectory.json'
        if trajectory_file.exists():
            with open(trajectory_file, 'r') as f:
                trajectory_data = json.load(f)
        else:
            trajectory_data = {}
        
        # 統計情報を計算
        images_dir = exp_dir / 'images'
        total_images = len(list(images_dir.glob('*.png'))) if images_dir.exists() else 0
        
        states_csv = exp_dir / 'states.csv'
        total_states = sum(1 for _ in open(states_csv)) - 1 if states_csv.exists() else 0
        
        actions_csv = exp_dir / 'actions.csv'
        total_actions = sum(1 for _ in open(actions_csv)) - 1 if actions_csv.exists() else 0
        
        return jsonify({
            "exp_id": exp_id,
            "trajectory": trajectory_data,
            "total_images": total_images,
            "total_states": total_states,
            "total_actions": total_actions
        })
        
    except Exception as e:
        print(f"[data-collector] Error in /experiment/{exp_id}: {e}")
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500

if __name__ == '__main__':
    # 起動時にOUTPUT_DIRを作成
    ensure_directory(OUTPUT_DIR)
    print(f"[data-collector] Output directory: {OUTPUT_DIR}")
    print(f"[data-collector] Redis URL: {REDIS_URL}")
    
    app.run(host='0.0.0.0', port=5000)