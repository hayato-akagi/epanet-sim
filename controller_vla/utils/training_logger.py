import os
import csv
import time
from datetime import datetime
from threading import Lock


class TrainingLogger:
    """
    学習の進行状況をCSVファイルに記録
    
    可視化用に以下の情報を保存：
    - エピソード/ステップ情報
    - 報酬の推移
    - 損失の推移
    - バッファサイズ
    - その他の統計情報
    """
    
    def __init__(self, output_dir, exp_id):
        """
        Args:
            output_dir: 出力ディレクトリ（例: /shared/results/net1_vla_001）
            exp_id: 実験ID
        """
        self.output_dir = output_dir
        self.exp_id = exp_id
        self.lock = Lock()
        
        # CSVファイルパス
        self.step_log_path = os.path.join(output_dir, "training_steps.csv")
        self.episode_log_path = os.path.join(output_dir, "training_episodes.csv")
        
        # ディレクトリ作成
        os.makedirs(output_dir, exist_ok=True)
        
        # CSVファイル初期化
        self._initialize_step_log()
        self._initialize_episode_log()
        
        print(f"[TrainingLogger] Initialized")
        print(f"  Step log: {self.step_log_path}")
        print(f"  Episode log: {self.episode_log_path}")
    
    def _initialize_step_log(self):
        """ステップログのCSVヘッダーを作成"""
        if not os.path.exists(self.step_log_path):
            with open(self.step_log_path, 'w', newline='') as f:
                writer = csv.writer(f)
                writer.writerow([
                    'timestamp',
                    'episode',
                    'step_in_episode',
                    'total_steps',
                    'time_step',
                    'pressure',
                    'target_pressure',
                    'valve_setting',
                    'delta_action',
                    'reward',
                    'reward_tracking',
                    'reward_stability',
                    'reward_safety',
                    'q_value',
                    'actor_loss',
                    'critic_loss',
                    'buffer_size',
                    'learning_mode',
                    'exploration'
                ])
    
    def _initialize_episode_log(self):
        """エピソードログのCSVヘッダーを作成"""
        if not os.path.exists(self.episode_log_path):
            with open(self.episode_log_path, 'w', newline='') as f:
                writer = csv.writer(f)
                writer.writerow([
                    'timestamp',
                    'episode',
                    'total_steps',
                    'episode_steps',
                    'episode_reward',
                    'mean_reward',
                    'mean_actor_loss',
                    'mean_critic_loss',
                    'mean_q_value',
                    'buffer_size',
                    'mae',
                    'rmse',
                    'max_error',
                    'mean_valve_change'
                ])
    
    def log_step(self, step_data):
        """
        ステップごとのデータを記録
        
        Args:
            step_data: dict with keys:
                - episode: エピソード番号
                - step_in_episode: エピソード内ステップ
                - total_steps: 累積ステップ数
                - time_step: シミュレーション時刻
                - pressure: 圧力
                - target_pressure: 目標圧力
                - valve_setting: バルブ開度
                - delta_action: Δvalve
                - reward: 即時報酬
                - reward_tracking: 追従報酬
                - reward_stability: 安定性報酬
                - reward_safety: 安全制約報酬
                - q_value: Q値
                - actor_loss: Actor損失
                - critic_loss: Critic損失
                - buffer_size: バッファサイズ
                - learning_mode: 学習モード
                - exploration: 探索中か
        """
        with self.lock:
            try:
                with open(self.step_log_path, 'a', newline='') as f:
                    writer = csv.writer(f)
                    writer.writerow([
                        datetime.now().isoformat(),
                        step_data.get('episode', 0),
                        step_data.get('step_in_episode', 0),
                        step_data.get('total_steps', 0),
                        step_data.get('time_step', 0),
                        step_data.get('pressure', 0.0),
                        step_data.get('target_pressure', 0.0),
                        step_data.get('valve_setting', 0.0),
                        step_data.get('delta_action', 0.0),
                        step_data.get('reward', 0.0),
                        step_data.get('reward_tracking', 0.0),
                        step_data.get('reward_stability', 0.0),
                        step_data.get('reward_safety', 0.0),
                        step_data.get('q_value', 0.0),
                        step_data.get('actor_loss', 0.0),
                        step_data.get('critic_loss', 0.0),
                        step_data.get('buffer_size', 0),
                        step_data.get('learning_mode', 'online'),
                        step_data.get('exploration', True)
                    ])
            except Exception as e:
                print(f"[TrainingLogger] Error logging step: {e}")
    
    def log_episode(self, episode_data):
        """
        エピソード終了時のデータを記録
        
        Args:
            episode_data: dict with keys:
                - episode: エピソード番号
                - total_steps: 累積ステップ数
                - episode_steps: このエピソードのステップ数
                - episode_reward: エピソード累積報酬
                - mean_reward: 平均報酬
                - mean_actor_loss: 平均Actor損失
                - mean_critic_loss: 平均Critic損失
                - mean_q_value: 平均Q値
                - buffer_size: バッファサイズ
                - mae: 平均絶対誤差
                - rmse: 二乗平均平方根誤差
                - max_error: 最大誤差
                - mean_valve_change: 平均バルブ変化量
        """
        with self.lock:
            try:
                with open(self.episode_log_path, 'a', newline='') as f:
                    writer = csv.writer(f)
                    writer.writerow([
                        datetime.now().isoformat(),
                        episode_data.get('episode', 0),
                        episode_data.get('total_steps', 0),
                        episode_data.get('episode_steps', 0),
                        episode_data.get('episode_reward', 0.0),
                        episode_data.get('mean_reward', 0.0),
                        episode_data.get('mean_actor_loss', 0.0),
                        episode_data.get('mean_critic_loss', 0.0),
                        episode_data.get('mean_q_value', 0.0),
                        episode_data.get('buffer_size', 0),
                        episode_data.get('mae', 0.0),
                        episode_data.get('rmse', 0.0),
                        episode_data.get('max_error', 0.0),
                        episode_data.get('mean_valve_change', 0.0)
                    ])
                
                # エピソード終了時にプリント
                print(f"\n[TrainingLogger] Episode {episode_data.get('episode', 0)} Summary:")
                print(f"  Steps: {episode_data.get('episode_steps', 0)}")
                print(f"  Total Reward: {episode_data.get('episode_reward', 0.0):.3f}")
                print(f"  Mean Reward: {episode_data.get('mean_reward', 0.0):.3f}")
                print(f"  MAE: {episode_data.get('mae', 0.0):.3f}")
                print(f"  Actor Loss: {episode_data.get('mean_actor_loss', 0.0):.6f}")
                print(f"  Critic Loss: {episode_data.get('mean_critic_loss', 0.0):.6f}")
                
            except Exception as e:
                print(f"[TrainingLogger] Error logging episode: {e}")
    
    def flush(self):
        """ファイルをフラッシュ（明示的な書き込み）"""
        # Python CSVは自動的にフラッシュされるが、明示的に呼ぶことも可能
        pass