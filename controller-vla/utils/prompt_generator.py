class PromptGenerator:
    """
    センサーデータから制御用プロンプトを生成
    
    VLAモデル用の自然言語形式プロンプト
    """
    
    def __init__(self, control_mode='pressure'):
        """
        Args:
            control_mode: 'pressure' or 'flow'
        """
        self.control_mode = control_mode
    
    def generate(self, sensor_data):
        """
        プロンプト生成
        
        Args:
            sensor_data: dict with keys like ['pressure', 'target', 'prev_action', ...]
        
        Returns:
            str: 制御用プロンプト
        """
        if self.control_mode == 'pressure':
            return self._generate_pressure_prompt(sensor_data)
        elif self.control_mode == 'flow':
            return self._generate_flow_prompt(sensor_data)
        else:
            return self._generate_pressure_prompt(sensor_data)
    
    def _generate_pressure_prompt(self, sensor_data):
        """圧力制御用プロンプト"""
        pressure = sensor_data.get('pressure', 30.0)
        target = sensor_data.get('target', 30.0)
        valve = sensor_data.get('prev_action', 0.5)
        upstream = sensor_data.get('upstream_pressure', 50.0)
        downstream = sensor_data.get('downstream_pressure', pressure)
        
        prompt = f"""Control the water distribution network.
Current pressure: {pressure:.1f}m at Node 2
Target: {target:.1f}m
Valve opening: {valve*100:.1f}%
Upstream pressure: {upstream:.1f}m
Downstream pressure: {downstream:.1f}m

Task: Adjust the valve to maintain target pressure."""
        
        return prompt
    
    def _generate_flow_prompt(self, sensor_data):
        """流量制御用プロンプト"""
        flow = sensor_data.get('flow', 100.0)
        target = sensor_data.get('target', 100.0)
        valve = sensor_data.get('prev_action', 0.5)
        pressure = sensor_data.get('pressure', 30.0)
        
        prompt = f"""Control the water distribution network.
Current flow: {flow:.1f}L/s
Target: {target:.1f}L/s
Valve opening: {valve*100:.1f}%
Current pressure: {pressure:.1f}m

Task: Adjust the valve to maintain target flow."""
        
        return prompt