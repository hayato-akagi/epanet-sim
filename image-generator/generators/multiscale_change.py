"""
Multiscale Change Map Generator

Visualization: RGB encoding of changes at multiple time scales
- R channel: Short-term change (last 3 steps)
- G channel: Medium-term change (last 10 steps)
- B channel: Long-term change (last 30 steps)

Each pixel represents a node in the network
"""
import numpy as np
import matplotlib.pyplot as plt
from PIL import Image
from generators.base import BaseGenerator
from utils import image_to_bytes, get_multiscale_changes, normalize_value
from config import NETWORK_NODES


class MultiscaleChangeGenerator(BaseGenerator):
    """
    Generate multiscale change map using RGB channels
    """
    
    def __init__(self, scales=[3, 10, 30]):
        super().__init__('multiscale_change')
        self.scales = scales
    
    def generate(self, state, history, prev_state, size=(256, 256)):
        """Generate multiscale change map"""
        
        # Get changes at multiple scales
        pressure_changes = get_multiscale_changes(history, 'pressure', self.scales)
        flow_changes = get_multiscale_changes(history, 'flow', self.scales)
        valve_changes = get_multiscale_changes(history, 'valve_setting', self.scales)
        
        # Create image
        # Layout: Grid representing network
        grid_size = int(np.ceil(np.sqrt(len(NETWORK_NODES))))
        img_size = (grid_size * 32, grid_size * 32)  # Each cell is 32x32
        
        img_array = np.zeros((img_size[1], img_size[0], 3), dtype=np.uint8)
        
        # Map nodes to grid positions
        node_list = list(NETWORK_NODES.keys())
        
        for idx, node_id in enumerate(node_list):
            row = idx // grid_size
            col = idx % grid_size
            
            # Use pressure changes for this node
            # Normalize changes to [0, 255]
            # Positive change = brighter, negative = darker
            r = self._normalize_change(pressure_changes[0], max_change=5)
            g = self._normalize_change(pressure_changes[1], max_change=10)
            b = self._normalize_change(pressure_changes[2], max_change=15)
            
            # Fill cell
            y_start = row * 32
            y_end = (row + 1) * 32
            x_start = col * 32
            x_end = (col + 1) * 32
            
            img_array[y_start:y_end, x_start:x_end, 0] = r
            img_array[y_start:y_end, x_start:x_end, 1] = g
            img_array[y_start:y_end, x_start:x_end, 2] = b
        
        # Add network layout overlay
        # Draw connections as thin lines
        for start, end in __import__('config').NETWORK_LINKS:
            if start in node_list and end in node_list:
                idx_start = node_list.index(start)
                idx_end = node_list.index(end)
                
                row_start = idx_start // grid_size
                col_start = idx_start % grid_size
                row_end = idx_end // grid_size
                col_end = idx_end % grid_size
                
                # Draw line (simplified - just mark endpoints)
                y_start = (row_start * 32) + 16
                x_start = (col_start * 32) + 16
                y_end = (row_end * 32) + 16
                x_end = (col_end * 32) + 16
                
                # Simple line drawing
                steps = max(abs(y_end - y_start), abs(x_end - x_start))
                if steps > 0:
                    for i in range(steps):
                        t = i / steps
                        y = int(y_start + t * (y_end - y_start))
                        x = int(x_start + t * (x_end - x_start))
                        
                        if 0 <= y < img_size[1] and 0 <= x < img_size[0]:
                            img_array[y, x] = [255, 255, 255]  # White line
        
        # Resize to target size
        pil_img = Image.fromarray(img_array, mode='RGB')
        pil_img = pil_img.resize(size, Image.Resampling.BILINEAR)
        
        return image_to_bytes(pil_img)
    
    def _normalize_change(self, change, max_change=10):
        """
        Normalize change to [0, 255]
        
        Args:
            change: Change value
            max_change: Maximum expected change
        
        Returns:
            int: Pixel value (0-255)
        """
        # Map [-max_change, +max_change] to [0, 255]
        normalized = (change + max_change) / (2 * max_change)
        normalized = np.clip(normalized, 0, 1)
        return int(normalized * 255)