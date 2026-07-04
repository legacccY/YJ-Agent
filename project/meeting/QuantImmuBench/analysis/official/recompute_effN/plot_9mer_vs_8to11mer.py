#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
plot_9mer_vs_8to11mer.py

服务：QuantImmuBench §2.2 可变窗 (8-11mer) 补充口径出图。
数据源（只读，列名已核实）：
  - 9mer   effN : analysis/official/recompute_effN/R1_recomputed_effN8.csv        (pandas 读需 comment="#")
  - 8-11mer effN: analysis/official/recompute_effN/R1_recomputed_8to11mer_effN8.csv (同 comment="#")
      两表列: Tool、fisherz_rho_effN (per-patient Spearman, Fisher-z 均值, effN>=8 门槛)。
  - 覆盖  : data/frozen/pooled_clean_8to11mer.csv (每工具 <Tool>_max 列非空肽数, 满分 130)。

产物 (300dpi png + pdf 到 paper/figures/):
  A: fig_9mer_vs_8to11mer_spearman   —— 每工具 9mer vs 8-11mer 双色横向分组条形图
  B: fig_8to11mer_coverage           —— 8-11mer 口径 30 工具覆盖条形图

红线：本脚本【只写不跑】。数字全从 csv 现算，不硬编任何 rho/覆盖值。主线跑：
      python analysis/official/recompute_effN/plot_9mer_vs_8to11mer.py [--dpi 300]
"""
import argparse
from pathlib import Path

import matplotlib
matplotlib.use("Agg")  # Windows 无 GUI 后端
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

# ---- 路径 (相对脚本解析: 脚本在 analysis/official/recompute_effN/, 项目根=parents[3]) ----
SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[2]  # recompute_effN -> official -> analysis -> <ROOT>
# 校验: SCRIPT_DIR = ROOT/analysis/official/recompute_effN
assert SCRIPT_DIR == ROOT / "analysis" / "official" / "recompute_effN", \
    f"路径解析异常: SCRIPT_DIR={SCRIPT_DIR} ROOT={ROOT}"

CSV_9MER = SCRIPT_DIR / "R1_recomputed_effN8.csv"
CSV_811 = SCRIPT_DIR / "R1_recomputed_8to11mer_effN8.csv"
CSV_POOLED_811 = ROOT / "data" / "frozen" / "pooled_clean_8to11mer.csv"
OUT_DIR = ROOT / "paper" / "figures"

N_PEPTIDES = 130  # 8-11mer 池满分 (确定性核: 131 行 - 1 表头)

# ---- 学术配色 (蓝/灰双色, 色盲友好) ----
COLOR_9MER = "#2166AC"   # 深蓝 (9mer main)
COLOR_811 = "#92C5DE"    # 浅蓝灰 (8-11mer aperture)
COLOR_PASS = "#4DAF4A"   # 绿 (覆盖=130 达标)
COLOR_FAIL = "#FF7F00"   # 橙 (覆盖<130)
COLOR_DEGEN = "#999999"  # 灰 (非空满 130 但退化常数列, 秩相关 n/a)


def _save(fig, stem, dpi):
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    png = OUT_DIR / f"{stem}.png"
    pdf = OUT_DIR / f"{stem}.pdf"
    fig.savefig(png, dpi=dpi, bbox_inches="tight")
    fig.savefig(pdf, bbox_inches="tight")
    plt.close(fig)
    return png, pdf


def make_fig_a(dpi):
    """图A: 9mer vs 8-11mer per-patient Spearman 双色横向分组条形图。"""
    df9 = pd.read_csv(CSV_9MER, comment="#")[["Tool", "fisherz_rho_effN"]]
    df8 = pd.read_csv(CSV_811, comment="#")[["Tool", "fisherz_rho_effN"]]
    merged = df9.merge(df8, on="Tool", how="inner", suffixes=("_9mer", "_811")).dropna(
        subset=["fisherz_rho_effN_9mer", "fisherz_rho_effN_811"]
    )
    # 只保留「两种长度口径都真适用」的工具: 剔 9mer-only 硬限长工具 —— 其 8-11max ≡ 9mer max
    #   (数据核: NeoaPred 结构 9mer diff=0/14, DeepNetBim 硬 9mer diff=0/130, 见 04_LOG Entry 51),
    #   放进对比图=两条等长的假对比。其余工具 8-11 max 均随口径变化 (含 DeepImmuno 9-10mer, diff=50/130)。
    EXCLUDE_9MER_ONLY = {"NeoaPred", "DeepNetBim"}
    n_before = len(merged)
    merged = merged[~merged["Tool"].isin(EXCLUDE_9MER_ONLY)].copy()
    dropped = n_before - len(merged)
    # 按 9mer 值降序
    merged = merged.sort_values("fisherz_rho_effN_9mer", ascending=False).reset_index(drop=True)

    tools = merged["Tool"].tolist()
    v9 = merged["fisherz_rho_effN_9mer"].to_numpy()
    v8 = merged["fisherz_rho_effN_811"].to_numpy()
    n = len(tools)

    # y 轴: 降序 => 顶部为最高值, 故 y 位置反转
    y = np.arange(n)[::-1]
    h = 0.38

    fig, ax = plt.subplots(figsize=(13.0, max(6.5, 0.46 * n + 1.6)))
    ax.barh(y + h / 2, v9, height=h, color=COLOR_9MER, label="9mer main", edgecolor="white", linewidth=0.3)
    ax.barh(y - h / 2, v8, height=h, color=COLOR_811, label="8-11mer aperture", edgecolor="white", linewidth=0.3)

    # 每条标数值 (符号感知: 正条标右, 负条标左, 不遮条)
    off = 0.006
    for yi, val in zip(y + h / 2, v9):
        ax.text(val + (off if val >= 0 else -off), yi, f"{val:.3f}",
                va="center", ha=("left" if val >= 0 else "right"),
                fontsize=6.5, color=COLOR_9MER, fontweight="bold")
    for yi, val in zip(y - h / 2, v8):
        ax.text(val + (off if val >= 0 else -off), yi, f"{val:.3f}",
                va="center", ha=("left" if val >= 0 else "right"),
                fontsize=6.5, color="#3B7CB0")

    ax.axvline(0.0, color="0.35", linestyle="--", linewidth=1.0, zorder=0)
    ax.set_yticks(y)
    ax.set_yticklabels(tools, fontsize=9)
    # xlim 右/左各留标签空间
    vmin = float(min(v8.min(), v9.min()))
    vmax = float(max(v8.max(), v9.max()))
    ax.set_xlim(min(vmin - 0.09, -0.02), vmax + 0.09)
    ax.set_xlabel("Per-patient Spearman (Fisher-z mean, effN>=8)", fontsize=10)
    ax.set_title(
        "Per-patient Spearman: 9mer main vs 8-11mer variable-window aperture (effN>=8)",
        fontsize=11.5,
    )
    # 图例放坐标区外右上, 绝不压条
    ax.legend(loc="upper left", bbox_to_anchor=(1.005, 1.0), fontsize=9, frameon=True)
    ax.grid(axis="x", linestyle=":", color="0.8", linewidth=0.6, zorder=0)
    ax.set_axisbelow(True)
    fig.text(
        0.01, 0.005,
        "Source: R1_recomputed_effN8.csv (9mer) + R1_recomputed_8to11mer_effN8.csv (8-11mer). "
        "Per-patient Spearman rho, Fisher-z averaged over patients with effN>=8. "
        "Only tools applicable to both apertures shown; DeepNetBim / NeoaPred excluded (9mer-only: 8-11 max identical to 9mer max).",
        fontsize=6.5, color="0.4",
    )

    png, pdf = _save(fig, "fig_9mer_vs_8to11mer_spearman", dpi)

    # ---- print 关键值供主线核 ----
    print(f"[Fig A] joined tools (dropna) = {n} (excluded {dropped} 9mer-only: {sorted(EXCLUDE_9MER_ONLY)})")
    print("[Fig A] top3 by 9mer:")
    for i in range(min(3, n)):
        print(f"    {tools[i]:<16s} 9mer={v9[i]:.4f}  8-11mer={v8[i]:.4f}")
    print(f"[Fig A] saved: {png.name}, {pdf.name}")
    return n


def make_fig_b(dpi):
    """图B: 8-11mer 口径 30 工具覆盖 (<Tool>_max 非空肽数)。工具集取自 8-11mer effN csv。"""
    df8 = pd.read_csv(CSV_811, comment="#")
    tools = df8["Tool"].tolist()
    # coverage_fail 标记 (退化列: 非空满 130 但秩相关算不出, 如 DeepNetBim 恒=1.0 常数列)
    covfail_map = dict(zip(df8["Tool"], df8["coverage_fail"].fillna(False).astype(bool)))

    pooled = pd.read_csv(CSV_POOLED_811, comment="#")
    n_rows = len(pooled)  # 应为 130
    assert n_rows == N_PEPTIDES, f"pooled 行数={n_rows} != {N_PEPTIDES}"

    cov, degen = {}, {}
    missing_cols = []
    for t in tools:
        col = f"{t}_max"
        if col in pooled.columns:
            s = pooled[col]
            cov[t] = int(s.notna().sum())
            # 退化 = 非空满 130 但唯一值 <=1 (常数列, 秩相关 n/a) 或 R1 标 coverage_fail
            degen[t] = bool(cov[t] >= N_PEPTIDES and (s.dropna().nunique() <= 1 or covfail_map.get(t, False)))
        else:
            missing_cols.append(t)
    if missing_cols:
        print(f"[Fig B] WARNING: missing <Tool>_max columns for: {missing_cols}")

    cov_df = pd.DataFrame({"Tool": list(cov.keys()), "coverage": list(cov.values())})
    cov_df["degen"] = cov_df["Tool"].map(degen)
    cov_df = cov_df.sort_values("coverage", ascending=False).reset_index(drop=True)

    tlist = cov_df["Tool"].tolist()
    cvals = cov_df["coverage"].to_numpy()
    dflags = cov_df["degen"].tolist()
    n = len(tlist)
    # 满覆盖但退化 (DeepNetBim) 用灰色区分 "假满覆盖", 真满=绿, 部分=橙
    colors = [(COLOR_DEGEN if d else (COLOR_PASS if c >= N_PEPTIDES else COLOR_FAIL))
              for c, d in zip(cvals, dflags)]
    any_degen = any(dflags)

    y = np.arange(n)[::-1]
    fig, ax = plt.subplots(figsize=(8.0, max(6.0, 0.38 * n + 1.5)))
    ax.barh(y, cvals, color=colors, edgecolor="white", linewidth=0.3)
    ax.axvline(N_PEPTIDES, color="0.3", linestyle="--", linewidth=1.0, zorder=0)

    for yi, c, d in zip(y, cvals, dflags):
        txt = f"{int(c)} *" if d else str(int(c))
        ax.text(c + 1.0, yi, txt, va="center", ha="left", fontsize=7, color="0.25")

    ax.set_yticks(y)
    ax.set_yticklabels([f"{t} *" if d else t for t, d in zip(tlist, dflags)], fontsize=8)
    ax.set_xlim(0, N_PEPTIDES + 8)
    ax.set_xlabel(f"Peptides covered (non-null <Tool>_max, max {N_PEPTIDES})", fontsize=10)
    ax.set_title(f"Tool coverage under 8-11mer aperture (n={N_PEPTIDES} peptides)", fontsize=11)
    ax.grid(axis="x", linestyle=":", color="0.8", linewidth=0.6, zorder=0)
    ax.set_axisbelow(True)

    # 图例
    from matplotlib.patches import Patch
    handles = [
        Patch(facecolor=COLOR_PASS, label=f"full ({N_PEPTIDES}/{N_PEPTIDES})"),
        Patch(facecolor=COLOR_FAIL, label=f"partial (<{N_PEPTIDES})"),
    ]
    if any_degen:
        handles.append(Patch(facecolor=COLOR_DEGEN, label="* degenerate (const. column, rho n/a)"))
    ax.legend(handles=handles, loc="lower right", fontsize=9, frameon=True)
    foot = ("Source: data/frozen/pooled_clean_8to11mer.csv. "
            "Coverage = count of non-null <Tool>_max over 130 peptides.")
    if any_degen:
        foot += ("  * = 130 non-null but constant after max-pool (e.g. DeepNetBim all=1.0); "
                 "rank correlation degenerate, rho=n/a (see Fig.1 reference zone); not a usable tool.")
    fig.text(0.01, 0.005, foot, fontsize=6.5, color="0.4")

    png, pdf = _save(fig, "fig_8to11mer_coverage", dpi)

    # ---- print 关键值供主线核 ----
    n_full = int((cvals >= N_PEPTIDES).sum())
    print(f"[Fig B] tools plotted = {n}, full-coverage({N_PEPTIDES}) tools = {n_full}")
    print("[Fig B] top3 by coverage:")
    for i in range(min(3, n)):
        print(f"    {tlist[i]:<16s} coverage={int(cvals[i])}")
    print("[Fig B] bottom3 by coverage:")
    for i in range(max(0, n - 3), n):
        print(f"    {tlist[i]:<16s} coverage={int(cvals[i])}")
    print(f"[Fig B] saved: {png.name}, {pdf.name}")
    return n_full


def main():
    ap = argparse.ArgumentParser(description="QuantImmuBench §2.2 8-11mer aperture figures")
    ap.add_argument("--dpi", type=int, default=300, help="raster dpi for png (default 300)")
    args = ap.parse_args()

    print(f"[out] figures -> {OUT_DIR}")
    make_fig_a(args.dpi)
    make_fig_b(args.dpi)
    print("[done] both figures written.")


if __name__ == "__main__":
    main()
