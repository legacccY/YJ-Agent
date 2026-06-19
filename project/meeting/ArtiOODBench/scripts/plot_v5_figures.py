"""
ArtiOODBench v5 figure generation — 3 publication-quality PDFs + PNG backups.
Drift contract: reads CSVs only, no data modification.

Figure / CSV mapping:
  fig_v5_heatmap_13x7.pdf
      <- results/l3_raw_ranking.csv   cols: pair, subset, method, rank, auroc

  fig_v5_vim_leakage.pdf
      <- results/l3_raw_ranking.csv   (raw ViM AUROC)
      <- results/l3_cleanC_ranking.csv (cleanC ViM AUROC, subset==cleanC or cleanC_INSUF)

  fig_v5_a4_negative.pdf
      <- results/a4_bootstrap_spearman.csv  cols: pair, spearman_point, ci_lower, ci_upper
"""

import os
os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import FancyBboxPatch
from pathlib import Path

# ── paths ─────────────────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent.parent
RES  = ROOT / "results"
FIG  = ROOT / "figures"
FIG.mkdir(parents=True, exist_ok=True)

# ── shared palette (Wong 2011 colorblind-safe) ────────────────────────────────
CB = {
    "orange":  "#E69F00",
    "sky":     "#56B4E9",
    "green":   "#009E73",
    "yellow":  "#F0E442",
    "blue":    "#0072B2",
    "red":     "#D55E00",
    "pink":    "#CC79A7",
    "black":   "#000000",
}

FONT_SIZE = 11
plt.rcParams.update({
    "font.size":        FONT_SIZE,
    "axes.titlesize":   FONT_SIZE + 1,
    "axes.labelsize":   FONT_SIZE,
    "xtick.labelsize":  FONT_SIZE - 1,
    "ytick.labelsize":  FONT_SIZE - 1,
    "legend.fontsize":  FONT_SIZE - 1,
    "figure.dpi":       150,
    "pdf.fonttype":     42,   # embed TrueType for camera-ready
    "ps.fonttype":      42,
})

# ── domain constants ──────────────────────────────────────────────────────────
ALL_PAIRS = [
    "NIH_vs_VinDr",
    "NIH_vs_RSNA_normal",
    "BraTS_normal_vs_BrainTumor_normal",
    "HAM_NV_vs_ISIC2020_benign",
    "VinDr_CXR_vs_RSNA_normal",
    "HAM_NV_vs_fitzpatrick17k",
    "ISIC2020_benign_vs_PAD_UFES",
]

PAIR_SHORT = {
    "NIH_vs_VinDr":                       "NIH vs\nVinDr",
    "NIH_vs_RSNA_normal":                 "NIH vs\nRSNA",
    "BraTS_normal_vs_BrainTumor_normal":  "BraTS vs\nBrainTumor",
    "HAM_NV_vs_ISIC2020_benign":          "HAM vs\nISIC2020",
    "VinDr_CXR_vs_RSNA_normal":           "VinDr vs\nRSNA",
    "HAM_NV_vs\nfitzpatrick17k":          "HAM vs\nFitz17k",
    "ISIC2020_benign_vs_PAD_UFES":        "ISIC2020 vs\nPAD-UFES",
}
# Corrected key for HAM_NV_vs_fitzpatrick17k
PAIR_SHORT["HAM_NV_vs_fitzpatrick17k"] = "HAM vs\nFitz17k"

# Modality groupings
MODALITY = {
    "NIH_vs_VinDr":                       "CXR",
    "NIH_vs_RSNA_normal":                 "CXR",
    "VinDr_CXR_vs_RSNA_normal":           "CXR",
    "BraTS_normal_vs_BrainTumor_normal":  "BrainMRI",
    "HAM_NV_vs_ISIC2020_benign":          "Dermoscopy",
    "HAM_NV_vs_fitzpatrick17k":           "Dermoscopy",
    "ISIC2020_benign_vs_PAD_UFES":        "Dermoscopy",
}

MODALITY_COLORS = {
    "CXR":        CB["sky"],
    "BrainMRI":   CB["green"],
    "Dermoscopy": CB["orange"],
}

ALL_METHODS_ORDER = [
    "MSP", "ODIN", "Energy", "MDS", "KNN",
    "ViM", "GradNorm", "Residual", "SHE",
    "NNGuide", "fDBD", "DICE", "ASH",
]  # will be re-sorted by mean AUROC descending inside fig1


def save(fig: plt.Figure, stem: str) -> None:
    pdf_path = FIG / f"{stem}.pdf"
    png_path = FIG / f"{stem}.png"
    fig.savefig(pdf_path, bbox_inches="tight")
    fig.savefig(png_path, bbox_inches="tight", dpi=150)
    print(f"  saved: {pdf_path.name}  {png_path.name}")
    plt.close(fig)


# ═══════════════════════════════════════════════════════════════════════════════
# Fig 1 — 13x7 heatmap of raw AUROC (methods x pairs)
# ═══════════════════════════════════════════════════════════════════════════════
def plot_heatmap_13x7() -> None:
    print("[fig_v5_heatmap_13x7] reading l3_raw_ranking.csv ...")
    df = pd.read_csv(RES / "l3_raw_ranking.csv")
    df = df[df["subset"] == "raw"]

    # Build 13x7 AUROC matrix
    methods_in_data = df["method"].unique().tolist()
    pairs_in_data   = df["pair"].unique().tolist()

    # Sort pairs by modality group (CXR, BrainMRI, Dermoscopy)
    mod_order = ["CXR", "BrainMRI", "Dermoscopy"]
    pairs_sorted = sorted(pairs_in_data,
                          key=lambda p: (mod_order.index(MODALITY[p]), p))

    # Sort methods by mean AUROC descending
    method_mean = {}
    for m in methods_in_data:
        vals = df[df["method"] == m]["auroc"].values
        method_mean[m] = float(np.nanmean(vals))
    methods_sorted = sorted(methods_in_data, key=lambda m: method_mean[m], reverse=True)

    # Build matrix (rows=methods, cols=pairs)
    mat = np.full((len(methods_sorted), len(pairs_sorted)), np.nan)
    for i, m in enumerate(methods_sorted):
        for j, p in enumerate(pairs_sorted):
            row = df[(df["method"] == m) & (df["pair"] == p)]
            if len(row) > 0:
                mat[i, j] = float(row["auroc"].iloc[0])

    fig, ax = plt.subplots(figsize=(13, 6.5))

    im = ax.imshow(mat, cmap="RdYlGn", aspect="auto", vmin=0.3, vmax=1.0)

    # Annotate each cell
    for i in range(len(methods_sorted)):
        for j in range(len(pairs_sorted)):
            val = mat[i, j]
            if not np.isnan(val):
                text_color = "black" if 0.45 < val < 0.85 else "white"
                ax.text(j, i, f"{val:.2f}", ha="center", va="center",
                        fontsize=8.5, color=text_color, fontweight="bold")

    # Colorbar
    cbar = fig.colorbar(im, ax=ax, fraction=0.025, pad=0.02)
    cbar.set_label("AUROC (raw)", fontsize=FONT_SIZE)

    # x-axis: pair short names
    ax.set_xticks(range(len(pairs_sorted)))
    ax.set_xticklabels([PAIR_SHORT[p] for p in pairs_sorted],
                       ha="center", fontsize=9)

    # y-axis: method names
    ax.set_yticks(range(len(methods_sorted)))
    ax.set_yticklabels(methods_sorted, fontsize=10)

    # Modality group separators and top labels
    # CXR: 3 pairs, BrainMRI: 1, Dermoscopy: 3
    group_sizes = {"CXR": 3, "BrainMRI": 1, "Dermoscopy": 3}
    group_starts = {"CXR": 0, "BrainMRI": 3, "Dermoscopy": 4}

    n_methods = len(methods_sorted)
    for mod, start in group_starts.items():
        size = group_sizes[mod]
        end  = start + size
        # Draw vertical separator (except at 0)
        if start > 0:
            ax.axvline(start - 0.5, color="white", linewidth=2.5, zorder=5)
        # Modality label above x-axis (use ax.annotate in figure coords)
        mid_col = start + (size - 1) / 2.0
        ax.annotate(
            mod,
            xy=(mid_col, -0.5),
            xycoords=("data", "axes fraction"),
            xytext=(mid_col, 1.04),
            textcoords=("data", "axes fraction"),
            ha="center", va="bottom",
            fontsize=10, fontweight="bold",
            color=MODALITY_COLORS[mod],
            annotation_clip=False,
        )
        # Draw a colored underline above column group
        ax.annotate(
            "",
            xy=   (end - 0.5,  1.025),
            xytext=(start - 0.5, 1.025),
            xycoords=("data", "axes fraction"),
            textcoords=("data", "axes fraction"),
            arrowprops=dict(arrowstyle="-", color=MODALITY_COLORS[mod],
                            lw=3, connectionstyle="arc3,rad=0"),
            annotation_clip=False,
        )

    ax.set_title(
        "Artifact source-leakage across 13 OOD methods x 7 cross-source normal-vs-normal pairs",
        fontsize=FONT_SIZE, pad=28,
    )
    ax.set_xlabel("Dataset Pair (grouped by modality)", labelpad=6)
    ax.set_ylabel("OOD Method (sorted by mean raw AUROC, descending)")

    fig.tight_layout()
    save(fig, "fig_v5_heatmap_13x7")

    # Print key values for verifier
    print("  [verifier info] method mean AUROC (descending):")
    for m in methods_sorted:
        print(f"    {m:12s}  mean={method_mean[m]:.4f}")


# ═══════════════════════════════════════════════════════════════════════════════
# Fig 2 — ViM source-leakage dual bar (7 pairs, raw + cleanC)
# ═══════════════════════════════════════════════════════════════════════════════
def plot_vim_leakage_v5() -> None:
    print("[fig_v5_vim_leakage] reading raw + cleanC ranking CSVs ...")
    raw_df   = pd.read_csv(RES / "l3_raw_ranking.csv")
    clean_df = pd.read_csv(RES / "l3_cleanC_ranking.csv")

    # ViM raw AUROC for all 7 pairs
    vim_raw = {}
    for p in ALL_PAIRS:
        row = raw_df[(raw_df["pair"] == p) & (raw_df["method"] == "ViM") &
                     (raw_df["subset"] == "raw")]
        vim_raw[p] = float(row["auroc"].iloc[0]) if len(row) > 0 else np.nan

    # ViM cleanC AUROC — subset==cleanC (evaluable) or cleanC_INSUF
    vim_clean = {}
    vim_clean_na = {}    # True if BraTS N/A
    for p in ALL_PAIRS:
        row_ev = clean_df[(clean_df["pair"] == p) & (clean_df["method"] == "ViM") &
                          (clean_df["subset"] == "cleanC")]
        row_in = clean_df[(clean_df["pair"] == p) & (clean_df["method"] == "ViM") &
                          (clean_df["subset"] == "cleanC_INSUF")]
        if len(row_ev) > 0:
            vim_clean[p] = float(row_ev["auroc"].iloc[0])
            vim_clean_na[p] = False
        elif len(row_in) > 0:
            vim_clean[p] = np.nan
            vim_clean_na[p] = True
        else:
            vim_clean[p] = np.nan
            vim_clean_na[p] = False

    # Sort pairs by modality then pair name (CXR, BrainMRI, Derm)
    mod_order = ["CXR", "BrainMRI", "Dermoscopy"]
    pairs_sorted = sorted(ALL_PAIRS,
                          key=lambda p: (mod_order.index(MODALITY[p]), p))

    fig, ax = plt.subplots(figsize=(13, 5.5))

    x = np.arange(len(pairs_sorted))
    bar_w = 0.35

    # Raw bars (solid)
    raw_vals = [vim_raw.get(p, np.nan) for p in pairs_sorted]
    bars_raw = ax.bar(x - bar_w / 2, raw_vals, bar_w,
                      label="Raw AUROC", color=CB["red"], alpha=0.85,
                      zorder=3)

    # CleanC bars (hatch pattern)
    clean_vals = []
    for p in pairs_sorted:
        if vim_clean_na[p]:
            clean_vals.append(0.0)   # placeholder; annotated separately
        else:
            clean_vals.append(vim_clean.get(p, np.nan))

    bars_clean = ax.bar(x + bar_w / 2, clean_vals, bar_w,
                        label="Clean-C AUROC", color=CB["sky"], alpha=0.75,
                        hatch="////", edgecolor="black", linewidth=0.6,
                        zorder=3)

    # BraTS N/A annotation
    for i, p in enumerate(pairs_sorted):
        if vim_clean_na[p]:
            ax.text(i + bar_w / 2, 0.32, "N/A\n(n<30)",
                    ha="center", va="bottom", fontsize=8,
                    color="0.4", style="italic")

    # Annotate raw bar values
    for i, (p, rv) in enumerate(zip(pairs_sorted, raw_vals)):
        if not np.isnan(rv):
            ax.text(i - bar_w / 2, rv + 0.005, f"{rv:.2f}",
                    ha="center", va="bottom", fontsize=8.5, color="white",
                    fontweight="bold",
                    bbox=dict(boxstyle="round,pad=0.1", fc=CB["red"],
                              ec="none", alpha=0.85))

    # Annotate cleanC bar values (evaluable only)
    for i, p in enumerate(pairs_sorted):
        cv = vim_clean.get(p, np.nan)
        if not vim_clean_na[p] and not np.isnan(cv):
            ax.text(i + bar_w / 2, cv + 0.005, f"{cv:.2f}",
                    ha="center", va="bottom", fontsize=8.5, color="black",
                    fontweight="bold",
                    bbox=dict(boxstyle="round,pad=0.1", fc=CB["sky"],
                              ec="none", alpha=0.85))

    # A-5 gate line at 0.95
    ax.axhline(0.95, color=CB["red"], linestyle="--", linewidth=1.6,
               label="A-5 gate (0.95)", zorder=4)

    # Modality background shading
    mod_spans = {"CXR": (0, 3), "BrainMRI": (3, 4), "Dermoscopy": (4, 7)}
    mod_alpha = 0.07
    for mod, (s, e) in mod_spans.items():
        ax.axvspan(s - 0.5, e - 0.5, alpha=mod_alpha,
                   color=MODALITY_COLORS[mod], zorder=1)
        ax.text((s + e - 1) / 2.0, 1.095, mod,
                ha="center", va="center", fontsize=9.5,
                fontweight="bold", color=MODALITY_COLORS[mod],
                transform=ax.get_xaxis_transform())

    # Annotation text
    ax.text(0.01, 0.97,
            "ViM raw AUROC = 1.0 on 7/7 pairs;\n"
            "cleanC = 1.0 on 6/6 evaluable\n"
            "(L2 decontam vacuous for ViM -> deep source leakage)",
            transform=ax.transAxes,
            ha="left", va="top", fontsize=8.5,
            bbox=dict(boxstyle="round,pad=0.4", fc="lightyellow",
                      ec="0.5", alpha=0.90))

    ax.set_xticks(x)
    ax.set_xticklabels([PAIR_SHORT[p] for p in pairs_sorted],
                       ha="center", fontsize=9)
    ax.set_ylabel("ViM AUROC")
    ax.set_ylim(0.28, 1.12)
    ax.set_xlim(-0.6, len(pairs_sorted) - 0.4)
    ax.set_title(
        "ViM Source-Leakage: Raw vs Clean-C AUROC across 7 normal-vs-normal pairs",
        fontsize=FONT_SIZE, pad=20,
    )
    ax.legend(loc="lower right", framealpha=0.85)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

    fig.tight_layout()
    save(fig, "fig_v5_vim_leakage")

    # Print verifier info
    print("  [verifier info] ViM AUROC values:")
    for p in pairs_sorted:
        rv  = vim_raw.get(p, np.nan)
        cv  = vim_clean.get(p, np.nan)
        na  = vim_clean_na[p]
        tag = "N/A" if na else f"{cv:.4f}"
        print(f"    {p:45s}  raw={rv:.4f}  cleanC={tag}")


# ═══════════════════════════════════════════════════════════════════════════════
# Fig 3 — A-4 Spearman negative result: 6 evaluable pairs + 95% CI
# ═══════════════════════════════════════════════════════════════════════════════
def plot_a4_negative() -> None:
    print("[fig_v5_a4_negative] reading a4_bootstrap_spearman.csv ...")
    df = pd.read_csv(RES / "a4_bootstrap_spearman.csv")

    # Exclude BraTS (INSUFFICIENT)
    evaluable = df[~df["A4_verdict"].str.startswith("INSUFFICIENT")].copy()
    evaluable = evaluable.reset_index(drop=True)

    # Sort by modality then pair name
    mod_order = ["CXR", "BrainMRI", "Dermoscopy"]
    evaluable["_mod"] = evaluable["pair"].map(MODALITY)
    evaluable["_mod_ord"] = evaluable["_mod"].map(lambda m: mod_order.index(m))
    evaluable = evaluable.sort_values(["_mod_ord", "pair"]).reset_index(drop=True)

    pairs   = evaluable["pair"].tolist()
    points  = evaluable["spearman_point"].values
    ci_lo   = evaluable["ci_lower"].values
    ci_hi   = evaluable["ci_upper"].values
    mods    = evaluable["_mod"].tolist()

    fig, ax = plt.subplots(figsize=(10, 5))

    x = np.arange(len(pairs))

    # Error bars: asymmetric (point - ci_lo, ci_hi - point)
    err_lo = points - ci_lo
    err_hi = ci_hi - points

    # Color by modality
    point_colors = [MODALITY_COLORS[m] for m in mods]

    for i in range(len(pairs)):
        ax.errorbar(x[i], points[i],
                    yerr=[[err_lo[i]], [err_hi[i]]],
                    fmt="o", markersize=9,
                    color=point_colors[i],
                    ecolor=point_colors[i],
                    elinewidth=2.0, capsize=5, capthick=2.0,
                    zorder=5)
        # Annotate point value
        ax.text(x[i], points[i] + err_hi[i] + 0.025,
                f"{points[i]:.3f}",
                ha="center", va="bottom", fontsize=8.5,
                color=point_colors[i], fontweight="bold")

    # A-4 gate at 0.7 (CI upper < 0.7 required for "flip")
    ax.axhline(0.7, color=CB["red"], linestyle="--", linewidth=1.8,
               label="A-4 gate: Spearman = 0.7", zorder=4)

    # Zero line
    ax.axhline(0.0, color="0.6", linestyle=":", linewidth=1.0, zorder=3)

    # Modality legend patches
    legend_patches = [
        mpatches.Patch(color=MODALITY_COLORS[m], label=m)
        for m in mod_order if m in set(mods)
    ]
    legend_patches.append(
        plt.Line2D([0], [0], color=CB["red"], linestyle="--",
                   linewidth=1.8, label="A-4 gate (0.7)")
    )
    ax.legend(handles=legend_patches, loc="lower right", framealpha=0.85,
              fontsize=FONT_SIZE - 1)

    # Right-top annotation
    ax.text(0.98, 0.97,
            "All CI upper bounds > 0.7 even with 13 methods\n"
            "-> structural low-power (pre-specified)",
            transform=ax.transAxes,
            ha="right", va="top", fontsize=8.5,
            bbox=dict(boxstyle="round,pad=0.4", fc="lightyellow",
                      ec="0.5", alpha=0.90))

    ax.set_xticks(x)
    ax.set_xticklabels([PAIR_SHORT[p] for p in pairs],
                       ha="center", fontsize=9)
    ax.set_ylabel("Spearman(raw rank, cleanC rank)")
    ax.set_ylim(-0.25, 1.18)
    ax.set_xlim(-0.6, len(pairs) - 0.4)
    ax.set_title(
        "A-4 Negative Result: Ranking Correlation Raw vs Clean-C "
        "(6 evaluable pairs, 13 methods, 95% bootstrap CI)",
        fontsize=FONT_SIZE, pad=8,
    )
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

    fig.tight_layout()
    save(fig, "fig_v5_a4_negative")

    # Print verifier info
    print("  [verifier info] Spearman point + CI:")
    for _, row in evaluable.iterrows():
        print(f"    {row['pair']:45s}  rho={row['spearman_point']:.4f}  "
              f"CI=[{row['ci_lower']:.4f}, {row['ci_upper']:.4f}]  "
              f"verdict={row['A4_verdict']}")


# ═══════════════════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    print("=== ArtiOODBench v5 figure generation ===")
    print(f"Output dir: {FIG}\n")

    plot_heatmap_13x7()
    plot_vim_leakage_v5()
    plot_a4_negative()

    print("\nDone. All v5 figures written to:", FIG)
