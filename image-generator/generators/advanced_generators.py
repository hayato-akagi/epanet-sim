"""
Remaining generators (simplified implementations)
These can be expanded later
"""
import numpy as np
import matplotlib.pyplot as plt
from PIL import Image
from generators.base import BaseGenerator
from utils import fig_to_bytes, image_to_bytes, normalize_value, hsv_to_rgb
from config import NETWORK_NODES, NETWORK_LINKS


# ========================================
# 6. Energy Landscape Generator
# ========================================
class EnergyLandscapeGenerator(BaseGenerator):
    """Generate energy landscape (pressure + elevation)"""
    
    def __init__(self):
        super().__init__('energy_landscape')
    
    def generate(self, state, history, prev_state, size=(256, 256)):
        fig, ax = self.create_figure(size)
        
        pressure = self.get_safe_value(state, 'pressure', 30.0)
        
        # Create energy field
        x_range = np.linspace(-2, 2, 50)
        y_range = np.linspace(-2, 7, 50)
        X, Y = np.meshgrid(x_range, y_range)
        
        # Energy = pressure + elevation (y-coordinate as elevation)
        E = Y * 2 + pressure * 0.5
        
        # 3D-like contour plot
        ax.contourf(X, Y, E, levels=30, cmap='terrain', alpha=0.9)
        
        ax.set_xlim(-2, 2)
        ax.set_ylim(-2, 7)
        ax.set_aspect('equal')
        ax.axis('off')
        
        img_bytes = fig_to_bytes(fig)
        self.close_figure(fig)
        return img_bytes


# ========================================
# 7. Pressure Gradient Generator
# ========================================
class PressureGradientGenerator(BaseGenerator):
    """Generate pressure gradient vector field"""
    
    def __init__(self):
        super().__init__('pressure_gradient')
    
    def generate(self, state, history, prev_state, size=(256, 256)):
        fig, ax = self.create_figure(size)
        
        pressure = self.get_safe_value(state, 'pressure', 30.0)
        
        # Calculate gradients between connected nodes
        for start, end in NETWORK_LINKS:
            x_start, y_start = NETWORK_NODES[start]
            x_end, y_end = NETWORK_NODES[end]
            
            # Assume pressure gradient along link
            p_start = pressure if start == '2' else pressure * 0.95
            p_end = pressure if end == '2' else pressure * 0.9
            
            # Arrow from high to low pressure
            if p_start > p_end:
                dx = (x_end - x_start) * 0.5
                dy = (y_end - y_start) * 0.5
                color = plt.cm.Reds(0.7)
            else:
                dx = (x_start - x_end) * 0.5
                dy = (y_start - y_end) * 0.5
                color = plt.cm.Blues(0.7)
            
            ax.arrow(x_start, y_start, dx, dy,
                    color=color, width=0.02, head_width=0.1)
        
        ax.set_xlim(-2, 2)
        ax.set_ylim(-2, 7)
        ax.set_aspect('equal')
        ax.axis('off')
        
        img_bytes = fig_to_bytes(fig)
        self.close_figure(fig)
        return img_bytes


# ========================================
# 8. HSV Encoding Generator
# ========================================
class HSVEncodingGenerator(BaseGenerator):
    """
    Generate HSV-encoded image:
    - Hue: Pressure (0-360° for 20-50m)
    - Saturation: Flow (0-100%)
    - Value: Pressure change rate (bright=increasing, dark=decreasing)
    """
    
    def __init__(self):
        super().__init__('hsv_encoding')
    
    def generate(self, state, history, prev_state, size=(256, 256)):
        pressure = self.get_safe_value(state, 'pressure', 30.0)
        flow = self.get_safe_value(state, 'flow', 100.0)
        
        # Calculate change rate
        pressure_change = 0
        if prev_state:
            prev_pressure = self.get_safe_value(prev_state, 'pressure', 30.0)
            pressure_change = pressure - prev_pressure
        
        # Create HSV image
        img_array = np.zeros((size[1], size[0], 3), dtype=np.uint8)
        
        # Map to HSV
        hue = normalize_value(pressure, 20, 50) * 360  # 0-360
        saturation = normalize_value(flow, 50, 150)  # 0-1
        value = 0.5 + normalize_value(pressure_change, -2, 2) * 0.5  # 0-1
        
        # Fill image with single color
        for i in range(size[1]):
            for j in range(size[0]):
                rgb = hsv_to_rgb(hue, saturation, value)
                img_array[i, j] = rgb
        
        # Add spatial pattern (grid of network nodes)
        grid_size = int(np.ceil(np.sqrt(len(NETWORK_NODES))))
        cell_h = size[1] // grid_size
        cell_w = size[0] // grid_size
        
        for idx, (node_id, (nx, ny)) in enumerate(NETWORK_NODES.items()):
            row = idx // grid_size
            col = idx % grid_size
            
            y = row * cell_h + cell_h // 2
            x = col * cell_w + cell_w // 2
            
            # Draw small marker
            for dy in range(-3, 4):
                for dx in range(-3, 4):
                    if 0 <= y+dy < size[1] and 0 <= x+dx < size[0]:
                        if dx*dx + dy*dy <= 9:
                            img_array[y+dy, x+dx] = [255, 255, 255]
        
        pil_img = Image.fromarray(img_array, mode='RGB')
        return image_to_bytes(pil_img)


# ========================================
# 9. Optical Flow Generator
# ========================================
class OpticalFlowGenerator(BaseGenerator):
    """Generate optical flow-style visualization"""
    
    def __init__(self):
        super().__init__('optical_flow')
    
    def generate(self, state, history, prev_state, size=(256, 256)):
        fig, ax = self.create_figure(size)
        
        pressure = self.get_safe_value(state, 'pressure', 30.0)
        prev_pressure = self.get_safe_value(prev_state, 'pressure', 30.0) if prev_state else pressure
        
        pressure_change = pressure - prev_pressure
        
        # Draw nodes with motion vectors
        for node_id, (x, y) in NETWORK_NODES.items():
            # Vector shows pressure change
            dy = pressure_change * 0.5  # Scale for visibility
            
            # Color based on direction
            if dy > 0:
                color = 'green'
            elif dy < 0:
                color = 'red'
            else:
                color = 'gray'
            
            ax.arrow(x, y, 0, dy, color=color, width=0.05, head_width=0.2)
            ax.scatter([x], [y], s=50, c=color, alpha=0.5)
        
        ax.set_xlim(-2, 2)
        ax.set_ylim(-2, 7)
        ax.set_aspect('equal')
        ax.axis('off')
        
        img_bytes = fig_to_bytes(fig)
        self.close_figure(fig)
        return img_bytes


# ========================================
# 10. Attention Map Generator
# ========================================
class AttentionMapGenerator(BaseGenerator):
    """Generate attention-friendly map (saliency-based)"""
    
    def __init__(self):
        super().__init__('attention_map')
    
    def generate(self, state, history, prev_state, size=(256, 256)):
        fig, ax = self.create_figure(size)
        
        pressure = self.get_safe_value(state, 'pressure', 30.0)
        target = self.get_safe_value(state, 'target_pressure', 120.0)
        
        error = abs(target - pressure)
        
        # Create attention map
        # High error = high attention (bright/saturated)
        x_range = np.linspace(-2, 2, 100)
        y_range = np.linspace(-2, 7, 100)
        X, Y = np.meshgrid(x_range, y_range)
        
        # Attention centered on control node
        cx, cy = NETWORK_NODES['2']
        dist = np.sqrt((X - cx)**2 + (Y - cy)**2)
        
        # Gaussian attention with error-based intensity
        attention = np.exp(-dist**2 / 2) * normalize_value(error, 0, 20)
        
        ax.imshow(attention, extent=[-2, 2, -2, 7], cmap='hot', 
                 origin='lower', alpha=0.8)
        
        ax.set_xlim(-2, 2)
        ax.set_ylim(-2, 7)
        ax.set_aspect('equal')
        ax.axis('off')
        
        img_bytes = fig_to_bytes(fig)
        self.close_figure(fig)
        return img_bytes