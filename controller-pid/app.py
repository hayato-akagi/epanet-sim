"""
controller-pid/app.py (修正版)

Modified to support:
1. Initialization requests from sim-runner
2. New payload format: {"time_step": ..., "sensor_data": [...]}
3. Multi-episode execution
4. Enhanced debug logging
"""
import os
import json
from flask import Flask, request, jsonify
from simple_pid import PID

app = Flask(__name__)

# グローバル変数: 各ループ用のPIDコントローラを辞書で管理
pid_controllers = {}  # loop_id -> PID instance
control_mode = None  # 'pressure' または 'flow'
current_episode = 0  # エピソードカウンタ


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
    
    2つのモード:
    1. 初期化モード: {"init": true, "control_loops": [...], "control_mode": "..."}
    2. 制御モード: {"time_step": ..., "sensor_data": [...]}
    """
    global pid_controllers, control_mode, current_episode
    
    data = request.json
    
    # ========================================
    # Mode 1: Initialization Request
    # ========================================
    if data.get('init', False):
        print("\n" + "=" * 70)
        print(f"📋 INITIALIZATION REQUEST RECEIVED (Episode {current_episode + 1})")
        print("=" * 70)
        
        # Reset PID controllers for new episode
        if pid_controllers:
            print(f"🔚 Resetting previous episode {current_episode}...")
            for loop_id, pid in pid_controllers.items():
                # Reset PID internal state
                pid._integral = 0.0
                pid._last_input = None
                print(f"   Reset {loop_id} PID state")
        
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
                "pid_params": data.get('pid_params', {})
            }]
        
        # Initialize or reset controllers
        initialize_controllers(loops, mode)
        
        print(f"\n✅ Episode {current_episode} initialized successfully!")
        print("=" * 70)
        print()
        
        return jsonify({
            "status": "initialized",
            "episode": current_episode,
            "control_mode": control_mode,
            "num_loops": len(pid_controllers),
            "controller_type": "batch"  # PID is batch-style controller
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
            print(f"\n[DEBUG] PID control request at t={time_step}")
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
            
            if loop_id not in pid_controllers:
                print(f"⚠️  WARNING: Controller not found for loop '{loop_id}'")
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
                print(f"⚠️  WARNING: No sensor value for loop '{loop_id}'")
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
            
            # Log every 50 steps
            step = sensor_data.get('step', time_step // 600)
            if step % 50 == 0 and step > 0:
                print(f"   Step {step}: loop={loop_id}, error={error:.2f}, action={control_action:.4f}")
            
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
    global pid_controllers, control_mode, current_episode
    
    if not pid_controllers:
        return jsonify({
            "status": "not_initialized",
            "control_mode": None,
            "current_episode": current_episode,
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
        "current_episode": current_episode,
        "num_loops": len(pid_controllers),
        "controllers": controllers_info
    })


@app.route('/reset', methods=['POST'])
def reset():
    """PIDコントローラーをリセット"""
    global pid_controllers, control_mode
    
    print("\n🔄 Manual reset requested")
    
    for loop_id, pid in pid_controllers.items():
        pid._integral = 0.0
        pid._last_input = None
        print(f"   Reset {loop_id} PID state")
    
    print("✓ All PID controllers reset\n")
    
    return jsonify({
        "status": "reset",
        "message": "All PID controllers have been reset"
    })


@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint"""
    return jsonify({
        "status": "ok",
        "service": "controller-pid"
    })


if __name__ == '__main__':
    print("\n" + "=" * 70)
    print("🚀 PID Controller Service Starting")
    print("=" * 70)
    print()
    
    print("📋 Configuration:")
    print(f"   Service: PID Controller")
    print(f"   Port: 5000")
    print()
    
    print("🌐 Starting Flask app on 0.0.0.0:5000")
    print("=" * 70)
    print()
    
    app.run(host='0.0.0.0', port=5000)