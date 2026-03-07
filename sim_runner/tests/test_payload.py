import pytest

# Import the consolidated sim_runner package
from sim_runner.main import RemoteValveControlEnv


def make_dummy_env(control_mode='pressure'):
    env = RemoteValveControlEnv.__new__(RemoteValveControlEnv)
    env.control_mode = control_mode
    return env


def test_build_sensor_entry_pressure_mode():
    env = make_dummy_env(control_mode='pressure')
    loop_info = {'loop_id': 'loop_1', 'current_valve': 0.5}
    loop_config = {'target': {'target_pressure': 30.0, 'target_flow': 100.0}}
    measurements = {'measured_pressure': 127.5, 'flow': 42.0}

    entry = env._build_sensor_entry(loop_info, loop_config, measurements, step_count=0, current_time=0)

    assert entry['loop_id'] == 'loop_1'
    assert 'pressure' in entry and 'flow' in entry
    assert entry['pressure'] == 127.5
    assert entry['flow'] == 42.0
    assert entry['controlled_value'] == 127.5
    assert 'target' in entry and entry['target']['target_pressure'] == 30.0


def test_build_sensor_entry_flow_mode():
    env = make_dummy_env(control_mode='flow')
    loop_info = {'loop_id': 'loop_1', 'current_valve': 0.75}
    loop_config = {'target': {'target_pressure': 20.0, 'target_flow': 150.0}}
    measurements = {'measured_pressure': 110.0, 'flow': -12.5}

    entry = env._build_sensor_entry(loop_info, loop_config, measurements, step_count=5, current_time=3600)

    assert entry['loop_id'] == 'loop_1'
    assert entry['pressure'] == 110.0
    assert entry['flow'] == -12.5
    assert entry['controlled_value'] == -12.5
    assert entry['target']['target_flow'] == 150.0
    assert entry['prev_action'] == 0.75
