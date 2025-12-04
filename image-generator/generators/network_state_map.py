"""
Network State Map Generator

Visualization: Network topology with pressure heatmap (colors) and flow thickness (line width)
No text labels - pure visual representation
"""
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.patches import Circle
from generators.base import BaseGenerator
from utils import fig_to_bytes, normalize_value
from config import NETWORK_NODES, NETWORK_LINKS, CONTROL_NODE


class NetworkStateMapGenerator(BaseGenerator):
    """
    Generate network topology with:
    - Node colors represent pressure (heatmap)
    - Edge thickness represents flow
    - Control node highlighted with special marker
    """
    
    def __init__(self):
        super().__init__('network_state_map')
    
    def generate(self, state, history, prev_state, size=(256, 256)):
        """Generate network state map"""
        fig, ax = self.create_figure(size)
        
        # Get current values
        pressure = self.get_safe_value(state, 'pressure', 30.0)
        flow = self.get_safe_value(state, 'flow', 100.0)
        valve = self.get_safe_value(state, 'valve_setting', 0.5)
        
        # Draw links (edges) with thickness based on flow
        # Normalize flow to [0.5, 3.0] for line width
        flow_normalized = normalize_value(flow, 50, 150)
        link_width = 0.5 + flow_normalized * 2.5
        
        for start, end in NETWORK_LINKS:
            x_start, y_start = NETWORK_NODES[start]
            x_end, y_end = NETWORK_NODES[end]
            
            ax.plot([x_start, x_end], [y_start, y_end], 
                   'k-', linewidth=link_width, alpha=0.6, zorder=1)
        
        # Draw nodes with pressure-based colors
        for node_id, (x, y) in NETWORK_NODES.items():
            # Use actual pressure for control node, estimate for others
            if node_id == CONTROL_NODE:
                node_pressure = pressure
            else:
                # Simplified: estimate based on distance from control node
                node_pressure = pressure * 0.95  # Placeholder
            
            # Normalize pressure to [0, 1] for colormap (20-50m range)
            color_val = normalize_value(node_pressure, 20, 50)
            color = plt.cm.viridis(color_val)
            
            # Node size
            radius = 0.3
            
            circle = Circle((x, y), radius, color=color, 
                          ec='white', linewidth=1.5, zorder=2)
            ax.add_patch(circle)
        
        # Highlight control node (no text, just visual marker)
        cx, cy = NETWORK_NODES[CONTROL_NODE]
        
        # Outer ring for control node
        highlight = Circle((cx, cy), 0.4, fill=False, 
                         ec='red', linewidth=2.5, zorder=3)
        ax.add_patch(highlight)
        
        # Valve indicator at control node (size based on valve opening)
        valve_marker = Circle((cx, cy), 0.15 * valve, 
                            color='magenta', alpha=0.8, zorder=4)
        ax.add_patch(valve_marker)
        
        ax.set_xlim(-2, 2)
        ax.set_ylim(-2, 7)
        ax.set_aspect('equal')
        ax.axis('off')
        
        # Convert to bytes
        img_bytes = fig_to_bytes(fig)
        self.close_figure(fig)
        
        return img_bytes