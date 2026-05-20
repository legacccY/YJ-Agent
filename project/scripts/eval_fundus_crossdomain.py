"""D15-D17: Cross-modality QCTS evaluation on fundus images (APTOS 2019 DR dataset).

Uses ViT fine-tuned on DR grading (HuggingFace: Kontawat/vit-diabetic-retinopathy-classification).
Binary task: grade 0 = No DR (0), grade 1-4 = DR (1).
Applies imagecorruptions to create quality levels; corruption severity = q_bar proxy.
Fits QCTS on val subset and evaluates on corrupted versions.

Output: results/crossdomain/fundus_crossdomain.json
        results/crossdomain/fundus_crossdomain.csv

Usage:
    python project/scripts/eval_fundus_crossdomain.py
    python project/scripts/eval_fundus_crossdomain.py --data-dir D:/YJ-Agent/data/fundus/gaussian_filtered_images/gaussian_filtered_images
"""
import argparse
import json
import os
import sys
from pathlib import Path

import cv2
import numpy as np
import pandas as pd
import torch
from scipy.optimize import minimize
from scipy.stats import spearmanr
from sklearn.metrics import roc_auc_score
from tqdm import tqdm
from transformers import AutoModelForImageClassification, AutoFeatureExtractor
import warnings
warnings.filterwarnings("ignore")

try:
    from imagecorruptions import corrupt
    HAS_IMAGECORRUPTIONS = True
except ImportError:
    HAS_IMAGECORRUPTIONS = False
    print("[warn] imagecorruptions not installed; using simple blur only")

ROOT = Path("D:/YJ-Agent")
OUT_DIR = ROOT / "project/results/crossdomain"
IMG_SIZE = 224
MODEL_NAME = "Kontawat/vit-diabetic-retinopathy-classification"

CORRUPTIONS = [
    "gaussian_noise", "defocus_blur", "brightness", "contrast", "jpeg_compression"
] if HAS_IMAGECORRUPTIONS else ["blur"]


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--data-dir", default=None,
                   help="Path to fundus images folder (auto-detected if omitted)")
    p.add_argument("--n-test", type=int, default=200,
                   help="Test set size (default: 200)")
    p.add_argument("--n-val", type=int, default=400,
                   help="Val set size for QCTS fitting (default: 400)")
    p.add_argument("--seed", type=int, default=42)
    return p.parse_args()


def find_data_dir():
    """Auto-detect the fundus image directory."""
    candidates = [
        "D:/YJ-Agent/data/fundus/colored_images",
        "D:/YJ-Agent/data/fundus/gaussian_filtered_images/gaussian_filtered_images",
        "D:/YJ-Agent/data/fundus/gaussian_filtered_images",
        "D:/YJ-Agent/data/fundus/train_images",
        "D:/YJ-Agent/data/fundus/images",
        "D:/YJ-Agent/data/fundus",
    ]
    for c in candidates:
        p = Path(c)
        if p.exists():
            subdirs = [x.name for x in p.iterdir() if x.is_dir()]
            if any(d in subdirs for d in ['0', '1', '2', '3', '4', 'No_DR', 'Mild']):
                return p
    return None


GRADE_DIRNAME_MAP = {
    "No_DR": 0, "no_dr": 0, "0": 0,
    "Mild": 1, "mild": 1, "1": 1,
    "Moderate": 2, "moderate": 2, "2": 2,
    "Severe": 3, "severe": 3, "3": 3,
    "Proliferate_DR": 4, "proliferate_dr": 4, "4": 4,
}


def load_fundus_images(data_dir: Path, n_val: int, n_test: int, seed: int = 42):
    """Load fundus images. Supports named grade-subdir or numeric-subdir or csv structure."""
    records = []

    # Structure 1: named or numeric grade subdirectories
    for subdir in data_dir.iterdir():
        if not subdir.is_dir():
            continue
        grade = GRADE_DIRNAME_MAP.get(subdir.name)
        if grade is None:
            continue
        label = 0 if grade == 0 else 1
        for ext in ["*.png", "*.jpg", "*.jpeg"]:
            for img_path in subdir.glob(ext):
                records.append({"path": str(img_path), "target": label, "grade": grade})

    # Structure 2: flat directory with CSV
    if not records:
        csv_candidates = [data_dir / "train.csv", data_dir.parent / "train.csv",
                          data_dir / "trainLabels.csv"]
        for csv_p in csv_candidates:
            if csv_p.exists():
                df_meta = pd.read_csv(csv_p)
                label_col = [c for c in df_meta.columns
                             if any(k in c.lower() for k in ['label', 'level', 'diagnosis'])][0]
                id_col = df_meta.columns[0]
                for _, row in df_meta.iterrows():
                    for ext in ['.png', '.jpg', '.jpeg']:
                        p = data_dir / f"{row[id_col]}{ext}"
                        if p.exists():
                            grade = int(row[label_col])
                            records.append({"path": str(p), "target": 0 if grade == 0 else 1,
                                            "grade": grade})
                            break
                break

    if not records:
        raise FileNotFoundError(f"No fundus images found in {data_dir}. "
                                f"Expected subdirs 0/1/2/3/4 or CSV + images.")

    df = pd.DataFrame(records)
    print(f"[data] {len(df)} images total | No DR: {(df.target==0).sum()} | DR: {(df.target==1).sum()}")

    # Balanced sample for val + test
    rng = np.random.default_rng(seed)
    total_needed = n_val + n_test

    # Try to balance classes
    df0 = df[df.target == 0].sample(min(len(df[df.target == 0]), total_needed // 2),
                                    random_state=seed)
    df1 = df[df.target == 1].sample(min(len(df[df.target == 1]), total_needed - len(df0)),
                                    random_state=seed)
    df_use = pd.concat([df0, df1]).sample(frac=1, random_state=seed).reset_index(drop=True)

    df_val = df_use.iloc[:n_val].reset_index(drop=True)
    df_test = df_use.iloc[n_val:n_val + n_test].reset_index(drop=True)
    print(f"[split] val={len(df_val)} (DR:{(df_val.target==1).sum()}) | "
          f"test={len(df_test)} (DR:{(df_test.target==1).sum()})")
    return df_val, df_test


def preprocess_fundus(img_bgr: np.ndarray, feature_extractor) -> dict:
    """Preprocess for ViT feature extractor."""
    img_rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
    img_rgb = cv2.resize(img_rgb, (IMG_SIZE, IMG_SIZE))
    return feature_extractor(images=img_rgb, return_tensors="pt")


def corrupt_image(img_bgr: np.ndarray, corruption: str, severity: int) -> np.ndarray:
    if not HAS_IMAGECORRUPTIONS:
        ksize = 2 * severity + 1
        return cv2.GaussianBlur(img_bgr, (ksize, ksize), 0)
    img_rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
    corrupted = corrupt(img_rgb, corruption_name=corruption, severity=severity)
    return cv2.cvtColor(corrupted, cv2.COLOR_RGB2BGR)


@torch.no_grad()
def run_inference(model, feature_extractor, df: pd.DataFrame,
                  corruption: str = None, severity: int = 0, device="cpu") -> dict:
    model.eval()
    probs, targets, entropies = [], [], []

    for _, row in tqdm(df.iterrows(), total=len(df),
                       desc=f"infer {corruption or 'clean'} sev={severity}", leave=False):
        img = cv2.imread(row["path"])
        if img is None:
            continue
        if corruption:
            img = corrupt_image(img, corruption, severity)

        inputs = preprocess_fundus(img, feature_extractor)
        inputs = {k: v.to(device) for k, v in inputs.items()}
        logits = model(**inputs).logits  # (1, 5)

        # Softmax over 5 grades, then P(DR) = sum of grades 1-4
        probs_all = torch.softmax(logits[0], dim=0).cpu().numpy()
        p_dr = float(probs_all[1:].sum())
        p_dr = max(min(p_dr, 1 - 1e-7), 1e-7)
        H = -(p_dr * np.log(p_dr) + (1 - p_dr) * np.log(1 - p_dr))

        probs.append(p_dr)
        targets.append(int(row["target"]))
        entropies.append(H)

    return {
        "probs": np.array(probs),
        "targets": np.array(targets),
        "entropies": np.array(entropies),
    }


def compute_ece(probs: np.ndarray, targets: np.ndarray, n_bins: int = 10) -> float:
    bins = np.linspace(0, 1, n_bins + 1)
    ece = 0.0
    for lo, hi in zip(bins[:-1], bins[1:]):
        m = (probs >= lo) & (probs < hi)
        if m.sum() == 0:
            continue
        ece += m.mean() * abs(targets[m].mean() - probs[m].mean())
    return float(ece)


def softplus(x):
    return np.log1p(np.exp(np.clip(x, -30, 30)))


def qcts_temperature(T0, alpha, qbar):
    return softplus(T0 + alpha * (1.0 - qbar))


def fit_qcts(logits, qbar, targets, seeds=3):
    def nll(params):
        T0, alpha = params
        T = np.maximum(qcts_temperature(T0, alpha, qbar), 1e-3)
        scaled = logits / T
        lp = -np.log1p(np.exp(-scaled))
        ln = -np.log1p(np.exp(scaled))
        return float(-(targets * lp + (1 - targets) * ln).mean())

    best, best_params = np.inf, None
    rng = np.random.default_rng(0)
    for _ in range(seeds):
        x0 = rng.uniform(0, 1, 2)
        res = minimize(nll, x0, method="L-BFGS-B",
                       bounds=[(-5, 5), (0, 10)], options={"maxiter": 500})
        if res.fun < best:
            best = res.fun
            best_params = res.x
    return float(best_params[0]), float(best_params[1])


def main():
    args = parse_args()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    np.random.seed(args.seed)

    # Find data
    data_dir = Path(args.data_dir) if args.data_dir else find_data_dir()
    if data_dir is None:
        print("[error] Could not find fundus data directory.")
        print("  Expected: D:/YJ-Agent/data/fundus/<subdir>/0/  1/  2/  3/  4/")
        sys.exit(1)
    print(f"[data] Using: {data_dir}")

    # Load model
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"[init] Loading {MODEL_NAME} on {device}...")
    feature_extractor = AutoFeatureExtractor.from_pretrained(MODEL_NAME)
    model = AutoModelForImageClassification.from_pretrained(MODEL_NAME).to(device)
    model.eval()
    print("[init] Model loaded.")

    # Load images
    df_val, df_test = load_fundus_images(data_dir, args.n_val, args.n_test, args.seed)

    # Val inference (clean) for QCTS fitting
    print("[step 1] val inference (clean)...")
    val_out = run_inference(model, feature_extractor, df_val, device=device)
    val_probs = val_out["probs"]
    val_tgt = val_out["targets"]
    val_logits = np.log(val_probs / (1 - val_probs + 1e-9) + 1e-9)

    try:
        auc_clean = float(roc_auc_score(val_tgt, val_probs))
        print(f"[val] Clean AUC={auc_clean:.3f}")
    except Exception:
        print("[val] AUC could not be computed (single class?)")

    # Fit standard TS
    def ts_nll(T):
        T = max(T[0], 1e-3)
        p = 1 / (1 + np.exp(-val_logits / T))
        p = np.clip(p, 1e-7, 1 - 1e-7)
        return float(-(val_tgt * np.log(p) + (1 - val_tgt) * np.log(1 - p)).mean())
    T_ts = minimize(ts_nll, [1.0], method="L-BFGS-B", bounds=[(1e-3, 20)]).x[0]
    print(f"[TS] T_ts={T_ts:.4f}")

    results = []
    for corr_name in CORRUPTIONS:
        for sev in [1, 2, 3, 4, 5]:
            qbar = 1.0 - sev / 5.0

            val_qbar = np.full(len(df_val), qbar)
            T0, alpha = fit_qcts(val_logits, val_qbar, val_tgt)

            test_out = run_inference(model, feature_extractor, df_test,
                                     corruption=corr_name, severity=sev, device=device)
            t_probs = test_out["probs"]
            t_tgt = test_out["targets"]
            t_logits = np.log(t_probs / (1 - t_probs + 1e-9) + 1e-9)

            ece_raw = compute_ece(t_probs, t_tgt)
            try:
                auc_raw = float(roc_auc_score(t_tgt, t_probs))
            except Exception:
                auc_raw = float("nan")

            p_ts = np.clip(1 / (1 + np.exp(-t_logits / T_ts)), 1e-7, 1 - 1e-7)
            ece_ts = compute_ece(p_ts, t_tgt)

            T_qcts = np.maximum(qcts_temperature(T0, alpha, qbar), 1e-3)
            p_qcts = np.clip(1 / (1 + np.exp(-t_logits / T_qcts)), 1e-7, 1 - 1e-7)
            ece_qcts = compute_ece(p_qcts, t_tgt)

            print(f"  {corr_name} sev={sev} (qbar={qbar:.1f}) | "
                  f"AUC={auc_raw:.3f} ECE_raw={ece_raw:.3f} "
                  f"ECE_ts={ece_ts:.3f} ECE_qcts={ece_qcts:.3f} "
                  f"T0={T0:.3f} alpha={alpha:.3f}")

            results.append({
                "corruption": corr_name, "severity": sev, "qbar": qbar,
                "auc_raw": auc_raw,
                "ece_raw": ece_raw, "ece_ts": ece_ts, "ece_qcts": ece_qcts,
                "T0": T0, "alpha": alpha, "T_ts": T_ts,
            })

    df_res = pd.DataFrame(results)
    df_res.to_csv(OUT_DIR / "fundus_crossdomain.csv", index=False)

    # Global rho
    all_qbar, all_H_raw, all_H_ts, all_H_qcts = [], [], [], []
    for sev in [1, 2, 3, 4, 5]:
        q = 1.0 - sev / 5.0
        row_ref = df_res[df_res["severity"] == sev].iloc[0]
        T0_r, alpha_r, T_ts_r = row_ref["T0"], row_ref["alpha"], row_ref["T_ts"]
        n_sample = min(50, len(df_test))
        df_sub = df_test.sample(n_sample, random_state=sev)
        out_s = run_inference(model, feature_extractor, df_sub,
                              corruption=CORRUPTIONS[0], severity=sev, device=device)
        t_log = np.log(out_s["probs"] / (1 - out_s["probs"] + 1e-9) + 1e-9)
        p_ts_s = np.clip(1 / (1 + np.exp(-t_log / T_ts_r)), 1e-7, 1 - 1e-7)
        T_q = max(qcts_temperature(T0_r, alpha_r, q), 1e-3)
        p_q_s = np.clip(1 / (1 + np.exp(-t_log / T_q)), 1e-7, 1 - 1e-7)
        h_raw = out_s["entropies"]
        h_ts = -(p_ts_s * np.log(p_ts_s) + (1 - p_ts_s) * np.log(1 - p_ts_s))
        h_q = -(p_q_s * np.log(p_q_s) + (1 - p_q_s) * np.log(1 - p_q_s))
        all_qbar.extend([q] * len(h_raw))
        all_H_raw.extend(h_raw.tolist())
        all_H_ts.extend(h_ts.tolist())
        all_H_qcts.extend(h_q.tolist())

    rho_raw, p_raw = spearmanr(all_H_raw, all_qbar)
    rho_ts, p_ts_ = spearmanr(all_H_ts, all_qbar)
    rho_qcts, p_qcts_ = spearmanr(all_H_qcts, all_qbar)

    qcdi_grp = df_res.groupby("severity")
    QCDI_raw = float(qcdi_grp["ece_raw"].mean()[5] - qcdi_grp["ece_raw"].mean()[1])
    QCDI_ts = float(qcdi_grp["ece_ts"].mean()[5] - qcdi_grp["ece_ts"].mean()[1])
    QCDI_qcts = float(qcdi_grp["ece_qcts"].mean()[5] - qcdi_grp["ece_qcts"].mean()[1])

    summary = {
        "model": MODEL_NAME,
        "dataset": "APTOS 2019 (binary: No DR vs DR)",
        "n_test": len(df_test), "n_val": len(df_val),
        "corruptions": CORRUPTIONS,
        "QCDI_raw": round(QCDI_raw, 4),
        "QCDI_ts": round(QCDI_ts, 4),
        "QCDI_qcts": round(QCDI_qcts, 4),
        "rho_raw": round(float(rho_raw), 4), "p_raw": float(p_raw),
        "rho_ts": round(float(rho_ts), 4), "p_ts": float(p_ts_),
        "rho_qcts": round(float(rho_qcts), 4), "p_qcts": float(p_qcts_),
    }
    with open(OUT_DIR / "fundus_crossdomain.json", "w") as f:
        json.dump(summary, f, indent=2)

    print("\n=== Fundus Cross-domain Summary ===")
    print(f"  QCDI: raw={QCDI_raw:+.3f}  TS={QCDI_ts:+.3f}  QCTS={QCDI_qcts:+.3f}")
    print(f"  rho(H,qbar): raw={rho_raw:.3f}  TS={rho_ts:.3f}  QCTS={rho_qcts:.3f}")
    print(f"Saved to {OUT_DIR}")


if __name__ == "__main__":
    main()
