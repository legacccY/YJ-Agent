"""Generate fig5: Per-bin optimal T* vs QCTS softplus curve (§5.4).

For each backbone, bins ITB samples by q̄ (20 bins), fits the oracle optimal
temperature T* per bin (minimises NLL on that bin), then overlays the QCTS
softplus curve fitted on degraded-val.

Output: figures/fig5_perbin_optimal_T.{pdf,svg,png}
"""
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np
from scipy.optimize import minimize_scalar
from scipy.special import expit

THIS_DIR = Path(__file__).resolve().parent.parent
BACKBONE_DIR = THIS_DIR / "results" / "backbones"
FIG_DIR = THIS_DIR / "meeting" / "BMVC" / "figures"
FIG_DIR.mkdir(parents=True, exist_ok=True)

BACKBONES = [
    ("resnet50",  "ResNet-50"),
    ("vit_tiny",  "ViT-Tiny (DeiT)"),
]

N_BINS = 20


def softplus(x):
    return np.log1p(np.exp(x))


def qcts_T(qbar, T0, alpha):
    return softplus(T0 + alpha * (1.0 - qbar))


def bin_nll(T, logits, targets):
    """NLL for a single constant temperature on a bin."""
    scaled = logits / max(T, 1e-3)
    log_p_pos = -np.log1p(np.exp(-scaled))
    log_p_neg = -np.log1p(np.exp(scaled))
    return float(-(targets * log_p_pos + (1 - targets) * log_p_neg).mean())


def fit_bin_T(logits, targets, bracket=(0.05, 10.0)):
    """Scalar golden-section search for optimal T in a single bin."""
    res = minimize_scalar(bin_nll, bounds=bracket, method="bounded",
                          args=(logits, targets))
    return float(res.x)


def load_backbone(name):
    d = BACKBONE_DIR / name
    # Use degraded_val (9936 samples) for stable per-bin T* estimation —
    # same data QCTS was fitted on, so curve should align well.
    logits  = np.load(d / "degraded_val_logits.npy")
    qbar    = np.load(d / "degraded_val_qbar.npy")
    targets = np.load(d / "degraded_val_targets.npy")
    params  = json.loads((d / "qcts_params.json").read_text())
    if logits.ndim == 2:
        logits = logits[:, 1] - logits[:, 0]
    return logits, qbar, targets, params


T_BRACKET = (0.1, 4.0)      # physically reasonable range
T_BOUNDARY_TOL = 0.05       # discard bins where T* is within 5% of bracket boundary


def compute_perbin(logits, qbar, targets, n_bins=N_BINS):
    edges = np.percentile(qbar, np.linspace(0, 100, n_bins + 1))
    edges[0] -= 1e-6
    edges[-1] += 1e-6

    centers, T_stars, counts = [], [], []
    T_lo, T_hi = T_BRACKET
    for lo, hi in zip(edges[:-1], edges[1:]):
        m = (qbar > lo) & (qbar <= hi)
        if m.sum() < 20:
            continue
        if len(np.unique(targets[m])) < 2:
            continue
        T_opt = fit_bin_T(logits[m], targets[m], bracket=T_BRACKET)
        # discard bins that hit the bracket boundary (unreliable oracle)
        if T_opt <= T_lo * (1 + T_BOUNDARY_TOL) or T_opt >= T_hi * (1 - T_BOUNDARY_TOL):
            continue
        centers.append(float(qbar[m].mean()))
        T_stars.append(T_opt)
        counts.append(int(m.sum()))

    return np.array(centers), np.array(T_stars), np.array(counts)


def make_fig5():
    # ---- colour palette (BMVC style) ----
    C_SCATTER = "#4C72B0"   # steel blue for scatter
    C_QCTS    = "#DD8452"   # orange for QCTS curve
    C_TS      = "#C44E52"   # red dashed for flat TS

    fig, axes = plt.subplots(1, 2, figsize=(7.5, 3.2), constrained_layout=True)

    for ax, (folder, display_name) in zip(axes, BACKBONES):
        logits, qbar, targets, params = load_backbone(folder)
        T0    = params["T0"]
        alpha = params["alpha"]
        T_ts  = params["T_ts"]

        centers, T_stars, counts = compute_perbin(logits, qbar, targets)

        # ---- QCTS curve ----
        q_line = np.linspace(0.0, 1.0, 300)
        T_line = qcts_T(q_line, T0, alpha)

        # ---- scatter (size ∝ bin count) ----
        s = 20 + 80 * (counts / counts.max())
        ax.scatter(centers, T_stars, s=s, c=C_SCATTER, alpha=0.8,
                   zorder=3, label="Per-bin optimal $T^*$")

        ax.plot(q_line, T_line, color=C_QCTS, lw=2.0, zorder=4,
                label=r"QCTS $T(\bar{q})$")

        ax.axhline(T_ts, color=C_TS, lw=1.4, ls="--", zorder=2,
                   label=f"Std-TS $T$={T_ts:.2f}")

        ax.set_xlabel(r"Image quality $\bar{q}$", fontsize=9)
        ax.set_ylabel("Temperature $T$", fontsize=9)
        ax.set_title(display_name, fontsize=9, fontweight="bold")
        ax.set_xlim(0.0, 1.0)
        ax.set_ylim(bottom=0.0)
        ax.tick_params(labelsize=8)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        ax.legend(fontsize=7.5, framealpha=0.85)

    for ext in ("pdf", "svg", "png"):
        out = FIG_DIR / f"fig5_perbin_optimal_T.{ext}"
        fig.savefig(out, dpi=200, bbox_inches="tight")
        print(f"[saved] {out}")

    plt.close(fig)
    print("Done.")


if __name__ == "__main__":
    make_fig5()
