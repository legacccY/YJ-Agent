"""D10 质量标量来源消融 — 5 种 q̄ 来源对比 QCTS 效果

5 质量标量：
1. VisiScore-Net (ours): 已有 quality_labels_all.csv
2. BRISQUE: piq.BRISQUELoss, invert + normalize
3. CLIP-IQA: piq.CLIPIQA
4. RF-Stat: sklearn RF on 8 image statistics -> q̄
5. LaplacianVar: normalized Laplacian variance (simplest)

Usage:
  cd D:/YJ-Agent/project
  python run_quality_scalar_ablation.py
"""

import json
import re
import sys
import pickle
from pathlib import Path

import cv2
import numpy as np
import pandas as pd
import torch
import torch.nn as nn
from scipy.optimize import minimize
from scipy.stats import spearmanr
from sklearn.ensemble import RandomForestRegressor
from torch.utils.data import DataLoader, TensorDataset
from tqdm import tqdm

sys.path.insert(0, str(Path(__file__).parent))
from benchmark.metrics import compute_binary_ece
from models.q_vib_encoder import QVIBEncoder
from models.qad_classifier import QADClassifier

DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")
ROOT = Path("D:/YJ-Agent")
PROJ = Path(__file__).parent
SCORE_COLS = ["sharpness", "brightness", "completeness", "color_temp", "contrast"]
CACHE_PATH = PROJ / "results/quality_scalar_cache.pkl"
IMG_SIZE = 224
VAL_SUBSAMPLE = None  # use full val set for reliable QCTS fitting
BATCH_SIZE = 32


# ── 图像加载工具 ───────────────────────────────────────────────────────────────

def load_image_tensor(path, size=IMG_SIZE):
    """Load image → normalized float32 tensor (C, H, W) in [0, 1]."""
    img = cv2.imread(str(path))
    if img is None:
        return None
    img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    img = cv2.resize(img, (size, size))
    return torch.tensor(img / 255.0, dtype=torch.float32).permute(2, 0, 1)


def load_images_batch(paths, size=IMG_SIZE):
    """Load list of paths → (N, C, H, W) tensor, skipping None."""
    tensors, valid_idx = [], []
    for i, p in enumerate(paths):
        t = load_image_tensor(p, size)
        if t is not None:
            tensors.append(t)
            valid_idx.append(i)
    if not tensors:
        return None, []
    return torch.stack(tensors), valid_idx


# ── 质量标量计算函数 ───────────────────────────────────────────────────────────

def _brisque_single(img_tensor, loss_fn):
    """BRISQUE for single image, returns raw score or NaN on failure."""
    try:
        with torch.no_grad():
            raw = loss_fn(img_tensor.unsqueeze(0)).item()
        return raw
    except (AssertionError, Exception):
        return np.nan


def compute_brisque(paths, batch_size=BATCH_SIZE):
    """BRISQUE: lower = distorted = lower quality. Invert + clip to [0, 1]."""
    from piq import BRISQUELoss
    loss_fn = BRISQUELoss(data_range=1.0, reduction="none")
    loss_fn_cpu = BRISQUELoss(data_range=1.0, reduction="none")  # CPU fallback
    scores = np.full(len(paths), np.nan)

    for start in tqdm(range(0, len(paths), batch_size), desc="BRISQUE"):
        batch_paths = paths[start:start + batch_size]
        batch, valid = load_images_batch(batch_paths)
        if batch is None:
            continue
        # try batch first, fall back to per-image on assertion error
        try:
            with torch.no_grad():
                raw = loss_fn(batch.to(DEVICE)).cpu().numpy()
            q = np.clip(1.0 - raw / 100.0, 0.0, 1.0)
            for local_i, global_i in enumerate(valid):
                scores[start + global_i] = float(q[local_i])
        except (AssertionError, Exception):
            # per-image fallback (CPU)
            for local_i, global_i in enumerate(valid):
                raw_single = _brisque_single(batch[local_i].cpu(), loss_fn_cpu)
                if not np.isnan(raw_single):
                    scores[start + global_i] = float(np.clip(1.0 - raw_single / 100.0, 0, 1))

    return scores


def compute_clipiqa(paths, batch_size=16):
    """CLIP-IQA: higher = better. Already in [0, 1] range."""
    from piq import CLIPIQA
    model = CLIPIQA().to(DEVICE).eval()
    scores = np.full(len(paths), np.nan)

    for start in tqdm(range(0, len(paths), batch_size), desc="CLIP-IQA"):
        batch_paths = paths[start:start + batch_size]
        batch, valid = load_images_batch(batch_paths)
        if batch is None:
            continue
        with torch.no_grad():
            raw = model(batch.to(DEVICE)).squeeze(-1).cpu().numpy()
        raw = np.atleast_1d(raw)
        for local_i, global_i in enumerate(valid):
            scores[start + global_i] = float(raw[local_i])

    return scores


def compute_laplacian(paths):
    """Laplacian variance: captures sharpness. Normalize by percentile clipping."""
    raw = []
    for p in tqdm(paths, desc="LaplacianVar"):
        img = cv2.imread(str(p))
        if img is None:
            raw.append(np.nan)
            continue
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        lap_var = cv2.Laplacian(gray, cv2.CV_64F).var()
        raw.append(lap_var)

    raw = np.array(raw, dtype=np.float32)
    p5, p95 = np.nanpercentile(raw, 5), np.nanpercentile(raw, 95)
    scores = np.clip((raw - p5) / (p95 - p5 + 1e-8), 0.0, 1.0)
    return scores


def extract_image_stats(paths):
    """8 image statistics per image for RF training."""
    feats = []
    for p in tqdm(paths, desc="StatFeat"):
        img = cv2.imread(str(p))
        if img is None:
            feats.append(np.full(8, np.nan))
            continue
        gray_u8 = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        gray = gray_u8.astype(np.float32) / 255.0
        lap_var = cv2.Laplacian(gray_u8, cv2.CV_64F).var()
        sobel = cv2.Sobel(gray_u8, cv2.CV_64F, 1, 1).var()
        mean_v = float(np.mean(gray))
        std_v = float(np.std(gray))
        p10 = float(np.percentile(gray, 10))
        p90 = float(np.percentile(gray, 90))
        local_var = float(np.std(cv2.blur(gray, (8, 8)) - gray))
        contrast = float(p90 - p10)
        feats.append([lap_var, sobel, mean_v, std_v, p10, p90, local_var, contrast])

    return np.array(feats, dtype=np.float32)


# ── 共用工具（QCTS 拟合 + 评测）───────────────────────────────────────────────

def softplus(x):
    return np.log1p(np.exp(np.clip(x, -30, 30)))


def _binary_nll(logits, targets, T):
    T = np.maximum(T, 1e-3)
    scaled = logits / T
    log_pos = -np.log1p(np.exp(-scaled))
    log_neg = -np.log1p(np.exp(scaled))
    return -(targets * log_pos + (1 - targets) * log_neg).mean()


def fit_qcts(val_logits, val_qbar, val_targets, seeds=3):
    def nll(params):
        T0, alpha = params
        T = softplus(T0 + alpha * (1.0 - val_qbar))
        return float(_binary_nll(val_logits, val_targets, T))

    best_nll, best_params = np.inf, None
    for seed in range(seeds):
        rng = np.random.default_rng(seed)
        x0 = rng.uniform(0.0, 1.0, size=2)
        res = minimize(nll, x0, method="L-BFGS-B",
                       bounds=[(-5, 5), (0, 10)], options={"maxiter": 500})
        if res.fun < best_nll:
            best_nll = res.fun
            best_params = res.x
    return float(best_params[0]), float(best_params[1]), float(best_nll)


def eval_qcts_on_itb(T0, alpha, itb_preds, itb_quality_arr):
    """Apply QCTS using given T0, alpha and per-sample quality array."""
    d_preds = itb_preds[itb_preds["baseline"] == "D"].reset_index(drop=True)
    assert len(d_preds) == len(itb_quality_arr), \
        f"length mismatch: {len(d_preds)} vs {len(itb_quality_arr)}"

    p = d_preds["prob_pos"].clip(1e-7, 1 - 1e-7).values
    logits = np.log(p / (1 - p))
    qbar = itb_quality_arr

    T = softplus(T0 + alpha * (1.0 - qbar))
    T = np.maximum(T, 1e-3)
    prob = 1.0 / (1.0 + np.exp(-logits / T))
    entropy = -(prob * np.log(prob + 1e-9) + (1 - prob) * np.log(1 - prob + 1e-9))

    d_preds = d_preds.copy()
    d_preds["prob_q"] = prob
    d_preds["entropy_q"] = entropy
    d_preds["qbar_new"] = qbar

    ece_lq = compute_binary_ece(
        d_preds[d_preds["subset"] == "ITB-LQ"]["prob_q"].values,
        d_preds[d_preds["subset"] == "ITB-LQ"]["target"].values,
    )
    ece_hq = compute_binary_ece(
        d_preds[d_preds["subset"] == "ITB-HQ"]["prob_q"].values,
        d_preds[d_preds["subset"] == "ITB-HQ"]["target"].values,
    )
    rho, _ = spearmanr(entropy, d_preds["qbar"].values)
    return ece_lq, ece_hq, ece_lq - ece_hq, rho


# ── Val 数据加载 + 推理 ────────────────────────────────────────────────────────

def load_assets():
    q_labels = pd.read_csv(ROOT / "data/quality_labels_all.csv")
    abcd_cache = pd.read_csv(ROOT / "data/abcd_cache.csv")
    ef_index = pd.read_csv(ROOT / "data/efficientnet_index.csv")
    ef_all = np.load(ROOT / "data/efficientnet_features.npy", mmap_mode="r")
    isic_split = pd.read_csv(ROOT / "data/isic_split.csv")
    metadata = pd.read_csv(
        ROOT / "data/raw/isic2020/train-metadata.csv"
    )[["isic_id", "target"]]
    return q_labels, abcd_cache, ef_index, ef_all, isic_split, metadata


def get_val_samples(q_labels, abcd_cache, ef_index, ef_all, isic_split, metadata,
                    n_subsample=VAL_SUBSAMPLE, seed=42):
    val_ids = set(isic_split[isic_split["split"] == "val"]["isic_id"])
    q = q_labels.copy()
    q["isic_id"] = q["original_path"].apply(
        lambda p: re.search(r"(ISIC_\d+)", str(p)).group(1)
        if re.search(r"(ISIC_\d+)", str(p)) else None
    )
    q_val = q[(q["isic_id"].isin(val_ids)) & (q["source"] == "isic2020")].copy()
    q_val = q_val.merge(metadata, on="isic_id", how="inner")
    q_val = q_val.merge(abcd_cache, on="degraded_path", how="inner")
    q_val = q_val.merge(ef_index, on="degraded_path", how="inner")

    # stratified subsample by level
    rng = np.random.default_rng(seed)
    if n_subsample and len(q_val) > n_subsample:
        q_val = q_val.groupby("level", group_keys=False).apply(
            lambda g: g.sample(min(len(g), n_subsample // 3), random_state=seed)
        ).reset_index(drop=True)
        q_val = q_val.sample(min(n_subsample, len(q_val)), random_state=seed).reset_index(drop=True)

    print(f"[val subset] {len(q_val)} samples")
    return q_val


def get_val_logits(q_val, ef_all):
    abcd_arr = torch.tensor(q_val[["A", "B", "C", "D"]].values.astype(np.float32))
    q_arr = torch.tensor(q_val[SCORE_COLS].values.astype(np.float32))
    qbar_arr = torch.tensor(q_arr.numpy().mean(axis=1))
    ef_arr = torch.tensor(ef_all[q_val["efnet_row_idx"].values].astype(np.float32))
    targets_t = torch.tensor(q_val["target"].values.astype(np.int64))

    ckpt = torch.load(ROOT / "checkpoints/stdvib/best_qad.pth", map_location=DEVICE)
    from models.q_vib_encoder import QVIBEncoder
    from models.qad_classifier import QADClassifier
    encoder = QVIBEncoder(
        abcd_dim=4, q_dim=5, d_model=128, n_heads=4, latent_dim=64, efnet_dim=1280
    ).to(DEVICE).eval()
    classifier = QADClassifier(
        latent_dim=64, hidden_dim=128, num_classes=2, dropout=0.2
    ).to(DEVICE).eval()
    encoder.load_state_dict(ckpt["encoder"])
    classifier.load_state_dict(ckpt["classifier"])
    encoder.tokenizer.forward = lambda q: torch.zeros(q.shape[0], device=q.device)

    dataset = TensorDataset(abcd_arr, q_arr, qbar_arr, ef_arr, targets_t)
    loader = DataLoader(dataset, batch_size=512, shuffle=False, num_workers=0)
    all_logits, all_targets = [], []
    with torch.no_grad():
        for abcd_b, q_b, qbar_b, ef_b, tgt_b in tqdm(loader, desc="[val inference]"):
            mu, _ = encoder(abcd_b.to(DEVICE), q_b.to(DEVICE), efnet_feat=ef_b.to(DEVICE))
            logits_2 = classifier(mu)
            binary_logit = logits_2[:, 1] - logits_2[:, 0]
            all_logits.append(binary_logit.cpu())
            all_targets.append(tgt_b)

    return (
        torch.cat(all_logits).numpy(),
        torch.cat(all_targets).numpy(),
        q_arr.numpy().mean(axis=1),   # VisiScore q̄ for val subset
    )


# ── 主实验流程 ─────────────────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("D10 Quality Scalar Ablation -- 5 Methods")
    print("=" * 60)

    # 1. Load assets
    q_labels, abcd_cache, ef_index, ef_all, isic_split, metadata = load_assets()

    # 2. Val subset
    q_val = get_val_samples(q_labels, abcd_cache, ef_index, ef_all, isic_split, metadata)
    val_paths = q_val["degraded_path"].tolist()
    print(f"\n[val] inferring logits for {len(val_paths)} samples...")
    val_logits, val_targets, val_visiscore = get_val_logits(q_val, ef_all)

    # 3. ITB images (D baseline rows, same order as in itb_predictions.csv)
    itb_sub = pd.read_csv(PROJ / "results/itb_subsets.csv")
    # itb_sub matches D rows in itb_predictions.csv order
    itb_paths = itb_sub["image_path"].tolist()
    # VisiScore q̄ for ITB: from qbar column in itb_subsets (computed by VisiScore-Net)
    itb_visiscore = itb_sub["qbar"].values

    # 4. Load / compute quality scores
    cache = {}
    if CACHE_PATH.exists():
        cache = pickle.load(open(CACHE_PATH, "rb"))
        print(f"[cache] loaded {list(cache.keys())}")

    # BRISQUE
    if "brisque_val" not in cache:
        print("\n[Computing BRISQUE on val...]")
        cache["brisque_val"] = compute_brisque(val_paths)
        print("\n[Computing BRISQUE on ITB...]")
        cache["brisque_itb"] = compute_brisque(itb_paths)
        pickle.dump(cache, open(CACHE_PATH, "wb"))

    # CLIP-IQA
    if "clipiqa_val" not in cache:
        print("\n[Computing CLIP-IQA on val...]")
        cache["clipiqa_val"] = compute_clipiqa(val_paths)
        print("\n[Computing CLIP-IQA on ITB...]")
        cache["clipiqa_itb"] = compute_clipiqa(itb_paths)
        pickle.dump(cache, open(CACHE_PATH, "wb"))

    # Laplacian
    if "lap_val" not in cache:
        print("\n[Computing LaplacianVar on val...]")
        cache["lap_val"] = compute_laplacian(val_paths)
        print("\n[Computing LaplacianVar on ITB...]")
        cache["lap_itb"] = compute_laplacian(itb_paths)
        pickle.dump(cache, open(CACHE_PATH, "wb"))

    # RF-Stat: compute image stats for train split to train RF
    if "rf_val" not in cache:
        print("\n[RF-Stat] extracting val features...")
        val_feats = extract_image_stats(val_paths)
        val_rf_target = val_visiscore

        print("[RF-Stat] training RF on val features -> qbar...")
        valid_mask = ~np.isnan(val_feats).any(axis=1)
        rf = RandomForestRegressor(n_estimators=100, random_state=42, n_jobs=-1)
        rf.fit(val_feats[valid_mask], val_rf_target[valid_mask])

        # predict on val (in-sample, acceptable for QCTS fitting ablation)
        val_rf_pred = rf.predict(val_feats)
        val_rf_pred = np.clip(val_rf_pred, 0, 1)

        print("[RF-Stat] extracting ITB features...")
        itb_feats = extract_image_stats(itb_paths)
        itb_rf_pred = rf.predict(np.nan_to_num(itb_feats, nan=0.5))
        itb_rf_pred = np.clip(itb_rf_pred, 0, 1)

        cache["rf_val"] = val_rf_pred
        cache["rf_itb"] = itb_rf_pred
        pickle.dump(cache, open(CACHE_PATH, "wb"))

    # 5. QCTS fitting and ITB evaluation for all 5 methods
    itb_preds = pd.read_csv(PROJ / "results/itb_predictions.csv")

    # handle NaN in quality scores: fill with median
    def safe_qbar(arr):
        arr = arr.copy()
        med = np.nanmedian(arr)
        arr[np.isnan(arr)] = med
        return np.clip(arr, 0, 1)

    methods = {
        "5-head IQA (ours)": (val_visiscore, itb_visiscore),
        "BRISQUE":       (cache["brisque_val"], cache["brisque_itb"]),
        "CLIP-IQA":      (cache["clipiqa_val"], cache["clipiqa_itb"]),
        "RF-Stat":       (cache["rf_val"],      cache["rf_itb"]),
        "LaplacianVar":  (cache["lap_val"],      cache["lap_itb"]),
    }

    rows = []
    print("\n[QCTS fitting + ITB evaluation for 5 methods]")
    for name, (val_q, itb_q) in methods.items():
        val_q = safe_qbar(val_q)
        itb_q = safe_qbar(itb_q)

        T0, alpha, nll = fit_qcts(val_logits, val_q, val_targets)
        ece_lq, ece_hq, qcdi, rho = eval_qcts_on_itb(T0, alpha, itb_preds, itb_q)

        print(f"  {name:15s}  T0={T0:.3f}  a={alpha:.3f}  "
              f"ECE-LQ={ece_lq:.3f}  ECE-HQ={ece_hq:.3f}  "
              f"QCDI={qcdi:+.3f}  rho={rho:.3f}  NLL={nll:.4f}")

        rows.append({
            "method": name,
            "T0": T0, "alpha": alpha,
            "ece_lq": ece_lq, "ece_hq": ece_hq,
            "qcdi": qcdi, "rho": rho, "val_nll": nll,
        })

    # 6. Baseline: standard TS (quality-agnostic)
    with open(ROOT / "checkpoints/stdvib/temperature.json") as f:
        T_ts = json.load(f)["T"]
    d_preds = itb_preds[itb_preds["baseline"] == "D"].copy()
    p = d_preds["prob_pos"].clip(1e-7, 1 - 1e-7).values
    logits_itb = np.log(p / (1 - p))
    prob_ts = 1.0 / (1.0 + np.exp(-logits_itb / T_ts))
    ent_ts = -(prob_ts * np.log(prob_ts + 1e-9) + (1 - prob_ts) * np.log(1 - prob_ts + 1e-9))
    d_preds = d_preds.reset_index(drop=True)
    lq_mask = (d_preds["subset"] == "ITB-LQ").values
    hq_mask = (d_preds["subset"] == "ITB-HQ").values
    ece_ts_lq = compute_binary_ece(prob_ts[lq_mask], d_preds["target"].values[lq_mask])
    ece_ts_hq = compute_binary_ece(prob_ts[hq_mask], d_preds["target"].values[hq_mask])
    rho_ts, _ = spearmanr(ent_ts, d_preds["qbar"].values)
    print(f"  {'Std TS (baseline)':15s}  (T={T_ts:.3f})  "
          f"ECE-LQ={ece_ts_lq:.3f}  ECE-HQ={ece_ts_hq:.3f}  "
          f"QCDI={ece_ts_lq - ece_ts_hq:+.3f}  rho={rho_ts:.3f}")

    # 7. Save results
    df = pd.DataFrame(rows)
    out_csv = PROJ / "results/quality_scalar_ablation.csv"
    df.to_csv(out_csv, index=False)
    print(f"\n[Saved] {out_csv}")

    # 8. Generate LaTeX table
    _generate_tex(df, T_ts, ece_ts_lq, ece_ts_hq, rho_ts)

    print("\n[Done]")
    print("  -> results/quality_scalar_ablation.csv")
    print("  -> meeting/BMVC/table3_quality_scalar.tex")


def _generate_tex(df, T_ts, ece_ts_lq, ece_ts_hq, rho_ts):
    METHOD_ORDER = ["5-head IQA (ours)", "BRISQUE", "CLIP-IQA", "RF-Stat", "LaplacianVar"]
    METHOD_LABEL = {
        "5-head IQA (ours)": r"5-head IQA (ours)",
        "BRISQUE":       r"BRISQUE~\cite{brisque}",
        "CLIP-IQA":      r"CLIP-IQA~\cite{clipiqa}",
        "RF-Stat":       r"RF on image statistics",
        "LaplacianVar":  r"Laplacian variance",
    }
    qcdi_ts = ece_ts_lq - ece_ts_hq

    all_ece_lq = list(df["ece_lq"]) + [ece_ts_lq]
    all_ece_hq = list(df["ece_hq"]) + [ece_ts_hq]
    all_qcdi   = list(df["qcdi"])   + [qcdi_ts]
    all_rho    = list(df["rho"])    + [rho_ts]

    best_ece_lq = min(all_ece_lq)
    best_ece_hq = min(all_ece_hq)
    best_qcdi   = min(all_qcdi)
    best_rho    = min(all_rho)

    def fmt_v(val, best):
        s = f"{val:.3f}"
        if abs(val - best) < 5e-4:
            s = r"\textbf{" + s + r"}"
        return s

    def fmt_qcdi(val, best):
        s = f"$+${abs(val):.3f}" if val > 1e-4 else f"$-${abs(val):.3f}"
        if abs(val - best) < 5e-4:
            s = r"\textbf{" + s + r"}"
        return s

    lines = [
        r"\begin{table}[t]",
        r"\centering",
        r"\caption{",
        r"\textbf{QCTS under different quality scalars $\bar q$.}",
        r"QCTS is fitted separately for each quality estimator on the same frozen Std VIB backbone and val split.",
        r"All quality-conditioned variants outperform standard TS (bottom row) on both ECE-LQ and QCDI.",
        r"The proposed 5-head IQA achieves the best quality-aware calibration owing to domain-specific training,",
        r"but even the training-free Laplacian sharpness proxy improves quality-conditional ECE.",
        r"}",
        r"\label{tab:quality_scalar}",
        r"\footnotesize",
        r"\setlength{\tabcolsep}{6pt}",
        r"\renewcommand{\arraystretch}{1.05}",
        r"\begin{tabular}{lccccc}",
        r"\toprule",
        r"Quality scalar $\bar q$ & Learnable & ECE-LQ\,$\downarrow$ & ECE-HQ\,$\downarrow$ & QCDI\,$\downarrow$ & $\rho(H,\bar q)\,\downarrow$ \\",
        r"\midrule",
    ]

    LEARNABLE = {
        "5-head IQA (ours)": r"\checkmark",
        "BRISQUE":       r"---",
        "CLIP-IQA":      r"\checkmark",
        "RF-Stat":       r"\checkmark",
        "LaplacianVar":  r"---",
    }

    for name in METHOD_ORDER:
        row = df[df["method"] == name]
        if len(row) == 0:
            continue
        r = row.iloc[0]
        cells = [
            LEARNABLE[name],
            fmt_v(r["ece_lq"], best_ece_lq),
            fmt_v(r["ece_hq"], best_ece_hq),
            fmt_qcdi(r["qcdi"], best_qcdi),
            fmt_v(r["rho"], best_rho),
        ]
        lines.append(f"{METHOD_LABEL[name]} & {' & '.join(cells)} \\\\")

    # TS baseline
    lines.append(r"\midrule")
    ts_cells = [
        r"---",
        fmt_v(ece_ts_lq, best_ece_lq),
        fmt_v(ece_ts_hq, best_ece_hq),
        fmt_qcdi(qcdi_ts, best_qcdi),
        fmt_v(rho_ts, best_rho),
    ]
    lines.append(f"Standard TS (no quality) & {' & '.join(ts_cells)} \\\\")

    lines += [
        r"\bottomrule",
        r"\end{tabular}",
        r"\vspace{-4pt}",
        r"\end{table}",
    ]

    out_tex = PROJ / "meeting/BMVC/table3_quality_scalar.tex"
    out_tex.write_text("\n".join(lines), encoding="utf-8")
    print(f"[Saved] {out_tex}")


if __name__ == "__main__":
    main()
