#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
plot_toolcorr_mds.py — 袁老师选项【第 4 种：MDS 工具地图 (multidimensional scaling)】
==================================================================================
服务: QuantImmuBench 「工具间打分相关结构可视化(替代热图)」lever。四张候选图之一, 给袁老师挑。

读什么列 → 算什么 → 画什么图:
  · 读 data/frozen/pooled_clean_9mer.csv 的 30 个 <tool>_max 列 (共享底座 _toolcorr_common)
  · 跨 130 肽算 Spearman 相关阵 → 剔全 NaN 退化工具 (DeepNetBim) → ~29×29
  · 相异度 = 1 − |相关| → sklearn.manifold.MDS(dissimilarity='precomputed', random_state 固定)
    降到 2D → 每工具一个散点。**图上两点越近 = 两工具打分越相似。**
  · 点按类别上色 (蓝 呈递 / 橙 免疫原), 标工具名 (下划线→连字符 + DTU); 防重叠用手动 offset
    (adjustText 若装可用则用其自动避让, 否则 fallback 手动, 不硬依赖)。
  · 可叠 KMeans(k) 上色/画凸包显簇 (--kmeans)。

为什么是 MDS 地图: 把 29 维相关结构**压到一张 2D 散点地图**, 全局「谁离谁近」一眼看清,
  比热图更直觉地展示工具的整体版图与聚集区。

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
from matplotlib.lines import Line2D

from sklearn.manifold import MDS
from sklearn.cluster import KMeans

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")     # Windows 必要: UTF-8 stdout

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import _toolcorr_common as tc                # noqa: E402  (共享底座: 数据/配色/存图)

tc.apply_matplotlib_style(plt)

DEFAULT_OUT = tc.FIG_DIR / "fig_toolcorr_mds.png"

# adjustText 可选 (未装则手动 offset, 不硬依赖) —— TODO: 若主线环境未装 adjustText, 自动走 fallback
try:
    from adjustText import adjust_text
    _HAS_ADJUSTTEXT = True
except Exception:
    _HAS_ADJUSTTEXT = False


def draw(input_path, out_png, seed, kmeans_k):
    scores = tc.load_max_scores(input_path)
    corr, dropped = tc.spearman_corr(scores)
    tools = list(corr.columns)
    n_pep = len(scores)

    dist = tc.distance_from_corr(corr)               # 1 − |ρ|, 预计算相异度
    mds = MDS(n_components=2, dissimilarity="precomputed", random_state=seed,
              n_init=8, max_iter=500, normalized_stress="auto")
    xy = mds.fit_transform(dist)                     # (n, 2) 坐标
    stress = float(mds.stress_)

    fig, ax = plt.subplots(figsize=(12, 10))
    colors = [tc.cat_color(t) for t in tools]

    # 可选 KMeans 显簇: 画每簇凸包背景 (仅示意聚集, 不改点的类别色)
    if kmeans_k and kmeans_k >= 2:
        km = KMeans(n_clusters=min(kmeans_k, len(tools)), random_state=seed, n_init=10)
        lab = km.fit_predict(xy)
        try:
            from scipy.spatial import ConvexHull
            for c in np.unique(lab):
                pts = xy[lab == c]
                if len(pts) >= 3:
                    hull = ConvexHull(pts)
                    poly = pts[hull.vertices]
                    ax.fill(poly[:, 0], poly[:, 1], alpha=0.07, color="#888888", zorder=0)
        except Exception:
            pass                                     # 无 scipy.spatial 就跳过背景, 不阻断主图

    ax.scatter(xy[:, 0], xy[:, 1], s=180, c=colors, edgecolors="white",
               linewidths=1.4, zorder=3)

    # 工具名标注
    labels = [tc.display_name(t) + (" (DTU)" if tc.is_dtu(t) else "") for t in tools]
    texts = []
    for (x, y), lab, c in zip(xy, labels, colors):
        texts.append(ax.text(x, y, lab, fontsize=9.5, color=c, fontweight="bold",
                             ha="center", va="center", zorder=4))
    if _HAS_ADJUSTTEXT:
        adjust_text(texts, ax=ax,
                    arrowprops=dict(arrowstyle="-", color="#BBBBBB", lw=0.6))
    else:
        # fallback: 简单向上 offset + 细引线, 减轻重叠 (不引入外部依赖)
        for (x, y), t in zip(xy, texts):
            t.set_position((x, y + (np.ptp(xy[:, 1]) * 0.028)))
            t.set_va("bottom")

    ax.set_xlabel("MDS 维 1", fontsize=12)
    ax.set_ylabel("MDS 维 2", fontsize=12)
    ax.set_title("工具打分 MDS 地图（距离近 = 两工具打分越相似）", fontsize=16, pad=12)
    ax.axhline(0, color="#DDDDDD", lw=0.8, zorder=0)
    ax.axvline(0, color="#DDDDDD", lw=0.8, zorder=0)

    cat_handles = [Patch(facecolor=tc.C_PRESENT, edgecolor="white", label="呈递/结合类"),
                   Patch(facecolor=tc.C_IMMUNO, edgecolor="white", label="免疫原类")]
    if kmeans_k and kmeans_k >= 2:
        cat_handles.append(Line2D([0], [0], marker="s", color="none",
                                  markerfacecolor="#888888", alpha=0.3, markersize=12,
                                  label=f"KMeans(k={kmeans_k}) 簇背景"))
    ax.legend(handles=cat_handles, loc="best", fontsize=11, title="工具类别",
              framealpha=0.95)
    ax.text(0.99, 0.01, f"MDS stress={stress:.2f}"
            + ("" if _HAS_ADJUSTTEXT else "  (标签手动 offset)"),
            transform=ax.transAxes, ha="right", va="bottom", fontsize=9,
            color="#888888", style="italic")

    fig.text(0.5, 0.005, tc.caption_note(n_pep, len(tools), dropped)
             + "  MDS(dissimilarity=1−|ρ|, precomputed); 坐标轴无绝对含义, 只看点间相对距离。",
             ha="center", va="bottom", fontsize=9.3, color="#555555")
    fig.tight_layout(rect=(0, 0.05, 1, 1))
    tc.savefig_all(fig, out_png)
    plt.close(fig)
    print(f"[info] 入图工具={len(tools)}; 剔除={dropped}; MDS stress={stress:.3f}; "
          f"adjustText={_HAS_ADJUSTTEXT}; kmeans_k={kmeans_k}")


def main():
    ap = argparse.ArgumentParser(description="选项4: 工具打分 MDS 地图 (替代热图)")
    ap.add_argument("--input", default=None, help="pooled csv (默认 data/frozen/pooled_clean_9mer.csv)")
    ap.add_argument("--out", default=str(DEFAULT_OUT), help="输出 PNG 路径 (同名 PDF + paper/figures 自动)")
    ap.add_argument("--seed", type=int, default=42, help="MDS/KMeans 随机种子 (复现零偏离, 默认 42)")
    ap.add_argument("--kmeans", type=int, default=0,
                    help="叠 KMeans 显簇的簇数 (默认 0=不叠; 建议 3~4)")
    args = ap.parse_args()
    draw(args.input, args.out, args.seed, args.kmeans)
    print("[DONE] plot_toolcorr_mds 完成")


if __name__ == "__main__":
    main()
