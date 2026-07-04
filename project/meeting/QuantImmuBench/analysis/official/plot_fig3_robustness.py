#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
plot_fig3_robustness.py
=======================
服务: QuantImmuBench 论文 outline §3.3.4「Robustness（删 10% / 20%）」的**核心鲁棒性图 (图3)**。
lever = 把干净 canonical 上重跑的子采样鲁棒性汇总 (R6_robustness_official_summary.csv) 可视化,
       只读不重算。

它画什么 (一句话):
  12 种 fusion 法在**随机删 10% / 20% 突变**扰动下的稳健性双面板:
    · 上面板 (headline): win_rate_top1 —— 该法在 30 种子子采样中「12 法排第一」的比例;
      outline headline 口径, geomean 在 10% 与 20% 双双第一。
    · 下面板: 子采样均值 ρ̄ ± std (裸) + 满数据 (0% drop) 点估计菱形 + max-baseline 参考线;
      对照「满数据点估计 vs 子采样均值」(outline 反面教材: 点估计陷阱)。
  两面板 geomean 高亮 (金框 + ★ + x 标签加粗 + 竖向浅底纹)。

读哪个 csv 的哪些列:
  输入 = analysis/official/R6_robustness_official_summary.csv (--input 可覆写)
    每 method × drop_frac 一行:
    · method            方法名 (fusion: geomean/mean_rank/... 12 种; single: *_max 7 种)
    · kind              'fusion' | 'single'  (本图上面板只取 fusion; 下面板 max-baseline 取 single)
    · drop_frac         0.1 | 0.2  (删 10% / 20%; csv 无 0.0 行, 满数据在 full_data_rho 列)
    · full_data_rho     满数据 (0% drop) 裸点估计 ← 下面板菱形 (跨 drop 恒定)
    · mean_rho / std_rho 跨 30 种子子采样均值 / 标准差 (裸) ← 下面板条 + 误差棒
    · win_rate_top1     该 fusion 在多少比例 seed 里为 12 法中第一 ← 上面板条 (single 行为空)
    · n_seeds           子采样种子数 (=30)
  max-baseline 单工具 = netMHCpan_BA_max (csv 注释头明示; 下面板画其 mean_rho 参考线)。

跑法 (主线跑, coder 不跑):
  python analysis/official/plot_fig3_robustness.py
  python analysis/official/plot_fig3_robustness.py --input analysis/official/R6_robustness_official_summary.csv \
         --out analysis/official/figures/fig3_robustness.png

Windows 规范: matplotlib Agg + Microsoft YaHei + axes.unicode_minus=False; pathlib; 纯 numpy/pandas;
  300 dpi PNG + 同名 PDF + paper/figures pdf。
"""

import sys
import argparse
from pathlib import Path

import numpy as np
import pandas as pd

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.patches import Patch

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

plt.rcParams["font.sans-serif"] = ["Microsoft YaHei"]
plt.rcParams["axes.unicode_minus"] = False

HERE = Path(__file__).resolve().parent
FIG_DIR = HERE / "figures"
PAPER_FIG = HERE.parent.parent / "paper" / "figures"
DEFAULT_CSV = HERE / "R6_robustness_official_summary.csv"
DEFAULT_OUT = FIG_DIR / "fig3_robustness.png"

# ── 配色 (色盲友好 Okabe-Ito) ─────────────────────────────────────────────────
C_D10 = "#0072B2"       # drop 10% 蓝
C_D20 = "#E69F00"       # drop 20% 橙
C_HL = "#D55E00"        # geomean 高亮框 朱红
C_BASE = "#009E73"      # max-baseline 参考线 绿
C_FULL = "#333333"      # 满数据(0% drop)点估计菱形 深灰

HIGHLIGHT = "geomean"   # 高亮方法 (outline headline: geomean 双第一)
BASELINE_TOOL = "netMHCpan_BA_max"   # csv 注释头指定的 max-baseline 单工具


def _read_csv(path):
    p = Path(path)
    if not p.exists():
        sys.exit(f"[ERR] 源 csv 不存在: {p}")
    return pd.read_csv(p, comment="#", encoding="utf-8")


def make_fig(csv_path, out_path):
    df = _read_csv(csv_path)
    need = ["method", "kind", "drop_frac", "full_data_rho", "mean_rho", "std_rho",
            "win_rate_top1", "n_seeds"]
    for c in need:
        if c not in df.columns:
            sys.exit(f"[ERR] R6 summary 缺列 {c}; 实际={list(df.columns)}")
    for c in ("drop_frac", "full_data_rho", "mean_rho", "std_rho", "win_rate_top1"):
        df[c] = pd.to_numeric(df[c], errors="coerce")

    drops = sorted(df["drop_frac"].dropna().unique().tolist())   # 期望 [0.1, 0.2]
    if len(drops) < 1:
        sys.exit("[ERR] R6 summary 无 drop_frac 值")

    fus = df[df["kind"] == "fusion"].copy()
    if fus.empty:
        sys.exit("[ERR] R6 summary 无 fusion 行")

    # 方法排序: 按 win_rate_top1 跨 drop 均值降序 (高亮法自然靠前)
    order = (fus.groupby("method")["win_rate_top1"].mean()
             .sort_values(ascending=False).index.tolist())
    x = np.arange(len(order))
    nd = len(drops)
    width = 0.8 / nd
    drop_colors = [C_D10, C_D20, "#56B4E9", "#CC79A7"][:nd]      # 支持 >2 drop 兜底

    def _vals(sub_method_index, col):
        """取每 method 在各 drop 的列值 (缺失 → NaN)。返回 shape=(len(order), nd)。"""
        out = np.full((len(order), nd), np.nan)
        for i, m in enumerate(order):
            for j, d in enumerate(drops):
                r = df[(df["method"] == m) & (df["kind"] == "fusion")
                       & (np.isclose(df["drop_frac"], d))]
                if len(r):
                    out[i, j] = float(r.iloc[0][col])
        return out

    win = _vals(order, "win_rate_top1")
    meanr = _vals(order, "mean_rho")
    stdr = _vals(order, "std_rho")
    # full_data_rho 跨 drop 恒定 → 每 method 取一个 (任一 drop 行)
    fullr = np.array([
        float(df[(df["method"] == m) & (df["kind"] == "fusion")]["full_data_rho"].iloc[0])
        if len(df[(df["method"] == m) & (df["kind"] == "fusion")]) else np.nan
        for m in order])

    # max-baseline 单工具 (netMHCpan_BA_max) 各 drop 的 mean_rho (下面板参考线)
    base_mean = {}
    for d in drops:
        rb = df[(df["method"] == BASELINE_TOOL) & (df["kind"] == "single")
                & (np.isclose(df["drop_frac"], d))]
        base_mean[d] = float(rb.iloc[0]["mean_rho"]) if len(rb) else np.nan

    hl_idx = order.index(HIGHLIGHT) if HIGHLIGHT in order else None

    fig, (axA, axB) = plt.subplots(2, 1, figsize=(14, 10.5), sharex=True)

    # ── 上面板: win_rate_top1 ────────────────────────────────────────────────
    for j, d in enumerate(drops):
        bars = axA.bar(x + (j - (nd - 1) / 2) * width, win[:, j], width,
                       color=drop_colors[j], edgecolor="white", zorder=2,
                       label=f"删 {int(round(d*100))}%")
        for i, b in enumerate(bars):
            v = win[i, j]
            if np.isfinite(v):
                axA.text(b.get_x() + b.get_width() / 2, v + 0.012, f"{v:.3f}",
                         ha="center", va="bottom", fontsize=8.5,
                         color=drop_colors[j], rotation=90)
    axA.set_ylabel("win-rate top-1\n（12 法中排第一的种子比例）", fontsize=12)
    axA.set_ylim(0, max(0.75, float(np.nanmax(win)) + 0.12))
    axA.set_title("图3 · fusion 删突变鲁棒性（§3.3.4；30 种子子采样，geomean 高亮）",
                  fontsize=15, pad=10)
    axA.grid(axis="y", ls=":", color="#DDDDDD", zorder=0)
    axA.legend(loc="upper right", fontsize=11, title="扰动强度", framealpha=0.95)

    # ── 下面板: mean_rho ± std + 满数据菱形 + max-baseline 参考线 ─────────────
    for j, d in enumerate(drops):
        barsB = axB.bar(x + (j - (nd - 1) / 2) * width, meanr[:, j], width,
                        yerr=stdr[:, j], color=drop_colors[j], edgecolor="white", zorder=2,
                        error_kw=dict(ecolor="#444444", elinewidth=0.9, capsize=2.0),
                        label=f"删 {int(round(d*100))}% 子采样均值 $\\bar{{\\rho}}$±std")
        # 下面板每根柱加数值标签 (上面板 win-rate 已标, 这里补齐均值 ρ̄)。
        # 24 根柱 (12 法 × 2 drop) 防挤: 字号小(7) + 竖排(rot=90) + 置于误差棒顶上方,
        # 颜色跟对应 drop 便于左右柱区分; 格式 0.XX (2 位小数)。
        for i, b in enumerate(barsB):
            v = meanr[i, j]
            if np.isfinite(v):
                s_i = stdr[i, j] if np.isfinite(stdr[i, j]) else 0.0
                axB.text(b.get_x() + b.get_width() / 2, v + s_i + 0.006, f"{v:.2f}",
                         ha="center", va="bottom", fontsize=7, rotation=90,
                         color=drop_colors[j], zorder=6)
    # 满数据 (0% drop) 点估计: 每 method 一个菱形 (跨 drop 恒定)
    axB.scatter(x, fullr, marker="D", s=42, c=C_FULL, edgecolors="white",
                linewidths=0.6, zorder=5, label="满数据 (0% drop) 点估计")
    # max-baseline 参考线 (各 drop 一条虚线); 标签移到图外图例, 不在图内压柱 (原右端文字与柱重叠)
    for j, d in enumerate(drops):
        if np.isfinite(base_mean[d]):
            axB.axhline(base_mean[d], color=C_BASE, ls="--", lw=1.3, alpha=0.85, zorder=1)
    axB.set_ylabel("per-patient Spearman $\\bar{\\rho}$\n（子采样均值，裸口径）", fontsize=12)
    axB.grid(axis="y", ls=":", color="#DDDDDD", zorder=0)

    # x 轴 (共享)
    axB.set_xticks(x)
    axB.set_xticklabels(order, rotation=35, ha="right", fontsize=11)
    if hl_idx is not None:
        axB.get_xticklabels()[hl_idx].set_fontweight("bold")
        axB.get_xticklabels()[hl_idx].set_color(C_HL)

    # geomean 高亮: 两面板竖向浅底纹 + ★
    if hl_idx is not None:
        for axi in (axA, axB):
            axi.axvspan(hl_idx - 0.45, hl_idx + 0.45, color="#FFF3E0", zorder=0)
        ytop = axA.get_ylim()[1]
        axA.annotate("★ geomean", xy=(hl_idx, ytop * 0.96), ha="center", va="top",
                     fontsize=12, fontweight="bold", color=C_HL)

    # 图例挪到坐标轴外右侧 (原 loc="upper right" 在下面板右上角与柱/baseline 文字重叠);
    # 放图外后 bbox_inches="tight" 会完整收进, 且 baseline 线的标识由此图例给出, 不再图内压柱。
    axB.legend(loc="upper left", bbox_to_anchor=(1.005, 1.0), borderaxespad=0.0,
               fontsize=10, framealpha=0.95,
               handles=[
                   Patch(facecolor=C_D10, label=f"删 {int(round(drops[0]*100))}% 均值 $\\bar{{\\rho}}$±std"),
                   Patch(facecolor=C_D20, label=f"删 {int(round(drops[min(1,nd-1)]*100))}% 均值 $\\bar{{\\rho}}$±std")
                   if nd > 1 else Patch(facecolor=C_D10, label="均值 $\\bar{\\rho}$±std"),
                   Line2D([0], [0], marker="D", color="w", markerfacecolor=C_FULL,
                          markersize=8, label="满数据 (0% drop) 点估计"),
                   Line2D([0], [0], color=C_BASE, ls="--", lw=1.3,
                          label=f"{BASELINE_TOOL} max-baseline"),
               ])

    fig.text(0.5, 0.008,
             "win-rate top-1 (outline §3.3.4 headline 口径) = 该 fusion 法在多少比例子采样种子里为 12 法中第一；"
             "误差棒 = 30 种子 std。\n"
             "满数据点估计 (菱形) vs 子采样均值 (条): 前者可能虚高、后者更反映真信号 —— outline「点估计陷阱」反面教材。"
             "$\\bar{\\rho}$ = per-patient Spearman 跨患者 Fisher-z 等权 (裸口径)。",
             ha="center", va="bottom", fontsize=10, color="#555555")

    fig.tight_layout(rect=(0, 0.05, 1, 1))
    _save(fig, out_path)


def _save(fig, out_path):
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=300, bbox_inches="tight")
    out_pdf = out_path.with_suffix(".pdf")
    fig.savefig(out_pdf, bbox_inches="tight")
    PAPER_FIG.mkdir(parents=True, exist_ok=True)
    paper_pdf = PAPER_FIG / out_pdf.name
    fig.savefig(paper_pdf, bbox_inches="tight")
    plt.close(fig)
    print(f"[saved] {out_path}")
    print(f"[saved] {out_pdf}")
    print(f"[saved] {paper_pdf}")


def main():
    ap = argparse.ArgumentParser(description="图3 fusion 删突变鲁棒性双面板 (§3.3.4)")
    ap.add_argument("--input", default=str(DEFAULT_CSV),
                    help="R6_robustness_official_summary.csv 路径")
    ap.add_argument("--out", default=str(DEFAULT_OUT), help="输出 PNG 路径 (同目录同名存 PDF)")
    args = ap.parse_args()
    print(f"[info] 读: {args.input}")
    make_fig(args.input, args.out)
    print("[DONE] plot_fig3_robustness 完成")


if __name__ == "__main__":
    main()
