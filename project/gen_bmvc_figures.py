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
import numpy as np
import pandas as pd
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
# Fig 1: Taxonomy Scatter — ECE-HQ (x) vs ECE-LQ (y)
# ═══════════════════════════════════════════════════════════════════════════════

# 手动偏移：精调后不重叠
LABEL_OFFSETS = {
    "A":    (-0.062,  0.010),
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
    xlim_full = (0.07, 0.50)
    ylim_full = (0.10, 0.68)
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
    zoom_x = (0.07, 0.22)
    zoom_y = (0.10, 0.22)
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
    xlim_zoom = (0.07, 0.22)
    ylim_zoom = (0.10, 0.22)

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
        "Entropy–Quality Correlation (Proposition 2): HAM10000 Zero-Shot",
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

def fig5_T_curve():
    data = np.load(PROJ / "results/qcts_T_curve.npy")
    qbar_grid, T_best = data[0], data[1]
    seeds_data = np.load(PROJ / "results/qcts_T_curves_seeds.npy")
    qbar_s, T_seeds = seeds_data[0], seeds_data[1:]

    import json
    params = json.load(open(PROJ / "results/qcts_params.json"))
    alpha_vals = [s["alpha"] for s in params["all_seeds"]]

    fig, ax = plt.subplots(figsize=(5.5, 3.4))

    seed_colors = ["#aec7e8", "#c5b0d5", "#98df8a"]
    for i, (T_s, a) in enumerate(zip(T_seeds, alpha_vals)):
        ax.plot(qbar_s, T_s, lw=1.2, ls="--", color=seed_colors[i],
                label=fr"Seed {i}: $\alpha={a:.2f}$", zorder=3)

    ax.plot(qbar_grid, T_best, lw=2.2, color="#d62728",
            label=fr"Best ($\alpha={params['alpha']:.2f}$)", zorder=5)

    # Reference: standard TS (horizontal line)
    import torch
    T_ts = json.loads(open(ROOT / "checkpoints/stdvib/temperature.json").read())["T"]
    ax.axhline(T_ts, ls=":", color="gray", lw=1.0, label=f"Standard TS ($T={T_ts:.2f}$)")

    ax.set_xlabel(r"Quality Score $\bar{q}$", labelpad=4)
    ax.set_ylabel(r"Temperature $T(\bar{q})$", labelpad=4)
    ax.set_xlim(0, 1)
    ax.set_title(r"Learned QCTS Temperature Function $T(\bar{q})$",
                 fontweight="semibold", pad=6)
    ax.legend(fontsize=8, framealpha=0.92, edgecolor="lightgray")

    # Annotation: low vs high quality
    ax.annotate("Low quality\n(high T → low confidence)",
                xy=(0.1, float(T_best[int(0.1 / 1.0 * len(T_best))])),
                xytext=(0.22, float(T_best[int(0.1 / 1.0 * len(T_best))]) + 0.12),
                arrowprops=dict(arrowstyle="->", color="#666666", lw=0.8),
                fontsize=7.5, color="#666666", ha="center")
    ax.annotate("High quality\n(low T → confident)",
                xy=(0.9, float(T_best[-1])),
                xytext=(0.75, float(T_best[-1]) - 0.18),
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

    print(f"\n[Done] All figures -> {OUT}/")


if __name__ == "__main__":
    main()
