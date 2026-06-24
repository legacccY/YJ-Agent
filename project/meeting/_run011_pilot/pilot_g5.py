"""
pilot_g5.py
===========
用途：run-011 候选A G5 杀手锏 pilot。
      跑 2方法 × 3比例 × 2seed = 12 runs，评估标注效率曲线。

方法：
  (1) supervised  — 仅用标注子集监督训练
  (2) mean_teacher — EMA teacher + 一致性损失（参考 SSL4MIS mean_teacher 实现）

标注比例：5%, 10%, 20%
Seeds：0, 1

怎么跑（主线按序执行）：
  # 烟测（1 seed, 5% ratio, 5 epoch，约 2-5 min）
  python pilot_g5.py --quick

  # 全量（12 runs，约 30-60 min on RTX4070）
  python pilot_g5.py

输出：
  results/results.csv   — 最终所有 run 的 Dice / HD95
  results/state.json    — 实时进度（context 压缩后主线靠它续）

红线（已遵守）：
  - 测试集固定 held-out，绝不参与训练（dataset.py make_splits 保证）
  - num_workers=0，pin_memory=False（Windows spawn 安全）
  - OMP_NUM_THREADS=1（防 OMP Error #15）
  - 路径全用 pathlib / os.path.join
"""

from __future__ import annotations

import argparse
import copy
import csv
import json
import os
import random
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

# 本地模块
from dataset import get_dataloaders, UnlabeledPSFHSDataset, PSFHSDataset, make_splits
from dataset import _find_subdir, _IMAGE_DIR_CANDIDATES, _LABEL_DIR_CANDIDATES, _get_case_ids
from pathlib import Path as _Path
from torch.utils.data import DataLoader
from unet import UNet

# ---------- 路径配置 ----------
SCRIPT_DIR = Path(__file__).resolve().parent
DATA_DIR = SCRIPT_DIR / "data" / "PSFHS"
RESULTS_DIR = SCRIPT_DIR / "results"
RESULTS_CSV = RESULTS_DIR / "results.csv"
STATE_JSON = RESULTS_DIR / "state.json"

# ---------- 超参 ----------
NUM_CLASSES = 3        # 0=bg, 1=PS, 2=FH
IN_CHANNELS = 1
BASE_CHANNELS = 32
IMAGE_SIZE = 256
BATCH_SIZE = 4         # 小 batch，兼顾 8GB 显存
LR = 1e-3
WEIGHT_DECAY = 1e-4

# Mean Teacher
MT_CONSISTENCY_WEIGHT = 0.1   # 一致性损失权重（参考 SSL4MIS 默认）
MT_EMA_DECAY = 0.99            # EMA 衰减（参考 SSL4MIS mean_teacher.py）
MT_RAMPUP_EPOCHS = 40          # 一致性权重 sigmoid ramp-up 长度（参考 SSL4MIS）

LABEL_RATIOS = [0.05, 0.10, 0.20]
SEEDS = [0, 1]
N_EPOCHS = 100   # 全量 epoch（本地小图约 100 epoch 可看趋势）

# --quick 模式
QUICK_EPOCHS = 5
QUICK_RATIO = 0.05
QUICK_SEED = 0


# ============================================================
# 工具函数
# ============================================================

def set_seed(seed: int):
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)


def sigmoid_rampup(current_epoch: int, rampup_length: int) -> float:
    """Sigmoid ramp-up，用于平滑增加一致性权重（SSL4MIS 同款）。"""
    if rampup_length == 0:
        return 1.0
    current = np.clip(current_epoch / rampup_length, 0.0, 1.0)
    phase = 1.0 - current
    return float(np.exp(-5.0 * phase * phase))


def update_ema_variables(model: nn.Module, ema_model: nn.Module, alpha: float):
    """EMA teacher 参数更新：teacher = alpha * teacher + (1-alpha) * student。"""
    for ema_param, param in zip(ema_model.parameters(), model.parameters()):
        ema_param.data.mul_(alpha).add_(param.data * (1.0 - alpha))


def compute_dice_per_class(
    preds: torch.Tensor, targets: torch.Tensor, num_classes: int
) -> List[float]:
    """
    计算每个前景类的 Dice（排除 class 0 背景）。
    preds:   [B, H, W] int64
    targets: [B, H, W] int64
    返回: list of float, len = num_classes - 1
    """
    dices = []
    for c in range(1, num_classes):  # 跳过背景
        pred_c = (preds == c).float()
        tgt_c = (targets == c).float()
        inter = (pred_c * tgt_c).sum()
        union = pred_c.sum() + tgt_c.sum()
        if union < 1e-6:
            # 该类在 batch 中不存在 → Dice=1（两者都空）
            dices.append(1.0)
        else:
            dices.append((2.0 * inter / union).item())
    return dices


def compute_hd95(
    preds: torch.Tensor, targets: torch.Tensor, num_classes: int
) -> List[float]:
    """
    近似 HD95（基于 numpy，避免 scipy）。
    对每类分别计算，取 95th percentile 豪斯多夫距离。
    CPU-only，在测试集上全量跑。
    """
    from scipy.ndimage import distance_transform_edt  # scipy 仅用于 distance_transform，不涉及 OMP 冲突
    # 注：scipy.ndimage.distance_transform_edt 不经 OpenMP 线程池，安全
    hds = []
    preds_np = preds.cpu().numpy()
    tgts_np = targets.cpu().numpy()

    for c in range(1, num_classes):
        pred_c = (preds_np == c).astype(np.uint8)
        tgt_c = (tgts_np == c).astype(np.uint8)

        # 若两者都空或都满，HD=0
        if pred_c.sum() == 0 and tgt_c.sum() == 0:
            hds.append(0.0)
            continue
        if pred_c.sum() == 0 or tgt_c.sum() == 0:
            # 极端情况：预测/真值一方全空 → HD=图像对角线
            hds.append(float(np.sqrt(pred_c.shape[-2] ** 2 + pred_c.shape[-1] ** 2)))
            continue

        # 扁平化所有 batch 样本（近似）
        pred_flat = pred_c.reshape(-1, pred_c.shape[-2], pred_c.shape[-1])
        tgt_flat = tgt_c.reshape(-1, tgt_c.shape[-2], tgt_c.shape[-1])

        hd_batch = []
        for i in range(pred_flat.shape[0]):
            p = pred_flat[i]
            t = tgt_flat[i]
            if p.sum() == 0 or t.sum() == 0:
                continue
            dist_p = distance_transform_edt(1 - p)
            dist_t = distance_transform_edt(1 - t)
            # 对称豪斯多夫：每个预测点到最近真值点的距离 + 反向
            surf_dists = np.concatenate([dist_t[p == 1], dist_p[t == 1]])
            hd_batch.append(np.percentile(surf_dists, 95))

        hds.append(np.mean(hd_batch) if hd_batch else 0.0)

    return hds


# ============================================================
# 状态持久化
# ============================================================

def load_state() -> dict:
    if STATE_JSON.exists():
        with open(STATE_JSON, "r", encoding="utf-8") as f:
            return json.load(f)
    return {
        "phase": "init",
        "current_run": None,
        "runs_done": [],
        "total_runs": 0,
        "last_dice": None,
    }


def save_state(state: dict):
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    with open(STATE_JSON, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)


def init_csv():
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    if not RESULTS_CSV.exists():
        with open(RESULTS_CSV, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([
                "method", "label_ratio", "seed",
                "dice_ps", "dice_fh", "dice_mean",
                "hd95_ps", "hd95_fh", "hd95_mean",
                "n_labeled", "n_unlabeled", "n_test",
                "epochs", "train_time_min",
            ])


def append_csv(row: dict):
    with open(RESULTS_CSV, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "method", "label_ratio", "seed",
            "dice_ps", "dice_fh", "dice_mean",
            "hd95_ps", "hd95_fh", "hd95_mean",
            "n_labeled", "n_unlabeled", "n_test",
            "epochs", "train_time_min",
        ])
        writer.writerow(row)


def run_already_done(state: dict, run_id: str) -> bool:
    return run_id in state.get("runs_done", [])


# ============================================================
# 评估
# ============================================================

def evaluate(model: nn.Module, loader: DataLoader, device: torch.device) -> Tuple[List[float], List[float]]:
    """在 loader 上评估，返回 (dice_list, hd95_list)，各 len=num_classes-1。"""
    model.eval()
    all_preds = []
    all_targets = []

    with torch.no_grad():
        for imgs, lbls in loader:
            imgs = imgs.to(device)
            with autocast(enabled=device.type == "cuda"):
                logits = model(imgs)
            preds = logits.argmax(dim=1).cpu()  # [B, H, W]
            all_preds.append(preds)
            all_targets.append(lbls)

    all_preds = torch.cat(all_preds, dim=0)
    all_targets = torch.cat(all_targets, dim=0)

    dices = compute_dice_per_class(all_preds, all_targets, NUM_CLASSES)
    hds = compute_hd95(all_preds, all_targets, NUM_CLASSES)

    return dices, hds


# ============================================================
# Supervised-only 训练
# ============================================================

def train_supervised(
    labeled_loader: DataLoader,
    test_loader: DataLoader,
    device: torch.device,
    n_epochs: int,
    run_id: str,
) -> dict:
    model = UNet(in_channels=IN_CHANNELS, num_classes=NUM_CLASSES, base_channels=BASE_CHANNELS).to(device)
    optimizer = torch.optim.Adam(model.parameters(), lr=LR, weight_decay=WEIGHT_DECAY)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=n_epochs)
    scaler = GradScaler(enabled=device.type == "cuda")
    ce_loss = nn.CrossEntropyLoss()

    t0 = time.time()
    for epoch in range(n_epochs):
        model.train()
        total_loss = 0.0
        n_batches = 0
        for imgs, lbls in labeled_loader:
            imgs, lbls = imgs.to(device), lbls.to(device)
            optimizer.zero_grad()
            with autocast(enabled=device.type == "cuda"):
                logits = model(imgs)
                loss = ce_loss(logits, lbls)
            scaler.scale(loss).backward()
            scaler.step(optimizer)
            scaler.update()
            total_loss += loss.item()
            n_batches += 1
        scheduler.step()

        if (epoch + 1) % max(1, n_epochs // 5) == 0 or epoch == n_epochs - 1:
            avg_loss = total_loss / max(n_batches, 1)
            dices, _ = evaluate(model, test_loader, device)
            print(
                f"  [supervised] {run_id} epoch={epoch+1}/{n_epochs} "
                f"loss={avg_loss:.4f} dice_mean={np.mean(dices):.4f}"
            )

    train_time = (time.time() - t0) / 60.0
    dices, hds = evaluate(model, test_loader, device)
    return {"dices": dices, "hds": hds, "train_time_min": train_time}


# ============================================================
# Mean Teacher 训练（参考 SSL4MIS HiLab-git/SSL4MIS mean_teacher 实现）
# 核心逻辑：student 用有标注数据做 CE loss + 无标注数据做一致性 loss（MSE on softmax）
# teacher 用 EMA 更新，不直接梯度
# ============================================================

def train_mean_teacher(
    labeled_loader: DataLoader,
    unlabeled_loader: DataLoader,
    test_loader: DataLoader,
    device: torch.device,
    n_epochs: int,
    run_id: str,
) -> dict:
    student = UNet(in_channels=IN_CHANNELS, num_classes=NUM_CLASSES, base_channels=BASE_CHANNELS).to(device)
    teacher = copy.deepcopy(student)
    # teacher 参数不参与梯度更新
    for param in teacher.parameters():
        param.requires_grad_(False)

    optimizer = torch.optim.Adam(student.parameters(), lr=LR, weight_decay=WEIGHT_DECAY)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=n_epochs)
    scaler = GradScaler(enabled=device.type == "cuda")
    ce_loss = nn.CrossEntropyLoss()

    # 无标注 loader 需要能循环（无标注样本可能比标注多很多）
    unlabeled_iter = iter(unlabeled_loader)

    t0 = time.time()
    for epoch in range(n_epochs):
        student.train()
        teacher.train()  # BN 在 teacher 也 train（SSL4MIS 同款，让 BN 统计更准）
        total_sup_loss = 0.0
        total_cons_loss = 0.0
        n_batches = 0

        consistency_weight = MT_CONSISTENCY_WEIGHT * sigmoid_rampup(epoch, MT_RAMPUP_EPOCHS)

        for imgs_l, lbls_l in labeled_loader:
            imgs_l = imgs_l.to(device)
            lbls_l = lbls_l.to(device)

            # 取一个无标注 batch（循环）
            try:
                imgs_u = next(unlabeled_iter)
            except StopIteration:
                unlabeled_iter = iter(unlabeled_loader)
                imgs_u = next(unlabeled_iter)
            imgs_u = imgs_u.to(device)

            optimizer.zero_grad()

            with autocast(enabled=device.type == "cuda"):
                # --- 有监督损失（student on labeled）---
                logits_l = student(imgs_l)
                sup_loss = ce_loss(logits_l, lbls_l)

                # --- 一致性损失（student vs teacher on unlabeled）---
                logits_u_student = student(imgs_u)
                with torch.no_grad():
                    logits_u_teacher = teacher(imgs_u)

                # softmax 后 MSE（SSL4MIS mean_teacher 用 MSE on softmax）
                prob_student = F.softmax(logits_u_student, dim=1)
                prob_teacher = F.softmax(logits_u_teacher, dim=1).detach()
                cons_loss = F.mse_loss(prob_student, prob_teacher)

                loss = sup_loss + consistency_weight * cons_loss

            scaler.scale(loss).backward()
            scaler.step(optimizer)
            scaler.update()

            # EMA 更新 teacher
            update_ema_variables(student, teacher, alpha=MT_EMA_DECAY)

            total_sup_loss += sup_loss.item()
            total_cons_loss += cons_loss.item()
            n_batches += 1

        scheduler.step()

        if (epoch + 1) % max(1, n_epochs // 5) == 0 or epoch == n_epochs - 1:
            avg_sup = total_sup_loss / max(n_batches, 1)
            avg_cons = total_cons_loss / max(n_batches, 1)
            dices, _ = evaluate(teacher, test_loader, device)  # 用 teacher 评估（SSL4MIS 惯例）
            print(
                f"  [mean_teacher] {run_id} epoch={epoch+1}/{n_epochs} "
                f"sup={avg_sup:.4f} cons={avg_cons:.4f} "
                f"cw={consistency_weight:.3f} dice_mean={np.mean(dices):.4f}"
            )

    train_time = (time.time() - t0) / 60.0
    dices, hds = evaluate(teacher, test_loader, device)  # 最终用 teacher 评估
    return {"dices": dices, "hds": hds, "train_time_min": train_time}


# ============================================================
# 单次 run
# ============================================================

def run_one(
    method: str,
    label_ratio: float,
    seed: int,
    n_epochs: int,
    device: torch.device,
    state: dict,
) -> Optional[dict]:
    run_id = f"{method}_r{int(label_ratio*100):03d}_s{seed}"

    if run_already_done(state, run_id):
        print(f"[skip] {run_id} 已完成（见 state.json），跳过")
        return None

    print(f"\n{'='*60}")
    print(f"[run] {run_id}  epochs={n_epochs}")

    set_seed(seed)

    # 构建 dataloader
    labeled_loader, unlabeled_loader, test_loader = get_dataloaders(
        data_dir=str(DATA_DIR),
        label_ratio=label_ratio,
        batch_size=BATCH_SIZE,
        seed=seed,
        num_workers=0,
    )

    n_labeled = len(labeled_loader.dataset)
    n_unlabeled = len(unlabeled_loader.dataset)
    n_test = len(test_loader.dataset)

    state["current_run"] = run_id
    state["phase"] = "training"
    save_state(state)

    # 训练
    if method == "supervised":
        result = train_supervised(labeled_loader, test_loader, device, n_epochs, run_id)
    elif method == "mean_teacher":
        result = train_mean_teacher(
            labeled_loader, unlabeled_loader, test_loader, device, n_epochs, run_id
        )
    else:
        raise ValueError(f"未知方法: {method}")

    dices = result["dices"]   # [dice_ps, dice_fh]
    hds = result["hds"]       # [hd95_ps, hd95_fh]

    row = {
        "method": method,
        "label_ratio": f"{label_ratio:.2f}",
        "seed": seed,
        "dice_ps": f"{dices[0]:.4f}",
        "dice_fh": f"{dices[1]:.4f}",
        "dice_mean": f"{np.mean(dices):.4f}",
        "hd95_ps": f"{hds[0]:.2f}",
        "hd95_fh": f"{hds[1]:.2f}",
        "hd95_mean": f"{np.mean(hds):.2f}",
        "n_labeled": n_labeled,
        "n_unlabeled": n_unlabeled,
        "n_test": n_test,
        "epochs": n_epochs,
        "train_time_min": f"{result['train_time_min']:.2f}",
    }
    append_csv(row)

    state["runs_done"].append(run_id)
    state["current_run"] = None
    state["last_dice"] = float(np.mean(dices))
    save_state(state)

    print(
        f"[done] {run_id}  dice_ps={dices[0]:.4f}  dice_fh={dices[1]:.4f}  "
        f"dice_mean={np.mean(dices):.4f}  hd95={np.mean(hds):.1f}  "
        f"time={result['train_time_min']:.1f}min"
    )
    return row


# ============================================================
# 主入口
# ============================================================

def main():
    parser = argparse.ArgumentParser(description="run-011 G5 杀手锏 pilot")
    parser.add_argument(
        "--quick",
        action="store_true",
        default=False,
        help="烟测模式：1 seed, 5%% ratio, 5 epoch（约 2-5 min）",
    )
    parser.add_argument(
        "--data_dir",
        type=str,
        default=str(DATA_DIR),
        help="PSFHS 数据目录",
    )
    parser.add_argument(
        "--epochs",
        type=int,
        default=None,
        help="覆盖 epoch 数（默认 100 / quick 模式 5）",
    )
    args = parser.parse_args()

    # 检查数据
    data_dir = Path(args.data_dir)
    if not data_dir.exists():
        print(f"[ERROR] 数据目录不存在: {data_dir}")
        print("请先运行：python download_psfhs.py")
        return

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"[pilot_g5] device={device}")
    if device.type == "cuda":
        print(f"  GPU: {torch.cuda.get_device_name(0)}")
        print(f"  VRAM: {torch.cuda.get_device_properties(0).total_memory / 1024**3:.1f} GB")

    # 确定运行矩阵
    if args.quick:
        methods = ["supervised", "mean_teacher"]
        ratios = [QUICK_RATIO]
        seeds = [QUICK_SEED]
        n_epochs = args.epochs or QUICK_EPOCHS
        print(f"[quick] 烟测模式：{len(methods)} methods × {len(ratios)} ratios × {len(seeds)} seeds × {n_epochs} epochs")
    else:
        methods = ["supervised", "mean_teacher"]
        ratios = LABEL_RATIOS
        seeds = SEEDS
        n_epochs = args.epochs or N_EPOCHS
        total = len(methods) * len(ratios) * len(seeds)
        print(f"[full] {len(methods)} methods × {len(ratios)} ratios × {len(seeds)} seeds = {total} runs × {n_epochs} epochs")

    # 初始化状态和 CSV
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    state = load_state()
    state["total_runs"] = len(methods) * len(ratios) * len(seeds)
    state["phase"] = "starting"
    save_state(state)
    init_csv()

    # 跑所有 runs
    all_rows = []
    for method in methods:
        for ratio in ratios:
            for seed in seeds:
                row = run_one(method, ratio, seed, n_epochs, device, state)
                if row:
                    all_rows.append(row)

    # 汇总打印
    state["phase"] = "done"
    save_state(state)

    print(f"\n{'='*60}")
    print(f"[summary] 所有 run 完成")
    print(f"  结果: {RESULTS_CSV}")
    print(f"  状态: {STATE_JSON}")

    # 打印汇总表（命门判断依据）
    if RESULTS_CSV.exists():
        print(f"\n{'method':<16} {'ratio':<8} {'seed':<6} {'dice_ps':<10} {'dice_fh':<10} {'dice_mean':<10}")
        print("-" * 65)
        with open(RESULTS_CSV, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for r in reader:
                print(
                    f"{r['method']:<16} {r['label_ratio']:<8} {r['seed']:<6} "
                    f"{r['dice_ps']:<10} {r['dice_fh']:<10} {r['dice_mean']:<10}"
                )

    print("\n[verdict guide]")
    print("  spread（同比例两法 dice_mean 差）< 1% 且无交叉/拐点 → 故事塌，建议 kill")
    print("  spread ≥ 2% 或有交叉/拐点结构                      → 有可报告曲线，候选A PASS")


# Windows spawn 安全：__main__ 守卫
if __name__ == "__main__":
    main()
