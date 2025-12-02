import os
import json
from flask import Flask, request, jsonify
from simple_pid import PID

app = Flask(__name__)

# グローバル変数: 各ループ用のPIDコントローラを辞書で管理
pid_controllers = {}  # loop_id -> PID instance
control_mode = None  # 'pressure' または 'flow'

def initialize_controllers(loops, mode='pressure'):
    """複数の制御ループに対してPIDコントローラを初期化"""
    global pid_controllers, control_mode
    
    control_mode = mode
    pid_controllers = {}
    
    for loop in loops:
        loop_id = loop.get('loop_id', 'default')
        params = loop.get('pid_params', {})
        target_config = loop.get('target', {})
        
        # 制御モードに応じたデフォルトパラメータの選択
        if mode == 'flow':
            # 流量制御用のデフォルトゲイン
            default_kp = params.get('kp_flow', params.get('Kp', params.get('kp', 0.01)))
            default_ki = params.get('ki_flow', params.get('Ki', params.get('ki', 0.001)))
            default_kd = params.get('kd_flow', params.get('Kd', params.get('kd', 0.02)))
            default_setpoint = params.get('setpoint_flow', target_config.get('target_flow', 100.0))
        else:  # pressure
            default_kp = params.get('Kp', params.get('kp', 1.0))
            default_ki = params.get('Ki', params.get('ki', 0.1))
            default_kd = params.get('Kd', params.get('kd', 0.05))
            default_setpoint = params.get('setpoint', target_config.get('target_pressure', 30.0))
        
        # PID(Kp, Ki, Kd, setpoint)
        pid = PID(
            default_kp,
            default_ki,
            default_kd,
            setpoint=default_setpoint
        )
        
        # 出力制限（バルブ開度は 0.0 ～ 1.0 の範囲）
        pid.output_limits = (0.1, 1.0)
        
        pid_controllers[loop_id] = pid
        
        print(f"PID Controller Initialized for Loop '{loop_id}':")
        print(f"  Mode: {control_mode}")
        print(f"  Kp={default_kp}, Ki={default_ki}, Kd={default_kd}")
        print(f"  Setpoint={default_setpoint}")
    
    print(f"Total {len(pid_controllers)} PID controllers initialized")

@app.route('/control', methods=['POST'])
def control():
    """
    制御計算エンドポイント
    複数の制御ループに対してPID計算を行う
    """
    global pid_controllers, control_mode
    
    data = request.json
    
    # 初期化リクエストの確認
    if data.get('init', False):
        loops = data.get('control_loops', [])
        mode = data.get('control_mode', 'pressure')  # デフォルトは圧力制御
        
        # 後方互換性: 旧形式の場合
        if not loops:
            loops = [{
                "loop_id": "default",
                "target": {"target_pressure": 30.0, "target_flow": 100.0},
                "actuator": {"initial_setting": 1.0},
                "pid_params": data.get('pid_params', {})
            }]
        
        initialize_controllers(loops, mode)
        
        return jsonify({
            "status": "initialized",
            "control_mode": control_mode,
            "num_loops": len(pid_controllers)
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
        
        if loop_id not in pid_controllers:
            print(f"Warning: Controller not found for loop '{loop_id}'")
            actions.append({
                "loop_id": loop_id,
                "action": 0.5,
                "error": "Controller not initialized",
                "p_term": 0.0,
                "i_term": 0.0,
                "d_term": 0.0
            })
            continue
        
        if current_value is None:
            actions.append({
                "loop_id": loop_id,
                "action": 0.5,
                "error": "No sensor value",
                "p_term": 0.0,
                "i_term": 0.0,
                "d_term": 0.0
            })
            continue
        
        pid = pid_controllers[loop_id]
        
        # PIDのセットポイント動的更新（必要に応じて）
        if target_value is not None and target_value != pid.setpoint:
            pid.setpoint = target_value
        
        # PID計算
        control_action = pid(current_value)
        
        # エラー計算
        error = target_value - current_value if target_value is not None else 0.0
        
        actions.append({
            "loop_id": loop_id,
            "action": float(control_action),
            "p_term": float(pid.components[0]),
            "i_term": float(pid.components[1]),
            "d_term": float(pid.components[2]),
            "error": float(error),
            "control_mode": control_mode,
            "current_value": float(current_value),
            "target_value": float(target_value) if target_value is not None else None
        })
    
    return jsonify({"actions": actions})

@app.route('/status', methods=['GET'])
def status():
    """コントローラーの状態を返す（デバッグ用）"""
    global pid_controllers, control_mode
    
    if not pid_controllers:
        return jsonify({
            "status": "not_initialized",
            "control_mode": None,
            "num_loops": 0
        })
    
    controllers_info = {}
    for loop_id, pid in pid_controllers.items():
        controllers_info[loop_id] = {
            "setpoint": pid.setpoint,
            "kp": pid.Kp,
            "ki": pid.Ki,
            "kd": pid.Kd,
            "output_limits": pid.output_limits
        }
    
    return jsonify({
        "status": "active",
        "control_mode": control_mode,
        "num_loops": len(pid_controllers),
        "controllers": controllers_info
    })

@app.route('/reset', methods=['POST'])
def reset():
    """PIDコントローラーをリセット"""
    global pid_controllers, control_mode
    
    pid_controllers = {}
    control_mode = None
    
    return jsonify({
        "status": "reset",
        "message": "All PID controllers have been reset"
    })

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)