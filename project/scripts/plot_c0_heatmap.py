"""
plot_c0_heatmap.py
------------------
ICLR 2027 VisiSkin-Agent §3.3 + §7.1
C0 决策面：5轴 × 5档 recoverability_delta heatmap
+ AUC vs severity 退化曲线（辅图，csv 有 auc 列时自动产出）

Usage:
    python plot_c0_heatmap.py [--csv PATH] [--out DIR]
Defaults:
    --csv  D:/YJ-Agent/project/results/c0_decision_surface.csv
    --out  D:/YJ-Agent/project/meeting/ICLR2027/figures
"""

import argparse
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np
import pandas as pd

# ---------- CLI ----------
parser = argparse.ArgumentParser()
parser.add_argument(
    "--csv",
    default="D:/YJ-Agent/project/results/c0_decision_surface.csv",
)
parser.add_argument(
    "--out",
    default="D:/YJ-Agent/project/meeting/ICLR2027/figures",
)
args = parser.parse_args()

os.makedirs(args.out, exist_ok=True)

# ---------- load ----------
df = pd.read_csv(args.csv)

REQUIRED = [
    "axis", "severity_level",
    "recoverability_delta", "recoverability_ci_lo", "recoverability_ci_hi",
]
missing = [c for c in REQUIRED if c not in df.columns]
if missing:
    sys.exit(f"[ERROR] csv 缺列: {missing}")

AXES_ORDER = ["blur", "contrast", "color_shift", "brightness", "completeness"]
AXIS_LABELS = {
    "blur": "Blur",
    "contrast": "Contrast",
    "color_shift": "Color Shift",
    "brightness": "Brightness",
    "completeness": "Completeness",
}
SEV_LEVELS = [1, 2, 3, 4, 5]
SEV_LABELS = ["S1", "S2", "S3", "S4", "S5"]

# verify all 25 combos present
present_axes = df["axis"].unique().tolist()
for a in AXES_ORDER:
    if a not in present_axes:
        sys.exit(f"[ERROR] csv 缺 axis={a}")

# ---------- build 2-D arrays ----------
n_ax = len(AXES_ORDER)
n_sev = len(SEV_LEVELS)

delta = np.full((n_ax, n_sev), np.nan)
ci_lo = np.full((n_ax, n_sev), np.nan)
ci_hi = np.full((n_ax, n_sev), np.nan)

for i, ax in enumerate(AXES_ORDER):
    for j, sl in enumerate(SEV_LEVELS):
        row = df[(df["axis"] == ax) & (df["severity_level"] == sl)]
        if len(row) != 1:
            sys.exit(f"[ERROR] 找不到唯一行 axis={ax} severity_level={sl}")
        delta[i, j] = row["recoverability_delta"].values[0]
        ci_lo[i, j] = row["recoverability_ci_lo"].values[0]
        ci_hi[i, j] = row["recoverability_ci_hi"].values[0]

# significance: CI 完全不跨 0
sig_pos = (ci_lo > 0)   # 显著正：增强有效救援
sig_neg = (ci_hi < 0)   # 显著负：增强帮倒忙（HURT）

# ---------- self-check: contrast S5 ----------
c5_i = AXES_ORDER.index("contrast")
c5_j = SEV_LEVELS.index(5)
c5_val = delta[c5_i, c5_j]
print(f"[self-check] contrast S5 delta = {c5_val:.6f}  "
      f"CI=[{ci_lo[c5_i,c5_j]:.6f}, {ci_hi[c5_i,c5_j]:.6f}]  "
      f"sig_neg={sig_neg[c5_i,c5_j]}")
assert sig_neg[c5_i, c5_j], "[FAIL] contrast S5 should be sig_neg"
assert sig_neg.sum() == 1, "[FAIL] should be exactly 1 sig_neg cell"

# ---------- FIGURE 1: heatmap ----------
fig, ax = plt.subplots(figsize=(7.5, 4.8))

# symmetric vmax centered on 0
vabs = np.nanmax(np.abs(delta)) * 1.05
im = ax.imshow(
    delta,
    cmap="RdBu",
    vmin=-vabs,
    vmax=vabs,
    aspect="auto",
)

# axis / tick labels
ax.set_xticks(range(n_sev))
ax.set_xticklabels(SEV_LABELS, fontsize=11)
ax.set_yticks(range(n_ax))
ax.set_yticklabels([AXIS_LABELS[a] for a in AXES_ORDER], fontsize=11)
ax.set_xlabel("Severity Level", fontsize=12)
ax.set_ylabel("Degradation Axis", fontsize=12)

# colorbar
cbar = fig.colorbar(im, ax=ax, pad=0.02, fraction=0.046)
cbar.set_label(r"Recoverability $\Delta$AUC", fontsize=11)
cbar.ax.tick_params(labelsize=9)

# cell text + significance markers
for i in range(n_ax):
    for j in range(n_sev):
        val = delta[i, j]
        is_sig_pos = sig_pos[i, j]
        is_sig_neg = sig_neg[i, j]

        # text colour: light for dark bg cells (large |delta|)
        norm_val = val / vabs          # -1..1
        if abs(norm_val) > 0.45:
            txt_color = "white"
        else:
            txt_color = "black"

        # base delta string
        val_str = f"{val:+.3f}"

        # draw delta value
        ax.text(
            j, i, val_str,
            ha="center", va="center" if not (is_sig_pos or is_sig_neg) else "top",
            fontsize=8.5, color=txt_color,
            fontweight="bold" if is_sig_neg else "normal",
        )

        # significance marker below the value
        if is_sig_pos:
            ax.text(
                j, i + 0.22, "★",
                ha="center", va="center",
                fontsize=9, color=txt_color,
            )
        elif is_sig_neg:
            ax.text(
                j, i + 0.22, "†HURT",
                ha="center", va="center",
                fontsize=8, color="white",
                fontweight="bold",
            )

        # grey overlay for CI-crossing-0 (not significant either way)
        if not is_sig_pos and not is_sig_neg:
            rect = plt.Rectangle(
                (j - 0.5, i - 0.5), 1, 1,
                fill=True, facecolor="white", alpha=0.25,
                linewidth=0,
            )
            ax.add_patch(rect)

# highlight border on sig_neg cell (contrast S5)
for i in range(n_ax):
    for j in range(n_sev):
        if sig_neg[i, j]:
            rect = plt.Rectangle(
                (j - 0.5, i - 0.5), 1, 1,
                fill=False, edgecolor="crimson", linewidth=2.5,
            )
            ax.add_patch(rect)

# legend
legend_patches = [
    mpatches.Patch(facecolor="#2166ac", label="Positive: enhancement helps"),
    mpatches.Patch(facecolor="#d73027", label="Negative: enhancement hurts"),
    mpatches.Patch(
        facecolor="gray", alpha=0.4,
        label=u"★ Sig. positive  †HURT Sig. negative",
    ),
]
ax.legend(
    handles=legend_patches,
    loc="upper left",
    bbox_to_anchor=(0.0, -0.15),
    ncol=1,
    fontsize=8.5,
    frameon=False,
)

plt.tight_layout(rect=[0, 0.12, 1, 1])

out_pdf = os.path.join(args.out, "c0_recoverability_heatmap.pdf")
out_png = os.path.join(args.out, "c0_recoverability_heatmap.png")
fig.savefig(out_pdf, bbox_inches="tight", dpi=300)
fig.savefig(out_png, bbox_inches="tight", dpi=300)
plt.close(fig)
print(f"[OK] heatmap -> {out_pdf}")
print(f"[OK] heatmap -> {out_png}")

# ---------- FIGURE 2: AUC degradation curves (optional) ----------
if "auc" not in df.columns:
    print("[SKIP] csv 无 auc 列，跳过辅图")
    sys.exit(0)

AXIS_COLORS = {
    "blur": "#d73027",
    "contrast": "#fc8d59",
    "color_shift": "#4dac26",
    "brightness": "#2166ac",
    "completeness": "#762a83",
}
AXIS_MARKERS = {
    "blur": "o",
    "contrast": "s",
    "color_shift": "^",
    "brightness": "D",
    "completeness": "P",
}

fig2, ax2 = plt.subplots(figsize=(6.0, 4.0))

for ax_name in AXES_ORDER:
    sub = df[df["axis"] == ax_name].sort_values("severity_level")
    sev = sub["severity_level"].values
    auc = sub["auc"].values
    ax2.plot(
        sev, auc,
        marker=AXIS_MARKERS[ax_name],
        color=AXIS_COLORS[ax_name],
        label=AXIS_LABELS[ax_name],
        linewidth=1.8,
        markersize=6,
    )
    # optional CI band if columns present
    if "auc_ci_lo" in df.columns and "auc_ci_hi" in df.columns:
        lo = sub["auc_ci_lo"].values
        hi = sub["auc_ci_hi"].values
        ax2.fill_between(sev, lo, hi, alpha=0.10, color=AXIS_COLORS[ax_name])

ax2.set_xlabel("Severity Level", fontsize=12)
ax2.set_ylabel("AUC", fontsize=12)
ax2.set_xticks(SEV_LEVELS)
ax2.set_xticklabels(SEV_LABELS, fontsize=10)
ax2.tick_params(axis="y", labelsize=10)
ax2.set_ylim(0.82, 0.96)
ax2.legend(fontsize=9, frameon=False)
ax2.grid(axis="y", linewidth=0.5, alpha=0.4)
ax2.spines["top"].set_visible(False)
ax2.spines["right"].set_visible(False)

plt.tight_layout()

out2_pdf = os.path.join(args.out, "c0_reliability_curves.pdf")
out2_png = os.path.join(args.out, "c0_reliability_curves.png")
fig2.savefig(out2_pdf, bbox_inches="tight", dpi=300)
fig2.savefig(out2_png, bbox_inches="tight", dpi=300)
plt.close(fig2)
print(f"[OK] curves  -> {out2_pdf}")
print(f"[OK] curves  -> {out2_png}")
