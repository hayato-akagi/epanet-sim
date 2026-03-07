import numpy as np
import random
from collections import deque


class ReplayBuffer:
    """Experience Replay Buffer for off-policy RL"""
    
    def __init__(self, capacity=10000):
        """
        Args:
            capacity: Maximum number of transitions to store
        """
        self.capacity = capacity
        self.buffer = deque(maxlen=capacity)
        self.position = 0
    
    def add(self, obs, action, reward, next_obs, done):
        """
        Add a transition to the buffer
        
        Args:
            obs: Observation (dict with 'images' and 'prompt')
            action: Action taken (float)
            reward: Reward received (float)
            next_obs: Next observation (dict)
            done: Episode done flag (bool)
        """
        transition = {
            'obs': obs,
            'action': action,
            'reward': reward,
            'next_obs': next_obs,
            'done': done
        }
        
        self.buffer.append(transition)
    
    def sample(self, batch_size):
        """
        Sample a batch of transitions
        
        Args:
            batch_size: Number of transitions to sample
        
        Returns:
            dict: Batch of transitions
        """
        if len(self.buffer) < batch_size:
            batch_size = len(self.buffer)
        
        batch = random.sample(self.buffer, batch_size)
        
        # Unpack batch
        obs_batch = [t['obs'] for t in batch]
        action_batch = [t['action'] for t in batch]
        reward_batch = [t['reward'] for t in batch]
        next_obs_batch = [t['next_obs'] for t in batch]
        done_batch = [t['done'] for t in batch]
        
        return {
            'obs': obs_batch,
            'action': np.array(action_batch, dtype=np.float32),
            'reward': np.array(reward_batch, dtype=np.float32),
            'next_obs': next_obs_batch,
            'done': np.array(done_batch, dtype=np.float32)
        }
    
    def __len__(self):
        """Return current buffer size"""
        return len(self.buffer)
    
    def clear(self):
        """Clear the buffer"""
        self.buffer.clear()
        self.position = 0