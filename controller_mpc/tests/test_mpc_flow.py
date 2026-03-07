from controller_mpc.app import app


def test_mpc_flow_mode_init_and_control():
    client = app.test_client()

    init_payload = {
        "init": True,
        "control_mode": "flow",
        "control_loops": [
            {
                "loop_id": "loop_1",
                "target": {"node_id": "2", "target_pressure": 30.0, "target_flow": 100.0},
                "actuator": {"link_id": "10", "initial_setting": 1.0, "min_setting": 0.0, "max_setting": 1.0},
                "mpc_params": {"horizon": 3, "dt": 300}
            }
        ]
    }

    r = client.post('/control', json=init_payload)
    assert r.status_code == 200
    data = r.get_json()
    assert data.get('status') == 'initialized'
    assert data.get('control_mode') == 'flow'

    control_payload = {
        "time_step": 0,
        "sensor_data": [
            {
                "loop_id": "loop_1",
                "pressure": 110.0,
                "flow": 50.0,
                "prev_action": 1.0,
                "step": 1
            }
        ]
    }

    r2 = client.post('/control', json=control_payload)
    assert r2.status_code == 200
    resp = r2.get_json()
    assert 'actions' in resp
    actions = resp['actions']
    assert len(actions) == 1
    a = actions[0]
    assert abs(a.get('current_value') - 50.0) < 1e-6
    assert 'output_limits' in a
    assert a['output_limits'][0] == 0.0
    assert a['output_limits'][1] == 1.0
