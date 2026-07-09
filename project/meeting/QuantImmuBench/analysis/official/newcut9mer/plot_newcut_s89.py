#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
plot_newcut_s89.py — 新切 9mer「§8 给老师回复」三图 (自包含出图, 只写本目录 figures/)
服务: QuantImmuBench §3.2/§3.3 老师 §8 回复配图 —— ①融合无净优势 / ②a③ 鲁棒性 / ④ max vs 最优 pooling。

★ 隔离约束 (task#6 派单):
  · 只读【新切 9mer 已落盘结果】+ 只写 analysis/official/newcut9mer/figures/ (脚本内 mkdir)。
  · 绝不复制到 paper/figures, 不调现有 plot_fig* 的 _save —— 自己 savefig, 防覆盖投稿图。

数据源 (新切 9mer, 8 患者 n=8; 列名已对源脚本核过):
  Fig A: analysis/fusion_cv/newcut9mer/k_curve.csv            (select_engine 产; K_CURVE_COLS)
         analysis/fusion_cv/newcut9mer/fusion_nested_cv.csv   (fusion_nested_cv 产; CSV_COLS)
  Fig B: analysis/official/newcut9mer/R6_robustness_official_summary.csv  (R6 产)
  Fig C: analysis/official/newcut9mer/R2_best_per_tool.csv                (R2 产)

Windows 规范: matplotlib Agg 后端 + Microsoft YaHei + axes.unicode_minus=False (防负号/中文豆腐块);
  pd.read_csv(comment='#', encoding='utf-8'); 300dpi PNG + 同名 PDF; 纯 numpy/pandas/matplotlib, 零 GPU。
措辞: 客观中性, 只陈述表内数; 禁「如期/符合预期」类主观词。

跑法 (主线跑, 我不跑): python analysis/official/newcut9mer/plot_newcut_s89.py
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")                       # 无 GUI 后端 (只出文件)
import matplotlib.pyplot as plt             # noqa: E402
from matplotlib.lines import Line2D          # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False  # 负 ρ 值用 ASCII '-', 防负号豆腐块

# ── 目录 (脚本就在新切官方结果目录内) ────────────────────────────────────────────
HERE = Path(__file__).resolve().parent                  # analysis/official/newcut9mer/
ROOT = HERE.parents[2]                                  # QuantImmuBench/
FUSION_DIR = ROOT / "analysis" / "fusion_cv" / "newcut9mer"   # fusion_cv 新切产物
OFFICIAL_DIR = HERE                                     # 新切 R*/S* 产物即本目录
FIG_DIR = HERE / "figures"                              # ★ 唯一输出目录 (不碰 paper/figures)
TAG = "新切9mer·8患者·n=8"

# ── 中性配色 ──────────────────────────────────────────────────────────────────
C_CV = "#1f77b4"        # 诚实 CV / 零选择 max
C_ORACLE = "#d62728"    # 样本内 oracle / 最优 pooling
C_HL = "#d62728"        # 高亮
C_MUTE = "#9aa0a6"      # 灰 (连线/次要)
C_MAXBEST = "#2ca02c"   # best==max 工具


def _read(path):
    """读带 '#' 注释头的 csv (源脚本头几行均 '#' 开头); 缺文件 fail-loud, 给主线清晰路径。"""
    if not path.exists():
        raise FileNotFoundError(f"缺输入表 {path} —— 先跑新切重跑产出该表再出图")
    return pd.read_csv(path, comment="#", encoding="utf-8")


def _num(s):
    """列 -> float ndarray (空/字符串 -> NaN), 防某些 rho 列以空串写出。"""
    return pd.to_numeric(s, errors="coerce").values.astype(float)


def _save(fig, stem):
    """写 300dpi PNG + 同名 PDF 到本目录 figures/ (★ 绝不写 paper/figures)。"""
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    png, pdf = FIG_DIR / f"{stem}.png", FIG_DIR / f"{stem}.pdf"
    fig.savefig(png, dpi=300, bbox_inches="tight")
    fig.savefig(pdf, bbox_inches="tight")       # PDF 矢量, 同名
    plt.close(fig)
    print(f"[saved] {png}")
    print(f"[saved] {pdf}")


# ═══════════════════════════════════════════════════════════════════════════════
# Fig A — ① 融合无净优势 (核心): 诚实 CV vs 样本内 oracle 随 k 的双折线 + 选择膨胀阴影
# ═══════════════════════════════════════════════════════════════════════════════
def fig_a():
    kc = _read(FUSION_DIR / "k_curve.csv")
    kc = kc[(kc["caliber"] == "raw") & (kc["select_mode"] == "greedy_to_k")].copy()
    kc = kc.sort_values("k")
    k = _num(kc["k"])
    cv = _num(kc["cv_rho"])          # 诚实 nested-CV, 随 k 下降
    orc = _num(kc["oracle_rho"])     # 样本内选择, 随 k 上升

    fig, ax = plt.subplots(figsize=(7.4, 5.2))
    ax.plot(k, cv, "-o", color=C_CV, lw=2, ms=6, label="cv_rho (诚实 nested-CV)")
    ax.plot(k, orc, "-s", color=C_ORACLE, lw=2, ms=6, label="oracle_rho (样本内选择上界)")
    good = (~np.isnan(cv)) & (~np.isnan(orc))
    ax.fill_between(k, cv, orc, where=good & (orc >= cv), color=C_ORACLE, alpha=0.12,
                    label="选择膨胀 = oracle − cv")

    # k=1 单工具标注: 工具名从 modal_members 读取 (不硬编码)
    k1 = kc[kc["k"] == 1]
    if len(k1):
        tool1 = str(k1["modal_members"].values[0]) or "单工具"
        cv1 = float(_num(k1["cv_rho"])[0])
        ax.annotate(f"k=1 单工具 {tool1}\ncv_rho={cv1:.3f}",
                    xy=(1, cv1), xytext=(1.6, cv1 - 0.13), fontsize=9,
                    arrowprops=dict(arrowstyle="->", color="black", lw=0.8))

    # 副标题: k>=2 对最强单工具的配对 p (读表, 不臆断结论)
    p_ge2 = _num(kc[kc["k"] >= 2]["paired_p_vs_best_single"])
    p_ge2 = p_ge2[~np.isnan(p_ge2)]
    sub = (f"k≥2 对最强单工具 paired_p 最小 = {np.min(p_ge2):.2f} (均 >0.05)"
           if len(p_ge2) else "k≥2 对最强单工具 paired_p 见 k_curve 表")

    ax.axhline(0, color="gray", lw=0.6, ls=":")
    ax.set_xticks(range(1, int(np.nanmax(k)) + 1))
    ax.set_xlabel("融合成员数 k (前向贪心)")
    ax.set_ylabel("per-patient Fisher-z ρ (raw)")
    ax.set_title(f"Fig A｜融合成员数 k 下 诚实CV vs 样本内 ({TAG})\n{sub}", fontsize=11)
    ax.legend(loc="lower left", fontsize=8, framealpha=0.9)

    # ── 内嵌小条形: fusion_nested_cv 4 臂 Δ=integration_minus_single_cv (全负) ──
    try:
        fn = _read(FUSION_DIR / "fusion_nested_cv.csv")
        labels = [f"{r['pool']}·{r['caliber']}" for _, r in fn.iterrows()]
        delta = _num(fn["integration_minus_single_cv"])
        iax = ax.inset_axes([0.55, 0.60, 0.42, 0.36])
        xp = np.arange(len(labels))
        iax.bar(xp, delta, color=[C_HL if (not np.isnan(d) and d < 0) else C_MUTE
                                  for d in delta], alpha=0.85)
        iax.axhline(0, color="black", lw=0.6)
        iax.set_xticks(xp)
        iax.set_xticklabels(labels, rotation=30, ha="right", fontsize=6)
        iax.set_title("整合−单工具 Δ (nested-CV, 4 臂)", fontsize=7)
        iax.tick_params(labelsize=6)
    except Exception as e:                    # 内嵌图非关键, 失败不拖垮主图
        print(f"[fig_a] 内嵌 Δ 条形跳过: {e}")

    _save(fig, "figA_newcut_fusion_no_net_gain")


# ═══════════════════════════════════════════════════════════════════════════════
# Fig B — ②a③ 鲁棒性: 30 seed 子采样 mean±std ρ, drop=0.1/0.2 并列; 高亮单工具/geomean/median
# ═══════════════════════════════════════════════════════════════════════════════
HL_METHODS = {"netMHCpan_BA_max", "geomean", "median"}   # 高亮 (单工具 rank1 / geomean / median)


def fig_b():
    df = _read(OFFICIAL_DIR / "R6_robustness_official_summary.csv")
    df["drop_frac"] = _num(df["drop_frac"])
    d1 = df[np.isclose(df["drop_frac"], 0.1)].copy()
    d2 = df[np.isclose(df["drop_frac"], 0.2)].copy()
    if d1.empty:                              # 兜底: 无 0.1 则取最小正 drop
        pos = sorted(v for v in set(df["drop_frac"]) if v > 0)
        d1 = df[np.isclose(df["drop_frac"], pos[0])].copy() if pos else df.copy()
    d1 = d1.sort_values("rank")               # 按 drop=0.1 的 rank 排序 (best 在左)
    methods = d1["method"].tolist()

    mean1 = pd.to_numeric(d1.set_index("method")["mean_rho"], errors="coerce").reindex(methods)
    std1 = pd.to_numeric(d1.set_index("method")["std_rho"], errors="coerce").reindex(methods)
    m2 = d2.set_index("method")
    mean2 = pd.to_numeric(m2["mean_rho"], errors="coerce").reindex(methods) if not d2.empty \
        else pd.Series(np.nan, index=methods)
    std2 = pd.to_numeric(m2["std_rho"], errors="coerce").reindex(methods) if not d2.empty \
        else pd.Series(np.nan, index=methods)
    rank1 = pd.to_numeric(d1.set_index("method")["rank"], errors="coerce").reindex(methods)

    x = np.arange(len(methods))
    w = 0.4
    fig, ax = plt.subplots(figsize=(max(10.5, len(methods) * 0.62), 5.6))
    col1 = [C_HL if m in HL_METHODS else C_CV for m in methods]
    col2 = [C_HL if m in HL_METHODS else C_MUTE for m in methods]
    ax.bar(x - w / 2, mean1.values, w, yerr=std1.values, capsize=2, color=col1,
           alpha=0.92, error_kw=dict(lw=0.7), label="drop=0.1")
    ax.bar(x + w / 2, mean2.values, w, yerr=std2.values, capsize=2, color=col2,
           alpha=0.55, error_kw=dict(lw=0.7), label="drop=0.2")

    # 高亮法标 rank (drop=0.1)
    for xi, m in zip(x, methods):
        if m in HL_METHODS and not np.isnan(rank1[m]):
            yv = mean1[m] if not np.isnan(mean1[m]) else 0.0
            ax.text(xi - w / 2, yv + 0.012, f"rank{int(rank1[m])}", ha="center",
                    va="bottom", fontsize=7.5, color=C_HL, fontweight="bold")

    ax.axhline(0, color="gray", lw=0.6, ls=":")
    ax.set_xticks(x)
    ax.set_xticklabels(methods, rotation=45, ha="right", fontsize=8)
    ax.set_ylabel("子采样 mean ρ ± std (30 seed)")
    ax.set_title(f"Fig B｜病人内随机删突变子采样鲁棒性 ({TAG})\n"
                 f"红=高亮: netMHCpan_BA_max(单工具) / geomean / median (rank 见标注, 按 drop=0.1 排序)",
                 fontsize=10.5)
    ax.legend(loc="upper right", fontsize=9)
    _save(fig, "figB_newcut_robustness")


# ═══════════════════════════════════════════════════════════════════════════════
# Fig C — ④ max vs 最优 pooling: 哑铃图 (每工具 max_rho_lenctrl → best_lenctrl_rho); best==max 标色
# ═══════════════════════════════════════════════════════════════════════════════
def fig_c():
    df = _read(OFFICIAL_DIR / "R2_best_per_tool.csv")
    df = df.copy()
    df["max_rho_lenctrl"] = _num(df["max_rho_lenctrl"])
    df["best_lenctrl_rho"] = _num(df["best_lenctrl_rho"])
    df = df[df["max_rho_lenctrl"] > 0].copy()          # 只留有信号工具 (控肽长 max>0)
    df = df.sort_values("best_lenctrl_rho")            # 按最优 pooling ρ 升序 (强者在上)

    tools = df["Tool"].tolist()
    maxr = df["max_rho_lenctrl"].values
    bestr = df["best_lenctrl_rho"].values
    is_maxbest = (df["best_lenctrl"].astype(str) == "max").values   # 最优 pooling 恰为 max

    y = np.arange(len(tools))
    fig, ax = plt.subplots(figsize=(8.2, max(5.0, len(tools) * 0.32)))
    for i in range(len(tools)):
        ax.plot([maxr[i], bestr[i]], [y[i], y[i]], color=C_MUTE, lw=1.5, zorder=1)
    ax.scatter(maxr, y, color=C_CV, s=38, zorder=2)
    ax.scatter(bestr, y, color=np.where(is_maxbest, C_MAXBEST, C_ORACLE),
               s=38, zorder=3)

    ax.set_yticks(y)
    ax.set_yticklabels(tools, fontsize=8)
    ax.set_xlabel("per-patient 控肽长偏相关 ρ (lenctrl)")
    ax.axvline(0, color="gray", lw=0.6, ls=":")

    n_sig = len(tools)
    n_maxbest = int(is_maxbest.sum())
    n_notmax = n_sig - n_maxbest
    handles = [
        Line2D([0], [0], marker="o", ls="", color=C_CV, label="max_rho_lenctrl (零选择 max)"),
        Line2D([0], [0], marker="o", ls="", color=C_ORACLE, label="best_lenctrl_rho (样本内最优 pooling)"),
        Line2D([0], [0], marker="o", ls="", color=C_MAXBEST, label="最优 pooling == max"),
    ]
    ax.legend(handles=handles, loc="lower right", fontsize=8, framealpha=0.9)
    ax.set_title(f"Fig C｜每工具 零选择max vs 样本内最优pooling ({TAG})\n"
                 f"best 为样本内乐观上界·非 held-out 增益; {n_notmax}/{n_sig} 有信号工具最优≠max",
                 fontsize=10)
    _save(fig, "figC_newcut_max_vs_bestpooling")


def main():
    print(f"[plot_newcut_s89] ROOT={ROOT}")
    print(f"[in ] fusion_cv 新切: {FUSION_DIR}")
    print(f"[in ] official 新切:  {OFFICIAL_DIR}")
    print(f"[out] figures ->      {FIG_DIR}  (★ 只写本目录, 绝不碰 paper/figures)")
    made = 0
    for name, fn in [("Fig A 融合无净优势", fig_a),
                     ("Fig B 鲁棒性", fig_b),
                     ("Fig C max vs 最优pooling", fig_c)]:
        try:
            fn()
            made += 1
        except Exception as e:                # 单图缺输入不拖垮其余
            print(f"[skip] {name} 失败: {e}")
    print(f"[DONE] plot_newcut_s89 —— 成功 {made}/3 图")


if __name__ == "__main__":
    main()
