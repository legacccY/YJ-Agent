#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pooling_sweep.py
服务: quantimmu-bench / lever=pooling 维度扩展 + 二维扫描

================== 架构（两级聚合）==================
  Level-1 Pooling:
    一个肽的所有子肽×HLA 分数数组 arr → 肽级标量
    8 种算子: max / mean / top3mean / sum / geomean / softmax / topk_w / rankdecay
    arr 先去 NaN，再降序排列 s_1>=s_2>=...>=s_n，再计算。

  Level-2 CrossPatientAgg:
    DS2 肽级分 → 每患者内 Spearman ρ_i（min_pep=3）→ 跨患者聚合
    3 种: fisherz_weighted / median / simple_mean
    函数体直接复制自 per_patient_spearman_multimethod.py，未 import 原文件。

================== 8 种 Pooling 数学定义 ==================
  1. max        : s_1
  2. mean       : (1/n) * Σ s_i
  3. top3mean   : mean(s_1,...,s_{min(3,n)})（降序前三）
  4. sum        : Σ s_i
  5. geomean    : (Π arr')^(1/n)，若 min(arr)<=0 先平移 arr'=arr-min(arr)+eps(1e-9)
  6. softmax(T) : Σ w_i*s_i，w_i=exp((s_i-max(s))/T)/Σexp(…)（数值稳定减max）
  7. topk_w(k,scheme): Σ_{i<=k} w_i*s_i / Σ w_i（inv_rank: w_i=1/i; linear: k+1-i; equal: 1）
  8. rankdecay(d)     : Σ d^(i-1)*s_i / Σ d^(i-1)（i从1，降序）

参数 TODO 待 researcher/朱实验室对账:
  - softmax T=1.0 默认；各工具分数尺度不同，T 需独立校准；见 POOLINGS_SENSITIVITY 三温度扫描
  - topk_w k=5, weight_scheme='inv_rank' 默认；候选 k∈[3,5,10]；见 POOLINGS_SENSITIVITY
  - rankdecay d=0.5 默认；候选 d∈[0.3,0.5,0.8]；见 POOLINGS_SENSITIVITY

================== 四个输出 ==================
  analysis/pooling_global_spearman.csv
    列: Tool, Pooling, n_pep, Spearman_rho, Spearman_pval, pval_note,
        count_confounded, pending_DTU_consent, hlathena_caveat
    逻辑: 每(Tool, Pooling) → 全 DS2 肽级 Spearman（正态近似 p 值）

  analysis/pooling_2d_scan.csv
    列: Tool, Pooling, CrossAgg, headline_value, n_patients_used, ci_lo, ci_hi,
        count_confounded, pending_DTU_consent, hlathena_caveat
    逻辑: 每(Tool, Pooling) → per-patient ρ_i → 3 种跨患者 agg

  analysis/pooling_best_per_tool.csv
    列: Tool, best_pooling, best_rho, rho_max_baseline, delta_best_minus_max,
        underestimated_by_max, best_pooling_countsafe, best_rho_countsafe,
        delta_countsafe_minus_max, underestimated_by_max_countsafe,
        sum_is_confound_note, crosscheck_note, pending_DTU_consent, hlathena_caveat
    逻辑: naive 最优（含混杂）+ count-safe 最优（排 count_confounded=True 的 pooling）

  analysis/pooling_count_confound.csv   ← 新增混杂诊断
    列: Tool, Pooling, rho_pooled_vs_nsubpep, n_pep
    逻辑: 肽级分数 vs 子肽数 Spearman；|rho|>COUNT_CONFOUND_THRESH=0.5 → count_confounded=True
          sum 必超（实测~0.75）；n_subpep↔Elispot=0.16, Peptide_Length↔Elispot=0.31

================== 对账标注 ==================
  max/mean/top3mean 三种 pooling 的 Spearman_rho 应与
  metrics_ds2_9tools.csv（Aggregation 列×Spearman_rho）一致。
  注: merge_metrics_9tools.py 用 scipy.stats.spearmanr，本文件用 spearman_np
  (rank Pearson)，数学等价但可能有浮点末位差异。

================== DTU 说明 ==================
  当前 9 工具均 pending_DTU_consent=False:
    PRIME: 学术免费已 clone，不需要 DTU 同意
    netMHCpan-BA: 新波次，尚未进入 9tools 表（若未来纳入须在 PENDING_DTU 改 True 并补同意书）
  HLAthena: presentation proxy（预测 MHC-I 提呈，非免疫原性），ELISpot 上预期近随机

================== 跑法 ==================
  python analysis/pooling_sweep.py
  python analysis/pooling_sweep.py --input scripts/out/merged_all_tools_9tools.xlsx
  python analysis/pooling_sweep.py --min_pep 3 --sensitivity
"""

import sys
import argparse
from pathlib import Path
from functools import partial
from math import erf, sqrt as msqrt

import numpy as np
import pandas as pd

# UTF-8 stdout (Windows 必要)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent

# ── 常量 ─────────────────────────────────────────────────────────────────────
PATIENT_COL_CANDIDATES = ["Patient_ID", "Patient", "PatientID", "patient_id",
                           "Subject", "Sample_ID"]
MIN_PEP_DEFAULT = 3        # 患者内 Spearman 最少肽数
FISHER_CLIP     = 0.9999   # rho=±1 → arctanh(±inf)，clip 到此
FISHER_MIN_N    = 3        # n_i<=3 → Var 分母 n-3<=0，剔出 Fisher-z 加权
ALL_PATIENTS    = [101, 102, 104, 105, 106, 107, 108, 109, 110]

# count 混杂判定阈值: |rho(pooled_score, n_subpeptides)| > 0.5 → 该 pooling 受子肽数驱动
# 实测均值: sum=0.747 / top3mean=0.330 / topk_w=0.339 / rankdecay=0.328
#            max=0.238 / geomean=0.080 / mean=0.036 / softmax=0.032
# 0.5 保守中线: 隔开 sum(混杂) 与其余（部分 count 敏感但远低于 sum）
# 参考: n_subpep↔Elispot=0.16, Peptide_Length↔Elispot=0.31, n_subpep↔Length=0.79
COUNT_CONFOUND_THRESH = 0.5

# 排除非工具 MT_* 列（复制自 per_patient_spearman_multimethod.py）
EXCLUDE = {"MT_FullPeptide", "MT_Subpeptide", "MT_NOAH", "MT_NetCleave",
           "MT_Stab_peptide", "MT_TCR_contact"}

# DTU 同意书状态（当前 9 工具）
# True  = 部署/发表前需取得 DTU 同意（暂无），False = 学术免费/已取得/不在表内
# 未来若纳入 netMHCpan-BA 等 DTU 工具，须在此改为 True 并附同意书
PENDING_DTU = {
    "DeepImmuno": False,
    "PredIG":     False,
    "IMPROVE":    False,
    "NeoTImmuML": False,
    "pTuneos":    False,
    "PRIME":      False,    # 学术免费已 clone，无需 DTU
    "ImmuneApp":  False,
    "deepHLApan": False,
    "HLAthena":   False,    # presentation proxy，非免疫原性工具，近随机预期
    # 示例（未来扩展）: "netMHCpan-BA": True,
}


# ── 纯 numpy Spearman（复制自 per_patient_spearman_multimethod.py，禁 scipy 防 OMP#15）
def spearman_np(x, y):
    """纯 numpy Spearman (rank Pearson), 避免 scipy.stats 与 torch 抢 OpenMP。"""
    x = np.asarray(x, float)
    y = np.asarray(y, float)
    m = ~(np.isnan(x) | np.isnan(y))
    x, y = x[m], y[m]
    n = len(x)
    if n < 3 or len(np.unique(x)) < 2 or len(np.unique(y)) < 2:
        return np.nan
    rx = pd.Series(x).rank().values
    ry = pd.Series(y).rank().values
    rx -= rx.mean()
    ry -= ry.mean()
    denom = np.sqrt((rx ** 2).sum() * (ry ** 2).sum())
    if denom == 0:
        return np.nan
    return float((rx * ry).sum() / denom)


def spearman_pval_approx(rho, n):
    """
    Spearman rho 双尾 p 值（正态近似，适用于 n>20）。
    t = rho * sqrt(n-2) / sqrt(1-rho^2)，大 n 时 t ~ N(0,1)。
    用 math.erf 实现正态 CDF（stdlib，无 OMP 风险）。
    TODO: n<20 时近似误差较大；精确 p 值需 scipy.stats.t.sf（因 OMP#15 禁用）。
    """
    if np.isnan(rho) or n < 4:
        return np.nan
    rho2 = min(rho ** 2, 1.0 - 1e-15)
    t_stat = rho * msqrt((n - 2) / max(1.0 - rho2, 1e-15))
    p_one = 0.5 * (1.0 - erf(abs(t_stat) / msqrt(2.0)))
    return float(2.0 * p_one)


# ── 跨患者聚合（复制自 per_patient_spearman_multimethod.py，不 import 原文件）──────

def fisherz_weighted(rhos, ns):
    """
    Fisher-z 固定效应加权均值 + 95% CI（主报方法）。
    Spearman 专用方差: Var(z_i) = (1 + rho_i^2/2) / (n_i - 3)
    [Fieller-Hartley-Pearson 1957, Biometrika 44:470]
    rho=±1 → clip ±FISHER_CLIP; n_i<=FISHER_MIN_N → 剔出（Var 分母<=0）。
    返回: (rho_bar, ci_lo, ci_hi, n_used, n_dropped)
    """
    rhos = np.asarray(rhos, float)
    ns   = np.asarray(ns, float)
    valid = ~np.isnan(rhos)
    rhos, ns = rhos[valid], ns[valid]
    keep = ns > FISHER_MIN_N
    n_dropped = int((~keep).sum())
    rhos_k, ns_k = rhos[keep], ns[keep]
    if len(rhos_k) == 0:
        return np.nan, np.nan, np.nan, 0, n_dropped
    rhos_k = np.clip(rhos_k, -FISHER_CLIP, FISHER_CLIP)
    z     = np.arctanh(rhos_k)
    var_z = (1.0 + rhos_k ** 2 / 2.0) / (ns_k - 3.0)
    w     = 1.0 / var_z
    sum_w = w.sum()
    z_bar   = (w * z).sum() / sum_w
    rho_bar = float(np.tanh(z_bar))
    ci_lo   = float(np.tanh(z_bar - 1.96 / np.sqrt(sum_w)))
    ci_hi   = float(np.tanh(z_bar + 1.96 / np.sqrt(sum_w)))
    return rho_bar, ci_lo, ci_hi, int(keep.sum()), n_dropped


# ── Pooling 内部辅助 ──────────────────────────────────────────────────────────

def _sort_desc(arr):
    """去 NaN，降序排列，返回连续 numpy 数组 s_1>=s_2>=...>=s_n。"""
    arr = np.asarray(arr, float)
    arr = arr[~np.isnan(arr)]
    if len(arr) == 0:
        return arr
    return np.sort(arr)[::-1].copy()


# ── 8 种 Pooling 算子 ─────────────────────────────────────────────────────────

def pool_max(arr):
    """
    max pooling.
    数学定义: f(arr) = s_1 = max(arr)
    """
    s = _sort_desc(arr)
    if len(s) == 0:
        return np.nan
    return float(s[0])


def pool_mean(arr):
    """
    mean pooling（算术均值）.
    数学定义: f(arr) = (1/n) * Σ_{i=1}^{n} s_i
    """
    s = _sort_desc(arr)
    if len(s) == 0:
        return np.nan
    return float(s.mean())


def pool_top3mean(arr, k=3):
    """
    top-k mean pooling（默认 k=3）.
    数学定义: f(arr) = mean(s_1, s_2, ..., s_{min(k,n)})
    降序后取前 k 个求均值；不足 k 取全部（不补 0 不丢肽）。
    """
    s = _sort_desc(arr)
    if len(s) == 0:
        return np.nan
    return float(s[:min(k, len(s))].mean())


def pool_sum(arr):
    """
    sum pooling.
    数学定义: f(arr) = Σ_{i=1}^{n} s_i
    ⚠ CRITICAL — count 混杂:
      实测 DeepImmuno rho(sum_score, n_subpep)=0.96；8 工具均值≈0.747，远超阈值 0.5。
      n_subpep≈肽长度（n_sub↔Length rho=0.79），而 Length↔Elispot=0.31（弱）→
      sum 的「提升」几乎完全来自长度泄漏，非真实聚合增益。
      DeepImmuno 用 sum 从 rho=-0.12 翻至 +0.29，但 per-patient 2D 内长度变量不消。
      pooling_count_confound.csv 记录每工具 rho_pooled_vs_nsubpep；
      pooling_global/2d_scan.csv 中 count_confounded=True。
      建议: 仅作探索对照，不作主报；优先选 count_confounded=False 的算子。
    """
    s = _sort_desc(arr)
    if len(s) == 0:
        return np.nan
    return float(s.sum())


def pool_geomean(arr, eps=1e-9):
    """
    几何均值 pooling.
    数学定义: f(arr) = (Π_{i=1}^{n} arr'_i)^(1/n)，其中：
      - 若 min(arr) <= 0: arr' = arr - min(arr) + eps（平移保证全正）
      - 否则: arr' = arr
      eps = 1e-9 防对数退化。
    平移处理说明:
      分数可能含负值或零（如 log-odds 型工具）；平移改变绝对尺度但保留相对秩序，
      保证几何均值可计算。平移量等于 abs(min)+eps，对相关系数方向无影响。
    参数:
      eps (float): 最小平移量，默认 1e-9。
    """
    s = _sort_desc(arr)
    if len(s) == 0:
        return np.nan
    # s 降序，s[-1] 为最小值
    if s[-1] <= 0:
        s = s - s[-1] + eps
    return float(np.exp(np.mean(np.log(np.maximum(s, eps)))))


def pool_softmax(arr, T=1.0):
    """
    softmax 温度加权均值.
    数学定义: f(arr) = Σ_i w_i * s_i
      w_i = exp((s_i - max(s)) / T) / Σ_j exp((s_j - max(s)) / T)
    数值稳定: 每次 exp 前减去 max(s/T)，防上溢；最大权重对应 s_1。
    参数:
      T (float): 温度系数，默认 1.0。
        T→0: 逼近 max pooling（最大分数主导）
        T→∞: 逼近 mean pooling（均匀权重）
    TODO 待对账:
      - 分数尺度因工具而异（概率 vs log-odds vs 原始整数分），T 对不同工具
        的效果差异显著，需各工具独立校准。
      - 默认 T=1.0 仅为占位起始值；最优 T 见 POOLINGS_SENSITIVITY 三温度对比
        (T∈{0.1, 1.0, 10.0})，最终参数待与朱实验室对账后确认。
    """
    s = _sort_desc(arr)
    if len(s) == 0:
        return np.nan
    logits  = s / T
    logits -= logits.max()       # 数值稳定：max后最大项=0，exp(0)=1
    w  = np.exp(logits)
    w /= w.sum()
    return float((w * s).sum())


def pool_topk_w(arr, k=5, weight_scheme="inv_rank"):
    """
    Top-k 排名加权均值.
    数学定义: f(arr) = Σ_{i=1}^{min(k,n)} w_i * s_i / Σ_{i=1}^{min(k,n)} w_i
    参数:
      k (int): 取分最高的 k 个子肽，默认 5；不足 k 取全部。
      weight_scheme (str): 权重方案，默认 'inv_rank'。
        'inv_rank': w_i = 1/i（i=1 得最高权重 1，i=2 得 1/2，…，名次递减权重递降）
        'linear':   w_i = k+1-i（线性递减：第1名 k，第2名 k-1，…，第k名 1）
        'equal':    w_i = 1（等权，等价于 pool_top3mean 对 k 的泛化）
    TODO 待对账:
      - k=5 为经验默认；候选 k∈{3,5,10}，敏感性见 POOLINGS_SENSITIVITY。
      - weight_scheme 选择待与朱实验室对账。
      - 不足 k 时不补 0，直接对实际 min(k,n) 个值加权。
    """
    s = _sort_desc(arr)
    if len(s) == 0:
        return np.nan
    top = s[:min(k, len(s))]
    m   = len(top)
    ranks = np.arange(1, m + 1, dtype=float)
    if weight_scheme == "inv_rank":
        w = 1.0 / ranks
    elif weight_scheme == "linear":
        w = (m + 1.0 - ranks)
    elif weight_scheme == "equal":
        w = np.ones(m, dtype=float)
    else:
        raise ValueError(f"未知 weight_scheme: {weight_scheme!r}")
    w_sum = w.sum()
    if w_sum == 0:
        return np.nan
    return float((w * top).sum() / w_sum)


def pool_rankdecay(arr, d=0.5):
    """
    指数衰减排名加权均值.
    数学定义: f(arr) = Σ_{i=1}^{n} d^(i-1) * s_i / Σ_{i=1}^{n} d^(i-1)
              s_1>=s_2>=...>=s_n（降序），i 从 1 开始，d^0=1（最高分权重最大）。
    参数:
      d (float): 衰减系数，默认 0.5，取值范围 (0,1)。
        d→0: 逼近 max pooling（权重集中在 s_1）
        d→1: 逼近 mean pooling（等权）
    TODO 待对账:
      - d=0.5 为经验默认；候选 d∈{0.3, 0.5, 0.8}，敏感性见 POOLINGS_SENSITIVITY。
      - 衰减率的选择需结合各工具子肽分数多样性分析后对账确认。
    """
    s = _sort_desc(arr)
    if len(s) == 0:
        return np.nan
    n        = len(s)
    exps     = np.arange(n, dtype=float)   # [0, 1, 2, ..., n-1]
    w        = d ** exps                    # [d^0, d^1, ..., d^(n-1)]
    w_sum    = w.sum()
    if w_sum == 0:
        return np.nan
    return float((w * s).sum() / w_sum)


# ── 主 Pooling 字典（默认参数，主表 8 种）─────────────────────────────────────
POOLINGS = {
    "max":       pool_max,
    "mean":      pool_mean,
    "top3mean":  pool_top3mean,
    "sum":       pool_sum,
    "geomean":   pool_geomean,
    "softmax":   partial(pool_softmax,   T=1.0),
    "topk_w":    partial(pool_topk_w,    k=5, weight_scheme="inv_rank"),
    "rankdecay": partial(pool_rankdecay, d=0.5),
}

# ── 敏感性扫描扩展版（--sensitivity 时用，在主 8 种基础上追加）─────────────────
POOLINGS_SENSITIVITY = dict(POOLINGS)
# softmax 额外温度（T=0.1 接近max, T=10 接近mean）
for _T in [0.1, 10.0]:
    POOLINGS_SENSITIVITY[f"softmax_T{_T}"] = partial(pool_softmax, T=_T)
# topk_w 额外 k（默认 k=5 已在主表）
for _k in [3, 10]:
    POOLINGS_SENSITIVITY[f"topk_w_k{_k}"] = partial(pool_topk_w,
                                                      k=_k,
                                                      weight_scheme="inv_rank")
# rankdecay 额外衰减率
for _d in [0.3, 0.8]:
    POOLINGS_SENSITIVITY[f"rankdecay_d{_d}"] = partial(pool_rankdecay, d=_d)


# ── 工具函数（复制自 per_patient_spearman_multimethod.py）────────────────────

def resolve_xlsx(root: Path, arg_input):
    """优先 9tools xlsx, 退 8tools。"""
    if arg_input is not None:
        p = Path(arg_input)
        if not p.is_absolute():
            p = root / p
        if p.exists():
            return p
        raise SystemExit(f"[ERR] 指定输入不存在: {p}")
    for name in ["merged_all_tools_9tools.xlsx", "merged_all_tools_8tools.xlsx"]:
        p = root / "scripts" / "out" / name
        if p.exists():
            return p
    raise SystemExit(
        "[ERR] 找不到 merged_all_tools_9tools.xlsx 或 _8tools.xlsx\n"
        f"      查找目录: {root / 'scripts' / 'out'}"
    )


def col_to_toolname(col):
    """MT_列名 -> 工具短名; IMPROVE 特例处理（列名含 IMPROVE_mean_prediction_rf）。"""
    name = col[3:]  # strip "MT_"
    if name.startswith("IMPROVE"):
        return "IMPROVE"
    return name


def find_patient_col(df):
    """按候选列名依序查找患者列，返回首个命中列名或 None。"""
    for c in PATIENT_COL_CANDIDATES:
        if c in df.columns:
            return c
    return None


def patient_from_peptide_id(pid):
    """从 '16097-101-10' 形式 Peptide_ID 反解患者号字符串 -> '101'。"""
    if not isinstance(pid, str):
        return None
    parts = pid.split("-")
    return parts[1] if len(parts) >= 3 else None


def _r4(v):
    """四舍五入到 4 位小数; nan/None 返回 np.nan。"""
    if v is None:
        return np.nan
    try:
        f = float(v)
        return np.nan if np.isnan(f) else round(f, 4)
    except (TypeError, ValueError):
        return np.nan


# ── 子肽→肽级分数（groupby Peptide_ID → pooling_func）──────────────────────

def compute_peptide_scores(ds2, mt_col, pooling_func):
    """
    子肽×HLA 行 → 肽级分数 Series (index=Peptide_ID)。
    只保留该工具有非 NaN 分数的行，再 groupby 聚合。
    """
    valid = ds2[ds2[mt_col].notna()][["Peptide_ID", mt_col]].copy()
    if valid.empty:
        return pd.Series(dtype=float)
    scores = (
        valid.groupby("Peptide_ID")[mt_col]
             .agg(lambda grp: pooling_func(grp.values))
             .rename("peptide_score")
    )
    # 数字稳定性修正: 多 tie 工具(如 pTuneos 83 ties)中, pooling 内部不同
    # 求和顺序产生 ~1e-16 浮点噪声, 经 Spearman 秩相关被 tie-break 放大成
    # 0.005 级 rho 漂移(0.0970 vs 0.0905, 均浮点假象)。round 到 8dp 让真 tie
    # 保持 tie、消除求和顺序依赖, 得确定性结果(pTuneos top3mean → 稳定 0.0945)。
    # 真实分数差 >>1e-8, 不受影响。详见 POOLING_STUDY.md §数字稳定性。
    return scores.round(8)


# ── 主函数 ────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(
        description="pooling_sweep: 8 pooling × DS2 全局/per-patient Spearman 扫描 (quantimmu-bench)"
    )
    ap.add_argument("--input", default=None,
                    help="合并表路径（默认自动找 9tools/8tools xlsx）")
    ap.add_argument("--min_pep", type=int, default=MIN_PEP_DEFAULT,
                    help=f"患者内 Spearman 最少肽数（默认 {MIN_PEP_DEFAULT}）")
    ap.add_argument("--sensitivity", action="store_true",
                    help="同时运行敏感性扫描（softmax 3温度/topk 3k/rankdecay 3d，共 14 种 pooling）")
    args = ap.parse_args()

    poolings_to_run = POOLINGS_SENSITIVITY if args.sensitivity else POOLINGS
    print(f"[info] pooling 数量: {len(poolings_to_run)}  sensitivity={args.sensitivity}")
    print(f"[info] min_pep={args.min_pep}")

    # ── 读数据 ────────────────────────────────────────────────────────────────
    xlsx_path = resolve_xlsx(ROOT, args.input)
    print(f"[info] 输入: {xlsx_path}")
    df = pd.read_excel(xlsx_path)
    print(f"[info] 总行数: {len(df)}  列数: {len(df.columns)}")

    if "Dataset" not in df.columns:
        raise SystemExit("[ERR] 缺 'Dataset' 列，无法筛 DS2")
    ds2 = df[df["Dataset"] == "DS2"].copy()
    print(f"[info] DS2 行数: {len(ds2)}")
    if ds2.empty:
        raise SystemExit("[ERR] DS2 子集为空，请检查 Dataset 列值")

    for req in ["Elispot", "Peptide_ID"]:
        if req not in ds2.columns:
            raise SystemExit(f"[ERR] 缺必需列 '{req}'")

    # ── 患者 ID（Patient_ID 列优先，缺退 Peptide_ID 反解）────────────────────
    pcol = find_patient_col(ds2)
    if pcol is None:
        print(f"[warn] 未找到患者列（试过 {PATIENT_COL_CANDIDATES}），从 Peptide_ID 反解")
    else:
        print(f"[info] 患者列 = '{pcol}'")

    def get_patient(row):
        if pcol is not None and pd.notna(row[pcol]):
            return str(row[pcol])
        return patient_from_peptide_id(row["Peptide_ID"])

    ds2 = ds2.copy()
    ds2["_patient"] = ds2.apply(get_patient, axis=1)
    before = len(ds2)
    ds2 = ds2.dropna(subset=["_patient"])
    if len(ds2) < before:
        print(f"[warn] {before - len(ds2)} 行无法解析患者 ID，已丢弃")

    patients_in_data = sorted(ds2["_patient"].unique(),
                               key=lambda x: int(x) if str(x).isdigit() else 0)
    print(f"[info] DS2 患者 ({len(patients_in_data)}): {patients_in_data}")

    # ── 工具列自动检测（复制 per_patient 逻辑）───────────────────────────────
    mt_cols = []
    for c in ds2.columns:
        if not c.startswith("MT_") or c in EXCLUDE:
            continue
        ds2[c] = pd.to_numeric(ds2[c], errors="coerce")
        if ds2[c].notna().any():
            mt_cols.append(c)
    if not mt_cols:
        raise SystemExit("[ERR] 未找到有效数值 MT_* 工具列")
    tools = {col_to_toolname(c): c for c in mt_cols}
    print(f"[info] 检测到 {len(tools)} 个工具: {list(tools.keys())}")

    # ── 肽级元信息 ────────────────────────────────────────────────────────────
    pep_info = (
        ds2.drop_duplicates("Peptide_ID")
           [["Peptide_ID", "_patient", "Elispot"]]
           .set_index("Peptide_ID")
    )

    # ── 扫描主循环 ────────────────────────────────────────────────────────────
    global_rows   = []   # Output A: 全局 Spearman
    scan_rows     = []   # Output B: 2D 扫描
    confound_rows = []   # Output D: count 混杂诊断
    # {(tool_name, pool_name): is_confounded} 供 Output C count-safe 列查用
    confound_lookup: dict = {}

    n_total = len(tools) * len(poolings_to_run)
    print(f"\n[info] 扫描矩阵: {len(tools)} 工具 × {len(poolings_to_run)} pooling = {n_total} 组合")
    print("=" * 80)

    for tool_name, mt_col in tools.items():
        is_hlathena  = (tool_name == "HLAthena")  # presentation proxy，近随机预期
        pending_dtu  = PENDING_DTU.get(tool_name, False)

        # 该工具有效子肽数 per Peptide_ID（只计 mt_col 非 NaN 的行）
        # n_subpep 受肽长度驱动（n_sub↔Length rho≈0.79）；sum pooling 几乎纯测此变量
        _valid_for_count = ds2[ds2[mt_col].notna()]
        n_subpep_series  = _valid_for_count.groupby("Peptide_ID").size().rename("n_subpep")

        for pool_name, pool_func in poolings_to_run.items():
            # ── Level-1: 子肽 → 肽级分数 ──────────────────────────────────
            pep_scores = compute_peptide_scores(ds2, mt_col, pool_func)
            if pep_scores.empty:
                continue

            pep_df = (
                pep_scores.to_frame()
                          .join(pep_info[["_patient", "Elispot"]], how="inner")
                          .dropna(subset=["Elispot", "peptide_score"])
            )
            if pep_df.empty:
                continue

            n_pep = len(pep_df)

            # ── count 混杂诊断: pooled_score vs n_subpeptides ──────────────
            # n_subpep_series reindex 对齐同一批 Peptide_ID（缺失自动填 NaN 被 spearman_np 过滤）
            n_subpep_aligned = n_subpep_series.reindex(pep_df.index)
            rho_confound  = spearman_np(pep_df["peptide_score"].values,
                                        n_subpep_aligned.values)
            is_confounded = (abs(rho_confound) > COUNT_CONFOUND_THRESH
                             if not np.isnan(rho_confound) else False)
            confound_lookup[(tool_name, pool_name)] = is_confounded
            confound_rows.append({
                "Tool":                  tool_name,
                "Pooling":               pool_name,
                "rho_pooled_vs_nsubpep": _r4(rho_confound),
                "n_pep":                 n_pep,
            })

            # ── Output A: 全局 Spearman ────────────────────────────────────
            rho_global  = spearman_np(pep_df["peptide_score"].values,
                                      pep_df["Elispot"].values)
            pval_global = spearman_pval_approx(rho_global, n_pep)

            global_rows.append({
                "Tool":                tool_name,
                "Pooling":             pool_name,
                "n_pep":               n_pep,
                "Spearman_rho":        _r4(rho_global),
                "Spearman_pval":       _r4(pval_global),
                # pval 为正态近似（t-stat → normal CDF via math.erf）
                # n_pep=101 时近似合理；若 n_pep<20 误差较大（TODO: 精确 p 值需 scipy.t）
                "pval_note":           "normal_approx_t",
                # |rho(pooled_score, n_subpeptides)| > COUNT_CONFOUND_THRESH=0.5
                # sum 必 True(~0.75)；其余据工具实测（top3mean/topk_w/rankdecay 约 0.33，一般 False）
                "count_confounded":    is_confounded,
                "pending_DTU_consent": pending_dtu,
                "hlathena_caveat":     is_hlathena,
            })

            # ── Level-2: per-patient → 跨患者聚合 ─────────────────────────
            pat_rhos, pat_ns = [], []
            for pat, g in pep_df.groupby("_patient"):
                if len(g) >= args.min_pep:
                    rho_i = spearman_np(g["peptide_score"].values,
                                        g["Elispot"].values)
                    if not np.isnan(rho_i):
                        pat_rhos.append(rho_i)
                        pat_ns.append(len(g))

            if not pat_rhos:
                continue

            rhos_arr = np.array(pat_rhos, float)
            ns_arr   = np.array(pat_ns,   float)
            n_pat    = len(rhos_arr)

            # Output B - fisherz_weighted
            fz_rho, fz_ci_lo, fz_ci_hi, fz_n_used, _ = \
                fisherz_weighted(rhos_arr, ns_arr)
            scan_rows.append({
                "Tool":                tool_name,
                "Pooling":             pool_name,
                "CrossAgg":            "fisherz_weighted",
                "headline_value":      _r4(fz_rho),
                "n_patients_used":     fz_n_used,
                "ci_lo":               _r4(fz_ci_lo),
                "ci_hi":               _r4(fz_ci_hi),
                "count_confounded":    is_confounded,
                "pending_DTU_consent": pending_dtu,
                "hlathena_caveat":     is_hlathena,
            })
            # Output B - median
            scan_rows.append({
                "Tool":                tool_name,
                "Pooling":             pool_name,
                "CrossAgg":            "median",
                "headline_value":      _r4(float(np.median(rhos_arr))),
                "n_patients_used":     n_pat,
                "ci_lo":               np.nan,
                "ci_hi":               np.nan,
                "count_confounded":    is_confounded,
                "pending_DTU_consent": pending_dtu,
                "hlathena_caveat":     is_hlathena,
            })
            # Output B - simple_mean
            scan_rows.append({
                "Tool":                tool_name,
                "Pooling":             pool_name,
                "CrossAgg":            "simple_mean",
                "headline_value":      _r4(float(rhos_arr.mean())),
                "n_patients_used":     n_pat,
                "ci_lo":               np.nan,
                "ci_hi":               np.nan,
                "count_confounded":    is_confounded,
                "pending_DTU_consent": pending_dtu,
                "hlathena_caveat":     is_hlathena,
            })

    if not global_rows:
        raise SystemExit("[ERR] 无有效结果，所有 CSV 未写出")

    # ── 写出 Output A: pooling_global_spearman.csv ────────────────────────────
    global_df = pd.DataFrame(global_rows)
    out_a = HERE / "pooling_global_spearman.csv"
    global_df.to_csv(out_a, index=False, encoding="utf-8")
    print(f"[saved] {out_a}  shape={global_df.shape}")

    # ── 写出 Output B: pooling_2d_scan.csv ───────────────────────────────────
    if scan_rows:
        scan_df = pd.DataFrame(scan_rows)
        out_b = HERE / "pooling_2d_scan.csv"
        scan_df.to_csv(out_b, index=False, encoding="utf-8")
        print(f"[saved] {out_b}  shape={scan_df.shape}")
    else:
        print("[warn] per-patient 扫描无有效结果，pooling_2d_scan.csv 未写出")

    # ── 写出 Output D: pooling_count_confound.csv ─────────────────────────────
    if confound_rows:
        confound_df = pd.DataFrame(confound_rows)
        out_d = HERE / "pooling_count_confound.csv"
        with open(out_d, "w", encoding="utf-8") as _f:
            _f.write(
                "# count-confound diagnostic: high |rho| => pooling 受子肽数(≈肽长)驱动而非真分数;"
                " sum 最重(~0.75); 参考 n_subpep↔Elispot=0.16, Peptide_Length↔Elispot=0.31\n"
            )
            confound_df.to_csv(_f, index=False)
        print(f"[saved] {out_d}  shape={confound_df.shape}")

    # ── Output C: pooling_best_per_tool.csv ──────────────────────────────────
    # 只用主 8 种 pooling（排除 sensitivity 扩展版）
    main_global = global_df[global_df["Pooling"].isin(POOLINGS.keys())].copy()
    best_rows   = []

    for tool_name in main_global["Tool"].unique():
        tool_df = main_global[main_global["Tool"] == tool_name].dropna(
            subset=["Spearman_rho"]
        )
        if tool_df.empty:
            continue

        # max pooling 作基准（对账 merge_metrics_9tools.py Aggregation=max）
        max_row = tool_df[tool_df["Pooling"] == "max"]
        rho_max_base = float(max_row["Spearman_rho"].iloc[0]) if not max_row.empty else np.nan

        # 所有 8 种中最优 pooling
        best_idx  = tool_df["Spearman_rho"].idxmax()
        best_row  = tool_df.loc[best_idx]
        best_pool = best_row["Pooling"]
        best_rho  = float(best_row["Spearman_rho"])
        delta     = (best_rho - rho_max_base) if not np.isnan(rho_max_base) else np.nan

        # delta > 0.01 (1 Spearman 单位) 标为"被 max 低估"
        # 阈值 0.01 为保守设置（排除浮点随机偏差）; delta 列提供精确值供用户自定义筛选
        underestimated = (delta > 0.01) if not np.isnan(delta) else False

        # ── count-safe 最优: 排除 |rho(score, n_subpep)| > COUNT_CONFOUND_THRESH 的 pooling ──
        safe_df = tool_df[
            tool_df["Pooling"].map(
                lambda p: not confound_lookup.get((tool_name, p), False)
            )
        ].copy()
        if not safe_df.empty:
            safe_df = safe_df.dropna(subset=["Spearman_rho"])

        if not safe_df.empty:
            best_safe_idx  = safe_df["Spearman_rho"].idxmax()
            best_safe_row  = safe_df.loc[best_safe_idx]
            best_safe_pool = best_safe_row["Pooling"]
            best_safe_rho  = float(best_safe_row["Spearman_rho"])
            delta_safe     = (best_safe_rho - rho_max_base) if not np.isnan(rho_max_base) else np.nan
            under_safe     = (delta_safe > 0.01) if not np.isnan(delta_safe) else False
        else:
            best_safe_pool = np.nan
            best_safe_rho  = np.nan
            delta_safe     = np.nan
            under_safe     = False

        best_rows.append({
            "Tool":                          tool_name,
            # naive 最优（含混杂 pooling，如 sum；仅用于对比）
            "best_pooling":                  best_pool,
            "best_rho":                      _r4(best_rho),
            "rho_max_baseline":              _r4(rho_max_base),
            "delta_best_minus_max":          _r4(delta),
            # True = 某 non-max pooling 比 max 高 >0.01，即 max 低估了该工具（naive）
            "underestimated_by_max":         underestimated,
            # count-safe 最优（排除 count_confounded=True 的 pooling 后最高 Spearman）
            "best_pooling_countsafe":        best_safe_pool,
            "best_rho_countsafe":            _r4(best_safe_rho),
            "delta_countsafe_minus_max":     _r4(delta_safe),
            "underestimated_by_max_countsafe": under_safe,
            # sum 因 count 混杂被排除出 countsafe 选择池
            "sum_is_confound_note":          (
                "sum excluded from countsafe: rho(sum_score,n_subpep)~0.75"
                " >> COUNT_CONFOUND_THRESH=0.5;"
                " driven by peptide_length not true immunogenicity signal"
            ),
            # 对账说明: rho_max_baseline 应与 metrics_ds2_9tools.csv (Aggregation=max)
            # Spearman_rho 列一致（两文件均用 rank Pearson，末位浮点可能有 <0.001 差异）
            "crosscheck_note":               (
                "rho_max_baseline vs "
                "metrics_ds2_9tools.csv[Aggregation=max][Spearman_rho]"
            ),
            "pending_DTU_consent":           PENDING_DTU.get(tool_name, False),
            "hlathena_caveat":               (tool_name == "HLAthena"),
        })

    if best_rows:
        best_df = pd.DataFrame(best_rows)
        out_c = HERE / "pooling_best_per_tool.csv"
        best_df.to_csv(out_c, index=False, encoding="utf-8")
        print(f"[saved] {out_c}  shape={best_df.shape}")

    # ── 对账打印（max/mean/top3mean vs metrics_ds2_9tools.csv）──────────────
    print("\n[对账] max/mean/top3mean 全局 Spearman（应与 metrics_ds2_9tools.csv 一致）:")
    ref_pools = ["max", "mean", "top3mean"]
    check = (
        main_global[main_global["Pooling"].isin(ref_pools)]
        [["Tool", "Pooling", "Spearman_rho"]]
        .sort_values(["Tool", "Pooling"])
    )
    print(check.to_string(index=False))

    # ── 统计提示 ─────────────────────────────────────────────────────────────
    print("\n[STATISTICAL NOTES]")
    print("  1. Spearman_pval 为正态近似（n=101 DS2 肽时误差可接受）；精确值需 scipy.stats.t（因 OMP#15 禁用）。")
    print("  2. 8 种 pooling 多重比较未校正；最优 pooling 选择带过拟合风险，建议独立集验证。")
    print("  3. geomean 平移处理改变绝对分数尺度，但 Spearman（秩相关）结果不受影响。")
    print("  4. softmax T/topk k/rankdecay d 参数待对账，当前默认值仅为探索性起点。")
    print("  5. HLAthena = presentation proxy（预测 MHC-I 提呈，非免疫原性），ELISpot 上预期近随机。")
    print(f"\n[DONE] pooling_sweep 完成")


if __name__ == "__main__":
    main()
