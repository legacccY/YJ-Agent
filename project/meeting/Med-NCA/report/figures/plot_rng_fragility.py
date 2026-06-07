"""
Figure: fig_rng_fragility  (REVISED — corrected mechanism)
Two panels, both on Prostate (the controlled, aggressive regime):

(a) Implementation change. Official BackboneNCA samples the fire mask on the
    CPU (seed-controlled); the "fast" subclass samples it on the GPU. This is
    a genuine RNG-STREAM change -> training collapses 0.672 -> 0.0.

(b) Same seed, same official code, two runs. Epoch-1 training loss is 1.25
    (run 1435378, converged to 0.672) vs 4.33 (run 1436781, diverged). Fixed
    seeds do NOT make the trajectory repeatable, because the deciding
    perturbation is cuDNN/atomicAdd floating-point NONDETERMINISM (not covered
    by torch.manual_seed), amplified by the 64-step x 2-level recurrence.

All values hard-coded per report spec.
"""

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import os

OUT = os.path.dirname(os.path.abspath(__file__))

plt.rcParams.update({
    "font.family":       "DejaVu Sans",
    "font.size":         9,
    "axes.titlesize":    10,
    "axes.labelsize":    9,
    "axes.spines.top":   False,
    "axes.spines.right": False,
    "figure.dpi":        150,
})
COL_OK   = "#2CA084"   # converged / good
COL_FAIL = "#C0392B"   # diverged / bad
COL_GREY = "#9aa0a6"
HEALTHY  = 1.25
DIV_THR  = 3.0

fig, (axA, axB) = plt.subplots(1, 2, figsize=(8.4, 3.6))

# ── (a) implementation change: official CPU-rand vs fast GPU-rand ─────────────
labels_a = ["Official\n(CPU-rand\nfire mask)", "Fast subclass\n(GPU-rand\nfire mask)"]
dice_a   = [0.672, 0.0]
cols_a   = [COL_OK, COL_FAIL]
x = np.arange(2)
axA.bar(x, dice_a, color=cols_a, width=0.6, edgecolor="white", linewidth=0.8, zorder=3)
axA.axhline(0.799, ls="--", lw=1.0, color=COL_GREY, zorder=1)
axA.text(1.45, 0.799 + 0.01, "U-Net 0.799", ha="right", va="bottom", fontsize=7.5, color="#666")
for xi, d in zip(x, dice_a):
    axA.text(xi, d + 0.02, ("0.0 (diverged)" if d == 0 else f"{d:.3f}"),
             ha="center", va="bottom", fontsize=8.5, fontweight="bold",
             color=(COL_FAIL if d == 0 else COL_OK))
axA.set_xticks(x); axA.set_xticklabels(labels_a, fontsize=7.8)
axA.set_ylabel("per-volume Dice")
axA.set_ylim(0, 0.95)
axA.set_title("(a)  RNG-stream change\n(mathematically equivalent)",
              loc="left", fontweight="bold", fontsize=9)

# ── (b) same seed 42, two official runs: epoch-1 loss decides basin ───────────
labels_b = ["run 1435378\nseed 42", "run 1436781\nseed 42"]
ep1_b    = [1.25, 4.33]
cols_b   = [COL_OK, COL_FAIL]
outcome  = ["converged\n-> Dice 0.672", "diverged\n-> Dice 0"]
xb = np.arange(2)
axB.bar(xb, ep1_b, color=cols_b, width=0.6, edgecolor="white", linewidth=0.8, zorder=3)
axB.axhline(HEALTHY, ls="--", lw=1.0, color=COL_GREY, zorder=1)
axB.text(1.45, HEALTHY + 0.08, "healthy ~1.25", ha="right", va="bottom", fontsize=7.5, color="#666")
axB.axhspan(DIV_THR, 6.0, color=COL_FAIL, alpha=0.06, zorder=0)
for xi, v, o in zip(xb, ep1_b, outcome):
    axB.text(xi, v + 0.12, f"{v:.2f}", ha="center", va="bottom", fontsize=8.5, fontweight="bold",
             color=(COL_FAIL if v > DIV_THR else COL_OK))
    axB.text(xi, 0.45, o, ha="center", va="bottom", fontsize=7.3,
             color="white", fontweight="bold")
axB.set_xticks(xb); axB.set_xticklabels(labels_b, fontsize=7.8)
axB.set_ylabel("epoch-1 training loss")
axB.set_ylim(0, 6.0)
axB.set_title("(b)  same seed, same code\n(cuDNN FP nondeterminism)",
              loc="left", fontweight="bold", fontsize=9)

fig.tight_layout(w_pad=2.2)
for ext in ("pdf", "png"):
    fig.savefig(os.path.join(OUT, f"fig_rng_fragility.{ext}"), bbox_inches="tight")
print("saved fig_rng_fragility.pdf / .png")
