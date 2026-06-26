"""
ours_gdn2.py — Adapter for our method: UNetGDN2 (Mechanism B + Associative Memory).

Purpose:
  - 把现有 UNetGDN2 包成 BaselineAdapter，让 Ours 也走 evaluate.py 同一套台子。
  - 自证公平：Ours 走和所有 baseline 完全相同的评估路径（无后门）。
  - 只 import 现有 models/unet_gdn2.py，不修改它。

Kind:
  architecture — 变量是整套 Ours 模型+关联记忆（UNetGDN2），尊重官方所有配方。
  因此 build_loss / build_optimizer 返回 Ours 自己的训练配置，不强制统一。

超参状态：
  lr: 1e-3（train_pilot.py 默认值，已用于 P1/P2 pilot）
  optimizer: Adam
  loss: BCE + Dice 各 0.5 weighted（combined_loss in train_pilot.py）
  scheduler: ReduceLROnPlateau（train_pilot 配置）

NOTE: 这些超参已在 train_pilot.py 中确认；若主线后续改超参，同步更新此文件。
"""

from __future__ import annotations

import sys
import types
from pathlib import Path
from typing import Any, Dict, Optional

import torch
import torch.nn as nn
import torch.nn.functional as F

# 确保 src/ 在 sys.path（多 cwd 场景兼容）
_src_dir = Path(__file__).parent.parent.parent
if str(_src_dir) not in sys.path:
    sys.path.insert(0, str(_src_dir))

from baselines.base_adapter import (
    BaselineAdapter,
    ENV_MAIN,
    KIND_ARCHITECTURE,
)
from baselines.registry import register


# --------------------------------------------------------------------------- #
#  Loss helpers（复刻 train_pilot.py 中的实现，保持零偏离）
# --------------------------------------------------------------------------- #

def _dice_loss(pred_prob: torch.Tensor, target: torch.Tensor,
               mask: torch.Tensor, eps: float = 1e-6) -> torch.Tensor:
    """Soft Dice loss inside FOV mask — same as train_pilot.py."""
    pred_flat = (pred_prob * mask).reshape(pred_prob.shape[0], -1)
    tgt_flat = (target * mask).reshape(target.shape[0], -1)
    intersection = (pred_flat * tgt_flat).sum(1)
    denom = pred_flat.sum(1) + tgt_flat.sum(1)
    dice = (2 * intersection + eps) / (denom + eps)
    return 1.0 - dice.mean()


def _bce_loss(logits: torch.Tensor, target: torch.Tensor,
              mask: torch.Tensor) -> torch.Tensor:
    """BCE inside FOV mask — same as train_pilot.py."""
    bce = F.binary_cross_entropy_with_logits(logits, target, reduction='none')
    n_valid = mask.sum().clamp(min=1)
    return (bce * mask).sum() / n_valid


class _BCEDiceLoss:
    """Callable loss: 0.5 * BCE + 0.5 * Dice (train_pilot.py 默认配置)."""

    def __init__(self, bce_weight: float = 0.5, dice_weight: float = 0.5):
        self.bce_w = bce_weight
        self.dice_w = dice_weight

    def __call__(
        self,
        logits: torch.Tensor,
        target: torch.Tensor,
        fov_mask: torch.Tensor,
    ) -> torch.Tensor:
        prob = torch.sigmoid(logits)
        return (self.bce_w * _bce_loss(logits, target, fov_mask)
                + self.dice_w * _dice_loss(prob, target, fov_mask))


# --------------------------------------------------------------------------- #
#  Adapter
# --------------------------------------------------------------------------- #

@register
class OursGDN2Adapter(BaselineAdapter):
    """
    Ours: UNetGDN2 with Mechanism B (Frangi-modulated erase/write gates)
    + GDN-2 associative memory module.

    完整模型是变量（architecture kind），尊重 Ours 训练配方（不统一）。
    Ours 走 evaluate.py 同一评估台子（自证公平）。
    """

    name: str = "ours_gdn2"
    kind: str = KIND_ARCHITECTURE
    source_repo: str = "internal — project/meeting/ACCV/gdn2vessel/src/models/unet_gdn2.py"
    env_tag: str = ENV_MAIN

    def build_model(self, cfg: Dict[str, Any]) -> nn.Module:
        """
        构建 UNetGDN2。

        cfg keys (from baselines/ours_gdn2.yaml):
          base_ch    : int (default 32)
          use_memory : bool (default True)
          backend    : 'naive' | 'chunk' (default 'naive')
          in_ch      : int (default 1)
          out_ch     : int (default 1)
        """
        # 懒 import：FLA 在 mamba 环境才装，main env 靠 mock 或已装 FLA
        from models.unet_gdn2 import UNetGDN2

        base_ch = int(cfg.get("base_ch", 32))
        use_memory = bool(cfg.get("use_memory", True))
        backend = str(cfg.get("backend", "naive"))
        in_ch = int(cfg.get("in_ch", 1))
        out_ch = int(cfg.get("out_ch", 1))

        return UNetGDN2(
            in_ch=in_ch,
            out_ch=out_ch,
            base_ch=base_ch,
            use_memory=use_memory,
            backend=backend,
        )

    def build_loss(self, cfg: Dict[str, Any]) -> _BCEDiceLoss:
        """
        0.5 BCE + 0.5 Dice（train_pilot.py combined_loss 配置）。
        """
        bce_w = float(cfg.get("loss_bce_weight", 0.5))
        dice_w = float(cfg.get("loss_dice_weight", 0.5))
        return _BCEDiceLoss(bce_weight=bce_w, dice_weight=dice_w)

    def build_optimizer(
        self,
        model: nn.Module,
        cfg: Dict[str, Any],
    ) -> torch.optim.Optimizer:
        """
        Adam，lr=1e-3（train_pilot.py 默认）。
        """
        lr = float(cfg.get("lr", 1e-3))
        return torch.optim.Adam(model.parameters(), lr=lr)

    def build_scheduler(
        self,
        optimizer: torch.optim.Optimizer,
        cfg: Dict[str, Any],
    ) -> Optional[Any]:
        """
        ReduceLROnPlateau on val Dice（train_pilot.py 配置）。
        """
        return torch.optim.lr_scheduler.ReduceLROnPlateau(
            optimizer,
            mode="max",
            factor=float(cfg.get("scheduler_factor", 0.5)),
            patience=int(cfg.get("scheduler_patience", 10)),
            min_lr=float(cfg.get("scheduler_min_lr", 1e-6)),
        )

    def preprocess_cfg(self) -> Dict[str, Any]:
        """
        Ours: 绿通道 + CLAHE，单通道 (B,1,H,W)，全图训练（padding 到 32 倍数）。
        与 drive.py DRIVEDataset 默认配置一致。
        """
        return {
            "channels": "green_clahe",
            "normalize": {"mean": [0.5], "std": [0.1]},
            "input_mode": "fullimg",
            "patch_size": None,
            "clahe": True,
            "extra": {
                "pad_multiple": 32,
                "clahe_clip": 2.0,
                "note": "Same as DRIVEDataset defaults in src/datasets/drive.py",
            },
        }

    # GDN-2 bottleneck = H/16 × W/16 tokens; hard limit = 1024.
    # Training size: 512×512 → 32×32 = 1024 (exactly at limit).
    # Native DRIVE 565×584 → 35×36 = 1260 > 1024 → assert fires.
    # Fix: if bottleneck token count > 1024, resize input to 512×512
    # (the training resolution), forward, then upsample output back to
    # the original padded size H'×W'.  This is the method's hard capacity
    # ceiling — eval runs at max feasible resolution (512²) and upsamples
    # predictions back to native GT size.  evaluate.py then crops to
    # (orig_H, orig_W) for metric computation.
    _GDN2_MAX_TOKENS: int = 1024
    _GDN2_STRIDE: int = 16       # total spatial stride of 4 MaxPool2d(2) blocks
    _GDN2_TRAIN_SIZE: int = 512  # training resolution (32×32 = 1024 tokens exactly)

    def forward_adapt(
        self,
        model: nn.Module,
        x: torch.Tensor,
        device: torch.device,
    ) -> torch.Tensor:
        """
        全图推理：UNetGDN2 整图训练模型。

        分辨率兼容处理（GDN-2 容量天花板）：
          训练尺寸 512×512 → bottleneck 32×32 = 1024 token（恰好上限）。
          eval native DRIVE 565×584 → bottleneck 35×36 = 1260 > 1024 → assert 崩。
          修复：bottleneck token 超限时，resize 输入到 512×512（训练分辨率）→
                forward → F.interpolate 输出回原 H'×W'。
          evaluate.py 之后做 logits[:, :, :orig_H, :orig_W] crop 回 native GT 尺寸。
          这是方法固有容量限制（benchmark 诚实注记：GDN-2 容量限制分辨率）。

        输入 (B,1,H,W) → 输出 (B,1,H,W) logits（输出尺寸 = 输入尺寸）。
        """
        _, _, H, W = x.shape
        out_H, out_W = H, W  # 目标输出尺寸 = 输入尺寸（evaluate.py 期望一致）

        # 检查 bottleneck token 数是否超限
        bot_H = H // self._GDN2_STRIDE
        bot_W = W // self._GDN2_STRIDE
        tokens = bot_H * bot_W

        if tokens > self._GDN2_MAX_TOKENS:
            # resize 到训练分辨率 512×512（不超 1024 token）
            x_fwd = F.interpolate(
                x,
                size=(self._GDN2_TRAIN_SIZE, self._GDN2_TRAIN_SIZE),
                mode='bilinear',
                align_corners=False,
            )
        else:
            x_fwd = x

        model.eval()
        with torch.no_grad():
            logits = model(x_fwd)

        # 若做了 resize，把输出 upsample 回原始 H'×W'
        if tokens > self._GDN2_MAX_TOKENS:
            logits = F.interpolate(
                logits,
                size=(out_H, out_W),
                mode='bilinear',
                align_corners=False,
            )

        # 输出形状断言
        assert logits.shape[1] == 1 and logits.ndim == 4, (
            f"OursGDN2Adapter.forward_adapt: expected (B,1,H,W), got {logits.shape}"
        )
        assert logits.shape[2] == out_H and logits.shape[3] == out_W, (
            f"OursGDN2Adapter.forward_adapt: output size mismatch, "
            f"expected ({out_H},{out_W}), got {logits.shape[2:]}"
        )
        return logits
