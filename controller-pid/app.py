import os
import json
from flask import Flask, request, jsonify
from simple_pid import PID

app = Flask(__name__)

# グローバルPIDコントローラの保持用（簡易的な実装として単一セッションを想定）
# 複数のシミュレーションを同時に走らせる場合は、セッションID管理が必要です
pid_controller = None

def initialize_pid(params):
    """設定ファイルに基づいてPIDコントローラを初期化"""
    global pid_controller
    # PID(Kp, Ki, Kd, setpoint)
    pid_controller = PID(
        params.get('kp', 1.0),
        params.get('ki', 0.1),
        params.get('kd', 0.05),
        setpoint=params.get('setpoint', 30.0)
    )
    # 出力制限（バルブ開度は 0.0 ～ 1.0 の範囲）
    pid_controller.output_limits = (0.0, 1.0)
    print(f"PID Controller Initialized: {params}")

@app.route('/control', methods=['POST'])
def control():
    """
    Step 3: 制御計算 (Control Calculation)
    リクエストを受け取り、PID計算を行って新しいバルブ設定値を返す
    """
    global pid_controller
    
    data = request.json
    
    # 初期化リクエストの確認 (初回ステップまたは明示的なリセット)
    if data.get('init', False) or pid_controller is None:
        pid_params = data.get('pid_params', {})
        initialize_pid(pid_params)
        # 初期化時は初期アクションを返すだけ
        return jsonify({"action": 1.0, "status": "initialized"})

    # センサーデータの取得
    current_pressure = data.get('sensor_data', {}).get('pressure')
    target_pressure = data.get('sensor_data', {}).get('target')
    
    if current_pressure is None:
        return jsonify({"error": "No pressure data provided"}), 400

    # PIDのセットポイント動的更新（必要に応じて）
    if target_pressure is not None and target_pressure != pid_controller.setpoint:
        pid_controller.setpoint = target_pressure

    # PID計算
    # simple_pid は update(current_value) を呼ぶと制御入力(操作量)を返す
    # ここでは「バルブ開度」を操作量とする
    # 注意: 圧力が低い -> バルブを開ける(値を大きくする) などの方向性は
    # PIDのゲインの符号またはロジックで調整が必要。
    # ここでは一般的なフィードバックとして計算し、必要なら符号反転等を検討してください。
    control_action = pid_controller(current_pressure)

    response = {
        "action": float(control_action),
        "p_term": float(pid_controller.components[0]),
        "i_term": float(pid_controller.components[1]),
        "d_term": float(pid_controller.components[2]),
        "error": float(target_pressure - current_pressure)
    }
    
    return jsonify(response)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)