"""
cldice.py — clDice loss baseline adapter（kind='loss'，统一 backbone U-Net base_ch32）

BASELINE_SPEC §2.4 loss 类：
  backbone   = UNet(in_ch=1, out_ch=1, base_ch=32)（钉死，与 Ours 同款）
  optimizer  = Adam lr=1e-3（统一）
  scheduler  = ReduceLROnPlateau mode=max factor=0.5 patience=10（统一）
  loss       = (1-α)*SoftDice + α*clDice，α=0.5（官方 repo default）
               实现：0.5 SoftDice + 0.5 clDice = ClDiceLoss(alpha=0.5)

超参来源：
  - α=0.5：官方 jocpae/clDice repo default（BASELINE_SPEC §1 确认）
  - backbone/optimizer/scheduler：BASELINE_SPEC §2.4 统一配方

Windows 安全：无 scipy.stats，无 multiprocessing。
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, Optional

import torch
import torch.nn as nn

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


@register
class ClDiceAdapter(BaselineAdapter):
    """
    clDice loss baseline（MICCAI 2021, jocpae/clDice, MIT）。

    kind='loss'：仅 loss 是变量，backbone + 训练超参统一（§2.4 反向公平）。
    loss = (1-0.5)*SoftDice + 0.5*clDice（官方 α=0.5 default）。
    """

    name: str = "cldice"
    kind: str = KIND_LOSS
    source_repo: str = "https://github.com/jocpae/clDice"
    env_tag: str = ENV_MAIN

    def build_model(self, cfg: Dict[str, Any]) -> nn.Module:
        """统一 backbone UNet(in_ch=1, out_ch=1, base_ch=32)。"""
        from models.unet import UNet
        return UNet(in_ch=1, out_ch=1, base_ch=_UNIFIED_BASE_CH)

    def build_loss(self, cfg: Dict[str, Any]) -> Any:
        """
        clDice loss：(1-α)*SoftDice + α*clDice，α=0.5。
        signature: loss_fn(logits, target, fov_mask) -> scalar tensor
        """
        from baselines.losses.cldice_loss import ClDiceLoss
        alpha = float(cfg.get("alpha", 0.5))  # 官方 default α=0.5
        return ClDiceLoss(alpha=alpha)

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
            f"ClDiceAdapter.forward_adapt: expected (B,1,H,W), got {logits.shape}"
        )
        return logits
