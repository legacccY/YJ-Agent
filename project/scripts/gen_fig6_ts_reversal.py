"""Generate fig6: TS reversal as ECE-LQ/HQ flip (§5.4).

Two-backbone comparison bar chart:
  - For ViT-Tiny: standard TS flips the ECE gap (QCDI sign reversal)
                  → LQ was harder to calibrate, after TS HQ becomes harder
  - For ResNet-50: TS is neutral; QCDI sign is stable

Data source: section54_summary.csv (pre-computed in run_qcts_backbone.py)

Output: figures/fig6_ts_reversal.{pdf,svg,png}
"""
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

THIS_DIR = Path(__file__).resolve().parent.parent
SUMMARY_CSV = THIS_DIR / "results" / "backbones" / "section54_summary.csv"
FIG_DIR = THIS_DIR / "meeting" / "BMVC" / "figures"
FIG_DIR.mkdir(parents=True, exist_ok=True)

import pandas as pd

# ── Data ────────────────────────────────────────────────────────────────────
df = pd.read_csv(SUMMARY_CSV)
# Use the rows with Diverse excluded (ViT-Tiny DeiT, ResNet-50)
# These are the "exclude-diverse" runs used for §5.4
BACKBONE_ROWS = {
    "ViT-Tiny":  df[df["backbone"] == "ViT-Tiny (DeiT)"].iloc[0],
    "ResNet-50": df[df["backbone"] == "ResNet-50"].iloc[0],
}

METHODS   = ["raw", "ts", "qcts"]
METHOD_LABELS = ["Raw", "Std-TS", "QCTS"]

C_LQ = "#EE6677"
C_HQ = "#4477AA"
C_QCDI_POS = "#2CA02C"   # QCDI > 0 (correct ordering)
C_QCDI_NEG = "#D62728"   # QCDI < 0 (reversed ordering)


def make_fig6():
    fig, axes = plt.subplots(1, 2, figsize=(8.0, 3.4), constrained_layout=True)

    for ax, (backbone_name, row) in zip(axes, BACKBONE_ROWS.items()):
        ece_lq = [row[f"{m}_ITB-LQ_ece"] for m in METHODS]
        ece_hq = [row[f"{m}_ITB-HQ_ece"] for m in METHODS]
        qcdi   = [lq - hq for lq, hq in zip(ece_lq, ece_hq)]

        x = np.arange(len(METHODS))
        w = 0.30

        bars_lq = ax.bar(x - w/2, ece_lq, w, color=C_LQ, alpha=0.85,
                         label="ECE-LQ (degraded)", zorder=3)
        bars_hq = ax.bar(x + w/2, ece_hq, w, color=C_HQ, alpha=0.85,
                         label="ECE-HQ (clean)", zorder=3)

        # Annotate QCDI arrow between the two bars and the value
        for i, (lq_v, hq_v, qcdi_v) in enumerate(zip(ece_lq, ece_hq, qcdi)):
            top = max(lq_v, hq_v)
            col = C_QCDI_POS if qcdi_v >= 0 else C_QCDI_NEG
            sign = "+" if qcdi_v >= 0 else ""
            ax.text(i, top + 0.003, f"ΔECE={sign}{qcdi_v:.3f}",
                    ha="center", va="bottom", fontsize=7.2,
                    color=col, fontweight="bold")

        ax.set_xticks(x)
        ax.set_xticklabels(METHOD_LABELS, fontsize=9)
        ax.set_ylabel("ECE ↓", fontsize=9)
        ax.set_title(backbone_name, fontsize=10, fontweight="bold")
        ax.set_ylim(0, ax.get_ylim()[1] * 1.25)
        ax.tick_params(labelsize=8)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        ax.legend(fontsize=7.5, loc="upper right", framealpha=0.85)

        # Reversal annotation for ViT-Tiny
        if backbone_name == "ViT-Tiny":
            ax.annotate("ECE gap\nreverses",
                        xy=(1, max(ece_lq[1], ece_hq[1]) + 0.008),
                        xytext=(1.5, max(ece_lq[1], ece_hq[1]) + 0.022),
                        fontsize=7.5, color=C_QCDI_NEG, ha="center",
                        arrowprops=dict(arrowstyle="->", color=C_QCDI_NEG, lw=1.0))

    for ext in ("pdf", "svg", "png"):
        out = FIG_DIR / f"fig6_ts_reversal.{ext}"
        fig.savefig(out, dpi=200, bbox_inches="tight")
        print(f"[saved] {out}")
    plt.close(fig)
    print("Done.")


if __name__ == "__main__":
    make_fig6()
