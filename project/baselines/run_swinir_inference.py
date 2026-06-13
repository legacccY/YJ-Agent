"""E10 SOTA baseline — SwinIR (colorDN-M) zero-shot 增强 wrapper.

权重: 005_colorDN_DFWB_s128w8_SwinIR-M_noise25.pth (官方 color denoising, sigma=25, ckpt key 'params').
契约见 baselines/base_enhancer.py: build(device, weights_dir) -> obj, obj(x, q) -> enh, [0,1] RGB 256.
window_size=8, 256 已整除, pad_to_multiple 仅作兜底.
"""
from __future__ import annotations

import torch

from baselines.base_enhancer import BaselineEnhancer, pad_to_multiple, crop_to
from baselines.archs.swinir_arch import SwinIR

DISPLAY_NAME = "SwinIR (colorDN)"


def build(device, weights_dir="checkpoints/baselines"):
    net = SwinIR(
        upscale=1, in_chans=3, img_size=128, window_size=8, img_range=1.,
        depths=[6, 6, 6, 6, 6, 6], embed_dim=180, num_heads=[6, 6, 6, 6, 6, 6],
        mlp_ratio=2, upsampler='', resi_connection='1conv',
    )
    ckpt_path = f"{weights_dir}/swinir/005_colorDN_DFWB_s128w8_SwinIR-M_noise25.pth"
    ck = torch.load(ckpt_path, map_location=device, weights_only=False)
    net.load_state_dict(ck.get('params', ck), strict=True)
    return _Wrap(net, device)


class _Wrap(BaselineEnhancer):
    def enhance(self, x: torch.Tensor) -> torch.Tensor:
        # x: [B,3,256,256] RGB [0,1]. img_range=1. -> 不做 imagenet norm.
        xp, hw = pad_to_multiple(x, 8)
        out = self.net(xp)
        return crop_to(out, hw)
