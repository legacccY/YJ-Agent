#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
plot_ppt_figs_v2.py
服务: quantimmu-bench PPT 重做 — 修两硬伤: ①标签不压柱 ②宽高比 ≤ 1.6

产出 (analysis/figures/*_v2.{png,pdf}):
  fig_spearman_17tools_corrected_v2
  fig_perpatient_fisherz_17tools_v2
  fig_auc_17tools_corrected_v2
  pooling_heatmap_global_17tools_v2
  pooling_max_vs_countsafe_17tools_v2
  pooling_spread_17tools_v2
  spearman_ceiling_squeeze_17tools_v2

数据源 (analysis/):
  metrics_ds2_16tools.csv
  per_patient_spearman_16tools.csv
  pooling_best_per_tool_17tools.csv
  pooling_global_spearman_17tools.csv
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

# ── 中文字体 ──────────────────────────────────────────────────────────────────
plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False

HERE    = Path(__file__).resolve().parent
FIG_DIR = HERE / "figures"
FIG_DIR.mkdir(exist_ok=True)

# ── 颜色方案 (Okabe-Ito accessible) ──────────────────────────────────────────
COLOR_OLD = "#0072B2"   # 蓝 — 原始 8 工具
COLOR_NEW = "#E69F00"   # 橙 — 新增 9 工具
COLOR_DTU = "#CC79A7"   # 粉 — pending DTU consent

OLD_TOOLS  = {"DeepImmuno", "PredIG", "NeoTImmuML", "IMPROVE",
              "pTuneos", "PRIME", "ImmuneApp", "deepHLApan"}
DTU_PENDING = {"netmhcpan_ba", "TSCAPE"}


# ── 工具函数 ──────────────────────────────────────────────────────────────────
def save_fig(fig, name: str):
    """保存 PNG(dpi=150) + PDF，返回 (w, h, ratio)。"""
    png = FIG_DIR / f"{name}.png"
    pdf = FIG_DIR / f"{name}.pdf"
    fig.savefig(png, dpi=150, bbox_inches="tight")
    fig.savefig(pdf, bbox_inches="tight")
    # 读实际像素
    try:
        from PIL import Image
        img = Image.open(png)
        w, h = img.size
        img.close()
    except Exception:
        w = round(fig.get_figwidth() * 150)
        h = round(fig.get_figheight() * 150)
    ratio = w / h
    plt.close(fig)
    print(f"  [saved] {name}  {w}x{h}px  ratio={ratio:.2f}")
    return w, h, ratio


def get_color(tool: str, pending_dtu: bool) -> str:
    if pending_dtu:
        return COLOR_DTU
    return COLOR_OLD if tool in OLD_TOOLS else COLOR_NEW


def sig_stars(p: float) -> str:
    if p < 0.001: return "***"
    if p < 0.01:  return "**"
    if p < 0.05:  return "*"
    return ""


def make_ylabel(row) -> str:
    name = str(row["Tool"])
    suf  = ""
    if bool(row.get("reinference_pending", False)):
        suf += " †"
    if bool(row.get("pending_DTU_consent", False)):
        suf += " ‡"
    return name + suf


def hbar_label(ax, i: int, val: float, label: str,
               pad: float, fs: float = 7.5, color: str = "#222"):
    """在水平条形图中，把标签放在条外侧（不压柱）。"""
    if val >= 0:
        ax.text(val + pad, i, label, ha="left",  va="center",
                fontsize=fs, color=color, zorder=5)
    else:
        ax.text(val - pad, i, label, ha="right", va="center",
                fontsize=fs, color=color, zorder=5)


# ─────────────────────────────────────────────────────────────────────────────
# 1. Spearman 17 工具条形图
# ─────────────────────────────────────────────────────────────────────────────
def plot_spearman_v2():
    df  = pd.read_csv(HERE / "metrics_ds2_16tools.csv", comment="#")
    sub = df[df["Threshold"] == ">0"].copy()
    best = sub[sub["Aggregation"] == "max"].copy()
    best = best.sort_values("Spearman_rho", ascending=True).reset_index(drop=True)

    n      = len(best)
    fig, ax = plt.subplots(figsize=(9, 8))      # ratio 1.125
    y      = np.arange(n)
    rho    = best["Spearman_rho"].values.astype(float)
    colors = [get_color(r["Tool"], bool(r["pending_DTU_consent"]))
              for _, r in best.iterrows()]

    ax.barh(y, rho, height=0.65, color=colors,
            edgecolor="#444", linewidth=0.5, zorder=3)
    ax.axvline(0.0, color="#444", lw=1.4, zorder=4)

    lim = max(abs(rho)) + 0.30
    pad = lim * 0.012
    for i, (_, row) in enumerate(best.iterrows()):
        rv    = float(row["Spearman_rho"])
        stars = sig_stars(float(row["Spearman_pval"]))
        label = f"{rv:+.3f}{stars}  [max]"
        hbar_label(ax, i, rv, label, pad)

    ax.set_yticks(y)
    ax.set_yticklabels([make_ylabel(r) for _, r in best.iterrows()], fontsize=8.5)
    ax.set_xlim(-lim, lim)
    ax.set_xlabel("Spearman ρ（肽分数 vs ELISpot，DS2 HLA修正后）", fontsize=10)
    ax.set_title(
        "17工具 Spearman 相关系数 — DS2 HLA修正后（2026-06-27）\n"
        "max 聚合（与主表对照列一致）  |  * p<0.05  ** p<0.01  *** p<0.001",
        fontsize=10, pad=8)

    ax.legend(handles=[
        mpatches.Patch(color=COLOR_OLD, label="原始8工具"),
        mpatches.Patch(color=COLOR_NEW, label="新增9工具"),
        mpatches.Patch(color=COLOR_DTU, label="DTU同意待获取 (‡)"),
    ], loc="lower right", fontsize=8)
    ax.text(0.0, -0.055,
            "†: P101/P102未评分，n=86肽  ‡: DTU数据使用协议待获取",
            transform=ax.transAxes, fontsize=7, color="#555")
    ax.grid(axis="x", color="#eee", lw=0.5, zorder=0)
    ax.set_axisbelow(True)
    plt.tight_layout(rect=[0, 0.04, 1, 1])
    return save_fig(fig, "fig_spearman_17tools_corrected_v2")


# ─────────────────────────────────────────────────────────────────────────────
# 2. Per-patient Fisher-Z + 95% CI
# ─────────────────────────────────────────────────────────────────────────────
def plot_perpatient_fisherz_v2():
    df  = pd.read_csv(HERE / "per_patient_spearman_16tools.csv")
    df  = df.sort_values("fisherz_weighted", ascending=True).reset_index(drop=True)

    n      = len(df)
    fig, ax = plt.subplots(figsize=(9, 8))      # ratio 1.125
    y      = np.arange(n)
    fz     = df["fisherz_weighted"].values.astype(float)
    lo     = df["fisherz_ci_lo"].values.astype(float)
    hi     = df["fisherz_ci_hi"].values.astype(float)

    colors = []
    for _, row in df.iterrows():
        t = row["Tool"]
        colors.append(COLOR_DTU if t in DTU_PENDING
                      else (COLOR_OLD if t in OLD_TOOLS else COLOR_NEW))

    ax.barh(y, fz, height=0.65, color=colors,
            edgecolor="#444", linewidth=0.5, alpha=0.85, zorder=3)
    # 误差棒（95% CI）
    xerr_lo = np.maximum(fz - lo, 0.0)
    xerr_hi = np.maximum(hi - fz, 0.0)
    ax.errorbar(fz, y, xerr=[xerr_lo, xerr_hi],
                fmt="none", ecolor="#333", elinewidth=1.2,
                capsize=4, capthick=1.2, zorder=4)
    ax.axvline(0.0, color="#444", lw=1.4, zorder=5)

    # 标签放在 CI 外侧
    xlim = max(abs(hi).max(), abs(lo).min()) + 0.20
    pad  = xlim * 0.014
    for i, (_, row) in enumerate(df.iterrows()):
        fzv = float(row["fisherz_weighted"])
        hiv = float(row["fisherz_ci_hi"])
        lov = float(row["fisherz_ci_lo"])
        label = f"{fzv:+.3f}"
        if fzv >= 0:
            ax.text(hiv + pad, i, label, ha="left",  va="center",
                    fontsize=7.5, color="#222", zorder=6)
        else:
            ax.text(lov - pad, i, label, ha="right", va="center",
                    fontsize=7.5, color="#222", zorder=6)

    ylabels = []
    for _, row in df.iterrows():
        t   = row["Tool"]
        suf = " †" if bool(row.get("reinference_pending", False)) else ""
        suf += " ‡" if t in DTU_PENDING else ""
        ylabels.append(t + suf)
    ax.set_yticks(y)
    ax.set_yticklabels(ylabels, fontsize=8.5)
    ax.set_xlim(-xlim, xlim)
    ax.set_xlabel("Fisher-Z 加权 Spearman（跨患者，带95% CI）", fontsize=10)
    ax.set_title(
        "17工具 患者内 Spearman 相关性（Fisher-Z 聚合）\n"
        "误差棒 = 95% 置信区间；纵轴按 Fisher-Z 升序排列",
        fontsize=10, pad=8)
    ax.legend(handles=[
        mpatches.Patch(color=COLOR_OLD, label="原始8工具"),
        mpatches.Patch(color=COLOR_NEW, label="新增9工具"),
        mpatches.Patch(color=COLOR_DTU, label="DTU同意待获取 (‡)"),
    ], loc="lower right", fontsize=8)
    ax.text(0.0, -0.055,
            "† P101/P102未评分（n=86肽）；NeoTImmuML/Repitope为n=101肽",
            transform=ax.transAxes, fontsize=7, color="#555")
    ax.grid(axis="x", color="#eee", lw=0.5, zorder=0)
    ax.set_axisbelow(True)
    plt.tight_layout(rect=[0, 0.04, 1, 1])
    return save_fig(fig, "fig_perpatient_fisherz_17tools_v2")


# ─────────────────────────────────────────────────────────────────────────────
# 3. AUC-ROC 17 工具
# ─────────────────────────────────────────────────────────────────────────────
def plot_auc_v2():
    df   = pd.read_csv(HERE / "metrics_ds2_16tools.csv", comment="#")
    best = df.loc[df.groupby("Tool")["AUC_ROC"].idxmax()].copy()
    best = best.sort_values("AUC_ROC", ascending=True).reset_index(drop=True)

    n      = len(best)
    fig, ax = plt.subplots(figsize=(9, 8))      # ratio 1.125
    y      = np.arange(n)
    auc    = best["AUC_ROC"].values.astype(float)
    colors = [get_color(r["Tool"], bool(r["pending_DTU_consent"]))
              for _, r in best.iterrows()]

    ax.barh(y, auc, height=0.65, color=colors,
            edgecolor="#444", linewidth=0.5, zorder=3)
    ax.axvline(0.5,  color="#888",    lw=1.4, ls="--", zorder=4)
    ax.axvline(0.75, color="#CC6600", lw=1.0, ls=":",  zorder=4)
    ax.text(0.502, n - 0.5, "随机 (0.5)",     fontsize=7.5, color="#888",    va="top")
    ax.text(0.752, n - 0.5, "参考线 (0.75)", fontsize=7.5, color="#CC6600", va="top")

    pad = 0.010
    for i, (_, row) in enumerate(best.iterrows()):
        av    = float(row["AUC_ROC"])
        label = f"{av:.3f}  [{row['Aggregation']}/{row['Threshold']}]"
        ax.text(av + pad, i, label, ha="left", va="center",
                fontsize=7.5, color="#222", zorder=5)

    ax.set_yticks(y)
    ax.set_yticklabels([make_ylabel(r) for _, r in best.iterrows()], fontsize=8.5)
    ax.set_xlim(0.0, 1.12)
    ax.set_xticks(np.arange(0.0, 1.01, 0.1))
    ax.set_xlabel("AUC-ROC（DS2 HLA修正后）", fontsize=10)
    ax.set_title(
        "17工具 AUC-ROC — DS2 HLA修正后（2026-06-27）\n"
        "每工具取最高AUC的聚合方式+阈值组合",
        fontsize=10, pad=8)
    ax.legend(handles=[
        mpatches.Patch(color=COLOR_OLD, label="原始8工具"),
        mpatches.Patch(color=COLOR_NEW, label="新增9工具"),
        mpatches.Patch(color=COLOR_DTU, label="DTU同意待获取 (‡)"),
        Line2D([0],[0], color="#888",    ls="--", lw=1.4, label="随机 AUC=0.5"),
        Line2D([0],[0], color="#CC6600", ls=":",  lw=1.0, label="参考线 AUC=0.75"),
    ], loc="lower right", fontsize=8)
    ax.text(0.0, -0.055,
            "† P101/P102未评分（n=86肽）  ‡ DTU数据使用协议待获取",
            transform=ax.transAxes, fontsize=7, color="#555")
    ax.grid(axis="x", color="#eee", lw=0.5, zorder=0)
    ax.set_axisbelow(True)
    plt.tight_layout(rect=[0, 0.04, 1, 1])
    return save_fig(fig, "fig_auc_17tools_corrected_v2")


# ─────────────────────────────────────────────────────────────────────────────
# 4. Pooling 热图（17 × 8）
# ─────────────────────────────────────────────────────────────────────────────
def plot_pooling_heatmap_v2():
    df = pd.read_csv(HERE / "pooling_global_spearman_17tools.csv")

    POOLING_ORDER = ["max", "mean", "top3mean", "geomean",
                     "softmax", "topk_w", "rankdecay", "sum"]
    cols = [c for c in POOLING_ORDER if c in df["Pooling"].unique()]

    pivot = df.pivot_table(index="Tool", columns="Pooling",
                           values="Spearman_rho", aggfunc="first")
    pivot = pivot.reindex(columns=cols)

    # 排序：按 max rho 降序
    tool_order = pivot.max(axis=1).sort_values(ascending=False).index.tolist()
    pivot = pivot.reindex(index=tool_order)

    # count_confounded mask
    cc = df.pivot_table(index="Tool", columns="Pooling",
                        values="count_confounded", aggfunc="first")
    cc = cc.reindex(index=tool_order, columns=cols).fillna(False).astype(bool)

    n_tools   = len(pivot)
    n_pooling = len(cols)
    fig, ax   = plt.subplots(figsize=(10, 9))   # ratio 1.11

    vmin, vmax = -0.35, 0.45
    im = ax.imshow(pivot.values, aspect="auto", cmap="RdYlGn",
                   vmin=vmin, vmax=vmax, interpolation="nearest")

    for i, tool in enumerate(pivot.index):
        for j, pool in enumerate(cols):
            val = pivot.loc[tool, pool]
            if pd.isna(val):
                continue
            tc = "white" if abs(val) > 0.22 else "black"
            ax.text(j, i, f"{val:.2f}", ha="center", va="center",
                    fontsize=7.2, color=tc, zorder=3)
            if cc.loc[tool, pool]:
                ax.text(j, i, "X", ha="center", va="center",
                        fontsize=14, color="#cc0000", alpha=0.60,
                        fontweight="bold", zorder=4)

    ax.set_xticks(range(n_pooling))
    ax.set_xticklabels(cols, fontsize=9, rotation=30, ha="right")
    ax.set_yticks(range(n_tools))
    ax.set_yticklabels(pivot.index, fontsize=8)

    cb = fig.colorbar(im, ax=ax, fraction=0.025, pad=0.02)
    cb.set_label("Spearman ρ", fontsize=9)

    ax.set_title(
        "聚合方式 × 工具 — 全局 Spearman 热图（DS2，17工具×8聚合）\n"
        "红 X = count-confounded（不纳入主指标，仅参考）",
        fontsize=10, pad=8)
    ax.set_xlabel("聚合方式", fontsize=9)
    ax.set_ylabel("工具", fontsize=9)
    plt.tight_layout()
    return save_fig(fig, "pooling_heatmap_global_17tools_v2")


# ─────────────────────────────────────────────────────────────────────────────
# 5. Max vs Count-safe 最优聚合对比
# ─────────────────────────────────────────────────────────────────────────────
def plot_max_vs_countsafe_v2():
    df = pd.read_csv(HERE / "pooling_best_per_tool_17tools.csv")
    df = df.sort_values("best_rho_countsafe", ascending=True).reset_index(drop=True)

    n      = len(df)
    fig, ax = plt.subplots(figsize=(9, 8))      # ratio 1.125
    y      = np.arange(n)
    bh     = 0.34
    rho_mx = df["rho_max_baseline"].values.astype(float)
    rho_cs = df["best_rho_countsafe"].values.astype(float)

    ax.barh(y - bh/2, rho_mx, height=bh, color="#888888",
            edgecolor="#555", linewidth=0.4, label="max 聚合（基线）", zorder=3)
    ax.barh(y + bh/2, rho_cs, height=bh, color=COLOR_OLD,
            edgecolor="#444", linewidth=0.4, label="最优 count-safe 聚合", zorder=3)
    ax.axvline(0.0, color="#444", lw=1.4, zorder=4)

    xlim = max(abs(rho_mx).max(), abs(rho_cs).max()) + 0.22
    pad  = xlim * 0.013
    for i, (_, row) in enumerate(df.iterrows()):
        rm  = float(row["rho_max_baseline"])
        rc  = float(row["best_rho_countsafe"])
        bp  = row["best_pooling_countsafe"]
        hbar_label(ax, i - bh/2, rm, f"{rm:+.3f}", pad, fs=6.8, color="#555")
        hbar_label(ax, i + bh/2, rc, f"{rc:+.3f} [{bp}]", pad, fs=6.8, color="#222")

    ax.set_yticks(y)
    ax.set_yticklabels(df["Tool"].tolist(), fontsize=8.5)
    ax.set_xlim(-xlim, xlim)
    ax.set_xlabel("Spearman ρ（全局，DS2）", fontsize=10)
    ax.set_title(
        "聚合方式选择影响：max基线 vs 最优count-safe聚合\n"
        "按最优 count-safe ρ 排序（升序）",
        fontsize=10, pad=8)
    ax.legend(loc="lower right", fontsize=8)
    ax.grid(axis="x", color="#eee", lw=0.5, zorder=0)
    ax.set_axisbelow(True)
    plt.tight_layout()
    return save_fig(fig, "pooling_max_vs_countsafe_17tools_v2")


# ─────────────────────────────────────────────────────────────────────────────
# 6. Pooling 敏感度（spread + gain）
# ─────────────────────────────────────────────────────────────────────────────
def plot_spread_v2():
    df = pd.read_csv(HERE / "pooling_best_per_tool_17tools.csv")
    df = df.sort_values("spread", ascending=True).reset_index(drop=True)

    n      = len(df)
    fig, ax = plt.subplots(figsize=(9, 8))      # ratio 1.125
    y      = np.arange(n)
    bh     = 0.34
    spread = df["spread"].values.astype(float)
    delta  = df["delta_countsafe_minus_max"].values.astype(float)

    ax.barh(y - bh/2, spread, height=bh, color="#5599cc",
            edgecolor="#3377aa", linewidth=0.4, alpha=0.85,
            label="ρ range（max−min across 聚合）", zorder=3)
    ax.barh(y + bh/2, delta, height=bh, color="#ee8800",
            edgecolor="#cc6600", linewidth=0.4, alpha=0.85,
            label="Δρ（best count-safe − max 基线）", zorder=3)
    ax.axvline(0.0, color="#444", lw=1.4, zorder=4)

    max_val = max(spread.max(), abs(delta).max()) + 0.18
    pad     = max_val * 0.013
    for i, (_, row) in enumerate(df.iterrows()):
        sp = float(row["spread"])
        dl = float(row["delta_countsafe_minus_max"])
        ax.text(sp + pad, i - bh/2, f"{sp:.3f}", ha="left", va="center",
                fontsize=7, color="#333", zorder=5)
        hbar_label(ax, i + bh/2, dl,
                   (f"+{dl:.3f}" if dl >= 0 else f"{dl:.3f}"),
                   pad, fs=7, color="#884400")

    ax.set_yticks(y)
    ax.set_yticklabels(df["Tool"].tolist(), fontsize=8.5)
    ax.set_xlim(-0.18, max_val + 0.05)
    ax.set_xlabel("Δ Spearman ρ", fontsize=10)
    ax.set_title(
        "聚合方式敏感度：各工具 ρ 范围 + 最优聚合增益\n"
        "按 ρ range（聚合敏感度）升序排列",
        fontsize=10, pad=8)
    ax.legend(loc="lower right", fontsize=8)
    ax.grid(axis="x", color="#eee", lw=0.5, zorder=0)
    ax.set_axisbelow(True)
    plt.tight_layout()
    return save_fig(fig, "pooling_spread_17tools_v2")


# ─────────────────────────────────────────────────────────────────────────────
# 7. 天花板夹逼（Ceiling Squeeze）
# ─────────────────────────────────────────────────────────────────────────────
def plot_ceiling_squeeze_v2():
    df = pd.read_csv(HERE / "pooling_best_per_tool_17tools.csv")
    df = df.dropna(subset=["best_rho_countsafe"]).copy()
    df = df.sort_values("best_rho_countsafe", ascending=False).reset_index(drop=True)

    # 参考数字真源: INTEGRATED_FINDINGS.md §2.3 + fusion_methods.csv
    THEORY_LO   = 0.40
    THEORY_HI   = 0.60
    ZHU_FUSION  = 0.43
    I_FUSION_LO = 0.3281
    I_FUSION_HI = 0.3336
    F_PILOT     = 0.328
    SQUEEZE_LO  = 0.33
    SQUEEZE_HI  = 0.43

    NEW_TOOLS_SET = {
        "BigMHC", "CNNeo", "IEDB_Calis", "MHCflurry_presentation",
        "MHCflurry_affinity_neg", "Repitope", "netmhcpan_ba", "TSCAPE",
    }

    n      = len(df)
    x      = np.arange(n)
    fig, ax = plt.subplots(figsize=(10, 8))     # ratio 1.25

    def bar_color(row):
        t, rho = row["Tool"], row["best_rho_countsafe"]
        if t in DTU_PENDING:
            return "#e68a00"
        if t in NEW_TOOLS_SET:
            return "#1a6faf" if rho >= 0 else "#888888"
        return "#3399cc" if rho >= 0 else "#aaaaaa"

    bar_colors = [bar_color(r) for _, r in df.iterrows()]

    # 背景色带
    ax.axhspan(THEORY_LO, THEORY_HI, color="#dddddd", alpha=0.40, zorder=0)
    ax.axhspan(SQUEEZE_LO, SQUEEZE_HI, color="#fff3cd", alpha=0.60, zorder=0)

    # 参考线
    ax.axhline(ZHU_FUSION,  color="#d04a02", lw=1.8, ls="-",  zorder=3)
    ax.axhline(I_FUSION_LO, color="#2060a8", lw=1.4, ls="--", zorder=3)
    ax.axhline(I_FUSION_HI, color="#2060a8", lw=1.4, ls=":",  zorder=3)
    ax.axhline(0,           color="black",   lw=0.8,           zorder=2)

    # 文字注释（靠右端，不被柱子遮）
    ax.text(n - 0.5, ZHU_FUSION + 0.014,
            f"朱同学融合 ρ={ZHU_FUSION} (p=0.70)",
            ha="right", va="bottom", fontsize=8, color="#d04a02", fontweight="bold")
    ax.text(n - 0.5, I_FUSION_HI + 0.010,
            f"I-fusion {I_FUSION_LO:.3f}–{I_FUSION_HI:.3f}  /  F-pilot {F_PILOT}",
            ha="right", va="bottom", fontsize=8, color="#2060a8", fontweight="bold")
    ax.text(n - 0.5, THEORY_HI - 0.012,
            f"理论天花板（低置信）ρ={THEORY_LO}–{THEORY_HI}",
            ha="right", va="top", fontsize=7.5, color="#888888", style="italic")
    ax.text(n - 0.5, SQUEEZE_LO + 0.005,
            f"信号天花板区 ρ~{SQUEEZE_LO}–{SQUEEZE_HI}",
            ha="right", va="bottom", fontsize=8, color="#9a6b00", fontweight="bold")

    # 条形
    bars = ax.bar(x, df["best_rho_countsafe"], color=bar_colors,
                  width=0.65, alpha=0.88, zorder=2,
                  edgecolor="white", linewidth=0.5)

    # HLAthena 虚线边框
    for i, (_, row) in enumerate(df.iterrows()):
        if row["Tool"] == "HLAthena":
            bars[i].set_linestyle("--")
            bars[i].set_edgecolor("#3399cc")
            bars[i].set_linewidth(1.8)
            bars[i].set_alpha(0.55)

    # 数值标注（柱外，不压柱）
    LABEL_THRESH = 0.15
    LABEL_TOOLS  = {"netmhcpan_ba", "PredIG", "HLAthena", "IMPROVE",
                    "PRIME", "TSCAPE", "MHCflurry_affinity_neg"}
    for i, (_, row) in enumerate(df.iterrows()):
        t   = row["Tool"]
        rho = float(row["best_rho_countsafe"])
        pool = row["best_pooling_countsafe"]
        if abs(rho) < LABEL_THRESH and t not in LABEL_TOOLS:
            continue
        note = f"ρ={rho:.3f}\n[{pool}]"
        fw   = "bold" if abs(rho) >= 0.28 else "normal"
        fc   = "#1a3a6b" if rho >= 0 else "#cc2200"
        if rho >= 0:
            ax.text(i, rho + 0.018, note, ha="center", va="bottom",
                    fontsize=7, color=fc, fontweight=fw, zorder=5)
        else:
            ax.text(i, rho - 0.018, note, ha="center", va="top",
                    fontsize=7, color=fc, fontweight=fw, zorder=5)

    # X 轴标签
    xlabels = []
    for _, row in df.iterrows():
        t = row["Tool"]
        if t == "HLAthena":
            xlabels.append("HLAthena\n(proxy)")
        elif t in NEW_TOOLS_SET:
            xlabels.append(f"{t}*")
        else:
            xlabels.append(t)
    ax.set_xticks(x)
    ax.set_xticklabels(xlabels, fontsize=8, rotation=35, ha="right")

    ymin = min(-0.36, float(df["best_rho_countsafe"].min()) - 0.10)
    ymax = max(0.68, THEORY_HI + 0.10)
    ax.set_ylim(ymin, ymax)
    ax.set_xlim(-0.8, n)
    ax.set_ylabel("Spearman ρ（全局，count-safe最优聚合）", fontsize=10)
    ax.set_title(
        "天花板夹逼 — 17工具 vs 融合基准 & 理论上界\n"
        "四个独立来源汇聚：信号天花板 ρ ~ 0.33–0.43（DS2，101肽，9患者）",
        fontsize=10, pad=8, fontweight="bold")

    ax.legend(handles=[
        mpatches.Patch(color="#3399cc", alpha=0.88, label="原始工具（正向信号）"),
        mpatches.Patch(color="#1a6faf", alpha=0.88, label="新工具*（正向信号）"),
        mpatches.Patch(color="#e68a00", alpha=0.88, label="新工具 [DTU待授权]"),
        mpatches.Patch(color="#aaaaaa", alpha=0.88, label="负/零信号工具"),
        Line2D([0],[0], color="#d04a02", lw=1.8, ls="-",
               label=f"朱同学融合 ρ={ZHU_FUSION} (p=0.70)"),
        Line2D([0],[0], color="#2060a8", lw=1.4, ls="--",
               label=f"I-fusion fixavg ρ={I_FUSION_LO:.4f}"),
        Line2D([0],[0], color="#2060a8", lw=1.4, ls=":",
               label=f"I-fusion rankmean ρ={I_FUSION_HI:.4f}"),
        mpatches.Patch(color="#dddddd", alpha=0.55,
                       label=f"理论天花板（低置信）ρ={THEORY_LO}–{THEORY_HI}"),
        mpatches.Patch(color="#fff3cd", alpha=0.85, edgecolor="#e6a817",
                       label=f"信号天花板区 ρ~{SQUEEZE_LO}–{SQUEEZE_HI}"),
    ], fontsize=7.5, loc="upper right", framealpha=0.92,
       ncol=1, handlelength=1.8)

    fig.text(
        0.01, 0.002,
        "† geomean: min-shift 使 Spearman 不变（排名基准）。"
        "[DTU] pending: netmhcpan_ba/TSCAPE。* 新增工具（17工具波次）。"
        "数源: INTEGRATED_FINDINGS.md §2.3 + pooling_best_per_tool_17tools.csv",
        fontsize=6.5, color="#555", va="bottom", wrap=True)

    plt.tight_layout(rect=[0, 0.05, 1, 1])
    return save_fig(fig, "spearman_ceiling_squeeze_17tools_v2")


# ─────────────────────────────────────────────────────────────────────────────
# 主入口
# ─────────────────────────────────────────────────────────────────────────────
def main():
    print("=== plot_ppt_figs_v2.py — 开始出图 ===\n")
    steps = [
        ("1. Spearman 17工具",      plot_spearman_v2),
        ("2. Per-patient Fisher-Z", plot_perpatient_fisherz_v2),
        ("3. AUC-ROC 17工具",       plot_auc_v2),
        ("4. Pooling 热图 17×8",    plot_pooling_heatmap_v2),
        ("5. Max vs Count-safe",    plot_max_vs_countsafe_v2),
        ("6. Pooling 敏感度",        plot_spread_v2),
        ("7. 天花板夹逼",            plot_ceiling_squeeze_v2),
    ]

    results = {}
    for label, fn in steps:
        print(f"\n--- {label} ---")
        try:
            w, h, r = fn()
            results[label] = (w, h, r)
        except Exception as e:
            print(f"  [ERR] {e}")
            import traceback; traceback.print_exc()

    print("\n" + "=" * 70)
    print(f"{'图名':<30} {'像素':>14} {'ratio':>7}  {'OK?'}")
    print("-" * 70)
    for label, (w, h, r) in results.items():
        flag = "OK" if r <= 1.6 else "TOO WIDE"
        print(f"{label:<30} {w}x{h:>5}px  {r:>5.2f}  {flag}")
    print("=" * 70)
    print(f"\n[DONE] 图输出目录: {FIG_DIR}")


if __name__ == "__main__":
    main()
