#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
plot_toolcorr_network.py  — 袁老师选项【第 1 种：相关性网络图 (correlation network)】
=====================================================================================
服务: QuantImmuBench 「工具间打分相关结构可视化(替代热图)」lever。四张候选图之一, 给袁老师挑。

读什么列 → 算什么 → 画什么图:
  · 读 data/frozen/pooled_clean_9mer.csv 的 30 个 <tool>_max 列 (共享底座 _toolcorr_common)
  · 跨 130 肽算 Spearman 相关阵 → 剔全 NaN 退化工具 (DeepNetBim) → ~29×29
  · 画**相关性网络**: 工具=节点 (按类别蓝/橙上色; 大小∝单工具 per-patient Spearman 性能
    fisherz_rho, 从 R1_recomputed_effN8.csv 读), 边=|相关|≥阈值 (默认 0.4) 连线,
    线宽∝|相关|, 正相关实线 / 负相关虚线(异色)。spring_layout(Fruchterman-Reingold, seed 固定)。
  · 目标: 一眼看「工具家族簇」—— 哪些工具打分彼此高度相关, 抱成团。

为什么是网络而非热图: 网络把「谁和谁像」的**拓扑结构**直接摊开, 家族簇一眼可见, 不必逐格读热图。

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
from matplotlib.lines import Line2D
from matplotlib.patches import Patch

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")     # Windows 必要: UTF-8 stdout

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import _toolcorr_common as tc                # noqa: E402  (共享底座: 数据/配色/存图)

tc.apply_matplotlib_style(plt)

DEFAULT_OUT = tc.FIG_DIR / "fig_toolcorr_network.png"

# networkx 是本图硬依赖 (spring_layout); 缺则明确退出提示, 不静默糊图
try:
    import networkx as nx
except Exception:
    nx = None

# adjustText 用于中心核心团标签自动避让 (推开重叠 + 画细引线连回节点);
# 缺则退回固定偏移方式 (可能仍有重叠, 但不硬崩)
try:
    from adjustText import adjust_text
except Exception:
    adjust_text = None


def build_network(input_path, thresh, perf_csv, seed):
    scores = tc.load_max_scores(input_path)
    corr, dropped = tc.spearman_corr(scores)
    tools = list(corr.columns)
    perf = tc.load_perf(perf_csv, tools)     # {tool_key: rho}; 缺则等大小

    G = nx.Graph()
    for t in tools:
        G.add_node(t)
    # 边: 只连 |ρ|≥thresh 的工具对 (上三角遍历, 不含自环)
    edge_rows = []
    for i, ti in enumerate(tools):
        for j in range(i + 1, len(tools)):
            tj = tools[j]
            rho = float(corr.iloc[i, j])
            if np.isfinite(rho) and abs(rho) >= thresh:
                G.add_edge(ti, tj, weight=abs(rho), rho=rho)
                edge_rows.append((ti, tj, rho))

    # k 调大=节点斥力更强, 防密集正相关塌成一团 (n≈29 默认 k≈0.19 太挤); iterations 加多收敛更开
    # k=2.0: 比 1.6 更散, 把中心 ~12 个高互相关工具再拉开, 给 adjustText 标签避让留空间
    pos = nx.spring_layout(G, seed=seed, k=2.0, iterations=400)   # FR 布局, seed 固定=可复现
    return corr, dropped, tools, perf, G, pos, edge_rows, len(scores)


def node_sizes(tools, perf):
    """节点大小∝ per-patient Spearman 性能 (rho); 缺/全无性能 → 统一中等大小。"""
    vals = np.array([perf.get(t, np.nan) for t in tools], dtype=float)
    finite = vals[np.isfinite(vals)]
    if finite.size == 0:
        return np.full(len(tools), 600.0), False
    lo, hi = float(np.min(finite)), float(np.max(finite))
    span = (hi - lo) if hi > lo else 1.0
    sizes = []
    for v in vals:
        if not np.isfinite(v):
            sizes.append(300.0)                          # 无性能记录 → 最小
        else:
            sizes.append(300.0 + 2200.0 * (v - lo) / span)
    return np.array(sizes), True


def draw(input_path, out_png, thresh, perf_csv, seed):
    if nx is None:
        sys.exit("[ERR] 需要 networkx (pip install networkx); 本图硬依赖 spring_layout")
    corr, dropped, tools, perf, G, pos, edge_rows, n_pep = build_network(
        input_path, thresh, perf_csv, seed)

    fig, ax = plt.subplots(figsize=(16, 14))
    ax.set_axis_off()

    # 边: 正相关实线(红) / 负相关虚线(蓝), 线宽∝|ρ| (阈值~1 映射到 0.8~5.5)
    if edge_rows:
        wmax = max(abs(r) for *_e, r in edge_rows)
        wmax = wmax if wmax > 0 else 1.0
        for ti, tj, rho in edge_rows:
            x = [pos[ti][0], pos[tj][0]]
            y = [pos[ti][1], pos[tj][1]]
            lw = 0.8 + 4.7 * (abs(rho) / wmax)
            ax.plot(x, y, color=(tc.C_POS if rho > 0 else tc.C_NEG),
                    ls="-" if rho > 0 else "--", lw=lw,
                    alpha=0.55, zorder=1, solid_capstyle="round")

    # 节点: 类别上色 + 大小∝性能; 整体缩到 ~0.6 倍, 给中心团标签让出空间
    sizes, has_perf = node_sizes(tools, perf)
    sizes = sizes * 0.6
    colors = [tc.cat_color(t) for t in tools]
    xs = np.array([pos[t][0] for t in tools])
    ys = np.array([pos[t][1] for t in tools])
    ax.scatter(xs, ys, s=sizes, c=colors, edgecolors="white", linewidths=1.4,
               zorder=3)

    # 标签: 展示名 (下划线→连字符) + DTU 后缀; 字号调小 (9.5→8.5) 给密集中心团减压
    labels = [tc.display_name(t) + (" (DTU)" if tc.is_dtu(t) else "") for t in tools]
    if adjust_text is not None:
        # adjustText 自动避让: 先把每个标签放在其节点上, 再迭代把重叠标签推开,
        # arrowprops 画细灰引线把移开的标签连回原节点 —— 中心核心团标签不再互相压死
        texts = [ax.text(pos[t][0], pos[t][1], lab, ha="center", va="center",
                         fontsize=8.5, zorder=4,
                         bbox=dict(boxstyle="round,pad=0.15", fc="white", ec="none", alpha=0.6))
                 for t, lab in zip(tools, labels)]
        adjust_text(texts, ax=ax,
                    arrowprops=dict(arrowstyle="-", color="gray", lw=0.5))
    else:
        # fallback: 无 adjustText 时退回固定偏移 (中心团可能仍有重叠, 但不硬崩)
        for t, lab in zip(tools, labels):
            ax.annotate(lab, xy=pos[t], xytext=(0, 9), textcoords="offset points",
                        ha="center", va="bottom", fontsize=8.5, zorder=4,
                        bbox=dict(boxstyle="round,pad=0.15", fc="white", ec="none", alpha=0.6))

    ax.set_title(f"工具打分相关性网络（节点=工具，边=|Spearman ρ|≥{thresh:.2f}）",
                 fontsize=16, pad=14)

    # 图例: 类别色 + 边含义 + (若有性能) 节点大小含义
    cat_handles = [Patch(facecolor=tc.C_PRESENT, edgecolor="white", label="呈递/结合类"),
                   Patch(facecolor=tc.C_IMMUNO, edgecolor="white", label="免疫原类")]
    edge_handles = [Line2D([0], [0], color=tc.C_POS, ls="-", lw=3, label="正相关 (实线)"),
                    Line2D([0], [0], color=tc.C_NEG, ls="--", lw=3, label="负相关 (虚线)"),
                    Line2D([0], [0], color="#999999", ls="-", lw=1,
                           label="线宽 ∝ |ρ|（越粗越相关）")]
    leg1 = ax.legend(handles=cat_handles, loc="upper left", fontsize=11,
                     title="工具类别", framealpha=0.95)
    ax.add_artist(leg1)
    ax.legend(handles=edge_handles, loc="lower left", fontsize=10,
              title="边 = 工具对相关", framealpha=0.95)
    if has_perf:
        ax.text(0.99, 0.01, "节点大小 ∝ 单工具 per-patient Spearman 性能 (fisherz_rho)",
                transform=ax.transAxes, ha="right", va="bottom", fontsize=9.5,
                color="#555555", style="italic")

    fig.text(0.5, 0.005, tc.caption_note(n_pep, len(tools), dropped),
             ha="center", va="bottom", fontsize=9.5, color="#555555")
    fig.tight_layout(rect=(0, 0.055, 1, 1))
    tc.savefig_all(fig, out_png)
    plt.close(fig)
    print(f"[info] 边数(|ρ|≥{thresh})={len(edge_rows)}; 入图工具={len(tools)}; 剔除={dropped}")


def main():
    ap = argparse.ArgumentParser(description="选项1: 工具打分相关性网络图 (替代热图)")
    ap.add_argument("--input", default=None, help="pooled csv (默认 data/frozen/pooled_clean_9mer.csv)")
    ap.add_argument("--out", default=str(DEFAULT_OUT), help="输出 PNG 路径 (同名 PDF + paper/figures 自动)")
    ap.add_argument("--thresh", type=float, default=0.4, help="连边的 |Spearman ρ| 阈值 (默认 0.4)")
    ap.add_argument("--perf-csv", default=None,
                    help="单工具性能 csv (默认 recompute_effN/R1_recomputed_effN8.csv), 定节点大小")
    ap.add_argument("--seed", type=int, default=42, help="spring_layout 随机种子 (复现零偏离, 默认 42)")
    args = ap.parse_args()
    draw(args.input, args.out, args.thresh, args.perf_csv, args.seed)
    print("[DONE] plot_toolcorr_network 完成")


if __name__ == "__main__":
    main()
