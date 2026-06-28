#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pooling_sweep_17tools.py
服务: quantimmu-bench / lever=pooling sweep 扩展 17 工具版（旧 9 + 新 8）

================== 输入 ==================
  scripts/out/merged_all_tools_16tools.xlsx
  （34247 行子肽×HLA 级别；DS2=33922 行；101 个肽；HLA-AUDIT 修复版）

================== 输出 ==================
  analysis/pooling_global_spearman_17tools.csv
    列: Tool, Pooling, n_pep, Spearman_rho, Spearman_pval, pval_note,
        count_confounded, pending_DTU_consent, reinference_pending, hlathena_caveat

  analysis/pooling_best_per_tool_17tools.csv
    列: Tool, rho_max_baseline, best_pooling_countsafe, best_rho_countsafe,
        spread, delta_countsafe_minus_max, best_pooling_all, best_rho_all,
        pending_DTU_consent, reinference_pending, hlathena_caveat

  analysis/figures/pooling_heatmap_global_17tools.{png,pdf}
    17 工具 × 8 pooling Spearman 热图；count_confounded 格打叉

  analysis/figures/pooling_max_vs_countsafe_17tools.{png,pdf}
    max pooling 基准 vs count-safe 最优 Δ 条形；新旧工具分色

  analysis/figures/pooling_spread_17tools.{png,pdf}
    每工具 pooling 敏感度（max−min rho 跨 8 pooling）；新旧工具分色

================== Caveats ==================
  pending_DTU_consent=True : netmhcpan_ba（DTU 禁再分发）/ TSCAPE（CC-BY-NC-ND）
  reinference_pending=True : P101/P102 HLA-dep 工具格为 NaN，待 Phase B 重推理
  hlathena_caveat         : HLAthena=presentation proxy，非免疫原性工具，近随机预期

================== 与旧 9 工具表关系 ==================
  本脚本产出 _17tools 后缀，不覆盖旧 pooling_global_spearman.csv 等。
  旧 9 工具用旧 9tools.xlsx（n_pep 可能略异），本表用 16tools.xlsx（HLA-corrected）。

================== 跑法 ==================
  python analysis/pooling_sweep_17tools.py
  python analysis/pooling_sweep_17tools.py --sensitivity
"""

import sys
import argparse
from pathlib import Path
from functools import partial
from math import erf, sqrt as msqrt

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")  # 非交互后端（Windows 无显示器环境）
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches

# UTF-8 stdout (Windows 必要)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent

# ── 常量 ─────────────────────────────────────────────────────────────────────
PATIENT_COL_CANDIDATES = ["Patient_ID", "Patient", "PatientID", "patient_id",
                           "Subject", "Sample_ID"]
MIN_PEP_DEFAULT = 3
FISHER_CLIP     = 0.9999
FISHER_MIN_N    = 3
ALL_PATIENTS    = [101, 102, 104, 105, 106, 107, 108, 109, 110]

# count 混杂判定阈值（同旧脚本）
COUNT_CONFOUND_THRESH = 0.5

# 非工具 MT_* 列
EXCLUDE = {"MT_FullPeptide", "MT_Subpeptide", "MT_NOAH", "MT_NetCleave",
           "MT_Stab_peptide", "MT_TCR_contact"}

# ── 旧 9 工具集（用于图中分色）─────────────────────────────────────────────
OLD_TOOLS = {
    "DeepImmuno", "PredIG", "IMPROVE", "NeoTImmuML", "pTuneos",
    "PRIME", "ImmuneApp", "deepHLApan", "HLAthena",
}
# 新 8 工具（含 netmhcpan_ba / TSCAPE）
NEW_TOOLS = {
    "BigMHC", "CNNeo", "IEDB_Calis", "MHCflurry_presentation",
    "MHCflurry_affinity_neg", "Repitope", "netmhcpan_ba", "TSCAPE",
}

# ── DTU / 许可证状态（17 工具全量）─────────────────────────────────────────
# True = 发表/分发前需取得书面许可（当前无）
PENDING_DTU = {
    # 旧 9 工具
    "DeepImmuno":            False,
    "PredIG":                False,
    "IMPROVE":               False,
    "NeoTImmuML":            False,
    "pTuneos":               False,
    "PRIME":                 False,   # 学术免费已 clone
    "ImmuneApp":             False,
    "deepHLApan":            False,
    "HLAthena":              False,
    # 新 8 工具
    "BigMHC":                False,
    "CNNeo":                 False,
    "IEDB_Calis":            False,
    "MHCflurry_presentation": False,
    "MHCflurry_affinity_neg": False,
    "Repitope":              False,
    "netmhcpan_ba":          True,    # DTU 禁再分发，未取得同意
    "TSCAPE":                True,    # CC-BY-NC-ND，商业禁用
}

# ── reinference_pending（P101/P102 HLA-dep 工具 NaN，需 Phase B 重推）─────
# 来源: analysis/metrics_ds2_16tools.csv 第 4 列 reinference_pending
REINFERENCE_PENDING = {
    # 旧 9 工具（P101/P102 依赖 HLA，均 pending）
    "DeepImmuno":            True,
    "PredIG":                True,
    "IMPROVE":               True,
    "NeoTImmuML":            False,   # 全患者有值
    "pTuneos":               True,
    "PRIME":                 True,
    "ImmuneApp":             True,
    "deepHLApan":            True,
    "HLAthena":              True,
    # 新 8 工具
    "BigMHC":                True,
    "CNNeo":                 True,
    "IEDB_Calis":            True,
    "MHCflurry_presentation": True,
    "MHCflurry_affinity_neg": True,
    "Repitope":              False,   # 全患者有值
    "netmhcpan_ba":          True,
    "TSCAPE":                True,
}


# ── 纯 numpy Spearman（禁 scipy 防 OMP#15）───────────────────────────────────
def spearman_np(x, y):
    x = np.asarray(x, float)
    y = np.asarray(y, float)
    m = ~(np.isnan(x) | np.isnan(y))
    x, y = x[m], y[m]
    n = len(x)
    if n < 3 or len(np.unique(x)) < 2 or len(np.unique(y)) < 2:
        return np.nan
    rx = pd.Series(x).rank().values
    ry = pd.Series(y).rank().values
    rx -= rx.mean()
    ry -= ry.mean()
    denom = np.sqrt((rx ** 2).sum() * (ry ** 2).sum())
    if denom == 0:
        return np.nan
    return float((rx * ry).sum() / denom)


def spearman_pval_approx(rho, n):
    """正态近似双尾 p 值（n>20 时合理；禁 scipy）。"""
    if np.isnan(rho) or n < 4:
        return np.nan
    rho2 = min(rho ** 2, 1.0 - 1e-15)
    t_stat = rho * msqrt((n - 2) / max(1.0 - rho2, 1e-15))
    p_one = 0.5 * (1.0 - erf(abs(t_stat) / msqrt(2.0)))
    return float(2.0 * p_one)


# ── Pooling 内部辅助 ──────────────────────────────────────────────────────────
def _sort_desc(arr):
    arr = np.asarray(arr, float)
    arr = arr[~np.isnan(arr)]
    if len(arr) == 0:
        return arr
    return np.sort(arr)[::-1].copy()


# ── 8 种 Pooling 算子（数学定义见 pooling_sweep.py 注释，此处直接复用）────────
def pool_max(arr):
    s = _sort_desc(arr)
    return float(s[0]) if len(s) else np.nan


def pool_mean(arr):
    s = _sort_desc(arr)
    return float(s.mean()) if len(s) else np.nan


def pool_top3mean(arr, k=3):
    s = _sort_desc(arr)
    return float(s[:min(k, len(s))].mean()) if len(s) else np.nan


def pool_sum(arr):
    """⚠ count 混杂: sum≈n_subpep，近似测肽长而非免疫原性。"""
    s = _sort_desc(arr)
    return float(s.sum()) if len(s) else np.nan


def pool_geomean(arr, eps=1e-9):
    s = _sort_desc(arr)
    if len(s) == 0:
        return np.nan
    if s[-1] <= 0:
        s = s - s[-1] + eps
    return float(np.exp(np.mean(np.log(np.maximum(s, eps)))))


def pool_softmax(arr, T=1.0):
    s = _sort_desc(arr)
    if len(s) == 0:
        return np.nan
    logits  = s / T
    logits -= logits.max()
    w  = np.exp(logits)
    w /= w.sum()
    return float((w * s).sum())


def pool_topk_w(arr, k=5, weight_scheme="inv_rank"):
    s = _sort_desc(arr)
    if len(s) == 0:
        return np.nan
    top = s[:min(k, len(s))]
    m   = len(top)
    ranks = np.arange(1, m + 1, dtype=float)
    if weight_scheme == "inv_rank":
        w = 1.0 / ranks
    elif weight_scheme == "linear":
        w = (m + 1.0 - ranks)
    elif weight_scheme == "equal":
        w = np.ones(m, dtype=float)
    else:
        raise ValueError(f"未知 weight_scheme: {weight_scheme!r}")
    w_sum = w.sum()
    return float((w * top).sum() / w_sum) if w_sum else np.nan


def pool_rankdecay(arr, d=0.5):
    s = _sort_desc(arr)
    if len(s) == 0:
        return np.nan
    n    = len(s)
    exps = np.arange(n, dtype=float)
    w    = d ** exps
    w_sum = w.sum()
    return float((w * s).sum() / w_sum) if w_sum else np.nan


# ── 主 8 种 Pooling 字典 ─────────────────────────────────────────────────────
POOLINGS = {
    "max":       pool_max,
    "mean":      pool_mean,
    "top3mean":  pool_top3mean,
    "sum":       pool_sum,
    "geomean":   pool_geomean,
    "softmax":   partial(pool_softmax,   T=1.0),
    "topk_w":    partial(pool_topk_w,    k=5, weight_scheme="inv_rank"),
    "rankdecay": partial(pool_rankdecay, d=0.5),
}

# ── 敏感性扩展（--sensitivity 时用）────────────────────────────────────────
POOLINGS_SENSITIVITY = dict(POOLINGS)
for _T in [0.1, 10.0]:
    POOLINGS_SENSITIVITY[f"softmax_T{_T}"] = partial(pool_softmax, T=_T)
for _k in [3, 10]:
    POOLINGS_SENSITIVITY[f"topk_w_k{_k}"] = partial(pool_topk_w,
                                                      k=_k,
                                                      weight_scheme="inv_rank")
for _d in [0.3, 0.8]:
    POOLINGS_SENSITIVITY[f"rankdecay_d{_d}"] = partial(pool_rankdecay, d=_d)


# ── 工具函数 ──────────────────────────────────────────────────────────────────
def col_to_toolname(col):
    """MT_列名 -> 工具短名; IMPROVE 特例（列名=MT_IMPROVE_mean_prediction_rf）。"""
    name = col[3:]
    if name.startswith("IMPROVE"):
        return "IMPROVE"
    return name


def find_patient_col(df):
    for c in PATIENT_COL_CANDIDATES:
        if c in df.columns:
            return c
    return None


def patient_from_peptide_id(pid):
    if not isinstance(pid, str):
        return None
    parts = pid.split("-")
    return parts[1] if len(parts) >= 3 else None


def _r4(v):
    if v is None:
        return np.nan
    try:
        f = float(v)
        return np.nan if np.isnan(f) else round(f, 4)
    except (TypeError, ValueError):
        return np.nan


def compute_peptide_scores(ds2, mt_col, pooling_func):
    """子肽行 → 肽级分数 Series（groupby Peptide_ID，round(8) 消浮点 tie）。"""
    valid = ds2[ds2[mt_col].notna()][["Peptide_ID", mt_col]].copy()
    if valid.empty:
        return pd.Series(dtype=float)
    scores = (
        valid.groupby("Peptide_ID")[mt_col]
             .agg(lambda grp: pooling_func(grp.values))
             .rename("peptide_score")
    )
    return scores.round(8)


# ── 图 1: 17×8 Spearman 热图 ─────────────────────────────────────────────────
def plot_heatmap(global_df, confound_lookup, out_prefix, pooling_order):
    """
    17 工具 × 8 pooling Spearman rho 热图。
    count_confounded 格打 'X' 标记。
    工具顺序: 按 max pooling rho 降序。
    """
    main = global_df[global_df["Pooling"].isin(POOLINGS.keys())].copy()

    # 透视：行=Tool，列=Pooling
    pivot = main.pivot(index="Tool", columns="Pooling", values="Spearman_rho")
    # 按 max pooling rho 降序排工具
    if "max" in pivot.columns:
        tool_order = pivot["max"].sort_values(ascending=False).index.tolist()
    else:
        tool_order = pivot.index.tolist()
    pivot = pivot.loc[tool_order, pooling_order]

    # confound 矩阵（True/False）
    confound_pivot = main.pivot(index="Tool", columns="Pooling", values="count_confounded")
    confound_pivot = confound_pivot.loc[tool_order, pooling_order]

    n_tools, n_pool = pivot.shape
    fig_h = max(6, 0.55 * n_tools + 2.5)
    fig_w = max(10, 0.9 * n_pool + 4)
    fig, ax = plt.subplots(figsize=(fig_w, fig_h))

    # 对称色阶
    vmax = max(0.45, float(pivot.abs().max().max()))
    vmin = -vmax

    im = ax.imshow(pivot.values.astype(float), cmap="RdBu_r",
                   vmin=vmin, vmax=vmax, aspect="auto")

    # 标注数值
    for i, tool in enumerate(tool_order):
        for j, pool in enumerate(pooling_order):
            val = pivot.loc[tool, pool]
            is_conf = bool(confound_pivot.loc[tool, pool]) if pool in confound_pivot.columns else False
            txt_col = "white" if abs(val) > 0.25 else "black"
            if not np.isnan(val):
                ax.text(j, i, f"{val:.2f}", ha="center", va="center",
                        fontsize=8.5, color=txt_col, fontweight="bold" if is_conf else "normal")
            if is_conf:
                # 打叉
                ax.plot([j - 0.45, j + 0.45], [i - 0.45, i + 0.45],
                        color="black", lw=1.5, alpha=0.7)
                ax.plot([j + 0.45, j - 0.45], [i - 0.45, i + 0.45],
                        color="black", lw=1.5, alpha=0.7)

    # 轴标签
    ax.set_xticks(range(n_pool))
    ax.set_xticklabels(pooling_order, fontsize=10, rotation=30, ha="right")
    ax.set_yticks(range(n_tools))

    # 工具标签：新工具加 * 标记
    ylabels = []
    for t in tool_order:
        if t in NEW_TOOLS:
            ylabels.append(f"{t}*")
        elif t == "HLAthena":
            ylabels.append("HLAthena (proxy)")
        else:
            ylabels.append(t)
    ax.set_yticklabels(ylabels, fontsize=9)

    # colorbar
    cbar = fig.colorbar(im, ax=ax, fraction=0.03, pad=0.02)
    cbar.set_label("Spearman rho", fontsize=9)

    ax.set_title(
        "Global Spearman rho: Neoantigen-level Pooling vs ELISpot Immunogenicity\n"
        "(✗ = count-confounded, score driven by peptide length not signal)",
        fontsize=11, pad=10
    )

    # 图例
    new_patch = mpatches.Patch(facecolor="none", edgecolor="steelblue",
                                linestyle="--", label="* new tool (16tools xlsx)")
    cross_line = plt.Line2D([0], [0], color="black", lw=1.5, label="count-confounded (✗)")
    ax.legend(handles=[new_patch, cross_line], loc="upper right",
              fontsize=8, framealpha=0.85)

    fig.text(0.01, 0.01,
             "* new tools added in 17-tool wave. geomean: min-shift applied.",
             fontsize=7, color="gray")

    plt.tight_layout(rect=[0, 0.03, 1, 1])
    for ext in ["png", "pdf"]:
        p = HERE / "figures" / f"{out_prefix}.{ext}"
        fig.savefig(p, dpi=150, bbox_inches="tight")
        print(f"[saved] {p}")
    plt.close(fig)


# ── 图 2: max vs count-safe 最优条形 ─────────────────────────────────────────
def plot_max_vs_countsafe(best_df, out_prefix):
    """
    每工具: max pooling 基准 vs count-safe 最优 pooling Spearman rho。
    Δ = best_rho_countsafe - rho_max_baseline 标注在 count-safe 条上。
    新旧工具分色。
    """
    df = best_df.sort_values("rho_max_baseline", ascending=False).copy()
    n  = len(df)
    x  = np.arange(n)
    w  = 0.35

    fig, ax = plt.subplots(figsize=(max(12, n * 0.8 + 2), 6))

    for i, row in enumerate(df.itertuples()):
        tool      = row.Tool
        rho_max   = row.rho_max_baseline if not np.isnan(row.rho_max_baseline) else 0.0
        rho_safe  = row.best_rho_countsafe if not np.isnan(row.best_rho_countsafe) else 0.0
        delta     = row.delta_countsafe_minus_max

        is_new = (tool in NEW_TOOLS)
        col_max  = "#aaaaaa"
        col_safe = "#1a6faf" if is_new else "#3399cc"
        if rho_safe < 0:
            col_safe = "#cc3333"

        ax.bar(i - w / 2, rho_max,  width=w, color=col_max,  alpha=0.8, zorder=2)
        ax.bar(i + w / 2, rho_safe, width=w, color=col_safe, alpha=0.85, zorder=2)

        # Δ 标注
        if not np.isnan(delta):
            y_pos = max(rho_max, rho_safe) + 0.012
            delta_str = f"+{delta:.2f}" if delta >= 0 else f"{delta:.2f}"
            safe_pool = row.best_pooling_countsafe if not isinstance(row.best_pooling_countsafe, float) else "n/a"
            ax.text(i + w / 2, y_pos, f"{delta_str}\n{safe_pool}",
                    ha="center", va="bottom", fontsize=7.5,
                    color="#1a6faf" if delta > 0 else "#cc3333", fontweight="bold")

    ax.axhline(0, color="black", lw=0.8)
    ax.set_xticks(x)
    xlabels = []
    for t in df["Tool"].tolist():
        if t == "HLAthena":
            xlabels.append("HLAthena\n(proxy)")
        elif t in NEW_TOOLS:
            xlabels.append(f"{t}*")
        else:
            xlabels.append(t)
    ax.set_xticklabels(xlabels, fontsize=9, rotation=30, ha="right")
    ax.set_ylabel("Spearman rho vs ELISpot", fontsize=10)
    ax.set_title(
        "max pooling (baseline) vs Count-Safe Best Pooling, per Tool — 17 Tools\n"
        "Blue = uplift over max  |  Red = no signal after removing confounders",
        fontsize=11
    )

    # 图例
    p_max  = mpatches.Patch(color="#aaaaaa", alpha=0.8, label="max pooling (baseline)")
    p_new  = mpatches.Patch(color="#1a6faf", alpha=0.85, label="count-safe best (new tool*)")
    p_old  = mpatches.Patch(color="#3399cc", alpha=0.85, label="count-safe best (old tool)")
    p_neg  = mpatches.Patch(color="#cc3333", alpha=0.85, label="count-safe best (negative)")
    ax.legend(handles=[p_max, p_old, p_new, p_neg], fontsize=8, loc="upper right")

    fig.text(0.01, 0.01,
             "* new tools in 17-tool wave. Δ = count-safe best rho − max rho.",
             fontsize=7.5, color="gray")

    plt.tight_layout(rect=[0, 0.04, 1, 1])
    for ext in ["png", "pdf"]:
        p = HERE / "figures" / f"{out_prefix}.{ext}"
        fig.savefig(p, dpi=150, bbox_inches="tight")
        print(f"[saved] {p}")
    plt.close(fig)


# ── 图 3: pooling spread 条形 ─────────────────────────────────────────────────
def plot_spread(best_df, out_prefix):
    """
    每工具 pooling 敏感度: spread = max_rho_8poolings - min_rho_8poolings。
    新旧工具分色。
    """
    df = best_df.sort_values("spread", ascending=False).copy()
    n  = len(df)
    x  = np.arange(n)

    fig, ax = plt.subplots(figsize=(max(12, n * 0.75 + 2), 5))

    colors = []
    for t in df["Tool"]:
        colors.append("#1a6faf" if t in NEW_TOOLS else "#3399cc")

    bars = ax.bar(x, df["spread"].fillna(0), color=colors, alpha=0.85, zorder=2)

    # 数值标注
    for bar, val in zip(bars, df["spread"].fillna(0)):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.005,
                f"{val:.2f}", ha="center", va="bottom", fontsize=8)

    ax.set_xticks(x)
    xlabels = []
    for t in df["Tool"].tolist():
        if t == "HLAthena":
            xlabels.append("HLAthena\n(proxy)")
        elif t in NEW_TOOLS:
            xlabels.append(f"{t}*")
        else:
            xlabels.append(t)
    ax.set_xticklabels(xlabels, fontsize=9, rotation=30, ha="right")
    ax.set_ylabel("Spread (max − min rho across 8 poolings)", fontsize=10)
    ax.set_title(
        "Pooling Sensitivity per Tool — 17 Tools\n"
        "Higher spread = more sensitive to pooling choice",
        fontsize=11
    )

    p_new = mpatches.Patch(color="#1a6faf", alpha=0.85, label="new tool*")
    p_old = mpatches.Patch(color="#3399cc", alpha=0.85, label="old tool")
    ax.legend(handles=[p_old, p_new], fontsize=9, loc="upper right")

    fig.text(0.01, 0.01,
             "* new tools in 17-tool wave. Spread across main 8 poolings (excl. sensitivity variants).",
             fontsize=7.5, color="gray")

    plt.tight_layout(rect=[0, 0.04, 1, 1])
    for ext in ["png", "pdf"]:
        p = HERE / "figures" / f"{out_prefix}.{ext}"
        fig.savefig(p, dpi=150, bbox_inches="tight")
        print(f"[saved] {p}")
    plt.close(fig)


# ── 主函数 ────────────────────────────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser(
        description="pooling_sweep_17tools: 8 pooling × 17 工具 DS2 Spearman 扫描"
    )
    ap.add_argument("--input", default=None,
                    help="合并表路径（默认 scripts/out/merged_all_tools_16tools.xlsx）")
    ap.add_argument("--min_pep", type=int, default=MIN_PEP_DEFAULT,
                    help=f"患者内 Spearman 最少肽数（默认 {MIN_PEP_DEFAULT}）")
    ap.add_argument("--sensitivity", action="store_true",
                    help="同时运行 softmax/topk/rankdecay 参数扩展版（14 种 pooling）")
    args = ap.parse_args()

    poolings_to_run = POOLINGS_SENSITIVITY if args.sensitivity else POOLINGS
    print(f"[info] pooling 数量: {len(poolings_to_run)}  sensitivity={args.sensitivity}")
    print(f"[info] min_pep={args.min_pep}")

    # ── 读输入 ────────────────────────────────────────────────────────────────
    if args.input is not None:
        xlsx_path = Path(args.input)
        if not xlsx_path.is_absolute():
            xlsx_path = ROOT / xlsx_path
    else:
        xlsx_path = ROOT / "scripts" / "out" / "merged_all_tools_16tools.xlsx"

    if not xlsx_path.exists():
        raise SystemExit(f"[ERR] 输入文件不存在: {xlsx_path}")

    print(f"[info] 输入: {xlsx_path}")
    df = pd.read_excel(xlsx_path)
    print(f"[info] 总行数: {len(df)}  列数: {len(df.columns)}")

    if "Dataset" not in df.columns:
        raise SystemExit("[ERR] 缺 'Dataset' 列")
    ds2 = df[df["Dataset"] == "DS2"].copy()
    print(f"[info] DS2 行数: {len(ds2)}")
    if ds2.empty:
        raise SystemExit("[ERR] DS2 子集为空")

    for req in ["Elispot", "Peptide_ID"]:
        if req not in ds2.columns:
            raise SystemExit(f"[ERR] 缺必需列 '{req}'")

    # ── 患者 ID ───────────────────────────────────────────────────────────────
    pcol = find_patient_col(ds2)
    if pcol is None:
        print(f"[warn] 未找到患者列（试过 {PATIENT_COL_CANDIDATES}），从 Peptide_ID 反解")
    else:
        print(f"[info] 患者列 = '{pcol}'")

    def get_patient(row):
        if pcol is not None and pd.notna(row[pcol]):
            return str(int(row[pcol])) if str(row[pcol]).replace(".0", "").isdigit() else str(row[pcol])
        return patient_from_peptide_id(row["Peptide_ID"])

    ds2 = ds2.copy()
    ds2["_patient"] = ds2.apply(get_patient, axis=1)
    before = len(ds2)
    ds2 = ds2.dropna(subset=["_patient"])
    if len(ds2) < before:
        print(f"[warn] {before - len(ds2)} 行无法解析患者 ID，已丢弃")

    patients_in_data = sorted(ds2["_patient"].unique(),
                               key=lambda x: int(x) if str(x).isdigit() else 0)
    print(f"[info] DS2 患者 ({len(patients_in_data)}): {patients_in_data}")

    # ── 工具列自动检测 ────────────────────────────────────────────────────────
    mt_cols = []
    for c in ds2.columns:
        if not c.startswith("MT_") or c in EXCLUDE:
            continue
        ds2[c] = pd.to_numeric(ds2[c], errors="coerce")
        if ds2[c].notna().any():
            mt_cols.append(c)
    if not mt_cols:
        raise SystemExit("[ERR] 未找到有效数值 MT_* 工具列")
    tools = {col_to_toolname(c): c for c in mt_cols}
    print(f"[info] 检测到 {len(tools)} 个工具: {sorted(tools.keys())}")

    # ── 肽级元信息（Peptide_ID→患者+Elispot）────────────────────────────────
    pep_info = (
        ds2.drop_duplicates("Peptide_ID")
           [["Peptide_ID", "_patient", "Elispot"]]
           .set_index("Peptide_ID")
    )
    n_pep_total = len(pep_info)
    print(f"[info] 肽数: {n_pep_total}")

    # ── 扫描主循环 ────────────────────────────────────────────────────────────
    global_rows   = []
    confound_rows = []
    confound_lookup: dict = {}

    n_total = len(tools) * len(poolings_to_run)
    print(f"\n[info] 扫描矩阵: {len(tools)} 工具 × {len(poolings_to_run)} pooling = {n_total} 组合")
    print("=" * 80)

    for tool_name, mt_col in sorted(tools.items()):
        is_hlathena     = (tool_name == "HLAthena")
        pending_dtu     = PENDING_DTU.get(tool_name, False)
        reinf_pending   = REINFERENCE_PENDING.get(tool_name, False)

        _valid_for_count = ds2[ds2[mt_col].notna()]
        n_subpep_series  = _valid_for_count.groupby("Peptide_ID").size().rename("n_subpep")

        for pool_name, pool_func in poolings_to_run.items():
            pep_scores = compute_peptide_scores(ds2, mt_col, pool_func)
            if pep_scores.empty:
                continue

            pep_df = (
                pep_scores.to_frame()
                          .join(pep_info[["_patient", "Elispot"]], how="inner")
                          .dropna(subset=["Elispot", "peptide_score"])
            )
            if pep_df.empty:
                continue

            n_pep = len(pep_df)

            # count 混杂诊断
            n_subpep_aligned = n_subpep_series.reindex(pep_df.index)
            rho_confound  = spearman_np(pep_df["peptide_score"].values,
                                        n_subpep_aligned.values)
            is_confounded = (abs(rho_confound) > COUNT_CONFOUND_THRESH
                             if not np.isnan(rho_confound) else False)
            confound_lookup[(tool_name, pool_name)] = is_confounded
            confound_rows.append({
                "Tool":                  tool_name,
                "Pooling":               pool_name,
                "rho_pooled_vs_nsubpep": _r4(rho_confound),
                "n_pep":                 n_pep,
            })

            # 全局 Spearman
            rho_global  = spearman_np(pep_df["peptide_score"].values,
                                      pep_df["Elispot"].values)
            pval_global = spearman_pval_approx(rho_global, n_pep)

            global_rows.append({
                "Tool":                 tool_name,
                "Pooling":              pool_name,
                "n_pep":                n_pep,
                "Spearman_rho":         _r4(rho_global),
                "Spearman_pval":        _r4(pval_global),
                "pval_note":            "normal_approx_t",
                "count_confounded":     is_confounded,
                "pending_DTU_consent":  pending_dtu,
                "reinference_pending":  reinf_pending,
                "hlathena_caveat":      is_hlathena,
            })

        print(f"  [done] {tool_name}  poolings={len(poolings_to_run)}")

    if not global_rows:
        raise SystemExit("[ERR] 无有效结果，CSV 未写出")

    # ── 写出 pooling_global_spearman_17tools.csv ──────────────────────────────
    global_df = pd.DataFrame(global_rows)
    out_a = HERE / "pooling_global_spearman_17tools.csv"
    global_df.to_csv(out_a, index=False, encoding="utf-8")
    print(f"\n[saved] {out_a}  shape={global_df.shape}")

    # ── 写出 pooling_count_confound_17tools.csv ───────────────────────────────
    confound_df = pd.DataFrame(confound_rows)
    out_d = HERE / "pooling_count_confound_17tools.csv"
    with open(out_d, "w", encoding="utf-8") as _f:
        _f.write(
            "# count-confound diagnostic: |rho(pooled_score, n_subpep)| > 0.5 => count_confounded=True;"
            " sum ~0.75 (must True); 参考 n_subpep↔Elispot≈0.16, Peptide_Length↔Elispot≈0.31\n"
        )
        confound_df.to_csv(_f, index=False)
    print(f"[saved] {out_d}  shape={confound_df.shape}")

    # ── 写出 pooling_best_per_tool_17tools.csv ───────────────────────────────
    # 只用主 8 种 pooling
    main_global = global_df[global_df["Pooling"].isin(POOLINGS.keys())].copy()
    best_rows   = []

    for tool_name in sorted(main_global["Tool"].unique()):
        tool_df = main_global[main_global["Tool"] == tool_name].dropna(subset=["Spearman_rho"])
        if tool_df.empty:
            continue

        # max pooling 算子作基准（对账 metrics_ds2_16tools.csv Aggregation=max）
        max_row        = tool_df[tool_df["Pooling"] == "max"]
        rho_max_base   = float(max_row["Spearman_rho"].iloc[0]) if not max_row.empty else np.nan

        # 所有 8 种中最优（含混杂）
        best_idx  = tool_df["Spearman_rho"].idxmax()
        best_row  = tool_df.loc[best_idx]
        best_pool = best_row["Pooling"]
        best_rho  = float(best_row["Spearman_rho"])

        # spread = max_rho - min_rho（8 种 pooling 范围）
        spread = float(tool_df["Spearman_rho"].max() - tool_df["Spearman_rho"].min())

        # count-safe 最优（排除 count_confounded=True 的 pooling）
        safe_df = tool_df[
            tool_df["Pooling"].map(lambda p: not confound_lookup.get((tool_name, p), False))
        ].dropna(subset=["Spearman_rho"])

        if not safe_df.empty:
            safe_idx       = safe_df["Spearman_rho"].idxmax()
            best_safe_pool = safe_df.loc[safe_idx, "Pooling"]
            best_safe_rho  = float(safe_df.loc[safe_idx, "Spearman_rho"])
            delta_safe     = (best_safe_rho - rho_max_base) if not np.isnan(rho_max_base) else np.nan
        else:
            best_safe_pool = np.nan
            best_safe_rho  = np.nan
            delta_safe     = np.nan

        best_rows.append({
            "Tool":                      tool_name,
            "rho_max_baseline":          _r4(rho_max_base),
            "best_pooling_countsafe":    best_safe_pool,
            "best_rho_countsafe":        _r4(best_safe_rho),
            "spread":                    _r4(spread),
            "delta_countsafe_minus_max": _r4(delta_safe),
            "best_pooling_all":          best_pool,
            "best_rho_all":              _r4(best_rho),
            "pending_DTU_consent":       PENDING_DTU.get(tool_name, False),
            "reinference_pending":       REINFERENCE_PENDING.get(tool_name, False),
            "hlathena_caveat":           (tool_name == "HLAthena"),
        })

    best_df = pd.DataFrame(best_rows)
    out_c = HERE / "pooling_best_per_tool_17tools.csv"
    best_df.to_csv(out_c, index=False, encoding="utf-8")
    print(f"[saved] {out_c}  shape={best_df.shape}")

    # ── 对账打印（max pooling vs metrics_ds2_16tools.csv）────────────────────
    print("\n[对账] max pooling rho（应与 metrics_ds2_16tools.csv Aggregation=max Spearman_rho 一致）:")
    check = (
        main_global[main_global["Pooling"] == "max"]
        [["Tool", "n_pep", "Spearman_rho"]]
        .sort_values("Tool")
    )
    print(check.to_string(index=False))

    # ── figures 目录 ──────────────────────────────────────────────────────────
    fig_dir = HERE / "figures"
    fig_dir.mkdir(exist_ok=True)

    pooling_order = list(POOLINGS.keys())   # ['max','mean','top3mean','sum','geomean','softmax','topk_w','rankdecay']

    print("\n[图 1] 生成 pooling_heatmap_global_17tools ...")
    plot_heatmap(global_df, confound_lookup, "pooling_heatmap_global_17tools", pooling_order)

    print("[图 2] 生成 pooling_max_vs_countsafe_17tools ...")
    plot_max_vs_countsafe(best_df, "pooling_max_vs_countsafe_17tools")

    print("[图 3] 生成 pooling_spread_17tools ...")
    plot_spread(best_df, "pooling_spread_17tools")

    # ── 统计注 ────────────────────────────────────────────────────────────────
    print("\n[STATISTICAL NOTES]")
    print("  1. Spearman_pval 正态近似（n=101 DS2 肽时可接受）；精确值需 scipy.t（OMP#15 禁用）。")
    print("  2. 8 种 pooling 多重比较未校正；最优 pooling 带过拟合风险，建议独立集验证。")
    print("  3. geomean 平移保证全正（min-shift），Spearman（秩）不受绝对值影响。")
    print("  4. TSCAPE pending_DTU_consent=True (CC-BY-NC-ND)；netmhcpan_ba 同（DTU 禁再分发）。")
    print("  5. reinference_pending=True 工具 P101/P102 为 NaN，待 Phase B 重推后数字可能变化。")
    print("  6. n_pep < 101 的工具 = HLA-dep 工具 P101/P102 格 NaN 后只剩其余 9 患者肽（n≈86）。")
    print(f"\n[DONE] pooling_sweep_17tools 完成，产出 _17tools 系列 CSV + 3 张图。")


if __name__ == "__main__":
    main()
