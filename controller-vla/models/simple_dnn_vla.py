import torch
import torch.nn as nn
import torchvision.transforms as transforms
from PIL import Image
import re

class SimpleDNNVLA(nn.Module):
    """
    シンプルなDNN版VLA
    - 4枚の画像を小さなCNNで特徴抽出
    - プロンプトから数値を抽出
    - MLPで回帰
    """
    
    def __init__(self):
        super().__init__()
        
        # 画像エンコーダ（各画像共通）
        self.image_encoder = nn.Sequential(
            nn.Conv2d(3, 16, kernel_size=5, stride=2, padding=2),  # 256->128
            nn.ReLU(),
            nn.MaxPool2d(2),  # 128->64
            nn.Conv2d(16, 32, kernel_size=3, stride=2, padding=1),  # 64->32
            nn.ReLU(),
            nn.MaxPool2d(2),  # 32->16
            nn.Conv2d(32, 64, kernel_size=3, stride=2, padding=1),  # 16->8
            nn.ReLU(),
            nn.AdaptiveAvgPool2d(1),  # 8x8 -> 1x1
            nn.Flatten()  # -> 64
        )
        
        # プロンプトエンコーダ（数値抽出）
        self.prompt_dim = 5  # [current, target, valve, upstream, downstream]
        
        # 統合MLP
        self.mlp = nn.Sequential(
            nn.Linear(64 * 4 + self.prompt_dim, 128),  # 4画像+プロンプト
            nn.ReLU(),
            nn.Dropout(0.2),
            nn.Linear(128, 64),
            nn.ReLU(),
            nn.Dropout(0.2),
            nn.Linear(64, 1),  # 出力: Δvalve
            nn.Tanh()  # -1 ~ 1
        )
        
        self.transform = transforms.Compose([
            transforms.Resize((256, 256)),
            transforms.ToTensor(),
            transforms.Normalize(mean=[0.485, 0.456, 0.406], 
                               std=[0.229, 0.224, 0.225])
        ])
    
    def encode_prompt(self, prompt):
        """プロンプトから数値を抽出"""
        # 正規表現で数値を抽出
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
            (current - 30.0) / 10.0,      # 圧力正規化
            (target - 30.0) / 10.0,
            valve,                         # バルブ（0-1）
            (upstream - 40.0) / 10.0,     # 上流圧力
            (downstream - 30.0) / 10.0    # 下流圧力
        ], dtype=torch.float32)
        
        return features
    
    def forward(self, images_dict, prompt):
        """
        推論
        
        Args:
            images_dict: {
                'system_ui': PIL.Image,
                'valve_detail': PIL.Image,
                'flow_dashboard': PIL.Image,
                'comparison': PIL.Image
            }
            prompt: str
        
        Returns:
            torch.Tensor: Δvalve_opening
        """
        print(f"[DEBUG] SimpleDNNVLA forward called")
        print(f"[DEBUG]   images_dict keys: {list(images_dict.keys())}")
        
        # 画像エンコーディング
        image_features = []
        for img_type in ['system_ui', 'valve_detail', 'flow_dashboard', 'comparison']:
            img = images_dict.get(img_type)
            if img is None:
                # ダミー画像
                print(f"[DEBUG]   {img_type}: None, creating dummy")
                img = Image.new('RGB', (256, 256), color=(128, 128, 128))
            else:
                print(f"[DEBUG]   {img_type}: {img.mode} {img.size}")
            
            print(f"[DEBUG]   Transforming {img_type}...")
            img_tensor = self.transform(img).unsqueeze(0)  # [1, 3, 256, 256]
            print(f"[DEBUG]     Tensor shape: {img_tensor.shape}")
            
            print(f"[DEBUG]   Encoding {img_type}...")
            features = self.image_encoder(img_tensor)  # [1, 64]
            print(f"[DEBUG]     Features shape: {features.shape}")
            image_features.append(features)
        
        # 画像特徴を結合
        image_features = torch.cat(image_features, dim=1)  # [1, 256]
        print(f"[DEBUG]   Combined image features shape: {image_features.shape}")
        
        # プロンプトエンコーディング
        print(f"[DEBUG]   Encoding prompt...")
        prompt_features = self.encode_prompt(prompt).unsqueeze(0)  # [1, 5]
        print(f"[DEBUG]   Prompt features shape: {prompt_features.shape}")
        
        # 統合
        combined = torch.cat([image_features, prompt_features], dim=1)  # [1, 261]
        print(f"[DEBUG]   Combined features shape: {combined.shape}")
        
        # 予測
        print(f"[DEBUG]   Passing through MLP...")
        delta_valve = self.mlp(combined) * 0.05  # Tanh(-1~1) -> (-0.05~0.05)
        print(f"[DEBUG]   delta_valve: {delta_valve.item()}")
        
        return delta_valve.item()


class SimpleDNNVLAWrapper:
    """SimpleDNNVLAのラッパー"""
    
    def __init__(self, checkpoint_path=None):
        self.model = SimpleDNNVLA()
        
        if checkpoint_path:
            try:
                self.model.load_state_dict(torch.load(checkpoint_path, map_location='cpu'))
                print(f"Loaded checkpoint from {checkpoint_path}")
            except Exception as e:
                print(f"Warning: Could not load checkpoint: {e}")
                print("Using random initialization")
        
        self.model.eval()
        print("Initialized SimpleDNN VLA Model")
    
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