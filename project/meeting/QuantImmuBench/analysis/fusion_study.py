#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fusion_study.py
===============
服务: quantimmu-bench § fusion_ceiling lever (I-fusion 窗)
目标:
  A. 9工具单工具地板 (直接用工具分, 无训练)
  B. 融合 LOPO (patient-level): fixavg_surv6 / rankmean_surv6 / ridge_surv6 / gbdt_surv6
  C. 防泄漏对照 (shuffle Elispot + fixavg_surv6, seed=42)
  D. ★ 融合 vs 最优单工具 患者级配对 bootstrap (B=10000) — headline (复现朱 p=0.70)
  E. 天花板距离 (ceiling=[0.4, 0.6], precursor frequency 锁)

依赖: spearman_np / fisherz_weighted_agg / effective_dof / find_ridge_alpha / impute_fold
      照抄 quantimmune/lopo_eval.py 公式, 保证可比。

Windows 规范: UTF-8 stdout, 禁 scipy (OMP Error #15), 纯 numpy/pandas/sklearn

输入:  quantimmune/model_matrix.csv
输出 (analysis/):
  fusion_single_floor.csv      — 9工具单工具 per-patient Spearman 汇总
  fusion_methods.csv           — 融合法 LOPO + DS1敏感性 + shuffle对照
  fusion_vs_single_paired.csv  — 配对 bootstrap 结果 (headline)
  fusion_ceiling_distance.csv  — 天花板距离分析

跑法:
  python analysis/fusion_study.py
  python analysis/fusion_study.py --matrix quantimmune/model_matrix.csv
  python analysis/fusion_study.py --B 10000 --seed 42
"""

import math
import sys
import argparse
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge
from sklearn.ensemble import GradientBoostingRegressor

# Windows 必要: UTF-8 stdout
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

HERE = Path(__file__).resolve().parent          # analysis/
ROOT = HERE.parent                               # QuantImmuBench/
DEFAULT_MATRIX = ROOT / "quantimmune" / "model_matrix.csv"

# ── 患者集合 ──────────────────────────────────────────────────────────────────
DS2_PATIENTS = [101, 102, 104, 105, 106, 107, 108, 109, 110]  # 主分析
DS1_PATIENTS = [1, 2, 3, 4, 5, 6]                              # 仅敏感性

# ── 特征列定义 ────────────────────────────────────────────────────────────────
ALL9_TOOLS = [
    "MT_DeepImmuno", "MT_PredIG", "MT_IMPROVE_mean_prediction_rf",
    "MT_NeoTImmuML", "MT_pTuneos", "MT_PRIME",
    "MT_ImmuneApp", "MT_deepHLApan", "MT_HLAthena",
]
SURV6_TOOLS = [
    "MT_PredIG", "MT_IMPROVE_mean_prediction_rf", "MT_pTuneos",
    "MT_PRIME", "MT_ImmuneApp", "MT_deepHLApan",
]

FISHER_CLIP = 0.9999
FISHER_MIN_N = 3    # n <= 3 → Var(z_i) 分母 <= 0, 不进 Fisher-z 加权
MIN_PEP = 4         # 患者内最少肽数才算 rho (LEDGER 约束④)

CEILING_LOW  = 0.4  # precursor frequency 锁下沿 (THEORY_quant.md)
CEILING_HIGH = 0.6  # 上沿


# ═══════════════════════════════════════════════════════════════════════════════
# 核心统计函数 — 照抄 lopo_eval.py 公式, 保证可比
# ═══════════════════════════════════════════════════════════════════════════════

def spearman_np(x, y):
    """纯 numpy Spearman rank correlation. 返回 NaN 若样本不足。
    禁 scipy 防 OMP Error #15 (Windows multi-process)。
    照抄 quantimmune/lopo_eval.py。
    """
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


def fisherz_weighted_agg(rhos, ns):
    """
    Fisher-z 固定效应加权均值 + 95% CI.
    Spearman 专用方差: Var(z_i) = (1 + rho_i^2/2) / (n_i - 3)
    [Fieller-Hartley-Pearson 1957, Biometrika 44:470]
    n_i <= FISHER_MIN_N 剔出。
    返回 (rho_bar, ci_lo, ci_hi, n_used, n_dropped)
    照抄 quantimmune/lopo_eval.py。
    """
    rhos = np.asarray(rhos, float)
    ns   = np.asarray(ns,   float)
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
    w = 1.0 / var_z
    sum_w = w.sum()
    z_bar = (w * z).sum() / sum_w
    rho_bar = float(np.tanh(z_bar))
    ci_lo   = float(np.tanh(z_bar - 1.96 / np.sqrt(sum_w)))
    ci_hi   = float(np.tanh(z_bar + 1.96 / np.sqrt(sum_w)))
    return rho_bar, ci_lo, ci_hi, int(keep.sum()), n_dropped


def effective_dof(X: np.ndarray, alpha: float) -> float:
    """eff_DOF = sum(d^2 / (d^2 + alpha)), d = singular values of X.
    照抄 quantimmune/lopo_eval.py。
    """
    _, s, _ = np.linalg.svd(X, full_matrices=False)
    return float(np.sum(s ** 2 / (s ** 2 + alpha)))


def find_ridge_alpha(X: np.ndarray, target_dof: float = 2.5,
                     n_grid: int = 200) -> tuple:
    """logspace 网格搜索使 eff_DOF 最接近 target_dof 的 alpha。
    返回 (alpha_best, dof_achieved)。
    照抄 quantimmune/lopo_eval.py。
    """
    _, s, _ = np.linalg.svd(X, full_matrices=False)
    s_sq_max = float(s[0] ** 2) if len(s) > 0 else 1.0
    alpha_grid = np.logspace(
        np.log10(max(s_sq_max * 1e-3, 1e-4)),
        np.log10(s_sq_max * 1e7 + 1.0),
        n_grid,
    )
    dofs = np.array([effective_dof(X, a) for a in alpha_grid])
    idx = int(np.argmin(np.abs(dofs - target_dof)))
    return float(alpha_grid[idx]), float(dofs[idx])


def impute_fold(train_df: pd.DataFrame, test_df: pd.DataFrame,
                feature_cols: list) -> tuple:
    """折内填补: 训练折各特征列均值 → 填入训练和测试折缺失值。
    防泄漏: 严格不用含 held-out 患者的统计。
    照抄 quantimmune/lopo_eval.py。
    """
    train_f = train_df.copy()
    test_f  = test_df.copy()
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


# ═══════════════════════════════════════════════════════════════════════════════
# 聚合辅助
# ═══════════════════════════════════════════════════════════════════════════════

def aggregate_per_patient(pat_rho_dict: dict, patient_list: list):
    """
    从 {pat: (rho, n_pep)} 中按 sorted(patient_list) 顺序提取 DS rho+n,
    做 Fisher-z 加权聚合。
    返回 (rho_bar, ci_lo, ci_hi, median_rho, n_used, n_dropped, rhos_list, ns_list)
    rhos_list / ns_list 顺序与 sorted(patient_list) 一致 (含 NaN)。
    """
    pat_list = sorted(patient_list)
    rhos = []
    ns   = []
    for pat in pat_list:
        rho, n = pat_rho_dict.get(pat, (np.nan, 0))
        rhos.append(float(rho) if rho is not None else np.nan)
        ns.append(float(n))

    rho_bar, ci_lo, ci_hi, n_used, n_dropped = fisherz_weighted_agg(
        np.array(rhos, dtype=float), np.array(ns, dtype=float))
    valid_rhos = [r for r in rhos if not np.isnan(r)]
    median_rho = float(np.nanmedian(valid_rhos)) if valid_rhos else np.nan

    return rho_bar, ci_lo, ci_hi, median_rho, n_used, n_dropped, rhos, ns


# ═══════════════════════════════════════════════════════════════════════════════
# Section A: 单工具地板
# ═══════════════════════════════════════════════════════════════════════════════

def compute_single_tool_floor(df: pd.DataFrame, patients: list,
                               tool_cols: list, min_pep: int = MIN_PEP) -> dict:
    """
    对每个工具直接用工具分数当预测, 计算 per-patient Spearman rho。
    不需要训练, 不需要 LOPO。
    返回 {tool: {pat: (rho, n_pep)}}
    """
    results = {t: {} for t in tool_cols}
    for pat in patients:
        pat_df = df[df["Patient_ID"] == pat]
        n = len(pat_df)
        y = pat_df["Elispot"].values.astype(float)
        for tool in tool_cols:
            if tool not in pat_df.columns:
                results[tool][pat] = (np.nan, n)
                continue
            x = pat_df[tool].values.astype(float)
            rho = spearman_np(x, y) if n >= min_pep else np.nan
            results[tool][pat] = (rho, n)
    return results


# ═══════════════════════════════════════════════════════════════════════════════
# Section B: 融合 LOPO
# ═══════════════════════════════════════════════════════════════════════════════

def run_lopo(df: pd.DataFrame, patients: list, feature_cols: list,
             seed: int = 42, min_pep: int = MIN_PEP,
             dof_target: float = 2.5, include_gbdt: bool = True) -> dict:
    """
    Patient-level LOPO (留1患者训其余)。
    防泄漏: 缺失用训练折均值填; 标准化用训练折统计。
    方法:
      fixavg   — z-score(训练折统计) + 等权平均 (零参数, 对应 F 窗口径)
      rankmean — 测试折内各工具 rank + 等权平均
                 (尺度无关新变体: 不用训练折统计做 rank, 缺失已由训练折均值填补)
                 Spearman(rank_avg, Elispot) ≠ Spearman(z-avg, Elispot) 因为
                 rank 消除了工具间量纲差异 (如 PRIME 分布 vs ImmuneApp 分布不同)
      ridge    — Ridge alpha grid eff_DOF≈2.5 (同 F 窗)
      gbdt     — GradientBoosting max_depth=2, 仅敏感性
    返回 {method: {pat: (rho, n_pep)}}
    """
    methods = ["fixavg", "rankmean", "ridge"]
    if include_gbdt:
        methods.append("gbdt")
    results = {m: {} for m in methods}

    for pat in patients:
        test_mask    = df["Patient_ID"] == pat
        train_df_raw = df[~test_mask].copy()
        test_df_raw  = df[test_mask].copy()
        n_test       = len(test_df_raw)

        if n_test < min_pep:
            for m in methods:
                results[m][pat] = (np.nan, n_test)
            continue

        # 折内缺失值填补 (防泄漏)
        train_df, test_df = impute_fold(train_df_raw, test_df_raw, feature_cols)

        X_train = train_df[feature_cols].values.astype(float)
        X_test  = test_df[feature_cols].values.astype(float)
        y_eval  = test_df["Elispot"].values.astype(float)
        y_train = train_df["Elispot"].values.astype(float)

        # 丢掉训练集 y 为 NaN 的行
        valid_train = ~np.isnan(y_train)
        X_train = X_train[valid_train]
        y_train = y_train[valid_train]
        if len(X_train) == 0:
            for m in methods:
                results[m][pat] = (np.nan, n_test)
            continue

        # 标准化 (训练折统计)
        X_mean = np.nanmean(X_train, axis=0)
        X_std  = np.nanstd(X_train, axis=0)
        X_std[X_std < 1e-10] = 1.0
        X_train_s = (X_train - X_mean) / X_std
        X_test_s  = (X_test  - X_mean) / X_std

        # ── fixavg: z-score 后等权平均 ─────────────────────────────────────────
        pred_fixavg = np.nanmean(X_test_s, axis=1)
        results["fixavg"][pat] = (spearman_np(pred_fixavg, y_eval), n_test)

        # ── rankmean: 测试折内各工具 rank + 等权平均 ──────────────────────────
        # 用 impute_fold 填补后的原始尺度 X_test (缺失已填训练折均值)
        # 对每列在测试折内做 rank, 消除各工具量纲差异
        # pd.Series.rank() 默认 method='average' 处理并列
        rank_mat = np.column_stack([
            pd.Series(X_test[:, j]).rank().values.astype(float)
            for j in range(X_test.shape[1])
        ])
        pred_rankmean = np.nanmean(rank_mat, axis=1)
        results["rankmean"][pat] = (spearman_np(pred_rankmean, y_eval), n_test)

        # ── ridge: alpha grid eff_DOF≈2.5 ────────────────────────────────────
        alpha_best, _dof = find_ridge_alpha(X_train_s, target_dof=dof_target)
        ridge_model = Ridge(alpha=alpha_best, fit_intercept=True)
        ridge_model.fit(X_train_s, y_train)
        pred_ridge = ridge_model.predict(X_test_s)
        results["ridge"][pat] = (spearman_np(pred_ridge, y_eval), n_test)

        # ── gbdt: 仅敏感性 ───────────────────────────────────────────────────
        if include_gbdt:
            gbdt = GradientBoostingRegressor(
                max_depth=2, n_estimators=100, subsample=0.8, random_state=seed)
            gbdt.fit(X_train_s, y_train)
            pred_gbdt = gbdt.predict(X_test_s)
            results["gbdt"][pat] = (spearman_np(pred_gbdt, y_eval), n_test)

    return results


# ═══════════════════════════════════════════════════════════════════════════════
# Section D: 配对 bootstrap
# ═══════════════════════════════════════════════════════════════════════════════

def paired_bootstrap(fus_rhos: np.ndarray, fus_ns: np.ndarray,
                     sing_rhos: np.ndarray, sing_ns: np.ndarray,
                     B: int = 10000, seed: int = 42) -> tuple:
    """
    患者级配对 bootstrap: 融合 vs 最优单工具, Fisher-z 空间。
    fus_rhos / sing_rhos: 同顺序排列 (sorted(ds2_patients)), 含 NaN
    算法:
      1. 共同有效患者: 两侧均非 NaN 且 n > FISHER_MIN_N
      2. z_fus_i = arctanh(rho_fus_i), z_sing_i = arctanh(rho_sing_i)
      3. Delta_z_i = z_fus_i - z_sing_i
      4. bootstrap B次: 有放回重抽 n_valid 患者, 每次计算 mean(Delta_z)
      5. 点估 = mean(Delta_z_i), CI = percentile(boot_means, [2.5, 97.5])
      6. P(Delta>0) = 正向 bootstrap 比例; p_two_sided = 2*min(...)
    返回 (delta_z_mean, ci_lo, ci_hi, p_two_sided, prob_delta_gt0)
    """
    rng = np.random.default_rng(seed)
    fus_rhos  = np.asarray(fus_rhos,  float)
    sing_rhos = np.asarray(sing_rhos, float)
    fus_ns    = np.asarray(fus_ns,    float)
    sing_ns   = np.asarray(sing_ns,   float)

    # 共同有效患者 (双侧有 rho 且 n 足够)
    valid = (~np.isnan(fus_rhos)) & (~np.isnan(sing_rhos)) & \
            (fus_ns > FISHER_MIN_N) & (sing_ns > FISHER_MIN_N)

    fus_v  = np.clip(fus_rhos[valid],  -FISHER_CLIP, FISHER_CLIP)
    sing_v = np.clip(sing_rhos[valid], -FISHER_CLIP, FISHER_CLIP)
    n_valid = len(fus_v)

    if n_valid < 2:
        return np.nan, np.nan, np.nan, np.nan, np.nan

    z_fus  = np.arctanh(fus_v)
    z_sing = np.arctanh(sing_v)
    delta_z = z_fus - z_sing                  # shape (n_valid,)
    delta_z_mean = float(np.mean(delta_z))    # 点估

    # 有放回重抽 n_valid 患者 B 次
    idxs = rng.integers(0, n_valid, size=(B, n_valid))
    boot_means = np.mean(delta_z[idxs], axis=1)   # shape (B,)

    ci_lo        = float(np.percentile(boot_means, 2.5))
    ci_hi        = float(np.percentile(boot_means, 97.5))
    prob_gt0     = float(np.mean(boot_means > 0))
    p_two_sided  = float(2.0 * min(
        float(np.mean(boot_means > 0)),
        float(np.mean(boot_means < 0))
    ))

    return delta_z_mean, ci_lo, ci_hi, p_two_sided, prob_gt0


# ═══════════════════════════════════════════════════════════════════════════════
# Section D 补充检验 — 对 K=9 小样本比 bootstrap 更可信
# ═══════════════════════════════════════════════════════════════════════════════

def sign_test_exact_p(fus_rhos: np.ndarray, fus_ns: np.ndarray,
                      sing_rhos: np.ndarray, sing_ns: np.ndarray) -> tuple:
    """
    精确符号检验 (纯 numpy, 禁 scipy 防 OMP Error #15).
    K=9 患者级别, bootstrap 组合离散时此检验更可靠。
    H0: P(Delta_z > 0) = 0.5 (融合与单工具无差异)
    算法:
      k = min(n_pos, n_neg)   (n = n_pos + n_neg, 精确零 ties 剔出)
      p_two = 2 * sum_{i=0}^{k} C(n,i) * 0.5^n  (精确二项 p)
      用 log-gamma 数值稳定计算各项。
    返回 (sign_test_p, n_pos, n_neg)
    """
    fus_rhos  = np.asarray(fus_rhos,  float)
    sing_rhos = np.asarray(sing_rhos, float)
    fus_ns    = np.asarray(fus_ns,    float)
    sing_ns   = np.asarray(sing_ns,   float)

    valid = (~np.isnan(fus_rhos)) & (~np.isnan(sing_rhos)) & \
            (fus_ns > FISHER_MIN_N) & (sing_ns > FISHER_MIN_N)
    fus_v  = np.clip(fus_rhos[valid],  -FISHER_CLIP, FISHER_CLIP)
    sing_v = np.clip(sing_rhos[valid], -FISHER_CLIP, FISHER_CLIP)
    delta_z = np.arctanh(fus_v) - np.arctanh(sing_v)

    n_pos = int(np.sum(delta_z > 0))
    n_neg = int(np.sum(delta_z < 0))
    n     = n_pos + n_neg          # 精确零 (delta_z == 0) 不计入

    if n == 0:
        return np.nan, n_pos, n_neg

    k = min(n_pos, n_neg)          # 较小的那侧
    # sum_{i=0}^{k} C(n,i) * 0.5^n
    log_half_n = -n * np.log(2.0)
    cum = 0.0
    for i in range(k + 1):
        log_coef = (math.lgamma(n + 1)
                    - math.lgamma(i + 1)
                    - math.lgamma(n - i + 1))
        cum += float(np.exp(log_coef + log_half_n))
    p_two_sided = float(min(2.0 * cum, 1.0))
    return p_two_sided, n_pos, n_neg


def permutation_sign_flip_p(fus_rhos: np.ndarray, fus_ns: np.ndarray,
                             sing_rhos: np.ndarray, sing_ns: np.ndarray,
                             seed: int = 42) -> float:
    """
    配对置换检验 (符号翻转), 纯 numpy.
    K=9 → 全枚举 2^9=512 种符号组合; K>20 → Monte Carlo (本场景不触发)。
    null 分布: mean(Delta_z * signs_combo) for each of 2^K combos
    p_two_sided = P(|null_mean| >= |observed_mean|)
    返回 perm_test_p
    """
    fus_rhos  = np.asarray(fus_rhos,  float)
    sing_rhos = np.asarray(sing_rhos, float)
    fus_ns    = np.asarray(fus_ns,    float)
    sing_ns   = np.asarray(sing_ns,   float)

    valid = (~np.isnan(fus_rhos)) & (~np.isnan(sing_rhos)) & \
            (fus_ns > FISHER_MIN_N) & (sing_ns > FISHER_MIN_N)
    fus_v  = np.clip(fus_rhos[valid],  -FISHER_CLIP, FISHER_CLIP)
    sing_v = np.clip(sing_rhos[valid], -FISHER_CLIP, FISHER_CLIP)
    delta_z = np.arctanh(fus_v) - np.arctanh(sing_v)

    K = len(delta_z)
    if K < 2:
        return np.nan

    obs_mean = float(np.mean(delta_z))

    if K <= 20:
        # 全枚举 2^K 符号组合
        # signs_mat[combo_idx, patient_idx] = +1 if bit patient_idx set in combo_idx
        n_perms = 2 ** K
        bits = np.arange(n_perms, dtype=np.int64)[:, np.newaxis]
        pow2 = (1 << np.arange(K, dtype=np.int64))[np.newaxis, :]
        signs_mat = np.where(bits & pow2, 1.0, -1.0).astype(float)  # (512, K)
        null_means = np.mean(signs_mat * delta_z[np.newaxis, :], axis=1)  # (512,)
    else:
        # Monte Carlo fallback (K=9 不触发; 保留供健壮性)
        rng = np.random.default_rng(seed)
        n_perms = 100000
        signs_mat = rng.choice(np.array([-1.0, 1.0]), size=(n_perms, K))
        null_means = np.mean(signs_mat * delta_z[np.newaxis, :], axis=1)

    p_two_sided = float(np.mean(np.abs(null_means) >= np.abs(obs_mean)))
    return p_two_sided


# ═══════════════════════════════════════════════════════════════════════════════
# 主函数
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    ap = argparse.ArgumentParser(
        description="fusion_study.py — quantimmu-bench fusion ceiling analysis")
    ap.add_argument("--matrix",  default=str(DEFAULT_MATRIX),
                    help="model_matrix.csv 路径")
    ap.add_argument("--seed",    type=int, default=42)
    ap.add_argument("--B",       type=int, default=10000,
                    help="配对 bootstrap 次数 (默认 10000)")
    ap.add_argument("--min_pep", type=int, default=MIN_PEP,
                    help="患者内最少肽数才算 rho (默认 4)")
    args = ap.parse_args()

    out_dir = HERE
    out_dir.mkdir(parents=True, exist_ok=True)

    # ── 读 model_matrix ──────────────────────────────────────────────────────
    matrix_path = Path(args.matrix)
    if not matrix_path.exists():
        sys.exit(f"[ERR] model_matrix.csv 不存在: {matrix_path}\n"
                 f"      先运行: python quantimmune/build_model_matrix.py")
    df = pd.read_csv(matrix_path, encoding="utf-8")
    print(f"[info] model_matrix: {df.shape}, 患者={df['Patient_ID'].nunique()}")

    # 确认特征列实际存在
    tool_cols  = [t for t in ALL9_TOOLS  if t in df.columns]
    surv6_cols = [t for t in SURV6_TOOLS if t in df.columns]
    missing_tools = [t for t in ALL9_TOOLS  if t not in df.columns]
    if missing_tools:
        print(f"[warn] 以下工具列缺失: {missing_tools}")
    print(f"[info] tool_cols ({len(tool_cols)}): {tool_cols}")
    print(f"[info] surv6_cols ({len(surv6_cols)}): {surv6_cols}")

    ds2_patients = sorted([p for p in DS2_PATIENTS if p in df["Patient_ID"].unique()])
    ds1_patients = sorted([p for p in DS1_PATIENTS if p in df["Patient_ID"].unique()])
    all_patients = ds2_patients + ds1_patients
    print(f"[info] DS2={ds2_patients}")
    print(f"[info] DS1={ds1_patients}")

    # 辅助: 安全 round (NaN → np.nan)
    def _r(v, d=6):
        return round(float(v), d) if (v is not None and not np.isnan(float(v))) else np.nan

    # ═══════════════════════════════════════════════════════════════════════════
    # Section A: 单工具地板
    # ═══════════════════════════════════════════════════════════════════════════
    print("\n" + "=" * 70)
    print("Section A: 单工具地板 (9工具直接预测, DS2 主分析)")
    print("=" * 70)

    floor_ds2 = compute_single_tool_floor(df, ds2_patients, tool_cols, args.min_pep)
    floor_ds1 = compute_single_tool_floor(df, ds1_patients, tool_cols, args.min_pep)

    floor_rows = []
    best_single_tool  = None
    best_single_fz    = -np.inf
    best_single_rhos_arr = None
    best_single_ns_arr   = None

    for tool in tool_cols:
        rho_bar, ci_lo, ci_hi, median_rho, n_used, n_dropped, rhos, ns = \
            aggregate_per_patient(floor_ds2[tool], ds2_patients)

        if not np.isnan(rho_bar) and rho_bar > best_single_fz:
            best_single_fz       = rho_bar
            best_single_tool     = tool
            best_single_rhos_arr = np.array(rhos, dtype=float)
            best_single_ns_arr   = np.array(ns,   dtype=float)

        row = {
            "tool":        tool,
            "n_patients":  n_used,
            "fisherz_rho": _r(rho_bar),
            "ci_lo":       _r(ci_lo),
            "ci_hi":       _r(ci_hi),
            "median":      _r(median_rho),
            "n_used":      n_used,
            "n_dropped":   n_dropped,
        }
        for pat in sorted(ds2_patients):
            rho_i, n_i = floor_ds2[tool].get(pat, (np.nan, 0))
            row[f"rho_p{pat}"] = _r(rho_i)
            row[f"n_p{pat}"]   = int(n_i)
        floor_rows.append(row)

        ci_str = f"CI[{ci_lo:+.4f},{ci_hi:+.4f}]" if not np.isnan(ci_lo) else "CI[N/A]"
        print(f"  {tool:<40s}  rho={rho_bar:+.4f}  {ci_str}  med={median_rho:+.4f}")

    print(f"\n  >> best_single = {best_single_tool}  rho_bar = {best_single_fz:+.4f}")

    floor_df = pd.DataFrame(floor_rows)
    out_floor = out_dir / "fusion_single_floor.csv"
    with open(out_floor, "w", encoding="utf-8") as f:
        f.write("# fusion_single_floor.csv\n")
        f.write("# 9工具直接用工具分预测 DS2 per-patient Spearman (无训练)\n")
        f.write("# tool=工具列名; n_patients/n_used=纳入Fisher-z聚合的患者数\n")
        f.write("# fisherz_rho=Fisher-z加权rho, ci_lo/ci_hi=95%CI, median=中位数\n")
        f.write("# rho_p{id}=该患者per-patient rho_i, n_p{id}=该患者肽数\n")
        floor_df.to_csv(f, index=False)
    print(f"[saved] {out_floor}")

    # ═══════════════════════════════════════════════════════════════════════════
    # Section B: 融合 LOPO (DS2 + DS1)
    # ═══════════════════════════════════════════════════════════════════════════
    print("\n" + "=" * 70)
    print("Section B: 融合 LOPO (surv6 特征集, patient-level 留一)")
    print("=" * 70)

    lopo_res = run_lopo(df, all_patients, surv6_cols,
                        seed=args.seed, min_pep=args.min_pep,
                        dof_target=2.5, include_gbdt=True)

    # internal key → output label
    method_label_map = {
        "fixavg":   "fixavg_surv6",
        "rankmean": "rankmean_surv6",
        "ridge":    "ridge_surv6",
        "gbdt":     "gbdt_surv6",
    }

    method_rows = []
    fusion_fz_rho  = {}   # {label: rho_bar} DS2 主分析, 供 Summary
    fusion_pat_rhos = {}  # {label: (rhos_arr, ns_arr)} DS2 sorted order, 供 bootstrap

    for m_key, m_label in method_label_map.items():
        if m_key not in lopo_res:
            continue
        pat_dict = lopo_res[m_key]

        # DS2 主分析
        rho_bar, ci_lo, ci_hi, median_rho, n_used, n_dropped, rhos, ns = \
            aggregate_per_patient(pat_dict, ds2_patients)
        fusion_fz_rho[m_label]   = rho_bar
        fusion_pat_rhos[m_label] = (np.array(rhos, dtype=float),
                                    np.array(ns,   dtype=float))

        row = {
            "method":      m_label,
            "dataset":     "DS2_main",
            "n_patients":  n_used,
            "fisherz_rho": _r(rho_bar),
            "ci_lo":       _r(ci_lo),
            "ci_hi":       _r(ci_hi),
            "median":      _r(median_rho),
        }
        for pat in sorted(ds2_patients):
            rho_i, n_i = pat_dict.get(pat, (np.nan, 0))
            row[f"rho_p{pat}"] = _r(rho_i)
            row[f"n_p{pat}"]   = int(n_i)
        method_rows.append(row)

        ci_str = f"[{ci_lo:+.4f},{ci_hi:+.4f}]" if not np.isnan(ci_lo) else "[N/A]"
        print(f"  {m_label:<25s}  rho={rho_bar:+.4f}  CI{ci_str}  med={median_rho:+.4f}")

        # DS1 敏感性行
        rb1, cl1, ch1, med1, nu1, nd1, rhos1, ns1 = \
            aggregate_per_patient(pat_dict, ds1_patients)
        row_ds1 = {
            "method":      f"{m_label}_DS1_sensitivity",
            "dataset":     "DS1_sensitivity",
            "n_patients":  nu1,
            "fisherz_rho": _r(rb1),
            "ci_lo":       _r(cl1),
            "ci_hi":       _r(ch1),
            "median":      _r(med1),
        }
        for pat in sorted(ds1_patients):
            rho_i, n_i = pat_dict.get(pat, (np.nan, 0))
            row_ds1[f"rho_p{pat}"] = _r(rho_i)
            row_ds1[f"n_p{pat}"]   = int(n_i)
        method_rows.append(row_ds1)
        print(f"  {'':25s}  DS1-sens: rho={rb1:+.4f}  CI[{cl1:+.4f},{ch1:+.4f}]")

    # ═══════════════════════════════════════════════════════════════════════════
    # Section C: 防泄漏对照 (shuffle fixavg_surv6)
    # ═══════════════════════════════════════════════════════════════════════════
    print("\n" + "=" * 70)
    print("Section C: 防泄漏对照 (shuffle Elispot, fixavg_surv6, seed=42)")
    print("=" * 70)

    df_shuf = df.copy()
    rng_shuf = np.random.default_rng(args.seed)
    df_shuf["Elispot"] = rng_shuf.permutation(df_shuf["Elispot"].values)

    lopo_shuf = run_lopo(df_shuf, all_patients, surv6_cols,
                         seed=args.seed, min_pep=args.min_pep,
                         dof_target=2.5, include_gbdt=False)

    shuf_dict = lopo_shuf["fixavg"]
    rb_s, cl_s, ch_s, med_s, nu_s, _nd_s, rhos_s, ns_s = \
        aggregate_per_patient(shuf_dict, ds2_patients)
    print(f"  shuffle_fixavg_surv6: rho={rb_s:+.4f}  CI[{cl_s:+.4f},{ch_s:+.4f}]  "
          f"(期望≈0 → 管道干净)")

    row_shuf = {
        "method":      "shuffle_fixavg_surv6",
        "dataset":     "DS2_shuffle_control",
        "n_patients":  nu_s,
        "fisherz_rho": _r(rb_s),
        "ci_lo":       _r(cl_s),
        "ci_hi":       _r(ch_s),
        "median":      _r(med_s),
    }
    for pat in sorted(ds2_patients):
        rho_i, n_i = shuf_dict.get(pat, (np.nan, 0))
        row_shuf[f"rho_p{pat}"] = _r(rho_i)
        row_shuf[f"n_p{pat}"]   = int(n_i)
    method_rows.append(row_shuf)

    methods_df = pd.DataFrame(method_rows)
    out_methods = out_dir / "fusion_methods.csv"
    with open(out_methods, "w", encoding="utf-8") as f:
        f.write("# fusion_methods.csv\n")
        f.write("# 融合方法 LOPO 结果 (DS2 主分析 + DS1 敏感性 + shuffle 防泄漏对照)\n")
        f.write("# method=方法名 (_DS1_sensitivity=仅参考, _shuffle=防泄漏对照)\n")
        f.write("# dataset: DS2_main / DS1_sensitivity / DS2_shuffle_control\n")
        f.write("# fisherz_rho=Fisher-z加权rho, ci_lo/ci_hi=95%CI, median=中位数\n")
        f.write("# rho_p{id}=该患者per-patient rho_i, n_p{id}=该患者肽数\n")
        methods_df.to_csv(f, index=False)
    print(f"[saved] {out_methods}")

    # ═══════════════════════════════════════════════════════════════════════════
    # Section D: ★ 融合 vs 最优单工具 配对 bootstrap (headline)
    # ═══════════════════════════════════════════════════════════════════════════
    print("\n" + "=" * 70)
    print(f"Section D: 配对检验 (bootstrap B={args.B} + sign test + permutation, seed={args.seed})")
    print(f"           best_single = {best_single_tool}  rho = {best_single_fz:+.4f}")
    print("           Dz_i = arctanh(rho_fusion) - arctanh(rho_single) per patient")
    print("           sign/perm 对 K=9 比 bootstrap 更可靠 (skeptic 红队补充)")
    print("=" * 70)

    if best_single_tool is None or best_single_rhos_arr is None:
        print("[ERR] 无有效最优单工具, 跳过 Section D")
        paired_rows = []
    else:
        main_fusion_labels = ["fixavg_surv6", "rankmean_surv6",
                              "ridge_surv6", "gbdt_surv6"]
        paired_rows = []

        for m_label in main_fusion_labels:
            if m_label not in fusion_pat_rhos:
                continue
            fus_rhos_arr, fus_ns_arr = fusion_pat_rhos[m_label]

            # ── bootstrap (点估 + CI + P) ──────────────────────────────────
            dz_mean, ci_lo_b, ci_hi_b, p_boot, prob_gt0 = paired_bootstrap(
                fus_rhos_arr, fus_ns_arr,
                best_single_rhos_arr, best_single_ns_arr,
                B=args.B, seed=args.seed,
            )

            # ── 精确符号检验 (K=9 首选) ────────────────────────────────────
            sign_p, n_pos, n_neg = sign_test_exact_p(
                fus_rhos_arr, fus_ns_arr,
                best_single_rhos_arr, best_single_ns_arr,
            )

            # ── 配对置换检验 全枚举 2^K (K=9→512种) ──────────────────────
            perm_p = permutation_sign_flip_p(
                fus_rhos_arr, fus_ns_arr,
                best_single_rhos_arr, best_single_ns_arr,
                seed=args.seed,
            )

            fus_rho_bar = fusion_fz_rho.get(m_label, np.nan)
            sign_p_str = f"{sign_p:.4f}" if not np.isnan(sign_p) else "NaN"
            perm_p_str = f"{perm_p:.4f}" if not np.isnan(perm_p) else "NaN"
            print(f"  {m_label:<25s}  Dz={dz_mean:+.4f}  "
                  f"CI[{ci_lo_b:+.4f},{ci_hi_b:+.4f}]  "
                  f"boot_p={p_boot:.4f}  sign_p={sign_p_str} (n+={n_pos},n-={n_neg})  "
                  f"perm_p={perm_p_str}  P(D>0)={prob_gt0:.3f}")

            paired_rows.append({
                "method":           m_label,
                "best_single_tool": best_single_tool,
                "delta_z_mean":     _r(dz_mean),
                "delta_z_ci_lo":    _r(ci_lo_b),
                "delta_z_ci_hi":    _r(ci_hi_b),
                "p_two_sided":      _r(p_boot),
                "prob_delta_gt0":   _r(prob_gt0),
                "sign_test_p":      _r(sign_p),
                "n_pos":            n_pos,
                "n_neg":            n_neg,
                "perm_test_p":      _r(perm_p),
                "fusion_rho":       _r(fus_rho_bar),
                "single_rho":       _r(best_single_fz),
            })

    paired_df = pd.DataFrame(paired_rows) if paired_rows else pd.DataFrame()
    out_paired = out_dir / "fusion_vs_single_paired.csv"
    with open(out_paired, "w", encoding="utf-8") as f:
        f.write("# fusion_vs_single_paired.csv\n")
        f.write(f"# 融合 vs 最优单工具 患者级配对检验 (bootstrap B={args.B} + sign + permutation)\n")
        f.write("# delta_z = arctanh(rho_fusion) - arctanh(rho_best_single) per patient\n")
        f.write("# delta_z_mean=简单均值点估; delta_z_ci_lo/hi=bootstrap percentile 95%CI\n")
        f.write("# p_two_sided=bootstrap 2*min(P(D>0),P(D<0)); prob_delta_gt0=P(Dz>0)\n")
        f.write("# sign_test_p=精确符号检验 p (二项 p=0.5, K=9 首选); n_pos/n_neg=正负个数\n")
        f.write("# perm_test_p=配对置换检验 p (全枚举 2^K=512 符号翻转, K=9 首选)\n")
        f.write("# fusion_rho/single_rho=整体 Fisher-z rho_bar\n")
        f.write("# headline: 三检验 p 若均大→融合不显著超最优单工具 (复现朱结论)\n")
        if not paired_df.empty:
            paired_df.to_csv(f, index=False)
    print(f"[saved] {out_paired}")

    # ═══════════════════════════════════════════════════════════════════════════
    # Section E: 天花板距离
    # ═══════════════════════════════════════════════════════════════════════════
    print("\n" + "=" * 70)
    print(f"Section E: 天花板距离 (ceiling_low={CEILING_LOW}, ceiling_high={CEILING_HIGH})")
    print("=" * 70)

    ceiling_rows = []

    # best_single CI 从 floor_df 读
    bs_row = floor_df[floor_df["tool"] == best_single_tool] \
        if best_single_tool else pd.DataFrame()
    bs_ci_lo = float(bs_row["ci_lo"].iloc[0]) if len(bs_row) > 0 else np.nan
    bs_ci_hi = float(bs_row["ci_hi"].iloc[0]) if len(bs_row) > 0 else np.nan

    all_methods_ceiling = []
    if best_single_tool:
        all_methods_ceiling.append(
            (f"single_{best_single_tool}", best_single_fz, bs_ci_lo, bs_ci_hi))

    # 融合法 CI 从 methods_df 读 (DS2_main 行)
    for m_label in ["fixavg_surv6", "rankmean_surv6", "ridge_surv6", "gbdt_surv6"]:
        sub = methods_df[(methods_df["method"] == m_label) &
                         (methods_df["dataset"] == "DS2_main")]
        if len(sub) == 0:
            continue
        rho_m  = float(sub["fisherz_rho"].iloc[0])
        ci_lo_m = float(sub["ci_lo"].iloc[0])
        ci_hi_m = float(sub["ci_hi"].iloc[0])
        all_methods_ceiling.append((m_label, rho_m, ci_lo_m, ci_hi_m))

    for name, rho_m, ci_lo_m, ci_hi_m in all_methods_ceiling:
        dist_to_04 = float(CEILING_LOW - rho_m) if not np.isnan(rho_m) else np.nan
        ci_touches = bool(not np.isnan(ci_hi_m) and ci_hi_m >= CEILING_LOW)

        ci_str = f"[{ci_lo_m:+.4f},{ci_hi_m:+.4f}]" if not np.isnan(ci_lo_m) else "[N/A]"
        print(f"  {name:<35s}  rho={rho_m:+.4f}  CI{ci_str}  "
              f"dist_to_0.4={dist_to_04:+.4f}  "
              f"ci_touches={'YES' if ci_touches else 'NO'}")

        ceiling_rows.append({
            "method":             name,
            "fisherz_rho":        _r(rho_m),
            "ci_hi":              _r(ci_hi_m),
            "ceiling_low":        CEILING_LOW,
            "ceiling_high":       CEILING_HIGH,
            "dist_to_0.4":        _r(dist_to_04),
            "ci_touches_ceiling": ci_touches,
        })

    ceiling_df = pd.DataFrame(ceiling_rows)
    out_ceiling = out_dir / "fusion_ceiling_distance.csv"
    with open(out_ceiling, "w", encoding="utf-8") as f:
        f.write("# fusion_ceiling_distance.csv\n")
        f.write("# 各方法 rho_bar 到理论天花板 [0.4, 0.6] 的距离\n")
        f.write("# ceiling_low=0.4 / ceiling_high=0.6 (precursor frequency 锁, THEORY_quant.md)\n")
        f.write("# dist_to_0.4 = 0.4 - fisherz_rho (正值=未触及天花板下沿)\n")
        f.write("# ci_touches_ceiling = (ci_hi >= 0.4)\n")
        ceiling_df.to_csv(f, index=False)
    print(f"[saved] {out_ceiling}")

    # ═══════════════════════════════════════════════════════════════════════════
    # 终汇 SUMMARY
    # ═══════════════════════════════════════════════════════════════════════════
    print("\n" + "=" * 70)
    print("SUMMARY (主结论, DS2 9患者)")
    print("=" * 70)
    print(f"  best_single = {best_single_tool}  rho = {best_single_fz:+.4f}")
    for m_label in ["fixavg_surv6", "rankmean_surv6", "ridge_surv6", "gbdt_surv6"]:
        rho_m = fusion_fz_rho.get(m_label, np.nan)
        print(f"  {m_label:<25s}  rho = {rho_m:+.4f}")
    print()
    if paired_rows:
        print("  配对显著性 (headline — 复现朱 p=0.70):")
        print(f"  {'method':<25s}  boot_p   sign_p   perm_p   Dz_mean")
        for row in paired_rows:
            def _ps(v):
                return f"{float(v):.4f}" if (v is not None and not np.isnan(float(v))) else "  NaN"
            print(f"    {row['method']:<25s}  {_ps(row['p_two_sided'])}  "
                  f"{_ps(row['sign_test_p'])}  {_ps(row['perm_test_p'])}  "
                  f"{_ps(row['delta_z_mean'])}")
    print("=" * 70)
    print("[DONE] 输出文件:")
    print(f"  {out_floor}")
    print(f"  {out_methods}")
    print(f"  {out_paired}")
    print(f"  {out_ceiling}")


if __name__ == "__main__":
    main()
