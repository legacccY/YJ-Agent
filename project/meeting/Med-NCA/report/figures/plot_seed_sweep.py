"""
Figure (NEW headline): fig_seed_sweep
Three-panel summary of the 9-seed x 1000-epoch zero-deviation Prostate sweep.

(a) Epoch-1 training loss for all 9 seeds -> bimodal: 2 land in the "good basin"
    (loss ~1.3), 7 land in the "bad basin" (loss 3.3-4.5) on the very first epoch.
(b) Full per-epoch loss trajectories -> the 2 good-basin seeds (43, 46) train
    healthily for 60 / 121 epochs, then collapse off a cliff in a single epoch.
(c) Crash-epoch timeline across all 11 official-config attempts (9 fresh seeds +
    2 history 1000-ep runs + 1 partial 301-ep run). 0 / 11 ever reach 1000 ep.

Data: results/r2_seed_sweep_traces.csv, results/r2_seed_sweep_summary.json
No GPU / no dataset needed.
"""

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import json, os

HERE = os.path.dirname(os.path.abspath(__file__))
RES  = os.path.normpath(os.path.join(HERE, "..", "..", "results"))

traces  = pd.read_csv(os.path.join(RES, "r2_seed_sweep_traces.csv"))
summary = json.load(open(os.path.join(RES, "r2_seed_sweep_summary.json"), encoding="utf-8"))

# ── style ────────────────────────────────────────────────────────────────────
plt.rcParams.update({
    "font.family":     "DejaVu Sans",
    "font.size":       9,
    "axes.titlesize":  10,
    "axes.labelsize":  9,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "figure.dpi":      150,
})
COL_GOOD = "#2CA084"   # teal  — good basin / healthy
COL_BAD  = "#C0392B"   # red   — bad basin / diverged
COL_GREY = "#9aa0a6"
HEALTHY  = 1.25        # reference healthy ep1 loss (run 1435378)
DIV_THR  = 3.0         # divergence signature threshold

seeds = [42, 43, 44, 45, 46, 47, 48, 49, 50]

fig, (axA, axB, axC) = plt.subplots(1, 3, figsize=(13.0, 3.7))

# ── (a) ep1 loss bimodal ─────────────────────────────────────────────────────
ep1 = []
for s in seeds:
    g = traces[(traces.seed == s) & (traces.epoch == 1)]
    ep1.append(g.train_loss.values[0])
ep1 = np.array(ep1)
colors = [COL_GOOD if v < DIV_THR else COL_BAD for v in ep1]
x = np.arange(len(seeds))
axA.bar(x, ep1, color=colors, edgecolor="white", linewidth=0.6, zorder=3)
axA.axhline(HEALTHY, ls="--", lw=1.0, color=COL_GREY, zorder=2)
axA.text(len(seeds) - 0.4, HEALTHY + 0.12, "healthy start ~1.25",
         ha="right", va="bottom", fontsize=7.5, color="#555")
axA.axhspan(DIV_THR, axA.get_ylim()[1] if axA.get_ylim()[1] > DIV_THR else 6.5,
            color=COL_BAD, alpha=0.05, zorder=0)
axA.set_xticks(x)
axA.set_xticklabels([str(s) for s in seeds])
axA.set_xlabel("random seed")
axA.set_ylabel("epoch-1 training loss")
axA.set_title("(a)  basin decided at epoch 1", loc="left", fontweight="bold")
axA.set_ylim(0, 6.5)
# annotate the 2 good ones
for i, s in enumerate(seeds):
    if ep1[i] < DIV_THR:
        axA.text(i, ep1[i] + 0.12, "good", ha="center", va="bottom",
                 fontsize=7.5, color=COL_GOOD, fontweight="bold")
axA.text(0.02, 0.97, "2/9 good basin · 7/9 bad basin",
         transform=axA.transAxes, ha="left", va="top", fontsize=7.5,
         color="#444", style="italic")

# ── (b) loss trajectories with cliffs ────────────────────────────────────────
for s in seeds:
    g = traces[traces.seed == s].sort_values("epoch")
    is_good = g[g.epoch == 1].train_loss.values[0] < DIV_THR
    if is_good:
        axB.plot(g.epoch, g.train_loss, lw=1.8, color=COL_GOOD, zorder=4,
                 label=f"seed {s} (good→cliff)")
    else:
        axB.plot(g.epoch, g.train_loss, lw=0.9, color=COL_BAD, alpha=0.55, zorder=2)
axB.axhline(DIV_THR, ls=":", lw=1.0, color=COL_GREY, zorder=1)
# cliff annotations
axB.annotate("seed 43\ncliff @ ep61", xy=(61, 3.9), xytext=(78, 2.3),
             fontsize=7.5, color=COL_GOOD, fontweight="bold",
             arrowprops=dict(arrowstyle="->", color=COL_GOOD, lw=1.0))
axB.annotate("seed 46\ncliff @ ep122", xy=(122, 4.0), xytext=(120, 1.4),
             fontsize=7.5, color="#1f7a66", fontweight="bold",
             arrowprops=dict(arrowstyle="->", color="#1f7a66", lw=1.0))
axB.text(8, 5.6, "7 seeds: flat-high\nfrom ep1 (diverged)",
         fontsize=7.5, color=COL_BAD)
axB.set_xlabel("epoch")
axB.set_ylabel("training loss")
axB.set_title("(b)  no safe zone: healthy runs collapse mid-training",
              loc="left", fontweight="bold")
axB.set_xlim(0, 175)
axB.set_ylim(0, 6.5)

# ── (c) crash-epoch timeline, 0/11 reach 1000 ────────────────────────────────
# fresh seeds + history runs
rows = []
for s in seeds:
    d = summary[str(s)]
    crash = d["crash_ep"] if d["crash_ep"] else d["max_ep_reached"]
    good  = d["ep1_loss"] < DIV_THR
    rows.append((f"seed {s}", crash, good, "fresh"))
hist = summary["_global"]["history_runs"]
rows.append(("1435378*", 301, True,  "hist"))   # stopped manually, not crashed
rows.append(("1436075",  hist["1436075_1000ep"]["crash_ep"], True, "hist"))
rows.append(("1436470",  hist["1436470_1000ep"]["crash_ep"], True, "hist"))

rows = sorted(rows, key=lambda r: r[1])
labels = [r[0] for r in rows]
xs     = [r[1] for r in rows]
y      = np.arange(len(rows))
bar_cols = [COL_GOOD if r[2] else COL_BAD for r in rows]
axC.barh(y, xs, color=bar_cols, edgecolor="white", linewidth=0.6, height=0.62, zorder=3)
for yi, (lab, xv, good, kind) in zip(y, rows):
    tag = "stopped" if lab.endswith("*") else "crash"
    axC.text(xv + 12, yi, f"ep{xv} ({tag})", va="center", fontsize=7, color="#444")
axC.axvline(1000, ls="--", lw=1.2, color="#333", zorder=2)
axC.text(1000, len(rows) - 0.3, "paper: 1000 ep", ha="right", va="bottom",
         fontsize=8, color="#333", fontweight="bold")
axC.set_yticks(y)
axC.set_yticklabels(labels, fontsize=7.5)
axC.set_xlabel("epoch reached")
axC.set_xlim(0, 1100)
axC.set_title("(c)  0 / 11 survive to 1000 ep", loc="left", fontweight="bold")
axC.text(0.98, 0.04, "* = stopped manually (only non-crash)",
         transform=axC.transAxes, ha="right", va="bottom", fontsize=6.8,
         color="#777", style="italic")

fig.tight_layout(w_pad=2.0)
for ext in ("pdf", "png"):
    fig.savefig(os.path.join(HERE, f"fig_seed_sweep.{ext}"), bbox_inches="tight")
print("saved fig_seed_sweep.pdf / .png")
