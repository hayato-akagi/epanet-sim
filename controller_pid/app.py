"""
controller_pid/app.py

Modified to support:
1. Initialization requests from sim_runner
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
pid_controllers = {}  # loop_id -> { 'pid': PID instance, 'min': float, 'max': float }
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
        actuator_config = loop.get('actuator', {})

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

        # Determine actuator limits (prefer explicit actuator config)
        min_setting = actuator_config.get('min_setting', actuator_config.get('min', 0.0))
        max_setting = actuator_config.get('max_setting', actuator_config.get('max', 1.0))

        pid.output_limits = (min_setting, max_setting)

        pid_controllers[loop_id] = {
            'pid': pid,
            'min': min_setting,
            'max': max_setting,
            'target': default_setpoint
        }


@app.route('/control', methods=['POST'])
def control():
    global pid_controllers, control_mode, current_episode

    data = request.json

    # Initialization
    if data.get('init', False):
        loops = data.get('control_loops', [])
        mode = data.get('control_mode', 'pressure')
        initialize_controllers(loops, mode=mode)
        current_episode += 1
        return jsonify({
            "status": "initialized",
            "episode": current_episode,
            "control_mode": control_mode,
            "num_loops": len(pid_controllers),
            "controller_type": "batch"
        })

    # Control step
    exp_id = data.get('exp_id')
    step = data.get('step', 0)
    sensor_list = data.get('sensor_data', [])
    responses = []

    for s in sensor_list:
        loop_id = s.get('loop_id')
        controller = pid_controllers.get(loop_id)
        if controller is None:
            responses.append({'loop_id': loop_id, 'error': 'not_initialized'})
            continue

        # Determine current value based on control_mode
        if control_mode == 'flow':
            current_value = s.get('flow', s.get('pressure'))
            target = s.get('target', {}).get('target_flow', controller['target']) if isinstance(s.get('target'), dict) else s.get('target', controller['target'])
        else:
            current_value = s.get('pressure')
            target = s.get('target', {}).get('target_pressure', controller['target']) if isinstance(s.get('target'), dict) else s.get('target', controller['target'])

        controller['pid'].setpoint = target
        output = controller['pid'](current_value)
        # clip
        output = max(controller['min'], min(controller['max'], output))

        responses.append({
            'loop_id': loop_id,
            'action': float(output),
            'control_mode': control_mode,
            'current_value': float(current_value) if current_value is not None else None,
            'target_value': float(target) if target is not None else None,
            'output_limits': [controller.get('min'), controller.get('max')]
        })

    return jsonify({'actions': responses})


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
