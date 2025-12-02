# メトリクス詳細ガイド

制御性能評価指標の詳細な説明と使い方。

---

## 目次

1. [メトリクスの概要](#メトリクスの概要)
2. [出力ファイル](#出力ファイル)
3. [評価指標](#評価指標)
4. [コントローラー比較](#コントローラー比較)
5. [可視化](#可視化)

---

## メトリクスの概要

### 自動計算の仕組み

```
[sim-runner]
    ↓ result.csv出力
[metrics-calculator]
    ├─ 5秒ごとにポーリング
    ├─ 新規/更新ファイルを検出
    ├─ ループごとに指標を計算
    ├─ 全体統合指標を計算
    └─ metrics.csv生成
```

**処理フロー**:
1. result.csvを検出
2. LoopIDでデータを分割
3. 各ループの性能指標を計算
4. 全体統合指標を計算（複数ループの場合）
5. metrics.csvに保存

---

## 出力ファイル

### result.csv

**場所**: `shared/results/{EXP_ID}/result.csv`

**主な列**:

| 列名 | 説明 | 単位 |
|:---|:---|:---|
| `Time` | シミュレーション時刻 | 秒 |
| `Step` | ステップ番号 | - |
| `LoopID` | ループ識別子 | - |
| `Pressure` | 観測圧力 | m |
| `Flow` | 観測流量 | m³/h |
| `ControlMode` | 制御モード | - |
| `ControlledValue` | 制御対象値 | m または m³/h |
| `TargetValue` | 目標値 | m または m³/h |
| `ValveSetting` | 現在のバルブ開度 | 0.0〜1.0 |
| `NewValveSetting` | 次のバルブ開度 | 0.0〜1.0 |
| `Error` | 制御誤差 | m または m³/h |

**PID/MPC追加列**:
- `PID_P`, `PID_I`, `PID_D` - PID各項
- `DeltaAction` - バルブ変化量

**確認コマンド**:
```bash
# 最初の5行
head -5 shared/results/exp_001/result.csv

# 最後の5行
tail -5 shared/results/exp_001/result.csv

# 特定の列のみ
cut -d',' -f1,4,5,8 shared/results/exp_001/result.csv | head -10
```

---

### metrics.csv

**場所**: `shared/results/{EXP_ID}/metrics.csv`

**構造**:
- 単一ループ: 1行（そのループの指標）
- 複数ループ: N+1行（各ループ + 全体統合）

**主な列**:

| カテゴリ | 列名 | 説明 |
|:---|:---|:---|
| **基本情報** | `SourceFile` | 元ファイル名 |
|  | `ProcessedAt` | 処理日時 |
|  | `LoopID` | ループID |
|  | `ControlMode` | 制御モード |
|  | `DurationSec` | シミュレーション時間 |
|  | `NumLoops` | ループ数（全体のみ） |
| **制御精度** | `MAE` | 平均絶対誤差 |
|  | `RMSE` | 二乗平均平方根誤差 |
|  | `MaxError` | 最大誤差 |
|  | `IAE` | 積分絶対誤差 |
|  | `ISE` | 積分二乗誤差 |
| **定常性能** | `SteadyMAE` | 定常状態MAE |
|  | `SteadyRMSE` | 定常状態RMSE |
| **制御努力** | `TotalVariation` | バルブ総変動量 |
|  | `MeanValve` | 平均バルブ開度 |
| **システム状態** | `MeanPressure` | 平均圧力 |
|  | `MeanFlow` | 平均流量 |

**確認コマンド**:
```bash
# 全体表示
cat shared/results/exp_001/metrics.csv

# 見やすく表示
column -t -s',' shared/results/exp_001/metrics.csv | less -S
```

---

### training_episodes.csv（VLAのみ）

**場所**: `shared/results/{EXP_ID}/training_episodes.csv`

**主な列**:

| 列名 | 説明 |
|:---|:---|
| `timestamp` | タイムスタンプ |
| `episode` | エピソード番号 |
| `total_steps` | 総ステップ数 |
| `episode_steps` | エピソードステップ数 |
| `episode_reward` | エピソード累積報酬 |
| `mean_reward` | 平均報酬 |
| `mean_actor_loss` | 平均Actor損失 |
| `mean_critic_loss` | 平均Critic損失 |
| `mean_q_value` | 平均Q値 |
| `buffer_size` | リプレイバッファサイズ |
| `mae` | 平均絶対誤差 |
| `rmse` | 二乗平均平方根誤差 |
| `max_error` | 最大誤差 |
| `mean_valve_change` | 平均バルブ変化量 |

---

## 評価指標

### 制御精度指標

#### MAE (Mean Absolute Error)

**定義**:
```
MAE = (1/n) Σ |e(t)|
```

**説明**:
- 平均絶対誤差
- すべての誤差を等しく重視
- 直感的に理解しやすい

**評価基準**:
- **0〜2m**: 優秀
- **2〜5m**: 良好
- **5〜10m**: 許容範囲
- **10m以上**: 要改善

**例**:
```
目標: 120m
実測: [118, 122, 119, 121, 120]
誤差: [2, 2, 1, 1, 0]
MAE = (2+2+1+1+0)/5 = 1.2m  → 優秀
```

---

#### RMSE (Root Mean Square Error)

**定義**:
```
RMSE = sqrt((1/n) Σ e(t)²)
```

**説明**:
- 二乗平均平方根誤差
- 大きな誤差をより重視
- MAEより敏感

**評価基準**:
- **0〜3m**: 優秀
- **3〜8m**: 良好
- **8〜15m**: 許容範囲
- **15m以上**: 要改善

**MAEとの比較**:
```
ケース1: 誤差 = [1, 1, 1, 1, 1]
  MAE = 1.0
  RMSE = 1.0
  → 一定の小さな誤差

ケース2: 誤差 = [0, 0, 0, 0, 5]
  MAE = 1.0
  RMSE = 2.24
  → RMSE > MAE は大きな誤差の存在を示唆
```

---

#### MaxError

**定義**:
```
MaxError = max(|e(t)|)
```

**説明**:
- 最大絶対誤差
- 最悪ケースの性能
- 安全性評価に重要

**評価基準**:
- **0〜5m**: 優秀
- **5〜15m**: 良好
- **15〜30m**: 許容範囲
- **30m以上**: 要改善

---

### 累積誤差指標

#### IAE (Integral Absolute Error)

**定義**:
```
IAE = ∫ |e(t)| dt
```

**説明**:
- 積分絶対誤差
- 時間軸での累積誤差
- 長期的な追従性能

**評価**:
- **低いほど良好**
- 制御の総合的な精度を表す
- MAEとシミュレーション時間の積に近い

---

#### ISE (Integral Square Error)

**定義**:
```
ISE = ∫ e(t)² dt
```

**説明**:
- 積分二乗誤差
- 大きな誤差を重視した累積指標
- 最適制御の目的関数としても使用

**評価**:
- **低いほど良好**
- RMSEとシミュレーション時間の積の二乗に近い

---

### 定常状態性能

#### SteadyMAE / SteadyRMSE

**定義**:
```
後半50%のデータでMAE/RMSEを計算
```

**説明**:
- 定常状態での制御精度
- 過渡応答を除外
- 長期的な安定性

**評価**:
- **SteadyMAE < MAE**: 定常状態で改善
- **SteadyMAE ≈ MAE**: 一貫した性能
- **SteadyMAE > MAE**: 定常状態で悪化（要注意）

**例**:
```
MAE = 3.5m
SteadyMAE = 2.1m  → 定常状態で改善（良好）
```

---

### 制御努力指標

#### TotalVariation

**定義**:
```
TotalVariation = Σ |Δu(t)|
```

**説明**:
- バルブ開度変化の総和
- アクチュエータの摩耗に直結
- 省エネルギー性能

**評価基準**:

| 値 | 評価 | バルブへの影響 |
|---:|:---|:---|
| 0〜0.5 | 非常に滑らか | 摩耗最小 |
| 0.5〜2.0 | 滑らか | 摩耗少 |
| 2.0〜5.0 | やや頻繁 | 摩耗中 |
| 5.0以上 | 頻繁 | 摩耗大（要注意） |

**例**:
```
144ステップで TotalVariation = 1.5
→ 平均変化量 = 1.5/144 ≈ 0.01 (1%)
→ 滑らかな制御
```

---

#### MeanValve

**定義**:
```
MeanValve = (1/n) Σ u(t)
```

**説明**:
- 平均バルブ開度
- 操作範囲の利用状況
- 調整余地の指標

**評価基準**:

| 値 | 評価 | 調整余地 |
|:---:|:---|:---|
| 0.0〜0.2 | ほぼ閉 | 開方向のみ |
| 0.2〜0.4 | やや閉 | 開方向優位 |
| 0.4〜0.6 | 中立 | 両方向に余裕（理想） |
| 0.6〜0.8 | やや開 | 閉方向優位 |
| 0.8〜1.0 | ほぼ開 | 閉方向のみ |

---

## コントローラー比較

### 典型的な性能プロファイル

**Net1ネットワーク、目標圧力120m、144ステップ**

| 指標 | PID | MPC | VLA (学習後) |
|:---|---:|---:|---:|
| **MAE** | 2.5 | 1.8 | 2.2 |
| **RMSE** | 3.8 | 2.9 | 3.2 |
| **MaxError** | 15.2 | 12.4 | 18.5 |
| **IAE** | 360 | 259 | 317 |
| **SteadyMAE** | 1.9 | 1.3 | 1.7 |
| **TotalVariation** | 0.15 | 0.08 | 0.12 |
| **MeanValve** | 0.52 | 0.49 | 0.51 |

### 特性比較

| 特性 | PID | MPC | VLA |
|:---|:---:|:---:|:---:|
| **初期性能** | 中 | 高 | 低 |
| **定常性能** | 中 | 高 | 高 |
| **滑らかさ** | 中 | 高 | 中 |
| **ロバスト性** | 高 | 中 | 中〜高 |
| **学習能力** | なし | なし | あり |

---

## 可視化

### Pythonでの可視化

```python
import pandas as pd
import matplotlib.pyplot as plt

# metrics.csvを読み込み
df_metrics = pd.read_csv('shared/results/exp_001/metrics.csv')

# 複数ループの場合、ループごとに表示
if 'LoopID' in df_metrics.columns:
    loops = df_metrics[df_metrics['LoopID'] != 'ALL']
    
    # MAE比較
    plt.figure(figsize=(10, 6))
    plt.bar(loops['LoopID'], loops['MAE'])
    plt.xlabel('Loop ID')
    plt.ylabel('MAE (m)')
    plt.title('Control Accuracy Comparison')
    plt.grid(True)
    plt.savefig('mae_comparison.png')
    
    # RMSE比較
    plt.figure(figsize=(10, 6))
    plt.bar(loops['LoopID'], loops['RMSE'])
    plt.xlabel('Loop ID')
    plt.ylabel('RMSE (m)')
    plt.title('Control Precision Comparison')
    plt.grid(True)
    plt.savefig('rmse_comparison.png')
    
    # TotalVariation比較
    plt.figure(figsize=(10, 6))
    plt.bar(loops['LoopID'], loops['TotalVariation'])
    plt.xlabel('Loop ID')
    plt.ylabel('Total Variation')
    plt.title('Control Effort Comparison')
    plt.grid(True)
    plt.savefig('total_variation_comparison.png')
```

---

### 複数コントローラー比較

```python
import pandas as pd
import matplotlib.pyplot as plt
import numpy as np

# 各コントローラーのmetricsを読み込み
df_pid = pd.read_csv('shared/results/exp_pid_001/metrics.csv')
df_mpc = pd.read_csv('shared/results/exp_mpc_001/metrics.csv')
df_vla = pd.read_csv('shared/results/exp_vla_001/metrics.csv')

# 指標を抽出
metrics_names = ['MAE', 'RMSE', 'MaxError', 'TotalVariation']
controllers = ['PID', 'MPC', 'VLA']

data = {
    'PID': [df_pid[m].iloc[0] for m in metrics_names],
    'MPC': [df_mpc[m].iloc[0] for m in metrics_names],
    'VLA': [df_vla[m].iloc[0] for m in metrics_names]
}

# グラフ作成
x = np.arange(len(metrics_names))
width = 0.25

fig, ax = plt.subplots(figsize=(12, 6))
ax.bar(x - width, data['PID'], width, label='PID')
ax.bar(x, data['MPC'], width, label='MPC')
ax.bar(x + width, data['VLA'], width, label='VLA')

ax.set_xlabel('Metrics')
ax.set_ylabel('Value')
ax.set_title('Controller Performance Comparison')
ax.set_xticks(x)
ax.set_xticklabels(metrics_names)
ax.legend()
ax.grid(True, axis='y')

plt.tight_layout()
plt.savefig('controller_comparison.png')
```

---

### レーダーチャート

```python
import matplotlib.pyplot as plt
import numpy as np

# 指標を正規化（0-1スケール、低いほど良い指標は反転）
def normalize_metrics(df):
    return {
        'Accuracy': 1 - min(df['MAE'].iloc[0] / 10, 1),  # 10m基準
        'Precision': 1 - min(df['RMSE'].iloc[0] / 15, 1),  # 15m基準
        'Stability': 1 - min(df['MaxError'].iloc[0] / 30, 1),  # 30m基準
        'Smoothness': 1 - min(df['TotalVariation'].iloc[0] / 5, 1),  # 5基準
        'Steady State': 1 - min(df['SteadyMAE'].iloc[0] / 5, 1)  # 5m基準
    }

# 各コントローラーのスコア
scores_pid = normalize_metrics(df_pid)
scores_mpc = normalize_metrics(df_mpc)
scores_vla = normalize_metrics(df_vla)

# レーダーチャート
categories = list(scores_pid.keys())
N = len(categories)

angles = [n / float(N) * 2 * np.pi for n in range(N)]
angles += angles[:1]

fig, ax = plt.subplots(figsize=(8, 8), subplot_kw=dict(projection='polar'))

# PID
values_pid = list(scores_pid.values())
values_pid += values_pid[:1]
ax.plot(angles, values_pid, 'o-', linewidth=2, label='PID')
ax.fill(angles, values_pid, alpha=0.25)

# MPC
values_mpc = list(scores_mpc.values())
values_mpc += values_mpc[:1]
ax.plot(angles, values_mpc, 'o-', linewidth=2, label='MPC')
ax.fill(angles, values_mpc, alpha=0.25)

# VLA
values_vla = list(scores_vla.values())
values_vla += values_vla[:1]
ax.plot(angles, values_vla, 'o-', linewidth=2, label='VLA')
ax.fill(angles, values_vla, alpha=0.25)

ax.set_xticks(angles[:-1])
ax.set_xticklabels(categories)
ax.set_ylim(0, 1)
ax.set_title('Controller Performance Profile', size=16, pad=20)
ax.legend(loc='upper right', bbox_to_anchor=(1.3, 1.1))
ax.grid(True)

plt.tight_layout()
plt.savefig('radar_chart.png')
```

---

## 次のステップ

- [可視化ガイド](VISUALIZATION.md)でダッシュボードの使い方を学習
- [CONTROLLERS.md](CONTROLLERS.md)で各コントローラーの調整方法を確認
- 実験を実行してメトリクスを比較