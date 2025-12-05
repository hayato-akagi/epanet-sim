"""
Image Generator Registry

All generators are registered here and can be enabled/disabled via config
"""
from generators.network_state_map import NetworkStateMapGenerator
from generators.temporal_slice import TemporalSliceGenerator
from generators.phase_space import PhaseSpaceGenerator
from generators.multiscale_change import MultiscaleChangeGenerator
from generators.flow_vector_field import FlowVectorFieldGenerator
from generators.advanced_generators import (
    EnergyLandscapeGenerator,
    PressureGradientGenerator,
    HSVEncodingGenerator,
    OpticalFlowGenerator,
    AttentionMapGenerator
)
from generators.legacy import (
    SystemUIGenerator,
    ValveDetailGenerator,
    FlowDashboardGenerator,
    ComparisonGenerator
)


# All available generators
ALL_GENERATORS = {
    # New visual-first generators
    'network_state_map': NetworkStateMapGenerator(),
    'temporal_slice': TemporalSliceGenerator(),
    'phase_space': PhaseSpaceGenerator(),
    'multiscale_change': MultiscaleChangeGenerator(),
    'flow_vector_field': FlowVectorFieldGenerator(),
    'energy_landscape': EnergyLandscapeGenerator(),
    'pressure_gradient': PressureGradientGenerator(),
    'hsv_encoding': HSVEncodingGenerator(),
    'optical_flow': OpticalFlowGenerator(),
    'attention_map': AttentionMapGenerator(),
    
    # Legacy generators (for backward compatibility)
    'system_ui': SystemUIGenerator(),
    'valve_detail': ValveDetailGenerator(),
    'flow_dashboard': FlowDashboardGenerator(),
    'comparison': ComparisonGenerator()
}


def get_enabled_generators(enabled_list):
    """
    Get enabled generators based on config
    
    Args:
        enabled_list: List of enabled generator names
    
    Returns:
        dict: {name: generator_instance}
    """
    enabled_generators = {}
    
    for name in enabled_list:
        if name in ALL_GENERATORS:
            enabled_generators[name] = ALL_GENERATORS[name]
        else:
            print(f"Warning: Generator '{name}' not found")
    
    return enabled_generators


def list_all_generators():
    """
    List all available generators
    
    Returns:
        list: List of generator names
    """
    return list(ALL_GENERATORS.keys())


def get_generator_info():
    """
    Get information about all generators
    
    Returns:
        dict: {name: description}
    """
    info = {}
    
    # Group by category
    visual_first = [
        'network_state_map',
        'temporal_slice',
        'phase_space',
        'multiscale_change'
    ]
    
    advanced = [
        'flow_vector_field',
        'energy_landscape',
        'pressure_gradient',
        'hsv_encoding',
        'optical_flow',
        'attention_map'
    ]
    
    legacy = [
        'system_ui',
        'valve_detail',
        'flow_dashboard',
        'comparison'
    ]
    
    info['visual_first'] = {
        'description': 'Recommended for VLA training (minimal text, pure visual)',
        'generators': visual_first
    }
    
    info['advanced'] = {
        'description': 'Advanced visualizations (experimental)',
        'generators': advanced
    }
    
    info['legacy'] = {
        'description': 'Original generators (with text labels)',
        'generators': legacy
    }
    
    return info