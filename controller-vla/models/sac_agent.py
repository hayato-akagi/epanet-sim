import torch
import torch.nn as nn
import torch.optim as optim
import numpy as np
from models.simple_dnn_vla import SimpleDNNVLA


class SACAgent:
    """
    Soft Actor-Critic Agent (簡易版)
    
    SimpleDNNVLAをベースにSACを実装
    将来的にはOpenVLAに置き換え可能
    """
    
    def __init__(self, config):
        """
        Args:
            config: VLA設定辞書
        """
        self.config = config
        training_config = config.get('training', {})
        
        # ハイパーパラメータ
        self.gamma = training_config.get('gamma', 0.99)
        self.tau = training_config.get('tau', 0.005)
        self.alpha = training_config.get('alpha', 0.2)
        self.learning_starts = training_config.get('learning_starts', 1000)
        self.batch_size = training_config.get('batch_size', 256)
        
        # Actor: SimpleDNNVLAをベースにする
        self.actor = SimpleDNNVLA()
        
        # Critic: Q-networks（簡易版）
        # 実際の実装では画像特徴も使うべきだが、
        # ここでは動作検証のため数値のみで簡略化
        self.critic_1 = self._build_critic()
        self.critic_2 = self._build_critic()
        
        # Target networks
        self.critic_1_target = self._build_critic()
        self.critic_2_target = self._build_critic()
        self.critic_1_target.load_state_dict(self.critic_1.state_dict())
        self.critic_2_target.load_state_dict(self.critic_2.state_dict())
        
        # Optimizers
        self.actor_optimizer = optim.Adam(
            self.actor.parameters(),
            lr=training_config.get('learning_rate_actor', 3e-4)
        )
        self.critic_1_optimizer = optim.Adam(
            self.critic_1.parameters(),
            lr=training_config.get('learning_rate_critic', 3e-4)
        )
        self.critic_2_optimizer = optim.Adam(
            self.critic_2.parameters(),
            lr=training_config.get('learning_rate_critic', 3e-4)
        )
        
        # 学習統計
        self.last_actor_loss = 0.0
        self.last_critic_loss = 0.0
        self.update_count = 0
        
        print("SAC Agent initialized (simplified version)")
    
    def _build_critic(self):
        """Critic networkの構築（簡易版）"""
        return nn.Sequential(
            nn.Linear(6, 128),  # [pressure, target, valve, action, upstream, downstream]
            nn.ReLU(),
            nn.Linear(128, 64),
            nn.ReLU(),
            nn.Linear(64, 1)
        )
    
    def select_action(self, images, prompt, deterministic=False):
        """
        行動を選択
        
        Args:
            images: 画像辞書
            prompt: プロンプト文字列
            deterministic: 決定的行動か（評価時True）
        
        Returns:
            float: Δvalve
        """
        print(f"[DEBUG] SAC select_action called")
        print(f"[DEBUG]   images keys: {list(images.keys())}")
        print(f"[DEBUG]   prompt length: {len(prompt)}")
        print(f"[DEBUG]   deterministic: {deterministic}")
        
        with torch.no_grad():
            print(f"[DEBUG]   Calling actor forward...")
            action = self.actor(images, prompt)
            print(f"[DEBUG]   Actor returned: {action}")
        
        # 探索ノイズ（学習時のみ）
        if not deterministic:
            noise = np.random.normal(0, 0.01)
            print(f"[DEBUG]   Adding noise: {noise}")
            action = action + noise
            action = np.clip(action, -0.05, 0.05)
        
        print(f"[DEBUG]   Final action: {action}")
        return float(action)
    
    def update(self, batch):
        """
        SACの学習更新（簡易版）
        
        現在は最小限の実装。
        本格的なSACにする場合は、画像特徴の抽出と
        Criticへの入力を拡張する必要がある。
        
        Args:
            batch: Replay bufferからのバッチ
        """
        # バッチから数値状態を抽出（簡易版）
        states = []
        actions = []
        rewards = batch['reward']
        next_states = []
        dones = batch['done']
        
        for obs in batch['obs']:
            # プロンプトから数値を抽出（簡易版）
            state = self._extract_state_from_prompt(obs['prompt'])
            states.append(state)
        
        for obs in batch['next_obs']:
            next_state = self._extract_state_from_prompt(obs['prompt'])
            next_states.append(next_state)
        
        actions = batch['action']
        
        states = torch.FloatTensor(states)
        actions = torch.FloatTensor(actions).unsqueeze(1)
        rewards = torch.FloatTensor(rewards).unsqueeze(1)
        next_states = torch.FloatTensor(next_states)
        dones = torch.FloatTensor(dones).unsqueeze(1)
        
        # Critic更新（簡易版）
        with torch.no_grad():
            # 次状態での行動（ランダムサンプリング）
            next_actions = torch.randn_like(actions) * 0.01
            next_actions = torch.clamp(next_actions, -0.05, 0.05)
            
            # Target Q-values
            next_state_actions = torch.cat([next_states, next_actions], dim=1)
            q1_next = self.critic_1_target(next_state_actions)
            q2_next = self.critic_2_target(next_state_actions)
            q_next = torch.min(q1_next, q2_next)
            
            target_q = rewards + (1 - dones) * self.gamma * q_next
        
        # Current Q-values
        state_actions = torch.cat([states, actions], dim=1)
        q1 = self.critic_1(state_actions)
        q2 = self.critic_2(state_actions)
        
        # Critic loss
        critic_1_loss = nn.MSELoss()(q1, target_q)
        critic_2_loss = nn.MSELoss()(q2, target_q)
        
        # Criticの更新
        self.critic_1_optimizer.zero_grad()
        critic_1_loss.backward()
        self.critic_1_optimizer.step()
        
        self.critic_2_optimizer.zero_grad()
        critic_2_loss.backward()
        self.critic_2_optimizer.step()
        
        # Actorの更新（簡易版：スキップ）
        # 本格実装では、Actorから行動をサンプリングして
        # Criticで評価し、Q値を最大化するように更新
        
        # Target networksのソフトアップデート
        self._soft_update(self.critic_1, self.critic_1_target)
        self._soft_update(self.critic_2, self.critic_2_target)
        
        self.last_critic_loss = (critic_1_loss.item() + critic_2_loss.item()) / 2
        self.last_actor_loss = 0.0  # 簡易版ではActor更新なし
        self.update_count += 1
        
        return {
            'critic_loss': self.last_critic_loss,
            'actor_loss': self.last_actor_loss
        }
    
    def _extract_state_from_prompt(self, prompt):
        """プロンプトから数値状態を抽出（簡易版）"""
        import re
        
        current_match = re.search(r'Current \w+: ([\d.]+)', prompt)
        target_match = re.search(r'Target: ([\d.]+)', prompt)
        valve_match = re.search(r'Valve opening: ([\d.]+)%', prompt)
        upstream_match = re.search(r'Upstream pressure: ([\d.]+)', prompt)
        downstream_match = re.search(r'Downstream pressure: ([\d.]+)', prompt)
        
        current = float(current_match.group(1)) if current_match else 30.0
        target = float(target_match.group(1)) if target_match else 30.0
        valve = float(valve_match.group(1)) / 100 if valve_match else 0.5
        upstream = float(upstream_match.group(1)) if upstream_match else 50.0
        downstream = float(downstream_match.group(1)) if downstream_match else 30.0
        
        # 正規化
        state = [
            (current - 30.0) / 10.0,
            (target - 30.0) / 10.0,
            valve,
            (upstream - 40.0) / 10.0,
            (downstream - 30.0) / 10.0
        ]
        
        return state
    
    def _soft_update(self, source, target):
        """ターゲットネットワークのソフトアップデート"""
        for target_param, param in zip(target.parameters(), source.parameters()):
            target_param.data.copy_(
                target_param.data * (1.0 - self.tau) + param.data * self.tau
            )
    
    def save(self, path):
        """モデルの保存"""
        torch.save({
            'actor': self.actor.state_dict(),
            'critic_1': self.critic_1.state_dict(),
            'critic_2': self.critic_2.state_dict(),
            'critic_1_target': self.critic_1_target.state_dict(),
            'critic_2_target': self.critic_2_target.state_dict(),
            'actor_optimizer': self.actor_optimizer.state_dict(),
            'critic_1_optimizer': self.critic_1_optimizer.state_dict(),
            'critic_2_optimizer': self.critic_2_optimizer.state_dict(),
            'update_count': self.update_count
        }, path)
        print(f"SAC model saved to {path}")
    
    def load(self, path):
        """モデルの読み込み"""
        checkpoint = torch.load(path, map_location='cpu')
        self.actor.load_state_dict(checkpoint['actor'])
        self.critic_1.load_state_dict(checkpoint['critic_1'])
        self.critic_2.load_state_dict(checkpoint['critic_2'])
        self.critic_1_target.load_state_dict(checkpoint['critic_1_target'])
        self.critic_2_target.load_state_dict(checkpoint['critic_2_target'])
        self.actor_optimizer.load_state_dict(checkpoint['actor_optimizer'])
        self.critic_1_optimizer.load_state_dict(checkpoint['critic_1_optimizer'])
        self.critic_2_optimizer.load_state_dict(checkpoint['critic_2_optimizer'])
        self.update_count = checkpoint['update_count']
        print(f"SAC model loaded from {path}")