"""fig10: Prior-induced representation collapse (S2.4b).

Reads kl_history and val_metric_history from experiment_state.json.
Dual-axis: KL suppression (left) + AUC degradation (right).

Usage:
  cd D:/YJ-Agent/project
  python plot_kl_collapse.py
"""

import json
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

STATE_PATH = Path(__file__).parent.parent / "log" / "experiment_state.json"
OUT_PATH   = Path(__file__).parent / "results" / "figures" / "fig10_kl_collapse.png"
OUT_PATH.parent.mkdir(parents=True, exist_ok=True)


def main():
    if not STATE_PATH.exists():
        print(f"State file not found: {STATE_PATH}")
        sys.exit(1)

    with open(STATE_PATH) as f:
        state = json.load(f)

    prog       = state["progress"]
    auc_hist   = prog.get("val_metric_history", [])
    kl_hist    = prog.get("kl_history", [])
    n          = min(len(auc_hist), len(kl_hist))

    if n == 0:
        print("No epoch history found in state.json")
        sys.exit(1)

    epochs   = list(range(1, n + 1))
    kl_vals  = kl_hist[:n]
    auc_vals = auc_hist[:n]

    print(f"Epochs: {n}")
    for ep, kl, auc in zip(epochs, kl_vals, auc_vals):
        print(f"  Epoch {ep:2d}  KL={kl:.4f}  AUC={auc:.4f}")

    # ── Figure ────────────────────────────────────────────────────────────────
    fig, ax1 = plt.subplots(figsize=(7, 4.5))

    color_kl  = "#d62728"
    color_auc = "#1f77b4"

    ax1.set_xlabel("Epoch", fontsize=12)
    ax1.set_ylabel("Mean KL Divergence (train)", color=color_kl, fontsize=12)
    ax1.plot(epochs, kl_vals, color=color_kl, linewidth=2.5, marker="o",
             markersize=6, label="KL divergence")
    ax1.tick_params(axis="y", labelcolor=color_kl)
    ax1.set_xticks(epochs)

    ax2 = ax1.twinx()
    ax2.set_ylabel("Validation AUC-ROC", color=color_auc, fontsize=12)
    ax2.plot(epochs, auc_vals, color=color_auc, linewidth=2.5, marker="s",
             markersize=6, linestyle="--", label="Val AUC")
    ax2.axhline(0.5, color=color_auc, linestyle=":", alpha=0.4, linewidth=1.5)
    ax2.text(epochs[-1] * 0.98, 0.502, "Random", color=color_auc,
             alpha=0.6, ha="right", fontsize=9)
    ax2.tick_params(axis="y", labelcolor=color_auc)
    ax2.set_ylim(0.45, max(auc_vals) * 1.05)

    # Annotation
    ax1.annotate(
        "Prior dominates:\nKL forced to 0\nmu collapsed to prior mean",
        xy=(epochs[3], kl_vals[3]), xytext=(epochs[2] + 0.3, kl_vals[0] * 0.6),
        arrowprops=dict(arrowstyle="->", color="gray"),
        fontsize=8.5, color="gray",
    )

    lines1, labels1 = ax1.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax1.legend(lines1 + lines2, labels1 + labels2, loc="upper right", fontsize=10)

    plt.title(
        "Tight Prior Collapse: σ₀²=0.1 + β=0.1 + 1536-D B3 Features\n"
        "Prior forces KL→0, destroying discriminative representations",
        fontsize=10.5
    )
    fig.tight_layout()
    plt.savefig(OUT_PATH, dpi=300, bbox_inches="tight")
    plt.close()
    print(f"\nFigure saved: {OUT_PATH}")

    # Acceptance check
    min_auc = min(auc_vals)
    print(f"\nAcceptance check:")
    print(f"  Min AUC < 0.55: {min_auc:.4f}  {'PASS' if min_auc < 0.55 else 'FAIL'}")
    print(f"  Final KL near 0: {kl_vals[-1]:.4f}  {'PASS (prior dominates)' if kl_vals[-1] < 1.0 else 'partial'}")


if __name__ == "__main__":
    main()
