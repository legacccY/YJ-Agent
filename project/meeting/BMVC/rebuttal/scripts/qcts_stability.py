"""E1 (rebuttal, reviewer isv7): stability of the 2-parameter QCTS fit (T0, alpha).

We probe whether the QCTS fit is *stable* under (A) bootstrap resampling of the
degraded-val set and (B) reducing the fitting sample size. If (T0, alpha) barely
move, the "two parameters are unstable / overfit" concern is unfounded.

ZERO-DEVIATION NOTE
-------------------
The exact fit logic (softplus temperature T(qbar)=softplus(T0+alpha*(1-qbar)),
multi-start L-BFGS minimising the calibration NLL) is REUSED verbatim from
project/run_qcts_backbone.py (functions softplus / qcts_temperature / qcts_nll /
fit_qcts / binary_logit, lines 37-72). We do NOT re-implement the objective here.

Inputs (per backbone, already on disk):
  project/results/backbones/{name}/degraded_val_logits.npy   (N, 2)  -> binary_logit
  project/results/backbones/{name}/degraded_val_qbar.npy      (N,)
  project/results/backbones/{name}/degraded_val_targets.npy   (N,)

Outputs (project/meeting/BMVC/rebuttal/results/):
  qcts_stability.csv           long-format per (backbone, analysis, n, param)
  qcts_stability_summary.json  per-backbone bootstrap alpha CV + full-fit refs
  qcts_stability.pdf           2 subplots (T0, alpha) x=subsample size, 4 lines

Usage (main thread runs this, NOT the coder):
  python project/meeting/BMVC/rebuttal/scripts/qcts_stability.py
"""
import json
import os
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")  # headless / Windows safe
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

# --- Repo root & path wiring so we can reuse the paper's own fit code --------
ROOT = Path(__file__).resolve().parents[5]          # -> D:\YJ-Agent
PROJECT_DIR = ROOT / "project"
sys.path.insert(0, str(PROJECT_DIR))

# Reuse the EXACT fit logic from the paper's pipeline (no re-implementation).
from run_qcts_backbone import binary_logit, fit_qcts  # noqa: E402

BACKBONES = {
    "resnet50": "ResNet-50",
    "convnext_tiny": "ConvNeXt-Tiny",
    "swin_tiny": "Swin-Tiny",
    "vit_tiny": "ViT-Tiny",
}
BB_ROOT = PROJECT_DIR / "results" / "backbones"
OUT_DIR = ROOT / "project" / "meeting" / "BMVC" / "rebuttal" / "results"

N_BOOTSTRAP = 500
SUBSAMPLE_SIZES = [200, 500, 1000, 2000]   # "full" appended per-backbone
SUBSAMPLE_REPEATS = 100

# Fit-seed count matches the paper default (fit_qcts n_seeds=5).
FIT_SEEDS = 5


def load_backbone(key):
    d = BB_ROOT / key
    logits = binary_logit(np.load(d / "degraded_val_logits.npy"))
    qbar = np.load(d / "degraded_val_qbar.npy")
    targets = np.load(d / "degraded_val_targets.npy")
    return logits, qbar, targets


def bootstrap_fits(logits, qbar, targets, b=N_BOOTSTRAP):
    """B resample-with-replacement refits -> arrays of T0, alpha."""
    n = len(logits)
    rng = np.random.default_rng(12345)
    t0s = np.empty(b, dtype=np.float64)
    als = np.empty(b, dtype=np.float64)
    for i in range(b):
        idx = rng.integers(0, n, size=n)
        T0, alpha, _ = fit_qcts(
            logits[idx], qbar[idx], targets[idx], n_seeds=FIT_SEEDS
        )
        t0s[i] = T0
        als[i] = alpha
    return t0s, als


def subsample_fits(logits, qbar, targets, size, repeats=SUBSAMPLE_REPEATS):
    """`repeats` without-replacement subsamples of `size` -> T0, alpha arrays."""
    n = len(logits)
    rng = np.random.default_rng(777 + size)
    t0s = np.empty(repeats, dtype=np.float64)
    als = np.empty(repeats, dtype=np.float64)
    for i in range(repeats):
        idx = rng.choice(n, size=size, replace=False)
        T0, alpha, _ = fit_qcts(
            logits[idx], qbar[idx], targets[idx], n_seeds=FIT_SEEDS
        )
        t0s[i] = T0
        als[i] = alpha
    return t0s, als


def summarise(param_name, analysis, n, arr, n_repeats):
    return {
        "analysis": analysis,
        "n": int(n),
        "param": param_name,
        "mean": float(np.mean(arr)),
        "std": float(np.std(arr, ddof=1)) if len(arr) > 1 else 0.0,
        "ci_lo": float(np.percentile(arr, 2.5)),
        "ci_hi": float(np.percentile(arr, 97.5)),
        "n_repeats": int(n_repeats),
    }


def main():
    try:
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        rows = []
        summary = {}
        # per-backbone subsample curves for plotting: {key: {param: (xs, means, stds)}}
        curves = {}

        for key, pretty in BACKBONES.items():
            print(f"=== {pretty} ({key}) ===")
            logits, qbar, targets = load_backbone(key)
            n_full = len(logits)
            print(f"  loaded degraded_val n={n_full}")

            # --- full-set reference fit -------------------------------------
            T0_full, alpha_full, nll_full = fit_qcts(
                logits, qbar, targets, n_seeds=FIT_SEEDS
            )
            print(f"  [full fit] T0={T0_full:.4f} alpha={alpha_full:.4f} "
                  f"NLL={nll_full:.4f}")

            # --- (A) bootstrap ---------------------------------------------
            print(f"  bootstrap B={N_BOOTSTRAP} ...")
            t0_boot, al_boot = bootstrap_fits(logits, qbar, targets)
            rows.append({"backbone": pretty,
                         **summarise("T0", "bootstrap", n_full, t0_boot,
                                     N_BOOTSTRAP)})
            rows.append({"backbone": pretty,
                         **summarise("alpha", "bootstrap", n_full, al_boot,
                                     N_BOOTSTRAP)})
            alpha_cv = float(np.std(al_boot, ddof=1) / abs(np.mean(al_boot)))
            t0_cv = float(np.std(t0_boot, ddof=1) / abs(np.mean(t0_boot))) \
                if abs(np.mean(t0_boot)) > 1e-9 else float("nan")
            print(f"  [bootstrap] alpha mean={np.mean(al_boot):.4f} "
                  f"std={np.std(al_boot, ddof=1):.4f} CV={alpha_cv:.4f}")

            # --- (B) subsample sweep ---------------------------------------
            sizes = [s for s in SUBSAMPLE_SIZES if s < n_full] + [n_full]
            xs, t0_means, t0_stds, al_means, al_stds = [], [], [], [], []
            for size in sizes:
                if size >= n_full:
                    # full set: deterministic, single fit, std=0
                    t0_arr = np.array([T0_full])
                    al_arr = np.array([alpha_full])
                    reps = 1
                else:
                    t0_arr, al_arr = subsample_fits(logits, qbar, targets, size)
                    reps = SUBSAMPLE_REPEATS
                rows.append({"backbone": pretty,
                             **summarise("T0", "subsample", size, t0_arr, reps)})
                rows.append({"backbone": pretty,
                             **summarise("alpha", "subsample", size, al_arr,
                                         reps)})
                xs.append(size)
                t0_means.append(float(np.mean(t0_arr)))
                t0_stds.append(float(np.std(t0_arr, ddof=1)) if reps > 1 else 0.0)
                al_means.append(float(np.mean(al_arr)))
                al_stds.append(float(np.std(al_arr, ddof=1)) if reps > 1 else 0.0)
                print(f"  [subsample n={size}] T0={np.mean(t0_arr):.4f}"
                      f"±{t0_stds[-1]:.4f}  alpha={np.mean(al_arr):.4f}"
                      f"±{al_stds[-1]:.4f}")

            curves[pretty] = {
                "xs": xs,
                "T0": (t0_means, t0_stds),
                "alpha": (al_means, al_stds),
            }
            summary[pretty] = {
                "full_fit": {"T0": T0_full, "alpha": alpha_full,
                             "nll": nll_full, "n": int(n_full)},
                "bootstrap_alpha_mean": float(np.mean(al_boot)),
                "bootstrap_alpha_std": float(np.std(al_boot, ddof=1)),
                "bootstrap_alpha_cv": alpha_cv,
                "bootstrap_T0_mean": float(np.mean(t0_boot)),
                "bootstrap_T0_std": float(np.std(t0_boot, ddof=1)),
                "bootstrap_T0_cv": t0_cv,
            }

        # --- write CSV -----------------------------------------------------
        df = pd.DataFrame(rows, columns=["backbone", "analysis", "n", "param",
                                         "mean", "std", "ci_lo", "ci_hi",
                                         "n_repeats"])
        csv_path = OUT_DIR / "qcts_stability.csv"
        df.to_csv(csv_path, index=False)
        print(f"\n[saved] {csv_path}")

        # --- write JSON summary -------------------------------------------
        json_path = OUT_DIR / "qcts_stability_summary.json"
        json_path.write_text(json.dumps(summary, indent=2))
        print(f"[saved] {json_path}")

        # --- figure --------------------------------------------------------
        fig, axes = plt.subplots(1, 2, figsize=(11, 4.5))
        colors = plt.cm.tab10(np.linspace(0, 1, len(BACKBONES)))
        for (pretty, c) in zip(curves, colors):
            xs = curves[pretty]["xs"]
            for ax, param in zip(axes, ("T0", "alpha")):
                means, stds = curves[pretty][param]
                means = np.asarray(means)
                stds = np.asarray(stds)
                ax.plot(xs, means, "-o", color=c, label=pretty, markersize=4)
                ax.fill_between(xs, means - stds, means + stds,
                                color=c, alpha=0.18)
        for ax, param, ylab in zip(axes, ("T0", "alpha"),
                                   (r"$T_0$", r"$\alpha$")):
            ax.set_xlabel("subsample size (n)")
            ax.set_ylabel(ylab)
            ax.set_xscale("log")
            ax.grid(True, alpha=0.3)
            ax.set_title(param)
        axes[0].legend(fontsize=8, loc="best")
        fig.suptitle("QCTS fit stability across bootstrap resamples and "
                     "subsample sizes")
        fig.tight_layout(rect=[0, 0, 1, 0.96])
        pdf_path = OUT_DIR / "qcts_stability.pdf"
        fig.savefig(pdf_path, dpi=300)
        plt.close(fig)
        print(f"[saved] {pdf_path}")

        # --- conclusion-style summary print --------------------------------
        print("\n=== STABILITY CONCLUSION (bootstrap alpha CV per backbone) ===")
        for pretty in BACKBONES.values():
            s = summary[pretty]
            print(f"  {pretty}: alpha={s['bootstrap_alpha_mean']:.4f} "
                  f"(std={s['bootstrap_alpha_std']:.4f}, "
                  f"CV={s['bootstrap_alpha_cv']:.3%})  |  "
                  f"full-fit alpha={s['full_fit']['alpha']:.4f}, "
                  f"T0={s['full_fit']['T0']:.4f}")
        max_cv = max(summary[p]["bootstrap_alpha_cv"] for p in BACKBONES.values())
        print(f"  --> worst-case bootstrap alpha CV across 4 backbones = "
              f"{max_cv:.3%}; small CV => the 2-parameter QCTS fit is stable.")

    except Exception as exc:  # noqa: BLE001
        import traceback
        print(f"[ERROR] qcts_stability.py failed: {exc}")
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
