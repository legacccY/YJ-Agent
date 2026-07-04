#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
plot_toolcorr_corrplot.py — 袁老师选项【第 3 种：聚类椭圆 corrplot (非填色热图)】
================================================================================
服务: QuantImmuBench 「工具间打分相关结构可视化(替代热图)」lever。四张候选图之一, 给袁老师挑。

读什么列 → 算什么 → 画什么图:
  · 读 data/frozen/pooled_clean_9mer.csv 的 30 个 <tool>_max 列 (共享底座 _toolcorr_common)
  · 跨 130 肽算 Spearman 相关阵 → 剔全 NaN 退化工具 (DeepNetBim) → ~29×29
  · 按层次聚类 (1−|ρ| 距离, average linkage) 的叶顺序**重排行列**, 让相似工具相邻
  · 每个 (i,j) 单元手绘一个**椭圆** (matplotlib.patches.Ellipse, 非方格纯色填充):
      - 扁度编码 |ρ|:  |ρ|→1 椭圆越扁 (趋近一条线); ρ=0 → 正圆
      - 朝向编码正负:  ρ>0 右倾(+45°) / ρ<0 左倾(−45°)
      - 颜色编码 ρ:    蓝(−) — 白(0) — 红(+)  (RdBu_r)
  · addrect 式: 在聚类簇边界画黑框 (fcluster 切 k 簇, 沿对角块框出)

为什么是椭圆 corrplot 而非热图: **形状(扁度+朝向)与颜色双编码**同一个 ρ, 强相关一眼跳出;
  「不用方格纯色填充」正是与热图的关键区分 —— 这是袁老师要的「非热图专业画法」。

Windows 规范: matplotlib Agg + Microsoft YaHei + pathlib; 300dpi PNG + PDF(矢量) + paper/figures pdf。
★ 本脚本不自跑 —— 主线跑 (见文件尾)。相关数值全部从 csv 现算, 脚本内零硬编码。
"""

import sys
import argparse
from pathlib import Path

import numpy as np

import matplotlib
matplotlib.use("Agg")                       # 无 GUI 后端 (只出文件)
import matplotlib.pyplot as plt
from matplotlib.patches import Ellipse, Rectangle
from matplotlib.colors import Normalize
from matplotlib.cm import ScalarMappable

from scipy.spatial.distance import squareform
from scipy.cluster.hierarchy import linkage, leaves_list, fcluster

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")     # Windows 必要: UTF-8 stdout

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import _toolcorr_common as tc                # noqa: E402  (共享底座: 数据/配色/存图)

tc.apply_matplotlib_style(plt)

DEFAULT_OUT = tc.FIG_DIR / "fig_toolcorr_corrplot.png"

MAXD = 0.86          # 单元内椭圆最大直径 (略小于 1 留缝, 防相邻椭圆粘连)


def _cluster_order(corr, method, k):
    """层次聚类叶顺序 + 每叶的簇标签 (供重排 + addrect)。"""
    dist = tc.distance_from_corr(corr)
    condensed = squareform(dist, checks=False)
    Z = linkage(condensed, method=method)
    order = leaves_list(Z)                          # 重排索引
    n = corr.shape[0]
    kk = max(1, min(k, n))
    clusters = fcluster(Z, t=kk, criterion="maxclust")   # 每原始叶的簇号
    return order, clusters


def draw(input_path, out_png, method, k, triangle):
    scores = tc.load_max_scores(input_path)
    corr, dropped = tc.spearman_corr(scores)
    n_pep = len(scores)

    order, clusters = _cluster_order(corr, method, k)
    tools = [corr.columns[i] for i in order]        # 重排后的工具序
    M = corr.to_numpy()[np.ix_(order, order)]       # 重排后的相关阵
    clus_ord = clusters[order]                       # 重排后每行的簇号 (对角连续)
    n = len(tools)

    cmap = plt.get_cmap("RdBu_r")                   # 低=蓝, 高=红
    norm = Normalize(vmin=-1.0, vmax=1.0)

    fig, ax = plt.subplots(figsize=(12.5, 11.5))

    def _draw_cell(i, j):
        rho = float(M[i, j])
        cx, cy = j + 0.5, i + 0.5
        major = MAXD
        minor = MAXD * (1.0 - abs(rho))             # |ρ|→1 → 扁成线; ρ=0 → 圆
        angle = 45.0 if rho >= 0 else -45.0         # 正右倾 / 负左倾
        e = Ellipse((cx, cy), width=major, height=minor, angle=angle,
                    facecolor=cmap(norm(rho)), edgecolor="#666666", lw=0.4, zorder=2)
        ax.add_patch(e)

    # 单元格: 按 triangle 选画范围
    for i in range(n):
        for j in range(n):
            if triangle == "upper" and j < i:
                continue
            if triangle == "lower" and j > i:
                continue
            _draw_cell(i, j)

    # addrect: 沿对角块框出聚类簇 (clus_ord 连续段)
    b = 0
    while b < n:
        e = b
        while e + 1 < n and clus_ord[e + 1] == clus_ord[b]:
            e += 1
        ax.add_patch(Rectangle((b, b), e - b + 1, e - b + 1, fill=False,
                               edgecolor="black", lw=1.8, zorder=3))
        b = e + 1

    # 轴: 工具名 (下划线→连字符 + DTU); 行左 / 列顶, 按类别上色
    labels = [tc.display_name(t) + (" (DTU)" if tc.is_dtu(t) else "") for t in tools]
    ax.set_xlim(0, n)
    ax.set_ylim(0, n)
    ax.set_xticks(np.arange(n) + 0.5)
    ax.set_yticks(np.arange(n) + 0.5)
    ax.set_xticklabels(labels, rotation=90, fontsize=9)
    ax.set_yticklabels(labels, fontsize=9)
    ax.xaxis.set_ticks_position("top")
    ax.xaxis.set_label_position("top")
    for tick, t in zip(ax.get_xticklabels(), tools):
        tick.set_color(tc.cat_color(t)); tick.set_fontweight("bold")
    for tick, t in zip(ax.get_yticklabels(), tools):
        tick.set_color(tc.cat_color(t)); tick.set_fontweight("bold")
    ax.invert_yaxis()                               # 行 0 置顶 (矩阵习惯)
    ax.set_aspect("equal")
    ax.tick_params(length=0)
    for s in ax.spines.values():
        s.set_visible(False)

    ax.set_title("工具打分相关 椭圆 corrplot（聚类重排；扁度=|ρ|，朝向=正负，颜色=ρ）",
                 fontsize=15.5, pad=34)

    # 颜色条 (ρ 图例)
    sm = ScalarMappable(norm=norm, cmap=cmap); sm.set_array([])
    cbar = fig.colorbar(sm, ax=ax, fraction=0.035, pad=0.02)
    cbar.set_label("Spearman ρ", fontsize=11)

    fig.text(0.5, 0.005, tc.caption_note(n_pep, len(tools), dropped)
             + f"  行列按 average-linkage 聚类重排；黑框=fcluster 切 {k} 簇；椭圆非填色方格(区别热图)",
             ha="center", va="bottom", fontsize=9.3, color="#555555")
    fig.tight_layout(rect=(0, 0.04, 1, 1))
    tc.savefig_all(fig, out_png)
    plt.close(fig)
    print(f"[info] 入图工具={len(tools)}; 剔除={dropped}; 簇数k={k}; triangle={triangle}")


def main():
    ap = argparse.ArgumentParser(description="选项3: 工具打分椭圆 corrplot (聚类重排, 非热图)")
    ap.add_argument("--input", default=None, help="pooled csv (默认 data/frozen/pooled_clean_9mer.csv)")
    ap.add_argument("--out", default=str(DEFAULT_OUT), help="输出 PNG 路径 (同名 PDF + paper/figures 自动)")
    ap.add_argument("--method", default="average", help="linkage 方法 (默认 average)")
    ap.add_argument("--k", type=int, default=4, help="addrect 黑框切簇数 (fcluster maxclust, 默认 4)")
    ap.add_argument("--triangle", default="full", choices=["full", "upper", "lower"],
                    help="画全阵/上三角/下三角 (默认 full)")
    args = ap.parse_args()
    draw(args.input, args.out, args.method, args.k, args.triangle)
    print("[DONE] plot_toolcorr_corrplot 完成")


if __name__ == "__main__":
    main()
