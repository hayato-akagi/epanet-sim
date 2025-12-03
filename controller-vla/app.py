"""
VLA Controller Flask Application
Modified to support:
1. Initialization requests from sim-runner
2. Automatic episode tracking
3. Multi-episode execution
"""
import os
import sys
import time
from flask import Flask, request, jsonify

# Debug: Check environment and imports
print("=" * 60)
print("STARTING CONTROLLER-VLA")
print("=" * 60)
print(f"Python version: {sys.version}")
print(f"Working directory: {os.getcwd()}")
print(f"Python path: {sys.path}")
print("=" * 60)

try:
    from flask import Flask
    print("✓ Flask imported successfully")
except ImportError as e:
    print(f"✗ Failed to import Flask: {e}")
    sys.exit(1)

# Import VLAController with debug info
print("\n[DEBUG] Checking training module...")
training_dir = os.path.join(os.getcwd(), 'training')
print(f"  training dir exists: {os.path.exists(training_dir)}")
print(f"  training/__init__.py exists: {os.path.exists(os.path.join(training_dir, '__init__.py'))}")
print(f"  training/controller.py exists: {os.path.exists(os.path.join(training_dir, 'controller.py'))}")
if os.path.exists(training_dir):
    print(f"  training/ contents: {os.listdir(training_dir)}")

print("\n[DEBUG] Checking dependencies...")
models_dir = os.path.join(os.getcwd(), 'models')
utils_dir = os.path.join(os.getcwd(), 'utils')
print(f"  models dir exists: {os.path.exists(models_dir)}")
print(f"  utils dir exists: {os.path.exists(utils_dir)}")
if os.path.exists(models_dir):
    print(f"  models/ contents: {os.listdir(models_dir)}")
if os.path.exists(utils_dir):
    print(f"  utils/ contents: {os.listdir(utils_dir)}")

print("\n[DEBUG] Attempting to import VLAController...")
try:
    from training.controller import VLAController
    print("✓ VLAController imported successfully")
except ImportError as e:
    print(f"✗ Failed to import VLAController: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Create Flask app
app = Flask(__name__)
print("✓ Flask app created")

# Configuration
EXP_ID = os.environ.get('EXP_ID', f'vla_exp_{int(time.time())}')
OUTPUT_PATH = os.environ.get('OUTPUT_PATH', '/shared/results')
REDIS_URL = os.environ.get('REDIS_URL', 'redis://redis:6379')
IMAGE_GENERATOR_URL = os.environ.get('IMAGE_GENERATOR_URL', 'http://image-generator:5000')
DATA_COLLECTOR_URL = os.environ.get('DATA_COLLECTOR_URL', 'http://data-collector:5000')
VLA_MODEL = os.environ.get('VLA_MODEL', 'simple_dnn')
VLA_CHECKPOINT = os.environ.get('VLA_CHECKPOINT', '')

print("\n" + "=" * 60)
print("EXPERIMENT CONFIGURATION")
print("=" * 60)
print(f"EXP_ID: {EXP_ID}")
print(f"OUTPUT_PATH: {OUTPUT_PATH}")
print(f"Result directory: {os.path.join(OUTPUT_PATH, EXP_ID)}")
print("=" * 60)
print()

# Create result directory
exp_result_dir = os.path.join(OUTPUT_PATH, EXP_ID)
os.makedirs(exp_result_dir, exist_ok=True)

# Initialize VLA controllers (will be populated when receiving first control request)
vla_controllers = {}
current_episode = 0  # グローバルエピソードカウンタ

# Import required modules
import time
import redis
import requests
from models.simple_dnn_vla import SimpleDNNVLA
from models.sac_agent import SACAgent
from utils.image_fetcher import ImageFetcher
from utils.prompt_generator import PromptGenerator
from utils.reward import RewardCalculator
from utils.data_logger import DataLogger


def initialize_controller(loop_id, loop_config):
    """Initialize VLA controller for a control loop"""
    
    # Initialize VLA model
    if VLA_MODEL == 'simple_dnn':
        vla_model = SimpleDNNVLA()
        print("Initialized SimpleDNN VLA Model")
    elif VLA_MODEL == 'dummy':
        from models.dummy_agent import DummyVLA
        vla_model = DummyVLA()
        print("Initialized Dummy VLA Model")
    else:
        raise ValueError(f"Unknown VLA model: {VLA_MODEL}")
    
    # Extract VLA parameters
    vla_params = loop_config.get('vla_params', {})
    
    # Initialize SAC agent
    agent = SACAgent(config=vla_params)
    print("SAC Agent initialized")
    
    # Initialize utilities
    image_fetcher = ImageFetcher(
        redis_url=REDIS_URL,
        image_generator_url=IMAGE_GENERATOR_URL
    )
    
    prompt_generator = PromptGenerator()
    
    reward_config = vla_params.get('reward', {})
    reward_calculator = RewardCalculator(
        tracking_weight=reward_config.get('tracking_weight', 1.0),
        stability_weight=reward_config.get('stability_weight', 0.5),
        safety_weight=reward_config.get('safety_weight', 10.0),
        safety_bounds=reward_config.get('safety_bounds', {}),
        normalize=reward_config.get('normalize', True),
        clip_range=reward_config.get('clip_range', [-10, 10])
    )
    
    data_logger = DataLogger(DATA_COLLECTOR_URL)
    print(f"DataLogger initialized: {DATA_COLLECTOR_URL}")
    
    # Initialize VLA controller
    controller = VLAController(
        loop_id=loop_id,
        vla_model=vla_model,
        agent=agent,
        reward_calculator=reward_calculator,
        image_fetcher=image_fetcher,
        prompt_generator=prompt_generator,
        data_logger=data_logger,
        exp_id=EXP_ID,
        exp_result_dir=exp_result_dir,
        config=vla_params
    )
    
    # Load checkpoint if specified
    if VLA_CHECKPOINT and os.path.exists(VLA_CHECKPOINT):
        controller.load_checkpoint(VLA_CHECKPOINT)
    
    print(f"VLA Controller Initialized for Loop '{loop_id}':")
    print(f"  Model: {VLA_MODEL}")
    print(f"  Learning Mode: {vla_params.get('learning_mode', 'online')}")
    print(f"  Experiment ID: {EXP_ID}")
    
    return controller


@app.route('/control', methods=['POST'])
def control():
    """
    Handle control request from sim-runner
    
    Supports two modes:
    1. Initialization: {"init": true, "control_loops": [...], "control_mode": "..."}
    2. Control step: {"loop_id": "...", "pressure": ..., "target": ..., ...}
    """
    global vla_controllers, current_episode
    
    data = request.json
    
    # ========================================
    # Mode 1: Initialization Request
    # ========================================
    if data.get('init', False):
        print("\n" + "=" * 70)
        print(f"📋 INITIALIZATION REQUEST RECEIVED (Episode {current_episode + 1})")
        print("=" * 70)
        
        # Finalize previous episode for all controllers
        if vla_controllers:
            print(f"🔚 Finalizing previous episode {current_episode}...")
            for loop_id, controller in vla_controllers.items():
                try:
                    # Force episode completion if there's data in buffer
                    if len(controller.episode_buffer) > 0:
                        print(f"   Finalizing {loop_id} (buffer size: {len(controller.episode_buffer)})")
                        controller._finish_episode()
                except Exception as e:
                    print(f"   ⚠ Error finalizing {loop_id}: {e}")
            
            print("✓ Previous episode finalized")
        
        # Increment episode counter
        current_episode += 1
        print(f"🎬 Starting Episode {current_episode}")
        
        # Get control loops from initialization data
        control_loops = data.get('control_loops', [])
        control_mode = data.get('control_mode', 'pressure')
        
        print(f"⚙️  Control mode: {control_mode}")
        print(f"🔄 Number of loops: {len(control_loops)}")
        
        # Initialize or reset controllers for each loop
        for loop_data in control_loops:
            loop_id = loop_data.get('loop_id', 'default')
            print(f"\n   Initializing loop: {loop_id}")
            
            # Build loop config from loop_data
            loop_config = {
                'vla_params': loop_data.get('vla_params', {
                    'model_type': VLA_MODEL,
                    'learning_mode': 'online',
                    'training': {
                        'buffer_size': 10000,
                        'batch_size': 32,
                        'learning_starts': 100,
                        'learning_rate_actor': 0.0003,
                        'learning_rate_critic': 0.0003,
                        'learning_rate_alpha': 0.0003,
                        'gamma': 0.99,
                        'tau': 0.005,
                        'alpha': 0.2
                    },
                    'exploration': {
                        'initial_random_steps': 50
                    },
                    'reward': {
                        'tracking_weight': 1.0,
                        'stability_weight': 0.5,
                        'safety_weight': 10.0,
                        'safety_bounds': {
                            'pressure_min': 100.0,
                            'pressure_max': 150.0
                        },
                        'normalize': True,
                        'clip_range': [-10, 10]
                    },
                    'action': {
                        'delta_range': [-0.1, 0.1],
                        'absolute_range': [0.0, 2.0]
                    }
                })
            }
            
            # Create new controller or reset existing one
            if loop_id in vla_controllers:
                print(f"   Resetting existing controller for {loop_id}")
                # Reset controller state for new episode
                controller = vla_controllers[loop_id]
                controller.current_episode = current_episode
                controller.step_in_episode = 0
                controller.prev_state = None
                controller.prev_action = None
                controller.episode_buffer = []
                print(f"   ✓ Controller {loop_id} reset")
            else:
                print(f"   Creating new controller for {loop_id}")
                vla_controllers[loop_id] = initialize_controller(loop_id, loop_config)
                vla_controllers[loop_id].current_episode = current_episode
                print(f"   ✓ Controller {loop_id} created")
        
        print("\n✅ Episode {} initialized successfully!".format(current_episode))
        print("=" * 70)
        print()
        
        return jsonify({
            "status": "initialized",
            "episode": current_episode,
            "control_mode": control_mode,
            "num_loops": len(control_loops),
            "loop_ids": [loop.get('loop_id', 'default') for loop in control_loops]
        })
    
    # ========================================
    # Mode 2: Control Step Request
    # ========================================
    else:
        # ★ CRITICAL FIX: sensor_data配列を展開
        # sim-runnerは sensor_data: [{...}] の形式で送ってくる
        if 'sensor_data' in data and isinstance(data['sensor_data'], list) and len(data['sensor_data']) > 0:
            # sensor_data配列の最初の要素を取得
            sensor_data_item = data['sensor_data'][0]
            
            # トップレベルのtime_stepを保持しつつ、sensor_dataの内容を展開
            actual_data = {
                'time_step': data.get('time_step', sensor_data_item.get('time_step', 0)),
                **sensor_data_item  # sensor_dataの内容を展開
            }
            
            # DEBUG: 最初のリクエストでデータ構造を表示
            step = actual_data.get('step', 0)
            if step == 0 or step == 1:
                print(f"\n[DEBUG] Original request keys: {list(data.keys())}")
                print(f"[DEBUG] Extracted data keys: {list(actual_data.keys())}")
                print(f"[DEBUG] Extracted data: {actual_data}")
        else:
            # sensor_data配列がない場合（旧形式）
            actual_data = data
            step = actual_data.get('step', 0)
            if step == 0 or step == 1:
                print(f"\n[DEBUG] Using legacy format (no sensor_data array)")
                print(f"[DEBUG] Request keys: {list(data.keys())}")
        
        # loop_idを取得
        loop_id = actual_data.get('loop_id')
        
        # ★ FALLBACK: loop_idがNoneの場合、既存のコントローラーから取得
        if loop_id is None:
            if len(vla_controllers) > 0:
                loop_id = list(vla_controllers.keys())[0]
                if step == 0:
                    print(f"⚠️  WARNING: No loop_id in request, using default: {loop_id}")
            else:
                print(f"❌ ERROR: No loop_id and no controllers initialized!")
                return jsonify({"error": "No loop_id provided and no controllers available"}), 400
        
        # Initialize controller on first request (backward compatibility)
        if loop_id not in vla_controllers:
            print(f"\n⚠️  WARNING: Controller {loop_id} not initialized via init request")
            print(f"   Creating controller with default config...")
            
            loop_config = {
                'vla_params': {
                    'model_type': VLA_MODEL,
                    'learning_mode': 'online',
                    'training': {
                        'buffer_size': 10000,
                        'batch_size': 32,
                        'learning_starts': 100,
                        'learning_rate_actor': 0.0003,
                        'learning_rate_critic': 0.0003,
                        'learning_rate_alpha': 0.0003,
                        'gamma': 0.99,
                        'tau': 0.005,
                        'alpha': 0.2
                    },
                    'exploration': {
                        'initial_random_steps': 50
                    },
                    'reward': {
                        'tracking_weight': 1.0,
                        'stability_weight': 0.5,
                        'safety_weight': 10.0,
                        'safety_bounds': {
                            'pressure_min': 100.0,
                            'pressure_max': 150.0
                        },
                        'normalize': True,
                        'clip_range': [-10, 10]
                    },
                    'action': {
                        'delta_range': [-0.1, 0.1],
                        'absolute_range': [0.0, 2.0]
                    }
                }
            }
            vla_controllers[loop_id] = initialize_controller(loop_id, loop_config)
        
        controller = vla_controllers[loop_id]
        
        # Prepare sensor data from actual_data
        sensor_data = {
            'loop_id': loop_id,  # 確実に設定
            'pressure': actual_data.get('pressure', 0.0),
            'target': actual_data.get('target', 0.0),
            'prev_action': actual_data.get('prev_action', 0.0),
            # Additional fields that PromptGenerator might need
            'valve_opening': actual_data.get('valve_opening', actual_data.get('prev_action', 0.0) * 100),  # Convert to percentage
            'upstream_pressure': actual_data.get('upstream_pressure', 0.0),
            'downstream_pressure': actual_data.get('downstream_pressure', actual_data.get('pressure', 0.0)),
            'flow': actual_data.get('flow', 0.0)
        }
        
        step = actual_data.get('step', 0)
        time_step = actual_data.get('time_step', 0)
        
        # Log first and every 50th step
        if step == 0:
            print(f"\n🎮 Starting control loop for {loop_id} (Episode {current_episode})...")
            print(f"   Sensor data keys: {list(sensor_data.keys())}")
            print(f"   Pressure: {sensor_data['pressure']:.2f}, Target: {sensor_data['target']:.2f}")
        elif step % 50 == 0:
            print(f"   Step {step}... (loop_id={loop_id}, pressure={sensor_data['pressure']:.2f})")
        
        # Compute action
        delta_action = controller.compute_action(
            sensor_data=sensor_data,
            step=step,
            time_step=time_step
        )
        
        return jsonify({
            'delta_action': float(delta_action)
        })


@app.route('/episode_end', methods=['POST'])
def episode_end():
    """
    Handle episode end notification from sim-runner
    
    Request JSON:
    {
        "loop_id": "loop_1",
        "episode": 0,
        "total_steps": 144
    }
    """
    data = request.json
    loop_id = data.get('loop_id')
    
    print(f"\n[/episode_end] Received episode end for {loop_id}")
    
    if loop_id in vla_controllers:
        controller = vla_controllers[loop_id]
        
        # Force episode end (in case auto-detection missed it)
        if len(controller.episode_buffer) > 0:
            print(f"   Forcing episode completion (buffer size: {len(controller.episode_buffer)})")
            controller._finish_episode()
        
        print(f"✓ Episode {controller.current_episode} ended for {loop_id}")
        
        return jsonify({'status': 'ok', 'message': 'Episode ended'})
    else:
        return jsonify({'status': 'error', 'message': f'Controller {loop_id} not found'}), 404


@app.route('/checkpoint', methods=['POST'])
def save_checkpoint():
    """Save model checkpoint"""
    data = request.json
    loop_id = data.get('loop_id')
    
    if loop_id in vla_controllers:
        controller = vla_controllers[loop_id]
        checkpoint_path = os.path.join(
            exp_result_dir,
            f'{EXP_ID}_{loop_id}_ep{controller.current_episode}.pt'
        )
        controller.save_checkpoint(checkpoint_path)
        print(f"💾 Checkpoint saved: {checkpoint_path}")
        return jsonify({'status': 'ok', 'checkpoint': checkpoint_path})
    else:
        return jsonify({'status': 'error', 'message': f'Controller {loop_id} not found'}), 404


@app.route('/status', methods=['GET'])
def status():
    """Status check endpoint"""
    return jsonify({
        'status': 'running',
        'exp_id': EXP_ID,
        'current_episode': current_episode,
        'controllers': list(vla_controllers.keys()),
        'num_controllers': len(vla_controllers)
    })


@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint"""
    return jsonify({
        'status': 'ok',
        'exp_id': EXP_ID,
        'controllers': list(vla_controllers.keys())
    })


if __name__ == '__main__':
    print(f"\n" + "=" * 60)
    print("🚀 VLA Controller Service Ready")
    print("=" * 60)
    print(f"  Experiment ID: {EXP_ID}")
    print(f"  Model: {VLA_MODEL}")
    print(f"  Checkpoint: {VLA_CHECKPOINT if VLA_CHECKPOINT else 'None'}")
    print(f"  Redis: {REDIS_URL}")
    print(f"  Image Generator: {IMAGE_GENERATOR_URL}")
    print(f"  Data Collector: {DATA_COLLECTOR_URL}")
    print("=" * 60)
    print()
    
    app.run(host='0.0.0.0', port=5000, debug=False)