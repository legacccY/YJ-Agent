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
TAG = "固定窗口9肽 · 8位患者 · n=8"

# ── 图内标签白话映射 (与报告正文用词一致, 去内部黑话) ────────────────────────────
# 融合法 / 单工具方法名 -> 中文
LBL = {
    "geomean": "几何平均", "median": "中位数", "mean_rank": "平均名次",
    "weighted_mean_rank": "加权平均名次", "ridge": "岭回归", "powmean": "幂平均",
    "min": "取最低", "max": "取最高", "constrained": "约束型",
    "stacking": "堆叠回归", "softmax_rank": "指数加权名次", "gbdt": "梯度提升树",
}
# 四设置组合: 工具集 · 相关口径
POOL_LBL = {"fullcov": "全部工具", "fullcov_no_dtu": "剔除DTU"}
CAL_LBL = {"raw": "原始", "lenctrl": "控长"}
# 工具名下划线 -> 连字符 (与报告正文一致)
_TOOL_HYPHEN = {"netMHCpan_BA": "netMHCpan-BA", "netMHCpan_EL": "netMHCpan-EL",
                "BigMHC_IM": "BigMHC-IM", "IEDB_Calis": "IEDB-Calis"}


def _lbl(m):
    """融合法名 -> 中文; 单工具「<工具>_max」-> 去 _max 后缀 + 下划线转连字符 (图内零黑话)。"""
    s = str(m)
    if s in LBL:
        return LBL[s]
    if s.endswith("_max"):
        s = s[:-4]
    return _TOOL_HYPHEN.get(s, s)


# ── 中性配色 ──────────────────────────────────────────────────────────────────
C_CV = "#1f77b4"        # 交叉验证实际 / 取最高分
C_ORACLE = "#d62728"    # 样本内理想上界 / 最优合成方式
C_HL = "#d62728"        # 高亮
C_MUTE = "#9aa0a6"      # 灰 (连线/次要)
C_MAXBEST = "#2ca02c"   # 最优即取最高分 工具


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
    ax.plot(k, cv, "-o", color=C_CV, lw=2, ms=6, label="交叉验证实际成绩(无泄漏)")
    ax.plot(k, orc, "-s", color=C_ORACLE, lw=2, ms=6, label="样本内理想上界")
    good = (~np.isnan(cv)) & (~np.isnan(orc))
    ax.fill_between(k, cv, orc, where=good & (orc >= cv), color=C_ORACLE, alpha=0.12,
                    label="选择造成的虚高 = 理想上界 − 实际")

    # k=1 单工具标注: 工具名从 modal_members 读取 (不硬编码)
    k1 = kc[kc["k"] == 1]
    if len(k1):
        tool1 = str(k1["modal_members"].values[0]) or "单工具"
        cv1 = float(_num(k1["cv_rho"])[0])
        ax.annotate(f"k=1 单工具 {_lbl(tool1)}\n实际成绩={cv1:.3f}",
                    xy=(1, cv1), xytext=(1.6, cv1 - 0.13), fontsize=9,
                    arrowprops=dict(arrowstyle="->", color="black", lw=0.8))

    # 副标题: k>=2 对最强单工具的配对 p (读表, 不臆断结论)
    p_ge2 = _num(kc[kc["k"] >= 2]["paired_p_vs_best_single"])
    p_ge2 = p_ge2[~np.isnan(p_ge2)]
    sub = (f"融合≥2个工具 对最强单工具 配对 p 最小 = {np.min(p_ge2):.2f} (均 >0.05)"
           if len(p_ge2) else "融合≥2个工具 对最强单工具 配对 p 见结果表")

    ax.axhline(0, color="gray", lw=0.6, ls=":")
    ax.set_xticks(range(1, int(np.nanmax(k)) + 1))
    ax.set_xlabel("融合的工具个数 k (逐个加入)")
    ax.set_ylabel("患者内秩相关 ρ (原始)")
    ax.set_title(f"图 A｜geomean 融合·逐个贪心加入工具 k 下 交叉验证实际 vs 样本内理想 ({TAG})\n{sub}", fontsize=11)
    ax.legend(loc="lower left", fontsize=9, framealpha=0.9)
    # 注: 四设置"融合−单工具"差值见报告 §2.7 表, 不再内嵌(避免压住主图数据点)。
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
           alpha=0.92, error_kw=dict(lw=0.7), label="删 10%")
    ax.bar(x + w / 2, mean2.values, w, yerr=std2.values, capsize=2, color=col2,
           alpha=0.55, error_kw=dict(lw=0.7), label="删 20%")

    # 高亮法标 rank (drop=0.1)
    for xi, m in zip(x, methods):
        if m in HL_METHODS and not np.isnan(rank1[m]):
            yv = mean1[m] if not np.isnan(mean1[m]) else 0.0
            ax.text(xi - w / 2, yv + 0.012, f"rank{int(rank1[m])}", ha="center",
                    va="bottom", fontsize=7.5, color=C_HL, fontweight="bold")

    ax.axhline(0, color="gray", lw=0.6, ls=":")
    ax.set_xticks(x)
    ax.set_xticklabels([_lbl(m) for m in methods], rotation=45, ha="right", fontsize=8)
    ax.set_ylabel("子采样均值 ρ ± 标准差 (30 次)")
    ax.set_title(f"图 B｜随机删突变的稳健性 ({TAG})\n"
                 f"红色高亮: netMHCpan-BA取最高(单工具) / 几何平均 / 中位数 (名次见标注, 按删10%排序)",
                 fontsize=10.5)
    ax.legend(loc="upper right", fontsize=9)
    _save(fig, "figB_newcut_robustness")


# ═══════════════════════════════════════════════════════════════════════════════
# Fig C — ④ max vs 最优 pooling: 哑铃图 (每工具 max_rho_lenctrl → best_lenctrl_rho); best==max 标色
# ═══════════════════════════════════════════════════════════════════════════════
def fig_c():
    df = _read(OFFICIAL_DIR / "R2_best_per_tool.csv")
    df = df.copy()
    df["max_rho"] = _num(df["max_rho"])
    df["best_raw_rho"] = _num(df["best_raw_rho"])
    df = df[df["max_rho"] > 0].copy()                  # 只留有信号工具 (原始 max>0)
    df = df.sort_values("best_raw_rho")                # 按最优 pooling ρ 升序 (强者在上)

    tools = df["Tool"].tolist()
    maxr = df["max_rho"].values
    bestr = df["best_raw_rho"].values
    is_maxbest = (df["best_raw"].astype(str) == "max").values   # 最优 pooling 恰为 max

    y = np.arange(len(tools))
    fig, ax = plt.subplots(figsize=(8.2, max(5.0, len(tools) * 0.32)))
    for i in range(len(tools)):
        ax.plot([maxr[i], bestr[i]], [y[i], y[i]], color=C_MUTE, lw=1.5, zorder=1)
    ax.scatter(maxr, y, color=C_CV, s=38, zorder=2)
    ax.scatter(bestr, y, color=np.where(is_maxbest, C_MAXBEST, C_ORACLE),
               s=38, zorder=3)

    ax.set_yticks(y)
    ax.set_yticklabels([_lbl(t) for t in tools], fontsize=8)
    ax.set_xlabel("患者内秩相关 ρ (原始)")
    ax.axvline(0, color="gray", lw=0.6, ls=":")

    n_sig = len(tools)
    n_maxbest = int(is_maxbest.sum())
    n_notmax = n_sig - n_maxbest
    handles = [
        Line2D([0], [0], marker="o", ls="", color=C_CV, label="取最高分(无可调参数)"),
        Line2D([0], [0], marker="o", ls="", color=C_ORACLE, label="样本内最优合成方式"),
        Line2D([0], [0], marker="o", ls="", color=C_MAXBEST, label="最优即取最高分"),
    ]
    ax.legend(handles=handles, loc="lower right", fontsize=8, framealpha=0.9)
    ax.set_title(f"图 C｜每个工具 取最高分 vs 样本内最优合成方式 ({TAG})\n"
                 f"右侧点为样本内乐观上界(非留出增益); {n_notmax}/{n_sig} 个有区分力工具最优合成方式≠取最高分",
                 fontsize=10)
    _save(fig, "figC_newcut_max_vs_bestpooling")


# ═══════════════════════════════════════════════════════════════════════════════
# Fig D — pooling 选择的留出验证: 每工具 取最高分 / 样本内最优(乐观上界) / 留出验证(nested-LOPO)
# ═══════════════════════════════════════════════════════════════════════════════
def fig_d():
    df = _read(OFFICIAL_DIR / "R2b_pooling_lopo_official.csv")
    for c in ("max_rho_raw", "oracle_rho_raw", "lopo_rho_raw"):
        df[c] = _num(df[c])
    df = df.dropna(subset=["max_rho_raw", "oracle_rho_raw", "lopo_rho_raw"])
    df = df.sort_values("lopo_rho_raw")               # 留出值升序 (强者在上)
    tools = [_lbl(t) for t in df["Tool"]]
    mx = df["max_rho_raw"].values
    orc = df["oracle_rho_raw"].values
    lp = df["lopo_rho_raw"].values

    y = np.arange(len(tools))
    fig, ax = plt.subplots(figsize=(8.6, max(5.0, len(tools) * 0.33)))
    for i in range(len(tools)):
        # 样本内虚高段 (留出 → 样本内上界): 淡红, 直观显示「挑最优造成的虚高」
        ax.plot([lp[i], orc[i]], [y[i], y[i]], color=C_ORACLE, lw=2.0, alpha=0.30, zorder=1)
        # 基线 → 留出段: 灰
        ax.plot([mx[i], lp[i]], [y[i], y[i]], color=C_MUTE, lw=1.0, alpha=0.55, zorder=1)
    ax.scatter(mx, y, color=C_CV, s=34, zorder=3, label="取最高分(零选择基线)")
    ax.scatter(orc, y, facecolors="none", edgecolors=C_ORACLE, s=44, lw=1.4,
               zorder=3, label="样本内最优(乐观上界)")
    ax.scatter(lp, y, color=C_MAXBEST, s=42, zorder=4, label="留出验证(嵌套交叉验证)")

    ax.set_yticks(y)
    ax.set_yticklabels(tools, fontsize=8)
    ax.set_xlabel("患者内秩相关 ρ (原始)")
    ax.axvline(0, color="gray", lw=0.6, ls=":")
    ax.legend(loc="lower right", fontsize=8, framealpha=0.9)

    n = len(tools)
    n_pos = int((lp > mx).sum())
    med_infl = float(np.median(orc - lp))
    ax.set_title(f"图 D｜合成方式选择的留出验证 vs 样本内上界 ({TAG})\n"
                 f"红空心=样本内最优(乐观); 绿=无泄漏留出; {n_pos}/{n} 工具留出增益>0, "
                 f"但无一达显著; 样本内上界中位虚高 {med_infl:+.3f}", fontsize=10)
    _save(fig, "figD_newcut_pooling_lopo")


# ═══════════════════════════════════════════════════════════════════════════════
# Fig E — 权威融合(预先固定面板 + median 名次) vs 最强单工具: 无一超过基线
# ═══════════════════════════════════════════════════════════════════════════════
def fig_e():
    df = _read(OFFICIAL_DIR / "R3b_fusion_authoritative_official.csv")
    # ★ 新切已构造性去长度 → 融合/单工具以 raw 为主口径 (非控长; 控长仅 pooling 比较层用)
    df["fusion_rho_raw"] = _num(df["fusion_rho_raw"])
    df["single_rho_raw"] = _num(df["single_rho_raw"])
    AGG_LBL = {"geomean": "几何平均", "mean_rank": "平均名次",
               "weighted_mean_rank": "加权平均名次", "constrained": "约束型",
               "min": "取最低", "powmean": "幂平均", "median": "名次中位数",
               "ridge": "岭回归", "stacking": "堆叠回归", "max": "取最高",
               "softmax_rank": "指数加权名次", "gbdt": "梯度提升树"}
    sub = df[df["panel"] == "双轴小面板"].copy()          # 三工具面板 12 聚合函数
    sub = sub[sub["aggregator"].isin(AGG_LBL)].sort_values("fusion_rho_raw")
    labels = [AGG_LBL[a] for a in sub["aggregator"].tolist()]
    vals = sub["fusion_rho_raw"].values
    baseline = float(sub["single_rho_raw"].iloc[0])       # 最强单工具 (各行同值)

    y = np.arange(len(labels))
    colors = [C_MAXBEST if v > baseline else C_MUTE for v in vals]
    fig, ax = plt.subplots(figsize=(8.6, max(4.2, len(labels) * 0.42)))
    ax.barh(y, vals, color=colors, alpha=0.9, height=0.62)
    ax.axvline(baseline, color=C_HL, lw=2, ls="--",
               label=f"最强单工具 netMHCpan-BA = {baseline:.3f}")
    for yi, v in zip(y, vals):
        ha, x, col = ("left", v + 0.006, "#222") if v < 0.03 else ("right", v - 0.006, "white")
        ax.text(x, yi, f"{v:.3f}", va="center", ha=ha, fontsize=9, color=col, fontweight="bold")

    ax.set_yticks(y)
    ax.set_yticklabels(labels, fontsize=9.5)
    ax.set_xlabel("患者内秩相关 ρ")
    ax.axvline(0, color="gray", lw=0.6, ls=":")
    from matplotlib.patches import Patch
    ax.legend(handles=[Patch(color=C_MAXBEST, label="高于单工具"),
                       Patch(color=C_MUTE, label="低于单工具"),
                       Line2D([0], [0], color=C_HL, lw=2, ls="--", label=f"单工具基线 {baseline:.3f}")],
              loc="lower right", fontsize=8.5, framealpha=0.95)
    n_win = int((vals > baseline).sum())
    ax.set_title(f"图 E｜三工具面板 (netMHCpan-BA+PRIME+deepHLApan) 各聚合函数 vs 最强单工具 ({TAG})\n"
                 f"几何平均最高 ({vals.max():.3f}); {n_win}/{len(labels)} 个聚合函数高于单工具基线",
                 fontsize=9.5)
    _save(fig, "figE_newcut_fusion_authoritative")


def main():
    print(f"[plot_newcut_s89] ROOT={ROOT}")
    print(f"[in ] fusion_cv 新切: {FUSION_DIR}")
    print(f"[in ] official 新切:  {OFFICIAL_DIR}")
    print(f"[out] figures ->      {FIG_DIR}  (★ 只写本目录, 绝不碰 paper/figures)")
    made = 0
    for name, fn in [("Fig A 融合无净优势", fig_a),
                     ("Fig B 鲁棒性", fig_b),
                     ("Fig C max vs 最优pooling", fig_c),
                     ("Fig D pooling留出验证", fig_d),
                     ("Fig E 权威融合vs单工具", fig_e)]:
        try:
            fn()
            made += 1
        except Exception as e:                # 单图缺输入不拖垮其余
            print(f"[skip] {name} 失败: {e}")
    print(f"[DONE] plot_newcut_s89 —— 成功 {made}/3 图")


if __name__ == "__main__":
    main()
