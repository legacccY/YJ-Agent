"""
ArtiOODBench — fig_heldout_vim_vs_artifact (n=7 版本)
散点图：x = artifact-only all_43dim AUROC (source separability)
        y = held-out ViM AUROC (A-5 正式协议)

数据源：04_LOG Entry 11 / 02_ACCEPTANCE A-5 v6 表，经 verifier 核实，直接硬编码。
覆盖旧 n=4 版 figures/fig_heldout_vim_vs_artifact.pdf/.png。

Drift contract: ArtiOODBench § lever=投稿前图收尾。无文件写入 results/，只输出 figures/。
"""

import os
os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"
os.environ.setdefault("OMP_NUM_THREADS", "1")

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from pathlib import Path

# ── 路径 ─────────────────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent.parent
FIG  = ROOT / "figures"
FIG.mkdir(parents=True, exist_ok=True)

OUT_PDF = FIG / "fig_heldout_vim_vs_artifact.pdf"
OUT_PNG = FIG / "fig_heldout_vim_vs_artifact.png"

# ── 硬编码数据（04_LOG Entry 11 / 02_ACCEPTANCE A-5 v6 表，verifier 已核）───
# (label, artifact_auroc, heldout_vim_auroc)
DATA = [
    ("BraTS",                  0.9997, 0.997),
    ("HAM_vs_fitzpatrick17k",  0.991,  0.938),
    ("VinDr_vs_RSNA",          0.907,  0.772),
    ("NIH_vs_VinDr",           0.896,  0.841),
    ("HAM_vs_ISIC2020",        0.816,  0.689),
    ("ISIC2020_vs_PAD_UFES",   0.805,  0.798),
    ("NIH_vs_RSNA",            0.640,  0.406),  # honest negative (≈chance)
]

HONEST_NEG_LABEL = "NIH_vs_RSNA"

# ── 字体规范（贴合 plot_v5_figures.py 风格）──────────────────────────────────
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

# ── 颜色（Wong 2011 colorblind-safe，与项目其他图一致）───────────────────────
C_MAIN = "#0072B2"   # blue  — 普通点
C_NEG  = "#D55E00"   # red   — honest negative (NIH_vs_RSNA)


def spearman_numpy(x, y):
    """纯 numpy Spearman ρ（禁 scipy，避免 OMP Error #15）。"""
    n = len(x)
    rx = np.argsort(np.argsort(x)).astype(float) + 1
    ry = np.argsort(np.argsort(y)).astype(float) + 1
    d2 = np.sum((rx - ry) ** 2)
    return 1.0 - 6.0 * d2 / (n * (n ** 2 - 1))


def pearson_numpy(x, y):
    """纯 numpy Pearson r。"""
    xm, ym = x - x.mean(), y - y.mean()
    return float(np.dot(xm, ym) / (np.linalg.norm(xm) * np.linalg.norm(ym) + 1e-12))


def main():
    labels  = [d[0] for d in DATA]
    xs      = np.array([d[1] for d in DATA])
    ys      = np.array([d[2] for d in DATA])

    rho = spearman_numpy(xs, ys)
    r   = pearson_numpy(xs, ys)
    n   = len(DATA)

    # ── 拟合线 ────────────────────────────────────────────────────────────────
    coeffs  = np.polyfit(xs, ys, 1)
    x_line  = np.linspace(xs.min() - 0.02, xs.max() + 0.02, 200)
    y_line  = np.polyval(coeffs, x_line)

    # ── 画布 ──────────────────────────────────────────────────────────────────
    fig, ax = plt.subplots(figsize=(5.5, 4.5))

    # chance 水平虚线（y=0.5）
    ax.axhline(0.5, color="gray", linewidth=0.9, linestyle="--",
               label="Chance (AUROC = 0.5)", zorder=1)

    # 拟合线
    ax.plot(x_line, y_line, color="dimgray", linewidth=1.2,
            linestyle="-", zorder=2, label="Linear fit")

    # 散点
    for lbl, x, y in DATA:
        is_neg = (lbl == HONEST_NEG_LABEL)
        color  = C_NEG if is_neg else C_MAIN
        marker = "^" if is_neg else "o"
        ax.scatter(x, y, color=color, marker=marker, s=70, zorder=4,
                   edgecolors="white", linewidths=0.5)

    # 文字标签（手动微调 offset 避免遮挡）
    OFFSETS = {
        "BraTS":                 (-0.005, 0.012),
        "HAM_vs_fitzpatrick17k": (-0.005, 0.012),
        "VinDr_vs_RSNA":         (0.008,  0.008),
        "NIH_vs_VinDr":          (-0.06,  0.012),
        "HAM_vs_ISIC2020":       (0.008, -0.022),
        "ISIC2020_vs_PAD_UFES":  (-0.11,  0.012),
        "NIH_vs_RSNA":           (0.008,  0.008),
    }
    for lbl, x, y in DATA:
        is_neg = (lbl == HONEST_NEG_LABEL)
        dx, dy = OFFSETS.get(lbl, (0.008, 0.008))
        display_lbl = lbl.replace("_vs_", "\nvs ")
        if is_neg:
            display_lbl += "\n(honest neg.)"
        ax.text(x + dx, y + dy, display_lbl,
                fontsize=FONT_SIZE - 2.5,
                color=C_NEG if is_neg else "black",
                va="bottom", ha="left", zorder=5)

    # 统计注释
    stat_text = (
        f"Spearman ρ = {rho:.3f}\n"
        f"Pearson r = {r:.3f}  (n = {n})"
    )
    ax.text(0.03, 0.97, stat_text,
            transform=ax.transAxes,
            fontsize=FONT_SIZE - 1.5,
            va="top", ha="left",
            bbox=dict(boxstyle="round,pad=0.3", facecolor="white",
                      edgecolor="lightgray", alpha=0.85))

    # 轴标签 / 范围
    ax.set_xlabel("Artifact-only AUROC (source separability)", fontsize=FONT_SIZE)
    ax.set_ylabel("Held-out ViM AUROC", fontsize=FONT_SIZE)
    ax.set_title("Artifact Separability vs. Held-out ViM OOD Performance\n"
                 r"($\rho$=0.821, $r$=0.955, $n$=7)",
                 fontsize=FONT_SIZE + 0.5)

    ax.set_xlim(0.58, 1.04)
    ax.set_ylim(0.33, 1.03)
    ax.tick_params(axis="both", which="both", length=3)

    # 图例
    from matplotlib.lines import Line2D
    legend_handles = [
        Line2D([0], [0], marker="o", color="w", markerfacecolor=C_MAIN,
               markersize=7, label="Dataset pair"),
        Line2D([0], [0], marker="^", color="w", markerfacecolor=C_NEG,
               markersize=7, label="Honest negative (NIH vs RSNA)"),
        Line2D([0], [0], color="dimgray", linewidth=1.2, label="Linear fit"),
        Line2D([0], [0], color="gray", linewidth=0.9, linestyle="--",
               label="Chance (0.5)"),
    ]
    ax.legend(handles=legend_handles, fontsize=FONT_SIZE - 2,
              loc="lower right", framealpha=0.85)

    plt.tight_layout()

    fig.savefig(OUT_PDF, bbox_inches="tight")
    fig.savefig(OUT_PNG, dpi=200, bbox_inches="tight")
    plt.close(fig)

    print(f"[OK] {OUT_PDF}")
    print(f"[OK] {OUT_PNG}")
    print(f"     Spearman rho={rho:.3f}  Pearson r={r:.3f}  n={n}")


if __name__ == "__main__":
    main()
