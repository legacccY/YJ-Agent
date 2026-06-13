"""E10 baseline — MIRNet-v2 (LOL-enhancement), zero-shot, no quality-conditioning.

官方 repo: https://github.com/swz30/MIRNetv2
arch vendor 自: basicsr/models/archs/mirnet_v2_arch.py (逐字, 见 baselines/archs/mirnetv2_arch.py)
权重: enhancement_lol.pth, ckpt key 'params', 与 MIRNet_v2() 默认构造参数匹配
  (inp_channels=3, out_channels=3, n_feat=80, chan_factor=1.5, n_RRG=4, n_MRB=2,
   height=3, width=2, scale=1, bias=False, task=None).

契约见 baselines/base_enhancer.py: build(device, weights_dir) -> callable(x_low, q) -> enh
"""
from __future__ import annotations

import torch

from baselines.base_enhancer import BaselineEnhancer
from baselines.archs.mirnetv2_arch import MIRNet_v2

DISPLAY_NAME = "MIRNet-v2 (LOL-enh)"


class _Wrap(BaselineEnhancer):
    def enhance(self, x: torch.Tensor) -> torch.Tensor:
        # x: [B,3,256,256] RGB [0,1], 官方无 imagenet norm, 残差输出已在 forward 内 += inp_img
        return self.net(x)


def build(device, weights_dir="checkpoints/baselines"):
    net = MIRNet_v2()
    ckpt_path = f"{weights_dir}/mirnetv2/enhancement_lol.pth"
    ck = torch.load(ckpt_path, map_location=device, weights_only=False)
    net.load_state_dict(ck.get("params", ck), strict=True)
    return _Wrap(net, device)
