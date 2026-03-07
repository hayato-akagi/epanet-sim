import os
import tempfile
import importlib.util
import sys
import types

import numpy as np


def load_reward_calculator():
    base = os.getcwd()
    rpath = os.path.join(base, 'controller_vla', 'utils', 'reward.py')
    spec = importlib.util.spec_from_file_location('vla_reward', rpath)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.RewardCalculator


def load_vla_controller_class():
    base = os.getcwd()
    path = os.path.join(base, 'controller_vla', 'training', 'controller.py')

    # Mock torch to avoid heavy dependency
    if 'torch' not in sys.modules:
        mock_torch = types.ModuleType('torch')
        mock_torch.save = lambda *a, **k: None
        mock_torch.load = lambda *a, **k: {}
        sys.modules['torch'] = mock_torch

    # Lightweight stub for models.replay_buffer used by VLAController
    if 'models.replay_buffer' not in sys.modules:
        rb_mod = types.ModuleType('models.replay_buffer')
        class ReplayBuffer:
            def __init__(self, size=10000):
                self.buf = []
                self.size = size
            def add(self, *args, **kwargs):
                self.buf.append((args, kwargs))
            def sample(self, batch_size):
                return None
            def __len__(self):
                return len(self.buf)
        rb_mod.ReplayBuffer = ReplayBuffer
        sys.modules['models.replay_buffer'] = rb_mod

    # Ensure imports from controller_vla local package resolve
    controller_vla_dir = os.path.join(base, 'controller_vla')
    if controller_vla_dir not in sys.path:
        sys.path.insert(0, controller_vla_dir)

    spec = importlib.util.spec_from_file_location('vla_training_controller', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.VLAController


class DummyAgent:
    def select_action(self, images, prompt, deterministic=False):
        return 0.2


class DummyImageFetcher:
    def fetch(self, exp_id, step, sensor_data):
        return {}


class DummyPromptGenerator:
    def generate(self, sensor_data):
        return "p"


class DummyDataLogger:
    def __init__(self, url):
        self.url = url
    def send(self, payload):
        return True


class DummyVLAModel:
    def state_dict(self):
        return {}


class DummyTrainingLogger:
    def __init__(self, output_dir, exp_id):
        self.output_dir = output_dir
        self.exp_id = exp_id
        self.logged_episode = None
    def log_step(self, step_data):
        return None
    def log_episode(self, episode_data):
        self.logged_episode = episode_data
    def flush(self):
        pass


def test_reward_components_pressure_and_safety():
    RewardCalculator = load_reward_calculator()

    rc = RewardCalculator(tracking_weight=1.0, stability_weight=0.5,
                          safety_weight=10.0,
                          safety_bounds={'pressure_min': 90.0, 'pressure_max': 150.0},
                          normalize=False)

    # Case: within bounds
    res_ok = rc.calculate(current_pressure=100.0, target_pressure=110.0,
                          prev_pressure=101.0, valve_change=0.02, time_step=0)
    assert 'total_reward' in res_ok and 'tracking' in res_ok
    assert isinstance(res_ok['total_reward'], float)

    # Case: below safety bound triggers safety penalty
    res_bad = rc.calculate(current_pressure=50.0, target_pressure=110.0,
                           prev_pressure=60.0, valve_change=0.5, time_step=0)
    assert res_bad['safety'] < 0
    assert res_bad['total_reward'] == res_bad['tracking'] + res_bad['stability'] + res_bad['safety']


def test_episode_finish_and_logging():
    VLAController = load_vla_controller_class()
    tmpdir = tempfile.mkdtemp()

    controller = VLAController(
        loop_id='loop_test',
        vla_model=DummyVLAModel(),
        agent=DummyAgent(),
        reward_calculator=load_reward_calculator()(),
        image_fetcher=DummyImageFetcher(),
        prompt_generator=DummyPromptGenerator(),
        data_logger=DummyDataLogger('http://noop'),
        exp_id='exp_test',
        exp_result_dir=tmpdir,
        config={'exploration': {'initial_random_steps': 0}, 'training': {'learning_starts': 1000000}}
    )

    # Replace training_logger with dummy that records log_episode
    controller.training_logger = DummyTrainingLogger(tmpdir, 'exp_test')

    # Force agent path (so not random)
    controller.total_steps = 1000

    # First step: set prev_state
    s1 = {'pressure': 120.0, 'target': 130.0, 'prev_action': 0.1}
    a1 = controller.compute_action(sensor_data=s1, step=0, time_step=0, exp_id='x')

    # Second step: cause step() to be called and data added to episode_buffer
    s2 = {'pressure': 121.0, 'target': 130.0, 'prev_action': 0.1}
    a2 = controller.compute_action(sensor_data=s2, step=1, time_step=600, exp_id='x')

    # At least one item should be in episode_buffer
    assert len(controller.episode_buffer) >= 1

    # Call finish and ensure training_logger.log_episode was called and buffer cleared
    controller._finish_episode()
    assert controller.training_logger.logged_episode is not None
    assert len(controller.episode_buffer) == 0
