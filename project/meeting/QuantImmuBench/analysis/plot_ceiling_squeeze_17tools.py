#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
plot_ceiling_squeeze_17tools.py
服务: quantimmu-bench / lever=天花板夹逼图（PPT 头条图）

================== 数字真源 ==================
  reference/INTEGRATED_FINDINGS.md §2.3:
    理论天花板(THEORY_quant 低置信): ρ_max ≈ 0.4–0.6
    I-fusion 点估: 0.328–0.334
      fixavg_surv6  DS2_main fisherz_rho=0.3281 (analysis/fusion_methods.csv 行8)
      rankmean_surv6 DS2_main fisherz_rho=0.3336 (analysis/fusion_methods.csv 行10)
    F-pilot 集成: 0.328 (reference/INTEGRATED_FINDINGS.md §2.3)
    朱同学融合: 0.43 (p=0.70) (reference/INTEGRATED_FINDINGS.md §2.3)
    夹逼区标注: 0.33–0.43 (§2.3 "四个独立来源全落在 0.33–0.43")

  工具 best_rho_countsafe:
    analysis/pooling_best_per_tool_17tools.csv (pooling_sweep_17tools.py 产出)

================== 运行 ==================
  python analysis/plot_ceiling_squeeze_17tools.py

================== 产出 ==================
  analysis/figures/spearman_ceiling_squeeze_17tools.{png,pdf}
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

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent

# ── 图中所用参考数字（全部来自 reference/INTEGRATED_FINDINGS.md §2.3 + fusion_methods.csv）
# 数字真源见文件头注释，已 Bash 核 CSV 确认
THEORY_LO    = 0.40   # 理论天花板下沿（低置信）
THEORY_HI    = 0.60   # 理论天花板上沿（低置信）
ZHU_FUSION   = 0.43   # 朱同学融合 (p=0.70), INTEGRATED_FINDINGS §2.3
I_FUSION_LO  = 0.3281 # fixavg_surv6 DS2_main, fusion_methods.csv line8
I_FUSION_HI  = 0.3336 # rankmean_surv6 DS2_main, fusion_methods.csv line10
F_PILOT      = 0.328  # QuantImmune pilot stacking, INTEGRATED_FINDINGS §2.3

SQUEEZE_LO   = 0.33   # 夹逼区下沿 (§2.3 "全落在 0.33–0.43")
SQUEEZE_HI   = 0.43   # 夹逼区上沿 (= 朱同学融合)

# 新工具集
NEW_TOOLS = {
    "BigMHC", "CNNeo", "IEDB_Calis", "MHCflurry_presentation",
    "MHCflurry_affinity_neg", "Repitope", "netmhcpan_ba", "TSCAPE",
}

# DTU pending 工具（需许可）
DTU_PENDING = {"netmhcpan_ba", "TSCAPE"}

# geomean 为 count-safe 最优的工具（min-shift 实现，exploratory caveat）
GEOMEAN_TOOLS_SET = set()  # 填充于 main()


def main():
    # ── 读 best_per_tool ────────────────────────────────────────────────────
    bpt_path = HERE / "pooling_best_per_tool_17tools.csv"
    if not bpt_path.exists():
        raise SystemExit(f"[ERR] 找不到 {bpt_path}，先跑 pooling_sweep_17tools.py")
    bpt = pd.read_csv(bpt_path)

    # 仅保留有有效 count-safe rho 的工具
    bpt = bpt.dropna(subset=["best_rho_countsafe"]).copy()
    # 按 best_rho_countsafe 降序
    bpt = bpt.sort_values("best_rho_countsafe", ascending=False).reset_index(drop=True)

    # 记录 geomean 工具（best_pooling_countsafe 列）
    for _, row in bpt.iterrows():
        if str(row["best_pooling_countsafe"]).lower() == "geomean":
            GEOMEAN_TOOLS_SET.add(row["Tool"])

    n = len(bpt)
    x = np.arange(n)

    # ── 颜色方案 ────────────────────────────────────────────────────────────
    COLORS = {
        "old_positive": "#3399cc",      # 旧工具，正向信号
        "new_positive": "#1a6faf",      # 新工具，正向信号
        "old_negative": "#aaaaaa",      # 旧工具，负/零 (视觉降噪)
        "new_negative": "#888888",      # 新工具，负
        "proxy":        "#3399cc",      # presentation proxy (HLAthena)
        "dtu":          "#e68a00",      # DTU pending（橙色警示）
    }

    def bar_color(row):
        t = row["Tool"]
        rho = row["best_rho_countsafe"]
        if t in DTU_PENDING:
            return COLORS["dtu"]
        if t in NEW_TOOLS:
            return COLORS["new_positive"] if rho >= 0 else COLORS["new_negative"]
        return COLORS["old_positive"] if rho >= 0 else COLORS["old_negative"]

    bar_colors = [bar_color(row) for _, row in bpt.iterrows()]

    # ── 图形尺寸 ────────────────────────────────────────────────────────────
    fig_w = max(14, n * 0.78 + 3)
    fig_h = 7.5
    fig, ax = plt.subplots(figsize=(fig_w, fig_h))

    # ── Background 1: Theory ceiling band (light grey) ───────────────────
    ax.axhspan(THEORY_LO, THEORY_HI, color="#dddddd", alpha=0.45, zorder=0,
               label=f"Theory ceiling THEORY_quant (low-confidence) rho={THEORY_LO}-{THEORY_HI}")
    ax.text(n - 0.3, (THEORY_LO + THEORY_HI) / 2,
            f"Theory ceiling\n(low confidence)\nrho={THEORY_LO}-{THEORY_HI}",
            ha="right", va="center", fontsize=7.5, color="#888888", style="italic")

    # ── Background 2: Squeeze zone (light yellow) ─────────────────────
    ax.axhspan(SQUEEZE_LO, SQUEEZE_HI, color="#fff3cd", alpha=0.6, zorder=0)
    ax.text(-0.6, (SQUEEZE_LO + SQUEEZE_HI) / 2,
            f"Signal ceiling\npep+HLA\nrho~{SQUEEZE_LO}-{SQUEEZE_HI}",
            ha="left", va="center", fontsize=8, color="#9a6b00",
            fontweight="bold",
            bbox=dict(boxstyle="round,pad=0.3", facecolor="#fff3cd",
                      edgecolor="#e6a817", alpha=0.9))

    # ── Reference lines ────────────────────────────────────────────────
    # Zhu et al. ensemble 0.43
    ax.axhline(ZHU_FUSION, color="#d04a02", lw=1.8, ls="-", zorder=3,
               label=f"Zhu et al. ensemble rho={ZHU_FUSION} (p=0.70, §2.3)")
    ax.text(n - 0.2, ZHU_FUSION + 0.008,
            f"Zhu et al. ensemble {ZHU_FUSION}", ha="right", va="bottom",
            fontsize=8.5, color="#d04a02", fontweight="bold")

    # I-fusion range (fixavg ~ rankmean)
    ax.axhline(I_FUSION_LO, color="#2060a8", lw=1.4, ls="--", zorder=3,
               label=f"I-fusion fixavg {I_FUSION_LO:.4f}")
    ax.axhline(I_FUSION_HI, color="#2060a8", lw=1.4, ls=":", zorder=3,
               label=f"I-fusion rankmean {I_FUSION_HI:.4f}")
    ax.text(0.2, I_FUSION_HI + 0.006,
            f"I-fusion {I_FUSION_LO:.3f}-{I_FUSION_HI:.3f}  /  F-pilot {F_PILOT:.3f}",
            ha="left", va="bottom", fontsize=8, color="#2060a8", fontweight="bold")

    # F-pilot (nearly same as fixavg, label only, no extra line)

    # ── 条形 ────────────────────────────────────────────────────────────────
    bars = ax.bar(x, bpt["best_rho_countsafe"], color=bar_colors,
                  width=0.65, alpha=0.88, zorder=2, edgecolor="white", linewidth=0.5)

    # proxy 工具（HLAthena）用虚线边框区分
    for i, (_, row) in enumerate(bpt.iterrows()):
        if row["Tool"] == "HLAthena":
            bars[i].set_linestyle("--")
            bars[i].set_edgecolor("#3399cc")
            bars[i].set_linewidth(1.8)
            bars[i].set_alpha(0.55)

    # ── 数值标注（高信号工具 + 关键新工具）───────────────────────────────
    # 标注阈值：abs(rho) >= 0.15 或工具在关注列表
    LABEL_TOOLS = {"netmhcpan_ba", "PredIG", "HLAthena", "IMPROVE", "PRIME",
                   "TSCAPE", "MHCflurry_affinity_neg"}
    for i, (_, row) in enumerate(bpt.iterrows()):
        t   = row["Tool"]
        rho = row["best_rho_countsafe"]
        pool= row["best_pooling_countsafe"]
        if abs(rho) < 0.15 and t not in LABEL_TOOLS:
            continue

        y_offset = 0.010 if rho >= 0 else -0.018
        va = "bottom" if rho >= 0 else "top"

        # 构建标注文字
        note = f"ρ={rho:.3f}\n({pool})"
        if t in GEOMEAN_TOOLS_SET:
            note += " †"
        if t in DTU_PENDING:
            note += " [DTU]"
        if t == "HLAthena":
            note += "\n[proxy]"

        ax.text(i, rho + y_offset, note,
                ha="center", va=va, fontsize=7.2,
                color="#cc2200" if rho < 0 else "#1a3a6b",
                fontweight="bold" if abs(rho) >= 0.28 else "normal")

    # ── X 轴 ────────────────────────────────────────────────────────────────
    ax.set_xticks(x)
    xlabels = []
    for _, row in bpt.iterrows():
        t = row["Tool"]
        lbl = t
        if t == "HLAthena":
            lbl = "HLAthena\n(proxy)"
        elif t in NEW_TOOLS:
            lbl = f"{t}*"
        xlabels.append(lbl)
    ax.set_xticklabels(xlabels, fontsize=8.5, rotation=35, ha="right")

    # ── Y axis ───────────────────────────────────────────────────────────────
    ax.set_ylabel("Spearman rho vs ELISpot (global, count-safe best pooling)",
                  fontsize=10)
    ax.axhline(0, color="black", lw=0.8, zorder=2)
    ymin = min(-0.35, bpt["best_rho_countsafe"].min() - 0.05)
    ymax = max(0.65, THEORY_HI + 0.05)
    ax.set_ylim(ymin, ymax)
    ax.set_xlim(-1.0, n)

    # ── 标题 ────────────────────────────────────────────────────────────────
    ax.set_title(
        "Ceiling Squeeze — 17-Tool Count-Safe Spearman vs Fusion Benchmarks & Theory\n"
        "Four independent sources converge: signal ceiling rho ~ 0.33-0.43 (DS2, 101 peptides, 9 patients)",
        fontsize=11.5, pad=10, fontweight="bold"
    )

    # ── Legend ───────────────────────────────────────────────────────────────
    legend_handles = [
        mpatches.Patch(color=COLORS["old_positive"], alpha=0.88, label="Old tool (positive signal)"),
        mpatches.Patch(color=COLORS["new_positive"], alpha=0.88, label="New tool* (positive signal)"),
        mpatches.Patch(color=COLORS["dtu"],          alpha=0.88, label="New tool [DTU pending] (netmhcpan_ba/TSCAPE)"),
        mpatches.Patch(facecolor=COLORS["old_positive"], alpha=0.45,
                       edgecolor=COLORS["old_positive"], linestyle="--",
                       linewidth=1.5, label="HLAthena (presentation proxy, dashed border)"),
        Line2D([0],[0], color="#d04a02", lw=1.8, ls="-",  label=f"Zhu et al. ensemble rho={ZHU_FUSION} (p=0.70)"),
        Line2D([0],[0], color="#2060a8", lw=1.4, ls="--", label=f"I-fusion fixavg rho={I_FUSION_LO:.4f}"),
        Line2D([0],[0], color="#2060a8", lw=1.4, ls=":",  label=f"I-fusion rankmean rho={I_FUSION_HI:.4f}  /  F-pilot rho={F_PILOT}"),
        mpatches.Patch(color="#dddddd", alpha=0.55, label=f"Theory ceiling THEORY_quant (low-conf) rho={THEORY_LO}-{THEORY_HI}"),
        mpatches.Patch(color="#fff3cd", alpha=0.8,
                       edgecolor="#e6a817", label=f"Signal ceiling zone rho~{SQUEEZE_LO}-{SQUEEZE_HI}"),
    ]
    ax.legend(handles=legend_handles, fontsize=7.8, loc="upper right",
              framealpha=0.92, ncol=1, handlelength=1.8)

    # ── Footnote ─────────────────────────────────────────────────────────────
    footnotes = (
        "† geomean: min-shift applied to ensure positivity; absolute scale changes but Spearman (rank-based) unaffected. "
        "Exploratory only — robust primary metric: mean/top3mean.\n"
        "[DTU] pending consent: netmhcpan_ba (DTU redistribution restriction) / TSCAPE (CC-BY-NC-ND). "
        "* New tools (17-tool wave). "
        "Sources: INTEGRATED_FINDINGS.md §2.3 (Zhu0.43/I-fusion0.328-0.334/F-pilot0.328/theory0.4-0.6) + "
        "pooling_best_per_tool_17tools.csv (count-safe best rho)."
    )
    fig.text(0.01, 0.002, footnotes, fontsize=6.8, color="#555555",
             va="bottom", wrap=True)

    plt.tight_layout(rect=[0, 0.09, 1, 1])

    # ── 保存 ────────────────────────────────────────────────────────────────
    fig_dir = HERE / "figures"
    fig_dir.mkdir(exist_ok=True)
    for ext in ["png", "pdf"]:
        p = fig_dir / f"spearman_ceiling_squeeze_17tools.{ext}"
        fig.savefig(p, dpi=150, bbox_inches="tight")
        print(f"[saved] {p}")
    plt.close(fig)
    print("[DONE]")


if __name__ == "__main__":
    main()
