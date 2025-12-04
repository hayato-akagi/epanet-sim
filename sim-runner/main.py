import os
import json
import time
import shutil
import requests
import pandas as pd
from epyt import epanet
import numpy as np


class RemoteValveControlEnv:
    def __init__(self, config_path, network_dir, controller_url, output_root, exp_id):
        self.config_path = config_path
        self.controller_url = controller_url
        self.output_root = output_root
        self.exp_id = exp_id
        self.exp_dir = os.path.join(self.output_root, self.exp_id)
        os.makedirs(self.exp_dir, exist_ok=True)
        
        # ★ NEW: Image generator URL
        self.image_generator_url = os.environ.get(
            'IMAGE_GENERATOR_URL', 
            'http://image-generator:5000'
        )
        self.enable_image_generation = os.environ.get(
            'ENABLE_IMAGE_GENERATION', 
            'true'
        ).lower() == 'true'
        
        # ★ NEW: Image saving configuration
        self.save_images = os.environ.get(
            'SAVE_IMAGES',
            'true'
        ).lower() == 'true'
        self.image_save_interval = int(os.environ.get(
            'IMAGE_SAVE_INTERVAL',
            '10'  # Save every 10 steps
        ))
        self.image_save_dir = os.path.join(
            '/shared/training_data',
            self.exp_id,
            'images'
        )
        
        # Create image save directory
        if self.save_images:
            os.makedirs(self.image_save_dir, exist_ok=True)
            print(f"Images will be saved to: {self.image_save_dir}")
            print(f"Save interval: every {self.image_save_interval} steps")
        
        # Controller type detection (will be set during initialization)
        self.controller_type = None  # 'batch' (PID/MPC) or 'individual' (VLA)
        
        with open(config_path, 'r') as f:
            self.config = json.load(f)
        
        dest_config_path = os.path.join(self.exp_dir, f"{self.exp_id}_config.json")
        shutil.copy(self.config_path, dest_config_path)
        print(f"Config copied to: {dest_config_path}")
        
        inp_file = self.config.get('network', {}).get('inp_file', 'Net1.inp')
        self.network_path = os.path.join(network_dir, inp_file)
        
        self.sim_config = self.config['simulation']
        self.control_mode = self.config.get('control_mode', 'pressure')
        self.control_loops = self.config.get('control_loops', [])
        
        if not self.control_loops:
            print("Using legacy single-loop configuration")
            self.control_loops = [{
                "loop_id": "default",
                "target": self.config.get('target', {}),
                "actuator": self.config.get('actuator', {}),
                "pid_params": self.config.get('pid_params', {}),
                "mpc_params": self.config.get('mpc_params', {})
            }]
        
        self.results = []
        
        # ★ NEW: History tracking for image generation
        self.pressure_history = []
        self.valve_history = []
        self.flow_history = []
        self.error_history = []
        
        print(f"Loading Network: {self.network_path}")
        print(f"Control Mode: {self.control_mode}")
        print(f"Number of Control Loops: {len(self.control_loops)}")
        print(f"Image Generation: {'Enabled' if self.enable_image_generation else 'Disabled'}")
        
        try:
            self.epanet_api = epanet(self.network_path)
        except Exception as e:
            print(f"Error loading INP file: {self.network_path}")
            print("Please ensure the file exists in shared/networks/")
            raise e
    
    def _to_float(self, value):
        if isinstance(value, np.ndarray):
            if value.ndim == 0:
                return float(value.item())
            else:
                return float(value.flat[0])
        return float(value)
    
    def _save_images_from_redis(self, redis_keys, step_count):
        """
        Save images from Redis to disk
        
        Args:
            redis_keys: Dictionary of {image_type: redis_key}
            step_count: Current step number
        """
        try:
            import redis
            from PIL import Image
            import io
            
            # Connect to Redis
            redis_client = redis.from_url(
                os.environ.get('REDIS_URL', 'redis://redis:6379'),
                decode_responses=False
            )
            
            saved_count = 0
            for img_type, redis_key in redis_keys.items():
                try:
                    # Get image from Redis
                    img_bytes = redis_client.get(redis_key)
                    
                    if img_bytes:
                        # Save to disk
                        filename = f"step_{step_count:04d}_{img_type}.png"
                        filepath = os.path.join(self.image_save_dir, filename)
                        
                        with open(filepath, 'wb') as f:
                            f.write(img_bytes)
                        
                        saved_count += 1
                    else:
                        print(f"    [WARNING] Image not found in Redis: {redis_key}")
                
                except Exception as e:
                    print(f"    [WARNING] Failed to save {img_type}: {e}")
            
            if saved_count > 0:
                print(f"  💾 Saved {saved_count} images for step {step_count} to {self.image_save_dir}")
        
        except Exception as e:
            print(f"  [WARNING] Failed to save images: {e}")
    
    def wait_for_controller(self):
        print("Waiting for controller...")
        max_retries = 10
        for i in range(max_retries):
            try:
                payload = {
                    "init": True,
                    "control_mode": self.control_mode,
                    "control_loops": self.control_loops
                }
                response = requests.post(self.controller_url, json=payload, timeout=30)  # ★ INCREASED
                if response.status_code == 200:
                    resp_data = response.json()
                    print(f"Controller connected and initialized.")
                    print(f"  Response keys: {list(resp_data.keys())}")
                    print(f"  Initialized {resp_data.get('num_loops', len(self.control_loops))} control loops")
                    
                    # Improved controller type detection
                    if 'controller_type' in resp_data:
                        self.controller_type = resp_data['controller_type']
                        print(f"  Detected controller type (explicit): {self.controller_type}")
                    elif 'episode' in resp_data or 'loop_ids' in resp_data:
                        self.controller_type = 'individual'
                        print(f"  Detected controller type (VLA indicators): {self.controller_type}")
                    elif 'status' in resp_data and resp_data.get('status') == 'initialized':
                        if 'vla' in self.controller_url.lower():
                            self.controller_type = 'individual'
                            print(f"  Detected controller type (URL contains 'vla'): {self.controller_type}")
                        else:
                            self.controller_type = 'batch'
                            print(f"  Detected controller type (batch style): {self.controller_type}")
                    else:
                        self.controller_type = 'individual'
                        print(f"  Detected controller type (default): {self.controller_type}")
                    
                    return
            except requests.exceptions.ConnectionError:
                print(f"Connection failed, retrying... ({i+1}/{max_retries})")
                time.sleep(2)
        raise Exception("Could not connect to controller")
    
    def _generate_images(self, step_count, current_time, loop_data, loop_measurements):
        """
        Generate visualization images via image-generator service
        
        Args:
            step_count: Current step number
            current_time: Current simulation time
            loop_data: List of loop information
            loop_measurements: List of measurements for each loop
        """
        if not self.enable_image_generation:
            return
        
        try:
            # Use first loop for simplicity (can be extended for multi-loop)
            if len(loop_data) == 0 or len(loop_measurements) == 0:
                return
            
            loop_info = loop_data[0]
            measurements = loop_measurements[0]
            loop_config = self.control_loops[0]
            
            # Prepare state data
            state = {
                "pressure": measurements['measured_pressure'],
                "target_pressure": measurements['target_value'],
                "valve_setting": loop_info['current_valve'],
                "flow": measurements['flow'],
                "target_flow": loop_config['target'].get('target_flow', 100.0),
                "upstream_pressure": 150.0,  # Placeholder
                "downstream_pressure": measurements['measured_pressure'],
                "timestamp": f"{current_time}s"
            }
            
            # Prepare history data (last 30 steps for better temporal visualization)
            history = {
                "pressure": self.pressure_history[-30:] if len(self.pressure_history) > 0 else [measurements['measured_pressure']],
                "valve_setting": self.valve_history[-30:] if len(self.valve_history) > 0 else [loop_info['current_valve']],
                "flow": self.flow_history[-30:] if len(self.flow_history) > 0 else [measurements['flow']],
                "error": self.error_history[-30:] if len(self.error_history) > 0 else [0.0]
            }
            
            # Request payload
            payload = {
                "exp_id": self.exp_id,
                "step": step_count,
                "state": state,
                "history": history
            }
            
            # Send request to image-generator
            response = requests.post(
                f"{self.image_generator_url}/generate",
                json=payload,
                timeout=10  # ★ INCREASED from 5 to 10 for image generation
            )
            
            if response.status_code == 200:
                data = response.json()
                redis_keys = data.get('redis_keys', {})
                
                # Log image generation (only occasionally to avoid spam)
                if step_count == 0 or step_count % 50 == 0:
                    print(f"  Generated {len(redis_keys)} images for step {step_count}")
                    if step_count == 0:
                        print(f"    Image types: {list(redis_keys.keys())}")
                
                # ★ NEW: Save images to disk at specified intervals
                if self.save_images and (step_count % self.image_save_interval == 0):
                    self._save_images_from_redis(redis_keys, step_count)
            else:
                if step_count % 50 == 0:
                    print(f"  [WARNING] Image generation failed at step {step_count}: status {response.status_code}")
        
        except requests.exceptions.Timeout:
            if step_count % 50 == 0:
                print(f"  [WARNING] Image generation timeout at step {step_count}")
        except requests.exceptions.ConnectionError:
            if step_count == 0:
                print(f"  [WARNING] Cannot connect to image-generator service")
                print(f"    Make sure image-generator is running at {self.image_generator_url}")
        except Exception as e:
            if step_count % 50 == 0:
                print(f"  [WARNING] Error generating images at step {step_count}: {e}")
    
    def run(self):
        self.wait_for_controller()
        
        duration = self.sim_config['duration']
        step_size = self.sim_config['hydraulic_step']
        self.epanet_api.setTimeSimulationDuration(duration)
        self.epanet_api.setTimeHydraulicStep(step_size)
        
        # Debug: Network info
        print("\n=== Network Debug Info ===")
        print(f"Total Nodes: {self.epanet_api.getNodeCount()}")
        print(f"Total Links: {self.epanet_api.getLinkCount()}")
        print(f"Node IDs: {self.epanet_api.getNodeNameID()}")
        print(f"Link IDs: {self.epanet_api.getLinkNameID()}")
        print("========================\n")
        
        loop_data = []
        for loop in self.control_loops:
            node_id = loop['target']['node_id']
            link_id = loop['actuator']['link_id']
            
            print(f"\n=== Loop {loop['loop_id']} ===")
            print(f"Requested Node ID: {node_id} (type: {type(node_id)})")
            print(f"Requested Link ID: {link_id} (type: {type(link_id)})")
            
            try:
                node_idx = self.epanet_api.getNodeIndex(node_id)
                print(f"Node Index: {node_idx} (type: {type(node_idx)})")
            except Exception as e:
                print(f"ERROR getting node index: {e}")
                raise
            
            try:
                link_idx = self.epanet_api.getLinkIndex(link_id)
                print(f"Link Index: {link_idx} (type: {type(link_idx)})")
            except Exception as e:
                print(f"ERROR getting link index: {e}")
                raise
            
            current_valve = loop['actuator']['initial_setting']
            
            if isinstance(node_idx, np.ndarray):
                node_idx = int(node_idx.item())
            if isinstance(link_idx, np.ndarray):
                link_idx = int(link_idx.item())
            
            print(f"Final Node Index: {node_idx}")
            print(f"Final Link Index: {link_idx}")
            
            self.epanet_api.setLinkSettings(link_idx, current_valve)
            
            loop_data.append({
                "loop_id": loop['loop_id'],
                "node_idx": node_idx,
                "link_idx": link_idx,
                "current_valve": current_valve
            })
            
            print(f"Loop {loop['loop_id']}: Node={node_id} (idx={node_idx}), Link={link_id} (idx={link_idx})")
        
        print(f"\nStarting Simulation Loop for Experiment: {self.exp_id}...")
        print(f"  Duration: {duration}s")
        print(f"  Hydraulic step: {step_size}s")
        print(f"  Expected steps: {duration // step_size}")
        print(f"  Controller type: {self.controller_type}")
        
        self.epanet_api.openHydraulicAnalysis()
        self.epanet_api.initializeHydraulicAnalysis()
        current_time = 0
        step_count = 0
        
        while current_time <= duration:
            t = self.epanet_api.runHydraulicAnalysis()
            
            sensor_data = []
            loop_measurements = []
            
            for i, loop_info in enumerate(loop_data):
                loop_config = self.control_loops[i]
                
                try:
                    measured_pressure = self._to_float(self.epanet_api.getNodePressure(loop_info['node_idx']))
                except Exception as e:
                    print(f"ERROR: getNodePressure failed for node_idx={loop_info['node_idx']}: {e}")
                    raise
                
                try:
                    flow = self._to_float(self.epanet_api.getLinkFlows(loop_info['link_idx']))
                except Exception as e:
                    print(f"ERROR: getLinkFlows failed for link_idx={loop_info['link_idx']}: {e}")
                    raise
                
                if self.control_mode == 'flow':
                    controlled_value = flow
                    target_value = loop_config['target'].get('target_flow', 100.0)
                else:
                    controlled_value = measured_pressure
                    target_value = loop_config['target'].get('target_pressure', 30.0)
                
                sensor_data.append({
                    "loop_id": loop_info['loop_id'],
                    "pressure": controlled_value,
                    "target": target_value,
                    "prev_action": loop_info['current_valve'],
                    "step": step_count,
                    "time_step": current_time
                })
                
                loop_measurements.append({
                    "measured_pressure": measured_pressure,
                    "flow": flow,
                    "controlled_value": controlled_value,
                    "target_value": target_value
                })
                
                # ★ NEW: Update history (for first loop only, can be extended)
                if i == 0:
                    self.pressure_history.append(measured_pressure)
                    self.valve_history.append(loop_info['current_valve'])
                    self.flow_history.append(flow)
                    self.error_history.append(target_value - controlled_value)
            
            # ★ NEW: Generate images BEFORE sending control request
            # This ensures VLA controller has fresh images available
            self._generate_images(step_count, current_time, loop_data, loop_measurements)
            
            # Send requests based on controller type
            if self.controller_type == 'batch':
                # PID/MPC style: Send all loops in one request
                payload = {
                    "exp_id": self.exp_id,  # ★ ADD: for image fetching
                    "step": step_count,      # ★ ADD: for image fetching
                    "time_step": current_time,
                    "sensor_data": sensor_data
                }
                
                try:
                    response = requests.post(self.controller_url, json=payload, timeout=30)  # ★ INCREASED from 5 to 30
                    
                    if response.status_code != 200:
                        print(f"[WARNING] Controller returned status {response.status_code}")
                        continue
                    
                    response_data = response.json()
                    actions = response_data.get("actions", [])
                    
                    for i, action_data in enumerate(actions):
                        if i >= len(loop_data):
                            break
                        
                        loop_info = loop_data[i]
                        loop_config = self.control_loops[i]
                        measurements = loop_measurements[i]
                        
                        new_valve = action_data.get("action", loop_info['current_valve'])
                        
                        action_config = loop_config.get('actuator', {})
                        min_valve = action_config.get('min_setting', 0.1)
                        max_valve = action_config.get('max_setting', 1.0)
                        
                        if new_valve < min_valve:
                            print(f"[WARNING] Loop {loop_info['loop_id']}: Valve {new_valve:.4f} too low, clamping to {min_valve}")
                            new_valve = min_valve
                        elif new_valve > max_valve:
                            print(f"[WARNING] Loop {loop_info['loop_id']}: Valve {new_valve:.4f} too high, clamping to {max_valve}")
                            new_valve = max_valve
                        
                        self.epanet_api.setLinkSettings(loop_info['link_idx'], new_valve)
                        
                        self.results.append({
                            "Time": current_time,
                            "Step": step_count,
                            "LoopID": loop_info['loop_id'],
                            "Pressure": measurements['measured_pressure'],
                            "Flow": measurements['flow'],
                            "ControlMode": self.control_mode,
                            "ControlledValue": measurements['controlled_value'],
                            "TargetValue": measurements['target_value'],
                            "TargetPressure": loop_config['target'].get('target_pressure', 0),
                            "TargetFlow": loop_config['target'].get('target_flow', 0),
                            "ValveSetting": loop_info['current_valve'],
                            "NewValveSetting": new_valve,
                            "PID_P": action_data.get("p_term", 0),
                            "PID_I": action_data.get("i_term", 0),
                            "PID_D": action_data.get("d_term", 0),
                            "Error": action_data.get("error", measurements['target_value'] - measurements['controlled_value'])
                        })
                        
                        loop_info['current_valve'] = new_valve
                    
                except Exception as e:
                    print(f"Error communicating with controller: {e}")
                    import traceback
                    traceback.print_exc()
                    
            else:
                # VLA style: Send individual requests for each loop
                for i, loop_info in enumerate(loop_data):
                    loop_config = self.control_loops[i]
                    measurements = loop_measurements[i]
                    sensor = sensor_data[i]
                    
                    payload = {
                        "exp_id": self.exp_id,  # ★ ADD: for image fetching
                        "step": step_count,      # ★ ADD: for image fetching
                        "time_step": current_time,
                        "sensor_data": [sensor]
                    }
                    
                    if step_count == 0:
                        print(f"\n[DEBUG] VLA payload for loop {loop_info['loop_id']}: {payload}")
                    
                    try:
                        response = requests.post(self.controller_url, json=payload, timeout=30)  # ★ INCREASED from 5 to 30
                        
                        if response.status_code != 200:
                            print(f"[WARNING] Controller returned status {response.status_code}")
                            continue
                        
                        response_data = response.json()
                        
                        if step_count == 0:
                            print(f"[DEBUG] VLA response: {response_data}")
                        
                        if "delta_action" in response_data:
                            delta_action = response_data.get("delta_action", 0.0)
                            new_valve = loop_info['current_valve'] + delta_action
                            
                            action_config = loop_config.get('vla_params', {}).get('action', {})
                            min_valve = action_config.get('absolute_range', [0.0, 2.0])[0]
                            max_valve = action_config.get('absolute_range', [0.0, 2.0])[1]
                            
                            if new_valve < min_valve:
                                if step_count % 10 == 0:
                                    print(f"[WARNING] Loop {loop_info['loop_id']}: Valve {new_valve:.4f} too low, clamping to {min_valve}")
                                new_valve = min_valve
                            elif new_valve > max_valve:
                                if step_count % 10 == 0:
                                    print(f"[WARNING] Loop {loop_info['loop_id']}: Valve {new_valve:.4f} too high, clamping to {max_valve}")
                                new_valve = max_valve
                            
                            self.epanet_api.setLinkSettings(loop_info['link_idx'], new_valve)
                            
                            self.results.append({
                                "Time": current_time,
                                "Step": step_count,
                                "LoopID": loop_info['loop_id'],
                                "Pressure": measurements['measured_pressure'],
                                "Flow": measurements['flow'],
                                "ControlMode": self.control_mode,
                                "ControlledValue": measurements['controlled_value'],
                                "TargetValue": measurements['target_value'],
                                "TargetPressure": loop_config['target'].get('target_pressure', 0),
                                "TargetFlow": loop_config['target'].get('target_flow', 0),
                                "ValveSetting": loop_info['current_valve'],
                                "DeltaAction": delta_action,
                                "NewValveSetting": new_valve,
                                "Error": measurements['target_value'] - measurements['controlled_value']
                            })
                            
                            loop_info['current_valve'] = new_valve
                            
                            if step_count == 0:
                                print(f"[DEBUG] Recorded data for step {step_count}, loop {loop_info['loop_id']}")
                            
                        else:
                            print(f"[WARNING] Unexpected response format from controller: {response_data.keys()}")
                            
                    except Exception as e:
                        print(f"Error communicating with controller at step {step_count}: {e}")
                        import traceback
                        traceback.print_exc()
            
            step_advanced = self.epanet_api.nextHydraulicAnalysisStep()
            current_time += step_size
            step_count += 1
            
            if step_count % 10 == 0:
                print(f"  Step {step_count}/{duration // step_size} completed (t={current_time}s, recorded={len(self.results)})")
            
            if step_advanced == 0:
                print(f"[INFO] EPANET simulation completed at step {step_count}")
                break
        
        self.epanet_api.closeHydraulicAnalysis()
        
        print(f"\n[DEBUG] Total results before save: {len(self.results)}")
        if len(self.results) > 0:
            print(f"[DEBUG] First result: {self.results[0]}")
            print(f"[DEBUG] Last result: {self.results[-1]}")
        
        self.save_results()
        print(f"Simulation {self.exp_id} Completed.")
    
    def save_results(self):
        filename = f"result.csv"
        output_path = os.path.join(self.exp_dir, filename)
        
        df = pd.DataFrame(self.results)
        df.to_csv(output_path, index=False)
        print(f"Results saved to {output_path}")
        print(f"  Total records: {len(df)}")
        
        if len(df) > 0:
            print(f"  Loops: {df['LoopID'].nunique()}")
            print(f"  Time range: {df['Time'].min():.0f}s - {df['Time'].max():.0f}s")
            print(f"  Steps: {df['Step'].nunique()}")
        else:
            print("[WARNING] No data recorded!")


if __name__ == "__main__":
    config_path = os.environ.get('CONFIG_PATH', '/shared/configs/exp_001.json')
    network_dir = os.environ.get('NETWORK_DIR', '/shared/networks')
    controller_url = os.environ.get('CONTROLLER_URL', 'http://localhost:5000/control')
    output_root = os.environ.get('OUTPUT_PATH', '/shared/results')
    exp_id = os.environ.get('EXP_ID', 'exp_default')
    
    env = RemoteValveControlEnv(config_path, network_dir, controller_url, output_root, exp_id)
    env.run()