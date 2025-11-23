import os
import json
from flask import Flask, request, jsonify
from simple_pid import PID

app = Flask(__name__)

# グローバルPIDコントローラの保持用（簡易的な実装として単一セッションを想定）
# 複数のシミュレーションを同時に走らせる場合は、セッションID管理が必要です
pid_controller = None
control_mode = None  # 'pressure' または 'flow'

def initialize_pid(params, mode='pressure'):
    """設定ファイルに基づいてPIDコントローラを初期化"""
    global pid_controller, control_mode
    
    control_mode = mode
    
    # 制御モードに応じたデフォルトパラメータの選択
    if mode == 'flow':
        # 流量制御用のデフォルトゲイン（必要に応じて調整）
        default_kp = params.get('kp_flow', params.get('kp', 0.01))
        default_ki = params.get('ki_flow', params.get('ki', 0.001))
        default_kd = params.get('kd_flow', params.get('kd', 0.02))
        default_setpoint = params.get('setpoint_flow', params.get('setpoint', 100.0))
    else:  # pressure
        default_kp = params.get('kp', 1.0)
        default_ki = params.get('ki', 0.1)
        default_kd = params.get('kd', 0.05)
        default_setpoint = params.get('setpoint', 30.0)
    
    # PID(Kp, Ki, Kd, setpoint)
    pid_controller = PID(
        default_kp,
        default_ki,
        default_kd,
        setpoint=default_setpoint
    )
    
    # 出力制限（バルブ開度は 0.0 ～ 1.0 の範囲）
    pid_controller.output_limits = (0.0, 1.0)
    
    print(f"PID Controller Initialized:")
    print(f"  Mode: {control_mode}")
    print(f"  Kp={default_kp}, Ki={default_ki}, Kd={default_kd}")
    print(f"  Setpoint={default_setpoint}")

@app.route('/control', methods=['POST'])
def control():
    """
    Step 3: 制御計算 (Control Calculation)
    リクエストを受け取り、PID計算を行って新しいバルブ設定値を返す
    """
    global pid_controller, control_mode
    
    data = request.json
    
    # 初期化リクエストの確認 (初回ステップまたは明示的なリセット)
    if data.get('init', False) or pid_controller is None:
        pid_params = data.get('pid_params', {})
        mode = data.get('control_mode', 'pressure')  # デフォルトは圧力制御
        initialize_pid(pid_params, mode)
        # 初期化時は初期アクションを返すだけ
        return jsonify({
            "action": 1.0, 
            "status": "initialized",
            "control_mode": control_mode
        })

    # センサーデータの取得
    # 'pressure' というキー名だが、実際は制御対象値（圧力または流量）
    current_value = data.get('sensor_data', {}).get('pressure')
    target_value = data.get('sensor_data', {}).get('target')
    
    if current_value is None:
        return jsonify({"error": "No sensor data provided"}), 400

    # PIDのセットポイント動的更新（必要に応じて）
    if target_value is not None and target_value != pid_controller.setpoint:
        pid_controller.setpoint = target_value

    # PID計算
    # simple_pid は update(current_value) を呼ぶと制御入力(操作量)を返す
    # ここでは「バルブ開度」を操作量とする
    control_action = pid_controller(current_value)

    # エラー計算
    error = target_value - current_value if target_value is not None else 0.0

    response = {
        "action": float(control_action),
        "p_term": float(pid_controller.components[0]),
        "i_term": float(pid_controller.components[1]),
        "d_term": float(pid_controller.components[2]),
        "error": float(error),
        "control_mode": control_mode,
        "current_value": float(current_value),
        "target_value": float(target_value) if target_value is not None else None
    }
    
    return jsonify(response)

@app.route('/status', methods=['GET'])
def status():
    """コントローラーの状態を返す（デバッグ用）"""
    global pid_controller, control_mode
    
    if pid_controller is None:
        return jsonify({
            "status": "not_initialized",
            "control_mode": None
        })
    
    return jsonify({
        "status": "active",
        "control_mode": control_mode,
        "setpoint": pid_controller.setpoint,
        "kp": pid_controller.Kp,
        "ki": pid_controller.Ki,
        "kd": pid_controller.Kd,
        "output_limits": pid_controller.output_limits
    })

@app.route('/reset', methods=['POST'])
def reset():
    """PIDコントローラーをリセット（必要に応じて）"""
    global pid_controller, control_mode
    
    pid_controller = None
    control_mode = None
    
    return jsonify({
        "status": "reset",
        "message": "PID controller has been reset"
    })

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)