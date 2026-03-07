import os
import tempfile
import importlib.util
import sys
import types

import numpy as np


def load_vla_controller_class():
    # Load training/controller.py from controller_vla using importlib
    base = os.getcwd()
    path = os.path.join(base, 'controller_vla', 'training', 'controller.py')
    # Ensure torch is available (mock) so the module can be imported in test env
    if 'torch' not in sys.modules:
        mock_torch = types.ModuleType('torch')
        def _mock_save(obj, filepath):
            return None
        def _mock_load(filepath):
            return {}
        mock_torch.save = _mock_save
        mock_torch.load = _mock_load
        sys.modules['torch'] = mock_torch

    # Provide lightweight stubs for local packages used by the controller to
    # avoid importing heavy ML dependencies (torch) and full model modules.
    # Stub: models.replay_buffer.ReplayBuffer
    if 'models' not in sys.modules:
        sys.modules['models'] = types.ModuleType('models')
    if 'models.replay_buffer' not in sys.modules:
        rb_mod = types.ModuleType('models.replay_buffer')
        class ReplayBuffer:
            def __init__(self, size=10000):
                self.buf = []
                self.size = size
            def add(self, *args, **kwargs):
                self.buf.append((args, kwargs))
                if len(self.buf) > self.size:
                    self.buf.pop(0)
            def sample(self, batch_size):
                if len(self.buf) < batch_size:
                    return None
                return self.buf[:batch_size]
            def __len__(self):
                return len(self.buf)
        rb_mod.ReplayBuffer = ReplayBuffer
        sys.modules['models.replay_buffer'] = rb_mod

    # Stub: utils.training_logger.TrainingLogger
    if 'utils' not in sys.modules:
        sys.modules['utils'] = types.ModuleType('utils')
    if 'utils.training_logger' not in sys.modules:
        tl_mod = types.ModuleType('utils.training_logger')
        class TrainingLogger:
            def __init__(self, output_dir, exp_id):
                self.output_dir = output_dir
                self.exp_id = exp_id
            def log_step(self, step_data):
                return None
            def log_episode(self, episode_data):
                return None
            def flush(self):
                return None
        tl_mod.TrainingLogger = TrainingLogger
        sys.modules['utils.training_logger'] = tl_mod

    spec = importlib.util.spec_from_file_location('vla_training_controller', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.VLAController


def load_reward_calculator():
    base = os.getcwd()
    rpath = os.path.join(base, 'controller_vla', 'utils', 'reward.py')
    spec = importlib.util.spec_from_file_location('vla_reward', rpath)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.RewardCalculator


class DummyAgent:
    def select_action(self, images, prompt, deterministic=False):
        return 0.12345


class DummyImageFetcher:
    def fetch(self, exp_id, step, sensor_data):
        return {}


class DummyPromptGenerator:
    def generate(self, sensor_data):
        return "short prompt"


class DummyDataLogger:
    def __init__(self, url):
        self.url = url

    def send(self, payload):
        return True


class DummyVLAModel:
    def state_dict(self):
        return {}


def test_vla_flow_mode_mapping():
    VLAController = load_vla_controller_class()

    # Build minimal config to ensure agent path is used
    config = {
        'exploration': {'initial_random_steps': 0},
        'training': {'learning_starts': 1000000},
        'action': {'delta_range': [-0.1, 0.1]}
    }

    tmpdir = tempfile.mkdtemp()

    RewardCalculator = load_reward_calculator()

    controller = VLAController(
        loop_id='loop_1',
        vla_model=DummyVLAModel(),
        agent=DummyAgent(),
        reward_calculator=RewardCalculator(),
        image_fetcher=DummyImageFetcher(),
        prompt_generator=DummyPromptGenerator(),
        data_logger=DummyDataLogger('http://noop'),
        exp_id='test_exp',
        exp_result_dir=tmpdir,
        config=config
    )

    # Ensure total_steps is high so agent is used (exploration.initial_random_steps == 0)
    controller.total_steps = 1000

    # First call: set prev_state
    sensor_data_1 = {'pressure': 120.0, 'target': 130.0, 'prev_action': 0.5}
    a1 = controller.compute_action(sensor_data=sensor_data_1, step=0, time_step=0, exp_id='test')
    assert isinstance(a1, float) or isinstance(a1, (int, np.number))

    # Second call: provide flow-mode payload
    sensor_data_flow = {
        'flow': 55.0,
        'target': {'target_flow': 100.0},
        'prev_action': 0.5
    }

    a2 = controller.compute_action(sensor_data=sensor_data_flow, step=1, time_step=600, exp_id='test')
    assert isinstance(a2, float) or isinstance(a2, (int, np.number))

    # After compute_action, controller.prev_state should map flow into 'pressure' key
    assert controller.prev_state['pressure'] == sensor_data_flow['flow']
    assert controller.prev_state['target'] == sensor_data_flow['target']['target_flow']
