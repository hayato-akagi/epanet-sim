"""
Base class for all image generators
"""
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from abc import ABC, abstractmethod
from utils import fig_to_bytes


class BaseGenerator(ABC):
    """
    Base class for all image generators
    
    All generators must implement the generate() method
    """
    
    def __init__(self, name):
        """
        Initialize generator
        
        Args:
            name: Generator name (used as key)
        """
        self.name = name
    
    @abstractmethod
    def generate(self, state, history, prev_state, size=(256, 256)):
        """
        Generate image
        
        Args:
            state: Current state dict
                - pressure: Current pressure (m)
                - target_pressure: Target pressure (m)
                - valve_setting: Current valve setting (0-1)
                - flow: Current flow (L/s)
                - target_flow: Target flow (L/s)
                - upstream_pressure: Upstream pressure (m)
                - downstream_pressure: Downstream pressure (m)
                - timestamp: Current timestamp
            
            history: History dict
                - pressure: List of pressure values
                - valve_setting: List of valve settings
                - flow: List of flow values
                - error: List of error values
            
            prev_state: Previous state dict (may be None)
            
            size: Image size (width, height)
        
        Returns:
            bytes: PNG image data
        """
        pass
    
    def create_figure(self, size=(256, 256), dpi=100):
        """
        Create matplotlib figure with standard settings
        
        Args:
            size: Image size (width, height)
            dpi: DPI
        
        Returns:
            tuple: (fig, ax)
        """
        width_inch = size[0] / dpi
        height_inch = size[1] / dpi
        
        fig, ax = plt.subplots(figsize=(width_inch, height_inch), dpi=dpi)
        
        return fig, ax
    
    def close_figure(self, fig):
        """
        Close matplotlib figure to free memory
        
        Args:
            fig: Matplotlib figure
        """
        plt.close(fig)
    
    def get_safe_value(self, state, key, default=0.0):
        """
        Safely get value from state dict
        
        Args:
            state: State dict
            key: Key to retrieve
            default: Default value if key not found
        
        Returns:
            Value or default
        """
        return state.get(key, default) if state else default