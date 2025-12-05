import os
import io
import redis
from PIL import Image


class ImageFetcher:
    """
    Redisから画像を取得
    画像生成はsim-runnerが行うため、ここでは取得のみ
    """
    
    def __init__(self, redis_url, image_generator_url):
        """
        Args:
            redis_url: RedisのURL
            image_generator_url: image-generatorのURL（未使用、互換性のため保持）
        """
        self.redis_url = redis_url
        self.image_generator_url = image_generator_url  # For compatibility
        
        # Redis接続
        if redis_url:
            try:
                self.redis_client = redis.from_url(redis_url, decode_responses=False)
                print(f"[ImageFetcher] Connected to Redis: {redis_url}")
            except Exception as e:
                print(f"[ImageFetcher] Warning: Could not connect to Redis: {e}")
                self.redis_client = None
        else:
            self.redis_client = None
        
        # 有効な画像タイプ（環境変数から取得）
        enabled_generators = os.environ.get(
            'ENABLED_GENERATORS',
            'network_state_map,temporal_slice,phase_space,multiscale_change'
        )
        self.image_types = [g.strip() for g in enabled_generators.split(',')]
        print(f"[ImageFetcher] Will fetch image types: {self.image_types}")
    
    def fetch(self, exp_id, step, state):
        """
        指定されたステップの画像をRedisから取得
        
        NOTE: 画像生成はsim-runnerが事前に行っているため、
              ここでは既にRedisに保存されている画像を取得するのみ
        
        Args:
            exp_id: 実験ID
            step: ステップ番号
            state: センサーデータ（未使用、互換性のため保持）
        
        Returns:
            dict: {image_type: PIL.Image}
        """
        print(f"[ImageFetcher] Fetching images: exp_id={exp_id}, step={step}")
        
        images_dict = {}
        
        if not self.redis_client:
            print("[ImageFetcher] Redis client not available, returning dummy images")
            return self._create_dummy_images()
        
        # Redisから画像を取得
        for img_type in self.image_types:
            redis_key = f"{exp_id}:step_{step}:{img_type}"
            print(f"[ImageFetcher]   Fetching {img_type} from Redis: {redis_key}")
            
            try:
                img_bytes = self.redis_client.get(redis_key)
                
                if img_bytes:
                    print(f"[ImageFetcher]     Got {len(img_bytes)} bytes from Redis")
                    img = Image.open(io.BytesIO(img_bytes))
                    print(f"[ImageFetcher]     Opened image: mode={img.mode}, size={img.size}")
                    
                    # RGBに変換（RGBAの場合があるため）
                    if img.mode != 'RGB':
                        print(f"[ImageFetcher]     Converting from {img.mode} to RGB")
                        img = img.convert('RGB')
                    
                    images_dict[img_type] = img
                    print(f"[ImageFetcher]     ✓ Successfully loaded {img_type}")
                else:
                    print(f"[ImageFetcher]   ⚠️  Image not found in Redis: {redis_key}")
                    print(f"[ImageFetcher]     This may be normal on first step")
                    images_dict[img_type] = self._create_dummy_image()
            
            except Exception as e:
                print(f"[ImageFetcher]   ✗ Error loading {img_type} from Redis: {e}")
                import traceback
                traceback.print_exc()
                images_dict[img_type] = self._create_dummy_image()
        
        print(f"[ImageFetcher] Returning {len(images_dict)} images")
        for img_type, img in images_dict.items():
            if img:
                print(f"[ImageFetcher]   {img_type}: {img.mode} {img.size}")
        
        return images_dict
    
    def _create_dummy_image(self):
        """ダミー画像を生成"""
        return Image.new('RGB', (256, 256), color=(128, 128, 128))
    
    def _create_dummy_images(self):
        """全画像タイプのダミー画像を生成"""
        return {img_type: self._create_dummy_image() for img_type in self.image_types}