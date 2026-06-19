"""
plot_fig2_composite.py
----------------------
ICLR 2027 VisiSkin-Agent §3.3  C0 动机  Fig2 双 panel 组图
Panel A: AUC vs severity 折线（5 axis，Okabe-Ito 色，blur 加粗+标注）
Panel B: recoverability_delta 热图（5×5，RdBu 居中 0，CI 不跨 0 打 *，
         contrast S5 唯一 HURT 加红描边）

Usage:
    python plot_fig2_composite.py [--csv PATH] [--out DIR]
Defaults:
    --csv  D:/YJ-Agent/project/results/c0_decision_surface.csv
    --out  D:/YJ-Agent/project/meeting/ICLR2027/figures
"""

import argparse
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib as mpl
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np
import pandas as pd

# ---------- CLI ----------
parser = argparse.ArgumentParser()
parser.add_argument("--csv",
    default="D:/YJ-Agent/project/results/c0_decision_surface.csv")
parser.add_argument("--out",
    default="D:/YJ-Agent/project/meeting/ICLR2027/figures")
parser.add_argument("--smoke", type=int, default=0,
    help="Set 1 to run minimal smoke check and exit (no GPU needed)")
args = parser.parse_args()

if args.smoke:
    print("[smoke] import OK, args parsed OK")
    sys.exit(0)

# ---------- global style ----------
OKABE = {
    "black":     "#000000",
    "orange":    "#E69F00",
    "skyblue":   "#56B4E9",
    "green":     "#009E73",
    "yellow":    "#F0E442",
    "blue":      "#0072B2",
    "vermillion":"#D55E00",
    "purple":    "#CC79A7",
}

mpl.rcParams.update({
    "font.family":    "sans-serif",
    "font.size":      9,
    "axes.linewidth": 0.8,
    "pdf.fonttype":   42,
    "ps.fonttype":    42,
})

# ---------- load ----------
os.makedirs(args.out, exist_ok=True)
df = pd.read_csv(args.csv)

REQUIRED = [
    "axis", "severity_level", "severity_value",
    "auc", "auc_ci_lo", "auc_ci_hi",
    "recoverability_delta", "recoverability_ci_lo", "recoverability_ci_hi",
]
missing = [c for c in REQUIRED if c not in df.columns]
if missing:
    sys.exit(f"[ERROR] csv 缺列: {missing}  # TODO: 需补充这些列才能画图")

AXES_ORDER  = ["blur", "completeness", "color_shift", "brightness", "contrast"]
AXIS_LABELS = {
    "blur":        "Blur",
    "contrast":    "Contrast",
    "color_shift": "Color Shift",
    "brightness":  "Brightness",
    "completeness":"Completeness",
}
SEV_LEVELS = [1, 2, 3, 4, 5]
SEV_LABELS = ["S1", "S2", "S3", "S4", "S5"]

# Okabe-Ito colors per axis (5 distinct, no jet/rainbow)
AXIS_COLORS = {
    "blur":        OKABE["vermillion"],   # #D55E00 — 最脆，暖红突出
    "completeness":OKABE["blue"],         # #0072B2
    "color_shift": OKABE["green"],        # #009E73
    "brightness":  OKABE["orange"],       # #E69F00
    "contrast":    OKABE["purple"],       # #CC79A7
}
AXIS_MARKERS = {
    "blur":        "o",
    "completeness":"P",
    "color_shift": "^",
    "brightness":  "D",
    "contrast":    "s",
}

# verify all 25 rows present
present_axes = df["axis"].unique().tolist()
for a in AXES_ORDER:
    if a not in present_axes:
        sys.exit(f"[ERROR] csv 缺 axis={a}")

# ---------- build 2-D arrays for heatmap ----------
n_ax  = len(AXES_ORDER)
n_sev = len(SEV_LEVELS)

# rows = AXES_ORDER (blur first), cols = S1..S5
delta  = np.full((n_ax, n_sev), np.nan)
ci_lo  = np.full((n_ax, n_sev), np.nan)
ci_hi  = np.full((n_ax, n_sev), np.nan)

for i, ax_name in enumerate(AXES_ORDER):
    for j, sl in enumerate(SEV_LEVELS):
        row = df[(df["axis"] == ax_name) & (df["severity_level"] == sl)]
        if len(row) != 1:
            sys.exit(f"[ERROR] 找不到唯一行 axis={ax_name} severity_level={sl}")
        delta[i, j]  = row["recoverability_delta"].values[0]
        ci_lo[i, j]  = row["recoverability_ci_lo"].values[0]
        ci_hi[i, j]  = row["recoverability_ci_hi"].values[0]

# significance: CI 不跨 0
sig_pos = (ci_lo > 0)   # 增强显著有效
sig_neg = (ci_hi < 0)   # 增强帮倒忙（HURT）

# ---------- self-checks (guard on key values) ----------
# blur S1→S5 drop
blur_i = AXES_ORDER.index("blur")
blur_s1_auc = df[(df["axis"]=="blur") & (df["severity_level"]==1)]["auc"].values[0]
blur_s5_auc = df[(df["axis"]=="blur") & (df["severity_level"]==5)]["auc"].values[0]
blur_drop = blur_s1_auc - blur_s5_auc
print(f"[self-check] blur AUC S1={blur_s1_auc:.6f}  S5={blur_s5_auc:.6f}  "
      f"drop={blur_drop:.6f}  (expect ~0.0911)")

# contrast S5 delta
c5_i   = AXES_ORDER.index("contrast")
c5_val = delta[c5_i, 4]
c5_lo  = ci_lo[c5_i, 4]
c5_hi  = ci_hi[c5_i, 4]
print(f"[self-check] contrast S5 delta={c5_val:.6f}  "
      f"CI=[{c5_lo:.6f}, {c5_hi:.6f}]  sig_neg={sig_neg[c5_i,4]}")
assert sig_neg[c5_i, 4],    "[FAIL] contrast S5 should be sig_neg"
assert sig_neg.sum() == 1,  "[FAIL] exactly 1 sig_neg cell expected"

# ---------- FIGURE: 2-panel composite ----------
fig, (axA, axB) = plt.subplots(
    1, 2,
    figsize=(9.5, 3.8),
    gridspec_kw={"width_ratios": [1.1, 1.0]},
)
fig.subplots_adjust(wspace=0.38)

# ============================================================
# PANEL A: AUC reliability curves
# ============================================================
for ax_name in AXES_ORDER:
    sub  = df[df["axis"] == ax_name].sort_values("severity_level")
    sev  = sub["severity_level"].values
    auc  = sub["auc"].values
    lo   = sub["auc_ci_lo"].values
    hi   = sub["auc_ci_hi"].values
    is_blur = (ax_name == "blur")

    lw = 2.4 if is_blur else 1.4
    axA.plot(
        sev, auc,
        marker=AXIS_MARKERS[ax_name],
        color=AXIS_COLORS[ax_name],
        label=AXIS_LABELS[ax_name],
        linewidth=lw,
        markersize=5.5 if is_blur else 4.5,
        zorder=3 if is_blur else 2,
    )
    # CI band
    axA.fill_between(sev, lo, hi,
                     alpha=0.12 if is_blur else 0.07,
                     color=AXIS_COLORS[ax_name])

# blur annotation: S1→S5 drop
blur_sub  = df[df["axis"]=="blur"].sort_values("severity_level")
blur_sevs = blur_sub["severity_level"].values
blur_aucs = blur_sub["auc"].values
# arrow from S5 value upward, label drop
axA.annotate(
    f"−{blur_drop:.4f}",
    xy=(5, blur_aucs[-1]),
    xytext=(4.15, blur_aucs[-1] + 0.013),
    fontsize=7.5,
    color=AXIS_COLORS["blur"],
    fontweight="bold",
    arrowprops=dict(arrowstyle="-|>", color=AXIS_COLORS["blur"],
                    lw=1.0, mutation_scale=8),
)
# S1 label
axA.text(1.08, blur_aucs[0] + 0.002, "S1",
         fontsize=7, color=AXIS_COLORS["blur"], fontweight="bold")
# S5 label
axA.text(5.05, blur_aucs[-1] - 0.001, "S5",
         fontsize=7, color=AXIS_COLORS["blur"], fontweight="bold")

axA.set_xlabel("Severity Level", fontsize=9)
axA.set_ylabel("Diagnostic AUC", fontsize=9)
axA.set_xticks(SEV_LEVELS)
axA.set_xticklabels(SEV_LABELS, fontsize=8)
axA.tick_params(axis="y", labelsize=8)
axA.set_ylim(0.82, 0.965)
axA.set_xlim(0.7, 5.7)
axA.spines["top"].set_visible(False)
axA.spines["right"].set_visible(False)
axA.grid(axis="y", linewidth=0.4, alpha=0.35, linestyle="--")
axA.legend(fontsize=7.5, frameon=False, loc="lower left",
           handlelength=1.5, labelspacing=0.3)

# panel label
axA.text(-0.13, 1.04, "A", transform=axA.transAxes,
         fontsize=12, fontweight="bold", va="top")

# ============================================================
# PANEL B: recoverability_delta heatmap
# ============================================================
vabs = np.nanmax(np.abs(delta)) * 1.05   # symmetric, centered on 0
im = axB.imshow(
    delta,
    cmap="RdBu",
    vmin=-vabs,
    vmax=vabs,
    aspect="auto",
)

axB.set_xticks(range(n_sev))
axB.set_xticklabels(SEV_LABELS, fontsize=8)
axB.set_yticks(range(n_ax))
axB.set_yticklabels([AXIS_LABELS[a] for a in AXES_ORDER], fontsize=8)
axB.set_xlabel("Severity Level", fontsize=9)
axB.set_ylabel("Degradation Axis", fontsize=9)
axB.tick_params(length=2)

# colorbar
cbar = fig.colorbar(im, ax=axB, pad=0.03, fraction=0.046, aspect=20)
cbar.set_label(r"Recoverability $\Delta$AUC", fontsize=8)
cbar.ax.tick_params(labelsize=7)
cbar.ax.axhline(0, color="black", linewidth=0.6)   # 0 reference line

# cell annotations
for i in range(n_ax):
    for j in range(n_sev):
        val       = delta[i, j]
        is_sp     = sig_pos[i, j]
        is_sn     = sig_neg[i, j]
        norm_val  = val / vabs   # -1..1

        # text colour: white on dark bg
        txt_color = "white" if abs(norm_val) > 0.45 else "black"

        val_str = f"{val:+.3f}"

        # value text (shift up slightly if marker below)
        y_offset = -0.18 if (is_sp or is_sn) else 0.0
        axB.text(j, i + y_offset, val_str,
                 ha="center", va="center",
                 fontsize=7, color=txt_color,
                 fontweight="bold" if is_sn else "normal")

        # significance marker
        if is_sp:
            axB.text(j, i + 0.26, "*",
                     ha="center", va="center",
                     fontsize=10, color=txt_color, fontweight="bold")
        elif is_sn:
            axB.text(j, i + 0.26, "*",
                     ha="center", va="center",
                     fontsize=10, color="white", fontweight="bold")

        # semi-transparent overlay for non-significant cells
        if not is_sp and not is_sn:
            rect = plt.Rectangle((j - 0.5, i - 0.5), 1, 1,
                                  fill=True, facecolor="white", alpha=0.20,
                                  linewidth=0)
            axB.add_patch(rect)

# red border on contrast S5 (unique HURT)
for i in range(n_ax):
    for j in range(n_sev):
        if sig_neg[i, j]:
            rect = plt.Rectangle((j - 0.5, i - 0.5), 1, 1,
                                  fill=False,
                                  edgecolor="#b2182b",
                                  linewidth=2.2)
            axB.add_patch(rect)

# panel label
axB.text(-0.22, 1.04, "B", transform=axB.transAxes,
         fontsize=12, fontweight="bold", va="top")

# ---------- save ----------
out_pdf = os.path.join(args.out, "fig2_decision_surface.pdf")
out_png = os.path.join(args.out, "fig2_decision_surface.png")
fig.savefig(out_pdf, bbox_inches="tight", dpi=300)
fig.savefig(out_png, bbox_inches="tight", dpi=300)
plt.close(fig)

print(f"[OK] fig2 composite -> {out_pdf}")
print(f"[OK] fig2 composite -> {out_png}")
print(f"[key values] blur drop S1->S5 = {blur_drop:.4f}  |  contrast S5 delta = {c5_val:.4f}")
