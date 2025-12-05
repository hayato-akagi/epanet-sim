"""
Phase Space Plot Generator

Visualization: State space (phase portrait)
- X-axis: Control error (target - actual)
- Y-axis: Error derivative (rate of change)
- Color: Valve opening
- Trajectory shows recent history
- Origin (0,0) is the goal
"""
import numpy as np
import matplotlib.pyplot as plt
from generators.base import BaseGenerator
from utils import fig_to_bytes, calculate_derivative, normalize_value


class PhaseSpaceGenerator(BaseGenerator):
    """
    Generate phase space plot showing control dynamics
    """
    
    def __init__(self, trajectory_length=10):
        super().__init__('phase_space')
        self.trajectory_length = trajectory_length
    
    def generate(self, state, history, prev_state, size=(256, 256)):
        """Generate phase space plot"""
        fig, ax = self.create_figure(size)
        
        # Get current state
        pressure = self.get_safe_value(state, 'pressure', 30.0)
        target = self.get_safe_value(state, 'target_pressure', 120.0)
        valve = self.get_safe_value(state, 'valve_setting', 0.5)
        
        # Current error
        error = target - pressure
        
        # Error derivative
        error_derivative = calculate_derivative(history, 'pressure', window=3)
        # Flip sign because pressure increase means error decrease
        error_derivative = -error_derivative
        
        # Get trajectory history
        pressure_history = history.get('pressure', [])
        
        if len(pressure_history) >= 2:
            # Calculate trajectory
            errors = []
            derivatives = []
            
            for i in range(max(0, len(pressure_history) - self.trajectory_length), 
                          len(pressure_history)):
                hist_pressure = pressure_history[i]
                hist_error = target - hist_pressure
                errors.append(hist_error)
                
                # Calculate derivative at this point
                if i > 0:
                    deriv = -(pressure_history[i] - pressure_history[i-1])
                    derivatives.append(deriv)
                else:
                    derivatives.append(0)
            
            # Plot trajectory (fading line)
            if len(errors) > 1:
                for i in range(len(errors) - 1):
                    alpha = (i + 1) / len(errors)
                    ax.plot(errors[i:i+2], derivatives[i:i+2],
                           'b-', alpha=alpha * 0.5, linewidth=1)
        
        # Plot current point
        # Color based on valve opening
        valve_color = plt.cm.RdYlGn(valve)
        
        ax.scatter([error], [error_derivative], 
                  s=200, c=[valve_color], 
                  edgecolors='black', linewidths=2, zorder=10)
        
        # Goal point (origin)
        ax.scatter([0], [0], s=300, marker='*', 
                  c='gold', edgecolors='black', linewidths=2, zorder=5)
        
        # Quadrants (visual guides)
        ax.axhline(0, color='gray', linestyle='--', linewidth=0.5, alpha=0.5)
        ax.axvline(0, color='gray', linestyle='--', linewidth=0.5, alpha=0.5)
        
        # Set limits
        max_error = max(abs(error), 15)
        max_deriv = max(abs(error_derivative), 2)
        
        ax.set_xlim(-max_error * 1.2, max_error * 1.2)
        ax.set_ylim(-max_deriv * 1.2, max_deriv * 1.2)
        
        ax.set_aspect('equal', adjustable='box')
        
        # Remove ticks (pure visual)
        ax.set_xticks([])
        ax.set_yticks([])
        
        # Subtle box
        for spine in ax.spines.values():
            spine.set_edgecolor('gray')
            spine.set_linewidth(0.5)
        
        # Convert to bytes
        img_bytes = fig_to_bytes(fig)
        self.close_figure(fig)
        
        return img_bytes