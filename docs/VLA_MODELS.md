# VLAモデル実装ガイド

各 VLA モデルのアーキテクチャ・学習戦略・使用方法の詳細。

---

## 目次

1. [モデル一覧](#モデル一覧)
2. [OpenVLA](#openvla)
3. [SmolVLA](#smolvla)
4. [TinyVLA](#tinyvla)
5. [SimpleDNN](#simplednn)
6. [チェックポイントの扱い](#チェックポイントの扱い)

---

## モデル一覧

| モデル | 規模 | VRAM | 事前学習重み | 実装状態 |
|--------|------|------|-------------|---------|
| `openvla` | ~8.3B | ~14GB (fp16) | `openvla/openvla-7b` | ✅ 実装済み |
| `smolvla` | ~450M | ~4GB | `lerobot/smolvla_base` | 🔧 実装中 |
| `tinyvla` | ~1.3B | ~6GB | LLaVA-Pythia (要確認) | 🔧 実装中 |
| `simple_dnn` | ~1M | <1GB | なし（ゼロ学習） | ✅ 実装済み |

---

## OpenVLA

### 概要

[OpenVLA (Kim et al., 2024)](https://arxiv.org/abs/2406.09246) のアーキテクチャを、水道ネットワークの単軸バルブ制御に適応した実装。

- 論文実装: https://github.com/openvla/openvla
- HuggingFace: `openvla/openvla-7b`

### アーキテクチャ

```
入力: 画像 (256×256) + テキストプロンプト
        │
        ▼
┌───────────────────────────────────────────────────────┐
│  vision_backbone                          【FROZEN】  │
│                                                       │
│  SigLIP ViT-So400m/14  ──┐                            │
│                           ├─ 特徴融合 → パッチトークン │
│  DINOv2 ViT-L/14       ──┘                            │
└───────────────────────────────────────────────────────┘
        │
        ▼
┌───────────────────────────────────────────────────────┐
│  projector (2-layer MLP)              【Full Train】  │
│  vision 特徴 → LLM embedding 空間へ射影               │
└───────────────────────────────────────────────────────┘
        │
        ▼ (テキストトークンと結合)
┌───────────────────────────────────────────────────────┐
│  language_model (Llama-2 7B)             【LoRA】    │
│                                                       │
│  全 linear 層に ΔW = B·A を注入 (rank=32)             │
│  q_proj, k_proj, v_proj, o_proj,                      │
│  gate_proj, up_proj, down_proj, ...                   │
│                                                       │
│  元の重みは変更されない                               │
└───────────────────────────────────────────────────────┘
        │ hidden_states[-1]  (最終層, 最後のトークン)
        ▼
┌───────────────────────────────────────────────────────┐
│  action_head                          【Full Train】  │
│                                                       │
│  Linear(4096 → 512) → GELU → Dropout(0.1)            │
│  Linear(512  → 128) → GELU → Dropout(0.1)            │
│  Linear(128  → 1)   → Tanh                           │
│                        × 0.05                         │
└───────────────────────────────────────────────────────┘
        │
        ▼
  Δvalve ∈ [-0.05, 0.05]
```

### 学習対象パラメータ

| コンポーネント | パラメータ数 | 学習 | 備考 |
|-------------|------------|------|------|
| Vision Backbone (SigLIP + DINOv2) | ~1.3B | ❌ 凍結 | `vision_backbone.*` |
| Projector (MLP) | ~30M | ✅ 全学習 | `projector.*` |
| Llama-2 7B 元重み | ~7B | ❌ 凍結 | |
| Llama-2 7B LoRA (rank=32) | ~42M | ✅ LoRA | 全体の ~0.6% |
| Action Head | ~2M | ✅ 全学習 | `action_head.*` |
| **学習対象 合計** | **~74M** | ✅ | 全体の ~0.9% |

### 設計の意図

| コンポーネント | 方針 | 理由 |
|-------------|------|------|
| Vision Backbone | 凍結 | SigLIP + DINOv2 は大規模データで事前学習済み。再学習すると壊滅的忘却のリスクがある |
| Projector | 全学習 | ネットワーク画像という新規ドメインの視覚特徴を LLM に渡す方法を学習する最重要箇所 |
| Llama-2 7B | LoRA | 言語理解はほぼ転移できるが、「圧力制御」ドメインへの微調整が必要。LoRA なら元の重みを保持したまま適応できる |
| Action Head | 全学習 | 原論文の 7-DoF ロボット制御出力をこのプロジェクトの 1 次元バルブ制御に完全に作り直す |

### チェックポイント形式

OpenVLA のチェックポイントは **ディレクトリ** として保存される（旧モデルの `.pt` ファイルとは異なる）。

```
checkpoints/
└── openvla_loop_1_latest/
    ├── adapter_config.json    ← LoRA 設定 (PEFT)
    ├── adapter_model.bin      ← LoRA 重み (PEFT)
    ├── action_head.pt         ← アクションヘッド state dict
    └── projector.pt           ← プロジェクター state dict
```

```python
# 保存
model.save_trainable_weights("checkpoints/openvla_loop_1_latest")

# ロード
model.load_trainable_weights("checkpoints/openvla_loop_1_latest")
```

### 必要ライブラリ

```bash
pip install transformers>=4.40.0 peft>=0.9.0 accelerate>=0.27.0
pip install sentencepiece protobuf
pip install bitsandbytes>=0.43.0   # 4-bit 量子化を使う場合
```

### VRAM 要件

| モード | VRAM | 備考 |
|--------|------|------|
| fp16 推論 | ~14GB | デフォルト |
| 4-bit 量子化 (NF4) | ~6GB | `use_4bit=True` |
| fp16 + LoRA 学習 | ~20GB | batch_size=1 |
| 4-bit + LoRA 学習 | ~10GB | bitsandbytes 必要 |

24GB VRAM 環境では fp16 + LoRA 学習が推奨。

### 使用方法

```bash
# docker-compose
VLA_MODEL=openvla docker-compose up --build
```

```python
# Python
from models import get_vla_model

model = get_vla_model('openvla')
action = model.predict(images, prompt)  # float: Δvalve
```

---

## SmolVLA

> 🔧 実装中

### 概要

[SmolVLA (HuggingFace, 2025)](https://huggingface.co/blog/smolvla) のアーキテクチャを適応予定。

- HuggingFace: `lerobot/smolvla_base`
- LeRobot ライブラリ: https://github.com/huggingface/lerobot

### アーキテクチャ（予定）

```
入力: 画像 + テキスト
        ↓
SmolVLM2-500M (SigLIP + SmolLM2-1.7B)
  前半レイヤーのみ使用 / PixelShuffle で視覚トークンを 64 に圧縮
  → Frozen または 軽量 LoRA
        ↓
Flow Matching Action Expert (~100M params)
  Cross-Attention (VLM 特徴 ↔ アクショントークン)
  Self-Attention  (時系列平滑化)
  → 1 次元連続アクション生成
        ↓
Δvalve ∈ [-0.05, 0.05]
```

| コンポーネント | パラメータ | 学習 |
|-------------|----------|------|
| SmolVLM2 backbone | ~350M | ❌ 凍結 |
| Flow Matching Expert | ~100M | ✅ 全学習 |

---

## TinyVLA

> 🔧 実装中

### 概要

[TinyVLA (Wen et al., 2024)](https://arxiv.org/abs/2409.12514) のアーキテクチャを適応予定。

- GitHub: https://github.com/liyaxuanliyaxuan/TinyVLA

### アーキテクチャ（予定）

```
入力: 画像 + テキスト
        ↓
LLaVA framework (CLIP ViT-L/14 + Pythia 400M〜1.3B)
  → Frozen または LoRA (5% パラメータのみ学習)
        ↓
Diffusion Policy Head (DDPM)
  ノイズ除去プロセスで滑らかな連続アクション生成
  → 1 次元出力
        ↓
Δvalve ∈ [-0.05, 0.05]
```

| コンポーネント | パラメータ | 学習 |
|-------------|----------|------|
| CLIP ViT-L/14 | ~307M | ❌ 凍結 |
| Pythia LLM | ~400M〜1.3B | LoRA |
| Diffusion Policy Head | ~50M | ✅ 全学習 |

---

## SimpleDNN

> ✅ 実装済み / 事前学習なし

シンプルな CNN + MLP によるベースライン実装。依存ライブラリ追加なし、即座に動作する。

```
[4 画像]
   ├── CNN(3→16→32→64) ──> AdaptiveAvgPool ──> 64 次元
   ├── CNN ...
   ├── CNN ...
   └── CNN ...           → Concat → 256 次元
                                │
[プロンプト] ──> 正規化 ──> 5 次元
                                │
                         Concat → 261 次元
                                │
                    MLP(261→128→64→1) + Tanh × 0.05
                                │
                    Δvalve ∈ [-0.05, 0.05]
```

---

## チェックポイントの扱い

### モデル別チェックポイント形式

| モデル | 形式 | パス例 |
|--------|------|--------|
| `simple_dnn` | `.pt` ファイル | `checkpoints/simple_dnn_loop_1_latest.pt` |
| `tinyvla` | `.pt` ファイル | `checkpoints/tinyvla_loop_1_latest.pt` |
| `openvla` | **ディレクトリ** | `checkpoints/openvla_loop_1_latest/` |
| `smolvla` | **ディレクトリ** (予定) | `checkpoints/smolvla_loop_1_latest/` |

### 環境変数での指定

```bash
# simple_dnn / tinyvla (.pt ファイル)
VLA_CHECKPOINT=/shared/results/exp_001/checkpoints/simple_dnn_loop_1_latest.pt

# openvla (ディレクトリ)
VLA_CHECKPOINT=/shared/results/exp_001/checkpoints/openvla_loop_1_latest
```

`VLA_AUTO_RESUME=true` の場合、`EXP_ID` に対応する最新チェックポイントが自動的にロードされる。

---

## 関連ドキュメント

- [VLAセットアップガイド](VLA_SETUP.md) — 起動手順・環境設定
- [設定リファレンス](CONFIGURATION.md) — ハイパーパラメータ一覧
- [メトリクス](METRICS.md) — 学習進捗の評価方法
