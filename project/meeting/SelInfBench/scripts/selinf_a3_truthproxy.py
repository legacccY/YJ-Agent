"""
selinf_a3_truthproxy.py — SelInfBench A3 test-as-truth winner's curse 验证
服务: SelInfBench (selinf) A3，lever = 真 benchmark 上 winner's curse 去偏证据
不启动训练外部进程；写完交主线跑。

# 核心协议（test-as-truth）
对每个 benchmark（HAM10000/ISIC2020/BraTS2021）：
  1. 三分 train/val/test（test = truth proxy，选择阶段绝不碰）
     - ISIC2020: 复用 isic_split.csv 现有 train/val/test 三分
       train=23188, val=3312, test=6626（按 patient-level split 已存在）
     - BraTS2021: 从 MedIAnomaly test 集（normal 175 cases + tumor 199 cases）
       按 case-level split → train 60% / val 20% / test 20%
       （BraTS2021 train/ 目录为无标签 normal-only，不含 tumor label，不用）
     - HAM10000: patient-level 三分（opt-in，需 --benchmarks HAM10000）
  2. M-config grid：M=18 为主（可 --m_values 指定；M=36 robustness 加做）
     绝不把「随 M」当 headline，headline = 去偏移位方向
  3. 每 config 在 train 训练，val 和 test 各评一次 AUROC
  4. 选 i* = argmax(val_AUROC)（选择阶段只看 val，不碰 test）
  5. 每 benchmark 输出：
     - val_best = val_AUROC[i*]
     - test_selected = test_AUROC[i*]（truth proxy 下的真泛化）
     - winners_curse = val_best − test_selected（>0 = 高估）
     - g_star = data fission 去偏点估计（复用 data_fission_ci，sigma=val AUROC pooled std）
     - debias_shift = val_best − g_star（data fission 校正幅度）
     - 方向验证：gstar_to_test_abs < naive_to_test_abs（g_star 比 val_best 更接近 test）

# A3 VERDICT 判据（02_ACCEPTANCE 真源）
PASS = >=3 benchmark 上：
  (a) winner's curse = val_best−test_selected 一致 > 0（系统高估）
  (b) debias_shift > 0（data fission 校正幅度正向）
  (c) gstar_to_test_abs < naive_to_test_abs（多数 benchmark 成立）
FAIL/弱信号 → 据实报，不强撑

# 输出
  results/a3_truthproxy.csv
  列: benchmark, M, val_best, test_selected, winners_curse,
      g_star, debias_shift, gstar_to_test_abs, naive_to_test_abs,
      sigma_hat, n_train, n_val, n_test

# Windows 规范
  num_workers=0, pin_memory=False, if __name__=='__main__',
  _disable_inplace_silu, cudnn.benchmark=False, 正斜杠, 种子固定
  multiprocessing_context 用不到（num_workers=0）

# 算力预算（供主线参考）
  M=18×3 benchmark × 15 epoch × ~2min/config (RTX4070 8GB)
  = 18 config × 3 bench × 15 ep ≈ 18×3×(~3min) ≈ 1.5 GPU·h
  + M=36 robustness ≈ ×2 → 总 ≤ 3 GPU·h
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
ISIC_IMG_DIR   = Path("D:/YJ-Agent/data/raw/isic2020/train-image/image")
ISIC_GT_CSV    = Path("D:/YJ-Agent/data/raw/isic2020/ISIC_2020_Training_GroundTruth_v2.csv")
ISIC_SPLIT_CSV = Path("D:/YJ-Agent/data/isic_split.csv")

# BraTS2021 MedIAnomaly 格式：test/normal + test/tumor（含有标签 slice）
BRATS_TEST     = Path("D:/YJ-Agent/project/meeting/MedAD-FailMap/data/BraTS2021/test")
BRATS_NORMAL   = BRATS_TEST / "normal"
BRATS_TUMOR    = BRATS_TEST / "tumor"

# HAM10000（可选，需 metadata）
HAM_IMG_DIRS = [
    Path("D:/YJ-Agent/data/external/ham10000/HAM10000_images_part_1"),
    Path("D:/YJ-Agent/data/external/ham10000/HAM10000_images_part_2"),
]
HAM_META_CSV = Path("D:/YJ-Agent/data/external/ham10000/HAM10000_metadata.csv")

OUT_DIR  = Path("D:/YJ-Agent/project/meeting/SelInfBench/results")
OUT_CSV  = OUT_DIR / "a3_truthproxy.csv"

# ── HP sweep 网格（与 a3_benchmarks.py 完全一致，跨集可比）──────────────────
HP_LR          = [1e-3, 3e-4]
HP_DROPOUT     = [0.2, 0.4, 0.6]
HP_SEEDS_18    = [42, 123, 2024]            # M=4/8/18 用
HP_SEEDS_36    = [42, 123, 2024, 7, 99, 314]  # M=36 扩 seed

M_SUBSET_IDX = {
    4:  [0, 5, 11, 17],
    8:  [0, 2, 4, 7, 9, 12, 14, 17],
    18: list(range(18)),
    36: None,   # 另建 grid（2×3×6=36）
}

BATCH               = 32
EPOCHS_PER_CONFIG   = 15
FISSION_TAU         = 1.0
ALPHA               = 0.05

# ISIC 样本数控制（保持阳性比例 stratified）
ISIC_TRAIN_N        = 2000
ISIC_VAL_N          = 600
ISIC_TEST_N         = 1000   # truth proxy 子集，保持 pos 比例

# BraTS case-level 三分比例（按 case 切，防 slice 泄漏）
BRATS_SPLIT_TRAIN   = 0.60   # 60% cases → train slices
BRATS_SPLIT_VAL     = 0.20   # 20% cases → val slices（选 i* 用）
# 余 20% cases → test slices（truth proxy）

# HAM 样本数控制
HAM_TRAIN_N  = 2000
HAM_VAL_N    = 600
HAM_TEST_N   = 600

DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")
torch.backends.cudnn.benchmark = False   # RTX4070 WDDM 兼容


# ═══════════════════════════════════════════════════════════════════════════════
# 工具函数（纯 numpy，禁 scipy.stats OMP Error #15）
# ═══════════════════════════════════════════════════════════════════════════════

def set_seed(s: int):
    random.seed(s)
    np.random.seed(s)
    torch.manual_seed(s)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(s)


def z_score(alpha: float) -> float:
    """N(0,1) upper alpha/2 quantile，纯 numpy+math.erf（禁 scipy.stats）。"""
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
    二分类 AUROC，纯 numpy Mann-Whitney U（禁 sklearn/scipy OMP Error #15）。
    labels: 0/1; scores: float（越高=越正类）。
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
    tpr = np.concatenate([[0.0], np.cumsum(ranked == 1) / n_pos])
    fpr = np.concatenate([[0.0], np.cumsum(ranked == 0) / n_neg])
    # trapz AUC（ascending fpr order）
    return float(np.trapz(tpr, fpr))


def _disable_inplace_silu(model: nn.Module) -> nn.Module:
    """
    EfficientNet SiLU inplace=True → RTX4070 WDDM CUDA illegal memory access。
    递归改为 out-of-place，不影响精度。
    """
    for name, child in model.named_children():
        if isinstance(child, nn.SiLU) and child.inplace:
            setattr(model, name, nn.SiLU(inplace=False))
        else:
            _disable_inplace_silu(child)
    return model


# ── Data Fission CI（Leiner+ JASA2023，口径同 selinf_datafission.py）─────────

def data_fission_ci(
    accs: np.ndarray,
    sigma: float,
    tau: float = FISSION_TAU,
    alpha: float = ALPHA,
    rng=None,
) -> dict:
    """
    Leiner+ JASA2023 data fission selective CI。
    f = accs + tau*Z（选择用），g = accs − Z/tau（推断用）。
    i* = argmax(f)，g_star = g[i*]，对 g_star 建标准 CI。
    """
    if rng is None:
        rng = np.random.default_rng(0)
    M      = len(accs)
    Z      = rng.normal(0.0, sigma, size=M)
    f      = accs + tau * Z
    g      = accs - Z / tau
    i_star = int(np.argmax(f))
    g_star = float(g[i_star])
    se_g   = sigma * np.sqrt(1.0 + 1.0 / tau**2)
    z      = z_score(alpha)
    return {
        "selected_idx": i_star,
        "g_star":       g_star,
        "se_g":         se_g,
        "ci_low":       g_star - z * se_g,
        "ci_high":      g_star + z * se_g,
        "ci_width":     2 * z * se_g,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# Dataset — ISIC2020 melanoma 二分类
# ═══════════════════════════════════════════════════════════════════════════════

class ISICDataset(Dataset):
    """
    ISIC2020 melanoma 二分类。
    图像: data/raw/isic2020/train-image/image/<image_name>.jpg
    GT:   data/raw/isic2020/ISIC_2020_Training_GroundTruth_v2.csv (target 0/1)
    Split: data/isic_split.csv (isic_id, split∈{train,val,test})
    test 分 = truth proxy，不在选择阶段碰。
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
    从 isic_split.csv 取指定 split，合并 GT 拿 target 标签。
    max_n: stratified 限制样本数（保阳性比例）。
    """
    gt     = pd.read_csv(ISIC_GT_CSV)[["image_name", "target"]]
    sp     = pd.read_csv(ISIC_SPLIT_CSV).rename(columns={"isic_id": "image_name"})
    merged = sp[sp["split"] == split].merge(gt, on="image_name", how="inner")

    if max_n is not None and len(merged) > max_n:
        rng   = np.random.default_rng(seed)
        pos   = merged[merged["target"] == 1]
        neg   = merged[merged["target"] == 0]
        n_pos = max(1, int(max_n * len(pos) / len(merged)))
        n_neg = max_n - n_pos
        pos_s = pos.sample(n=min(n_pos, len(pos)),
                           random_state=int(rng.integers(1_000_000)))
        neg_s = neg.sample(n=min(n_neg, len(neg)),
                           random_state=int(rng.integers(1_000_000)))
        merged = pd.concat([pos_s, neg_s]).reset_index(drop=True)

    return [{"image_name": row["image_name"], "label": int(row["target"])}
            for _, row in merged.iterrows()]


def make_weighted_sampler(records: list) -> WeightedRandomSampler:
    """不平衡二分类 → WeightedRandomSampler 每 epoch 均衡采样。"""
    labels  = np.array([r["label"] for r in records])
    n_pos   = int(labels.sum())
    n_neg   = len(labels) - n_pos
    w_pos   = 1.0 / max(n_pos, 1)
    w_neg   = 1.0 / max(n_neg, 1)
    weights = np.where(labels == 1, w_pos, w_neg)
    return WeightedRandomSampler(
        weights=torch.from_numpy(weights).float(),
        num_samples=len(records),
        replacement=True,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# Dataset — BraTS2021 FLAIR slice tumor-vs-normal 二分类
# ═══════════════════════════════════════════════════════════════════════════════

class BraTSDataset(Dataset):
    """
    BraTS2021 FLAIR slice 二分类（tumor=1, normal=0）。
    数据来自 MedIAnomaly test 集：
      test/normal/ 828 slices（175 cases）
      test/tumor/  1948 slices（199 cases）
    按 case-level split（文件名 BraTS2021_<case_id>_flair_<slice>.png）
    防止同一 case 的 slice 出现在不同 partition（防泄漏）。
    """
    TFM = transforms.Compose([
        transforms.Resize(224),
        transforms.CenterCrop(224),
        transforms.Grayscale(num_output_channels=3),   # FLAIR 灰度 → 3ch
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
        img = Image.open(rec["path"]).convert("L")   # FLAIR 灰度
        return self.tfm(img), int(rec["label"])


def build_brats_case_split(seed: int = 42) -> dict:
    """
    Case-level train/val/test 三分（防 slice 泄漏）。
    文件名格式：BraTS2021_<case_id>_flair_<slice>.png
    返回 {"train": [...], "val": [...], "test": [...]}

    策略：
      1. 提取所有 case_id（normal + tumor 分别独立 shuffle+split）
      2. normal case: 60/20/20
      3. tumor case:  60/20/20
      4. 按 case_id 映射回 slice 记录
    """
    normal_paths = sorted(BRATS_NORMAL.glob("*.png"))
    tumor_paths  = sorted(BRATS_TUMOR.glob("*.png"))

    def extract_case_id(p: Path) -> str:
        return p.stem.split("_")[1]   # BraTS2021_01467_flair_13 -> "01467"

    # 分组
    normal_by_case: dict = {}
    for p in normal_paths:
        cid = extract_case_id(p)
        normal_by_case.setdefault(cid, []).append(p)

    tumor_by_case: dict = {}
    for p in tumor_paths:
        cid = extract_case_id(p)
        tumor_by_case.setdefault(cid, []).append(p)

    rng = np.random.default_rng(seed)

    def split_cases(cases_dict: dict, label: int) -> dict:
        case_ids  = sorted(cases_dict.keys())
        shuffled  = rng.permutation(case_ids).tolist()
        n         = len(shuffled)
        n_train   = int(n * BRATS_SPLIT_TRAIN)
        n_val     = int(n * BRATS_SPLIT_VAL)
        train_ids = set(shuffled[:n_train])
        val_ids   = set(shuffled[n_train:n_train + n_val])
        # test = 余下 case
        result    = {"train": [], "val": [], "test": []}
        for cid, paths in cases_dict.items():
            for p in paths:
                rec = {"path": str(p), "label": label, "case_id": cid}
                if cid in train_ids:
                    result["train"].append(rec)
                elif cid in val_ids:
                    result["val"].append(rec)
                else:
                    result["test"].append(rec)
        return result

    normal_split = split_cases(normal_by_case, label=0)
    tumor_split  = split_cases(tumor_by_case,  label=1)

    combined: dict = {}
    for sp in ("train", "val", "test"):
        combined[sp] = normal_split[sp] + tumor_split[sp]

    return combined


# ═══════════════════════════════════════════════════════════════════════════════
# Dataset — HAM10000 melanoma 二分类（可选）
# ═══════════════════════════════════════════════════════════════════════════════

class HAMDataset(Dataset):
    """HAM10000 melanoma 二分类（mel=1, 其他=0）。"""
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
        rec = self.records[idx]
        img = Image.open(rec["path"]).convert("RGB")
        return self.tfm(img), int(rec["label"])


def build_ham_records_threeway(seed: int = 42):
    """
    HAM10000 patient-level 三分 train/val/test。
    binary: mel=1, 其余=0。
    返回 {"train":[], "val":[], "test":[], "pos_weight": float} 或 None（数据不存在）。
    """
    if not HAM_META_CSV.exists():
        print(f"[WARN] HAM metadata not found: {HAM_META_CSV}")
        print("       Skipping HAM10000. Use --benchmarks ISIC2020,BraTS2021")
        return None

    # 构建 image_id → path 查找表（两个 part 目录）
    id_to_path: dict = {}
    for img_dir in HAM_IMG_DIRS:
        if img_dir.exists():
            for p in img_dir.glob("*.jpg"):
                id_to_path[p.stem] = p

    meta = pd.read_csv(HAM_META_CSV)
    required = {"image_id", "dx"}
    if not required.issubset(set(meta.columns)):
        print(f"[WARN] HAM metadata missing columns, skipping")
        return None

    meta["label"] = (meta["dx"] == "mel").astype(int)

    # patient-level（若有 patient_id 按 patient，否则按 lesion_id 近似）
    id_col = "patient_id" if "patient_id" in meta.columns else "lesion_id"
    patients = sorted(meta[id_col].unique())
    rng      = np.random.default_rng(seed)
    shuffled = rng.permutation(patients).tolist()
    n        = len(shuffled)
    n_train  = int(n * 0.60)
    n_val    = int(n * 0.20)

    train_pats = set(shuffled[:n_train])
    val_pats   = set(shuffled[n_train:n_train + n_val])
    test_pats  = set(shuffled[n_train + n_val:])

    def make_recs(pat_set, max_n=None, seed_offset=0):
        sub  = meta[meta[id_col].isin(pat_set)].copy()
        recs = []
        for _, row in sub.iterrows():
            iid = str(row["image_id"])
            if iid not in id_to_path:
                continue
            recs.append({"path": str(id_to_path[iid]), "label": int(row["label"])})
        if max_n is not None and len(recs) > max_n:
            rng2  = np.random.default_rng(seed + seed_offset)
            pos   = [r for r in recs if r["label"] == 1]
            neg   = [r for r in recs if r["label"] == 0]
            n_pos = max(1, int(max_n * len(pos) / len(recs)))
            n_neg = max_n - n_pos
            pos_s = [pos[i] for i in rng2.choice(len(pos), min(n_pos, len(pos)), replace=False)]
            neg_s = [neg[i] for i in rng2.choice(len(neg), min(n_neg, len(neg)), replace=False)]
            recs  = pos_s + neg_s
        return recs

    train_recs = make_recs(train_pats, HAM_TRAIN_N, 0)
    val_recs   = make_recs(val_pats,   HAM_VAL_N,   1)
    test_recs  = make_recs(test_pats,  HAM_TEST_N,  2)

    n_pos_tr   = sum(r["label"] for r in train_recs)
    n_neg_tr   = len(train_recs) - n_pos_tr
    pos_weight = float(n_neg_tr) / max(n_pos_tr, 1)

    print(f"[HAM] train={len(train_recs)} (mel={n_pos_tr}, pos_w={pos_weight:.1f})"
          f"  val={len(val_recs)}  test={len(test_recs)}")
    return {"train": train_recs, "val": val_recs, "test": test_recs,
            "pos_weight": pos_weight}


# ═══════════════════════════════════════════════════════════════════════════════
# 模型（EfficientNet-B3，口径同 a3_benchmarks.py + selinf_datafission.py）
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
# 单 config 训练 → 返回 (best_val_auroc, test_auroc_at_best_val)
# test 仅在最佳 val epoch 的模型状态下评一次，绝不用于选 epoch/选 config
# ═══════════════════════════════════════════════════════════════════════════════

def run_config_val_test(
    train_recs:           list,
    val_recs:             list,
    test_recs:            list,
    lr:                   float,
    dropout:              float,
    seed:                 int,
    epochs:               int,
    dataset_cls,
    use_weighted_sampler: bool  = False,
    pos_weight            = None,
) -> tuple:
    """
    Fine-tune EfficientNet-B3 二分类。
    - 训练: train_recs
    - 每 epoch 后: val AUROC（用于选 best epoch + 选 i*）
    - 训练结束: 用 best val 模型评 test AUROC（truth proxy，不参与任何选择）
    返回 (best_val_auroc, test_auroc_at_best_val)。
    """
    set_seed(seed)
    model = build_model(n_classes=2, dropout=dropout)

    tr_ds = dataset_cls(train_recs, augment=True)
    vl_ds = dataset_cls(val_recs,   augment=False)
    te_ds = dataset_cls(test_recs,  augment=False)

    if use_weighted_sampler:
        sampler   = make_weighted_sampler(train_recs)
        tr_loader = DataLoader(tr_ds, batch_size=BATCH, sampler=sampler,
                               num_workers=0, pin_memory=False)
    else:
        tr_loader = DataLoader(tr_ds, batch_size=BATCH, shuffle=True,
                               num_workers=0, pin_memory=False)

    vl_loader = DataLoader(vl_ds, batch_size=BATCH, shuffle=False,
                           num_workers=0, pin_memory=False)
    te_loader = DataLoader(te_ds, batch_size=BATCH, shuffle=False,
                           num_workers=0, pin_memory=False)

    if pos_weight is not None:
        pw        = torch.tensor([pos_weight], device=DEVICE)
        criterion = nn.BCEWithLogitsLoss(pos_weight=pw)
        use_bce   = True
    else:
        criterion = nn.CrossEntropyLoss()
        use_bce   = False

    opt            = torch.optim.Adam(model.parameters(), lr=lr)
    best_val_auroc = 0.0
    best_state     = None

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
                x = x.to(DEVICE)
                logits = model(x)
                scores = F.softmax(logits, dim=1)[:, 1]
                all_labels.append(y.numpy())
                all_scores.append(scores.cpu().numpy())
        val_labels = np.concatenate(all_labels)
        val_scores = np.concatenate(all_scores)
        val_auroc  = binary_auroc_numpy(val_labels, val_scores)

        if not np.isnan(val_auroc) and val_auroc > best_val_auroc:
            best_val_auroc = val_auroc
            # 保存 best val 模型 state（CPU clone 节省显存）
            best_state = {k: v.cpu().clone() for k, v in model.state_dict().items()}

    # test 评一次（truth proxy）
    if best_state is not None:
        model.load_state_dict({k: v.to(DEVICE) for k, v in best_state.items()})
    model.eval()
    all_labels_te, all_scores_te = [], []
    with torch.no_grad():
        for x, y in te_loader:
            x = x.to(DEVICE)
            logits = model(x)
            scores = F.softmax(logits, dim=1)[:, 1]
            all_labels_te.append(y.numpy())
            all_scores_te.append(scores.cpu().numpy())
    te_labels  = np.concatenate(all_labels_te)
    te_scores  = np.concatenate(all_scores_te)
    test_auroc = binary_auroc_numpy(te_labels, te_scores)

    return float(best_val_auroc), float(test_auroc)


# ═══════════════════════════════════════════════════════════════════════════════
# 难度体检（val AUROC 快探）
# ═══════════════════════════════════════════════════════════════════════════════

def difficulty_probe(
    bench_name:           str,
    train_recs:           list,
    val_recs:             list,
    test_recs:            list,
    dataset_cls,
    use_weighted_sampler: bool = False,
    pos_weight                 = None,
    n_probe_epochs:       int  = 3,
) -> float:
    """
    快探 2 config × 3 epoch，估 val AUROC 中位数。
    >0.95 = 触顶 WARNING。返回 median val AUROC。
    """
    probe_grid = [(1e-3, 0.2, 42), (3e-4, 0.4, 123)]
    aurocs = []
    print(f"\n[DIFFICULTY PROBE] {bench_name} 2 config × {n_probe_epochs} epoch")
    for lr, dp, s in probe_grid:
        va, _ = run_config_val_test(
            train_recs, val_recs, test_recs,
            lr=lr, dropout=dp, seed=s,
            epochs=n_probe_epochs,
            dataset_cls=dataset_cls,
            use_weighted_sampler=use_weighted_sampler,
            pos_weight=pos_weight,
        )
        aurocs.append(va)
        print(f"  lr={lr} dp={dp} s={s} -> val_AUROC={va:.4f}")

    med = float(np.nanmedian(aurocs))
    print(f"[DIFFICULTY PROBE] {bench_name} baseline val_AUROC median={med:.4f}")
    if med > 0.95:
        print(f"  WARNING: {bench_name} AUROC > 0.95 触顶！config 间方差可能→0，"
              f"winner's curse 信号坍塌（任务过易），建议换更难变体。")
    elif med < 0.55:
        print(f"  WARNING: {bench_name} AUROC < 0.55，接近随机，检查数据加载/标签。")
    else:
        print(f"  OK: {bench_name} 难度适中 (AUROC={med:.4f}，有 winner's curse 空间)。")
    return med


# ═══════════════════════════════════════════════════════════════════════════════
# build_grid（复用 a3_benchmarks.py 口径）
# ═══════════════════════════════════════════════════════════════════════════════

def build_grid(m: int) -> list:
    grid18 = list(itertools.product(HP_LR, HP_DROPOUT, HP_SEEDS_18))
    if m == 36:
        return list(itertools.product(HP_LR, HP_DROPOUT, HP_SEEDS_36))
    return [grid18[i] for i in M_SUBSET_IDX[m]]


# ═══════════════════════════════════════════════════════════════════════════════
# 单 benchmark sweep → 返回一行 a3_truthproxy.csv
# ═══════════════════════════════════════════════════════════════════════════════

def sweep_benchmark_truthproxy(
    bench_name:           str,
    train_recs:           list,
    val_recs:             list,
    test_recs:            list,
    dataset_cls,
    m:                    int,
    baseline_med:         float,
    use_weighted_sampler: bool  = False,
    pos_weight                  = None,
    smoke:                bool  = False,
) -> dict:
    """
    跑 M-config sweep。选择/sigma 只用 val；test 仅在 i* 选定后评一次。
    返回一行 dict（对应 a3_truthproxy.csv 一行）。
    """
    grid    = build_grid(m)
    if smoke:
        grid = grid[:2]

    epochs   = 2 if smoke else EPOCHS_PER_CONFIG
    m_actual = len(grid)
    print(f"\n[SWEEP] {bench_name} M={m_actual} epochs={epochs}")

    val_aurocs  = []
    test_aurocs = []
    cfg_names   = []

    for i, (lr, dropout, seed) in enumerate(grid):
        cfg = f"lr={lr}_dp={dropout}_s={seed}"
        print(f"  [{i+1}/{m_actual}] {cfg}")
        va, te = run_config_val_test(
            train_recs, val_recs, test_recs,
            lr=lr, dropout=dropout, seed=seed,
            epochs=epochs,
            dataset_cls=dataset_cls,
            use_weighted_sampler=use_weighted_sampler,
            pos_weight=pos_weight,
        )
        print(f"    val_AUROC={va:.4f}  test_AUROC={te:.4f}")
        val_aurocs.append(va)
        test_aurocs.append(te)
        cfg_names.append(cfg)

    val_arr  = np.array(val_aurocs)
    test_arr = np.array(test_aurocs)

    # i* = argmax(val)，选择阶段不看 test
    i_star        = int(np.argmax(val_arr))
    val_best      = float(val_arr[i_star])
    test_selected = float(test_arr[i_star])

    sigma_hat     = float(np.std(val_arr, ddof=1))

    # winner's curse = val_best − test_selected（>0 = 高估）
    winners_curse = val_best - test_selected

    # data fission 去偏点估计（sigma = val AUROC pooled std）
    rng_f  = np.random.default_rng(42)
    df_res = data_fission_ci(val_arr, sigma=sigma_hat, tau=FISSION_TAU, rng=rng_f)
    g_star = df_res["g_star"]

    # debias_shift = val_best − g_star（data fission 校正幅度，>0 = 向下校正）
    debias_shift = val_best - g_star

    # 方向验证：g* 是否比 val_best 更接近 test（真泛化估计改善了多少）
    naive_to_test_abs  = abs(val_best - test_selected)
    gstar_to_test_abs  = abs(g_star   - test_selected)
    closer = gstar_to_test_abs < naive_to_test_abs

    print(f"\n  [RESULT] {bench_name} M={m_actual}")
    print(f"    val_best={val_best:.4f}  test_selected={test_selected:.4f}")
    print(f"    winners_curse={winners_curse:+.4f}  "
          f"{'HIGH_ESTIMATE' if winners_curse > 0 else 'NO_INFLATION'}")
    print(f"    g_star={g_star:.4f}  debias_shift={debias_shift:+.4f}")
    print(f"    naive_to_test={naive_to_test_abs:.4f}  "
          f"gstar_to_test={gstar_to_test_abs:.4f}  "
          f"{'g* closer OK' if closer else 'g* NOT closer FAIL'}")
    print(f"    sigma_hat={sigma_hat:.6f}  selected={cfg_names[i_star]}")

    return {
        "benchmark":         bench_name,
        "M":                 m_actual,
        "val_best":          round(val_best,         6),
        "test_selected":     round(test_selected,    6),
        "winners_curse":     round(winners_curse,    6),
        "g_star":            round(g_star,           6),
        "debias_shift":      round(debias_shift,     6),
        "gstar_to_test_abs": round(gstar_to_test_abs, 6),
        "naive_to_test_abs": round(naive_to_test_abs, 6),
        "sigma_hat":         round(sigma_hat,        6),
        "n_train":           len(train_recs),
        "n_val":             len(val_recs),
        "n_test":            len(test_recs),
        "baseline_val_med":  round(baseline_med,     6),
        "selected_config":   cfg_names[i_star],
    }


# ═══════════════════════════════════════════════════════════════════════════════
# A3 VERDICT（02_ACCEPTANCE 判据真源）
# ═══════════════════════════════════════════════════════════════════════════════

def print_a3_verdict(df: pd.DataFrame):
    """
    A3 PASS 条件（02_ACCEPTANCE）：
    >=3 benchmark（M=18 主参考行）上：
      (a) winner's curse > 0（系统高估）
      (b) debias_shift > 0（data fission 校正方向正确）
      (c) gstar_to_test_abs < naive_to_test_abs（g* 比 val_best 更接近 test，多数 bench 成立）
    """
    print("\n" + "=" * 70)
    print("A3 VERDICT — test-as-truth winner's curse 验证")
    print("  判据来源：02_ACCEPTANCE A3（去偏移位方向 + truth proxy 方向一致）")
    print("=" * 70)

    benchmarks   = df["benchmark"].unique()
    n_pass_wc    = 0   # winner's curse > 0
    n_pass_shift = 0   # debias_shift > 0
    n_pass_dir   = 0   # gstar_to_test < naive_to_test

    for bm in benchmarks:
        rows = df[df["benchmark"] == bm]
        for _, r in rows.iterrows():
            wc    = r["winners_curse"]
            shift = r["debias_shift"]
            n2t   = r["naive_to_test_abs"]
            g2t   = r["gstar_to_test_abs"]
            print(f"\n  {bm} M={int(r['M'])}:")
            print(f"    val_best={r['val_best']:.4f}  "
                  f"test_selected={r['test_selected']:.4f}")
            print(f"    winners_curse={wc:+.4f}  "
                  f"{'OK >0' if wc > 0 else 'FAIL <=0'}")
            print(f"    debias_shift(val-g*)={shift:+.4f}  "
                  f"{'OK >0' if shift > 0 else 'FAIL <=0'}")
            print(f"    naive→test={n2t:.4f}  g*→test={g2t:.4f}  "
                  f"{'g* closer OK' if g2t < n2t else 'g* NOT closer'}")
            print(f"    g_star={r['g_star']:.4f}  sigma={r['sigma_hat']:.6f}")

        # 用 M=18 行计票
        if 18 in rows["M"].values:
            ref = rows[rows["M"] == 18].iloc[0]
        else:
            ref = rows.sort_values("M").iloc[-1]
        if ref["winners_curse"] > 0:
            n_pass_wc += 1
        if ref["debias_shift"] > 0:
            n_pass_shift += 1
        if ref["gstar_to_test_abs"] < ref["naive_to_test_abs"]:
            n_pass_dir += 1

    n_bench = len(benchmarks)
    print(f"\n--- SUMMARY ({n_bench} benchmarks, M=18 rows) ---")
    print(f"  winners_curse > 0:           {n_pass_wc}/{n_bench}")
    print(f"  debias_shift > 0:            {n_pass_shift}/{n_bench}")
    print(f"  g* closer to test:           {n_pass_dir}/{n_bench}")

    if n_pass_wc >= 3 and n_pass_shift >= 2 and n_pass_dir >= 2:
        print("\n  A3 PASS")
        print(f"    >= 3 benchmark winner's curse > 0 ({n_pass_wc}/{n_bench})")
        print(f"    >= 2 benchmark debias_shift > 0 ({n_pass_shift}/{n_bench})")
        print(f"    >= 2 benchmark g* closer to test ({n_pass_dir}/{n_bench})")
        print("    data fission 去偏方向一致正确。")
    elif n_pass_wc >= 2 and n_pass_shift >= 2:
        print("\n  A3 PARTIAL")
        print(f"    {n_pass_wc}/{n_bench} winner's curse > 0（需 >=3）")
        print(f"    {n_pass_shift}/{n_bench} debias_shift > 0")
        print("    满足 TMLR 退路档；顶会线需再增 1 个 benchmark。")
    else:
        print("\n  A3 FAIL / 弱信号")
        print(f"    winner's curse > 0: {n_pass_wc}/{n_bench}（需 >=3）")
        print(f"    debias_shift > 0:   {n_pass_shift}/{n_bench}（需 >=2）")
        print("    去偏方向不一致或 winner's curse 不存在，据实报，不强撑。")
        print("    建议：核查数据切分/难度/sigma；或触发 K1 降格。")
    print("=" * 70)


# ═══════════════════════════════════════════════════════════════════════════════
# 主流程
# ═══════════════════════════════════════════════════════════════════════════════

def main(
    smoke:      bool = False,
    cpu_only:   bool = False,
    benchmarks: list = None,
    m_values:   list = None,
    skip_probe: bool = False,
    brats_seed: int  = 42,
):
    global DEVICE
    if cpu_only:
        DEVICE = torch.device("cpu")
    print(f"[selinf_a3_truthproxy] Device={DEVICE}  smoke={smoke}")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    set_seed(42)

    if benchmarks is None:
        benchmarks = ["ISIC2020", "BraTS2021"]
    if m_values is None:
        m_values = [18]

    all_rows = []

    # ── ISIC2020 ──────────────────────────────────────────────────────────────
    if "ISIC2020" in benchmarks:
        print("\n" + "-" * 60)
        print("BENCHMARK: ISIC2020 (truth proxy = isic_split.csv test split)")
        print("-" * 60)
        train_recs = build_isic_records("train", max_n=ISIC_TRAIN_N, seed=42)
        val_recs   = build_isic_records("val",   max_n=ISIC_VAL_N,   seed=42)
        test_recs  = build_isic_records("test",  max_n=ISIC_TEST_N,  seed=42)
        n_pos_tr   = sum(r["label"] for r in train_recs)
        n_pos_vl   = sum(r["label"] for r in val_recs)
        n_pos_te   = sum(r["label"] for r in test_recs)
        n_neg_tr   = len(train_recs) - n_pos_tr
        pos_w      = float(n_neg_tr) / max(n_pos_tr, 1)
        print(f"  train={len(train_recs)} (mel={n_pos_tr}, "
              f"~{n_pos_tr/len(train_recs)*100:.1f}%)")
        print(f"  val  ={len(val_recs)}   (mel={n_pos_vl})")
        print(f"  test ={len(test_recs)}  (mel={n_pos_te})  [truth proxy]")
        print(f"  BCE pos_weight={pos_w:.1f}")

        base_med = float("nan")
        if not skip_probe:
            base_med = difficulty_probe(
                "ISIC2020", train_recs, val_recs, test_recs,
                dataset_cls=ISICDataset,
                use_weighted_sampler=True,
                pos_weight=pos_w,
            )

        for m in m_values:
            row = sweep_benchmark_truthproxy(
                "ISIC2020", train_recs, val_recs, test_recs,
                dataset_cls=ISICDataset,
                m=m, baseline_med=base_med,
                use_weighted_sampler=True,
                pos_weight=pos_w,
                smoke=smoke,
            )
            all_rows.append(row)

    # ── BraTS2021 ─────────────────────────────────────────────────────────────
    if "BraTS2021" in benchmarks:
        print("\n" + "-" * 60)
        print("BENCHMARK: BraTS2021 (case-level truth proxy split)")
        print("-" * 60)
        brats_split = build_brats_case_split(seed=brats_seed)
        train_recs  = brats_split["train"]
        val_recs    = brats_split["val"]
        test_recs   = brats_split["test"]
        n_tr_pos    = sum(r["label"] for r in train_recs)
        n_vl_pos    = sum(r["label"] for r in val_recs)
        n_te_pos    = sum(r["label"] for r in test_recs)
        print(f"  train={len(train_recs)} (tumor={n_tr_pos}, "
              f"~{n_tr_pos/len(train_recs)*100:.1f}%)")
        print(f"  val  ={len(val_recs)}   (tumor={n_vl_pos})")
        print(f"  test ={len(test_recs)}  (tumor={n_te_pos})  [truth proxy]")
        print(f"  case-level split seed={brats_seed}")

        base_med = float("nan")
        if not skip_probe:
            base_med = difficulty_probe(
                "BraTS2021", train_recs, val_recs, test_recs,
                dataset_cls=BraTSDataset,
                use_weighted_sampler=False,
                pos_weight=None,
            )

        for m in m_values:
            row = sweep_benchmark_truthproxy(
                "BraTS2021", train_recs, val_recs, test_recs,
                dataset_cls=BraTSDataset,
                m=m, baseline_med=base_med,
                use_weighted_sampler=False,
                pos_weight=None,
                smoke=smoke,
            )
            all_rows.append(row)

    # ── HAM10000（可选，需 metadata）─────────────────────────────────────────
    if "HAM10000" in benchmarks:
        print("\n" + "-" * 60)
        print("BENCHMARK: HAM10000 (patient-level truth proxy split)")
        print("-" * 60)
        ham_data = build_ham_records_threeway(seed=42)
        if ham_data is not None:
            train_recs = ham_data["train"]
            val_recs   = ham_data["val"]
            test_recs  = ham_data["test"]
            pos_w      = ham_data["pos_weight"]

            base_med = float("nan")
            if not skip_probe:
                base_med = difficulty_probe(
                    "HAM10000", train_recs, val_recs, test_recs,
                    dataset_cls=HAMDataset,
                    use_weighted_sampler=True,
                    pos_weight=pos_w,
                )

            for m in m_values:
                row = sweep_benchmark_truthproxy(
                    "HAM10000", train_recs, val_recs, test_recs,
                    dataset_cls=HAMDataset,
                    m=m, baseline_med=base_med,
                    use_weighted_sampler=True,
                    pos_weight=pos_w,
                    smoke=smoke,
                )
                all_rows.append(row)
        else:
            print("  [SKIP] HAM10000 skipped (metadata not found).")

    if not all_rows:
        print("[ERROR] No rows generated. Check --benchmarks and data paths.")
        sys.exit(1)

    # ── 写 CSV ────────────────────────────────────────────────────────────────
    col_order = [
        "benchmark", "M",
        "val_best", "test_selected", "winners_curse",
        "g_star", "debias_shift",
        "gstar_to_test_abs", "naive_to_test_abs",
        "sigma_hat", "n_train", "n_val", "n_test",
        "baseline_val_med", "selected_config",
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
    multiprocessing.freeze_support()   # Windows spawn 安全

    parser = argparse.ArgumentParser(
        description="SelInfBench A3: test-as-truth winner's curse 验证"
    )
    parser.add_argument(
        "--smoke", type=int, default=0,
        help="1 = smoke: 2 config × 2 epoch，加 --cpu 做 CPU dry-run",
    )
    parser.add_argument(
        "--cpu", action="store_true",
        help="force CPU (smoke test)",
    )
    parser.add_argument(
        "--benchmarks", type=str, default="ISIC2020,BraTS2021",
        help="逗号分隔，可选: ISIC2020,BraTS2021,HAM10000 (default: ISIC2020,BraTS2021)",
    )
    parser.add_argument(
        "--m_values", type=str, default="18",
        help="逗号分隔 M 值，主 M=18，加 36 做 robustness (default: 18)",
    )
    parser.add_argument(
        "--skip_probe", action="store_true",
        help="跳过难度体检（smoke 时可加快）",
    )
    parser.add_argument(
        "--brats_seed", type=int, default=42,
        help="BraTS case-level split seed (default: 42)",
    )
    args = parser.parse_args()

    benchmarks_list = [b.strip() for b in args.benchmarks.split(",")]
    m_values_list   = [int(x)    for x in args.m_values.split(",")]

    main(
        smoke      = bool(args.smoke),
        cpu_only   = args.cpu,
        benchmarks = benchmarks_list,
        m_values   = m_values_list,
        skip_probe = args.skip_probe,
        brats_seed = args.brats_seed,
    )
