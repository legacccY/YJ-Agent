"""
smp backbone + GDN-2 bottleneck hybrid model for retinal vessel segmentation.

Architecture (headline-agnostic skeleton):
  - Encoder: smp.Unet with ImageNet-pretrained ResNet-34 (or other smp encoders).
  - Decoder: smp stock bilinear decoder with skip connections.
  - GDN-2 memory module inserted at the smp bottleneck (features[-1]):
      features[-1]  shape: (B, encoder_channels[-1], H_pad/32, W_pad/32)
      After GDN-2:  same shape, passed to smp decoder unchanged.
  - Segmentation head: smp stock Conv2d head.

Input / padding contract:
  ResNet-34 output_stride=32.  For a 565×584 DRIVE full image, bottleneck would
  be 17.7×18.25 — fractional, and 17×18=306 tokens.  We pad to the next 32-multiple
  (576×608) before forward and crop back to original size after.  This ensures:
    (a) no fractional spatial dims anywhere in the network
    (b) bottleneck tokens = (H_pad/32)*(W_pad/32) ≤ 1024

  Max input size that keeps tokens ≤ 1024:  32*32 at bottleneck = 1024×1024 input.
  DRIVE full image (565×584) → pad to 576×608 → bottleneck 18×19 = 342 tokens.  OK.

GDN-2 module wiring:
  - Reuses GDN2MemoryModule from unet_gdn2.py verbatim (not reimplemented here).
  - d_model must match encoder_channels[-1] (512 for resnet34).
  - Token constraint asserted inside GDN2MemoryModule.forward (T ≤ 1024).

Headline-agnostic boundaries:
  - ReID head NOT wired (gradient flow from ReID head into encoder/memory is headline-B).
  - Detach / re-flow boundary (path-A vs path-B) NOT wired.
  - Frangi gate: forwarded to GDN2MemoryModule if use_frangi=True (same as UNetGDN2).
  All three marked with # TODO headline 定后接.

Windows training compliance:
  - No scipy / OpenMP-conflicting libs.
  - Padding/crop uses torch.nn.functional only.

Dependencies:
  - segmentation_models_pytorch (smp): install in gdn2venv via
      pip install segmentation-models-pytorch timm torchvision
    # TODO: 主线 HPC 装 smp 后跑 python src/models/unet_smp_gdn2.py --smoke 1 验算子

Author: coder (sonnet), 2026-06-22
Service: gdn2vessel / ACCV2026 P1 主实验官方化迁移 lever=smp-backbone
"""

from __future__ import annotations

import math
import os
from typing import Dict, List, Optional, Tuple, Union

import torch
import torch.nn as nn
import torch.nn.functional as F

# --------------------------------------------------------------------------- #
#  smp import — gated so tests can mock without real smp installed
#  # TODO: 待主线 HPC 装 smp 后烟测 (gdn2venv 当前缺 timm/torchvision)
# --------------------------------------------------------------------------- #

try:
    import segmentation_models_pytorch as smp  # type: ignore[import]
    _SMP_AVAILABLE = True
except ImportError:
    smp = None  # type: ignore[assignment]
    _SMP_AVAILABLE = False

# GDN2MemoryModule lives next door — import lazily so test stubs can patch fla first
# (caller is responsible for patching fla BEFORE importing this module, same as test_shapes.py)
from .unet_gdn2 import GDN2MemoryModule, BACKEND

# --------------------------------------------------------------------------- #
#  Constants
# --------------------------------------------------------------------------- #

# ResNet-34 output_stride.  features[-1] spatial = (H_pad / STRIDE, W_pad / STRIDE)
_RESNET_STRIDE = 32

# GDN-2 max sequence length (must match GDN2MemoryModule.MAX_SEQ_LEN)
_MAX_SEQ_LEN = 1024

# resnet34 encoder channel widths (smp default depth=5):
#   features = [None, 64, 64, 128, 256, 512]
#   features[-1] = 512ch (bottleneck)
# SOURCE: qubvel-org/segmentation_models_pytorch, encoders/resnet.py
_RESNET34_BOTTLENECK_CH = 512


# --------------------------------------------------------------------------- #
#  Padding helpers
# --------------------------------------------------------------------------- #

def _pad_to_stride(
    x: torch.Tensor,
    stride: int,
) -> Tuple[torch.Tensor, Tuple[int, int, int, int]]:
    """
    Pad x (B,C,H,W) to nearest stride-multiple on H and W dims.

    Returns:
        x_pad: (B, C, H_pad, W_pad) where H_pad % stride == 0, W_pad % stride == 0
        pad_hw: (pad_top, pad_bottom, pad_left, pad_right) — stored for crop-back
    """
    _, _, H, W = x.shape
    H_pad = math.ceil(H / stride) * stride
    W_pad = math.ceil(W / stride) * stride
    pad_h = H_pad - H   # total vertical padding
    pad_w = W_pad - W   # total horizontal padding
    # Distribute evenly; extra pixel goes to bottom/right (matches smp convention)
    pad_top    = pad_h // 2
    pad_bottom = pad_h - pad_top
    pad_left   = pad_w // 2
    pad_right  = pad_w - pad_left
    # F.pad takes (left, right, top, bottom) in reverse-dim order.
    # zero-pad (constant): 标准 U-Net/smp 输入对齐做法,无尺寸限制(reflect 在 pad>dim 时报错,
    # 极小尺寸 feature 会爆);decoder 输出 crop 回原尺寸,黑边不入 loss。
    x_pad = F.pad(x, (pad_left, pad_right, pad_top, pad_bottom), mode='constant', value=0.0)
    return x_pad, (pad_top, pad_bottom, pad_left, pad_right)


def _crop_to_original(
    x: torch.Tensor,
    pad_hw: Tuple[int, int, int, int],
    H_orig: int,
    W_orig: int,
) -> torch.Tensor:
    """
    Crop x (B,C,H_pad,W_pad) back to (B,C,H_orig,W_orig) using stored pad amounts.
    """
    pad_top, pad_bottom, pad_left, pad_right = pad_hw
    H_pad = x.shape[-2]
    W_pad = x.shape[-1]
    h_end = H_pad - pad_bottom if pad_bottom > 0 else H_pad
    w_end = W_pad - pad_right  if pad_right  > 0 else W_pad
    return x[:, :, pad_top:h_end, pad_left:w_end]


# --------------------------------------------------------------------------- #
#  UNetSmpGDN2
# --------------------------------------------------------------------------- #

class UNetSmpGDN2(nn.Module):
    """
    smp.Unet with ImageNet-pretrained ResNet-34 encoder + GDN-2 bottleneck memory.

    Drop-in forward signature compatible with UNetGDN2 (same args, same output).
    The only outward difference vs UNetGDN2:
      - encoder is ResNet-34 (ImageNet weights, smp) not the bespoke UNet CNN
      - input is padded to 32-multiple before forward, cropped back after
      - GDN-2 is inserted at features[-1] (smp bottleneck = 512ch)

    Headline-agnostic:  ReID head, detach path-A/B are NOT wired here.
    To add ReID or gradient-flow decisions, subclass and override forward().

    Args:
        in_channels:     input image channels (1 for green-channel DRIVE)
        classes:         output segmentation classes (1 for binary vessel)
        encoder_name:    smp encoder name (default 'resnet34')
        encoder_weights: 'imagenet' for ImageNet pretrain; None for random init
        d_head:          GDN-2 head dimension (default 64, same as UNetGDN2)
        n_heads:         GDN-2 number of heads (default 1)
        use_memory:      True = GDN-2 active; False = plain smp.Unet (no memory)
        backend:         'naive' | 'chunk'  (FLA backend; naive = HPC-tested)
        directions:      1 / 2 / 4 scan directions for ablation (default 1)
        use_frangi:      True = Mechanism B Frangi gate; False = off
        frangi_scales:   DifferentiableFrangi σ values
        decoder_attention_type: smp decoder attention (None | 'scse')

    GDN-2 channel config (resnet34):
        bottleneck = features[-1] → 512ch
        GDN2MemoryModule(d_model=512, d_head=64, n_heads=1)
        bottleneck spatial at 576×608 input → 18×19 = 342 tokens ≤ 1024 OK
    """

    def __init__(
        self,
        in_channels: int = 1,
        classes: int = 1,
        encoder_name: str = 'resnet34',
        encoder_weights: Optional[str] = 'imagenet',
        d_head: int = 64,
        n_heads: int = 1,
        use_memory: bool = True,
        backend: str = BACKEND,
        directions: int = 1,
        use_frangi: bool = True,
        frangi_scales: Tuple[float, ...] = (0.5, 1.0, 1.5),
        decoder_attention_type: Optional[str] = None,
    ):
        super().__init__()

        # -- smp model ----------------------------------------------------- #
        if not _SMP_AVAILABLE:
            raise ImportError(
                "segmentation_models_pytorch not installed.  "
                "Run: pip install segmentation-models-pytorch timm torchvision\n"
                "# TODO: 待主线 HPC 装 smp 后烟测"
            )

        # smp.Unet with 1-channel input (smp internally sums imagenet weights
        # along channel dim to adapt 3ch → 1ch when in_channels != 3)
        # SOURCE: qubvel-org/segmentation_models_pytorch, encoders/_utils.py
        self._base = smp.Unet(
            encoder_name=encoder_name,
            encoder_weights=encoder_weights,
            in_channels=in_channels,
            classes=classes,
            activation=None,               # raw logits, sigmoid applied at loss
            decoder_attention_type=decoder_attention_type,
        )

        # Determine encoder bottleneck channels from smp encoder info
        # encoder.out_channels is a tuple: (3, 64, 64, 128, 256, 512) for resnet34
        # features[-1] corresponds to out_channels[-1]
        # SOURCE: smp EncoderMixin.out_channels
        bottleneck_ch = self._base.encoder.out_channels[-1]
        # Sanity check for resnet34; other encoders should still work but bottleneck_ch
        # may differ — GDN2MemoryModule will use whatever bottleneck_ch is.
        if encoder_name == 'resnet34':
            assert bottleneck_ch == _RESNET34_BOTTLENECK_CH, (
                f"Expected resnet34 bottleneck_ch={_RESNET34_BOTTLENECK_CH}, "
                f"got {bottleneck_ch}"
            )

        self.in_channels = in_channels
        self.classes = classes
        self.use_memory = use_memory
        self.d_head = d_head
        self.n_heads = n_heads
        self._bottleneck_ch = bottleneck_ch

        # -- GDN-2 memory module at bottleneck ------------------------------ #
        if use_memory:
            self.memory = GDN2MemoryModule(
                d_model=bottleneck_ch,
                d_head=d_head,
                n_heads=n_heads,
                max_seq_len=_MAX_SEQ_LEN,
                backend=backend,
                directions=directions,
                use_frangi=use_frangi,
                frangi_scales=frangi_scales,
                # frangi_beta1, frangi_beta2: use GDN2MemoryModule defaults (Frangi 1998)
            )
        else:
            self.memory = None

        # -- TODO headline 定后接 ------------------------------------------- #
        # ReID head (path-B, Claim 2):
        #   self.reid_head = ReIDReadoutHead(...)  # TODO: 主线接 headline 后补
        # Detach / gradient boundary (path-A vs path-B):
        #   features[-1] = self.memory(features[-1])  vs
        #   features[-1] = self.memory(features[-1].detach()) + residual path
        # Both left to subclass / training loop level once headline is set.

    @property
    def encoder(self):
        """Expose smp encoder for inspection / fine-tuning control."""
        return self._base.encoder

    @property
    def decoder(self):
        """Expose smp decoder."""
        return self._base.decoder

    @property
    def segmentation_head(self):
        """Expose smp segmentation head."""
        return self._base.segmentation_head

    # ---------------------------------------------------------------------- #
    #  Forward
    # ---------------------------------------------------------------------- #

    def forward(
        self,
        x: torch.Tensor,
        return_reid_ctx: bool = False,
    ) -> Union[torch.Tensor, Tuple[torch.Tensor, Dict]]:
        """
        Args:
            x: (B, in_channels, H, W) — input image (normalised, e.g. green channel)
               NOTE: GT is NOT passed here or to any submodule.
            return_reid_ctx: if True, return extra context dict for ReID head.
                Currently returns partial ctx (o_seq, memory_state, bottleneck shape).
                dec_feat wiring left TODO (headline-agnostic: no decoder layer hook yet).

        Returns:
            return_reid_ctx=False → logits: (B, classes, H, W)
            return_reid_ctx=True  → (logits, reid_ctx)
                reid_ctx keys:
                  'o_seq':        (B, T, n_heads*d_head) or None  — memory output seq
                  'memory_state': List[Optional[Tensor]] or None   — per-dir states
                  'H_bot', 'W_bot': int  — bottleneck spatial dims (post-pad)
                  # TODO headline 定后接:
                  #   'dec_feat': (B, dec_ch, H_dec, W_dec) — decoder layer for ReID
        """
        B, C, H_orig, W_orig = x.shape

        # ------------------------------------------------------------------ #
        # 1. Pad to stride-multiple (ResNet-34 requires H,W divisible by 32)
        # ------------------------------------------------------------------ #
        x_pad, pad_hw = _pad_to_stride(x, _RESNET_STRIDE)
        H_pad, W_pad = x_pad.shape[-2], x_pad.shape[-1]

        # Safety check: token count at bottleneck must not exceed GDN-2 limit
        H_bot = H_pad // _RESNET_STRIDE
        W_bot = W_pad // _RESNET_STRIDE
        n_tokens = H_bot * W_bot
        assert n_tokens <= _MAX_SEQ_LEN, (
            f"Bottleneck token count {n_tokens} (H_bot={H_bot}, W_bot={W_bot}) "
            f"exceeds GDN-2 limit {_MAX_SEQ_LEN}.  "
            f"Input (after pad) {H_pad}x{W_pad} is too large.  "
            f"Max supported input: {_RESNET_STRIDE * 32}x{_RESNET_STRIDE * 32}"
        )

        # ------------------------------------------------------------------ #
        # 2. smp encoder: extract multi-scale features
        # ------------------------------------------------------------------ #
        # smp.Unet encoder.forward(x) returns:
        #   features: list of tensors [skip0, skip1, ..., skip_n, bottleneck]
        #   For resnet34 depth=5:
        #     features[0]: (B, 3,  H,    W)    — initial (identity or stem)
        #     features[1]: (B, 64, H/2,  W/2)  — after layer0 (maxpool)
        #     features[2]: (B, 64, H/4,  W/4)  — after layer1
        #     features[3]: (B, 128,H/8,  W/8)  — after layer2
        #     features[4]: (B, 256,H/16, W/16) — after layer3
        #     features[5]: (B, 512,H/32, W/32) — after layer4  ← bottleneck
        # SOURCE: qubvel-org/segmentation_models_pytorch, decoders/unet/decoder.py
        features: List[torch.Tensor] = self._base.encoder(x_pad)

        # ------------------------------------------------------------------ #
        # 3. Insert GDN-2 at bottleneck: features[-1] shape (B, 512, H_bot, W_bot)
        # ------------------------------------------------------------------ #
        o_seq = None
        memory_states = None

        if self.use_memory and self.memory is not None:
            bottleneck_feat = features[-1]   # (B, 512, H_bot, W_bot)

            # GDN2MemoryModule.forward: (B,C,H,W) → (B,C,H,W) same shape
            # return_memory=True also gives per-direction final states + _last_o_seq
            if return_reid_ctx:
                bottleneck_feat, memory_states = self.memory(
                    bottleneck_feat, return_memory=True
                )
                o_seq = self.memory._last_o_seq  # (B, T, n_heads*d_head)
            else:
                bottleneck_feat = self.memory(bottleneck_feat)

            # Put modified bottleneck back into feature list
            # NOTE: features is a list from smp encoder; safe to mutate index in-place
            features[-1] = bottleneck_feat

            # TODO headline 定后接 (路A/路B gradient boundary):
            # 路A (detach ReID, not memory):
            #   memory path stays attached; ReID head uses o_seq.detach()
            #   (already handled inside ReIDReadoutHead via detach1/2/3 barriers)
            # 路B (detach bottleneck into memory):
            #   features[-1] = self.memory(features[-1].detach())
            #   + optional residual path from un-detached features[-1]
            # Current: no detach at this level (headline-agnostic; matches UNetGDN2 default)

        # ------------------------------------------------------------------ #
        # 4. smp decoder + segmentation head
        # ------------------------------------------------------------------ #
        # smp decoder expects the full features list (skip connections + bottleneck)
        decoder_output = self._base.decoder(*features)
        # Decoder output shape: (B, decoder_channels[0], H_pad, W_pad)
        # (smp bilinear decoder upsamples back to input resolution)

        logits_pad = self._base.segmentation_head(decoder_output)
        # logits_pad: (B, classes, H_pad, W_pad)

        # ------------------------------------------------------------------ #
        # 5. Crop back to original spatial size
        # ------------------------------------------------------------------ #
        logits = _crop_to_original(logits_pad, pad_hw, H_orig, W_orig)
        # logits: (B, classes, H_orig, W_orig)

        if return_reid_ctx:
            reid_ctx: Dict = {
                'o_seq': o_seq,               # (B, T, n_heads*d_head) or None
                'memory_state': memory_states, # List[Optional[Tensor]] or None
                'H_bot': H_bot,
                'W_bot': W_bot,
                # TODO headline 定后接:
                # 'dec_feat': <decoder layer feature for ReID local feat>
                # Requires hooking into smp decoder intermediates; defer until
                # headline (path-A or path-B) is confirmed.
            }
            return logits, reid_ctx

        return logits

    # ---------------------------------------------------------------------- #
    #  Smoke-test entry point (run by MAIN LINE, NOT by this coder)
    # ---------------------------------------------------------------------- #

    @staticmethod
    def _smoke(device: str = 'cpu') -> None:  # pragma: no cover
        """
        Minimal forward pass smoke test.
        DO NOT run here — invoke from main line:
            python src/models/unet_smp_gdn2.py --smoke 1
        """
        import sys
        print(f"[smoke] device={device}")
        # Build model (random init, no imagenet weights for speed)
        model = UNetSmpGDN2(
            in_channels=1, classes=1,
            encoder_name='resnet34', encoder_weights=None,
            use_memory=True, backend='naive',
        )
        model.eval().to(device)
        # 576×608 = padded DRIVE full image size (32-multiple)
        x = torch.randn(1, 1, 576, 608, device=device)
        with torch.no_grad():
            out = model(x)
        print(f"[smoke] input {tuple(x.shape)} → output {tuple(out.shape)}")
        assert out.shape == (1, 1, 576, 608), f"Shape mismatch: {out.shape}"
        # Test with odd-size input (pad/crop round-trip)
        x2 = torch.randn(1, 1, 565, 584, device=device)
        with torch.no_grad():
            out2 = model(x2)
        assert out2.shape == (1, 1, 565, 584), f"Crop mismatch: {out2.shape}"
        print(f"[smoke] pad/crop round-trip OK: {tuple(x2.shape)} → {tuple(out2.shape)}")
        print("[smoke] PASS")
        sys.exit(0)


# --------------------------------------------------------------------------- #
#  CLI smoke entry
# --------------------------------------------------------------------------- #

if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--smoke', type=int, default=0,
                        help='1 = run smoke test (main line use only)')
    parser.add_argument('--device', default='cpu')
    args = parser.parse_args()
    if args.smoke:
        UNetSmpGDN2._smoke(device=args.device)
