#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
plot_fig6to8_8tools.py
服务: quantimmu-bench — 修 reviewer 🔴-A：重画 fig6/fig7/fig8（全 8 工具，DS2 max/>0）

旧 fig6 的两宗罪（reviewer 致命伤）:
  (1) y 轴从 0.3 截断放大柱差 → 把 ~0.06 的 AUC 差视觉夸成天壤
  (2) 一条红色「pTuneos best (0.75)」基准线 → 把 n_neg=11 下脆弱的点估画成天花板
本脚本修正:
  - fig6: y 轴从 0 起 (scale 0~1)，删 pTuneos 基准线，唯一基准 = 灰色 0.5 随机线，
          每柱叠 95% bootstrap CI error bar（读 bootstrap_ci_ds2.csv，CI 普遍跨 0.5）
  - fig7: Spearman rho 柱状，0 线为唯一基准，无截断 (-0.2~0.4 对称)
  - fig8: 8 工具 ROC 折线 (max-agg, >0)，对角随机线，无任何「最优」高亮

数据源:
  - AUC / Spearman: analysis/metrics_ds2_8tools.csv  (max 聚合, >0 行)
  - 95% CI:         analysis/bootstrap_ci_ds2.csv     (须先跑 bootstrap_ci.py 扩成 8 行)
  - ROC 点:         scripts/out/merged_all_tools_8tools.xlsx 现算 (max-agg, Elispot>0)

输出: analysis/figures/fig6_8tools_auc_comparison.png / fig7_8tools_spearman.png / fig8_8tools_roc_curves.png
      (覆盖旧的截断版；同时存 .pdf 供 PPT)

跑法 (主线，本脚本不自跑):
  python analysis/bootstrap_ci.py            # 先扩 CI 到 8 行
  python analysis/plot_fig6to8_8tools.py
"""
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from sklearn.metrics import roc_curve

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
METRICS = HERE / "metrics_ds2_8tools.csv"
CI_CSV = HERE / "bootstrap_ci_ds2.csv"
MERGED = ROOT / "scripts" / "out" / "merged_all_tools_8tools.xlsx"
FIG_DIR = HERE / "figures"
FIG_DIR.mkdir(exist_ok=True)

# 工具列 + 顺序 (与 bootstrap_ci.py / metrics_topk.py 一致)
TOOL_COLS = {
    "DeepImmuno": "MT_DeepImmuno",
    "PredIG": "MT_PredIG",
    "NeoTImmuML": "MT_NeoTImmuML",
    "IMPROVE": "MT_IMPROVE_mean_prediction_rf",
    "pTuneos": "MT_pTuneos",
    "PRIME": "MT_PRIME",
    "ImmuneApp": "MT_ImmuneApp",
    "deepHLApan": "MT_deepHLApan",
}
NEW_TOOLS = {"ImmuneApp", "PRIME", "deepHLApan"}
# Okabe-Ito：旧蓝、新橙；按 AUC 不预排，柱顺序固定按工具 list
OLD_COLOR = "#0072B2"
NEW_COLOR = "#E69F00"


def save_fig(fig, name):
    png = FIG_DIR / f"{name}.png"
    pdf = FIG_DIR / f"{name}.pdf"
    fig.savefig(png, dpi=200, bbox_inches="tight")
    fig.savefig(pdf, bbox_inches="tight")
    print("saved", png)
    print("saved", pdf)


def load_metrics_max_gt0():
    """从 metrics_ds2_8tools.csv 取 max 聚合 + >0 阈值行 (fig6/fig7 的点)。"""
    m = pd.read_csv(METRICS)
    sub = m[(m["Aggregation"] == "max") & (m["Threshold"] == ">0")].copy()
    sub = sub.set_index("Tool")
    return sub


def fig6_auc_with_ci(metrics):
    """AUC 柱 + 95% CI error bar，y 从 0，唯一基准 0.5 随机线，无 pTuneos 基准线。"""
    if CI_CSV.exists():
        ci = pd.read_csv(CI_CSV).set_index("Tool")
    else:
        ci = None
        print("[warn] 缺 bootstrap_ci_ds2.csv → fig6 不画 error bar，请先跑 bootstrap_ci.py")

    tools = [t for t in TOOL_COLS if t in metrics.index]
    auc = np.array([metrics.loc[t, "AUC_ROC"] for t in tools], dtype=float)
    colors = [NEW_COLOR if t in NEW_TOOLS else OLD_COLOR for t in tools]

    fig, ax = plt.subplots(figsize=(8.5, 5.2))
    x = np.arange(len(tools))
    bars = ax.bar(x, auc, width=0.62, color=colors, edgecolor="grey30" if False else "#444", linewidth=0.5)

    # 95% CI error bar（不对称）
    if ci is not None:
        lo = np.array([metrics.loc[t, "AUC_ROC"] - ci.loc[t, "CI_lo"] if t in ci.index else 0 for t in tools])
        hi = np.array([ci.loc[t, "CI_hi"] - metrics.loc[t, "AUC_ROC"] if t in ci.index else 0 for t in tools])
        ax.errorbar(x, auc, yerr=[lo, hi], fmt="none", ecolor="#333", elinewidth=1.2,
                    capsize=5, capthick=1.2, zorder=4)

    # 唯一基准：0.5 随机线（灰色虚线），删掉旧的 pTuneos best 红线
    ax.axhline(0.5, ls="--", color="#888", lw=1.3, zorder=2, label="random (AUC=0.5)")

    # 柱顶标 AUC 值
    for xi, a in zip(x, auc):
        ax.text(xi, a + 0.012, f"{a:.3f}", ha="center", va="bottom", fontsize=8.5, color="#333")

    ax.set_ylim(0, 1.0)                       # ★ 从 0 起，不截断
    ax.set_yticks(np.arange(0, 1.01, 0.2))
    ax.set_xticks(x)
    ax.set_xticklabels([f"{t}\n(n={int(metrics.loc[t,'n_pep'])})" for t in tools],
                       rotation=20, ha="right", fontsize=9)
    ax.set_ylabel("AUC-ROC (DS2, max aggregation, Elispot>0)")
    ax.set_title("Per-tool AUC with 95% bootstrap CI — all 8 tools (CIs span 0.5; no tool clears random robustly)")
    ax.legend(loc="upper right", fontsize=9)
    ax.grid(axis="y", color="#eee", lw=0.5, zorder=0)
    ax.set_axisbelow(True)
    save_fig(fig, "fig6_8tools_auc_comparison")
    plt.close(fig)


def fig7_spearman(metrics):
    """Spearman rho 柱，0 线唯一基准，对称范围，无截断。"""
    tools = [t for t in TOOL_COLS if t in metrics.index]
    rho = np.array([metrics.loc[t, "Spearman_rho"] for t in tools], dtype=float)
    pval = np.array([metrics.loc[t, "Spearman_pval"] for t in tools], dtype=float)
    colors = [NEW_COLOR if t in NEW_TOOLS else OLD_COLOR for t in tools]

    fig, ax = plt.subplots(figsize=(8.5, 5.0))
    x = np.arange(len(tools))
    ax.bar(x, rho, width=0.62, color=colors, edgecolor="#444", linewidth=0.5, zorder=3)
    ax.axhline(0.0, color="#888", lw=1.3, zorder=2)

    for xi, r, p in zip(x, rho, pval):
        star = "*" if p < 0.05 else ""
        off = 0.012 if r >= 0 else -0.012
        ax.text(xi, r + off, f"{r:.3f}{star}", ha="center",
                va="bottom" if r >= 0 else "top", fontsize=8.5, color="#333")

    lim = max(0.42, np.nanmax(np.abs(rho)) + 0.08)
    ax.set_ylim(-lim, lim)                    # 对称，0 居中，不截断
    ax.set_xticks(x)
    ax.set_xticklabels([f"{t}\n(n={int(metrics.loc[t,'n_pep'])})" for t in tools],
                       rotation=20, ha="right", fontsize=9)
    ax.set_ylabel("Spearman rho (score vs ELISpot, max agg)")
    ax.set_title("Per-tool Spearman correlation — all 8 tools (* p<0.05; magnitudes weak, near 0)")
    ax.grid(axis="y", color="#eee", lw=0.5, zorder=0)
    ax.set_axisbelow(True)
    save_fig(fig, "fig7_8tools_spearman")
    plt.close(fig)


def fig8_roc():
    """8 工具 ROC (max-agg, Elispot>0) 现算，对角随机线，无最优高亮。"""
    df = pd.read_excel(MERGED)
    if "Dataset" in df.columns:
        df = df[df["Dataset"] == "DS2"].copy()
    g = df.groupby("Peptide_ID")
    elis = g["Elispot"].first()

    fig, ax = plt.subplots(figsize=(6.2, 6.0))
    for t, col in TOOL_COLS.items():
        if col not in df.columns:
            continue
        sc = g[col].max()
        m = pd.concat([elis, sc], axis=1)
        m.columns = ["Elispot", "score"]
        m = m.dropna(subset=["Elispot", "score"])
        y = (m["Elispot"].values.astype(float) > 0).astype(int)
        s = m["score"].values.astype(float)
        if len(np.unique(y)) < 2:
            continue
        fpr, tpr, _ = roc_curve(y, s)
        c = NEW_COLOR if t in NEW_TOOLS else OLD_COLOR
        ls = "--" if t in NEW_TOOLS else "-"
        ax.plot(fpr, tpr, lw=1.4, ls=ls, color=c, alpha=0.85, label=t)

    ax.plot([0, 1], [0, 1], ls=":", color="#888", lw=1.2, label="random")
    ax.set_xlim(0, 1); ax.set_ylim(0, 1)
    ax.set_xlabel("False Positive Rate")
    ax.set_ylabel("True Positive Rate")
    ax.set_title("ROC curves — all 8 tools (DS2, max agg, Elispot>0)")
    ax.legend(loc="lower right", fontsize=8)
    save_fig(fig, "fig8_8tools_roc_curves")
    plt.close(fig)


def main():
    metrics = load_metrics_max_gt0()
    fig6_auc_with_ci(metrics)
    fig7_spearman(metrics)
    fig8_roc()
    print("\n=== fig6/7/8 重画完成 (无截断 / 无 pTuneos 基准线 / fig6 叠 95% CI) ===")


if __name__ == "__main__":
    main()
