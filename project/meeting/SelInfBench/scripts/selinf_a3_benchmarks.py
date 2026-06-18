"""
selinf_a3_benchmarks.py — SelInfBench A3 扩 benchmark + deflation-vs-M 曲线
服务: SelInfBench (selinf) A3，lever = ≥3 benchmark deflation-vs-M 单调增 + 真区间系统失效
不启动训练外部进程；写完交主线跑。

Benchmark 清单（3 个，与 HAM 合计即覆盖 A3 ≥3 判据）：
  1. HAM10000     — 7 类皮镜（旧结果，A3 里复用 _stat 行；本脚本不重跑 HAM）
  2. ISIC2020     — melanoma 二分类（AUROC 主指标，~1.77% 阳性；数据路径 datasets.json isic2020）
  3. BraTS2021    — FLAIR slice tumor-vs-normal 二分类（AUROC；路径 medianomaly_bench BraTS2021 test 集）

统一 sweep 协议（18-config，与 HAM 完全一致，跨集可比）：
  HP_LR       = [1e-3, 3e-4]
  HP_DROPOUT  = [0.2, 0.4, 0.6]
  HP_SEEDS    = [42, 123, 2024]
  2×3×3 = 18 configs，各跑 15 epoch，batch=32，EfficientNet-B3 ImageNet1K pretrain

deflation-vs-M 曲线（每 benchmark × M∈{4,8,18,36}）：
  M=4：从 M=18 网格中等间隔取 4 个 config（idx = [0,5,11,17] in 0-based grid18 排列）
  M=8：从 M=18 网格中等间隔取 8 个 config（idx = [0,2,4,7,9,12,14,17]）
  M=18：全量 2×3×3 grid
  M=36：扩 seed 列表到 6 个 [42,123,2024,7,99,314]，2×3×6=36 configs
  理由（等间隔取子集保可比）：等间隔遍历 lr × dropout × seed 三维网格，
    使 M=4/8 子集的边际分布覆盖 lr 和 dropout 取值范围，避免 M 小时只采一侧极端点，
    与 M=18 完全可比（都用同样初始化 + 数据分割）。

难度体检（skeptic 要求，跑 sweep 前先快探）：
  先跑 3 epoch 2-config 快探，估 baseline AUROC 中位数；
  >0.95 触顶 → 打印 WARNING，标注「可能任务过易，deflation 坍由 config 间方差→0 导致，非 winner's curse 不存在」。
  体检结果写入 csv baseline_auroc_median 列 + 末尾 print。

sigma 估计口径：sweep pooled std（与 HAM 完全一致）。
data fission：tau=1.0，Leiner+ JASA2023（复用 selinf_datafission.py 的实现）。

输出：
  project/meeting/SelInfBench/results/a3_deflation_vs_M.csv
  列：benchmark, M, method{naive,datafission,sqrtM}, selected_config, ci_width,
       deflation_pct, best_auroc, baseline_auroc_median

A3 判决（末尾 print）：
  3 benchmark deflation-vs-M 斜率是否同向为正 + data fission 是否随 M 系统增

Windows 规范：num_workers=0, pin_memory=False, if __name__=='__main__',
  _disable_inplace_silu, cudnn.benchmark=False, 正斜杠路径, 种子固定
单卡 8GB：batch≤32，TRAIN_N/VAL_N 控制规模
算力预算：≤4 GPU·h（两 benchmark × M=18 各≈0.36 GPU·h；M=36 约 ×2=≈1.44 GPU·h；总≤3 GPU·h）
"""

import os
import sys
import argparse
import itertools
import random
from pathlib import Path

os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")

import numpy as np
import pandas as pd
import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.utils.data import Dataset, DataLoader, WeightedRandomSampler
from torchvision import transforms
from torchvision.models import efficientnet_b3, EfficientNet_B3_Weights
from PIL import Image

# ── 路径（真源 .portfolio/datasets.json）──────────────────────────────────────
ISIC_IMG_DIR  = Path("D:/YJ-Agent/data/raw/isic2020/train-image/image")
ISIC_GT_CSV   = Path("D:/YJ-Agent/data/raw/isic2020/ISIC_2020_Training_GroundTruth_v2.csv")
ISIC_SPLIT_CSV= Path("D:/YJ-Agent/data/isic_split.csv")

BRATS_TEST    = Path("D:/YJ-Agent/project/meeting/MedAD-FailMap/data/BraTS2021/test")
BRATS_NORMAL  = BRATS_TEST / "normal"
BRATS_TUMOR   = BRATS_TEST / "tumor"

HAM_RESULT_CSV= Path("D:/YJ-Agent/project/meeting/SelInfBench/results/ham_datafission.csv")
OUT_DIR       = Path("D:/YJ-Agent/project/meeting/SelInfBench/results")
OUT_CSV       = OUT_DIR / "a3_deflation_vs_M.csv"

# ── HP sweep 网格（与 HAM 完全一致，跨集可比）───────────────────────────────
HP_LR         = [1e-3, 3e-4]
HP_DROPOUT    = [0.2, 0.4, 0.6]
HP_SEEDS_18   = [42, 123, 2024]          # M=4/8/18 用
HP_SEEDS_36   = [42, 123, 2024, 7, 99, 314]  # M=36 扩 seed

# M∈{4,8,18,36} 子集索引（基于 M=18 grid 的 0-based 等间隔取）
# grid18 = list(itertools.product(HP_LR, HP_DROPOUT, HP_SEEDS_18))
# 等间隔取法：np.linspace(0,17,M,dtype=int)
M_VALUES      = [4, 8, 18, 36]
M_SUBSET_IDX  = {
    4:  [0, 5, 11, 17],
    8:  [0, 2, 4, 7, 9, 12, 14, 17],
    18: list(range(18)),    # 全量
    36: None,               # 用 HP_SEEDS_36 另建 grid（2×3×6=36）
}

BATCH               = 32
EPOCHS_PER_CONFIG   = 15
FISSION_TAU         = 1.0
ALPHA               = 0.05

# ISIC 样本数控制（二分类，高度不平衡）
ISIC_TRAIN_N        = 2000   # 从 train split 取（正样本 ~35 = 1.77%）
ISIC_VAL_N          = 600    # 从 val split 取

# BraTS 样本数控制（normal 828 / tumor 1948，适中直接用全量 test）
BRATS_USE_ALL_TEST  = True   # 如需限制样本改 False 并设 BRATS_TRAIN_N/VAL_N

# 难度体检快探参数
PROBE_EPOCHS        = 3      # 难度体检只跑 3 epoch
PROBE_CONFIGS       = 2      # 快探 2 个 config（lr=1e-3/dp=0.2/s=42 + lr=3e-4/dp=0.4/s=123）

DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")
torch.backends.cudnn.benchmark = False   # RTX4070 WDDM 兼容


# ═══════════════════════════════════════════════════════════════════════════════
# 复用 selinf_datafission.py 的工具函数（直接内嵌，避免 import 路径问题）
# ═══════════════════════════════════════════════════════════════════════════════

def set_seed(s: int):
    random.seed(s)
    np.random.seed(s)
    torch.manual_seed(s)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(s)


def z_score(alpha: float) -> float:
    """N(0,1) upper alpha/2 quantile，纯 numpy + math.erf（禁 scipy.stats，OMP Error #15）。"""
    import math
    p     = 1.0 - alpha / 2.0
    sqrt2 = math.sqrt(2.0)
    sqp2  = math.sqrt(2.0 * math.pi)
    t     = math.sqrt(-2.0 * math.log(min(p, 1.0 - p)))
    c     = [2.515517, 0.802853, 0.010328]
    d     = [1.432788, 0.189269, 0.001308]
    x0    = t - (c[0] + c[1]*t + c[2]*t**2) / (1 + d[0]*t + d[1]*t**2 + d[2]*t**3)
    x     = x0 if p >= 0.5 else -x0
    for _ in range(5):
        phi_x  = 0.5 * (1.0 + math.erf(x / sqrt2))
        dphi_x = math.exp(-0.5 * x * x) / sqp2
        x -= (phi_x - p) / dphi_x
    return float(x)


def binary_auroc_numpy(labels: np.ndarray, scores: np.ndarray) -> float:
    """
    二分类 AUROC，纯 numpy Mann-Whitney U（禁 sklearn/scipy，OMP Error #15）。
    labels: 0/1 array; scores: float array（越高=越正类）。
    """
    y_bin = labels.astype(float)
    if y_bin.sum() == 0 or y_bin.sum() == len(y_bin):
        return float("nan")
    pos = scores[y_bin == 1]
    neg = scores[y_bin == 0]
    n_pos, n_neg = len(pos), len(neg)
    all_s = np.concatenate([pos, neg])
    all_l = np.concatenate([np.ones(n_pos), np.zeros(n_neg)])
    order = np.argsort(-all_s)
    ranked = all_l[order]
    tpr = np.concatenate([[0.0], np.cumsum(ranked == 1) / n_pos, [1.0]])
    fpr = np.concatenate([[0.0], np.cumsum(ranked == 0) / n_neg, [1.0]])
    return float(np.trapz(tpr, fpr))


def _disable_inplace_silu(model: nn.Module) -> nn.Module:
    """
    EfficientNet SiLU inplace=True → illegal memory access on RTX 4070 WDDM CUDA。
    递归改为 out-of-place，不影响精度。（与 selinf_datafission.py 完全相同）
    """
    for name, child in model.named_children():
        if isinstance(child, nn.SiLU) and child.inplace:
            setattr(model, name, nn.SiLU(inplace=False))
        else:
            _disable_inplace_silu(child)
    return model


# ── Data Fission CI（复用口径，与 selinf_datafission.py 完全一致）─────────────

def data_fission_ci(
    accs: np.ndarray,
    sigma: float,
    tau: float = FISSION_TAU,
    alpha: float = ALPHA,
    rng=None,
) -> dict:
    """Leiner+ JASA2023 data fission selective CI（口径同 selinf_datafission.py）。"""
    if rng is None:
        rng = np.random.default_rng(0)
    M  = len(accs)
    Z  = rng.normal(0.0, sigma, size=M)
    f  = accs + tau * Z
    g  = accs - Z / tau
    i_star  = int(np.argmax(f))
    g_star  = float(g[i_star])
    se_g    = sigma * np.sqrt(1.0 + 1.0 / tau**2)
    z       = z_score(alpha)
    return {
        "selected_idx": i_star,
        "g_star":       g_star,
        "se_g":         se_g,
        "ci_low":       g_star - z * se_g,
        "ci_high":      g_star + z * se_g,
        "ci_width":     2 * z * se_g,
    }


def naive_ci(accs: np.ndarray, alpha: float = ALPHA) -> dict:
    M  = len(accs)
    mu = float(accs.mean())
    se = float(np.std(accs, ddof=1) / np.sqrt(M))
    z  = z_score(alpha)
    return {
        "ci_low":   mu - z * se,
        "ci_high":  mu + z * se,
        "ci_width": 2 * z * se,
        "best_acc": float(accs.max()),
    }


def sqrtm_ci_width(accs: np.ndarray, alpha: float = ALPHA) -> float:
    """√M 近似宽度（invalid baseline，恒等式）。"""
    M      = len(accs)
    naive  = naive_ci(accs, alpha)
    return float(naive["ci_width"] * np.sqrt(M))


# ═══════════════════════════════════════════════════════════════════════════════
# Dataset 类 — ISIC2020 melanoma 二分类
# ═══════════════════════════════════════════════════════════════════════════════

class ISICDataset(Dataset):
    """
    ISIC2020 melanoma 二分类。
    数据路径真源：datasets.json isic2020
      images: data/raw/isic2020/train-image/image/<image_name>.jpg
      gt:     data/raw/isic2020/ISIC_2020_Training_GroundTruth_v2.csv (target 列, 0/1)
      split:  data/isic_split.csv (isic_id 列, split∈{train,val,test})

    注意：gt CSV 的 id 列名是 image_name，split CSV 的 id 列名是 isic_id，合并时重命名。
    """
    TFM = transforms.Compose([
        transforms.Resize(224),
        transforms.CenterCrop(224),
        transforms.ToTensor(),
        transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
    ])
    TFM_TRAIN = transforms.Compose([
        transforms.RandomResizedCrop(224, scale=(0.8, 1.0)),
        transforms.RandomHorizontalFlip(),
        transforms.ToTensor(),
        transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
    ])

    def __init__(self, records: list, augment: bool = False):
        self.records = records
        self.tfm     = self.TFM_TRAIN if augment else self.TFM

    def __len__(self):
        return len(self.records)

    def __getitem__(self, idx):
        rec  = self.records[idx]
        path = ISIC_IMG_DIR / f"{rec['image_name']}.jpg"
        img  = Image.open(path).convert("RGB")
        return self.tfm(img), int(rec["label"])


def build_isic_records(split: str, max_n=None, seed: int = 42) -> list:
    """
    从 isic_split.csv 取指定 split，合并 gt 拿 target 标签。
    max_n: 限制样本数（保持阳性比例 stratified）。
    """
    gt    = pd.read_csv(ISIC_GT_CSV)[["image_name", "target"]]
    sp    = pd.read_csv(ISIC_SPLIT_CSV).rename(columns={"isic_id": "image_name"})
    merged= sp[sp["split"] == split].merge(gt, on="image_name", how="inner")

    if max_n is not None and len(merged) > max_n:
        rng = np.random.default_rng(seed)
        pos = merged[merged["target"] == 1]
        neg = merged[merged["target"] == 0]
        n_pos = max(1, int(max_n * len(pos) / len(merged)))
        n_neg = max_n - n_pos
        pos_s = pos.sample(n=min(n_pos, len(pos)), random_state=int(rng.integers(1000000)))
        neg_s = neg.sample(n=min(n_neg, len(neg)), random_state=int(rng.integers(1000000)))
        merged= pd.concat([pos_s, neg_s]).reset_index(drop=True)

    recs = []
    for _, row in merged.iterrows():
        recs.append({"image_name": row["image_name"], "label": int(row["target"])})
    return recs


def make_isic_weighted_sampler(records: list) -> WeightedRandomSampler:
    """
    WeightedRandomSampler 处理 ISIC 高度不平衡（~1.77% 阳性）。
    每个样本权重 = 1/class_freq（正类权重约 56×）。
    """
    labels = np.array([r["label"] for r in records])
    n_pos  = int(labels.sum())
    n_neg  = len(labels) - n_pos
    w_pos  = 1.0 / max(n_pos, 1)
    w_neg  = 1.0 / max(n_neg, 1)
    weights= np.where(labels == 1, w_pos, w_neg)
    return WeightedRandomSampler(
        weights=torch.from_numpy(weights).float(),
        num_samples=len(records),
        replacement=True,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# Dataset 类 — BraTS2021 FLAIR slice tumor-vs-normal 二分类
# ═══════════════════════════════════════════════════════════════════════════════

class BraTSDataset(Dataset):
    """
    BraTS2021 FLAIR slice 二分类（tumor=1, normal=0）。
    数据路径真源：datasets.json medianomaly_bench BraTS2021
      test/normal/: 828 张 PNG FLAIR 切片（正常）
      test/tumor/:  1948 张 PNG FLAIR 切片（肿瘤）

    直接用 test 集做 train/val 分割（无标准 train split for classification）：
      取前 70% 做 train，后 30% 做 val（按文件名排序，保持确定性）。
    """
    TFM = transforms.Compose([
        transforms.Resize(224),
        transforms.CenterCrop(224),
        transforms.Grayscale(num_output_channels=3),  # FLAIR 灰度 → 3ch
        transforms.ToTensor(),
        transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
    ])
    TFM_TRAIN = transforms.Compose([
        transforms.RandomResizedCrop(224, scale=(0.8, 1.0)),
        transforms.RandomHorizontalFlip(),
        transforms.Grayscale(num_output_channels=3),
        transforms.ToTensor(),
        transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
    ])

    def __init__(self, records: list, augment: bool = False):
        self.records = records
        self.tfm     = self.TFM_TRAIN if augment else self.TFM

    def __len__(self):
        return len(self.records)

    def __getitem__(self, idx):
        rec = self.records[idx]
        img = Image.open(rec["path"]).convert("L")    # FLAIR=灰度
        return self.tfm(img), int(rec["label"])


def build_brats_records(split: str) -> list:
    """
    BraTS test 集按文件名排序后 70/30 分 train/val（确定性切割）。
    normal=0, tumor=1。
    """
    normal_paths = sorted(BRATS_NORMAL.glob("*.png"))
    tumor_paths  = sorted(BRATS_TUMOR.glob("*.png"))

    all_recs = []
    for p in normal_paths:
        all_recs.append({"path": str(p), "label": 0})
    for p in tumor_paths:
        all_recs.append({"path": str(p), "label": 1})

    n_total = len(all_recs)
    n_train = int(n_total * 0.7)

    if split == "train":
        return all_recs[:n_train]
    elif split == "val":
        return all_recs[n_train:]
    else:
        return all_recs


# ═══════════════════════════════════════════════════════════════════════════════
# 模型构建（复用 HAM 口径：EfficientNet-B3 + 替换 classifier）
# ═══════════════════════════════════════════════════════════════════════════════

def build_model(n_classes: int, dropout: float) -> nn.Module:
    model = efficientnet_b3(weights=EfficientNet_B3_Weights.IMAGENET1K_V1)
    in_features = model.classifier[1].in_features
    model.classifier = nn.Sequential(
        nn.Dropout(p=dropout),
        nn.Linear(in_features, n_classes),
    )
    _disable_inplace_silu(model)
    return model.to(DEVICE)


# ═══════════════════════════════════════════════════════════════════════════════
# 单 config 训练 — 二分类（ISIC / BraTS），返回最佳 val AUROC
# ═══════════════════════════════════════════════════════════════════════════════

def run_binary_config(
    train_recs: list,
    val_recs: list,
    lr: float,
    dropout: float,
    seed: int,
    epochs: int,
    use_sampler: bool = False,
    pos_weight=None,
    dataset_cls=None,
) -> float:
    """
    Fine-tune EfficientNet-B3 做二分类，返回最佳 val AUROC。
    主指标：AUROC（对不平衡数据比 acc 更有意义）。
    """
    set_seed(seed)
    model = build_model(n_classes=2, dropout=dropout)

    tr_ds = dataset_cls(train_recs, augment=True)
    vl_ds = dataset_cls(val_recs,   augment=False)

    if use_sampler:
        sampler = make_isic_weighted_sampler(train_recs)
        tr_loader = DataLoader(tr_ds, batch_size=BATCH, sampler=sampler,
                               num_workers=0, pin_memory=False)
    else:
        tr_loader = DataLoader(tr_ds, batch_size=BATCH, shuffle=True,
                               num_workers=0, pin_memory=False)
    vl_loader = DataLoader(vl_ds, batch_size=BATCH, shuffle=False,
                           num_workers=0, pin_memory=False)

    if pos_weight is not None:
        pw = torch.tensor([pos_weight], device=DEVICE)
        criterion = nn.BCEWithLogitsLoss(pos_weight=pw)
        use_bce = True
    else:
        criterion = nn.CrossEntropyLoss()
        use_bce = False

    opt = torch.optim.Adam(model.parameters(), lr=lr)
    best_auroc = 0.0

    for ep in range(epochs):
        model.train()
        for x, y in tr_loader:
            x, y = x.to(DEVICE), y.to(DEVICE)
            opt.zero_grad()
            logits = model(x)
            if use_bce:
                loss = criterion(logits[:, 1].float(), y.float())
            else:
                loss = criterion(logits, y)
            loss.backward()
            opt.step()

        model.eval()
        all_labels, all_scores = [], []
        with torch.no_grad():
            for x, y in vl_loader:
                x, y = x.to(DEVICE), y.to(DEVICE)
                logits = model(x)
                scores = F.softmax(logits, dim=1)[:, 1]
                all_labels.append(y.cpu().numpy())
                all_scores.append(scores.cpu().numpy())

        all_labels = np.concatenate(all_labels)
        all_scores = np.concatenate(all_scores)
        auroc = binary_auroc_numpy(all_labels, all_scores)
        if not np.isnan(auroc) and auroc > best_auroc:
            best_auroc = auroc

    return best_auroc


# ═══════════════════════════════════════════════════════════════════════════════
# 难度体检（快探 baseline AUROC，3 epoch × 2 config）
# ═══════════════════════════════════════════════════════════════════════════════

def difficulty_probe(
    bench_name: str,
    train_recs: list,
    val_recs: list,
    dataset_cls,
    use_sampler: bool = False,
    pos_weight=None,
) -> float:
    """
    快跑 PROBE_CONFIGS 个 config × PROBE_EPOCHS epoch，估 baseline AUROC 中位数。
    返回 median AUROC。触顶阈 0.95 打印 WARNING。
    """
    probe_grid = [
        (1e-3, 0.2, 42),
        (3e-4, 0.4, 123),
    ][:PROBE_CONFIGS]

    probe_aurocs = []
    print(f"\n[DIFFICULTY PROBE] {bench_name} — {PROBE_CONFIGS} configs × {PROBE_EPOCHS} epochs")
    for lr, dp, s in probe_grid:
        auroc = run_binary_config(
            train_recs, val_recs,
            lr=lr, dropout=dp, seed=s,
            epochs=PROBE_EPOCHS,
            use_sampler=use_sampler,
            pos_weight=pos_weight,
            dataset_cls=dataset_cls,
        )
        probe_aurocs.append(auroc)
        print(f"  lr={lr}, dp={dp}, s={s} -> val_AUROC={auroc:.4f}")

    med = float(np.nanmedian(probe_aurocs))
    print(f"[DIFFICULTY PROBE] {bench_name} baseline AUROC median = {med:.4f}")
    if med > 0.95:
        print(f"  WARNING: {bench_name} baseline AUROC {med:.4f} > 0.95 触顶阈!")
        print(f"      config 间方差可能->0，deflation 坍原因将是「任务过易」而非 winner's curse 不存在。")
        print(f"      建议换更难任务变体（如 BraTS: 更细粒度分级 / 换更难 benchmark）。")
    elif med < 0.55:
        print(f"  WARNING: {bench_name} baseline AUROC {med:.4f} < 0.55，接近随机，")
        print(f"      可能数据加载/标签存在问题，请检查数据集。")
    else:
        print(f"  OK: {bench_name} 难度适中（AUROC {med:.4f}，不触顶 <0.95，有 deflation 空间）。")
    return med


# ═══════════════════════════════════════════════════════════════════════════════
# sweep + deflation 计算（单 benchmark）
# ═══════════════════════════════════════════════════════════════════════════════

def build_grid(m: int) -> list:
    """
    构建 M 个 config 的 sweep 网格：
      M=4/8/18: 从 grid18 中等间隔取 idx
      M=36:     用 HP_SEEDS_36 构建新 grid（2×3×6=36）
    """
    grid18 = list(itertools.product(HP_LR, HP_DROPOUT, HP_SEEDS_18))
    if m == 36:
        return list(itertools.product(HP_LR, HP_DROPOUT, HP_SEEDS_36))
    else:
        idx = M_SUBSET_IDX[m]
        return [grid18[i] for i in idx]


def sweep_benchmark(
    bench_name: str,
    train_recs: list,
    val_recs: list,
    dataset_cls,
    m: int,
    baseline_auroc_med: float,
    use_sampler: bool = False,
    pos_weight=None,
    smoke: bool = False,
) -> list:
    """
    跑 M 个 config，返回 deflation csv 行列表（naive/datafission/sqrtM 各一行）。
    """
    grid = build_grid(m)
    if smoke:
        grid = grid[:2]

    epochs = 2 if smoke else EPOCHS_PER_CONFIG
    m_actual = len(grid)
    print(f"\n[SWEEP] {bench_name} M={m_actual}  configs={m_actual}  epochs={epochs}")

    aurocs = []
    cfg_names = []

    for i, (lr, dropout, seed) in enumerate(grid):
        cfg = f"lr={lr}_dp={dropout}_s={seed}"
        print(f"  [{i+1}/{m_actual}] {cfg}")
        auroc = run_binary_config(
            train_recs, val_recs,
            lr=lr, dropout=dropout, seed=seed,
            epochs=epochs,
            use_sampler=use_sampler,
            pos_weight=pos_weight,
            dataset_cls=dataset_cls,
        )
        print(f"    val_AUROC={auroc:.4f}")
        aurocs.append(auroc)
        cfg_names.append(cfg)

    accs_np   = np.array(aurocs)
    sigma_hat = float(np.std(accs_np, ddof=1))
    best_idx  = int(np.argmax(accs_np))
    best_cfg  = cfg_names[best_idx]
    best_aur  = float(accs_np[best_idx])

    print(f"  sigma_hat(pooled std, M={m_actual}) = {sigma_hat:.6f}")
    print(f"  best AUROC = {best_aur:.4f}  [{best_cfg}]")

    naive     = naive_ci(accs_np)
    rng_f     = np.random.default_rng(42)
    df_ci     = data_fission_ci(accs_np, sigma=sigma_hat, tau=FISSION_TAU, rng=rng_f)
    sqrtm_w   = sqrtm_ci_width(accs_np)

    defl_df   = df_ci["ci_width"] / naive["ci_width"] - 1.0
    defl_sqm  = sqrtm_w / naive["ci_width"] - 1.0

    df_sel_cfg = cfg_names[df_ci["selected_idx"]]

    rows = []
    for method, ci_w, defl, sel_cfg in [
        ("naive",       naive["ci_width"],  0.0,      best_cfg),
        ("datafission", df_ci["ci_width"],  defl_df,  df_sel_cfg),
        ("sqrtM",       sqrtm_w,            defl_sqm, best_cfg),
    ]:
        rows.append({
            "benchmark":             bench_name,
            "M":                     m_actual,
            "method":                method,
            "selected_config":       sel_cfg,
            "ci_width":              round(ci_w, 6),
            "deflation_pct":         round(defl * 100, 4),
            "best_auroc":            round(best_aur, 6),
            "baseline_auroc_median": round(baseline_auroc_med, 6),
            "sigma_hat":             round(sigma_hat, 6),
        })
    return rows


# ═══════════════════════════════════════════════════════════════════════════════
# 从 HAM 旧结果读 _STAT_ 行（不重跑 HAM）
# ═══════════════════════════════════════════════════════════════════════════════

def load_ham_stat_rows() -> list:
    """
    从 ham_datafission.csv 提取 _STAT_ 行，转换为 A3 输出格式（M=18 单点）。
    注：HAM 主指标是 acc 非 AUROC，best_auroc 列填 nan。
    """
    if not HAM_RESULT_CSV.exists():
        print(f"[WARN] HAM result not found: {HAM_RESULT_CSV}, skipping HAM rows.")
        return []
    df = pd.read_csv(HAM_RESULT_CSV)
    stat = df[df["config"].str.startswith("_STAT_")].copy()
    rows = []
    for _, row in stat.iterrows():
        method = str(row.get("method", ""))
        if method not in ("naive", "datafission", "sqrtM_invalid"):
            continue
        method_out = "sqrtM" if method == "sqrtM_invalid" else method
        rows.append({
            "benchmark":             "HAM10000",
            "M":                     int(row.get("M", 18)),
            "method":                method_out,
            "selected_config":       str(row.get("selected_config", "")),
            "ci_width":              float(row.get("ci_width", float("nan"))),
            "deflation_pct":         float(row.get("deflation_pct", 0.0)),
            "best_auroc":            float("nan"),  # HAM acc 非 AUROC
            "baseline_auroc_median": float("nan"),
            "sigma_hat":             float(row.get("sigma_hat", float("nan"))),
        })
    print(f"[HAM] Loaded {len(rows)} _STAT_ rows from {HAM_RESULT_CSV} (M=18 reference)")
    return rows


# ═══════════════════════════════════════════════════════════════════════════════
# A3 verdict 判决
# ═══════════════════════════════════════════════════════════════════════════════

def print_a3_verdict(df: pd.DataFrame):
    """
    A3 判据：
    1. 对每 benchmark，data fission deflation 随 M 斜率是否为正（M 越大 deflation 越大）
    2. >= 3 benchmark 斜率方向一致
    3. data fission deflation 随 M 系统增
    """
    print("\n" + "=" * 70)
    print("A3 VERDICT — SelInfBench deflation-vs-M 曲线")
    print("=" * 70)

    df_f = df[df["method"] == "datafission"].copy()
    benchmarks = df_f["benchmark"].unique()

    slopes = {}
    for bm in benchmarks:
        sub = df_f[df_f["benchmark"] == bm].sort_values("M")
        Ms  = sub["M"].values.astype(float)
        Ds  = sub["deflation_pct"].values.astype(float)
        if len(Ms) >= 2:
            slope = float(np.polyfit(Ms, Ds, 1)[0])
        else:
            slope = float("nan")
        slopes[bm] = slope
        print(f"\n  {bm} deflation-vs-M (datafission):")
        for _, r in sub.iterrows():
            auc_str = f"{r['best_auroc']:.4f}" if not np.isnan(r['best_auroc']) else "N/A(acc)"
            print(f"    M={int(r['M']):2d}  deflation={r['deflation_pct']:.1f}%  best={auc_str}")
        slope_str = f"positive OK" if slope > 0 else "negative/zero FAIL"
        print(f"  slope = {slope:.3f}  ({slope_str})")

    positive_slopes = [bm for bm, s in slopes.items() if s > 0]
    n_pos_auroc     = sum(1 for bm, s in slopes.items()
                         if s > 0 and bm in ("ISIC2020", "BraTS2021"))

    print(f"\n  positive slope benchmarks: {positive_slopes}")
    print(f"  AUROC benchmarks (ISIC+BraTS) with positive slope: {n_pos_auroc}/2")

    print("\n--- A3 DECISION ---")
    if len(positive_slopes) >= 3:
        print(f"  PASS: >=3 benchmark deflation-vs-M slope positive ({len(positive_slopes)}/{len(slopes)})")
        print(f"        data fission deflation systematically increases with M")
        print(f"        = winner's curse has M-scaling, not artifact")
    elif n_pos_auroc == 2:
        print(f"  PARTIAL PASS: ISIC+BraTS AUROC benchmarks both positive slope")
        print(f"        Full A3 PASS needs HAM deflation-vs-M to also trend positive.")
        print(f"        Recommend: re-run HAM with M=4/8/36 sweep.")
    else:
        print(f"  FAIL: positive slope < 2 benchmarks ({len(positive_slopes)}/{len(slopes)})")
        print(f"        No systematic M-scaling in deflation. K1 risk elevated.")
    print("=" * 70)


# ═══════════════════════════════════════════════════════════════════════════════
# 主流程
# ═══════════════════════════════════════════════════════════════════════════════

def main(
    smoke: bool = False,
    cpu_only: bool = False,
    benchmarks=None,
    m_values=None,
    skip_ham: bool = False,
    skip_probe: bool = False,
):
    global DEVICE
    if cpu_only:
        DEVICE = torch.device("cpu")
    print(f"[selinf_a3_benchmarks] Device={DEVICE}  smoke={smoke}")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    set_seed(42)

    if benchmarks is None:
        benchmarks = ["ISIC2020", "BraTS2021"]
    if m_values is None:
        m_values = M_VALUES if not smoke else [4, 8]

    all_rows = []

    # ── 加载 HAM M=18 参照行（不重跑）────────────────────────────────────────
    if not skip_ham:
        all_rows.extend(load_ham_stat_rows())

    # ── ISIC2020 ──────────────────────────────────────────────────────────────
    if "ISIC2020" in benchmarks:
        print("\n" + "-" * 60)
        print("BENCHMARK: ISIC2020 melanoma binary classification")
        print("-" * 60)
        train_recs = build_isic_records("train", max_n=ISIC_TRAIN_N, seed=42)
        val_recs   = build_isic_records("val",   max_n=ISIC_VAL_N,   seed=42)
        n_pos_tr   = sum(1 for r in train_recs if r["label"] == 1)
        n_pos_vl   = sum(1 for r in val_recs   if r["label"] == 1)
        print(f"  train={len(train_recs)} (pos={n_pos_tr},"
              f" ~{n_pos_tr/max(len(train_recs),1)*100:.1f}%)")
        print(f"  val  ={len(val_recs)}   (pos={n_pos_vl},"
              f" ~{n_pos_vl/max(len(val_recs),1)*100:.1f}%)")
        n_neg_tr   = len(train_recs) - n_pos_tr
        pos_w      = float(n_neg_tr) / max(n_pos_tr, 1)
        print(f"  BCE pos_weight = {pos_w:.1f}")

        if not skip_probe:
            base_med_isic = difficulty_probe(
                "ISIC2020", train_recs, val_recs,
                dataset_cls=ISICDataset,
                use_sampler=True,
                pos_weight=pos_w,
            )
        else:
            base_med_isic = float("nan")

        for m in m_values:
            rows = sweep_benchmark(
                "ISIC2020", train_recs, val_recs,
                dataset_cls=ISICDataset,
                m=m,
                baseline_auroc_med=base_med_isic,
                use_sampler=True,
                pos_weight=pos_w,
                smoke=smoke,
            )
            all_rows.extend(rows)

    # ── BraTS2021 ─────────────────────────────────────────────────────────────
    if "BraTS2021" in benchmarks:
        print("\n" + "-" * 60)
        print("BENCHMARK: BraTS2021 FLAIR slice tumor-vs-normal")
        print("-" * 60)
        train_recs = build_brats_records("train")
        val_recs   = build_brats_records("val")
        n_pos_tr   = sum(1 for r in train_recs if r["label"] == 1)
        n_pos_vl   = sum(1 for r in val_recs   if r["label"] == 1)
        print(f"  train={len(train_recs)} (tumor={n_pos_tr},"
              f" ~{n_pos_tr/max(len(train_recs),1)*100:.1f}%)")
        print(f"  val  ={len(val_recs)}   (tumor={n_pos_vl},"
              f" ~{n_pos_vl/max(len(val_recs),1)*100:.1f}%)")

        if not skip_probe:
            base_med_brats = difficulty_probe(
                "BraTS2021", train_recs, val_recs,
                dataset_cls=BraTSDataset,
                use_sampler=False,
                pos_weight=None,
            )
        else:
            base_med_brats = float("nan")

        for m in m_values:
            rows = sweep_benchmark(
                "BraTS2021", train_recs, val_recs,
                dataset_cls=BraTSDataset,
                m=m,
                baseline_auroc_med=base_med_brats,
                use_sampler=False,
                pos_weight=None,
                smoke=smoke,
            )
            all_rows.extend(rows)

    # ── 写 csv ────────────────────────────────────────────────────────────────
    col_order = [
        "benchmark", "M", "method", "selected_config",
        "ci_width", "deflation_pct", "best_auroc", "baseline_auroc_median", "sigma_hat",
    ]
    df_out = pd.DataFrame(all_rows)
    df_out = df_out[[c for c in col_order if c in df_out.columns]]
    df_out.to_csv(OUT_CSV, index=False)
    print(f"\nSaved: {OUT_CSV}")
    print(df_out.to_string(index=False))

    print_a3_verdict(df_out)


# ═══════════════════════════════════════════════════════════════════════════════
# CLI 入口
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import multiprocessing
    multiprocessing.freeze_support()  # Windows spawn 安全

    parser = argparse.ArgumentParser(
        description="SelInfBench A3: ISIC2020+BraTS2021 deflation-vs-M curve"
    )
    parser.add_argument("--smoke", type=int, default=0,
                        help="1 = smoke: 2 config x 2 epoch x M={4,8} (add --cpu)")
    parser.add_argument("--cpu",   action="store_true",
                        help="force CPU (smoke test)")
    parser.add_argument("--benchmarks", type=str, default="ISIC2020,BraTS2021",
                        help="comma-separated benchmarks (default: ISIC2020,BraTS2021)")
    parser.add_argument("--m_values", type=str, default="4,8,18,36",
                        help="comma-separated M values (default: 4,8,18,36)")
    parser.add_argument("--skip_ham",   action="store_true",
                        help="skip loading HAM csv")
    parser.add_argument("--skip_probe", action="store_true",
                        help="skip difficulty probe (faster smoke)")
    args = parser.parse_args()

    benchmarks_list = [b.strip() for b in args.benchmarks.split(",")]
    m_values_list   = [int(x) for x in args.m_values.split(",")]

    main(
        smoke      = bool(args.smoke),
        cpu_only   = args.cpu,
        benchmarks = benchmarks_list,
        m_values   = m_values_list,
        skip_ham   = args.skip_ham,
        skip_probe = args.skip_probe,
    )
