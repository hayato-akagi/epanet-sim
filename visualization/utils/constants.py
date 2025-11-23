import os

# 定数・パス設定
RESULTS_DIR = os.environ.get('RESULTS_DIR', '/shared/results')
NETWORKS_DIR = os.environ.get('NETWORKS_DIR', '/shared/networks')

# 色設定
COLOR_MAP = {
    'Pressure Sensor': 'red',
    'Flow Sensor': 'purple',
    'Reservoir': 'blue',
    'Tank': 'cyan',
    'Junction': 'lightgray'
}

SYMBOL_MAP = {
    'Pressure Sensor': 'diamond',
    'Flow Sensor': 'diamond',
    'Reservoir': 'square',
    'Tank': 'square',
    'Junction': 'circle'
}