"""
harness.py
==========
FetalSSBench 统一训练 harness。

支持 5 种 SSL 方法：
  supervised    — 仅用标注数据 CE loss
  mean_teacher  — EMA teacher + MSE 一致性（MT_EMA=0.99, cons=0.1, rampup=40ep）
  cps           — 双 UNet 互换伪标签（cons=0.1, sigmoid rampup 200 epoch 换算）
  uamt          — MT + MC-dropout T=8 不确定性掩码（thresh=(0.75+0.25*rampup)*ln2）
  fixmatch      — 弱增广伪标签(conf=0.8) + 强增广一致性（cons=0.1 sigmoid rampup）

超参真源：project/meeting/FetalSSBench/reference/SSL4MIS_hparams.md（禁臆想）
对照协议：训练预算统一（Adam lr=1e-3 / CosineAnneal / base_ch=32 / batch=4 / AMP）
评估：Dice+HD95，前景类 per-structure；MT/UAMT/CPS 用 teacher/model1 评估

用法：
  # 烟测
  python harness.py --method cps --dataset hc18 --quick

  # 全量
  python harness.py --method cps --dataset hc18 --ratio 0.05 --seed 0

结果：
  results/results.csv
  results/state.json（已跑 run 自动跳过，支持续跑）
"""

from __future__ import annotations

import argparse
import copy
import csv
import json
import math
import os
import random
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# ---------- Windows OMP 安全 ----------
os.environ.setdefault("OMP_NUM_THREADS", "1")

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.cuda.amp import GradScaler, autocast
from torch.utils.data import DataLoader

# 本地模块（相对路径，harness.py 在 src/ 下）
_SRC_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(_SRC_DIR))

from datasets import get_dataloaders, DATASET_INFO

# UNet：优先从本 src/ 取，否则 fallback 到 pilot 目录
try:
    from unet import UNet
except ImportError:
    _PILOT_DIR = _SRC_DIR.parent.parent / "_run011_pilot"
    sys.path.insert(0, str(_PILOT_DIR))
    from unet import UNet

# ------------------------------------------------------------------ #
# 路径 & 结果
# ------------------------------------------------------------------ #
RESULTS_DIR = _SRC_DIR / "results"
# RESULTS_TAG 环境变量：每个并行 chunk 写自己 results_<tag>.csv + state_<tag>.json，防并发写竞争
_TAG = os.environ.get("RESULTS_TAG", "")
_SUF = f"_{_TAG}" if _TAG else ""
RESULTS_CSV = RESULTS_DIR / f"results{_SUF}.csv"
STATE_JSON = RESULTS_DIR / f"state{_SUF}.json"

# ------------------------------------------------------------------ #
# 固定超参（对照协议，禁修改）
# ------------------------------------------------------------------ #
IN_CHANNELS = 1
BASE_CHANNELS = 32
IMAGE_SIZE = 256
BATCH_SIZE = 4
LR = 1e-3
WEIGHT_DECAY = 1e-4
N_EPOCHS = 100

# SSL 方法特有超参（来自 SSL4MIS_hparams.md，复现零偏离）
MT_EMA_DECAY = 0.99            # Mean Teacher / UAMT EMA 衰减
MT_CONSISTENCY = 0.1           # 一致性权重上限（MT/CPS/UAMT/FixMatch 统一）
MT_RAMPUP_EPOCHS = 40          # MeanTeacher sigmoid rampup 长度（epoch 制）

# CPS（官方 iteration-based rampup=200，以 iteration//150 为输入）
# 我们转为 epoch-based：每 epoch 约 max(1, n_labeled//batch) iterations
# rampup 输入按 epoch（见 _cps_rampup 函数注释）
CPS_CONSISTENCY = 0.1          # SSL4MIS CPS 官方值
CPS_RAMPUP_EPOCHS = 200        # 官方 iteration 单位 200，转 epoch 保守取 200

# UAMT 官方超参（SSL4MIS train_uncertainty_aware_mean_teacher_2D.py）
UAMT_EMA_DECAY = 0.99
UAMT_CONSISTENCY = 0.1
UAMT_RAMPUP_EPOCHS = 200       # 官方 iteration 200，转 epoch 制
UAMT_T = 8                     # MC-dropout 次数（官方 T=8）

# FixMatch
FIXMATCH_CONF_THRESH = 0.8     # 官方 SSL4MIS conf_thresh（≠ 原始 FixMatch 0.95）
FIXMATCH_CONSISTENCY = 0.1     # 并入一致性权重 sigmoid rampup
FIXMATCH_RAMPUP_EPOCHS = 200

# ------------------------------------------------------------------ #
# 工具函数
# ------------------------------------------------------------------ #

def set_seed(seed: int):
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)


def sigmoid_rampup(current: int, rampup_length: int) -> float:
    """Sigmoid ramp-up，0→1（SSL4MIS 同款）。"""
    if rampup_length == 0:
        return 1.0
    t = np.clip(current / rampup_length, 0.0, 1.0)
    return float(np.exp(-5.0 * (1.0 - t) ** 2))


def update_ema(model: nn.Module, ema_model: nn.Module, alpha: float):
    """EMA 更新：ema = alpha * ema + (1-alpha) * model。"""
    with torch.no_grad():
        for ema_p, p in zip(ema_model.parameters(), model.parameters()):
            ema_p.data.mul_(alpha).add_(p.data * (1.0 - alpha))


def create_model(num_classes: int) -> nn.Module:
    """创建 UNet，Kaiming 默认初始化。"""
    return UNet(in_channels=IN_CHANNELS, num_classes=num_classes, base_channels=BASE_CHANNELS)


def create_ema_model(model: nn.Module) -> nn.Module:
    """深拷贝 model 作为 EMA teacher，关闭梯度。"""
    ema = copy.deepcopy(model)
    for p in ema.parameters():
        p.requires_grad_(False)
    return ema


# ------------------------------------------------------------------ #
# 评估（Dice + HD95，per-structure）
# ------------------------------------------------------------------ #

def compute_dice_per_class(
    preds: torch.Tensor, targets: torch.Tensor, num_classes: int
) -> List[float]:
    """
    计算每个前景类的 Dice（排除 class 0 背景）。
    preds/targets: [N, H, W] int64
    返回 list, len = num_classes - 1
    """
    dices = []
    for c in range(1, num_classes):
        pred_c = (preds == c).float()
        tgt_c = (targets == c).float()
        inter = (pred_c * tgt_c).sum()
        union = pred_c.sum() + tgt_c.sum()
        if union < 1e-6:
            dices.append(1.0)
        else:
            dices.append((2.0 * inter / union).item())
    return dices


def compute_hd95(
    preds: torch.Tensor, targets: torch.Tensor, num_classes: int
) -> List[float]:
    """
    计算 HD95（per class，前景类）。
    使用 scipy.ndimage.distance_transform_edt（不走 OpenMP，安全）。
    """
    from scipy.ndimage import distance_transform_edt  # noqa: 仅 ndimage，非 stats，无 OMP 冲突

    preds_np = preds.cpu().numpy()
    tgts_np = targets.cpu().numpy()
    hds = []

    for c in range(1, num_classes):
        pred_c = (preds_np == c).astype(np.uint8)
        tgt_c = (tgts_np == c).astype(np.uint8)

        if pred_c.sum() == 0 and tgt_c.sum() == 0:
            hds.append(0.0)
            continue
        if pred_c.sum() == 0 or tgt_c.sum() == 0:
            diag = float(np.sqrt(pred_c.shape[-2] ** 2 + pred_c.shape[-1] ** 2))
            hds.append(diag)
            continue

        pred_flat = pred_c.reshape(-1, pred_c.shape[-2], pred_c.shape[-1])
        tgt_flat = tgt_c.reshape(-1, tgt_c.shape[-2], tgt_c.shape[-1])
        hd_batch = []
        for i in range(pred_flat.shape[0]):
            p, t = pred_flat[i], tgt_flat[i]
            if p.sum() == 0 or t.sum() == 0:
                continue
            d_p2t = distance_transform_edt(1 - t)[p == 1]
            d_t2p = distance_transform_edt(1 - p)[t == 1]
            surf = np.concatenate([d_p2t, d_t2p])
            hd_batch.append(float(np.percentile(surf, 95)))
        hds.append(float(np.mean(hd_batch)) if hd_batch else 0.0)

    return hds


def evaluate(
    model: nn.Module, loader: DataLoader, device: torch.device, num_classes: int
) -> Tuple[List[float], List[float]]:
    """在 loader 上评估，返回 (dice_list, hd95_list)。"""
    model.eval()
    all_preds, all_targets = [], []

    with torch.no_grad():
        for batch in loader:
            imgs, lbls = batch[0].to(device), batch[1]
            with autocast(enabled=device.type == "cuda"):
                logits = model(imgs)
            preds = logits.argmax(dim=1).cpu()
            all_preds.append(preds)
            all_targets.append(lbls)

    all_preds = torch.cat(all_preds, dim=0)
    all_targets = torch.cat(all_targets, dim=0)

    dices = compute_dice_per_class(all_preds, all_targets, num_classes)
    hds = compute_hd95(all_preds, all_targets, num_classes)
    return dices, hds


# ------------------------------------------------------------------ #
# 无标注 iterator（循环）
# ------------------------------------------------------------------ #

class InfiniteLoader:
    """把 DataLoader 包成无限迭代器，每轮 exhausted 自动重置。"""
    def __init__(self, loader: DataLoader):
        self.loader = loader
        self._iter = iter(loader)

    def next(self):
        try:
            return next(self._iter)
        except StopIteration:
            self._iter = iter(self.loader)
            return next(self._iter)


# ------------------------------------------------------------------ #
# 1. Supervised
# ------------------------------------------------------------------ #

def train_supervised(
    labeled_loader: DataLoader,
    test_loader: DataLoader,
    device: torch.device,
    n_epochs: int,
    num_classes: int,
    run_id: str,
) -> dict:
    model = create_model(num_classes).to(device)
    optimizer = torch.optim.Adam(model.parameters(), lr=LR, weight_decay=WEIGHT_DECAY)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=n_epochs)
    scaler = GradScaler(enabled=device.type == "cuda")
    ce_loss = nn.CrossEntropyLoss()

    t0 = time.time()
    log_every = max(1, n_epochs // 5)

    for epoch in range(n_epochs):
        model.train()
        total_loss, n_batches = 0.0, 0
        for imgs, lbls in labeled_loader:
            imgs, lbls = imgs.to(device), lbls.to(device)
            optimizer.zero_grad()
            with autocast(enabled=device.type == "cuda"):
                loss = ce_loss(model(imgs), lbls)
            scaler.scale(loss).backward()
            scaler.step(optimizer)
            scaler.update()
            total_loss += loss.item()
            n_batches += 1
        scheduler.step()

        if (epoch + 1) % log_every == 0 or epoch == n_epochs - 1:
            dices, _ = evaluate(model, test_loader, device, num_classes)
            print(
                f"  [supervised] {run_id} ep={epoch+1}/{n_epochs} "
                f"loss={total_loss/max(n_batches,1):.4f} "
                f"dice_mean={np.mean(dices):.4f}"
            )

    dices, hds = evaluate(model, test_loader, device, num_classes)
    return {"dices": dices, "hds": hds, "train_time_min": (time.time() - t0) / 60.0}


# ------------------------------------------------------------------ #
# 2. Mean Teacher
# 官方：SSL4MIS/train_mean_teacher_2D.py，EMA=0.99, cons=0.1, rampup=40ep
# ------------------------------------------------------------------ #

def train_mean_teacher(
    labeled_loader: DataLoader,
    unlabeled_loader: DataLoader,
    test_loader: DataLoader,
    device: torch.device,
    n_epochs: int,
    num_classes: int,
    run_id: str,
) -> dict:
    student = create_model(num_classes).to(device)
    teacher = create_ema_model(student).to(device)

    optimizer = torch.optim.Adam(student.parameters(), lr=LR, weight_decay=WEIGHT_DECAY)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=n_epochs)
    scaler = GradScaler(enabled=device.type == "cuda")
    ce_loss = nn.CrossEntropyLoss()
    unlabeled_iter = InfiniteLoader(unlabeled_loader)

    t0 = time.time()
    log_every = max(1, n_epochs // 5)

    for epoch in range(n_epochs):
        student.train()
        teacher.train()  # BN 在 teacher 也 train（SSL4MIS 惯例）
        cw = MT_CONSISTENCY * sigmoid_rampup(epoch, MT_RAMPUP_EPOCHS)
        total_sup, total_cons, n_batches = 0.0, 0.0, 0

        for imgs_l, lbls_l in labeled_loader:
            imgs_l, lbls_l = imgs_l.to(device), lbls_l.to(device)
            imgs_u = unlabeled_iter.next().to(device)

            optimizer.zero_grad()
            with autocast(enabled=device.type == "cuda"):
                sup_loss = ce_loss(student(imgs_l), lbls_l)
                prob_s = F.softmax(student(imgs_u), dim=1)
                with torch.no_grad():
                    prob_t = F.softmax(teacher(imgs_u), dim=1).detach()
                cons_loss = F.mse_loss(prob_s, prob_t)
                loss = sup_loss + cw * cons_loss

            scaler.scale(loss).backward()
            scaler.step(optimizer)
            scaler.update()
            update_ema(student, teacher, MT_EMA_DECAY)
            total_sup += sup_loss.item()
            total_cons += cons_loss.item()
            n_batches += 1

        scheduler.step()

        if (epoch + 1) % log_every == 0 or epoch == n_epochs - 1:
            dices, _ = evaluate(teacher, test_loader, device, num_classes)
            print(
                f"  [mean_teacher] {run_id} ep={epoch+1}/{n_epochs} "
                f"sup={total_sup/max(n_batches,1):.4f} "
                f"cons={total_cons/max(n_batches,1):.4f} "
                f"cw={cw:.3f} dice_mean={np.mean(dices):.4f}"
            )

    dices, hds = evaluate(teacher, test_loader, device, num_classes)
    return {"dices": dices, "hds": hds, "train_time_min": (time.time() - t0) / 60.0}


# ------------------------------------------------------------------ #
# 3. CPS（Cross Pseudo Supervision）
# 官方：SSL4MIS/train_cross_pseudo_supervision_2D.py
# 双 UNet 同架构独立初始化，互换 argmax 伪标签监督
# cons=0.1，sigmoid rampup (official: iter//150 → 我们 epoch-based 换算 200ep)
# ------------------------------------------------------------------ #

def train_cps(
    labeled_loader: DataLoader,
    unlabeled_loader: DataLoader,
    test_loader: DataLoader,
    device: torch.device,
    n_epochs: int,
    num_classes: int,
    run_id: str,
) -> dict:
    # 两个独立初始化的 UNet（不共享权重，不从同一 copy 来）
    model1 = create_model(num_classes).to(device)
    model2 = create_model(num_classes).to(device)
    # 确保独立初始化（不同 seed 轮次 create_model 会用当前 global seed，已在 run_one 调用前 set_seed）
    # 给 model2 重新随机初始化保证差异
    for m in model2.modules():
        if isinstance(m, (nn.Conv2d, nn.Linear)):
            nn.init.kaiming_normal_(m.weight, mode="fan_out", nonlinearity="relu")
            if m.bias is not None:
                nn.init.zeros_(m.bias)

    optimizer1 = torch.optim.Adam(model1.parameters(), lr=LR, weight_decay=WEIGHT_DECAY)
    optimizer2 = torch.optim.Adam(model2.parameters(), lr=LR, weight_decay=WEIGHT_DECAY)
    scheduler1 = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer1, T_max=n_epochs)
    scheduler2 = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer2, T_max=n_epochs)
    scaler = GradScaler(enabled=device.type == "cuda")
    ce_loss = nn.CrossEntropyLoss()
    unlabeled_iter = InfiniteLoader(unlabeled_loader)

    t0 = time.time()
    log_every = max(1, n_epochs // 5)

    for epoch in range(n_epochs):
        model1.train()
        model2.train()
        # 官方 CPS 的 consistency_weight 输入是 iter//150，我们用 epoch 等效换算
        # 官方 max_iterations 默认 6000，get_current_consistency_weight(iter//150) ≈ sigmoid(iter/150/rampup)
        # 转换：epoch → 等效 iter = epoch * iters_per_epoch，但按 epoch 直接喂 rampup 也合理
        cw = CPS_CONSISTENCY * sigmoid_rampup(epoch, CPS_RAMPUP_EPOCHS)
        total_sup, total_cps, n_batches = 0.0, 0.0, 0

        for imgs_l, lbls_l in labeled_loader:
            imgs_l, lbls_l = imgs_l.to(device), lbls_l.to(device)
            imgs_u = unlabeled_iter.next().to(device)

            # 合并 labeled + unlabeled 喂入（CPS 在两者上都做互换伪标签）
            imgs_all = torch.cat([imgs_l, imgs_u], dim=0)

            optimizer1.zero_grad()
            optimizer2.zero_grad()

            with autocast(enabled=device.type == "cuda"):
                logits1_all = model1(imgs_all)
                logits2_all = model2(imgs_all)

                # 有监督部分（只对 labeled 部分）
                n_l = imgs_l.shape[0]
                sup_loss1 = ce_loss(logits1_all[:n_l], lbls_l)
                sup_loss2 = ce_loss(logits2_all[:n_l], lbls_l)

                # CPS 互换伪标签（在全部样本上，对方 argmax 作为伪标签）
                pseudo_label1 = logits1_all.argmax(dim=1).detach().long()  # model1 → 监督 model2
                pseudo_label2 = logits2_all.argmax(dim=1).detach().long()  # model2 → 监督 model1

                cps_loss1 = ce_loss(logits1_all, pseudo_label2)  # model1 向 model2 伪标签学
                cps_loss2 = ce_loss(logits2_all, pseudo_label1)  # model2 向 model1 伪标签学

                loss1 = sup_loss1 + cw * cps_loss1
                loss2 = sup_loss2 + cw * cps_loss2
                loss = loss1 + loss2

            scaler.scale(loss).backward()
            scaler.step(optimizer1)
            scaler.step(optimizer2)
            scaler.update()
            total_sup += (sup_loss1.item() + sup_loss2.item()) / 2
            total_cps += (cps_loss1.item() + cps_loss2.item()) / 2
            n_batches += 1

        scheduler1.step()
        scheduler2.step()

        if (epoch + 1) % log_every == 0 or epoch == n_epochs - 1:
            # 用 model1 评估（两个对称，取其一）
            dices, _ = evaluate(model1, test_loader, device, num_classes)
            print(
                f"  [cps] {run_id} ep={epoch+1}/{n_epochs} "
                f"sup={total_sup/max(n_batches,1):.4f} "
                f"cps={total_cps/max(n_batches,1):.4f} "
                f"cw={cw:.3f} dice_mean={np.mean(dices):.4f}"
            )

    dices, hds = evaluate(model1, test_loader, device, num_classes)
    return {"dices": dices, "hds": hds, "train_time_min": (time.time() - t0) / 60.0}


# ------------------------------------------------------------------ #
# 4. UAMT（Uncertainty-Aware Mean Teacher）
# 官方：SSL4MIS/train_uncertainty_aware_mean_teacher_2D.py
# EMA=0.99, cons=0.1, rampup=200(iter-based→epoch), T=8
# threshold=(0.75+0.25*rampup)*ln(2)，不确定性掩码
# ------------------------------------------------------------------ #

def _mc_dropout_uncertainty(
    model: nn.Module,
    imgs: torch.Tensor,
    T: int,
    num_classes: int,
    device: torch.device,
) -> Tuple[torch.Tensor, torch.Tensor]:
    """
    MC-Dropout 不确定性估计。
    model 处于 train 模式（Dropout 激活），对 imgs 推理 T 次。
    返回 (mean_prob [B, C, H, W], uncertainty [B, H, W])

    不确定性 = -sum(p * log(p+eps)) 的平均（按官方 UAMT 用 entropy）
    """
    model.train()  # 保持 BN + Dropout 在 train 模式
    probs_list = []
    with torch.no_grad():
        for _ in range(T):
            with autocast(enabled=device.type == "cuda"):
                logits = model(imgs)
            probs_list.append(F.softmax(logits, dim=1))
    # [T, B, C, H, W]
    probs_stack = torch.stack(probs_list, dim=0)
    mean_prob = probs_stack.mean(dim=0)          # [B, C, H, W]
    # Entropy-based 不确定性（UAMT 官方用 entropy）
    eps = 1e-6
    entropy = -(mean_prob * torch.log(mean_prob + eps)).sum(dim=1)  # [B, H, W]
    return mean_prob, entropy


class UNetWithDropout(nn.Module):
    """
    UAMT 需要 MC-Dropout，给 UNet bottleneck 后加 Dropout。
    包装 UNet，在 bottleneck 特征后插入 Dropout2d。
    """
    def __init__(self, base_unet: nn.Module, p_drop: float = 0.5):
        super().__init__()
        self.unet = base_unet
        self.dropout = nn.Dropout2d(p=p_drop)

    def forward(self, x):
        # 利用 UNet 内部结构：enc → bottleneck（加 dropout）→ dec
        e1 = self.unet.enc1(x)
        e2 = self.unet.enc2(e1)
        e3 = self.unet.enc3(e2)
        e4 = self.unet.enc4(e3)
        bn = self.unet.bottleneck(e4)
        bn = self.dropout(bn)   # MC-Dropout 在 bottleneck
        d4 = self.unet.dec4(bn, e4)
        d3 = self.unet.dec3(d4, e3)
        d2 = self.unet.dec2(d3, e2)
        d1 = self.unet.dec1(d2, e1)
        return self.unet.out_conv(d1)


def train_uamt(
    labeled_loader: DataLoader,
    unlabeled_loader: DataLoader,
    test_loader: DataLoader,
    device: torch.device,
    n_epochs: int,
    num_classes: int,
    run_id: str,
) -> dict:
    base_student = create_model(num_classes)
    student = UNetWithDropout(base_student, p_drop=0.5).to(device)
    # teacher 也带 Dropout（MC-dropout 在 teacher 上跑）
    base_teacher = create_model(num_classes)
    teacher = UNetWithDropout(copy.deepcopy(base_student), p_drop=0.5).to(device)
    for p in teacher.parameters():
        p.requires_grad_(False)

    optimizer = torch.optim.Adam(student.parameters(), lr=LR, weight_decay=WEIGHT_DECAY)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=n_epochs)
    scaler = GradScaler(enabled=device.type == "cuda")
    ce_loss = nn.CrossEntropyLoss()
    unlabeled_iter = InfiniteLoader(unlabeled_loader)

    t0 = time.time()
    log_every = max(1, n_epochs // 5)

    for epoch in range(n_epochs):
        student.train()
        rampup_val = sigmoid_rampup(epoch, UAMT_RAMPUP_EPOCHS)
        cw = UAMT_CONSISTENCY * rampup_val
        # UAMT 官方不确定性阈值：threshold=(0.75+0.25*rampup)*ln(2)
        uncertainty_thresh = (0.75 + 0.25 * rampup_val) * math.log(2)
        total_sup, total_cons, n_batches = 0.0, 0.0, 0

        for imgs_l, lbls_l in labeled_loader:
            imgs_l, lbls_l = imgs_l.to(device), lbls_l.to(device)
            imgs_u = unlabeled_iter.next().to(device)

            optimizer.zero_grad()

            with autocast(enabled=device.type == "cuda"):
                # 有监督损失
                student.train()
                sup_loss = ce_loss(student(imgs_l), lbls_l)

            # MC-Dropout 不确定性（teacher，T=8 次）
            # 注意：teacher 的 Dropout 也在 train 模式才激活
            teacher.train()
            with torch.no_grad():
                mean_prob_t, uncertainty = _mc_dropout_uncertainty(
                    teacher, imgs_u, UAMT_T, num_classes, device
                )
            # 不确定性掩码（uncertainty < threshold 的像素才纳入一致性损失）
            mask = (uncertainty < uncertainty_thresh).float()  # [B, H, W]

            # 一致性损失（student 输出 vs teacher mean_prob，masked MSE）
            student.train()
            with autocast(enabled=device.type == "cuda"):
                prob_s = F.softmax(student(imgs_u), dim=1)  # [B, C, H, W]
                # Masked MSE：只在低不确定性区域
                mask_expanded = mask.unsqueeze(1).expand_as(prob_s)  # [B, C, H, W]
                cons_loss = (F.mse_loss(prob_s, mean_prob_t.detach(), reduction="none") * mask_expanded).mean()
                loss = sup_loss + cw * cons_loss

            scaler.scale(loss).backward()
            scaler.step(optimizer)
            scaler.update()
            # EMA 更新 teacher
            update_ema(student, teacher, UAMT_EMA_DECAY)

            total_sup += sup_loss.item()
            total_cons += cons_loss.item()
            n_batches += 1

        scheduler.step()

        if (epoch + 1) % log_every == 0 or epoch == n_epochs - 1:
            # 评估用 teacher（eval 模式关掉 Dropout）
            teacher.eval()
            dices, _ = evaluate(teacher, test_loader, device, num_classes)
            print(
                f"  [uamt] {run_id} ep={epoch+1}/{n_epochs} "
                f"sup={total_sup/max(n_batches,1):.4f} "
                f"cons={total_cons/max(n_batches,1):.4f} "
                f"cw={cw:.3f} thresh={uncertainty_thresh:.3f} "
                f"dice_mean={np.mean(dices):.4f}"
            )

    teacher.eval()
    dices, hds = evaluate(teacher, test_loader, device, num_classes)
    return {"dices": dices, "hds": hds, "train_time_min": (time.time() - t0) / 60.0}


# ------------------------------------------------------------------ #
# 5. FixMatch
# 官方：SSL4MIS/train_fixmatch_standard_augs.py
# conf_thresh=0.8, cons=0.1 sigmoid rampup 200ep
# 弱增广伪标签 → 只有高置信度像素才监督强增广预测
# ------------------------------------------------------------------ #

def train_fixmatch(
    labeled_loader: DataLoader,
    unlabeled_loader: DataLoader,   # 此 loader 的 dataset 应是 WeakStrongUnlabeledDataset
    test_loader: DataLoader,
    device: torch.device,
    n_epochs: int,
    num_classes: int,
    run_id: str,
) -> dict:
    model = create_model(num_classes).to(device)
    optimizer = torch.optim.Adam(model.parameters(), lr=LR, weight_decay=WEIGHT_DECAY)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=n_epochs)
    scaler = GradScaler(enabled=device.type == "cuda")
    ce_loss = nn.CrossEntropyLoss()
    unlabeled_iter = InfiniteLoader(unlabeled_loader)

    t0 = time.time()
    log_every = max(1, n_epochs // 5)

    for epoch in range(n_epochs):
        model.train()
        cw = FIXMATCH_CONSISTENCY * sigmoid_rampup(epoch, FIXMATCH_RAMPUP_EPOCHS)
        total_sup, total_fix, n_batches = 0.0, 0.0, 0

        for imgs_l, lbls_l in labeled_loader:
            imgs_l, lbls_l = imgs_l.to(device), lbls_l.to(device)

            # unlabeled_loader 返回 (weak_aug, strong_aug) 对（WeakStrongUnlabeledDataset）
            batch_u = unlabeled_iter.next()
            if isinstance(batch_u, (list, tuple)) and len(batch_u) == 2:
                imgs_weak, imgs_strong = batch_u[0].to(device), batch_u[1].to(device)
            else:
                # fallback：如果不是双视图 loader，只有单图（用两次）
                imgs_weak = batch_u.to(device)
                imgs_strong = imgs_weak

            optimizer.zero_grad()

            with autocast(enabled=device.type == "cuda"):
                # 有监督损失
                sup_loss = ce_loss(model(imgs_l), lbls_l)

                # 弱增广生成伪标签
                with torch.no_grad():
                    logits_weak = model(imgs_weak)
                    prob_weak = F.softmax(logits_weak, dim=1)
                    conf, pseudo_label = prob_weak.max(dim=1)   # [B, H, W]
                    # 置信掩码：max prob > conf_thresh 的像素
                    conf_mask = (conf >= FIXMATCH_CONF_THRESH).float()  # [B, H, W]

                # 强增广预测
                logits_strong = model(imgs_strong)
                # Masked CE：只在高置信度像素算损失
                # 用 conf_mask 做逐像素加权 CE
                # CE reduction="none" → [B, H, W]，再乘 mask 取均值
                ce_strong = F.cross_entropy(
                    logits_strong, pseudo_label, reduction="none"
                )  # [B, H, W]
                n_valid = conf_mask.sum().clamp(min=1.0)
                fix_loss = (ce_strong * conf_mask).sum() / n_valid

                loss = sup_loss + cw * fix_loss

            scaler.scale(loss).backward()
            scaler.step(optimizer)
            scaler.update()
            total_sup += sup_loss.item()
            total_fix += fix_loss.item()
            n_batches += 1

        scheduler.step()

        if (epoch + 1) % log_every == 0 or epoch == n_epochs - 1:
            dices, _ = evaluate(model, test_loader, device, num_classes)
            print(
                f"  [fixmatch] {run_id} ep={epoch+1}/{n_epochs} "
                f"sup={total_sup/max(n_batches,1):.4f} "
                f"fix={total_fix/max(n_batches,1):.4f} "
                f"cw={cw:.3f} dice_mean={np.mean(dices):.4f}"
            )

    dices, hds = evaluate(model, test_loader, device, num_classes)
    return {"dices": dices, "hds": hds, "train_time_min": (time.time() - t0) / 60.0}


# ------------------------------------------------------------------ #
# 状态持久化（续跑支持）
# ------------------------------------------------------------------ #

def load_state() -> dict:
    if STATE_JSON.exists():
        with open(STATE_JSON, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"phase": "init", "current_run": None, "runs_done": [], "last_dice": None}


def save_state(state: dict):
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    with open(STATE_JSON, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)


def run_already_done(state: dict, run_id: str) -> bool:
    return run_id in state.get("runs_done", [])


# ------------------------------------------------------------------ #
# CSV 管理
# ------------------------------------------------------------------ #

def _csv_fieldnames(num_classes: int, class_names: List[str]) -> List[str]:
    fg_names = class_names[1:]   # 排除背景
    dice_cols = [f"dice_{n}" for n in fg_names]
    hd_cols = [f"hd95_{n}" for n in fg_names]
    return (
        ["method", "dataset", "label_ratio", "seed"]
        + dice_cols + ["dice_mean"]
        + hd_cols + ["hd95_mean"]
        + ["n_labeled", "n_unlabeled", "n_test", "epochs", "train_time_min"]
    )


def init_csv(fieldnames: List[str]):
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    if not RESULTS_CSV.exists():
        with open(RESULTS_CSV, "w", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow(fieldnames)


def append_csv(row: dict, fieldnames: List[str]):
    with open(RESULTS_CSV, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writerow(row)


# ------------------------------------------------------------------ #
# 数据集路径解析
# ------------------------------------------------------------------ #

# 默认数据根路径（相对 harness.py）；可用环境变量 FETALSS_DATA_ROOT 覆盖（HPC 用）
_DEFAULT_DATA_ROOT = Path(os.environ["FETALSS_DATA_ROOT"]) if os.environ.get("FETALSS_DATA_ROOT") \
    else _SRC_DIR.parent.parent / "_run011_pilot" / "data"

DATASET_DATA_DIRS = {
    "psfhs": _DEFAULT_DATA_ROOT / "PSFHS",
    "hc18": _DEFAULT_DATA_ROOT / "HC18",
}


# ------------------------------------------------------------------ #
# 单次 run
# ------------------------------------------------------------------ #

def run_one(
    method: str,
    dataset: str,
    label_ratio: float,
    seed: int,
    n_epochs: int,
    device: torch.device,
    state: dict,
    data_dir: Optional[str] = None,
    batch_size: int = BATCH_SIZE,
) -> Optional[dict]:
    run_id = f"{method}_{dataset}_r{int(label_ratio*100):03d}_s{seed}"

    if run_already_done(state, run_id):
        print(f"[skip] {run_id} 已完成，跳过")
        return None

    print(f"\n{'='*70}")
    print(f"[run] {run_id}  epochs={n_epochs}")

    set_seed(seed)

    num_classes = DATASET_INFO[dataset]["num_classes"]
    class_names = DATASET_INFO[dataset]["class_names"]
    fieldnames = _csv_fieldnames(num_classes, class_names)
    init_csv(fieldnames)

    # 数据路径
    if data_dir is None:
        d_dir = str(DATASET_DATA_DIRS.get(dataset, _DEFAULT_DATA_ROOT / dataset))
    else:
        d_dir = data_dir

    # FixMatch 需要 WeakStrongUnlabeledDataset
    fixmatch_mode = (method == "fixmatch")

    labeled_loader, unlabeled_loader, test_loader = get_dataloaders(
        dataset=dataset,
        data_dir=d_dir,
        label_ratio=label_ratio,
        batch_size=batch_size,
        seed=seed,
        num_workers=0,
        fixmatch_mode=fixmatch_mode,
    )

    n_labeled = len(labeled_loader.dataset)
    n_unlabeled = len(unlabeled_loader.dataset)
    n_test = len(test_loader.dataset)

    state["current_run"] = run_id
    state["phase"] = "training"
    save_state(state)

    # 调用对应训练函数
    if method == "supervised":
        result = train_supervised(
            labeled_loader, test_loader, device, n_epochs, num_classes, run_id
        )
    elif method == "mean_teacher":
        result = train_mean_teacher(
            labeled_loader, unlabeled_loader, test_loader, device, n_epochs, num_classes, run_id
        )
    elif method == "cps":
        result = train_cps(
            labeled_loader, unlabeled_loader, test_loader, device, n_epochs, num_classes, run_id
        )
    elif method == "uamt":
        result = train_uamt(
            labeled_loader, unlabeled_loader, test_loader, device, n_epochs, num_classes, run_id
        )
    elif method == "fixmatch":
        result = train_fixmatch(
            labeled_loader, unlabeled_loader, test_loader, device, n_epochs, num_classes, run_id
        )
    else:
        raise ValueError(f"未知方法: {method}")

    dices = result["dices"]     # list, len = num_classes - 1
    hds = result["hds"]         # list, len = num_classes - 1
    fg_names = class_names[1:]  # 前景类名

    row = {
        "method": method,
        "dataset": dataset,
        "label_ratio": f"{label_ratio:.2f}",
        "seed": seed,
        "dice_mean": f"{np.mean(dices):.4f}",
        "hd95_mean": f"{np.mean(hds):.2f}",
        "n_labeled": n_labeled,
        "n_unlabeled": n_unlabeled,
        "n_test": n_test,
        "epochs": n_epochs,
        "train_time_min": f"{result['train_time_min']:.2f}",
    }
    for i, name in enumerate(fg_names):
        row[f"dice_{name}"] = f"{dices[i]:.4f}"
        row[f"hd95_{name}"] = f"{hds[i]:.2f}"

    append_csv(row, fieldnames)

    state["runs_done"].append(run_id)
    state["current_run"] = None
    state["last_dice"] = float(np.mean(dices))
    save_state(state)

    print(
        f"[done] {run_id}  "
        + "  ".join(f"dice_{n}={dices[i]:.4f}" for i, n in enumerate(fg_names))
        + f"  dice_mean={np.mean(dices):.4f}"
        + f"  hd95_mean={np.mean(hds):.1f}"
        + f"  time={result['train_time_min']:.1f}min"
    )
    return row


# ------------------------------------------------------------------ #
# 主入口
# ------------------------------------------------------------------ #

METHODS = ["supervised", "mean_teacher", "cps", "uamt", "fixmatch"]
DATASETS = ["psfhs", "hc18"]
LABEL_RATIOS = [0.01, 0.02, 0.05, 0.10, 0.20]
SEEDS = [0, 1, 2]


def main():
    parser = argparse.ArgumentParser(description="FetalSSBench 统一训练 harness")
    parser.add_argument(
        "--method", choices=METHODS, required=True,
        help=f"SSL 方法 {{{','.join(METHODS)}}}"
    )
    parser.add_argument(
        "--dataset", choices=DATASETS, default="psfhs",
        help="数据集 psfhs 或 hc18"
    )
    parser.add_argument(
        "--ratio", type=float, default=0.10,
        help="标注比例 e.g. 0.05=5%%"
    )
    parser.add_argument(
        "--seed", type=int, default=0,
        help="实验 seed"
    )
    parser.add_argument(
        "--epochs", type=int, default=None,
        help=f"覆盖 epoch 数（默认 {N_EPOCHS}）"
    )
    parser.add_argument(
        "--data_dir", type=str, default=None,
        help="数据根目录（默认自动探测 _run011_pilot/data/<dataset>）"
    )
    parser.add_argument(
        "--batch_size", type=int, default=BATCH_SIZE,
        help=f"batch size（默认 {BATCH_SIZE}）"
    )
    parser.add_argument(
        "--quick", action="store_true",
        help="烟测模式：5 epoch（验算子通路）"
    )
    args = parser.parse_args()

    n_epochs = args.epochs or (5 if args.quick else N_EPOCHS)

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"[harness] method={args.method} dataset={args.dataset} "
          f"ratio={args.ratio} seed={args.seed} epochs={n_epochs}")
    print(f"[harness] device={device}")
    if device.type == "cuda":
        print(f"  GPU: {torch.cuda.get_device_name(0)}")
        print(f"  VRAM: {torch.cuda.get_device_properties(0).total_memory/1024**3:.1f} GB")

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    state = load_state()
    state["phase"] = "starting"
    save_state(state)

    run_one(
        method=args.method,
        dataset=args.dataset,
        label_ratio=args.ratio,
        seed=args.seed,
        n_epochs=n_epochs,
        device=device,
        state=state,
        data_dir=args.data_dir,
        batch_size=args.batch_size,
    )

    state["phase"] = "done"
    save_state(state)


# Windows spawn 安全
if __name__ == "__main__":
    main()
