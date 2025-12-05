"""
Flow Vector Field Generator

Visualization: Pressure heatmap + flow direction vectors
- Background: Pressure heatmap
- Foreground: Arrows showing flow direction and magnitude
"""
import numpy as np
import matplotlib.pyplot as plt
from generators.base import BaseGenerator
from utils import fig_to_bytes, normalize_value, create_arrow
from config import NETWORK_NODES, NETWORK_LINKS


class FlowVectorFieldGenerator(BaseGenerator):
    """
    Generate flow vector field overlaid on pressure heatmap
    """
    
    def __init__(self):
        super().__init__('flow_vector_field')
    
    def generate(self, state, history, prev_state, size=(256, 256)):
        """Generate flow vector field"""
        fig, ax = self.create_figure(size)
        
        # Get current values
        pressure = self.get_safe_value(state, 'pressure', 30.0)
        flow = self.get_safe_value(state, 'flow', 100.0)
        
        # Create pressure field (background)
        # Interpolate between nodes for smooth field
        x_range = np.linspace(-2, 2, 50)
        y_range = np.linspace(-2, 7, 50)
        X, Y = np.meshgrid(x_range, y_range)
        Z = np.zeros_like(X)
        
        # Simple interpolation: inverse distance weighting
        for node_id, (nx, ny) in NETWORK_NODES.items():
            node_pressure = pressure if node_id == '2' else pressure * 0.95
            
            dist = np.sqrt((X - nx)**2 + (Y - ny)**2) + 0.1
            weight = 1.0 / dist**2
            Z += weight * node_pressure
        
        # Normalize
        Z = Z / Z.max() * 40  # Scale to pressure range
        
        # Plot pressure heatmap
        im = ax.contourf(X, Y, Z, levels=20, cmap='viridis', alpha=0.7)
        
        # Draw flow vectors on links
        flow_normalized = normalize_value(flow, 50, 150)
        
        for start, end in NETWORK_LINKS:
            x_start, y_start = NETWORK_NODES[start]
            x_end, y_end = NETWORK_NODES[end]
            
            # Arrow from start to end
            dx = (x_end - x_start) * 0.6
            dy = (y_end - y_start) * 0.6
            
            # Arrow thickness based on flow
            width = 0.01 + flow_normalized * 0.04
            
            create_arrow(ax, x_start, y_start, dx, dy,
                        color='white', width=width, head_width=width*5)
        
        ax.set_xlim(-2, 2)
        ax.set_ylim(-2, 7)
        ax.set_aspect('equal')
        ax.axis('off')
        
        # Convert to bytes
        img_bytes = fig_to_bytes(fig)
        self.close_figure(fig)
        
        return img_bytes