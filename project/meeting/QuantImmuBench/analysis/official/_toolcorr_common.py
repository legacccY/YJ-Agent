#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
_toolcorr_common.py
===================
服务: QuantImmuBench 「工具间打分相关结构可视化(替代热图)」lever 的 **共享数据/配色底座**。
被 plot_toolcorr_{network,dendrogram,corrplot,mds}.py 四个出图脚本共用, 让「相关口径」单一真源
(防四张图各算各的口径漂移)。

它做什么 (一句话):
  读 data/frozen/pooled_clean_9mer.csv → 取 30 个 <tool>_max 列 → 跨 130 肽算 **Spearman** 相关
  → 剔「全 NaN」工具 (DeepNetBim: max-pool 饱和成常数列, std=0 致相关未定义, 与 fig1 脚注一致)
  → 得约 29×29 相关阵。**所有相关数值每次从 csv 现算, 脚本内零硬编码。**

配色 / PRESENTATION_TOOLS 逐字复用 recompute_effN/plot_R1_effN.py (色盲友好 Okabe-Ito, 呈递蓝 /
免疫原橙); DTU_TOOLS 从 _official_common import (纯常量, 无副作用)。类别名单为权威来源, 非本脚本臆断。

★ 本模块不自跑, 无 __main__; 由四个出图脚本 import。四出图脚本亦不自跑 —— 主线跑 (见各脚本尾)。
"""

import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent                 # analysis/official/
PROJECT_ROOT = HERE.parent.parent                      # QuantImmuBench/ (根)
DEFAULT_INPUT = PROJECT_ROOT / "data" / "frozen" / "pooled_clean_9mer.csv"
DEFAULT_PERF_CSV = HERE / "recompute_effN" / "R1_recomputed_effN8.csv"
FIG_DIR = HERE / "figures"                             # 默认产物目录 (与 plot_fig2/3/4 一致)
PAPER_FIG = PROJECT_ROOT / "paper" / "figures"         # 投稿矢量副本

MAXCOL_SUFFIX = "_max"                                 # headline 零选择 pooling 列后缀

# ── 配色 (逐字复用 fig1 plot_R1_effN.py; Okabe-Ito) ──────────────────────────────
C_PRESENT = "#0072B2"   # 呈递/结合类 蓝
C_IMMUNO = "#E69F00"    # 免疫原类 橙
C_POS = "#B2182B"       # 正相关 红 (corrplot/network 用)
C_NEG = "#2166AC"       # 负相关 蓝 (corrplot/network 用)

# 呈递/结合类名单 (权威, 逐字同 fig1 plot_R1_effN.py + §3.2 诊断脚本; 去 _max 后匹配)。
# 其余 22 工具 = 免疫原类 (与 04_LOG「官方口径 8 呈递 + 22 免疫原」一致)。
PRESENTATION_TOOLS = {
    "HLAthena", "MHCflurry", "MHCnuggets", "MHCseqNet", "TransHLA",
    "netMHCpan_BA", "netMHCpan_EL", "netMHCstabpan",
}

# DTU 受限工具 (纯常量, 无副作用): 名后标 " (DTU)"
sys.path.insert(0, str(HERE))
try:
    from _official_common import DTU_TOOLS      # noqa: E402
except Exception:                               # 极端: 相对路径解析失败时退回硬编码同值
    DTU_TOOLS = {"netMHCpan_BA", "netMHCpan_EL", "netMHCstabpan", "TSCAPE",
                 "ICERFIRE", "NetTepi", "Seq2Neo"}


# ───────────────────────────── 数据: 读列 → 算相关 ─────────────────────────────
def load_max_scores(input_path=None):
    """读 pooled csv, 返回 30 个 <tool>_max 列 (列名去 _max), index=肽行。

    返回 DataFrame [n_peptide × n_tool]; 列名 = tool_key (下划线形式, 如 netMHCpan_BA)。
    """
    p = Path(input_path) if input_path else DEFAULT_INPUT
    if not p.exists():
        sys.exit(f"[ERR] 输入 csv 不存在: {p}")
    df = pd.read_csv(p, encoding="utf-8")
    maxcols = [c for c in df.columns if c.endswith(MAXCOL_SUFFIX)]
    if not maxcols:
        sys.exit(f"[ERR] csv 里找不到任何 {MAXCOL_SUFFIX} 结尾列: {p}")
    if len(maxcols) != 30:
        warnings.warn(f"[warn] 预期 30 个 {MAXCOL_SUFFIX} 列, 实际 {len(maxcols)} 个 "
                      f"(口径变了? 继续用实际列)")
    scores = df[maxcols].copy()
    scores.columns = [c[: -len(MAXCOL_SUFFIX)] for c in maxcols]   # 去 _max 后缀 → tool_key
    scores = scores.apply(pd.to_numeric, errors="coerce")
    return scores


def spearman_corr(scores):
    """跨肽 Spearman 相关阵 + 剔「全 NaN」退化工具。

    返回 (corr_clean [DataFrame], dropped [list])。
      · corr = scores.corr(method='spearman')  ← 数值现算, 零硬编码
      · 退化工具判定: 对其它工具的相关**全 NaN** (常数列, std=0) → 剔 (预期只有 DeepNetBim)
      · 残余 off-diagonal NaN (理论不该有, 130 肽全非缺) → 填 0 相关并告警, 保证下游矩阵可用
      · 对角线强制 1.0
    """
    corr = scores.corr(method="spearman")
    degenerate = []
    for t in corr.columns:
        others = corr[t].drop(labels=[t])
        if others.isna().all():
            degenerate.append(t)
    corr_clean = corr.drop(index=degenerate, columns=degenerate)

    arr = corr_clean.to_numpy(dtype=float).copy()  # .copy() 防 to_numpy 只读视图 → fill_diagonal 原地改报错
    n = arr.shape[0]
    off = ~np.eye(n, dtype=bool)
    if np.isnan(arr[off]).any():
        n_bad = int(np.isnan(arr[off]).sum())
        warnings.warn(f"[warn] 剔退化工具后仍有 {n_bad} 个 off-diagonal NaN 相关; 填 0 (=距离1) "
                      f"以保下游 squareform/MDS 可用")
        arr = np.where(np.isnan(arr) & off, 0.0, arr)
    np.fill_diagonal(arr, 1.0)
    corr_clean = pd.DataFrame(arr, index=corr_clean.index, columns=corr_clean.columns)
    return corr_clean, degenerate


def distance_from_corr(corr):
    """相异度矩阵 = 1 − |相关| (对称, 零对角); 供 dendrogram / MDS 吃。

    返回 numpy 数组 (与 corr 行列同序)。|ρ|=1 → 距离 0 (最像); |ρ|=0 → 距离 1 (最不像)。
    """
    d = 1.0 - np.abs(corr.to_numpy(dtype=float))
    d = (d + d.T) / 2.0                 # 数值对称化 (防浮点微差)
    np.fill_diagonal(d, 0.0)
    return d


# ───────────────────────────── 名称 / 类别 / 配色 ─────────────────────────────
def display_name(tool_key):
    """展示名: 去 _max 后的 tool_key 里下划线换连字符 (netMHCpan_BA → netMHCpan-BA)。"""
    return tool_key.replace("_", "-")


def category(tool_key):
    """工具类别: 呈递/结合 (PRESENTATION_TOOLS) 否则 免疫原。"""
    return "presentation" if tool_key in PRESENTATION_TOOLS else "immunogenicity"


def cat_color(tool_key):
    return C_PRESENT if category(tool_key) == "presentation" else C_IMMUNO


def is_dtu(tool_key):
    return tool_key in DTU_TOOLS


def load_perf(perf_csv=None, tools=None):
    """读 R1_recomputed_effN8.csv 的单工具 per-patient Spearman (fisherz_rho_effN),
    返回 {tool_key: rho}。仅供 network 图节点定大小用; 缺/NaN 的工具不进字典。

    ★ Tool 列为下划线形式 (netMHCpan_BA), 与 load_max_scores 的 tool_key 同口径, 直接对齐。
    """
    p = Path(perf_csv) if perf_csv else DEFAULT_PERF_CSV
    if not p.exists():
        warnings.warn(f"[warn] 性能 csv 不存在, network 节点将等大小: {p}")
        return {}
    df = pd.read_csv(p, comment="#", encoding="utf-8")
    if "Tool" not in df.columns or "fisherz_rho_effN" not in df.columns:
        warnings.warn(f"[warn] {p.name} 缺 Tool/fisherz_rho_effN 列, network 节点将等大小")
        return {}
    df["fisherz_rho_effN"] = pd.to_numeric(df["fisherz_rho_effN"], errors="coerce")
    out = {}
    for _, r in df.iterrows():
        t = str(r["Tool"]).strip()
        v = r["fisherz_rho_effN"]
        if pd.notna(v):
            out[t] = float(v)
    if tools is not None:
        out = {t: out[t] for t in tools if t in out}
    return out


# ───────────────────────────── 出图公用: 字体 / 存图 / 脚注 ────────────────────
def apply_matplotlib_style(plt):
    """Windows 铁律: Microsoft YaHei + axes.unicode_minus=False (防中文/负号豆腐块)。"""
    plt.rcParams["font.sans-serif"] = ["Microsoft YaHei"]
    plt.rcParams["axes.unicode_minus"] = False


def savefig_all(fig, out_png):
    """存 PNG(300dpi) + 同名 PDF(矢量) 到产物目录, 再复制一份 PDF 进 paper/figures/。"""
    out_png = Path(out_png)
    out_png.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_png, dpi=300, bbox_inches="tight")
    out_pdf = out_png.with_suffix(".pdf")
    fig.savefig(out_pdf, bbox_inches="tight")
    PAPER_FIG.mkdir(parents=True, exist_ok=True)
    paper_pdf = PAPER_FIG / out_pdf.name
    fig.savefig(paper_pdf, bbox_inches="tight")
    print(f"[saved] {out_png}")
    print(f"[saved] {out_pdf}")
    print(f"[saved] {paper_pdf}")


def caption_note(n_pep, n_tools, dropped):
    """标准口径脚注串 (含实际肽数/工具数/剔除名单, 全从现算量填, 零硬编码)。"""
    drop_txt = "、".join(dropped) if dropped else "无"
    return (f"相关口径: 30 工具 {MAXCOL_SUFFIX} 打分的 per-peptide Spearman 相关, n={n_pep} 肽 "
            f"(DS2 9mer)。已剔 {drop_txt}（max-pool 饱和成常数列, 相关未定义）→ 实入图 {n_tools} 工具。\n"
            f"颜色=工具类别（蓝 呈递/结合，橙 免疫原）；名后 (DTU)=数据使用受限工具。")
