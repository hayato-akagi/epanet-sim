"""
TinyVLA - Improved version of SimpleDNN VLA
- Better CNN architecture (ResNet-style)
- Attention mechanism
- No additional dependencies
- Ready to use immediately
"""

import torch
import torch.nn as nn
import torchvision.transforms as transforms
from PIL import Image
import re


class ResidualBlock(nn.Module):
    """残差ブロック"""
    def __init__(self, channels):
        super().__init__()
        self.conv1 = nn.Conv2d(channels, channels, 3, padding=1)
        self.bn1 = nn.BatchNorm2d(channels)
        self.conv2 = nn.Conv2d(channels, channels, 3, padding=1)
        self.bn2 = nn.BatchNorm2d(channels)
        
    def forward(self, x):
        residual = x
        out = torch.relu(self.bn1(self.conv1(x)))
        out = self.bn2(self.conv2(out))
        out += residual
        return torch.relu(out)


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
        
        # 画像エンコーダ（ResNet-style）
        self.image_encoder = nn.Sequential(
            # Block 1: 256 -> 128
            nn.Conv2d(3, 32, kernel_size=5, stride=2, padding=2),
            nn.BatchNorm2d(32),
            nn.ReLU(),
            ResidualBlock(32),
            
            # Block 2: 128 -> 64
            nn.Conv2d(32, 64, kernel_size=3, stride=2, padding=1),
            nn.BatchNorm2d(64),
            nn.ReLU(),
            ResidualBlock(64),
            
            # Block 3: 64 -> 32
            nn.Conv2d(64, 128, kernel_size=3, stride=2, padding=1),
            nn.BatchNorm2d(128),
            nn.ReLU(),
            ResidualBlock(128),
            
            # Block 4: 32 -> 16
            nn.Conv2d(128, 256, kernel_size=3, stride=2, padding=1),
            nn.BatchNorm2d(256),
            nn.ReLU(),
            
            # Global pooling
            nn.AdaptiveAvgPool2d(1),
            nn.Flatten()  # -> 256
        )
        
        # マルチヘッドアテンション（4枚の画像間の関係を学習）
        self.attention = nn.MultiheadAttention(
            embed_dim=256,
            num_heads=4,
            batch_first=True
        )
        
        # プロンプトエンコーダ
        self.prompt_dim = 5  # [current, target, valve, upstream, downstream]
        
        # プロンプトMLP
        self.prompt_encoder = nn.Sequential(
            nn.Linear(self.prompt_dim, 32),
            nn.ReLU(),
            nn.Linear(32, 64),
            nn.ReLU()
        )
        
        # 統合MLP（より深い）
        self.mlp = nn.Sequential(
            nn.Linear(256 + 64, 256),
            nn.ReLU(),
            nn.Dropout(0.2),
            nn.Linear(256, 128),
            nn.ReLU(),
            nn.Dropout(0.2),
            nn.Linear(128, 64),
            nn.ReLU(),
            nn.Dropout(0.1),
            nn.Linear(64, 1),
            nn.Tanh()
        )
        
        self.transform = transforms.Compose([
            transforms.Resize((256, 256)),
            transforms.ToTensor(),
            transforms.Normalize(mean=[0.485, 0.456, 0.406], 
                               std=[0.229, 0.224, 0.225])
        ])
    
    def encode_prompt(self, prompt):
        """プロンプトから数値を抽出"""
        # SimpleDNNVLAと同じ
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
        
        # 正規化
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
        # 画像タイプの優先順位（visual-first推奨）
        image_types = [
            'network_state_map', 'temporal_slice', 'phase_space', 'multiscale_change'
        ]
        
        # フォールバック（legacy）
        if not any(img_type in images_dict for img_type in image_types):
            image_types = ['system_ui', 'valve_detail', 'flow_dashboard', 'comparison']
        
        # 画像エンコーディング
        image_features_list = []
        for img_type in image_types:
            img = images_dict.get(img_type)
            if img is None:
                img = Image.new('RGB', (256, 256), color=(128, 128, 128))
            
            img_tensor = self.transform(img).unsqueeze(0)  # [1, 3, 256, 256]
            features = self.image_encoder(img_tensor)  # [1, 256]
            image_features_list.append(features)
        
        # Stack for attention: [1, 4, 256]
        image_features_stacked = torch.stack(image_features_list, dim=1)
        
        # Self-attention（画像間の関係を学習）
        attended_features, _ = self.attention(
            image_features_stacked,
            image_features_stacked,
            image_features_stacked
        )  # [1, 4, 256]
        
        # Mean pooling over images
        image_features = attended_features.mean(dim=1)  # [1, 256]
        
        # プロンプトエンコーディング
        prompt_features = self.encode_prompt(prompt).unsqueeze(0)  # [1, 5]
        prompt_features = self.prompt_encoder(prompt_features)  # [1, 64]
        
        # 統合
        combined = torch.cat([image_features, prompt_features], dim=1)  # [1, 320]
        
        # 予測
        delta_valve = self.mlp(combined) * 0.05  # Tanh(-1~1) -> (-0.05~0.05)
        
        return delta_valve.item()


class TinyVLAWrapper:
    """TinyVLAのラッパー（SimpleDNNVLAと同じインターフェース）"""
    
    def __init__(self, checkpoint_path=None):
        self.model = TinyVLA()
        
        if checkpoint_path:
            try:
                self.model.load_state_dict(torch.load(checkpoint_path, map_location='cpu'))
                print(f"[TinyVLA] Loaded checkpoint from {checkpoint_path}")
            except Exception as e:
                print(f"[TinyVLA] Warning: Could not load checkpoint: {e}")
                print("[TinyVLA] Using random initialization")
        
        self.model.eval()
        print("[TinyVLA] Initialized TinyVLA Model")
        print("[TinyVLA] Architecture: ResNet-style + Attention")
        print("[TinyVLA] Parameters: ~2M (lightweight)")
    
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
    print("Testing TinyVLA...")
    
    images = {
        'network_state_map': Image.new('RGB', (256, 256), color=(100, 150, 200)),
        'temporal_slice': Image.new('RGB', (256, 256), color=(150, 100, 200)),
        'phase_space': Image.new('RGB', (256, 256), color=(200, 150, 100)),
        'multiscale_change': Image.new('RGB', (256, 256), color=(150, 200, 100))
    }
    
    prompt = "Current pressure: 35.5m, target: 30.0m, Valve opening: 75.0%"
    
    model = TinyVLAWrapper()
    action = model.predict(images, prompt)
    
    print(f"Result: delta_valve = {action:.4f}")