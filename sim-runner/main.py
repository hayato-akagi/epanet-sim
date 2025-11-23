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
        
        # 制御モードの読み込み (デフォルトは圧力制御)
        self.control_mode = self.config.get('control_mode', 'pressure')
        
        # 制御ループの配列を読み込み
        self.control_loops = self.config.get('control_loops', [])
        
        # 後方互換性: 旧形式の場合は1つのループとして扱う
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
                    "control_mode": self.control_mode,
                    "control_loops": self.control_loops  # 配列をそのまま送信
                }
                response = requests.post(self.controller_url, json=payload, timeout=5)
                if response.status_code == 200:
                    resp_data = response.json()
                    print(f"Controller connected and initialized.")
                    print(f"  Initialized {resp_data.get('num_loops', len(self.control_loops))} control loops")
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
        
        # 各ループのノードとリンクのインデックスを取得
        loop_data = []
        for loop in self.control_loops:
            node_idx = self.epanet_api.getNodeIndex(loop['target']['node_id'])
            link_idx = self.epanet_api.getLinkIndex(loop['actuator']['link_id'])
            current_valve = loop['actuator']['initial_setting']
            
            self.epanet_api.setLinkSettings(link_idx, current_valve)
            
            loop_data.append({
                "loop_id": loop['loop_id'],
                "node_idx": node_idx,
                "link_idx": link_idx,
                "current_valve": current_valve
            })
            
            print(f"Loop {loop['loop_id']}: Node={loop['target']['node_id']}, Link={loop['actuator']['link_id']}")

        print(f"Starting Simulation Loop for Experiment: {self.exp_id}...")
        
        self.epanet_api.openHydraulicAnalysis()
        self.epanet_api.initializeHydraulicAnalysis()
        current_time = 0
        
        while current_time < duration:
            t = self.epanet_api.runHydraulicAnalysis()
            
            # 各ループのセンサーデータを収集
            sensor_data = []
            loop_measurements = []  # 結果保存用
            
            for i, loop_info in enumerate(loop_data):
                loop_config = self.control_loops[i]
                
                # EPANETから値を取得してfloatに変換
                measured_pressure = self._to_float(self.epanet_api.getNodePressure(loop_info['node_idx']))
                flow = self._to_float(self.epanet_api.getLinkFlows(loop_info['link_idx']))
                
                # 制御モードに応じて制御対象値と目標値を選択
                if self.control_mode == 'flow':
                    controlled_value = flow
                    target_value = loop_config['target'].get('target_flow', 100.0)
                else:  # pressure
                    controlled_value = measured_pressure
                    target_value = loop_config['target'].get('target_pressure', 30.0)
                
                sensor_data.append({
                    "loop_id": loop_info['loop_id'],
                    "pressure": controlled_value,  # 制御対象値（名前はpressureだが実際は制御対象値）
                    "target": target_value,
                    "prev_action": loop_info['current_valve']
                })
                
                # 結果保存用にデータを保持
                loop_measurements.append({
                    "measured_pressure": measured_pressure,
                    "flow": flow,
                    "controlled_value": controlled_value,
                    "target_value": target_value
                })
            
            # コントローラに全ループ分のデータを送信
            payload = {
                "time_step": current_time,
                "sensor_data": sensor_data  # 配列
            }
            
            try:
                response = requests.post(self.controller_url, json=payload, timeout=2)
                response_data = response.json()
                
                # 各ループのアクションを取得して適用
                actions = response_data.get("actions", [])
                
                for i, action_data in enumerate(actions):
                    if i >= len(loop_data):
                        break
                    
                    loop_info = loop_data[i]
                    loop_config = self.control_loops[i]
                    measurements = loop_measurements[i]
                    
                    new_valve = action_data.get("action", loop_info['current_valve'])
                    self.epanet_api.setLinkSettings(loop_info['link_idx'], new_valve)
                    
                    # 結果保存
                    self.results.append({
                        "Time": current_time,
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
                        "Error": action_data.get("error", 0)
                    })
                    
                    loop_info['current_valve'] = new_valve
                    
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
        print(f"  Total records: {len(df)}")
        print(f"  Loops: {df['LoopID'].nunique()}")


if __name__ == "__main__":
    config_path = os.environ.get('CONFIG_PATH', '/shared/configs/exp_001.json')
    network_dir = os.environ.get('NETWORK_DIR', '/shared/networks')
    controller_url = os.environ.get('CONTROLLER_URL', 'http://localhost:5000/control')
    output_root = os.environ.get('OUTPUT_PATH', '/shared/results')
    exp_id = os.environ.get('EXP_ID', 'exp_default')
    
    env = RemoteValveControlEnv(config_path, network_dir, controller_url, output_root, exp_id)
    env.run()