"""
SmoLVLA - Smaller OpenVLA
- EfficientNet for vision (lighter than ViT)
- Lightweight attention
- Good balance of performance and speed
- SimpleDNNVLA interface compatible

Dependencies (optional):
    pip install efficientnet_pytorch
"""

import torch
import torch.nn as nn
import torchvision.transforms as transforms
from PIL import Image
import re

try:
    from efficientnet_pytorch import EfficientNet
    EFFICIENTNET_AVAILABLE = True
except ImportError:
    EFFICIENTNET_AVAILABLE = False
    print("[SmoLVLA] Warning: efficientnet_pytorch not available, using CNN fallback")


class EfficientImageEncoder(nn.Module):
    """EfficientNet-based image encoder"""
    
    def __init__(self):
        super().__init__()
        
        if EFFICIENTNET_AVAILABLE:
            # Use EfficientNet-B0 (lightweight)
            self.encoder = EfficientNet.from_name('efficientnet-b0', include_top=False)
            self.output_dim = 1280  # EfficientNet-B0 output
            self.pool = nn.AdaptiveAvgPool2d(1)
        else:
            # Fallback: MobileNet-style CNN
            self.encoder = nn.Sequential(
                # Depthwise separable convolutions
                nn.Conv2d(3, 32, 3, 2, 1),
                nn.BatchNorm2d(32),
                nn.ReLU6(),
                
                self._depthwise_separable(32, 64, 1),
                self._depthwise_separable(64, 128, 2),
                self._depthwise_separable(128, 128, 1),
                self._depthwise_separable(128, 256, 2),
                self._depthwise_separable(256, 256, 1),
                self._depthwise_separable(256, 512, 2),
                
                nn.AdaptiveAvgPool2d(1),
            )
            self.output_dim = 512
            self.pool = None
    
    def _depthwise_separable(self, in_channels, out_channels, stride):
        """Depthwise separable convolution"""
        return nn.Sequential(
            # Depthwise
            nn.Conv2d(in_channels, in_channels, 3, stride, 1, groups=in_channels),
            nn.BatchNorm2d(in_channels),
            nn.ReLU6(),
            # Pointwise
            nn.Conv2d(in_channels, out_channels, 1, 1, 0),
            nn.BatchNorm2d(out_channels),
            nn.ReLU6()
        )
    
    def forward(self, x):
        features = self.encoder(x)
        if self.pool is not None:
            features = self.pool(features)
        return features.flatten(1)


class LightweightAttention(nn.Module):
    """軽量なアテンション機構"""
    
    def __init__(self, dim):
        super().__init__()
        self.query = nn.Linear(dim, dim // 4)
        self.key = nn.Linear(dim, dim // 4)
        self.value = nn.Linear(dim, dim)
        self.out = nn.Linear(dim, dim)
        
    def forward(self, x):
        """
        Args:
            x: [B, N, dim]
        Returns:
            [B, N, dim]
        """
        B, N, dim = x.shape
        
        q = self.query(x)  # [B, N, dim//4]
        k = self.key(x)    # [B, N, dim//4]
        v = self.value(x)  # [B, N, dim]
        
        # Attention scores
        scores = torch.matmul(q, k.transpose(-2, -1)) / (dim // 4) ** 0.5  # [B, N, N]
        attn = torch.softmax(scores, dim=-1)
        
        # Apply attention
        out = torch.matmul(attn, v)  # [B, N, dim]
        out = self.out(out)
        
        return out + x  # Residual


class SmoLVLA(nn.Module):
    """
    SmoLVLA - Smaller OpenVLA
    
    Architecture:
    1. EfficientNet/MobileNet for vision
    2. Lightweight attention
    3. Action head
    
    Good balance between SimpleDNN and OpenVLA
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
        
        # Vision encoder
        self.vision_encoder = EfficientImageEncoder()
        vision_dim = self.vision_encoder.output_dim
        
        # Project to common dimension
        self.vision_proj = nn.Linear(vision_dim, 256)
        
        # Prompt encoder
        self.prompt_dim = 5
        self.prompt_encoder = nn.Sequential(
            nn.Linear(self.prompt_dim, 64),
            nn.ReLU(),
            nn.Linear(64, 128),
            nn.ReLU(),
            nn.Linear(128, 256),
            nn.ReLU()
        )
        
        # Attention over images + prompt
        self.attention = LightweightAttention(256)
        
        # Action head
        self.action_head = nn.Sequential(
            nn.Linear(256, 256),
            nn.ReLU(),
            nn.Dropout(0.1),
            nn.Linear(256, 128),
            nn.ReLU(),
            nn.Dropout(0.1),
            nn.Linear(128, 1),
            nn.Tanh()
        )
        
        self.transform = transforms.Compose([
            transforms.Resize((224, 224)),
            transforms.ToTensor(),
            transforms.Normalize(mean=[0.485, 0.456, 0.406], 
                               std=[0.229, 0.224, 0.225])
        ])
    
    def encode_prompt(self, prompt):
        """プロンプトから数値を抽出"""
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
        # 画像タイプ
        image_types = [
            'network_state_map', 'temporal_slice', 'phase_space', 'multiscale_change'
        ]
        
        if not any(img_type in images_dict for img_type in image_types):
            image_types = ['system_ui', 'valve_detail', 'flow_dashboard', 'comparison']
        
        # 画像エンコーディング
        image_features_list = []
        for img_type in image_types:
            img = images_dict.get(img_type)
            if img is None:
                img = Image.new('RGB', (256, 256), color=(128, 128, 128))
            
            img_tensor = self.transform(img).unsqueeze(0)
            features = self.vision_encoder(img_tensor)  # [1, vision_dim]
            features = self.vision_proj(features)  # [1, 256]
            image_features_list.append(features)
        
        # プロンプトエンコーディング
        prompt_raw = self.encode_prompt(prompt).unsqueeze(0)
        prompt_features = self.prompt_encoder(prompt_raw)  # [1, 256]
        
        # Combine: [1, 5, 256] (4 images + 1 prompt)
        all_features = torch.stack(image_features_list + [prompt_features], dim=1)
        
        # Attention
        attended = self.attention(all_features)  # [1, 5, 256]
        
        # Pool (focus on prompt token)
        final_features = attended[:, -1, :]  # [1, 256] (last token = prompt)
        
        # Action prediction
        delta_valve = self.action_head(final_features) * 0.05
        
        return delta_valve.item()


class SmoLVLAWrapper:
    """SmoLVLAのラッパー（SimpleDNNVLAと同じインターフェース）"""
    
    def __init__(self, checkpoint_path=None):
        self.model = SmoLVLA()
        
        if checkpoint_path:
            try:
                self.model.load_state_dict(torch.load(checkpoint_path, map_location='cpu'))
                print(f"[SmoLVLA] Loaded checkpoint from {checkpoint_path}")
            except Exception as e:
                print(f"[SmoLVLA] Warning: Could not load checkpoint: {e}")
                print("[SmoLVLA] Using random initialization")
        
        self.model.eval()
        print("[SmoLVLA] Initialized SmoLVLA Model")
        if EFFICIENTNET_AVAILABLE:
            print("[SmoLVLA] Architecture: EfficientNet + Lightweight Attention")
        else:
            print("[SmoLVLA] Architecture: MobileNet + Lightweight Attention")
        print("[SmoLVLA] Parameters: ~3-4M")
    
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
    print("Testing SmoLVLA...")
    
    images = {
        'network_state_map': Image.new('RGB', (256, 256), color=(100, 150, 200)),
        'temporal_slice': Image.new('RGB', (256, 256), color=(150, 100, 200)),
        'phase_space': Image.new('RGB', (256, 256), color=(200, 150, 100)),
        'multiscale_change': Image.new('RGB', (256, 256), color=(150, 200, 100))
    }
    
    prompt = "Current pressure: 35.5m, target: 30.0m, Valve opening: 75.0%"
    
    model = SmoLVLAWrapper()
    action = model.predict(images, prompt)
    
    print(f"Result: delta_valve = {action:.4f}")