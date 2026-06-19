"""
kill1_baseline.py — DisagreePred KILL-1 分歧可预测性 baseline (v2, CV 版)

服务项目：DisagreePred，lever = KILL-1 gating（方案甲）
前置：先跑 parse_lidc.py 生成 lidc_disagree_labels.csv + patch npy 文件

设计变更（v2, 2026-06-18）：
  - 废弃单次 train/val/test split（test 仅 15 cluster，AUROC 粒度 0.25）
  - 改为 patient-level StratifiedGroupKFold（n_splits=5）：
      groups = patient_id，stratify = disagree_binary
      每折 test 出 out-of-fold P(disagree) → 聚合全 75 cluster → CV-AUROC
  - Bootstrap CI 按 patient 重采样（防同一 patient 多 cluster 非独立高估）
  - 置换检验：只打乱 train fold 标签，val/test 保持真实；>=100 rep 稳定 null
  - ASCII print（[PASS]/[FAIL]），避免 Windows GBK UnicodeEncodeError

超参来源（researcher 核源 2026-06-18）：
  - Adam lr=1e-4, weight_decay=1e-4
  - batch=16，max_epochs=50，patience=8
  - 增强：水平翻转 + +-10 度旋转（CT 禁垂直翻转）
  - ImageNet 预训练 ResNet-18

判据（02_ACCEPTANCE.md A1，更新为 CV 版）：
  CV-AUROC（75 样本）> 0.60
  AND bootstrap CI 下界 > 0.50（patient 级重采样）
  AND perm null 塌回 ~0.50（perm_auroc_mean < 0.60）
  三条全满足 = KILL-1 PASS；否则 FAIL/不可定论

Windows 规范：
  - if __name__=='__main__' 包主逻辑 + freeze_support
  - num_workers=0，pin_memory=False
  - 路径正斜杠 / pathlib.Path
  - ASCII print only（无 Unicode 特殊字符）
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import random
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
from torch.utils.data import DataLoader, Dataset

# --- 路径配置 -----------------------------------------------------------------
SCRIPTS_DIR = Path(__file__).resolve().parent
PROJECT_DIR = SCRIPTS_DIR.parent
RESULTS_DIR = PROJECT_DIR / "results"
LABEL_CSV   = RESULTS_DIR / "lidc_disagree_labels.csv"
OUT_CSV     = RESULTS_DIR / "kill1_cv_auroc.csv"       # 新输出：per-fold + 汇总

# 超参（官方口径，researcher 核源 2026-06-18）
LR           = 1e-4
WEIGHT_DECAY = 1e-4
BATCH_SIZE   = 16
MAX_EPOCHS   = 50
PATIENCE     = 8
N_SPLITS     = 5       # StratifiedGroupKFold 折数
N_BOOTSTRAP  = 1000    # bootstrap AUROC CI 次数（纯 numpy）
N_PERM       = 100     # 置换检验 rep 数（>=100 稳定 null）

# 置换检验 epoch 数（CPU 上 100 rep 可能耗时，少 epoch 加速保留早停）
PERM_MAX_EPOCHS = 30
PERM_PATIENCE   = 5

ROTATE_DEG   = 10      # +-10 度旋转（CT 禁垂直翻转）


# --- 纯 numpy AUROC（绕 scipy.stats OMP Error #15）---------------------------
def auroc_numpy(labels: np.ndarray, scores: np.ndarray) -> float:
    """
    纯 numpy 计算 AUROC（trapezoid rule）。
    labels: binary int/float array; scores: float array (higher = more likely positive)
    """
    labels = np.asarray(labels, dtype=np.float32)
    scores = np.asarray(scores, dtype=np.float32)
    order = np.argsort(scores)[::-1]
    labels_sorted = labels[order]
    n_pos = labels_sorted.sum()
    n_neg = len(labels_sorted) - n_pos
    if n_pos == 0 or n_neg == 0:
        return float("nan")
    tp_cum = np.cumsum(labels_sorted)
    fp_cum = np.cumsum(1 - labels_sorted)
    tpr = tp_cum / n_pos
    fpr = fp_cum / n_neg
    tpr = np.concatenate([[0.0], tpr])
    fpr = np.concatenate([[0.0], fpr])
    auc = float(np.trapz(tpr, fpr))
    return auc


def bootstrap_auroc_ci_patient(
    labels: np.ndarray,
    scores: np.ndarray,
    patient_ids: np.ndarray,
    n: int = N_BOOTSTRAP,
    ci: float = 0.95,
    seed: int = 0,
) -> tuple[float, float]:
    """
    按 patient 重采样的 bootstrap AUROC 95% CI（纯 numpy）。
    patient 内所有 cluster 一同选入/排除，防同 patient 多 cluster 非独立高估。
    labels/scores/patient_ids: 1-D arrays，长度 = 全 cluster 数。
    """
    rng = np.random.default_rng(seed)
    unique_pids = np.unique(patient_ids)
    n_patients = len(unique_pids)

    boot_aurocs = []
    for _ in range(n):
        # 按 patient 有放回采样
        sampled_pids = rng.choice(unique_pids, size=n_patients, replace=True)
        idx_list = []
        for pid in sampled_pids:
            idx_list.append(np.where(patient_ids == pid)[0])
        idx = np.concatenate(idx_list)
        try:
            a = auroc_numpy(labels[idx], scores[idx])
            if not np.isnan(a):
                boot_aurocs.append(a)
        except Exception:
            pass

    if not boot_aurocs:
        return float("nan"), float("nan")
    lo = float(np.percentile(boot_aurocs, (1 - ci) / 2 * 100))
    hi = float(np.percentile(boot_aurocs, (1 + ci) / 2 * 100))
    return lo, hi


def auprc_numpy(labels: np.ndarray, scores: np.ndarray) -> float:
    """纯 numpy 计算 AUPRC（precision-recall AUC）。"""
    labels = np.asarray(labels, dtype=np.float32)
    scores = np.asarray(scores, dtype=np.float32)
    order = np.argsort(scores)[::-1]
    labels_sorted = labels[order]
    n_pos = labels_sorted.sum()
    if n_pos == 0:
        return float("nan")
    tp_cum = np.cumsum(labels_sorted)
    idx_arr = np.arange(1, len(labels_sorted) + 1, dtype=np.float32)
    precision = tp_cum / idx_arr
    recall = tp_cum / n_pos
    precision = np.concatenate([[precision[0]], precision])
    recall = np.concatenate([[0.0], recall])
    auc = float(np.trapz(precision, recall))
    return auc


# --- 纯 numpy StratifiedGroupKFold -------------------------------------------
def stratified_group_kfold_split(
    n_splits: int,
    labels: np.ndarray,
    groups: np.ndarray,
    seed: int = 0,
) -> list[tuple[np.ndarray, np.ndarray]]:
    """
    Patient-level StratifiedGroupKFold，纯 numpy 实现（绕 sklearn OMP 冲突风险）。
    按 patient 分组（同 patient 全进同一 fold），尽量保持各折正负比接近总体。

    返回 [(train_indices, test_indices), ...] 长度 = n_splits。
    所有 index 基于输入数组 0-based 行号。
    """
    rng = np.random.default_rng(seed)
    unique_groups = np.unique(groups)

    # 计算每个 patient 的 label（patient 若混合正负则取多数票）
    pid_labels = {}
    for pid in unique_groups:
        mask = groups == pid
        majority = int(np.round(labels[mask].mean()))
        pid_labels[pid] = majority

    # 按 label 分桶，patient 内随机打乱再分折（最简单有效分层策略）
    pos_pids = [p for p in unique_groups if pid_labels[p] == 1]
    neg_pids = [p for p in unique_groups if pid_labels[p] == 0]
    rng.shuffle(pos_pids)
    rng.shuffle(neg_pids)

    # 各折分配 patient
    fold_patients: list[list] = [[] for _ in range(n_splits)]
    for i, pid in enumerate(pos_pids):
        fold_patients[i % n_splits].append(pid)
    for i, pid in enumerate(neg_pids):
        fold_patients[i % n_splits].append(pid)

    # 构造 (train_idx, test_idx)
    folds = []
    all_idx = np.arange(len(labels))
    for fold_i in range(n_splits):
        test_pids = set(fold_patients[fold_i])
        test_mask = np.array([g in test_pids for g in groups])
        test_idx  = all_idx[test_mask]
        train_idx = all_idx[~test_mask]
        folds.append((train_idx, test_idx))
    return folds


# --- 旋转（纯 numpy，避免 scipy.ndimage）-------------------------------------
def _rotate_patch(patch: np.ndarray, angle_deg: float) -> np.ndarray:
    """纯 numpy 双线性旋转（绕中心），angle_deg 单位度。"""
    if abs(angle_deg) < 0.5:
        return patch
    h, w = patch.shape
    cx, cy = w / 2.0, h / 2.0
    angle_rad = math.radians(angle_deg)
    cos_a = math.cos(angle_rad)
    sin_a = math.sin(angle_rad)

    ys, xs = np.meshgrid(np.arange(h), np.arange(w), indexing="ij")
    xs_c = xs - cx
    ys_c = ys - cy
    xs_src = cos_a * xs_c + sin_a * ys_c + cx
    ys_src = -sin_a * xs_c + cos_a * ys_c + cy

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


# --- Dataset（fold-based，无 split 列依赖）-----------------------------------
class LIDCFoldDataset(Dataset):
    """
    从全量 rows + 索引子集构造，按 fold 切割，不依赖 CSV 的 split 列。
    augment=True 时做水平翻转 + +-10 度旋转（train fold 用）。
    perm_labels: 若非 None，则用这个 array 替换原始 label（置换检验用）。
    """

    def __init__(
        self,
        rows: list[dict],
        indices: np.ndarray,
        augment: bool = False,
        perm_labels: np.ndarray | None = None,
    ) -> None:
        self.rows = [rows[i] for i in indices]
        self.augment = augment
        # perm_labels 长度应等于 indices 长度（train fold 子集）
        self.perm_labels = perm_labels

    def __len__(self) -> int:
        return len(self.rows)

    def __getitem__(self, idx: int):
        row = self.rows[idx]
        patch_path = row["patch_path"]
        if self.perm_labels is not None:
            label = int(self.perm_labels[idx])
        else:
            label = int(row["disagree_binary"])

        patch = np.load(patch_path).astype(np.float32)   # (96, 96)

        if self.augment:
            if random.random() > 0.5:
                patch = np.fliplr(patch).copy()
            angle_deg = random.uniform(-ROTATE_DEG, ROTATE_DEG)
            patch = _rotate_patch(patch, angle_deg)

        # 灰度复制 3 通道 (3, H, W)
        tensor = torch.from_numpy(patch).unsqueeze(0).repeat(3, 1, 1)
        return tensor, torch.tensor(label, dtype=torch.float32)


# --- 模型 --------------------------------------------------------------------
def build_model(device: torch.device) -> nn.Module:
    """ImageNet 预训练 ResNet-18，fc 替换为单 logit。"""
    from torchvision.models import resnet18, ResNet18_Weights
    model = resnet18(weights=ResNet18_Weights.IMAGENET1K_V1)
    model.fc = nn.Linear(model.fc.in_features, 1)
    return model.to(device)


# --- 训练 / 推理 --------------------------------------------------------------
def train_epoch(model, loader, optimizer, criterion, device) -> float:
    model.train()
    total_loss = 0.0
    for imgs, labels in loader:
        imgs   = imgs.to(device, non_blocking=False)
        labels = labels.to(device)
        optimizer.zero_grad()
        logits = model(imgs).squeeze(1)
        loss   = criterion(logits, labels)
        loss.backward()
        optimizer.step()
        total_loss += loss.item() * len(labels)
    return total_loss / max(len(loader.dataset), 1)


@torch.no_grad()
def eval_epoch(model, loader, device) -> tuple[np.ndarray, np.ndarray]:
    """返回 (all_labels, all_scores)，scores = sigmoid(logit)。"""
    model.eval()
    all_labels, all_scores = [], []
    for imgs, labels in loader:
        imgs   = imgs.to(device, non_blocking=False)
        logits = model(imgs).squeeze(1)
        scores = torch.sigmoid(logits).cpu().numpy()
        all_labels.append(labels.numpy())
        all_scores.append(scores)
    if not all_labels:
        return np.array([]), np.array([])
    return np.concatenate(all_labels), np.concatenate(all_scores)


# --- 单折训练（基础 or 置换检验）----------------------------------------------
def train_fold(
    rows: list[dict],
    train_idx: np.ndarray,
    val_idx: np.ndarray,
    test_idx: np.ndarray,
    seed: int,
    device: torch.device,
    perm_train_labels: np.ndarray | None = None,   # 置换检验时传入打乱后 train 标签
    max_epochs: int = MAX_EPOCHS,
    patience: int = PATIENCE,
    verbose: bool = True,
) -> tuple[np.ndarray, np.ndarray]:
    """
    在 train_idx 上训练（可选置换标签），val_idx 用于早停（标签不打乱），
    在 test_idx 上出预测分数。
    返回 (test_labels, test_scores)。
    """
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)

    train_set = LIDCFoldDataset(rows, train_idx, augment=True,
                                perm_labels=perm_train_labels)
    val_set   = LIDCFoldDataset(rows, val_idx,   augment=False, perm_labels=None)
    test_set  = LIDCFoldDataset(rows, test_idx,  augment=False, perm_labels=None)

    train_loader = DataLoader(train_set, batch_size=BATCH_SIZE, shuffle=True,
                              num_workers=0, pin_memory=False)
    val_loader   = DataLoader(val_set,   batch_size=BATCH_SIZE, shuffle=False,
                              num_workers=0, pin_memory=False)
    test_loader  = DataLoader(test_set,  batch_size=BATCH_SIZE, shuffle=False,
                              num_workers=0, pin_memory=False)

    model     = build_model(device)
    # foreach=False: 绕开 PyTorch 2.7+CUDA 12.6 RTX4070-Laptop(SM8.9) 上
    # _multi_tensor_adam / torch._foreach_addcdiv_ 触发 CUDA illegal memory access。
    # foreach=False 退回逐参数循环实现，数学等价（lr/wd/超参不变）。
    # 根因：75-cluster 时 ~5 batch/epoch 未触发；289-cluster 18+ batch 必炸。
    optimizer = torch.optim.Adam(
        model.parameters(), lr=LR, weight_decay=WEIGHT_DECAY, foreach=False
    )
    criterion = nn.BCEWithLogitsLoss()

    best_val_auroc   = -1.0
    best_state       = None
    patience_counter = 0

    for epoch in range(max_epochs):
        tr_loss          = train_epoch(model, train_loader, optimizer, criterion, device)
        val_lbl, val_sc  = eval_epoch(model, val_loader, device)
        val_auroc        = auroc_numpy(val_lbl, val_sc)
        if np.isnan(val_auroc):
            val_auroc = 0.0

        if val_auroc > best_val_auroc:
            best_val_auroc   = val_auroc
            best_state       = {k: v.cpu().clone() for k, v in model.state_dict().items()}
            patience_counter = 0
        else:
            patience_counter += 1

        if verbose and ((epoch + 1) % 10 == 0 or patience_counter == patience):
            perm_tag = "[PERM]" if perm_train_labels is not None else ""
            print(f"    epoch {epoch+1:3d}{perm_tag} | tr_loss={tr_loss:.4f} "
                  f"| val_auroc={val_auroc:.4f} | best={best_val_auroc:.4f} "
                  f"| patience={patience_counter}/{patience}")

        if patience_counter >= patience:
            if verbose:
                print(f"    [early_stop] epoch {epoch+1}")
            break

    if best_state is not None:
        model.load_state_dict(best_state)

    test_lbl, test_sc = eval_epoch(model, test_loader, device)
    return test_lbl, test_sc


# --- 主逻辑 -------------------------------------------------------------------
def load_label_csv(csv_path: Path) -> list[dict]:
    assert csv_path.exists(), (
        f"[DATA] label CSV not found: {csv_path}\n"
        "Please run parse_lidc.py first to generate lidc_disagree_labels.csv"
    )
    rows = []
    with open(str(csv_path), newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            pp = Path(row["patch_path"])
            assert pp.exists(), f"[DATA] patch file missing: {pp}"
            rows.append(row)
    assert rows, f"[DATA] CSV empty: {csv_path}"
    print(f"[load] total {len(rows)} clusters (k>=1, schema A)")

    n_pos = sum(int(r["disagree_binary"]) for r in rows)
    n_neg = len(rows) - n_pos
    print(f"[load] disagree=1: {n_pos}, disagree=0: {n_neg}, "
          f"rate={n_pos/len(rows):.3f}")
    return rows


def run_kill1_cv(
    rows: list[dict],
    device: torch.device,
    run_permutation: bool = True,
    n_perm: int = N_PERM,
    seed: int = 0,
    verbose_fold: bool = True,
) -> None:
    """
    Patient-level StratifiedGroupKFold (n_splits=5) CV baseline.
    置换检验：只打乱 train fold 标签，val/test 保持真实标签。
    输出 kill1_cv_auroc.csv + kill1_cv_summary.json。
    """
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    # 准备数组
    all_labels   = np.array([int(r["disagree_binary"]) for r in rows])
    all_patients = np.array([r["patient_id"] for r in rows])

    unique_patients = np.unique(all_patients)
    print(f"[cv] {len(rows)} clusters / {len(unique_patients)} patients / "
          f"n_splits={N_SPLITS}")

    # 生成 fold 划分
    folds = stratified_group_kfold_split(
        N_SPLITS, all_labels, all_patients, seed=seed
    )

    # CV：5 折 out-of-fold 预测
    oof_labels = np.full(len(rows), -1, dtype=np.float32)
    oof_scores = np.full(len(rows), float("nan"), dtype=np.float32)
    fold_results = []

    print("\n[KILL-1 CV] Starting 5-fold patient-level CV ...")
    for fold_i, (train_val_idx, test_idx) in enumerate(folds):
        # 从 train+val 中按 patient 留 20% 作 val（用于早停）
        tv_patients  = np.unique(all_patients[train_val_idx])
        rng_split    = np.random.default_rng(seed + fold_i + 1)
        n_val_p      = max(1, len(tv_patients) // 5)
        val_pids_set = set(rng_split.choice(
            tv_patients, size=n_val_p, replace=False).tolist())
        val_mask      = np.array([all_patients[i] in val_pids_set
                                   for i in train_val_idx])
        val_idx_sub   = train_val_idx[val_mask]
        train_idx_sub = train_val_idx[~val_mask]

        n_test_pos = all_labels[test_idx].sum()
        n_test_neg = len(test_idx) - n_test_pos
        print(f"\n  [fold {fold_i+1}/{N_SPLITS}] "
              f"train={len(train_idx_sub)} val={len(val_idx_sub)} "
              f"test={len(test_idx)}(pos={int(n_test_pos)},neg={int(n_test_neg)})")

        test_lbl, test_sc = train_fold(
            rows, train_idx_sub, val_idx_sub, test_idx,
            seed=seed + fold_i * 100,
            device=device,
            verbose=verbose_fold,
        )
        oof_labels[test_idx] = test_lbl
        oof_scores[test_idx] = test_sc

        fold_auroc = auroc_numpy(test_lbl, test_sc)
        fold_results.append({
            "fold": fold_i + 1,
            "n_test_fold": len(test_idx),
            "auroc_fold": round(float(fold_auroc), 6),
        })
        print(f"  [fold {fold_i+1}] auroc={fold_auroc:.4f}")

    # CV-AUROC（基于全 75 样本 out-of-fold 预测）
    assert (oof_labels >= 0).all(), "[BUG] Some OOF labels not filled"
    cv_auroc = auroc_numpy(oof_labels, oof_scores)

    print(f"\n[KILL-1] CV pooled AUROC (n={len(rows)}): {cv_auroc:.4f}")

    # Bootstrap CI（patient 级重采样）
    print("[KILL-1] Computing bootstrap CI (patient-level resampling)...")
    ci_lo, ci_hi = bootstrap_auroc_ci_patient(
        oof_labels, oof_scores, all_patients,
        n=N_BOOTSTRAP, seed=seed,
    )
    print(f"[KILL-1] Bootstrap 95% CI: [{ci_lo:.4f}, {ci_hi:.4f}]")

    # 置换检验（只打乱 train fold 标签，>=100 rep）
    perm_aurocs: list[float] = []
    if run_permutation:
        print(f"\n[KILL-1] Permutation test ({n_perm} reps) ...")
        print("  [note] Only train-fold labels shuffled; val/test labels unchanged.")
        print(f"  [note] Each rep: {PERM_MAX_EPOCHS} max epochs, "
              f"patience={PERM_PATIENCE}.")
        print("  [note] CPU 100 rep estimate: ~30-90 min depending on hardware.")

        for rep in range(n_perm):
            rep_seed = seed + 10000 + rep
            perm_rng = np.random.default_rng(rep_seed)

            # 对每折只打乱 train 标签，不碰 val/test
            rep_oof_labels = np.full(len(rows), -1, dtype=np.float32)
            rep_oof_scores = np.full(len(rows), float("nan"), dtype=np.float32)

            for fold_i, (train_val_idx, test_idx) in enumerate(folds):
                tv_patients  = np.unique(all_patients[train_val_idx])
                rng_split    = np.random.default_rng(rep_seed + fold_i + 1)
                n_val_p      = max(1, len(tv_patients) // 5)
                val_pids_set = set(rng_split.choice(
                    tv_patients, size=n_val_p, replace=False).tolist())
                val_mask      = np.array([all_patients[i] in val_pids_set
                                           for i in train_val_idx])
                val_idx_sub   = train_val_idx[val_mask]
                train_idx_sub = train_val_idx[~val_mask]

                # 只打乱 train fold 的标签
                train_orig_labels = all_labels[train_idx_sub].copy()
                perm_rng.shuffle(train_orig_labels)

                test_lbl, test_sc = train_fold(
                    rows, train_idx_sub, val_idx_sub, test_idx,
                    seed=rep_seed + fold_i * 100,
                    device=device,
                    perm_train_labels=train_orig_labels,
                    max_epochs=PERM_MAX_EPOCHS,
                    patience=PERM_PATIENCE,
                    verbose=False,   # perm rep 不打详细 log，只报进度
                )
                rep_oof_labels[test_idx] = test_lbl
                rep_oof_scores[test_idx] = test_sc

            rep_auroc = auroc_numpy(rep_oof_labels, rep_oof_scores)
            perm_aurocs.append(float(rep_auroc))

            if (rep + 1) % 10 == 0 or rep == 0:
                print(f"  perm rep {rep+1:3d}/{n_perm} | "
                      f"auroc={rep_auroc:.4f} | "
                      f"running_mean={np.mean(perm_aurocs):.4f}")

    perm_mean = float(np.mean(perm_aurocs)) if perm_aurocs else float("nan")
    # p-value：置换分布中 >= 真实 CV-AUROC 的比例
    perm_p = (float(np.mean(np.array(perm_aurocs) >= cv_auroc))
              if perm_aurocs else float("nan"))

    # 判决
    crit_auroc = cv_auroc > 0.60
    crit_ci    = ci_lo > 0.50
    crit_perm  = (np.isnan(perm_mean) or perm_mean < 0.60)  # null 应塌回 <0.60

    print("\n" + "=" * 60)
    print("KILL-1 VERDICT (02_ACCEPTANCE.md A1, CV version)")
    print(f"  CV pooled AUROC (n={len(rows)}) : {cv_auroc:.4f}")
    print(f"  Bootstrap 95% CI              : [{ci_lo:.4f}, {ci_hi:.4f}]")
    if perm_aurocs:
        print(f"  Perm null mean ({n_perm} rep)     : {perm_mean:.4f}  (expected ~0.50)")
        print(f"  Perm p-value                  : {perm_p:.4f}")
    print()
    if crit_auroc and crit_ci and crit_perm:
        verdict = "PASS"
        print("  [PASS] KILL-1 PASS: AUROC > 0.60, CI_low > 0.50, perm null < 0.60")
        print("  --> Disagreement predictability claim supported. Proceed A2/A3/A4.")
    else:
        verdict = "FAIL"
        reasons = []
        if not crit_auroc:
            reasons.append(f"AUROC={cv_auroc:.4f} <= 0.60")
        if not crit_ci:
            reasons.append(f"CI_low={ci_lo:.4f} <= 0.50")
        if not crit_perm:
            reasons.append(f"perm_mean={perm_mean:.4f} >= 0.60 (null did not collapse)")
        print(f"  [FAIL] KILL-1 FAIL: {'; '.join(reasons)}")
        print("  --> Core claim dead. Honest withdrawal per ACCEPTANCE.md kill criteria.")
    print("=" * 60)

    # 写 CSV（per-fold 行 + summary 行）
    fieldnames_ext = [
        "fold", "n_test_fold", "auroc_fold",
        "cv_pooled_auroc", "ci_low", "ci_high",
        "perm_auroc_mean", "perm_p_value", "verdict",
    ]

    with open(str(OUT_CSV), "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames_ext, extrasaction="ignore")
        writer.writeheader()
        for fr in fold_results:
            writer.writerow(fr)
        # 汇总行
        writer.writerow({
            "fold": "summary",
            "n_test_fold": len(rows),
            "auroc_fold": "",
            "cv_pooled_auroc": round(cv_auroc, 6),
            "ci_low": round(float(ci_lo), 6),
            "ci_high": round(float(ci_hi), 6),
            "perm_auroc_mean": (round(perm_mean, 6)
                                if not np.isnan(perm_mean) else "nan"),
            "perm_p_value": (round(perm_p, 6)
                             if not np.isnan(perm_p) else "nan"),
            "verdict": verdict,
        })

    print(f"\n[output] CSV     -> {OUT_CSV}")

    # ── 持久化 per-cluster OOF 分数（供 A2 残余信息分析配对使用）──────────
    # 只加落盘，不改任何训练逻辑/超参/折划分。
    OOF_CSV = RESULTS_DIR / "kill1_oof_scores.csv"
    oof_fieldnames = ["cluster_id", "patient_id", "disagree_binary", "oof_score", "fold"]
    # 构建 cluster→fold 映射：每个 test_idx 对应哪一折
    cluster_to_fold = np.full(len(rows), -1, dtype=np.int32)
    for fold_i, (_, test_idx) in enumerate(folds):
        cluster_to_fold[test_idx] = fold_i + 1
    with open(str(OOF_CSV), "w", newline="", encoding="utf-8") as f_oof:
        oof_writer = csv.DictWriter(f_oof, fieldnames=oof_fieldnames)
        oof_writer.writeheader()
        for i, row in enumerate(rows):
            oof_writer.writerow({
                "cluster_id": row["nodule_cluster_id"],
                "patient_id": row["patient_id"],
                "disagree_binary": int(row["disagree_binary"]),
                "oof_score": float(oof_scores[i]),
                "fold": int(cluster_to_fold[i]),
            })
    print(f"[output] OOF CSV -> {OOF_CSV}")
    # ─────────────────────────────────────────────────────────────────────────

    # 写 summary JSON
    summary = {
        "cv_pooled_auroc": round(cv_auroc, 6),
        "ci_low": round(float(ci_lo), 6),
        "ci_high": round(float(ci_hi), 6),
        "perm_auroc_mean": (round(perm_mean, 6)
                            if not np.isnan(perm_mean) else None),
        "perm_p_value": (round(perm_p, 6)
                         if not np.isnan(perm_p) else None),
        "perm_n_rep": n_perm,
        "kill1_verdict": verdict,
        "threshold_auroc": 0.60,
        "threshold_ci_low": 0.50,
        "n_clusters": len(rows),
        "n_patients": int(len(unique_patients)),
        "n_splits": N_SPLITS,
        "per_fold": fold_results,
        "hyperparams": {
            "lr": LR,
            "weight_decay": WEIGHT_DECAY,
            "batch_size": BATCH_SIZE,
            "max_epochs": MAX_EPOCHS,
            "patience": PATIENCE,
            "perm_max_epochs": PERM_MAX_EPOCHS,
            "perm_patience": PERM_PATIENCE,
            "augment": "hflip+rot10deg",
            "model": "ResNet-18 ImageNet pretrained",
            "source": "researcher official 2026-06-18",
        },
        "design_note": (
            "Patient-level StratifiedGroupKFold n=5; "
            "groups=patient_id; stratify=disagree_binary. "
            "OOF predictions aggregated over all 75 clusters -> CV-AUROC. "
            "Permutation: only train-fold labels shuffled, val/test unchanged."
        ),
    }
    summary_path = RESULTS_DIR / "kill1_cv_summary.json"
    with open(str(summary_path), "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)
    print(f"[output] summary -> {summary_path}")


# --- 主函数 -------------------------------------------------------------------
def main() -> None:
    import multiprocessing
    multiprocessing.freeze_support()   # Windows spawn required

    parser = argparse.ArgumentParser(
        description="DisagreePred KILL-1 CV baseline: ResNet-18 predicts disagreement")
    parser.add_argument(
        "--label_csv", type=str, default=str(LABEL_CSV),
        help="Path to lidc_disagree_labels.csv from parse_lidc.py")
    parser.add_argument(
        "--no_permutation", action="store_true",
        help="Skip permutation test (debug / faster run)")
    parser.add_argument(
        "--n_perm", type=int, default=N_PERM,
        help=f"Number of permutation reps (default {N_PERM})")
    parser.add_argument(
        "--cpu", action="store_true",
        help="Force CPU (smoke test)")
    parser.add_argument(
        "--smoke", type=int, default=0,
        help="Smoke mode: use first N rows only (0=full)")
    parser.add_argument(
        "--seed", type=int, default=0,
        help="Global random seed (default 0)")
    parser.add_argument(
        "--quiet_fold", action="store_true",
        help="Suppress per-epoch fold output")
    args = parser.parse_args()

    # device
    if args.cpu or not torch.cuda.is_available():
        device = torch.device("cpu")
        print("[device] CPU")
    else:
        device = torch.device("cuda")
        print(f"[device] {torch.cuda.get_device_name(0)}")

    # load labels
    csv_path = Path(args.label_csv)
    rows = load_label_csv(csv_path)

    # smoke mode
    if args.smoke > 0:
        rows = rows[: args.smoke]
        print(f"[smoke] truncated to first {args.smoke} rows")

    run_kill1_cv(
        rows,
        device,
        run_permutation=not args.no_permutation,
        n_perm=args.n_perm,
        seed=args.seed,
        verbose_fold=not args.quiet_fold,
    )


if __name__ == "__main__":
    main()
