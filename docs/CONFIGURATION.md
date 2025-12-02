# 設定ファイル詳細ガイド

実験設定は `shared/configs/*.json` で管理されます。

---

## 目次

1. [設定ファイルの構造](#設定ファイルの構造)
2. [基本設定](#基本設定)
3. [単一ループ設定](#単一ループ設定)
4. [複数ループ設定](#複数ループ設定)
5. [PIDパラメータ](#pidパラメータ)
6. [MPCパラメータ](#mpcパラメータ)
7. [VLAパラメータ](#vlaパラメータ)
8. [設定例集](#設定例集)

---

## 設定ファイルの構造

### 単一ループ設定

```json
{
  "control_mode": "pressure",
  "network": { ... },
  "simulation": { ... },
  "target": { ... },
  "actuator": { ... },
  "pid_params": { ... },
  "mpc_params": { ... }
}
```

### 複数ループ設定

```json
{
  "control_mode": "pressure",
  "network": { ... },
  "simulation": { ... },
  "control_loops": [
    {
      "loop_id": "loop_1",
      "target": { ... },
      "actuator": { ... },
      "pid_params": { ... }
    }
  ]
}
```

---

## 基本設定

### control_mode

制御モードの指定。

| 値 | 説明 |
|:---|:---|
| `"pressure"` | 圧力制御モード（デフォルト） |
| `"flow"` | 流量制御モード |

**例**:
```json
{
  "control_mode": "pressure"
}
```

---

### network

EPANETネットワークファイルの指定。

| パラメータ | 型 | 説明 | 必須 |
|:---|:---|:---|:---:|
| `inp_file` | string | EPANETファイル名 | ✅ |

**例**:
```json
{
  "network": {
    "inp_file": "Net1.inp"
  }
}
```

**利用可能なINPファイル**:
- `Net1.inp` - EPANET公式サンプル（小規模）
- `Net2.inp` - 中規模ネットワーク
- `Net3.inp` - 大規模ネットワーク
- カスタムINPファイル（`shared/networks/`に配置）

---

### simulation

シミュレーション実行パラメータ。

| パラメータ | 型 | 説明 | 推奨値 | 必須 |
|:---|:---|:---|:---|:---:|
| `duration` | integer | シミュレーション総時間（秒） | 86400（24時間） | ✅ |
| `hydraulic_step` | integer | 水理計算タイムステップ（秒） | 300〜3600 | ✅ |

**例**:
```json
{
  "simulation": {
    "duration": 86400,
    "hydraulic_step": 600
  }
}
```

**hydraulic_stepの選び方**:

| 値 | ステップ数 | 用途 | 計算時間 |
|---:|---:|:---|:---|
| 300秒 | 288 | 高精度実験 | 長い |
| 600秒 | 144 | 標準実験 | 中程度 |
| 1800秒 | 48 | 高速テスト | 短い |
| 3600秒 | 24 | 概算確認 | 非常に短い |

**注意**:
- 小さすぎる → 計算時間増加、数値誤差
- 大きすぎる → 制御精度低下、見逃し

---

## 単一ループ設定

### target

制御目標の指定。

| パラメータ | 型 | 説明 | 制御モード | 必須 |
|:---|:---|:---|:---|:---:|
| `node_id` | string | 観測ノードID | 両方 | ✅ |
| `target_pressure` | float | 目標圧力（m） | pressure | ✅ |
| `target_flow` | float | 目標流量（m³/h） | flow | ✅ |

**例（圧力制御）**:
```json
{
  "target": {
    "node_id": "10",
    "target_pressure": 120.0
  }
}
```

**例（流量制御）**:
```json
{
  "target": {
    "node_id": "2",
    "target_flow": 100.0
  }
}
```

**ノードIDの確認方法**:
```bash
# EPANETファイルからノードIDを抽出
grep "^\[JUNCTIONS\]" -A 100 shared/networks/Net1.inp
```

---

### actuator

制御アクチュエータ（バルブ）の指定。

| パラメータ | 型 | 説明 | 範囲 | 必須 |
|:---|:---|:---|:---|:---:|
| `link_id` | string | バルブのリンクID | - | ✅ |
| `initial_setting` | float | 初期バルブ開度 | 0.0〜1.0 | ✅ |

**例**:
```json
{
  "actuator": {
    "link_id": "9",
    "initial_setting": 1.0
  }
}
```

**initial_settingの推奨値**:
- `0.5` - 中立位置（標準）
- `1.0` - 全開（VLA制御で推奨）
- `0.3〜0.7` - 調整余地あり

**リンクIDの確認方法**:
```bash
# EPANETファイルからリンクIDを抽出
grep "^\[PIPES\]" -A 100 shared/networks/Net1.inp
grep "^\[PUMPS\]" -A 100 shared/networks/Net1.inp
```

---

## 複数ループ設定

### control_loops

複数の制御ループを定義する配列。

**構造**:
```json
{
  "control_loops": [
    {
      "loop_id": "loop_1",
      "target": { ... },
      "actuator": { ... },
      "pid_params": { ... }
    },
    {
      "loop_id": "loop_2",
      "target": { ... },
      "actuator": { ... },
      "pid_params": { ... }
    }
  ]
}
```

**各ループの要素**:

| パラメータ | 型 | 説明 | 必須 |
|:---|:---|:---|:---:|
| `loop_id` | string | ループ識別子 | ✅ |
| `target` | object | 制御目標 | ✅ |
| `actuator` | object | 制御バルブ | ✅ |
| `pid_params` | object | PIDパラメータ（オプション） | ❌ |
| `mpc_params` | object | MPCパラメータ（オプション） | ❌ |
| `vla_params` | object | VLAパラメータ（オプション） | ❌ |

**完全な例**:
```json
{
  "control_mode": "pressure",
  "network": {
    "inp_file": "Net1.inp"
  },
  "simulation": {
    "duration": 86400,
    "hydraulic_step": 3600
  },
  "control_loops": [
    {
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
    },
    {
      "loop_id": "loop_2",
      "target": {
        "node_id": "12",
        "target_pressure": 25.0
      },
      "actuator": {
        "link_id": "12",
        "initial_setting": 0.6
      },
      "pid_params": {
        "Kp": 0.03,
        "Ki": 0.002,
        "Kd": 0.06
      }
    }
  ]
}
```

**注意点**:
- `loop_id` はユニークである必要がある
- 各ループは独立して制御される（分散制御）
- ループ間の相互作用は考慮されない

---

## PIDパラメータ

### 基本パラメータ

| パラメータ | 型 | 説明 | 推奨範囲 | 必須 |
|:---|:---|:---|:---|:---:|
| `Kp` (または `kp`) | float | 比例ゲイン | 0.01〜2.0 | ✅ |
| `Ki` (または `ki`) | float | 積分ゲイン | 0.0001〜0.5 | ✅ |
| `Kd` (または `kd`) | float | 微分ゲイン | 0.001〜0.2 | ✅ |
| `setpoint` | float | 目標値（通常targetと同じ） | - | ❌ |

**圧力制御の例**:
```json
{
  "pid_params": {
    "Kp": 0.5,
    "Ki": 0.1,
    "Kd": 0.05,
    "setpoint": 30.0
  }
}
```

**流量制御の例**:
```json
{
  "pid_params": {
    "Kp": 0.01,
    "Ki": 0.001,
    "Kd": 0.02,
    "kp_flow": 0.01,
    "ki_flow": 0.001,
    "kd_flow": 0.02,
    "setpoint_flow": 100.0
  }
}
```

### チューニングガイド

#### Ziegler-Nichols法（第一法）

1. **Ki = 0, Kd = 0に設定**
2. **Kpを徐々に増加**
   - 振動が始まるまで増やす
   - この時のKpを「限界ゲイン Ku」とする
   - 振動周期を「Tu」とする

3. **以下の式で計算**:
   - `Kp = 0.6 * Ku`
   - `Ki = 1.2 * Ku / Tu`
   - `Kd = 0.075 * Ku * Tu`

#### 手動チューニング

| ステップ | 操作 | 効果 |
|:---|:---|:---|
| 1 | Kpを増やす | 応答速度↑、振動リスク↑ |
| 2 | Kiを増やす | 定常偏差除去、振動リスク↑ |
| 3 | Kdを増やす | オーバーシュート抑制 |

#### 典型的なパラメータ値

| ネットワーク規模 | Kp | Ki | Kd |
|:---|---:|---:|---:|
| 小規模（Net1） | 0.5〜2.0 | 0.01〜0.1 | 0.01〜0.1 |
| 中規模 | 0.1〜0.5 | 0.001〜0.01 | 0.005〜0.05 |
| 大規模 | 0.01〜0.1 | 0.0001〜0.001 | 0.001〜0.01 |

---

## MPCパラメータ

### 基本パラメータ

| パラメータ | 型 | 説明 | 推奨範囲 | 必須 |
|:---|:---|:---|:---|:---:|
| `horizon` | integer | 予測ホライゾン（ステップ数） | 5〜20 | ✅ |
| `dt` | integer | タイムステップ（秒） | hydraulic_stepと同じ | ✅ |
| `tau` | float | 時定数（秒） | 600〜7200 | ✅ |
| `K` | float | プロセスゲイン | 30〜200 | ✅ |
| `weight_error` | float | 追従誤差の重み | 0.5〜2.0 | ✅ |
| `weight_du` | float | 操作量変化の重み | 0.1〜20.0 | ✅ |

**圧力制御の例**:
```json
{
  "mpc_params": {
    "horizon": 10,
    "dt": 300,
    "tau": 1800.0,
    "K": 50.0,
    "weight_error": 1.0,
    "weight_du": 10.0
  }
}
```

**流量制御の例**:
```json
{
  "mpc_params": {
    "horizon": 10,
    "dt": 300,
    "tau": 1200.0,
    "K": 30.0,
    "tau_flow": 1200.0,
    "K_flow": 30.0,
    "weight_error": 1.0,
    "weight_du": 0.5
  }
}
```

### モデルパラメータの同定

#### ステップ応答実験

1. **実験準備**
   - バルブを初期値（例: 0.5）で安定させる
   - 十分な時間待つ

2. **ステップ入力**
   - バルブを0.5→0.6に変更（Δu = 0.1）
   - 圧力応答を記録

3. **時定数τの推定**
   - 最終値の63.2%に到達する時間
   - グラフから読み取る

4. **ゲインKの推定**
   ```
   K = Δy / Δu
   ```
   - Δy: 圧力変化
   - Δu: バルブ変化（0.1）

**例**:
- バルブ: 0.5 → 0.6（Δu = 0.1）
- 圧力: 25m → 30m（Δy = 5m）
- τ: 1800秒（30分）
- K = 5 / 0.1 = 50

### チューニングガイド

#### horizon（予測ホライゾン）

| 値 | 特徴 | 用途 |
|---:|:---|:---|
| 5 | 計算速度最優先 | リアルタイム制御 |
| 10 | バランス型（推奨） | 標準的な制御 |
| 20 | 最適性重視 | オフライン最適化 |

#### weight_error vs weight_du

| weight_error | weight_du | 挙動 |
|:---:|:---:|:---|
| 大 | 小 | 追従性↑、操作量大 |
| 小 | 大 | 滑らか↑、追従性↓ |
| 1.0 | 10.0 | バランス型（推奨） |

---

## VLAパラメータ

### 基本パラメータ

```json
{
  "vla_params": {
    "learning_mode": "online",
    "action": { ... },
    "training": { ... },
    "exploration": { ... },
    "reward": { ... }
  }
}
```

### learning_mode

| 値 | 説明 |
|:---|:---|
| `"online"` | オンライン学習（推奨） |
| `"offline"` | オフライン学習（未実装） |

---

### action

行動空間の設定。

| パラメータ | 型 | 説明 | 推奨値 |
|:---|:---|:---|:---|
| `type` | string | "delta"（変化量）または "absolute" | "delta" |
| `delta_range` | array | 変化量の範囲 [min, max] | [-0.05, 0.05] |
| `absolute_range` | array | バルブ開度の範囲 [min, max] | [0.0, 2.0] |

**例**:
```json
{
  "action": {
    "type": "delta",
    "delta_range": [-0.05, 0.05],
    "absolute_range": [0.0, 2.0]
  }
}
```

**delta_rangeの選び方**:
- 大きい（±0.1）: 応答速い、不安定
- 小さい（±0.01）: 安定、応答遅い
- 推奨: ±0.05（バランス型）

---

### training

学習アルゴリズムの設定。

| パラメータ | 型 | 説明 | 推奨値 |
|:---|:---|:---|:---|
| `batch_size` | integer | ミニバッチサイズ | 32〜128 |
| `actor_lr` | float | Actorの学習率 | 1e-4〜1e-3 |
| `critic_lr` | float | Criticの学習率 | 1e-4〜1e-3 |
| `gamma` | float | 割引率 | 0.95〜0.99 |
| `tau` | float | ターゲットネットワーク更新率 | 0.001〜0.01 |
| `buffer_size` | integer | リプレイバッファサイズ | 10000〜100000 |

**例**:
```json
{
  "training": {
    "batch_size": 32,
    "actor_lr": 3e-4,
    "critic_lr": 3e-4,
    "gamma": 0.99,
    "tau": 0.005,
    "buffer_size": 10000
  }
}
```

---

### exploration

探索戦略の設定。

| パラメータ | 型 | 説明 | 推奨値 |
|:---|:---|:---|:---|
| `initial_noise` | float | 初期ノイズレベル | 0.1〜0.3 |
| `noise_decay` | float | ノイズ減衰率 | 0.99〜0.999 |
| `min_noise` | float | 最小ノイズレベル | 0.01〜0.05 |

**例**:
```json
{
  "exploration": {
    "initial_noise": 0.1,
    "noise_decay": 0.995,
    "min_noise": 0.01
  }
}
```

**探索スケジュール**:
```
noise(t) = max(initial_noise * (noise_decay ^ t), min_noise)
```

---

### reward

報酬関数の設定。

| パラメータ | 型 | 説明 | 推奨値 |
|:---|:---|:---|:---|
| `tracking_weight` | float | 追従誤差の重み | 0.5〜2.0 |
| `stability_weight` | float | 安定性の重み | 0.1〜1.0 |
| `safety_weight` | float | 安全制約の重み | 5.0〜20.0 |
| `safety_bounds` | object | 安全境界（オプション） | - |

**例**:
```json
{
  "reward": {
    "tracking_weight": 1.0,
    "stability_weight": 0.5,
    "safety_weight": 10.0,
    "safety_bounds": {
      "pressure_min": 0.0,
      "pressure_max": 200.0
    }
  }
}
```

**報酬関数**:
```python
reward = tracking_reward + stability_reward + safety_reward

tracking_reward = -|target - current| * tracking_weight
stability_reward = -|Δu| * stability_weight
safety_reward = -10 * safety_weight  # if violated
```

---

## 設定例集

### 1. 基本的なPID圧力制御（単一ループ）

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
  "target": {
    "node_id": "2",
    "target_pressure": 30.0
  },
  "actuator": {
    "link_id": "10",
    "initial_setting": 0.5
  },
  "pid_params": {
    "Kp": 0.5,
    "Ki": 0.1,
    "Kd": 0.05
  }
}
```

### 2. MPC圧力制御（単一ループ）

```json
{
  "control_mode": "pressure",
  "network": {
    "inp_file": "Net1.inp"
  },
  "simulation": {
    "duration": 86400,
    "hydraulic_step": 300
  },
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
}
```

### 3. VLA圧力制御（単一ループ）

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

### 4. 複数ループPID制御

```json
{
  "control_mode": "pressure",
  "network": {
    "inp_file": "Net1.inp"
  },
  "simulation": {
    "duration": 86400,
    "hydraulic_step": 3600
  },
  "control_loops": [
    {
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
    },
    {
      "loop_id": "loop_2",
      "target": {
        "node_id": "12",
        "target_pressure": 25.0
      },
      "actuator": {
        "link_id": "12",
        "initial_setting": 0.6
      },
      "pid_params": {
        "Kp": 0.03,
        "Ki": 0.002,
        "Kd": 0.06
      }
    }
  ]
}
```

### 5. 流量制御（PID）

```json
{
  "control_mode": "flow",
  "network": {
    "inp_file": "Net1.inp"
  },
  "simulation": {
    "duration": 86400,
    "hydraulic_step": 600
  },
  "target": {
    "node_id": "2",
    "target_flow": 100.0
  },
  "actuator": {
    "link_id": "10",
    "initial_setting": 0.5
  },
  "pid_params": {
    "Kp": 0.01,
    "Ki": 0.001,
    "Kd": 0.02,
    "kp_flow": 0.01,
    "ki_flow": 0.001,
    "kd_flow": 0.02,
    "setpoint_flow": 100.0
  }
}
```

---

## 設定ファイルの配置

### ファイル配置

```bash
shared/configs/
├── exp_001.json          # 単一ループPID（圧力）
├── exp_pid.json          # 複数ループPID（圧力）
├── exp_mpc.json          # 単一ループMPC（圧力）
├── exp_vla.json          # VLA制御
├── exp_flow_control.json # 流量制御
└── your_custom.json      # カスタム設定
```

### 使用方法

```bash
# .envファイルで指定
cat > .env << 'EOF'
EXP_ID=my_experiment_001
EXP_CONFIG_FILE=your_custom.json
CONTROLLER_HOST=controller-pid
EOF

docker-compose up --build
```

---

## トラブルシューティング

### 設定ファイルが読み込めない

**症状**: `FileNotFoundError: [Errno 2] No such file or directory`

**解決策**:
```bash
# ファイルの存在確認
ls shared/configs/

# パスの確認
echo $EXP_CONFIG_FILE
```

### ノードIDが見つからない

**症状**: `ERROR getting node index`

**解決策**:
```bash
# INPファイルのノードIDを確認
grep "^\[JUNCTIONS\]" -A 100 shared/networks/Net1.inp
```

### 制御が不安定

**症状**: 振動、発散

**解決策**:
1. **PID**: ゲインを下げる（特にKp、Kd）
2. **MPC**: weight_duを上げる
3. **VLA**: noise_decayを速くする

### 応答が遅い

**症状**: 目標値への追従が遅い

**解決策**:
1. **PID**: Kpを上げる
2. **MPC**: horizonを長くする
3. **VLA**: delta_rangeを大きくする

---

## 次のステップ

- [コントローラー詳細](CONTROLLERS.md)で各手法の詳細を学習
- [VLAセットアップガイド](VLA_SETUP.md)でVLA固有の設定を確認
- 実験を実行して結果を分析