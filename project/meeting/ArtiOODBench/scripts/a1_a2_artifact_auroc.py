"""
a1_a2_artifact_auroc.py
服务: ArtiOODBench Gate1 R1+R2（判据 A-1 + A-2）
lever: L1 artifact 量化

【做什么】
对任意 (ID 集, OOD 集) 对，用 43 维 artifact-only 特征（复用 c107 特征提取器）
在 5 个 seed {42,1,2,3,4} 上报 AUROC 均值 ± std，输出：
  - a1_artifact_auroc.csv  (对 × 特征组 × AUROC±std)
  - a2_modality_auroc.csv  (按模态聚合)

【公平性设计】
所有图像统一 resize 224² 灰度再提特征（分辨率红线）。

【数据集对（cross-source 跨机构，对齐判据 A-1/A-2）】
4 个 cross-source 对（主线，计入 A-1/A-2）:
  P1 CXR:       NIH ChestX-ray14 (ID)  vs VinDr-CXR (OOD)
  P2 CXR:       NIH ChestX-ray14 (ID)  vs RSNA_normal (OOD, medianomaly)
  P3 BrainMRI:  BraTS_normal (ID)      vs BrainTumor_normal (OOD, medianomaly)
  P4 Derm:      HAM_NV (ID)            vs ISIC2020_benign (OOD)

Within-source controls（仅入 appendix，subset='within_source_control'）:
  W1 BrainMRI:  BraTS_normal (ID)      vs BraTS_tumor
  W2 Derm:      HAM_NV (ID)            vs HAM_nonNV
  W3 CXR:       RSNA_normal (ID)       vs RSNA_pneumonia

【运行】
  # smoke（每数据集 10 张，CPU）
  python a1_a2_artifact_auroc.py --smoke 10

  # 全量
  python a1_a2_artifact_auroc.py
"""

import argparse
import csv
import io
import os
import random
import sys
from pathlib import Path

import numpy as np
from PIL import Image

# Windows GBK 终端安全：强制 stdout/stderr utf-8
if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
if sys.stderr.encoding and sys.stderr.encoding.lower() not in ("utf-8", "utf8"):
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# ============================================================
# 路径（从 datasets.json 真源）
# ============================================================
NIH_DIR = Path(
    "D:/YJ-Agent/project/meeting/Med-NCA/NCA-JEPA/data/nih_cxr14/images-224/images-224"
)
VINDR_DIR = Path("D:/YJ-Agent/data/external/vindr_cxr")
BRATS_DIR = Path("D:/YJ-Agent/project/meeting/MedAD-FailMap/data/BraTS2021")
HAM_DIR = Path("D:/YJ-Agent/data/external/ham10000")
# 新增 cross-source 数据集
RSNA_DIR = Path("D:/YJ-Agent/data/external/medianomaly/RSNA")
BRAINTUMOR_DIR = Path("D:/YJ-Agent/data/external/medianomaly/BrainTumor")
ISIC2020_GT_CSV = Path("D:/YJ-Agent/data/raw/isic2020/ISIC_2020_Training_GroundTruth_v2.csv")
ISIC2020_IMG_DIR = Path("D:/YJ-Agent/data/raw/isic2020/train-image/image")

OUT_DIR = Path(__file__).resolve().parent.parent / "results"
OUT_A1 = OUT_DIR / "a1_artifact_auroc.csv"
OUT_A2 = OUT_DIR / "a2_modality_auroc.csv"

TARGET_SIZE = 224  # 必须 resize，防分辨率泄漏
N_SAMPLE = 300     # 每侧采样数（全量）
SEEDS = [42, 1, 2, 3, 4]


# ============================================================
# 特征提取（完全复用 c107 逻辑，43 维）
# ============================================================
def load_image_gray224(path: Path) -> np.ndarray:
    img = Image.open(path).convert("L")
    if img.size != (TARGET_SIZE, TARGET_SIZE):
        img = img.resize((TARGET_SIZE, TARGET_SIZE), Image.BILINEAR)
    return np.array(img, dtype=np.uint8)


def feat_hist32(arr: np.ndarray) -> np.ndarray:
    hist, _ = np.histogram(arr.flatten(), bins=32, range=(0, 256))
    hist = hist.astype(np.float32)
    total = hist.sum()
    if total > 0:
        hist /= total
    return hist  # 32 dims


def feat_edge_ratio(arr: np.ndarray, border_px: int = 10) -> np.ndarray:
    h, w = arr.shape
    border_mask = np.zeros((h, w), dtype=bool)
    border_mask[:border_px, :] = True
    border_mask[-border_px:, :] = True
    border_mask[:, :border_px] = True
    border_mask[:, -border_px:] = True
    border_pixels = arr[border_mask]
    border_dark_ratio = float((border_pixels < 5).sum()) / max(len(border_pixels), 1)
    global_dark_ratio = float((arr.flatten() < 5).sum()) / max(arr.size, 1)
    return np.array([border_dark_ratio, global_dark_ratio], dtype=np.float32)  # 2 dims


def feat_glcm(arr: np.ndarray) -> np.ndarray:
    try:
        from skimage.feature import graycomatrix, graycoprops
    except ImportError:
        raise ImportError("需要 scikit-image: pip install scikit-image")
    arr_small = np.array(
        Image.fromarray(arr).resize((64, 64), Image.BILINEAR), dtype=np.uint8
    )
    arr_q = (arr_small // 8).astype(np.uint8)  # 0-31
    angles = [0, np.pi / 4, np.pi / 2, 3 * np.pi / 4]
    glcm = graycomatrix(arr_q, distances=[1], angles=angles, levels=32,
                        symmetric=True, normed=True)
    contrast = graycoprops(glcm, "contrast").mean()
    energy = graycoprops(glcm, "energy").mean()
    homogeneity = graycoprops(glcm, "homogeneity").mean()
    correlation = graycoprops(glcm, "correlation").mean()
    return np.array([contrast, energy, homogeneity, correlation], dtype=np.float32)  # 4 dims


def feat_stats(arr: np.ndarray) -> np.ndarray:
    flat = arr.flatten().astype(np.float32)
    mean = float(flat.mean())
    std = float(flat.std()) + 1e-8
    skewness = float(((flat - mean) ** 3).mean()) / (std ** 3)
    kurt = float(((flat - mean) ** 4).mean()) / (std ** 4) - 3.0
    return np.array([mean, float(flat.var()), skewness, kurt], dtype=np.float32)  # 4 dims


def feat_fft_ratio(arr: np.ndarray) -> np.ndarray:
    f = np.fft.fft2(arr.astype(np.float32))
    fshift = np.fft.fftshift(f)
    magnitude = np.abs(fshift)
    h, w = magnitude.shape
    cy, cx = h // 2, w // 2
    half_win = 5
    low_mask = np.zeros((h, w), dtype=bool)
    low_mask[cy - half_win: cy + half_win, cx - half_win: cx + half_win] = True
    low_energy = float(magnitude[low_mask].sum())
    high_energy = float(magnitude[~low_mask].sum())
    ratio = high_energy / (low_energy + 1e-8)
    return np.array([ratio], dtype=np.float32)  # 1 dim


FEATURE_GROUPS = {
    "hist32": (feat_hist32, 32),
    "edge_ratio": (feat_edge_ratio, 2),
    "glcm": (feat_glcm, 4),
    "stats": (feat_stats, 4),
    "fft_ratio": (feat_fft_ratio, 1),
}
# total = 43 dims


def extract_all_features(arr: np.ndarray) -> np.ndarray:
    feats = [fn(arr) for fn, _ in FEATURE_GROUPS.values()]
    return np.concatenate(feats)  # (43,)


# ============================================================
# 纯 numpy AUROC（避 scipy，Windows OMP 安全）
# ============================================================
def auroc_numpy(labels: np.ndarray, scores: np.ndarray) -> float:
    pos_scores = scores[labels == 1]
    neg_scores = scores[labels == 0]
    if len(pos_scores) == 0 or len(neg_scores) == 0:
        return float("nan")
    u = 0.0
    for ps in pos_scores:
        u += (neg_scores < ps).sum() + 0.5 * (neg_scores == ps).sum()
    return float(u / (len(pos_scores) * len(neg_scores)))


def sigmoid(x: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-np.clip(x, -100, 100)))


def logreg_proba(X_tr, y_tr, X_val, seed=42):
    """sklearn LR 优先，fallback 纯 numpy。"""
    try:
        from sklearn.linear_model import LogisticRegression
        mu = X_tr.mean(0)
        sigma = X_tr.std(0) + 1e-8
        clf = LogisticRegression(C=1.0, max_iter=1000, solver="lbfgs",
                                 random_state=seed)
        clf.fit((X_tr - mu) / sigma, y_tr)
        return clf.predict_proba((X_val - mu) / sigma)[:, 1].astype(np.float32)
    except ImportError:
        pass
    # fallback numpy LR
    mu = X_tr.mean(0)
    sigma = X_tr.std(0) + 1e-8
    Xn = (X_tr - mu) / sigma
    Xvn = (X_val - mu) / sigma
    n, d = Xn.shape
    w = np.zeros(d, dtype=np.float64)
    b = 0.0
    lr_rate = 0.1
    for _ in range(300):
        probs = sigmoid(Xn @ w + b)
        err = probs - y_tr.astype(np.float64)
        w -= lr_rate * ((Xn.T @ err) / n + w / n)
        b -= lr_rate * err.mean()
    return sigmoid(Xvn @ w + b).astype(np.float32)


def auroc_with_seed(X: np.ndarray, y: np.ndarray, seed: int, k: int = 5) -> float:
    """单 seed k-fold CV AUROC（非分层，手动 shuffle）。"""
    rng = np.random.RandomState(seed)
    idx = np.arange(len(y))
    rng.shuffle(idx)
    fold_size = len(y) // k
    aurocs = []
    for fold in range(k):
        val_idx = idx[fold * fold_size: (fold + 1) * fold_size]
        tr_idx = np.concatenate([idx[:fold * fold_size], idx[(fold + 1) * fold_size:]])
        probs = logreg_proba(X[tr_idx], y[tr_idx], X[val_idx], seed=seed)
        aurocs.append(auroc_numpy(y[val_idx], probs))
    return float(np.nanmean(aurocs))


def multi_seed_auroc(X: np.ndarray, y: np.ndarray, seeds=SEEDS):
    """多 seed 均值 ± std。"""
    vals = [auroc_with_seed(X, y, s) for s in seeds]
    return float(np.nanmean(vals)), float(np.nanstd(vals)), vals


# ============================================================
# 数据集加载器
# ============================================================
def load_images(paths, desc, n_sample=None, seed=42):
    rng = random.Random(seed)
    if n_sample and n_sample < len(paths):
        paths = list(paths)
        rng.shuffle(paths)
        paths = paths[:n_sample]
    feats = []
    for i, p in enumerate(paths):
        if (i + 1) % 50 == 0:
            print(f"  [{desc}] {i+1}/{len(paths)}")
        try:
            arr = load_image_gray224(Path(p))
            feats.append(extract_all_features(arr))
        except Exception as e:
            print(f"  [WARN] skip {Path(p).name}: {e}", file=sys.stderr)
    return np.array(feats, dtype=np.float32) if feats else np.zeros((0, 43), dtype=np.float32)


def _glob_images(d: Path, exts=(".png", ".jpg", ".jpeg")):
    if not d.exists():
        return []
    return [p for p in d.iterdir() if p.suffix.lower() in exts]


def collect_brats_normal():
    """BraTS2021 正常脑（test/normal 子目录）。"""
    norm_dir = BRATS_DIR / "test" / "normal"
    if not norm_dir.exists():
        # 有些版本结构不同，尝试 normal/
        norm_dir = BRATS_DIR / "normal"
    return _glob_images(norm_dir)


def collect_brats_tumor():
    """BraTS2021 tumor 脑。"""
    tumor_dir = BRATS_DIR / "test" / "tumor"
    if not tumor_dir.exists():
        tumor_dir = BRATS_DIR / "tumor"
    return _glob_images(tumor_dir)


def collect_ham_nv():
    """HAM10000 nevus（NV）作 ID。dx==nv。"""
    meta_candidates = [
        HAM_DIR / "HAM10000_metadata.csv",
        HAM_DIR / "metadata.csv",
    ]
    meta = None
    for mc in meta_candidates:
        if mc.exists():
            meta = mc
            break
    if meta is None:
        print("[WARN] HAM10000 metadata CSV not found, returning empty", file=sys.stderr)
        return [], []
    nv_ids, nonnv_ids = [], []
    with open(meta, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            dx = row.get("dx", "").strip().lower()
            img_id = row.get("image_id", "").strip()
            if dx == "nv":
                nv_ids.append(img_id)
            else:
                nonnv_ids.append(img_id)

    def ids_to_paths(ids):
        paths = []
        for img_id in ids:
            for part in ["HAM10000_images_part_1", "HAM10000_images_part_2"]:
                p = HAM_DIR / part / f"{img_id}.jpg"
                if p.exists():
                    paths.append(p)
                    break
        return paths

    return ids_to_paths(nv_ids), ids_to_paths(nonnv_ids)


def _load_medianomaly_normal(dataset_dir: Path) -> list:
    """
    MedIAnomaly 格式：data.json  {"train":{"0":[fn,...]}, "test":{"0":[fn,...]}}
    images/ 子目录存 PNG 或 JPG。
    label "0" = normal。
    """
    import json
    data_json = dataset_dir / "data.json"
    if not data_json.exists():
        print(f"[WARN] data.json not found: {data_json}", file=sys.stderr)
        return []
    with open(data_json, "r", encoding="utf-8") as f:
        data = json.load(f)
    filenames = []
    for split_key in ("train", "test"):
        filenames.extend(data.get(split_key, {}).get("0", []))
    imgs_dir = dataset_dir / "images"
    paths = []
    for fn in filenames:
        p = imgs_dir / fn
        if p.exists():
            paths.append(p)
        else:
            # try with/without extension fallback
            for ext in (".png", ".jpg", ".jpeg"):
                pb = imgs_dir / (Path(fn).stem + ext)
                if pb.exists():
                    paths.append(pb)
                    break
    if not paths:
        print(f"[WARN] {dataset_dir.name}: 0 normal images resolved from data.json", file=sys.stderr)
    return paths


def collect_rsna_normal() -> list:
    """RSNA medianomaly normal subset."""
    return _load_medianomaly_normal(RSNA_DIR)


def collect_braintumor_normal() -> list:
    """BrainTumor medianomaly normal subset."""
    return _load_medianomaly_normal(BRAINTUMOR_DIR)


def collect_isic2020_benign() -> list:
    """ISIC 2020 benign lesions from ground-truth CSV."""
    if not ISIC2020_GT_CSV.exists():
        print(f"[WARN] ISIC2020 GT CSV not found: {ISIC2020_GT_CSV}", file=sys.stderr)
        return []
    if not ISIC2020_IMG_DIR.exists():
        print(f"[WARN] ISIC2020 image dir not found: {ISIC2020_IMG_DIR}", file=sys.stderr)
        return []
    paths = []
    with open(ISIC2020_GT_CSV, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row.get("benign_malignant", "").strip().lower() == "benign":
                name = row.get("image_name", "").strip()
                if not name:
                    continue
                for ext in (".jpg", ".jpeg", ".png"):
                    p = ISIC2020_IMG_DIR / (name + ext)
                    if p.exists():
                        paths.append(p)
                        break
    if not paths:
        print(f"[WARN] ISIC2020: 0 benign images resolved", file=sys.stderr)
    return paths


def collect_rsna_pneumonia() -> list:
    """RSNA medianomaly abnormal subset (label '1' = pneumonia)."""
    import json
    data_json = RSNA_DIR / "data.json"
    if not data_json.exists():
        return []
    with open(data_json, "r", encoding="utf-8") as f:
        data = json.load(f)
    filenames = []
    for split_key in ("train", "test"):
        filenames.extend(data.get(split_key, {}).get("1", []))
    imgs_dir = RSNA_DIR / "images"
    paths = []
    for fn in filenames:
        p = imgs_dir / fn
        if p.exists():
            paths.append(p)
    return paths


# ============================================================
# 核心：对一组数据算各特征组 AUROC
# ============================================================
def compute_pair_auroc(X_id: np.ndarray, X_ood: np.ndarray,
                       pair_name: str, seeds=SEEDS):
    """
    对 (ID, OOD) 数据矩阵，分别计算：
    - all_43dim: 全 43 维 LR
    - 各特征组单独 LR
    返回 list of dicts（行）。
    """
    if len(X_id) == 0 or len(X_ood) == 0:
        print(f"  [SKIP] {pair_name}: 数据为空 id={len(X_id)} ood={len(X_ood)}")
        return []

    X_all = np.concatenate([X_id, X_ood], axis=0)
    y_all = np.array([0] * len(X_id) + [1] * len(X_ood), dtype=np.int32)

    rows = []
    # all-43dim
    mean_a, std_a, _ = multi_seed_auroc(X_all, y_all, seeds)
    rows.append({"pair": pair_name, "feature_group": "all_43dim",
                 "auroc_mean": round(mean_a, 4), "auroc_std": round(std_a, 4),
                 "n_id": len(X_id), "n_ood": len(X_ood)})
    print(f"  {pair_name} | all_43dim : {mean_a:.4f} ± {std_a:.4f}")

    # per-group
    col_offset = 0
    for group_name, (_, dim) in FEATURE_GROUPS.items():
        Xg = X_all[:, col_offset: col_offset + dim]
        col_offset += dim
        mg, sg, _ = multi_seed_auroc(Xg, y_all, seeds)
        rows.append({"pair": pair_name, "feature_group": group_name,
                     "auroc_mean": round(mg, 4), "auroc_std": round(sg, 4),
                     "n_id": len(X_id), "n_ood": len(X_ood)})
        print(f"  {pair_name} | {group_name:12s}: {mg:.4f} ± {sg:.4f}")

    return rows


# ============================================================
# 主逻辑
# ============================================================
def main(smoke_n: int = 0):
    n = smoke_n if smoke_n > 0 else N_SAMPLE
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    print(f"[A1/A2] n_per_side={n}, seeds={SEEDS}, resize={TARGET_SIZE}^2")

    # all_a1_rows: 4 cross-source main pairs (count toward A-1/A-2)
    # ctrl_rows: within-source controls (appendix only)
    all_a1_rows = []
    ctrl_rows = []
    # modality_records: cross-source only
    modality_records = {}  # modality -> [(pair_name, auroc_mean), ...]

    # ================================================================
    # Cross-source P1: CXR -- NIH(ID) vs VinDr(OOD)
    # ================================================================
    print("\n[P1] CXR cross-source: NIH(ID) vs VinDr(OOD)")
    nih_files = _glob_images(NIH_DIR)
    vindr_files = (_glob_images(VINDR_DIR / "test") +
                   _glob_images(VINDR_DIR / "train"))
    if not nih_files:
        print(f"  [WARN] NIH dir empty: {NIH_DIR}", file=sys.stderr)
    if not vindr_files:
        print(f"  [WARN] VinDr dir empty: {VINDR_DIR}", file=sys.stderr)
    if nih_files and vindr_files:
        X_nih = load_images(nih_files, "NIH", n_sample=n)
        X_vindr = load_images(vindr_files, "VinDr", n_sample=n)
        rows_p1 = compute_pair_auroc(X_nih, X_vindr, "NIH_vs_VinDr")
        all_a1_rows.extend(rows_p1)
        for r in rows_p1:
            if r["feature_group"] == "all_43dim":
                modality_records.setdefault("CXR", []).append(
                    (r["pair"], r["auroc_mean"]))
    else:
        print("  [SKIP] P1 missing data")

    # ================================================================
    # Cross-source P2: CXR -- NIH(ID) vs RSNA_normal(OOD)
    # ================================================================
    print("\n[P2] CXR cross-source: NIH(ID) vs RSNA_normal(OOD)")
    rsna_normal_files = collect_rsna_normal()
    if not rsna_normal_files:
        print(f"  [WARN] RSNA_normal 0 images: {RSNA_DIR}", file=sys.stderr)
    if nih_files and rsna_normal_files:
        X_nih2 = load_images(nih_files, "NIH_p2", n_sample=n)
        X_rsna = load_images(rsna_normal_files, "RSNA_normal", n_sample=n)
        rows_p2 = compute_pair_auroc(X_nih2, X_rsna, "NIH_vs_RSNA_normal")
        all_a1_rows.extend(rows_p2)
        for r in rows_p2:
            if r["feature_group"] == "all_43dim":
                modality_records.setdefault("CXR", []).append(
                    (r["pair"], r["auroc_mean"]))
    else:
        print("  [SKIP] P2 missing data")

    # ================================================================
    # Cross-source P3: BrainMRI -- BraTS_normal(ID) vs BrainTumor_normal(OOD)
    # ================================================================
    print("\n[P3] BrainMRI cross-source: BraTS_normal(ID) vs BrainTumor_normal(OOD)")
    brats_norm_files = collect_brats_normal()
    braintumor_norm_files = collect_braintumor_normal()
    if not brats_norm_files:
        print(f"  [WARN] BraTS_normal 0 images: {BRATS_DIR}", file=sys.stderr)
    if not braintumor_norm_files:
        print(f"  [WARN] BrainTumor_normal 0 images: {BRAINTUMOR_DIR}", file=sys.stderr)
    if brats_norm_files and braintumor_norm_files:
        X_brats_n = load_images(brats_norm_files, "BraTS_normal", n_sample=n)
        X_bt_n = load_images(braintumor_norm_files, "BrainTumor_normal", n_sample=n)
        rows_p3 = compute_pair_auroc(X_brats_n, X_bt_n, "BraTS_normal_vs_BrainTumor_normal")
        all_a1_rows.extend(rows_p3)
        for r in rows_p3:
            if r["feature_group"] == "all_43dim":
                modality_records.setdefault("BrainMRI", []).append(
                    (r["pair"], r["auroc_mean"]))
    else:
        print("  [SKIP] P3 missing data")

    # ================================================================
    # Cross-source P4: Derm -- HAM_NV(ID) vs ISIC2020_benign(OOD)
    # ================================================================
    print("\n[P4] Derm cross-source: HAM_NV(ID) vs ISIC2020_benign(OOD)")
    ham_nv_files, ham_nonnv_files = collect_ham_nv()
    isic_benign_files = collect_isic2020_benign()
    if not ham_nv_files:
        print(f"  [WARN] HAM_NV 0 images: {HAM_DIR}", file=sys.stderr)
    if not isic_benign_files:
        print(f"  [WARN] ISIC2020_benign 0 images: {ISIC2020_IMG_DIR}", file=sys.stderr)
    if ham_nv_files and isic_benign_files:
        X_nv = load_images(ham_nv_files, "HAM_NV", n_sample=n)
        X_isic = load_images(isic_benign_files, "ISIC2020_benign", n_sample=n)
        rows_p4 = compute_pair_auroc(X_nv, X_isic, "HAM_NV_vs_ISIC2020_benign")
        all_a1_rows.extend(rows_p4)
        for r in rows_p4:
            if r["feature_group"] == "all_43dim":
                modality_records.setdefault("Dermoscopy", []).append(
                    (r["pair"], r["auroc_mean"]))
    else:
        print("  [SKIP] P4 missing data")

    # ================================================================
    # Within-source controls (appendix only, subset='within_source_control')
    # ================================================================
    print("\n[W1] BrainMRI within-source: BraTS_normal vs BraTS_tumor (control)")
    brats_tumor_files = collect_brats_tumor()
    if brats_norm_files and brats_tumor_files:
        X_brats_n2 = load_images(brats_norm_files, "BraTS_normal_w", n_sample=n)
        X_btumor = load_images(brats_tumor_files, "BraTS_tumor", n_sample=n)
        rows_w1 = compute_pair_auroc(X_brats_n2, X_btumor, "BraTS_normal_vs_tumor")
        for r in rows_w1:
            r["subset"] = "within_source_control"
        ctrl_rows.extend(rows_w1)
    else:
        print(f"  [SKIP] W1 (norm={len(brats_norm_files)} tumor={len(brats_tumor_files)})")

    print("\n[W2] Derm within-source: HAM_NV vs HAM_nonNV (control)")
    if ham_nv_files and ham_nonnv_files:
        X_nv2 = load_images(ham_nv_files, "HAM_NV_w", n_sample=n)
        X_nonnv = load_images(ham_nonnv_files, "HAM_nonNV", n_sample=n)
        rows_w2 = compute_pair_auroc(X_nv2, X_nonnv, "HAM_NV_vs_nonNV")
        for r in rows_w2:
            r["subset"] = "within_source_control"
        ctrl_rows.extend(rows_w2)
    else:
        print(f"  [SKIP] W2 (nv={len(ham_nv_files)} nonnv={len(ham_nonnv_files)})")

    print("\n[W3] CXR within-source: RSNA_normal vs RSNA_pneumonia (control)")
    rsna_pneumonia_files = collect_rsna_pneumonia()
    if rsna_normal_files and rsna_pneumonia_files:
        X_rsna_n2 = load_images(rsna_normal_files, "RSNA_normal_w", n_sample=n)
        X_rsna_p = load_images(rsna_pneumonia_files, "RSNA_pneumonia", n_sample=n)
        rows_w3 = compute_pair_auroc(X_rsna_n2, X_rsna_p, "RSNA_normal_vs_pneumonia")
        for r in rows_w3:
            r["subset"] = "within_source_control"
        ctrl_rows.extend(rows_w3)
    else:
        print(f"  [SKIP] W3 (normal={len(rsna_normal_files)} pneumonia={len(rsna_pneumonia_files)})")

    # ============================================================
    # Write A1 CSV (cross-source main pairs)
    # ============================================================
    fieldnames_a1 = ["pair", "feature_group", "auroc_mean", "auroc_std", "n_id", "n_ood"]
    with open(OUT_A1, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames_a1)
        w.writeheader()
        w.writerows(all_a1_rows)
    print(f"\n[A1] -> {OUT_A1}  ({len(all_a1_rows)} rows)")

    # within-source controls saved as appendix table
    out_ctrl = OUT_DIR / "a1_within_source_controls.csv"
    if ctrl_rows:
        ctrl_fieldnames = ["pair", "feature_group", "auroc_mean", "auroc_std",
                           "n_id", "n_ood", "subset"]
        with open(out_ctrl, "w", newline="", encoding="utf-8") as f:
            wc = csv.DictWriter(f, fieldnames=ctrl_fieldnames, extrasaction="ignore")
            wc.writeheader()
            wc.writerows(ctrl_rows)
        print(f"[W]  -> {out_ctrl}  ({len(ctrl_rows)} rows, appendix-only)")

    # ============================================================
    # Write A2 CSV (modality aggregation, cross-source only)
    # ============================================================
    a2_rows = []
    for modality, pair_list in modality_records.items():
        aurocs = [a for _, a in pair_list]
        a2_rows.append({
            "modality": modality,
            "n_pairs": len(pair_list),
            "pairs": "|".join(p for p, _ in pair_list),
            "auroc_mean_of_pairs": round(float(np.mean(aurocs)), 4),
            "auroc_min": round(float(np.min(aurocs)), 4),
            "auroc_max": round(float(np.max(aurocs)), 4),
            "A2_pass": int(float(np.min(aurocs)) > 0.75),
        })

    fieldnames_a2 = ["modality", "n_pairs", "pairs", "auroc_mean_of_pairs",
                     "auroc_min", "auroc_max", "A2_pass"]
    with open(OUT_A2, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames_a2)
        w.writeheader()
        w.writerows(a2_rows)
    print(f"[A2] -> {OUT_A2}")

    # Verdict summary
    print("\n" + "=" * 60)
    print("A-1 (>=3 cross-source pairs; >=2 AUROC>=0.80; >=1 >0.90):")
    all_43_by_pair = [(r["pair"], r["auroc_mean"])
                      for r in all_a1_rows if r["feature_group"] == "all_43dim"]
    for pair, auc in all_43_by_pair:
        flag = ""
        if auc >= 0.90:
            flag = " *** >0.90"
        elif auc >= 0.80:
            flag = " ** >=0.80"
        elif auc >= 0.75:
            flag = " * >=0.75"
        print(f"  {pair}: {auc:.4f}{flag}")
    n_gte_080 = sum(1 for _, a in all_43_by_pair if a >= 0.80)
    n_gte_090 = sum(1 for _, a in all_43_by_pair if a >= 0.90)
    print(f"\n  pairs>=0.80: {n_gte_080}/{len(all_43_by_pair)}, pairs>0.90: {n_gte_090}")
    a1_pass = (len(all_43_by_pair) >= 3) and (n_gte_080 >= 2) and (n_gte_090 >= 1)
    print(f"  A-1 PASS: {a1_pass}")
    print("\nA-2 (each modality min AUROC>0.75, need >=3 modalities):")
    for r in a2_rows:
        print(f"  {r['modality']}: pairs={r['n_pairs']} min={r['auroc_min']:.4f} pass={bool(r['A2_pass'])}")
    n_mod_pass = sum(1 for r in a2_rows if r["A2_pass"])
    a2_pass = n_mod_pass >= 3
    print(f"  modalities_pass={n_mod_pass}/3  A-2 PASS: {a2_pass}")
    print("=" * 60)

    if smoke_n > 0:
        print(f"\n[SMOKE] n={smoke_n}/side, structure-only, not final numbers.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="A1+A2 artifact AUROC (multi-pair, multi-seed)")
    parser.add_argument("--smoke", type=int, default=0,
                        help="smoke n（0=全量）")
    args = parser.parse_args()
    main(smoke_n=args.smoke)
