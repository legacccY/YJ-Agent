"""
cbdice.py — cbDice loss baseline adapter（kind='loss'，统一 backbone U-Net base_ch32）

BASELINE_SPEC §2.4 loss 类：
  backbone   = UNet(in_ch=1, out_ch=1, base_ch=32)（钉死，与 Ours 同款）
  optimizer  = Adam lr=1e-3（统一）
  scheduler  = ReduceLROnPlateau mode=max factor=0.5 patience=10（统一）
  loss       = 2·BCE + 1·Dice + 1·cbDice（官方 2:1:1 比例）
               来源：nnUNetTrainer_CE_DC_CBDC.py::_build_loss()
                     lambda_ce = lambda_dice + lambda_cbdice（CE 刻意加倍）
                     compound_cbdice_loss.py::forward() 末行实证
               baseline-fix 2026-06-20 对齐官方源

超参来源：
  - cbDice 核心参数：iter_=10 smooth=1.0（官方 SoftcbDiceLoss 默认值）
  - 混合权重 2:1:1（CE:Dice:cbDice）：官方 nnUNetTrainer_CE_DC_CBDC 核实
    (PengchengShi1220/cbDice, Apache-2.0, MICCAI24 arXiv2407.01517 Table2)
  - backbone/optimizer/scheduler：BASELINE_SPEC §2.4 统一配方

Windows 安全：无 scipy.stats（cbdice_loss.py 用 scipy.ndimage），无 multiprocessing。
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

from baselines.base_adapter import BaselineAdapter, ENV_MAIN, KIND_LOSS
from baselines.registry import register


# 统一超参（loss 类固定，同 backbone_unet.py）
_UNIFIED_BASE_CH: int = 32
_UNIFIED_LR: float = 1e-3
_UNIFIED_SCHEDULER_FACTOR: float = 0.5
_UNIFIED_SCHEDULER_PATIENCE: int = 10
_UNIFIED_SCHEDULER_MIN_LR: float = 1e-6


def _dice_loss(
    pred_prob: torch.Tensor,
    target: torch.Tensor,
    mask: torch.Tensor,
    eps: float = 1e-6,
) -> torch.Tensor:
    pred_flat = (pred_prob * mask).reshape(pred_prob.shape[0], -1)
    tgt_flat = (target * mask).reshape(target.shape[0], -1)
    intersection = (pred_flat * tgt_flat).sum(1)
    denom = pred_flat.sum(1) + tgt_flat.sum(1)
    dice = (2 * intersection + eps) / (denom + eps)
    return 1.0 - dice.mean()


def _bce_loss(
    logits: torch.Tensor,
    target: torch.Tensor,
    mask: torch.Tensor,
) -> torch.Tensor:
    bce = F.binary_cross_entropy_with_logits(logits, target, reduction="none")
    n_valid = mask.sum().clamp(min=1)
    return (bce * mask).sum() / n_valid


class _CbDiceMixedLoss:
    """
    混合 loss：2·BCE + 1·Dice + 1·cbDice（官方 2:1:1 比例）。

    来源：PengchengShi1220/cbDice nnUNetTrainer_CE_DC_CBDC.py::_build_loss()
          lambda_ce = lambda_dice + lambda_cbdice → CE 加倍
          compound_cbdice_loss.py::forward(): weight_ce*ce + weight_dice*dc + weight_cbdice*cbdice

    二值场景 CE ≈ BCE，比例必须对齐官方 2:1:1（baseline-fix 2026-06-20）。

    signature: loss_fn(logits, target, fov_mask) -> scalar tensor
    """

    def __init__(self):
        from baselines.losses.cbdice_loss import CbDiceLoss
        self._cbdice = CbDiceLoss()

    def __call__(
        self,
        logits: torch.Tensor,
        target: torch.Tensor,
        fov_mask: torch.Tensor,
    ) -> torch.Tensor:
        prob = torch.sigmoid(logits)
        bce = _bce_loss(logits, target, fov_mask)
        dice = _dice_loss(prob, target, fov_mask)
        cbdice = self._cbdice(logits, target, fov_mask)
        # 官方 2·CE + 1·Dice + 1·cbDice（lambda_ce = lambda_dice + lambda_cbdice）
        return 2.0 * bce + dice + cbdice


@register
class CbDiceAdapter(BaselineAdapter):
    """
    cbDice loss baseline（MICCAI 2024, PengchengShi1220/cbDice, Apache-2.0）。

    kind='loss'：仅 loss 是变量，backbone + 训练超参统一（§2.4 反向公平）。
    loss = 2·BCE + 1·Dice + 1·cbDice（官方 nnUNetTrainer_CE_DC_CBDC 2:1:1 比例）。
    impl 已对齐官方比例（baseline-fix 2026-06-20）。
    """

    name: str = "cbdice"
    kind: str = KIND_LOSS
    source_repo: str = "https://github.com/PengchengShi1220/cbDice"
    env_tag: str = ENV_MAIN

    def build_model(self, cfg: Dict[str, Any]) -> nn.Module:
        """统一 backbone UNet(in_ch=1, out_ch=1, base_ch=32)。"""
        from models.unet import UNet
        return UNet(in_ch=1, out_ch=1, base_ch=_UNIFIED_BASE_CH)

    def build_loss(self, cfg: Dict[str, Any]) -> Any:
        """
        混合 loss：2·BCE + 1·Dice + 1·cbDice（官方 2:1:1）。
        signature: loss_fn(logits, target, fov_mask) -> scalar tensor
        """
        return _CbDiceMixedLoss()

    def build_optimizer(
        self,
        model: nn.Module,
        cfg: Dict[str, Any],
    ) -> torch.optim.Optimizer:
        """统一 Adam lr=1e-3（loss 类强制约束）。"""
        return torch.optim.Adam(model.parameters(), lr=_UNIFIED_LR)

    def build_scheduler(
        self,
        optimizer: torch.optim.Optimizer,
        cfg: Dict[str, Any],
    ) -> Optional[Any]:
        """统一 ReduceLROnPlateau（loss 类共用）。"""
        return torch.optim.lr_scheduler.ReduceLROnPlateau(
            optimizer,
            mode="max",
            factor=_UNIFIED_SCHEDULER_FACTOR,
            patience=_UNIFIED_SCHEDULER_PATIENCE,
            min_lr=_UNIFIED_SCHEDULER_MIN_LR,
        )

    def preprocess_cfg(self) -> Dict[str, Any]:
        """
        统一预处理：绿通道 + CLAHE，单通道全图（与 Ours 一致，§2.4 公平）。
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
                    "BASELINE_SPEC §2.4: loss-class adapter uses same "
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
        """全图推理：整图 UNet forward。"""
        model.eval()
        with torch.no_grad():
            logits = model(x)
        assert logits.shape[1] == 1 and logits.ndim == 4, (
            f"CbDiceAdapter.forward_adapt: expected (B,1,H,W), got {logits.shape}"
        )
        return logits
