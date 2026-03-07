"""
controller_mpc/app.py

Modified to support:
1. Initialization requests from sim_runner
2. New payload format: {"time_step": ..., "sensor_data": [...]}
3. Multi-episode execution
4. Enhanced debug logging
"""
import numpy as np
from flask import Flask, request, jsonify
from scipy.optimize import minimize

app = Flask(__name__)

# グローバル変数: 各ループ用のMPC状態を辞書で管理
mpc_states = {}  # loop_id -> {"last_u": ..., "config": ..., "mode": ..., "actuator_bounds": (min,max)}
control_mode = None
current_episode = 0  # エピソードカウンタ


def predict_trajectory(u_sequence, current_y, A, B, horizon):
    predictions = []
    y = current_y
    for u in u_sequence:
        y = A * y + B * u
        predictions.append(y)
    return np.array(predictions)


def cost_function(u_sequence, current_y, target, last_val_u, A, B, horizon, weight_error, weight_du):
    preds = predict_trajectory(u_sequence, current_y, A, B, horizon)
    error_cost = np.sum((preds - target) ** 2) * weight_error
    u_diffs = np.diff(np.concatenate(([last_val_u], u_sequence)))
    du_cost = np.sum(u_diffs ** 2) * weight_du
    return error_cost + du_cost


def initialize_mpc_controllers(loops, mode='pressure'):
    global mpc_states, control_mode
    control_mode = mode
    mpc_states = {}
    for loop in loops:
        loop_id = loop.get('loop_id', 'default')
        params = loop.get('mpc_params', {})
        actuator_config = loop.get('actuator', {})

        default_config = {
            "horizon": params.get('horizon', 10),
            "dt": params.get('dt', 300),
            "tau": params.get('tau', 600.0),
            "K": params.get('K', 10.0),
            "weight_error": params.get('weight_error', 1.0),
            "weight_du": params.get('weight_du', 0.5)
        }

        min_setting = actuator_config.get('min_setting', actuator_config.get('min', 0.0))
        max_setting = actuator_config.get('max_setting', actuator_config.get('max', 1.0))

        mpc_states[loop_id] = {
            'config': default_config,
            'last_u': 0.0,
            'actuator_bounds': (min_setting, max_setting),
            'target': default_config.get('target', 0.0)
        }


@app.route('/control', methods=['POST'])
def control():
    global mpc_states, control_mode, current_episode
    data = request.json

    if data.get('init', False):
        loops = data.get('control_loops', [])
        mode = data.get('control_mode', 'pressure')
        initialize_mpc_controllers(loops, mode=mode)
        current_episode += 1
        return jsonify({
            "status": "initialized",
            "episode": current_episode,
            "control_mode": control_mode,
            "num_loops": len(mpc_states),
            "controller_type": "batch"
        })

    exp_id = data.get('exp_id')
    step = data.get('step', 0)
    results = []
    for s in data.get('sensor_data', []):
        loop_id = s.get('loop_id')
        state = mpc_states.get(loop_id)
        if state is None:
            results.append({'loop_id': loop_id, 'error': 'not_initialized'})
            continue

        if control_mode == 'flow':
            current_value = s.get('flow', s.get('pressure'))
            target = s.get('target', {}).get('target_flow', state.get('target')) if isinstance(s.get('target'), dict) else s.get('target', state.get('target'))
        else:
            current_value = s.get('pressure')
            target = s.get('target', {}).get('target_pressure', state.get('target')) if isinstance(s.get('target'), dict) else s.get('target', state.get('target'))

        cfg = state['config']
        horizon = cfg['horizon']
        A = 1.0 - cfg.get('dt', 300) / cfg.get('tau', 600.0)
        B = cfg.get('K', 10.0)

        # Initial guess
        u0 = np.full(horizon, state['last_u'])
        bounds = [(state['actuator_bounds'][0], state['actuator_bounds'][1])] * horizon

        res = minimize(
            lambda u: cost_function(u, current_value, target, state['last_u'], A, B, horizon, cfg['weight_error'], cfg['weight_du']),
            u0,
            bounds=bounds
        )

        u_opt = res.x[0] if res.success else state['last_u']
        state['last_u'] = u_opt
        results.append({
            'loop_id': loop_id,
            'action': float(u_opt),
            'control_mode': control_mode,
            'current_value': float(current_value) if current_value is not None else None,
            'target_value': float(target) if target is not None else None,
            'output_limits': list(state.get('actuator_bounds', (0.0, 1.0)))
        })

    return jsonify({'actions': results})


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
