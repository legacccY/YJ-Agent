#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
plot_17tools_corrected.py
服务: quantimmu-bench — HLA-FIX(6-27) 后 17 工具全横评图 (corrected)

数据源:
  analysis/metrics_ds2_16tools.csv  (DS2 corrected-full, 17 工具×9行/工具)
  (注释行 # 开头自动 skip)

产出 (不覆盖旧 8tools 图):
  analysis/figures/fig_spearman_17tools_corrected.png/pdf
  analysis/figures/fig_auc_17tools_corrected.png/pdf

颜色方案 (Okabe-Ito accessible):
  老 8 工具 (metrics_ds2_8tools 已有): #0072B2 蓝
  新 9 工具 (本轮新增):               #E69F00 橙
  pending_DTU_consent (netmhcpan_ba): #CC79A7 粉

标注规则:
  † reinference_pending = P101/P102 无有效分，n=86 而非 101
  ‡ pending_DTU_consent = DTU 同意待获取
"""

from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches

HERE = Path(__file__).resolve().parent
METRICS = HERE / "metrics_ds2_16tools.csv"
FIG_DIR = HERE / "figures"
FIG_DIR.mkdir(exist_ok=True)

# ── 颜色 ────────────────────────────────────────────────────────────────────
COLOR_OLD  = "#0072B2"   # 蓝 — 原始 8 工具
COLOR_NEW  = "#E69F00"   # 橙 — 新增 9 工具
COLOR_DTU  = "#CC79A7"   # 粉 — pending DTU consent

# 原始 8 工具（来自 metrics_ds2_8tools.csv 定义）
OLD_TOOLS = {
    "DeepImmuno", "PredIG", "NeoTImmuML", "IMPROVE",
    "pTuneos", "PRIME", "ImmuneApp", "deepHLApan"
}


def load_data() -> pd.DataFrame:
    """读 CSV，跳过 # 开头注释行。"""
    df = pd.read_csv(METRICS, comment="#")
    return df


def sig_stars(p: float) -> str:
    """显著性星标。"""
    if p < 0.001:
        return "***"
    if p < 0.01:
        return "**"
    if p < 0.05:
        return "*"
    return ""


def get_color(tool: str, pending_dtu: bool) -> str:
    if pending_dtu:
        return COLOR_DTU
    if tool in OLD_TOOLS:
        return COLOR_OLD
    return COLOR_NEW


def select_best_spearman(df: pd.DataFrame) -> pd.DataFrame:
    """
    每工具选代表聚合 = |rho| 最大的 aggregation。
    注: Spearman rho 在同 aggregation 内不随 threshold 变，故先去重 (Tool, Aggregation)。
    """
    cols = ["Tool", "Aggregation", "Threshold", "n_pep",
            "Spearman_rho", "Spearman_pval",
            "pending_DTU_consent", "reinference_pending"]
    # 每 (Tool, Aggregation) 只保留一行 (取 >0 threshold 作为代表标注)
    sub = df[df["Threshold"] == ">0"][cols].copy()
    sub["abs_rho"] = sub["Spearman_rho"].abs()
    best = sub.loc[sub.groupby("Tool")["abs_rho"].idxmax()].copy()
    best = best.drop(columns=["abs_rho"]).reset_index(drop=True)
    return best


def select_best_auc(df: pd.DataFrame) -> pd.DataFrame:
    """每工具选代表 aggregation+threshold = AUC_ROC 最大的行。"""
    cols = ["Tool", "Aggregation", "Threshold", "n_pep", "n_pos", "n_neg",
            "AUC_ROC", "AUPRC", "pending_DTU_consent", "reinference_pending"]
    best = df.loc[df.groupby("Tool")["AUC_ROC"].idxmax(), cols].copy()
    best = best.reset_index(drop=True)
    return best


def make_ylabel(row) -> str:
    name = row["Tool"]
    suffix = ""
    if row["reinference_pending"]:
        suffix += " †"
    if row["pending_DTU_consent"]:
        suffix += " ‡"
    return f"{name}{suffix}"


def save_fig(fig: plt.Figure, name: str) -> None:
    png = FIG_DIR / f"{name}.png"
    pdf = FIG_DIR / f"{name}.pdf"
    fig.savefig(png, dpi=200, bbox_inches="tight")
    fig.savefig(pdf, bbox_inches="tight")
    print(f"saved {png}")
    print(f"saved {pdf}")


# ── Fig 1: Spearman rho 横向条形图 ─────────────────────────────────────────
def plot_spearman(df: pd.DataFrame) -> None:
    best = select_best_spearman(df)
    # 按 rho 升序 → 负值在底部，正值在顶部，最正 = 最顶
    best = best.sort_values("Spearman_rho", ascending=True).reset_index(drop=True)

    n = len(best)
    fig, ax = plt.subplots(figsize=(11, 9))
    y = np.arange(n)
    rho  = best["Spearman_rho"].values.astype(float)
    pval = best["Spearman_pval"].values.astype(float)
    colors = [get_color(r["Tool"], r["pending_DTU_consent"]) for _, r in best.iterrows()]

    ax.barh(y, rho, height=0.62, color=colors, edgecolor="#444", linewidth=0.5, zorder=3)

    # 唯一基准线: rho = 0
    ax.axvline(0.0, color="#444", lw=1.6, zorder=4)

    # 标注: rho值 + 星 + [agg] 于柱外
    for i, (_, row) in enumerate(best.iterrows()):
        rho_v = float(row["Spearman_rho"])
        stars = sig_stars(float(row["Spearman_pval"]))
        agg   = row["Aggregation"]
        label = f"{rho_v:+.3f}{stars}  [{agg}]"
        xoff  = 0.008 if rho_v >= 0 else -0.008
        ha    = "left" if rho_v >= 0 else "right"
        ax.text(rho_v + xoff, i, label,
                ha=ha, va="center", fontsize=7.8, color="#222", zorder=5)

    ylabels = [make_ylabel(row) for _, row in best.iterrows()]
    ax.set_yticks(y)
    ax.set_yticklabels(ylabels, fontsize=9)

    lim = max(0.48, float(np.nanmax(np.abs(rho))) + 0.15)
    ax.set_xlim(-lim, lim)
    ax.set_xlabel("Spearman rho  (peptide score vs ELISpot, DS2 corrected)", fontsize=10)
    ax.set_title(
        "17-Tool Spearman Correlation — DS2 after HLA-FIX (2026-06-27)\n"
        "Each tool: aggregation with best |rho|  |  * p<0.05   ** p<0.01   *** p<0.001",
        fontsize=10, pad=8
    )

    # 图例
    legend_handles = [
        mpatches.Patch(color=COLOR_OLD,  label="Original 8 tools"),
        mpatches.Patch(color=COLOR_NEW,  label="New 9 tools"),
        mpatches.Patch(color=COLOR_DTU,  label="Pending DTU consent (‡)"),
    ]
    ax.legend(handles=legend_handles, loc="lower right", fontsize=8.5)

    ax.text(0.0, -0.05,
            "†  reinference_pending: P101/P102 not scored — n=86 peptides (vs 101 for NeoTImmuML/Repitope)\n"
            "‡  pending_DTU_consent: DTU data-use agreement pending",
            transform=ax.transAxes, fontsize=7.5, color="#555")

    ax.grid(axis="x", color="#eee", lw=0.5, zorder=0)
    ax.set_axisbelow(True)
    plt.tight_layout(rect=[0, 0.04, 1, 1])
    save_fig(fig, "fig_spearman_17tools_corrected")
    plt.close(fig)

    # ── 核对回汇表 ──────────────────────────────────────────────────────────
    print("\n=== Spearman 代表值表 (按 rho 降序) ===")
    header = f"{'Tool':<30} {'Agg':<12} {'rho':>8} {'p':>8} {'sig':<5} {'reinf':<6} {'DTU':<6}"
    print(header)
    print("-" * len(header))
    for _, row in best.sort_values("Spearman_rho", ascending=False).iterrows():
        print(f"{row['Tool']:<30} {row['Aggregation']:<12} "
              f"{float(row['Spearman_rho']):>8.4f} {float(row['Spearman_pval']):>8.4f} "
              f"{sig_stars(float(row['Spearman_pval'])):<5} "
              f"{str(bool(row['reinference_pending'])):<6} "
              f"{str(bool(row['pending_DTU_consent'])):<6}")


# ── Fig 2: AUC-ROC 横向条形图 ───────────────────────────────────────────────
def plot_auc(df: pd.DataFrame) -> None:
    best = select_best_auc(df)
    # 按 AUC 升序 → 最高在顶
    best = best.sort_values("AUC_ROC", ascending=True).reset_index(drop=True)

    n = len(best)
    fig, ax = plt.subplots(figsize=(11, 9))
    y = np.arange(n)
    auc    = best["AUC_ROC"].values.astype(float)
    colors = [get_color(r["Tool"], r["pending_DTU_consent"]) for _, r in best.iterrows()]

    ax.barh(y, auc, height=0.62, color=colors, edgecolor="#444", linewidth=0.5, zorder=3)

    # 基准线: 0.5 随机 + 0.75 参考
    ax.axvline(0.5,  color="#888",   lw=1.4, ls="--", zorder=4, label="Random (AUC=0.5)")
    ax.axvline(0.75, color="#CC6600", lw=1.0, ls=":",  zorder=4, label="Reference (AUC=0.75)")

    # 标注: AUC值 + [agg/threshold]
    for i, (_, row) in enumerate(best.iterrows()):
        auc_v = float(row["AUC_ROC"])
        label = f"{auc_v:.3f}  [{row['Aggregation']}/{row['Threshold']}]"
        ax.text(auc_v + 0.006, i, label,
                ha="left", va="center", fontsize=7.8, color="#222", zorder=5)

    ylabels = [make_ylabel(row) for _, row in best.iterrows()]
    ax.set_yticks(y)
    ax.set_yticklabels(ylabels, fontsize=9)

    ax.set_xlim(0.0, 1.05)
    ax.set_xticks(np.arange(0.0, 1.01, 0.1))
    ax.set_xlabel("AUC-ROC  (DS2 corrected)", fontsize=10)
    ax.set_title(
        "17-Tool AUC-ROC — DS2 after HLA-FIX (2026-06-27)\n"
        "Each tool: aggregation + threshold with best AUC",
        fontsize=10, pad=8
    )

    legend_handles = [
        mpatches.Patch(color=COLOR_OLD,  label="Original 8 tools"),
        mpatches.Patch(color=COLOR_NEW,  label="New 9 tools"),
        mpatches.Patch(color=COLOR_DTU,  label="Pending DTU consent (‡)"),
        plt.Line2D([0], [0], color="#888",    ls="--", lw=1.4, label="Random (0.5)"),
        plt.Line2D([0], [0], color="#CC6600", ls=":",  lw=1.0, label="Reference (0.75)"),
    ]
    ax.legend(handles=legend_handles, loc="lower right", fontsize=8.5)

    ax.text(0.0, -0.05,
            "†  reinference_pending: P101/P102 not scored — n=86 peptides (vs 101 for NeoTImmuML/Repitope)\n"
            "‡  pending_DTU_consent: DTU data-use agreement pending",
            transform=ax.transAxes, fontsize=7.5, color="#555")

    ax.grid(axis="x", color="#eee", lw=0.5, zorder=0)
    ax.set_axisbelow(True)
    plt.tight_layout(rect=[0, 0.04, 1, 1])
    save_fig(fig, "fig_auc_17tools_corrected")
    plt.close(fig)

    # ── 核对回汇表 ──────────────────────────────────────────────────────────
    print("\n=== AUC 代表值表 (按 AUC 降序) ===")
    header = f"{'Tool':<30} {'Agg':<12} {'Thr':<10} {'AUC':>8} {'reinf':<6} {'DTU':<6}"
    print(header)
    print("-" * len(header))
    for _, row in best.sort_values("AUC_ROC", ascending=False).iterrows():
        print(f"{row['Tool']:<30} {row['Aggregation']:<12} "
              f"{row['Threshold']:<10} {float(row['AUC_ROC']):>8.4f} "
              f"{str(bool(row['reinference_pending'])):<6} "
              f"{str(bool(row['pending_DTU_consent'])):<6}")


def verify_analyst_figs() -> None:
    """核对 analyst 已出图是否存在。"""
    targets = [
        FIG_DIR / "fig_newtools_fisherz.png",
        FIG_DIR / "fig_newtools_auc.png",
        FIG_DIR / "fig_newtools_spearman_heatmap.png",
    ]
    print("\n=== 核对 analyst 既有图 ===")
    for p in targets:
        status = "EXISTS" if p.exists() else "MISSING"
        print(f"  [{status}] {p.name}")


def main() -> None:
    df = load_data()
    n_tools = df["Tool"].nunique()
    print(f"Loaded {len(df)} rows, {n_tools} tools")
    print("Tools:", sorted(df["Tool"].unique()))

    verify_analyst_figs()
    plot_spearman(df)
    plot_auc(df)

    print("\n=== 17-tool corrected figures DONE ===")
    print(f"Output dir: {FIG_DIR}")


if __name__ == "__main__":
    main()
