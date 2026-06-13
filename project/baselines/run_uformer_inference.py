"""E10 baseline — Uformer-B (CVPR22, ZhendongWang6/Uformer), SIDD 真实噪声去噪权重.

zero-shot: 官方 Uformer_B 直接对 256x256 RGB[0,1] 输入做去噪式复原, 无 quality-conditioning.
契约见 baselines/base_enhancer.py: build(device, weights_dir) -> callable(x_low, q) -> enh.

构造参数核对依据 (ZhendongWang6/Uformer, utils/model_utils.py::get_arch, arch=='Uformer_B'):
    Uformer(img_size=train_ps, embed_dim=32, win_size=8, token_projection='linear',
            token_mlp='leff', depths=[1,2,8,8,2,8,8,2,1], modulator=True, dd_in=3)
  num_heads 未覆盖, 用 model.py Uformer.__init__ 默认值 [1,2,4,8,16,16,8,4,2].
  img_size 仅影响 relative-position 表的 input_resolution / flops 打印, 权重 shape
  与 img_size 无关 (window-based attention, win_size=8 固定), 256 可整除 2**4*8=128, 安全.

ckpt 加载依据 (utils/model_utils.py::load_checkpoint):
    checkpoint["state_dict"], 部分权重 key 带 'module.' 前缀 (DataParallel 训练), 需 strip.
"""
from __future__ import annotations

import torch

from baselines.base_enhancer import BaselineEnhancer
from baselines.archs.uformer_arch import Uformer

DISPLAY_NAME = "Uformer-B (SIDD-DN)"


def build(device, weights_dir="checkpoints/baselines"):
    net = Uformer(
        img_size=256,
        embed_dim=32,
        win_size=8,
        token_projection="linear",
        token_mlp="leff",
        depths=[1, 2, 8, 8, 2, 8, 8, 2, 1],
        modulator=True,
        dd_in=3,
    )

    ckpt_path = f"{weights_dir}/uformer/Uformer_B.pth"
    ckpt = torch.load(ckpt_path, map_location=device, weights_only=False)
    sd = ckpt.get("state_dict", ckpt)
    sd = {(k[7:] if k.startswith("module.") else k): v for k, v in sd.items()}
    net.load_state_dict(sd, strict=True)

    return _Wrap(net, device)


class _Wrap(BaselineEnhancer):
    """Uformer 全卷积+窗口注意力, 256x256 直接过, 不做 ImageNet 归一化."""

    def enhance(self, x_low: torch.Tensor) -> torch.Tensor:
        return self.net(x_low)
