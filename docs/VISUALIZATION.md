# 可視化ガイド

Streamlitダッシュボードの使い方と各タブの詳細説明。

---

## 目次

1. [ダッシュボードの起動](#ダッシュボードの起動)
2. [Tab 1: Network 3D](#tab-1-network-3d)
3. [Tab 2: Control Performance](#tab-2-control-performance)
4. [Tab 3: Time Series](#tab-3-time-series)
5. [Tab 4: Metrics](#tab-4-metrics)
6. [カスタム可視化](#カスタム可視化)

---

## ダッシュボードの起動

### 起動方法

```bash
# visualizationサービスを起動
docker-compose up -d visualization

# ブラウザで開く
open http://localhost:8501
```

**または、全サービスと同時起動**:
```bash
docker-compose up --build
```

**アクセスURL**: http://localhost:8501

---

### データの選択

ダッシュボードの上部で実験を選択：

```
Select Experiment: [▼ exp_001    ]
                       exp_002
                       exp_pid_001
                       simplednn_001
                       ...
```

**選択すると自動的に**:
- result.csvを読み込み
- metrics.csvを読み込み（存在する場合）
- INPファイルを解析
- グラフを更新

---

## Tab 1: Network 3D

### 概要

EPANETネットワークの3D可視化。制御要素（センサー、アクチュエータ）を強調表示。

### 表示要素

#### ノード（接続点）

| 記号 | 色 | 説明 |
|:---|:---|:---|
| ⚪ 円 | 灰色 | ジャンクション（配管接続点） |
| 🟦 四角 | 青 | 貯水池（水源） |
| 🟦 四角 | シアン | タンク（貯水槽） |
| 🔴 ダイヤ | 赤 | **圧力センサー**（圧力制御時） |
| 🟣 ダイヤ | 紫 | **流量センサー**（流量制御時） |

#### リンク（配管）

| 記号 | 色 | 太さ | 説明 |
|:---|:---|:---|:---|
| ─ 線 | 灰色 | 細 | 通常のパイプ |
| ━ 線 | オレンジ | **太** | **制御バルブ**（アクチュエータ） |

---

### 操作方法

#### カメラコントロール

- **回転**: マウスドラッグ
- **ズーム**: マウスホイール
- **パン**: Shift + マウスドラッグ

#### 視点のリセット

ダッシュボード右上の🏠ボタンをクリック

---

### 情報表示

#### ネットワーク情報

```
Network Information:
├─ Total Nodes: 11
├─ Total Links: 13
├─ Junctions: 9
├─ Reservoirs: 1
└─ Tanks: 1
```

#### 制御ループ情報（複数ループの場合）

```
Control Loops:
├─ Loop 1:
│   ├─ Sensor Node: 2 (Pressure)
│   └─ Actuator Link: 10 (Valve)
└─ Loop 2:
    ├─ Sensor Node: 12 (Pressure)
    └─ Actuator Link: 12 (Valve)
```

---

### 使用例

#### 単一ループの確認

1. 赤いダイヤモンド（センサー）の位置を確認
2. 太いオレンジ線（バルブ）の位置を確認
3. 両者の接続関係を確認

#### 複数ループの確認

1. すべてのセンサー位置を確認
2. 各センサーに対応するバルブを確認
3. ループ間の物理的な距離を確認
4. 相互作用の可能性を評価

---

## Tab 2: Control Performance

### 概要

制御追従性能とシステム応答の詳細な時系列グラフ。

---

### ループ選択（複数ループの場合）

```
Select Loop: [▼ All Loops ]
                 loop_1
                 loop_2
                 loop_3
```

- **All Loops**: すべてのループを重ねて表示
- **個別選択**: 特定のループのみ表示

---

### グラフ1: Control Tracking

**表示内容**:
- 実線: 実測値（Pressure/Flow）
- 点線: 目標値（Target）

**Y軸**:
- 圧力制御: 圧力（m）
- 流量制御: 流量（m³/h）

**X軸**: 時間（秒）

**色分け**（複数ループ）:
- loop_1: 青
- loop_2: 赤
- loop_3: 緑

**評価**:
- ✅ 実線が点線に近い → 追従性良好
- ⚠️ 振動している → 不安定
- ❌ 大きく外れている → 追従性不良

---

### グラフ2: Valve Setting

**表示内容**:
- バルブ開度の時間変化

**Y軸**: バルブ開度（0.0〜1.0）

**X軸**: 時間（秒）

**評価**:
- ✅ 滑らかな曲線 → 制御が滑らか
- ⚠️ 細かい振動 → やや不安定
- ❌ 大きな振動 → 不安定、要調整

---

### グラフ3: System State

**表示内容**:
- 上段: 圧力の時間変化
- 下段: 流量の時間変化

**色分け**（複数ループ）:
各ループを異なる色で表示

**用途**:
- 圧力と流量の関係を確認
- ループ間の相互作用を確認
- システム全体の挙動を把握

---

### グラフ4: Control Error

**表示内容**:
- 制御誤差（Target - Actual）の時間変化

**Y軸**: 誤差（m または m³/h）

**X軸**: 時間（秒）

**基準線**:
- y=0（目標達成ライン）

**評価**:
- ✅ 0に近い → 高精度
- ⚠️ 振動している → 不安定
- ❌ 0から離れている → 追従性不良

---

### グラフ5: Controller Internal State（PID/MPCのみ）

**表示内容**:
- P項（比例項）
- I項（積分項）
- D項（微分項）

**用途**:
- どの項が支配的かを確認
- パラメータチューニングの参考
- 制御メカニズムの理解

**例**:
```
P項が大きい → 現在の誤差が大きい
I項が増加 → 定常偏差が蓄積している
D項が振動 → 誤差の変化が激しい
```

---

## Tab 3: Time Series

### 概要

カスタム時系列分析。任意の列を選択してグラフ化。

---

### ループフィルター（複数ループの場合）

```
Filter by Loop: [▼ All Loops ]
                    loop_1
                    loop_2
```

選択したループのデータのみを表示・プロット。

---

### カスタムプロット

#### 列の選択

```
Select columns to plot: [☑ Pressure      ]
                         [☑ Flow          ]
                         [☐ ValveSetting  ]
                         [☐ Error         ]
```

- 複数選択可能
- チェックボックスで選択/解除

#### グラフの生成

**Plot Selected Columns** ボタンをクリック

**表示**:
- 各列を異なる色で表示
- 複数ループの場合、さらに色分け
- 凡例で識別

---

### データテーブル

**生データの表示**:
- result.csvの全データをテーブル形式で表示
- スクロール可能
- ソート可能（列ヘッダークリック）

**用途**:
- 特定のステップの値を確認
- 異常値の検出
- 詳細な分析

---

### 使用例

#### 圧力と流量の関係分析

1. **列を選択**: Pressure, Flow
2. **プロット生成**
3. **観察**: 圧力が上がると流量がどう変化するか

#### バルブと圧力の関係

1. **列を選択**: ValveSetting, Pressure
2. **プロット生成**
3. **観察**: バルブ開度と圧力の応答関係

#### 誤差の詳細分析

1. **列を選択**: Error
2. **フィルター**: 特定のループ
3. **データテーブルで確認**: 最大誤差の発生時刻

---

## Tab 4: Metrics

### 概要

制御性能指標のサマリー表示と比較。

---

### 単一ループの場合

#### 全体サマリー

```
Control Performance Metrics
├─ Control Mode: pressure
├─ Target Value: 120.0 m
├─ Duration: 86400 s (24 hours)
└─ Number of Samples: 144
```

#### 精度指標

```
Accuracy Metrics:
├─ MAE (Mean Absolute Error): 2.5 m
├─ RMSE (Root Mean Square Error): 3.8 m
├─ Max Error: 15.2 m
├─ IAE (Integral Absolute Error): 360 m·s
└─ ISE (Integral Square Error): 1965 m²·s
```

#### 定常状態性能

```
Steady State Performance:
├─ Steady MAE: 1.9 m
└─ Steady RMSE: 2.8 m
```

#### 制御努力

```
Control Effort:
├─ Total Variation: 0.15
├─ Mean Valve Setting: 0.52
├─ Mean Pressure: 121.3 m
└─ Mean Flow: 152.7 m³/h
```

---

### 複数ループの場合

#### 全体統合指標

```
Overall Performance (All Loops):
├─ Number of Loops: 2
├─ Average MAE: 2.8 m
├─ Average RMSE: 4.2 m
├─ Max Error (all loops): 18.5 m
└─ Total Variation (sum): 0.27
```

#### 個別ループ指標テーブル

| Loop ID | MAE | RMSE | MaxError | TotalVariation | MeanValve |
|:---|---:|---:|---:|---:|---:|
| loop_1 | 2.5 | 3.8 | 15.2 | 0.15 | 0.52 |
| loop_2 | 3.1 | 4.6 | 18.5 | 0.12 | 0.48 |

#### ループ比較バーグラフ

4つの指標を横並び比較:
1. **MAE**: 平均絶対誤差
2. **RMSE**: 二乗平均平方根誤差
3. **TotalVariation**: バルブ総変動量
4. **SteadyMAE**: 定常状態MAE

**用途**:
- ループ間の性能差を可視化
- 問題のあるループを特定
- パラメータ調整の優先順位決定

---

### VLA追加指標（VLAコントローラーのみ）

```
Learning Performance:
├─ Episode Reward: -575.16
├─ Mean Reward: -3.99
├─ Mean Critic Loss: 9.27
├─ Mean Actor Loss: 0.0
└─ Buffer Size: 144
```

---

## カスタム可視化

### Jupyter Notebookでの分析

```python
import pandas as pd
import matplotlib.pyplot as plt
import plotly.express as px

# データ読み込み
df = pd.read_csv('shared/results/exp_001/result.csv')

# インタラクティブな時系列グラフ
fig = px.line(df, x='Time', y=['Pressure', 'TargetPressure'],
              title='Control Performance')
fig.show()

# 誤差のヒストグラム
plt.figure(figsize=(10, 6))
plt.hist(df['Error'], bins=50, edgecolor='black')
plt.xlabel('Error (m)')
plt.ylabel('Frequency')
plt.title('Error Distribution')
plt.grid(True)
plt.show()

# バルブ変化のヒストグラム
valve_changes = df['NewValveSetting'].diff().abs()
plt.figure(figsize=(10, 6))
plt.hist(valve_changes.dropna(), bins=50, edgecolor='black')
plt.xlabel('Valve Change')
plt.ylabel('Frequency')
plt.title('Valve Change Distribution')
plt.grid(True)
plt.show()
```

---

### Plotlyでの3D可視化

```python
import plotly.graph_objects as go

# 時間 vs 圧力 vs 流量の3Dプロット
fig = go.Figure(data=[go.Scatter3d(
    x=df['Time'],
    y=df['Pressure'],
    z=df['Flow'],
    mode='markers',
    marker=dict(
        size=2,
        color=df['Error'],
        colorscale='Viridis',
        showscale=True,
        colorbar=dict(title="Error")
    )
)])

fig.update_layout(
    title='State Space Trajectory',
    scene=dict(
        xaxis_title='Time (s)',
        yaxis_title='Pressure (m)',
        zaxis_title='Flow (m³/h)'
    )
)

fig.show()
```

---

### コントローラー比較ダッシュボード

```python
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# 各コントローラーのデータ読み込み
df_pid = pd.read_csv('shared/results/exp_pid_001/result.csv')
df_mpc = pd.read_csv('shared/results/exp_mpc_001/result.csv')
df_vla = pd.read_csv('shared/results/exp_vla_001/result.csv')

# サブプロット作成
fig = make_subplots(
    rows=2, cols=2,
    subplot_titles=('Control Tracking', 'Control Error',
                    'Valve Setting', 'Metrics Comparison')
)

# Control Tracking
fig.add_trace(
    go.Scatter(x=df_pid['Time'], y=df_pid['Pressure'], name='PID'),
    row=1, col=1
)
fig.add_trace(
    go.Scatter(x=df_mpc['Time'], y=df_mpc['Pressure'], name='MPC'),
    row=1, col=1
)
fig.add_trace(
    go.Scatter(x=df_vla['Time'], y=df_vla['Pressure'], name='VLA'),
    row=1, col=1
)

# Control Error
fig.add_trace(
    go.Scatter(x=df_pid['Time'], y=df_pid['Error'], name='PID', showlegend=False),
    row=1, col=2
)
fig.add_trace(
    go.Scatter(x=df_mpc['Time'], y=df_mpc['Error'], name='MPC', showlegend=False),
    row=1, col=2
)
fig.add_trace(
    go.Scatter(x=df_vla['Time'], y=df_vla['Error'], name='VLA', showlegend=False),
    row=1, col=2
)

# Valve Setting
fig.add_trace(
    go.Scatter(x=df_pid['Time'], y=df_pid['ValveSetting'], name='PID', showlegend=False),
    row=2, col=1
)
fig.add_trace(
    go.Scatter(x=df_mpc['Time'], y=df_mpc['ValveSetting'], name='MPC', showlegend=False),
    row=2, col=1
)
fig.add_trace(
    go.Scatter(x=df_vla['Time'], y=df_vla['ValveSetting'], name='VLA', showlegend=False),
    row=2, col=1
)

# Metrics Comparison (バーグラフ)
metrics_pid = pd.read_csv('shared/results/exp_pid_001/metrics.csv')
metrics_mpc = pd.read_csv('shared/results/exp_mpc_001/metrics.csv')
metrics_vla = pd.read_csv('shared/results/exp_vla_001/metrics.csv')

fig.add_trace(
    go.Bar(name='PID', x=['MAE', 'RMSE'], 
           y=[metrics_pid['MAE'].iloc[0], metrics_pid['RMSE'].iloc[0]]),
    row=2, col=2
)
fig.add_trace(
    go.Bar(name='MPC', x=['MAE', 'RMSE'],
           y=[metrics_mpc['MAE'].iloc[0], metrics_mpc['RMSE'].iloc[0]]),
    row=2, col=2
)
fig.add_trace(
    go.Bar(name='VLA', x=['MAE', 'RMSE'],
           y=[metrics_vla['MAE'].iloc[0], metrics_vla['RMSE'].iloc[0]]),
    row=2, col=2
)

fig.update_layout(height=800, width=1200, title_text="Controller Comparison Dashboard")
fig.show()
```

---

## 次のステップ

- [メトリクス詳細](METRICS.md)で各指標の意味を理解
- [開発ガイド](DEVELOPMENT.md)で新しいタブの追加方法を学習
- 実験を実行して可視化を確認