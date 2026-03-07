import numpy as np


class DummyAgent:
    """
    テスト用のダミーエージェント
    
    シンプルなルールベース制御を実装
    """
    
    def __init__(self):
        print("Initialized Dummy Agent")
    
    def predict(self, images, prompt):
        """
        ダミー推論
        
        プロンプトから現在値と目標値を抽出し、
        簡単な比例制御を行う
        
        Args:
            images: 画像辞書（使用しない）
            prompt: プロンプト文字列
        
        Returns:
            float: Δvalve
        """
        import re
        
        # プロンプトから数値を抽出
        current_match = re.search(r'Current \w+: ([\d.]+)', prompt)
        target_match = re.search(r'[Tt]arget[:\s]+([\d.]+)', prompt)
        
        if current_match and target_match:
            current = float(current_match.group(1))
            target = float(target_match.group(1))
            
            # 簡単な比例制御
            error = target - current
            kp = 0.01  # 比例ゲイン
            
            delta_valve = kp * error
            
            # クリッピング
            delta_valve = np.clip(delta_valve, -0.05, 0.05)
            
            return float(delta_valve)
        else:
            # パースに失敗した場合はランダム
            return float(np.random.uniform(-0.01, 0.01))