"""
VLA Controller with automatic episode statistics calculation
DEBUG VERSION with extensive logging
"""
import os
import time
import numpy as np
import torch

from models.replay_buffer import ReplayBuffer
from utils.training_logger import TrainingLogger


class VLAController:
    """VLA Controller with online learning and automatic episode tracking"""
    
    def __init__(self, loop_id, vla_model, agent, reward_calculator, 
                 image_fetcher, prompt_generator, data_logger,
                 exp_id, exp_result_dir, config):
        """
        Initialize VLA Controller
        
        Args:
            loop_id: Control loop ID
            vla_model: VLA model instance
            agent: RL agent (SAC)
            reward_calculator: Reward calculator
            image_fetcher: Image fetcher
            prompt_generator: Prompt generator
            data_logger: Data logger for sending to data-collector
            exp_id: Experiment ID
            exp_result_dir: Result directory path
            config: VLA configuration dict
        """
        self.loop_id = loop_id
        self.vla_model = vla_model
        self.agent = agent
        self.reward_calculator = reward_calculator
        self.image_fetcher = image_fetcher
        self.prompt_generator = prompt_generator
        self.data_logger = data_logger
        self.exp_id = exp_id
        self.exp_result_dir = exp_result_dir
        self.config = config
        
        # Training configuration
        training_config = config.get('training', {})
        self.buffer_size = training_config.get('buffer_size', 10000)
        self.batch_size = training_config.get('batch_size', 256)
        self.learning_starts = training_config.get('learning_starts', 1000)
        self.update_frequency = training_config.get('update_frequency', 1)
        self.gradient_steps = training_config.get('gradient_steps', 1)
        
        # Episode configuration
        self.max_steps_per_episode = self._calculate_max_steps()
        
        # Initialize replay buffer
        self.replay_buffer = ReplayBuffer(self.buffer_size)
        
        # Initialize training logger
        print(f"[VLAController] Training logs will be saved to: {exp_result_dir}")
        print(f"  - training_steps.csv")
        print(f"  - training_episodes.csv")
        self.training_logger = TrainingLogger(exp_result_dir, exp_id)
        
        # Episode tracking variables
        self.current_episode = 0
        self.step_in_episode = 0
        self.total_steps = 0
        self.episode_buffer = []  # Store data for current episode
        
        # State tracking
        self.prev_state = None
        self.prev_action = None
        
        # Learning tracking
        self.last_actor_loss = 0.0
        self.last_critic_loss = 0.0
        self.last_q_value = 0.0
        
        print(f"[VLAController] Initialized: {loop_id}")
        print(f"  Model: {config.get('model_type', 'unknown')}")
        print(f"  Learning Mode: {config.get('learning_mode', 'online')}")
        print(f"  Max steps per episode: {self.max_steps_per_episode}")
        print(f"  [DEBUG] Episode buffer initialized (size=0)")
    
    def _calculate_max_steps(self):
        """Calculate maximum steps per episode from simulation config"""
        # This should be passed from experiment config
        # For now, use a default value
        # TODO: Get this from exp_vla.json
        max_steps = 144  # 24 hours at 600 second intervals
        print(f"[DEBUG] _calculate_max_steps() = {max_steps}")
        return max_steps
    
    def compute_action(self, sensor_data, step, time_step):
        """
        Compute control action using VLA model
        
        Args:
            sensor_data: Dictionary containing sensor readings
            step: Current step number
            time_step: Current simulation time
            
        Returns:
            delta_action: Action to take (delta valve setting)
        """
        print(f"[DEBUG] compute_action called: step={step}, time_step={time_step}")
        print(f"[DEBUG]   sensor_data keys: {sensor_data.keys()}")
        
        # Fetch images
        print(f"[DEBUG] Fetching images...")
        images = self.image_fetcher.fetch(self.exp_id, step, sensor_data)
        print(f"[DEBUG]   Got {len(images)} images: {list(images.keys())}")
        
        # Generate prompt
        print(f"[DEBUG] Generating prompt...")
        prompt = self.prompt_generator.generate(sensor_data=sensor_data)
        print(f"[DEBUG]   Prompt length: {len(prompt)} chars")
        
        # Construct state
        current_state = {
            'images': images,
            'prompt': prompt,
            'pressure': sensor_data['pressure'],
            'target': sensor_data['target'],
            'prev_action': sensor_data.get('prev_action', 0.0)
        }
        
        # Select action
        print(f"[DEBUG] Selecting action...")
        
        # Exploration vs exploitation
        exploration_config = self.config.get('exploration', {})
        initial_random_steps = exploration_config.get('initial_random_steps', 500)
        
        if self.total_steps < initial_random_steps:
            # Random exploration
            action_config = self.config.get('action', {})
            delta_range = action_config.get('delta_range', [-0.05, 0.05])
            delta_action = np.random.uniform(delta_range[0], delta_range[1])
            print(f"[DEBUG]   Random exploration: delta_action={delta_action}")
        else:
            # Use agent
            delta_action = self.agent.select_action(
                images=images,
                prompt=prompt,
                deterministic=False
            )
            print(f"[DEBUG]   Agent action: delta_action={delta_action}")
        
        # If we have previous state, perform learning step
        if self.prev_state is not None:
            print(f"[DEBUG] Calling step() with prev_state...")
            
            # Calculate reward
            reward_components = self.reward_calculator.calculate(
                current_pressure=sensor_data['pressure'],
                target_pressure=sensor_data['target'],
                prev_pressure=self.prev_state['pressure'],
                valve_change=abs(delta_action),
                time_step=time_step
            )
            reward = reward_components['total_reward']
            
            print(f"[DEBUG]   Reward: {reward}")
            
            # Store transition and learn
            done = False  # Will be updated by episode detection
            self.step(
                state=self.prev_state,
                action=self.prev_action,
                reward=reward,
                next_state=current_state,
                done=done,
                reward_components=reward_components,
                step=step,
                time_step=time_step
            )
        else:
            print(f"[DEBUG] First step, no prev_state yet")
        
        # Update previous state and action
        self.prev_state = current_state
        self.prev_action = delta_action
        
        return delta_action
    
    def step(self, state, action, reward, next_state, done, 
             reward_components, step, time_step):
        """
        Process one step of interaction
        
        Args:
            state: Current state
            action: Action taken
            reward: Reward received
            next_state: Next state
            done: Episode done flag
            reward_components: Breakdown of reward
            step: Step number
            time_step: Simulation time
        """
        print(f"[DEBUG] step() called: total_steps={self.total_steps}, step_in_episode={self.step_in_episode}")
        
        # Add to replay buffer
        self.replay_buffer.add(state, action, reward, next_state, done)
        
        # Increment counters
        self.total_steps += 1
        self.step_in_episode += 1
        
        print(f"[DEBUG]   After increment: total_steps={self.total_steps}, step_in_episode={self.step_in_episode}")
        
        # Perform learning updates
        actor_loss = 0.0
        critic_loss = 0.0
        q_value = 0.0
        
        if self.total_steps >= self.learning_starts:
            if self.total_steps % self.update_frequency == 0:
                for _ in range(self.gradient_steps):
                    # Sample batch from replay buffer
                    batch = self.replay_buffer.sample(self.batch_size)
                    if batch is not None:
                        losses = self.agent.update(batch)
                        if losses:
                            actor_loss = losses.get('actor_loss', 0.0)
                            critic_loss = losses.get('critic_loss', 0.0)
                            q_value = losses.get('q_value', 0.0)
        
        # Store losses for logging
        self.last_actor_loss = actor_loss
        self.last_critic_loss = critic_loss
        self.last_q_value = q_value
        
        # Log step data
        step_data = {
            'timestamp': time.strftime('%Y-%m-%dT%H:%M:%S.%f'),
            'episode': self.current_episode,
            'step_in_episode': step,
            'total_steps': self.total_steps,
            'time_step': time_step,
            'pressure': state['pressure'],
            'target_pressure': state['target'],
            'valve_setting': state['prev_action'],
            'delta_action': action,
            'reward': reward,
            'reward_tracking': reward_components.get('tracking', 0.0),
            'reward_stability': reward_components.get('stability', 0.0),
            'reward_safety': reward_components.get('safety', 0.0),
            'q_value': q_value,
            'actor_loss': actor_loss,
            'critic_loss': critic_loss,
            'buffer_size': len(self.replay_buffer),
            'learning_mode': 'online',
            'exploration': self.total_steps < self.config.get('exploration', {}).get('initial_random_steps', 500)
        }
        
        # Add to episode buffer
        self.episode_buffer.append(step_data)
        print(f"[DEBUG]   Added to episode_buffer (size now: {len(self.episode_buffer)})")
        
        # Log to CSV
        self.training_logger.log_step(step_data)
        
        # Check for episode end
        print(f"[DEBUG]   Checking episode end: step_in_episode={self.step_in_episode} vs max={self.max_steps_per_episode}")
        
        # Method 1: Check done flag (if provided by sim-runner)
        # Method 2: Check step count
        if done or self.step_in_episode >= self.max_steps_per_episode:
            print(f"\n{'='*60}")
            print(f"[VLAController] EPISODE {self.current_episode} COMPLETED!")
            print(f"{'='*60}")
            print(f"  Total steps in episode: {self.step_in_episode}")
            print(f"  Episode buffer size: {len(self.episode_buffer)}")
            print(f"  Calling _finish_episode()...")
            
            self._finish_episode()
            
            # Reset for next episode
            self.current_episode += 1
            self.step_in_episode = 0
            self.prev_state = None
            self.prev_action = None
            
            print(f"  Next episode: {self.current_episode}")
            print(f"{'='*60}\n")
        else:
            print(f"[DEBUG]   Episode not finished yet ({self.step_in_episode}/{self.max_steps_per_episode})")
    
    def _finish_episode(self):
        """Calculate and log episode statistics"""
        print(f"[DEBUG] _finish_episode() called")
        print(f"[DEBUG]   episode_buffer size: {len(self.episode_buffer)}")
        
        if len(self.episode_buffer) == 0:
            print("[WARNING] Episode buffer is empty, skipping episode logging")
            return
        
        # Calculate episode statistics
        print(f"[DEBUG]   Calling _calculate_episode_stats()...")
        try:
            episode_stats = self._calculate_episode_stats()
            print(f"[DEBUG]   Episode stats calculated successfully")
            print(f"[DEBUG]   Stats keys: {episode_stats.keys()}")
        except Exception as e:
            print(f"[ERROR] Failed to calculate episode stats: {e}")
            import traceback
            traceback.print_exc()
            return
        
        # Log to CSV
        print(f"[DEBUG]   Calling training_logger.log_episode()...")
        try:
            self.training_logger.log_episode(episode_stats)
            print(f"[DEBUG]   Episode stats logged to CSV successfully")
        except Exception as e:
            print(f"[ERROR] Failed to log episode stats: {e}")
            import traceback
            traceback.print_exc()
            return
        
        # Print summary
        print(f"\n  Episode {episode_stats['episode']} Summary:")
        print(f"  ├─ Episode reward: {episode_stats['episode_reward']:.3f}")
        print(f"  ├─ Mean reward: {episode_stats['mean_reward']:.3f}")
        print(f"  ├─ MAE: {episode_stats['mae']:.3f} m")
        print(f"  ├─ RMSE: {episode_stats['rmse']:.3f} m")
        print(f"  ├─ Max error: {episode_stats['max_error']:.3f} m")
        print(f"  ├─ Mean critic loss: {episode_stats['mean_critic_loss']:.4f}")
        print(f"  ├─ Mean actor loss: {episode_stats['mean_actor_loss']:.4f}")
        print(f"  └─ Buffer size: {episode_stats['buffer_size']}\n")
        
        # Clear episode buffer for next episode
        print(f"[DEBUG]   Clearing episode_buffer...")
        self.episode_buffer.clear()
        print(f"[DEBUG]   Episode buffer cleared (size now: {len(self.episode_buffer)})")
    
    def _calculate_episode_stats(self):
        """
        Calculate statistics for the completed episode
        
        Returns:
            dict: Episode statistics
        """
        print(f"[DEBUG] _calculate_episode_stats() called")
        print(f"[DEBUG]   Processing {len(self.episode_buffer)} steps")
        
        # Extract data from episode buffer
        rewards = [s['reward'] for s in self.episode_buffer]
        pressures = [s['pressure'] for s in self.episode_buffer]
        targets = [s['target_pressure'] for s in self.episode_buffer]
        actor_losses = [s['actor_loss'] for s in self.episode_buffer]
        critic_losses = [s['critic_loss'] for s in self.episode_buffer]
        q_values = [s['q_value'] for s in self.episode_buffer]
        delta_actions = [s['delta_action'] for s in self.episode_buffer]
        
        print(f"[DEBUG]   Extracted data arrays")
        print(f"[DEBUG]     rewards: {len(rewards)} values, first 3: {rewards[:3]}")
        print(f"[DEBUG]     pressures: {len(pressures)} values")
        print(f"[DEBUG]     targets: {len(targets)} values")
        
        # Calculate errors
        errors = [abs(p - t) for p, t in zip(pressures, targets)]
        squared_errors = [(p - t)**2 for p, t in zip(pressures, targets)]
        
        print(f"[DEBUG]   Calculated errors")
        print(f"[DEBUG]     errors: first 3: {errors[:3]}")
        
        # Calculate statistics
        episode_stats = {
            'timestamp': self.episode_buffer[-1]['timestamp'],
            'episode': self.current_episode,
            'total_steps': self.total_steps,
            'episode_steps': len(self.episode_buffer),
            'episode_reward': sum(rewards),
            'mean_reward': np.mean(rewards),
            'mean_actor_loss': np.mean(actor_losses),
            'mean_critic_loss': np.mean(critic_losses),
            'mean_q_value': np.mean(q_values),
            'buffer_size': len(self.replay_buffer),
            'mae': np.mean(errors),
            'rmse': np.sqrt(np.mean(squared_errors)),
            'max_error': max(errors),
            'mean_valve_change': np.mean([abs(da) for da in delta_actions])
        }
        
        print(f"[DEBUG]   Calculated statistics:")
        print(f"[DEBUG]     episode_reward: {episode_stats['episode_reward']}")
        print(f"[DEBUG]     mae: {episode_stats['mae']}")
        print(f"[DEBUG]     rmse: {episode_stats['rmse']}")
        
        return episode_stats
    
    def save_checkpoint(self, filepath):
        """Save model checkpoint"""
        checkpoint = {
            'vla_model_state': self.vla_model.state_dict(),
            'agent_state': self.agent.get_state(),
            'episode': self.current_episode,
            'total_steps': self.total_steps,
            'config': self.config
        }
        torch.save(checkpoint, filepath)
        print(f"[VLAController] Checkpoint saved: {filepath}")
    
    def load_checkpoint(self, filepath):
        """Load model checkpoint"""
        checkpoint = torch.load(filepath)
        self.vla_model.load_state_dict(checkpoint['vla_model_state'])
        self.agent.load_state(checkpoint['agent_state'])
        self.current_episode = checkpoint['episode']
        self.total_steps = checkpoint['total_steps']
        print(f"[VLAController] Checkpoint loaded: {filepath}")
        print(f"  Episode: {self.current_episode}")
        print(f"  Total steps: {self.total_steps}")