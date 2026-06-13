"""E10 SOTA baseline — Real-ESRGAN (x2) zero-shot wrapper, used as an enhancer via SR round-trip.

官方 arch 逐字 vendor 于 baselines/archs/rrdbnet_arch.py (XPixelGroup/BasicSR RRDBNet,
basicsr.utils.registry / basicsr.archs.arch_util 依赖已内联, 无 basicsr import).
权重: RealESRGAN_x2plus.pth, ckpt['params_ema'] -> RRDBNet(num_in_ch=3, num_out_ch=3,
num_feat=64, num_block=23, num_grow_ch=32, scale=2).

契约: build(device, weights_dir) -> obj; obj(x_low, q) -> enh
  x_low : [B,3,256,256] RGB [0,1], 已在 device
  enh   : [B,3,256,256] RGB [0,1], 同 device

RRDBNet 训练于 [0,1] RGB, 不做 ImageNet 归一化. Real-ESRGAN 是超分模型, 这里当增强用:
先 1/2 下采样再 x2 SR 回原尺寸, 等效一次去退化 round-trip (sr_roundtrip helper).
"""
from __future__ import annotations

import torch

from baselines.base_enhancer import BaselineEnhancer, sr_roundtrip
from baselines.archs.rrdbnet_arch import RRDBNet

DISPLAY_NAME = "Real-ESRGAN (x2)"


class _Wrap(BaselineEnhancer):
    def enhance(self, x: torch.Tensor) -> torch.Tensor:
        return sr_roundtrip(x, lambda lo: self.net(lo), scale=2)


def build(device, weights_dir="checkpoints/baselines"):
    net = RRDBNet(num_in_ch=3, num_out_ch=3, num_feat=64, num_block=23, num_grow_ch=32, scale=2)
    ckpt = torch.load(
        f"{weights_dir}/realesrgan/RealESRGAN_x2plus.pth",
        map_location=device,
        weights_only=False,
    )
    net.load_state_dict(ckpt.get("params_ema", ckpt.get("params", ckpt)), strict=True)
    return _Wrap(net, device)
