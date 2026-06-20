"""
skeleton_recall_loss.py — 忠实移植官方 Skeleton Recall loss（standalone，零 nnU-Net 依赖）

Source:
  https://github.com/MIC-DKFZ/Skeleton-Recall  (Apache-2.0 License)
  Files fetched (branch: master, fetched 2026-06-20 via jsdelivr CDN):
    nnunetv2/training/loss/dice.py               → SoftSkeletonRecallLoss
    nnunetv2/training/loss/compound_losses.py    → DC_SkelREC_and_CE_loss (参考混合权重)
    nnunetv2/training/data_augmentation/
      custom_transforms/skeletonization.py       → SkeletonTransform (skeleton GT 生成)
  Original authors: Yannick et al. (MIC-DKFZ)
  Paper: "Skeleton Recall Loss for Connectivity Conserving and Resource Efficient
          Segmentation of Thin Tubular Structures" (MICCAI 2024)

移植说明：
  - SoftSkeletonRecallLoss：完整移植官方 dice.py 中的实现
    - 去掉 AllGatherGrad（DDP 用，单卡训练不需要）
    - 去掉 apply_nonlin 参数（harness wrapper 内做 sigmoid→softmax 转换）
    - batch_dice=False（官方单样本 dice 模式）
    - do_bg=False（官方要求，background 不参与 skeleton recall）
  - 官方训练时通过 SkeletonTransform（离线 skimage.morphology.skeletonize）
    预计算 skeleton GT；我们在 loss forward 内实时计算（batch 级，no_grad）
    → 等价官方（tubed=False，原始 skeleton，无 dilation）
  - 官方混合 loss（DC_SkelREC_and_CE_loss）:
      weight_ce=1 weight_dice=1 weight_srec=1
    我们 wrapper 用 0.5 BCE+Dice + 0.5 SkelRecall（受控变量设计，adapter 层控制）

⚠️ 复现零偏离注记：
  - SoftSkeletonRecallLoss.smooth=1.0（官方 smooth=1.）
  - Skeleton GT 计算：skimage.morphology.skeletonize（官方 SkeletonTransform 同）
  - 无 dilation（官方 do_tube=False 等价，保留原始 skeleton 宽度）
  - skeletonize 操作在 no_grad 内完成，不影响梯度链

Windows 安全：无 scipy.stats，无 multiprocessing，路径无反斜杠。
"""

from __future__ import annotations

import numpy as np
import torch
import torch.nn as nn
from skimage.morphology import skeletonize as skimage_skeletonize


# ============================================================================
# Skeleton GT helper (等价官方 SkeletonTransform，无 dilation)
# ============================================================================

def _compute_skeleton_gt(target: torch.Tensor) -> torch.Tensor:
    """
    实时计算 skeleton GT（等价官方 SkeletonTransform，do_tube=False）。

    target: (B, 1, H, W) binary float tensor（值 0/1）
    返回: (B, 1, H, W) binary float tensor（skeleton mask）

    官方 SkeletonTransform 使用 skimage.morphology.skeletonize（Lee 算法）。
    此函数在 no_grad 上下文内调用，纯 numpy 实现，不计入梯度。
    """
    device = target.device
    B = target.shape[0]
    tgt_np = target.detach().cpu().numpy()  # (B, 1, H, W)
    skel_np = np.zeros_like(tgt_np, dtype=np.float32)
    for i in range(B):
        bin_seg = (tgt_np[i, 0] > 0.5)
        if bin_seg.sum() > 0:
            skel = skimage_skeletonize(bin_seg)
            skel_np[i, 0] = skel.astype(np.float32)
    return torch.from_numpy(skel_np).to(device=device, dtype=torch.float32)


# ============================================================================
# SoftSkeletonRecallLoss (官方核心 class，精简自 dice.py)
# Source: nnunetv2/training/loss/dice.py (MIC-DKFZ/Skeleton-Recall, master)
# 修改点：
#   1. 去掉 AllGatherGrad（DDP），单卡直接 sum
#   2. 去掉 apply_nonlin 参数（wrapper 层做转换）
#   3. do_bg 固定 False（官方 skeleton recall 不支持 background）
#   4. forward 签名简化：x=(B,C,H,W) prob，y=(B,1,H,W) binary skeleton GT
# ============================================================================

class SoftSkeletonRecallLoss(nn.Module):
    """
    Official Skeleton Recall Loss (single-GPU standalone).

    forward(x, y, loss_mask=None):
      x: (B, C, H, W) probability map（已做 nonlinearity），C=2 for binary
         取 x[:, 1:] 作为前景概率
      y: (B, 1, H, W) binary skeleton GT（值 0/1）
      loss_mask: (B, 1, H, W) optional mask（None = 全部有效）
    返回: scalar，-recall（负 recall，最小化 = 最大化 recall）
    """

    def __init__(self, smooth: float = 1.0):
        super().__init__()
        # do_bg=False 固定（官方要求）
        self.smooth = smooth
        self.batch_dice = False  # 官方单样本模式

    def forward(
        self,
        x: torch.Tensor,
        y: torch.Tensor,
        loss_mask: torch.Tensor | None = None,
    ) -> torch.Tensor:
        """官方 forward 逻辑（AllGatherGrad 分支去除，逻辑完整保留）。"""
        shp_x = x.shape   # (B, C, H, W)
        shp_y = y.shape   # (B, 1, H, W)

        # 官方: x = x[:, 1:]（去掉 background channel）
        x_fg = x[:, 1:]   # (B, C-1, H, W)，二值场景 C=2 → (B,1,H,W)

        # make everything shape (b, c)
        axes = list(range(2, len(shp_x)))

        with torch.no_grad():
            if len(shp_x) != len(shp_y):
                y = y.view((shp_y[0], 1, *shp_y[1:]))

            if all([i == j for i, j in zip(shp_x, shp_y)]):
                # gt is already one hot encoding
                y_onehot = y[:, 1:]
            else:
                gt = y.long()
                y_onehot = torch.zeros(shp_x, device=x.device, dtype=y.dtype)
                y_onehot.scatter_(1, gt, 1)
                y_onehot = y_onehot[:, 1:]  # (B, C-1, H, W)

            sum_gt = (
                y_onehot.sum(axes)
                if loss_mask is None
                else (y_onehot * loss_mask).sum(axes)
            )

        inter_rec = (
            (x_fg * y_onehot).sum(axes)
            if loss_mask is None
            else (x_fg * y_onehot * loss_mask).sum(axes)
        )

        if self.batch_dice:
            inter_rec = inter_rec.sum(0)
            sum_gt = sum_gt.sum(0)

        rec = (inter_rec + self.smooth) / torch.clamp(sum_gt + self.smooth, min=1e-8)
        rec = rec.mean()
        return -rec


# ============================================================================
# Harness-compatible wrapper
# ============================================================================

class SkeletonRecallLoss:
    """
    gdn2vessel harness adapter wrapper for SoftSkeletonRecallLoss.

    signature: loss_fn(logits, target, fov_mask) -> scalar tensor
      - logits   : (B,1,H,W) raw model output（sigmoid 二值）
      - target   : (B,1,H,W) binary GT [0,1]
      - fov_mask : (B,1,H,W) FOV mask (1=valid, 0=ignore)

    内部流程：
      1. sigmoid(logits) → 前景概率 (B,1,H,W)
      2. 转为 (B,2,H,W)：[p_bg, p_fg]
      3. 实时计算 skeleton GT（no_grad，skimage.morphology.skeletonize）
      4. FOV mask 以 loss_mask 传入 SoftSkeletonRecallLoss
      5. 返回 -recall（skeleton recall loss）

    官方混合：DC_SkelREC_and_CE_loss = weight_ce·CE + weight_dice·Dice + weight_srec·SkelRec
    adapter build_loss 负责混合（见 skeleton_recall.py adapter）。
    """

    def __init__(self):
        self._loss = SoftSkeletonRecallLoss(smooth=1.0)

    def __call__(
        self,
        logits: torch.Tensor,
        target: torch.Tensor,
        fov_mask: torch.Tensor,
    ) -> torch.Tensor:
        prob_fg = torch.sigmoid(logits)          # (B,1,H,W)
        prob_bg = 1.0 - prob_fg
        # (B,2,H,W) 格式，与官方 x[:, 1:] 取前景对应
        x_2ch = torch.cat([prob_bg, prob_fg], dim=1)

        # Skeleton GT：实时计算（no_grad）
        with torch.no_grad():
            skel_gt = _compute_skeleton_gt(target)  # (B,1,H,W) binary

        # FOV mask 处理：将 fov_mask 扩展为 (B,1,H,W) 传 loss_mask
        # SoftSkeletonRecallLoss 内部对 skel_gt 用 y_onehot 处理，
        # loss_mask 施加在 inter_rec 和 sum_gt 上（官方 DC_SkelREC_and_CE_loss 同）
        loss_mask = fov_mask  # (B,1,H,W)

        # target 转为 (B,1,H,W) long（官方 gt.long()）
        skel_gt_long = (skel_gt > 0.5).float()

        return self._loss(x_2ch, skel_gt_long, loss_mask=loss_mask)
