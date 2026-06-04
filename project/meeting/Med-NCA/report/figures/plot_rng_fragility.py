"""
Figure 6: fig_rng_fragility  ★ headline figure
Grouped bar chart — Fast-impl (GPU-rand) vs Official (CPU-rand)
Tasks: Hippocampus and Prostate
Dramatic finding: Prostate Fast-impl diverged (Dice = 0.0),
                  Official converged (Dice = 0.672).
All values hard-coded per report spec.
"""

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import matplotlib.patheffects as pe
import numpy as np
import os

OUT_DIR = os.path.dirname(os.path.abspath(__file__))

# ── Hard-coded data ──────────────────────────────────────────────────────────
groups = ["Hippocampus", "Prostate"]

# Fast-impl (GPU-rand, FastBackboneNCA)
fast_dice = np.array([0.866, 0.000])

# Official (CPU-rand, BackboneNCA)
offic_dice = np.array([0.8644, 0.672])

# ── Colors ───────────────────────────────────────────────────────────────────
# Converged: teal; Diverged: muted red/grey
COL_FAST_OK   = "#2CA084"   # teal-green — Fast converged (Hippocampus)
COL_FAST_FAIL = "#C0392B"   # red — Fast diverged (Prostate)
COL_OFFIC     = "#2CA084"   # same teal for official (both converged)

# We'll assign colors per bar individually
fast_colors  = [COL_FAST_OK, COL_FAST_FAIL]
offic_colors = [COL_OFFIC,   COL_OFFIC]

plt.rcParams.update({
    "font.family":     "DejaVu Sans",
    "font.size":       11,
    "axes.linewidth":  0.8,
    "xtick.labelsize": 11,
    "ytick.labelsize": 10,
})

fig, ax = plt.subplots(figsize=(7.2, 5.0))

n_groups = len(groups)
x        = np.arange(n_groups)
width    = 0.28
gap      = 0.04

offsets  = np.array([-0.5, 0.5]) * (width + gap)

# ── Draw bars individually to allow per-bar color ────────────────────────────
fast_bars  = []
offic_bars = []

for i in range(n_groups):
    # Fast bar
    b = ax.bar(x[i] + offsets[0], fast_dice[i], width,
               color=fast_colors[i],
               edgecolor="white" if fast_dice[i] > 0 else "#8B0000",
               linewidth=0.8 if fast_dice[i] > 0 else 1.5,
               alpha=0.90, zorder=3)
    fast_bars.append(b[0])

    # Official bar
    b = ax.bar(x[i] + offsets[1], offic_dice[i], width,
               color=offic_colors[i],
               edgecolor="white", linewidth=0.8,
               alpha=0.72, hatch="\\\\",   # subtle hatch to distinguish
               zorder=3)
    offic_bars.append(b[0])

# ── Value labels ──────────────────────────────────────────────────────────────
label_offset = 0.012

for i, (bar, val) in enumerate(zip(fast_bars, fast_dice)):
    if val > 0.01:
        ax.text(bar.get_x() + bar.get_width() / 2.0,
                val + label_offset,
                f"{val:.3f}",
                ha="center", va="bottom", fontsize=9.5, color="#111111")
    # Zero bar handled by annotation below

for i, (bar, val) in enumerate(zip(offic_bars, offic_dice)):
    ax.text(bar.get_x() + bar.get_width() / 2.0,
            val + label_offset,
            f"{val:.3f}",
            ha="center", va="bottom", fontsize=9.5, color="#111111")

# ── "Diverged" annotation on Prostate Fast bar ───────────────────────────────
prostate_idx = 1
fast_prostate_bar = fast_bars[prostate_idx]
bx = fast_prostate_bar.get_x() + fast_prostate_bar.get_width() / 2.0

# Text above the (zero-height) bar
ax.text(bx, 0.045,
        "diverged\n(logits→ −1e9)",
        ha="center", va="bottom",
        fontsize=8.5, color="#8B0000", fontstyle="italic",
        multialignment="center",
        bbox=dict(boxstyle="round,pad=0.25", facecolor="#FDECEA",
                  edgecolor="#C0392B", linewidth=0.8, alpha=0.90))

# ── Story annotation box ──────────────────────────────────────────────────────
story = (
    "Mathematically equivalent fire-mask sampling;\n"
    "only the RNG device/stream differs."
)
ax.text(0.98, 0.97, story,
        transform=ax.transAxes,
        ha="right", va="top",
        fontsize=9, color="#333333", style="italic",
        bbox=dict(boxstyle="round,pad=0.4", facecolor="#F0F4F8",
                  edgecolor="#AABBCC", linewidth=0.8, alpha=0.92))

# ── Axes formatting ───────────────────────────────────────────────────────────
ax.set_ylabel("Dice", fontsize=12)
ax.set_ylim(0, 1.12)
ax.set_xticks(x)
ax.set_xticklabels(groups, fontsize=12)
ax.yaxis.grid(True, alpha=0.3, linewidth=0.7, zorder=0)
ax.set_axisbelow(True)

ax.spines["top"].set_visible(False)
ax.spines["right"].set_visible(False)

# ── Legend ────────────────────────────────────────────────────────────────────
# Manual legend entries: Fast (OK), Fast (fail), Official
patch_fast_ok   = mpatches.Patch(facecolor=COL_FAST_OK,   edgecolor="white",
                                  alpha=0.90, label="Fast-impl (GPU-rand)")
patch_fast_fail = mpatches.Patch(facecolor=COL_FAST_FAIL,  edgecolor="#8B0000",
                                  linewidth=1.5, alpha=0.90,
                                  label="Fast-impl (GPU-rand) — diverged")
patch_offic     = mpatches.Patch(facecolor=COL_OFFIC,      edgecolor="white",
                                  alpha=0.72, hatch="\\\\",
                                  label="Official (CPU-rand)")

# Simplified 2-entry legend (Fast / Official), with note that red = diverged
patch_fast  = mpatches.Patch(facecolor=COL_FAST_OK,  edgecolor="white",
                              alpha=0.90, label="Fast-impl (GPU-rand)")
patch_off   = mpatches.Patch(facecolor=COL_OFFIC,    edgecolor="white",
                              alpha=0.72, hatch="\\\\",
                              label="Official (CPU-rand)")

ax.legend(handles=[patch_fast, patch_off],
          loc="upper left", framealpha=0.85, fontsize=10,
          edgecolor="#cccccc", handlelength=1.8)

plt.tight_layout()

# ── Save ─────────────────────────────────────────────────────────────────────
base = os.path.join(OUT_DIR, "fig_rng_fragility")
fig.savefig(base + ".pdf", bbox_inches="tight")
fig.savefig(base + ".png", dpi=200, bbox_inches="tight")
plt.close(fig)
print(f"Saved: {base}.pdf  and  {base}.png")
