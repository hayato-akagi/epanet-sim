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
        
        print(f"Loading Network: {self.network_path}")
        print(f"Control Mode: {self.control_mode}")
        print(f"Number of Control Loops: {len(self.control_loops)}")
        
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
                response = requests.post(self.controller_url, json=payload, timeout=5)
                if response.status_code == 200:
                    resp_data = response.json()
                    print(f"Controller connected and initialized.")
                    print(f"  Response keys: {list(resp_data.keys())}")
                    print(f"  Initialized {resp_data.get('num_loops', len(self.control_loops))} control loops")
                    
                    # ★ FIXED: Improved controller type detection
                    # Check for explicit controller_type field first
                    if 'controller_type' in resp_data:
                        self.controller_type = resp_data['controller_type']
                        print(f"  Detected controller type (explicit): {self.controller_type}")
                    # Check for VLA-specific fields (episode, loop_ids)
                    elif 'episode' in resp_data or 'loop_ids' in resp_data:
                        self.controller_type = 'individual'  # VLA style
                        print(f"  Detected controller type (VLA indicators): {self.controller_type}")
                    # Check for batch controller response format
                    elif 'status' in resp_data and resp_data.get('status') == 'initialized':
                        # Additional check: if controller URL contains 'vla', it's VLA
                        if 'vla' in self.controller_url.lower():
                            self.controller_type = 'individual'
                            print(f"  Detected controller type (URL contains 'vla'): {self.controller_type}")
                        else:
                            self.controller_type = 'batch'  # PID/MPC style
                            print(f"  Detected controller type (batch style): {self.controller_type}")
                    else:
                        # Default: assume individual (VLA)
                        self.controller_type = 'individual'
                        print(f"  Detected controller type (default): {self.controller_type}")
                    
                    return
            except requests.exceptions.ConnectionError:
                print(f"Connection failed, retrying... ({i+1}/{max_retries})")
                time.sleep(2)
        raise Exception("Could not connect to controller")
    
    def run(self):
        self.wait_for_controller()
        
        duration = self.sim_config['duration']
        step_size = self.sim_config['hydraulic_step']
        self.epanet_api.setTimeSimulationDuration(duration)
        self.epanet_api.setTimeHydraulicStep(step_size)
        
        # === デバッグ: ネットワーク情報の表示 ===
        print("\n=== Network Debug Info ===")
        print(f"Total Nodes: {self.epanet_api.getNodeCount()}")
        print(f"Total Links: {self.epanet_api.getLinkCount()}")
        print(f"Node IDs: {self.epanet_api.getNodeNameID()}")
        print(f"Link IDs: {self.epanet_api.getLinkNameID()}")
        print("========================\n")
        # ======================================
        
        loop_data = []
        for loop in self.control_loops:
            node_id = loop['target']['node_id']
            link_id = loop['actuator']['link_id']
            
            # === デバッグ: インデックス取得 ===
            print(f"\n=== Loop {loop['loop_id']} ===")
            print(f"Requested Node ID: {node_id} (type: {type(node_id)})")
            print(f"Requested Link ID: {link_id} (type: {type(link_id)})")
            # =================================
            
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
            
            # === インデックスの妥当性チェック ===
            if isinstance(node_idx, np.ndarray):
                node_idx = int(node_idx.item())
            if isinstance(link_idx, np.ndarray):
                link_idx = int(link_idx.item())
            
            print(f"Final Node Index: {node_idx}")
            print(f"Final Link Index: {link_idx}")
            # ==================================
            
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
        
        # Fixed: Use <= instead of < to include the final step
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
            
            # Send requests based on controller type
            if self.controller_type == 'batch':
                # PID/MPC style: Send all loops in one request
                payload = {
                    "time_step": current_time,
                    "sensor_data": sensor_data
                }
                
                try:
                    response = requests.post(self.controller_url, json=payload, timeout=5)
                    
                    if response.status_code != 200:
                        print(f"[WARNING] Controller returned status {response.status_code}")
                        continue
                    
                    response_data = response.json()
                    actions = response_data.get("actions", [])
                    
                    # Process actions
                    for i, action_data in enumerate(actions):
                        if i >= len(loop_data):
                            break
                        
                        loop_info = loop_data[i]
                        loop_config = self.control_loops[i]
                        measurements = loop_measurements[i]
                        
                        new_valve = action_data.get("action", loop_info['current_valve'])
                        
                        # Clamp to valid range
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
                        "time_step": current_time,
                        "sensor_data": [sensor]  # ★ FIXED: Wrap in array to match controller-vla expectation
                    }
                    
                    if step_count == 0:
                        print(f"\n[DEBUG] VLA payload for loop {loop_info['loop_id']}: {payload}")
                    
                    try:
                        response = requests.post(self.controller_url, json=payload, timeout=5)
                        
                        if response.status_code != 200:
                            print(f"[WARNING] Controller returned status {response.status_code}")
                            continue
                        
                        response_data = response.json()
                        
                        if step_count == 0:
                            print(f"[DEBUG] VLA response: {response_data}")
                        
                        # Handle VLA-style response (delta_action)
                        if "delta_action" in response_data:
                            delta_action = response_data.get("delta_action", 0.0)
                            new_valve = loop_info['current_valve'] + delta_action
                            
                            # Clamp to valid range
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
                            
                            # ★ FIXED: Record data
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