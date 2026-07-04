#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
plot_fig2_pooling.py
====================
服务: QuantImmuBench 论文 outline §3.2「单工具 × 4 种 pooling 比较」的**核心「洗牌」图 (图2)**。
lever = 把干净 canonical 上重跑的下游结果表 (R2_best_per_tool.csv) 可视化, 只读不重算。

它画什么 (一句话):
  每个工具一行的**哑铃图 (dumbbell)**: 零选择 max-pool 的 per-patient Spearman ρ (控肽长偏
  相关口径) → in-sample 最优 pooling 变体的 ρ, 两点连线 = pooling 带来的「洗牌」提升。
  按工具类别 (呈递/结合 vs 免疫原) 分色, 标注每工具最优 pooling 算子 + 提升量 Δ。
  表达 outline 核心 claim:「亲和/结合类靠聚合 (top-k 等权平均), 免疫原类取最强 (max 即峰)」。

读哪个 csv 的哪些列:
  输入 = analysis/official/R2_best_per_tool.csv (--input 可覆写)
    · Tool                     工具名 (y 轴一行)
    · pending_DTU              DTU 受限工具 (True → 名后标 " (DTU)")
    · max_rho_lenctrl          零选择 max-pool 的控肽长偏相关 ρ  ← 哑铃左端 (空心)
    · best_lenctrl             控肽长偏相关口径选出的最优 pooling 变体名 (如 topk_k20_a0p5)
    · best_lenctrl_rho         该最优 pooling 变体的控肽长偏相关 ρ ← 哑铃右端 (实心)
    · gain_lenctrl_over_maxlen best_lenctrl_rho − max_rho_lenctrl (提升量 Δ, 排序键)
  ★ 全程用 *_lenctrl (控肽长, ctrl=peplen) 列 = outline §3.2 明确「规律以 lenctrl 为准」的去伪迹口径;
    raw 口径 (best_raw/max_rho) 会捡回肽长混杂, 本图不用。

工具类别分类 (权威来源, 非本脚本臆断):
  PRESENTATION_TOOLS (8 呈递/结合) 逐字复用两处权威定义并交叉一致:
    (a) fig1 出图脚本 analysis/official/recompute_effN/plot_R1_effN.py 的 PRESENTATION_TOOLS;
    (b) §3.2 诊断脚本 analysis/official/compare_countclean_vs_dirty.py 的
        PRESENTATION_10 ∩ TOOLS_30 (outline §3.2, MixMHCpred/BigMHC_EL 未进 30 名册故交集=8)。
  其余 22 工具 = 免疫原类 (与 04_LOG「官方口径 8 呈递 + 22 免疫原」一致)。

跑法 (主线跑, coder 不跑):
  python analysis/official/plot_fig2_pooling.py
  python analysis/official/plot_fig2_pooling.py --input analysis/official/R2_best_per_tool.csv \
         --out analysis/official/figures/fig2_pooling_shuffle.png

Windows 规范: matplotlib Agg (无 GUI) + Microsoft YaHei + axes.unicode_minus=False (防豆腐块);
  pathlib; 纯 numpy/pandas 读表 (零 scipy); 300 dpi PNG + 同名 PDF (投稿矢量) + paper/figures pdf。
"""

import sys
import argparse
from pathlib import Path

import numpy as np
import pandas as pd

import matplotlib
matplotlib.use("Agg")                       # 无 GUI 后端 (只出文件)
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")     # Windows 必要: UTF-8 stdout

# ── 中文字体 (铁律: 防缺字豆腐块) ─────────────────────────────────────────────
plt.rcParams["font.sans-serif"] = ["Microsoft YaHei"]
plt.rcParams["axes.unicode_minus"] = False

HERE = Path(__file__).resolve().parent                 # analysis/official/
FIG_DIR = HERE / "figures"                             # 默认产物目录
PAPER_FIG = HERE.parent.parent / "paper" / "figures"   # 投稿矢量副本 (root/paper/figures)
DEFAULT_CSV = HERE / "R2_best_per_tool.csv"
DEFAULT_OUT = FIG_DIR / "fig2_pooling_shuffle.png"

# ── 配色 (逐字复用 fig1 plot_R1_effN.py, 色盲友好 Okabe-Ito) ───────────────────
C_PRESENT = "#0072B2"   # 呈递/结合类 蓝
C_IMMUNO = "#E69F00"    # 免疫原类 橙
C_MAX = "#FFFFFF"       # max 端 空心填白

# 呈递/结合类名单 (权威, 见文件头 docstring「工具类别分类」; 逐字同 fig1 + §3.2 诊断脚本)
PRESENTATION_TOOLS = {
    "HLAthena", "MHCflurry", "MHCnuggets", "MHCseqNet", "TransHLA",
    "netMHCpan_BA", "netMHCpan_EL", "netMHCstabpan",
}


def cat_of(tool):
    """工具类别: 呈递/结合 (PRESENTATION_TOOLS) 否则 免疫原。"""
    return "presentation" if tool in PRESENTATION_TOOLS else "immunogenic"


def cat_color(tool):
    return C_PRESENT if cat_of(tool) == "presentation" else C_IMMUNO


def _as_bool(series):
    """'True'/'1'/'yes' → True (大小写/空白无关)。"""
    return series.astype(str).str.strip().str.lower().isin(["true", "1", "yes"])


def _num(tok):
    """pooling 变体串里的数字段: 'p' 当小数点 (0p5 → 0.5, 0p03 → 0.03)。"""
    return tok.replace("p", ".")


def pretty_pool(variant):
    """pooling 变体串 → 可读标注 (纯解析 csv 字符串, 不硬编码数值)。
    max / topk_k{K}_a{A} / softmax_T{T} / rankdecay_g{G}。"""
    if not isinstance(variant, str) or variant.strip() == "":
        return "?"
    v = variant.strip()
    if v == "max":
        return "max"
    parts = v.split("_")
    fam = parts[0]
    try:
        if fam == "topk" and len(parts) >= 3:
            k = _num(parts[1][1:]); a = _num(parts[2][1:])
            return f"top-k (k={k}, α={a})"
        if fam == "softmax" and len(parts) >= 2:
            return f"softmax (T={_num(parts[1][1:])})"
        if fam == "rankdecay" and len(parts) >= 2:
            return f"rankdecay (γ={_num(parts[1][1:])})"
    except (IndexError, ValueError):
        return v
    return v


def _read_csv(path):
    p = Path(path)
    if not p.exists():
        sys.exit(f"[ERR] 源 csv 不存在: {p}")
    return pd.read_csv(p, comment="#", encoding="utf-8")   # csv 有 # 注释头, 必须跳过


def make_fig(csv_path, out_path):
    df = _read_csv(csv_path)
    need = ["Tool", "pending_DTU", "max_rho_lenctrl", "best_lenctrl",
            "best_lenctrl_rho", "gain_lenctrl_over_maxlen"]
    for c in need:
        if c not in df.columns:
            sys.exit(f"[ERR] R2_best_per_tool 缺列 {c}; 实际={list(df.columns)}")

    df["pending_DTU"] = _as_bool(df["pending_DTU"])
    for c in ("max_rho_lenctrl", "best_lenctrl_rho", "gain_lenctrl_over_maxlen"):
        df[c] = pd.to_numeric(df[c], errors="coerce")

    # 哑铃需两端点齐全; max-pool 退化 (常数列 → ρ=NaN, 如 DeepNetBim) 无左端 → 剔出并脚注
    dropped = df[df["max_rho_lenctrl"].isna() | df["best_lenctrl_rho"].isna()]["Tool"].tolist()
    work = df.dropna(subset=["max_rho_lenctrl", "best_lenctrl_rho"]).copy()
    if dropped:
        print(f"[warn] 略去 max-pool 退化/缺端点工具 (无控肽长 max ρ): {dropped}")

    # 排序: 按 pooling 提升量 (洗牌幅度) 降序 → 提升最大者在最上
    work = work.sort_values("gain_lenctrl_over_maxlen", ascending=False).reset_index(drop=True)

    tools = work["Tool"].tolist()
    max_rho = work["max_rho_lenctrl"].values.astype(float)
    best_rho = work["best_lenctrl_rho"].values.astype(float)
    gain = work["gain_lenctrl_over_maxlen"].values.astype(float)
    best_var = work["best_lenctrl"].tolist()
    dtu = work["pending_DTU"].values.astype(bool)

    n = len(tools)
    y = np.arange(n)[::-1]                     # 第 0 行画在最上
    colors = [cat_color(t) for t in tools]

    ylabels = [f"{t} (DTU)" if d else t for t, d in zip(tools, dtu)]

    fig, ax = plt.subplots(figsize=(12.5, 14))

    # 哑铃: 连线 + 左端 max(空心) + 右端 best(实心)
    for yi, mr, br, c in zip(y, max_rho, best_rho, colors):
        ax.plot([mr, br], [yi, yi], color=c, lw=2.4, alpha=0.55, zorder=2,
                solid_capstyle="round")
    ax.scatter(max_rho, y, s=70, facecolors=C_MAX, edgecolors=colors, linewidths=2.0,
               zorder=3, label="_max")
    ax.scatter(best_rho, y, s=95, c=colors, edgecolors="white", linewidths=1.0,
               zorder=4, label="_best")
    ax.axvline(0, color="#888888", ls="--", lw=1.0, zorder=1)

    # 右侧标注列: 最优 pooling 算子 + 提升量 Δ + (max→best 数值), 供 verifier 直接核
    finite_best = best_rho[np.isfinite(best_rho)]
    right_edge = float(np.nanmax(finite_best)) if len(finite_best) else 0.0
    op_x = right_edge + 0.03                    # 算子标注列
    for yi, mr, br, g, bv, c in zip(y, max_rho, best_rho, gain, best_var, colors):
        ax.text(op_x, yi, f"{pretty_pool(bv)}   Δ{g:+.3f}   [{mr:+.3f}→{br:+.3f}]",
                va="center", ha="left", fontsize=11, color=c, fontweight="bold")

    ax.set_yticks(y)
    ax.set_yticklabels(ylabels, fontsize=13)
    ax.set_xlabel("per-patient Spearman ρ（控肽长偏相关，ctrl=peplen；跨患者 Fisher-z 等权聚合）",
                  fontsize=13)
    ax.tick_params(axis="x", labelsize=12)
    ax.set_title("图2 · pooling「洗牌」效应：单工具 max-pool → in-sample 最优 pooling（§3.2；控肽长口径）",
                 fontsize=15, pad=12)

    finite_lo = np.concatenate([max_rho[np.isfinite(max_rho)], best_rho[np.isfinite(best_rho)]])
    xmin = min(-0.10, float(np.nanmin(finite_lo)) - 0.05) if len(finite_lo) else -0.10
    ax.set_xlim(xmin, op_x + 0.42)

    # 图例: 类别色 + max/best 标记形状
    legend_cat = [
        Line2D([0], [0], marker="o", color="w", markerfacecolor=C_PRESENT,
               markersize=11, label="呈递/结合类 (8)"),
        Line2D([0], [0], marker="o", color="w", markerfacecolor=C_IMMUNO,
               markersize=11, label="免疫原类 (22)"),
        Line2D([0], [0], marker="o", color="w", markerfacecolor="white",
               markeredgecolor="#555555", markeredgewidth=2.0, markersize=11,
               label="零选择 max-pool（左端）"),
        Line2D([0], [0], marker="o", color="w", markerfacecolor="#555555",
               markersize=11, label="in-sample 最优 pooling（右端）"),
    ]
    # 图例定位自检 (为何放坐标轴外下方 fig.legend 而非 loc="lower right"):
    #   Δ 标注列占满整个右侧 (每行右端 op_x 处都有 "算子 Δ [max→best]" 文字),
    #   故图例放右侧任意 loc 都会压住 HLAthena/IMPROVE 等末行的 Δ 数值。
    #   左侧散布哑铃点、上方是标题、下方是脚注 → 唯一确定空的区域 = 坐标轴外正下方、
    #   脚注上方的图外条带。用 fig.legend(figure 坐标, 与 14 英寸高无关) 放这里, 两行 ncol=2,
    #   下面 tight_layout rect 底部留 0.14 给「图例 + 脚注」双层, 保证不压任何点/文字/脚注。
    fig.legend(handles=legend_cat, loc="lower center", bbox_to_anchor=(0.5, 0.058),
               ncol=2, fontsize=11, title="类别 / 标记", framealpha=0.95,
               columnspacing=2.2, handletextpad=0.5)

    fig.text(0.5, 0.008,
             "哑铃左端 = 零选择 max-pool 的控肽长偏相关 ρ；右端 = in-sample 选出的最优 pooling 变体 ρ；"
             "Δ = 提升量 (best − max)。行按 Δ 降序。\n"
             "口径 = per-patient Spearman(工具打分, Elispot) 偏相关控 peplen，跨患者 Fisher-z 等权聚合 "
             "(outline §3.2 规律以 lenctrl 为准，去肽长伪迹)。名后 (DTU) = DTU 受限工具。"
             + (f"  略去 max-pool 退化工具: {', '.join(dropped)}。" if dropped else ""),
             ha="center", va="bottom", fontsize=10, color="#555555")

    fig.tight_layout(rect=(0, 0.14, 1, 1))   # 底部 14% 留给图外图例(上) + 脚注(下)
    _save(fig, out_path)


def _save(fig, out_path):
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=300, bbox_inches="tight")           # 300 dpi PNG
    out_pdf = out_path.with_suffix(".pdf")
    fig.savefig(out_pdf, bbox_inches="tight")                     # 同名矢量 PDF
    PAPER_FIG.mkdir(parents=True, exist_ok=True)
    paper_pdf = PAPER_FIG / out_pdf.name
    fig.savefig(paper_pdf, bbox_inches="tight")                   # 投稿副本
    plt.close(fig)
    print(f"[saved] {out_path}")
    print(f"[saved] {out_pdf}")
    print(f"[saved] {paper_pdf}")


def main():
    ap = argparse.ArgumentParser(description="图2 pooling 洗哑铃图 (§3.2, 控肽长口径)")
    ap.add_argument("--input", default=str(DEFAULT_CSV), help="R2_best_per_tool.csv 路径")
    ap.add_argument("--out", default=str(DEFAULT_OUT), help="输出 PNG 路径 (同目录同名存 PDF)")
    args = ap.parse_args()
    print(f"[info] 读: {args.input}")
    make_fig(args.input, args.out)
    print("[DONE] plot_fig2_pooling 完成")


if __name__ == "__main__":
    main()
