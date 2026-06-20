"""
vmunet.py — Adapter for VM-UNet (Visual Mamba U-Net).

官方 repo  : https://github.com/JCruan519/VM-UNet  (Apache-2.0)
官方论文   : arXiv 2402.02491
官方超参   : AdamW lr=1e-3; CosineAnnealingLR min_lr=1e-5; epochs=300;
             batch=32; input=256×256; loss=BceDice;
             data aug: flip+rotation（随机水平/垂直翻转+随机旋转）。
             Source: BASELINE_SPEC §1 + github.com/JCruan519/VM-UNet train.py

架构特点   : Visual State Space (VSS) block-based U-Net with Mamba SSM kernel.
             依赖 mamba-ssm CUDA kernel（env_tag='mamba'）。
             vendor 已 curl 到 third_party/VM-UNet/（Apache-2.0）。

env_tag    : 'mamba'（需独立 mamba_venv，见 BASELINE_SPEC §3）

VMUNet 说明 :
  - forward 内部含 sigmoid（return torch.sigmoid(logits)），输出 [0,1] 概率。
  - 本 adapter 的 forward_adapt 把概率转回 logit（logit = log(p/(1-p))），
    保持与其他 adapter 同一接口约定（evaluate.py 统一 threshold）。
  - build_model 输入 input_channels=1（灰度；官方单通道时做 repeat(1,3,1,1)）。

Windows 规范 :
  - 无 scipy.stats
  - 无 multiprocessing
  - 路径用 pathlib.Path
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

from baselines.base_adapter import BaselineAdapter, ENV_MAMBA, KIND_ARCHITECTURE
from baselines.registry import register

# vendor 路径（curl 已完成）
_VENDOR_DIR = Path(__file__).parent.parent / "third_party" / "VM-UNet"


# --------------------------------------------------------------------------- #
#  Loss helper — BceDice（官方 loss）
#  官方: bce_loss + dice_loss，各权重 1.0（加和不平均）
#  Source: github.com/JCruan519/VM-UNet/utils/loss.py
# --------------------------------------------------------------------------- #

class _BceDiceLoss:
    """
    BceDice loss — 官方 VM-UNet loss 实现。
    公式: L = BCE(logits, target) + Dice(sigmoid(logits), target)
    signature: (logits, target, fov_mask) -> scalar
    官方代码未做 FOV masking，此处保持原样（fov_mask 接收但忽略，与官方一致）。
    """

    def __call__(
        self,
        logits: torch.Tensor,
        target: torch.Tensor,
        fov_mask: torch.Tensor,
    ) -> torch.Tensor:
        import torch.nn.functional as F

        # BCE part（官方用 BCEWithLogitsLoss，reduction='mean'，全图无 mask）
        bce = F.binary_cross_entropy_with_logits(logits, target, reduction="mean")

        # Dice part（官方 smooth=1e-5）
        smooth = 1e-5
        prob = torch.sigmoid(logits)
        num = (prob * target).sum(dim=(2, 3))
        denom = prob.sum(dim=(2, 3)) + target.sum(dim=(2, 3))
        dice_score = (2.0 * num + smooth) / (denom + smooth)
        dice_loss = 1.0 - dice_score.mean()

        return bce + dice_loss


# --------------------------------------------------------------------------- #
#  Adapter
# --------------------------------------------------------------------------- #

@register
class VMUNetAdapter(BaselineAdapter):
    """
    VM-UNet baseline adapter (Visual Mamba U-Net).

    官方 repo : https://github.com/JCruan519/VM-UNet (Apache-2.0)
    env_tag   : 'mamba' — 需 mamba_venv（mamba-ssm + causal-conv1d）
    vendor    : third_party/VM-UNet/（Apache-2.0，已 curl）

    ⚠️ build_model 依赖 mamba_ssm CUDA kernel：
       本地（主 env）无 mamba_ssm → 抛 RuntimeError 并给出 HPC 指引。
       HPC mamba_venv 中正常实例化。
    """

    name: str = "vm_unet"
    kind: str = KIND_ARCHITECTURE
    source_repo: str = "https://github.com/JCruan519/VM-UNet"
    env_tag: str = ENV_MAMBA

    def build_model(self, cfg: Dict[str, Any]) -> nn.Module:
        """
        构建 VMUNet（依赖 mamba_ssm）。

        cfg keys (from configs/baselines/vmunet.yaml):
          input_channels  : int (default 1, 灰度；官方内部做 repeat×3)
          num_classes     : int (default 1)
          depths          : list (default [2,2,9,2])
          depths_decoder  : list (default [2,9,2,2])
          drop_path_rate  : float (default 0.2)
          load_ckpt_path  : str | null (预训练权重，可选)

        Raises:
            RuntimeError: 若 mamba_ssm 未安装（需 mamba_venv）。
        """
        # 先检查 mamba_ssm 是否可用
        try:
            import mamba_ssm  # noqa: F401
        except ImportError as exc:
            raise RuntimeError(
                "VM-UNet 需要 mamba-ssm CUDA kernel，当前环境未安装。\n"
                "请在 HPC mamba_venv 中运行（见 BASELINE_SPEC §3）：\n"
                "  pip install mamba-ssm causal-conv1d（HF torch29-cu126 wheel）\n"
                f"原始 ImportError: {exc}"
            ) from exc

        # 把 vendor 目录加进 sys.path
        vmunet_models_dir = _VENDOR_DIR / "models"
        if str(vmunet_models_dir) not in sys.path:
            sys.path.insert(0, str(vmunet_models_dir))

        from vmunet.vmunet import VMUNet

        input_channels = int(cfg.get("input_channels", 1))
        num_classes = int(cfg.get("num_classes", 1))
        depths = list(cfg.get("depths", [2, 2, 9, 2]))
        depths_decoder = list(cfg.get("depths_decoder", [2, 9, 2, 2]))
        drop_path_rate = float(cfg.get("drop_path_rate", 0.2))
        load_ckpt_path = cfg.get("load_ckpt_path", None)

        model = VMUNet(
            input_channels=input_channels,
            num_classes=num_classes,
            depths=depths,
            depths_decoder=depths_decoder,
            drop_path_rate=drop_path_rate,
            load_ckpt_path=load_ckpt_path,
        )
        return model

    def build_loss(self, cfg: Dict[str, Any]) -> _BceDiceLoss:
        """官方 loss = BCE + Dice（官方 VM-UNet utils/loss.py）。"""
        return _BceDiceLoss()

    def build_optimizer(
        self,
        model: nn.Module,
        cfg: Dict[str, Any],
    ) -> torch.optim.Optimizer:
        """
        AdamW lr=1e-3（官方 train.py）。
        官方未明示 weight_decay，PyTorch AdamW default=1e-2。
        # TODO: 官方 VM-UNet train.py 中 AdamW weight_decay 未在论文中明示；
        #       github.com/JCruan519/VM-UNet train.py 需核实 → 此处占位 1e-2。
        """
        lr = float(cfg.get("lr", 1e-3))
        wd = float(cfg.get("weight_decay", 1e-2))
        return torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=wd)

    def build_scheduler(
        self,
        optimizer: torch.optim.Optimizer,
        cfg: Dict[str, Any],
    ) -> Optional[Any]:
        """
        CosineAnnealingLR T_max=300 eta_min=1e-5（官方）。
        """
        epochs = int(cfg.get("epochs", 300))
        min_lr = float(cfg.get("min_lr", 1e-5))
        return torch.optim.lr_scheduler.CosineAnnealingLR(
            optimizer, T_max=epochs, eta_min=min_lr
        )

    def preprocess_cfg(self) -> Dict[str, Any]:
        """
        官方预处理：256×256 resize，flip + rotation 增强。
        输入通道：灰度单通道（官方内部 repeat×3 处理）。
        # TODO: 官方具体 normalize mean/std 未在论文/README 中明示；
        #       需查 github.com/JCruan519/VM-UNet/datasets/ 确认。
        """
        return {
            "channels": "green_raw",          # 灰度，官方内部 repeat→3ch
            "normalize": {
                "mean": [0.0],                 # TODO: 官方未明示，占位
                "std": [1.0],                  # TODO: 官方未明示，占位
            },
            "input_mode": "fullimg",
            "patch_size": None,
            "clahe": False,
            "extra": {
                "resize": 256,                 # 官方 input=256×256
                "augment": "flip+rotation",    # 官方 data aug（官方 train.py）
                "note": (
                    "VM-UNet input=256×256, grayscale (internal repeat×3). "
                    "Eval: resize to 256 → forward → resize back to original. "
                    "Source: BASELINE_SPEC §1 + github.com/JCruan519/VM-UNet."
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
        全图推理：resize 到 256×256 → VMUNet forward → resize 回原尺寸。
        VMUNet.forward 末尾含 sigmoid（输出概率），此处转回 logit。

        Args:
            model : VMUNet 实例，eval 模式，已 .to(device)。
            x     : (B, 1, H, W) 灰度全图，已在 device 上。
            device: 推理设备。

        Returns:
            (B, 1, H, W) logits。
        """
        import torch.nn.functional as F

        model.eval()
        B, C, H, W = x.shape
        assert C == 1, (
            f"VMUNetAdapter: 期望单通道输入 (B,1,H,W)，实际 C={C}"
        )

        # resize 到 256×256（官方训练/推理尺寸）
        x_resized = F.interpolate(x, size=(256, 256), mode="bilinear", align_corners=False)

        with torch.no_grad():
            prob = model(x_resized)  # VMUNet 内部含 sigmoid，输出 [0,1]

        # 转回 logits（clamp 避免 log(0)/log(1) 数值问题）
        prob_clamp = prob.clamp(min=1e-7, max=1.0 - 1e-7)
        logits_256 = torch.log(prob_clamp / (1.0 - prob_clamp))

        # resize 回原始尺寸
        logits = F.interpolate(logits_256, size=(H, W), mode="bilinear", align_corners=False)

        assert logits.shape == (B, 1, H, W), (
            f"VMUNetAdapter.forward_adapt: shape mismatch, got {logits.shape}"
        )
        return logits
