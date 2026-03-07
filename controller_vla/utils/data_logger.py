import requests
import threading
import time


class DataLogger:
    """
    data-collectorへの非同期データ送信
    
    学習データをバッチで送信
    """
    
    def __init__(self, collector_url):
        """
        Args:
            collector_url: data-collectorのURL
        """
        self.collector_url = collector_url
        self.queue = []
        self.lock = threading.Lock()
        self.batch_size = 10
        self.enabled = collector_url is not None
        
        if self.enabled:
            print(f"DataLogger initialized: {collector_url}")
        else:
            print("DataLogger disabled (no collector URL)")
    
    def log_transition(self, transition_data):
        """
        Transitionを記録
        
        Args:
            transition_data: dict with keys ['exp_id', 'loop_id', 'step', 'state', 'action', 'reward', ...]
        """
        if not self.enabled:
            return
        
        with self.lock:
            self.queue.append(transition_data)
        
        # バッチサイズに達したら送信
        if len(self.queue) >= self.batch_size:
            threading.Thread(target=self._send_batch, daemon=True).start()
    
    def _send_batch(self):
        """バッチでdata-collectorに送信"""
        with self.lock:
            if len(self.queue) < self.batch_size:
                return
            
            batch = self.queue[:self.batch_size]
            self.queue = self.queue[self.batch_size:]
        
        try:
            response = requests.post(
                f"{self.collector_url}/collect",
                json={"transitions": batch},
                timeout=5
            )
            
            if response.status_code == 200:
                print(f"[DataLogger] Logged {len(batch)} transitions")
            else:
                print(f"[DataLogger] Failed to log data: status {response.status_code}")
                # 失敗したらキューに戻す
                with self.lock:
                    self.queue = batch + self.queue
        
        except requests.exceptions.Timeout:
            print(f"[DataLogger] Timeout sending data")
            # タイムアウトしたらキューに戻す
            with self.lock:
                self.queue = batch + self.queue
        
        except Exception as e:
            print(f"[DataLogger] Error sending data: {e}")
            # エラーの場合もキューに戻す
            with self.lock:
                self.queue = batch + self.queue
    
    def flush(self):
        """残りのデータを強制送信"""
        if not self.enabled:
            return
        
        with self.lock:
            if not self.queue:
                return
            
            batch = self.queue.copy()
            self.queue = []
        
        try:
            response = requests.post(
                f"{self.collector_url}/collect",
                json={"transitions": batch},
                timeout=10
            )
            
            if response.status_code == 200:
                print(f"[DataLogger] Flushed {len(batch)} transitions")
            else:
                print(f"[DataLogger] Failed to flush data: status {response.status_code}")
        
        except Exception as e:
            print(f"[DataLogger] Error flushing data: {e}")