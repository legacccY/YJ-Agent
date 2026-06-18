"""
kill1_baseline.py — DisagreePred KILL-1 分歧可预测性 baseline

服务项目：DisagreePred，lever = KILL-1 gating（方案甲）
前置：先跑 parse_lidc.py 生成 lidc_disagree_labels.csv + patch npy 文件

方案：ImageNet 预训练 ResNet-18（2D），预测 disagree_binary（方案甲标签）
超参来源（researcher 核源 2026-06-18）：
  - Adam lr=1e-4, weight_decay=1e-4（官方口径）
  - batch=16~32（单卡 RTX4070 8GB 2D 全够）
  - 增强：水平翻转 + ±10° 旋转（CT 禁垂直翻转）
  - 5 seed {0,1,2,3,4}，报 test AUROC 均值±std
  - bootstrap 1000 次 AUROC 95% CI（纯 numpy，绕 scipy OMP 冲突）
  - 置换检验：标签打乱重训，AUROC 应塌 ~0.50（sanity check，非设计层防泄漏）

判据（02_ACCEPTANCE.md A1）：
  5-seed 均值 AUROC > 0.60 且 CI 下界 > 0.50 = KILL-1 PASS
  ≤ 0.60 = KILL-1 触发砍

Windows 规范：
  - if __name__=='__main__' 包主逻辑 + freeze_support
  - num_workers=0（spawn 模式不用 fork workers）
  - pin_memory=False（spawn worker 不支持）
  - 路径用正斜杠 / pathlib.Path

注意：本脚本不启动训练调度，写完交主线 /loop /run-experiment 跑
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import random
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
from torch.utils.data import DataLoader, Dataset

# ─── 路径配置 ─────────────────────────────────────────────────────────────────
SCRIPTS_DIR = Path(__file__).resolve().parent
PROJECT_DIR = SCRIPTS_DIR.parent
RESULTS_DIR = PROJECT_DIR / "results"
LABEL_CSV   = RESULTS_DIR / "lidc_disagree_labels.csv"
OUT_CSV     = RESULTS_DIR / "kill1_disagree_auroc.csv"

# 超参（官方口径，researcher 核源 2026-06-18）
LR           = 1e-4
WEIGHT_DECAY = 1e-4
BATCH_SIZE   = 16
MAX_EPOCHS   = 50
PATIENCE     = 8       # 早停
SEEDS        = [0, 1, 2, 3, 4]
N_BOOTSTRAP  = 1000    # bootstrap 次数（AUROC CI）

# 增强角度
ROTATE_DEG   = 10      # ±10° 旋转（CT 禁垂直翻转）


# ─── 纯 numpy AUROC（绕 scipy.stats OMP Error #15）──────────────────────────
def auroc_numpy(labels: np.ndarray, scores: np.ndarray) -> float:
    """
    纯 numpy 计算 AUROC（trapezoid rule）。
    绕过 scipy.stats.rankdata / kendalltau 与 torch 争 OpenMP → OMP Error #15。
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
    # 加 (0,0) 起点
    tpr = np.concatenate([[0.0], tpr])
    fpr = np.concatenate([[0.0], fpr])
    auc = float(np.trapz(tpr, fpr))
    return auc


def bootstrap_auroc_ci(labels: np.ndarray, scores: np.ndarray,
                       n: int = N_BOOTSTRAP,
                       ci: float = 0.95,
                       seed: int = 0) -> tuple[float, float]:
    """Bootstrap AUROC 95% CI（纯 numpy）。"""
    rng = np.random.default_rng(seed)
    size = len(labels)
    boot_aurocs = []
    for _ in range(n):
        idx = rng.integers(0, size, size)
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
    # 加 (0, precision[0]) 起点（避免 recall=0 漏起）
    precision = np.concatenate([[precision[0]], precision])
    recall = np.concatenate([[0.0], recall])
    auc = float(np.trapz(precision, recall))
    return auc


# ─── Dataset ─────────────────────────────────────────────────────────────────
class LIDCDisagreeDataset(Dataset):
    """
    方案甲：从 parse_lidc.py 输出的 CSV + npy patch 加载。
    只含 k≥1 cluster（CSV 已过滤，无需二次过滤）。
    输入：96×96 float32 灰度 npy → 复制成 3 通道 (3, 96, 96)。
    标签：disagree_binary (0/1)。
    增强（仅 train）：水平翻转 + ±10° 旋转（CT 禁垂直翻转）。
    """

    def __init__(self, rows: list[dict], split: str,
                 augment: bool = False,
                 permute_labels: bool = False,
                 seed: int = 0) -> None:
        self.rows = [r for r in rows if r["split"] == split]
        self.augment = augment
        self.permute_labels = permute_labels
        if permute_labels:
            # 置换检验：打乱标签（不动 patch）
            rng = random.Random(seed + 9999)
            labels = [int(r["disagree_binary"]) for r in self.rows]
            rng.shuffle(labels)
            for r, lb in zip(self.rows, labels):
                r = dict(r)   # 浅拷贝，不改原 rows
            # 重新构造带置换标签的 rows
            self._perm_labels = labels
        else:
            self._perm_labels = None

    def __len__(self) -> int:
        return len(self.rows)

    def __getitem__(self, idx: int):
        row = self.rows[idx]
        patch_path = row["patch_path"]
        label = self._perm_labels[idx] if self._perm_labels else int(row["disagree_binary"])

        # 加载 npy patch
        patch = np.load(patch_path).astype(np.float32)   # (96, 96) 或 (H, W)

        # 增强（仅 train，CT 禁垂直翻转）
        if self.augment:
            # 水平翻转
            if random.random() > 0.5:
                patch = np.fliplr(patch).copy()
            # ±10° 旋转（scipy 不可用，用 numpy 实现简单旋转）
            angle_deg = random.uniform(-ROTATE_DEG, ROTATE_DEG)
            patch = _rotate_patch(patch, angle_deg)

        # 灰度复制 3 通道（ImageNet ResNet-18 期望 3 通道输入）
        tensor = torch.from_numpy(patch).unsqueeze(0).repeat(3, 1, 1)   # (3, H, W)
        return tensor, torch.tensor(label, dtype=torch.float32)


def _rotate_patch(patch: np.ndarray, angle_deg: float) -> np.ndarray:
    """
    纯 numpy 双线性旋转（绕中心）。避免 scipy.ndimage（OMP 冲突）。
    angle_deg：旋转角度（度）
    """
    if abs(angle_deg) < 0.5:
        return patch
    h, w = patch.shape
    cx, cy = w / 2.0, h / 2.0
    angle_rad = math.radians(angle_deg)
    cos_a = math.cos(angle_rad)
    sin_a = math.sin(angle_rad)

    # 目标像素坐标网格
    ys, xs = np.meshgrid(np.arange(h), np.arange(w), indexing="ij")
    # 平移到中心
    xs_c = xs - cx
    ys_c = ys - cy
    # 逆旋转（从目标到源）
    xs_src = cos_a * xs_c + sin_a * ys_c + cx
    ys_src = -sin_a * xs_c + cos_a * ys_c + cy

    # 双线性插值
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


import math   # 补 import（_rotate_patch 依赖）


# ─── 模型 ─────────────────────────────────────────────────────────────────────
def build_model(device: torch.device) -> nn.Module:
    """
    ImageNet 预训练 ResNet-18，输出单 logit（sigmoid 后为 P(disagree=1)）。
    输入：(B, 3, 96, 96) 灰度复制 3 通道。
    首层保持 7×7 conv（96×96 输入够用，无需改）。
    """
    from torchvision.models import resnet18, ResNet18_Weights
    model = resnet18(weights=ResNet18_Weights.IMAGENET1K_V1)
    # 替换最终 fc → 单 logit
    model.fc = nn.Linear(model.fc.in_features, 1)
    return model.to(device)


# ─── 训练 / 评估单轮 ──────────────────────────────────────────────────────────
def train_epoch(model, loader, optimizer, criterion, device):
    model.train()
    total_loss = 0.0
    for imgs, labels in loader:
        imgs = imgs.to(device, non_blocking=False)
        labels = labels.to(device)
        optimizer.zero_grad()
        logits = model(imgs).squeeze(1)
        loss = criterion(logits, labels)
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
        imgs = imgs.to(device, non_blocking=False)
        logits = model(imgs).squeeze(1)
        scores = torch.sigmoid(logits).cpu().numpy()
        all_labels.append(labels.numpy())
        all_scores.append(scores)
    if not all_labels:
        return np.array([]), np.array([])
    return np.concatenate(all_labels), np.concatenate(all_scores)


# ─── 单 seed 跑完整训练 ───────────────────────────────────────────────────────
def run_one_seed(rows: list[dict], seed: int, device: torch.device,
                 permute: bool = False) -> dict:
    """
    训练一个 seed，返回结果字典。
    permute=True：标签置换检验模式。
    """
    # 固定随机种子
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)

    train_set = LIDCDisagreeDataset(rows, "train", augment=True,
                                    permute_labels=permute, seed=seed)
    val_set   = LIDCDisagreeDataset(rows, "val",   augment=False,
                                    permute_labels=permute, seed=seed)
    test_set  = LIDCDisagreeDataset(rows, "test",  augment=False,
                                    permute_labels=permute, seed=seed)

    # Windows：num_workers=0，pin_memory=False
    train_loader = DataLoader(train_set, batch_size=BATCH_SIZE, shuffle=True,
                              num_workers=0, pin_memory=False)
    val_loader   = DataLoader(val_set,   batch_size=BATCH_SIZE, shuffle=False,
                              num_workers=0, pin_memory=False)
    test_loader  = DataLoader(test_set,  batch_size=BATCH_SIZE, shuffle=False,
                              num_workers=0, pin_memory=False)

    model = build_model(device)
    optimizer = torch.optim.Adam(
        model.parameters(), lr=LR, weight_decay=WEIGHT_DECAY)
    criterion = nn.BCEWithLogitsLoss()

    # 早停
    best_val_auroc = -1.0
    best_state = None
    patience_counter = 0

    print(f"  [seed={seed}{'|PERM' if permute else ''}] "
          f"train={len(train_set)} val={len(val_set)} test={len(test_set)}")

    for epoch in range(MAX_EPOCHS):
        tr_loss = train_epoch(model, train_loader, optimizer, criterion, device)
        val_labels, val_scores = eval_epoch(model, val_loader, device)
        val_auroc = auroc_numpy(val_labels, val_scores)
        if np.isnan(val_auroc):
            val_auroc = 0.0

        if val_auroc > best_val_auroc:
            best_val_auroc = val_auroc
            best_state = {k: v.cpu().clone() for k, v in model.state_dict().items()}
            patience_counter = 0
        else:
            patience_counter += 1

        if (epoch + 1) % 10 == 0 or patience_counter == PATIENCE:
            print(f"    epoch {epoch+1:3d} | tr_loss={tr_loss:.4f} "
                  f"| val_auroc={val_auroc:.4f} | best={best_val_auroc:.4f} "
                  f"| patience={patience_counter}/{PATIENCE}")

        if patience_counter >= PATIENCE:
            print(f"    [早停] epoch {epoch+1}")
            break

    # 恢复最佳 ckpt 评估测试集
    if best_state is not None:
        model.load_state_dict(best_state)

    test_labels, test_scores = eval_epoch(model, test_loader, device)
    test_auroc = auroc_numpy(test_labels, test_scores)
    ci_lo, ci_hi = bootstrap_auroc_ci(test_labels, test_scores,
                                      N_BOOTSTRAP, seed=seed)
    test_auprc = auprc_numpy(test_labels, test_scores)

    return {
        "seed": seed,
        "permute": permute,
        "split": "test",
        "n_test": len(test_set),
        "auroc": round(float(test_auroc), 6),
        "auroc_ci_low": round(float(ci_lo), 6),
        "auroc_ci_high": round(float(ci_hi), 6),
        "auprc": round(float(test_auprc), 6),
        "best_val_auroc": round(float(best_val_auroc), 6),
    }


# ─── 主函数 ───────────────────────────────────────────────────────────────────
def load_label_csv(csv_path: Path) -> list[dict]:
    assert csv_path.exists(), (
        f"[DATA] 标签 CSV 未找到：{csv_path}\n"
        "请先运行 parse_lidc.py 生成 lidc_disagree_labels.csv"
    )
    rows = []
    with open(str(csv_path), newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            # 验证所有 patch 文件存在
            pp = Path(row["patch_path"])
            assert pp.exists(), f"[DATA] patch 文件缺失：{pp}"
            rows.append(row)
    assert rows, f"[DATA] CSV 为空：{csv_path}"
    print(f"[load] 共 {len(rows)} 条 cluster（全 k>=1，方案甲）")

    # 统计类别分布
    n_pos = sum(int(r["disagree_binary"]) for r in rows)
    n_neg = len(rows) - n_pos
    print(f"[load] disagree=1: {n_pos}, disagree=0: {n_neg}, "
          f"rate={n_pos/len(rows):.3f}")
    return rows


def run_kill1(rows: list[dict], device: torch.device,
              run_permutation: bool = True,
              seeds: list[int] | None = None) -> None:
    """
    主实验：5 seed 跑 baseline + 置换检验（标签打乱）。
    输出 kill1_disagree_auroc.csv + 终端 KILL-1 判决。
    seeds: 使用的 seed 列表，None 则用模块常量 SEEDS。
    """
    if seeds is None:
        seeds = SEEDS
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    all_results = []

    # ─── 5 seed baseline ─────────────────────────────────────────────────
    print("\n[KILL-1] 开始 5-seed baseline 训练...")
    for seed in seeds:
        print(f"\n[seed={seed}]")
        result = run_one_seed(rows, seed, device, permute=False)
        all_results.append(result)
        print(f"  test AUROC={result['auroc']:.4f} "
              f"CI=[{result['auroc_ci_low']:.4f}, {result['auroc_ci_high']:.4f}] "
              f"AUPRC={result['auprc']:.4f}")

    # ─── 置换检验（仅 seed=0，验 sanity）────────────────────────────────
    perm_aurocs = []
    if run_permutation:
        print("\n[KILL-1] 置换检验（标签打乱，AUROC 应塌 ~0.50）...")
        print("  注意：置换检验是 sanity check，非设计层防泄漏手段")
        print("  方案甲防泄漏靠：只在 k>=1 区内预测（不含 k=0 无结节区）")
        for seed in seeds[:2]:   # 只跑 2 个 seed 节省算力
            print(f"\n[perm seed={seed}]")
            result_perm = run_one_seed(rows, seed, device, permute=True)
            all_results.append(result_perm)
            perm_aurocs.append(result_perm["auroc"])
            print(f"  perm AUROC={result_perm['auroc']:.4f}")

    # ─── 写 CSV ──────────────────────────────────────────────────────────
    perm_mean = float(np.mean(perm_aurocs)) if perm_aurocs else float("nan")
    fieldnames = [
        "seed", "split", "n_test", "auroc",
        "auroc_ci_low", "auroc_ci_high", "auprc",
        "permutation_auroc_mean",
    ]
    with open(str(OUT_CSV), "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in all_results:
            if r["permute"]:
                continue   # 置换结果单独在摘要，不混入主 CSV
            writer.writerow({
                "seed": r["seed"],
                "split": r["split"],
                "n_test": r["n_test"],
                "auroc": r["auroc"],
                "auroc_ci_low": r["auroc_ci_low"],
                "auroc_ci_high": r["auroc_ci_high"],
                "auprc": r["auprc"],
                "permutation_auroc_mean": round(perm_mean, 6) if not np.isnan(perm_mean) else "nan",
            })

    # ─── KILL-1 判决 ─────────────────────────────────────────────────────
    baseline_aurocs = [r["auroc"] for r in all_results if not r["permute"]]
    mean_auroc = float(np.mean(baseline_aurocs))
    std_auroc  = float(np.std(baseline_aurocs))
    # 5-seed 联合 CI：对所有 test 样本合并后跑 bootstrap
    # 此处以各 seed 的 CI 下界均值作为保守估计（严格需合并预测）
    ci_lows = [r["auroc_ci_low"] for r in all_results if not r["permute"]]
    mean_ci_low = float(np.mean(ci_lows))

    print("\n" + "=" * 60)
    print("KILL-1 VERDICT (02_ACCEPTANCE.md A1)")
    print(f"  5-seed 均值 AUROC : {mean_auroc:.4f} ± {std_auroc:.4f}")
    print(f"  CI 下界（各 seed 均值）: {mean_ci_low:.4f}")
    if perm_aurocs:
        print(f"  置换检验均值 AUROC   : {perm_mean:.4f}  (期望 ~0.50)")
    print()
    if mean_auroc > 0.60 and mean_ci_low > 0.50:
        verdict = "PASS"
        print("  ✓ KILL-1 PASS：均值 AUROC > 0.60，CI 下界 > 0.50")
        print("  → 分歧可预测性 claim 有实证支撑，继续 A2/A3/A4。")
    else:
        verdict = "FAIL"
        print("  ✗ KILL-1 FAIL：AUROC ≤ 0.60 或 CI 下界 ≤ 0.50")
        print("  → 核心 claim 死，按 ACCEPTANCE.md kill criteria 诚实回退。")
    print("=" * 60)

    # 写摘要 json
    summary = {
        "mean_auroc": round(mean_auroc, 6),
        "std_auroc": round(std_auroc, 6),
        "mean_ci_low": round(mean_ci_low, 6),
        "permutation_auroc_mean": round(perm_mean, 6) if not np.isnan(perm_mean) else None,
        "kill1_verdict": verdict,
        "threshold_auroc": 0.60,
        "threshold_ci_low": 0.50,
        "seeds": seeds,
        "hyperparams": {
            "lr": LR, "weight_decay": WEIGHT_DECAY,
            "batch_size": BATCH_SIZE, "max_epochs": MAX_EPOCHS,
            "patience": PATIENCE, "augment": "hflip+rot10deg",
            "model": "ResNet-18 ImageNet pretrained",
            "source": "researcher 官方口径 2026-06-18",
        },
        "design_note": "方案甲：k>=1 区内预测分歧；置换检验=sanity check非设计层防泄漏",
    }
    summary_path = RESULTS_DIR / "kill1_summary.json"
    with open(str(summary_path), "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)

    print(f"\n[输出] CSV     → {OUT_CSV}")
    print(f"[输出] 摘要    → {summary_path}")


def main() -> None:
    import multiprocessing
    multiprocessing.freeze_support()   # Windows spawn 必须

    parser = argparse.ArgumentParser(
        description="DisagreePred KILL-1 baseline：ResNet-18 预测分歧（方案甲）")
    parser.add_argument(
        "--label_csv", type=str, default=str(LABEL_CSV),
        help="parse_lidc.py 输出的标签 CSV 路径")
    parser.add_argument(
        "--no_permutation", action="store_true",
        help="跳过置换检验（节省时间，调试用）")
    parser.add_argument(
        "--cpu", action="store_true",
        help="强制 CPU（smoke 测试用）")
    parser.add_argument(
        "--smoke", type=int, default=0,
        help="smoke 模式：只用前 N 条（0=全量）")
    parser.add_argument(
        "--seeds", type=int, nargs="+", default=SEEDS,
        help="运行的 seed 列表（默认 0 1 2 3 4）")
    args = parser.parse_args()

    # device
    if args.cpu or not torch.cuda.is_available():
        device = torch.device("cpu")
        print("[device] CPU")
    else:
        device = torch.device("cuda")
        print(f"[device] {torch.cuda.get_device_name(0)}")

    # 加载标签
    csv_path = Path(args.label_csv)
    rows = load_label_csv(csv_path)

    # smoke 模式：截断
    if args.smoke > 0:
        rows = rows[: args.smoke]
        print(f"[smoke] 截断到前 {args.smoke} 条")

    run_kill1(rows, device, run_permutation=not args.no_permutation,
              seeds=args.seeds)


if __name__ == "__main__":
    main()
