"""QCTS evaluation for arbitrary backbone — BMVC §5.4 universality.

Reads npy files produced by infer_backbone.py:
  results/backbones/{name}/degraded_val_logits.npy + qbar + targets
  results/backbones/{name}/itb_logits.npy + qbar + targets + subset

Pipeline per backbone:
  1. Fit QCTS (T0, alpha) on degraded val (multi-start L-BFGS, multi-seed)
  2. Fit standard TS on degraded val (single T)
  3. Apply QCTS + TS + raw to each ITB subset, compute AUC / ECE / QCDI / rho
  4. Bootstrap 95% CI on ECE (n=1000 by default)
  5. Append a row to results/backbones/section54_summary.csv

The key §5.4 claim we want to surface in the table:
  - TS reversal: ECE-LQ vs ECE-HQ flip after applying standard TS
  - QCTS rescues: applying QCTS recovers quality-aware behaviour on this backbone

Usage:
    python project/run_qcts_backbone.py --backbone-dir project/results/backbones/resnet50 \\
        --backbone-name "ResNet-50"
"""
import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.optimize import minimize
from scipy.special import expit
from scipy.stats import spearmanr
from sklearn.metrics import roc_auc_score

THIS_DIR = Path(__file__).resolve().parent
SUMMARY_CSV = THIS_DIR / "results/backbones/section54_summary.csv"


def softplus(x):
    return np.log1p(np.exp(x))


def binary_logit(logits_2col: np.ndarray) -> np.ndarray:
    """Convert (N, 2) logits to scalar binary logit l1 - l0."""
    return logits_2col[:, 1] - logits_2col[:, 0]


def qcts_temperature(params, qbar):
    T0, alpha = params
    return softplus(T0 + alpha * (1.0 - qbar))


def qcts_nll(params, logits, qbar, targets):
    T = np.maximum(qcts_temperature(params, qbar), 1e-3)
    scaled = logits / T
    log_p_pos = -np.log1p(np.exp(-scaled))
    log_p_neg = -np.log1p(np.exp(scaled))
    return float(-(targets * log_p_pos + (1 - targets) * log_p_neg).mean())


def fit_qcts(logits, qbar, targets, n_seeds: int = 5):
    best = (np.inf, None)
    for seed in range(n_seeds):
        rng = np.random.default_rng(seed)
        x0 = rng.uniform(-0.5, 1.5, size=2)
        res = minimize(
            qcts_nll, x0, args=(logits, qbar, targets),
            method="L-BFGS-B", bounds=[(-5, 5), (0, 10)],
            options={"maxiter": 500},
        )
        if res.fun < best[0]:
            best = (res.fun, res.x)
    T0, alpha = best[1]
    return float(T0), float(alpha), float(best[0])


def fit_ts(logits, targets):
    """Standard temperature scaling (single T) via L-BFGS."""
    def nll_ts(logT, *_):
        T = np.exp(logT[0])
        scaled = logits / T
        log_p_pos = -np.log1p(np.exp(-scaled))
        log_p_neg = -np.log1p(np.exp(scaled))
        return float(-(targets * log_p_pos + (1 - targets) * log_p_neg).mean())
    best = (np.inf, None)
    for seed in range(3):
        rng = np.random.default_rng(seed)
        x0 = rng.uniform(-1.0, 1.5, size=1)
        res = minimize(nll_ts, x0, method="L-BFGS-B", bounds=[(-3, 3)])
        if res.fun < best[0]:
            best = (res.fun, res.x)
    return float(np.exp(best[1][0])), float(best[0])


def binary_ece(prob_pos, targets, n_bins: int = 15) -> float:
    """Expected calibration error on the positive class confidence."""
    conf = np.maximum(prob_pos, 1 - prob_pos)
    pred = (prob_pos >= 0.5).astype(int)
    correct = (pred == targets).astype(float)
    bins = np.linspace(0, 1, n_bins + 1)
    ece = 0.0
    n = len(conf)
    for lo, hi in zip(bins[:-1], bins[1:]):
        mask = (conf > lo) & (conf <= hi) if lo > 0 else (conf >= lo) & (conf <= hi)
        if mask.sum() == 0:
            continue
        avg_conf = conf[mask].mean()
        acc = correct[mask].mean()
        ece += abs(avg_conf - acc) * mask.sum() / n
    return float(ece)


def bootstrap_ece(prob, targets, n_iter: int = 1000, seed: int = 0):
    rng = np.random.default_rng(seed)
    n = len(prob)
    vals = np.empty(n_iter, dtype=np.float64)
    for i in range(n_iter):
        idx = rng.integers(0, n, size=n)
        vals[i] = binary_ece(prob[idx], targets[idx])
    return float(np.percentile(vals, 2.5)), float(np.percentile(vals, 97.5))


def metrics_for(prob, targets, qbar, name: str, do_bootstrap: bool = True) -> dict:
    n = len(prob)
    auc = float(roc_auc_score(targets, prob)) if len(set(targets)) > 1 else float("nan")
    ece = binary_ece(prob, targets)
    H = -(prob * np.log(prob + 1e-9) + (1 - prob) * np.log(1 - prob + 1e-9))
    out = {
        "n": n, "auc": auc, "ece": ece,
        "mean_entropy": float(H.mean()),
    }
    if do_bootstrap and n >= 50:
        lo, hi = bootstrap_ece(prob, targets)
        out["ece_ci_lo"] = lo
        out["ece_ci_hi"] = hi
    print(f"  [{name}] n={n} auc={auc:.3f} ece={ece:.4f}")
    return out


def evaluate_method(method: str, logits, qbar, targets, subset, T0=None, alpha=None, T_ts=None):
    """Apply method to ITB logits, return dict {subset: metrics}."""
    if method == "raw":
        prob = expit(logits)
    elif method == "ts":
        prob = expit(logits / T_ts)
    elif method == "qcts":
        T = qcts_temperature([T0, alpha], qbar)
        prob = expit(logits / np.maximum(T, 1e-3))
    else:
        raise ValueError(method)

    rows = {}
    for sub in sorted(set(subset)):
        m = subset == sub
        rows[sub] = metrics_for(prob[m], targets[m], qbar[m], f"{method}/{sub}")

    # Global rho on full ITB (entropy ~ qbar)
    H = -(prob * np.log(prob + 1e-9) + (1 - prob) * np.log(1 - prob + 1e-9))
    rho, pval = spearmanr(H, qbar)
    rows["__rho"] = {"rho": float(rho), "pval": float(pval)}
    print(f"  [{method}] rho(H, qbar) on full ITB = {rho:.4f}  p={pval:.2e}")
    return rows


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--backbone-dir", required=True)
    parser.add_argument("--backbone-name", required=True, help="Pretty name for table row")
    parser.add_argument("--bootstrap-iter", type=int, default=1000)
    parser.add_argument("--seeds", type=int, default=5)
    parser.add_argument("--no-append", action="store_true",
                        help="Don't append to section54_summary.csv")
    parser.add_argument("--exclude-diverse", action="store_true",
                        help="Drop ITB-Diverse (Fitzpatrick17k cross-domain) before evaluation")
    args = parser.parse_args()

    bb_dir = Path(args.backbone_dir)
    print(f"=== {args.backbone_name}  ({bb_dir}) ===")

    # Load
    deg_logits = binary_logit(np.load(bb_dir / "degraded_val_logits.npy"))
    deg_qbar = np.load(bb_dir / "degraded_val_qbar.npy")
    deg_targets = np.load(bb_dir / "degraded_val_targets.npy")

    itb_logits = binary_logit(np.load(bb_dir / "itb_logits.npy"))
    itb_qbar = np.load(bb_dir / "itb_qbar.npy")
    itb_targets = np.load(bb_dir / "itb_targets.npy")
    itb_subset = np.load(bb_dir / "itb_subset.npy")

    if args.exclude_diverse:
        keep = itb_subset != "ITB-Diverse"
        itb_logits  = itb_logits[keep]
        itb_qbar    = itb_qbar[keep]
        itb_targets = itb_targets[keep]
        itb_subset  = itb_subset[keep]
        print("[filter] ITB-Diverse excluded (cross-domain Fitzpatrick17k)")

    print(f"[loaded] degraded_val n={len(deg_logits)}  itb n={len(itb_logits)}")

    # Fit on degraded val
    T0, alpha, nll_qcts = fit_qcts(deg_logits, deg_qbar, deg_targets, n_seeds=args.seeds)
    T_ts, nll_ts = fit_ts(deg_logits, deg_targets)
    print(f"[fit] QCTS T0={T0:.4f}  alpha={alpha:.4f}  NLL={nll_qcts:.4f}")
    print(f"[fit] TS   T={T_ts:.4f}  NLL={nll_ts:.4f}")

    # Save params
    params = {
        "backbone": args.backbone_name,
        "T0": T0, "alpha": alpha, "nll_qcts": nll_qcts,
        "T_ts": T_ts, "nll_ts": nll_ts,
        "deg_val_n": int(len(deg_logits)),
        "itb_n": int(len(itb_logits)),
    }
    (bb_dir / "qcts_params.json").write_text(json.dumps(params, indent=2))
    print(f"[saved] {bb_dir / 'qcts_params.json'}")

    # Evaluate on ITB
    print("\n--- Raw ---")
    raw = evaluate_method("raw", itb_logits, itb_qbar, itb_targets, itb_subset)
    print("\n--- TS ---")
    ts = evaluate_method("ts", itb_logits, itb_qbar, itb_targets, itb_subset, T_ts=T_ts)
    print("\n--- QCTS ---")
    qcts = evaluate_method("qcts", itb_logits, itb_qbar, itb_targets, itb_subset, T0=T0, alpha=alpha)

    # Summary row
    def grab(d, sub, key):
        return d.get(sub, {}).get(key, float("nan"))

    row = {
        "backbone": args.backbone_name,
        "T0": T0, "alpha": alpha, "T_ts": T_ts,
    }
    for method, d in [("raw", raw), ("ts", ts), ("qcts", qcts)]:
        for sub in ("ITB-LQ", "ITB-HQ", "ITB-Edge", "ITB-Diverse"):
            row[f"{method}_{sub}_ece"] = grab(d, sub, "ece")
            row[f"{method}_{sub}_auc"] = grab(d, sub, "auc")
        row[f"{method}_rho"] = d["__rho"]["rho"]
        row[f"{method}_qcdi"] = grab(d, "ITB-LQ", "ece") - grab(d, "ITB-HQ", "ece")

    summary_csv = SUMMARY_CSV
    summary_csv.parent.mkdir(parents=True, exist_ok=True)
    if summary_csv.exists() and not args.no_append:
        existing = pd.read_csv(summary_csv)
        existing = existing[existing["backbone"] != args.backbone_name]
        df = pd.concat([existing, pd.DataFrame([row])], ignore_index=True)
    else:
        df = pd.DataFrame([row])
    df.to_csv(summary_csv, index=False)
    print(f"\n[saved] {summary_csv}")

    # Headline numbers
    print("\n=== Headline (this backbone) ===")
    print(f"  Raw:   QCDI={row['raw_qcdi']:.4f}  rho={row['raw_rho']:.4f}")
    print(f"  TS:    QCDI={row['ts_qcdi']:.4f}  rho={row['ts_rho']:.4f}  (sign flip vs raw? {np.sign(row['ts_rho']) != np.sign(row['raw_rho'])})")
    print(f"  QCTS:  QCDI={row['qcts_qcdi']:.4f}  rho={row['qcts_rho']:.4f}")


if __name__ == "__main__":
    main()
