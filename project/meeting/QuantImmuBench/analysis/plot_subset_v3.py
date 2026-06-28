#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
plot_subset_v3.py
服务: quantimmu-bench — 给 5 工具 / 10 工具 deck 出「全量对齐 v3」的子集图。

为什么重画:
  旧 fig6/7/8_5tools、fig6/8_8tools 等是 HLA 修正前 + 全局池化（所有患者肽混一起算
  一个 Spearman），没计入患者间差异。本脚本照 plot_ppt_figs_v2.py 的算法/样式，按工具
  子集过滤 HLA 修正后的真源 csv 重画，并把「患者内 Fisher-Z」作为定量主图（计入患者差异）。

产出 (analysis/figures/*_v3.{png,pdf})，每个子集 3 张:
  fig_perpatient_fisherz_<label>_v3   ← 定量主图（患者内 Spearman，Fisher-Z 聚合，带95%CI）
  fig_spearman_<label>_v3             ← 全局 Spearman（每工具取 |ρ| 最大聚合，作对照）
  fig_auc_<label>_v3                  ← 判别力 AUC（参考）

数据源 (analysis/，与 17 工具 v3 图同源):
  metrics_ds2_16tools.csv
  per_patient_spearman_16tools.csv

子集:
  5tools  = DeepImmuno PredIG pTuneos IMPROVE NeoTImmuML
  10tools = 上 5 + PRIME ImmuneApp deepHLApan HLAthena（MHLAPre 无数据，不入图）
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.lines import Line2D

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False

HERE    = Path(__file__).resolve().parent
FIG_DIR = HERE / "figures"
FIG_DIR.mkdir(exist_ok=True)

# 第一批 5 工具蓝、扩充 4 工具橙、HLAthena（提呈 proxy）单独灰边——与 deck 叙事一致
FIRST5 = {"DeepImmuno", "PredIG", "pTuneos", "IMPROVE", "NeoTImmuML"}
COLOR_FIRST = "#0072B2"   # 蓝 — 第一批 5 工具
COLOR_EXT   = "#E69F00"   # 橙 — 扩充工具
COLOR_PROXY = "#7F7F7F"   # 灰 — HLAthena 提呈 proxy

SUBSETS = {
    "5tools":  ["DeepImmuno", "PredIG", "pTuneos", "IMPROVE", "NeoTImmuML"],
    "10tools": ["DeepImmuno", "PredIG", "pTuneos", "IMPROVE", "NeoTImmuML",
                "PRIME", "ImmuneApp", "deepHLApan", "HLAthena"],
}


def save_fig(fig, name):
    png = FIG_DIR / f"{name}.png"
    pdf = FIG_DIR / f"{name}.pdf"
    fig.savefig(png, dpi=150, bbox_inches="tight")
    fig.savefig(pdf, bbox_inches="tight")
    try:
        from PIL import Image
        img = Image.open(png); w, h = img.size; img.close()
    except Exception:
        w = round(fig.get_figwidth() * 150); h = round(fig.get_figheight() * 150)
    ratio = w / h
    plt.close(fig)
    print(f"  [saved] {name}  {w}x{h}px  ratio={ratio:.2f}")
    return w, h, ratio


def tool_color(t):
    if t == "HLAthena":
        return COLOR_PROXY
    return COLOR_FIRST if t in FIRST5 else COLOR_EXT


def sig_stars(p):
    if p < 0.001: return "***"
    if p < 0.01:  return "**"
    if p < 0.05:  return "*"
    return ""


def dagger(row):
    return " †" if bool(row.get("reinference_pending", False)) else ""


def hbar_label(ax, i, val, label, pad, fs=8.5, color="#222"):
    if val >= 0:
        ax.text(val + pad, i, label, ha="left",  va="center", fontsize=fs, color=color, zorder=6)
    else:
        ax.text(val - pad, i, label, ha="right", va="center", fontsize=fs, color=color, zorder=6)


def legend_handles(tools):
    h = [mpatches.Patch(color=COLOR_FIRST, label="第一批 5 工具")]
    if any(t not in FIRST5 and t != "HLAthena" for t in tools):
        h.append(mpatches.Patch(color=COLOR_EXT, label="扩充工具"))
    if "HLAthena" in tools:
        h.append(mpatches.Patch(color=COLOR_PROXY, label="HLAthena（提呈 proxy）"))
    return h


# ── 1. 患者内 Fisher-Z（定量主图，计入患者差异）────────────────────────────────
def plot_perpatient(tools, label, nlabel):
    df = pd.read_csv(HERE / "per_patient_spearman_16tools.csv")
    df = df[df["Tool"].isin(tools)].copy()
    df = df.sort_values("fisherz_weighted", ascending=True).reset_index(drop=True)

    n = len(df)
    fig, ax = plt.subplots(figsize=(9, max(6.6, 0.62 * n + 2.4)))
    y  = np.arange(n)
    fz = df["fisherz_weighted"].values.astype(float)
    lo = df["fisherz_ci_lo"].values.astype(float)
    hi = df["fisherz_ci_hi"].values.astype(float)
    colors = [tool_color(t) for t in df["Tool"]]

    ax.barh(y, fz, height=0.62, color=colors, edgecolor="#444",
            linewidth=0.5, alpha=0.88, zorder=3)
    ax.errorbar(fz, y, xerr=[np.maximum(fz - lo, 0.0), np.maximum(hi - fz, 0.0)],
                fmt="none", ecolor="#333", elinewidth=1.2, capsize=4, capthick=1.2, zorder=4)
    ax.axvline(0.0, color="#444", lw=1.4, zorder=5)

    xlim = max(abs(hi).max(), abs(lo).min()) + 0.22
    pad  = xlim * 0.015
    for i, (_, row) in enumerate(df.iterrows()):
        fzv = float(row["fisherz_weighted"])
        edge = float(row["fisherz_ci_hi"]) if fzv >= 0 else float(row["fisherz_ci_lo"])
        hbar_label(ax, i, edge if fzv >= 0 else edge, f"{fzv:+.3f}", pad)

    ax.set_yticks(y)
    ax.set_yticklabels([t + dagger(r) for t, (_, r) in zip(df["Tool"], df.iterrows())], fontsize=9.5)
    ax.set_xlim(-xlim, xlim)
    ax.set_xlabel("Fisher-Z 加权 Spearman（跨患者聚合，带 95% 置信区间）", fontsize=10.5)
    ax.set_title(
        f"{nlabel} 患者内 Spearman 相关性（Fisher-Z 聚合）— DS2 HLA 修正后\n"
        "先在每位患者内部算相关，再跨患者聚合，已计入患者间差异；误差棒为 95% 置信区间",
        fontsize=10.5, pad=8)
    ax.legend(handles=legend_handles(list(df["Tool"])), loc="lower right", fontsize=9)
    ax.text(0.0, -0.06 if n > 5 else -0.10,
            "† 该工具在 P101/P102 未评分（n=86 肽）",
            transform=ax.transAxes, fontsize=8, color="#555")
    ax.grid(axis="x", color="#eee", lw=0.5, zorder=0)
    ax.set_axisbelow(True)
    plt.tight_layout(rect=[0, 0.05, 1, 1])
    return save_fig(fig, f"fig_perpatient_fisherz_{label}_v3")


# ── 2. 全局 Spearman（max 聚合，与主表对照列一致）─────────────────────────────
def plot_spearman_global(tools, label, nlabel):
    df  = pd.read_csv(HERE / "metrics_ds2_16tools.csv", comment="#")
    sub = df[(df["Threshold"] == ">0") & (df["Tool"].isin(tools))].copy()
    best = sub[sub["Aggregation"] == "max"].copy()
    best = best.sort_values("Spearman_rho", ascending=True).reset_index(drop=True)

    n = len(best)
    fig, ax = plt.subplots(figsize=(9, max(6.6, 0.62 * n + 2.4)))
    y   = np.arange(n)
    rho = best["Spearman_rho"].values.astype(float)
    colors = [tool_color(t) for t in best["Tool"]]

    ax.barh(y, rho, height=0.62, color=colors, edgecolor="#444", linewidth=0.5, zorder=3)
    ax.axvline(0.0, color="#444", lw=1.4, zorder=4)

    lim = max(abs(rho)) + 0.34
    pad = lim * 0.013
    for i, (_, row) in enumerate(best.iterrows()):
        rv    = float(row["Spearman_rho"])
        stars = sig_stars(float(row["Spearman_pval"]))
        hbar_label(ax, i, rv, f"{rv:+.3f}{stars}  [max]", pad)

    ax.set_yticks(y)
    ax.set_yticklabels([t + dagger(r) for t, (_, r) in zip(best["Tool"], best.iterrows())], fontsize=9.5)
    ax.set_xlim(-lim, lim)
    ax.set_xlabel("Spearman ρ（肽分数 vs ELISpot，所有患者肽合并的全局口径）", fontsize=10.5)
    ax.set_title(
        f"{nlabel} 全局 Spearman 相关系数 — DS2 HLA 修正后\n"
        "max 聚合（与主表对照列一致）；全局口径不区分患者，仅作对照  |  * p<0.05  ** p<0.01  *** p<0.001",
        fontsize=10.5, pad=8)
    ax.legend(handles=legend_handles(list(best["Tool"])), loc="lower right", fontsize=9)
    ax.text(0.0, -0.06 if n > 5 else -0.10,
            "† 该工具在 P101/P102 未评分（n=86 肽）",
            transform=ax.transAxes, fontsize=8, color="#555")
    ax.grid(axis="x", color="#eee", lw=0.5, zorder=0)
    ax.set_axisbelow(True)
    plt.tight_layout(rect=[0, 0.05, 1, 1])
    return save_fig(fig, f"fig_spearman_{label}_v3")


# ── 3. AUC（判别力，参考）──────────────────────────────────────────────────────
def plot_auc(tools, label, nlabel):
    df   = pd.read_csv(HERE / "metrics_ds2_16tools.csv", comment="#")
    df   = df[df["Tool"].isin(tools)]
    best = df.loc[df.groupby("Tool")["AUC_ROC"].idxmax()].copy()
    best = best.sort_values("AUC_ROC", ascending=True).reset_index(drop=True)

    n = len(best)
    fig, ax = plt.subplots(figsize=(9, max(6.6, 0.62 * n + 2.4)))
    y   = np.arange(n)
    auc = best["AUC_ROC"].values.astype(float)
    colors = [tool_color(t) for t in best["Tool"]]

    ax.barh(y, auc, height=0.62, color=colors, edgecolor="#444", linewidth=0.5, zorder=3)
    ax.axvline(0.5,  color="#888",    lw=1.4, ls="--", zorder=4)
    ax.axvline(0.75, color="#CC6600", lw=1.0, ls=":",  zorder=4)
    ax.text(0.502, n - 0.5, "随机 (0.5)",   fontsize=8, color="#888",    va="top")
    ax.text(0.752, n - 0.5, "参考 (0.75)",  fontsize=8, color="#CC6600", va="top")

    for i, (_, row) in enumerate(best.iterrows()):
        av = float(row["AUC_ROC"])
        ax.text(av + 0.010, i, f"{av:.3f}  [{row['Aggregation']}/{row['Threshold']}]",
                ha="left", va="center", fontsize=8.5, color="#222", zorder=5)

    ax.set_yticks(y)
    ax.set_yticklabels([t + dagger(r) for t, (_, r) in zip(best["Tool"], best.iterrows())], fontsize=9.5)
    ax.set_xlim(0.0, 1.12)
    ax.set_xticks(np.arange(0.0, 1.01, 0.1))
    ax.set_xlabel("AUC-ROC（DS2 HLA 修正后；二分判别力，仅作参考）", fontsize=10.5)
    ax.set_title(
        f"{nlabel} AUC-ROC — DS2 HLA 修正后\n"
        "每工具取最高 AUC 的聚合方式与阈值组合",
        fontsize=10.5, pad=8)
    ax.legend(handles=legend_handles(list(best["Tool"])) + [
        Line2D([0], [0], color="#888",    ls="--", lw=1.4, label="随机 AUC=0.5"),
        Line2D([0], [0], color="#CC6600", ls=":",  lw=1.0, label="参考线 AUC=0.75"),
    ], loc="lower right", fontsize=9)
    ax.text(0.0, -0.06 if n > 5 else -0.10,
            "† 该工具在 P101/P102 未评分（n=86 肽）",
            transform=ax.transAxes, fontsize=8, color="#555")
    ax.grid(axis="x", color="#eee", lw=0.5, zorder=0)
    ax.set_axisbelow(True)
    plt.tight_layout(rect=[0, 0.05, 1, 1])
    return save_fig(fig, f"fig_auc_{label}_v3")


def main():
    print("=== plot_subset_v3.py — 5/10 工具 v3 对齐子集图 ===")
    NLABEL = {"5tools": "第一批 5 工具", "10tools": "10 工具"}
    for label, tools in SUBSETS.items():
        print(f"\n##### 子集 {label}: {tools}")
        plot_perpatient(tools, label, NLABEL[label])
        plot_spearman_global(tools, label, NLABEL[label])
        plot_auc(tools, label, NLABEL[label])
    print("\n[DONE]", FIG_DIR)


if __name__ == "__main__":
    main()
