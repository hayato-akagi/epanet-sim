"""
Utility functions for image generation
"""
import numpy as np
import io
from PIL import Image


def normalize_value(value, vmin, vmax):
    """
    Normalize value to [0, 1] range
    
    Args:
        value: Value to normalize
        vmin: Minimum value
        vmax: Maximum value
    
    Returns:
        float: Normalized value (0-1)
    """
    return np.clip((value - vmin) / (vmax - vmin), 0, 1)


def bytes_to_image(img_bytes):
    """
    Convert bytes to PIL Image
    
    Args:
        img_bytes: Image bytes
    
    Returns:
        PIL.Image: Image object
    """
    return Image.open(io.BytesIO(img_bytes))


def image_to_bytes(img, format='PNG'):
    """
    Convert PIL Image to bytes
    
    Args:
        img: PIL Image
        format: Image format (default: PNG)
    
    Returns:
        bytes: Image bytes
    """
    buffer = io.BytesIO()
    img.save(buffer, format=format)
    return buffer.getvalue()


def fig_to_bytes(fig, dpi=100):
    """
    Convert matplotlib figure to bytes
    
    Args:
        fig: Matplotlib figure
        dpi: DPI for output
    
    Returns:
        bytes: PNG image bytes
    """
    buffer = io.BytesIO()
    fig.savefig(buffer, format='png', bbox_inches='tight', dpi=dpi)
    return buffer.getvalue()


def calculate_derivative(history, key, window=3):
    """
    Calculate numerical derivative from history
    
    Args:
        history: History dict
        key: Key to calculate derivative for
        window: Window size for derivative calculation
    
    Returns:
        float: Derivative value
    """
    values = history.get(key, [])
    if len(values) < 2:
        return 0.0
    
    # Use last 'window' values
    recent = values[-window:]
    
    if len(recent) < 2:
        return 0.0
    
    # Simple finite difference
    return (recent[-1] - recent[0]) / len(recent)


def get_multiscale_changes(history, key, scales=[3, 10, 30]):
    """
    Calculate changes at multiple time scales
    
    Args:
        history: History dict
        key: Key to get changes for
        scales: List of time scales (in steps)
    
    Returns:
        list: Changes at each scale
    """
    values = history.get(key, [])
    
    changes = []
    for scale in scales:
        if len(values) < 2:
            changes.append(0.0)
        elif len(values) < scale:
            changes.append(values[-1] - values[0])
        else:
            changes.append(values[-1] - values[-scale])
    
    return changes


def interpolate_color(value, colormap='viridis'):
    """
    Get RGB color from normalized value using matplotlib colormap
    
    Args:
        value: Normalized value (0-1)
        colormap: Matplotlib colormap name
    
    Returns:
        tuple: (r, g, b) in [0, 255]
    """
    import matplotlib.pyplot as plt
    
    cmap = plt.get_cmap(colormap)
    rgba = cmap(np.clip(value, 0, 1))
    
    return tuple(int(c * 255) for c in rgba[:3])


def create_arrow(ax, x, y, dx, dy, color='black', width=0.01, head_width=0.05):
    """
    Create arrow on matplotlib axis
    
    Args:
        ax: Matplotlib axis
        x, y: Arrow start position
        dx, dy: Arrow direction and magnitude
        color: Arrow color
        width: Arrow shaft width
        head_width: Arrow head width
    """
    ax.arrow(x, y, dx, dy, 
             color=color, 
             width=width, 
             head_width=head_width,
             head_length=head_width*1.5,
             length_includes_head=True)


def rgb_to_hsv(r, g, b):
    """
    Convert RGB to HSV
    
    Args:
        r, g, b: RGB values (0-255)
    
    Returns:
        tuple: (h, s, v) where h is in [0, 360], s and v in [0, 1]
    """
    r, g, b = r / 255.0, g / 255.0, b / 255.0
    
    max_val = max(r, g, b)
    min_val = min(r, g, b)
    diff = max_val - min_val
    
    # Hue
    if diff == 0:
        h = 0
    elif max_val == r:
        h = 60 * (((g - b) / diff) % 6)
    elif max_val == g:
        h = 60 * (((b - r) / diff) + 2)
    else:
        h = 60 * (((r - g) / diff) + 4)
    
    # Saturation
    s = 0 if max_val == 0 else diff / max_val
    
    # Value
    v = max_val
    
    return h, s, v


def hsv_to_rgb(h, s, v):
    """
    Convert HSV to RGB
    
    Args:
        h: Hue (0-360)
        s: Saturation (0-1)
        v: Value (0-1)
    
    Returns:
        tuple: (r, g, b) in [0, 255]
    """
    c = v * s
    x = c * (1 - abs((h / 60) % 2 - 1))
    m = v - c
    
    if h < 60:
        r, g, b = c, x, 0
    elif h < 120:
        r, g, b = x, c, 0
    elif h < 180:
        r, g, b = 0, c, x
    elif h < 240:
        r, g, b = 0, x, c
    elif h < 300:
        r, g, b = x, 0, c
    else:
        r, g, b = c, 0, x
    
    return tuple(int((val + m) * 255) for val in (r, g, b))