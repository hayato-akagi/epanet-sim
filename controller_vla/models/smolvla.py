"""
SmolVLA - True SmolVLA Implementation
======================================
Based on: https://github.com/huggingface/lerobot
Paper: SmolVLA: A Vision-Language-Action Model for Affordable and Efficient Robotics
       (HuggingFace, 2025)
HuggingFace VLM backbone: HuggingFaceTB/SmolVLM2-500M-Instruct

Architecture:
  - VLM Backbone  : SmolVLM2-500M (SigLIP-B/16 + SmolLM2-360M) → 一部 Frozen / LoRA
  - Flow Matching : Action Expert (Cross-Attn + MLP denoiser)   → Full train

Flow Matching (lerobot SmolVLA を 1D に簡略化):
  Training : x_t = (1-t)*noise + t*action   (線形補間)
             v_target = action - noise        (一定速度場)
             Loss = MSE(v_pred(x_t, t, cond), v_target)
  Inference: Euler ODE, N=10 steps, noise → action

学習戦略:
  Frozen  : vision_model.* (SigLIP-B/16)
  LoRA    : text_model.*   (SmolLM2-360M, rank=16)
  Full    : connector.*, action_expert.*

Checkpoint format (directory):
  <checkpoint_dir>/
    adapter_config.json + adapter_model.bin  ← LoRA weights (PEFT)
    action_expert.pt                         ← Flow Matching expert

Requirements:
    pip install transformers>=4.40.0 peft>=0.9.0 accelerate>=0.27.0
"""

import os
import math
import logging
import torch
import torch.nn as nn
from PIL import Image

logger = logging.getLogger(__name__)

try:
    from transformers import AutoModelForVision2Seq, AutoProcessor
    TRANSFORMERS_AVAILABLE = True
except ImportError:
    TRANSFORMERS_AVAILABLE = False
    logger.warning("[SmolVLA] transformers not installed. Run: pip install transformers>=4.40.0")

try:
    from peft import LoraConfig, get_peft_model, TaskType, PeftModel
    PEFT_AVAILABLE = True
except ImportError:
    PEFT_AVAILABLE = False
    logger.warning("[SmolVLA] peft not installed. Run: pip install peft>=0.9.0")


# ---------------------------------------------------------------------------
# Flow Matching Action Expert
# ---------------------------------------------------------------------------

def _sinusoidal_embedding(timesteps: torch.Tensor, dim: int) -> torch.Tensor:
    """
    Sinusoidal time step embedding (DDPM / Flow Matching 共通)
    timesteps: [B] float (0.0 ~ 1.0)
    returns  : [B, dim]
    """
    half = dim // 2
    freqs = torch.exp(
        -math.log(10000) * torch.arange(half, dtype=torch.float32) / half
    ).to(timesteps.device)
    args = timesteps.float().unsqueeze(1) * freqs.unsqueeze(0)  # [B, half]
    return torch.cat([torch.cos(args), torch.sin(args)], dim=-1)  # [B, dim]


class FlowMatchingActionExpert(nn.Module):
    """
    Flow Matching Action Expert (lerobot SmolVLA を 1D バルブ制御向けに簡略化)

    lerobot 実装との対応:
      - Cross-Attention (VLM 特徴 ↔ action tokens) → conditioning MLP で近似
      - Self-Attention (時系列平滑化)               → 1D なので省略
      - Flow Matching 目的関数                       → 同じ線形補間 + 速度場

    入力:
      x_t       : [B, 1]    (ノイズ混じりのアクション)
      t         : [B]       (フロー時刻, 0.0 ~ 1.0)
      cond      : [B, cond_dim]  (VLM hidden state から射影した条件)
    出力:
      v_pred    : [B, 1]    (予測速度場)
    """

    TIME_EMB_DIM = 64

    def __init__(self, cond_dim: int = 128):
        super().__init__()
        in_dim = 1 + self.TIME_EMB_DIM + cond_dim
        self.net = nn.Sequential(
            nn.Linear(in_dim, 256),
            nn.SiLU(),
            nn.Linear(256, 256),
            nn.SiLU(),
            nn.Linear(256, 128),
            nn.SiLU(),
            nn.Linear(128, 1),
        )

    def forward(
        self,
        x_t: torch.Tensor,
        t: torch.Tensor,
        cond: torch.Tensor,
    ) -> torch.Tensor:
        t_emb = _sinusoidal_embedding(t, self.TIME_EMB_DIM)  # [B, 64]
        h = torch.cat([x_t, t_emb, cond], dim=-1)
        return self.net(h)  # [B, 1]

    # ------------------------------------------------------------------
    # Training
    # ------------------------------------------------------------------

    def compute_loss(
        self,
        action: torch.Tensor,
        cond: torch.Tensor,
    ) -> torch.Tensor:
        """
        Flow Matching 損失 (Lipman et al. 2022 の条件付き線形フロー)
        action: [B, 1]  真のアクション (x_1)
        cond  : [B, cond_dim]
        """
        B = action.size(0)
        device = action.device

        # ランダム時刻 t ∈ [0, 1]
        t = torch.rand(B, device=device)
        # ランダムノイズ (x_0)
        noise = torch.randn_like(action)
        # 線形補間: x_t = (1-t)*noise + t*action
        t_expand = t.view(B, 1)
        x_t = (1 - t_expand) * noise + t_expand * action
        # 目標速度場: v = x_1 - x_0 = action - noise
        v_target = action - noise

        v_pred = self.forward(x_t, t, cond)
        return nn.functional.mse_loss(v_pred, v_target)

    # ------------------------------------------------------------------
    # Inference (Euler ODE)
    # ------------------------------------------------------------------

    @torch.no_grad()
    def sample(
        self,
        cond: torch.Tensor,
        n_steps: int = 10,
    ) -> torch.Tensor:
        """
        Euler ODE で noise → action を積分
        cond: [B, cond_dim]
        returns: [B, 1]
        """
        B = cond.size(0)
        device = cond.device

        x = torch.randn(B, 1, device=device)
        dt = 1.0 / n_steps

        for i in range(n_steps):
            t_val = i / n_steps
            t = torch.full((B,), t_val, device=device)
            v = self.forward(x, t, cond)
            x = x + v * dt

        return x  # [B, 1]


# ---------------------------------------------------------------------------
# SmolVLA
# ---------------------------------------------------------------------------

class SmolVLA(nn.Module):
    """
    True SmolVLA: SmolVLM2-500M backbone + Flow Matching Action Expert

    学習戦略:
      Frozen : vision_model.* (SigLIP)
      LoRA   : text_model.*   (SmolLM2-360M)
      Full   : connector.*, cond_proj.*, action_expert.*
    """

    HF_MODEL_ID = "HuggingFaceTB/SmolVLM2-500M-Instruct"
    # SmolLM2-360M の hidden_size。config から自動取得するが fallback 値として保持。
    _SMOLLM2_HIDDEN_SIZE = 960

    def __init__(
        self,
        pretrained: bool = True,
        lora_rank: int = 16,
        lora_alpha: int = 32,
        local_model_path: str = None,
    ):
        super().__init__()

        if not TRANSFORMERS_AVAILABLE:
            raise ImportError(
                "transformers が必要です:\n"
                "  pip install transformers>=4.40.0 accelerate>=0.27.0"
            )

        model_path = local_model_path or self.HF_MODEL_ID

        # --- Processor -------------------------------------------------------
        logger.info(f"[SmolVLA] Loading processor from {model_path} ...")
        self.processor = AutoProcessor.from_pretrained(model_path)

        # --- Base model -------------------------------------------------------
        load_kwargs = dict(
            torch_dtype=torch.bfloat16,
            low_cpu_mem_usage=True,
        )

        if pretrained:
            logger.info(f"[SmolVLA] Loading pretrained model from {model_path} ...")
            self.base_model = AutoModelForVision2Seq.from_pretrained(
                model_path, **load_kwargs
            )
        else:
            logger.warning("[SmolVLA] pretrained=False: ランダム初期化（テスト専用）")
            from transformers import AutoConfig
            config = AutoConfig.from_pretrained(model_path)
            self.base_model = AutoModelForVision2Seq.from_config(config)

        # --- Freeze vision encoder (SigLIP) ----------------------------------
        self._freeze_vision()

        # --- LoRA on language model (SmolLM2) --------------------------------
        if PEFT_AVAILABLE and lora_rank > 0:
            self._apply_lora(lora_rank, lora_alpha)
        else:
            logger.warning("[SmolVLA] LoRA をスキップ")

        # --- Flow Matching Action Expert -------------------------------------
        hidden_size = self._get_hidden_size()
        logger.info(f"[SmolVLA] LLM hidden_size = {hidden_size}")

        # VLM hidden state → conditioning vector (float32 で計算)
        self.cond_proj = nn.Linear(hidden_size, 128)
        self.action_expert = FlowMatchingActionExpert(cond_dim=128)

        self.action_scale = 0.05  # Tanh 相当のスケール

    # -----------------------------------------------------------------------
    # Setup helpers
    # -----------------------------------------------------------------------

    def _freeze_vision(self):
        """SigLIP vision encoder を凍結"""
        frozen = 0
        for name, param in self.base_model.named_parameters():
            if "vision_model" in name or "vision_encoder" in name:
                param.requires_grad = False
                frozen += 1
        logger.info(f"[SmolVLA] Vision encoder: {frozen} パラメータを凍結")

    def _apply_lora(self, rank: int, alpha: int):
        """SmolLM2 (text_model) の全 linear 層に LoRA を適用"""
        config = LoraConfig(
            r=rank,
            lora_alpha=alpha,
            lora_dropout=0.0,
            target_modules="all-linear",
            init_lora_weights="gaussian",
            bias="none",
        )
        self.base_model = get_peft_model(self.base_model, config)
        self.base_model.print_trainable_parameters()

    def _get_hidden_size(self) -> int:
        """SmolLM2 の hidden_size を config から取得"""
        for attr in ("hidden_size", "text_config.hidden_size", "language_config.hidden_size"):
            obj = self.base_model.config
            try:
                for key in attr.split("."):
                    obj = getattr(obj, key)
                return int(obj)
            except AttributeError:
                continue
        return self._SMOLLM2_HIDDEN_SIZE

    # -----------------------------------------------------------------------
    # Forward (inference)
    # -----------------------------------------------------------------------

    def _get_conditioning(self, images_dict: dict, prompt: str) -> torch.Tensor:
        """VLM forward → conditioning vector [1, 128]"""
        image = self._pick_image(images_dict)

        # SmolVLM2 は chat template または直接 <image> タグを使用
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "image"},
                    {"type": "text", "text": prompt},
                ],
            }
        ]
        text = self.processor.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=False
        )
        inputs = self.processor(
            text=[text],
            images=[image],
            return_tensors="pt",
        )

        device = next(self.base_model.parameters()).device
        inputs = {k: v.to(device) for k, v in inputs.items()}

        outputs = self.base_model(
            **inputs,
            output_hidden_states=True,
            return_dict=True,
        )

        # 最終層の最後トークン → float32 → conditioning
        last_hidden = outputs.hidden_states[-1][:, -1, :].float()  # [1, hidden_size]
        return self.cond_proj(last_hidden)  # [1, 128]

    def forward(self, images_dict: dict, prompt: str) -> float:
        """
        Args:
            images_dict : Dict[str, PIL.Image]
            prompt      : str

        Returns:
            float : Δvalve_opening ∈ [-0.05, 0.05]
        """
        cond = self._get_conditioning(images_dict, prompt)            # [1, 128]
        action = self.action_expert.sample(cond, n_steps=10)          # [1, 1]
        # action をスケール: 1.0 → 0.05 になるよう tanh で圧縮
        delta_valve = torch.tanh(action) * self.action_scale
        return delta_valve.item()

    def _pick_image(self, images_dict: dict) -> Image.Image:
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
        os.makedirs(checkpoint_dir, exist_ok=True)
        if PEFT_AVAILABLE:
            self.base_model.save_pretrained(checkpoint_dir)
        torch.save(
            {
                "cond_proj": self.cond_proj.state_dict(),
                "action_expert": self.action_expert.state_dict(),
            },
            os.path.join(checkpoint_dir, "action_expert.pt"),
        )
        logger.info(f"[SmolVLA] Saved to {checkpoint_dir}")

    def load_trainable_weights(self, checkpoint_dir: str):
        if not os.path.isdir(checkpoint_dir):
            logger.warning(f"[SmolVLA] Checkpoint not found: {checkpoint_dir}")
            return
        adapter_cfg = os.path.join(checkpoint_dir, "adapter_config.json")
        if PEFT_AVAILABLE and os.path.exists(adapter_cfg):
            self.base_model = PeftModel.from_pretrained(self.base_model, checkpoint_dir)
            logger.info(f"[SmolVLA] LoRA loaded from {checkpoint_dir}")
        expert_path = os.path.join(checkpoint_dir, "action_expert.pt")
        if os.path.exists(expert_path):
            ckpt = torch.load(expert_path, map_location="cpu")
            self.cond_proj.load_state_dict(ckpt["cond_proj"])
            self.action_expert.load_state_dict(ckpt["action_expert"])
            logger.info(f"[SmolVLA] Action expert loaded from {expert_path}")


# ---------------------------------------------------------------------------
# Wrapper (既存インターフェース互換)
# ---------------------------------------------------------------------------

class SmolVLAWrapper:
    """
    SmolVLA の既存インターフェース互換ラッパー。

    checkpoint_path:
      - None      → pretrained 重みのみ
      - str (dir) → LoRA + action expert をロード
    """

    def __init__(self, checkpoint_path: str = None):
        self.model = SmolVLA()

        if checkpoint_path and os.path.isdir(checkpoint_path):
            self.model.load_trainable_weights(checkpoint_path)

        self.model.eval()
        logger.info("[SmolVLA] Ready")
        logger.info("[SmolVLA] Architecture: SmolVLM2-500M (frozen SigLIP + LoRA SmolLM2) + Flow Matching")

    def predict(self, images: dict, prompt: str) -> float:
        with torch.no_grad():
            return float(self.model(images, prompt))


# ---------------------------------------------------------------------------
# Smoke test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print("Testing SmolVLA (pretrained=False, smoke test only)...")

    images = {
        "network_state_map": Image.new("RGB", (256, 256), color=(100, 150, 200)),
    }
    prompt = "Current pressure: 35.5m at Node 2\nTarget: 30.0m\nValve opening: 75.0%"

    model = SmolVLA(pretrained=False)
    model.eval()
    with torch.no_grad():
        action = model(images, prompt)
    print(f"Result: delta_valve = {action:.4f}")
