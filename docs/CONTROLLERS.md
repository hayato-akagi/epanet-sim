# コントローラー詳細ガイド

本システムは3種類の制御アルゴリズムをサポートしています。

---

## 目次

1. [PID制御](#pid制御)
2. [MPC制御](#mpc制御)
3. [VLA制御](#vla制御)
4. [コントローラー比較](#コントローラー比較)

---

## PID制御

### 概要

PID（Proportional-Integral-Derivative）制御は、最も広く使われている古典的な制御手法です。

**動作原理**:
```
u(t) = Kp·e(t) + Ki·∫e(t)dt + Kd·de(t)/dt
```

- **P項**: 現在の誤差に比例
- **I項**: 過去の誤差の累積（定常偏差除去）
- **D項**: 誤差の変化率（オーバーシュート抑制）

### 使用方法

```bash
cat > .env << 'EOF'
EXP_ID=exp_pid_001
EXP_CONFIG_FILE=exp_pid.json
CONTROLLER_HOST=controller-pid
EOF

docker-compose up --build
```

### パラメータ設定

#### 基本パラメータ

| パラメータ | 説明 | チューニング指針 |
|:---|:---|:---|
| **Kp** | 比例ゲイン | 大→応答速↑、振動リスク↑<br>小→安定↑、応答速↓ |
| **Ki** | 積分ゲイン | 大→定常偏差除去↑、振動リスク↑<br>小→安定↑、定常偏差残存 |
| **Kd** | 微分ゲイン | 大→オーバーシュート抑制↑、ノイズ増幅<br>小→滑らか、オーバーシュート許容 |

#### 設定例（圧力制御）

```json
{
  "control_mode": "pressure",
  "control_loops": [{
    "loop_id": "loop_1",
    "target": {
      "node_id": "2",
      "target_pressure": 30.0
    },
    "actuator": {
      "link_id": "10",
      "initial_setting": 0.5
    },
    "pid_params": {
      "Kp": 0.02,
      "Ki": 0.001,
      "Kd": 0.05
    }
  }]
}
```

#### 設定例（流量制御）

```json
"pid_params": {
  "Kp": 0.01,
  "Ki": 0.001,
  "Kd": 0.02,
  "kp_flow": 0.01,
  "ki_flow": 0.001,
  "kd_flow": 0.02,
  "setpoint_flow": 100.0
}
```

### チューニングガイド

#### ステップ1: P制御のみ
1. Ki = 0, Kd = 0に設定
2. Kpを小さい値から徐々に増やす
3. 振動が始まる直前の値を選択

#### ステップ2: I項の追加
1. Kiを小さい値から徐々に増やす
2. 定常偏差が消えるまで調整
3. 振動が激しくなったらKiを下げる

#### ステップ3: D項の追加
1. Kdを小さい値から徐々に増やす
2. オーバーシュートが減少するまで調整
3. ノイズが増幅したらKdを下げる

### 長所・短所

**長所**:
- ✅ 実装がシンプル
- ✅ 計算負荷が低い
- ✅ 幅広い問題に適用可能
- ✅ 調整が比較的容易

**短所**:
- ❌ 制約条件を扱えない
- ❌ 予測制御ができない
- ❌ 複雑なシステムでは最適でない

---

## MPC制御

### 概要

MPC（Model Predictive Control）は、システムのモデルを用いて未来を予測し、最適な制御入力を計算する手法です。

**動作原理**:
1. システムモデルで未来の状態を予測
2. 目的関数を最小化する制御入力を計算
3. 最初の制御入力のみを適用
4. 次のステップで再計算（Receding Horizon）

### 使用方法

```bash
cat > .env << 'EOF'
EXP_ID=exp_mpc_001
EXP_CONFIG_FILE=exp_mpc.json
CONTROLLER_HOST=controller-mpc
EOF

docker-compose up --build
```

### システムモデル

本実装では**一次遅れ系**を仮定：

```
dy/dt = (K·u - y) / τ
```

- **τ (tau)**: 時定数（システムの反応速度）
- **K**: プロセスゲイン（感度）

### パラメータ設定

#### 基本パラメータ

| パラメータ | 説明 | チューニング指針 |
|:---|:---|:---|
| **horizon** | 予測ホライゾン（何ステップ先まで予測） | 大→最適性↑、計算時間↑<br>推奨: 5〜20 |
| **dt** | タイムステップ（秒） | hydraulic_stepと一致 |
| **tau** | 時定数（秒） | システムの反応速度<br>実験的に同定 |
| **K** | プロセスゲイン | システムの感度<br>実験的に同定 |
| **weight_error** | 追従誤差の重み | 大→追従性↑、操作量増 |
| **weight_du** | 操作量変化の重み | 大→滑らか↑、応答遅 |

#### 設定例（圧力制御）

```json
{
  "control_mode": "pressure",
  "control_loops": [{
    "loop_id": "loop_1",
    "target": {
      "node_id": "2",
      "target_pressure": 30.0
    },
    "actuator": {
      "link_id": "10",
      "initial_setting": 0.5
    },
    "mpc_params": {
      "horizon": 10,
      "dt": 300,
      "tau": 1800.0,
      "K": 50.0,
      "weight_error": 1.0,
      "weight_du": 10.0
    }
  }]
}
```

### モデルパラメータの同定

#### ステップ応答実験

1. バルブ開度を0.5→0.6にステップ変化
2. 圧力応答を記録
3. 時定数τを推定:
   - 最終値の63.2%に達する時間
4. ゲインKを推定:
   - K = Δy / Δu

#### 推奨値

| ネットワーク規模 | tau (秒) | K |
|:---|:---|:---|
| 小規模（Net1） | 600〜1800 | 30〜50 |
| 中規模 | 1800〜3600 | 50〜100 |
| 大規模 | 3600〜7200 | 100〜200 |

### 長所・短所

**長所**:
- ✅ 制約条件を明示的に扱える
- ✅ 予測制御が可能
- ✅ 多変数制御に拡張可能
- ✅ 理論的に最適

**短所**:
- ❌ モデル同定が必要
- ❌ 計算負荷が高い
- ❌ パラメータが多い
- ❌ モデル誤差に敏感

---

## VLA制御

### 概要

VLA（Vision-Language-Action）制御は、画像とテキストを入力として行動を出力する、深層強化学習ベースの制御手法です。

**動作原理**:
1. ネットワーク状態を可視化（4種類の画像）
2. 状態を説明するテキストプロンプトを生成
3. VLAモデルが最適な行動を推論
4. SAC（Soft Actor-Critic）で学習

### アーキテクチャ

```
[画像入力] ──┐
             ├─> [VLAモデル] ─> [行動] ─> [環境]
[プロンプト]──┘                    │
                                  ↓
                            [報酬] ─> [SAC学習]
```

### 使用方法

```bash
cat > .env << 'EOF'
EXP_ID=simplednn_001
EXP_CONFIG_FILE=exp_vla.json
CONTROLLER_HOST=controller-vla
VLA_MODEL=simple_dnn
EOF

docker-compose up --build
```

### 対応モデル

| モデル | 説明 | 推奨用途 |
|:---|:---|:---|
| **simple_dnn** | 軽量なCNN+MLP | 学習・デバッグ |
| **openvla** | 大規模VLAモデル | 本格的な実験 |
| **smolvla** | 中規模モデル | バランス型 |
| **tinyvla** | 超軽量モデル | 高速推論 |

### パラメータ設定

#### 基本パラメータ

```json
{
  "control_mode": "pressure",
  "control_loops": [{
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
  }]
}
```

#### 行動空間

| パラメータ | 説明 |
|:---|:---|
| type | "delta"（変化量）または "absolute"（絶対値） |
| delta_range | 1ステップあたりの変化量範囲 |
| absolute_range | バルブ開度の絶対範囲 |

#### 学習パラメータ

| パラメータ | 説明 | 推奨値 |
|:---|:---|:---|
| batch_size | ミニバッチサイズ | 32〜128 |
| actor_lr | Actorの学習率 | 1e-4〜1e-3 |
| critic_lr | Criticの学習率 | 1e-4〜1e-3 |
| gamma | 割引率 | 0.95〜0.99 |
| tau | ターゲットネットワーク更新率 | 0.001〜0.01 |
| buffer_size | リプレイバッファサイズ | 10000〜100000 |

#### 報酬関数

```python
reward = tracking_reward + stability_reward + safety_reward

tracking_reward = -|target - current| * tracking_weight
stability_reward = -|Δu| * stability_weight  
safety_reward = -10 * safety_weight if violated
```

### 出力データ

#### training_episodes.csv
エピソードごとの統計：

| 列 | 説明 |
|:---|:---|
| episode | エピソード番号 |
| episode_reward | エピソードの累積報酬 |
| mae | 平均絶対誤差 |
| rmse | 二乗平均平方根誤差 |
| mean_critic_loss | Criticの平均損失 |
| mean_actor_loss | Actorの平均損失 |

#### training_steps.csv
ステップごとの詳細：

| 列 | 説明 |
|:---|:---|
| step_in_episode | エピソード内ステップ |
| pressure | 観測圧力 |
| target_pressure | 目標圧力 |
| delta_action | 行動（バルブ変化量） |
| reward | 即時報酬 |
| critic_loss | Critic損失 |
| actor_loss | Actor損失 |
| exploration | 探索中かどうか |

### 学習のモニタリング

```bash
# Critic損失の推移
tail -f shared/results/simplednn_001/training_steps.csv | grep critic_loss

# エピソード統計
cat shared/results/simplednn_001/training_episodes.csv
```

**期待される学習曲線**:
- Critic損失: 収束（通常10以下）
- MAE/RMSE: 減少傾向
- 報酬: 増加傾向

### 長所・短所

**長所**:
- ✅ 視覚情報を活用
- ✅ 複雑な非線形システムに対応
- ✅ 学習による継続的改善
- ✅ モデル同定不要

**短所**:
- ❌ 学習に時間がかかる
- ❌ 計算負荷が高い
- ❌ 安定性の保証が困難
- ❌ ハイパーパラメータが多い

---

## コントローラー比較

### 性能比較表

| 項目 | PID | MPC | VLA |
|:---|:---:|:---:|:---:|
| **実装難易度** | ★☆☆ | ★★☆ | ★★★ |
| **チューニング難易度** | ★★☆ | ★★★ | ★★★ |
| **計算負荷** | 低 | 中 | 高 |
| **制約処理** | ❌ | ✅ | ✅ |
| **予測制御** | ❌ | ✅ | △ |
| **学習能力** | ❌ | ❌ | ✅ |
| **視覚情報活用** | ❌ | ❌ | ✅ |

### 使い分けガイド

#### PIDを選ぶべき場合
- ✅ シンプルな制御問題
- ✅ リアルタイム性が最優先
- ✅ 計算リソースが限られている
- ✅ 実績のある手法を使いたい

#### MPCを選ぶべき場合
- ✅ 制約条件がある
- ✅ 予測制御が必要
- ✅ モデル同定が可能
- ✅ 最適性が重要

#### VLAを選ぶべき場合
- ✅ 視覚情報が重要
- ✅ 複雑な非線形システム
- ✅ 継続的な学習・改善が必要
- ✅ 計算リソースに余裕がある

### 実験結果例

典型的な性能指標（Net1ネットワーク、目標圧力120m）:

| コントローラー | MAE | RMSE | TotalVariation |
|:---|---:|---:|---:|
| PID | 2.5 m | 3.8 m | 0.15 |
| MPC | 1.8 m | 2.9 m | 0.08 |
| VLA (学習後) | 2.2 m | 3.2 m | 0.12 |

**注意**: VLAは学習初期の性能は低いが、学習により改善します。

---

## 次のステップ

- [設定ファイル詳細](CONFIGURATION.md)を確認
- [VLAセットアップガイド](VLA_SETUP.md)でVLAの詳細を学習
- [メトリクス詳細](METRICS.md)で性能評価方法を理解