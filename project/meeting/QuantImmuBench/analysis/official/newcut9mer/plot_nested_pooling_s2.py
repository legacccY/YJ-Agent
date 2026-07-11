# -*- coding: utf-8 -*-
"""
plot_nested_pooling_s2.py — 新切 9mer 融合层「nested pooling selection」三图 (§3.3 报告配图)
================================================================================
服务: QuantImmuBench §3.3 融合层报告 —— nested pooling selection 的算子对比 / 成员选择过拟合 /
      选择梯队三张图。lever = nested pooling selection 结果可视化。

★ 隔离约束: 只写 analysis/official/newcut9mer/figures/ (脚本内 mkdir), 绝不碰 paper/figures。
  输出【覆盖】三个 PNG + 同名 PDF (引擎按固定名嵌入):
    figures/figE_newcut_fusion_authoritative.png   (图3, 8 聚合算子交叉验证 ρ)
    figures/figA_newcut_fusion_no_net_gain.png     (图4, k-curve 成员选择过拟合)
    figures/figB_newcut_selection_ladder.png       (图5, 选择梯队, 新文件名)

数据源:
  · figE / figB 用固定常量 (来自 nested_pooling_selection.py 已核 stdout, 见各图注释, 照抄不改)。
  · figA 读真实文件 analysis/fusion_cv/newcut9mer/k_curve.csv (列 k/caliber/select_mode/
    cv_rho/oracle_rho), 按真实列名取 raw + greedy_to_k 行。

Windows 规范: matplotlib Agg + Microsoft YaHei + axes.unicode_minus=False; dpi=150 白底简洁 (顶会审美);
  纯 numpy/pandas/matplotlib, 零 GPU。字体缺失时 matplotlib 仅 warning, 不影响出图。
跑法 (主线跑, 我不跑): python analysis/official/newcut9mer/plot_nested_pooling_s2.py
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")                                   # 无 GUI 后端 (只出文件)
import matplotlib.pyplot as plt                          # noqa: E402
from matplotlib.lines import Line2D                       # noqa: E402
from matplotlib.patches import Patch                      # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

matplotlib.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "DejaVu Sans"]
matplotlib.rcParams["axes.unicode_minus"] = False       # 负 ρ 用 ASCII '-', 防负号豆腐块

# ── 目录 ────────────────────────────────────────────────────────────────────────
HERE = Path(__file__).resolve().parent                  # analysis/official/newcut9mer/
ROOT = HERE.parents[2]                                  # QuantImmuBench/
FUSION_DIR = ROOT / "analysis" / "fusion_cv" / "newcut9mer"
FIG_DIR = HERE / "figures"                              # ★ 唯一输出目录 (不碰 paper/figures)

TAG = "固定窗口9肽 · 8位有效患者 · 9折LOPO"
SINGLE_BASELINE = 0.372                                  # 单工具 netMHCpan-BA_max (红虚线基线)

# ── 中性配色 (顶会审美) ──────────────────────────────────────────────────────────
C_CV = "#1f77b4"        # 交叉验证实际
C_ORACLE = "#d62728"    # 样本内 oracle
C_HL = "#2ca02c"        # 高亮 (名次平均类 / 只选pooling)
C_MUTE = "#9aa0a6"      # 灰 (次要)
C_BASE = "#d62728"      # 单工具基线红虚线


def _save(fig, stem):
    """写 dpi=150 PNG (覆盖) + 同名 PDF 到 figures/。"""
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    png, pdf = FIG_DIR / f"{stem}.png", FIG_DIR / f"{stem}.pdf"
    fig.savefig(png, dpi=150, bbox_inches="tight", facecolor="white")
    fig.savefig(pdf, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print(f"[saved] {png}")
    print(f"[saved] {pdf}")


# ═══════════════════════════════════════════════════════════════════════════════
# 图 3 (figE) — 同一面板 8 种聚合函数的交叉验证 ρ
#   值来自 nested_pooling_selection.py (4) 段已核 stdout, 照抄不改:
#   weighted_mean_rank 0.4516 / geomean 0.4510 / mean_rank 0.4508 / median 0.3845 /
#   powmean 0.3831 / min 0.3704 / max 0.3353 / softmax_rank 0.3128; 每折选算子 0.3900。
#   名次平均三兄弟 (weighted_mean_rank/geomean/mean_rank ≈0.451) 高亮; 单工具 0.372 红虚线。
# ═══════════════════════════════════════════════════════════════════════════════
OP_CV = [                       # (中文标签, 内部名, CV ρ) —— 按 CV 降序
    ("加权平均名次", "weighted_mean_rank", 0.4516),
    ("几何平均",     "geomean",            0.4510),
    ("平均名次",     "mean_rank",          0.4508),
    ("中位数",       "median",             0.3845),
    ("幂平均",       "powmean",            0.3831),
    ("取最低",       "min",                0.3704),
    ("取最高",       "max",                0.3353),
    ("指数加权名次", "softmax_rank",       0.3128),
]
OP_SELECT_CV = 0.3900           # 每折选算子 (多搜一维) 的 CV
HL_OPS = {"weighted_mean_rank", "geomean", "mean_rank"}   # 名次平均三兄弟高亮


def fig_e():
    labels = [x[0] for x in OP_CV] + ["每折选聚合函数"]
    names = [x[1] for x in OP_CV] + ["__select__"]
    vals = [x[2] for x in OP_CV] + [OP_SELECT_CV]
    colors = []
    for nm in names:
        if nm in HL_OPS:
            colors.append(C_HL)
        elif nm == "__select__":
            colors.append(C_MUTE)
        else:
            colors.append(C_MUTE)

    x = np.arange(len(labels))
    fig, ax = plt.subplots(figsize=(9.0, 5.0))
    bars = ax.bar(x, vals, color=colors, alpha=0.92, width=0.66, edgecolor="white", linewidth=0.6)
    # 每折选算子柱加斜纹, 与固定算子区分
    bars[-1].set_hatch("//")
    bars[-1].set_edgecolor("#555")

    ax.axhline(SINGLE_BASELINE, color=C_BASE, lw=1.8, ls="--",
               label=f"单工具 netMHCpan-BA = {SINGLE_BASELINE:.3f}")
    for xi, v in zip(x, vals):
        ax.text(xi, v + 0.006, f"{v:.4f}", ha="center", va="bottom", fontsize=8.5)

    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=30, ha="right", fontsize=9)
    ax.set_ylabel("患者内秩相关 ρ (嵌套合成方式 交叉验证)")
    ax.set_ylim(0, max(vals) + 0.06)
    ax.set_title(f"同一面板 8 种聚合函数的交叉验证 ρ ({TAG})\n"
                 f"绿色 = 名次平均类 (≈0.451, 并列最高); 斜纹 = 每折另选聚合函数 (未涨)", fontsize=10.5)
    ax.legend(handles=[Patch(color=C_HL, label="名次平均类 (最高)"),
                       Patch(color=C_MUTE, label="其余聚合函数"),
                       Line2D([0], [0], color=C_BASE, lw=1.8, ls="--",
                              label=f"单工具基线 {SINGLE_BASELINE:.3f}")],
              loc="upper right", fontsize=8.5, framealpha=0.95)
    ax.spines[["top", "right"]].set_visible(False)
    _save(fig, "figE_newcut_fusion_authoritative")


# ═══════════════════════════════════════════════════════════════════════════════
# 图 4 (figA) — k-curve: 成员选择过拟合 (CV 峰在 k=1, 加工具后下降)
#   读 analysis/fusion_cv/newcut9mer/k_curve.csv (raw + greedy_to_k); cv_rho 蓝 / oracle_rho 红。
# ═══════════════════════════════════════════════════════════════════════════════
def fig_a():
    kc = pd.read_csv(FUSION_DIR / "k_curve.csv", comment="#", encoding="utf-8")
    kc = kc[(kc["caliber"] == "raw") & (kc["select_mode"] == "greedy_to_k")].copy()
    kc = kc.sort_values("k")
    k = pd.to_numeric(kc["k"], errors="coerce").values.astype(float)
    cv = pd.to_numeric(kc["cv_rho"], errors="coerce").values.astype(float)
    orc = pd.to_numeric(kc["oracle_rho"], errors="coerce").values.astype(float)

    fig, ax = plt.subplots(figsize=(7.6, 5.0))
    ax.plot(k, cv, "-o", color=C_CV, lw=2, ms=6, label="交叉验证估计 (无泄漏)")
    ax.plot(k, orc, "-s", color=C_ORACLE, lw=2, ms=6, label="样本内理想上界")
    good = (~np.isnan(cv)) & (~np.isnan(orc))
    ax.fill_between(k, cv, orc, where=good & (orc >= cv), color=C_ORACLE, alpha=0.10)
    ax.axhline(SINGLE_BASELINE, color=C_BASE, lw=1.6, ls="--",
               label=f"单工具 netMHCpan-BA = {SINGLE_BASELINE:.3f}")

    # k=1 峰值标注 (CV 峰在此)
    if len(k):
        cv1 = float(cv[0])
        ax.annotate("CV 峰在 k=1\n加工具后下降",
                    xy=(1, cv1), xytext=(2.1, cv1 + 0.02), fontsize=9.5,
                    arrowprops=dict(arrowstyle="->", color="black", lw=0.8))

    ax.set_xticks(range(1, int(np.nanmax(k)) + 1))
    ax.set_xlabel("融合的工具个数 k (前向贪心逐个加入)")
    ax.set_ylabel("患者内秩相关 ρ (原始)")
    ax.set_title(f"成员选择过拟合: 交叉验证 vs 样本内, 随工具个数 k ({TAG})", fontsize=10.5)
    ax.legend(loc="upper left", fontsize=9, framealpha=0.95)
    ax.spines[["top", "right"]].set_visible(False)
    _save(fig, "figA_newcut_fusion_no_net_gain")


# ═══════════════════════════════════════════════════════════════════════════════
# 图 5 (figB) — 选择梯队: 选择越多, 诚实交叉验证越低
#   值来自 nested_pooling_selection.py (5)(6) 段已核 stdout, 照抄不改:
#   只选pooling 0.451 (绿) → 完全数据驱动 0.332 → 只选成员 0.171;
#   样本内挑的最大值 0.446 与 0.493 (灰, 标"不进CV、不可复现"); 单工具 0.372 红虚线。
#   ★ 新文件名 figB_newcut_selection_ladder (引擎映射由主线同步)。
# ═══════════════════════════════════════════════════════════════════════════════
LADDER = [                      # (标签, CV ρ) —— 诚实 CV 随选择层数下降
    ("只选合成方式\n(面板固定)", 0.451),
    ("完全数据驱动\n(成员+合成方式)", 0.332),
    ("只选成员\n(合成方式固定取最高分)", 0.171),
]
INSAMPLE_MAX = [                # (标签, 样本内值) —— 不进 CV, 不可复现
    ("固定面板取最高分\n(样本内)", 0.446),
    ("交叉验证取最大(k=4)\n(样本内)", 0.493),
]


def fig_b():
    labels = [x[0] for x in LADDER] + [x[0] for x in INSAMPLE_MAX]
    vals = [x[1] for x in LADDER] + [x[1] for x in INSAMPLE_MAX]
    colors = [C_HL, C_CV, C_CV, C_MUTE, C_MUTE]
    n_cv = len(LADDER)

    x = np.arange(len(labels))
    fig, ax = plt.subplots(figsize=(8.6, 5.0))
    bars = ax.bar(x, vals, color=colors, alpha=0.92, width=0.62,
                  edgecolor="white", linewidth=0.6)
    # 样本内柱加斜纹 + 虚线边, 显式区分"不进 CV"
    for i in range(n_cv, len(bars)):
        bars[i].set_hatch("//")
        bars[i].set_edgecolor("#555")
        bars[i].set_linestyle("--")

    ax.axhline(SINGLE_BASELINE, color=C_BASE, lw=1.8, ls="--",
               label=f"单工具 netMHCpan-BA = {SINGLE_BASELINE:.3f}")
    for xi, v in zip(x, vals):
        ax.text(xi, v + 0.008, f"{v:.3f}", ha="center", va="bottom", fontsize=9.5)

    # 分隔线: 诚实 CV | 样本内 (不进 CV)
    ax.axvline(n_cv - 0.5, color="#cccccc", lw=1.0, ls=":")
    ax.text(n_cv - 0.5, max(vals) + 0.045, "交叉验证 ｜ 样本内 (不进CV, 不可复现)",
            ha="center", va="bottom", fontsize=8.5, color="#555")

    ax.set_xticks(x)
    ax.set_xticklabels(labels, fontsize=8.8)
    ax.set_ylabel("患者内秩相关 ρ")
    ax.set_ylim(0, max(vals) + 0.09)
    ax.set_title(f"选择越多, 交叉验证 ρ 越低 ({TAG})", fontsize=11)
    # 图例移到坐标轴外侧右方, 不再压住右侧两根灰柱 (0.446 / 0.493) 及其数值标签;
    # _save 用 bbox_inches="tight", 会自动把画布撑开容纳外置图例。
    ax.legend(handles=[Patch(color=C_HL, label="只选合成方式 (最高CV)"),
                       Patch(color=C_CV, label="更深数据驱动选择"),
                       Patch(facecolor=C_MUTE, hatch="//", edgecolor="#555",
                             label="样本内挑的最大值 (不进CV)"),
                       Line2D([0], [0], color=C_BASE, lw=1.8, ls="--",
                              label=f"单工具基线 {SINGLE_BASELINE:.3f}")],
              loc="upper left", bbox_to_anchor=(1.01, 1.0),
              fontsize=8.3, framealpha=0.95)
    ax.spines[["top", "right"]].set_visible(False)
    _save(fig, "figB_newcut_selection_ladder")


def main():
    print(f"[plot_nested_pooling_s2] ROOT={ROOT}")
    print(f"[out] figures -> {FIG_DIR}  (★ 只写本目录, 绝不碰 paper/figures)")
    made = 0
    for name, fn in [("图3 figE 8聚合算子", fig_e),
                     ("图4 figA k-curve", fig_a),
                     ("图5 figB 选择梯队", fig_b)]:
        try:
            fn()
            made += 1
        except Exception as e:                      # 单图缺输入不拖垮其余
            print(f"[skip] {name} 失败: {e}")
    print(f"[DONE] plot_nested_pooling_s2 —— 成功 {made}/3 图")


if __name__ == "__main__":
    main()
