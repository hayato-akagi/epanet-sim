import numpy as np
from flask import Flask, request, jsonify
from scipy.optimize import minimize

app = Flask(__name__)

# グローバル変数: 各ループ用のMPC状態を辞書で管理
mpc_states = {}  # loop_id -> {"last_u": ..., "config": ..., "mode": ...}
control_mode = None

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
    複数の制御ループに対してMPC計算を行う
    """
    global mpc_states, control_mode
    
    data = request.json
    
    # 初期化
    if data.get('init', False):
        loops = data.get('control_loops', [])
        mode = data.get('control_mode', 'pressure')
        
        # 後方互換性: 旧形式の場合
        if not loops:
            loops = [{
                "loop_id": "default",
                "target": {"target_pressure": 30.0, "target_flow": 100.0},
                "actuator": {"initial_setting": 1.0},
                "mpc_params": data.get('mpc_params', {})
            }]
        
        initialize_mpc_controllers(loops, mode)
        
        return jsonify({
            "status": "MPC initialized",
            "control_mode": control_mode,
            "num_loops": len(mpc_states)
        })

    # センサーデータの取得（配列または辞書に対応）
    sensor_data_raw = data.get('sensor_data')
    
    # 後方互換性: 旧形式（辞書）の場合は配列に変換
    if isinstance(sensor_data_raw, dict):
        sensor_data_list = [{
            "loop_id": "default",
            "pressure": sensor_data_raw.get('pressure'),
            "target": sensor_data_raw.get('target'),
            "prev_action": data.get('prev_action', 0.5)
        }]
    elif isinstance(sensor_data_raw, list):
        sensor_data_list = sensor_data_raw
    else:
        return jsonify({"error": "Invalid sensor data format"}), 400
    
    if not sensor_data_list:
        return jsonify({"error": "No sensor data provided"}), 400
    
    actions = []
    
    for sensor_data in sensor_data_list:
        loop_id = sensor_data.get('loop_id', 'default')
        current_value = sensor_data.get('pressure')  # 制御対象値
        target_value = sensor_data.get('target')
        
        if loop_id not in mpc_states:
            print(f"Warning: MPC not found for loop '{loop_id}'")
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
            print(f"MPC optimization failed for loop '{loop_id}': {e}")
            next_action = last_u
            cost = -1.0
        
        # エラー計算
        error = target_value - current_value
        
        # 予測値の計算
        predicted_next = A * current_value + B * next_action
        
        # 状態更新
        state['last_u'] = next_action
        
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
    global mpc_states, control_mode
    
    if not mpc_states:
        return jsonify({
            "status": "not_initialized",
            "control_mode": None,
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
        "num_loops": len(mpc_states),
        "controllers": controllers_info
    })

@app.route('/reset', methods=['POST'])
def reset():
    """MPCコントローラーをリセット"""
    global mpc_states, control_mode
    
    mpc_states = {}
    control_mode = None
    
    return jsonify({
        "status": "reset",
        "message": "All MPC controllers have been reset"
    })

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)