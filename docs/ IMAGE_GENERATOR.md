# Image Generator - 生成画像の完全ガイド

## 📋 目次

1. [概要](#概要)
2. [ファイル命名規則](#-ファイル命名規則)
3. [Visual-First画像（VLA学習用・推奨）](#-visual-first画像vla学習用推奨)
4. [Advanced画像（実験用）](#-advanced画像実験用)
5. [Legacy画像（互換性用）](#-legacy画像互換性用)
6. [画像の選択方法](#-画像の選択方法)
7. [ストレージ使用量](#-ストレージ使用量)

---

## 概要

image-generatorサービスは、水道ネットワークの状態を**14種類の視覚表現**として出力します。

### 画像のカテゴリ

| カテゴリ | 画像数 | 説明 | 推奨度 |
|:---|:---:|:---|:---:|
| **Visual-First** | 4種類 | 文字なし・VLA学習用 | ⭐⭐⭐⭐⭐ |
| **Advanced** | 6種類 | 高度な可視化・実験用 | ⭐⭐⭐ |
| **Legacy** | 4種類 | 文字あり・互換性用 | ⭐⭐ |

---

## 📁 ファイル命名規則

### 基本形式

```
step_{STEP:04d}_{IMAGE_TYPE}.png
```

- `step_`: 固定プレフィックス
- `{STEP:04d}`: 4桁のステップ番号（0埋め）
- `{IMAGE_TYPE}`: 画像タイプ名（下記参照）
- `.png`: PNG形式（256x256ピクセル、RGB）

### 保存先

```
shared/training_data/{EXP_ID}/images/
```

**例**: `shared/training_data/simplednn_correct_001/images/`

---

## 🎨 Visual-First画像（VLA学習用・推奨）

**特徴**: 文字情報を完全に排除し、色・形状・位置のみで表現。CNNが自然にパターンを学習できる。

### 1. Network State Map（ネットワーク状態マップ）

**ファイル名**: `step_{STEP:04d}_network_state_map.png`

**例**: 
- `step_0000_network_state_map.png`
- `step_0010_network_state_map.png`
- `step_0100_network_state_map.png`

**説明**:
ネットワーク全体の**空間的な状態**を一目で把握する画像。

**表現内容**:
- **ノード（円）**: 各ジャンクション
  - 色：圧力ヒートマップ（viridis）
    - 青（低圧 20m）→ 緑（中圧 35m）→ 黄（高圧 50m）
  - サイズ：ノードの重要度
- **エッジ（線）**: パイプ接続
  - 太さ：流量（0.5-3.0）
  - 色：灰色
- **制御ノード**: 赤い輪郭で強調
- **バルブ開度**: マゼンタの円（サイズ=開度）

**VLAが学習する内容**:
- ネットワークトポロジー（構造）
- 圧力分布のパターン
- 流量分布
- 制御点の位置
- 現在のバルブ状態

**見方**:
```
青が多い   → 全体的に低圧（バルブを開く）
緑が多い   → 適切な圧力
黄色が多い → 全体的に高圧（バルブを閉じる）
太い線     → 大量の水が流れている
```

**典型的なサイズ**: 20-30 KB

---

### 2. Temporal Slice（時空間スライス）

**ファイル名**: `step_{STEP:04d}_temporal_slice.png`

**例**:
- `step_0000_temporal_slice.png`
- `step_0010_temporal_slice.png`
- `step_0100_temporal_slice.png`

**説明**:
時間的な変化パターンを時空間図として可視化。

**表現内容**:
- **横軸**: 時間（過去30ステップ）
  - 左：過去、右：現在
- **縦軸**: ネットワークノード（空間）
- **色**: 圧力ヒートマップ（viridis）

**VLAが学習する内容**:
- 圧力の時間変化（トレンド）
- 波の伝播パターン
- 周期的な変動
- 突発的な変化
- 過去の制御の影響

**見方**:
```
横方向の縞模様 → 圧力が時間変化している
縦方向の縞模様 → 特定ノードだけ変化
斜めの縞模様   → 波が伝播している
```

**CNNの学習**:
- 横方向の畳み込み：時間的パターン
- 縦方向の畳み込み：空間的パターン
- 斜め方向：時空間カップリング

**典型的なサイズ**: 15-25 KB

---

### 3. Phase Space（位相空間プロット）

**ファイル名**: `step_{STEP:04d}_phase_space.png`

**例**:
- `step_0000_phase_space.png`
- `step_0010_phase_space.png`
- `step_0100_phase_space.png`

**説明**:
制御動態をPD制御的な位相空間で表現。

**表現内容**:
- **横軸**: 制御誤差（target - actual）
  - 左：負の誤差（圧力高すぎ）
  - 右：正の誤差（圧力低すぎ）
- **縦軸**: 誤差の微分（変化率）
  - 上：誤差増加中
  - 下：誤差減少中
- **現在点**: バルブ開度で色分け（RdYlGn）
  - 赤：バルブ閉
  - 緑：バルブ開
- **軌跡**: 過去10ステップ（フェード）
- **ゴール**: 原点（0,0）に金色の星

**VLAが学習する内容**:
- PD制御的な動態
- 目標への収束パターン
- オーバーシュート/アンダーシュート
- 振動の有無
- 制御の安定性

**見方**:
```
原点付近         → 制御成功
右上（第1象限）  → 低圧で下降中（危険）
左下（第3象限）  → 高圧で上昇中（危険）
右下（第4象限）  → 低圧だが回復中（良い）
左上（第2象限）  → 高圧だが下降中（良い）
```

**典型的なサイズ**: 10-20 KB

---

### 4. Multiscale Change（マルチスケール変化マップ）

**ファイル名**: `step_{STEP:04d}_multiscale_change.png`

**例**:
- `step_0000_multiscale_change.png`
- `step_0010_multiscale_change.png`
- `step_0100_multiscale_change.png`

**説明**:
複数の時間スケールの変化をRGBチャンネルで同時に表現。

**表現内容**:
- **Rチャンネル**: 短期変化（3ステップ = 30分）
- **Gチャンネル**: 中期変化（10ステップ = 100分）
- **Bチャンネル**: 長期変化（30ステップ = 300分）
- **レイアウト**: グリッド配置でノードを表示

**VLAが学習する内容**:
- 短期・中期・長期の変化の違い
- どの時間スケールに注目すべきか
- 急激な変化 vs 緩やかな変化
- ノードごとの変化の違い

**色の意味**:
```
赤が強い   → 短期的に急変
緑が強い   → 中期的に変化（トレンド）
青が強い   → 長期的に変化（季節変動）
白っぽい   → 全時間スケールで変化（不安定）
黒っぽい   → 全時間スケールで安定（理想）
```

**典型的なサイズ**: 25-35 KB

---

## 🔬 Advanced画像（実験用）

**特徴**: より高度な可視化手法。研究・実験用。

### 5. Flow Vector Field（フローベクトル場）

**ファイル名**: `step_{STEP:04d}_flow_vector_field.png`

**例**:
- `step_0000_flow_vector_field.png`
- `step_0010_flow_vector_field.png`

**説明**:
圧力と流量を組み合わせたベクトル場表現。

**表現内容**:
- **背景**: 圧力の補間フィールド（contourf）
- **前景**: 流量方向の白い矢印
- **矢印の太さ**: 流量の大きさ

**VLAが学習する内容**:
- 流れの方向と強度
- 圧力場と流量場の関係
- ソース/シンクの位置

**典型的なサイズ**: 30-40 KB

---

### 6. Energy Landscape（エネルギー地形図）

**ファイル名**: `step_{STEP:04d}_energy_landscape.png`

**例**:
- `step_0000_energy_landscape.png`
- `step_0010_energy_landscape.png`

**説明**:
圧力と位置エネルギーを地形図として可視化。

**表現内容**:
- **colormap**: terrain（地形図風）
- **高さ**: 圧力 + 位置エネルギー
- **等高線**: エネルギー等値線

**VLAが学習する内容**:
- エネルギー地形のポテンシャル
- 安定点/不安定点
- エネルギー勾配

**典型的なサイズ**: 25-35 KB

---

### 7. Pressure Gradient（圧力勾配ベクトル）

**ファイル名**: `step_{STEP:04d}_pressure_gradient.png`

**例**:
- `step_0000_pressure_gradient.png`
- `step_0010_pressure_gradient.png`

**説明**:
圧力勾配を矢印で表現。

**表現内容**:
- **背景**: 圧力ヒートマップ
- **矢印**: 高圧→低圧の方向
- **矢印の長さ**: 勾配の大きさ

**VLAが学習する内容**:
- 圧力勾配の方向と強度
- 流れの駆動力
- 圧力損失の分布

**典型的なサイズ**: 20-30 KB

---

### 8. HSV Encoding（HSV色空間エンコーディング）

**ファイル名**: `step_{STEP:04d}_hsv_encoding.png`

**例**:
- `step_0000_hsv_encoding.png`
- `step_0010_hsv_encoding.png`

**説明**:
圧力・流量・変化率をHSV色空間で統合表現。

**表現内容**:
- **Hue（色相）**: 圧力（0-360度）
- **Saturation（彩度）**: 流量（0-1）
- **Value（明度）**: 変化率（0-1）

**VLAが学習する内容**:
- 3つの状態変数の同時理解
- 色空間での関係性
- 統合的な状態認識

**典型的なサイズ**: 25-35 KB

---

### 9. Optical Flow（オプティカルフロー風）

**ファイル名**: `step_{STEP:04d}_optical_flow.png`

**例**:
- `step_0000_optical_flow.png`
- `step_0010_optical_flow.png`

**説明**:
圧力変化を動きベクトルとして表現。

**表現内容**:
- **背景**: 現在の圧力
- **矢印**: 圧力変化の方向と大きさ
- **色**: 変化の速度

**VLAが学習する内容**:
- 圧力の動的な変化
- 変化の伝播速度
- 動的システムの挙動

**典型的なサイズ**: 20-30 KB

---

### 10. Attention Map（注目領域マップ）

**ファイル名**: `step_{STEP:04d}_attention_map.png`

**例**:
- `step_0000_attention_map.png`
- `step_0010_attention_map.png`

**説明**:
誤差ベースのガウシアン注目マップ。

**表現内容**:
- **背景**: ネットワーク構造
- **前景**: 誤差の大きいノードにガウシアンハイライト
- **強度**: 誤差の大きさ

**VLAが学習する内容**:
- どのノードに注目すべきか
- 重要度の分布
- Attention機構のヒント

**典型的なサイズ**: 15-25 KB

---

## 📚 Legacy画像（互換性用）

**特徴**: 文字情報あり。人間が読むための画像。VLA学習には非推奨。

### 11. System UI（システムUI）

**ファイル名**: `step_{STEP:04d}_system_ui.png`

**例**:
- `step_0000_system_ui.png`
- `step_0010_system_ui.png`

**説明**:
ネットワーク図にテキストラベルを追加した人間向けUI。

**表現内容**:
- ノード名（テキスト）
- 圧力値（テキスト）
- 流量値（テキスト）
- バルブ開度（テキスト）

**用途**: デバッグ、プレゼンテーション

**典型的なサイズ**: 30-40 KB

---

### 12. Valve Detail（バルブ詳細）

**ファイル名**: `step_{STEP:04d}_valve_detail.png`

**例**:
- `step_0000_valve_detail.png`
- `step_0010_valve_detail.png`

**説明**:
バルブの状態をゲージで表示。

**表現内容**:
- バルブ開度ゲージ（数値表示）
- 圧力ゲージ（数値表示）
- ステータステキスト

**用途**: モニタリング、レポート

**典型的なサイズ**: 15-25 KB

---

### 13. Flow Dashboard（フローダッシュボード）

**ファイル名**: `step_{STEP:04d}_flow_dashboard.png`

**例**:
- `step_0000_flow_dashboard.png`
- `step_0010_flow_dashboard.png`

**説明**:
流量履歴をグラフで表示。

**表現内容**:
- 時系列グラフ（軸ラベル付き）
- 凡例（テキスト）
- 数値表示

**用途**: トレンド分析、レポート

**典型的なサイズ**: 20-30 KB

---

### 14. Comparison（前後比較）

**ファイル名**: `step_{STEP:04d}_comparison.png`

**例**:
- `step_0000_comparison.png`
- `step_0010_comparison.png`

**説明**:
前ステップとの比較を並べて表示。

**表現内容**:
- 左：前ステップ
- 右：現ステップ
- 差分表示（テキスト）

**用途**: 変化の可視化、分析

**典型的なサイズ**: 40-50 KB

---

## 🎯 画像の選択方法

### 推奨設定（VLA学習用）

```bash
# .env
ENABLED_GENERATORS=network_state_map,temporal_slice,phase_space,multiscale_change
```

**理由**:
- 文字情報なし
- 空間・時間・動態・マルチスケールをカバー
- CNNが自然に学習可能

**ファイル数（間隔10）**: 15ステップ × 4種類 = **60枚**
**サイズ**: 約6 MB/エピソード

---

### 実験用設定（全Visual-First + Advanced）

```bash
# .env
ENABLED_GENERATORS=network_state_map,temporal_slice,phase_space,multiscale_change,flow_vector_field,energy_landscape,pressure_gradient,hsv_encoding,optical_flow,attention_map
```

**ファイル数（間隔10）**: 15ステップ × 10種類 = **150枚**
**サイズ**: 約15 MB/エピソード

---

### デバッグ用設定（Legacy含む）

```bash
# .env
ENABLED_GENERATORS=network_state_map,phase_space,system_ui,valve_detail
```

**ファイル数（間隔10）**: 15ステップ × 4種類 = **60枚**
**サイズ**: 約7 MB/エピソード

---

### 最小構成（Phase Spaceのみ）

```bash
# .env
ENABLED_GENERATORS=phase_space
```

**ファイル数（間隔10）**: 15ステップ × 1種類 = **15枚**
**サイズ**: 約0.3 MB/エピソード

---

## 💾 ストレージ使用量

### 1エピソード（144ステップ、間隔10）

| 設定 | 画像数 | サイズ |
|:---|:---:|:---:|
| Visual-First (4種) | 60枚 | 6 MB |
| Visual + Advanced (10種) | 150枚 | 15 MB |
| 全種類 (14種) | 210枚 | 20 MB |
| Phase Spaceのみ (1種) | 15枚 | 0.3 MB |

### 10エピソード

| 設定 | 画像数 | サイズ |
|:---|:---:|:---:|
| Visual-First (4種) | 600枚 | 60 MB |
| Visual + Advanced (10種) | 1500枚 | 150 MB |
| 全種類 (14種) | 2100枚 | 200 MB |
| Phase Spaceのみ (1種) | 150枚 | 3 MB |

### 100エピソード

| 設定 | 画像数 | サイズ |
|:---|:---:|:---:|
| Visual-First (4種) | 6000枚 | 600 MB |
| Visual + Advanced (10種) | 15000枚 | 1.5 GB |
| 全種類 (14種) | 21000枚 | 2 GB |
| Phase Spaceのみ (1種) | 1500枚 | 30 MB |

---

## 📊 画像一覧表

### Visual-First（VLA学習用・推奨）

| # | 画像タイプ | ファイル名 | 説明 | サイズ |
|:---:|:---|:---|:---|:---:|
| 1 | network_state_map | `step_XXXX_network_state_map.png` | 空間的状態 | 20-30KB |
| 2 | temporal_slice | `step_XXXX_temporal_slice.png` | 時間変化 | 15-25KB |
| 3 | phase_space | `step_XXXX_phase_space.png` | 制御動態 | 10-20KB |
| 4 | multiscale_change | `step_XXXX_multiscale_change.png` | マルチスケール | 25-35KB |

### Advanced（実験用）

| # | 画像タイプ | ファイル名 | 説明 | サイズ |
|:---:|:---|:---|:---|:---:|
| 5 | flow_vector_field | `step_XXXX_flow_vector_field.png` | ベクトル場 | 30-40KB |
| 6 | energy_landscape | `step_XXXX_energy_landscape.png` | エネルギー地形 | 25-35KB |
| 7 | pressure_gradient | `step_XXXX_pressure_gradient.png` | 圧力勾配 | 20-30KB |
| 8 | hsv_encoding | `step_XXXX_hsv_encoding.png` | HSV統合 | 25-35KB |
| 9 | optical_flow | `step_XXXX_optical_flow.png` | 動きベクトル | 20-30KB |
| 10 | attention_map | `step_XXXX_attention_map.png` | 注目領域 | 15-25KB |

### Legacy（互換性用）

| # | 画像タイプ | ファイル名 | 説明 | サイズ |
|:---:|:---|:---|:---|:---:|
| 11 | system_ui | `step_XXXX_system_ui.png` | システムUI | 30-40KB |
| 12 | valve_detail | `step_XXXX_valve_detail.png` | バルブ詳細 | 15-25KB |
| 13 | flow_dashboard | `step_XXXX_flow_dashboard.png` | ダッシュボード | 20-30KB |
| 14 | comparison | `step_XXXX_comparison.png` | 前後比較 | 40-50KB |

---

## 🚀 クイックスタート

### 1. Visual-First画像のみ生成（推奨）

```bash
# .env
ENABLED_GENERATORS=network_state_map,temporal_slice,phase_space,multiscale_change
IMAGE_SAVE_INTERVAL=10
SAVE_IMAGES=true

# 実行
./run_multiepisode.sh 1

# 確認
ls shared/training_data/simplednn_correct_001/images/
# 出力例:
# step_0000_multiscale_change.png
# step_0000_network_state_map.png
# step_0000_phase_space.png
# step_0000_temporal_slice.png
# ...
```

### 2. すべての画像を生成

```bash
# .env
ENABLED_GENERATORS=network_state_map,temporal_slice,phase_space,multiscale_change,flow_vector_field,energy_landscape,pressure_gradient,hsv_encoding,optical_flow,attention_map,system_ui,valve_detail,flow_dashboard,comparison

# 実行
./run_multiepisode.sh 1

# 確認
ls shared/training_data/simplednn_correct_001/images/ | wc -l
# 出力: 210枚（15ステップ × 14種類）
```

### 3. Phase Spaceのみ生成

```bash
# .env
ENABLED_GENERATORS=phase_space
IMAGE_SAVE_INTERVAL=1

# 実行
./run_multiepisode.sh 1

# 確認
ls shared/training_data/simplednn_correct_001/images/*_phase_space.png | wc -l
# 出力: 145枚（全ステップ）
```

---

## 🎨 まとめ

image-generatorは**14種類**の画像を生成可能：

- **Visual-First（4種）**: VLA学習に最適
- **Advanced（6種）**: 高度な分析・実験用
- **Legacy（4種）**: 人間向け・互換性用

**推奨設定**: Visual-First 4種
**ファイル名**: `step_{STEP:04d}_{IMAGE_TYPE}.png`
**保存先**: `shared/training_data/{EXP_ID}/images/`

これにより、VLAモデルは視覚的なパターンから制御を学習できます。