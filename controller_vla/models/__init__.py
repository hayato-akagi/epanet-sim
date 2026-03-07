"""
VLA Models Package
==================

Available models:
- simple_dnn: SimpleDNNVLA (baseline, ~1M params)
- tiny_vla: TinyVLA (recommended, ~2M params)
- smolvla: SmolVLA (medium, ~3-4M params)
- openvla: OpenVLA (large, ~5M params)
- dummy: DummyVLA (for testing)

Usage:
    from models import get_vla_model
    
    model = get_vla_model('tiny_vla')
    action = model.predict(images, prompt)
"""

import os


def get_vla_model(model_name='tiny_vla', checkpoint_path=None):
    """
    VLAモデルをロード
    
    Args:
        model_name: モデル名
            - 'simple_dnn': SimpleDNNVLA (baseline, ~1M params)
            - 'tiny_vla': TinyVLA (recommended, ~2M params)
            - 'smolvla': SmolVLA (medium, ~3-4M params)
            - 'openvla': OpenVLA (large, ~5M params)
            - 'dummy': DummyVLA (testing)
        checkpoint_path: チェックポイントのパス（オプション）
    
    Returns:
        VLAモデルのインスタンス
    """
    model_name = model_name.lower()
    
    print(f"[get_vla_model] Loading model: {model_name}")
    
    if model_name == 'simple_dnn' or model_name == 'simplednn':
        from .simple_dnn_vla import SimpleDNNVLAWrapper
        return SimpleDNNVLAWrapper(checkpoint_path)
    
    elif model_name == 'tiny_vla' or model_name == 'tinyvla':
        try:
            from .tiny_vla import TinyVLAWrapper
            return TinyVLAWrapper(checkpoint_path)
        except Exception as e:
            print(f"[get_vla_model] Error loading TinyVLA: {e}")
            print("[get_vla_model] Falling back to SimpleDNN")
            from .simple_dnn_vla import SimpleDNNVLAWrapper
            return SimpleDNNVLAWrapper(checkpoint_path)
    
    elif model_name == 'smolvla':
        try:
            from .smolvla import SmolVLAWrapper
            return SmolVLAWrapper(checkpoint_path)
        except Exception as e:
            print(f"[get_vla_model] Error loading SmolVLA: {e}")
            print("[get_vla_model] Falling back to TinyVLA")
            try:
                from .tiny_vla import TinyVLAWrapper
                return TinyVLAWrapper(checkpoint_path)
            except:
                print("[get_vla_model] Falling back to SimpleDNN")
                from .simple_dnn_vla import SimpleDNNVLAWrapper
                return SimpleDNNVLAWrapper(checkpoint_path)
    
    elif model_name == 'openvla':
        try:
            from .openvla import OpenVLAWrapper
            return OpenVLAWrapper(checkpoint_path)
        except Exception as e:
            print(f"[get_vla_model] Error loading OpenVLA: {e}")
            print("[get_vla_model] Falling back to SmolVLA")
            try:
                from .smolvla import SmolVLAWrapper
                return SmolVLAWrapper(checkpoint_path)
            except:
                try:
                    from .tiny_vla import TinyVLAWrapper
                    return TinyVLAWrapper(checkpoint_path)
                except:
                    print("[get_vla_model] Falling back to SimpleDNN")
                    from .simple_dnn_vla import SimpleDNNVLAWrapper
                    return SimpleDNNVLAWrapper(checkpoint_path)
    
    # elif model_name == 'dummy':
    #     from .dummy_vla import DummyVLA
    #     return DummyVLA()
    
    else:
        print(f"[get_vla_model] Unknown model: {model_name}")
        print("[get_vla_model] Available models: simple_dnn, tiny_vla, smolvla, openvla, dummy")
        print("[get_vla_model] Using TinyVLA as default")
        from .tiny_vla import TinyVLAWrapper
        return TinyVLAWrapper(checkpoint_path)


# Exports
from .simple_dnn_vla import SimpleDNNVLA, SimpleDNNVLAWrapper

try:
    from .tiny_vla import TinyVLA, TinyVLAWrapper
except ImportError:
    print("[models] Warning: TinyVLA not available")

try:
    from .smolvla import SmolVLA, SmolVLAWrapper
except ImportError:
    print("[models] Warning: SmolVLA not available")

try:
    from .openvla import OpenVLA, OpenVLAWrapper
except ImportError:
    print("[models] Warning: OpenVLA not available")

# from .dummy_vla import DummyVLA


__all__ = [
    'get_vla_model',
    'SimpleDNNVLA',
    # 'SimpleDNNVLAWrapper',
    'TinyVLA',
    # 'TinyVLAWrapper',
    'SmolVLA',
    # 'SmolVLAWrapper',
    'OpenVLA',
    # 'OpenVLAWrapper',
    # 'DummyVLA',
]