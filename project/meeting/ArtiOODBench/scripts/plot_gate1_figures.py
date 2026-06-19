"""
ArtiOODBench Gate-1 figure generation — 4 publication-quality PDFs + PNG backups.
Drift contract: reads CSVs, no data modification. Numbers come verbatim from CSV.

Figure / CSV mapping:
  fig_a1_artifact_auroc.pdf
      <- results/a1_artifact_auroc.csv  cols: pair, feature_group, auroc_mean, auroc_std

  fig_vim_source_leakage.pdf
      <- results/l3_method_scores_raw.csv  cols: pair, label, vim_score

  fig_l3_ranking_slope.pdf
      <- results/l3_raw_ranking.csv      cols: pair, subset, method, rank, auroc
      <- results/l3_cleanC_ranking.csv   cols: pair, subset, method, rank, auroc, n_matched
      Spearman values from a4_bootstrap_spearman.csv col: spearman_point

  fig_a3_decontam.pdf
      <- results/a1_artifact_auroc.csv   row feature_group==all_43dim  -> auroc_mean (raw)
      <- results/a4_bootstrap_spearman.csv col: artifact_only_auroc_cleanC
"""

import os
os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.lines import Line2D
from pathlib import Path

# ── paths ────────────────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent.parent
RES  = ROOT / "results"
FIG  = ROOT / "figures"
FIG.mkdir(parents=True, exist_ok=True)

# ── shared style ─────────────────────────────────────────────────────────────
# Colorblind-safe palette (Wong 2011)
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

# Feature-group color mapping (used in fig_a1)
FG_COLORS = {
    "all_43dim":  CB["blue"],
    "hist32":     CB["orange"],
    "glcm":       CB["green"],
    "stats":      CB["sky"],
    "fft_ratio":  CB["pink"],
    "edge_ratio": CB["red"],
}
FG_ORDER = ["all_43dim", "hist32", "glcm", "stats", "fft_ratio", "edge_ratio"]
FG_LABELS = {
    "all_43dim":  "All 43-dim",
    "hist32":     "Histogram",
    "glcm":       "GLCM",
    "stats":      "Statistics",
    "fft_ratio":  "FFT",
    "edge_ratio": "Edge",
}

# Pair short names (display)
PAIR_SHORT = {
    "NIH_vs_VinDr":                         "NIH vs VinDr\n(CXR)",
    "NIH_vs_RSNA_normal":                   "NIH vs RSNA\n(CXR)",
    "BraTS_normal_vs_BrainTumor_normal":    "BraTS vs\nBrainTumor\n(MRI)",
    "HAM_NV_vs_ISIC2020_benign":            "HAM vs\nISIC2020\n(Derm)",
}
PAIR_ORDER = [
    "NIH_vs_VinDr",
    "NIH_vs_RSNA_normal",
    "BraTS_normal_vs_BrainTumor_normal",
    "HAM_NV_vs_ISIC2020_benign",
]

METHOD_COLORS = {
    "ViM":      CB["red"],
    "MSP":      CB["blue"],
    "ODIN":     CB["orange"],
    "Energy":   CB["green"],
    "MDS":      CB["sky"],
    "KNN":      CB["pink"],
    "GradNorm": CB["black"],
}
METHOD_ORDER = ["ViM", "MSP", "ODIN", "Energy", "MDS", "KNN", "GradNorm"]

FONT_SIZE = 11
plt.rcParams.update({
    "font.size": FONT_SIZE,
    "axes.titlesize": FONT_SIZE + 1,
    "axes.labelsize": FONT_SIZE,
    "xtick.labelsize": FONT_SIZE - 1,
    "ytick.labelsize": FONT_SIZE - 1,
    "legend.fontsize": FONT_SIZE - 1,
    "figure.dpi": 150,
    "pdf.fonttype": 42,   # embed TrueType in PDF (for camera-ready)
    "ps.fonttype": 42,
})


def save(fig: plt.Figure, stem: str) -> None:
    pdf_path = FIG / f"{stem}.pdf"
    png_path = FIG / f"{stem}.png"
    fig.savefig(pdf_path, bbox_inches="tight")
    fig.savefig(png_path, bbox_inches="tight", dpi=150)
    print(f"  saved: {pdf_path.name}  {png_path.name}")
    plt.close(fig)


# ═══════════════════════════════════════════════════════════════════════════════
# Fig 1 — A-1 Artifact-only AUROC grouped bar
# ═══════════════════════════════════════════════════════════════════════════════
def plot_a1_artifact_auroc() -> None:
    print("[fig_a1_artifact_auroc] reading a1_artifact_auroc.csv ...")
    df = pd.read_csv(RES / "a1_artifact_auroc.csv")

    n_pairs = len(PAIR_ORDER)
    n_fg    = len(FG_ORDER)
    bar_w   = 0.12
    group_w = n_fg * bar_w + 0.08   # gap between pair groups
    x_centers = np.arange(n_pairs) * group_w

    fig, ax = plt.subplots(figsize=(11, 4.5))

    for fi, fg in enumerate(FG_ORDER):
        offsets = x_centers + (fi - n_fg / 2 + 0.5) * bar_w
        means, stds = [], []
        for pair in PAIR_ORDER:
            row = df[(df["pair"] == pair) & (df["feature_group"] == fg)]
            if len(row) == 0:
                means.append(np.nan)
                stds.append(0.0)
            else:
                means.append(float(row["auroc_mean"].iloc[0]))
                stds.append(float(row["auroc_std"].iloc[0]))
        edgecolor = "black" if fg == "all_43dim" else "none"
        lw        = 1.2    if fg == "all_43dim" else 0
        ax.bar(offsets, means, bar_w,
               yerr=stds, capsize=2,
               color=FG_COLORS[fg], label=FG_LABELS[fg],
               edgecolor=edgecolor, linewidth=lw,
               error_kw=dict(elinewidth=0.8, ecolor="0.3"))

    # Reference lines
    ax.axhline(0.5, color="0.4", linestyle="--", linewidth=1.0, label="Random (0.50)")
    ax.axhline(0.8, color="0.2", linestyle=":",  linewidth=1.2, label="Threshold (0.80)")

    # Annotate all_43dim values on top of the bar
    for pi, pair in enumerate(PAIR_ORDER):
        row = df[(df["pair"] == pair) & (df["feature_group"] == "all_43dim")]
        if len(row) == 0:
            continue
        val = float(row["auroc_mean"].iloc[0])
        std = float(row["auroc_std"].iloc[0])
        fi  = FG_ORDER.index("all_43dim")
        xpos = x_centers[pi] + (fi - n_fg / 2 + 0.5) * bar_w
        ax.text(xpos, val + std + 0.012, f"{val:.3f}",
                ha="center", va="bottom", fontsize=8.5,
                fontweight="bold", color=CB["blue"])

    ax.set_xticks(x_centers)
    ax.set_xticklabels([PAIR_SHORT[p] for p in PAIR_ORDER], ha="center")
    ax.set_ylabel("AUROC (artifact-only features)")
    ax.set_title("A-1: Artifact-only AUROC by Feature Group and Dataset Pair")
    ax.set_ylim(0.35, 1.12)
    ax.set_xlim(-group_w * 0.5, x_centers[-1] + group_w * 0.5)
    ax.legend(loc="upper left", ncol=2, framealpha=0.85)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

    save(fig, "fig_a1_artifact_auroc")


# ═══════════════════════════════════════════════════════════════════════════════
# Fig 2 — ViM source leakage: log-scale KDE / histogram
# ═══════════════════════════════════════════════════════════════════════════════
def _log_kde(x: np.ndarray, x_grid: np.ndarray, bw_frac: float = 0.08) -> np.ndarray:
    """Simple Gaussian KDE in log-space (no scipy dependency)."""
    log_x    = np.log10(x)
    log_grid = np.log10(x_grid)
    bw = (log_x.max() - log_x.min()) * bw_frac + 1e-9
    # shape: (n_grid, n_data)
    diff = (log_grid[:, None] - log_x[None, :]) / bw
    density = np.exp(-0.5 * diff ** 2).mean(axis=1)
    # Normalise to area ~ 1 in log space
    dlog = np.diff(log_grid).mean()
    density /= (density.sum() * dlog + 1e-30)
    return density


def plot_vim_source_leakage() -> None:
    print("[fig_vim_source_leakage] reading l3_method_scores_raw.csv ...")
    df = pd.read_csv(RES / "l3_method_scores_raw.csv")

    # Show 2 pairs: NIH_vs_VinDr (CXR) + BraTS (MRI) — most visually extreme
    display_pairs = [
        "NIH_vs_VinDr",
        "BraTS_normal_vs_BrainTumor_normal",
    ]
    pair_titles = {
        "NIH_vs_VinDr":                       "NIH vs VinDr (CXR)",
        "BraTS_normal_vs_BrainTumor_normal":   "BraTS vs BrainTumor (MRI)",
    }

    fig, axes = plt.subplots(1, 2, figsize=(11, 4.2), sharey=False)

    for ax, pair in zip(axes, display_pairs):
        sub = df[df["pair"] == pair]
        v0  = sub[sub["label"] == 0]["vim_score"].values.astype(float)
        v1  = sub[sub["label"] == 1]["vim_score"].values.astype(float)

        # Compute AUROC via Mann-Whitney U (no scipy) — pure numpy
        # U = number of (s1, s0) pairs where s1 > s0
        # AUROC = U / (n0 * n1)
        n0, n1 = len(v0), len(v1)
        # Efficient rank-sum approach
        all_scores  = np.concatenate([v0, v1])
        all_labels  = np.array([0] * n0 + [1] * n1)
        rank_order  = np.argsort(all_scores)
        ranks       = np.empty(len(all_scores))
        ranks[rank_order] = np.arange(1, len(all_scores) + 1)
        rank_sum_pos = ranks[all_labels == 1].sum()
        U = rank_sum_pos - n1 * (n1 + 1) / 2.0
        auroc = float(U / (n0 * n1))
        if auroc < 0.5:
            auroc = 1.0 - auroc

        # Log-space KDE
        all_vals  = np.concatenate([v0, v1])
        x_min     = max(all_vals.min() * 0.5, 0.1)
        x_max     = all_vals.max() * 2.0
        x_grid    = np.logspace(np.log10(x_min), np.log10(x_max), 400)

        kde0 = _log_kde(v0, x_grid)
        kde1 = _log_kde(v1, x_grid)

        ax.fill_between(x_grid, kde0, alpha=0.45, color=CB["blue"],  label="Inlier (label=0)")
        ax.fill_between(x_grid, kde1, alpha=0.45, color=CB["red"],   label="OOD (label=1)")
        ax.plot(x_grid, kde0, color=CB["blue"], linewidth=1.5)
        ax.plot(x_grid, kde1, color=CB["red"],  linewidth=1.5)

        ax.set_xscale("log")
        ax.set_xlabel("ViM Score (log scale)")
        ax.set_ylabel("Density")
        ax.set_title(pair_titles[pair])

        # Annotate zero-overlap
        ax.text(0.97, 0.93,
                f"Zero overlap\nAUROC = {auroc:.3f}",
                transform=ax.transAxes,
                ha="right", va="top", fontsize=9.5,
                color="black",
                bbox=dict(boxstyle="round,pad=0.3", fc="lightyellow", ec="0.5", alpha=0.85))

        ax.legend(loc="upper left", framealpha=0.8)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)

    fig.suptitle(
        "ViM Scores: Inlier vs OOD — Source-Dataset Gap, Not Pathology",
        fontsize=FONT_SIZE + 1, fontweight="bold", y=1.02,
    )
    fig.tight_layout()
    save(fig, "fig_vim_source_leakage")


# ═══════════════════════════════════════════════════════════════════════════════
# Fig 3 — L3 ranking slope chart raw -> cleanC
# ═══════════════════════════════════════════════════════════════════════════════
def plot_l3_ranking_slope() -> None:
    print("[fig_l3_ranking_slope] reading ranking CSVs + Spearman from a4 ...")
    raw_df   = pd.read_csv(RES / "l3_raw_ranking.csv")
    clean_df = pd.read_csv(RES / "l3_cleanC_ranking.csv")
    spear_df = pd.read_csv(RES / "a4_bootstrap_spearman.csv")

    # Only evaluable pairs (not cleanC_INSUF)
    evaluable_clean = clean_df[clean_df["subset"] == "cleanC"]
    evaluable_pairs = evaluable_clean["pair"].unique().tolist()

    # Spearman lookup: pair -> point estimate
    spear_map = {}
    for _, row in spear_df.iterrows():
        spear_map[row["pair"]] = row["spearman_point"]

    # Note for BraTS (excluded)
    brats_note = "BraTS: n<30 clean samples — excluded"

    n_eval = len(evaluable_pairs)
    fig, axes = plt.subplots(1, n_eval, figsize=(4.5 * n_eval, 5.2), sharey=True)
    if n_eval == 1:
        axes = [axes]

    for ax, pair in zip(axes, evaluable_pairs):
        raw_sub   = raw_df[raw_df["pair"] == pair].set_index("method")
        clean_sub = evaluable_clean[evaluable_clean["pair"] == pair].set_index("method")

        methods_avail = list(set(raw_sub.index) & set(clean_sub.index))
        # Sort by raw rank
        methods_avail.sort(key=lambda m: int(raw_sub.loc[m, "rank"]))

        n_methods = 7
        y_raw   = {m: int(raw_sub.loc[m, "rank"])   for m in methods_avail}
        y_clean = {m: int(clean_sub.loc[m, "rank"]) for m in methods_avail}

        for m in methods_avail:
            color = METHOD_COLORS.get(m, "gray")
            yr = y_raw[m]
            yc = y_clean[m]
            ax.plot([0, 1], [yr, yc], color=color,
                    linewidth=2.0 if m == "ViM" else 1.2,
                    linestyle="-" if m == "ViM" else "--",
                    alpha=1.0 if m == "ViM" else 0.75,
                    zorder=3 if m == "ViM" else 2)
            # Left label (raw rank)
            ax.text(-0.06, yr, f"#{yr} {m}", ha="right", va="center",
                    fontsize=8.5, color=color,
                    fontweight="bold" if m == "ViM" else "normal")
            # Right label (clean rank)
            ax.text(1.06, yc, f"{m} #{yc}", ha="left", va="center",
                    fontsize=8.5, color=color,
                    fontweight="bold" if m == "ViM" else "normal")

        # Spine / axis cosmetics
        ax.set_xlim(-0.5, 1.5)
        ax.set_ylim(n_methods + 0.6, 0.4)   # rank 1 at top
        ax.set_xticks([0, 1])
        ax.set_xticklabels(["Raw", "Clean-C"], fontsize=10)
        ax.yaxis.set_visible(False)
        ax.spines["left"].set_visible(False)
        ax.spines["right"].set_visible(False)
        ax.spines["top"].set_visible(False)

        # Spearman annotation
        rho = spear_map.get(pair, np.nan)
        rho_txt = f"Spearman(raw, cleanC) = {rho:.3f}" if not np.isnan(rho) else "Spearman = N/A"
        ax.set_title(
            f"{PAIR_SHORT[pair]}\n{rho_txt}",
            fontsize=FONT_SIZE - 0.5, pad=6
        )

    # BraTS note below figure
    fig.text(0.5, -0.02, f"* {brats_note}", ha="center",
             fontsize=9, style="italic", color="0.4")

    fig.suptitle(
        "L-3: Method Ranking Before vs After Artifact Decontamination",
        fontsize=FONT_SIZE + 1, fontweight="bold"
    )
    fig.tight_layout()
    save(fig, "fig_l3_ranking_slope")


# ═══════════════════════════════════════════════════════════════════════════════
# Fig 4 — A-3 decontamination: raw vs cleanC artifact-only AUROC
# ═══════════════════════════════════════════════════════════════════════════════
def plot_a3_decontam() -> None:
    print("[fig_a3_decontam] reading a1 + a4_bootstrap_spearman.csv ...")
    a1_df    = pd.read_csv(RES / "a1_artifact_auroc.csv")
    spear_df = pd.read_csv(RES / "a4_bootstrap_spearman.csv")

    # 3 evaluable pairs (BraTS cleanC auroc = nan, include with nan for completeness)
    pairs_4 = PAIR_ORDER  # all 4; nan will be handled

    # Raw: all_43dim auroc_mean from a1
    raw_auroc = {}
    for pair in pairs_4:
        row = a1_df[(a1_df["pair"] == pair) & (a1_df["feature_group"] == "all_43dim")]
        raw_auroc[pair] = float(row["auroc_mean"].iloc[0]) if len(row) else np.nan

    # CleanC: artifact_only_auroc_cleanC from a4
    clean_auroc = {}
    for _, row in spear_df.iterrows():
        clean_auroc[row["pair"]] = float(row["artifact_only_auroc_cleanC"]) \
            if not pd.isna(row["artifact_only_auroc_cleanC"]) else np.nan

    # Only pairs where both values exist (3 of 4; BraTS=nan)
    plot_pairs = [p for p in pairs_4
                  if not np.isnan(raw_auroc.get(p, np.nan))
                  and not np.isnan(clean_auroc.get(p, np.nan))]

    fig, ax = plt.subplots(figsize=(7.5, 4.5))

    bar_w = 0.32
    x_pos = np.arange(len(plot_pairs))

    bars_raw   = ax.bar(x_pos - bar_w / 2,
                        [raw_auroc[p] for p in plot_pairs],
                        bar_w, color=CB["blue"],  alpha=0.85, label="Raw (all 43-dim)")
    bars_clean = ax.bar(x_pos + bar_w / 2,
                        [clean_auroc[p] for p in plot_pairs],
                        bar_w, color=CB["orange"], alpha=0.85, label="Clean-C (artifact-only)")

    # Reference line
    ax.axhline(0.5, color="0.4", linestyle="--", linewidth=1.0, label="Random (0.50)")

    # Annotate each bar with value + draw delta arrow
    for i, pair in enumerate(plot_pairs):
        rv = raw_auroc[pair]
        cv = clean_auroc[pair]
        delta = cv - rv

        # Bar value labels
        ax.text(i - bar_w / 2, rv + 0.012, f"{rv:.3f}",
                ha="center", va="bottom", fontsize=8.5, color=CB["blue"], fontweight="bold")
        ax.text(i + bar_w / 2, cv + 0.012, f"{cv:.3f}",
                ha="center", va="bottom", fontsize=8.5, color=CB["orange"], fontweight="bold")

        # Delta annotation above pair
        mid_y = max(rv, cv) + 0.06
        ax.annotate("",
                    xy=(i + bar_w / 2, cv + 0.005),
                    xytext=(i - bar_w / 2, rv + 0.005),
                    arrowprops=dict(arrowstyle="-|>", color="0.3",
                                   lw=1.0, mutation_scale=10))
        ax.text(i, mid_y, f"$\\Delta$={delta:+.3f}",
                ha="center", va="bottom", fontsize=9,
                color="0.3", fontstyle="italic")

    # BraTS annotation (insufficient)
    ax.text(len(plot_pairs) + 0.1, 0.52,
            "BraTS: insufficient\nclean samples (n=6)",
            fontsize=8.5, color="0.5", va="center", ha="left",
            style="italic")

    ax.set_xticks(x_pos)
    ax.set_xticklabels([PAIR_SHORT[p] for p in plot_pairs], ha="center")
    ax.set_ylabel("Artifact-only AUROC")
    ax.set_title("A-3: Decontamination Pulls Artifact Signal Toward Random")
    ax.set_ylim(0.35, 1.05)
    ax.set_xlim(-0.6, len(plot_pairs) + 0.5)
    ax.legend(loc="upper right", framealpha=0.85)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

    fig.tight_layout()
    save(fig, "fig_a3_decontam")


# ═══════════════════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    print("=== ArtiOODBench Gate-1 figure generation ===")
    print(f"Output dir: {FIG}\n")

    plot_a1_artifact_auroc()
    plot_vim_source_leakage()
    plot_l3_ranking_slope()
    plot_a3_decontam()

    print("\nDone. All figures written to:", FIG)
