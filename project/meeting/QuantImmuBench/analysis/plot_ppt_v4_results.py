#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
plot_ppt_v4_results.py
======================
服务: QuantImmuBench outline §3 三层结果 + §7 图表清单 —— 给 PPT 补齐 6 张主结果图
(当前 PPT 太简单, 缺 Spearman 主指标图 / 工具相关性图 / 30 工具全景图)。
框架真源 = paper/QuanImmu-Paper-Outline.md (袁老师定稿); 数字真源 = analysis/*.csv。

产 6 图 (全部落 analysis/figures_ppt_v4/, dpi=200 PNG):
  图1 fig1_spearman_30tools.png     —— 30 工具突变级 per-patient Spearman (主指标) 水平条 + 95%CI
  图2 fig_tool_corr_heatmap.png     —— 30 工具预测分两两 Spearman 相关热图 (层次聚类排序)
  图3 fig2_pooling_shuffle.png      —— 池化算子对单工具重排 (哑铃图, 控肽长)
  图4 fig3_robustness.png           —— 删突变鲁棒性: 融合法 top1 胜率 (drop10%/20%)
  图5 fig4_unified_ranking.png      —— 全方法统一排名 + 部署建议
  图6 fig_auprc_30tools.png         —— 30 工具肽级 AUPRC (副指标, 130 肽功效; 新算)

━━━ 类别映射 (着色依据) = DEPLOY_TRACKER.md 表 A(呈递/结合 10) + 表 B(免疫原 20) ━━━━━━━━━
  呈递/结合类 (表 A, 蓝 #0072B2): HLAthena, MHCflurry, MHCnuggets, MHCseqNet, TransHLA,
                                 netMHCpan_BA, netMHCpan_EL, netMHCstabpan  (共 8, 在 TOOLS_30 内)
  免疫原类   (表 B, 橙 #E69F00): 其余 22 工具 (BigMHC_IM/CNNeo/DeepImmuno/DeepNetBim/ICERFIRE/
                                 IEDB_Calis/IMPROVE/ImmuGenX/ImmuneApp/MUNIS/NeoTImmuML/NeoaG/
                                 NeoaPred/NetTepi/PRIME/PredIG/Repitope/Seq2Neo/TSCAPE/andy90/
                                 deepHLApan/pTuneos)
  负相关 (红 #B23A48): 图1/图5 中 rho<0 的条覆盖为红 (凸显控后塌/机制相反)。
  DTU 受限工具 (名后加 " (DTU)"): netMHCpan_BA/netMHCpan_EL/netMHCstabpan/TSCAPE/ICERFIRE/
                                 NetTepi/Seq2Neo (结果照常算, 部署受 DTU 书面同意约束)。
  ⚠️ MUNIS 机制是 EL 呈递模型但 DEPLOY_TRACKER 列于表 B 免疫原补位槽 → 按表位置归免疫原 (橙)。
     若类别有异议, 以 DEPLOY_TRACKER 表 A/B 名单为准 (本脚本按名单硬编码, 见 PRESENTATION_TOOLS)。

Windows 规范: Microsoft YaHei 字体 + axes.unicode_minus=False (防豆腐块); 禁用上划线/下标/✓✗/箭头
  等缺字符号 (改纯 ASCII 或中文); 纯 numpy Spearman (禁 scipy.stats 防 OMP #15, 仅 scipy.cluster
  聚类允许); pathlib 路径; 每图独立 figure + plt.close()。

跑法 (主线跑, 本脚本不自跑):
  cd analysis && python plot_ppt_v4_results.py
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd

import matplotlib
matplotlib.use("Agg")                       # 无 GUI 后端 (只出文件)
import matplotlib.pyplot as plt

# Windows 必要: UTF-8 stdout
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# ── 中文字体 (铁律: 防缺字豆腐块) ─────────────────────────────────────────────
plt.rcParams["font.sans-serif"] = ["Microsoft YaHei"]
plt.rcParams["axes.unicode_minus"] = False

# ── 路径 ─────────────────────────────────────────────────────────────────────
HERE = Path(__file__).resolve().parent                  # analysis/
OFFICIAL = HERE / "official"                            # analysis/official/
ROOT = HERE.parent                                     # QuantImmuBench/
OUT_DIR = HERE / "figures_ppt_v4"

# 复用官方引擎的常量 + 纯 numpy Spearman + 标签逻辑 (import 安全: 只定义, main 有 __main__ 守卫)。
sys.path.insert(0, str(OFFICIAL))
from _official_common import TOOLS_30, DTU_TOOLS, spearman_np      # noqa: E402
from S1_peptide_level_auprc import load_binary_labels             # noqa: E402

# ── 数据源 csv ───────────────────────────────────────────────────────────────
R1_CSV = OFFICIAL / "R1_single_maxpool_official.csv"                    # 图1
LEGACY_POOLED = ROOT / "data" / "frozen" / "pooled_peptide_level_30tools_9mer.csv"  # 图2+图6
R2_CSV = OFFICIAL / "R2_best_per_tool.csv"                              # 图3
R6_CSV = OFFICIAL / "R6_robustness_official_summary.csv"               # 图4
R8_CSV = OFFICIAL / "R8_unified_ranking_official.csv"                  # 图5

# ── 配色 v3 (task 铁律) ──────────────────────────────────────────────────────
C_PRESENT = "#0072B2"   # 呈递/结合类 蓝
C_IMMUNO = "#E69F00"    # 免疫原类 橙
C_NEG = "#B23A48"       # 负相关 红
C_GREY = "#7F7F7F"      # 灰 (稀疏覆盖 / 融合法)
C_FUSION = "#009E73"    # 融合法 绿 (与单工具区分)

# ── 类别名单 (硬编码自 DEPLOY_TRACKER 表 A; 其余 TOOLS_30 归免疫原) ───────────────
PRESENTATION_TOOLS = {
    "HLAthena", "MHCflurry", "MHCnuggets", "MHCseqNet", "TransHLA",
    "netMHCpan_BA", "netMHCpan_EL", "netMHCstabpan",
}


def tool_category(tool):
    """返回 'present' | 'immuno' (类别, 不含负相关判定)。"""
    return "present" if tool in PRESENTATION_TOOLS else "immuno"


def cat_color(tool, rho=None):
    """按类别 + rho 符号定条色。rho<0 -> 红 (负相关优先)。"""
    if rho is not None and not np.isnan(rho) and rho < 0:
        return C_NEG
    return C_PRESENT if tool_category(tool) == "present" else C_IMMUNO


def dtu_label(tool):
    """DTU 受限工具名后加 ' (DTU)'。"""
    return f"{tool} (DTU)" if tool in DTU_TOOLS else tool


def _read_csv(path):
    """读 csv, 跳注释行 (comment='#')。缺文件 fail-loud。"""
    p = Path(path)
    if not p.exists():
        sys.exit(f"[ERR] 源 csv 不存在: {p}")
    return pd.read_csv(p, comment="#", encoding="utf-8")


def _base_tool_from_method(method):
    """从 R8 method 名 (如 'HLAthena_max' / 'netMHCpan_BA_topk_k20_a0') 提取基础工具名。
    最长前缀匹配 TOOLS_30 (防 netMHCpan_BA/EL、NeoaG/NeoaPred 互为前缀误判)。找不到返回 None。
    """
    cands = [t for t in TOOLS_30 if method == t or method.startswith(t + "_")]
    return max(cands, key=len) if cands else None


def _legend(ax, entries, **kw):
    """用色块 handle 造图例 (避免 ✓✗ 等缺字符号)。entries=[(label,color),...]。"""
    from matplotlib.patches import Patch
    handles = [Patch(facecolor=c, edgecolor="none", label=l) for l, c in entries]
    ax.legend(handles=handles, **kw)


# ═══════════════════════════════════════════════════════════════════════════════
# 图1: 30 工具 per-patient Spearman (主指标) —— 源 R1_single_maxpool_official.csv
# ═══════════════════════════════════════════════════════════════════════════════
def fig1_spearman():
    df = _read_csv(R1_CSV)
    need = ["Tool", "fisherz_rho_raw", "ci_lo_raw", "ci_hi_raw", "fisherz_rho_lenctrl"]
    for c in need:
        if c not in df.columns:
            sys.exit(f"[ERR] fig1: R1 缺列 {c}; 实际={list(df.columns)}")
    df = df.sort_values("fisherz_rho_raw", ascending=False).reset_index(drop=True)

    tools = df["Tool"].tolist()
    rho = df["fisherz_rho_raw"].values.astype(float)
    lo = df["ci_lo_raw"].values.astype(float)
    hi = df["ci_hi_raw"].values.astype(float)
    lenctrl = df["fisherz_rho_lenctrl"].values.astype(float)

    n = len(tools)
    y = np.arange(n)[::-1]                       # 最高在最上
    colors = [cat_color(t, r) for t, r in zip(tools, rho)]

    fig, ax = plt.subplots(figsize=(9, 15))     # 收窄: 字相对画布更大, y 轴留长工具名
    # 误差棒 (95%CI): 相对条端的非对称长度
    xerr = np.vstack([np.clip(rho - lo, 0, None), np.clip(hi - rho, 0, None)])
    ax.barh(y, rho, color=colors, edgecolor="white", height=0.62, zorder=2)
    ax.errorbar(rho, y, xerr=xerr, fmt="none", ecolor="#444444",
                elinewidth=1.0, capsize=2.5, zorder=3)
    # 控肽长值 = 空心黑点 (凸显 HLAthena/andy90 控后塌)
    ax.scatter(lenctrl, y, facecolors="none", edgecolors="black",
               s=42, linewidths=1.2, zorder=4, label="控肽长偏相关")

    ax.axvline(0, color="#888888", ls="--", lw=1.0, zorder=1)
    ax.set_yticks(y)
    ax.set_yticklabels([dtu_label(t) for t in tools], fontsize=16)
    ax.set_xlabel("per-patient Spearman rho (裸, 跨患者 Fisher-z 等权聚合)", fontsize=14)
    ax.tick_params(axis="x", labelsize=12)
    ax.set_title("30 工具突变级 per-patient Spearman (官方 130 肽, 零选择 max)",
                 fontsize=18, pad=12)

    # 数值标签: 统一右对齐放到误差棒/控肽长点右端之外的固定列 (不压条不压点)
    right_edge = np.nanmax([np.nanmax(hi), np.nanmax(lenctrl)])
    label_x = right_edge + 0.05
    for yi, r in zip(y, rho):
        ax.text(label_x, yi, f"{r:.3f}", va="center", ha="left",
                fontsize=14, color="#222222")

    ax.set_xlim(min(-0.2, np.nanmin(lo) - 0.05), label_x + 0.14)
    _legend(ax, [("呈递/结合类", C_PRESENT), ("免疫原类", C_IMMUNO), ("负相关", C_NEG)],
            loc="lower right", fontsize=13, title="工具类别")
    ax.text(0.99, 0.02,
            "空心点=控肽长偏相关 (ctrl=peplen); 名后 (DTU)=受限工具; 误差棒=cluster-bootstrap 95%CI",
            transform=ax.transAxes, ha="right", va="bottom", fontsize=12, color="#555555")
    fig.tight_layout()
    out = OUT_DIR / "fig1_spearman_30tools.png"
    fig.savefig(out, dpi=200, bbox_inches="tight")
    plt.close(fig)
    print(f"[saved] {out}")


# ═══════════════════════════════════════════════════════════════════════════════
# 图2: 工具间预测分相关热图 —— 源 legacy pooled 表 (<tool>_max 列)
# ═══════════════════════════════════════════════════════════════════════════════
def fig_corr_heatmap():
    df = _read_csv(LEGACY_POOLED)
    cols, tools = [], []
    for t in TOOLS_30:
        c = f"{t}_max"
        if c in df.columns and df[c].notna().sum() > 0:
            cols.append(c)
            tools.append(t)
        else:
            print(f"[fig2] 跳过 (缺列或全空): {c}")
    k = len(tools)
    if k < 2:
        print("[fig2] 有效工具列 <2, 跳过热图")
        return
    print(f"[fig2] 有效工具 {k}/{len(TOOLS_30)}")

    mat = df[cols].values.astype(float)
    corr = np.eye(k)
    for i in range(k):
        for j in range(i + 1, k):
            r = spearman_np(mat[:, i], mat[:, j])
            corr[i, j] = corr[j, i] = 0.0 if np.isnan(r) else r

    # 层次聚类排序 (scipy.cluster 允许; scipy.stats 才禁)
    order = list(range(k))
    try:
        from scipy.cluster.hierarchy import linkage, leaves_list
        from scipy.spatial.distance import squareform
        dist = 1.0 - corr
        np.fill_diagonal(dist, 0.0)
        dist = (dist + dist.T) / 2.0
        order = list(leaves_list(linkage(squareform(dist, checks=False), method="average")))
        print("[fig2] 排序=层次聚类 (average linkage)")
    except Exception as e:                                  # 退回图1 Spearman 排序
        print(f"[fig2] scipy 聚类不可用 ({e}), 退回按图1 Spearman 值排序")
        try:
            r1 = _read_csv(R1_CSV).set_index("Tool")["fisherz_rho_raw"]
            order = sorted(range(k), key=lambda i: -float(r1.get(tools[i], np.nan)))
        except Exception:
            order = list(range(k))

    corr_o = corr[np.ix_(order, order)]
    tools_o = [dtu_label(tools[i]) for i in order]

    fig, ax = plt.subplots(figsize=(14, 13.5))  # 近方: 30x30 方阵, 工具名清晰
    im = ax.imshow(corr_o, cmap="RdBu_r", vmin=-1, vmax=1, aspect="equal")
    ax.set_xticks(np.arange(k))
    ax.set_yticks(np.arange(k))
    ax.set_xticklabels(tools_o, rotation=90, fontsize=14)
    ax.set_yticklabels(tools_o, fontsize=14)
    ax.set_title("工具间预测分相关性 (肽级 Spearman, 最强窗口 max 聚合)", fontsize=17, pad=12)
    cb = fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
    cb.set_label("Spearman 相关系数", fontsize=13)
    cb.ax.tick_params(labelsize=12)
    ax.text(0.0, -0.11,
            "高相关块 = 预测冗余; 低/负相关 = 互补, 为多工具融合提供依据。",
            transform=ax.transAxes, ha="left", va="top", fontsize=12, color="#555555")
    fig.tight_layout()
    out = OUT_DIR / "fig_tool_corr_heatmap.png"
    fig.savefig(out, dpi=200, bbox_inches="tight")
    plt.close(fig)
    print(f"[saved] {out}")


# ═══════════════════════════════════════════════════════════════════════════════
# 图3: 池化算子对单工具重排 (哑铃图, 控肽长) —— 源 R2_best_per_tool.csv
# ═══════════════════════════════════════════════════════════════════════════════
def fig_pooling_shuffle():
    df = _read_csv(R2_CSV)
    need = ["Tool", "max_rho_lenctrl", "best_lenctrl", "best_lenctrl_rho",
            "gain_lenctrl_over_maxlen"]
    for c in need:
        if c not in df.columns:
            sys.exit(f"[ERR] fig3: R2 缺列 {c}; 实际={list(df.columns)}")
    df = df.sort_values("gain_lenctrl_over_maxlen", ascending=True).reset_index(drop=True)

    tools = df["Tool"].tolist()
    max_v = df["max_rho_lenctrl"].values.astype(float)
    best_v = df["best_lenctrl_rho"].values.astype(float)
    best_name = df["best_lenctrl"].tolist()
    gain = df["gain_lenctrl_over_maxlen"].values.astype(float)

    n = len(tools)
    y = np.arange(n)
    fig, ax = plt.subplots(figsize=(9, 14))     # 收窄: 26 行字相对画布更大
    for yi, mv, bv, t, g in zip(y, max_v, best_v, tools, gain):
        col = cat_color(t)
        ls = "-" if g >= 0 else "--"                      # 正提升实线, 负虚线
        ax.plot([mv, bv], [yi, yi], color=col, lw=2.0, ls=ls, zorder=2)
        ax.scatter(mv, yi, facecolors="white", edgecolors=col, s=55,
                   linewidths=1.6, zorder=3)              # max = 空心
        ax.scatter(bv, yi, facecolors=col, edgecolors=col, s=55, zorder=3)  # best = 实心

    ax.axvline(0, color="#888888", ls="--", lw=1.0, zorder=1)
    ax.set_yticks(y)
    ax.set_yticklabels([dtu_label(t) for t in tools], fontsize=15)
    ax.set_xlabel("per-patient Spearman rho (控肽长偏相关, ctrl=peplen)", fontsize=14)
    ax.tick_params(axis="x", labelsize=12)
    ax.set_title("池化算子对单工具的重排 (控肽长; 空心=max, 实心=最优 pooling)",
                 fontsize=17, pad=12)
    # 标最优 pooling 名 (放实心点外侧)
    for yi, bv, bn in zip(y, best_v, best_name):
        ax.text(bv + 0.012, yi, str(bn), va="center", ha="left",
                fontsize=12, color="#333333")

    _legend(ax, [("呈递/结合类", C_PRESENT), ("免疫原类", C_IMMUNO)],
            loc="lower right", fontsize=13, title="工具类别")
    ax.text(0.01, 0.01,
            "实线=正增益, 虚线=负增益; 控肽长后增益才反映真 pooling 效应 (裸选会捡回肽长混杂)",
            transform=ax.transAxes, ha="left", va="bottom", fontsize=12, color="#555555")
    fig.tight_layout()
    out = OUT_DIR / "fig2_pooling_shuffle.png"
    fig.savefig(out, dpi=200, bbox_inches="tight")
    plt.close(fig)
    print(f"[saved] {out}")


# ═══════════════════════════════════════════════════════════════════════════════
# 图4: 删突变鲁棒性 融合法 top1 胜率 —— 源 R6_robustness_official_summary.csv
# ═══════════════════════════════════════════════════════════════════════════════
def fig_robustness():
    df = _read_csv(R6_CSV)
    need = ["method", "kind", "drop_frac", "win_rate_top1"]
    for c in need:
        if c not in df.columns:
            sys.exit(f"[ERR] fig4: R6 缺列 {c}; 实际={list(df.columns)}")
    # 只画融合法 (kind==fusion); 剔除单工具 (win_rate 全 NaN, 占位杂乱)
    df = df[df["kind"] == "fusion"].copy()
    drops = sorted(df["drop_frac"].unique().tolist())     # 期望 [0.1, 0.2]
    # method 顺序按 drop=drops[0] 的 win_rate_top1 降序
    d0 = df[df["drop_frac"] == drops[0]].sort_values("win_rate_top1", ascending=False)
    methods = d0["method"].tolist()

    x = np.arange(len(methods))
    nd = len(drops)
    width = 0.8 / max(nd, 1)
    bar_shades = ["#3B7DBF", "#9CC3E0"]                    # drop 组浅深

    fig, ax = plt.subplots(figsize=(14, 7.5))
    for di, dfrac in enumerate(drops):
        sub = df[df["drop_frac"] == dfrac].set_index("method")
        vals = [float(sub["win_rate_top1"].get(m, np.nan)) for m in methods]
        offs = x + (di - (nd - 1) / 2.0) * width
        cols = [bar_shades[di % len(bar_shades)]] * len(methods)
        # 高亮 geomean
        cols = ["#E69F00" if m == "geomean" else c for m, c in zip(methods, cols)]
        ax.bar(offs, vals, width=width * 0.95, color=cols, edgecolor="white",
               label=f"drop {int(round(dfrac * 100))}%")
        for xo, v in zip(offs, vals):
            if not np.isnan(v):
                ax.text(xo, v + 0.01, f"{v:.2f}", ha="center", va="bottom", fontsize=12)

    ax.set_xticks(x)
    ax.set_xticklabels(methods, rotation=45, ha="right", fontsize=13)
    ax.tick_params(axis="y", labelsize=12)
    ax.set_ylabel("top1 胜率 (30 seed 中为 12 法第一的比例)", fontsize=14)
    ax.set_title("删突变鲁棒性: 融合法 top1 胜率 (geomean 高亮)", fontsize=17, pad=12)
    ax.set_ylim(0, min(1.0, np.nanmax(df["win_rate_top1"].values) + 0.12))
    ax.legend(title="删突变比例", fontsize=13)
    ax.text(0.99, 0.97, "橙 = geomean (headline 融合法)", transform=ax.transAxes,
            ha="right", va="top", fontsize=12, color="#555555")
    fig.tight_layout()
    out = OUT_DIR / "fig3_robustness.png"
    fig.savefig(out, dpi=200, bbox_inches="tight")
    plt.close(fig)
    print(f"[saved] {out}")


# ═══════════════════════════════════════════════════════════════════════════════
# 图5: 全方法统一排名 + 部署建议 —— 源 R8_unified_ranking_official.csv
# ═══════════════════════════════════════════════════════════════════════════════
def fig_unified_ranking():
    df = _read_csv(R8_CSV)
    need = ["method", "family", "dim_set", "rho_bar", "coverage_flag", "deploy_candidate"]
    for c in need:
        if c not in df.columns:
            sys.exit(f"[ERR] fig5: R8 缺列 {c}; 实际={list(df.columns)}")
    df = df.sort_values("rho_bar", ascending=False).reset_index(drop=True)

    methods = df["method"].tolist()
    rho = df["rho_bar"].values.astype(float)
    family = df["family"].tolist()
    cov = df["coverage_flag"].astype(str).tolist()
    dim_set = df["dim_set"].astype(str).tolist()           # dim7 / SURV6 / '-' (单工具)

    n = len(methods)
    y = np.arange(n)[::-1]
    colors, labels = [], []
    for m, r, fam, cf, ds in zip(methods, rho, family, cov, dim_set):
        if cf == "sparse":
            colors.append(C_GREY)                          # 稀疏覆盖灰显
        elif fam == "fusion":
            colors.append(C_FUSION)
        else:
            base = _base_tool_from_method(m)
            colors.append(cat_color(base, r) if base else C_GREY)
        # 融合法后缀标维度集 (同名 geomean/min... 在 dim7 与 SURV6 各出现一次, 区分开)
        name = m
        if fam == "fusion" and ds and ds not in ("-", "nan", ""):
            name = f"{m} · {ds}"
        lab = name + ("  [覆盖稀疏, 不入部署]" if cf == "sparse" else "")
        labels.append(lab)

    fig, ax = plt.subplots(figsize=(10, 20))    # 收窄+保持高: 40+ 行最挤, 字不糊
    ax.barh(y, rho, color=colors, edgecolor="white", height=0.66, zorder=2)
    ax.axvline(0, color="#888888", ls="--", lw=1.0, zorder=1)
    ax.set_yticks(y)
    ax.set_yticklabels(labels, fontsize=14)
    ax.set_xlabel("per-patient Fisher-z rho_bar (裸, 零选择 max)", fontsize=14)
    ax.tick_params(axis="x", labelsize=12)
    ax.set_title("全方法统一排名与部署建议 (官方 130 肽)", fontsize=17, pad=12)
    for yi, r in zip(y, rho):
        off = 0.008 if r >= 0 else -0.008
        ax.text(r + off, yi, f"{r:.3f}", va="center",
                ha="left" if r >= 0 else "right", fontsize=13, color="#222222")

    # 部署方案标注 (outline §3.4)
    ax.text(0.99, 0.14,
            "部署方案 A: netMHCpan_BA topk20  rho_bar=0.461\n"
            "部署方案 B: 多维 geomean 融合     rho_bar=0.362",
            transform=ax.transAxes, ha="right", va="bottom", fontsize=13,
            bbox=dict(boxstyle="round", fc="#F5F5F5", ec="#999999"))
    _legend(ax, [("呈递/结合单工具", C_PRESENT), ("免疫原单工具", C_IMMUNO),
                 ("融合法", C_FUSION), ("覆盖稀疏(不入部署)", C_GREY)],
            loc="lower right", fontsize=13, title="方法类别")
    fig.tight_layout()
    out = OUT_DIR / "fig4_unified_ranking.png"
    fig.savefig(out, dpi=200, bbox_inches="tight")
    plt.close(fig)
    print(f"[saved] {out}")


# ═══════════════════════════════════════════════════════════════════════════════
# 图6: 30 工具肽级 AUPRC (副指标, 新算) —— 源 legacy pooled + 官方 xlsx 二分标签
# ═══════════════════════════════════════════════════════════════════════════════
def fig_auprc():
    from sklearn.metrics import average_precision_score
    df = _read_csv(LEGACY_POOLED)
    if "mut_key" not in df.columns:
        sys.exit("[ERR] fig6: legacy pooled 缺 mut_key 列, 无法 join 标签")

    labdf = load_binary_labels()                           # 复用 S1: pval<0.05 二分标签
    merged = df.merge(labdf[["mut_key", "label_pval"]], on="mut_key", how="left")
    y_all = merged["label_pval"].values.astype(float)
    n_pos = int(np.nansum(y_all == 1))
    n_neg = int(np.nansum(y_all == 0))
    base_rate = n_pos / (n_pos + n_neg) if (n_pos + n_neg) > 0 else np.nan
    print(f"[fig6] 标签 pval<0.05: 阳={n_pos} 阴={n_neg} 基线阳性率={base_rate:.3f}")

    rows = []
    for t in TOOLS_30:
        c = f"{t}_max"
        if c not in merged.columns or merged[c].notna().sum() == 0:
            print(f"[fig6] 跳过 (缺列或全空): {c}")
            continue
        s = merged[c].values.astype(float)
        m = ~(np.isnan(y_all) | np.isnan(s))
        yy, ss = y_all[m], s[m]
        if len(np.unique(yy)) < 2:
            print(f"[fig6] 跳过 (标签单类别): {t}")
            continue
        ap = float(average_precision_score(yy, ss))
        rows.append((t, ap, int(m.sum())))

    if not rows:
        print("[fig6] 无有效工具, 跳过")
        return
    rows.sort(key=lambda r: -r[1])
    tools = [r[0] for r in rows]
    aps = [r[1] for r in rows]

    n = len(tools)
    y = np.arange(n)[::-1]
    colors = [cat_color(t) for t in tools]                 # AUPRC 恒正, 按类别着色
    fig, ax = plt.subplots(figsize=(9, 14))     # 收窄: 27 行字相对画布更大
    ax.barh(y, aps, color=colors, edgecolor="white", height=0.66, zorder=2)
    if not np.isnan(base_rate):
        ax.axvline(base_rate, color=C_NEG, ls="--", lw=1.2, zorder=3,
                   label=f"随机基线 (阳性率={base_rate:.3f})")
    ax.set_yticks(y)
    ax.set_yticklabels([dtu_label(t) for t in tools], fontsize=15)
    ax.set_xlabel("肽级 AUPRC (130 肽当一个池子, sklearn average_precision_score)", fontsize=14)
    ax.tick_params(axis="x", labelsize=12)
    ax.set_title("30 工具肽级 AUPRC (副指标, 130 肽功效)", fontsize=17, pad=12)
    for yi, a in zip(y, aps):
        ax.text(a + 0.006, yi, f"{a:.3f}", va="center", ha="left",
                fontsize=13, color="#222222")
    ax.set_xlim(0, max(1.0, max(aps) + 0.08))
    ax.legend(loc="lower right", fontsize=13)
    ax.text(0.01, 0.01,
            "副指标: 估计量与 per-patient Spearman 不同 (混病人内/间信号, 忽略病人结构),\n"
            "与主指标并列不替换 (headline 仍是 Spearman)。",
            transform=ax.transAxes, ha="left", va="bottom", fontsize=12, color="#555555")
    fig.tight_layout()
    out = OUT_DIR / "fig_auprc_30tools.png"
    fig.savefig(out, dpi=200, bbox_inches="tight")
    plt.close(fig)
    print(f"[saved] {out}")


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    print(f"[info] 输出目录: {OUT_DIR}")
    fig1_spearman()
    fig_corr_heatmap()
    fig_pooling_shuffle()
    fig_robustness()
    fig_unified_ranking()
    fig_auprc()
    print("[DONE] plot_ppt_v4_results 全部 6 图完成")


if __name__ == "__main__":
    main()
