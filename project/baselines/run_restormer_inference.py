"""E10 SOTA baseline — Restormer (real-world denoising) zero-shot wrapper.

官方 arch 逐字 vendor 于 baselines/archs/restormer_arch.py (swz30/Restormer).
权重: real_denoising.pth, ckpt['params'] -> Restormer(dim=48, LayerNorm_type='WithBias') (默认参数).

契约: build(device, weights_dir) -> obj; obj(x_low, q) -> enh
  x_low : [B,3,256,256] RGB [0,1], 已在 device
  enh   : [B,3,256,256] RGB [0,1], 同 device

Restormer 训练于 [0,1] RGB, 不做 ImageNet 归一化; 全卷积+transformer 任意尺寸可过,
256x256 无需 pad_to_multiple.
"""
from __future__ import annotations

import torch

from baselines.base_enhancer import BaselineEnhancer
from baselines.archs.restormer_arch import Restormer

DISPLAY_NAME = "Restormer (real-DN)"


class _Wrap(BaselineEnhancer):
    def enhance(self, x: torch.Tensor) -> torch.Tensor:
        return self.net(x)


def build(device, weights_dir="checkpoints/baselines"):
    net = Restormer()  # 默认参数 (dim=48, LayerNorm_type='WithBias') 与 real_denoising 权重匹配
    ckpt = torch.load(
        f"{weights_dir}/restormer/real_denoising.pth",
        map_location=device,
        weights_only=False,
    )
    net.load_state_dict(ckpt.get("params", ckpt), strict=True)
    return _Wrap(net, device)
