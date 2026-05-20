"""D13-D14: Cross-modality QCTS evaluation on chest X-ray (chest-xray-pneumonia dataset).

Uses torchxrayvision DenseNet-121 (pretrained on all chest X-ray datasets) as backbone.
Applies imagecorruptions to create quality levels; corruption severity = q̄ proxy.
Fits QCTS on val subset (80% of clean test images) and evaluates on corrupted versions.

Output: results/crossdomain/chexray_crossdomain.json
        results/crossdomain/chexray_crossdomain.csv

Usage:
    python project/scripts/eval_chexray_crossdomain.py
    python project/scripts/eval_chexray_crossdomain.py --data-dir D:/YJ-Agent/data/chest_xray/chest_xray/test
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
import torchxrayvision as xrv
from scipy.optimize import minimize
from scipy.stats import spearmanr
from sklearn.metrics import roc_auc_score
from tqdm import tqdm

try:
    from imagecorruptions import corrupt
    HAS_IMAGECORRUPTIONS = True
except ImportError:
    HAS_IMAGECORRUPTIONS = False
    print("[warn] imagecorruptions not installed; using simple blur corruption only")

ROOT = Path("D:/YJ-Agent")
OUT_DIR = ROOT / "project/results/crossdomain"
PNEUMONIA_IDX = 8  # "Pneumonia" in torchxrayvision's all-dataset label list
IMG_SIZE = 224

CORRUPTIONS = [
    "gaussian_noise", "defocus_blur", "brightness", "contrast", "jpeg_compression"
] if HAS_IMAGECORRUPTIONS else ["blur"]


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--data-dir",
                   default="D:/YJ-Agent/data/chest_xray/chest_xray/test",
                   help="Path to chest-xray-pneumonia test/ folder")
    p.add_argument("--n-val", type=int, default=None,
                   help="Number of images for QCTS val fitting (default: 80% of test)")
    p.add_argument("--seed", type=int, default=42)
    return p.parse_args()


def load_xray_images(data_dir: Path, n: int = None, seed: int = 42):
    """Load NORMAL (0) and PNEUMONIA (1) images from the Kaggle dataset structure."""
    records = []
    for label, cls_name in [(0, "NORMAL"), (1, "PNEUMONIA")]:
        cls_dir = data_dir / cls_name
        if not cls_dir.exists():
            continue
        for img_path in sorted(cls_dir.glob("*.jpeg")):
            records.append({"path": str(img_path), "target": label})
    if not records:
        raise FileNotFoundError(f"No images found in {data_dir}")

    df = pd.DataFrame(records)
    if n is not None:
        df = df.sample(n=min(n, len(df)), random_state=seed).reset_index(drop=True)
    print(f"[data] {len(df)} images: {(df.target==0).sum()} NORMAL, {(df.target==1).sum()} PNEUMONIA")
    return df


def preprocess_xray(img_bgr: np.ndarray, size: int = IMG_SIZE) -> torch.Tensor:
    """torchxrayvision expects [-1024, 1024] grayscale tensor."""
    gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
    gray = cv2.resize(gray, (size, size))
    gray = gray.astype(np.float32) / 255.0 * 2048.0 - 1024.0
    return torch.tensor(gray[None, None])  # (1, 1, H, W)


def corrupt_image(img_bgr: np.ndarray, corruption: str, severity: int) -> np.ndarray:
    """Apply imagecorruptions corruption. Severity 1-5."""
    if not HAS_IMAGECORRUPTIONS:
        ksize = 2 * severity + 1
        return cv2.GaussianBlur(img_bgr, (ksize, ksize), 0)
    img_rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
    corrupted = corrupt(img_rgb, corruption_name=corruption, severity=severity)
    return cv2.cvtColor(corrupted, cv2.COLOR_RGB2BGR)


@torch.no_grad()
def run_inference(model, df: pd.DataFrame, corruption: str = None, severity: int = 0,
                  device="cpu") -> dict:
    """Run DenseNet on images (optionally corrupted). Returns probs, targets, entropies."""
    model.eval()
    probs, targets, entropies = [], [], []

    for _, row in tqdm(df.iterrows(), total=len(df), desc=f"infer {corruption or 'clean'} sev={severity}", leave=False):
        img = cv2.imread(row["path"])
        if img is None:
            continue
        if corruption:
            img = corrupt_image(img, corruption, severity)

        x = preprocess_xray(img).to(device)
        output = model(x)  # (1, 18) logits
        prob_pneumonia = torch.sigmoid(output[0, PNEUMONIA_IDX]).item()
        # Clamp to avoid log(0)
        p = max(min(prob_pneumonia, 1 - 1e-7), 1e-7)
        H = -(p * np.log(p) + (1 - p) * np.log(1 - p))

        probs.append(p)
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
    data_dir = Path(args.data_dir)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    np.random.seed(args.seed)

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"[init] loading torchxrayvision DenseNet-121 (all datasets)...")
    model = xrv.models.DenseNet(weights="densenet121-res224-all").to(device)
    model.eval()

    # Load all test images
    df = load_xray_images(data_dir, seed=args.seed)

    # Val/test split for QCTS fitting
    n_val = args.n_val or int(len(df) * 0.8)
    df_val = df.sample(n=n_val, random_state=args.seed)
    df_test = df.drop(df_val.index).reset_index(drop=True)
    df_val = df_val.reset_index(drop=True)
    print(f"[split] val={len(df_val)} test={len(df_test)}")

    # Run inference on val (clean) for QCTS fitting
    print("[step 1] val inference (clean)...")
    val_out = run_inference(model, df_val, device=device)
    val_probs = val_out["probs"]
    val_tgt = val_out["targets"]
    val_logits = np.log(val_probs / (1 - val_probs + 1e-9) + 1e-9)

    # Fit standard TS on val
    def ts_nll(T):
        T = max(T[0], 1e-3)
        p = 1 / (1 + np.exp(-val_logits / T))
        p = np.clip(p, 1e-7, 1 - 1e-7)
        return float(-(val_tgt * np.log(p) + (1 - val_tgt) * np.log(1 - p)).mean())
    T_ts = minimize(ts_nll, [1.0], method="L-BFGS-B", bounds=[(1e-3, 20)]).x[0]

    results = []
    for corr_name in CORRUPTIONS:
        for sev in [1, 2, 3, 4, 5]:
            qbar = 1.0 - sev / 5.0  # quality scalar: lower severity = higher quality

            # Fit QCTS on val with corruption-severity-based qbar
            # Use severity-independent val logits but corruption-aware qbar
            val_qbar = np.full(len(df_val), qbar)  # all val images have same qbar for this severity
            T0, alpha = fit_qcts(val_logits, val_qbar, val_tgt)

            # Evaluate on test images at this severity
            test_out = run_inference(model, df_test, corruption=corr_name,
                                     severity=sev, device=device)
            t_probs = test_out["probs"]
            t_tgt = test_out["targets"]
            t_logits = np.log(t_probs / (1 - t_probs + 1e-9) + 1e-9)

            # Raw
            ece_raw = compute_ece(t_probs, t_tgt)
            try:
                auc_raw = float(roc_auc_score(t_tgt, t_probs))
            except Exception:
                auc_raw = float("nan")

            # Standard TS
            p_ts = 1 / (1 + np.exp(-t_logits / T_ts))
            p_ts = np.clip(p_ts, 1e-7, 1 - 1e-7)
            ece_ts = compute_ece(p_ts, t_tgt)

            # QCTS
            T_qcts = np.maximum(qcts_temperature(T0, alpha, qbar), 1e-3)
            p_qcts = 1 / (1 + np.exp(-t_logits / T_qcts))
            p_qcts = np.clip(p_qcts, 1e-7, 1 - 1e-7)
            ece_qcts = compute_ece(p_qcts, t_tgt)

            print(f"  {corr_name} sev={sev} (q̄={qbar:.1f}) | "
                  f"AUC={auc_raw:.3f} ECE_raw={ece_raw:.3f} "
                  f"ECE_ts={ece_ts:.3f} ECE_qcts={ece_qcts:.3f} "
                  f"T0={T0:.3f} α={alpha:.3f}")

            results.append({
                "corruption": corr_name, "severity": sev, "qbar": qbar,
                "auc_raw": auc_raw,
                "ece_raw": ece_raw, "ece_ts": ece_ts, "ece_qcts": ece_qcts,
                "T0": T0, "alpha": alpha, "T_ts": T_ts,
            })

    # Summary: per-severity (averaged across corruptions) for ECE + entropy-quality correlation
    df_res = pd.DataFrame(results)
    df_res.to_csv(OUT_DIR / "chexray_crossdomain.csv", index=False)

    # Global rho: entropy vs qbar
    all_sev = [1, 2, 3, 4, 5]
    all_qbar, all_H_raw, all_H_ts, all_H_qcts = [], [], [], []
    for sev in all_sev:
        q = 1.0 - sev / 5.0
        row_ref = df_res[df_res["severity"] == sev].iloc[0]
        T0, alpha, T_ts = row_ref["T0"], row_ref["alpha"], row_ref["T_ts"]
        out_s = run_inference(model, df_test.sample(50, random_state=sev),
                              corruption=CORRUPTIONS[0], severity=sev, device=device)
        t_log = np.log(out_s["probs"] / (1 - out_s["probs"] + 1e-9) + 1e-9)
        p_ts_s = np.clip(1/(1+np.exp(-t_log/T_ts)), 1e-7, 1-1e-7)
        T_q = max(qcts_temperature(T0, alpha, q), 1e-3)
        p_q_s = np.clip(1/(1+np.exp(-t_log/T_q)), 1e-7, 1-1e-7)
        h_raw = out_s["entropies"]
        h_ts = -(p_ts_s*np.log(p_ts_s)+(1-p_ts_s)*np.log(1-p_ts_s))
        h_q = -(p_q_s*np.log(p_q_s)+(1-p_q_s)*np.log(1-p_q_s))
        all_qbar.extend([q]*len(h_raw))
        all_H_raw.extend(h_raw.tolist())
        all_H_ts.extend(h_ts.tolist())
        all_H_qcts.extend(h_q.tolist())

    rho_raw, p_raw = spearmanr(all_H_raw, all_qbar)
    rho_ts, p_ts_ = spearmanr(all_H_ts, all_qbar)
    rho_qcts, p_qcts_ = spearmanr(all_H_qcts, all_qbar)
    qcdi_raw = df_res.groupby("severity")["ece_raw"].mean()
    # QCDI = ECE(sev=5) - ECE(sev=1)  [sev=5 = LQ, sev=1 = HQ]
    QCDI_raw = float(qcdi_raw[5] - qcdi_raw[1])
    QCDI_ts = float(df_res.groupby("severity")["ece_ts"].mean()[5] -
                    df_res.groupby("severity")["ece_ts"].mean()[1])
    QCDI_qcts = float(df_res.groupby("severity")["ece_qcts"].mean()[5] -
                      df_res.groupby("severity")["ece_qcts"].mean()[1])

    summary = {
        "model": "DenseNet-121 (torchxrayvision, all datasets)",
        "dataset": "chest-xray-pneumonia test split",
        "n_test": len(df_test), "n_val": len(df_val),
        "corruptions": CORRUPTIONS,
        "QCDI_raw": round(QCDI_raw, 4),
        "QCDI_ts": round(QCDI_ts, 4),
        "QCDI_qcts": round(QCDI_qcts, 4),
        "rho_raw": round(float(rho_raw), 4), "p_raw": float(p_raw),
        "rho_ts": round(float(rho_ts), 4), "p_ts": float(p_ts_),
        "rho_qcts": round(float(rho_qcts), 4), "p_qcts": float(p_qcts_),
    }
    with open(OUT_DIR / "chexray_crossdomain.json", "w") as f:
        json.dump(summary, f, indent=2)

    print("\n=== CheXray Cross-domain Summary ===")
    print(f"  QCDI: raw={QCDI_raw:+.3f}  TS={QCDI_ts:+.3f}  QCTS={QCDI_qcts:+.3f}")
    print(f"  rho(H,q̄): raw={rho_raw:.3f}  TS={rho_ts:.3f}  QCTS={rho_qcts:.3f}")
    print(f"Saved to {OUT_DIR}")


if __name__ == "__main__":
    main()
