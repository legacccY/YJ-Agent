"""
Figure 3: Med-NCA V1 Robustness Degradation Curves
Plots mean Dice vs perturbation level for 5 perturbation types (2x3 grid).
"""
import json
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
import matplotlib.patches as mpatches

# ---- Load data -------------------------------------------------------
DATA_PATH = r"D:\YJ-Agent\project\meeting\Med-NCA\results\v1_robustness_summary.json"
OUT_DIR   = r"D:\YJ-Agent\project\meeting\Med-NCA\report\figures"

with open(DATA_PATH, "r", encoding="utf-8") as f:
    data = json.load(f)

by_type = data["by_type"]
print("Top-level keys:", list(by_type.keys()))
for k, v in by_type.items():
    print(f"  {k}: baseline={v['baseline_mean_dice']}, levels={list(v['levels'].keys())}")

# ---- Style constants -------------------------------------------------
MUTED_BLUE  = "#3A76AF"
ACCENT_RED  = "#C0392B"
BASELINE_C  = "#666666"
GRID_ALPHA  = 0.3
FONT_SIZE   = 11
LABEL_SIZE  = 10

plt.rcParams.update({
    "font.family":       "DejaVu Sans",
    "font.size":         FONT_SIZE,
    "axes.labelsize":    LABEL_SIZE,
    "axes.titlesize":    FONT_SIZE,
    "xtick.labelsize":   9,
    "ytick.labelsize":   9,
    "axes.spines.top":   False,
    "axes.spines.right": False,
})

# ---- Perturbation display config ------------------------------------
PTYPE_CFG = {
    "scale": {
        "title": "Scale",
        "xlabel": "Scale factor",
        "x_map": lambda lbl: float(lbl),
    },
    "translate": {
        "title": "Translation",
        "xlabel": "Shift (px)",
        "x_map": lambda lbl: float(lbl.replace("px", "")),
    },
    "noise": {
        "title": "Gaussian Noise",
        "xlabel": r"Noise std $\sigma$",
        "x_map": lambda lbl: float(lbl.replace("std", "")),
    },
    "bias_field": {
        "title": "Bias Field",
        "xlabel": "Coefficient",
        "x_map": lambda lbl: float(lbl.replace("coef", "")),
    },
    "ghosting": {
        "title": "Ghosting",
        "xlabel": "Intensity",
        "x_map": lambda lbl: float(lbl.replace("int", "")),
    },
}

ORDER = ["scale", "translate", "noise", "bias_field", "ghosting"]

# ---- Build figure (2x3 grid, last cell = blank legend) -------------
fig = plt.figure(figsize=(10, 6))
gs  = gridspec.GridSpec(2, 3, figure=fig, hspace=0.52, wspace=0.38)

axes = [fig.add_subplot(gs[r, c]) for r in range(2) for c in range(3)]

for idx, ptype in enumerate(ORDER):
    ax  = axes[idx]
    cfg = PTYPE_CFG[ptype]
    info = by_type[ptype]
    baseline_val = info["baseline_mean_dice"]

    levels = info["levels"]
    xs = []
    ys = []
    errs = []
    for lbl, stats in levels.items():
        xs.append(cfg["x_map"](lbl))
        ys.append(stats["mean_dice"])
        errs.append(stats["std_dice"])

    xs   = np.array(xs)
    ys   = np.array(ys)
    errs = np.array(errs)

    # Sort by x
    sort_idx = np.argsort(xs)
    xs, ys, errs = xs[sort_idx], ys[sort_idx], errs[sort_idx]

    # Shade ±1 std
    ax.fill_between(xs, ys - errs, ys + errs,
                    alpha=0.15, color=MUTED_BLUE, linewidth=0)

    # Main line + markers
    ax.plot(xs, ys, "-o", color=MUTED_BLUE, linewidth=1.8,
            markersize=5, markerfacecolor="white",
            markeredgewidth=1.5, markeredgecolor=MUTED_BLUE,
            zorder=3, label="Mean Dice ± std")

    # Baseline dashed
    ax.axhline(baseline_val, linestyle="--", color=BASELINE_C,
               linewidth=1.2, alpha=0.8, zorder=2, label=f"Clean ({baseline_val:.4f})")

    ax.set_ylim(0.0, 0.97)
    ax.set_xlabel(cfg["xlabel"], fontsize=LABEL_SIZE)
    ax.set_ylabel("Mean Dice", fontsize=LABEL_SIZE)
    ax.set_title(cfg["title"], fontsize=FONT_SIZE, fontweight="bold", pad=4)
    ax.grid(True, alpha=GRID_ALPHA, linewidth=0.6)

    # Annotate worst drop for noise (most destructive)
    if ptype == "noise":
        worst_y = ys.min()
        worst_x = xs[np.argmin(ys)]
        ax.annotate(f"std 0.40\n→ {worst_y:.3f}",
                    xy=(worst_x, worst_y),
                    xytext=(worst_x - 0.05, worst_y + 0.18),
                    fontsize=8, color=ACCENT_RED,
                    arrowprops=dict(arrowstyle="->", color=ACCENT_RED,
                                   lw=0.9, connectionstyle="arc3,rad=0.2"),
                    ha="center")

# ---- Last cell: custom legend panel ---------------------------------
ax_leg = axes[5]
ax_leg.set_axis_off()

legend_elements = [
    plt.Line2D([0], [0], color=MUTED_BLUE, linewidth=1.8,
               marker="o", markerfacecolor="white",
               markeredgewidth=1.5, markeredgecolor=MUTED_BLUE,
               markersize=6, label="Mean Dice"),
    plt.Line2D([0], [0], linestyle="--", color=BASELINE_C,
               linewidth=1.2, label="Clean baseline (0.866)"),
    mpatches.Patch(facecolor=MUTED_BLUE, alpha=0.25,
                   edgecolor="none", label=r"±1 std band"),
]
ax_leg.legend(handles=legend_elements, loc="center",
              fontsize=9.5, frameon=True, framealpha=0.9,
              edgecolor="#cccccc", handlelength=2.0)

# ---- Note annotation -----------------------------------------------
fig.text(0.5, 0.01,
         "n = 78 test volumes; clean Dice = 0.866; noise (std 0.40) is most destructive (Dice → 0.032); ghosting most benign (Dice → 0.852).",
         ha="center", fontsize=8, color="#555555", style="italic")

# ---- Save -----------------------------------------------------------
import os
out_pdf = os.path.join(OUT_DIR, "fig_v1_robustness.pdf")
out_png = os.path.join(OUT_DIR, "fig_v1_robustness.png")

fig.savefig(out_pdf, bbox_inches="tight")
fig.savefig(out_png, dpi=200, bbox_inches="tight")
plt.close(fig)

print(f"Saved: {out_pdf}")
print(f"Saved: {out_png}")
print("Figure 3 (robustness) complete.")
