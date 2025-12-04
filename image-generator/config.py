"""
Configuration management for image-generator service
"""
import os

# Redis configuration
REDIS_URL = os.environ.get('REDIS_URL', 'redis://redis:6379')

# Image generation configuration
ENABLED_GENERATORS = os.environ.get(
    'ENABLED_GENERATORS',
    'network_state_map,temporal_slice,phase_space,multiscale_change'
).split(',')

# Remove whitespace
ENABLED_GENERATORS = [g.strip() for g in ENABLED_GENERATORS if g.strip()]

# Image size configuration
IMAGE_WIDTH = int(os.environ.get('IMAGE_WIDTH', '256'))
IMAGE_HEIGHT = int(os.environ.get('IMAGE_HEIGHT', '256'))
IMAGE_DPI = int(os.environ.get('IMAGE_DPI', '100'))

# Redis TTL (seconds)
REDIS_TTL = int(os.environ.get('REDIS_TTL', '300'))

# Network topology (for Net1.inp)
NETWORK_NODES = {
    '2': (0, 0),
    '10': (-1, 1),
    '11': (1, 1),
    '12': (0, 2),
    '13': (-1, 3),
    '21': (1, 3),
    '22': (0, 4),
    '23': (-1, 5),
    '31': (1, 5),
    '32': (0, 6),
    '9': (0, -1)
}

NETWORK_LINKS = [
    ('9', '2'), ('2', '12'), ('12', '22'), ('22', '32'),
    ('2', '10'), ('10', '13'), ('13', '23'),
    ('2', '11'), ('11', '21'), ('21', '31')
]

# Control node (the one being controlled)
CONTROL_NODE = '2'

# Logging
DEBUG_MODE = os.environ.get('DEBUG_MODE', 'false').lower() == 'true'


def print_config():
    """Print current configuration"""
    print("=" * 60)
    print("Image Generator Configuration")
    print("=" * 60)
    print(f"Redis URL: {REDIS_URL}")
    print(f"Enabled Generators: {ENABLED_GENERATORS}")
    print(f"Image Size: {IMAGE_WIDTH}x{IMAGE_HEIGHT} @ {IMAGE_DPI}dpi")
    print(f"Redis TTL: {REDIS_TTL}s")
    print(f"Debug Mode: {DEBUG_MODE}")
    print("=" * 60)