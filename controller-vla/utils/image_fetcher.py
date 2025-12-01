import os
import io
import redis
import requests
from PIL import Image


class ImageFetcher:
    """
    image-generatorとRedisから画像を取得
    """
    
    def __init__(self, redis_url, image_generator_url):
        """
        Args:
            redis_url: RedisのURL
            image_generator_url: image-generatorのURL
        """
        self.redis_url = redis_url
        self.image_generator_url = image_generator_url
        
        # Redis接続
        if redis_url:
            try:
                self.redis_client = redis.from_url(redis_url, decode_responses=False)
                print(f"Connected to Redis: {redis_url}")
            except Exception as e:
                print(f"Warning: Could not connect to Redis: {e}")
                self.redis_client = None
        else:
            self.redis_client = None
    
    def fetch(self, exp_id, step, state):
        """
        指定されたステップの画像を取得
        
        Args:
            exp_id: 実験ID
            step: ステップ番号
            state: センサーデータ（画像生成のため）
        
        Returns:
            dict: {image_type: PIL.Image}
        """
        print(f"[DEBUG] ImageFetcher.fetch: exp_id={exp_id}, step={step}")
        
        # 1. image-generatorに画像生成をリクエスト
        images_dict = {}
        
        if self.image_generator_url:
            print(f"[DEBUG]   Requesting from {self.image_generator_url}/generate")
            try:
                response = requests.post(
                    f"{self.image_generator_url}/generate",
                    json={
                        "exp_id": exp_id,
                        "step": step,
                        "state": state,
                        "history": {}  # TODO: 履歴データの管理
                    },
                    timeout=5
                )
                
                print(f"[DEBUG]   Response status: {response.status_code}")
                if response.status_code == 200:
                    result = response.json()
                    redis_keys = result.get('redis_keys', {})
                    print(f"[DEBUG]   Got {len(redis_keys)} redis_keys: {list(redis_keys.keys())}")
                    
                    # 2. Redisから画像を取得
                    if self.redis_client:
                        for img_type, redis_key in redis_keys.items():
                            print(f"[DEBUG]     Fetching {img_type} from Redis: {redis_key}")
                            try:
                                img_bytes = self.redis_client.get(redis_key)
                                if img_bytes:
                                    print(f"[DEBUG]       Got {len(img_bytes)} bytes from Redis")
                                    img = Image.open(io.BytesIO(img_bytes))
                                    print(f"[DEBUG]       Opened image: mode={img.mode}, size={img.size}")
                                    # RGBに変換（RGBAの場合があるため）
                                    if img.mode != 'RGB':
                                        print(f"[DEBUG]       Converting from {img.mode} to RGB")
                                        img = img.convert('RGB')
                                    images_dict[img_type] = img
                                    print(f"[DEBUG]       ✓ Successfully loaded {img_type}")
                                else:
                                    print(f"[WARNING] Image not found in Redis: {redis_key}")
                                    images_dict[img_type] = self._create_dummy_image()
                            except Exception as e:
                                print(f"[ERROR] Error loading image from Redis: {e}")
                                import traceback
                                traceback.print_exc()
                                images_dict[img_type] = self._create_dummy_image()
                    else:
                        print("Warning: Redis client not available")
                        for img_type in redis_keys.keys():
                            images_dict[img_type] = self._create_dummy_image()
                else:
                    print(f"Warning: Image generator returned status {response.status_code}")
                    images_dict = self._create_dummy_images()
            
            except Exception as e:
                print(f"[ERROR] Could not fetch images from generator: {e}")
                import traceback
                traceback.print_exc()
                images_dict = self._create_dummy_images()
        else:
            print("[WARNING] Image generator URL not configured")
            images_dict = self._create_dummy_images()
        
        print(f"[DEBUG] ImageFetcher.fetch returning {len(images_dict)} images")
        for img_type, img in images_dict.items():
            if img:
                print(f"[DEBUG]   {img_type}: {img.mode} {img.size}")
        return images_dict
    
    def _create_dummy_image(self):
        """ダミー画像を生成"""
        return Image.new('RGB', (256, 256), color=(128, 128, 128))
    
    def _create_dummy_images(self):
        """全画像タイプのダミー画像を生成"""
        return {
            'system_ui': self._create_dummy_image(),
            'valve_detail': self._create_dummy_image(),
            'flow_dashboard': self._create_dummy_image(),
            'comparison': self._create_dummy_image()
        }