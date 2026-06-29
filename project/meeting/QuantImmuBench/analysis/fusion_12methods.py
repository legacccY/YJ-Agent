#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fusion_12methods.py
===================
服务: QuantImmuBench § G4 lever (fusion 扩 12 法 + geomean 单列, 论文头号 claim 主角)
对应大纲: §2.5 Fusion methods (12 种) + §3.3.1 多维 fusion 对比 (表 6)

定位:
  把 fusion 整合引擎从原 fusion_study.py 的 4 法 (fixavg/rankmean/ridge/gbdt) 扩到
  权威大纲表 4 列举的 12 法, 并暴露干净可 import 的 API 供下游 E1 (robustness) /
  E4 (ablation) 复用 (避免各自重写 fusion + per-patient Spearman 主指标)。

  ★ 不改 fusion_study.py — 直接 import 其统计引擎 (spearman_np / fisherz_weighted_agg /
    impute_fold / find_ridge_alpha), 保证与既有产物口径完全一致、零破坏。

════════════════════════════════════════════════════════════════════════════════
可 import 的公开 API (E1/E4 coder 直接拿这些, 别重写)
════════════════════════════════════════════════════════════════════════════════

  常量 / 注册表
  ----------------------------------------------------------------------------
  METHOD_ORDER : list[str]
      12 法规范顺序 (= 大纲表 4 列举顺序)。
  UNSUPERVISED_FUSIONS : dict[str, callable]
      无监督排名融合的「纯组合子」: fn(R: np.ndarray (n×D 病人内 rank 矩阵), **params)
      -> np.ndarray (n,)。不碰标签。8 个: mean_rank/geomean/median/powmean/max/min/
      weighted_mean_rank/softmax_rank。
  LEARNING_FUSIONS : set[str]
      学习型 (需 LOPO 无泄漏): {ridge, gbdt, stacking, constrained}。
  FUSION_METHODS : dict[str, callable]
      ★ 统一高层 API。所有 12 法签名一致:
          FUSION_METHODS[name](df, dim_cols, **params) -> pd.Series
      返回每行 (每突变) 1 个综合分 (与 df.index 对齐), 无监督=病人内 rank 组合,
      学习型=LOPO out-of-fold 预测 (无泄漏)。= functools.partial(apply_fusion, method=name)。

  统一入口
  ----------------------------------------------------------------------------
  apply_fusion(df, dim_cols, method, *, label_col='Elispot', patients=None,
               seed=42, min_pep=MIN_PEP, dof_target=2.5, **params) -> pd.Series
      df       : 含 Patient_ID / 各 dim 列 / label_col 的 DataFrame。
      dim_cols : 参与融合的维度列名 list (缺失列自动剔除并 warn)。
      method   : METHOD_ORDER 中之一。
      返回     : pd.Series, index==df.index, 每行 1 个综合分 (无效行/缺维=NaN)。
                 无监督法: 每病人内各维转 rank → 组合 (不用标签, leak-free)。
                 学习型法: patient-level LOPO, 留一病人, 用其余病人训练后预测留出行
                          (无泄漏); 标准化/缺失填补均仅用训练折统计 (照抄 run_lopo 协议)。

  主指标 (per-patient Spearman, Fisher-z 等权平均)
  ----------------------------------------------------------------------------
  per_patient_spearman(df, score_col, *, label_col='Elispot', patients=None,
                       min_pep=MIN_PEP) -> tuple
      返回 (rho_bar, ci_lo, ci_hi, n_used):
        rho_bar : Fisher-z 加权固定效应均值 ρ (主指标);
        ci_lo/ci_hi : 95% CI (Fisher-z, 同 fusion_study 口径);
        n_used  : 纳入聚合的有效病人数 (n_pep>=min_pep 且 n>FISHER_MIN_N)。
      纯封装 fusion_study.fisherz_weighted_agg, 与既有数字逐位可比。

════════════════════════════════════════════════════════════════════════════════
12 法逐一对照大纲表 4 (定义来源 + 置信)
════════════════════════════════════════════════════════════════════════════════
  ⚠️ 大纲表 4 原文只写「按 fourdim_cls2_aggregation.py / robustness_7dim_fusions.py /
     nested_lopo_ensemble.py / stacking_lopo.py 实际枚举填表 4」——这些朱同学的脚本
     不在本 repo, 故每法确切数学形式 (尤其 powmean p / softmax-rank T / weighted 权重 /
     constrained 约束形式) 大纲未给。以下为标准 rank-fusion 定义 + 合理默认, 凡大纲未
     明确处均标 [TODO 待朱对账], 绝不臆造成「权威」。Spearman 对最终分的单调变换不敏感,
     部分实现细节 (eps/平移) 不影响排名结论。

  设某病人内, 第 d 维原始分转升序 rank r_d ∈ [1, n] (分越大 rank 越大 = 越免疫原,
  与 Step1 定向一致), R = (r_1,...,r_D)。综合分 s:

  无监督 (8, 不碰标签):
   1. mean_rank          s = mean_d(r_d)                      —— 大纲列首项「mean-rank」, 标准定义。
   2. geomean ★头号主角   s = exp(mean_d(ln r_d)) = (Π r_d)^(1/D)
                         共识/AND 型: 任一维 rank 低则整体被拉低 (与 max 的 OR 型对立)。
                         r_d>=1 恒正, 无需平移。大纲 §3.3 明确 geomean 为唯一过双重检验的法则。
   3. median            s = median_d(r_d)                     —— 标准定义。
   4. powmean           s = (mean_d(r_d^p))^(1/p), 默认 p=2   —— [TODO p 待朱对账, 大纲未给]。
                         p=1→mean, p→0→geomean, p→+∞→max, p→-∞→min; p=2 偏 OR (二次平均)。
   5. max  (OR型)        s = max_d(r_d)                        —— 标准定义。
   6. min               s = min_d(r_d)                        —— 标准定义。
   7. weighted_mean_rank s = Σ_d w_d r_d / Σ_d w_d, 默认 w=等权(→塌回 mean_rank)
                         —— [TODO 权重方案待朱对账]; 大纲 §3.3.2 实测「加权一律塌回等权」。
                         经 weights=... 暴露给 ablation。
   8. softmax_rank      s = Σ_d softmax(r_d/T) · r_d, 默认 T=1 —— [TODO T 待朱对账, 大纲未给]。
                         逐行对各维 rank 做 softmax 加权 (沿用 pooling_sweep.pool_softmax 惯例,
                         数值稳定减 max), 偏向各突变 rank 最高的维 → 软 OR。

  学习型 (4, 必须 LOPO 无泄漏):
   9. stacking          线性回归 (OLS, sklearn LinearRegression) 元学习, LOPO 训练。
                         —— 大纲 §2.5「stacking/线性回归」; 对应 stacking_lopo.py [TODO 确切 meta 特征待对账]。
  10. constrained       非负 + 单纯形约束 (w>=0, Σw=1) 线性拟合, LOPO 训练。
                         —— 大纲 §2.5「constrained」; 对应 constrained_nested.py。
                         [TODO 确切约束形式待对账]; 本实现 = 投影梯度下降解 min‖Xw−y‖² s.t. 单纯形。
  11. ridge            Ridge, alpha 网格使 eff_DOF≈dof_target, LOPO。
                         —— 复用 fusion_study.find_ridge_alpha, 与既有 ridge_surv6 同协议。
  12. gbdt             GradientBoostingRegressor(max_depth=2,...), LOPO。
                         —— 复用 fusion_study 同超参 (仅敏感性, 大纲未将其列为主推)。

Windows 规范: UTF-8 stdout, 禁 scipy (OMP Error #15), 纯 numpy/pandas/sklearn, 零 GPU,
            pathlib 路径。

输入:  quantimmune/model_matrix_v2.csv (E0 产物, 183 行)
输出 (analysis/):
  fusion_12methods.csv  —— 列: method, ndim, fisherz_rho, ci_low, ci_high, ds1_sensitivity

跑法 (主线跑, 我不跑):
  python analysis/fusion_12methods.py
  python analysis/fusion_12methods.py --matrix quantimmune/model_matrix_v2.csv --seed 42
"""

import sys
import argparse
import functools
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge, LinearRegression
from sklearn.ensemble import GradientBoostingRegressor

# Windows 必要: UTF-8 stdout
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

HERE = Path(__file__).resolve().parent           # analysis/
ROOT = HERE.parent                                # QuantImmuBench/

# ── 复用 fusion_study 引擎 (不改原脚本, 仅 import) ──────────────────────────────
sys.path.insert(0, str(HERE))
from fusion_study import (                        # noqa: E402
    spearman_np,
    fisherz_weighted_agg,
    impute_fold,
    find_ridge_alpha,
    MIN_PEP,
    FISHER_MIN_N,
    DS1_PATIENTS,
    DS2_PATIENTS,
    SURV6_TOOLS,
)

DEFAULT_MATRIX = ROOT / "quantimmune" / "model_matrix_v2.csv"

# ── 维度集 (planner 默认, 朱同学待最终拍板) ─────────────────────────────────────
# 列名均已对照 quantimmune/model_matrix_v2.csv 核实存在。
DIM3 = ["pool_netAffneg_top20", "MT_PRIME", "MT_deepHLApan"]
# 4 维 = 3 维 + 1。大纲 §3.3.1 提 4 维 (朱 fourdim_cls2_aggregation.py), 但该脚本不在本
# repo, 第 4 维确切成员未确认 → [TODO 待朱对账]。默认补 MT_PredIG (大纲 §3.1 单工具最强 +0.322)。
DIM4 = DIM3 + ["MT_PredIG"]
# 6 维 = 现有 SURV6 (照搬 fusion_study.SURV6_TOOLS, 已核 v2 列名全在):
#   MT_PredIG / MT_IMPROVE_mean_prediction_rf / MT_pTuneos / MT_PRIME / MT_ImmuneApp / MT_deepHLApan
DIM6 = list(SURV6_TOOLS)
# 7 维 = SURV6 + pool_netAffneg_top20 (per planner 派单)
DIM7 = list(SURV6_TOOLS) + ["pool_netAffneg_top20"]

DIM_SETS = {3: DIM3, 4: DIM4, 6: DIM6, 7: DIM7}

GBDT_PARAMS = dict(max_depth=2, n_estimators=100, subsample=0.8)  # 同 fusion_study


# ═══════════════════════════════════════════════════════════════════════════════
# 无监督排名融合「纯组合子」: fn(R, **params) -> (n,)。R = n×D 病人内 rank 矩阵。
# 不碰标签 (leak-free)。Spearman 对单调变换不敏感, eps 等不影响排名。
# ═══════════════════════════════════════════════════════════════════════════════

def fuse_mean_rank(R: np.ndarray) -> np.ndarray:
    """1. mean-rank: 各维 rank 算术平均。"""
    return np.nanmean(R, axis=1)


def fuse_geomean(R: np.ndarray, eps: float = 1e-9) -> np.ndarray:
    """2. ★geomean (头号主角): rank 几何平均 = exp(mean(ln r))。
    共识/AND 型 (任一维 rank 低则整体被拉低)。r>=1 恒正, 无需平移。
    """
    return np.exp(np.nanmean(np.log(np.maximum(R, eps)), axis=1))


def fuse_median(R: np.ndarray) -> np.ndarray:
    """3. median: 各维 rank 中位数。"""
    return np.nanmedian(R, axis=1)


def fuse_powmean(R: np.ndarray, p: float = 2.0) -> np.ndarray:
    """4. powmean (幂平均/广义平均): (mean(r^p))^(1/p)。
    p=1→mean, p→0→geomean, p→+∞→max; 默认 p=2 偏 OR。
    [TODO p 待朱 robustness_7dim_fusions.py 对账, 大纲表 4 未给确切 p]。
    """
    return np.nanmean(np.power(R, p), axis=1) ** (1.0 / p)


def fuse_max(R: np.ndarray) -> np.ndarray:
    """5. max (OR 型): 各维 rank 最大值。"""
    return np.nanmax(R, axis=1)


def fuse_min(R: np.ndarray) -> np.ndarray:
    """6. min: 各维 rank 最小值。"""
    return np.nanmin(R, axis=1)


def fuse_weighted_mean_rank(R: np.ndarray, weights=None) -> np.ndarray:
    """7. weighted mean-rank: Σ w_d r_d / Σ w_d。
    默认等权 (→ 塌回 mean_rank, 与大纲 §3.3.2「加权塌回等权」一致)。
    [TODO 权重方案待朱对账]; 经 weights=array 暴露给 ablation。
    """
    D = R.shape[1]
    if weights is None:
        weights = np.ones(D, dtype=float)
    w = np.asarray(weights, dtype=float)
    w = w / w.sum()
    return np.nansum(R * w[np.newaxis, :], axis=1)


def fuse_softmax_rank(R: np.ndarray, T: float = 1.0) -> np.ndarray:
    """8. softmax-rank: 逐行对各维 rank 做 softmax 加权求和 s=Σ softmax(r_d/T)·r_d。
    数值稳定 (逐行减 max), 沿用 pooling_sweep.pool_softmax 惯例。偏向各突变 rank 最高
    的维 → 软 OR。[TODO T 待朱对账, 大纲表 4 未给 T]。
    """
    logits = R / T
    logits = logits - np.nanmax(logits, axis=1, keepdims=True)
    w = np.exp(logits)
    w = w / np.nansum(w, axis=1, keepdims=True)
    return np.nansum(w * R, axis=1)


UNSUPERVISED_FUSIONS = {
    "mean_rank":          fuse_mean_rank,
    "geomean":            fuse_geomean,
    "median":             fuse_median,
    "powmean":            fuse_powmean,
    "max":                fuse_max,
    "min":                fuse_min,
    "weighted_mean_rank": fuse_weighted_mean_rank,
    "softmax_rank":       fuse_softmax_rank,
}

LEARNING_FUSIONS = {"ridge", "gbdt", "stacking", "constrained"}

METHOD_ORDER = [
    "mean_rank", "geomean", "median", "powmean", "max", "min",
    "weighted_mean_rank", "softmax_rank",
    "stacking", "constrained", "ridge", "gbdt",
]


# ═══════════════════════════════════════════════════════════════════════════════
# constrained: 单纯形约束 (w>=0, Σw=1) 线性拟合 — 投影梯度下降 (纯 numpy, 无 scipy)
# ═══════════════════════════════════════════════════════════════════════════════

def _project_simplex(v: np.ndarray) -> np.ndarray:
    """欧氏投影到概率单纯形 {w>=0, Σw=1} (Held et al. 1974 / Duchi 2008)。"""
    v = np.asarray(v, dtype=float)
    n = len(v)
    u = np.sort(v)[::-1]
    css = np.cumsum(u)
    rho_idx = np.nonzero(u * np.arange(1, n + 1) > (css - 1.0))[0]
    if len(rho_idx) == 0:
        return np.ones(n) / n
    rho = rho_idx[-1]
    theta = (css[rho] - 1.0) / (rho + 1.0)
    return np.maximum(v - theta, 0.0)


def _fit_simplex(X: np.ndarray, y: np.ndarray,
                 n_iter: int = 2000) -> np.ndarray:
    """投影梯度下降解 min ‖Xw − y‖² s.t. w>=0, Σw=1。返回 w (D,)。
    [TODO constrained 确切约束形式待朱 constrained_nested.py 对账]。
    """
    D = X.shape[1]
    if D == 1:
        return np.ones(1)
    w = np.ones(D) / D
    XtX = X.T @ X
    Xty = X.T @ y
    # 步长 = 1/Lipschitz, L = 最大特征值 (谱范数)
    L = float(np.linalg.norm(XtX, 2)) + 1e-9
    lr = 1.0 / L
    for _ in range(n_iter):
        grad = XtX @ w - Xty
        w = _project_simplex(w - lr * grad)
    return w


# ═══════════════════════════════════════════════════════════════════════════════
# 学习型 LOPO out-of-fold 预测 (照抄 fusion_study.run_lopo 防泄漏协议)
# ═══════════════════════════════════════════════════════════════════════════════

def _lopo_scores(df: pd.DataFrame, dim_cols: list, method: str,
                 patients: list, label_col: str, seed: int,
                 min_pep: int, dof_target: float) -> pd.Series:
    """patient-level LOPO: 留一病人, 用其余病人训练, 预测留出行 (out-of-fold)。
    防泄漏: 缺失用训练折均值填; 标准化用训练折统计 (照抄 run_lopo)。
    返回 pd.Series (index==df.index, 仅 patients 内行有值, 其余 NaN)。
    """
    result = pd.Series(np.nan, index=df.index, dtype=float)
    universe = df[df["Patient_ID"].isin(patients)]

    for pat in patients:
        test_mask    = universe["Patient_ID"] == pat
        train_df_raw = universe[~test_mask].copy()
        test_df_raw  = universe[test_mask].copy()
        if len(test_df_raw) == 0:
            continue

        train_df, test_df = impute_fold(train_df_raw, test_df_raw, dim_cols)
        X_train = train_df[dim_cols].values.astype(float)
        X_test  = test_df[dim_cols].values.astype(float)
        y_train = train_df[label_col].values.astype(float)

        valid_train = ~np.isnan(y_train)
        X_train = X_train[valid_train]
        y_train = y_train[valid_train]
        if len(X_train) == 0:
            continue

        # 标准化 (训练折统计)
        X_mean = np.nanmean(X_train, axis=0)
        X_std  = np.nanstd(X_train, axis=0)
        X_std[X_std < 1e-10] = 1.0
        X_train_s = (X_train - X_mean) / X_std
        X_test_s  = (X_test  - X_mean) / X_std

        if method == "ridge":
            alpha_best, _ = find_ridge_alpha(X_train_s, target_dof=dof_target)
            model = Ridge(alpha=alpha_best, fit_intercept=True)
            model.fit(X_train_s, y_train)
            pred = model.predict(X_test_s)
        elif method == "gbdt":
            model = GradientBoostingRegressor(random_state=seed, **GBDT_PARAMS)
            model.fit(X_train_s, y_train)
            pred = model.predict(X_test_s)
        elif method == "stacking":
            # OLS 线性回归元学习器
            model = LinearRegression(fit_intercept=True)
            model.fit(X_train_s, y_train)
            pred = model.predict(X_test_s)
        elif method == "constrained":
            # 单纯形约束线性拟合 (intercept 对 Spearman 排名无影响, 用 y 居中)
            y_c = y_train - y_train.mean()
            w = _fit_simplex(X_train_s, y_c)
            pred = X_test_s @ w
        else:
            raise ValueError(f"未知学习型 method: {method}")

        result.loc[test_df.index] = pred

    return result


# ═══════════════════════════════════════════════════════════════════════════════
# ★ 统一入口 apply_fusion
# ═══════════════════════════════════════════════════════════════════════════════

def apply_fusion(df: pd.DataFrame, dim_cols: list, method: str, *,
                 label_col: str = "Elispot", patients=None,
                 seed: int = 42, min_pep: int = MIN_PEP,
                 dof_target: float = 2.5, **params) -> pd.Series:
    """对 df 的 dim_cols 应用某 fusion 法, 返回每行综合分 Series (index==df.index)。

    无监督法 (METHOD_ORDER 前 8): 每病人内各维转升序 rank → 组合子 (不用标签)。
                                  缺失值用「该病人该维均值」填 (leak-free), 全 NaN 维填 0。
    学习型法 (ridge/gbdt/stacking/constrained): patient-level LOPO out-of-fold 预测 (无泄漏)。

    参数:
      patients : 限定参与的病人 ID list; None=df 全部病人。
      **params : 透传给无监督组合子 (如 powmean p=..., softmax_rank T=..., weighted weights=...)。
    """
    present = [c for c in dim_cols if c in df.columns]
    missing = [c for c in dim_cols if c not in df.columns]
    if missing:
        print(f"[warn] apply_fusion: 维度列缺失, 已剔除: {missing}")
    if len(present) == 0:
        return pd.Series(np.nan, index=df.index, dtype=float)

    if patients is None:
        patients = sorted(df["Patient_ID"].unique().tolist())

    if method in LEARNING_FUSIONS:
        return _lopo_scores(df, present, method, patients,
                            label_col, seed, min_pep, dof_target)

    if method not in UNSUPERVISED_FUSIONS:
        raise ValueError(f"未知 method: {method} (合法: {METHOD_ORDER})")

    combiner = UNSUPERVISED_FUSIONS[method]
    result = pd.Series(np.nan, index=df.index, dtype=float)

    for pat, g in df.groupby("Patient_ID"):
        if pat not in patients:
            continue
        sub = g[present].astype(float)
        # 病人内均值填补 (无泄漏: 不碰标签, 不碰他人)
        filled = sub.fillna(sub.mean())
        filled = filled.fillna(0.0)
        # 各维升序 rank (分越大 rank 越大 = 越免疫原), method='average' 处理并列
        R = np.column_stack([
            filled[c].rank(method="average").values.astype(float)
            for c in present
        ])
        s = combiner(R, **params)
        result.loc[g.index] = np.asarray(s, dtype=float)

    return result


# ── 统一高层注册表: 12 法签名一致 (df, dim_cols, **params) -> Series ────────────
FUSION_METHODS = {
    name: functools.partial(apply_fusion, method=name)
    for name in METHOD_ORDER
}


# ═══════════════════════════════════════════════════════════════════════════════
# ★ 主指标: per-patient Spearman, Fisher-z 等权平均 (封装 fusion_study 引擎)
# ═══════════════════════════════════════════════════════════════════════════════

def per_patient_spearman(df: pd.DataFrame, score_col, *,
                         label_col: str = "Elispot", patients=None,
                         min_pep: int = MIN_PEP) -> tuple:
    """主指标: 逐病人 Spearman(score, label), 跨病人 Fisher-z 加权平均 + 95%CI。

    score_col : df 中的列名 (str) 或与 df 等长的 array/Series (apply_fusion 的返回值)。
    返回 (rho_bar, ci_lo, ci_hi, n_used)。口径与 fusion_study 逐位可比。
    """
    work = df.copy()
    if isinstance(score_col, str):
        col = score_col
    else:
        col = "__fusion_score__"
        work[col] = np.asarray(score_col, dtype=float)

    if patients is None:
        patients = sorted(work["Patient_ID"].unique().tolist())
    else:
        patients = sorted(patients)

    rhos, ns = [], []
    for pat in patients:
        pat_df = work[work["Patient_ID"] == pat]
        n = len(pat_df)
        x = pat_df[col].values.astype(float)
        y = pat_df[label_col].values.astype(float)
        rho = spearman_np(x, y) if n >= min_pep else np.nan
        rhos.append(rho)
        ns.append(float(n))

    rho_bar, ci_lo, ci_hi, n_used, _n_dropped = fisherz_weighted_agg(
        np.array(rhos, dtype=float), np.array(ns, dtype=float))
    return rho_bar, ci_lo, ci_hi, n_used


# ═══════════════════════════════════════════════════════════════════════════════
# 主程序: 12 法 × {3,4,6,7} 维 → fusion_12methods.csv
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    ap = argparse.ArgumentParser(
        description="fusion_12methods.py — QuantImmuBench G4: 12 fusion × {3,4,6,7} 维")
    ap.add_argument("--matrix", default=str(DEFAULT_MATRIX),
                    help="model_matrix_v2.csv 路径")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--min_pep", type=int, default=MIN_PEP,
                    help=f"病人内最少肽数才算 rho (默认 {MIN_PEP})")
    args = ap.parse_args()

    matrix_path = Path(args.matrix)
    if not matrix_path.exists():
        sys.exit(f"[ERR] model_matrix 不存在: {matrix_path}")
    df = pd.read_csv(matrix_path, encoding="utf-8")
    print(f"[info] matrix: {df.shape}, 病人={df['Patient_ID'].nunique()}")

    ds2 = sorted([p for p in DS2_PATIENTS if p in df["Patient_ID"].unique()])
    ds1 = sorted([p for p in DS1_PATIENTS if p in df["Patient_ID"].unique()])
    print(f"[info] DS2 (主分析) = {ds2}")
    print(f"[info] DS1 (敏感性) = {ds1}")

    def _r(v, d=6):
        return round(float(v), d) if (v is not None and not np.isnan(float(v))) else np.nan

    rows = []
    for ndim in sorted(DIM_SETS.keys()):
        dims = DIM_SETS[ndim]
        present = [c for c in dims if c in df.columns]
        miss = [c for c in dims if c not in df.columns]
        print("\n" + "=" * 70)
        print(f"[{ndim} 维] dims={present}" + (f"  (缺失剔除: {miss})" if miss else ""))
        print("=" * 70)

        for method in METHOD_ORDER:
            # DS2 主分析
            s2 = apply_fusion(df, present, method, patients=ds2,
                              seed=args.seed, min_pep=args.min_pep)
            rho2, cl2, ch2, nu2 = per_patient_spearman(
                df, s2, patients=ds2, min_pep=args.min_pep)

            # DS1 敏感性 (诚实呈现; 大纲: DS1 fusion 不复现 −0.157/−0.160)
            ds1_rho = np.nan
            if ds1:
                s1 = apply_fusion(df, present, method, patients=ds1,
                                  seed=args.seed, min_pep=args.min_pep)
                ds1_rho, _, _, _ = per_patient_spearman(
                    df, s1, patients=ds1, min_pep=args.min_pep)

            rows.append({
                "method":          method,
                "ndim":            ndim,
                "fisherz_rho":     _r(rho2),
                "ci_low":          _r(cl2),
                "ci_high":         _r(ch2),
                "ds1_sensitivity": _r(ds1_rho),
            })
            ci_str = f"[{cl2:+.4f},{ch2:+.4f}]" if not np.isnan(cl2) else "[N/A]"
            print(f"  {method:<20s}  rho={rho2:+.4f}  CI{ci_str}  "
                  f"ds1={ds1_rho:+.4f}  (n_pat={nu2})")

    out_df = pd.DataFrame(rows)
    out_path = HERE / "fusion_12methods.csv"
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("# fusion_12methods.csv\n")
        f.write("# QuantImmuBench G4: 12 fusion 法 × {3,4,6,7} 维 LOPO per-patient Spearman\n")
        f.write("# method=融合法 (顺序=大纲表4); ndim=维度集大小\n")
        f.write("# fisherz_rho=DS2主分析 Fisher-z 加权 rho; ci_low/ci_high=95%CI (Fisher-z)\n")
        f.write("# ds1_sensitivity=DS1 敏感性 rho (诚实呈现, 大纲: DS1 fusion 不复现)\n")
        f.write("# 无监督法不碰标签; 学习型(ridge/gbdt/stacking/constrained)=LOPO 无泄漏\n")
        out_df.to_csv(f, index=False)
    print(f"\n[saved] {out_path}")
    print("[DONE]")


if __name__ == "__main__":
    main()
