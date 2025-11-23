import numpy as np
from flask import Flask, request, jsonify
from scipy.optimize import minimize

app = Flask(__name__)

# MPC内部パラメータ
mpc_config = {
    "horizon": 10,       # 予測ホライゾン (ステップ数)
    "dt": 300,           # タイムステップ (秒)
    "tau": 600.0,        # 時定数 (秒) - システムの反応速度
    "K": 10.0,           # ゲイン - バルブ1単位変化あたりの圧力変化量
    "weight_error": 1.0, # 追従誤差の重み
    "weight_du": 0.5,    # 操作量変化の重み (抑制項)
    # 流量制御用パラメータ (デフォルト値)
    "tau_flow": 1200.0,
    "K_flow": 30.0,
    "weight_error_flow": 1.0,
    "weight_du_flow": 0.5
}

# 前回の制御入力 (Delta U 計算用)
last_u = 1.0
control_mode = None  # 'pressure' または 'flow'

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
    # u_sequenceの先頭と前回のuとの差分も考慮
    u_diffs = np.diff(np.concatenate(([last_val_u], u_sequence)))
    du_cost = np.sum(u_diffs ** 2) * weight_du
    
    return error_cost + du_cost

@app.route('/control', methods=['POST'])
def control():
    global last_u, mpc_config, control_mode
    
    data = request.json
    
    # 初期化
    if data.get('init', False):
        # 制御モードの取得
        control_mode = data.get('control_mode', 'pressure')
        
        # MPC設定の更新
        if 'mpc_params' in data:
            mpc_config.update(data['mpc_params'])
        
        # 制御モードに応じたパラメータの選択
        if control_mode == 'flow':
            # 流量制御用パラメータが明示的に指定されていればそれを使用
            if 'tau_flow' not in data.get('mpc_params', {}):
                # デフォルト値を使用
                pass
            print(f"MPC initialized for FLOW control")
            print(f"  tau={mpc_config.get('tau_flow', mpc_config['tau'])}")
            print(f"  K={mpc_config.get('K_flow', mpc_config['K'])}")
        else:
            print(f"MPC initialized for PRESSURE control")
            print(f"  tau={mpc_config['tau']}")
            print(f"  K={mpc_config['K']}")
        
        # 初期値リセット
        last_u = data.get('prev_action', 1.0)
        
        return jsonify({
            "action": last_u,
            "status": "MPC initialized",
            "control_mode": control_mode,
            "config": mpc_config
        })

    # 現在の状態取得
    # 'pressure' というキー名だが、実際は制御対象値（圧力または流量）
    current_value = data.get('sensor_data', {}).get('pressure')
    target_value = data.get('sensor_data', {}).get('target')
    
    if current_value is None:
        return jsonify({"error": "No sensor data provided"}), 400

    # --- MPC 計算 ---
    
    # 1. 制御モードに応じたモデル係数の選択
    dt = mpc_config["dt"]
    
    if control_mode == 'flow':
        # 流量制御用パラメータ
        tau = mpc_config.get("tau_flow", mpc_config["tau"])
        K = mpc_config.get("K_flow", mpc_config["K"])
        weight_error = mpc_config.get("weight_error_flow", mpc_config["weight_error"])
        weight_du = mpc_config.get("weight_du_flow", mpc_config["weight_du"])
    else:
        # 圧力制御用パラメータ
        tau = mpc_config["tau"]
        K = mpc_config["K"]
        weight_error = mpc_config["weight_error"]
        weight_du = mpc_config["weight_du"]
    
    # モデル係数の計算 (離散化: 一次遅れ系)
    # y[k+1] = A*y[k] + B*u[k]
    A = np.exp(-dt / tau)
    B = K * (1 - A)
    
    H = mpc_config["horizon"]
    
    # 2. 最適化問題の設定
    # 初期推定値: 前回の操作量を維持
    u0 = np.full(H, last_u)
    
    # 制約条件: 0.0 <= u <= 1.0
    bounds = [(0.0, 1.0) for _ in range(H)]
    
    # 最適化実行 (SLSQP法など)
    result = minimize(
        cost_function,
        u0,
        args=(current_value, target_value, last_u, A, B, H, weight_error, weight_du),
        method='SLSQP',
        bounds=bounds,
        options={'disp': False, 'ftol': 1e-4, 'maxiter': 50}
    )
    
    # 3. 最適な入力の最初のステップを適用
    optimal_u_sequence = result.x
    next_action = float(optimal_u_sequence[0])
    
    # エラー計算
    error = target_value - current_value if target_value is not None else 0.0
    
    # 予測値の計算
    predicted_next = A * current_value + B * next_action
    
    # 更新
    last_u = next_action
    
    # レスポンス (PID互換のキーを含めることでsim-runnerのログに残るようにする)
    response = {
        "action": next_action,
        "p_term": 0.0,  # MPCにはP項はないがログ互換性のため
        "i_term": 0.0,
        "d_term": 0.0,
        "error": float(error),
        "control_mode": control_mode,
        "current_value": float(current_value),
        "target_value": float(target_value) if target_value is not None else None,
        "mpc_info": {
            "cost": float(result.fun),
            "predicted_next": float(predicted_next),
            "tau": float(tau),
            "K": float(K),
            "A": float(A),
            "B": float(B),
            "weight_error": float(weight_error),
            "weight_du": float(weight_du)
        }
    }
    
    return jsonify(response)

@app.route('/status', methods=['GET'])
def status():
    """コントローラーの状態を返す（デバッグ用）"""
    global control_mode, mpc_config, last_u
    
    return jsonify({
        "status": "active" if control_mode is not None else "not_initialized",
        "control_mode": control_mode,
        "last_u": last_u,
        "config": mpc_config
    })

@app.route('/reset', methods=['POST'])
def reset():
    """MPCコントローラーをリセット（必要に応じて）"""
    global last_u, control_mode
    
    last_u = 1.0
    control_mode = None
    
    return jsonify({
        "status": "reset",
        "message": "MPC controller has been reset"
    })

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)