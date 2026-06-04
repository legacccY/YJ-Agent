"""
Figure 4: Med-NCA V2 NQM vs Dice scatter
Shows per-volume NQM score (x) vs Dice (y), n=78 volumes.
Failure cases (Dice < 0.8) highlighted in red.
"""
import csv
import json
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from scipy import stats
import os

# ---- Load data -------------------------------------------------------
CSV_PATH  = r"D:\YJ-Agent\project\meeting\Med-NCA\results\r1_nqm_per_volume.csv"
JSON_PATH = r"D:\YJ-Agent\project\meeting\Med-NCA\results\v2_r5_summary.json"
OUT_DIR   = r"D:\YJ-Agent\project\meeting\Med-NCA\report\figures"

# Read CSV
pids, dice_vals, nqm_vals = [], [], []
with open(CSV_PATH, newline="", encoding="utf-8") as f:
    reader = csv.DictReader(f)
    print("CSV columns:", reader.fieldnames)
    for row in reader:
        pids.append(int(row["pid"]))
        dice_vals.append(float(row["dice"]))
        nqm_vals.append(float(row["nqm"]))

dice_arr = np.array(dice_vals)
nqm_arr  = np.array(nqm_vals)
print(f"Loaded {len(pids)} volumes. Dice range [{dice_arr.min():.4f}, {dice_arr.max():.4f}]")
print(f"NQM  range [{nqm_arr.min():.5f}, {nqm_arr.max():.5f}]")

# Read JSON for stats
with open(JSON_PATH, "r", encoding="utf-8") as f:
    meta = json.load(f)

rho  = meta["R5_spearman"]["rho"]
pval = meta["R5_spearman"]["p_value_approx"]
n_fail = meta["n_fail_dice_lt_0.8"]
fail_thresh = meta["dice_fail_threshold"]  # 0.8
print(f"Spearman rho={rho:.4f}, p={pval:.2e}, n_fail={n_fail}")

# ---- Masks -----------------------------------------------------------
fail_mask = dice_arr < fail_thresh
pass_mask = ~fail_mask
print(f"Fail cases (Dice<{fail_thresh}): {fail_mask.sum()}, Pass: {pass_mask.sum()}")

# ---- Style constants -------------------------------------------------
MUTED_BLUE  = "#5B8DB8"
FAIL_RED    = "#C0392B"
THRESH_C    = "#888888"
TRENDLINE_C = "#3A76AF"
FONT_SIZE   = 11
LABEL_SIZE  = 11
GRID_ALPHA  = 0.3

plt.rcParams.update({
    "font.family":       "DejaVu Sans",
    "font.size":         FONT_SIZE,
    "axes.labelsize":    LABEL_SIZE,
    "axes.titlesize":    FONT_SIZE,
    "xtick.labelsize":   9.5,
    "ytick.labelsize":   9.5,
    "axes.spines.top":   False,
    "axes.spines.right": False,
})

# ---- Figure ----------------------------------------------------------
fig, ax = plt.subplots(figsize=(6, 5))

# Pass-cases scatter
ax.scatter(nqm_arr[pass_mask], dice_arr[pass_mask],
           color=MUTED_BLUE, alpha=0.55, s=38, linewidths=0,
           label=f"Pass (Dice ≥ 0.80, n={pass_mask.sum()})",
           zorder=3)

# Fail-cases scatter
ax.scatter(nqm_arr[fail_mask], dice_arr[fail_mask],
           color=FAIL_RED, alpha=0.95, s=70,
           marker="D", linewidths=0.8,
           edgecolors="darkred",
           label=f"Fail (Dice < 0.80, n={fail_mask.sum()})",
           zorder=5)

# Label fail points with pid
for i, is_fail in enumerate(fail_mask):
    if is_fail:
        ax.annotate(f"pid {pids[i]}",
                    xy=(nqm_arr[i], dice_arr[i]),
                    xytext=(nqm_arr[i] + 0.001, dice_arr[i] - 0.018),
                    fontsize=8.5, color=FAIL_RED,
                    arrowprops=dict(arrowstyle="->", color=FAIL_RED, lw=0.8))

# Failure threshold line
ax.axhline(fail_thresh, linestyle="--", color=THRESH_C,
           linewidth=1.3, alpha=0.8,
           label="Failure threshold (Dice = 0.80)",
           zorder=2)

# Faint OLS trend line
slope, intercept, _, _, _ = stats.linregress(nqm_arr, dice_arr)
x_fit = np.linspace(nqm_arr.min(), nqm_arr.max(), 200)
y_fit = slope * x_fit + intercept
ax.plot(x_fit, y_fit, "-", color=TRENDLINE_C,
        alpha=0.35, linewidth=1.4, zorder=1, label="OLS trend")

# Spearman annotation in upper-left
ax.text(0.04, 0.09,
        rf"Spearman $\rho$ = {rho:.2f}, $p$ < 10$^{{-5}}$",
        transform=ax.transAxes,
        fontsize=9.5, color="#333333",
        bbox=dict(boxstyle="round,pad=0.3", facecolor="white",
                  edgecolor="#cccccc", alpha=0.85))

# Note: NQM direction (higher = more variance = worse)
ax.text(0.04, 0.02,
        "Higher NQM → more inference variance",
        transform=ax.transAxes,
        fontsize=8.5, color="#666666", style="italic")

# Axes
ax.set_xlabel("NQM Score (inference variance proxy)", fontsize=LABEL_SIZE)
ax.set_ylabel("Dice Score", fontsize=LABEL_SIZE)

# Set limits with small padding
x_pad = (nqm_arr.max() - nqm_arr.min()) * 0.06
y_pad = 0.015
ax.set_xlim(nqm_arr.min() - x_pad, nqm_arr.max() + x_pad * 2.5)
ax.set_ylim(dice_arr.min() - y_pad * 2, dice_arr.max() + y_pad * 2)

ax.grid(True, alpha=GRID_ALPHA, linewidth=0.6)

# Legend
ax.legend(loc="lower right", fontsize=8.5, frameon=True,
          framealpha=0.9, edgecolor="#cccccc",
          handletextpad=0.5, borderpad=0.6)

plt.tight_layout()

# ---- Save -----------------------------------------------------------
out_pdf = os.path.join(OUT_DIR, "fig_v2_nqm.pdf")
out_png = os.path.join(OUT_DIR, "fig_v2_nqm.png")

fig.savefig(out_pdf, bbox_inches="tight")
fig.savefig(out_png, dpi=200, bbox_inches="tight")
plt.close(fig)

print(f"Saved: {out_pdf}")
print(f"Saved: {out_png}")
print("Figure 4 (NQM vs Dice) complete.")
