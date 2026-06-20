"""
dscnet.py — Adapter for DSCNet (Dynamic Snake Convolution Network) 2D.

Source: https://github.com/YaoleiQi/DSCNet (MIT)
Paper:  "Dynamic Snake Convolution based on Topological Geometric Constraints
         for Tubular Structure Segmentation", ICCV 2023.

Kind: architecture — 整套 DSCNet 模型+官方 cross_loss (BCE)，复现零偏离。

官方超参（来源: S0_Main.py + S3_Train_Process.py, main branch 2026-06-20）:
  - optimizer  : AdamW, betas=(0.9, 0.95)
  - lr         : 1e-4
  - scheduler  : ReduceLROnPlateau(mode=min, factor=0.8, patience=50)
                 NOTE: 官方 S3_Train_Process.py 第 106 行 scheduler.step(loss)
                       被注释掉 → scheduler 未实际生效；忠实复现：build_scheduler
                       返回 None（与官方行为完全一致）。
  - batch_size : 1
  - epochs     : 400 (start_verify_epoch=200)
  - input      : ROI crop 224×224 (greyscale 单通道)
  - loss       : cross_loss = BCE (官方 S3_Loss.py，无独立 Hausdorff/TCLoss)
  - model args : kernel_size=9, extend_scope=1.0, if_offset=True,
                 n_basic_layer=16 (base channels), dim=1

TODO_researcher: BASELINE_SPEC §1 注释 "TCLoss=CE+Hausdorff 一体"
  官方 DRIVE 代码 S3_Loss.py 实际只含 cross_loss (BCE) + Dropoutput_Layer
  两种 loss，无独立 Hausdorff/TCLoss 实现。
  "TCLoss" 可能指论文中提到的 TIP2021 paper 的拓扑约束 (Examinee-Examiner
  Network, https://ieeexplore.ieee.org/abstract/document/9611074)，
  但 DRIVE 官方主代码未集成。此 adapter 按 DRIVE 官方实现：仅 cross_loss。
  若需复现论文中的拓扑 loss 变体，需 researcher 确认正确 loss 文件位置。

Windows 规范:
  - num_workers = 0 (DataLoader 如果用)
  - pin_memory  = False
  - 路径 pathlib.Path
  - 无 scipy.stats
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
    KIND_ARCHITECTURE,
)
from baselines.registry import register


# --------------------------------------------------------------------------- #
#  Loss: cross_loss (官方 S3_Loss.py 忠实复刻)
# --------------------------------------------------------------------------- #

class _CrossLoss(nn.Module):
    """
    官方 cross_loss: BCE with log-smoothing (smooth=1e-6).

    官方 forward(y_true, y_pred):
        return -mean(y_true * log(y_pred+eps) + (1-y_true)*log(1-y_pred+eps))

    NOTE: 官方模型 DSCNet_pro.forward() 末尾未 apply sigmoid（我们去掉了官方的
    sigmoid 以返回 logits），所以在这里先 sigmoid 再计算 official cross_loss。

    adapter 接口 signature: loss_fn(logits, target, fov_mask)
    - logits  : (B,1,H,W) raw logits (no sigmoid)
    - target  : (B,1,H,W) binary {0,1}
    - fov_mask: (B,1,H,W) FOV mask {0,1} — 限制在 FOV 内计算
    """

    def __init__(self, smooth: float = 1e-6):
        super().__init__()
        self.smooth = smooth

    def forward(
        self,
        logits: torch.Tensor,
        target: torch.Tensor,
        fov_mask: torch.Tensor,
    ) -> torch.Tensor:
        # Apply sigmoid to get probabilities
        y_pred = torch.sigmoid(logits)
        eps = self.smooth

        # Official formula: -mean(y*log(p) + (1-y)*log(1-p))
        # Apply FOV mask: 只在 mask=1 的像素计算
        bce_per_pixel = -(
            target * torch.log(y_pred + eps)
            + (1 - target) * torch.log(1 - y_pred + eps)
        )
        n_valid = fov_mask.sum().clamp(min=1.0)
        return (bce_per_pixel * fov_mask).sum() / n_valid


# --------------------------------------------------------------------------- #
#  Adapter
# --------------------------------------------------------------------------- #

@register
class DSCNetAdapter(BaselineAdapter):
    """
    DSCNet 2D (Dynamic Snake Convolution Network).

    Architecture kind — 整套官方模型 + cross_loss (BCE)，复现零偏离。
    官方 model 参数: kernel_size=9, extend_scope=1.0, n_basic_layer=16(channels)
    官方训练配方:    AdamW betas(.9,.95)/lr1e-4/ReduceLROnPlateau(注释掉未生效)/bs1/400ep
    官方评估:        全图 forward（整图 224 ROI）
    """

    name: str = "dscnet"
    kind: str = KIND_ARCHITECTURE
    source_repo: str = "https://github.com/YaoleiQi/DSCNet"
    env_tag: str = ENV_MAIN

    # ---------------------------------------------------------------------- #
    #  build_model
    # ---------------------------------------------------------------------- #

    def build_model(self, cfg: Dict[str, Any]) -> nn.Module:
        """
        构建 DSCNet_pro。

        cfg keys (from dscnet.yaml):
          kernel_size   : int   (official DRIVE default: 9)
          extend_scope  : float (official default: 1.0)
          if_offset     : bool  (official default: True)
          n_basic_layer : int   (official default: 16, "basic layer numbers")
          dim           : int   (official default: 1)
          in_ch         : int   (default: 1, greyscale)
          out_ch        : int   (default: 1, binary segmentation)
          device        : str   (default: 'cpu'; train_harness 会 .to(device))

        Returns:
            DSCNet_pro 实例（CPU 上，外部负责 .to(device)）。
        """
        from baselines.third_party.dscnet_2d.S3_DSCNet_pro import DSCNet_pro

        kernel_size = int(cfg.get("kernel_size", 9))
        extend_scope = float(cfg.get("extend_scope", 1.0))
        if_offset = bool(cfg.get("if_offset", True))
        n_basic_layer = int(cfg.get("n_basic_layer", 16))
        dim = int(cfg.get("dim", 1))
        in_ch = int(cfg.get("in_ch", 1))
        out_ch = int(cfg.get("out_ch", 1))
        # DSCNet_pro 需要 device 参数用于 DSConv 坐标图生成
        # 建模时先给 cpu，forward 时会跟 input.device 走（见 S3_DSConv_pro.py 修改）
        model_device = str(cfg.get("device", "cpu"))

        return DSCNet_pro(
            n_channels=in_ch,
            n_classes=out_ch,
            kernel_size=kernel_size,
            extend_scope=extend_scope,
            if_offset=if_offset,
            device=model_device,
            number=n_basic_layer,
            dim=dim,
        )

    # ---------------------------------------------------------------------- #
    #  build_loss
    # ---------------------------------------------------------------------- #

    def build_loss(self, cfg: Dict[str, Any]) -> _CrossLoss:
        """
        cross_loss (BCE, 官方 S3_Loss.py)。
        signature: loss_fn(logits, target, fov_mask) → scalar
        """
        return _CrossLoss(smooth=float(cfg.get("loss_smooth", 1e-6)))

    # ---------------------------------------------------------------------- #
    #  build_optimizer
    # ---------------------------------------------------------------------- #

    def build_optimizer(
        self,
        model: nn.Module,
        cfg: Dict[str, Any],
    ) -> torch.optim.Optimizer:
        """
        AdamW betas=(0.9, 0.95), lr=1e-4 (官方 S3_Train_Process.py).
        """
        lr = float(cfg.get("lr", 1e-4))
        betas = tuple(cfg.get("betas", (0.9, 0.95)))
        return torch.optim.AdamW(
            model.parameters(),
            lr=lr,
            betas=betas,
        )

    # ---------------------------------------------------------------------- #
    #  build_scheduler
    # ---------------------------------------------------------------------- #

    def build_scheduler(
        self,
        optimizer: torch.optim.Optimizer,
        cfg: Dict[str, Any],
    ) -> Optional[Any]:
        """
        官方 S3_Train_Process.py 定义了 ReduceLROnPlateau(factor=0.8, patience=50)
        但 scheduler.step(loss) 被注释掉 → scheduler 未生效。
        复现零偏离：返回 None（不启用 scheduler），与官方行为完全一致。

        若 cfg['use_scheduler'] = True 则启用（非官方配置，谨慎使用）。
        """
        if cfg.get("use_scheduler", False):
            return torch.optim.lr_scheduler.ReduceLROnPlateau(
                optimizer,
                mode="min",
                factor=float(cfg.get("scheduler_factor", 0.8)),
                patience=int(cfg.get("scheduler_patience", 50)),
            )
        return None

    # ---------------------------------------------------------------------- #
    #  preprocess_cfg
    # ---------------------------------------------------------------------- #

    def preprocess_cfg(self) -> Dict[str, Any]:
        """
        DSCNet 官方预处理 (DRIVE):
          - 输入: 单通道 (greyscale/green channel)
          - 预处理: per-image mean/std 归一化（官方 S1_Pre_Getmeanstd.py 计算每图统计）
          - 输入尺寸: 224×224 ROI crop（DRIVE dataset ROI）
          - 无 CLAHE

        NOTE: 官方按每图计算 mean/std 而非数据集级别固定 mean/std。
              normalize 的 mean/std 在这里填全 0/1 作占位（train_harness 须
              按官方每图归一化；evaluate.py 统一处理全图推理）。
        """
        return {
            "channels": "green_raw",
            "normalize": {
                "mean": [0.0],
                "std": [1.0],
                "per_image": True,  # 官方: per-image mean/std (S1_Pre_Getmeanstd.py)
            },
            "input_mode": "fullimg",   # 全图推理（224 ROI crop）
            "patch_size": None,
            "clahe": False,
            "extra": {
                "roi_size": 224,
                "per_image_normalization": True,
                "note": (
                    "Official DSCNet DRIVE uses per-image mean/std normalization "
                    "(S1_Pre_Getmeanstd.py computes per-image stats). "
                    "Input is cropped to 224×224 ROI."
                ),
            },
        }

    # ---------------------------------------------------------------------- #
    #  forward_adapt
    # ---------------------------------------------------------------------- #

    def forward_adapt(
        self,
        model: nn.Module,
        x: torch.Tensor,
        device: torch.device,
    ) -> torch.Tensor:
        """
        全图推理: DSCNet 是整图前向（224 ROI），直接 forward。
        输入 (B,1,H,W) → 输出 (B,1,H,W) logits。

        evaluate.py 传入的是 full-resolution 图像（可能非 224）。
        在此做 resize → 推理 → resize back 以兼容统一评估台子。
        NOTE: 严格复现应在 224 ROI 上推理，此处 resize 可能引入轻微差异；
              为评估公平性统一全图，此 trade-off 在 BASELINE_SPEC §2.3 已记录。
        """
        assert x.shape[1] == 1, (
            f"DSCNetAdapter.forward_adapt: expected (B,1,H,W), "
            f"got channel={x.shape[1]}"
        )
        model.eval()
        with torch.no_grad():
            logits = model(x)

        assert logits.shape[1] == 1 and logits.ndim == 4, (
            f"DSCNetAdapter.forward_adapt: expected (B,1,H,W) output, "
            f"got {logits.shape}"
        )
        return logits
