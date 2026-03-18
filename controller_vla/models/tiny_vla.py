"""
TinyVLA - True TinyVLA Implementation
======================================
Based on: https://github.com/liyaxuanliyaxuan/TinyVLA
Paper: TinyVLA: Towards Fast, Data-Efficient Vision-Language-Action Models
       for Robotic Manipulation (Wen et al., 2024, arXiv:2409.12514)

Architecture:
  - Vision Encoder : CLIP ViT-L/14 (openai/clip-vit-large-patch14) → FROZEN
  - Projection     : Linear(768 → 2048)                             → Full train
  - LLM Backbone   : Pythia-1.4b (EleutherAI/pythia-1.4b)          → LoRA (rank=16)
  - Diffusion Policy: DDPM-based MLP denoiser (1D action)           → Full train

LLaVA-style 視覚-言語融合:
  CLIP pooler_output [B,768] → Projection → visual_embed [B,1,2048]
  Pythia tokenizer → text_embeds [B,seq,2048]
  inputs_embeds = [visual_embed, text_embeds] → Pythia → last hidden state

Diffusion Policy (DDPM, 1D action):
  Forward : x_t = sqrt(ᾱ_t)*x_0 + sqrt(1-ᾱ_t)*ε
  Denoiser: MLP(x_t ‖ time_emb ‖ cond) → predicted ε
  Inference: DDIM deterministic sampling, N=10 steps

学習戦略:
  Frozen : CLIP ViT-L/14 全体
  LoRA   : Pythia-1.4b (rank=16, target_modules="all-linear")
  Full   : projection.*, diffusion_head.*

Checkpoint format (directory):
  <checkpoint_dir>/
    adapter_config.json + adapter_model.bin  ← LoRA (Pythia)
    projection.pt                            ← vision projection
    diffusion_head.pt                        ← diffusion policy head

Requirements:
    pip install transformers>=4.40.0 peft>=0.9.0 accelerate>=0.27.0
"""

import os
import math
import logging
import torch
import torch.nn as nn
import torch.nn.functional as F
from PIL import Image

logger = logging.getLogger(__name__)

try:
    from transformers import (
        CLIPVisionModel,
        CLIPImageProcessor,
        AutoModelForCausalLM,
        AutoTokenizer,
    )
    TRANSFORMERS_AVAILABLE = True
except ImportError:
    TRANSFORMERS_AVAILABLE = False
    logger.warning("[TinyVLA] transformers not installed. Run: pip install transformers>=4.40.0")

try:
    from peft import LoraConfig, get_peft_model, TaskType, PeftModel
    PEFT_AVAILABLE = True
except ImportError:
    PEFT_AVAILABLE = False
    logger.warning("[TinyVLA] peft not installed. Run: pip install peft>=0.9.0")


# ---------------------------------------------------------------------------
# DDPM Noise Schedule
# ---------------------------------------------------------------------------

def _make_ddpm_schedule(n_timesteps: int = 100) -> dict:
    """
    線形ノイズスケジュール (Ho et al. 2020)
    returns dict of tensors: beta, alpha, alpha_bar, sqrt_alpha_bar, sqrt_one_minus_alpha_bar
    """
    beta = torch.linspace(1e-4, 0.02, n_timesteps)  # [T]
    alpha = 1.0 - beta                                # [T]
    alpha_bar = torch.cumprod(alpha, dim=0)           # [T]  ᾱ_t
    return {
        "beta": beta,
        "alpha": alpha,
        "alpha_bar": alpha_bar,
        "sqrt_alpha_bar": alpha_bar.sqrt(),
        "sqrt_one_minus_alpha_bar": (1.0 - alpha_bar).sqrt(),
    }


def _sinusoidal_embedding(timesteps: torch.Tensor, dim: int) -> torch.Tensor:
    """
    Sinusoidal time step embedding
    timesteps: [B] int (0 ~ T-1)
    returns  : [B, dim]
    """
    half = dim // 2
    freqs = torch.exp(
        -math.log(10000) * torch.arange(half, dtype=torch.float32) / half
    ).to(timesteps.device)
    args = timesteps.float().unsqueeze(1) * freqs.unsqueeze(0)
    return torch.cat([torch.cos(args), torch.sin(args)], dim=-1)


# ---------------------------------------------------------------------------
# Diffusion Policy Head (DDPM, 1D)
# ---------------------------------------------------------------------------

class DiffusionPolicyHead(nn.Module):
    """
    DDPM ベースの拡散ポリシーヘッド (TinyVLA 論文に準拠, 1D バルブ制御向け)

    liyaxuanliyaxuan/TinyVLA との対応:
      - 3-layer MLP denoiser で条件付き埋め込みを生成
      - 標準 DDPM フローでノイズ除去
      - 学習: noise prediction (ε-prediction) 目的関数

    入力 (forward):
      x_t   : [B, 1]       (ノイズ混じりのアクション)
      t     : [B] int      (拡散タイムステップ, 0 ~ T-1)
      cond  : [B, cond_dim] (Pythia last hidden state を射影したもの)
    出力:
      eps_pred : [B, 1]    (予測ノイズ)
    """

    N_TIMESTEPS = 100
    TIME_EMB_DIM = 64

    def __init__(self, cond_dim: int = 256):
        super().__init__()

        schedule = _make_ddpm_schedule(self.N_TIMESTEPS)
        # buffer として登録 (device 移動に追従)
        for k, v in schedule.items():
            self.register_buffer(k, v)

        in_dim = 1 + self.TIME_EMB_DIM + cond_dim
        self.denoiser = nn.Sequential(
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
        t_emb = _sinusoidal_embedding(t, self.TIME_EMB_DIM)    # [B, 64]
        h = torch.cat([x_t, t_emb, cond], dim=-1)
        return self.denoiser(h)                                 # [B, 1]

    # ------------------------------------------------------------------
    # Training loss (ε-prediction)
    # ------------------------------------------------------------------

    def compute_loss(
        self,
        action: torch.Tensor,
        cond: torch.Tensor,
    ) -> torch.Tensor:
        """
        DDPM ε-prediction 損失
        action: [B, 1]  真のアクション (x_0)
        cond  : [B, cond_dim]
        """
        B = action.size(0)
        device = action.device

        # ランダムタイムステップ
        t = torch.randint(0, self.N_TIMESTEPS, (B,), device=device)
        # ランダムノイズ
        eps = torch.randn_like(action)
        # 前向き拡散
        sq_ab = self.sqrt_alpha_bar[t].view(B, 1)
        sq_omab = self.sqrt_one_minus_alpha_bar[t].view(B, 1)
        x_t = sq_ab * action + sq_omab * eps

        eps_pred = self.forward(x_t, t, cond)
        return F.mse_loss(eps_pred, eps)

    # ------------------------------------------------------------------
    # Inference (DDIM deterministic sampling)
    # ------------------------------------------------------------------

    @torch.no_grad()
    def sample(
        self,
        cond: torch.Tensor,
        n_steps: int = 10,
    ) -> torch.Tensor:
        """
        DDIM でアクションをサンプリング
        cond: [B, cond_dim]
        returns: [B, 1]
        """
        B = cond.size(0)
        device = cond.device

        # タイムステップ列 (T-1 → 0, n_steps 個に均等サンプリング)
        timesteps = torch.linspace(
            self.N_TIMESTEPS - 1, 0, n_steps, device=device
        ).long()

        x = torch.randn(B, 1, device=device)

        for i, t_val in enumerate(timesteps):
            t_batch = t_val.expand(B)
            eps_pred = self.forward(x, t_batch, cond)

            # DDIM update (Eq. 12 in Song et al. 2020)
            ab_t = self.alpha_bar[t_val]
            x0_pred = (x - (1 - ab_t).sqrt() * eps_pred) / ab_t.sqrt()
            x0_pred = x0_pred.clamp(-1.0, 1.0)

            if i < n_steps - 1:
                t_prev = timesteps[i + 1]
                ab_prev = self.alpha_bar[t_prev]
                x = ab_prev.sqrt() * x0_pred + (1 - ab_prev).sqrt() * eps_pred
            else:
                x = x0_pred

        return x  # [B, 1]


# ---------------------------------------------------------------------------
# TinyVLA
# ---------------------------------------------------------------------------

class TinyVLA(nn.Module):
    """
    True TinyVLA: CLIP ViT-L/14 (frozen) + Projection + Pythia-1.4b (LoRA)
                  + Diffusion Policy Head

    LLaVA-style fusion:
      CLIP pooler [B,768] → proj → visual_embed [B,1,2048]
      [visual_embed ‖ text_embeds] → Pythia → last token hidden state
      → cond_proj → Diffusion Policy Head → Δvalve
    """

    CLIP_MODEL_ID = "openai/clip-vit-large-patch14"
    LLM_MODEL_ID = "EleutherAI/pythia-1.4b"

    _CLIP_DIM = 768       # CLIP ViT-L/14 pooler output dim
    _PYTHIA_DIM = 2048    # Pythia-1.4b hidden_size

    def __init__(
        self,
        pretrained: bool = True,
        lora_rank: int = 16,
        lora_alpha: int = 32,
        local_clip_path: str = None,
        local_llm_path: str = None,
    ):
        super().__init__()

        if not TRANSFORMERS_AVAILABLE:
            raise ImportError(
                "transformers が必要です:\n"
                "  pip install transformers>=4.40.0 accelerate>=0.27.0"
            )

        clip_path = local_clip_path or self.CLIP_MODEL_ID
        llm_path = local_llm_path or self.LLM_MODEL_ID

        # --- CLIP vision encoder (frozen) ------------------------------------
        logger.info(f"[TinyVLA] Loading CLIP from {clip_path} ...")
        if pretrained:
            self.vision_encoder = CLIPVisionModel.from_pretrained(
                clip_path, torch_dtype=torch.bfloat16
            )
        else:
            from transformers import CLIPVisionConfig
            self.vision_encoder = CLIPVisionModel(CLIPVisionConfig())

        self.image_processor = CLIPImageProcessor.from_pretrained(clip_path)
        self._freeze_vision()

        # --- Vision → LLM projection -----------------------------------------
        self.vision_proj = nn.Linear(self._CLIP_DIM, self._PYTHIA_DIM)

        # --- Pythia-1.4b (LLM backbone) --------------------------------------
        logger.info(f"[TinyVLA] Loading Pythia from {llm_path} ...")
        if pretrained:
            self.llm = AutoModelForCausalLM.from_pretrained(
                llm_path,
                torch_dtype=torch.bfloat16,
                low_cpu_mem_usage=True,
            )
        else:
            from transformers import AutoConfig
            cfg = AutoConfig.from_pretrained(llm_path)
            self.llm = AutoModelForCausalLM.from_config(cfg)

        self.tokenizer = AutoTokenizer.from_pretrained(llm_path)
        if self.tokenizer.pad_token is None:
            self.tokenizer.pad_token = self.tokenizer.eos_token

        # --- LoRA on Pythia --------------------------------------------------
        if PEFT_AVAILABLE and lora_rank > 0:
            self._apply_lora(lora_rank, lora_alpha)
        else:
            logger.warning("[TinyVLA] LoRA をスキップ")

        # --- Conditioning projection + Diffusion Policy ----------------------
        hidden_size = self._get_hidden_size()
        logger.info(f"[TinyVLA] Pythia hidden_size = {hidden_size}")
        self.cond_proj = nn.Linear(hidden_size, 256)
        self.diffusion_head = DiffusionPolicyHead(cond_dim=256)

        self.action_scale = 0.05

    # -----------------------------------------------------------------------
    # Setup helpers
    # -----------------------------------------------------------------------

    def _freeze_vision(self):
        """CLIP ViT-L/14 を完全凍結"""
        for param in self.vision_encoder.parameters():
            param.requires_grad = False
        logger.info("[TinyVLA] CLIP ViT-L/14: 全パラメータを凍結")

    def _apply_lora(self, rank: int, alpha: int):
        """Pythia の全 linear 層に LoRA を適用"""
        config = LoraConfig(
            r=rank,
            lora_alpha=alpha,
            lora_dropout=0.0,
            target_modules="all-linear",
            init_lora_weights="gaussian",
            bias="none",
        )
        self.llm = get_peft_model(self.llm, config)
        self.llm.print_trainable_parameters()

    def _get_hidden_size(self) -> int:
        try:
            return self.llm.config.hidden_size
        except AttributeError:
            return self._PYTHIA_DIM

    # -----------------------------------------------------------------------
    # Forward
    # -----------------------------------------------------------------------

    def _get_conditioning(self, images_dict: dict, prompt: str) -> torch.Tensor:
        """
        CLIP + Pythia で conditioning vector を生成 → [1, 256]
        LLaVA-style: visual_embed を text_embeds の先頭に結合
        """
        device = next(self.vision_encoder.parameters()).device
        image = self._pick_image(images_dict)

        # --- Visual encoding -------------------------------------------------
        pixel_values = self.image_processor(
            images=image, return_tensors="pt"
        ).pixel_values.to(device, dtype=torch.bfloat16)

        vision_out = self.vision_encoder(pixel_values=pixel_values)
        visual_feat = vision_out.pooler_output.float()            # [1, 768]
        visual_embed = self.vision_proj(visual_feat).unsqueeze(1) # [1, 1, 2048]

        # --- Text encoding ---------------------------------------------------
        tokens = self.tokenizer(
            prompt,
            return_tensors="pt",
            truncation=True,
            max_length=128,
        ).to(device)

        # Pythia の embedding layer から text_embeds を取得
        # (GPT-NeoX 系: model.gpt_neox.embed_in)
        try:
            embed_layer = self.llm.base_model.model.gpt_neox.embed_in
        except AttributeError:
            embed_layer = self.llm.get_input_embeddings()

        text_embeds = embed_layer(tokens.input_ids).float()  # [1, seq, 2048]

        # --- LLaVA-style fusion: [visual ‖ text] → Pythia -------------------
        inputs_embeds = torch.cat(
            [visual_embed, text_embeds], dim=1
        )  # [1, 1+seq, 2048]

        attention_mask = torch.ones(
            inputs_embeds.shape[:2], dtype=torch.long, device=device
        )

        outputs = self.llm(
            inputs_embeds=inputs_embeds.to(torch.bfloat16),
            attention_mask=attention_mask,
            output_hidden_states=True,
            return_dict=True,
        )

        last_hidden = outputs.hidden_states[-1][:, -1, :].float()  # [1, 2048]
        return self.cond_proj(last_hidden)                          # [1, 256]

    def forward(self, images_dict: dict, prompt: str) -> float:
        """
        Args:
            images_dict : Dict[str, PIL.Image]
            prompt      : str

        Returns:
            float : Δvalve_opening ∈ [-0.05, 0.05]
        """
        cond = self._get_conditioning(images_dict, prompt)       # [1, 256]
        action = self.diffusion_head.sample(cond, n_steps=10)    # [1, 1]
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
            self.llm.save_pretrained(checkpoint_dir)
        torch.save(self.vision_proj.state_dict(),
                   os.path.join(checkpoint_dir, "projection.pt"))
        torch.save(
            {
                "cond_proj": self.cond_proj.state_dict(),
                "diffusion_head": self.diffusion_head.state_dict(),
            },
            os.path.join(checkpoint_dir, "diffusion_head.pt"),
        )
        logger.info(f"[TinyVLA] Saved to {checkpoint_dir}")

    def load_trainable_weights(self, checkpoint_dir: str):
        if not os.path.isdir(checkpoint_dir):
            logger.warning(f"[TinyVLA] Checkpoint not found: {checkpoint_dir}")
            return
        adapter_cfg = os.path.join(checkpoint_dir, "adapter_config.json")
        if PEFT_AVAILABLE and os.path.exists(adapter_cfg):
            self.llm = PeftModel.from_pretrained(self.llm, checkpoint_dir)
            logger.info(f"[TinyVLA] LoRA loaded from {checkpoint_dir}")
        proj_path = os.path.join(checkpoint_dir, "projection.pt")
        if os.path.exists(proj_path):
            self.vision_proj.load_state_dict(
                torch.load(proj_path, map_location="cpu")
            )
        head_path = os.path.join(checkpoint_dir, "diffusion_head.pt")
        if os.path.exists(head_path):
            ckpt = torch.load(head_path, map_location="cpu")
            self.cond_proj.load_state_dict(ckpt["cond_proj"])
            self.diffusion_head.load_state_dict(ckpt["diffusion_head"])
            logger.info(f"[TinyVLA] Diffusion head loaded from {head_path}")


# ---------------------------------------------------------------------------
# Wrapper (既存インターフェース互換)
# ---------------------------------------------------------------------------

class TinyVLAWrapper:
    """
    TinyVLA の既存インターフェース互換ラッパー。

    checkpoint_path:
      - None      → pretrained 重みのみ
      - str (dir) → LoRA + diffusion head をロード
    """

    def __init__(self, checkpoint_path: str = None):
        self.model = TinyVLA()

        if checkpoint_path and os.path.isdir(checkpoint_path):
            self.model.load_trainable_weights(checkpoint_path)

        self.model.eval()
        logger.info("[TinyVLA] Ready")
        logger.info("[TinyVLA] Architecture: CLIP ViT-L/14 (frozen) + Pythia-1.4b (LoRA) + Diffusion Policy")

    def predict(self, images: dict, prompt: str) -> float:
        with torch.no_grad():
            return float(self.model(images, prompt))


# ---------------------------------------------------------------------------
# Smoke test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print("Testing TinyVLA (pretrained=False, smoke test only)...")

    images = {
        "network_state_map": Image.new("RGB", (256, 256), color=(100, 150, 200)),
    }
    prompt = "Current pressure: 35.5m at Node 2\nTarget: 30.0m\nValve opening: 75.0%"

    model = TinyVLA(pretrained=False)
    model.eval()
    with torch.no_grad():
        action = model(images, prompt)
    print(f"Result: delta_valve = {action:.4f}")
