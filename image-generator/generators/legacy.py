"""
Legacy Generators

Original image generators for backward compatibility
"""
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.patches import Circle
import io
from generators.base import BaseGenerator
from utils import fig_to_bytes
from config import NETWORK_NODES, NETWORK_LINKS


class SystemUIGenerator(BaseGenerator):
    """Legacy system_ui generator"""
    
    def __init__(self):
        super().__init__('system_ui')
    
    def generate(self, state, history, prev_state, size=(256, 256)):
        fig, ax = self.create_figure(size)
        
        pressure = self.get_safe_value(state, 'pressure', 30.0)
        target = self.get_safe_value(state, 'target_pressure', 30.0)
        
        # Plot nodes
        for node_id, (x, y) in NETWORK_NODES.items():
            if node_id == '2':
                color_val = (pressure - 20) / 30
            else:
                color_val = 0.5
            
            color = plt.cm.viridis(np.clip(color_val, 0, 1))
            circle = Circle((x, y), 0.3, color=color, ec='black', linewidth=1.5)
            ax.add_patch(circle)
            
            ax.text(x, y, node_id, ha='center', va='center', 
                   fontsize=6, color='white', weight='bold')
        
        # Highlight control node
        highlight = Circle((0, 0), 0.35, fill=False, ec='red', linewidth=2)
        ax.add_patch(highlight)
        
        # Draw links
        for start, end in NETWORK_LINKS:
            x_start, y_start = NETWORK_NODES[start]
            x_end, y_end = NETWORK_NODES[end]
            ax.plot([x_start, x_end], [y_start, y_end], 'k-', linewidth=1, alpha=0.5)
        
        ax.set_xlim(-2, 2)
        ax.set_ylim(-2, 7)
        ax.set_aspect('equal')
        ax.axis('off')
        ax.set_title(f'Network - P={pressure:.1f}m (Target={target:.1f}m)', fontsize=8)
        
        img_bytes = fig_to_bytes(fig)
        self.close_figure(fig)
        return img_bytes


class ValveDetailGenerator(BaseGenerator):
    """Legacy valve_detail generator"""
    
    def __init__(self):
        super().__init__('valve_detail')
    
    def generate(self, state, history, prev_state, size=(256, 256)):
        fig, ax = self.create_figure(size)
        
        valve = self.get_safe_value(state, 'valve_setting', 0.5) * 100
        upstream_p = self.get_safe_value(state, 'upstream_pressure', 50.0)
        downstream_p = self.get_safe_value(state, 'downstream_pressure', 30.0)
        delta_p = upstream_p - downstream_p
        
        # Gauge chart
        theta = np.linspace(0, np.pi, 100)
        ax.fill_between(theta, 0, 1, color='lightgray', alpha=0.3)
        
        # Current value
        valve_theta = np.pi * (1 - valve / 100)
        ax.plot([np.pi/2, np.pi/2 + 0.8*np.cos(valve_theta)], 
               [0, 0.8*np.sin(valve_theta)], 'r-', linewidth=4)
        
        # Ticks
        for v in [0, 25, 50, 75, 100]:
            t = np.pi * (1 - v / 100)
            ax.plot([np.pi/2 + 0.9*np.cos(t), np.pi/2 + 1.0*np.cos(t)], 
                   [0.9*np.sin(t), 1.0*np.sin(t)], 'k-', linewidth=1)
            ax.text(np.pi/2 + 1.1*np.cos(t), 1.1*np.sin(t), f'{v}%', 
                   ha='center', va='center', fontsize=8)
        
        # Text
        ax.text(np.pi/2, -0.3, f'{valve:.1f}%', ha='center', va='top', 
               fontsize=24, weight='bold')
        ax.text(np.pi/2, -0.5, f'ΔP = {delta_p:.1f}m', ha='center', va='top', 
               fontsize=12)
        
        ax.set_xlim(0, np.pi)
        ax.set_ylim(-0.6, 1.2)
        ax.set_aspect('equal')
        ax.axis('off')
        ax.set_title('Valve Opening', fontsize=10, weight='bold')
        
        img_bytes = fig_to_bytes(fig)
        self.close_figure(fig)
        return img_bytes


class FlowDashboardGenerator(BaseGenerator):
    """Legacy flow_dashboard generator"""
    
    def __init__(self):
        super().__init__('flow_dashboard')
    
    def generate(self, state, history, prev_state, size=(256, 256)):
        fig, ax = self.create_figure(size)
        
        flow_history = history.get('flow', [])
        if not flow_history:
            flow_history = [self.get_safe_value(state, 'flow', 95.0)]
        
        steps = list(range(len(flow_history)))
        target_flow = self.get_safe_value(state, 'target_flow', 100.0)
        
        ax.plot(steps, flow_history, 'r-', linewidth=2, label='Actual Flow')
        ax.axhline(target_flow, color='g', linestyle='--', linewidth=1.5, label='Target')
        ax.fill_between(steps, target_flow * 0.95, target_flow * 1.05, 
                       color='gray', alpha=0.2, label='±5% Range')
        
        ax.set_xlabel('Step', fontsize=8)
        ax.set_ylabel('Flow (L/s)', fontsize=8)
        ax.set_title('Flow History', fontsize=10, weight='bold')
        ax.legend(fontsize=6, loc='upper right')
        ax.grid(True, alpha=0.3)
        ax.tick_params(labelsize=7)
        
        img_bytes = fig_to_bytes(fig)
        self.close_figure(fig)
        return img_bytes


class ComparisonGenerator(BaseGenerator):
    """Legacy comparison generator"""
    
    def __init__(self):
        super().__init__('comparison')
    
    def generate(self, state, history, prev_state, size=(256, 256)):
        fig, axes = plt.subplots(1, 2, figsize=(5.12, 2.56), dpi=100)
        
        pressure = self.get_safe_value(state, 'pressure', 30.0)
        prev_pressure = self.get_safe_value(prev_state, 'pressure', 29.5) if prev_state else pressure
        
        valve = self.get_safe_value(state, 'valve_setting', 0.5) * 100
        prev_valve = self.get_safe_value(prev_state, 'valve_setting', 0.48) * 100 if prev_state else valve
        
        # Previous
        axes[0].text(0.5, 0.7, 'Previous', ha='center', va='center', 
                    fontsize=12, weight='bold', transform=axes[0].transAxes)
        axes[0].text(0.5, 0.5, f'P: {prev_pressure:.1f}m', ha='center', va='center', 
                    fontsize=10, transform=axes[0].transAxes)
        axes[0].text(0.5, 0.3, f'V: {prev_valve:.1f}%', ha='center', va='center', 
                    fontsize=10, transform=axes[0].transAxes)
        axes[0].axis('off')
        
        # Current
        axes[1].text(0.5, 0.7, 'Current', ha='center', va='center', 
                    fontsize=12, weight='bold', transform=axes[1].transAxes)
        axes[1].text(0.5, 0.5, f'P: {pressure:.1f}m', ha='center', va='center', 
                    fontsize=10, transform=axes[1].transAxes)
        axes[1].text(0.5, 0.3, f'V: {valve:.1f}%', ha='center', va='center', 
                    fontsize=10, transform=axes[1].transAxes)
        axes[1].axis('off')
        
        # Changes
        fig.text(0.5, 0.1, f'ΔP: {pressure - prev_pressure:+.2f}m, ΔV: {valve - prev_valve:+.1f}%', 
                ha='center', fontsize=10, weight='bold')
        
        buffer = io.BytesIO()
        plt.savefig(buffer, format='png', bbox_inches='tight', dpi=50)
        plt.close(fig)
        
        return buffer.getvalue()