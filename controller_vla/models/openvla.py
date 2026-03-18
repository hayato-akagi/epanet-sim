"""
OpenVLA - True OpenVLA Implementation
======================================
Based on: https://github.com/openvla/openvla
Paper: OpenVLA: An Open-Source Vision-Language-Action Model (Kim et al., 2024)
HuggingFace: openvla/openvla-7b

Architecture:
  - Vision Backbone : SigLIP ViT-So400m/14 + DINOv2 ViT-L/14 (fused)  → FROZEN
  - Projector       : 2-layer MLP (vision → LLM embedding space)         → Full train
  - Language Model  : Llama-2 7B                                          → LoRA (rank=32)
  - Action Head     : Custom regression head for Δvalve ∈ [-0.05, 0.05]  → Full train

Training strategy (per this project):
  Frozen   : vision_backbone.* (SigLIP + DINOv2 pretrained weights)
  LoRA     : language_model.* attention + FFN layers (target_modules="all-linear")
  Full     : projector.*, action_head.*

Checkpoint format (directory):
  <checkpoint_dir>/
    adapter_config.json    ← LoRA config (saved by PEFT)
    adapter_model.bin      ← LoRA weights (saved by PEFT)
    action_head.pt         ← action head state dict

Requirements:
    pip install transformers>=4.40.0 peft>=0.9.0 accelerate>=0.27.0
    pip install bitsandbytes>=0.43.0  # optional, for 4-bit quantization
    pip install sentencepiece protobuf  # tokenizer deps
"""

import os
import logging
import torch
import torch.nn as nn
from PIL import Image

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Optional dependency checks
# ---------------------------------------------------------------------------
try:
    from transformers import AutoModelForVision2Seq, AutoProcessor
    TRANSFORMERS_AVAILABLE = True
except ImportError:
    TRANSFORMERS_AVAILABLE = False
    logger.warning(
        "[OpenVLA] transformers not installed.\n"
        "  Run: pip install transformers>=4.40.0 accelerate>=0.27.0"
    )

try:
    from peft import LoraConfig, get_peft_model, TaskType, PeftModel
    PEFT_AVAILABLE = True
except ImportError:
    PEFT_AVAILABLE = False
    logger.warning(
        "[OpenVLA] peft not installed.\n"
        "  Run: pip install peft>=0.9.0"
    )


# ---------------------------------------------------------------------------
# Action Head
# ---------------------------------------------------------------------------
class OpenVLAActionHead(nn.Module):
    """
    1D 連続バルブ制御用アクションヘッド。
    OpenVLA の 7-DoF 離散トークン出力を置き換える。

    入力 : LLM 最終層の hidden state [B, seq_len, hidden_size]
    出力 : Δvalve ∈ [-1, 1]  (スケール適用後 [-0.05, 0.05])
    """

    def __init__(self, hidden_size: int = 4096):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(hidden_size, 512),
            nn.GELU(),
            nn.Dropout(0.1),
            nn.Linear(512, 128),
            nn.GELU(),
            nn.Dropout(0.1),
            nn.Linear(128, 1),
            nn.Tanh(),
        )

    def forward(self, hidden_states: torch.Tensor) -> torch.Tensor:
        # 最後のトークンの hidden state を使用
        last_token = hidden_states[:, -1, :]  # [B, hidden_size]
        return self.net(last_token)            # [B, 1]


# ---------------------------------------------------------------------------
# OpenVLA
# ---------------------------------------------------------------------------
class OpenVLA(nn.Module):
    """
    True OpenVLA: SigLIP + DINOv2 (vision) + Llama-2 7B (LLM) + LoRA + ActionHead

    pretrained=True  → openvla/openvla-7b を HuggingFace からロード
    pretrained=False → ランダム初期化（テスト用、実用では非推奨）
    """

    HF_MODEL_ID = "openvla/openvla-7b"
    # Llama-2 7B の hidden size。モデル config から自動取得するが
    # ネットワーク不通時のフォールバック値として保持する。
    _LLAMA2_HIDDEN_SIZE = 4096

    def __init__(
        self,
        pretrained: bool = True,
        lora_rank: int = 32,
        lora_alpha: int = 16,
        use_4bit: bool = False,
        local_model_path: str = None,
    ):
        super().__init__()

        if not TRANSFORMERS_AVAILABLE:
            raise ImportError(
                "transformers が必要です:\n"
                "  pip install transformers>=4.40.0 accelerate>=0.27.0"
            )

        model_path = local_model_path or self.HF_MODEL_ID

        # --- Processor (tokenizer + image preprocessor) -------------------
        logger.info(f"[OpenVLA] Loading processor from {model_path} ...")
        self.processor = AutoProcessor.from_pretrained(
            model_path,
            trust_remote_code=True,
        )

        # --- Base model load kwargs ----------------------------------------
        load_kwargs = dict(
            trust_remote_code=True,
            torch_dtype=torch.bfloat16,
            low_cpu_mem_usage=True,
        )

        if use_4bit:
            try:
                from transformers import BitsAndBytesConfig
                load_kwargs["quantization_config"] = BitsAndBytesConfig(
                    load_in_4bit=True,
                    bnb_4bit_quant_type="nf4",
                    bnb_4bit_compute_dtype=torch.bfloat16,
                )
                logger.info("[OpenVLA] 4-bit 量子化 (NF4) を使用")
            except ImportError:
                logger.warning("[OpenVLA] bitsandbytes が見つからないため 4-bit 量子化をスキップ")

        # --- Load pretrained model -----------------------------------------
        if pretrained:
            logger.info(f"[OpenVLA] Loading pretrained model from {model_path} ...")
            self.base_model = AutoModelForVision2Seq.from_pretrained(
                model_path, **load_kwargs
            )
        else:
            # テスト用: config だけロードしてランダム初期化
            logger.warning("[OpenVLA] pretrained=False: ランダム初期化（テスト専用）")
            from transformers import AutoConfig
            config = AutoConfig.from_pretrained(model_path, trust_remote_code=True)
            self.base_model = AutoModelForVision2Seq.from_config(
                config, trust_remote_code=True
            )

        # --- Freeze vision backbone (SigLIP + DINOv2) ----------------------
        self._freeze_vision_backbone()

        # --- Apply LoRA to LLM (Llama-2) -----------------------------------
        if PEFT_AVAILABLE and lora_rank > 0:
            self._apply_lora(lora_rank, lora_alpha)
        else:
            logger.warning("[OpenVLA] LoRA をスキップ (peft 未インストールまたは rank=0)")

        # --- Action head (float32 で学習安定性を確保) ----------------------
        hidden_size = self._get_hidden_size()
        logger.info(f"[OpenVLA] LLM hidden_size = {hidden_size}")
        self.action_head = OpenVLAActionHead(hidden_size=hidden_size)

        # Δvalve のスケール: Tanh 出力 [-1,1] → [-0.05, 0.05]
        self.action_scale = 0.05

    # -----------------------------------------------------------------------
    # Setup helpers
    # -----------------------------------------------------------------------

    def _freeze_vision_backbone(self):
        """
        vision_backbone.* パラメータを完全凍結。
        SigLIP + DINOv2 の pretrained 重みを保護する。
        """
        frozen = 0
        for name, param in self.base_model.named_parameters():
            if name.startswith("vision_backbone."):
                param.requires_grad = False
                frozen += 1
        logger.info(f"[OpenVLA] Vision backbone: {frozen} パラメータを凍結")

    def _apply_lora(self, rank: int, alpha: int):
        """
        language_model.* の全 linear 層に LoRA を適用。
        OpenVLA 公式 fine-tune スクリプトに準拠。
        """
        config = LoraConfig(
            r=rank,
            lora_alpha=alpha,
            lora_dropout=0.0,
            target_modules="all-linear",   # 全 linear 層（公式設定）
            init_lora_weights="gaussian",
            bias="none",
        )
        self.base_model = get_peft_model(self.base_model, config)
        self.base_model.print_trainable_parameters()

    def _get_hidden_size(self) -> int:
        """Llama-2 7B の hidden_size を config から取得"""
        try:
            return self.base_model.config.hidden_size
        except AttributeError:
            pass
        try:
            return self.base_model.config.text_config.hidden_size
        except AttributeError:
            pass
        return self._LLAMA2_HIDDEN_SIZE

    # -----------------------------------------------------------------------
    # Forward
    # -----------------------------------------------------------------------

    def forward(self, images_dict: dict, prompt: str) -> float:
        """
        Args:
            images_dict : Dict[str, PIL.Image]  ─ Redis から取得した可視化画像
            prompt      : str  ─ PromptGenerator が生成した自然言語センサ記述

        Returns:
            float : Δvalve_opening ∈ [-0.05, 0.05]
        """
        image = self._pick_image(images_dict)

        # PrismaticProcessor: "<image> {prompt}" 形式を期待
        inputs = self.processor(
            text=f"<image> {prompt}",
            images=image,
            return_tensors="pt",
        )

        device = next(self.base_model.parameters()).device
        inputs = {k: v.to(device) for k, v in inputs.items()}

        # Forward pass (hidden states を取得)
        outputs = self.base_model(
            **inputs,
            output_hidden_states=True,
            return_dict=True,
        )

        # outputs.hidden_states: tuple of [B, seq_len, hidden_size]
        # 最終層 (index -1) を使用, float32 に変換して action head へ
        last_hidden = outputs.hidden_states[-1].float()  # [1, seq_len, hidden_size]

        delta_valve = self.action_head(last_hidden) * self.action_scale  # [1, 1]
        return delta_valve.item()

    # -----------------------------------------------------------------------
    # Image selection helper
    # -----------------------------------------------------------------------

    def _pick_image(self, images_dict: dict) -> Image.Image:
        """優先順位に従って最初に見つかった画像を返す"""
        for key in (
            "network_state_map", "temporal_slice", "phase_space", "multiscale_change",
            "system_ui", "valve_detail", "flow_dashboard", "comparison",
        ):
            if key in images_dict:
                return images_dict[key]
        return Image.new("RGB", (256, 256), color=(128, 128, 128))

    # -----------------------------------------------------------------------
    # Checkpoint I/O
    # -----------------------------------------------------------------------

    def save_trainable_weights(self, checkpoint_dir: str):
        """
        学習対象の重みのみ保存:
          - LoRA adapter weights  (adapter_config.json + adapter_model.bin)
          - Action head           (action_head.pt)
          - Projector             (projector.pt)
        """
        os.makedirs(checkpoint_dir, exist_ok=True)

        # LoRA weights
        if PEFT_AVAILABLE:
            self.base_model.save_pretrained(checkpoint_dir)
            logger.info(f"[OpenVLA] LoRA weights saved to {checkpoint_dir}")

        # Action head
        action_head_path = os.path.join(checkpoint_dir, "action_head.pt")
        torch.save(self.action_head.state_dict(), action_head_path)
        logger.info(f"[OpenVLA] Action head saved to {action_head_path}")

        # Projector (base_model.projector)
        try:
            projector_path = os.path.join(checkpoint_dir, "projector.pt")
            torch.save(self.base_model.projector.state_dict(), projector_path)
            logger.info(f"[OpenVLA] Projector saved to {projector_path}")
        except AttributeError:
            logger.debug("[OpenVLA] projector not found in base_model, skipping")

    def load_trainable_weights(self, checkpoint_dir: str):
        """
        save_trainable_weights() で保存したディレクトリからロード。
        """
        if not os.path.isdir(checkpoint_dir):
            logger.warning(f"[OpenVLA] Checkpoint directory not found: {checkpoint_dir}")
            return

        # LoRA weights
        adapter_config = os.path.join(checkpoint_dir, "adapter_config.json")
        if PEFT_AVAILABLE and os.path.exists(adapter_config):
            self.base_model = PeftModel.from_pretrained(
                self.base_model, checkpoint_dir
            )
            logger.info(f"[OpenVLA] LoRA weights loaded from {checkpoint_dir}")

        # Action head
        action_head_path = os.path.join(checkpoint_dir, "action_head.pt")
        if os.path.exists(action_head_path):
            self.action_head.load_state_dict(
                torch.load(action_head_path, map_location="cpu")
            )
            logger.info(f"[OpenVLA] Action head loaded from {action_head_path}")

        # Projector
        projector_path = os.path.join(checkpoint_dir, "projector.pt")
        if os.path.exists(projector_path):
            try:
                self.base_model.projector.load_state_dict(
                    torch.load(projector_path, map_location="cpu")
                )
                logger.info(f"[OpenVLA] Projector loaded from {projector_path}")
            except AttributeError:
                logger.debug("[OpenVLA] projector not found in base_model, skipping")


# ---------------------------------------------------------------------------
# Wrapper (既存インターフェース互換)
# ---------------------------------------------------------------------------
class OpenVLAWrapper:
    """
    OpenVLA の既存インターフェース互換ラッパー。

    checkpoint_path:
      - None      → pretrained 重みのみ使用
      - str (dir) → LoRA + action head をロード
    """

    def __init__(self, checkpoint_path: str = None, use_4bit: bool = False):
        self.model = OpenVLA(use_4bit=use_4bit)

        if checkpoint_path:
            if os.path.isdir(checkpoint_path):
                # 新形式: LoRA ディレクトリ
                self.model.load_trainable_weights(checkpoint_path)
            elif os.path.isfile(checkpoint_path):
                # 旧形式: .pt ファイル → action head として読み込みを試みる
                logger.warning(
                    f"[OpenVLA] .pt ファイルが指定されました: {checkpoint_path}\n"
                    "  新形式はディレクトリです。action head の state dict として読み込みを試みます。"
                )
                try:
                    state = torch.load(checkpoint_path, map_location="cpu")
                    self.model.action_head.load_state_dict(state)
                    logger.info("[OpenVLA] Action head loaded from legacy .pt file")
                except Exception as e:
                    logger.warning(f"[OpenVLA] Legacy checkpoint load failed: {e}")

        self.model.eval()
        logger.info("[OpenVLA] Ready")
        logger.info("[OpenVLA] Architecture: SigLIP + DINOv2 (frozen) + Llama-2 7B (LoRA) + ActionHead")

    def predict(self, images: dict, prompt: str) -> float:
        """
        Args:
            images : Dict[str, PIL.Image]
            prompt : str

        Returns:
            float : Δvalve_opening ∈ [-0.05, 0.05]
        """
        with torch.no_grad():
            return float(self.model(images, prompt))


# ---------------------------------------------------------------------------
# Smoke test
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print("Testing OpenVLA wrapper (pretrained=False, smoke test only)...")

    images = {
        "network_state_map": Image.new("RGB", (256, 256), color=(100, 150, 200)),
        "temporal_slice":    Image.new("RGB", (256, 256), color=(150, 100, 200)),
        "phase_space":       Image.new("RGB", (256, 256), color=(200, 150, 100)),
        "multiscale_change": Image.new("RGB", (256, 256), color=(150, 200, 100)),
    }
    prompt = "Current pressure: 35.5m at Node 2\nTarget: 30.0m\nValve opening: 75.0%"

    # pretrained=False はランダム初期化のためモデルダウンロード不要
    model = OpenVLA(pretrained=False)
    model.eval()
    with torch.no_grad():
        action = model(images, prompt)
    print(f"Result: delta_valve = {action:.4f}")
