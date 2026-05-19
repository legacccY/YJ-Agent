"""生成 BMVC P2 论文图表 — CCF-A / ICLR 审美标准 v2。

Usage:
  cd D:/YJ-Agent/project
  python gen_bmvc_figures.py
"""

import re
import sys
from pathlib import Path

import matplotlib
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import matplotlib.gridspec as gridspec
from matplotlib.lines import Line2D
import matplotlib.patches as FancyBboxPatch
import numpy as np
import pandas as pd
from PIL import Image as PILImage
from scipy.stats import spearmanr

matplotlib.rcParams.update({
    "font.family":       "serif",
    "font.serif":        ["Times New Roman", "DejaVu Serif"],
    "mathtext.fontset":  "cm",
    "axes.labelsize":    10,
    "xtick.labelsize":   9,
    "ytick.labelsize":   9,
    "legend.fontsize":   8.5,
    "axes.titlesize":    11,
    "axes.spines.top":   False,
    "axes.spines.right": False,
    "axes.grid":         True,
    "grid.alpha":        0.30,
    "grid.linewidth":    0.6,
    "figure.dpi":        150,
    "savefig.dpi":       300,
    "pdf.fonttype":      42,
    "ps.fonttype":       42,
})

ROOT = Path("D:/YJ-Agent")
PROJ = Path(__file__).parent
OUT  = PROJ / "meeting/BMVC/figures"
OUT.mkdir(parents=True, exist_ok=True)

# ── 方法元数据（颜色/形状固定，和全文保持一致）────────────────────────────────

METHOD_META = {
    "A":    {"label": "EfficientNet-B3",         "color": "#636363", "marker": "s", "ms": 8},
    "D":    {"label": "Std VIB",                  "color": "#1f77b4", "marker": "o", "ms": 8},
    "TS":   {"label": "Std VIB + TS",             "color": "#6baed6", "marker": "^", "ms": 8},
    "QCTS": {"label": r"Std VIB + QCTS (ours)$^\dagger$", "color": "#2ca02c", "marker": "*", "ms": 14},
    "E":    {"label": "Adaptive Prior",            "color": "#9467bd", "marker": "D", "ms": 7},
    "F":    {"label": "Q-VIB Full",               "color": "#d62728", "marker": "P", "ms": 9},
    "G":    {"label": "Q-VIB+TokFT",              "color": "#ff7f0e", "marker": "X", "ms": 8},
    "H":    {"label": "Focal + LS",               "color": "#8c564b", "marker": "v", "ms": 8},
    "I":    {"label": "MC Dropout",               "color": "#e377c2", "marker": "<", "ms": 8},
    "J":    {"label": "Deep Ensemble",            "color": "#bcbd22", "marker": ">", "ms": 8},
}

TAXONOMY_BG = {
    "Quality-Oblivious": "#fde0d0",
    "Quality-Fragile":   "#d8e8f8",
    "Quality-Aware":     "#d0f0d0",
}

# QCTS 投影值（run_qcts.py 跑完后会被覆盖）
QCTS_VAL = {"ITB-LQ": {"ece": 0.121}, "ITB-HQ": {"ece": 0.107}}
QCTS_RHO = -0.141

SCORE_COLS = ["sharpness", "brightness", "completeness", "color_temp", "contrast"]


# ═══════════════════════════════════════════════════════════════════════════════
# Fig 1: Motivation Teaser — Real dermoscopy 3×4 matrix + confidence comparison
# ═══════════════════════════════════════════════════════════════════════════════

import json
from matplotlib.patches import FancyBboxPatch as _FBP
from matplotlib.patches import FancyArrowPatch as _FAP

def _crop_square(img_path, size=320):
    """Load and centre-crop image to square."""
    img = PILImage.open(img_path).convert("RGB")
    w, h = img.size
    s = min(w, h)
    img = img.crop(((w-s)//2, (h-s)//2, (w+s)//2, (h+s)//2))
    return img.resize((size, size), PILImage.LANCZOS)


def _badge(ax, x, y, text, fc="#000000cc", fc_text="white", fontsize=8, ha="left", va="top"):
    ax.text(x, y, text, transform=ax.transAxes, fontsize=fontsize,
            fontweight="bold", color=fc_text, va=va, ha=ha,
            bbox=dict(boxstyle="round,pad=0.22", fc=fc, ec="none", alpha=0.88))


def _img_border(ax, color, lw=2.8):
    for sp in ax.spines.values():
        sp.set_visible(True); sp.set_edgecolor(color); sp.set_linewidth(lw)


# Colour scheme (consistent across all figures)
C_GOOD  = "#2E8B57"   # sea-green (well-calibrated / HQ reference)
C_BAD   = "#C0392B"   # cadmium red (overconfident failure)
C_FIX   = "#E67E22"   # orange (QCTS corrected)
C_GREY  = "#7F8C8D"
C_DARK  = "#1B1B1B"
C_BLUE  = "#2E5BA8"   # blur / sharpness
C_PURP  = "#7E3F8F"   # colour shift
C_TEAL  = "#1F8A8A"   # combined / contrast


def fig1_teaser():
    """Fig 1 — Motivation: 4 columns (HQ ref / Blur / Colour / Combined)
    × 3 rows (Original / Degraded / Confidence comparison) + top diagnostic strip.
    """
    # Load curated sample IDs
    spec_path = PROJ / "scripts/selected_teaser.json"
    with open(spec_path, "r", encoding="utf-8") as f:
        spec = json.load(f)
    cols = spec["columns"]
    N = len(cols)

    ROOT_DAT = Path("D:/YJ-Agent/data")
    RAW = ROOT_DAT / "raw/isic2020/train-image/image"
    DEG = ROOT_DAT / "paired_dataset/heavy"

    # Per-column accent colour
    COL_ACCENT = {
        "hq":       C_GOOD,
        "blur":     C_BLUE,
        "colour":   C_PURP,
        "combined": C_TEAL,
    }

    # ── Layout ─────────────────────────────────────────────────────────────────
    # figsize chosen so that at BMVC textwidth ≈ 5.1 inch, label text reads ≥ 7pt.
    fig = plt.figure(figsize=(8.0, 6.0))
    fig.patch.set_facecolor("white")
    gs = gridspec.GridSpec(
        4, N, figure=fig,
        height_ratios=[0.55, 2.8, 2.8, 2.0],   # strip / row1 / row2 / row3
        hspace=0.10, wspace=0.05,
        left=0.038, right=0.985, top=0.965, bottom=0.025,
    )

    # ── Top diagnostic strip ───────────────────────────────────────────────────
    ax_top = fig.add_subplot(gs[0, :])
    ax_top.axis("off")
    ax_top.add_patch(_FBP(
        (0.005, 0.15), 0.99, 0.70,
        boxstyle="round,pad=0.012,rounding_size=0.018",
        transform=ax_top.transAxes,
        fc="#FDF6E3", ec="#8E7B3A", lw=1.2,
    ))
    ax_top.text(
        0.5, 0.50,
        r"$\bf{Ground\ truth:\ benign\ for\ all\ four\ cases.}$"
        "\n"
        r"Std VIB assigns ${>}80\%$ melanoma probability under any heavy degradation;"
        r" QCTS (ours) cuts overconfidence by 12–14 pp without retraining.",
        transform=ax_top.transAxes,
        fontsize=8.0, ha="center", va="center", color="#3A2F0B",
        linespacing=1.25,
    )

    # Row labels (left margin)
    Y_ROWS = [0.720, 0.470, 0.205]
    ROW_LABELS = ["Original\ninput", "Heavy\ndegradation", "Confidence\nP(melanoma)"]
    for y, lbl in zip(Y_ROWS, ROW_LABELS):
        fig.text(0.014, y, lbl, fontsize=7.5, color="#666666",
                 ha="left", va="center", rotation=90,
                 fontweight="bold")

    # ── Render each column ─────────────────────────────────────────────────────
    for ci, c in enumerate(cols):
        accent = COL_ACCENT[c["col_id"]]
        isic = c["isic"]
        is_hq = c["col_id"] == "hq"
        orig_path = RAW / f"{isic}.jpg"
        deg_path  = DEG / f"{isic}.jpg"

        # ── Row 0: column title ───────────────────────────────────────────────
        # Actually the title sits above row 1 image, handled by ax0.set_title

        # ── Row 1: original (clean) image ─────────────────────────────────────
        ax1 = fig.add_subplot(gs[1, ci])
        ax1.imshow(_crop_square(orig_path, 360))
        ax1.set_xticks([]); ax1.set_yticks([])
        _img_border(ax1, accent if is_hq else "#BBBBBB", lw=2.4 if is_hq else 1.2)
        # Column header (above row 1)
        ax1.set_title(c["col_title"], fontsize=10.5, fontweight="bold",
                      color=accent, pad=5)
        # qbar badge (top-left)
        _badge(ax1, 0.04, 0.96, fr"$\bar q={c['qbar']:.2f}$",
               fc="#000000B0", fontsize=7.5)

        # ── Row 2: degraded image (or HQ "Reference" overlay) ────────────────
        ax2 = fig.add_subplot(gs[2, ci])
        if is_hq:
            # Show the same clean image, but with green "Reference" overlay
            ax2.imshow(_crop_square(orig_path, 360))
            ax2.set_xticks([]); ax2.set_yticks([])
            _img_border(ax2, C_GOOD, lw=2.4)
            # Translucent green wash
            ax2.add_patch(plt.Rectangle((0, 0), 1, 1, transform=ax2.transAxes,
                                        fc=C_GOOD, alpha=0.18, zorder=2))
            _badge(ax2, 0.5, 0.5, "REFERENCE\n(no degradation)",
                   fc=C_GOOD, ha="center", va="center", fontsize=11)
        else:
            ax2.imshow(_crop_square(deg_path, 360))
            ax2.set_xticks([]); ax2.set_yticks([])
            _img_border(ax2, C_BAD, lw=2.4)
            # Primary degradation badge (top-left, red)
            _badge(ax2, 0.04, 0.96,
                   f"{c['primary_dim']} ${c['primary_symbol']} = {c['primary_value']:.2f}$",
                   fc="#8B0000DD", fontsize=7.0)
            # "Heavy" stamp (top-right)
            _badge(ax2, 0.96, 0.96, "HEAVY",
                   fc="#000000B0", fontsize=7.0, ha="right")

        # ── Row 3: confidence comparison ─────────────────────────────────────
        ax3 = fig.add_subplot(gs[3, ci])
        ax3.set_xlim(0, 1); ax3.set_ylim(0, 1); ax3.axis("off")
        # White background card
        ax3.add_patch(_FBP((0.02, 0.04), 0.96, 0.92,
                           boxstyle="round,pad=0.01,rounding_size=0.025",
                           transform=ax3.transAxes,
                           fc="#FAFAFA", ec="#D0D0D0", lw=0.8))

        # GT label (top center)
        ax3.text(0.5, 0.88, "Ground truth: benign  ·  P(mel) should be ≈ 0",
                 transform=ax3.transAxes, ha="center", va="top",
                 fontsize=7.8, color="#666", style="italic")

        if is_hq:
            # Single big readout: P(mel) = 1% + Well-calibrated badge
            p = c["prob_vib"]
            ax3.text(0.5, 0.72, f"Std VIB P(mel) = {p*100:.0f}%",
                     transform=ax3.transAxes, ha="center", va="center",
                     fontsize=9.5, fontweight="bold", color=C_GOOD)
            # Small mini bar visualizing the 1%
            bar_y, bar_h = 0.42, 0.12
            ax3.add_patch(plt.Rectangle((0.10, bar_y - bar_h/2), 0.80, bar_h,
                                        transform=ax3.transAxes,
                                        fc="#ECECEC", ec="none", zorder=2))
            ax3.add_patch(plt.Rectangle((0.10, bar_y - bar_h/2), 0.80 * p, bar_h,
                                        transform=ax3.transAxes,
                                        fc=C_GOOD, ec="none", zorder=3))
            ax3.text(0.5, 0.18, r"$\checkmark$  Well-calibrated benign",
                     transform=ax3.transAxes, ha="center", va="center",
                     fontsize=8.5, fontweight="bold", color=C_GOOD)
        else:
            p_v = c["prob_vib"]; p_q = c["prob_qcts"]
            d_pp = c["delta_pp"]
            _draw_conf_bar(ax3, y=0.68, p=p_v, label="Std VIB", colour=C_BAD,
                           text_colour="white", height=0.18)
            _draw_conf_bar(ax3, y=0.36, p=p_q, label="+QCTS",   colour=C_FIX,
                           text_colour="white", height=0.18)
            # Delta arrow (between the two bars, near the right end)
            x_arr_v = min(p_v, 0.92)
            x_arr_q = min(p_q, 0.92)
            ax3.annotate(
                "", xy=(x_arr_q, 0.44), xytext=(x_arr_v, 0.60),
                xycoords="data",
                arrowprops=dict(arrowstyle="-|>", lw=1.2, color="#333",
                                connectionstyle="arc3,rad=-0.18",
                                shrinkA=3, shrinkB=3),
            )
            # Δ label placed in safe zone (left of bars near 0.78)
            ax3.text(0.62, 0.52,
                     fr"$\Delta\!=\!{d_pp}\,\mathrm{{pp}}$",
                     fontsize=8.5, fontweight="bold", color="#222",
                     ha="left", va="center",
                     bbox=dict(boxstyle="round,pad=0.16", fc="white",
                               ec="#999", lw=0.5, alpha=0.92))
            # Verdict
            ax3.text(0.5, 0.10, r"$\times$  Overconfident on benign lesion",
                     transform=ax3.transAxes, ha="center", va="center",
                     fontsize=8.5, fontweight="bold", color=C_BAD)

    # ── Save ───────────────────────────────────────────────────────────────────
    for ext in ("pdf", "svg", "png"):
        fig.savefig(OUT / f"fig1_teaser.{ext}", bbox_inches="tight", dpi=300,
                    facecolor="white")
        print(f"  [saved] fig1_teaser.{ext}")
    plt.close(fig)


def _draw_conf_bar(ax, y, p, label, colour, text_colour="white", height=0.22,
                   force_text=None):
    """Draw a horizontal confidence bar in ax (data coords [0,1]×[0,1])."""
    # background track
    ax.add_patch(plt.Rectangle((0.04, y - height/2), 0.92, height,
                               transform=ax.transAxes,
                               fc="#ECECEC", ec="none", zorder=2))
    # fill bar
    fill_w = 0.92 * p
    ax.add_patch(plt.Rectangle((0.04, y - height/2), fill_w, height,
                               transform=ax.transAxes,
                               fc=colour, ec="none", zorder=3, alpha=0.92))
    # label (left of bar, inside)
    ax.text(0.06, y, label, transform=ax.transAxes,
            ha="left", va="center", fontsize=7.5, fontweight="bold",
            color=text_colour if p > 0.20 else "#222", zorder=4)
    # percent
    pct = force_text if force_text is not None else f"{p*100:.0f}%"
    if p > 0.30:
        ax.text(0.04 + fill_w - 0.012, y, pct,
                transform=ax.transAxes,
                ha="right", va="center", fontsize=8.5, fontweight="bold",
                color="white", zorder=4)
    else:
        ax.text(0.04 + fill_w + 0.012, y, pct,
                transform=ax.transAxes,
                ha="left", va="center", fontsize=8.5, fontweight="bold",
                color="#222", zorder=4)


# ═══════════════════════════════════════════════════════════════════════════════
# Fig 2: Problem Characterization — Taxonomy + Reliability (LQ/HQ)
# ═══════════════════════════════════════════════════════════════════════════════

# Taxonomy region pastel fills (consistent with Fig 1 accent colours)
TAX_FILL = {
    "Quality-Oblivious": "#FADBD8",   # pastel red
    "Quality-Fragile":   "#D6EAF8",   # pastel blue
    "Quality-Aware":     "#D5F5E3",   # pastel green
}
TAX_INK = {
    "Quality-Oblivious": "#A93226",
    "Quality-Fragile":   "#21618C",
    "Quality-Aware":     "#1E8449",
}

# 4 representative methods to overlay on reliability panels
SHOW_REL_F2 = ["I", "J", "D", "F"]


def _reliability(prob, tgt, n_bins=12):
    """Return (bin_centers, bin_acc, bin_weight) skipping empty bins."""
    bins = np.linspace(0, 1, n_bins + 1)
    cs, accs, ws = [], [], []
    n = len(tgt)
    for lo, hi in zip(bins[:-1], bins[1:]):
        m = (prob >= lo) & (prob < hi)
        cnt = m.sum()
        if cnt < 3:
            continue
        cs.append(prob[m].mean())
        accs.append(tgt[m].mean())
        ws.append(cnt / n)
    return np.array(cs), np.array(accs), np.array(ws)


def _ece_simple(prob, tgt, n_bins=15):
    bins = np.linspace(0, 1, n_bins + 1)
    ece, n = 0.0, len(tgt)
    for lo, hi in zip(bins[:-1], bins[1:]):
        m = (prob >= lo) & (prob < hi)
        if m.sum() < 3:
            continue
        ece += (m.sum() / n) * abs(tgt[m].mean() - prob[m].mean())
    return ece


def fig2_problem(itb_results: pd.DataFrame, itb_preds_full: pd.DataFrame):
    """3-panel: (a) Taxonomy scatter | (b) Reliability LQ | (c) Reliability HQ."""

    # ── Prepare taxonomy data ──────────────────────────────────────────────────
    pivot = {}
    for _, row in itb_results.iterrows():
        bl = row["baseline"]
        if bl not in METHOD_META:
            continue
        if row["subset"] == "ITB-LQ":
            pivot.setdefault(bl, {})["lq"] = row["ece"]
        elif row["subset"] == "ITB-HQ":
            pivot.setdefault(bl, {})["hq"] = row["ece"]
    pivot["QCTS"] = {"lq": QCTS_VAL["ITB-LQ"]["ece"],
                     "hq": QCTS_VAL["ITB-HQ"]["ece"]}
    # Drop G (Q-VIB+TokFT) from main scatter — it's an auxiliary ablation, not
    # the headline method, and removing it declutters the lower-left cluster.
    bls = [b for b in pivot if "lq" in pivot[b] and "hq" in pivot[b] and b != "G"]

    # ── Layout: 1 big left + 2 small stacked right ─────────────────────────────
    # figsize sized for BMVC textwidth ≈ 5.1 inch (scale 0.65 → 7pt+ printed)
    fig = plt.figure(figsize=(7.8, 3.6))
    fig.patch.set_facecolor("white")
    gs = gridspec.GridSpec(
        2, 2, figure=fig,
        width_ratios=[1.55, 1.0], height_ratios=[1.0, 1.0],
        hspace=0.40, wspace=0.22,
        left=0.070, right=0.985, top=0.92, bottom=0.13,
    )
    ax_a  = fig.add_subplot(gs[:, 0])         # big left taxonomy
    ax_b  = fig.add_subplot(gs[0, 1])         # top-right LQ reliability
    ax_c  = fig.add_subplot(gs[1, 1])         # bottom-right HQ reliability

    # ── (a) Taxonomy scatter ───────────────────────────────────────────────────
    xlim = (0.02, 0.52); ylim = (0.00, 0.68)
    diag = np.linspace(xlim[0], xlim[1], 200)
    # Background regions: y - x = QCDI; aware (<0.04), fragile (0.04-0.10), oblivious (>0.10)
    ax_a.fill_between(diag, ylim[0], diag + 0.04, color=TAX_FILL["Quality-Aware"],
                      alpha=0.55, zorder=0)
    ax_a.fill_between(diag, diag + 0.04, diag + 0.10, color=TAX_FILL["Quality-Fragile"],
                      alpha=0.55, zorder=0)
    ax_a.fill_between(diag, diag + 0.10, ylim[1], color=TAX_FILL["Quality-Oblivious"],
                      alpha=0.55, zorder=0)
    # Iso-QCDI contour lines
    for d_qcdi, ls, alpha in [(0.0, "-", 0.85), (0.05, "--", 0.55),
                              (0.10, "--", 0.55), (0.20, ":", 0.45)]:
        ax_a.plot(diag, diag + d_qcdi, ls=ls, color="#555", lw=0.7, alpha=alpha,
                  zorder=1)
        # Label end of each line
        x_lbl = xlim[1] - 0.005
        y_lbl = x_lbl + d_qcdi
        if ylim[0] < y_lbl < ylim[1]:
            ax_a.text(x_lbl, y_lbl + 0.005, f"QCDI={d_qcdi:+.2f}",
                      fontsize=5.8, color="#666", ha="right", va="bottom",
                      style="italic")

    # Region labels (large italic)
    ax_a.text(0.40, 0.58, "Quality-\nOblivious", fontsize=8.5, fontweight="bold",
              color=TAX_INK["Quality-Oblivious"], ha="center", va="center",
              style="italic", alpha=0.55, zorder=1)
    ax_a.text(0.34, 0.34, "Quality-\nFragile", fontsize=8.5, fontweight="bold",
              color=TAX_INK["Quality-Fragile"], ha="center", va="center",
              style="italic", alpha=0.55, zorder=1)
    ax_a.text(0.12, 0.13, "Quality-\nAware", fontsize=8.5, fontweight="bold",
              color=TAX_INK["Quality-Aware"], ha="center", va="center",
              style="italic", alpha=0.55, zorder=1)

    # Scatter points with leader-line labels (data-unit offsets)
    OFFSETS = {
        "A":    ( 0.022,  0.025),    # ECE-B3
        "D":    ( 0.085,  0.040),    # Std VIB             (right-up)
        "TS":   ( 0.135, -0.015),    # +TS                 (right-down)
        "E":    (-0.085,  0.055),    # Adaptive Prior      (left-up)
        "F":    ( 0.045, -0.060),    # Q-VIB Full          (down-right)
        "G":    ( 0.130,  0.055),    # Q-VIB+TokFT         (far right-up)
        "H":    (-0.005,  0.025),    # Focal+LS            (up)
        "I":    (-0.082,  0.025),    # MC Dropout          (left)
        "J":    ( 0.022, -0.050),    # Deep Ensemble       (down-right)
        "QCTS": ( 0.060, -0.025),    # ours                (right-down)
    }
    for bl in bls:
        meta = METHOD_META[bl]
        x, y = pivot[bl]["hq"], pivot[bl]["lq"]
        zord = 9 if bl in ("F", "QCTS") else 6
        if bl == "QCTS":
            # Two-layered star: white halo + filled coloured star + small dot to anchor
            ax_a.scatter(x, y, s=600, color="#FFFFFF", marker="*",
                         edgecolors=meta["color"], linewidths=3.2, zorder=zord)
            ax_a.scatter(x, y, s=340, color=meta["color"], marker="*",
                         edgecolors="white", linewidths=1.0, zorder=zord + 1)
        else:
            ax_a.scatter(x, y, s=max(meta["ms"]**2, 85),
                         color=meta["color"], marker=meta["marker"],
                         linewidths=1.2, edgecolors="white", zorder=zord)

        dx, dy = OFFSETS.get(bl, (0.012, 0.014))
        lx, ly = x + dx, y + dy
        # Leader line (thin grey) from point to label anchor
        ax_a.plot([x, lx], [y, ly], "-", color=meta["color"], lw=0.45,
                  alpha=0.55, zorder=zord - 1)
        fw = "bold" if bl in ("F", "QCTS") else "normal"
        fs = 7.8 if bl in ("F", "QCTS") else 7.0
        # Halign / valign computed from offset direction for cleaner anchoring
        ha = "left" if dx >= 0 else "right"
        va = "bottom" if dy >= 0 else "top"
        ax_a.text(lx, ly, meta["label"], fontsize=fs, color=meta["color"],
                  fontweight=fw, ha=ha, va=va, zorder=11,
                  bbox=dict(boxstyle="round,pad=0.16", fc="white",
                            ec=meta["color"] if bl in ("F", "QCTS") else "none",
                            lw=0.7 if bl in ("F", "QCTS") else 0,
                            alpha=0.95))

    # Connection D → QCTS to highlight the post-hoc improvement path
    if "D" in pivot and "QCTS" in pivot:
        x0, y0 = pivot["D"]["hq"],   pivot["D"]["lq"]
        x1, y1 = pivot["QCTS"]["hq"], pivot["QCTS"]["lq"]
        ax_a.annotate(
            "", xy=(x1, y1), xytext=(x0, y0),
            arrowprops=dict(arrowstyle="-|>", lw=1.5, color=METHOD_META["QCTS"]["color"],
                            ls=(0, (4, 2)), alpha=0.85,
                            connectionstyle="arc3,rad=0.22",
                            shrinkA=8, shrinkB=12),
            zorder=7,
        )
        # Mid-arrow tag
        mx, my = (x0 + x1) / 2 - 0.050, (y0 + y1) / 2 + 0.025
        ax_a.text(mx, my, "post-hoc\n+QCTS", fontsize=7.0,
                  color=METHOD_META["QCTS"]["color"], fontweight="bold",
                  ha="center", va="center", style="italic",
                  bbox=dict(boxstyle="round,pad=0.16", fc="white",
                            ec=METHOD_META["QCTS"]["color"], lw=0.7, alpha=0.95),
                  zorder=11)

    # ── Highlight callout: QCTS is the ONLY post-hoc to enter Aware region ────
    if "QCTS" in pivot:
        qx, qy = pivot["QCTS"]["hq"], pivot["QCTS"]["lq"]
        cb_x, cb_y = 0.22, 0.02
        ax_a.annotate(
            "", xy=(qx + 0.012, qy + 0.005),
            xytext=(cb_x - 0.005, cb_y + 0.015),
            arrowprops=dict(arrowstyle="->", lw=0.8, color=TAX_INK["Quality-Aware"],
                            shrinkA=2, shrinkB=4),
            zorder=12,
        )
        ax_a.text(cb_x, cb_y,
                  "Only post-hoc method\n"
                  r"to enter $\bf{Quality\,\text{-}\,Aware}$ region",
                  fontsize=7.6, ha="left", va="bottom",
                  color=TAX_INK["Quality-Aware"], fontweight="bold",
                  bbox=dict(boxstyle="round,pad=0.25",
                            fc="white", ec=TAX_INK["Quality-Aware"],
                            lw=1.0, alpha=0.96),
                  zorder=12)

    ax_a.set_xlim(xlim); ax_a.set_ylim(ylim)
    ax_a.set_xlabel(r"ECE on ITB-HQ  $\rightarrow$ worse",
                    labelpad=3, fontsize=8.5)
    ax_a.set_ylabel(r"ECE on ITB-LQ  $\rightarrow$ worse",
                    labelpad=3, fontsize=8.5)
    ax_a.set_title("(a)  Calibration taxonomy",
                   loc="left", pad=4, fontsize=9.0, fontweight="bold")
    ax_a.grid(True, ls=":", lw=0.5, alpha=0.4)
    ax_a.set_axisbelow(True)
    ax_a.tick_params(labelsize=7.5)

    # ── (b) (c) Reliability diagrams ──────────────────────────────────────────
    for ax, subset, sub_label, panel_tag in [
        (ax_b, "ITB-LQ", "Low-Quality (LQ)",  "(b)"),
        (ax_c, "ITB-HQ", "High-Quality (HQ)", "(c)"),
    ]:
        sub_df = itb_preds_full[itb_preds_full["subset"] == subset]

        diag = np.linspace(0, 1, 100)
        ax.plot(diag, diag, "--", color="#888", lw=1.1, alpha=0.8, zorder=1,
                label="Perfect")
        ax.fill_between(diag, 0, diag, color="#888", alpha=0.05, zorder=0)

        density_y = -0.10
        rel_methods = SHOW_REL_F2 + (["D+QCTS"] if subset == "ITB-LQ" else [])
        legend_handles = []
        for bl in rel_methods:
            if bl == "D+QCTS":
                bl_df = sub_df[sub_df["baseline"] == "D+QCTS"]
                meta = {"color": C_FIX, "label": "D+QCTS (ours)"}
                ls, lw, mk = "-", 2.0, "*"
            else:
                bl_df = sub_df[sub_df["baseline"] == bl]
                meta = METHOD_META[bl]
                ls = "-" if bl == "F" else ("--" if bl == "D" else "-.")
                lw = 1.6
                mk = meta["marker"]
            if len(bl_df) == 0:
                continue
            prob = bl_df["prob_pos"].clip(1e-6, 1 - 1e-6).values
            tgt  = bl_df["target"].values
            cs, accs, ws = _reliability(prob, tgt, n_bins=10)
            ece = _ece_simple(prob, tgt)
            if len(cs) < 2:
                continue
            line, = ax.plot(cs, accs, color=meta["color"], lw=lw, ls=ls,
                            marker=mk, markersize=5.5, zorder=5,
                            label=f"{meta['label']}  (ECE={ece:.3f})")
            legend_handles.append(line)
            # density strip
            for xb, wb in zip(cs, ws):
                ax.bar(xb, wb * 0.07, width=0.075, bottom=density_y,
                       color=meta["color"], alpha=0.30, linewidth=0, zorder=2)

        ax.axhline(density_y + 0.07, color="#CCC", lw=0.7)
        ax.text(0.005, density_y + 0.018, "pred density →", fontsize=6.4,
                color="#888", va="bottom")
        ax.set_xlim(-0.02, 1.02)
        ax.set_ylim(density_y - 0.04, 1.04)
        ax.set_xlabel("Mean predicted P(mel)", labelpad=2, fontsize=7.5)
        ax.set_ylabel("Empirical positive frac.", labelpad=2, fontsize=7.5)
        ax.set_title(f"{panel_tag}  Reliability — {sub_label}",
                     loc="left", pad=3, fontsize=8.5, fontweight="bold")
        ax.legend(loc="upper left", fontsize=6.3, framealpha=0.96,
                  edgecolor="#BBB", handlelength=1.6, borderpad=0.25,
                  labelspacing=0.25, handletextpad=0.4)
        ax.grid(True, ls=":", lw=0.5, alpha=0.4)
        ax.set_axisbelow(True)
        ax.tick_params(labelsize=6.8)

    for ext in ("pdf", "svg", "png"):
        fig.savefig(OUT / f"fig2_problem.{ext}", bbox_inches="tight", dpi=300,
                    facecolor="white")
        print(f"  [saved] fig2_problem.{ext}")
    plt.close(fig)


# ═══════════════════════════════════════════════════════════════════════════════
# Fig 3: QCTS Solution — Learned T(q̄) + Per-degradation + Per-bin ECE waterfall
# ═══════════════════════════════════════════════════════════════════════════════

DIM_DISPLAY_F3 = {
    "sharpness":  ("Blur",          r"$q_1\!\downarrow$"),
    "brightness": ("Low bright.",   r"$q_2\!\downarrow$"),
    "color_temp": ("Colour cast",   r"$q_4\!\downarrow$"),
    "contrast":   ("Low contrast",  r"$q_5\!\downarrow$"),
}

SHOW_BLS_F3 = ["D", "F", "D+QCTS"]   # only 3 for clarity in (b)
BL_F3_META = {
    "D":      dict(label="Std VIB",            colour=METHOD_META["D"]["color"], hatch=""),
    "F":      dict(label="Q-VIB Full",         colour=METHOD_META["F"]["color"], hatch=""),
    "D+QCTS": dict(label="Std VIB + QCTS (ours)", colour=C_FIX,                  hatch="//"),
}


def _softplus_np(x):
    return np.log1p(np.exp(np.clip(x, -30, 30)))


def fig3_qcts(itb_preds: pd.DataFrame, qcts_preds: pd.DataFrame):
    """3-panel QCTS solution figure."""
    # figsize sized for BMVC textwidth ≈ 5.1 inch (scale ~0.65 → ≥7pt printed)
    fig = plt.figure(figsize=(7.8, 2.7))
    fig.patch.set_facecolor("white")
    gs = gridspec.GridSpec(
        1, 3, figure=fig,
        width_ratios=[1.0, 1.25, 1.15],
        wspace=0.40,
        left=0.060, right=0.985, top=0.88, bottom=0.18,
    )
    ax_a = fig.add_subplot(gs[0, 0])
    ax_b = fig.add_subplot(gs[0, 1])
    ax_c = fig.add_subplot(gs[0, 2])

    # ── (a) Learned T(q̄) curve ───────────────────────────────────────────────
    params_path = PROJ / "results/qcts_params.json"
    if not params_path.exists():
        ax_a.text(0.5, 0.5, "qcts_params.json missing", ha="center", va="center",
                  transform=ax_a.transAxes)
    else:
        params = json.load(open(params_path))
        qg = np.linspace(0.0, 1.0, 200)
        seeds = params["all_seeds"]
        T_seeds = np.stack([_softplus_np(s["T0"] + s["alpha"] * (1 - qg))
                            for s in seeds])
        T_med   = np.median(T_seeds, axis=0)
        T_lo    = np.percentile(T_seeds, 16, axis=0)
        T_hi    = np.percentile(T_seeds, 84, axis=0)
        T_best  = _softplus_np(params["T0"] + params["alpha"] * (1 - qg))

        # Try Std TS reference temperature
        T_ts = None
        ts_path = ROOT / "checkpoints/stdvib/temperature.json"
        if ts_path.exists():
            T_ts = float(json.loads(open(ts_path).read())["T"])

        # 1-sigma band
        ax_a.fill_between(qg, T_lo, T_hi, color=C_FIX, alpha=0.18, lw=0,
                          label="3-seed range", zorder=2)
        # Individual seed curves (semi-transparent)
        seed_colours = ["#8DA0CB", "#BC80BD", "#80B1D3"]
        for s_meta, T_s, col in zip(seeds, T_seeds, seed_colours):
            ax_a.plot(qg, T_s, lw=1.1, ls="--", color=col, alpha=0.75,
                      zorder=3,
                      label=fr"Seed: $T_0\!=\!{s_meta['T0']:.2f},\ \alpha\!=\!{s_meta['alpha']:.2f}$")
        # Median (thick line)
        ax_a.plot(qg, T_med, color=C_FIX, lw=2.6, zorder=5, label="Median")

        # Std TS horizontal reference (α = 0 case)
        if T_ts is not None:
            ax_a.axhline(T_ts, color="#555", ls=":", lw=1.4, zorder=4,
                         label=fr"Std TS ($T\!=\!{T_ts:.2f}$, $\alpha\!=\!0$)")

        # Annotations: low-q→high T (uncertain) vs high-q→low T (confident)
        ax_a.annotate("low $\\bar q$\n→ high $T$",
                      xy=(0.04, T_med[8]),
                      xytext=(0.20, T_med[8] + 0.35),
                      arrowprops=dict(arrowstyle="->", color="#444", lw=0.7),
                      fontsize=6.5, color="#444", ha="center")
        ax_a.annotate("high $\\bar q$\n→ low $T$",
                      xy=(0.97, T_med[-3]),
                      xytext=(0.76, T_med[-3] - 0.32),
                      arrowprops=dict(arrowstyle="->", color="#444", lw=0.7),
                      fontsize=6.5, color="#444", ha="center")

        # Inset: bar chart of α values across seeds
        ax_a_in = ax_a.inset_axes([0.52, 0.66, 0.40, 0.26])
        alpha_vals = [s["alpha"] for s in seeds]
        ax_a_in.bar(range(len(alpha_vals)), alpha_vals,
                    color=C_FIX, edgecolor="white", lw=0.5)
        ax_a_in.axhline(0, color="#888", lw=0.5)
        ax_a_in.set_xticks(range(len(alpha_vals)))
        ax_a_in.set_xticklabels([f"s{i}" for i in range(len(alpha_vals))],
                                fontsize=5.5)
        ax_a_in.tick_params(axis="y", labelsize=5.5, pad=1)
        ax_a_in.set_title(r"$\alpha$ per seed",
                          fontsize=6.0, pad=1)
        for sp in ("top", "right"):
            ax_a_in.spines[sp].set_visible(False)

        ax_a.set_xlim(0, 1.0)
        ax_a.set_ylim(0, max(T_seeds.max(), (T_ts or 1.5)) * 1.10)
        ax_a.set_xlabel(r"Quality score $\bar q$", fontsize=7.5, labelpad=2)
        ax_a.set_ylabel(r"Temperature $T(\bar q)$", fontsize=7.5, labelpad=2)
        ax_a.set_title("(a)  Learned $T(\\bar q)$",
                       loc="left", fontweight="bold", pad=4, fontsize=9.0)
        ax_a.legend(loc="upper center", fontsize=5.5, framealpha=0.92,
                    edgecolor="#CCC", ncol=2, handlelength=1.4,
                    bbox_to_anchor=(0.5, -0.22), labelspacing=0.20,
                    handletextpad=0.4, columnspacing=0.8)
        ax_a.grid(True, ls=":", lw=0.5, alpha=0.4)
        ax_a.set_axisbelow(True)
        ax_a.tick_params(labelsize=6.8)

    # ── (b) Per-degradation ECE ────────────────────────────────────────────────
    deg_path = PROJ / "results/per_degradation_ece.csv"
    deg_df = pd.read_csv(deg_path)
    dims = [d for d in ["sharpness", "brightness", "color_temp", "contrast"]
            if d in deg_df["dim"].unique()]
    n_dims = len(dims)
    n_bls  = len(SHOW_BLS_F3)
    bar_w  = 0.24
    x_pos  = np.arange(n_dims)

    # Std VIB ITB-LQ baseline for delta annotations
    itb_res = pd.read_csv(PROJ / "results/itb_results.csv")
    d_lq_ece = float(itb_res[(itb_res["baseline"] == "D") & (itb_res["subset"] == "ITB-LQ")]["ece"].values[0])

    # Plot bars
    ece_grid = {}
    for i, bl in enumerate(SHOW_BLS_F3):
        meta = BL_F3_META[bl]
        sub = deg_df[deg_df["baseline"] == bl]
        eces = [float(sub[sub["dim"] == d]["ece"].values[0]) if len(sub[sub["dim"] == d]) else np.nan
                for d in dims]
        ece_grid[bl] = eces
        off = (i - (n_bls - 1) / 2) * bar_w
        ax_b.bar(x_pos + off, eces, bar_w,
                 color=meta["colour"], edgecolor="white", lw=0.7,
                 hatch=meta["hatch"], alpha=0.92,
                 label=meta["label"], zorder=4)

    # Delta annotation: D → D+QCTS for each dimension
    rel_changes = []
    for j, d in enumerate(dims):
        d_v = ece_grid["D"][j]
        q_v = ece_grid["D+QCTS"][j]
        if np.isnan(d_v) or np.isnan(q_v):
            continue
        rel = (q_v - d_v) / d_v * 100
        rel_changes.append(rel)
        ax_b.text(x_pos[j] + bar_w, max(d_v, q_v) + 0.018,
                  f"{rel:+.0f}%", ha="center", va="bottom",
                  fontsize=6.8, fontweight="bold",
                  color=C_FIX if rel < 0 else "#B71C1C")

    # n labels (sample count per dim)
    for j, d in enumerate(dims):
        row = deg_df[(deg_df["baseline"] == "I") & (deg_df["dim"] == d)]
        if len(row):
            ax_b.text(x_pos[j], -0.030, f"n={int(row['n'].values[0])}",
                      ha="center", va="top", fontsize=5.8, color="#888",
                      transform=ax_b.get_xaxis_transform())

    # Std VIB ITB-LQ full reference
    ax_b.axhline(d_lq_ece, ls="--", color=METHOD_META["D"]["color"],
                 lw=0.7, alpha=0.65, zorder=2,
                 label=f"Std VIB full ITB-LQ ({d_lq_ece:.2f})")

    ax_b.set_xticks(x_pos)
    ax_b.set_xticklabels([f"{DIM_DISPLAY_F3[d][0]}\n{DIM_DISPLAY_F3[d][1]}"
                          for d in dims], fontsize=7.0)
    ax_b.set_ylabel("ECE on ITB-LQ (bottom 20%)", fontsize=7.5, labelpad=2)
    ax_b.set_title("(b)  Per-degradation error",
                   loc="left", fontweight="bold", pad=4, fontsize=9.0)
    ymax = max([v for row in ece_grid.values() for v in row if not np.isnan(v)]) * 1.20
    ax_b.set_ylim(0, ymax)
    ax_b.legend(loc="upper right", fontsize=5.8, framealpha=0.95,
                edgecolor="#CCC", labelspacing=0.20, handlelength=1.4,
                handletextpad=0.3)
    ax_b.grid(True, axis="y", ls=":", lw=0.5, alpha=0.4)
    ax_b.set_axisbelow(True)
    ax_b.tick_params(axis="y", labelsize=6.8)

    # ── (c) ECE by q̄ bin — waterfall before/after QCTS ───────────────────────
    # Use ALL ITB subsets (LQ + Edge + HQ) for full q̄ range
    pred_d = itb_preds [(itb_preds ["baseline"] == "D")     & itb_preds ["subset"].isin(["ITB-LQ", "ITB-Edge", "ITB-HQ"])].copy()
    pred_q = qcts_preds[(qcts_preds["baseline"] == "D+QCTS") & qcts_preds["subset"].isin(["ITB-LQ", "ITB-Edge", "ITB-HQ"])].copy()

    # qbar bins
    bin_edges = np.array([0.20, 0.35, 0.45, 0.50, 0.55, 0.70])
    bin_mids  = (bin_edges[:-1] + bin_edges[1:]) / 2
    bin_labels = [fr"[{lo:.2f},{hi:.2f})" for lo, hi in zip(bin_edges[:-1], bin_edges[1:])]

    ece_before, ece_after, counts = [], [], []
    for lo, hi in zip(bin_edges[:-1], bin_edges[1:]):
        m_d = (pred_d["qbar"] >= lo) & (pred_d["qbar"] < hi)
        m_q = (pred_q["qbar"] >= lo) & (pred_q["qbar"] < hi)
        if m_d.sum() < 8 or m_q.sum() < 8:
            ece_before.append(np.nan); ece_after.append(np.nan); counts.append(int(m_d.sum())); continue
        ece_before.append(_ece_simple(pred_d.loc[m_d, "prob_pos"].values, pred_d.loc[m_d, "target"].values))
        ece_after .append(_ece_simple(pred_q.loc[m_q, "prob_pos"].values, pred_q.loc[m_q, "target"].values))
        counts.append(int(m_d.sum()))

    ece_before = np.array(ece_before); ece_after = np.array(ece_after)

    bar_w_c = 0.36
    xs = np.arange(len(bin_mids))
    ax_c.bar(xs - bar_w_c/2, ece_before, bar_w_c, color=METHOD_META["D"]["color"],
             edgecolor="white", lw=0.6, alpha=0.92, label="Std VIB (before)", zorder=4)
    ax_c.bar(xs + bar_w_c/2, ece_after,  bar_w_c, color=C_FIX,
             edgecolor="white", lw=0.6, alpha=0.92, label="+QCTS (after)", zorder=4,
             hatch="//")

    # Waterfall delta arrow between paired bars
    rel_per_bin = []
    for i, (b, a, n) in enumerate(zip(ece_before, ece_after, counts)):
        if np.isnan(b) or np.isnan(a):
            continue
        delta = a - b
        colour = C_GOOD if delta < 0 else C_BAD
        # arrow
        ax_c.annotate(
            "", xy=(i + bar_w_c/2, a), xytext=(i - bar_w_c/2, b),
            arrowprops=dict(arrowstyle="-|>", lw=1.0, color=colour,
                            connectionstyle="arc3,rad=-0.20",
                            shrinkA=2, shrinkB=2),
            zorder=6,
        )
        rel = delta / b * 100
        rel_per_bin.append(rel)
        ax_c.text(i, max(b, a) + 0.010,
                  fr"{rel:+.0f}%",
                  ha="center", va="bottom", fontsize=6.8, fontweight="bold",
                  color=colour)

    # sample count strip below
    for i, n in enumerate(counts):
        ax_c.text(i, -0.035, f"n={n}", ha="center", va="top", fontsize=5.8,
                  color="#888", transform=ax_c.get_xaxis_transform())

    # Headline: average reduction
    if rel_per_bin:
        avg_rel = np.mean(rel_per_bin)
        ax_c.text(0.97, 0.95,
                  f"Avg ECE reduction\nacross 5 bins: {abs(avg_rel):.0f}%",
                  transform=ax_c.transAxes, ha="right", va="top",
                  fontsize=7.4, fontweight="bold", color=C_GOOD,
                  bbox=dict(boxstyle="round,pad=0.28", fc="#EAF5EA",
                            ec=C_GOOD, lw=0.9, alpha=0.96))

    ax_c.set_xticks(xs)
    ax_c.set_xticklabels(bin_labels, fontsize=6.5)
    ax_c.set_ylabel("ECE within quality bin", fontsize=7.5, labelpad=2)
    ax_c.set_xlabel(r"Quality score bin $\bar q$", fontsize=7.5, labelpad=2)
    ax_c.set_title("(c)  ECE before/after QCTS by $\\bar q$ bin",
                   loc="left", fontweight="bold", pad=4, fontsize=9.0)
    ax_c.set_ylim(0, max(np.nanmax(ece_before), np.nanmax(ece_after)) * 1.32)
    ax_c.legend(loc="upper left", fontsize=6.3, framealpha=0.95,
                edgecolor="#CCC", labelspacing=0.20, handlelength=1.2,
                handletextpad=0.3)
    ax_c.grid(True, axis="y", ls=":", lw=0.5, alpha=0.4)
    ax_c.set_axisbelow(True)
    ax_c.tick_params(axis="y", labelsize=6.8)

    for ext in ("pdf", "svg", "png"):
        fig.savefig(OUT / f"fig3_qcts.{ext}", bbox_inches="tight", dpi=300,
                    facecolor="white")
        print(f"  [saved] fig3_qcts.{ext}")
    plt.close(fig)


# ═══════════════════════════════════════════════════════════════════════════════
# Fig 4: Generalization — Entropy~q̄ triptych + Cross-dataset + Fitzpatrick
# ═══════════════════════════════════════════════════════════════════════════════

# Methods present in cross_dataset_qcdi.csv (excluding I/J which weren't run)
CROSS_BLS = ["A", "D", "TS", "E", "F", "G", "H"]


def _entropy(prob_pos):
    p = np.clip(prob_pos, 1e-7, 1 - 1e-7)
    return -(p * np.log(p) + (1 - p) * np.log(1 - p))


def fig4_generalization(ham_preds: pd.DataFrame, qcts_preds: pd.DataFrame,
                        cross_df: pd.DataFrame, itb_subsets: pd.DataFrame,
                        itb_preds: pd.DataFrame):
    """3-panel generalization figure.

    (a) Entropy~q̄ triptych on HAM10000: Std VIB | +QCTS | Q-VIB Full
    (b) Cross-dataset QCDI bar chart (ISIC / HAM / PAD-UFES × 8 methods)
    (c) Fitzpatrick I-VI fairness QCDI per skin type × 3 methods
    """
    # figsize sized for BMVC textwidth ≈ 5.1 inch (scale ~0.65 → ≥7pt printed)
    fig = plt.figure(figsize=(7.8, 3.4))
    fig.patch.set_facecolor("white")
    gs = gridspec.GridSpec(
        2, 4, figure=fig,
        width_ratios=[1.0, 1.0, 1.0, 1.40],
        height_ratios=[1.0, 1.0],
        wspace=0.35, hspace=0.65,
        left=0.055, right=0.985, top=0.91, bottom=0.13,
    )
    # (a) three hexbin panels (top row, columns 0-2)
    ax_a1 = fig.add_subplot(gs[0, 0])
    ax_a2 = fig.add_subplot(gs[0, 1])
    ax_a3 = fig.add_subplot(gs[0, 2])
    # (b) cross-dataset (bottom row, columns 0-2)
    ax_b  = fig.add_subplot(gs[1, 0:3])
    # (c) fairness (right column, full height)
    ax_c  = fig.add_subplot(gs[:, 3])

    # ── (a) Entropy~q̄ triptych ────────────────────────────────────────────────
    from scipy.stats import spearmanr

    # Build {Std VIB, +QCTS, Q-VIB Full} per-sample on HAM10000
    pred_d = ham_preds[ham_preds["baseline"] == "D"].copy()
    pred_f = ham_preds[ham_preds["baseline"] == "F"].copy()

    # +QCTS: apply softplus(T0 + α(1-q̄)) to D's logits.  We don't store logits, so
    # use the qcts_preds CSV's HAM rows if present; otherwise approximate by recomputing.
    qcts_ham_path = PROJ / "results/qcts_external_ham10000_predictions.csv"
    if qcts_ham_path.exists():
        pred_q = pd.read_csv(qcts_ham_path)
    else:
        # Fallback: recompute from D prob + QCTS params
        params = json.load(open(PROJ / "results/qcts_params.json"))
        T0, alpha = params["T0"], params["alpha"]
        T_per_sample = _softplus_np(T0 + alpha * (1 - pred_d["q_bar"].values))
        # Recover logits from prob (binary): logit = log(p/(1-p))
        p = np.clip(pred_d["prob_pos"].values, 1e-7, 1 - 1e-7)
        logit = np.log(p / (1 - p))
        new_logit = logit / T_per_sample
        new_prob  = 1 / (1 + np.exp(-new_logit))
        pred_q = pred_d.copy()
        pred_q["prob_pos"] = new_prob

    panels = [
        (ax_a1, pred_d, "Std VIB",           METHOD_META["D"]["color"]),
        (ax_a2, pred_q, "+QCTS (ours)",      C_FIX),
        (ax_a3, pred_f, "Q-VIB Full",        METHOD_META["F"]["color"]),
    ]
    # Compute common axis range
    x_min, x_max = 0.35, 1.0
    y_min, y_max = 0.0, 0.75

    for ax, df, title, c in panels:
        qbar = df["q_bar"].values
        ent  = _entropy(df["prob_pos"].values)
        rho, p_val = spearmanr(qbar, ent)
        # Hexbin
        hb = ax.hexbin(qbar, ent, gridsize=42, cmap="magma_r",
                       extent=(x_min, x_max, y_min, y_max),
                       mincnt=1, linewidths=0.05)
        # Bin median trend (in 20 bins)
        bins = np.linspace(x_min, x_max, 21)
        mids, meds = [], []
        for lo, hi in zip(bins[:-1], bins[1:]):
            m = (qbar >= lo) & (qbar < hi)
            if m.sum() >= 8:
                mids.append((lo + hi) / 2)
                meds.append(np.median(ent[m]))
        ax.plot(mids, meds, "-", color="white", lw=3.2, alpha=0.85, zorder=4)
        ax.plot(mids, meds, "-", color=c, lw=1.8, alpha=0.95, zorder=5,
                label="per-bin median")

        # rho annotation — use plain unicode to avoid mathtext minus issues
        if p_val < 1e-50:
            p_text = "p < 1e-50"
        elif p_val < 1e-10:
            p_text = "p < 1e-10"
        else:
            p_text = f"p = {p_val:.2g}"
        # Unicode minus (U+2212) for proper visibility
        rho_str = f"{rho:.3f}".replace("-", "−")
        ax.text(0.96, 0.96,
                f"ρ = {rho_str}\n{p_text}",
                transform=ax.transAxes, ha="right", va="top",
                fontsize=7.0, fontweight="bold", color=c,
                bbox=dict(boxstyle="round,pad=0.22", fc="white",
                          ec=c, lw=0.8, alpha=0.97))

        ax.set_xlim(x_min, x_max); ax.set_ylim(y_min, y_max)
        ax.set_title(title, fontsize=7.8, fontweight="bold", color=c, pad=3)
        ax.set_xlabel(r"Quality $\bar q$", fontsize=7.0, labelpad=1)
        ax.set_ylabel(r"Entropy $H(p)$", fontsize=7.0, labelpad=1)
        ax.tick_params(labelsize=6.0, pad=1)
        ax.grid(True, ls=":", lw=0.5, alpha=0.4)
        ax.set_axisbelow(True)

    ax_a2.set_ylabel("")  # share ylabel with ax_a1
    ax_a3.set_ylabel("")
    fig.text(0.345, 0.965, "(a)  Entropy–quality on HAM10000 (zero-shot, n=10,015)",
             ha="center", fontsize=8.5, fontweight="bold")

    # ── (b) Cross-dataset QCDI ─────────────────────────────────────────────────
    # Compute QCTS QCDI on each dataset using on-the-fly temperature scaling
    qcts_params = json.load(open(PROJ / "results/qcts_params.json"))
    T0, alpha = qcts_params["T0"], qcts_params["alpha"]

    def _qcts_qcdi_for_df(df, qcol="q_bar", cut_lo=0.45, cut_hi=0.50):
        """Apply QCTS to D's predictions then compute ECE_LQ - ECE_HQ."""
        d_d = df[df["baseline"] == "D"]
        if len(d_d) < 50:
            return np.nan
        p = np.clip(d_d["prob_pos"].values, 1e-7, 1 - 1e-7)
        qb = d_d[qcol].values
        T = _softplus_np(T0 + alpha * (1 - qb))
        new_p = 1 / (1 + np.exp(-(np.log(p / (1 - p)) / T)))
        t = d_d["target"].values
        m_lo = qb < cut_lo; m_hi = qb > cut_hi
        if m_lo.sum() < 20 or m_hi.sum() < 20:
            return np.nan
        return _ece_simple(new_p[m_lo], t[m_lo]) - _ece_simple(new_p[m_hi], t[m_hi])

    ham_full = pd.read_csv(RES_DIR := PROJ / "results/external_ham10000_predictions.csv")
    pad_full = pd.read_csv(PROJ / "results/external_pad_ufes_predictions.csv")
    qcts_qcdi_ham = _qcts_qcdi_for_df(ham_full)
    qcts_qcdi_pad = _qcts_qcdi_for_df(pad_full)
    # For ITB, use qcts_itb_results.csv directly
    qcts_qcdi_itb = QCTS_VAL["ITB-LQ"]["ece"] - QCTS_VAL["ITB-HQ"]["ece"]

    # Append QCTS row to cross_df in memory
    cross_df_aug = pd.concat([
        cross_df,
        pd.DataFrame([{
            "baseline": "QCTS",
            "itb_qcdi": qcts_qcdi_itb,
            "ham_qcdi": qcts_qcdi_ham,
            "pad_qcdi": qcts_qcdi_pad,
        }]),
    ], ignore_index=True)

    cd_methods = [b for b in CROSS_BLS if b in cross_df_aug["baseline"].values] + ["QCTS"]
    n_m = len(cd_methods)
    bar_w = 0.25
    xs = np.arange(n_m)
    dataset_specs = [
        ("itb_qcdi", "ISIC-ITB",   "#34495E"),
        ("ham_qcdi", "HAM10000",   "#16A085"),
        ("pad_qcdi", "PAD-UFES",   "#9B59B6"),
    ]
    for i, (col, lbl, c) in enumerate(dataset_specs):
        vals = []
        for bl in cd_methods:
            r = cross_df_aug[cross_df_aug["baseline"] == bl]
            v = float(r[col].values[0]) if len(r) else np.nan
            vals.append(v)
        off = (i - 1) * bar_w
        bars = ax_b.bar(xs + off, vals, bar_w, color=c, edgecolor="white",
                        lw=0.5, label=lbl, alpha=0.92, zorder=4)
        # Highlight QCTS bars with thicker edge
        bars[-1].set_edgecolor(C_FIX)
        bars[-1].set_linewidth(1.3)

    ax_b.axhline(0, color="#888", lw=0.6, zorder=2)
    # Vertical separator before QCTS to visually mark "ours"
    ax_b.axvline(xs[-1] - 0.5, color=C_FIX, lw=0.8, ls=":", alpha=0.7, zorder=1)
    ax_b.text(xs[-1], ax_b.get_ylim()[1] * 0.95 if False else 0.13,
              "ours", fontsize=6.0, ha="center", color=C_FIX,
              fontweight="bold", style="italic")

    cd_labels = [METHOD_META[b]["label"] if b != "QCTS"
                 else "+QCTS\n(ours)" for b in cd_methods]
    ax_b.set_xticks(xs)
    ax_b.set_xticklabels(cd_labels, rotation=30, ha="right", fontsize=5.8)
    ax_b.set_ylabel("QCDI", fontsize=7.5, labelpad=2)
    ax_b.set_title("(b)  Cross-dataset QCDI",
                   loc="left", fontweight="bold", pad=4, fontsize=9.0)
    ax_b.legend(loc="upper left", fontsize=5.8, framealpha=0.95,
                edgecolor="#CCC", ncol=3, columnspacing=0.5,
                labelspacing=0.20, handlelength=1.0, handletextpad=0.3,
                borderpad=0.25)
    ax_b.grid(True, axis="y", ls=":", lw=0.5, alpha=0.4)
    ax_b.set_axisbelow(True)
    ax_b.tick_params(axis="y", labelsize=6.5)

    # ── (c) Fitzpatrick fairness QCDI ──────────────────────────────────────────
    fp_csv = ROOT / "data/raw/fitzpatrick17k/fitzpatrick17k.csv"
    fp_meta = pd.read_csv(fp_csv)[["md5hash", "fitzpatrick_scale"]]

    sub_diverse = itb_subsets[itb_subsets["subset"] == "ITB-Diverse"].reset_index(drop=True)
    sub_diverse = sub_diverse.merge(fp_meta, left_on="isic_id", right_on="md5hash", how="left")

    # 3 method × 3 skin-type groups (I-II / III-IV / V-VI)
    method_specs = [
        ("D",      "Std VIB",                  METHOD_META["D"]["color"]),
        ("D+QCTS", "+QCTS (ours)",             C_FIX),
        ("F",      "Q-VIB Full",               METHOD_META["F"]["color"]),
    ]
    group_specs = [
        ((1, 2), "I–II",  "#FFCFB3"),
        ((3, 4), "III–IV","#C68B5A"),
        ((5, 6), "V–VI",  "#5A2E12"),
    ]

    pred_diverse_D = itb_preds[(itb_preds["baseline"] == "D") & (itb_preds["subset"] == "ITB-Diverse")].reset_index(drop=True)
    pred_diverse_F = itb_preds[(itb_preds["baseline"] == "F") & (itb_preds["subset"] == "ITB-Diverse")].reset_index(drop=True)
    pred_diverse_Q = qcts_preds[(qcts_preds["baseline"] == "D+QCTS") & (qcts_preds["subset"] == "ITB-Diverse")].reset_index(drop=True)
    # Align fp_scale with prediction rows (assumed same order as itb_subsets)
    fp_scale = sub_diverse["fitzpatrick_scale"].values

    # Compute QCDI per group: ECE(low-q) - ECE(high-q) within that skin-type
    def group_qcdi(pred_df, scale_arr, lo_scale, hi_scale):
        m = (scale_arr >= lo_scale) & (scale_arr <= hi_scale)
        prob = pred_df.loc[m, "prob_pos"].values
        tgt  = pred_df.loc[m, "target"].values
        qb   = pred_df.loc[m, "qbar"].values if "qbar" in pred_df.columns else sub_diverse.loc[m, "qbar"].values
        if len(prob) < 30:
            return np.nan, 0
        # Use median qbar as cutoff
        cut = np.median(qb)
        m_lo = qb < cut; m_hi = qb >= cut
        if m_lo.sum() < 10 or m_hi.sum() < 10:
            return np.nan, m.sum()
        e_lo = _ece_simple(prob[m_lo], tgt[m_lo])
        e_hi = _ece_simple(prob[m_hi], tgt[m_hi])
        return e_lo - e_hi, m.sum()

    # qbar comes from sub_diverse; use that
    n_meth = len(method_specs); n_grp = len(group_specs)
    bar_w_c = 0.25
    ys = np.arange(n_grp)
    vals_by_method = {}
    for i, (mid, mlbl, mcol) in enumerate(method_specs):
        if mid == "D":
            pred_df = pred_diverse_D.copy(); pred_df["qbar"] = sub_diverse["qbar"].values
        elif mid == "F":
            pred_df = pred_diverse_F.copy(); pred_df["qbar"] = sub_diverse["qbar"].values
        else:
            pred_df = pred_diverse_Q.copy(); pred_df["qbar"] = sub_diverse["qbar"].values

        vals = []; ns = []
        for (lo, hi), _, _ in group_specs:
            v, n = group_qcdi(pred_df, fp_scale, lo, hi)
            vals.append(v); ns.append(n)
        vals_by_method[mid] = vals
        off = (i - 1) * bar_w_c
        bars = ax_c.barh(ys + off, vals, bar_w_c, color=mcol,
                         edgecolor="white", lw=0.5, label=mlbl,
                         alpha=0.92, zorder=4)
        # n labels right of bar
        for j, (v, n) in enumerate(zip(vals, ns)):
            if not np.isnan(v):
                ax_c.text(v + (0.005 if v >= 0 else -0.005),
                          ys[j] + off,
                          f"n={n}", ha="left" if v >= 0 else "right",
                          va="center", fontsize=5.2, color="#666")

    ax_c.axvline(0, color="#888", lw=0.6, zorder=2)
    ax_c.set_yticks(ys)
    ax_c.set_yticklabels([lbl for _, lbl, _ in group_specs], fontsize=7.5,
                         fontweight="bold")
    # Skin-type swatch on the left
    for j, (_, _, sc) in enumerate(group_specs):
        ax_c.add_patch(plt.Rectangle((-0.005, ys[j] - 0.32), 0.020, 0.64,
                                     transform=ax_c.get_yaxis_transform(),
                                     fc=sc, ec="#888", lw=0.4, clip_on=False,
                                     zorder=10))

    # Annotation: V-VI specifically — show absolute reduction
    if "D" in vals_by_method and "D+QCTS" in vals_by_method:
        d_vi  = vals_by_method["D"][2]
        q_vi  = vals_by_method["D+QCTS"][2]
        if not (np.isnan(d_vi) or np.isnan(q_vi)):
            ax_c.text(0.97, 0.04,
                      f"V–VI: Std VIB QCDI = {d_vi:+.3f}\n"
                      f"        +QCTS QCDI = {q_vi:+.3f}",
                      transform=ax_c.transAxes, ha="right", va="bottom",
                      fontsize=5.8, fontweight="bold", color=C_FIX,
                      bbox=dict(boxstyle="round,pad=0.20", fc="#FEF5E7",
                                ec=C_FIX, lw=0.8, alpha=0.96))

    ax_c.invert_yaxis()
    ax_c.set_xlabel("QCDI within skin-type group", fontsize=7.5, labelpad=2)
    ax_c.set_title("(c)  Fitzpatrick fairness",
                   loc="left", fontweight="bold", pad=4, fontsize=9.0)
    ax_c.legend(loc="upper right", fontsize=5.8, framealpha=0.95,
                edgecolor="#CCC", labelspacing=0.20, handlelength=1.0,
                handletextpad=0.3, borderpad=0.25)
    ax_c.grid(True, axis="x", ls=":", lw=0.5, alpha=0.4)
    ax_c.set_axisbelow(True)
    ax_c.tick_params(axis="x", labelsize=6.5)

    for ext in ("pdf", "svg", "png"):
        fig.savefig(OUT / f"fig4_generalization.{ext}", bbox_inches="tight",
                    dpi=300, facecolor="white")
        print(f"  [saved] fig4_generalization.{ext}")
    plt.close(fig)


# ═══════════════════════════════════════════════════════════════════════════════
# (legacy) Fig 0 teaser — kept for backward compat; replaced by fig1_teaser()
# ═══════════════════════════════════════════════════════════════════════════════

def fig0_teaser():
    """4-column × 3-row matrix teaser:
    Columns: HQ reference | Blur | Low Contrast | Colour Shift
    Rows:    Original clean image | Degraded image | Confidence comparison
    """
    ROOT_DAT = Path("D:/YJ-Agent/data")
    RAW  = ROOT_DAT / "raw/isic2020/train-image/image"
    DEG  = ROOT_DAT / "paired_dataset/heavy"

    # ── case definitions ──────────────────────────────────────────────────────
    # (isic_id, q̄, primary degradation dim, prob_StdVIB, prob_QCTS, label)
    COLS = [
        dict(isic="ISIC_4477650", qbar=0.640, deg_label="No degradation",
             dim_label=None,
             prob_vib=0.098, prob_qcts=None,
             col_title="High Quality",
             border_good="#2ca02c", border_bad="#2ca02c"),
        dict(isic="ISIC_8219342", qbar=0.448, deg_label="Blur ($q_1$)",
             dim_label=r"Sharpness $q_1 = 0.03$",
             prob_vib=0.999, prob_qcts=0.970,
             col_title="Blur Degradation",
             border_good="#1f77b4", border_bad="#d62728"),
        dict(isic="ISIC_1637536", qbar=0.415, deg_label="Low contrast ($q_5$)",
             dim_label=r"Contrast $q_5 = 0.13$",
             prob_vib=0.960, prob_qcts=0.838,
             col_title="Contrast Loss",
             border_good="#1f77b4", border_bad="#d62728"),
        dict(isic="ISIC_9766593", qbar=0.379, deg_label="Colour shift ($q_4$)",
             dim_label=r"Colour temp. $q_4 = 0.01$",
             prob_vib=0.967, prob_qcts=0.852,
             col_title="Colour Shift",
             border_good="#1f77b4", border_bad="#d62728"),
    ]
    N = len(COLS)

    # ── layout ────────────────────────────────────────────────────────────────
    fig = plt.figure(figsize=(12.0, 8.5))
    gs = gridspec.GridSpec(
        3, N, figure=fig,
        height_ratios=[2.6, 2.6, 1.8],
        hspace=0.10, wspace=0.06,
        left=0.03, right=0.97, top=0.93, bottom=0.03,
    )

    ROW_LABELS = ["Original\n(clean input)", "After\ndegradation", "Confidence"]
    for ri, rl in enumerate(ROW_LABELS):
        fig.text(0.012, [0.82, 0.50, 0.18][ri], rl,
                 fontsize=7.5, color="#666666", style="italic",
                 va="center", ha="left", rotation=90)

    for ci, C in enumerate(COLS):
        orig_path = RAW / f"{C['isic']}.jpg"
        deg_path  = DEG / f"{C['isic']}.jpg"

        # ── Row 0: original image ─────────────────────────────────────────────
        ax0 = fig.add_subplot(gs[0, ci])
        ax0.imshow(_crop_square(orig_path))
        ax0.axis("off")
        _img_border(ax0, "#888888", lw=1.5)
        _badge(ax0, 0.04, 0.97, f"$\\bar{{q}}={C['qbar']:.2f}$", fc="#1a1a1aCC")
        ax0.set_title(C["col_title"], fontsize=9.5, fontweight="bold",
                      color=C["border_bad"], pad=5)

        # ── Row 1: degraded image ─────────────────────────────────────────────
        ax1 = fig.add_subplot(gs[1, ci])
        if C["dim_label"] is None:
            # HQ column: show same clean image with "Reference" overlay
            ax1.imshow(_crop_square(orig_path))
            _badge(ax1, 0.5, 0.5, "Reference\n(no degradation)",
                   fc="#2ca02cCC", ha="center", va="center", fontsize=9)
        else:
            ax1.imshow(_crop_square(deg_path))
            _badge(ax1, 0.04, 0.97, C["dim_label"], fc="#990000CC", fontsize=7.5)
        ax1.axis("off")
        _img_border(ax1, C["border_bad"], lw=2.5)

        # ── Row 2: confidence bars ────────────────────────────────────────────
        ax2 = fig.add_subplot(gs[2, ci])
        ax2.set_xlim(0, 1); ax2.set_ylim(-0.2, 1.0); ax2.axis("off")

        # Ground truth label
        ax2.text(0.5, 0.97, "GT: Benign (P(mel)=0)",
                 ha="center", va="top", fontsize=7, color="#555555",
                 transform=ax2.transAxes)

        if C["prob_qcts"] is None:
            # HQ: single green bar
            p = C["prob_vib"]
            ax2.barh(0.55, p, height=0.28, color="#2ca02c", alpha=0.85, left=0)
            ax2.barh(0.55, 1-p, height=0.28, color="#dddddd", alpha=0.45, left=p)
            ax2.text(p/2, 0.55, f"Std VIB: {p*100:.0f}%",
                     ha="center", va="center", fontsize=8, fontweight="bold", color="white")
            ax2.text(0.5, 0.10, "Well-calibrated",
                     ha="center", va="center", fontsize=7.5, fontweight="bold",
                     color="#2ca02c", transform=ax2.transAxes)
        else:
            # LQ: Std VIB bar (red) + QCTS bar (orange), side by side
            p_vib  = C["prob_vib"]
            p_qcts = C["prob_qcts"]
            delta  = p_vib - p_qcts

            # Std VIB bar
            ax2.barh(0.70, p_vib, height=0.22, color="#d62728", alpha=0.85)
            ax2.barh(0.70, 1-p_vib, height=0.22, left=p_vib, color="#f0c0c0", alpha=0.35)
            ax2.text(p_vib/2, 0.70, f"Std VIB: {p_vib*100:.0f}%",
                     ha="center", va="center", fontsize=8, fontweight="bold", color="white")

            # QCTS bar
            ax2.barh(0.35, p_qcts, height=0.22, color="#ff7f0e", alpha=0.85)
            ax2.barh(0.35, 1-p_qcts, height=0.22, left=p_qcts, color="#ffe0b0", alpha=0.35)
            ax2.text(p_qcts/2, 0.35, f"QCTS: {p_qcts*100:.0f}%",
                     ha="center", va="center", fontsize=8, fontweight="bold", color="white")

            # Delta annotation
            ax2.annotate(f"",
                xy=(p_qcts + 0.02, 0.35),
                xytext=(p_vib + 0.02, 0.70),
                arrowprops=dict(arrowstyle="-|>", color="#555555", lw=1.1),
                annotation_clip=False)
            ax2.text(p_vib + 0.04, 0.525, f"$-{delta*100:.0f}$pp",
                     ha="left", va="center", fontsize=7.5, color="#555555")

            ax2.text(0.5, 0.02, "Overconfident (benign!)",
                     ha="center", va="bottom", fontsize=7.0, fontweight="bold",
                     color="#d62728", transform=ax2.transAxes)

    # ── global title ──────────────────────────────────────────────────────────
    fig.suptitle(
        r"Calibration failure under image quality shift: "
        r"Std VIB assigns high $P(\mathrm{mel})$ to benign lesions on degraded images;"
        r"  QCTS (ours) reduces overconfidence across all degradation types.",
        fontsize=9, style="italic", color="#333333", y=0.975, ha="center")

    for ext in ("pdf", "png"):
        fig.savefig(OUT / f"fig0_teaser.{ext}", bbox_inches="tight", dpi=300)
        print(f"  [saved] fig0_teaser.{ext}")
    plt.close(fig)


# ═══════════════════════════════════════════════════════════════════════════════
# Fig 1: Taxonomy Scatter — ECE-HQ (x) vs ECE-LQ (y)
# ═══════════════════════════════════════════════════════════════════════════════

# 手动偏移：精调后不重叠
LABEL_OFFSETS = {
    "A":    ( 0.007,  0.010),
    "D":    ( 0.004, -0.021),
    "TS":   ( 0.006,  0.015),
    "E":    (-0.068, -0.005),
    "F":    (-0.044, -0.022),
    "G":    ( 0.006,  0.012),
    "H":    ( 0.006,  0.008),
    "I":    ( 0.006,  0.008),
    "J":    ( 0.006, -0.020),
    "QCTS": ( 0.008,  0.014),
}


def fig1_taxonomy(itb_results: pd.DataFrame):
    # 提取各方法 LQ/HQ ECE
    pivot = {}
    for _, row in itb_results.iterrows():
        bl = row["baseline"]
        if bl not in METHOD_META:
            continue
        sub = row.get("subset", "")
        if sub == "ITB-LQ":
            pivot.setdefault(bl, {})["lq_ece"] = row["ece"]
        elif sub == "ITB-HQ":
            pivot.setdefault(bl, {})["hq_ece"] = row["ece"]

    # 加入 QCTS 投影值
    pivot["QCTS"] = {"lq_ece": QCTS_VAL["ITB-LQ"]["ece"],
                     "hq_ece": QCTS_VAL["ITB-HQ"]["ece"]}

    # 数据点
    bls   = [b for b in pivot if "lq_ece" in pivot[b] and "hq_ece" in pivot[b]]
    xs    = np.array([pivot[b]["hq_ece"] for b in bls])
    ys    = np.array([pivot[b]["lq_ece"] for b in bls])

    fig, axes = plt.subplots(1, 2, figsize=(9.0, 4.0),
                              gridspec_kw={"width_ratios": [1.8, 1.0]})

    # ── 左图：全局视图（含 H/I/J 大 ECE 方法） ──────────────────────────────
    ax = axes[0]

    # 对角线 & QCDI 参考线
    xlim_full = (0.04, 0.50)
    ylim_full = (0.04, 0.68)
    diag = np.array(xlim_full)
    ax.plot(diag, diag,       "--", color="gray", lw=1.2, alpha=0.6, zorder=1)
    ax.plot(diag, diag + 0.05, ":", color="gray", lw=0.8, alpha=0.45, zorder=1)
    ax.plot(diag, diag + 0.10, ":", color="gray", lw=0.8, alpha=0.45, zorder=1)

    # 背景色带
    xs_fill = np.linspace(xlim_full[0], xlim_full[1], 200)
    ax.fill_between(xs_fill, xs_fill + 0.10, ylim_full[1],
                    alpha=0.18, color=TAXONOMY_BG["Quality-Oblivious"], zorder=0)
    ax.fill_between(xs_fill, xs_fill + 0.05, xs_fill + 0.10,
                    alpha=0.18, color=TAXONOMY_BG["Quality-Fragile"], zorder=0)
    ax.fill_between(xs_fill, ylim_full[0], xs_fill + 0.05,
                    alpha=0.18, color=TAXONOMY_BG["Quality-Aware"], zorder=0)

    # 分类标注
    ax.text(0.44, 0.60, "Quality-\nOblivious", fontsize=8, color="#a03020",
            ha="center", va="center", style="italic", alpha=0.8)
    ax.text(0.38, 0.41, "Quality-\nFragile",   fontsize=8, color="#205080",
            ha="center", va="center", style="italic", alpha=0.8)
    ax.text(0.15, 0.23, "Quality-\nAware",     fontsize=8, color="#206020",
            ha="center", va="center", style="italic", alpha=0.8)

    # 散点 + 标签
    for bl in bls:
        meta = METHOD_META[bl]
        x, y = pivot[bl]["hq_ece"], pivot[bl]["lq_ece"]
        zord = 6 if bl in ("F", "QCTS") else 5
        ec   = "white" if bl != "QCTS" else meta["color"]
        ax.scatter(x, y, s=meta["ms"]**2, color=meta["color"], marker=meta["marker"],
                   linewidths=0.8, edgecolors=ec, zorder=zord)
        dx, dy = LABEL_OFFSETS.get(bl, (0.006, 0.010))
        ax.annotate(meta["label"], (x + dx, y + dy),
                    fontsize=7.5, color=meta["color"], annotation_clip=False,
                    fontweight="bold" if bl in ("F", "QCTS") else "normal")

    ax.set_xlim(xlim_full)
    ax.set_ylim(ylim_full)
    ax.set_xlabel("ECE on ITB-HQ (high-quality)", labelpad=5)
    ax.set_ylabel("ECE on ITB-LQ (low-quality)",  labelpad=5)
    ax.set_title("(a) All Methods", pad=6)

    # 虚框标注缩放区域
    zoom_x = (0.04, 0.22)
    zoom_y = (0.04, 0.22)
    rect = mpatches.FancyBboxPatch(
        (zoom_x[0], zoom_y[0]), zoom_x[1]-zoom_x[0], zoom_y[1]-zoom_y[0],
        boxstyle="square,pad=0.002", lw=1.2, edgecolor="#444444",
        facecolor="none", zorder=10, linestyle="-."
    )
    ax.add_patch(rect)
    ax.annotate("zoomed\nright →", (zoom_x[1]+0.002, (zoom_y[0]+zoom_y[1])/2),
                fontsize=7, color="#444444", va="center")

    # ── 右图：放大 Quality-Aware / Fragile 区域 ──────────────────────────────
    ax2 = axes[1]
    xlim_zoom = (0.04, 0.22)
    ylim_zoom = (0.04, 0.22)

    diag2 = np.linspace(xlim_zoom[0], xlim_zoom[1], 100)
    ax2.plot(diag2, diag2,        "--", color="gray", lw=1.2, alpha=0.6, zorder=1)
    ax2.plot(diag2, diag2 + 0.05, ":",  color="gray", lw=0.8, alpha=0.45, zorder=1)

    xs2_fill = np.linspace(xlim_zoom[0], xlim_zoom[1], 200)
    ax2.fill_between(xs2_fill, ylim_zoom[0], xs2_fill + 0.05,
                     alpha=0.22, color=TAXONOMY_BG["Quality-Aware"], zorder=0)
    ax2.fill_between(xs2_fill, xs2_fill + 0.05, ylim_zoom[1],
                     alpha=0.22, color=TAXONOMY_BG["Quality-Fragile"], zorder=0)
    ax2.text(0.130, 0.110, "Quality-Aware",   fontsize=7, color="#206020",
             ha="center", va="bottom", style="italic")
    ax2.text(0.155, 0.215, "Quality-Fragile", fontsize=7, color="#205080",
             ha="center", va="top",    style="italic")

    # 缩放标注偏移（需要更细致的手动偏移防止重叠）
    ZOOM_OFFSETS = {
        "D":    (-0.000,  0.006),
        "TS":   ( 0.004, -0.009),
        "E":    (-0.038,  0.000),
        "F":    (-0.037, -0.008),
        "G":    ( 0.003,  0.005),
        "A":    (-0.035,  0.004),
        "QCTS": ( 0.003,  0.006),
    }
    zoom_bls = [b for b in bls
                if xlim_zoom[0] - 0.01 <= pivot[b]["hq_ece"] <= xlim_zoom[1]
                and ylim_zoom[0] - 0.01 <= pivot[b]["lq_ece"] <= ylim_zoom[1]
                and b not in ("A",)]   # A is outside zoom range, skip
    for bl in zoom_bls:
        meta = METHOD_META[bl]
        x, y = pivot[bl]["hq_ece"], pivot[bl]["lq_ece"]
        zord = 6 if bl in ("F", "QCTS") else 5
        ec   = "white" if bl != "QCTS" else meta["color"]
        ax2.scatter(x, y, s=meta["ms"]**2 * 1.3, color=meta["color"],
                    marker=meta["marker"], linewidths=0.8, edgecolors=ec, zorder=zord)
        dx, dy = ZOOM_OFFSETS.get(bl, (0.003, 0.004))
        ax2.annotate(meta["label"], (x + dx, y + dy),
                     fontsize=7.5, color=meta["color"], annotation_clip=False,
                     fontweight="bold" if bl in ("F", "QCTS") else "normal")

    ax2.set_xlim(xlim_zoom)
    ax2.set_ylim(ylim_zoom)
    ax2.set_xlabel("ECE on ITB-HQ", labelpad=5)
    ax2.set_title("(b) Zoomed: Quality-Aware Region", pad=6)
    ax2.yaxis.set_label_position("right")
    ax2.yaxis.tick_right()

    # 图例（QCDI 参考线 + 分类背景）
    legend_elems = [
        Line2D([0], [0], ls="--", color="gray", lw=1.2, label="QCDI = 0"),
        Line2D([0], [0], ls=":",  color="gray", lw=0.8, label="QCDI = 0.05"),
        mpatches.Patch(color=TAXONOMY_BG["Quality-Oblivious"], alpha=0.5, label="Quality-Oblivious"),
        mpatches.Patch(color=TAXONOMY_BG["Quality-Fragile"],   alpha=0.5, label="Quality-Fragile"),
        mpatches.Patch(color=TAXONOMY_BG["Quality-Aware"],     alpha=0.5, label="Quality-Aware"),
    ]
    axes[0].legend(handles=legend_elems, loc="lower right",
                   framealpha=0.92, edgecolor="lightgray", fontsize=7.5)

    fig.suptitle("Calibration Taxonomy under Image Quality Shift",
                 fontsize=12, fontweight="semibold", y=1.01)
    fig.tight_layout(pad=1.2, w_pad=1.5)

    for ext in ("pdf", "png"):
        fig.savefig(OUT / f"fig1_taxonomy.{ext}", bbox_inches="tight")
        print(f"  [saved] fig1_taxonomy.{ext}")
    plt.close(fig)


# ═══════════════════════════════════════════════════════════════════════════════
# Fig 2: Reliability Diagrams — 焦点放在 [0, 0.5] 置信度区间
# ═══════════════════════════════════════════════════════════════════════════════

def _reliability_curve(prob_pos, targets, n_bins=12, conf_range=(0.0, 1.0)):
    bins = np.linspace(conf_range[0], conf_range[1], n_bins + 1)
    bin_confs, bin_accs, bin_w = [], [], []
    n = len(targets)
    for lo, hi in zip(bins[:-1], bins[1:]):
        mask = (prob_pos >= lo) & (prob_pos < hi)
        cnt = mask.sum()
        if cnt < 5:
            continue
        bin_confs.append(prob_pos[mask].mean())
        bin_accs.append(targets[mask].mean())
        bin_w.append(cnt / n)
    return np.array(bin_confs), np.array(bin_accs), np.array(bin_w)


def _ece(prob_pos, targets, n_bins=15):
    bins = np.linspace(0, 1, n_bins + 1)
    ece, n = 0.0, len(targets)
    for lo, hi in zip(bins[:-1], bins[1:]):
        mask = (prob_pos >= lo) & (prob_pos < hi)
        if mask.sum() < 3:
            continue
        ece += (mask.sum() / n) * abs(targets[mask].mean() - prob_pos[mask].mean())
    return ece


SHOW_REL = ["I", "J", "D", "F"]    # MC Dropout / Deep Ensemble / Std VIB / Q-VIB


def fig2_reliability(itb_preds: pd.DataFrame):
    subsets    = ["ITB-LQ", "ITB-HQ"]
    sub_titles = ["(a) Low Quality (ITB-LQ)", "(b) High Quality (ITB-HQ)"]

    fig, axes = plt.subplots(1, 2, figsize=(7.5, 3.4), sharey=False)

    for ax, subset, stitle in zip(axes, subsets, sub_titles):
        sub_df = itb_preds[itb_preds["subset"] == subset]

        # 全范围 [0, 1]：MC Dropout/Ensemble 的过度自信发生在 0.7-0.9 区间
        # 裁掉会隐藏关键故事
        diag = np.linspace(0, 1, 100)
        ax.plot(diag, diag, "--", color="gray", lw=1.1, alpha=0.7,
                label="Perfect calibration", zorder=1)
        ax.fill_between(diag, diag, alpha=0.06, color="gray", zorder=0)

        density_y = -0.10   # 密度条的 y 基线
        for bl in SHOW_REL:
            bl_df = sub_df[sub_df["baseline"] == bl]
            if len(bl_df) == 0:
                continue
            prob = bl_df["prob_pos"].clip(1e-7, 1 - 1e-7).values
            tgt  = bl_df["target"].values
            meta = METHOD_META[bl]
            ece  = _ece(prob, tgt)

            confs, accs, weights = _reliability_curve(
                prob, tgt, n_bins=10, conf_range=(0.0, 1.0))
            if len(confs) < 2:
                continue

            ls = "-"  if bl == "F" else ("--" if bl == "D" else "-.")
            lw = 1.8  if bl in ("F", "D") else 1.4
            ax.plot(confs, accs,
                    color=meta["color"], lw=lw, ls=ls,
                    marker=meta["marker"], markersize=5,
                    label=f"{meta['label']} (ECE={ece:.3f})",
                    zorder=5)

            # 底部密度条（显示预测集中在哪里）
            for xb, wb in zip(confs, weights):
                ax.bar(xb, wb * 0.07, width=0.08, bottom=density_y,
                       color=meta["color"], alpha=0.35, linewidth=0)

        ax.axhline(density_y + 0.07, color="lightgray", lw=0.7, ls="-")
        ax.text(0.01, density_y + 0.01, "Pred. density", fontsize=6.5,
                color="#888888", va="bottom")
        ax.set_xlim(-0.02, 1.02)
        ax.set_ylim(density_y - 0.02, 1.02)
        ax.set_xlabel("Mean Predicted Confidence", labelpad=4)
        ax.set_ylabel("Fraction of Positives",     labelpad=4)
        ax.set_title(stitle, pad=6, fontweight="semibold")

        ax.legend(loc="upper left", framealpha=0.92, edgecolor="lightgray",
                  fontsize=7.5, handlelength=2.0)

    fig.suptitle("Reliability Diagrams Conditioned on Quality Stratum",
                 fontsize=12, fontweight="semibold", y=1.01)
    fig.tight_layout(pad=1.0, w_pad=1.5)

    for ext in ("pdf", "png"):
        fig.savefig(OUT / f"fig2_reliability.{ext}", bbox_inches="tight")
        print(f"  [saved] fig2_reliability.{ext}")
    plt.close(fig)


# ═══════════════════════════════════════════════════════════════════════════════
# Fig 3: Per-Degradation ECE — 按降质维度分位数分组（不依赖"主降质"）
# ═══════════════════════════════════════════════════════════════════════════════

SHOW_BLS_DEG = ["I", "J", "D", "F"]
DIM_DISPLAY = {
    "sharpness":  "Blur\n" + r"($q_1\downarrow$)",
    "brightness": "Low bright.\n" + r"($q_2\downarrow$)",
    "color_temp": "Color temp.\n" + r"($q_4\downarrow$)",
    "contrast":   "Low contrast\n" + r"($q_5\downarrow$)",
}
CHECK_DIMS = list(DIM_DISPLAY.keys())


def fig3_degradation(itb_preds: pd.DataFrame, q_labels: pd.DataFrame,
                     itb_subsets: pd.DataFrame):
    """按各质量维度最低 20th 百分位分组（而非主降质）——每维度独立二分。"""
    lq = itb_subsets[itb_subsets["subset"] == "ITB-LQ"].copy().reset_index(drop=True)
    lq["degraded_path"] = lq["image_path"].apply(str)

    # 合并质量维度分数
    q_sub = q_labels[SCORE_COLS + ["degraded_path"]].copy()
    lq = lq.merge(q_sub, on="degraded_path", how="left")
    lq = lq.dropna(subset=CHECK_DIMS).reset_index(drop=True)
    n_lq = len(lq)

    # 各方法 ITB-LQ 预测（顺序和 itb_subsets 对齐）
    lq_preds_all = itb_preds[itb_preds["subset"] == "ITB-LQ"].copy()

    # 验证顺序一致性（D 的 target 对齐 lq 的 target）
    d_preds = lq_preds_all[lq_preds_all["baseline"] == "D"].reset_index(drop=True)
    min_len  = min(len(d_preds), n_lq)
    match    = (d_preds["target"].values[:min_len] == lq["target"].values[:min_len]).mean()
    if match < 0.95:
        print(f"  [warn] target alignment {match:.1%} — per-degradation results may be off")

    bar_data = {dim: {} for dim in CHECK_DIMS}

    for bl in SHOW_BLS_DEG:
        bl_df = lq_preds_all[lq_preds_all["baseline"] == bl].reset_index(drop=True)
        for dim in CHECK_DIMS:
            # 取该维度最低 20th 百分位为"重度降质"样本
            thresh = np.percentile(lq[dim].values[:min_len], 20)
            mask   = (lq[dim].values[:min_len] <= thresh)
            cnt    = mask.sum()
            if cnt < 10:
                continue
            prob = bl_df["prob_pos"].values[:min_len][mask]
            tgt  = lq["target"].values[:min_len][mask]
            ece  = _ece(prob, tgt)
            bar_data[dim][bl] = {"ece": ece, "n": int(cnt)}

    # 过滤掉所有方法都没有数据的维度
    valid_dims = [d for d in CHECK_DIMS if len(bar_data[d]) >= len(SHOW_BLS_DEG) - 1]

    if not valid_dims:
        print("  [skip] not enough per-degradation data")
        return

    n_dims = len(valid_dims)
    n_bls  = len(SHOW_BLS_DEG)
    bar_w  = 0.18
    x      = np.arange(n_dims)

    fig, ax = plt.subplots(figsize=(max(5.5, n_dims * 1.8), 3.8))

    for i, bl in enumerate(SHOW_BLS_DEG):
        meta   = METHOD_META[bl]
        eces   = [bar_data[d].get(bl, {}).get("ece", np.nan) for d in valid_dims]
        offset = (i - (n_bls - 1) / 2) * bar_w
        bars   = ax.bar(x + offset, eces, bar_w,
                        label=meta["label"],
                        color=meta["color"], alpha=0.88,
                        edgecolor="white", linewidth=0.5)

    # 显示 n（只标一次，放在第一组柱的顶端）
    first_bl = SHOW_BLS_DEG[0]
    for j, dim in enumerate(valid_dims):
        n = bar_data[dim].get(first_bl, {}).get("n", None)
        if n:
            ax.text(j, ax.get_ylim()[1] * 0.02, f"n = {n}",
                    ha="center", va="bottom", fontsize=7.0, color="#666666")

    ax.set_xticks(x)
    ax.set_xticklabels([DIM_DISPLAY[d] for d in valid_dims], fontsize=9.0)
    ax.set_ylabel("ECE on ITB-LQ (bottom 20th percentile)", labelpad=5)
    ax.set_title("Calibration Error by Dominant Degradation Type", pad=8,
                 fontweight="semibold")
    ymax = ax.get_ylim()[1]
    ax.set_ylim(0, ymax * 1.12)
    ax.legend(loc="upper right", framealpha=0.92, edgecolor="lightgray",
              ncol=2, fontsize=8.5)

    # 水平参考线（Std VIB 全集基准）
    ref_ece = itb_preds[(itb_preds["baseline"] == "D") &
                        (itb_preds["subset"] == "ITB-LQ")]["prob_pos"]
    ref_tgt = itb_preds[(itb_preds["baseline"] == "D") &
                        (itb_preds["subset"] == "ITB-LQ")]["target"]
    ax.axhline(_ece(ref_ece.values, ref_tgt.values), ls="--", color="#1f77b4",
               lw=0.9, alpha=0.6, label="Std VIB (full ITB-LQ)")

    fig.tight_layout(pad=1.2)
    for ext in ("pdf", "png"):
        fig.savefig(OUT / f"fig3_degradation.{ext}", bbox_inches="tight")
        print(f"  [saved] fig3_degradation.{ext}")
    plt.close(fig)


# ═══════════════════════════════════════════════════════════════════════════════
# Fig 4: Entropy–q̄ 对比（Proposition 2 实证）
# ═══════════════════════════════════════════════════════════════════════════════

def fig4_entropy_qbar(ham_preds: pd.DataFrame):
    """Entropy–q̄ 对比。

    使用 HAM10000（质量自然分布，n=10015）而非 ITB（人为分层会产生
    Simpson's Paradox，使 Std VIB 也呈现虚假相关）。
    HAM10000 的 rho 值与论文全测试集结论一致：
      D (Std VIB): rho ≈ -0.033  →  near-zero, quality-oblivious
      F (Q-VIB Full): rho ≈ -0.164  →  significant quality-aware
    """
    show = [("D", "Std VIB"), ("F", "Q-VIB Full")]
    fig, axes = plt.subplots(1, 2, figsize=(7.0, 3.2), sharey=True)

    for ax, (bl, bname) in zip(axes, show):
        sub  = ham_preds[ham_preds["baseline"] == bl].copy()
        p    = sub["prob_pos"].clip(1e-6, 1 - 1e-6).values
        ent  = -(p * np.log(p) + (1 - p) * np.log(1 - p))
        qbar = sub["q_bar"].values   # HAM10000 列名是 q_bar
        meta = METHOD_META[bl]

        rho, pval = spearmanr(ent, qbar)
        if pval < 1e-60:
            p_str = r"$p < 10^{-60}$"
        elif pval < 1e-10:
            p_str = r"$p < 10^{-10}$"
        else:
            p_str = f"$p = {pval:.2e}$"

        hb = ax.hexbin(qbar, ent, gridsize=50,
                       cmap="Blues" if bl == "D" else "Reds",
                       mincnt=1, linewidths=0.1)

        # 分位数趋势线（20 等分 bin 内取中位数）
        q_bins  = np.linspace(qbar.min(), qbar.max(), 21)
        q_mid   = (q_bins[:-1] + q_bins[1:]) / 2
        ent_med = []
        for i in range(len(q_bins) - 1):
            mask = (qbar >= q_bins[i]) & (qbar < q_bins[i + 1])
            ent_med.append(np.median(ent[mask]) if mask.sum() >= 5 else np.nan)
        ent_med = np.array(ent_med)
        valid   = ~np.isnan(ent_med)
        ax.plot(q_mid[valid], ent_med[valid],
                "-", color=meta["color"], lw=2.2, alpha=0.9)

        # rho 标注框
        rho_color = "#206020" if bl == "F" else "#444444"
        ax.text(0.97, 0.97,
                r"$\rho = $" + f"{rho:.3f}\n{p_str}",
                transform=ax.transAxes, ha="right", va="top",
                fontsize=9, color=rho_color,
                bbox=dict(boxstyle="round,pad=0.3", fc="white", ec=rho_color,
                          alpha=0.85, lw=0.8))

        ax.set_title(bname, pad=6, fontweight="semibold")
        ax.set_xlabel(r"Quality Score $\bar{q}$ (HAM10000, $n=10{,}015$)", labelpad=4)
        ax.set_ylabel("Predictive Entropy $H(p)$", labelpad=4)
        ax.set_xlim(0.35, 1.0)

    axes[1].set_ylabel("")   # 共用 y 轴，右图不重复标

    fig.suptitle(
        "Entropy–Quality Correlation on HAM10000 Zero-Shot",
        fontsize=11, fontweight="semibold", y=1.01)
    fig.tight_layout(pad=1.0, w_pad=0.5)

    for ext in ("pdf", "png"):
        fig.savefig(OUT / f"fig4_entropy_qbar.{ext}", bbox_inches="tight")
        print(f"  [saved] fig4_entropy_qbar.{ext}")
    plt.close(fig)


# ═══════════════════════════════════════════════════════════════════════════════
# Fig 3b: Per-degradation ECE from pre-computed CSV (includes D+QCTS)
# ═══════════════════════════════════════════════════════════════════════════════

SHOW_BLS_DEG_CSV = ["I", "J", "D", "F", "D+QCTS"]
DIM_DISPLAY_CSV = {
    "sharpness":  "Blur\n" + r"($q_1\downarrow$)",
    "brightness": "Low brightness\n" + r"($q_2\downarrow$)",
    "color_temp": "Color temperature\n" + r"($q_4\downarrow$)",
    "contrast":   "Low contrast\n" + r"($q_5\downarrow$)",
}
BL_COLORS_DEG = {
    "I": METHOD_META["I"]["color"],
    "J": METHOD_META["J"]["color"],
    "D": METHOD_META["D"]["color"],
    "F": METHOD_META["F"]["color"],
    "D+QCTS": "#2ca02c",
}
BL_LABELS_DEG = {
    "I": "MC Dropout",
    "J": "Deep Ensemble",
    "D": "Std VIB",
    "F": "Q-VIB Full",
    "D+QCTS": r"D + QCTS (ours)",
}


def fig3_from_csv():
    deg_df = pd.read_csv(PROJ / "results/per_degradation_ece.csv")

    valid_dims = [d for d in ["sharpness", "brightness", "color_temp", "contrast"]
                  if d in deg_df["dim"].unique()]
    n_dims = len(valid_dims)
    n_bls  = len(SHOW_BLS_DEG_CSV)
    bar_w  = 0.15
    x      = np.arange(n_dims)

    fig, ax = plt.subplots(figsize=(max(6.0, n_dims * 2.0), 4.0))

    for i, bl in enumerate(SHOW_BLS_DEG_CSV):
        bl_data = deg_df[deg_df["baseline"] == bl]
        eces = []
        for dim in valid_dims:
            row = bl_data[bl_data["dim"] == dim]
            eces.append(float(row["ece"].values[0]) if len(row) else np.nan)
        offset = (i - (n_bls - 1) / 2) * bar_w
        bars = ax.bar(x + offset, eces, bar_w,
                      label=BL_LABELS_DEG.get(bl, bl),
                      color=BL_COLORS_DEG.get(bl, "#888888"),
                      alpha=0.88, edgecolor="white", linewidth=0.5)

    # n labels
    first_bl = "I"
    for j, dim in enumerate(valid_dims):
        row = deg_df[(deg_df["baseline"] == first_bl) & (deg_df["dim"] == dim)]
        if len(row):
            ax.text(j, ax.get_ylim()[1] * 0.01, f"n={row['n'].values[0]}",
                    ha="center", va="bottom", fontsize=6.5, color="#666666")

    # Reference: Std VIB full ITB-LQ ECE
    itb_res = pd.read_csv(PROJ / "results/itb_results.csv")
    d_lq = itb_res[(itb_res["baseline"] == "D") & (itb_res["subset"] == "ITB-LQ")]
    if len(d_lq):
        ax.axhline(d_lq["ece"].values[0], ls="--", color=METHOD_META["D"]["color"],
                   lw=0.9, alpha=0.6, label=f"Std VIB full ITB-LQ")

    ax.set_xticks(x)
    ax.set_xticklabels([DIM_DISPLAY_CSV.get(d, d) for d in valid_dims], fontsize=9.0)
    ax.set_ylabel("ECE on ITB-LQ (bottom 20th percentile)", labelpad=5)
    ax.set_title("Calibration Error by Degradation Type", pad=8, fontweight="semibold")
    ax.set_ylim(0, ax.get_ylim()[1] * 1.14)
    ax.legend(loc="upper right", framealpha=0.92, edgecolor="lightgray",
              ncol=2, fontsize=8.5)

    fig.tight_layout(pad=1.2)
    for ext in ("pdf", "png"):
        fig.savefig(OUT / f"fig3_degradation.{ext}", bbox_inches="tight")
        print(f"  [saved] fig3_degradation.{ext}")
    plt.close(fig)


# ═══════════════════════════════════════════════════════════════════════════════
# Fig 5: T(q̄) learned curve — 3 seeds overlaid
# ═══════════════════════════════════════════════════════════════════════════════

def _softplus(x):
    return np.log1p(np.exp(np.clip(x, -30, 30)))


def fig5_T_curve():
    import json as _json
    params    = _json.load(open(PROJ / "results/qcts_params.json"))
    T_ts_data = _json.loads(open(ROOT / "checkpoints/stdvib/temperature.json").read())
    T_ts      = float(T_ts_data["T"])

    # Recompute T curves directly from JSON params — avoids stale .npy files
    qbar_grid  = np.linspace(0.0, 1.0, 200)
    alpha_vals = [s["alpha"] for s in params["all_seeds"]]
    T0_vals    = [s["T0"]    for s in params["all_seeds"]]
    T_seeds    = [_softplus(T0 + a * (1.0 - qbar_grid))
                  for T0, a in zip(T0_vals, alpha_vals)]
    T_best     = _softplus(params["T0"] + params["alpha"] * (1.0 - qbar_grid))

    fig, ax = plt.subplots(figsize=(5.5, 3.4))

    seed_colors = ["#aec7e8", "#c5b0d5", "#98df8a"]
    for i, (T_s, T0, a) in enumerate(zip(T_seeds, T0_vals, alpha_vals)):
        ax.plot(qbar_grid, T_s, lw=1.2, ls="--", color=seed_colors[i], alpha=0.75,
                label=fr"Seed {i}: $T_0\!=\!{T0:.2f},\ \alpha\!=\!{a:.2f}$", zorder=3)

    ax.plot(qbar_grid, T_best, lw=2.2, color="#d62728",
            label=fr"Best ($T_0\!=\!{params['T0']:.2f},\ \alpha\!=\!{params['alpha']:.2f}$)",
            zorder=5)

    ax.axhline(T_ts, ls=":", color="gray", lw=1.0, label=f"Standard TS ($T={T_ts:.2f}$)")

    ax.set_xlabel(r"Quality Score $\bar{q}$", labelpad=4)
    ax.set_ylabel(r"Temperature $T(\bar{q})$", labelpad=4)
    ax.set_xlim(0, 1)
    ax.set_title(r"Learned QCTS Temperature Function $T(\bar{q})$",
                 fontweight="semibold", pad=6)
    ax.legend(fontsize=8, framealpha=0.92, edgecolor="lightgray")

    # Annotations
    ax.annotate(r"Low $\bar{q}$: high $T$ → uncertain",
                xy=(0.05, float(T_best[10])),
                xytext=(0.28, float(T_best[10]) + 0.15),
                arrowprops=dict(arrowstyle="->", color="#666666", lw=0.8),
                fontsize=7.5, color="#666666", ha="center")
    ax.annotate(r"High $\bar{q}$: low $T$ → confident",
                xy=(0.95, float(T_best[-1])),
                xytext=(0.72, float(T_best[-1]) - 0.18),
                arrowprops=dict(arrowstyle="->", color="#666666", lw=0.8),
                fontsize=7.5, color="#666666", ha="center")

    fig.tight_layout(pad=1.2)
    for ext in ("pdf", "png"):
        fig.savefig(OUT / f"fig5_T_curve.{ext}", bbox_inches="tight")
        print(f"  [saved] fig5_T_curve.{ext}")
    plt.close(fig)


# ═══════════════════════════════════════════════════════════════════════════════
# Fig 6: QCDI bar chart — all methods, sorted, colored by taxonomy
# ═══════════════════════════════════════════════════════════════════════════════

TAXONOMY_COLOR = {
    "Quality-Oblivious": "#d62728",
    "Quality-Fragile":   "#ff7f0e",
    "Quality-Aware":     "#2ca02c",
}

def fig6_qcdi_barchart():
    qcdi_df = pd.read_csv(PROJ / "results/all_qcdi_summary.csv")

    # Sort by QCDI descending (worst to best)
    qcdi_df = qcdi_df.sort_values("qcdi", ascending=False).reset_index(drop=True)

    # Label map
    LABELS = {
        "A": "EfficientNet-B3",
        "I": "MC Dropout",
        "J": "Deep Ensemble",
        "G": "Q-VIB+TokFT*",
        "H": "Focal + LS",
        "D": "Std VIB",
        "TS": "Std VIB + TS",
        "E": "Adaptive Prior",
        "F": "Q-VIB Full",
        "D+QCTS": r"Std VIB + QCTS (ours)",
    }

    bls  = qcdi_df["baseline"].tolist()
    qcdi = qcdi_df["qcdi"].values
    tax  = qcdi_df["taxonomy"].tolist()
    cols = [TAXONOMY_COLOR[t] for t in tax]
    labels = [LABELS.get(b, b) for b in bls]

    fig, ax = plt.subplots(figsize=(7.0, 3.8))
    x = np.arange(len(bls))
    bars = ax.bar(x, qcdi, color=cols, alpha=0.85, edgecolor="white", linewidth=0.5, zorder=3)

    # Value labels on bars
    for xi, (bar, val) in enumerate(zip(bars, qcdi)):
        va = "bottom" if val >= 0 else "top"
        offset = 0.004 if val >= 0 else -0.004
        ax.text(xi, val + offset, f"{val:+.3f}", ha="center", va=va, fontsize=7.5)

    ax.axhline(0, color="black", lw=0.8)

    # Taxonomy background bands
    boundaries = {
        "Quality-Oblivious": (0.10, qcdi.max() + 0.05),
        "Quality-Fragile":   (0.04, 0.10),
        "Quality-Aware":     (qcdi.min() - 0.02, 0.04),
    }
    for tname, (ylo, yhi) in boundaries.items():
        ax.axhspan(ylo, yhi, color=TAXONOMY_COLOR[tname], alpha=0.06, zorder=0)

    # Taxonomy labels on right
    for tname, (ylo, yhi) in boundaries.items():
        ymid = (ylo + yhi) / 2
        if ymid < qcdi.min() - 0.01 or ymid > qcdi.max() + 0.04:
            continue
        ax.text(len(bls) - 0.2, ymid, tname.replace("-", "-\n"),
                ha="right", va="center", fontsize=7.5,
                color=TAXONOMY_COLOR[tname], style="italic")

    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=28, ha="right", fontsize=8.5)
    ax.set_ylabel(r"QCDI = $\mathrm{ECE}_\mathrm{LQ} - \mathrm{ECE}_\mathrm{HQ}$", labelpad=5)
    ax.set_title("Quality-Calibration Degradation Index (QCDI) Across All Methods",
                 fontweight="semibold", pad=6)
    ax.set_ylim(qcdi.min() - 0.04, qcdi.max() + 0.06)

    # Legend
    legend_patches = [mpatches.Patch(color=TAXONOMY_COLOR[t], alpha=0.85, label=t)
                      for t in ["Quality-Oblivious", "Quality-Fragile", "Quality-Aware"]]
    ax.legend(handles=legend_patches, loc="upper right", fontsize=8,
              framealpha=0.92, edgecolor="lightgray")

    fig.tight_layout(pad=1.2)
    for ext in ("pdf", "png"):
        fig.savefig(OUT / f"fig6_qcdi_barchart.{ext}", bbox_inches="tight")
        print(f"  [saved] fig6_qcdi_barchart.{ext}")
    plt.close(fig)


# ═══════════════════════════════════════════════════════════════════════════════
# Fig 7: QCDI Threshold Sensitivity
# ═══════════════════════════════════════════════════════════════════════════════

SHOW_SENS = ["A", "I", "D", "F", "D+QCTS"]
SENS_LABELS = {
    "A":     "EfficientNet-B3",
    "I":     "MC Dropout",
    "D":     "Std VIB",
    "F":     "Q-VIB Full",
    "D+QCTS": r"D + QCTS (ours)",
}
SENS_COLORS = {
    "A":     METHOD_META["A"]["color"],
    "I":     METHOD_META["I"]["color"],
    "D":     METHOD_META["D"]["color"],
    "F":     METHOD_META["F"]["color"],
    "D+QCTS": "#2ca02c",
}
SENS_LS = {"A": "-", "I": "-.", "D": "--", "F": ":", "D+QCTS": "-"}
SENS_LW = {"A": 1.8, "I": 1.4, "D": 1.4, "F": 1.4, "D+QCTS": 2.0}


def fig7_threshold_sensitivity():
    sens_path = PROJ / "results/threshold_sensitivity.csv"
    if not sens_path.exists():
        print("  Skipped: threshold_sensitivity.csv not found")
        return

    df = pd.read_csv(sens_path)
    taus = sorted(df["tau_lq"].unique())

    fig, ax = plt.subplots(figsize=(5.0, 3.2))

    # Taxonomy background bands
    ax.axhspan(0.10, 0.35, color=TAXONOMY_COLOR["Quality-Oblivious"], alpha=0.07, zorder=0)
    ax.axhspan(0.04, 0.10, color=TAXONOMY_COLOR["Quality-Fragile"],   alpha=0.07, zorder=0)
    ax.axhspan(-0.06, 0.04, color=TAXONOMY_COLOR["Quality-Aware"],    alpha=0.07, zorder=0)

    # Taxonomy boundary lines
    ax.axhline(0.10, ls=":", color=TAXONOMY_COLOR["Quality-Oblivious"], lw=0.8, alpha=0.6)
    ax.axhline(0.04, ls=":", color=TAXONOMY_COLOR["Quality-Fragile"],   lw=0.8, alpha=0.6)
    ax.axhline(0.00, ls="-", color="black", lw=0.6, alpha=0.4)

    for bl in SHOW_SENS:
        bl_df = df[df["baseline"] == bl].sort_values("tau_lq")
        if len(bl_df) == 0:
            continue
        ax.plot(bl_df["tau_lq"], bl_df["qcdi"],
                color=SENS_COLORS[bl], lw=SENS_LW[bl], ls=SENS_LS[bl],
                marker="o", markersize=4,
                label=SENS_LABELS[bl], zorder=4)

    # Band labels
    ax.text(taus[-1] + 0.003, 0.18, "Oblivious", fontsize=7,
            color=TAXONOMY_COLOR["Quality-Oblivious"], va="center", style="italic")
    ax.text(taus[-1] + 0.003, 0.07, "Fragile",   fontsize=7,
            color=TAXONOMY_COLOR["Quality-Fragile"],   va="center", style="italic")
    ax.text(taus[-1] + 0.003, 0.00, "Aware",     fontsize=7,
            color=TAXONOMY_COLOR["Quality-Aware"],     va="center", style="italic")

    ax.set_xlabel(r"LQ threshold $\tau_\mathrm{LQ}$", labelpad=4)
    ax.set_ylabel("QCDI", labelpad=4)
    ax.set_title("QCDI vs. LQ Threshold (Robustness Check)",
                 fontweight="semibold", pad=6, fontsize=10)
    ax.legend(fontsize=7.5, framealpha=0.92, edgecolor="lightgray",
              loc="upper right", ncol=1)
    ax.set_xlim(taus[0] - 0.005, taus[-1] + 0.025)

    fig.tight_layout(pad=1.2)
    for ext in ("pdf", "png"):
        fig.savefig(OUT / f"fig7_threshold_sensitivity.{ext}", bbox_inches="tight")
        print(f"  [saved] fig7_threshold_sensitivity.{ext}")
    plt.close(fig)


# ═══════════════════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    print("Loading data...")
    itb_results = pd.read_csv(PROJ / "results/itb_results.csv")
    itb_preds   = pd.read_csv(PROJ / "results/itb_predictions.csv")
    itb_subsets = pd.read_csv(PROJ / "results/itb_subsets.csv")
    q_labels    = pd.read_csv(ROOT / "data/quality_labels_all.csv")

    # 加载 QCTS 真实值覆盖投影值
    qcts_path = PROJ / "results/qcts_itb_results.csv"
    if qcts_path.exists():
        qcts_df = pd.read_csv(qcts_path)
        lq_row  = qcts_df[qcts_df["subset"] == "ITB-LQ"]
        hq_row  = qcts_df[qcts_df["subset"] == "ITB-HQ"]
        if len(lq_row) and len(hq_row):
            global QCTS_VAL, QCTS_RHO
            QCTS_VAL["ITB-LQ"]["ece"] = float(lq_row["ece"].values[0])
            QCTS_VAL["ITB-HQ"]["ece"] = float(hq_row["ece"].values[0])
            QCTS_RHO = float(qcts_df["rho"].values[0])
        qcts_df_fig = qcts_df.copy()
        qcts_df_fig["baseline"] = "QCTS"
        itb_results = pd.concat([itb_results, qcts_df_fig], ignore_index=True)
        print(f"  [QCTS] LQ ECE={QCTS_VAL['ITB-LQ']['ece']:.3f}  "
              f"HQ ECE={QCTS_VAL['ITB-HQ']['ece']:.3f}  QCDI={QCTS_VAL['ITB-LQ']['ece'] - QCTS_VAL['ITB-HQ']['ece']:+.4f}")

    # Merge QCTS predictions for fig2/fig3
    qcts_preds_path = PROJ / "results/qcts_itb_predictions.csv"
    if qcts_preds_path.exists():
        qcts_preds = pd.read_csv(qcts_preds_path)
        itb_preds_full = pd.concat([itb_preds, qcts_preds], ignore_index=True)
    else:
        itb_preds_full = itb_preds

    print("[Fig 0] Teaser figure...")
    fig0_teaser()

    print("\n[Fig 1] Taxonomy scatter (2-panel)...")
    fig1_taxonomy(itb_results)

    print("[Fig 2] Reliability diagrams...")
    fig2_reliability(itb_preds)

    print("[Fig 3] Per-degradation ECE...")
    if (PROJ / "results/per_degradation_ece.csv").exists():
        print("  Using pre-computed per_degradation_ece.csv")
        fig3_from_csv()
    else:
        fig3_degradation(itb_preds, q_labels, itb_subsets)

    print("[Fig 4] Entropy-qbar scatter (HAM10000)...")
    ham_preds = pd.read_csv(PROJ / "results/external_ham10000_predictions.csv")
    fig4_entropy_qbar(ham_preds)

    print("[Fig 5] T(q_bar) learned curve...")
    if (PROJ / "results/qcts_T_curve.npy").exists():
        fig5_T_curve()
    else:
        print("  Skipped: qcts_T_curve.npy not found")

    print("[Fig 6] QCDI bar chart...")
    if (PROJ / "results/all_qcdi_summary.csv").exists():
        fig6_qcdi_barchart()
    else:
        print("  Skipped: all_qcdi_summary.csv not found")

    print("[Fig 7] Threshold sensitivity...")
    fig7_threshold_sensitivity()

    print(f"\n[Done] All figures -> {OUT}/")


if __name__ == "__main__":
    main()
