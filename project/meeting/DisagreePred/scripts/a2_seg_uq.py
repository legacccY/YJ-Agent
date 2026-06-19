"""
a2_seg_uq.py — DisagreePred A2 UQ-proxy：分割模型不确定性

服务项目：DisagreePred，lever = A2「优于平凡基线·残余信息口径」
前置：kill1_baseline.py 已跑完（生成 lidc_disagree_labels.csv + patches）
      parse_lidc.py 已跑完（patches/ 目录就位）

设计：
  1. consensus mask：pylidc.utils.consensus(50% level) → 前景掩膜（同 patch 口径 96×96）
  2. 小型 2D U-Net（带 Dropout）：在 consensus mask 上做分割（像素级二分类）
  3. patient-level fold 划分：复用 kill1_baseline.py 的 stratified_group_kfold_split
     （同 seed=0，N_SPLITS=5，groups=patient_id）保证后续配对比较合法
  4. 逐像素不确定性 → cluster 级 UQ-proxy：
     - MC-dropout：T=20 前向，预测熵 → 前景区域均值
     - deep ensemble：k_ens=3 不同 seed 模型，像素级预测方差 → 前景均值
  5. 输出 results/a2_uq_proxy_scores.csv

超参来源：
  - U-Net 架构：LIDC 社区惯例（Ronneberger 2015 U-Net 缩减版）
    # TODO 超参待核源：encoder 层数(3层)、base channels(16)、dropout_rate(0.3)
    #   LIDC UQ 社区最常见值，但未找到单一权威论文指定此配置。
    #   若评审要求，需引用 Roy et al. (2019) Inherent Brain Segmentation Quality 等。
  - 分割 lr=1e-3, weight_decay=1e-4
    # TODO 超参待核源：LIDC 分割 lr 未找到权威统一源，1e-3 为 LIDC 社区常见初始 lr
    #   源：大量 pylidc 配套 notebook（非正式），需 researcher 确认
  - batch=8, max_epochs=30, patience=5
    # TODO 超参待核源：小数据集分割任务短训，未找到官方精确指定
  - MC-dropout T=20（任务 spec 给定，固定）
  - ensemble k_ens=3（任务 spec 给定，固定）

Windows 规范：
  - if __name__=='__main__' + freeze_support
  - num_workers=0, pin_memory=False
  - Adam foreach=False（RTX4070-Laptop SM8.9 _multi_tensor_adam 炸，同 kill1 L364）
  - 路径正斜杠/pathlib.Path

注意：需要 GPU 跑训练，主线 /loop /run-experiment 触发。
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import random
from pathlib import Path
from typing import Optional

import numpy as np
import torch
import torch.nn as nn
from torch.utils.data import DataLoader, Dataset

# ─── 路径配置 ─────────────────────────────────────────────────────────────────
SCRIPTS_DIR = Path(__file__).resolve().parent
PROJECT_DIR = SCRIPTS_DIR.parent
RESULTS_DIR = PROJECT_DIR / "results"
PATCH_DIR   = RESULTS_DIR / "patches"
LABEL_CSV   = RESULTS_DIR / "lidc_disagree_labels.csv"
OUT_CSV     = RESULTS_DIR / "a2_uq_proxy_scores.csv"
CKPT_DIR    = RESULTS_DIR / "a2_seg_ckpts"   # 保存 ensemble 模型权重

# ─── 超参 ─────────────────────────────────────────────────────────────────────
# TODO 超参待核源：以下分割超参均为 LIDC 社区惯例，未找到单一权威出处，需 researcher 确认
SEG_LR           = 1e-3       # TODO 超参待核源：分割 lr
SEG_WEIGHT_DECAY = 1e-4
SEG_BATCH        = 8
SEG_MAX_EPOCHS   = 30         # TODO 超参待核源：epoch 数
SEG_PATIENCE     = 5          # TODO 超参待核源：早停 patience
UNET_BASE_CH     = 16         # TODO 超参待核源：U-Net base channels
UNET_DEPTH       = 3          # TODO 超参待核源：encoder/decoder 层数（不含 bottleneck）
DROPOUT_RATE     = 0.3        # TODO 超参待核源：MC-dropout rate
MC_T             = 20         # MC-dropout 前向次数（任务 spec 给定）
ENS_K            = 3          # ensemble 模型数（任务 spec 给定）

# 折划分参数：与 kill1 完全一致（对齐保证配对合法）
N_SPLITS = 5
SEED     = 0

# patch 口径与 kill1/parse_lidc 一致
PATCH_SIZE = 96
HU_MIN     = -1000.0
HU_MAX     = 400.0


# ─── 复用 kill1 的折划分（直接 import 或本地复刻，带对齐注释）────────────────
def stratified_group_kfold_split(
    n_splits: int,
    labels: np.ndarray,
    groups: np.ndarray,
    seed: int = 0,
) -> list[tuple[np.ndarray, np.ndarray]]:
    """
    Patient-level StratifiedGroupKFold，纯 numpy 实现。
    与 kill1_baseline.py:stratified_group_kfold_split 完全相同实现 + 同 seed。
    保证 a2 使用同一套 patient-level 折划分，后续配对比较合法。
    """
    rng = np.random.default_rng(seed)
    unique_groups = np.unique(groups)

    pid_labels = {}
    for pid in unique_groups:
        mask = groups == pid
        majority = int(np.round(labels[mask].mean()))
        pid_labels[pid] = majority

    pos_pids = [p for p in unique_groups if pid_labels[p] == 1]
    neg_pids = [p for p in unique_groups if pid_labels[p] == 0]
    rng.shuffle(pos_pids)
    rng.shuffle(neg_pids)

    fold_patients: list[list] = [[] for _ in range(n_splits)]
    for i, pid in enumerate(pos_pids):
        fold_patients[i % n_splits].append(pid)
    for i, pid in enumerate(neg_pids):
        fold_patients[i % n_splits].append(pid)

    folds = []
    all_idx = np.arange(len(labels))
    for fold_i in range(n_splits):
        test_pids = set(fold_patients[fold_i])
        test_mask = np.array([g in test_pids for g in groups])
        test_idx  = all_idx[test_mask]
        train_idx = all_idx[~test_mask]
        folds.append((train_idx, test_idx))
    return folds


# ─── 从 kill1 复用的 val split 逻辑（与 kill1 train_fold_loop 中一致）────────
def split_train_val(
    train_val_idx: np.ndarray,
    all_patients: np.ndarray,
    rng_seed: int,
) -> tuple[np.ndarray, np.ndarray]:
    """
    从 train+val 按 patient 留 20% 作 val（用于早停）。
    与 kill1_baseline.py run_kill1_cv 内逻辑一致（seed + fold_i + 1）。
    """
    tv_patients = np.unique(all_patients[train_val_idx])
    rng_split   = np.random.default_rng(rng_seed)
    n_val_p     = max(1, len(tv_patients) // 5)
    val_pids_set = set(rng_split.choice(
        tv_patients, size=n_val_p, replace=False).tolist())
    val_mask      = np.array([all_patients[i] in val_pids_set
                               for i in train_val_idx])
    val_idx_sub   = train_val_idx[val_mask]
    train_idx_sub = train_val_idx[~val_mask]
    return train_idx_sub, val_idx_sub


# ─── 纯 numpy Dice（绕 scipy）──────────────────────────────────────────────────
def dice_numpy(pred_binary: np.ndarray, target: np.ndarray) -> float:
    pred_binary = pred_binary.astype(np.float32)
    target      = target.astype(np.float32)
    inter = (pred_binary * target).sum()
    denom = pred_binary.sum() + target.sum()
    if denom == 0:
        return 1.0   # 两者都空视为完美
    return float(2.0 * inter / denom)


# ─── consensus mask 生成 ────────────────────────────────────────────────────────
def get_consensus_mask(
    cluster: list,
    vol_shape: tuple[int, int, int],
    cz: int, cy: int, cx: int,
    patch_size: int = PATCH_SIZE,
) -> np.ndarray:
    """
    调用 pylidc.utils.consensus 以 50% level（majority vote）生成共识掩膜，
    然后裁到以 (cz, cy, cx) 为中心的 2D 轴向 patch（96×96）。

    返回 (patch_size, patch_size) float32 binary mask（0/1）。
    若 consensus 调用失败或无前景则返回全零 mask（UQ 计算会跳过前景均值）。
    """
    try:
        from pylidc.utils import consensus as pylidc_consensus
        # consensus 返回 (3D binary ndarray, padding_bounds)
        # 参数：cluster（list of Annotation），clevel=0.5（50% majority），
        #        pad 用于扩展 bbox，ret_masks=False（不需要各标注 mask）
        # 注：pylidc consensus 返回 bbox 对应的局部坐标系掩膜，需映射回 scan 坐标
        cmask, cbbox = pylidc_consensus(cluster, clevel=0.5, pad=[0, 0, 0])
        # cbbox 形如 [(z_lo, z_hi), (y_lo, y_hi), (x_lo, x_hi)]
        z_lo, z_hi = cbbox[0].start, cbbox[0].stop
        y_lo, y_hi = cbbox[1].start, cbbox[1].stop
        x_lo, x_hi = cbbox[2].start, cbbox[2].stop
    except Exception:
        return np.zeros((patch_size, patch_size), dtype=np.float32)

    # 取 consensus mask 在 cz 层的 2D 切片（scan 坐标系）
    # cmask 是局部坐标系（bbox 内），需换算 z 偏移
    local_z = cz - z_lo
    if local_z < 0 or local_z >= cmask.shape[0]:
        return np.zeros((patch_size, patch_size), dtype=np.float32)

    slice_mask_local = cmask[local_z].astype(np.float32)  # (cbbox_h, cbbox_w)

    # 把局部 mask 映射回全 scan 坐标系的同尺寸 2D 平面（稀疏填充）
    H, W = vol_shape[1], vol_shape[2]
    full_mask = np.zeros((H, W), dtype=np.float32)
    full_mask[y_lo:y_hi, x_lo:x_hi] = slice_mask_local

    # 裁 96×96 patch（同 extract_patch_2d 逻辑）
    half  = patch_size // 2
    y0, y1 = cy - half, cy + half
    x0, x1 = cx - half, cx + half
    patch_mask = np.zeros((patch_size, patch_size), dtype=np.float32)
    sy0, sy1 = max(y0, 0), min(y1, H)
    sx0, sx1 = max(x0, 0), min(x1, W)
    dy0, dy1 = sy0 - y0, sy1 - y0
    dx0, dx1 = sx0 - x0, sx1 - x0
    if sy0 < sy1 and sx0 < sx1:
        patch_mask[dy0:dy1, dx0:dx1] = full_mask[sy0:sy1, sx0:sx1]
    return patch_mask


# ─── 2D U-Net（带 Dropout，MC-dropout 用）─────────────────────────────────────
class ConvBlock(nn.Module):
    """2× (Conv→BN→ReLU)，带可选 Dropout。"""
    def __init__(self, in_ch: int, out_ch: int, dropout: float = 0.0) -> None:
        super().__init__()
        layers: list[nn.Module] = [
            nn.Conv2d(in_ch, out_ch, 3, padding=1, bias=False),
            nn.BatchNorm2d(out_ch),
            nn.ReLU(inplace=True),
        ]
        if dropout > 0:
            layers.append(nn.Dropout2d(dropout))
        layers += [
            nn.Conv2d(out_ch, out_ch, 3, padding=1, bias=False),
            nn.BatchNorm2d(out_ch),
            nn.ReLU(inplace=True),
        ]
        self.block = nn.Sequential(*layers)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.block(x)


class UNet2D(nn.Module):
    """
    小型 2D U-Net 用于 LIDC 结节分割（1 通道输入→1 通道输出）。
    depth=3：encoder 有 3 个下采样级；base_ch=16 起始通道。
    Dropout2d 在每个 ConvBlock 内，推理时可手动开启以实现 MC-dropout。

    # TODO 超参待核源：depth=3, base_ch=16 参考 LIDC 社区 notebook 惯例，
    #   非单一权威论文，需 researcher 确认架构设置。
    """
    def __init__(
        self,
        in_ch: int = 1,
        out_ch: int = 1,
        base_ch: int = UNET_BASE_CH,
        depth: int = UNET_DEPTH,
        dropout: float = DROPOUT_RATE,
    ) -> None:
        super().__init__()
        self.depth = depth

        # Encoder
        self.encoders = nn.ModuleList()
        self.pools    = nn.ModuleList()
        ch = in_ch
        enc_chs = []
        for i in range(depth):
            out = base_ch * (2 ** i)
            self.encoders.append(ConvBlock(ch, out, dropout=dropout))
            self.pools.append(nn.MaxPool2d(2))
            enc_chs.append(out)
            ch = out

        # Bottleneck
        bottleneck_ch = base_ch * (2 ** depth)
        self.bottleneck = ConvBlock(ch, bottleneck_ch, dropout=dropout)
        ch = bottleneck_ch

        # Decoder
        self.upconvs  = nn.ModuleList()
        self.decoders = nn.ModuleList()
        for i in range(depth - 1, -1, -1):
            skip_ch = enc_chs[i]
            out = skip_ch
            self.upconvs.append(
                nn.ConvTranspose2d(ch, out, kernel_size=2, stride=2)
            )
            self.decoders.append(ConvBlock(out + skip_ch, out, dropout=dropout))
            ch = out

        self.head = nn.Conv2d(ch, out_ch, 1)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        # Encoder
        skips: list[torch.Tensor] = []
        for enc, pool in zip(self.encoders, self.pools):
            x = enc(x)
            skips.append(x)
            x = pool(x)

        # Bottleneck
        x = self.bottleneck(x)

        # Decoder
        for upconv, dec, skip in zip(self.upconvs, self.decoders, reversed(skips)):
            x = upconv(x)
            # 处理奇数尺寸的尺寸不匹配
            if x.shape != skip.shape:
                x = nn.functional.interpolate(
                    x, size=skip.shape[2:], mode="bilinear", align_corners=False
                )
            x = torch.cat([x, skip], dim=1)
            x = dec(x)

        return self.head(x)   # (B, 1, H, W)，logit


def enable_dropout(model: nn.Module) -> None:
    """推理时打开 Dropout（MC-dropout 用）。"""
    for m in model.modules():
        if isinstance(m, (nn.Dropout, nn.Dropout2d)):
            m.train()


# ─── Dataset ─────────────────────────────────────────────────────────────────
class SegDataset(Dataset):
    """
    分割 Dataset：输入 = 灰度 patch (1, H, W)，target = consensus mask (1, H, W)。
    rows 中须包含 patch_path + consensus_mask_path（或在线生成）。
    """
    def __init__(
        self,
        rows: list[dict],
        indices: np.ndarray,
        augment: bool = False,
    ) -> None:
        self.items   = [rows[i] for i in indices]
        self.augment = augment

    def __len__(self) -> int:
        return len(self.items)

    def __getitem__(self, idx: int):
        row  = self.items[idx]
        patch = np.load(row["patch_path"]).astype(np.float32)  # (96, 96)
        mask  = np.load(row["mask_path"]).astype(np.float32)   # (96, 96)

        if self.augment:
            if random.random() > 0.5:
                patch = np.fliplr(patch).copy()
                mask  = np.fliplr(mask).copy()
            # +-10 度旋转（CT 禁垂直翻转，复用 kill1 一致增强）
            angle = random.uniform(-10.0, 10.0)
            patch = _rotate_patch_2d(patch, angle)
            mask  = _rotate_patch_2d(mask, angle)

        x = torch.from_numpy(patch).unsqueeze(0)   # (1, 96, 96)
        y = torch.from_numpy(mask).unsqueeze(0)    # (1, 96, 96)
        return x, y


# ─── 旋转（纯 numpy，绕 scipy，与 kill1 逻辑一致）─────────────────────────────
def _rotate_patch_2d(patch: np.ndarray, angle_deg: float) -> np.ndarray:
    """纯 numpy 双线性旋转（绕中心）。复用 kill1_baseline._rotate_patch。"""
    if abs(angle_deg) < 0.5:
        return patch
    h, w = patch.shape
    cx, cy_c = w / 2.0, h / 2.0
    angle_rad = math.radians(angle_deg)
    cos_a = math.cos(angle_rad)
    sin_a = math.sin(angle_rad)

    ys, xs = np.meshgrid(np.arange(h), np.arange(w), indexing="ij")
    xs_c = xs - cx
    ys_c = ys - cy_c
    xs_src = cos_a * xs_c + sin_a * ys_c + cx
    ys_src = -sin_a * xs_c + cos_a * ys_c + cy_c

    xs_src = np.clip(xs_src, 0, w - 1)
    ys_src = np.clip(ys_src, 0, h - 1)
    x0 = np.floor(xs_src).astype(np.int32)
    y0 = np.floor(ys_src).astype(np.int32)
    x1 = np.minimum(x0 + 1, w - 1)
    y1 = np.minimum(y0 + 1, h - 1)
    dx = xs_src - x0
    dy = ys_src - y0

    out = (patch[y0, x0] * (1 - dx) * (1 - dy)
           + patch[y0, x1] * dx * (1 - dy)
           + patch[y1, x0] * (1 - dx) * dy
           + patch[y1, x1] * dx * dy)
    return out.astype(np.float32)


# ─── 训练 / 推理 ──────────────────────────────────────────────────────────────
def train_seg_epoch(
    model: nn.Module,
    loader: DataLoader,
    optimizer: torch.optim.Optimizer,
    device: torch.device,
) -> float:
    model.train()
    total_loss = 0.0
    criterion  = nn.BCEWithLogitsLoss()
    for imgs, masks in loader:
        imgs  = imgs.to(device, non_blocking=False)
        masks = masks.to(device, non_blocking=False)
        optimizer.zero_grad()
        logits = model(imgs)                  # (B, 1, H, W)
        loss   = criterion(logits, masks)
        loss.backward()
        optimizer.step()
        total_loss += loss.item() * imgs.size(0)
    return total_loss / max(len(loader.dataset), 1)


@torch.no_grad()
def eval_seg_epoch(
    model: nn.Module,
    loader: DataLoader,
    device: torch.device,
) -> float:
    """返回平均 Dice（用于早停监控）。"""
    model.eval()
    dice_list = []
    for imgs, masks in loader:
        imgs  = imgs.to(device, non_blocking=False)
        masks = masks.cpu().numpy()
        logits = model(imgs).cpu().numpy()
        preds  = (logits > 0.0).astype(np.float32)
        for b in range(preds.shape[0]):
            dice_list.append(dice_numpy(preds[b, 0], masks[b, 0]))
    return float(np.mean(dice_list)) if dice_list else 0.0


def train_seg_fold(
    rows: list[dict],
    train_idx: np.ndarray,
    val_idx: np.ndarray,
    seed: int,
    device: torch.device,
    ckpt_path: Optional[Path] = None,
    verbose: bool = True,
) -> nn.Module:
    """
    训练单个分割模型（单折或 ensemble 的一个成员）。
    使用 Dice 做早停指标（分割任务标准）。
    返回加载了最优权重的模型。
    """
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)

    train_set = SegDataset(rows, train_idx, augment=True)
    val_set   = SegDataset(rows, val_idx,   augment=False)
    train_loader = DataLoader(train_set, batch_size=SEG_BATCH, shuffle=True,
                              num_workers=0, pin_memory=False)
    val_loader   = DataLoader(val_set,   batch_size=SEG_BATCH, shuffle=False,
                              num_workers=0, pin_memory=False)

    model = UNet2D().to(device)
    # foreach=False：绕开 RTX4070-Laptop SM8.9 _multi_tensor_adam CUDA illegal memory access
    # （kill1_baseline.py:364 同款注释，逐参数循环实现，数学等价）
    optimizer = torch.optim.Adam(
        model.parameters(), lr=SEG_LR, weight_decay=SEG_WEIGHT_DECAY, foreach=False
    )

    best_val_dice    = -1.0
    best_state       = None
    patience_counter = 0

    for epoch in range(SEG_MAX_EPOCHS):
        tr_loss   = train_seg_epoch(model, train_loader, optimizer, device)
        val_dice  = eval_seg_epoch(model, val_loader, device)

        if val_dice > best_val_dice:
            best_val_dice    = val_dice
            best_state       = {k: v.cpu().clone() for k, v in model.state_dict().items()}
            patience_counter = 0
        else:
            patience_counter += 1

        if verbose and ((epoch + 1) % 5 == 0 or patience_counter == SEG_PATIENCE):
            print(f"    epoch {epoch+1:3d} | tr_loss={tr_loss:.4f} "
                  f"| val_dice={val_dice:.4f} | best={best_val_dice:.4f} "
                  f"| patience={patience_counter}/{SEG_PATIENCE}")

        if patience_counter >= SEG_PATIENCE:
            if verbose:
                print(f"    [early_stop] epoch {epoch+1}")
            break

    if best_state is not None:
        model.load_state_dict(best_state)

    if ckpt_path is not None:
        ckpt_path.parent.mkdir(parents=True, exist_ok=True)
        torch.save(model.state_dict(), str(ckpt_path))
        if verbose:
            print(f"    [ckpt] saved -> {ckpt_path}")

    return model


# ─── MC-dropout UQ 推理 ────────────────────────────────────────────────────────
@torch.no_grad()
def mc_dropout_uq(
    model: nn.Module,
    patch: np.ndarray,
    mask_fg: np.ndarray,
    device: torch.device,
    T: int = MC_T,
) -> float:
    """
    MC-dropout UQ：T=20 次前向（dropout 开），计算像素级预测熵，
    返回前景区域（mask_fg > 0.5）的均值预测熵。
    若前景为空则返回全图均值（保守估计）。
    """
    enable_dropout(model)
    img_t = torch.from_numpy(patch).unsqueeze(0).unsqueeze(0).to(device)  # (1,1,H,W)

    probs_list = []
    with torch.no_grad():
        for _ in range(T):
            logit = model(img_t)                    # (1,1,H,W)
            prob  = torch.sigmoid(logit).squeeze().cpu().numpy()  # (H,W)
            probs_list.append(prob)
    probs = np.stack(probs_list, axis=0)  # (T, H, W)

    # 预测熵：E[-p*log(p) - (1-p)*log(1-p)] over T samples
    mean_prob = probs.mean(axis=0)  # (H, W)，平均后再算熵（predictive entropy）
    eps = 1e-7
    entropy = -(mean_prob * np.log(mean_prob + eps)
                + (1 - mean_prob) * np.log(1 - mean_prob + eps))  # (H, W)

    fg = mask_fg > 0.5
    if fg.any():
        return float(entropy[fg].mean())
    else:
        return float(entropy.mean())   # 全图均值（前景空时保守回退）


# ─── Ensemble UQ 推理 ─────────────────────────────────────────────────────────
@torch.no_grad()
def ensemble_uq(
    models: list[nn.Module],
    patch: np.ndarray,
    mask_fg: np.ndarray,
    device: torch.device,
) -> float:
    """
    Deep ensemble UQ：ENS_K=3 个模型，像素级预测方差，
    返回前景区域的均值方差。
    """
    img_t = torch.from_numpy(patch).unsqueeze(0).unsqueeze(0).to(device)  # (1,1,H,W)
    probs_list = []
    for m in models:
        m.eval()
        logit = m(img_t)
        prob  = torch.sigmoid(logit).squeeze().cpu().numpy()  # (H,W)
        probs_list.append(prob)
    probs = np.stack(probs_list, axis=0)  # (K, H, W)

    pixel_var = probs.var(axis=0)  # (H, W)

    fg = mask_fg > 0.5
    if fg.any():
        return float(pixel_var[fg].mean())
    else:
        return float(pixel_var.mean())


# ─── consensus mask 预存（避免推理时反复调 pylidc）──────────────────────────
def precompute_masks(label_csv: Path, mask_dir: Path) -> list[dict]:
    """
    对所有 cluster 预计算 consensus mask 并存为 npy（mask_dir）。
    返回扩充了 mask_path 字段的 rows。

    使用 pylidc 解析，依赖 ~/.pylidcrc 配置。
    """
    # monkey-patch numpy aliases（同 parse_lidc.py）
    np.int    = int
    np.float  = float
    np.bool   = bool
    np.object = object

    import configparser as _cp
    if not hasattr(_cp, "SafeConfigParser"):
        _cp.SafeConfigParser = _cp.ConfigParser

    import pylidc as pl

    mask_dir.mkdir(parents=True, exist_ok=True)

    # 读 label CSV
    rows = []
    with open(str(label_csv), newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(dict(row))

    print(f"[mask] total {len(rows)} clusters to process")

    # 按 patient 批量处理（避免重复加载 scan volume）
    from collections import defaultdict
    pid_to_rows: dict[str, list[tuple[int, dict]]] = defaultdict(list)
    for i, row in enumerate(rows):
        pid_to_rows[row["patient_id"]].append((i, row))

    all_scans = pl.query(pl.Scan).all()
    scan_map  = {s.patient_id: s for s in all_scans}

    for pid, row_list in sorted(pid_to_rows.items()):
        scan = scan_map.get(pid)
        if scan is None:
            print(f"  [WARN] patient {pid} not in pylidc DB, zero masks")
            for i, row in row_list:
                _save_zero_mask(rows, i, row, mask_dir)
            continue

        try:
            vol = scan.to_volume()
            vol_shape = vol.shape
        except Exception as e:
            print(f"  [WARN] {pid} to_volume failed: {e}, zero masks")
            for i, row in row_list:
                _save_zero_mask(rows, i, row, mask_dir)
            continue

        clusters = scan.cluster_annotations(tol=None)

        # cluster_idx → (cluster, row_i, row)
        for i, row in row_list:
            cluster_id = row["nodule_cluster_id"]  # {pid}_c{idx:03d}
            # 从 cluster_id 解析 cluster_idx
            try:
                cidx = int(cluster_id.split("_c")[-1])
            except (ValueError, IndexError):
                _save_zero_mask(rows, i, row, mask_dir)
                continue

            if cidx >= len(clusters):
                _save_zero_mask(rows, i, row, mask_dir)
                continue

            cluster = clusters[cidx]

            # 从 patch_path 解析 cz/cy/cx（通过重新计算质心）
            centroids = []
            for ann in cluster:
                try:
                    cy_a, cx_a, cz_a = ann.centroid
                    centroids.append((int(round(cz_a)), int(round(cy_a)), int(round(cx_a))))
                except Exception:
                    pass

            if not centroids:
                _save_zero_mask(rows, i, row, mask_dir)
                continue

            cz = int(round(np.mean([c[0] for c in centroids])))
            cy = int(round(np.mean([c[1] for c in centroids])))
            cx = int(round(np.mean([c[2] for c in centroids])))

            mask = get_consensus_mask(cluster, vol_shape, cz, cy, cx, PATCH_SIZE)
            mask_path = mask_dir / f"{cluster_id}_mask.npy"
            np.save(str(mask_path), mask)
            rows[i]["mask_path"] = str(mask_path).replace("\\", "/")

        print(f"  [mask] {pid}: {len(row_list)} clusters done")

    # 确认所有 rows 都有 mask_path
    missing = [r for r in rows if "mask_path" not in r or not r["mask_path"]]
    if missing:
        print(f"  [WARN] {len(missing)} clusters missing mask, using zero mask")
        for r in missing:
            _save_zero_mask_direct(r, mask_dir)

    return rows


def _save_zero_mask(rows: list[dict], i: int, row: dict, mask_dir: Path) -> None:
    cluster_id = row.get("nodule_cluster_id", f"unk_{i}")
    mask_path  = mask_dir / f"{cluster_id}_mask.npy"
    np.save(str(mask_path), np.zeros((PATCH_SIZE, PATCH_SIZE), dtype=np.float32))
    rows[i]["mask_path"] = str(mask_path).replace("\\", "/")


def _save_zero_mask_direct(row: dict, mask_dir: Path) -> None:
    cluster_id = row.get("nodule_cluster_id", "unk")
    mask_path  = mask_dir / f"{cluster_id}_mask.npy"
    np.save(str(mask_path), np.zeros((PATCH_SIZE, PATCH_SIZE), dtype=np.float32))
    row["mask_path"] = str(mask_path).replace("\\", "/")


# ─── 主流程 ──────────────────────────────────────────────────────────────────
def run_a2_seg_uq(
    rows: list[dict],
    device: torch.device,
    seed: int = SEED,
    verbose: bool = True,
) -> None:
    """
    主流程：
    1. 生成同 kill1 的 5-fold patient-level 折划分
    2. 对每折：训练 MC-dropout 分割模型 + ENS_K=3 ensemble 模型
    3. 对每 cluster：计算 MC-dropout 熵均值 + ensemble 方差均值
    4. 输出 a2_uq_proxy_scores.csv
    """
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    CKPT_DIR.mkdir(parents=True, exist_ok=True)

    all_labels   = np.array([int(r["disagree_binary"]) for r in rows])
    all_patients = np.array([r["patient_id"] for r in rows])
    all_k        = np.array([int(r["k_annotators"]) for r in rows])
    all_k_solo   = np.array([r["k_solo"] for r in rows])
    cluster_ids  = [r["nodule_cluster_id"] for r in rows]

    unique_patients = np.unique(all_patients)
    print(f"[a2] {len(rows)} clusters / {len(unique_patients)} patients / "
          f"n_splits={N_SPLITS}")

    # 折划分（与 kill1 完全对齐：同函数、同 seed）
    folds = stratified_group_kfold_split(N_SPLITS, all_labels, all_patients, seed=seed)

    # 输出 UQ 分数数组
    uq_mcdropout = np.full(len(rows), float("nan"), dtype=np.float64)
    uq_ensemble  = np.full(len(rows), float("nan"), dtype=np.float64)

    print("\n[a2] Starting 5-fold patient-level seg UQ training ...")

    for fold_i, (train_val_idx, test_idx) in enumerate(folds):
        print(f"\n  [fold {fold_i+1}/{N_SPLITS}] "
              f"train+val={len(train_val_idx)} test={len(test_idx)}")

        # 二级 val split（与 kill1 对齐：seed + fold_i + 1）
        train_idx, val_idx = split_train_val(
            train_val_idx, all_patients, rng_seed=seed + fold_i + 1
        )
        print(f"    train={len(train_idx)} val={len(val_idx)} test={len(test_idx)}")

        # ── MC-dropout 模型：单个模型，推理时开 dropout ────────────────────
        mc_ckpt = CKPT_DIR / f"fold{fold_i+1}_mcdropout.pt"
        print(f"    [MC-dropout] training fold {fold_i+1} ...")
        mc_model = train_seg_fold(
            rows, train_idx, val_idx,
            seed=seed + fold_i * 100,
            device=device,
            ckpt_path=mc_ckpt,
            verbose=verbose,
        )
        mc_model.eval()

        # ── Ensemble：ENS_K=3 个不同 seed 的模型 ──────────────────────────
        ens_models = []
        for ens_i in range(ENS_K):
            ens_seed  = seed + fold_i * 100 + (ens_i + 1) * 1000
            ens_ckpt  = CKPT_DIR / f"fold{fold_i+1}_ens{ens_i}.pt"
            print(f"    [ensemble] training fold {fold_i+1} member {ens_i+1}/{ENS_K} ...")
            ens_m = train_seg_fold(
                rows, train_idx, val_idx,
                seed=ens_seed,
                device=device,
                ckpt_path=ens_ckpt,
                verbose=verbose,
            )
            ens_m.eval()
            ens_models.append(ens_m)

        # ── 对 test_idx 推理 UQ ────────────────────────────────────────────
        print(f"    [infer] computing UQ for {len(test_idx)} test clusters ...")
        for idx in test_idx:
            row      = rows[idx]
            patch    = np.load(row["patch_path"]).astype(np.float32)
            mask_fg  = np.load(row["mask_path"]).astype(np.float32)

            uq_mcdropout[idx] = mc_dropout_uq(mc_model, patch, mask_fg, device, T=MC_T)
            uq_ensemble[idx]  = ensemble_uq(ens_models, patch, mask_fg, device)

        # 显存清理
        del mc_model
        for m in ens_models:
            del m
        if torch.cuda.is_available():
            torch.cuda.empty_cache()

        n_nan_mc  = int(np.isnan(uq_mcdropout[test_idx]).sum())
        n_nan_ens = int(np.isnan(uq_ensemble[test_idx]).sum())
        print(f"    [fold {fold_i+1}] done. NaN mc={n_nan_mc} ens={n_nan_ens}")

    # ── 写 CSV ────────────────────────────────────────────────────────────────
    assert not np.isnan(uq_mcdropout).all(), "[BUG] all MC-dropout UQ are nan"
    fieldnames = ["cluster_id", "patient_id", "disagree_binary", "k", "k_solo",
                  "uq_mcdropout", "uq_ensemble"]
    with open(str(OUT_CSV), "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for i, row in enumerate(rows):
            writer.writerow({
                "cluster_id":      row["nodule_cluster_id"],
                "patient_id":      row["patient_id"],
                "disagree_binary": int(row["disagree_binary"]),
                "k":               int(row["k_annotators"]),
                "k_solo":          row["k_solo"],
                "uq_mcdropout":    float(uq_mcdropout[i]) if not np.isnan(uq_mcdropout[i]) else "",
                "uq_ensemble":     float(uq_ensemble[i])  if not np.isnan(uq_ensemble[i])  else "",
            })
    print(f"\n[output] a2 UQ CSV -> {OUT_CSV}")

    # 简单统计
    valid_mc  = uq_mcdropout[~np.isnan(uq_mcdropout)]
    valid_ens = uq_ensemble[~np.isnan(uq_ensemble)]
    print(f"[a2] MC-dropout: n={len(valid_mc)} mean={valid_mc.mean():.4f} "
          f"std={valid_mc.std():.4f}")
    print(f"[a2] Ensemble:   n={len(valid_ens)} mean={valid_ens.mean():.4f} "
          f"std={valid_ens.std():.4f}")


# ─── 主函数 ──────────────────────────────────────────────────────────────────
def main() -> None:
    import multiprocessing
    multiprocessing.freeze_support()   # Windows spawn required

    parser = argparse.ArgumentParser(
        description="DisagreePred A2 UQ-proxy: 2D UNet seg uncertainty on LIDC")
    parser.add_argument("--label_csv", type=str, default=str(LABEL_CSV))
    parser.add_argument("--cpu", action="store_true", help="Force CPU (smoke test)")
    parser.add_argument("--smoke", type=int, default=0,
                        help="Smoke mode: use first N rows (0=full)")
    parser.add_argument("--seed", type=int, default=SEED)
    parser.add_argument("--precompute_masks_only", action="store_true",
                        help="Only precompute consensus masks then exit")
    args = parser.parse_args()

    if args.cpu or not torch.cuda.is_available():
        device = torch.device("cpu")
        print("[device] CPU")
    else:
        device = torch.device("cuda")
        print(f"[device] {torch.cuda.get_device_name(0)}")

    label_csv = Path(args.label_csv)
    assert label_csv.exists(), (
        f"[DATA] label CSV not found: {label_csv}\n"
        "Please run parse_lidc.py first."
    )

    # Step 1：预计算 consensus masks
    mask_dir = RESULTS_DIR / "a2_seg_masks"
    print("[a2] Step 1: precomputing consensus masks ...")
    rows = precompute_masks(label_csv, mask_dir)

    if args.precompute_masks_only:
        print("[a2] --precompute_masks_only: done, exit.")
        return

    # smoke
    if args.smoke > 0:
        rows = rows[: args.smoke]
        print(f"[smoke] truncated to {args.smoke} rows")

    # Step 2：训练 + UQ 推理
    print("[a2] Step 2: training seg models + UQ inference ...")
    run_a2_seg_uq(rows, device, seed=args.seed)


if __name__ == "__main__":
    main()
