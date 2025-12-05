"""
OpenVLA - Vision Transformer based VLA
- Vision Transformer for image encoding
- Cross-attention between images and prompt
- Closer to real OpenVLA architecture
- SimpleDNNVLA interface compatible

Dependencies (optional, will fallback if not available):
    pip install timm  # For Vision Transformer
"""

import torch
import torch.nn as nn
import torchvision.transforms as transforms
from PIL import Image
import re

try:
    import timm
    TIMM_AVAILABLE = True
except ImportError:
    TIMM_AVAILABLE = False
    print("[OpenVLA] Warning: timm not available, using CNN fallback")


class ViTImageEncoder(nn.Module):
    """Vision Transformer for image encoding"""
    
    def __init__(self):
        super().__init__()
        
        if TIMM_AVAILABLE:
            # Use Vision Transformer (ViT-Tiny)
            self.vit = timm.create_model('vit_tiny_patch16_224', pretrained=False, num_classes=0)
            self.output_dim = 192  # ViT-Tiny embedding dim
        else:
            # Fallback to CNN
            self.vit = nn.Sequential(
                nn.Conv2d(3, 64, kernel_size=7, stride=2, padding=3),
                nn.BatchNorm2d(64),
                nn.ReLU(),
                nn.MaxPool2d(3, 2, 1),
                
                nn.Conv2d(64, 128, 3, 2, 1),
                nn.BatchNorm2d(128),
                nn.ReLU(),
                
                nn.Conv2d(128, 192, 3, 2, 1),
                nn.BatchNorm2d(192),
                nn.ReLU(),
                
                nn.AdaptiveAvgPool2d(1),
                nn.Flatten()
            )
            self.output_dim = 192
    
    def forward(self, x):
        return self.vit(x)


class CrossAttentionBlock(nn.Module):
    """画像とプロンプト間のCross-Attention"""
    
    def __init__(self, dim, num_heads=4):
        super().__init__()
        self.attention = nn.MultiheadAttention(dim, num_heads, batch_first=True)
        self.norm1 = nn.LayerNorm(dim)
        self.norm2 = nn.LayerNorm(dim)
        self.ffn = nn.Sequential(
            nn.Linear(dim, dim * 4),
            nn.GELU(),
            nn.Linear(dim * 4, dim)
        )
    
    def forward(self, query, key_value):
        """
        Args:
            query: [B, N_query, dim] (prompt features)
            key_value: [B, N_kv, dim] (image features)
        """
        # Cross-attention
        attended, _ = self.attention(query, key_value, key_value)
        query = self.norm1(query + attended)
        
        # FFN
        ffn_out = self.ffn(query)
        query = self.norm2(query + ffn_out)
        
        return query


class OpenVLA(nn.Module):
    """
    OpenVLA - Vision Transformer based VLA
    
    Architecture:
    1. Vision Encoder (ViT) - 画像を埋め込みベクトルに
    2. Prompt Encoder (MLP) - プロンプトを埋め込みベクトルに
    3. Cross-Attention - 画像とプロンプトを統合
    4. Action Head (MLP) - アクションを出力
    """
    
    def __init__(self):
        super().__init__()
class TinyVLA(nn.Module):
    """
    TinyVLA - SimpleDNNVLAの改良版
    
    Improvements:
    - ResNet-style blocks (残差接続)
    - Attention mechanism (画像間の関係性を学習)
    - Better normalization (BatchNorm)
    - Deeper network (より表現力が高い)
    """
    
    def __init__(self):
        super().__init__()
        self.device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')

class TinyVLA(nn.Module):
    """
    TinyVLA - SimpleDNNVLAの改良版
    
    Improvements:
    - ResNet-style blocks (残差接続)
    - Attention mechanism (画像間の関係性を学習)
    - Better normalization (BatchNorm)
    - Deeper network (より表現力が高い)
    """
    
    def __init__(self):
        super().__init__()
        self.device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
        
        # Vision encoder
        self.vision_encoder = ViTImageEncoder()
        vision_dim = self.vision_encoder.output_dim  # 192
        
        # Prompt encoder
        self.prompt_dim = 5  # [current, target, valve, upstream, downstream]
        self.prompt_encoder = nn.Sequential(
            nn.Linear(self.prompt_dim, 64),
            nn.ReLU(),
            nn.Linear(64, 128),
            nn.ReLU(),
            nn.Linear(128, vision_dim),  # Match vision dim
            nn.ReLU()
        )
        
        # Cross-attention blocks
        self.cross_attention1 = CrossAttentionBlock(vision_dim, num_heads=4)
        self.cross_attention2 = CrossAttentionBlock(vision_dim, num_heads=4)
        
        # Action head
        self.action_head = nn.Sequential(
            nn.Linear(vision_dim, 256),
            nn.GELU(),
            nn.Dropout(0.1),
            nn.Linear(256, 128),
            nn.GELU(),
            nn.Dropout(0.1),
            nn.Linear(128, 1),
            nn.Tanh()
        )
        
        # Transform
        self.transform = transforms.Compose([
            transforms.Resize((224, 224)),  # ViT standard size
            transforms.ToTensor(),
            transforms.Normalize(mean=[0.485, 0.456, 0.406], 
                               std=[0.229, 0.224, 0.225])
        ])
    
    def encode_prompt(self, prompt):
        """プロンプトから数値を抽出（SimpleDNNVLAと同じ）"""
        current_match = re.search(r'Current \w+: ([\d.]+)', prompt)
        target_match = re.search(r'target[:\s]+([\d.]+)', prompt)
        valve_match = re.search(r'Valve opening: ([\d.]+)%', prompt)
        upstream_match = re.search(r'Upstream pressure: ([\d.]+)', prompt)
        downstream_match = re.search(r'Downstream pressure: ([\d.]+)', prompt)
        
        current = float(current_match.group(1)) if current_match else 30.0
        target = float(target_match.group(1)) if target_match else 30.0
        valve = float(valve_match.group(1)) / 100 if valve_match else 0.5
        upstream = float(upstream_match.group(1)) if upstream_match else 50.0
        downstream = float(downstream_match.group(1)) if downstream_match else 30.0
        
        features = torch.tensor([
            (current - 30.0) / 10.0,
            (target - 30.0) / 10.0,
            valve,
            (upstream - 40.0) / 10.0,
            (downstream - 30.0) / 10.0
        ], dtype=torch.float32)
        
        return features
    
    def forward(self, images_dict, prompt):
        """
        推論
        
        Args:
            images_dict: Dict[str, PIL.Image]
            prompt: str
        
        Returns:
            float: Δvalve_opening
        """
        # 画像タイプの優先順位
        image_types = [
            'network_state_map', 'temporal_slice', 'phase_space', 'multiscale_change'
        ]
        
        # フォールバック
        if not any(img_type in images_dict for img_type in image_types):
            image_types = ['system_ui', 'valve_detail', 'flow_dashboard', 'comparison']
        
        # 画像エンコーディング
        image_features_list = []
        for img_type in image_types:
            img = images_dict.get(img_type)
            if img is None:
                img = Image.new('RGB', (256, 256), color=(128, 128, 128))
            
            img_tensor = self.transform(img).unsqueeze(0)  # [1, 3, 224, 224]
            features = self.vision_encoder(img_tensor)  # [1, 192]
            image_features_list.append(features)
        
        # Stack: [1, 4, 192]
        image_features = torch.stack(image_features_list, dim=1)
        
        # プロンプトエンコーディング
        prompt_raw = self.encode_prompt(prompt).unsqueeze(0)  # [1, 5]
        prompt_features = self.prompt_encoder(prompt_raw).unsqueeze(1)  # [1, 1, 192]
        
        # Cross-attention: prompt attends to images
        attended_features = self.cross_attention1(prompt_features, image_features)  # [1, 1, 192]
        attended_features = self.cross_attention2(attended_features, image_features)  # [1, 1, 192]
        
        # Pool
        final_features = attended_features.squeeze(1)  # [1, 192]
        
        # Action prediction
        delta_valve = self.action_head(final_features) * 0.05  # [-0.05, 0.05]
        
        return delta_valve.item()


class OpenVLAWrapper:
    """OpenVLAのラッパー（SimpleDNNVLAと同じインターフェース）"""
    
    def __init__(self, checkpoint_path=None):
        self.model = OpenVLA()
        
        if checkpoint_path:
            try:
                self.model.load_state_dict(torch.load(checkpoint_path, map_location='cpu'))
                print(f"[OpenVLA] Loaded checkpoint from {checkpoint_path}")
            except Exception as e:
                print(f"[OpenVLA] Warning: Could not load checkpoint: {e}")
                print("[OpenVLA] Using random initialization")
        
        self.model.eval()
        print("[OpenVLA] Initialized OpenVLA Model")
        if TIMM_AVAILABLE:
            print("[OpenVLA] Architecture: Vision Transformer + Cross-Attention")
        else:
            print("[OpenVLA] Architecture: CNN + Cross-Attention (timm not available)")
        print("[OpenVLA] Parameters: ~5M")
    
    def predict(self, images, prompt):
        """
        推論
        
        Args:
            images: Dict[str, PIL.Image]
            prompt: str
        
        Returns:
            float: Δvalve_opening
        """
        with torch.no_grad():
            action = self.model(images, prompt)
        
        return float(action)


if __name__ == "__main__":
    # Test
    print("Testing OpenVLA...")
    
    images = {
        'network_state_map': Image.new('RGB', (256, 256), color=(100, 150, 200)),
        'temporal_slice': Image.new('RGB', (256, 256), color=(150, 100, 200)),
        'phase_space': Image.new('RGB', (256, 256), color=(200, 150, 100)),
        'multiscale_change': Image.new('RGB', (256, 256), color=(150, 200, 100))
    }
    
    prompt = "Current pressure: 35.5m, target: 30.0m, Valve opening: 75.0%"
    
    model = OpenVLAWrapper()
    action = model.predict(images, prompt)
    
    print(f"Result: delta_valve = {action:.4f}")