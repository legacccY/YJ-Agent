#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
plot_fig_lencompare.py

服务：QuantImmuBench §2.2 长度口径 —— 9mer 主口径 vs 8-11mer 可变窗（逐工具哑铃对比图）。

数据源（只读，列名已核实，两表 comment="#" 头）：
  - 9mer   effN : analysis/official/recompute_effN/R1_recomputed_effN8.csv
  - 8-11mer effN: analysis/official/recompute_effN/R1_recomputed_8to11mer_effN8.csv
      两表都含列: Tool、fisherz_rho_effN (per-patient Spearman, Fisher-z 均值, effN>=8 门槛)。
  merge on Tool + dropna(fisherz_rho_effN 两侧) => DeepNetBim（两表均无值）自动剔 => 29 共同工具。
  NeoaPred 为 9mer-only 结构工具（8-11 max ≡ 9mer max），两表同值 0.077，按 spec 保留（哑铃退化为一点）。

图设计（哑铃 / dumbbell）：
  每工具一行，按 9mer ρ 降序；横轴 = per-patient Spearman ρ。
  实心蓝点=9mer，空心橙点=8-11mer，横线连两点；两点各标数值。
  4 个 8-11mer > 9mer 的工具（用 v811>v9 现判，不硬编码）连线用异色（vermillion），诚实呈现「多数但非全部 9mer 更高」。
  角落注文：9mer/8-11mer 均值 + N/29 工具 9mer>=8-11mer（全部从 csv 现算）。

单图 vs 分两张：默认【分两张】（--single 可强制单张）。29 行带标注塞进 16:9 slide 会挤到读不清，
  按 9mer ρ 降序切上/下半（上 15 + 下 14）各一张，命名 fig_lencompare_1 / fig_lencompare_2。
  （不按工具类别分：呈递/免疫原类别非本两 csv 的列，硬编类别表违反零硬编码约束。）

产物（300dpi PNG + PDF，各写两处目录）：
  - analysis/official/figures/
  - paper/figures/
  固定 figsize + subplots_adjust + savefig 不用 bbox_inches='tight'
  => PNG 像素严格 = figsize*dpi，纵横比精确 = figW/figH（deck placeImg contain 需精确 ratio 防拉伸）。

红线：本脚本【只写不跑】。所有数值（含均值、计数、crossover 判定）一律从 csv 现算，零硬编码。
主线跑：  python analysis/official/plot_fig_lencompare.py [--dpi 300] [--single]
"""
import argparse
from pathlib import Path

import matplotlib
matplotlib.use("Agg")  # Windows 无 GUI 后端
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
import numpy as np
import pandas as pd

# 中文字体 + mathtext 希腊字母（吸取 fig3/fig4 豆腐块教训：中文字体缺 ρ，一律走 mathtext $\rho$）
matplotlib.rcParams["font.sans-serif"] = ["Microsoft YaHei", "DejaVu Sans"]
matplotlib.rcParams["axes.unicode_minus"] = False  # 负 ρ 值用 ASCII '-'，防负号豆腐块

# ---- 路径（脚本在 analysis/official/，项目根=parents[1]）----
SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[1]  # official -> analysis -> <ROOT>
assert SCRIPT_DIR == ROOT / "analysis" / "official", \
    f"路径解析异常: SCRIPT_DIR={SCRIPT_DIR} ROOT={ROOT}"

CSV_9MER = SCRIPT_DIR / "recompute_effN" / "R1_recomputed_effN8.csv"
CSV_811 = SCRIPT_DIR / "recompute_effN" / "R1_recomputed_8to11mer_effN8.csv"
OUT_DIRS = [ROOT / "analysis" / "official" / "figures", ROOT / "paper" / "figures"]

N_PEPTIDES = 130  # 8-11mer 池满分（130 肽，写入轴标注口径）

# ---- 学术配色（Okabe-Ito 色盲友好，与 deck 一致）----
COLOR_9MER = "#0072B2"   # 深蓝：9mer 主口径（实心）
COLOR_811 = "#E69F00"    # 橙：8-11mer 可变窗（空心）
COLOR_LINE = "#B0B0B0"   # 灰：常规连线（9mer >= 8-11mer）
COLOR_CROSS = "#D55E00"  # vermillion：crossover 连线（8-11mer > 9mer）


def load_merged():
    """读两表、merge、dropna => 29 共同工具（DeepNetBim 自动剔）；按 9mer ρ 降序。
    返回 (merged_df, stats)；stats 全部从 csv 现算。"""
    df9 = pd.read_csv(CSV_9MER, comment="#")[["Tool", "fisherz_rho_effN"]]
    df8 = pd.read_csv(CSV_811, comment="#")[["Tool", "fisherz_rho_effN"]]
    merged = df9.merge(df8, on="Tool", how="inner", suffixes=("_9mer", "_811")).dropna(
        subset=["fisherz_rho_effN_9mer", "fisherz_rho_effN_811"]
    )
    merged = merged.sort_values("fisherz_rho_effN_9mer", ascending=False).reset_index(drop=True)
    merged = merged.rename(columns={"fisherz_rho_effN_9mer": "v9", "fisherz_rho_effN_811": "v8"})

    v9 = merged["v9"].to_numpy()
    v8 = merged["v8"].to_numpy()
    n_tot = len(merged)
    stats = {
        "n_tot": n_tot,
        "mean9": float(v9.mean()),
        "mean8": float(v8.mean()),
        "n_ge": int((v9 >= v8).sum()),      # 9mer >= 8-11mer
        "n_cross": int((v8 > v9).sum()),    # 8-11mer > 9mer（crossover）
        "cross_tools": merged.loc[v8 > v9, "Tool"].tolist(),
    }
    return merged, stats


def _stats_str(stats):
    """角落注文（mathtext ρ / >= 防豆腐块），数值全来自 stats（csv 现算）。"""
    return (
        f"9mer 均值 $\\rho$ = {stats['mean9']:.3f}    |    "
        f"8-11mer 均值 $\\rho$ = {stats['mean8']:.3f}\n"
        f"{stats['n_ge']}/{stats['n_tot']} 工具：9mer $\\geq$ 8-11mer"
    )


def _draw_dumbbell(ax, sub, xlim):
    """在 ax 上画一组工具的哑铃行（sub 已按 9mer 降序）。"""
    tools = sub["Tool"].tolist()
    v9 = sub["v9"].to_numpy()
    v8 = sub["v8"].to_numpy()
    n = len(tools)
    y = np.arange(n)[::-1]  # 降序 => 最高值置顶
    off = 0.006             # 数值标签相对点的横向偏移

    for i in range(n):
        yy = y[i]
        x9, x8 = float(v9[i]), float(v8[i])
        is_cross = x8 > x9
        lc = COLOR_CROSS if is_cross else COLOR_LINE
        lw = 2.4 if is_cross else 1.7
        # 连线
        ax.plot([x9, x8], [yy, yy], color=lc, lw=lw, solid_capstyle="round", zorder=1)
        # 8-11mer 空心橙点
        ax.scatter([x8], [yy], s=46, facecolor="white", edgecolor=COLOR_811,
                   linewidth=1.6, zorder=3)
        # 9mer 实心蓝点
        ax.scatter([x9], [yy], s=46, color=COLOR_9MER, edgecolor="white",
                   linewidth=0.5, zorder=4)
        # 数值标注：左点标签朝左、右点标签朝右，防重叠
        if x9 >= x8:  # 9mer 在右
            ax.text(x9 + off, yy, f"{x9:.3f}", ha="left", va="center",
                    fontsize=7, color=COLOR_9MER, fontweight="bold", zorder=5)
            ax.text(x8 - off, yy, f"{x8:.3f}", ha="right", va="center",
                    fontsize=7, color=COLOR_811, zorder=5)
        else:         # 8-11mer 在右（crossover）
            ax.text(x8 + off, yy, f"{x8:.3f}", ha="left", va="center",
                    fontsize=7, color=COLOR_811, fontweight="bold", zorder=5)
            ax.text(x9 - off, yy, f"{x9:.3f}", ha="right", va="center",
                    fontsize=7, color=COLOR_9MER, zorder=5)

    ax.axvline(0.0, color="0.45", linestyle="--", linewidth=0.9, zorder=0)
    ax.set_yticks(y)
    ax.set_yticklabels(tools, fontsize=10)
    ax.set_ylim(-0.6, n - 0.4)
    ax.set_xlim(*xlim)
    ax.grid(axis="x", linestyle=":", color="0.82", linewidth=0.6, zorder=0)
    ax.set_axisbelow(True)


def _legend_stats(ax, stats):
    """自定义图例（左上，空区不压点）+ 角落统计框（右下）。"""
    handles = [
        Line2D([0], [0], marker="o", color="w", markerfacecolor=COLOR_9MER,
               markeredgecolor="white", markersize=9, label="9mer 主口径（实心）"),
        Line2D([0], [0], marker="o", color="w", markerfacecolor="white",
               markeredgecolor=COLOR_811, markeredgewidth=1.6, markersize=9,
               label="8-11mer 可变窗（空心）"),
        Line2D([0], [0], color=COLOR_CROSS, lw=2.6, label="8-11mer > 9mer"),
        Line2D([0], [0], color=COLOR_LINE, lw=2.0, label="9mer $\\geq$ 8-11mer"),
    ]
    ax.legend(handles=handles, loc="upper left", fontsize=8.5, frameon=True,
              framealpha=0.92, borderpad=0.6, handlelength=1.6)
    ax.text(0.985, 0.02, _stats_str(stats), transform=ax.transAxes,
            ha="right", va="bottom", fontsize=8.5, color="0.15",
            bbox=dict(boxstyle="round,pad=0.5", facecolor="white",
                      edgecolor="0.7", alpha=0.92))


BASE_TITLE = "§2.2 单工具 Spearman $\\rho$：9mer 主口径 vs 8-11mer 可变窗"
XLABEL = (
    "Per-patient Spearman $\\rho$"
    "（Fisher-z 均值，患者内 effN$\\geq$8，n=%d 肽）" % N_PEPTIDES
)
FOOTER = (
    "数据源：R1_recomputed_effN8.csv（9mer）+ R1_recomputed_8to11mer_effN8.csv（8-11mer）；"
    "per-patient Spearman ρ，患者内 effN$\\geq$8 的 Fisher-z 均值。"
    "DeepNetBim 两表均无值，dropna 后剔 → 29 共同工具。"
)


def _save(fig, stem, dpi):
    """写入两处目录（PNG 300dpi + PDF）。不用 bbox_inches='tight' => PNG 纵横比精确 = figW/figH。"""
    outs = []
    for d in OUT_DIRS:
        d.mkdir(parents=True, exist_ok=True)
        png = d / f"{stem}.png"
        pdf = d / f"{stem}.pdf"
        fig.savefig(png, dpi=dpi)   # 无 bbox_inches='tight'：像素严格 = figsize*dpi
        fig.savefig(pdf)
        outs.append(png)
    plt.close(fig)
    return outs


def make_figure(sub, stats, stem, title_suffix, xlim, figsize, dpi):
    """画一张哑铃图（一个工具子集）。固定 figsize + subplots_adjust，保证 PNG 精确纵横比。"""
    fig, ax = plt.subplots(figsize=figsize)
    fig.subplots_adjust(left=0.185, right=0.965, top=0.905, bottom=0.115)
    _draw_dumbbell(ax, sub, xlim)
    _legend_stats(ax, stats)
    ax.set_xlabel(XLABEL, fontsize=11)
    ax.set_title(BASE_TITLE + title_suffix, fontsize=12.5, pad=8)
    fig.text(0.5, 0.028, FOOTER, ha="center", fontsize=6.6, color="0.4")
    outs = _save(fig, stem, dpi)
    ratio = figsize[0] / figsize[1]
    print(f"[{stem}] rows={len(sub)}  figsize={figsize}  ratio(W/H)={ratio:.4f}")
    print(f"[{stem}] saved -> {'; '.join(str(p) for p in outs)}")
    return outs


def _xlim_for(sub, pad=0.075):
    v = np.concatenate([sub["v9"].to_numpy(), sub["v8"].to_numpy()])
    return (float(v.min()) - pad, float(v.max()) + pad)


def main():
    ap = argparse.ArgumentParser(description="QuantImmuBench §2.2 9mer vs 8-11mer 哑铃对比图")
    ap.add_argument("--dpi", type=int, default=300, help="raster dpi for png (default 300)")
    ap.add_argument("--single", action="store_true",
                    help="强制单张（默认分两张，上/下半各一张）")
    args = ap.parse_args()

    merged, stats = load_merged()
    n = stats["n_tot"]
    print(f"[data] merged tools (dropna) = {n}  "
          f"mean9={stats['mean9']:.4f} mean8={stats['mean8']:.4f}  "
          f"9mer>=8-11: {stats['n_ge']}/{n}  crossover(8-11>9mer)={stats['n_cross']}: {stats['cross_tools']}")
    for d in OUT_DIRS:
        print(f"[out] -> {d}")

    if args.single:
        xlim = _xlim_for(merged)
        figsize = (11.0, 1.6 + 0.34 * n)  # 单张较高
        make_figure(merged, stats, "fig_lencompare_all",
                    "（逐工具对比，全 %d 工具）" % n, xlim, figsize, args.dpi)
    else:
        # 按 9mer ρ 降序切上/下半：上 ceil(n/2) + 下 floor(n/2)
        k = (n + 1) // 2  # 29 -> 15
        top = merged.iloc[:k].reset_index(drop=True)
        bot = merged.iloc[k:].reset_index(drop=True)
        # 两张共用同一 figsize（=> 同一 ratio，deck 一致）；xlim 各自算（放大各半的动态范围，标签更疏）
        figsize = (9.6, 7.6)  # ratio = 1.2632（deck placeImg 用）
        make_figure(top, stats, "fig_lencompare_1",
                    "（逐工具对比·上半 %d 工具）" % len(top), _xlim_for(top), figsize, args.dpi)
        make_figure(bot, stats, "fig_lencompare_2",
                    "（逐工具对比·下半 %d 工具）" % len(bot), _xlim_for(bot), figsize, args.dpi)

    print("[done] figures written (script did NOT execute training/model code).")


if __name__ == "__main__":
    main()
