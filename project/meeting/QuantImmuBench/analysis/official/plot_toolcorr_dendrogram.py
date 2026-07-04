#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
plot_toolcorr_dendrogram.py — 袁老师选项【第 2 种：层次聚类树状图 (dendrogram)】
================================================================================
服务: QuantImmuBench 「工具间打分相关结构可视化(替代热图)」lever。四张候选图之一, 给袁老师挑。

读什么列 → 算什么 → 画什么图:
  · 读 data/frozen/pooled_clean_9mer.csv 的 30 个 <tool>_max 列 (共享底座 _toolcorr_common)
  · 跨 130 肽算 Spearman 相关阵 → 剔全 NaN 退化工具 (DeepNetBim) → ~29×29
  · 相异度 = 1 − |相关| → scipy.spatial.distance.squareform 压成 condensed 向量
  · scipy.cluster.hierarchy.linkage(method='average') 层次聚类 → dendrogram
  · 叶子标工具名 (下划线→连字符 + DTU 后缀); 叶标签按类别上色 (蓝 呈递 / 橙 免疫原);
    color_threshold 自动把主分支上色分簇。树高 = 相异度 (越矮合并 = 打分越像)。

为什么是树状图: 直接读出「工具合并的层级顺序」—— 哪几个工具最先抱团 (最像), 大类怎么分。
比热图更清晰地表达「聚类层级」这一维信息。

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
from matplotlib.patches import Patch

from scipy.spatial.distance import squareform
from scipy.cluster.hierarchy import linkage, dendrogram

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")     # Windows 必要: UTF-8 stdout

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import _toolcorr_common as tc                # noqa: E402  (共享底座: 数据/配色/存图)

tc.apply_matplotlib_style(plt)

DEFAULT_OUT = tc.FIG_DIR / "fig_toolcorr_dendrogram.png"


def draw(input_path, out_png, color_thresh, method):
    scores = tc.load_max_scores(input_path)
    corr, dropped = tc.spearman_corr(scores)
    tools = list(corr.columns)
    n_pep = len(scores)

    dist = tc.distance_from_corr(corr)               # 1 − |ρ|, 对称零对角
    condensed = squareform(dist, checks=False)        # 方阵 → condensed 上三角向量
    Z = linkage(condensed, method=method)             # 默认 average linkage

    # 叶标签 = 展示名 + DTU 后缀
    labels = [tc.display_name(t) + (" (DTU)" if tc.is_dtu(t) else "") for t in tools]

    # color_threshold: None → scipy 默认 (0.7*max); 传值则按值分簇上色
    ct = None if (color_thresh is None or color_thresh < 0) else color_thresh

    fig, ax = plt.subplots(figsize=(13, 9))
    dend = dendrogram(
        Z, labels=labels, ax=ax, leaf_rotation=90, leaf_font_size=10.5,
        color_threshold=ct, above_threshold_color="#B0B0B0",
    )

    # 叶标签按工具类别上色 (蓝 呈递 / 橙 免疫原) —— 覆盖 scipy 默认黑色叶标
    #  dend['ivl'] 是重排后的叶顺序; 反查 tool_key 判类别
    lab2tool = {tc.display_name(t) + (" (DTU)" if tc.is_dtu(t) else ""): t for t in tools}
    for tick in ax.get_xticklabels():
        t = lab2tool.get(tick.get_text())
        if t is not None:
            tick.set_color(tc.cat_color(t))
            tick.set_fontweight("bold")

    ax.set_ylabel("相异度  (1 − |Spearman ρ|)", fontsize=13)
    ax.set_title("工具打分层次聚类树状图（average linkage；树越矮合并=打分越像）",
                 fontsize=16, pad=12)
    ax.tick_params(axis="y", labelsize=11)

    # 图例: 叶标签颜色含义
    cat_handles = [Patch(facecolor=tc.C_PRESENT, edgecolor="none", label="呈递/结合类 (叶标签蓝)"),
                   Patch(facecolor=tc.C_IMMUNO, edgecolor="none", label="免疫原类 (叶标签橙)")]
    ax.legend(handles=cat_handles, loc="upper right", fontsize=11,
              title="工具类别", framealpha=0.95)

    fig.text(0.5, 0.005, tc.caption_note(n_pep, len(tools), dropped)
             + f"  linkage={method}；分簇上色阈值={'scipy默认(0.7·max)' if ct is None else f'{ct:.2f}'}",
             ha="center", va="bottom", fontsize=9.5, color="#555555")
    fig.tight_layout(rect=(0, 0.12, 1, 1))            # 底部留白给旋转叶标签 + 脚注
    tc.savefig_all(fig, out_png)
    plt.close(fig)
    print(f"[info] 入图工具={len(tools)}; 剔除={dropped}; linkage={method}")


def main():
    ap = argparse.ArgumentParser(description="选项2: 工具打分层次聚类树状图 (替代热图)")
    ap.add_argument("--input", default=None, help="pooled csv (默认 data/frozen/pooled_clean_9mer.csv)")
    ap.add_argument("--out", default=str(DEFAULT_OUT), help="输出 PNG 路径 (同名 PDF + paper/figures 自动)")
    ap.add_argument("--color-thresh", type=float, default=None,
                    help="dendrogram 分簇上色阈值 (相异度); 默认 None=scipy 默认 0.7·max")
    ap.add_argument("--method", default="average",
                    help="linkage 方法 (默认 average; 可 complete/ward 等)")
    args = ap.parse_args()
    draw(args.input, args.out, args.color_thresh, args.method)
    print("[DONE] plot_toolcorr_dendrogram 完成")


if __name__ == "__main__":
    main()
