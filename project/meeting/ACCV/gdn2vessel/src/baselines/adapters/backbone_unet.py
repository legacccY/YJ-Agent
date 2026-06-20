"""
backbone_unet.py — Adapter for the unified backbone U-Net (loss-class baselines).

Purpose:
  - BASELINE_SPEC §2.4 反向公平点：loss 类 baseline（clDice/cbDice/SkelRecall）的
    统一 backbone = src/models/unet.py（base_ch32 标准 U-Net），
    与 Ours 的 CNN 主干同款，确保 loss 增益能干净归因到「loss」而非「主干差异」。
  - 本 adapter 代表「backbone + 默认 BCE+Dice loss」，
    各 loss 类 adapter（fr_unet_cldice / cbdice / skeleton_recall）
    可以 subclass 或直接替换 build_loss。

Kind:
  loss — 变量是外挂的 topology loss。
  backbone + 训练超参钉死统一（这是 BASELINE_SPEC §2.4 的「反向公平」设计）。

统一超参（loss 类固定，不得 override）：
  backbone   : UNet(in_ch=1, out_ch=1, base_ch=32)
  optimizer  : Adam, lr=1e-3
  scheduler  : ReduceLROnPlateau mode=max factor=0.5 patience=10 min_lr=1e-6
  epochs     : 100（与 Ours 主实验对齐，审稿人可对比）
  batch_size : 2
  input      : green_clahe 单通道全图（与 Ours 相同）
  loss       : 由子类 override（本类默认 BCE+Dice 作 baseline 的 baseline）

NOTE: 若主线决策改统一超参，只需改本文件的 _UNIFIED_* 常量。
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, Optional

import torch
import torch.nn as nn
import torch.nn.functional as F

# 确保 src/ 在 sys.path
_src_dir = Path(__file__).parent.parent.parent
if str(_src_dir) not in sys.path:
    sys.path.insert(0, str(_src_dir))

from baselines.base_adapter import (
    BaselineAdapter,
    ENV_MAIN,
    KIND_LOSS,
)
from baselines.registry import register


# --------------------------------------------------------------------------- #
#  统一超参常量（BASELINE_SPEC §2.4 loss 类固定不可 override）
# --------------------------------------------------------------------------- #

_UNIFIED_BASE_CH: int = 32
_UNIFIED_LR: float = 1e-3
_UNIFIED_SCHEDULER_FACTOR: float = 0.5
_UNIFIED_SCHEDULER_PATIENCE: int = 10
_UNIFIED_SCHEDULER_MIN_LR: float = 1e-6


# --------------------------------------------------------------------------- #
#  Loss helpers
# --------------------------------------------------------------------------- #

def _dice_loss(pred_prob: torch.Tensor, target: torch.Tensor,
               mask: torch.Tensor, eps: float = 1e-6) -> torch.Tensor:
    pred_flat = (pred_prob * mask).reshape(pred_prob.shape[0], -1)
    tgt_flat = (target * mask).reshape(target.shape[0], -1)
    intersection = (pred_flat * tgt_flat).sum(1)
    denom = pred_flat.sum(1) + tgt_flat.sum(1)
    dice = (2 * intersection + eps) / (denom + eps)
    return 1.0 - dice.mean()


def _bce_loss(logits: torch.Tensor, target: torch.Tensor,
              mask: torch.Tensor) -> torch.Tensor:
    bce = F.binary_cross_entropy_with_logits(logits, target, reduction='none')
    n_valid = mask.sum().clamp(min=1)
    return (bce * mask).sum() / n_valid


class _UnifiedBCEDiceLoss:
    """
    统一 backbone 的默认 loss：0.5 BCE + 0.5 Dice（与 Ours 同款）。
    loss 类 adapter 通过 build_loss() override 替换此 loss。

    signature: loss_fn(logits, target, fov_mask) -> scalar tensor
    """

    def __call__(
        self,
        logits: torch.Tensor,
        target: torch.Tensor,
        fov_mask: torch.Tensor,
    ) -> torch.Tensor:
        prob = torch.sigmoid(logits)
        return (0.5 * _bce_loss(logits, target, fov_mask)
                + 0.5 * _dice_loss(prob, target, fov_mask))


# --------------------------------------------------------------------------- #
#  Adapter
# --------------------------------------------------------------------------- #

@register
class BackboneUNetAdapter(BaselineAdapter):
    """
    统一 backbone U-Net adapter（loss 类 baseline 的公共主干）。

    BASELINE_SPEC §2.4：loss 类 baseline 必须共用此 backbone，
    backbone 超参钉死，确保对比公平。

    此 adapter 也可直接当「UNet + BCE+Dice 对照」出现在结果表中。
    """

    name: str = "backbone_unet"
    kind: str = KIND_LOSS
    source_repo: str = (
        "internal — project/meeting/ACCV/gdn2vessel/src/models/unet.py"
    )
    env_tag: str = ENV_MAIN

    def build_model(self, cfg: Dict[str, Any]) -> nn.Module:
        """
        构建统一 backbone UNet(in_ch=1, out_ch=1, base_ch=32)。

        ⚠️ loss 类强制约束：base_ch 固定为 _UNIFIED_BASE_CH=32，
        即使 cfg 中传入不同值也会被忽略（写 WARNING 到 stderr）。
        这确保 loss 类的 backbone 参数量固定，审稿人可信。

        Args:
            cfg: dict，yaml 解析结果（base_ch 被忽略）。
        """
        from models.unet import UNet

        # 强制统一 base_ch
        cfg_base_ch = cfg.get("base_ch", _UNIFIED_BASE_CH)
        if int(cfg_base_ch) != _UNIFIED_BASE_CH:
            import sys as _sys
            print(
                f"[BackboneUNetAdapter] WARNING: cfg.base_ch={cfg_base_ch} "
                f"ignored for loss-class adapter. Using fixed {_UNIFIED_BASE_CH}.",
                file=_sys.stderr,
            )

        return UNet(in_ch=1, out_ch=1, base_ch=_UNIFIED_BASE_CH)

    def build_loss(self, cfg: Dict[str, Any]) -> _UnifiedBCEDiceLoss:
        """
        默认 loss：0.5 BCE + 0.5 Dice（loss 类子类 override 此方法）。
        """
        return _UnifiedBCEDiceLoss()

    def build_optimizer(
        self,
        model: nn.Module,
        cfg: Dict[str, Any],
    ) -> torch.optim.Optimizer:
        """
        统一 Adam，lr=_UNIFIED_LR=1e-3。
        loss 类 adapter 的 optimizer 必须一致（隔离 loss 贡献）。

        ⚠️ loss 类强制约束：cfg 中的 lr 值被忽略，强制使用 _UNIFIED_LR。
        """
        cfg_lr = cfg.get("lr", _UNIFIED_LR)
        if float(cfg_lr) != _UNIFIED_LR:
            import sys as _sys
            print(
                f"[BackboneUNetAdapter] WARNING: cfg.lr={cfg_lr} "
                f"ignored for loss-class adapter. Using fixed {_UNIFIED_LR}.",
                file=_sys.stderr,
            )
        return torch.optim.Adam(model.parameters(), lr=_UNIFIED_LR)

    def build_scheduler(
        self,
        optimizer: torch.optim.Optimizer,
        cfg: Dict[str, Any],
    ) -> Optional[Any]:
        """统一 scheduler：ReduceLROnPlateau（钉死，loss 类共用）。"""
        return torch.optim.lr_scheduler.ReduceLROnPlateau(
            optimizer,
            mode="max",
            factor=_UNIFIED_SCHEDULER_FACTOR,
            patience=_UNIFIED_SCHEDULER_PATIENCE,
            min_lr=_UNIFIED_SCHEDULER_MIN_LR,
        )

    def preprocess_cfg(self) -> Dict[str, Any]:
        """
        统一 backbone 预处理：绿通道 + CLAHE，单通道 (B,1,H,W)，全图。
        与 Ours 完全一致（审稿人可对比：loss 增益不来自预处理差异）。
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
                "note": (
                    "BASELINE_SPEC §2.4: loss-class adapter must use same "
                    "preprocessing as Ours to isolate loss contribution."
                ),
            },
        }

    def forward_adapt(
        self,
        model: nn.Module,
        x: torch.Tensor,
        device: torch.device,
    ) -> torch.Tensor:
        """
        全图推理：标准 UNet，整图直接 forward。
        输入 (B,1,H,W) → 输出 (B,1,H,W) logits。
        """
        model.eval()
        with torch.no_grad():
            logits = model(x)
        assert logits.shape[1] == 1 and logits.ndim == 4, (
            f"BackboneUNetAdapter.forward_adapt: expected (B,1,H,W), got {logits.shape}"
        )
        return logits
