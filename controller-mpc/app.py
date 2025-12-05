"""
controller-mpc/app.py (修正版)

Modified to support:
1. Initialization requests from sim-runner
2. New payload format: {"time_step": ..., "sensor_data": [...]}
3. Multi-episode execution
4. Enhanced debug logging
"""
import numpy as np
from flask import Flask, request, jsonify
from scipy.optimize import minimize

app = Flask(__name__)

# グローバル変数: 各ループ用のMPC状態を辞書で管理
mpc_states = {}  # loop_id -> {"last_u": ..., "config": ..., "mode": ...}
control_mode = None
current_episode = 0  # エピソードカウンタ


def predict_trajectory(u_sequence, current_y, A, B, horizon):
    """
    制御入力列 u_sequence に基づき、将来の出力 y を予測する
    モデル: y(k+1) = A * y(k) + B * u(k)
    """
    predictions = []
    y = current_y
    for u in u_sequence:
        y = A * y + B * u
        predictions.append(y)
    return np.array(predictions)


def cost_function(u_sequence, current_y, target, last_val_u, A, B, horizon, weight_error, weight_du):
    """
    コスト関数: 誤差の二乗和 + 操作量変化の二乗和
    """
    # 予測軌道の計算
    preds = predict_trajectory(u_sequence, current_y, A, B, horizon)
    
    # 誤差項 (Error term)
    error_cost = np.sum((preds - target) ** 2) * weight_error
    
    # 操作量変化項 (Control Effort term)
    u_diffs = np.diff(np.concatenate(([last_val_u], u_sequence)))
    du_cost = np.sum(u_diffs ** 2) * weight_du
    
    return error_cost + du_cost


def initialize_mpc_controllers(loops, mode='pressure'):
    """複数の制御ループに対してMPCコントローラを初期化"""
    global mpc_states, control_mode
    
    control_mode = mode
    mpc_states = {}
    
    for loop in loops:
        loop_id = loop.get('loop_id', 'default')
        params = loop.get('mpc_params', {})
        actuator_config = loop.get('actuator', {})
        
        # デフォルト設定
        default_config = {
            "horizon": params.get('horizon', 10),
            "dt": params.get('dt', 300),
            "tau": params.get('tau', 600.0),
            "K": params.get('K', 10.0),
            "weight_error": params.get('weight_error', 1.0),
            "weight_du": params.get('weight_du', 0.5)
        }
        
        # 制御モードに応じたパラメータの上書き
        if mode == 'flow':
            default_config['tau'] = params.get('tau_flow', default_config['tau'])
            default_config['K'] = params.get('K_flow', default_config['K'])
            default_config['weight_error'] = params.get('weight_error_flow', default_config['weight_error'])
            default_config['weight_du'] = params.get('weight_du_flow', default_config['weight_du'])
        
        mpc_states[loop_id] = {
            "last_u": actuator_config.get('initial_setting', 1.0),
            "config": default_config,
            "mode": mode
        }
        
        print(f"MPC Controller Initialized for Loop '{loop_id}':")
        print(f"  Mode: {mode}")
        print(f"  Horizon: {default_config['horizon']}")
        print(f"  tau: {default_config['tau']}, K: {default_config['K']}")
        print(f"  Weights: error={default_config['weight_error']}, du={default_config['weight_du']}")
    
    print(f"Total {len(mpc_states)} MPC controllers initialized")


@app.route('/control', methods=['POST'])
def control():
    """
    制御計算エンドポイント
    
    2つのモード:
    1. 初期化モード: {"init": true, "control_loops": [...], "control_mode": "..."}
    2. 制御モード: {"time_step": ..., "sensor_data": [...]}
    """
    global mpc_states, control_mode, current_episode
    
    data = request.json
    
    # ========================================
    # Mode 1: Initialization Request
    # ========================================
    if data.get('init', False):
        print("\n" + "=" * 70)
        print(f"📋 INITIALIZATION REQUEST RECEIVED (Episode {current_episode + 1})")
        print("=" * 70)
        
        # Reset MPC states for new episode
        if mpc_states:
            print(f"🔚 Resetting previous episode {current_episode}...")
            for loop_id, state in mpc_states.items():
                # Reset last_u to initial setting
                actuator_config = next(
                    (loop.get('actuator', {}) for loop in data.get('control_loops', []) 
                     if loop.get('loop_id') == loop_id), 
                    {}
                )
                state['last_u'] = actuator_config.get('initial_setting', 1.0)
                print(f"   Reset {loop_id} MPC state (last_u={state['last_u']:.4f})")
        
        # Increment episode counter
        current_episode += 1
        print(f"🎬 Starting Episode {current_episode}")
        
        # Get control loops from initialization data
        loops = data.get('control_loops', [])
        mode = data.get('control_mode', 'pressure')
        
        print(f"⚙️  Control mode: {mode}")
        print(f"🔄 Number of loops: {len(loops)}")
        
        # 後方互換性: 旧形式の場合
        if not loops:
            print("   Using legacy single-loop configuration")
            loops = [{
                "loop_id": "default",
                "target": {"target_pressure": 30.0, "target_flow": 100.0},
                "actuator": {"initial_setting": 1.0},
                "mpc_params": data.get('mpc_params', {})
            }]
        
        # Initialize or reset controllers
        initialize_mpc_controllers(loops, mode)
        
        print(f"\n✅ Episode {current_episode} initialized successfully!")
        print("=" * 70)
        print()
        
        return jsonify({
            "status": "initialized",
            "episode": current_episode,
            "control_mode": control_mode,
            "num_loops": len(mpc_states),
            "controller_type": "batch"  # MPC is batch-style controller
        })
    
    # ========================================
    # Mode 2: Control Request
    # ========================================
    else:
        # センサーデータの取得
        # 新形式: {"time_step": ..., "sensor_data": [...]}
        # 旧形式: {"sensor_data": {...}} または直接データ
        
        time_step = data.get('time_step', 0)
        sensor_data_raw = data.get('sensor_data')
        
        # DEBUG: Log first request
        if time_step == 0 or time_step == 600:
            print(f"\n[DEBUG] MPC control request at t={time_step}")
            print(f"[DEBUG] Request keys: {list(data.keys())}")
            print(f"[DEBUG] sensor_data type: {type(sensor_data_raw)}")
        
        # 後方互換性: 複数の形式に対応
        if sensor_data_raw is None:
            # 最も古い形式: データが直接トップレベルにある
            sensor_data_list = [{
                "loop_id": "default",
                "pressure": data.get('pressure'),
                "target": data.get('target'),
                "prev_action": data.get('prev_action', 0.5)
            }]
            if time_step == 0:
                print(f"[DEBUG] Using legacy format (data at top level)")
        elif isinstance(sensor_data_raw, dict):
            # 旧形式: sensor_dataが辞書（単一ループ）
            sensor_data_list = [{
                "loop_id": "default",
                "pressure": sensor_data_raw.get('pressure'),
                "target": sensor_data_raw.get('target'),
                "prev_action": data.get('prev_action', 0.5)
            }]
            if time_step == 0:
                print(f"[DEBUG] Using legacy format (sensor_data as dict)")
        elif isinstance(sensor_data_raw, list):
            # 新形式: sensor_dataが配列（複数ループ対応）
            sensor_data_list = sensor_data_raw
            if time_step == 0:
                print(f"[DEBUG] Using new format (sensor_data as array)")
                print(f"[DEBUG] Number of loops: {len(sensor_data_list)}")
        else:
            return jsonify({"error": "Invalid sensor data format"}), 400
        
        if not sensor_data_list:
            return jsonify({"error": "No sensor data provided"}), 400
        
        # Process each loop
        actions = []
        
        for sensor_data in sensor_data_list:
            loop_id = sensor_data.get('loop_id', 'default')
            current_value = sensor_data.get('pressure')  # 制御対象値
            target_value = sensor_data.get('target')
            
            if loop_id not in mpc_states:
                print(f"⚠️  WARNING: MPC not found for loop '{loop_id}'")
                actions.append({
                    "loop_id": loop_id,
                    "action": 0.5,
                    "error": "MPC not initialized",
                    "p_term": 0.0,
                    "i_term": 0.0,
                    "d_term": 0.0
                })
                continue
            
            if current_value is None or target_value is None:
                print(f"⚠️  WARNING: Invalid sensor data for loop '{loop_id}'")
                actions.append({
                    "loop_id": loop_id,
                    "action": 0.5,
                    "error": "Invalid sensor data",
                    "p_term": 0.0,
                    "i_term": 0.0,
                    "d_term": 0.0
                })
                continue
            
            # --- MPC 計算 ---
            state = mpc_states[loop_id]
            config = state['config']
            last_u = state['last_u']
            
            # モデル係数の計算 (離散化: 一次遅れ系)
            dt = config["dt"]
            tau = config["tau"]
            K = config["K"]
            
            A = np.exp(-dt / tau)
            B = K * (1 - A)
            
            H = config["horizon"]
            weight_error = config["weight_error"]
            weight_du = config["weight_du"]
            
            # 最適化問題の設定
            u0 = np.full(H, last_u)
            bounds = [(0.0, 1.0) for _ in range(H)]
            
            # 最適化実行
            try:
                result = minimize(
                    cost_function,
                    u0,
                    args=(current_value, target_value, last_u, A, B, H, weight_error, weight_du),
                    method='SLSQP',
                    bounds=bounds,
                    options={'disp': False, 'ftol': 1e-4, 'maxiter': 50}
                )
                
                optimal_u_sequence = result.x
                next_action = float(optimal_u_sequence[0])
                cost = float(result.fun)
                
            except Exception as e:
                print(f"⚠️  MPC optimization failed for loop '{loop_id}': {e}")
                next_action = last_u
                cost = -1.0
            
            # エラー計算
            error = target_value - current_value
            
            # 予測値の計算
            predicted_next = A * current_value + B * next_action
            
            # 状態更新
            state['last_u'] = next_action
            
            # Log every 50 steps
            step = sensor_data.get('step', time_step // 600)
            if step % 50 == 0 and step > 0:
                print(f"   Step {step}: loop={loop_id}, error={error:.2f}, action={next_action:.4f}, cost={cost:.2f}")
            
            actions.append({
                "loop_id": loop_id,
                "action": next_action,
                "p_term": 0.0,  # MPCにはP項はないがログ互換性のため
                "i_term": 0.0,
                "d_term": 0.0,
                "error": float(error),
                "control_mode": control_mode,
                "current_value": float(current_value),
                "target_value": float(target_value),
                "mpc_info": {
                    "cost": cost,
                    "predicted_next": float(predicted_next),
                    "tau": float(tau),
                    "K": float(K),
                    "A": float(A),
                    "B": float(B)
                }
            })
        
        return jsonify({"actions": actions})


@app.route('/status', methods=['GET'])
def status():
    """コントローラーの状態を返す（デバッグ用）"""
    global mpc_states, control_mode, current_episode
    
    if not mpc_states:
        return jsonify({
            "status": "not_initialized",
            "control_mode": None,
            "current_episode": current_episode,
            "num_loops": 0
        })
    
    controllers_info = {}
    for loop_id, state in mpc_states.items():
        controllers_info[loop_id] = {
            "last_u": state['last_u'],
            "config": state['config'],
            "mode": state['mode']
        }
    
    return jsonify({
        "status": "active",
        "control_mode": control_mode,
        "current_episode": current_episode,
        "num_loops": len(mpc_states),
        "controllers": controllers_info
    })


@app.route('/reset', methods=['POST'])
def reset():
    """MPCコントローラーをリセット"""
    global mpc_states, control_mode
    
    print("\n🔄 Manual reset requested")
    
    for loop_id, state in mpc_states.items():
        state['last_u'] = 1.0  # Reset to initial value
        print(f"   Reset {loop_id} MPC state (last_u=1.0)")
    
    print("✓ All MPC controllers reset\n")
    
    return jsonify({
        "status": "reset",
        "message": "All MPC controllers have been reset"
    })


@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint"""
    return jsonify({
        "status": "ok",
        "service": "controller-mpc"
    })


if __name__ == '__main__':
    print("\n" + "=" * 70)
    print("🚀 MPC Controller Service Starting")
    print("=" * 70)
    print()
    
    print("📋 Configuration:")
    print(f"   Service: MPC Controller")
    print(f"   Port: 5000")
    print()
    
    print("🌐 Starting Flask app on 0.0.0.0:5000")
    print("=" * 70)
    print()
    
    app.run(host='0.0.0.0', port=5000)