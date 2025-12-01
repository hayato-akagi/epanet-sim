"""
報酬計算ユーティリティ
汎用的な報酬関数を提供
将来的に異なる報酬関数を試す際に使用
"""

class RewardCalculator:
    """報酬計算クラス"""
    
    def __init__(self, tracking_weight=1.0, stability_weight=0.5, 
                 safety_weight=10.0, safety_bounds=None, 
                 normalize=True, clip_range=None):
        """
        初期化
        
        Args:
            tracking_weight: 追従誤差の重み
            stability_weight: 安定性の重み
            safety_weight: 安全制約の重み
            safety_bounds: 安全制約の境界 {'pressure_min': float, 'pressure_max': float}
            normalize: 正規化するか
            clip_range: クリッピング範囲 [min, max]
        """
        self.tracking_weight = tracking_weight
        self.stability_weight = stability_weight
        self.safety_weight = safety_weight
        self.safety_bounds = safety_bounds or {}
        self.normalize = normalize
        self.clip_range = clip_range or [-10, 10]
    
    def calculate(self, current_pressure, target_pressure, prev_pressure, 
                  valve_change, time_step):
        """
        報酬を計算
        
        Args:
            current_pressure: 現在の圧力
            target_pressure: 目標圧力
            prev_pressure: 前回の圧力
            valve_change: バルブ変化量
            time_step: 時刻
            
        Returns:
            dict: 報酬の内訳
                - total_reward: 合計報酬
                - tracking: 追従報酬
                - stability: 安定性報酬
                - safety: 安全制約報酬
        """
        # 追従報酬
        tracking_reward = self._compute_tracking_reward(
            current_pressure, target_pressure
        )
        
        # 安定性報酬
        stability_reward = self._compute_stability_reward(valve_change)
        
        # 安全制約報酬
        safety_reward = self._compute_safety_reward(current_pressure)
        
        # 合計
        total_reward = tracking_reward + stability_reward + safety_reward
        
        # 正規化・クリッピング
        if self.normalize:
            total_reward = max(self.clip_range[0], 
                             min(self.clip_range[1], total_reward))
        
        return {
            'total_reward': total_reward,
            'tracking': tracking_reward,
            'stability': stability_reward,
            'safety': safety_reward
        }
    
    def _compute_tracking_reward(self, current_value, target_value):
        """追従誤差報酬"""
        if target_value == 0:
            return 0.0
        
        error = abs(target_value - current_value)
        reward = -error / target_value
        return reward * self.tracking_weight
    
    def _compute_stability_reward(self, action):
        """操作安定性報酬"""
        reward = -abs(action)
        return reward * self.stability_weight
    
    def _compute_safety_reward(self, value):
        """安全制約報酬"""
        min_bound = self.safety_bounds.get('pressure_min', 15.0)
        max_bound = self.safety_bounds.get('pressure_max', 60.0)
        
        if value < min_bound or value > max_bound:
            return -self.safety_weight
        return 0.0


# 後方互換性のための関数（古いコードで使用されている場合のため）
def compute_tracking_reward(current_value, target_value, weight=1.0):
    """
    追従誤差報酬
    
    Args:
        current_value: 現在値
        target_value: 目標値
        weight: 重み
    
    Returns:
        float: 報酬
    """
    if target_value == 0:
        return 0.0
    
    error = abs(target_value - current_value)
    reward = -error / target_value
    return reward * weight


def compute_stability_reward(action, weight=0.5):
    """
    操作安定性報酬
    
    Args:
        action: 行動（Δvalve）
        weight: 重み
    
    Returns:
        float: 報酬
    """
    reward = -abs(action)
    return reward * weight


def compute_safety_reward(value, min_bound, max_bound, penalty=10.0):
    """
    安全制約報酬
    
    Args:
        value: チェックする値
        min_bound: 下限
        max_bound: 上限
        penalty: ペナルティ値
    
    Returns:
        float: 報酬
    """
    if value < min_bound or value > max_bound:
        return -penalty
    return 0.0


def compute_energy_reward(valve_setting, weight=0.1):
    """
    エネルギー効率報酬
    
    バルブ開度が0.5から離れるほどペナルティ
    （ポンプ効率を考慮）
    
    Args:
        valve_setting: バルブ開度（0-1）
        weight: 重み
    
    Returns:
        float: 報酬
    """
    deviation = abs(valve_setting - 0.5)
    reward = -deviation
    return reward * weight


def compute_combined_reward(state, action, next_state, config):
    """
    複合報酬計算
    
    Args:
        state: 前状態
        action: 行動
        next_state: 次状態
        config: 報酬設定辞書
    
    Returns:
        tuple: (total_reward, components_dict)
    """
    # 追従報酬
    r_tracking = compute_tracking_reward(
        next_state.get('pressure', 0),
        next_state.get('target', 0),
        config.get('tracking_weight', 1.0)
    )
    
    # 安定性報酬
    r_stability = compute_stability_reward(
        action,
        config.get('stability_weight', 0.5)
    )
    
    # 安全制約報酬
    safety_bounds = config.get('safety_bounds', {})
    r_safety = compute_safety_reward(
        next_state.get('pressure', 0),
        safety_bounds.get('pressure_min', 15.0),
        safety_bounds.get('pressure_max', 60.0),
        config.get('safety_weight', 10.0)
    )
    
    # 合計
    total_reward = r_tracking + r_stability + r_safety
    
    # 正規化・クリッピング
    if config.get('normalize', False):
        clip_range = config.get('clip_range', [-10, 10])
        total_reward = max(clip_range[0], min(clip_range[1], total_reward))
    
    components = {
        'r_tracking': r_tracking,
        'r_stability': r_stability,
        'r_safety': r_safety
    }
    
    return total_reward, components