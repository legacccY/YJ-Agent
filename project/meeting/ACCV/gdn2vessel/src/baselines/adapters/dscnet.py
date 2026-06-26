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

        TODO: 官方 S3_Train_Process.py torch.optim.AdamW(model.parameters(), lr=lr,
              betas=betas) 未见显式 weight_decay 参数（PyTorch AdamW 默认 wd=0.01）。
              # TODO: researcher 确认官方是否传 weight_decay 及具体值；
              #       若官方无显式 wd，保持 PyTorch 默认 0.01（AdamW 默认）。
        """
        lr = float(cfg.get("lr", 1e-4))
        betas = tuple(cfg.get("betas", (0.9, 0.95)))
        # TODO: 官方未见显式 weight_decay；PyTorch AdamW 默认 wd=0.01，此处沿用默认。
        #       researcher 确认后回填（dscnet.yaml weight_decay 字段）。
        return torch.optim.AdamW(
            model.parameters(),
            lr=lr,
            betas=betas,
            # weight_decay 未传 → 使用 PyTorch AdamW 默认 0.01（复现零偏离待 researcher 确认）
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
        DSCNet 官方预处理（§7.1，baseline-fix 2026-06-20）:
          - 输入: 单通道 (greyscale/green channel)
          - normalize: z-score (image-mean)/std，mean/std 由
                       S1_Pre_Getmeanstd.py 对**全训练集**计算后存 .npy；
                       非 per-image（§7.1 源：S3_Dataloader.py）
                       label /max 二值化
          - 输入尺寸: 224×224 ROI crop（DRIVE dataset ROI）
          - 无 CLAHE
          ⚠ mean/std 为全训练集统计值，train_harness 须从 .npy 加载同一组值。
        """
        return {
            "channels": "green_raw",
            "normalize": {
                "method": "zscore",              # (image-mean)/std，§7.1
                "whole_dataset_stats": True,      # 全训练集计算，非 per-image
                "stats_file": "mean_std.npy",     # S1_Pre_Getmeanstd.py 输出
                "mean": [0.0],  # 占位，实际值从 .npy 加载
                "std": [1.0],   # 占位，实际值从 .npy 加载
            },
            "input_mode": "fullimg",   # 全图推理（224 ROI crop）
            "patch_size": None,
            "clahe": False,
            "augment": {
                # 源：YaoleiQi/DSCNet S3_Data_Augumentation.py（§7.2）
                # MONAI dict pipeline，外层 80% 触发（20% pass）
                "outer_p": 0.8,
                "transforms": [
                    {"type": "Orientation", "p": 0.7},
                    {
                        "type": "Affine_or_2D_Elastic",  # 70% 二选一
                        "p": 0.7,
                        "affine": {
                            "translate_range": [-30, 30],  # px
                            "rotate_range": [-0.0873, 0.0873],  # ±π/36
                            "scale_range": [-0.15, 0.15],
                        },
                        "elastic": {
                            "spacing": 20,
                            "magnitude": 1,
                            "translate_range": [10, 20],
                            "rotate_range": [-0.0873, 0.0873],  # ±π/36
                        },
                    },
                    {"type": "ScaleIntensityRange", "p": 0.5},
                    {"type": "GaussianNoise_or_Smooth", "p": 0.5, "exclusive": True},
                ],
                "note": (
                    "DSCNet official MONAI augment pipeline (S3_Data_Augumentation.py §7.2). "
                    "TODO: exact prob thresholds need per-line verification in source. "
                    "Outer 80% trigger; sub-transforms as listed."
                ),
            },
            "extra": {
                "roi_size": 224,
                "note": (
                    "Official DSCNet DRIVE: z-score norm with whole-dataset mean/std "
                    "computed by S1_Pre_Getmeanstd.py and saved as .npy. "
                    "Source: S3_Dataloader.py + BASELINE_SPEC §7.1 §7.2."
                ),
            },
        }

    # ---------------------------------------------------------------------- #
    #  forward_adapt
    # ---------------------------------------------------------------------- #

    # DSCNet 架构下采样因子：MaxPool2d(2) × 3 = 8x，skip concat 要求 H%8==0, W%8==0。
    # 官方训练用 224×224 ROI (224%8==0 OK)。
    # native DRIVE 565×584: 565%8=5≠0 → upsample path 140 vs skip 141 → concat 崩。
    # 修复：preprocess_benchmark_image pad 到 8 整数倍，forward_adapt 直接 forward。
    # evaluate.py 之后 crop [:orig_H, :orig_W] 回 native GT 尺寸。
    _DSCNET_PAD_MULT: int = 8

    def preprocess_benchmark_image(
        self,
        npz_image: "np.ndarray",
        image_id: str,
        dataset_name: str,
        data_root: "Optional[str]" = None,
    ) -> "Tuple[np.ndarray, Tuple[int, int]]":
        """
        DSCNet benchmark 预处理：pad 输入到 8 整数倍（下采样兼容）。

        DSCNet 使用 MaxPool2d(2) × 3 下采样，要求 H%8==0, W%8==0。
        native DRIVE 565×584: 565%8=5，不整除 → skip concat 尺寸崩
        （encoder path 下采到 141，decoder upsample 到 140，cat 崩）。
        修复：pad 到 8 整数倍后 forward，输出保持 padded 尺寸，
        evaluate.py crop [:orig_H, :orig_W] 回 native GT 尺寸算指标。

        Args:
            npz_image:    (H, W) float32 from NPZ (green+CLAHE+norm).
            image_id:     image identifier (unused, kept for signature 兼容).
            dataset_name: dataset name (unused, kept for signature 兼容).
            data_root:    optional raw data root (unused for DSCNet).

        Returns:
            (padded_image, (orig_H, orig_W)):
              padded_image — (H', W') float32, H'%8==0 and W'%8==0.
              (orig_H, orig_W) — original size for crop-back in evaluate.py.
        """
        import numpy as _np

        img = npz_image.astype(_np.float32)
        orig_H, orig_W = img.shape

        mult = self._DSCNET_PAD_MULT
        pad_H = (mult - orig_H % mult) % mult
        pad_W = (mult - orig_W % mult) % mult

        if pad_H > 0 or pad_W > 0:
            img = _np.pad(img, ((0, pad_H), (0, pad_W)), mode='constant', constant_values=0.0)

        return img, (orig_H, orig_W)

    def forward_adapt(
        self,
        model: nn.Module,
        x: torch.Tensor,
        device: torch.device,
    ) -> torch.Tensor:
        """
        全图推理: DSCNet 整图前向。

        输入 (B,1,H,W) 其中 H%8==0, W%8==0（由 preprocess_benchmark_image 保证）。
        → 输出 (B,1,H,W) logits（形状与输入一致）。
        evaluate.py 之后 crop [:orig_H, :orig_W] 回 native GT 尺寸。

        NOTE: 严格复现应在 224 ROI 上推理；此处全图推理用于公平统一评估台子。
              H%8==0, W%8==0 保证 MaxPool2d(2)×3 的 skip-concat 维度匹配。
        """
        assert x.shape[1] == 1, (
            f"DSCNetAdapter.forward_adapt: expected (B,1,H,W), "
            f"got channel={x.shape[1]}"
        )
        _, _, H, W = x.shape
        assert H % self._DSCNET_PAD_MULT == 0 and W % self._DSCNET_PAD_MULT == 0, (
            f"DSCNetAdapter.forward_adapt: H={H}, W={W} 不是 {self._DSCNET_PAD_MULT} "
            f"整数倍，skip concat 会崩。请检查 preprocess_benchmark_image 是否正确 pad。"
        )

        model.eval()
        with torch.no_grad():
            logits = model(x)

        assert logits.shape[1] == 1 and logits.ndim == 4, (
            f"DSCNetAdapter.forward_adapt: expected (B,1,H,W) output, "
            f"got {logits.shape}"
        )
        return logits
