"""
cldice_loss.py — 忠实移植官方 clDice loss（standalone，零 nnU-Net 依赖）

Source:
  https://github.com/jocpae/clDice  (MIT License)
  Files fetched:
    cldice_loss/pytorch/soft_skeleton.py  (branch: master, fetched 2026-06-20)
    cldice_loss/pytorch/cldice.py         (branch: master, fetched 2026-06-20)
  Original authors: Suprosanna Shit, Johannes C. Paetzold et al.
  Paper: "clDice - a Novel Topology-Preserving Loss Function for Tubular
          Structure Segmentation" (CVPR 2021)

移植说明：
  - 完整保留官方 SoftSkeletonize、soft_dice、soft_cldice、soft_dice_cldice
  - 去掉 "from .soft_skeleton import SoftSkeletonize" 相对引用，改为本文件内联
  - 签名对齐 gdn2vessel harness：
      loss_fn(logits, target, fov_mask) -> scalar tensor
    其中 logits = (B,1,H,W) raw logits；target = (B,1,H,W) binary GT；
    fov_mask = (B,1,H,W) FOV mask（1=valid）
  - 内部先 sigmoid(logits) 再送给 soft_dice_cldice（官方接受概率图）
  - α=0.5（官方 repo default，已由 researcher 在 BASELINE_SPEC §1 确认）

⚠️ 复现零偏离注记：
  - num_iter=10（官方 SoftSkeletonize 内嵌默认）
  - iter_=3 → 影响 soft_cldice/soft_dice_cldice 内部 self.iter（未被用到，
    实际 skeletonize 迭代数由 SoftSkeletonize(num_iter=10) 控制）
  - smooth=1.0（官方 default）
  - 无 exclude_background（我们是单通道二值图，排 background 无意义）

Windows 安全：无 scipy.stats，无 multiprocessing，路径无反斜杠。
"""

from __future__ import annotations

import torch
import torch.nn as nn
import torch.nn.functional as F


# ============================================================================
# SoftSkeletonize
# Source: https://github.com/jocpae/clDice/blob/master/cldice_loss/pytorch/soft_skeleton.py
# Fetched: 2026-06-20, branch master
# ============================================================================

class SoftSkeletonize(torch.nn.Module):
    """
    Differentiable morphological soft skeletonization.
    Official clDice repo implementation (unchanged).
    """

    def __init__(self, num_iter: int = 40):
        super(SoftSkeletonize, self).__init__()
        self.num_iter = num_iter

    def soft_erode(self, img: torch.Tensor) -> torch.Tensor:
        if len(img.shape) == 4:
            p1 = -F.max_pool2d(-img, (3, 1), (1, 1), (1, 0))
            p2 = -F.max_pool2d(-img, (1, 3), (1, 1), (0, 1))
            return torch.min(p1, p2)
        elif len(img.shape) == 5:
            p1 = -F.max_pool3d(-img, (3, 1, 1), (1, 1, 1), (1, 0, 0))
            p2 = -F.max_pool3d(-img, (1, 3, 1), (1, 1, 1), (0, 1, 0))
            p3 = -F.max_pool3d(-img, (1, 1, 3), (1, 1, 1), (0, 0, 1))
            return torch.min(torch.min(p1, p2), p3)

    def soft_dilate(self, img: torch.Tensor) -> torch.Tensor:
        if len(img.shape) == 4:
            return F.max_pool2d(img, (3, 3), (1, 1), (1, 1))
        elif len(img.shape) == 5:
            return F.max_pool3d(img, (3, 3, 3), (1, 1, 1), (1, 1, 1))

    def soft_open(self, img: torch.Tensor) -> torch.Tensor:
        return self.soft_dilate(self.soft_erode(img))

    def soft_skel(self, img: torch.Tensor) -> torch.Tensor:
        img1 = self.soft_open(img)
        skel = F.relu(img - img1)

        for j in range(self.num_iter):
            img = self.soft_erode(img)
            img1 = self.soft_open(img)
            delta = F.relu(img - img1)
            skel = skel + F.relu(delta - skel * delta)

        return skel

    def forward(self, img: torch.Tensor) -> torch.Tensor:
        return self.soft_skel(img)


# ============================================================================
# clDice core loss classes
# Source: https://github.com/jocpae/clDice/blob/master/cldice_loss/pytorch/cldice.py
# Fetched: 2026-06-20, branch master
# (Inline SoftSkeletonize import replaced; rest unchanged)
# ============================================================================

def soft_dice(y_true: torch.Tensor, y_pred: torch.Tensor) -> torch.Tensor:
    """Official soft Dice loss. Input: probability maps (after sigmoid)."""
    smooth = 1.0
    intersection = torch.sum(y_true * y_pred)
    coeff = (2.0 * intersection + smooth) / (
        torch.sum(y_true) + torch.sum(y_pred) + smooth
    )
    return 1.0 - coeff


class soft_cldice(nn.Module):
    """
    Pure clDice (no Dice term). Official clDice repo class.
    Input: probability maps.
    """

    def __init__(
        self,
        iter_: int = 3,
        smooth: float = 1.0,
        exclude_background: bool = False,
    ):
        super(soft_cldice, self).__init__()
        self.iter = iter_
        self.smooth = smooth
        self.soft_skeletonize = SoftSkeletonize(num_iter=10)
        self.exclude_background = exclude_background

    def forward(
        self, y_true: torch.Tensor, y_pred: torch.Tensor
    ) -> torch.Tensor:
        if self.exclude_background:
            y_true = y_true[:, 1:, :, :]
            y_pred = y_pred[:, 1:, :, :]
        skel_pred = self.soft_skeletonize(y_pred)
        skel_true = self.soft_skeletonize(y_true)
        tprec = (
            torch.sum(torch.multiply(skel_pred, y_true)) + self.smooth
        ) / (torch.sum(skel_pred) + self.smooth)
        tsens = (
            torch.sum(torch.multiply(skel_true, y_pred)) + self.smooth
        ) / (torch.sum(skel_true) + self.smooth)
        cl_dice = 1.0 - 2.0 * (tprec * tsens) / (tprec + tsens)
        return cl_dice


class soft_dice_cldice(nn.Module):
    """
    Official clDice: (1-α)*SoftDice + α*clDice. α=0.5 repo default.
    Input: probability maps.
    """

    def __init__(
        self,
        iter_: int = 3,
        alpha: float = 0.5,
        smooth: float = 1.0,
        exclude_background: bool = False,
    ):
        super(soft_dice_cldice, self).__init__()
        self.iter = iter_
        self.smooth = smooth
        self.alpha = alpha
        self.soft_skeletonize = SoftSkeletonize(num_iter=10)
        self.exclude_background = exclude_background

    def forward(
        self, y_true: torch.Tensor, y_pred: torch.Tensor
    ) -> torch.Tensor:
        if self.exclude_background:
            y_true = y_true[:, 1:, :, :]
            y_pred = y_pred[:, 1:, :, :]
        dice = soft_dice(y_true, y_pred)
        skel_pred = self.soft_skeletonize(y_pred)
        skel_true = self.soft_skeletonize(y_true)
        tprec = (
            torch.sum(torch.multiply(skel_pred, y_true)) + self.smooth
        ) / (torch.sum(skel_pred) + self.smooth)
        tsens = (
            torch.sum(torch.multiply(skel_true, y_pred)) + self.smooth
        ) / (torch.sum(skel_true) + self.smooth)
        cl_dice = 1.0 - 2.0 * (tprec * tsens) / (tprec + tsens)
        return (1.0 - self.alpha) * dice + self.alpha * cl_dice


# ============================================================================
# Harness-compatible wrapper
# ============================================================================

class ClDiceLoss:
    """
    gdn2vessel harness adapter wrapper for soft_dice_cldice.

    signature: loss_fn(logits, target, fov_mask) -> scalar tensor
      - logits   : (B,1,H,W) raw model output (sigmoid applied internally)
      - target   : (B,1,H,W) binary GT [0,1]
      - fov_mask : (B,1,H,W) FOV mask (1=valid, 0=ignore)
                   ⚠️ clDice official does NOT use FOV mask — we apply it
                   as a multiplicative gate on BOTH pred & GT before loss,
                   consistent with §2.4 fairness contract.

    alpha=0.5: official repo default (BASELINE_SPEC §1 confirmed).
    """

    def __init__(self, alpha: float = 0.5):
        self._loss = soft_dice_cldice(iter_=3, alpha=alpha, smooth=1.0)
        self.alpha = alpha

    def __call__(
        self,
        logits: torch.Tensor,
        target: torch.Tensor,
        fov_mask: torch.Tensor,
    ) -> torch.Tensor:
        prob = torch.sigmoid(logits)
        # Apply FOV mask: zero-out non-FOV pixels (background exclusion)
        prob_masked = prob * fov_mask
        target_masked = target * fov_mask
        return self._loss(target_masked, prob_masked)
