"""E10 SOTA baseline — NAFNet (ECCV22, megvii-research/NAFNet), SIDD 去噪权重, zero-shot.

契约见 baselines/base_enhancer.py 顶部注释:
    build(device, weights_dir) -> obj
    obj(x_low, q) -> enh   # x_low/enh: [B,3,256,256] RGB [0,1], 同 device

NAFNet 与我方 VisiEnhanceNet 同源 (NAFBlock) -> 最干净消融线
"NAFNet 原版 vs +FiLM+DP"。构造参数须与 SIDD-width64 权重精确对齐:
  width=64, enc_blk_nums=[2,2,4,8], middle_blk_num=12, dec_blk_nums=[2,2,2,2]
ckpt key: 'params'. 训练于 [0,1] RGB, 不做 ImageNet 归一化。
"""
from __future__ import annotations

import torch

from baselines.base_enhancer import BaselineEnhancer
from baselines.archs.nafnet_arch import NAFNet

DISPLAY_NAME = "NAFNet (SIDD-DN)"


class _Wrap(BaselineEnhancer):
    """NAFNet 推理: [0,1] RGB 256 -> [0,1] RGB 256, 不做额外归一化."""

    def enhance(self, x: torch.Tensor) -> torch.Tensor:
        return self.net(x)


def build(device, weights_dir: str = "checkpoints/baselines"):
    net = NAFNet(
        img_channel=3,
        width=64,
        enc_blk_nums=[2, 2, 4, 8],
        middle_blk_num=12,
        dec_blk_nums=[2, 2, 2, 2],
    )
    ckpt_path = f"{weights_dir}/nafnet/NAFNet-SIDD-width64.pth"
    ck = torch.load(ckpt_path, map_location=device, weights_only=False)
    net.load_state_dict(ck.get("params", ck), strict=True)
    return _Wrap(net, device)
