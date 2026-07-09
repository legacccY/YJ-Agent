#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
_official_common.py
===================
服务: QuantImmuBench §3 官方版实验 (R1..R6) 的共享统计/融合引擎。
对应大纲: paper/QuanImmu-Paper-Outline.md §3.1-3.4 (袁老师定稿权威框架)。

定位 (为何单独抽一个 common):
  R1..R6 六个官方脚本都要复用同一套口径: 纯 numpy Spearman + Fisher-z 加权聚合 +
  病人内 rank fusion。旧骨架靠 import 链复用 (fusion_12methods import fusion_study；
  robustness import fusion_12methods)。官方版改读 data/frozen/ 冻结表, 与
  quantimmune/model_matrix_v2.csv 血缘解耦, 故把引擎抽到本模块, 6 脚本 import 它,
  保证 R1..R6 口径逐位一致、零重复。

复用来源 (算法逻辑照搬, 仅把输入指向冻结表):
  · spearman_np / fisherz_weighted_agg        ← analysis/fusion_study.py (照抄公式)
  · per-patient Spearman 主指标               ← analysis/fusion_12methods.py per_patient_spearman
  · 8 无监督 fusion 组合子 + apply_fusion       ← analysis/fusion_12methods.py
  · 学习型 LOPO (ridge/gbdt/stacking/constrained) ← analysis/fusion_12methods.py _lopo_scores
  · impute_fold / find_ridge_alpha / _fit_simplex ← analysis/fusion_study.py + fusion_12methods.py
  · per-patient 多聚合 (R1 各患者 rho 列)        ← analysis/per_patient_spearman_multimethod.py

输入 (只读, Phase 1 干净表, 绝不改):
  主分析 = data/frozen/pooled_clean_9mer.csv  (130×1536) —— 9mer 口径 (对齐 outline §2.2
    「全文主分析用 9AA-only」)。元列 mut_key,Patient_ID,Peptide_ID,Elispot,peplen(肽长),
    n_subpep + 30 工具×51 pooling 变体列。R1-R9 --input default=FROZEN_POOLED 自动跟切。
  补充 = data/frozen/pooled_clean_allwindow.csv —— 全窗 8-14mer (降为补充材料,
    FROZEN_POOLED_ALLWINDOW 指向; 各脚本可 --input 显式指它复现全窗)。
  legacy = data/frozen/pooled_peptide_level_30tools_9mer.csv (FROZEN_POOLED_LEGACY, 8-pooling,
    无 peplen; 保留供对照)。纯 DS2 (9 患者 101,102,104..110), Elispot=连续 SFC 真值 (不 clip 不二值化)。
  pooling 新命名: <Tool>_max / <Tool>_topk_k{k}_a{α} / <Tool>_softmax_T{T} / <Tool>_rankdecay_g{γ}
    (α/T/γ 小数点用 p, 如 netMHCpan_BA_topk_k20_a0); 遍历用 tool_pooling_cols(df, tool)。

Part B 评判标准重建 (outline §2.6 口径, 本次改动核心):
  · [B1] 跨病人 Fisher-z 默认从逆方差切到等权平均 (fisherz_weighted_agg weight='equal' 默认,
    'invvar' 保留对照); per_patient_spearman 默认跟切。
  · [B2] 新一等公民 per_patient_partial_spearman(ctrl='peplen'): 逐病人偏 Spearman 控肽长混杂,
    ≥4 有效点, 等权聚合。
  · [B4] bootstrap_patient_ci (cluster bootstrap over patients, 2000×) 出 CI, 弃固定效应过窄 CI;
    paired_patient_test 病人配对符号置换检验 (纯 numpy, 双侧)。

硬约束 (task 派单):
  · Spearman 纯 numpy (禁 scipy.stats, 防 OMP Error #15); p-value 用纯 numpy 符号置换或 betainc。
  · per-patient min_pep=3 (偏相关硬底 4); Fisher-z 聚合 (n<=FISHER_MIN_N=3 剔出)。
  · DTU 工具结果照常算, 由调用脚本注释标 pending_DTU_consent。

Windows 规范: UTF-8 stdout, pathlib 路径, 纯 numpy/pandas/sklearn, 零 GPU。
"""

import os
import sys
import functools
import itertools
from pathlib import Path

import numpy as np
import pandas as pd

# Windows 必要: UTF-8 stdout
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

HERE = Path(__file__).resolve().parent                  # analysis/official/
ANALYSIS = HERE.parent                                  # analysis/
ROOT = ANALYSIS.parent                                  # QuantImmuBench/

# ── 冻结表路径 (默认输入) ──────────────────────────────────────────────────────
# [Part C] 主分析改指 Phase 1 干净表 pooled_clean_9mer.csv (130×1536): 元列
#   mut_key/Patient_ID/Peptide_ID/Elispot/peplen(肽长)/n_subpep + 30 工具×51 pooling 列。
#   pooling 新命名 = <Tool>_max / <Tool>_topk_k{k}_a{α} / <Tool>_softmax_T{T} /
#   <Tool>_rankdecay_g{γ} (α/T/γ 小数点用 p, 如 netMHCpan_BA_topk_k20_a0)。
#   9mer 口径 (对齐 outline §2.2 「全文主分析用 9AA-only」); R1-R9 --input default 跟着切。
FROZEN_POOLED = ROOT / "data" / "frozen" / "pooled_clean_9mer.csv"
# [Part C] 全窗 8-14mer 干净表 (降为补充材料; 显式 --input 指它可复现全窗对照)。
FROZEN_POOLED_ALLWINDOW = ROOT / "data" / "frozen" / "pooled_clean_allwindow.csv"
# [Part C] 旧 8-pooling 肽级表 (保留供 legacy 对照, 别删); 命名 <Tool>_<8pooling>, 无 peplen 列。
FROZEN_POOLED_LEGACY = ROOT / "data" / "frozen" / "pooled_peptide_level_30tools_9mer.csv"
FROZEN_GT = ROOT / "data" / "frozen" / "ds2_official_groundtruth.csv"
# [B2-multi] indel 混杂来源: 只列 indel/WT-NA 肽 (列 mut_key,Variant_Type; DEL/INS=indel,
#   未匹配的 SNV 肽 = 0)。attach_confounders 从此表按 mut_key merge is_indel; 缺则回退 GT。
FROZEN_WT_NA_INDEL = ROOT / "data" / "frozen" / "WT_NA_indel_list.csv"
OUT_DIR = HERE                                           # analysis/official/

# ── 常量 (口径真源, 与冻结表对齐) ─────────────────────────────────────────────
# 冻结表实测患者 = DS2 9 人 (101,102,104,105,106,107,108,109,110), 无 DS1。
DS2_PATIENTS = [101, 102, 104, 105, 106, 107, 108, 109, 110]

# [Part B/C] 旧 8-pooling 常量 —— 仅供 FROZEN_POOLED_LEGACY 表 (命名 <Tool>_<8pooling>)。
# 新主分析表 pooled_clean_9mer.csv 是 51 变体命名 (<Tool>_max / _topk_k{k}_a{α} /
# _softmax_T{T} / _rankdecay_g{γ}), 遍历用 tool_pooling_cols(df, tool) 动态取, 不用本常量。
POOLINGS = ["max", "mean", "geomean", "sum", "softmax", "top3mean", "topk_w", "rankdecay"]

# ── count-clean 口径 【B2 起弃用: per_patient_partial_spearman(ctrl) 取代, 见下】───────
# 【弃用说明】旧 count-clean 靠冻结表 count_conf 布尔列排除 n_subpep 混杂的 pooling; 新
#   干净表 (pooled_clean_9mer.csv) 不再带 count_conf 列。改由 B2 偏相关在度量层直接控混杂
#   (per_patient_partial_spearman(ctrl='peplen'), outline §2.6), 比「排除整列 pooling」更细。
#   best_pooling_for_tool 不再读 COUNT_CLEAN; 本常量与下方 count_conf 系列函数仅保留 import 兼容。
# ── (以下为历史口径背景, 已由 B2 取代) ────────────────────────────────────────────
# 背景 (数字 Bash 核): n_subpep (一突变候选子肽数) 自身对 ELISpot per-patient
#   Spearman ≈ +0.36, 比多数工具真分还高 = 巨大 count 混杂; sum pooling 机械 ∝ n_subpep
#   (outline §3.2 自警 sum≈n_subpep 数子肽数作弊)。旧 best_pooling_for_tool 不管混杂地
#   在 8 pooling 里挑 per-patient Fisher-z 最高 → 21/29 工具挑到 sum, 「聚合打败 max」
#   大半是 count 混杂假象。count-clean = 只在数据驱动标记 count_conf_<tool>_<pooling>==False
#   的 pooling 里选最优, 隔离工具真 skill 而非「数子肽数」。
#
# count_conf_<tool>_<pooling> = 冻结表布尔列 (p0e 算: |Spearman(pooled_value, n_subpep)|>0.5
#   即 True), 每工具×pooling 一列, 值跨全部肽恒定 (取任一行即可)。
COUNT_CLEAN = True    # 主分析默认 count-clean; R2-R8 调 best_pooling_for_tool 自动跟切

# 30 工具 (task 派单清单, 顺序固定)
TOOLS_30 = [
    "BigMHC_IM", "CNNeo", "DeepImmuno", "DeepNetBim", "HLAthena", "ICERFIRE",
    "IEDB_Calis", "IMPROVE", "ImmuGenX", "ImmuneApp", "MHCflurry", "MHCnuggets",
    "MHCseqNet", "MUNIS", "NeoTImmuML", "NeoaG", "NeoaPred", "NetTepi", "PRIME",
    "PredIG", "Repitope", "Seq2Neo", "TSCAPE", "TransHLA", "andy90", "deepHLApan",
    "netMHCpan_BA", "netMHCpan_EL", "netMHCstabpan", "pTuneos",
]

# DTU 受限工具 (结果照常算, 调用脚本注释标 pending_DTU_consent)
DTU_TOOLS = {"netMHCpan_BA", "netMHCpan_EL", "netMHCstabpan", "TSCAPE",
             "ICERFIRE", "NetTepi", "Seq2Neo"}

MIN_PEP = 3            # 患者内最少肽数才算 rho (task 派单: min_pep=3)
FISHER_CLIP = 0.9999  # rho=±1 → arctanh(±inf); clip 到此
FISHER_MIN_N = 3      # n<=3 → Var(z) 分母 n-3<=0; 剔出 Fisher-z 加权

LABEL_COL = "Elispot"
GBDT_PARAMS = dict(max_depth=2, n_estimators=100, subsample=0.8)  # 同 fusion_study


# ═══════════════════════════════════════════════════════════════════════════════
# 纯 numpy Spearman + Fisher-z 加权聚合 (照抄 fusion_study.py, 禁 scipy)
# ═══════════════════════════════════════════════════════════════════════════════

def spearman_np(x, y):
    """纯 numpy Spearman rank correlation; 样本不足返回 NaN。照抄 fusion_study.py。"""
    x = np.asarray(x, float)
    y = np.asarray(y, float)
    m = ~(np.isnan(x) | np.isnan(y))
    x, y = x[m], y[m]
    n = len(x)
    if n < 2 or len(np.unique(x)) < 2 or len(np.unique(y)) < 2:
        return np.nan
    rx = pd.Series(x).rank().values.astype(float)
    ry = pd.Series(y).rank().values.astype(float)
    rx -= rx.mean()
    ry -= ry.mean()
    denom = np.sqrt((rx ** 2).sum() * (ry ** 2).sum())
    if denom == 0:
        return np.nan
    return float((rx * ry).sum() / denom)


def fisherz_weighted_agg(rhos, ns, *, weight="equal"):
    """Fisher-z 跨病人聚合均值 + 95%CI。Var(z_i)=(1+rho_i^2/2)/(n_i-3)
    [Fieller-Hartley-Pearson 1957]; n_i<=FISHER_MIN_N 剔出。返回 (rho_bar, ci_lo, ci_hi,
    n_used, n_dropped)。

    [B1 · outline §2.6] weight:
      · 'equal'  (默认, §2.6 明确「跨病人等权平均」): z 直接算术平均再 tanh 回。
                 CI 用等权固定效应方差 Var(z_bar)=Σ w_i² Var(z_i), w_i=1/k。
      · 'invvar' (旧口径, 对照): (n_i-3) 逆方差加权 (照抄 fusion_study.py 原实现, 逐位复现)。
    ★ 默认从旧 'invvar' 切到 'equal' 是有意的口径切换 (outline §2.6); 旧调用不传该参 → 走 equal。
    注: 对偏相关 (B2) 每控制变量少 1 自由度; equal 权下方差量级不入 z_bar, 仅 CI 略保守,
        headline CI 一律以 bootstrap_patient_ci (B4) 为准, 本固定效应 CI 仅作快速参考。
    """
    rhos = np.asarray(rhos, float)
    ns = np.asarray(ns, float)
    valid = ~np.isnan(rhos)
    rhos, ns = rhos[valid], ns[valid]
    keep = ns > FISHER_MIN_N
    n_dropped = int((~keep).sum())
    rhos_k, ns_k = rhos[keep], ns[keep]
    if len(rhos_k) == 0:
        return np.nan, np.nan, np.nan, 0, n_dropped
    rhos_k = np.clip(rhos_k, -FISHER_CLIP, FISHER_CLIP)
    z = np.arctanh(rhos_k)
    var_z = (1.0 + rhos_k ** 2 / 2.0) / (ns_k - 3.0)
    if weight == "invvar":
        w = 1.0 / var_z
        w = w / w.sum()
    elif weight == "equal":
        w = np.full(len(z), 1.0 / len(z))
    else:
        raise ValueError(f"未知 weight: {weight} (合法: 'equal' | 'invvar')")
    z_bar = float((w * z).sum())
    # 独立病人假设下 Var(z_bar)=Σ w_i² Var(z_i); invvar 时退化为 1/Σ(1/var) (与旧式一致)。
    se = float(np.sqrt((w ** 2 * var_z).sum()))
    rho_bar = float(np.tanh(z_bar))
    ci_lo = float(np.tanh(z_bar - 1.96 * se))
    ci_hi = float(np.tanh(z_bar + 1.96 * se))
    return rho_bar, ci_lo, ci_hi, int(keep.sum()), n_dropped


# ═══════════════════════════════════════════════════════════════════════════════
# 冻结表读取 + pooling 列名工具
# ═══════════════════════════════════════════════════════════════════════════════

def load_frozen(path=None):
    """读冻结肽级表 (只读)。返回 DataFrame; 强制 Patient_ID int, Elispot float。"""
    p = Path(path) if path else FROZEN_POOLED
    if not p.exists():
        sys.exit(f"[ERR] 冻结表不存在: {p}")
    df = pd.read_csv(p, encoding="utf-8")
    if "Patient_ID" not in df.columns or LABEL_COL not in df.columns:
        sys.exit(f"[ERR] 冻结表缺 Patient_ID/{LABEL_COL} 列: {p}")
    df["Patient_ID"] = df["Patient_ID"].astype(int)
    df[LABEL_COL] = pd.to_numeric(df[LABEL_COL], errors="coerce")
    return df


def pool_col(tool, pooling):
    """工具+pooling -> 冻结表列名 <Tool>_<pooling>。"""
    return f"{tool}_{pooling}"


def count_conf_col(tool, pooling):
    """工具+pooling -> 冻结表 count 混杂布尔列名 count_conf_<tool>_<pooling>。"""
    return f"count_conf_{tool}_{pooling}"


def is_count_confounded(df, tool, pooling):
    """该 <tool,pooling> 是否被标 count 混杂 (读冻结表 count_conf 布尔列, 跨肽恒定取任一行)。
    列缺失 -> 视为未标记 (False, 不排除); 全 NaN -> 同理 False。
    """
    c = count_conf_col(tool, pooling)
    if c not in df.columns:
        return False
    s = df[c].dropna()
    if len(s) == 0:
        return False
    return bool(s.iloc[0])


def present_patients(df, patients=None):
    """返回 df 中实际存在的目标患者 (默认 DS2 9 人), 升序。"""
    pats = patients if patients is not None else DS2_PATIENTS
    return sorted([p for p in pats if p in set(df["Patient_ID"].unique())])


# 新表 51 变体 pooling 家族前缀 (<tool>_ 之后的合法尾部)。
_POOLING_SUFFIX_FAMILIES = ("topk_", "softmax_", "rankdecay_")


def tool_pooling_cols(df, tool):
    """[Part B/C] 返回 df 中该工具的全部 pooling 列名 (新命名 51 变体:
    <tool>_max / <tool>_topk_k{k}_a{α} / <tool>_softmax_T{T} / <tool>_rankdecay_g{γ})。

    实现: 前缀 f"{tool}_" 匹配 + 尾部须属已知 pooling 家族 (max / topk_ / softmax_ /
    rankdecay_), 防工具名互为前缀误捕 (roster 已核 netMHCpan_BA/EL、NeoaG/NeoaPred 不冲突,
    尾部家族过滤再兜一层)。列顺序保留 df 出现序 (稳定)。
    """
    pre = f"{tool}_"
    cols = []
    for c in df.columns:
        if not c.startswith(pre):
            continue
        suf = c[len(pre):]
        if suf == "max" or suf.startswith(_POOLING_SUFFIX_FAMILIES):
            cols.append(c)
    return cols


# ═══════════════════════════════════════════════════════════════════════════════
# ★ 主指标: per-patient Spearman, Fisher-z 等权聚合 (封装, 与旧骨架口径逐位可比)
# ═══════════════════════════════════════════════════════════════════════════════

def per_patient_spearman(df, score, *, patients=None, min_pep=MIN_PEP,
                         label_col=LABEL_COL, return_perpat=False, weight="equal"):
    """逐病人 Spearman(score, label), 跨病人 Fisher-z 聚合 + 95%CI。

    score : df 列名 (str) 或与 df 等长 array/Series (fusion 返回值)。
    患者内 n_pep>=min_pep 才算 rho (否则该患者 rho=NaN, 不进聚合)。
    weight : [B1 · outline §2.6] 'equal' 等权 (默认) | 'invvar' 逆方差 (旧, 对照)。透传给
             fisherz_weighted_agg; 旧调用不传 → 默认 equal (有意口径切换, 见该函数 docstring)。
    返回 (rho_bar, ci_lo, ci_hi, n_used, n_dropped)；
    若 return_perpat=True 追加 (rhos_by_pat: dict, ns_by_pat: dict)。
    复用: fusion_12methods.per_patient_spearman 逻辑 + per_patient_spearman_multimethod 各患者 rho。
    """
    work = df
    if isinstance(score, str):
        col = score
    else:
        work = df.copy()
        col = "__score__"
        work[col] = np.asarray(score, dtype=float)

    pats = present_patients(work, patients)
    rhos, ns = [], []
    rhos_by_pat, ns_by_pat = {}, {}
    for pat in pats:
        g = work[work["Patient_ID"] == pat]
        n = len(g)
        x = g[col].values.astype(float)
        y = g[label_col].values.astype(float)
        rho = spearman_np(x, y) if n >= min_pep else np.nan
        rhos.append(rho)
        ns.append(float(n))
        rhos_by_pat[pat] = rho
        ns_by_pat[pat] = n

    rho_bar, ci_lo, ci_hi, n_used, n_dropped = fisherz_weighted_agg(
        np.array(rhos, float), np.array(ns, float), weight=weight)
    if return_perpat:
        return rho_bar, ci_lo, ci_hi, n_used, n_dropped, rhos_by_pat, ns_by_pat
    return rho_bar, ci_lo, ci_hi, n_used, n_dropped


def _partial_spearman_one(x, y, z):
    """[B2] 单病人偏 Spearman(x,y | z), 纯 numpy (禁 scipy.stats)。
    公式 r_xy.z = (r_xy - r_xz·r_yz)/sqrt((1-r_xz²)(1-r_yz²)); 任一 pairwise NaN 或分母<=0 → NaN。
    ★ x,y,z 须已是完整用例子集 (调用方先按 ~isnan 三者取交集), 保证三个 Spearman 同基。
    """
    r_xy = spearman_np(x, y)
    r_xz = spearman_np(x, z)
    r_yz = spearman_np(y, z)
    if np.isnan(r_xy) or np.isnan(r_xz) or np.isnan(r_yz):
        return np.nan
    denom = (1.0 - r_xz ** 2) * (1.0 - r_yz ** 2)
    if denom <= 0:
        return np.nan
    r = (r_xy - r_xz * r_yz) / np.sqrt(denom)
    return float(np.clip(r, -1.0, 1.0))


def per_patient_partial_spearman(df, score, ctrl="peplen", *, patients=None,
                                 min_pep=MIN_PEP, label_col=LABEL_COL,
                                 weight="equal", return_perpat=False):
    """[B2 · outline §2.6 · 新核心一等公民] 逐病人偏 Spearman(score, label | ctrl),
    跨病人等权 Fisher-z 聚合。控肽长 (或 n_subpep) 混杂: 隔离工具真 skill 与「肽长/子肽计数」搭便车。

    score : df 列名 (str) 或与 df 等长 array/Series (同 per_patient_spearman)。
    ctrl  : 控制变量列名 (默认 'peplen' 肽长; 亦可传 'n_subpep')。
    偏相关比 Spearman 多耗 1 自由度 → 病人内需 ≥4 有效点 (完整用例 = score/label/ctrl 三者非缺)。
    weight 透传 fisherz_weighted_agg (默认 equal)。返回 (rho_bar, ci_lo, ci_hi, n_used,
    n_dropped), 接口对齐 per_patient_spearman; return_perpat=True 追加 (rhos_by_pat, ns_by_pat)。
    """
    work = df
    if isinstance(score, str):
        col = score
    else:
        work = df.copy()
        col = "__score__"
        work[col] = np.asarray(score, dtype=float)
    if ctrl not in work.columns:
        sys.exit(f"[ERR] per_patient_partial_spearman: 控制列缺失 ctrl={ctrl}")

    pmin = max(int(min_pep), 4)   # 偏相关硬底 4 点 (比 Spearman 多耗 1 自由度)
    pats = present_patients(work, patients)
    rhos, ns = [], []
    rhos_by_pat, ns_by_pat = {}, {}
    for pat in pats:
        g = work[work["Patient_ID"] == pat]
        x = g[col].values.astype(float)
        y = g[label_col].values.astype(float)
        zc = g[ctrl].values.astype(float)
        m = ~(np.isnan(x) | np.isnan(y) | np.isnan(zc))   # 完整用例交集
        n = int(m.sum())
        rho = _partial_spearman_one(x[m], y[m], zc[m]) if n >= pmin else np.nan
        rhos.append(rho)
        ns.append(float(n))
        rhos_by_pat[pat] = rho
        ns_by_pat[pat] = n

    rho_bar, ci_lo, ci_hi, n_used, n_dropped = fisherz_weighted_agg(
        np.array(rhos, float), np.array(ns, float), weight=weight)
    if return_perpat:
        return rho_bar, ci_lo, ci_hi, n_used, n_dropped, rhos_by_pat, ns_by_pat
    return rho_bar, ci_lo, ci_hi, n_used, n_dropped


# ═══════════════════════════════════════════════════════════════════════════════
# ★ B2-multi 多变量残差控制: attach_confounders + per_patient_partial_spearman_multi
# ═══════════════════════════════════════════════════════════════════════════════

def _indel_from_variant_type(vt_series):
    """Variant_Type 列 -> is_indel float (DEL/INS=1.0, 其它含 SNV/NA=0.0)。大小写/空白不敏感。"""
    vt = vt_series.astype(str).str.upper().str.strip()
    return vt.isin(["DEL", "INS"]).astype(float)


def attach_confounders(df):
    """[B2-multi] 把多变量残差控制要用的混杂列补齐到 df 的副本并返回 (不改原 df)。

    补齐三列 (robustness 附表口径, 见 per_patient_partial_spearman_multi docstring):
      · peplen   : 肽长 (代理混杂; 主表通常已有, 缺则 warn 不补, 由调用方跳过该 ctrl)。
      · n_subpep : 一突变候选子肽数 (count 混杂; 主表已有, 缺则同上)。
      · is_indel : indel 突变标记 (更深机制混杂: indel 既触发多窗又本身真更免疫原)。
                   来源优先 WT_NA_indel_list.csv (列 mut_key,Variant_Type, DEL/INS=1),
                   按 mut_key merge; 未匹配肽 = SNV = 0。WT_NA 表缺失/无列 → 回退 GT
                   (ds2_official_groundtruth.csv 的 Variant_Type)。两源都拿不到 → warn 不补。

    peplen/n_subpep 已存在则原样保留 (不覆盖)。is_indel 已存在则原样保留 (不覆盖)。
    仅补列不删列; 与 per_partial 调用解耦, 任何脚本可先 attach_confounders(df) 再传 multi。
    """
    work = df.copy()

    for c in ("peplen", "n_subpep"):
        if c not in work.columns:
            print(f"[warn] attach_confounders: 主表缺 '{c}' 列, 该混杂无法补 (调用 multi 时会跳过)。")

    if "is_indel" in work.columns:
        return work

    if "mut_key" not in work.columns:
        print("[warn] attach_confounders: 主表无 'mut_key' 列, 无法 merge is_indel, 跳过。")
        return work

    vt_map = None                                   # mut_key -> Variant_Type
    if FROZEN_WT_NA_INDEL.exists():
        wt = pd.read_csv(FROZEN_WT_NA_INDEL, encoding="utf-8")
        if "mut_key" in wt.columns and "Variant_Type" in wt.columns:
            vt_map = wt.set_index("mut_key")["Variant_Type"]
    if vt_map is None and FROZEN_GT.exists():        # 回退 GT (全 130 肽都有 Variant_Type)
        gt = pd.read_csv(FROZEN_GT, encoding="utf-8")
        if "mut_key" in gt.columns and "Variant_Type" in gt.columns:
            vt_map = gt.set_index("mut_key")["Variant_Type"]

    if vt_map is None:
        print("[warn] attach_confounders: WT_NA_indel_list 与 GT 均无 Variant_Type, is_indel 跳过。")
        return work

    vt = work["mut_key"].map(vt_map)                 # 未匹配 (WT_NA 源下的 SNV) -> NaN
    # WT_NA 源只列 indel/WT-NA 肽 → 未匹配即 SNV → is_indel=0; GT 源则全表覆盖直接判。
    work["is_indel"] = _indel_from_variant_type(vt.fillna("SNV"))
    n_indel = int(work["is_indel"].sum())
    print(f"[attach_confounders] is_indel 补齐: indel={n_indel} / {len(work)} 肽 "
          f"(源={'WT_NA_indel_list' if FROZEN_WT_NA_INDEL.exists() else 'GT'})。")
    return work


def _rank_residual(rank_vec, ctrl_rank_mat):
    """[B2-multi] rank_vec(n,) 对 [截距 + ctrl_rank_mat(n,k)] 最小二乘残差 (np.linalg.lstsq)。
    ctrl_rank_mat 各列为已 rank 化的控制变量; rcond=None 用最小范数解, 天然容忍常量列共线。
    """
    n = len(rank_vec)
    A = np.column_stack([np.ones(n), ctrl_rank_mat]) if ctrl_rank_mat.size else np.ones((n, 1))
    coef, *_ = np.linalg.lstsq(A, rank_vec, rcond=None)
    return rank_vec - A @ coef


def per_patient_partial_spearman_multi(df, score, ctrls=("peplen", "n_subpep", "is_indel"),
                                       *, patients=None, min_pep=None, label_col=LABEL_COL,
                                       weight="equal", return_perpat=False):
    """[B2-multi · outline §2.6 robustness 附表口径] 逐病人 *多变量* 偏 Spearman:
    同时控 ctrls 全部混杂后, score 残差与 label 残差的 Spearman, 跨病人等权 Fisher-z 聚合。

    与单变量 per_patient_partial_spearman 的区别: 那个只能控 1 个 ctrl (偏相关闭式);
    本函数用 rank-based 残差化一次性联合控多个混杂 (peplen/n_subpep/is_indel):
      病人内对 score-rank 与 label-rank 各自用 [截距 + 各 ctrl 的 rank] 做最小二乘残差
      (np.linalg.lstsq), 再对两残差算 Spearman。等价于「秩空间偏相关」, 纯 numpy (禁 scipy)。

    混杂语义 (为何联合控):
      · peplen   = 肽长, 是免疫原性的 *代理* 混杂 (短肽更易呈递, 非工具真 skill)。
      · n_subpep = 候选子肽数, count 混杂 (sum/mean pooling 机械 ∝ 它, outline §3.2 自警)。
      · is_indel = indel 突变标记, 更深 *机制* 混杂: indel 既天然触发多子肽窗 (放大 count),
                   自身又真更免疫原 (移码新生表位) → 与工具分/标签双向关联, 单控 peplen 控不掉。
      单变量偏相关只能剥一层; 多变量联合残差化是「工具真信号 vs 全部已知混杂」的稳健下界,
      仅作 robustness 附表, headline 仍用主指标 per_patient_spearman (§2.6)。

    score  : df 列名 (str) 或与 df 等长 array/Series (同 per_patient_spearman)。
    ctrls  : 控制列名 tuple; df 中缺的列自动跳过 + warn (不 crash), 用剩余存在的 ctrl。
             (缺 is_indel 时先调 attach_confounders(df) 补齐。)
    min_pep: 病人内最少完整用例数; None → 硬底 len(有效ctrls)+2 (多控多耗自由度); 传值则取
             max(值, len(有效ctrls)+2)。完整用例 = score/label/全部有效 ctrl 均非缺。
    weight : 透传 fisherz_weighted_agg (默认 equal, §2.6)。
    返回 (rho_bar, ci_lo, ci_hi, n_used, n_dropped), 接口对齐 per_patient_partial_spearman;
    return_perpat=True 追加 (rhos_by_pat, ns_by_pat)。
    """
    work = df
    if isinstance(score, str):
        col = score
    else:
        work = df.copy()
        col = "__score__"
        work[col] = np.asarray(score, dtype=float)

    eff_ctrls = []
    for c in ctrls:
        if c in work.columns:
            eff_ctrls.append(c)
        else:
            print(f"[warn] per_patient_partial_spearman_multi: 控制列 '{c}' 缺失, 跳过该 ctrl。")
    if not eff_ctrls:
        sys.exit("[ERR] per_patient_partial_spearman_multi: 无任何有效控制列 (全缺)。")

    hard = len(eff_ctrls) + 2                        # 残差化多耗 len(ctrls)+1 自由度, +2 保余
    pmin = hard if min_pep is None else max(int(min_pep), hard)

    pats = present_patients(work, patients)
    rhos, ns = [], []
    rhos_by_pat, ns_by_pat = {}, {}
    for pat in pats:
        g = work[work["Patient_ID"] == pat]
        x = g[col].values.astype(float)
        y = g[label_col].values.astype(float)
        Z = np.column_stack([g[c].values.astype(float) for c in eff_ctrls])  # (n_g, k)
        m = ~(np.isnan(x) | np.isnan(y) | np.isnan(Z).any(axis=1))           # 完整用例交集
        n = int(m.sum())
        if n >= pmin:
            xr = pd.Series(x[m]).rank().values.astype(float)
            yr = pd.Series(y[m]).rank().values.astype(float)
            Zr = np.column_stack([pd.Series(Z[m, j]).rank().values.astype(float)
                                  for j in range(Z.shape[1])])
            res_x = _rank_residual(xr, Zr)
            res_y = _rank_residual(yr, Zr)
            rho = spearman_np(res_x, res_y)
        else:
            rho = np.nan
        rhos.append(rho)
        ns.append(float(n))
        rhos_by_pat[pat] = rho
        ns_by_pat[pat] = n

    rho_bar, ci_lo, ci_hi, n_used, n_dropped = fisherz_weighted_agg(
        np.array(rhos, float), np.array(ns, float), weight=weight)
    if return_perpat:
        return rho_bar, ci_lo, ci_hi, n_used, n_dropped, rhos_by_pat, ns_by_pat
    return rho_bar, ci_lo, ci_hi, n_used, n_dropped


# ═══════════════════════════════════════════════════════════════════════════════
# ★ B4 显著性: cluster bootstrap over patients CI + 病人配对置换检验 (纯 numpy)
# ═══════════════════════════════════════════════════════════════════════════════

def bootstrap_patient_ci(df, score_or_fn, *, n_boot=2000, seed=42, metric="spearman",
                         ctrl=None, patients=None, min_pep=MIN_PEP, label_col=LABEL_COL):
    """[B4 · outline §2.6] cluster bootstrap over patients 的 95%CI (弃固定效应过窄 CI)。
    有放回重采样病人 (n_boot 次), 每次对采到的病人等权 Fisher-z 聚合 ρ̄。

    score_or_fn : df 列名 (str) | 与 df 等长 array | callable(df)->array。★ score 只在全 df 上
      算一次 (每病人 rho 预算), 再对病人重采样 → 对 per-patient 独立指标 (Spearman/partial,
      含病人内 rank fusion) 严格正确; 对依赖跨病人的 LOPO 学习型仅近似 (非 B4 用例)。
    metric='spearman' 用 per_patient_spearman; ctrl 非 None → 自动走 per_patient_partial_spearman。
    返回 (rho_point, ci_lo_2p5, ci_hi_97p5, boot_array)。seed 固定 (np.random.default_rng)。
    """
    rng = np.random.default_rng(seed)
    if callable(score_or_fn):
        score = np.asarray(score_or_fn(df), dtype=float)
    elif isinstance(score_or_fn, str):
        score = score_or_fn                      # 列名透传, 保留 partial 读列语义
    else:
        score = np.asarray(score_or_fn, dtype=float)

    if ctrl is not None:
        _, _, _, _, _, rhos_by, ns_by = per_patient_partial_spearman(
            df, score, ctrl=ctrl, patients=patients, min_pep=min_pep,
            label_col=label_col, weight="equal", return_perpat=True)
    else:
        _, _, _, _, _, rhos_by, ns_by = per_patient_spearman(
            df, score, patients=patients, min_pep=min_pep,
            label_col=label_col, weight="equal", return_perpat=True)

    pats = present_patients(df, patients)
    rho_arr = np.array([rhos_by[p] for p in pats], float)
    n_arr = np.array([float(ns_by[p]) for p in pats], float)

    rho_point = fisherz_weighted_agg(rho_arr, n_arr, weight="equal")[0]

    K = len(pats)
    boot = np.full(n_boot, np.nan)
    for b in range(n_boot):
        if K == 0:
            break
        samp = rng.integers(0, K, size=K)        # 有放回重采样病人 (允许重复)
        boot[b] = fisherz_weighted_agg(rho_arr[samp], n_arr[samp], weight="equal")[0]

    boot_valid = boot[~np.isnan(boot)]
    if len(boot_valid) == 0:
        return rho_point, np.nan, np.nan, boot
    ci_lo = float(np.percentile(boot_valid, 2.5))
    ci_hi = float(np.percentile(boot_valid, 97.5))
    return rho_point, ci_lo, ci_hi, boot


def paired_patient_test(df, score_a, score_b, *, ctrl=None, patients=None,
                        min_pep=MIN_PEP, label_col=LABEL_COL, n_perm=10000, seed=42):
    """[B4 · outline §2.6] 两方法病人配对显著性: 每病人算两法 per-patient (partial) Spearman 的
    Fisher-z, 取差 (z_a - z_b), 纯 numpy 双侧符号置换检验 (避 scipy.stats/OMP)。
    ctrl 非 None → 两法都用偏相关 (控该混杂)。
    返回 (delta_zbar, p_permutation, n): delta_zbar=配对病人 z 差均值 (Fisher-z 空间);
      p=双侧符号置换 (配对病人数 K<=20 精确枚举 2^K, 否则 seed 固定随机 n_perm 次)。
    """
    def _perpat(s):
        if ctrl is not None:
            return per_patient_partial_spearman(
                df, s, ctrl=ctrl, patients=patients, min_pep=min_pep,
                label_col=label_col, weight="equal", return_perpat=True)
        return per_patient_spearman(
            df, s, patients=patients, min_pep=min_pep,
            label_col=label_col, weight="equal", return_perpat=True)

    _, _, _, _, _, ra, na = _perpat(score_a)
    _, _, _, _, _, rb, nb = _perpat(score_b)

    pats = present_patients(df, patients)
    diffs = []
    for p in pats:
        va, vb = ra.get(p, np.nan), rb.get(p, np.nan)
        if np.isnan(va) or np.isnan(vb):
            continue
        # 两法在该病人都需 n>FISHER_MIN_N (与聚合 keep 口径一致)
        if na.get(p, 0) <= FISHER_MIN_N or nb.get(p, 0) <= FISHER_MIN_N:
            continue
        za = np.arctanh(np.clip(va, -FISHER_CLIP, FISHER_CLIP))
        zb = np.arctanh(np.clip(vb, -FISHER_CLIP, FISHER_CLIP))
        diffs.append(za - zb)
    diffs = np.asarray(diffs, float)
    K = len(diffs)
    if K == 0:
        return np.nan, np.nan, 0
    observed = float(diffs.mean())
    if K <= 20:
        signs = np.array(list(itertools.product([1.0, -1.0], repeat=K)))   # 2^K × K 精确
        perm_means = (signs * diffs[np.newaxis, :]).mean(axis=1)
    else:
        rng = np.random.default_rng(seed)
        signs = rng.choice(np.array([1.0, -1.0]), size=(n_perm, K))
        perm_means = (signs * diffs[np.newaxis, :]).mean(axis=1)
    p = float(np.mean(np.abs(perm_means) >= np.abs(observed) - 1e-12))
    return observed, p, K


def best_pooling_for_tool(df, tool, *, patients=None, min_pep=MIN_PEP, count_clean=None,
                          weight="equal"):
    """[Part B/C] 该工具全部 pooling 变体 (新表 51 个) 各算 per-patient 等权 Fisher-z ρ̄,
    返回 (best_pooling, best_rho, all: dict)。缺列/全 NaN 的变体跳过。

    ★ 返回 best_pooling = pooling 后缀名 (如 'max' / 'topk_k20_a0' / 'softmax_T1'),
      与旧契约一致 → 调用方仍可 pool_col(tool, best_pooling) 还原完整列名 (R2/R3/R5/R6 不改)。

    ⚠️ 定位: 这是 outline §3.2 描述性研究用的 in-sample 上界 (B5 selection 上界) —— 在同一
       held-in 数据上遍历全 51 变体挑 ρ̄ 最高 = 乐观选择偏 (over-fit pooling)。★ headline 一律
       用零选择的 <tool>_max (pool_col(tool,'max')), 不用本函数的挑选结果当主结果。

    weight : per-patient 聚合权 (默认 'equal', outline §2.6); 透传 per_patient_spearman。
    count_clean : 【已弃用, B2 偏相关取代】保留签名兼容; 传任何非 None 值 → 忽略 + warn 一次。
      弃用理由: 旧 count-clean 靠冻结表 count_conf 布尔列排除 n_subpep 混杂的整列 pooling;
      新干净表 pooled_clean_9mer.csv 不再带 count_conf 列, 改由 per_partial_spearman(ctrl=
      'peplen'/'n_subpep') 在度量层直接偏相关控混杂 (outline §2.6), 比排除整列更细。

    返回 dict 附加键: __weight__, __count_clean__ (恒 False, 弃用)。
    """
    if count_clean is not None:
        print(f"[warn] best_pooling_for_tool: count_clean 参数已弃用 (B2 偏相关取代), 忽略。")

    out = {}
    for c in tool_pooling_cols(df, tool):
        pl = c[len(tool) + 1:]                    # 去 "<tool>_" 前缀 → pooling 后缀名
        if df[c].notna().sum() == 0:
            out[pl] = np.nan
            continue
        rho, *_ = per_patient_spearman(df, c, patients=patients, min_pep=min_pep,
                                       weight=weight)
        out[pl] = rho
    valid = {k: v for k, v in out.items() if v is not None and not np.isnan(v)}

    out["__weight__"] = weight
    out["__count_clean__"] = False               # 弃用, 恒 False
    if not valid:
        return None, np.nan, out
    best = max(valid, key=valid.get)
    return best, valid[best], out


# ═══════════════════════════════════════════════════════════════════════════════
# 8 无监督 fusion 组合子 (照抄 fusion_12methods.py; R = n×D 病人内 rank 矩阵)
# ═══════════════════════════════════════════════════════════════════════════════

def fuse_mean_rank(R):           return np.nanmean(R, axis=1)
def fuse_geomean(R, eps=1e-9):   return np.exp(np.nanmean(np.log(np.maximum(R, eps)), axis=1))
def fuse_median(R):              return np.nanmedian(R, axis=1)
def fuse_powmean(R, p=2.0):      return np.nanmean(np.power(R, p), axis=1) ** (1.0 / p)
def fuse_max(R):                 return np.nanmax(R, axis=1)
def fuse_min(R):                 return np.nanmin(R, axis=1)


def fuse_weighted_mean_rank(R, weights=None):
    D = R.shape[1]
    w = np.ones(D, float) if weights is None else np.asarray(weights, float)
    w = w / w.sum()
    return np.nansum(R * w[np.newaxis, :], axis=1)


def fuse_softmax_rank(R, T=1.0):
    logits = R / T
    logits = logits - np.nanmax(logits, axis=1, keepdims=True)
    w = np.exp(logits)
    w = w / np.nansum(w, axis=1, keepdims=True)
    return np.nansum(w * R, axis=1)


UNSUPERVISED_FUSIONS = {
    "mean_rank": fuse_mean_rank, "geomean": fuse_geomean, "median": fuse_median,
    "powmean": fuse_powmean, "max": fuse_max, "min": fuse_min,
    "weighted_mean_rank": fuse_weighted_mean_rank, "softmax_rank": fuse_softmax_rank,
}
LEARNING_FUSIONS = {"ridge", "gbdt", "stacking", "constrained"}
METHOD_ORDER = [
    "mean_rank", "geomean", "median", "powmean", "max", "min",
    "weighted_mean_rank", "softmax_rank",
    "stacking", "constrained", "ridge", "gbdt",
]


# ═══════════════════════════════════════════════════════════════════════════════
# 学习型支撑: impute_fold / find_ridge_alpha / 单纯形投影 (照抄 fusion_study + 12methods)
# ═══════════════════════════════════════════════════════════════════════════════

def impute_fold(train_df, test_df, feature_cols):
    """折内填补: 训练折各列均值填训练&测试折缺失。防泄漏。照抄 fusion_study.py。"""
    train_f, test_f = train_df.copy(), test_df.copy()
    for col in feature_cols:
        if col not in train_f.columns:
            continue
        col_mean = train_f[col].mean()
        if np.isnan(col_mean):
            col_mean = 0.0
        train_f[col] = train_f[col].fillna(col_mean)
        if col in test_f.columns:
            test_f[col] = test_f[col].fillna(col_mean)
    return train_f, test_f


def effective_dof(X, alpha):
    _, s, _ = np.linalg.svd(X, full_matrices=False)
    return float(np.sum(s ** 2 / (s ** 2 + alpha)))


def find_ridge_alpha(X, target_dof=2.5, n_grid=200):
    """logspace 网格搜 eff_DOF≈target_dof 的 alpha。照抄 fusion_study.py。"""
    _, s, _ = np.linalg.svd(X, full_matrices=False)
    s_sq_max = float(s[0] ** 2) if len(s) > 0 else 1.0
    alpha_grid = np.logspace(np.log10(max(s_sq_max * 1e-3, 1e-4)),
                             np.log10(s_sq_max * 1e7 + 1.0), n_grid)
    dofs = np.array([effective_dof(X, a) for a in alpha_grid])
    idx = int(np.argmin(np.abs(dofs - target_dof)))
    return float(alpha_grid[idx]), float(dofs[idx])


def _project_simplex(v):
    """欧氏投影到概率单纯形 {w>=0, Σw=1} (Duchi 2008)。照抄 fusion_12methods.py。"""
    v = np.asarray(v, float)
    n = len(v)
    u = np.sort(v)[::-1]
    css = np.cumsum(u)
    rho_idx = np.nonzero(u * np.arange(1, n + 1) > (css - 1.0))[0]
    if len(rho_idx) == 0:
        return np.ones(n) / n
    rho = rho_idx[-1]
    theta = (css[rho] - 1.0) / (rho + 1.0)
    return np.maximum(v - theta, 0.0)


def _fit_simplex(X, y, n_iter=2000):
    """投影梯度下降解 min‖Xw-y‖² s.t. w>=0,Σw=1。照抄 fusion_12methods.py。"""
    D = X.shape[1]
    if D == 1:
        return np.ones(1)
    w = np.ones(D) / D
    XtX = X.T @ X
    Xty = X.T @ y
    L = float(np.linalg.norm(XtX, 2)) + 1e-9
    lr = 1.0 / L
    for _ in range(n_iter):
        grad = XtX @ w - Xty
        w = _project_simplex(w - lr * grad)
    return w


def _lopo_scores(df, dim_cols, method, patients, label_col, seed, dof_target):
    """patient-level LOPO out-of-fold 预测 (照抄 fusion_12methods._lopo_scores 防泄漏协议)。
    缺失用训练折均值填; 标准化用训练折统计。返回 Series (index 对齐, 仅 patients 行有值)。
    """
    from sklearn.linear_model import Ridge, LinearRegression
    from sklearn.ensemble import GradientBoostingRegressor

    result = pd.Series(np.nan, index=df.index, dtype=float)
    universe = df[df["Patient_ID"].isin(patients)]
    for pat in patients:
        test_mask = universe["Patient_ID"] == pat
        train_raw = universe[~test_mask].copy()
        test_raw = universe[test_mask].copy()
        if len(test_raw) == 0:
            continue
        train_df, test_df = impute_fold(train_raw, test_raw, dim_cols)
        X_train = train_df[dim_cols].values.astype(float)
        X_test = test_df[dim_cols].values.astype(float)
        y_train = train_df[label_col].values.astype(float)
        valid = ~np.isnan(y_train)
        X_train, y_train = X_train[valid], y_train[valid]
        if len(X_train) == 0:
            continue
        X_mean = np.nanmean(X_train, axis=0)
        X_std = np.nanstd(X_train, axis=0)
        X_std[X_std < 1e-10] = 1.0
        Xtr = (X_train - X_mean) / X_std
        Xte = (X_test - X_mean) / X_std
        if method == "ridge":
            alpha_best, _ = find_ridge_alpha(Xtr, target_dof=dof_target)
            m = Ridge(alpha=alpha_best, fit_intercept=True)
            m.fit(Xtr, y_train)
            pred = m.predict(Xte)
        elif method == "gbdt":
            m = GradientBoostingRegressor(random_state=seed, **GBDT_PARAMS)
            m.fit(Xtr, y_train)
            pred = m.predict(Xte)
        elif method == "stacking":
            m = LinearRegression(fit_intercept=True)
            m.fit(Xtr, y_train)
            pred = m.predict(Xte)
        elif method == "constrained":
            yc = y_train - y_train.mean()
            w = _fit_simplex(Xtr, yc)
            pred = Xte @ w
        else:
            raise ValueError(f"未知学习型 method: {method}")
        result.loc[test_df.index] = pred
    return result


# ═══════════════════════════════════════════════════════════════════════════════
# ★ 统一入口 apply_fusion (照抄 fusion_12methods.py)
# ═══════════════════════════════════════════════════════════════════════════════

def apply_fusion(df, dim_cols, method, *, label_col=LABEL_COL, patients=None,
                 seed=42, dof_target=2.5, **params):
    """对 dim_cols 应用某 fusion 法, 返回每行综合分 Series (index 对齐)。
    无监督 (前 8): 病人内各维升序 rank → 组合子 (不碰标签, leak-free)。
    学习型 (ridge/gbdt/stacking/constrained): patient-level LOPO out-of-fold (无泄漏)。
    """
    present = [c for c in dim_cols if c in df.columns]
    missing = [c for c in dim_cols if c not in df.columns]
    if missing:
        print(f"[warn] apply_fusion: 维度列缺失已剔除: {missing}")
    if len(present) == 0:
        return pd.Series(np.nan, index=df.index, dtype=float)

    if patients is None:
        patients = sorted(df["Patient_ID"].unique().tolist())

    if method in LEARNING_FUSIONS:
        return _lopo_scores(df, present, method, patients, label_col, seed, dof_target)
    if method not in UNSUPERVISED_FUSIONS:
        raise ValueError(f"未知 method: {method} (合法: {METHOD_ORDER})")

    combiner = UNSUPERVISED_FUSIONS[method]
    result = pd.Series(np.nan, index=df.index, dtype=float)
    for pat, g in df.groupby("Patient_ID"):
        if pat not in patients:
            continue
        sub = g[present].astype(float)
        filled = sub.fillna(sub.mean()).fillna(0.0)
        R = np.column_stack([
            filled[c].rank(method="average").values.astype(float) for c in present])
        s = combiner(R, **params)
        result.loc[g.index] = np.asarray(s, dtype=float)
    return result


FUSION_METHODS = {name: functools.partial(apply_fusion, method=name)
                  for name in METHOD_ORDER}


def resolve_out_dir(default_base=None):
    """[新切输出隔离] 解析输出根目录 —— 只影响【落盘位置】, 绝不影响任何读入/计算/统计/随机种子。

    优先级: 环境变量 QIB_OUTDIR (设了且非空 → 用它) > default_base (默认 OUT_DIR=analysis/official/)。
    · QIB_OUTDIR 可为绝对路径, 或相对 ROOT (QuantImmuBench/) 的路径。
    · 默认 (未设 QIB_OUTDIR) 逐字节等价旧行为: 返回 default_base, 完全向后兼容。
    · default_base=None → OUT_DIR。供 fusion_cv 等【非 official 目录】脚本传各自 HERE 复用同一 env
      (设了 QIB_OUTDIR 时全体重定向到同一新切目录; 未设时各自守自己的默认目录)。
    动机: 新切 canonical 重跑时 `set QIB_OUTDIR=.../newcut9mer` 即把全体 R/S/Q 输出重定向到独立
      子目录, 防覆盖旧切固定文件名结果 + 防并行 sweep 互相踩踏 (零脚本逐个改)。"""
    base = OUT_DIR if default_base is None else Path(default_base)
    override = os.environ.get("QIB_OUTDIR", "").strip()
    if not override:
        return base
    p = Path(override)
    if not p.is_absolute():
        p = ROOT / p
    return p


def ensure_out_dir():
    """输出目录 (mkdir -p 后返回)。默认 OUT_DIR=analysis/official/; 若设 env QIB_OUTDIR 则重定向到它
    (新切 canonical 重跑写独立子目录, 见 resolve_out_dir)。默认 (未设 env) 行为逐字节不变。"""
    d = resolve_out_dir()
    d.mkdir(parents=True, exist_ok=True)
    return d


def r6(v, d=6):
    """安全 round (None/NaN -> np.nan)。"""
    if v is None:
        return np.nan
    try:
        fv = float(v)
    except (TypeError, ValueError):
        return np.nan
    return round(fv, d) if not np.isnan(fv) else np.nan
