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

        with open(config_path, 'r') as f:
            self.config = json.load(f)
        
        dest_config_path = os.path.join(self.exp_dir, f"{self.exp_id}_config.json")
        shutil.copy(self.config_path, dest_config_path)
        print(f"Config copied to: {dest_config_path}")
        
        inp_file = self.config.get('network', {}).get('inp_file', 'Net1.inp')
        self.network_path = os.path.join(network_dir, inp_file)
        
        self.sim_config = self.config['simulation']
        self.target_config = self.config['target']
        self.actuator_config = self.config['actuator']
        self.pid_params = self.config.get('pid_params', {})
        self.mpc_params = self.config.get('mpc_params', {})
        
        # 制御モードの読み込み (デフォルトは圧力制御)
        self.control_mode = self.config.get('control_mode', 'pressure')
        
        self.results = []
        
        print(f"Loading Network: {self.network_path}")
        print(f"Control Mode: {self.control_mode}")
        try:
            self.epanet_api = epanet(self.network_path)
        except Exception as e:
            print(f"Error loading INP file: {self.network_path}")
            print("Please ensure the file exists in shared/networks/")
            raise e
    
    def _to_float(self, value):
        """
        EPANETから返される値を安全にfloatに変換
        - 0次元配列（スカラー）: np.ndarray.item() を使用
        - 1次元配列: 最初の要素を取得
        - その他: そのままfloatに変換
        """
        if isinstance(value, np.ndarray):
            if value.ndim == 0:  # 0次元配列（スカラー）
                return float(value.item())
            else:  # 1次元以上の配列
                return float(value.flat[0])
        return float(value)

    def wait_for_controller(self):
        print("Waiting for controller...")
        max_retries = 10
        for i in range(max_retries):
            try:
                payload = {
                    "init": True,
                    "control_mode": self.control_mode,  # 制御モードを送信
                    "pid_params": self.pid_params,
                    "mpc_params": self.mpc_params
                }
                response = requests.post(self.controller_url, json=payload, timeout=5)
                if response.status_code == 200:
                    print("Controller connected and initialized.")
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
        
        node_idx = self.epanet_api.getNodeIndex(self.target_config['node_id'])
        link_idx = self.epanet_api.getLinkIndex(self.actuator_config['link_id'])
        
        current_valve_setting = self.actuator_config['initial_setting']
        self.epanet_api.setLinkSettings(link_idx, current_valve_setting)

        print(f"Starting Simulation Loop for Experiment: {self.exp_id}...")
        
        self.epanet_api.openHydraulicAnalysis()
        self.epanet_api.initializeHydraulicAnalysis()
        
        current_time = 0
        
        while current_time < duration:
            t = self.epanet_api.runHydraulicAnalysis()
            
            # EPANETから値を取得してfloatに変換
            measured_pressure = self._to_float(self.epanet_api.getNodePressure(node_idx))
            flow = self._to_float(self.epanet_api.getLinkFlows(link_idx))
            
            # 制御モードに応じて制御対象値と目標値を選択
            if self.control_mode == 'flow':
                controlled_value = flow
                target_value = self.target_config.get('target_flow', 100.0)
            else:  # pressure
                controlled_value = measured_pressure
                target_value = self.target_config.get('target_pressure', 30.0)
            
            payload = {
                "time_step": current_time,
                "sensor_data": {
                    "pressure": controlled_value,  # 制御対象の値（pressureという名前だが実際は制御対象値）
                    "target": target_value
                },
                "prev_action": current_valve_setting
            }
            
            try:
                response = requests.post(self.controller_url, json=payload, timeout=2)
                response_data = response.json()
                
                new_valve_setting = response_data.get("action", current_valve_setting)
                self.epanet_api.setLinkSettings(link_idx, new_valve_setting)
                
                self.results.append({
                    "Time": current_time,
                    "Pressure": measured_pressure,
                    "Flow": flow,
                    "ControlMode": self.control_mode,
                    "ControlledValue": controlled_value,
                    "TargetValue": target_value,
                    "TargetPressure": self.target_config.get('target_pressure', 0),
                    "TargetFlow": self.target_config.get('target_flow', 0),
                    "ValveSetting": current_valve_setting,
                    "NewValveSetting": new_valve_setting,
                    "PID_P": response_data.get("p_term", 0),
                    "PID_I": response_data.get("i_term", 0),
                    "PID_D": response_data.get("d_term", 0),
                    "Error": response_data.get("error", 0)
                })
                
                current_valve_setting = new_valve_setting
                
            except Exception as e:
                print(f"Error communicating with controller: {e}")
            
            step_advanced = self.epanet_api.nextHydraulicAnalysisStep()
            current_time += step_size
            
            if step_advanced == 0:
                break

        self.epanet_api.closeHydraulicAnalysis()
        self.save_results()
        print(f"Simulation {self.exp_id} Completed.")

    def save_results(self):
        filename = f"result.csv" 
        output_path = os.path.join(self.exp_dir, filename)
        
        df = pd.DataFrame(self.results)
        df.to_csv(output_path, index=False)
        print(f"Results saved to {output_path}")

if __name__ == "__main__":
    config_path = os.environ.get('CONFIG_PATH', '/shared/configs/exp_001.json')
    network_dir = os.environ.get('NETWORK_DIR', '/shared/networks')
    controller_url = os.environ.get('CONTROLLER_URL', 'http://localhost:5000/control')
    output_root = os.environ.get('OUTPUT_PATH', '/shared/results')
    exp_id = os.environ.get('EXP_ID', 'exp_default')
    
    env = RemoteValveControlEnv(config_path, network_dir, controller_url, output_root, exp_id)
    env.run()