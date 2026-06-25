#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
plot_5tools_max.py
服务: quantimmu-bench — 第一批 5 工具 benchmark 图（DS2, max 聚合, Elispot>0）

改编自 plot_fig6to8_8tools.py，口径完全一致（max agg, >0）。
工具集：DeepImmuno / PredIG / pTuneos / IMPROVE / NeoTImmuML（第一批，无新工具橙色）。

数据源:
  - AUC / Spearman: analysis/metrics_ds2.csv         (5 工具版, max + >0 行)
  - 95% CI:         analysis/bootstrap_ci_ds2.csv     (含 5 工具)
  - ROC 点:         scripts/out/merged_all_tools_5tools.xlsx (优先；缺则回退 8tools.xlsx)

输出 (analysis/figures/):
  fig6_5tools_auc.png / .pdf
  fig7_5tools_spearman.png / .pdf
  fig8_5tools_roc.png / .pdf

跑法 (主线，本脚本不自跑):
  python analysis/plot_5tools_max.py
"""
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from sklearn.metrics import roc_curve, auc as sklearn_auc

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
METRICS = HERE / "metrics_ds2.csv"                            # 5 工具版，含 max/>0
CI_CSV = HERE / "bootstrap_ci_ds2.csv"
MERGED_5 = ROOT / "scripts" / "out" / "merged_all_tools_5tools.xlsx"
MERGED_8 = ROOT / "scripts" / "out" / "merged_all_tools_8tools.xlsx"
FIG_DIR = HERE / "figures"
FIG_DIR.mkdir(exist_ok=True)

# 顺序固定，全第一批同色系（无 NEW/OLD 区分，统一用同一蓝色）
TOOLS_ORDER = ["DeepImmuno", "PredIG", "pTuneos", "IMPROVE", "NeoTImmuML"]
TOOL_COLS = {
    "DeepImmuno":  "MT_DeepImmuno",
    "PredIG":      "MT_PredIG",
    "pTuneos":     "MT_pTuneos",
    "IMPROVE":     "MT_IMPROVE_mean_prediction_rf",
    "NeoTImmuML":  "MT_NeoTImmuML",
}
# Okabe-Ito 5 色（色盲友好，5 工具各一色）
COLORS_5 = ["#0072B2", "#009E73", "#E69F00", "#CC79A7", "#56B4E9"]

# 自检基准（max, >0；来自 metrics_ds2.csv）
_EXPECTED_AUC = {
    "DeepImmuno": 0.4813,
    "PredIG":     0.6611,
    "pTuneos":    0.7525,
    "IMPROVE":    0.6207,
    "NeoTImmuML": 0.6551,
}


def save_fig(fig, name):
    png = FIG_DIR / f"{name}.png"
    pdf = FIG_DIR / f"{name}.pdf"
    fig.savefig(png, dpi=200, bbox_inches="tight")
    fig.savefig(pdf, bbox_inches="tight")
    print("saved", png)
    print("saved", pdf)


def load_metrics_max_gt0():
    """从 metrics_ds2.csv 取 max 聚合 + >0 阈值行，返回以 Tool 为索引的 DataFrame。"""
    m = pd.read_csv(METRICS)
    sub = m[(m["Aggregation"] == "max") & (m["Threshold"] == ">0")].copy()
    sub = sub.set_index("Tool")
    # 自检：AUC 偏差 > 0.001 说明读错口径
    for tool, expected in _EXPECTED_AUC.items():
        if tool in sub.index:
            got = float(sub.loc[tool, "AUC_ROC"])
            if abs(got - expected) > 0.001:
                print(f"[WARN] {tool} AUC self-check FAIL: got {got:.4f}, expected {expected:.4f} — 请排查口径/列")
    return sub


def _pick_merged():
    """优先用 5tools xlsx；缺则回退 8tools。"""
    if MERGED_5.exists():
        print(f"[info] ROC 数据源: {MERGED_5.name}")
        return pd.read_excel(MERGED_5)
    print(f"[warn] {MERGED_5.name} 不存在，回退 {MERGED_8.name}")
    return pd.read_excel(MERGED_8)


def fig6_auc_with_ci(metrics):
    """AUC 柱 + 95% CI error bar，y 从 0，灰色 0.5 随机线，无最优高亮。"""
    if CI_CSV.exists():
        ci = pd.read_csv(CI_CSV).set_index("Tool")
    else:
        ci = None
        print("[warn] 缺 bootstrap_ci_ds2.csv → fig6 不画 error bar")

    tools = [t for t in TOOLS_ORDER if t in metrics.index]
    auc = np.array([metrics.loc[t, "AUC_ROC"] for t in tools], dtype=float)
    colors = COLORS_5[: len(tools)]

    fig, ax = plt.subplots(figsize=(8.0, 5.2))
    x = np.arange(len(tools))
    ax.bar(x, auc, width=0.62, color=colors, edgecolor="#444", linewidth=0.5)

    # 95% CI error bar（不对称；仅含该工具时叠加）
    if ci is not None:
        lo = np.array([
            metrics.loc[t, "AUC_ROC"] - ci.loc[t, "CI_lo"] if t in ci.index else 0
            for t in tools
        ])
        hi = np.array([
            ci.loc[t, "CI_hi"] - metrics.loc[t, "AUC_ROC"] if t in ci.index else 0
            for t in tools
        ])
        ax.errorbar(x, auc, yerr=[lo, hi], fmt="none", ecolor="#333",
                    elinewidth=1.2, capsize=5, capthick=1.2, zorder=4)

    # 唯一基准：0.5 随机线（灰色虚线）
    ax.axhline(0.5, ls="--", color="#888", lw=1.3, zorder=2, label="random (AUC=0.5)")

    # 柱顶标 AUC 值
    for xi, a in zip(x, auc):
        ax.text(xi, a + 0.012, f"{a:.3f}", ha="center", va="bottom",
                fontsize=8.5, color="#333")

    ax.set_ylim(0, 1.0)                          # 从 0 起，不截断
    ax.set_yticks(np.arange(0, 1.01, 0.2))
    ax.set_xticks(x)
    ax.set_xticklabels(
        [f"{t}\n(n={int(metrics.loc[t, 'n_pep'])})" for t in tools],
        rotation=20, ha="right", fontsize=9
    )
    ax.set_ylabel("AUC-ROC (DS2, max aggregation, Elispot>0)")
    ax.set_title(
        "AUC-ROC — 5 first-batch tools (DS2, max agg, Elispot>0)\n"
        "95% bootstrap CI shown; grey dashed = random baseline"
    )
    ax.legend(loc="upper right", fontsize=9)
    ax.grid(axis="y", color="#eee", lw=0.5, zorder=0)
    ax.set_axisbelow(True)
    save_fig(fig, "fig6_5tools_auc")
    plt.close(fig)


def fig7_spearman(metrics):
    """Spearman rho 柱，0 线唯一基准，对称范围，* 标 p<0.05，无截断。"""
    tools = [t for t in TOOLS_ORDER if t in metrics.index]
    rho = np.array([metrics.loc[t, "Spearman_rho"] for t in tools], dtype=float)
    pval = np.array([metrics.loc[t, "Spearman_pval"] for t in tools], dtype=float)
    colors = COLORS_5[: len(tools)]

    fig, ax = plt.subplots(figsize=(8.0, 5.0))
    x = np.arange(len(tools))
    ax.bar(x, rho, width=0.62, color=colors, edgecolor="#444", linewidth=0.5, zorder=3)
    ax.axhline(0.0, color="#888", lw=1.3, zorder=2)

    for xi, r, p in zip(x, rho, pval):
        star = "*" if p < 0.05 else ""
        off = 0.012 if r >= 0 else -0.012
        ax.text(xi, r + off, f"{r:.3f}{star}",
                ha="center", va="bottom" if r >= 0 else "top",
                fontsize=8.5, color="#333")

    lim = max(0.42, float(np.nanmax(np.abs(rho))) + 0.08)
    ax.set_ylim(-lim, lim)                       # 对称，0 居中，不截断
    ax.set_xticks(x)
    ax.set_xticklabels(
        [f"{t}\n(n={int(metrics.loc[t, 'n_pep'])})" for t in tools],
        rotation=20, ha="right", fontsize=9
    )
    ax.set_ylabel("Spearman rho (score vs ELISpot, max agg)")
    ax.set_title(
        "Spearman correlation — 5 first-batch tools (DS2, max agg, Elispot>0)\n"
        "* p<0.05; 0 line = no correlation"
    )
    ax.grid(axis="y", color="#eee", lw=0.5, zorder=0)
    ax.set_axisbelow(True)
    save_fig(fig, "fig7_5tools_spearman")
    plt.close(fig)


def fig8_roc():
    """5 工具 ROC (max-agg, Elispot>0) 现算，对角随机线，无最优高亮，图例含 AUC。"""
    df = _pick_merged()
    if "Dataset" in df.columns:
        df = df[df["Dataset"] == "DS2"].copy()

    g = df.groupby("Peptide_ID")
    elis = g["Elispot"].first()

    fig, ax = plt.subplots(figsize=(6.2, 6.0))
    plotted = 0
    for (t, col), color in zip(TOOL_COLS.items(), COLORS_5):
        if col not in df.columns:
            print(f"[warn] 列 {col!r} 不在 merged xlsx 中，跳过 {t}")
            continue
        sc = g[col].max()
        m = pd.concat([elis, sc], axis=1)
        m.columns = ["Elispot", "score"]
        m = m.dropna(subset=["Elispot", "score"])
        y = (m["Elispot"].values.astype(float) > 0).astype(int)
        s = m["score"].values.astype(float)
        if len(np.unique(y)) < 2:
            print(f"[warn] {t}: y 只有一类，跳过 ROC")
            continue
        fpr, tpr, _ = roc_curve(y, s)
        roc_auc = sklearn_auc(fpr, tpr)
        ax.plot(fpr, tpr, lw=1.6, ls="-", color=color, alpha=0.88,
                label=f"{t} (AUC={roc_auc:.3f})")
        plotted += 1

    ax.plot([0, 1], [0, 1], ls=":", color="#888", lw=1.2, label="random")
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.set_xlabel("False Positive Rate")
    ax.set_ylabel("True Positive Rate")
    ax.set_title("ROC curves — 5 first-batch tools (DS2, max agg, Elispot>0)")
    ax.legend(loc="lower right", fontsize=8.5)
    ax.grid(color="#eee", lw=0.4, zorder=0)
    ax.set_axisbelow(True)
    if plotted == 0:
        print("[ERROR] 没有任何工具成功画 ROC，请检查 merged xlsx 列名")
    save_fig(fig, "fig8_5tools_roc")
    plt.close(fig)


def main():
    metrics = load_metrics_max_gt0()
    fig6_auc_with_ci(metrics)
    fig7_spearman(metrics)
    fig8_roc()
    print("\n=== fig6/7/8 (5 工具版) 完成 ===")
    print("    fig6_5tools_auc.png / fig7_5tools_spearman.png / fig8_5tools_roc.png")


if __name__ == "__main__":
    main()
