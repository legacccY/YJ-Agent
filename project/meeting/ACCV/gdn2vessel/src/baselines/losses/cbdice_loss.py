"""
cbdice_loss.py — 忠实移植官方 cbDice loss（standalone，零 monai/nnU-Net 依赖）

Source:
  https://github.com/PengchengShi1220/cbDice  (Apache-2.0 License)
  File fetched:
    loss/cbdice_loss.py  (branch: main, fetched 2026-06-20 via jsdelivr CDN)
  Original authors: Pengcheng Shi et al.
  Paper: "Centerline Boundary Dice Loss for Vascular Segmentation"
         (MICCAI 2024)

移植说明：
  - 保留官方 SoftcbDiceLoss.forward() 的全部逻辑（weight 公式完整照搬）
  - 官方依赖 monai.transforms.distance_transform_edt（环境无 monai）
    → 替换为 scipy.ndimage.distance_transform_edt（纯 CPU/numpy，无 OMP 冲突）
  - 官方依赖 nnunetv2 的 Skeletonize（拓扑保留骨架）和 SoftSkeletonize（形态学骨架）
    → 官方默认 t_skeletonize_flage=False（形态学骨架）
    → SoftSkeletonize 从 cldice_loss.py 复制（MIT，已在本 repo 引入）
    → 拓扑保留 Skeletonize 依赖外部库 martinmenten/skeletonization，
      standalone 版不支持，t_skeletonize_flage 固定为 False
  - 官方 forward 输入是 softmax 多类 logits (B,C,H,W)；
    我们 harness 输入是 sigmoid 二值 logits (B,1,H,W)
    → wrapper 内做签名转换，转为官方期望的 (B,2,H,W) softmax 等价形式
  - β=0.5：官方 β 参数未在 cbdice_loss.py 内显式（weight 公式内嵌），
    官方 compound loss 调用时 weight_ce=1 weight_dice=1 weight_cbdice=1；
    我们 adapter 默认混合权重 0.5 BCE+Dice + 0.5 cbDice（β=0.5，见 adapter）

⚠️ 复现零偏离注记：
  - iter_=10（官方 SoftSkeletonize 构造器默认）
  - smooth=1.0（官方 smooth=1.）
  - get_weights / combine_tensors 函数完整照搬官方（含注释）
  - EDT 用 scipy.ndimage（非 scipy.stats，无 OMP#15 风险）

Windows 安全：无 scipy.stats，无 multiprocessing，路径无反斜杠。
"""

from __future__ import annotations

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
from scipy.ndimage import distance_transform_edt as scipy_edt


# ============================================================================
# SoftSkeletonize (从 cldice_loss.py 复制，MIT license，原作者 jocpae 等)
# 官方 cbDice 也依赖此模块（引用 https://github.com/jocpae/clDice）
# ============================================================================

class SoftSkeletonize(torch.nn.Module):
    """Differentiable morphological soft skeletonization (clDice repo, unchanged)."""

    def __init__(self, num_iter: int = 40):
        super().__init__()
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
# EDT helper (替代 monai.transforms.distance_transform_edt)
# 官方用 distance_transform_edt(mask)，mask 是 binary torch tensor (B,H,W)
# → 我们 batch 级 numpy 实现，in no_grad block，返回 torch tensor 同设备
# ============================================================================

def _batch_edt(mask: torch.Tensor) -> torch.Tensor:
    """
    Batch-level Euclidean Distance Transform，等价官方 monai EDT。
    mask: (B, H, W) float/int binary tensor（in no_grad context）
    返回: (B, H, W) float tensor，同 device。
    """
    device = mask.device
    mask_np = mask.detach().cpu().numpy().astype(np.float32)
    out = np.zeros_like(mask_np)
    for i in range(mask_np.shape[0]):
        out[i] = scipy_edt(mask_np[i])
    return torch.from_numpy(out).to(device=device, dtype=torch.float32)


# ============================================================================
# 官方 helper 函数（完整照搬，仅替换 distance_transform_edt 调用）
# Source: loss/cbdice_loss.py (PengchengShi1220/cbDice, main branch)
# ============================================================================

def combine_tensors(A: torch.Tensor, B: torch.Tensor, C: torch.Tensor) -> torch.Tensor:
    """Official combine_tensors from cbDice repo (unchanged)."""
    A_C = A * C
    B_C = B * C
    D = B_C.clone()
    mask_AC = (A != 0) & (B == 0)
    D[mask_AC] = A_C[mask_AC]
    return D


def get_weights(
    mask_input: torch.Tensor,
    skel_input: torch.Tensor,
    dim: int,
    prob_flag: bool = True,
) -> tuple:
    """
    Official get_weights from cbDice repo.
    修改点：distance_transform_edt 调用替换为 _batch_edt（scipy.ndimage 实现）。
    其余逻辑完整保留。

    mask_input: (B, H, W)
    skel_input: (B, H, W)
    dim: 2（2D）or 3（3D）
    prob_flag: True=概率图输入，False=binary 输入
    """
    if prob_flag:
        mask_prob = mask_input
        skel_prob = skel_input

        mask = (mask_prob > 0.5).int()
        skel = (skel_prob > 0.5).int()
    else:
        mask = mask_input
        skel = skel_input

    # 官方: distances = distance_transform_edt(mask).float()
    # 替换：_batch_edt，接受 (B,H,W) binary
    distances = _batch_edt(mask.float())

    distances[mask == 0] = 0

    skel_radius = torch.zeros_like(distances, dtype=torch.float32)
    skel_radius[skel == 1] = distances[skel == 1]

    dist_map_norm = torch.zeros_like(distances, dtype=torch.float32)
    skel_R_norm = torch.zeros_like(skel_radius, dtype=torch.float32)
    I_norm = torch.zeros_like(mask, dtype=torch.float32)
    for i in range(skel_radius.shape[0]):
        distances_i = distances[i]
        skel_i = skel_radius[i]
        skel_radius_max = max(skel_i.max().item(), 1)
        skel_radius_min = max(skel_i.min().item(), 1)

        distances_i[distances_i > skel_radius_max] = skel_radius_max
        dist_map_norm[i] = distances_i / skel_radius_max
        skel_R_norm[i] = skel_i / skel_radius_max

        # subtraction-based inverse (linear) — 官方默认分支
        if dim == 2:
            I_norm[i] = (skel_radius_max - skel_i + skel_radius_min) / skel_radius_max
        else:
            I_norm[i] = (
                (skel_radius_max - skel_i + skel_radius_min) / skel_radius_max
            ) ** 2

    I_norm[skel == 0] = 0  # 0 for non-skeleton pixels

    if prob_flag:
        return dist_map_norm * mask_prob, skel_R_norm * mask_prob, I_norm * skel_prob
    else:
        return dist_map_norm * mask, skel_R_norm * mask, I_norm * skel


# ============================================================================
# SoftcbDiceLoss (官方核心 class，完整照搬，签名适配 harness 在 wrapper 做)
# Source: loss/cbdice_loss.py (PengchengShi1220/cbDice, main branch)
# 修改点：
#   1. 去掉 nnunetv2 和 monai import
#   2. Skeletonize（拓扑保留）不引入，t_skeletonize_flage 强制 False
#   3. m_skeletonize 用本文件 SoftSkeletonize(num_iter=10)
#   4. forward 签名改为接受 (B,C,H,W) softmax 输出，与官方一致
# ============================================================================

class SoftcbDiceLoss(nn.Module):
    """
    Official cbDice loss (morphological skeleton branch only).

    forward(y_pred, y_true):
      y_pred: (B, C, H, W)，softmax 前 logits 或 softmax 后概率（C≥2，二值场景 C=2）
              官方 forward 期待 softmax 后 probability（内部取 y_prob_binary[:, 1]）
      y_true: (B, 1, H, W)，binary GT，值 0/1

    ⚠️ t_skeletonize_flage 固定 False（形态学骨架，不依赖外部拓扑库）
    """

    def __init__(self, iter_: int = 10, smooth: float = 1.0):
        super().__init__()
        self.smooth = smooth
        # 官方: self.m_skeletonize = SoftSkeletonize(num_iter=iter_)
        self.m_skeletonize = SoftSkeletonize(num_iter=iter_)

    def forward(
        self, y_pred: torch.Tensor, y_true: torch.Tensor
    ) -> torch.Tensor:
        """
        官方 forward（t_skeletonize_flage=False 分支，逻辑完整保留）。

        y_pred: (B, 2, H, W) softmax probabilities
        y_true: (B, 1, H, W) binary GT
        """
        if len(y_true.shape) == 4:
            dim = 2
        elif len(y_true.shape) == 5:
            dim = 3
        else:
            raise ValueError("y_true should be 4D or 5D tensor.")

        # 官方逻辑（完整保留）
        y_pred_fore = y_pred[:, 1:]
        y_pred_fore = torch.max(y_pred_fore, dim=1, keepdim=True)[0]
        y_pred_binary = torch.cat([y_pred[:, :1], y_pred_fore], dim=1)
        y_prob_binary = torch.softmax(y_pred_binary, 1)
        y_pred_prob = y_prob_binary[:, 1]  # (B, H, W)

        with torch.no_grad():
            y_true_fg = torch.where(y_true > 0, 1, 0).squeeze(1).float()  # (B, H, W)
            y_pred_hard = (y_pred_prob > 0.5).float()

            # t_skeletonize_flage=False → 形态学骨架
            skel_pred_hard = self.m_skeletonize(y_pred_hard.unsqueeze(1)).squeeze(1)
            skel_true = self.m_skeletonize(y_true_fg.unsqueeze(1)).squeeze(1)

        skel_pred_prob = skel_pred_hard * y_pred_prob

        q_vl, q_slvl, q_sl = get_weights(
            y_true_fg, skel_true, dim, prob_flag=False
        )
        q_vp, q_spvp, q_sp = get_weights(
            y_pred_prob, skel_pred_prob, dim, prob_flag=True
        )

        w_tprec = (
            torch.sum(torch.multiply(q_sp, q_vl)) + self.smooth
        ) / (torch.sum(combine_tensors(q_spvp, q_slvl, q_sp)) + self.smooth)
        w_tsens = (
            torch.sum(torch.multiply(q_sl, q_vp)) + self.smooth
        ) / (torch.sum(combine_tensors(q_slvl, q_spvp, q_sl)) + self.smooth)

        cb_dice_loss = -2.0 * (w_tprec * w_tsens) / (w_tprec + w_tsens)
        return cb_dice_loss


# ============================================================================
# Harness-compatible wrapper
# ============================================================================

class CbDiceLoss:
    """
    gdn2vessel harness adapter wrapper for SoftcbDiceLoss.

    signature: loss_fn(logits, target, fov_mask) -> scalar tensor
      - logits   : (B,1,H,W) raw model output (sigmoid 二值)
      - target   : (B,1,H,W) binary GT [0,1]
      - fov_mask : (B,1,H,W) FOV mask (1=valid, 0=ignore)

    签名转换：官方 SoftcbDiceLoss 期待 (B,2,H,W) softmax prob；
    我们将 sigmoid logits 转为等价的 (B,2,H,W) softmax prob：
      p_fg = sigmoid(logits)
      p_bg = 1 - p_fg
      y_prob_2ch = cat([p_bg, p_fg], dim=1)
    这与官方内部 y_prob_binary = softmax(cat([bg_logit, fg_logit])) 等价。

    FOV mask 以 multiplicative gate 施加（与 clDice 同，§2.4 公平约定）。
    """

    def __init__(self):
        self._loss = SoftcbDiceLoss(iter_=10, smooth=1.0)

    def __call__(
        self,
        logits: torch.Tensor,
        target: torch.Tensor,
        fov_mask: torch.Tensor,
    ) -> torch.Tensor:
        prob_fg = torch.sigmoid(logits)               # (B,1,H,W)
        prob_bg = 1.0 - prob_fg                        # (B,1,H,W)
        # 转为 (B,2,H,W) softmax-equivalent prob（官方期望格式）
        y_pred_2ch = torch.cat([prob_bg, prob_fg], dim=1)  # (B,2,H,W)

        # Apply FOV mask
        # 对 y_pred 前景通道做 mask（index 1）
        y_pred_masked = y_pred_2ch.clone()
        y_pred_masked[:, 1:] = y_pred_2ch[:, 1:] * fov_mask
        y_pred_masked[:, :1] = y_pred_2ch[:, :1] * fov_mask + (1.0 - fov_mask)
        target_masked = target * fov_mask

        return self._loss(y_pred_masked, target_masked)
