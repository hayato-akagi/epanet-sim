"""
Temporal Slice Generator

Visualization: Spacetime diagram
- X-axis: Time (past → present)
- Y-axis: Spatial (network nodes)
- Color: Pressure or flow
"""
import numpy as np
import matplotlib.pyplot as plt
from generators.base import BaseGenerator
from utils import fig_to_bytes, normalize_value
from config import NETWORK_NODES, CONTROL_NODE


class TemporalSliceGenerator(BaseGenerator):
    """
    Generate temporal slice showing pressure evolution across network
    """
    
    def __init__(self, history_window=20):
        super().__init__('temporal_slice')
        self.history_window = history_window
    
    def generate(self, state, history, prev_state, size=(256, 256)):
        """Generate temporal slice"""
        fig, ax = self.create_figure(size)
        
        # Get pressure history
        pressure_history = history.get('pressure', [])
        
        # Pad if not enough history
        if len(pressure_history) < self.history_window:
            padding = [pressure_history[0] if pressure_history else 30.0] * \
                     (self.history_window - len(pressure_history))
            pressure_history = padding + pressure_history
        else:
            pressure_history = pressure_history[-self.history_window:]
        
        # Create time-space matrix
        # Rows: Nodes (spatial)
        # Cols: Time steps
        num_nodes = len(NETWORK_NODES)
        num_steps = len(pressure_history)
        
        # For simplicity, use same pressure for all nodes (can be extended)
        matrix = np.zeros((num_nodes, num_steps))
        
        for i in range(num_nodes):
            for j in range(num_steps):
                # Use actual pressure for control node
                # Add spatial variation for other nodes
                base_pressure = pressure_history[j]
                spatial_variation = np.sin(i * np.pi / num_nodes) * 2
                matrix[i, j] = base_pressure + spatial_variation
        
        # Normalize for colormap
        vmin, vmax = 20, 50
        
        # Plot heatmap
        im = ax.imshow(matrix, aspect='auto', cmap='viridis',
                      vmin=vmin, vmax=vmax, origin='lower',
                      interpolation='bilinear')
        
        # Remove ticks and labels (pure visual)
        ax.set_xticks([])
        ax.set_yticks([])
        
        # Subtle grid
        ax.grid(False)
        
        ax.set_xlim(-0.5, num_steps - 0.5)
        ax.set_ylim(-0.5, num_nodes - 0.5)
        
        # Convert to bytes
        img_bytes = fig_to_bytes(fig)
        self.close_figure(fig)
        
        return img_bytes