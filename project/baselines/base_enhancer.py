"""E10 SOTA baseline enhancer — 公共契约 + helper.

契约 (每个 baselines/run_<method>_inference.py 必须满足):
    build(device, weights_dir="checkpoints/baselines") -> callable
    返回对象 obj, 调用签名 obj(x_low, q) -> enh
      x_low : torch.FloatTensor [B,3,256,256] RGB, 值域 [0,1] (退化图, 已在 device)
      q     : visiscore 质量输出 (baseline 忽略 —— 无 quality-conditioning 正是对比点)
      enh   : torch.FloatTensor [B,3,256,256] RGB, 值域 [0,1], 同 device
    与 VisiEnhanceNet.forward(x, q) 签名一致, 可直接塞进 eval_diag_paired.collect_all
    的 models dict, 跑同一套 degrade(moderate)@256 -> enh -> CenterCrop224 -> B3 协议.

设计:
  - 各方法官方 arch 逐字 vendor 到 baselines/archs/<method>_arch.py (权重 key 精确匹配).
  - 各方法自己的归一化/分辨率怪癖在 wrapper 内吸收, 对外永远 [0,1] RGB 256.
  - 推理 torch.no_grad + eval(), 不训练.
"""
from __future__ import annotations

import torch
import torch.nn.functional as F


def imagenet_norm(x: torch.Tensor) -> torch.Tensor:
    """[0,1] RGB -> ImageNet 标准化 (部分 transformer 复原网络用)."""
    mean = x.new_tensor([0.485, 0.456, 0.406]).view(1, 3, 1, 1)
    std = x.new_tensor([0.229, 0.224, 0.225]).view(1, 3, 1, 1)
    return (x - mean) / std


def imagenet_denorm(x: torch.Tensor) -> torch.Tensor:
    mean = x.new_tensor([0.485, 0.456, 0.406]).view(1, 3, 1, 1)
    std = x.new_tensor([0.229, 0.224, 0.225]).view(1, 3, 1, 1)
    return x * std + mean


def pad_to_multiple(x: torch.Tensor, m: int):
    """右/下反射 pad 到 m 的倍数, 返回 (padded, (h, w)) 供裁回原尺寸.
    SwinIR/Uformer/Restormer 要求边长被 window/patch 整除; 256 多数已满足, 留兜底."""
    h, w = x.shape[-2:]
    ph, pw = (m - h % m) % m, (m - w % m) % m
    if ph or pw:
        x = F.pad(x, (0, pw, 0, ph), mode="reflect")
    return x, (h, w)


def crop_to(x: torch.Tensor, hw) -> torch.Tensor:
    h, w = hw
    return x[..., :h, :w]


def sr_roundtrip(x: torch.Tensor, model_fn, scale: int) -> torch.Tensor:
    """超分模型当增强用: 先 downsample 1/scale -> SR 回原尺寸 -> 等效去噪/复原.
    Real-ESRGAN(x2/x4)/SwinIR-SR 用. model_fn 接 [0,1] RGB 返回 [0,1] RGB (×scale)."""
    h, w = x.shape[-2:]
    lo = F.interpolate(x, scale_factor=1.0 / scale, mode="bicubic", align_corners=False)
    sr = model_fn(lo.clamp(0, 1))
    return F.interpolate(sr, size=(h, w), mode="bicubic", align_corners=False).clamp(0, 1)


class BaselineEnhancer:
    """薄基类: 子类实现 enhance(x_low)->enh; __call__ 吸收 q 并 no_grad/clamp."""

    def __init__(self, net, device):
        self.net = net.to(device).eval()
        self.device = device

    @torch.no_grad()
    def __call__(self, x_low: torch.Tensor, q=None) -> torch.Tensor:
        return self.enhance(x_low.to(self.device)).clamp(0, 1)

    def enhance(self, x_low: torch.Tensor) -> torch.Tensor:  # noqa
        raise NotImplementedError
