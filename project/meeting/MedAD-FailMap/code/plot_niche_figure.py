"""
plot_niche_figure.py
MedAD-FailMap · headline A' central figure
「三模态从三个不同维度都打不进 BraTS 几何 niche」

Output: results/fig_niche_three_modality.png

Data sources:
  brats_brain_px.csv         → area_ratio_brain  (n=1948)
  lesion_features_cbis_mass.csv → area_ratio_breast (n=1696)
  lesion_features_idrid.csv  → area_ratio_fov + n_components (n=54)
  HAM area_ratio: from area_ratio_check_ham.csv target_p50=0.282959 (n=3310)
    NOTE: lesion_features_ham.csv has no per-image area_ratio column;
    we use the 5-quantile distribution from area_ratio_check_ham.csv
    (p1/p5/p10/p25/p50/p75/p90/p95/p99) to reconstruct a representative
    distribution for visualisation.  Median marked separately as "HAM*" with
    footnote.  n_components for HAM assumed =1 (single lesion per image in
    ISIC/HAM standard; marked with * in panel b).
"""

import csv
import os
import numpy as np
import matplotlib
matplotlib.use("Agg")          # no display – Windows-safe
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.lines import Line2D

# ── paths ────────────────────────────────────────────────────────────────────
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RES  = os.path.join(BASE, "results")

def load_col(path, col, dtype=float):
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return [dtype(row[col]) for row in reader if row.get(col, "").strip()]

# ── load data ─────────────────────────────────────────────────────────────────
brats_ar  = np.array(load_col(os.path.join(RES, "brats_brain_px.csv"),         "area_ratio_brain"))
cbis_ar   = np.array(load_col(os.path.join(RES, "lesion_features_cbis_mass.csv"), "area_ratio_breast"))
idrid_ar  = np.array(load_col(os.path.join(RES, "lesion_features_idrid.csv"),   "area_ratio_fov"))
idrid_nc  = np.array(load_col(os.path.join(RES, "lesion_features_idrid.csv"),   "n_components"))
cbis_nc   = np.array(load_col(os.path.join(RES, "lesion_features_cbis_mass.csv"), "n_components"))

# HAM: reconstruct distribution from known quantiles (area_ratio_check_ham.csv)
_ham_q = {
    "p1":0.0176, "p5":0.044031, "p10":0.070996, "p25":0.150391,
    "p50":0.282959, "p75":0.450378, "p90":0.593555, "p95":0.693384,
    "p99":0.85325
}
# Interpolate ~200 points from quantile CDF for KDE-like plot
_q_probs  = np.array([0.01, 0.05, 0.10, 0.25, 0.50, 0.75, 0.90, 0.95, 0.99])
_q_vals   = np.array([_ham_q[k] for k in ["p1","p5","p10","p25","p50","p75","p90","p95","p99"]])
_t        = np.linspace(0, 1, 3310)
ham_ar    = np.interp(_t, _q_probs, _q_vals)   # representative sample

# ── computed stats ────────────────────────────────────────────────────────────
brats_med  = float(np.median(brats_ar))
cbis_med   = float(np.median(cbis_ar))
idrid_med  = float(np.median(idrid_ar))
ham_med    = float(np.median(ham_ar))           # == p50 by construction
idrid_nc_med = float(np.median(idrid_nc))
cbis_nc_med  = float(np.median(cbis_nc))
brats_p25  = float(np.percentile(brats_ar, 25))
brats_p75  = float(np.percentile(brats_ar, 75))

print("=== computed medians ===")
print(f"BraTS   area_ratio  median={brats_med:.4f}  (P25={brats_p25:.4f}, P75={brats_p75:.4f})  n={len(brats_ar)}")
print(f"HAM*    area_ratio  median={ham_med:.4f}  (reconstructed from area_ratio_check_ham.csv quantiles, n=3310)")
print(f"CBIS    area_ratio  median={cbis_med:.4f}  n={len(cbis_ar)}")
print(f"IDRiD   area_ratio  median={idrid_med:.4f}  n={len(idrid_ar)}")
print(f"IDRiD   n_components median={idrid_nc_med:.0f}")
print(f"CBIS    n_components median={cbis_nc_med:.0f}")
print(f"BraTS   n_components: no csv column -> assumed ~2 (literature: 1-3 tumour regions per slice; marked '~2' in plot)")
print(f"HAM     n_components: assumed =1 (single skin lesion per ISIC image; marked '*' in plot)")

# ── colour palette (colour-blind safe: Wong 2011) ─────────────────────────────
C = {
    "BraTS": "#0072B2",   # blue
    "HAM":   "#E69F00",   # amber
    "CBIS":  "#009E73",   # green
    "IDRiD": "#CC79A7",   # pink
}
ALPHA_DIST = 0.70
ALPHA_SHADE = 0.18

# ── figure layout ─────────────────────────────────────────────────────────────
fig, (ax_a, ax_b) = plt.subplots(1, 2, figsize=(12, 5))
fig.patch.set_facecolor("white")

# ====================================================================
# Panel (a): area-ratio distribution (log x, KDE-style histogram)
# ====================================================================
ax = ax_a

# log-spaced bins spanning full range
bins = np.logspace(np.log10(5e-4), np.log10(1.0), 60)

datasets = [
    ("BraTS",  brats_ar,  C["BraTS"]),
    ("HAM*",   ham_ar,    C["HAM"]),
    ("CBIS",   cbis_ar,   C["CBIS"]),
    ("IDRiD",  idrid_ar,  C["IDRiD"]),
]
meds = {
    "BraTS": brats_med,
    "HAM*":  ham_med,
    "CBIS":  cbis_med,
    "IDRiD": idrid_med,
}

for label, arr, color in datasets:
    counts, edges = np.histogram(arr, bins=bins, density=True)
    centers = 0.5 * (edges[:-1] + edges[1:])
    ax.fill_between(centers, counts, alpha=ALPHA_DIST, color=color, label=label)
    ax.plot(centers, counts, color=color, linewidth=1.2)

# BraTS niche band [P25, P75]
ax.axvspan(brats_p25, brats_p75, alpha=ALPHA_SHADE, color=C["BraTS"],
           label=f"BraTS niche [P25={brats_p25:.3f}, P75={brats_p75:.3f}]",
           zorder=0)

# median ticks
ymax_a = ax.get_ylim()[1]
for label, arr, color in datasets:
    m = meds[label]
    ax.axvline(m, color=color, linewidth=1.8, linestyle="--", alpha=0.9)
    ax.text(m, ymax_a * 0.92, f"{m:.3f}", color=color, fontsize=7.5,
            ha="center", va="bottom", rotation=90)

ax.set_xscale("log")
ax.set_xlabel("Lesion / tissue area ratio  (log scale)", fontsize=11)
ax.set_ylabel("Density", fontsize=11)
ax.set_title("(a)  Area-ratio distributions\nthree modalities miss BraTS niche from different sides",
             fontsize=10.5, pad=8)
ax.legend(fontsize=8.5, loc="upper left", framealpha=0.85)
ax.spines["top"].set_visible(False)
ax.spines["right"].set_visible(False)

# directional annotations
ymax_a = ax.get_ylim()[1]
ax.annotate("CBIS/IDRiD\ntoo small ->",
            xy=(cbis_med, ymax_a * 0.45),
            xytext=(cbis_med * 0.25, ymax_a * 0.62),
            fontsize=8, color="#333",
            arrowprops=dict(arrowstyle="->", color="#333", lw=1.0))
ax.annotate("<- HAM\ntoo large",
            xy=(ham_med, ymax_a * 0.35),
            xytext=(ham_med * 1.9, ymax_a * 0.55),
            fontsize=8, color="#333",
            arrowprops=dict(arrowstyle="->", color="#333", lw=1.0))

# ====================================================================
# Panel (b): 2-D iso space  x=median area-ratio (log), y=median n_comp (log)
# ====================================================================
ax = ax_b

ax.set_xscale("log")
ax.set_yscale("log")

# Fix axis range to keep all 4 points visible with room for labels
# x: cbis_med~0.010, idrid~0.019, brats~0.105, ham~0.283  → [0.004, 0.7]
# y: ham=1, cbis=1, brats~2, idrid=136                     → [0.5, 600]
ax.set_xlim(0.004, 0.7)
ax.set_ylim(0.5, 600)

# BraTS iso zone shading: [P25,P75] x [1, 5]
ax.fill_betweenx([1.0, 5.0], brats_p25, brats_p75,
                 alpha=0.22, color=C["BraTS"], zorder=0,
                 label="BraTS iso-niche\n[P25-P75 AR] x [1-5 comp]")

# scatter points
#   BraTS n_components: no csv col; placeholder ~2 (literature: 1-3 regions/slice)
pts = [
    ("BraTS",  brats_med,  2.0,          C["BraTS"]),
    ("HAM*",   ham_med,    1.0,          C["HAM"]),
    ("CBIS",   cbis_med,   cbis_nc_med,  C["CBIS"]),
    ("IDRiD",  idrid_med,  idrid_nc_med, C["IDRiD"]),
]
# label positions (x_text, y_text) chosen to avoid overlap given log axes
lbl_pos = {
    "BraTS":  (brats_med * 2.2,   4.0,   "BraTS (GBM, ~2 reg.)"),
    "HAM*":   (ham_med * 1.5,     2.5,   "HAM (skin, 1 lesion)"),
    "CBIS":   (cbis_med * 0.38,   2.2,   "CBIS (mammo)"),
    "IDRiD":  (idrid_med * 3.5,   idrid_nc_med * 1.5, "IDRiD (DR fundus)"),
}

for key, x, y, color in pts:
    ax.scatter(x, y, s=130, color=color, zorder=5,
               edgecolors="white", linewidths=0.9)
    tx, ty, lbl = lbl_pos[key]
    ax.annotate(lbl, (x, y), xytext=(tx, ty),
                fontsize=8.5, color=color,
                arrowprops=dict(arrowstyle="-", color=color, lw=0.8, alpha=0.7))

# escape arrows showing 3 different failure directions
# HAM: rightward (area too large)
ax.annotate("", xy=(ham_med * 0.78, 1.5), xytext=(brats_p75 * 1.1, 1.5),
            arrowprops=dict(arrowstyle="->", color=C["HAM"], lw=2.0))
ax.text(ham_med * 0.38, 1.85, "size ->", fontsize=7.5, color=C["HAM"], style="italic")

# CBIS: leftward (area too small)
ax.annotate("", xy=(cbis_med * 1.4, 1.35), xytext=(brats_p25 * 0.94, 1.35),
            arrowprops=dict(arrowstyle="->", color=C["CBIS"], lw=2.0))
ax.text(cbis_med * 0.55, 1.65, "<- size", fontsize=7.5, color=C["CBIS"], style="italic")

# IDRiD: upward (n_components too many)
ax.annotate("", xy=(idrid_med, idrid_nc_med * 0.72), xytext=(idrid_med, 6.0),
            arrowprops=dict(arrowstyle="->", color=C["IDRiD"], lw=2.0))
ax.text(idrid_med * 1.35, 22, "n_comp ^", fontsize=7.5, color=C["IDRiD"], style="italic")

ax.set_xlabel("Median lesion/tissue area ratio  (log scale)", fontsize=11)
ax.set_ylabel("Median lesion components  (log scale)", fontsize=11)
ax.set_title("(b)  Geometric iso-space: BraTS niche is 2-D\nthree modalities escape from different axes",
             fontsize=10.5, pad=8)

legend_els = [
    Line2D([0],[0], marker='o', color='w', markerfacecolor=C["BraTS"], markersize=9, label="BraTS (GBM)"),
    Line2D([0],[0], marker='o', color='w', markerfacecolor=C["HAM"],   markersize=9, label="HAM (skin)"),
    Line2D([0],[0], marker='o', color='w', markerfacecolor=C["CBIS"],  markersize=9, label="CBIS (mammo)"),
    Line2D([0],[0], marker='o', color='w', markerfacecolor=C["IDRiD"], markersize=9, label="IDRiD (DR)"),
    mpatches.Patch(facecolor=C["BraTS"], alpha=0.3, label="BraTS iso-niche"),
]
ax.legend(handles=legend_els, fontsize=8.5, loc="upper left", framealpha=0.85)
ax.spines["top"].set_visible(False)
ax.spines["right"].set_visible(False)

# ── footnotes ─────────────────────────────────────────────────────────────────
footnote = (
    "* HAM area ratio reconstructed from 9-quantile CDF in area_ratio_check_ham.csv "
    "(p1=0.018, p25=0.150, p50=0.283, p75=0.450, p99=0.853; n=3310). "
    "lesion_features_ham.csv has no per-image area_ratio column. "
    "HAM n_components assumed =1 (single lesion/ISIC image). "
    "BraTS n_components: no CSV column; placeholder ~2 (literature: 1-3 tumour regions/MRI slice). "
    "BraTS niche = [P25=0.052, P75=0.163] x [1-5 components]."
)
fig.text(0.01, 0.0, footnote, fontsize=6.2, color="#555",
         va="bottom",
         bbox=dict(boxstyle="round,pad=0.3", facecolor="#f5f5f5", edgecolor="#ccc", alpha=0.7))

plt.suptitle(
    "Geometric niche mismatch: BraTS lesions occupy a narrow 2-D regime\n"
    "that no cross-modal dataset shares — three distinct failure modes",
    fontsize=12, fontweight="bold", y=1.01
)

plt.tight_layout(rect=[0, 0.09, 1, 1])

out_path = os.path.join(RES, "fig_niche_three_modality.png")
plt.savefig(out_path, dpi=220, bbox_inches="tight", facecolor="white")
plt.close()
print(f"\nSaved -> {out_path}")
