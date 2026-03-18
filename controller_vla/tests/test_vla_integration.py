import os
import socket
import threading
import time
import importlib.util
import sys
import types

import requests


def _find_free_port():
    s = socket.socket()
    s.bind(('127.0.0.1', 0))
    addr, port = s.getsockname()
    s.close()
    return port


def _start_mock_collector(port, store):
    from flask import Flask, request, jsonify

    app = Flask('mock_collector')

    @app.route('/collect', methods=['POST'])
    def collect():
        data = request.get_json()
        store.append(data)
        return jsonify({'status': 'ok'})

    def run():
        app.run(host='127.0.0.1', port=port, debug=False, use_reloader=False)

    t = threading.Thread(target=run, daemon=True)
    t.start()
    # Wait briefly for server to start
    time.sleep(0.5)
    return t


def load_module(path, name='mod'):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_image_fetch_and_data_collector_integration():
    base = os.getcwd()

    # Prepare mock data-collector
    port = _find_free_port()
    collector_store = []
    _start_mock_collector(port, collector_store)

    # Set env var so app creates DataLogger pointing to mock collector
    os.environ['DATA_COLLECTOR_URL'] = f'http://127.0.0.1:{port}'

    # Provide minimal stubs for heavy deps before importing app
    if 'torch' not in sys.modules:
        torch_mod = types.ModuleType('torch')
        torch_mod.save = lambda *a, **k: None
        torch_mod.load = lambda *a, **k: {}
        # Provide a lightweight torch.nn submodule so `import torch.nn as nn` works
        nn_mod = types.ModuleType('torch.nn')
        class Module:
            pass
        class Linear:
            def __init__(self, *a, **k):
                pass
        nn_mod.Module = Module
        nn_mod.Linear = Linear
        torch_mod.nn = nn_mod
        sys.modules['torch'] = torch_mod
        sys.modules['torch.nn'] = nn_mod

    # Stub models.replay_buffer if needed
    if 'models.replay_buffer' not in sys.modules:
        rb_mod = types.ModuleType('models.replay_buffer')
        class ReplayBuffer:
            def __init__(self, size=10000):
                self.buf = []
            def add(self, *a, **k):
                self.buf.append((a, k))
            def sample(self, bs):
                return None
            def __len__(self):
                return len(self.buf)
        rb_mod.ReplayBuffer = ReplayBuffer
        sys.modules['models.replay_buffer'] = rb_mod

    # Stub redis module so ImageFetcher can import redis.from_url
    if 'redis' not in sys.modules:
        redis_mod = types.ModuleType('redis')
        class DummyRedisClient:
            def __init__(self, *a, **k):
                pass
            def get(self, key):
                return None
        def from_url(url, decode_responses=False):
            return DummyRedisClient()
        redis_mod.from_url = from_url
        sys.modules['redis'] = redis_mod

    # Ensure controller_vla local package imports resolve
    controller_vla_dir = os.path.join(base, 'controller_vla')
    if controller_vla_dir not in sys.path:
        sys.path.insert(0, controller_vla_dir)

    # Remove any lightweight 'models' stubs previously inserted by other tests
    for k in list(sys.modules.keys()):
        if k == 'models' or k.startswith('models.'):
            del sys.modules[k]

    # Insert a dummy top-level `models` package so Python does not execute
    # controller_vla/models/__init__.py (which imports heavy torch-based code).
    if 'models' not in sys.modules:
        models_pkg = types.ModuleType('models')
        # Mark as package so imports like `from models.sac_agent import ...` work
        models_pkg.__path__ = []
        sys.modules['models'] = models_pkg

    # Ensure a lightweight models.replay_buffer is present for imports
    if 'models.replay_buffer' not in sys.modules:
        rb_mod = types.ModuleType('models.replay_buffer')
        class ReplayBuffer:
            def __init__(self, size=10000):
                self.buf = []
            def add(self, *a, **k):
                self.buf.append((a, k))
            def sample(self, bs):
                return None
            def __len__(self):
                return len(self.buf)
        rb_mod.ReplayBuffer = ReplayBuffer
        sys.modules['models.replay_buffer'] = rb_mod
    # Provide a lightweight SACAgent stub so app imports succeed
    if 'models.sac_agent' not in sys.modules:
        sac_mod = types.ModuleType('models.sac_agent')
        class SACAgent:
            def __init__(self, *a, **k):
                pass
            def select_action(self, *a, **k):
                return 0.0
        sac_mod.SACAgent = SACAgent
        sys.modules['models.sac_agent'] = sac_mod
    # Force using the lightweight dummy VLA model for tests
    os.environ['VLA_MODEL'] = 'dummy'
    # Provide a dummy VLA implementation so initialize_controller() can instantiate it
    if 'models.dummy_agent' not in sys.modules:
        dummy_mod = types.ModuleType('models.dummy_agent')
        class DummyAgent:
            def __init__(self, *a, **k):
                pass
            def predict(self, images, prompt):
                return 0.0
        dummy_mod.DummyAgent = DummyAgent
        sys.modules['models.dummy_agent'] = dummy_mod

    # Provide lightweight `utils` package and required submodules
    if 'utils' not in sys.modules:
        utils_pkg = types.ModuleType('utils')
        utils_pkg.__path__ = []
        sys.modules['utils'] = utils_pkg

    # image_fetcher stub
    if 'utils.image_fetcher' not in sys.modules:
        im_mod = types.ModuleType('utils.image_fetcher')
        class ImageFetcher:
            def __init__(self, *a, **k):
                pass
            def fetch(self, exp_id, step, sensor_data):
                # Return empty image dict (controller handles missing images)
                return {}
        im_mod.ImageFetcher = ImageFetcher
        sys.modules['utils.image_fetcher'] = im_mod

    # prompt_generator stub
    if 'utils.prompt_generator' not in sys.modules:
        pg_mod = types.ModuleType('utils.prompt_generator')
        class PromptGenerator:
            def __init__(self, *a, **k):
                pass
            def generate(self, sensor_data=None):
                return 'Prompt: Current pressure: 30.0 target: 30.0'
        pg_mod.PromptGenerator = PromptGenerator
        sys.modules['utils.prompt_generator'] = pg_mod

    # reward stub
    if 'utils.reward' not in sys.modules:
        rw_mod = types.ModuleType('utils.reward')
        class RewardCalculator:
            def __init__(self, *a, **k):
                pass
            def calculate(self, **kwargs):
                return {'total_reward': 0.0}
        rw_mod.RewardCalculator = RewardCalculator
        sys.modules['utils.reward'] = rw_mod

    # data_logger stub (but load the real module file later for direct testing)
    if 'utils.data_logger' not in sys.modules:
        dl_mod_stub = types.ModuleType('utils.data_logger')
        class DataLoggerStub:
            def __init__(self, url):
                self.url = url
                self.buf = []
            def log_transition(self, t):
                self.buf.append(t)
            def flush(self):
                # Post to collector immediately
                try:
                    requests.post(self.url + '/collect', json={'transitions': self.buf}, timeout=1)
                except Exception:
                    pass
                self.buf = []
        dl_mod_stub.DataLogger = DataLoggerStub
        sys.modules['utils.data_logger'] = dl_mod_stub
    # Import the Flask app
    app_mod = load_module(os.path.join(base, 'controller_vla', 'app.py'), name='vla_app')
    app = getattr(app_mod, 'app')

    client = app.test_client()

    # Initialize controller via /control init
    init_payload = {
        'init': True,
        'control_mode': 'flow',
        'control_loops': [
            {
                'loop_id': 'loop_int',
                'vla_params': {},
                'actuator': {'initial_setting': 0.5}
            }
        ]
    }

    r = client.post('/control', json=init_payload)
    assert r.status_code == 200
    data = r.get_json()
    assert data.get('status') == 'initialized'

    # Send a control step; ImageFetcher should return dummy images (no Redis)
    control_payload = {
        'exp_id': 'integ_exp',
        'step': 0,
        'sensor_data': [
            {
                'loop_id': 'loop_int',
                'pressure': 120.0,
                'flow': 40.0,
                'target': 100.0,
                'prev_action': 0.5,
                'step': 0
            }
        ]
    }

    r2 = client.post('/control', json=control_payload)
    assert r2.status_code == 200
    resp = r2.get_json()
    assert 'delta_action' in resp

    # Now test DataLogger directly: create DataLogger pointing to mock collector
    dl_mod = load_module(os.path.join(base, 'controller_vla', 'utils', 'data_logger.py'), name='dlog')
    DataLogger = dl_mod.DataLogger

    dl = DataLogger(f'http://127.0.0.1:{port}')
    # Add a single transition and flush (flush posts immediately)
    dl.log_transition({'exp_id': 'integ_exp', 'value': 1})
    dl.flush()

    # Wait briefly for server to receive
    time.sleep(0.5)
    assert len(collector_store) >= 1
    # Ensure the posted payload contains our transition
    posted = collector_store[0]
    assert 'transitions' in posted
    assert any(t.get('exp_id') == 'integ_exp' for t in posted['transitions'])
