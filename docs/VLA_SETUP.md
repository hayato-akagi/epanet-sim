# VLAセットアップガイド

Vision-Language-Action (VLA) 制御の詳細なセットアップと使用方法。

---

## 目次

1. [VLA制御とは](#vla制御とは)
2. [システムアーキテクチャ](#システムアーキテクチャ)
3. [セットアップ手順](#セットアップ手順)
4. [対応モデル](#対応モデル)
5. [学習の監視](#学習の監視)
6. [トラブルシューティング](#トラブルシューティング)
7. [高度な使い方](#高度な使い方)

---

## VLA制御とは

### 概要

VLA (Vision-Language-Action) 制御は、画像とテキストを入力として、制御行動を出力する深層強化学習ベースの制御手法です。

### 特徴

- ✅ **視覚情報の活用**: ネットワーク状態を画像として理解
- ✅ **自然言語との統合**: テキストプロンプトで状態を説明
- ✅ **継続的な学習**: 運用しながら性能を改善
- ✅ **モデル不要**: 水理モデルの同定が不要

### 構成要素

```
[ネットワーク状態]
       │
       ├─> [画像生成] ──> [4種類の可視化画像]
       │                       │
       └─> [プロンプト生成]    │
                   │           │
                   └─────┬─────┘
                         ↓
                   [VLAモデル]
                         │
                         ├─> [Actor] ──> [行動]
                         └─> [Critic] ──> [価値]
                               │
                         [SAC学習]
```

---

## システムアーキテクチャ

### サービス構成

```
[controller-vla]
    │
    ├─ VLAController
    │   ├─ VLAModel (SimpleDNN/OpenVLA)
    │   ├─ SACAgent (学習)
    │   └─ TrainingLogger
    │
    ├─ ImageFetcher
    │   └─> [image-generator] ──> [Redis]
    │
    ├─ PromptGenerator
    │
    └─ DataLogger
        └─> [data-collector]
```

### データフロー

1. **観測**: センサーデータ取得
2. **画像生成**: image-generatorで4種類の画像を生成
3. **画像取得**: Redisから画像を取得
4. **プロンプト生成**: 状態を説明するテキストを生成
5. **推論**: VLAモデルで行動を推論
6. **学習**: SACアルゴリズムで学習
7. **データ収集**: data-collectorに保存

---

## セットアップ手順

### 1. 環境設定

```bash
# .envファイルを作成
cat > .env << 'EOF'
EXP_ID=vla_experiment_001
EXP_CONFIG_FILE=exp_vla.json
CONTROLLER_HOST=controller-vla
VLA_MODEL=simple_dnn
VLA_CHECKPOINT=
EOF
```

**環境変数**:

| 変数 | 説明 | デフォルト |
|:---|:---|:---|
| `EXP_ID` | 実験ID | exp_001 |
| `EXP_CONFIG_FILE` | 設定ファイル名 | exp_vla.json |
| `CONTROLLER_HOST` | コントローラーホスト | controller-vla |
| `VLA_MODEL` | VLAモデル | simple_dnn |
| `VLA_CHECKPOINT` | チェックポイントパス | なし |

---

### 2. 設定ファイルの作成

**最小限の設定**:
```json
{
  "control_mode": "pressure",
  "network": {
    "inp_file": "Net1.inp"
  },
  "simulation": {
    "duration": 86400,
    "hydraulic_step": 600
  },
  "control_loops": [
    {
      "loop_id": "loop_1",
      "target": {
        "node_id": "10",
        "target_pressure": 120.0
      },
      "actuator": {
        "link_id": "9",
        "initial_setting": 1.0
      },
      "vla_params": {
        "learning_mode": "online",
        "action": {
          "type": "delta",
          "delta_range": [-0.05, 0.05],
          "absolute_range": [0.0, 2.0]
        },
        "training": {
          "batch_size": 32,
          "actor_lr": 3e-4,
          "critic_lr": 3e-4,
          "gamma": 0.99,
          "tau": 0.005,
          "buffer_size": 10000
        },
        "exploration": {
          "initial_noise": 0.1,
          "noise_decay": 0.995,
          "min_noise": 0.01
        },
        "reward": {
          "tracking_weight": 1.0,
          "stability_weight": 0.5,
          "safety_weight": 10.0
        }
      }
    }
  ]
}
```

---

### 3. サービスの起動

```bash
# すべてのサービスを起動
docker-compose up --build

# または、段階的に起動
docker-compose up -d redis image-generator data-collector
docker-compose up -d controller-vla
docker-compose up sim-runner
```

**起動順序**:
1. redis（画像キャッシュ）
2. image-generator（画像生成）
3. data-collector（データ収集）
4. controller-vla（VLA制御）
5. sim-runner（シミュレーション）

---

### 4. 動作確認

```bash
# controller-vlaのログ確認
docker-compose logs -f controller-vla | grep -E "(Initialized|EPISODE|ERROR)"

# Redisの画像キー確認
docker-compose exec redis redis-cli DBSIZE

# 学習データの確認
ls -la shared/training_data/vla_experiment_001/
```

**期待される出力**:
```
Connected to Redis: redis://redis:6379
Initialized SimpleDNN VLA Model
SAC Agent initialized (simplified version)
[VLAController] Initialized: loop_1
  Model: simple_dnn
  Max steps per episode: 144
```

---

## 対応モデル

### SimpleDNN（推奨）

**特徴**:
- 軽量なCNN + MLP
- 高速な学習・推論
- デバッグに最適

**アーキテクチャ**:
```python
[4画像]
   │
   ├─> [CNN] ──> [64次元] ×4
   │
   └─> [Concat] ──> [256次元]
          │
          ├─> [プロンプト] ──> [5次元]
          │
          └─> [Concat] ──> [261次元]
                 │
                 └─> [MLP] ──> [delta_action]
```

**使用方法**:
```bash
VLA_MODEL=simple_dnn docker-compose up --build
```

---

### OpenVLA（大規模モデル）

**特徴**:
- 大規模な事前学習済みVLAモデル
- 高い表現力
- 計算コスト高

**必要リソース**:
- GPU: 8GB以上
- メモリ: 16GB以上

**使用方法**:
```bash
VLA_MODEL=openvla docker-compose up --build
```

**注意**: 現在未実装。将来のリリースで対応予定。

---

### SmolVLA / TinyVLA

**特徴**:
- 中間サイズのモデル
- OpenVLAより軽量

**使用方法**:
```bash
VLA_MODEL=smolvla docker-compose up --build
# または
VLA_MODEL=tinyvla docker-compose up --build
```

**注意**: 現在未実装。将来のリリースで対応予定。

---

## 学習の監視

### 1. リアルタイムログ

```bash
# エピソード完了ログ
docker-compose logs -f controller-vla | grep "EPISODE.*COMPLETED"

# Critic損失
docker-compose logs -f controller-vla | grep "critic_loss"

# Actor損失
docker-compose logs -f controller-vla | grep "actor_loss"
```

**期待される出力**:
```
============================================================
[VLAController] EPISODE 0 COMPLETED!
============================================================
  Total steps in episode: 144
  Episode buffer size: 144
  Episode 0 Summary:
  ├─ Episode reward: -575.16
  ├─ Mean reward: -3.99
  ├─ MAE: 26.95 m
  ├─ RMSE: 39.55 m
  └─ Mean critic loss: 9.27
============================================================
```

---

### 2. training_steps.csv

ステップごとの詳細ログ。

**場所**: `shared/results/{EXP_ID}/training_steps.csv`

**主な列**:

| 列名 | 説明 |
|:---|:---|
| `episode` | エピソード番号 |
| `step_in_episode` | エピソード内ステップ |
| `total_steps` | 総ステップ数 |
| `pressure` | 観測圧力 |
| `target_pressure` | 目標圧力 |
| `valve_setting` | バルブ開度 |
| `delta_action` | 行動（変化量） |
| `reward` | 即時報酬 |
| `critic_loss` | Critic損失 |
| `actor_loss` | Actor損失 |
| `exploration` | 探索中かどうか |

**確認コマンド**:
```bash
# 最新10ステップ
tail -10 shared/results/vla_experiment_001/training_steps.csv

# Critic損失の推移
cut -d',' -f16 shared/results/vla_experiment_001/training_steps.csv | tail -50
```

---

### 3. training_episodes.csv

エピソードごとの統計。

**場所**: `shared/results/{EXP_ID}/training_episodes.csv`

**主な列**:

| 列名 | 説明 |
|:---|:---|
| `episode` | エピソード番号 |
| `total_steps` | 総ステップ数 |
| `episode_steps` | エピソードステップ数 |
| `episode_reward` | エピソード累積報酬 |
| `mean_reward` | 平均報酬 |
| `mae` | 平均絶対誤差 |
| `rmse` | 二乗平均平方根誤差 |
| `mean_critic_loss` | 平均Critic損失 |
| `mean_actor_loss` | 平均Actor損失 |

**確認コマンド**:
```bash
# 全エピソード表示
cat shared/results/vla_experiment_001/training_episodes.csv
```

---

### 4. Pythonでの可視化

```python
import pandas as pd
import matplotlib.pyplot as plt

# training_steps.csvを読み込み
df_steps = pd.read_csv('shared/results/vla_experiment_001/training_steps.csv')

# Critic損失の推移
plt.figure(figsize=(12, 4))
plt.plot(df_steps['total_steps'], df_steps['critic_loss'])
plt.xlabel('Total Steps')
plt.ylabel('Critic Loss')
plt.title('Learning Progress: Critic Loss')
plt.grid(True)
plt.savefig('critic_loss.png')

# 報酬の推移
plt.figure(figsize=(12, 4))
plt.plot(df_steps['total_steps'], df_steps['reward'])
plt.xlabel('Total Steps')
plt.ylabel('Reward')
plt.title('Learning Progress: Reward')
plt.grid(True)
plt.savefig('reward.png')

# training_episodes.csvを読み込み
df_episodes = pd.read_csv('shared/results/vla_experiment_001/training_episodes.csv')

# エピソードごとのMAE
plt.figure(figsize=(12, 4))
plt.plot(df_episodes['episode'], df_episodes['mae'])
plt.xlabel('Episode')
plt.ylabel('MAE (m)')
plt.title('Learning Progress: MAE')
plt.grid(True)
plt.savefig('mae.png')
```

---

### 5. 学習曲線の評価

**健全な学習の兆候**:
- ✅ Critic損失が収束（通常10以下）
- ✅ MAE/RMSEが減少傾向
- ✅ 報酬が増加傾向
- ✅ エピソード報酬が安定

**問題のある学習**:
- ❌ Critic損失が発散
- ❌ MAE/RMSEが増加
- ❌ 報酬が減少または不安定
- ❌ Actor損失が異常に大きい

---

## トラブルシューティング

### 学習が進まない

**症状**: Critic損失が減少しない

**原因と対策**:

1. **学習率が高すぎる**
   ```json
   "training": {
     "actor_lr": 1e-4,  // 3e-4 → 1e-4に下げる
     "critic_lr": 1e-4
   }
   ```

2. **バッチサイズが小さすぎる**
   ```json
   "training": {
     "batch_size": 64  // 32 → 64に増やす
   }
   ```

3. **リプレイバッファが小さい**
   ```json
   "training": {
     "buffer_size": 50000  // 10000 → 50000に増やす
   }
   ```

---

### 制御が不安定

**症状**: 大きな振動、発散

**原因と対策**:

1. **探索ノイズが大きすぎる**
   ```json
   "exploration": {
     "initial_noise": 0.05,  // 0.1 → 0.05に下げる
     "noise_decay": 0.99     // 0.995 → 0.99に速くする
   }
   ```

2. **行動範囲が大きすぎる**
   ```json
   "action": {
     "delta_range": [-0.02, 0.02]  // [-0.05, 0.05] → 縮小
   }
   ```

3. **安全制約の重みが小さい**
   ```json
   "reward": {
     "safety_weight": 20.0  // 10.0 → 20.0に増やす
   }
   ```

---

### 画像が生成されない

**症状**: `ImageFetcher.fetch returning 0 images`

**原因と対策**:

1. **image-generatorが起動していない**
   ```bash
   docker-compose up -d image-generator
   ```

2. **Redisが起動していない**
   ```bash
   docker-compose up -d redis
   ```

3. **接続先URLが間違っている**
   ```bash
   # controller-vlaの環境変数を確認
   docker-compose exec controller-vla env | grep IMAGE_GENERATOR_URL
   ```

---

### メモリ不足

**症状**: `RuntimeError: CUDA out of memory`

**原因と対策**:

1. **バッチサイズを減らす**
   ```json
   "training": {
     "batch_size": 16  // 32 → 16に減らす
   }
   ```

2. **リプレイバッファを減らす**
   ```json
   "training": {
     "buffer_size": 5000  // 10000 → 5000に減らす
   }
   ```

3. **SimpleDNNモデルを使用**
   ```bash
   VLA_MODEL=simple_dnn docker-compose up --build
   ```

---

## 高度な使い方

### チェックポイントの保存と読み込み

**保存**:
```bash
# training/controller.pyで自動保存
# 場所: shared/results/{EXP_ID}/checkpoints/
```

**読み込み**:
```bash
# .envファイルで指定
VLA_CHECKPOINT=/shared/results/vla_experiment_001/checkpoints/episode_100.pth \
docker-compose up --build
```

---

### ハイパーパラメータチューニング

#### 学習率の調整

```bash
# 複数の学習率で実験
for lr in 1e-4 3e-4 1e-3; do
  cat > shared/configs/exp_vla_lr_${lr}.json << EOF
{
  ...
  "vla_params": {
    "training": {
      "actor_lr": ${lr},
      "critic_lr": ${lr}
    }
  }
}
EOF
  
  EXP_ID=vla_lr_${lr} \
  EXP_CONFIG_FILE=exp_vla_lr_${lr}.json \
  docker-compose up sim-runner controller-vla
done
```

#### 探索戦略の調整

```bash
# 異なるノイズレベルで実験
for noise in 0.05 0.1 0.2; do
  # 設定ファイルを編集
  # 実験を実行
done
```

---

### 複数エピソードの学習

**設定**:
```json
{
  "simulation": {
    "duration": 86400,     // 1エピソード = 24時間
    "hydraulic_step": 600  // 144ステップ
  }
}
```

**複数エピソード実行**:
```bash
# 10エピソード実行
for episode in {1..10}; do
  EXP_ID=vla_episode_${episode} \
  docker-compose up sim-runner controller-vla
done
```

---

### カスタム報酬関数

**実装場所**: `controller-vla/utils/reward.py`

**例**:
```python
class CustomRewardCalculator:
    def calculate(self, current_pressure, target_pressure, 
                  prev_pressure, valve_change, time_step):
        # 追従報酬
        tracking_error = abs(target_pressure - current_pressure)
        tracking_reward = -tracking_error * self.tracking_weight
        
        # 安定性報酬
        stability_reward = -abs(valve_change) * self.stability_weight
        
        # 時間帯による重み調整
        hour = (time_step // 3600) % 24
        if 6 <= hour <= 22:  # 日中
            tracking_reward *= 1.5  # 追従性重視
        else:  # 夜間
            stability_reward *= 1.5  # 安定性重視
        
        return {
            'total_reward': tracking_reward + stability_reward,
            'tracking': tracking_reward,
            'stability': stability_reward
        }
```

---

### オフライン学習データの活用

**データ収集**:
```bash
# data-collectorが自動的に保存
ls -la shared/training_data/vla_experiment_001/
```

**データ構造**:
```json
{
  "timestamp": "2025-12-01T...",
  "step": 0,
  "time_step": 0,
  "state": {
    "pressure": 127.5,
    "target": 120.0,
    "valve_setting": 1.0
  },
  "action": {
    "delta_action": 0.015
  },
  "reward": -0.5,
  "images": {
    "system_ui": "redis_key"
  }
}
```

**オフライン学習（将来実装）**:
```python
# データローダー
dataset = VLADataset('shared/training_data/vla_experiment_001/')

# オフライン学習
for epoch in range(100):
    for batch in dataset:
        loss = agent.offline_update(batch)
```

---

## 次のステップ

- [メトリクス詳細](METRICS.md)で性能評価方法を学習
- [可視化ガイド](VISUALIZATION.md)で学習曲線の見方を確認
- 実験を実行して学習の進捗を監視