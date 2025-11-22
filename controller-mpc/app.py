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
    "weight_du": 0.5     # 操作量変化の重み (抑制項)
}

# 前回の制御入力 (Delta U 計算用)
last_u = 1.0

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

def cost_function(u_sequence, current_y, target, last_val_u, A, B, horizon):
    """
    コスト関数: 誤差の二乗和 + 操作量変化の二乗和
    """
    # 予測軌道の計算
    preds = predict_trajectory(u_sequence, current_y, A, B, horizon)
    
    # 誤差項 (Error term)
    error_cost = np.sum((preds - target) ** 2) * mpc_config["weight_error"]
    
    # 操作量変化項 (Control Effort term)
    # u_sequenceの先頭と前回のuとの差分も考慮
    u_diffs = np.diff(np.concatenate(([last_val_u], u_sequence)))
    du_cost = np.sum(u_diffs ** 2) * mpc_config["weight_du"]
    
    return error_cost + du_cost

@app.route('/control', methods=['POST'])
def control():
    global last_u, mpc_config
    
    data = request.json
    
    # 初期化
    if data.get('init', False):
        params = data.get('pid_params', {}) # 設定ファイルの pid_params フィールドをMPC用パラメータとして流用、あるいは別途 mpc_params を用意
        # 簡易的に pid_params または mpc_params から設定を読み込む
        if 'mpc_params' in data:
            mpc_config.update(data['mpc_params'])
        
        # 初期値リセット
        last_u = data.get('prev_action', 1.0)
        return jsonify({"action": last_u, "status": "MPC initialized", "config": mpc_config})

    # 現在の状態取得
    current_pressure = data.get('sensor_data', {}).get('pressure')
    target_pressure = data.get('sensor_data', {}).get('target')
    
    if current_pressure is None:
        return jsonify({"error": "No pressure data provided"}), 400

    # --- MPC 計算 ---
    
    # 1. モデル係数の計算 (離散化: 一次遅れ系)
    # y[k+1] = (1 - dt/tau)*y[k] + (K*dt/tau)*u[k]
    # 注: これは簡易モデルです。実際のシステム同定がない場合、パラメータ調整が必要です。
    dt = mpc_config["dt"]
    tau = mpc_config["tau"]
    K = mpc_config["K"]
    
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
        args=(current_pressure, target_pressure, last_u, A, B, H),
        method='SLSQP',
        bounds=bounds,
        options={'disp': False, 'ftol': 1e-4, 'maxiter': 50}
    )
    
    # 3. 最適な入力の最初のステップを適用
    optimal_u_sequence = result.x
    next_action = float(optimal_u_sequence[0])
    
    # 更新
    last_u = next_action
    
    # レスポンス (PID互換のキーを含めることでsim-runnerのログに残るようにする)
    response = {
        "action": next_action,
        "p_term": 0.0, # MPCにはP項はないがログ互換性のため
        "i_term": 0.0,
        "d_term": 0.0,
        "mpc_info": {
            "cost": float(result.fun),
            "predicted_next_p": float(A * current_pressure + B * next_action)
        }
    }
    
    return jsonify(response)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)