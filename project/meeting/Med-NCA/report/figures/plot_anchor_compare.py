"""
Figure 5: fig_anchor_compare
Grouped bar chart — Paper Med-NCA vs Our Reproduction vs Paper UNet
Tasks: Hippocampus (n=78) and Prostate (n=9)
All values hard-coded per report spec.
"""

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np
import os

OUT_DIR = os.path.dirname(os.path.abspath(__file__))

# ── Hard-coded data ──────────────────────────────────────────────────────────
# Groups
groups = ["Hippocampus", "Prostate"]

# Paper Med-NCA: mean ± std
paper_mednca_mean  = np.array([0.886, 0.838])
paper_mednca_std   = np.array([0.042, 0.083])

# Our reproduction: mean, 95% CI bounds → asymmetric yerr
our_mean           = np.array([0.8644, 0.672])
our_ci_lo          = np.array([0.8557, 0.575])   # lower CI bound
our_ci_hi          = np.array([0.8718, 0.765])   # upper CI bound
our_yerr_lo        = our_mean - our_ci_lo         # distance below mean
our_yerr_hi        = our_ci_hi - our_mean         # distance above mean

# Paper UNet baseline: mean ± std
paper_unet_mean    = np.array([0.858, 0.799])
paper_unet_std     = np.array([0.044, 0.099])

# ── Layout ───────────────────────────────────────────────────────────────────
n_groups = len(groups)
n_bars   = 3
x        = np.arange(n_groups)
width    = 0.22
gap      = 0.03   # extra gap between groups

# Center offsets for the 3 bars within each group
offsets  = np.array([-1, 0, 1]) * (width + gap)

# ── Colors & style ───────────────────────────────────────────────────────────
# Muted professional palette
COL_PAPER   = "#4C72B0"   # steel blue — Paper Med-NCA
COL_OUR     = "#DD8452"   # muted orange — Our reproduction (accent)
COL_UNET    = "#8DA0CB"   # light periwinkle — Paper UNet

EDGE_COLOR  = "white"
BAR_ALPHA   = 0.92

plt.rcParams.update({
    "font.family":     "DejaVu Sans",
    "font.size":       11,
    "axes.linewidth":  0.8,
    "xtick.labelsize": 11,
    "ytick.labelsize": 10,
})

fig, ax = plt.subplots(figsize=(7.0, 4.6))

# ── Draw bars ────────────────────────────────────────────────────────────────
# 1. Paper Med-NCA
b1 = ax.bar(x + offsets[0], paper_mednca_mean, width,
            yerr=paper_mednca_std,
            color=COL_PAPER, edgecolor=EDGE_COLOR, linewidth=0.6,
            alpha=BAR_ALPHA, capsize=4,
            error_kw=dict(elinewidth=1.2, ecolor="#333333", capthick=1.2),
            label="Paper Med-NCA", zorder=3)

# 2. Our reproduction (hatched for visual distinction)
b2 = ax.bar(x + offsets[1], our_mean, width,
            yerr=[our_yerr_lo, our_yerr_hi],
            color=COL_OUR, edgecolor="#8B4000", linewidth=0.8,
            alpha=BAR_ALPHA, capsize=4, hatch="//",
            error_kw=dict(elinewidth=1.2, ecolor="#5A2E00", capthick=1.2),
            label="Our Reproduction", zorder=3)

# 3. Paper UNet baseline
b3 = ax.bar(x + offsets[2], paper_unet_mean, width,
            yerr=paper_unet_std,
            color=COL_UNET, edgecolor=EDGE_COLOR, linewidth=0.6,
            alpha=BAR_ALPHA, capsize=4,
            error_kw=dict(elinewidth=1.2, ecolor="#333333", capthick=1.2),
            label="Paper UNet Baseline", zorder=3)

# ── Value labels on bars ──────────────────────────────────────────────────────
def label_bars(bars, values, fmt="{:.3f}", offset_frac=0.008):
    for bar, val in zip(bars, values):
        h = bar.get_height()
        ax.text(bar.get_x() + bar.get_width() / 2.0,
                h + offset_frac,
                fmt.format(val),
                ha="center", va="bottom",
                fontsize=9, color="#222222", fontweight="normal")

label_bars(b1, paper_mednca_mean)
label_bars(b2, our_mean)
label_bars(b3, paper_unet_mean)

# ── Axes formatting ───────────────────────────────────────────────────────────
ax.set_ylabel("Dice", fontsize=12)
ax.set_ylim(0, 1.08)
ax.set_xticks(x)
ax.set_xticklabels(groups, fontsize=12)
ax.yaxis.grid(True, alpha=0.3, linewidth=0.7, zorder=0)
ax.set_axisbelow(True)

# Despine top and right
ax.spines["top"].set_visible(False)
ax.spines["right"].set_visible(False)

# Legend
ax.legend(loc="upper right", framealpha=0.85, fontsize=10,
          edgecolor="#cccccc", handlelength=1.6)

plt.tight_layout()

# ── Save ─────────────────────────────────────────────────────────────────────
base = os.path.join(OUT_DIR, "fig_anchor_compare")
fig.savefig(base + ".pdf", bbox_inches="tight")
fig.savefig(base + ".png", dpi=200, bbox_inches="tight")
plt.close(fig)
print(f"Saved: {base}.pdf  and  {base}.png")
