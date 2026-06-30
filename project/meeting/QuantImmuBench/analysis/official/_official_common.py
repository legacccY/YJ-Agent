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

输入 (只读, 已 sha256 冻结, 绝不改):
  data/frozen/pooled_peptide_level_30tools.csv  —— 130 肽级行; 元数据列
    mut_key,Patient_ID,Peptide_ID,Elispot,n_subpep + 每工具×8 pooling 列 <Tool>_<pooling>。
  纯 DS2 (9 患者 101,102,104..110), Elispot=连续 SFC 真值 (负值不 clip 不二值化)。

硬约束 (task 派单):
  · Spearman 纯 numpy (禁 scipy.stats, 防 OMP Error #15); p-value 如需可用 scipy.special.betainc。
  · per-patient min_pep=3 (不足跳过, 记 n_dropped); Fisher-z 等权聚合 (n<=FISHER_MIN_N=3 剔出加权)。
  · DTU 工具结果照常算, 由调用脚本注释标 pending_DTU_consent。

Windows 规范: UTF-8 stdout, pathlib 路径, 纯 numpy/pandas/sklearn, 零 GPU。
"""

import sys
import functools
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
FROZEN_POOLED = ROOT / "data" / "frozen" / "pooled_peptide_level_30tools.csv"
FROZEN_GT = ROOT / "data" / "frozen" / "ds2_official_groundtruth.csv"
OUT_DIR = HERE                                           # analysis/official/

# ── 常量 (口径真源, 与冻结表对齐) ─────────────────────────────────────────────
# 冻结表实测患者 = DS2 9 人 (101,102,104,105,106,107,108,109,110), 无 DS1。
DS2_PATIENTS = [101, 102, 104, 105, 106, 107, 108, 109, 110]

# 8 pooling (命名严格对齐冻结表表头; sum 列命名 <Tool>_sum)
POOLINGS = ["max", "mean", "geomean", "sum", "softmax", "top3mean", "topk_w", "rankdecay"]

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


def fisherz_weighted_agg(rhos, ns):
    """Fisher-z 固定效应加权均值 + 95%CI。Var(z_i)=(1+rho_i^2/2)/(n_i-3)
    [Fieller-Hartley-Pearson 1957]; n_i<=FISHER_MIN_N 剔出。照抄 fusion_study.py。
    返回 (rho_bar, ci_lo, ci_hi, n_used, n_dropped)。
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
    w = 1.0 / var_z
    sum_w = w.sum()
    z_bar = (w * z).sum() / sum_w
    rho_bar = float(np.tanh(z_bar))
    ci_lo = float(np.tanh(z_bar - 1.96 / np.sqrt(sum_w)))
    ci_hi = float(np.tanh(z_bar + 1.96 / np.sqrt(sum_w)))
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


def present_patients(df, patients=None):
    """返回 df 中实际存在的目标患者 (默认 DS2 9 人), 升序。"""
    pats = patients if patients is not None else DS2_PATIENTS
    return sorted([p for p in pats if p in set(df["Patient_ID"].unique())])


# ═══════════════════════════════════════════════════════════════════════════════
# ★ 主指标: per-patient Spearman, Fisher-z 等权聚合 (封装, 与旧骨架口径逐位可比)
# ═══════════════════════════════════════════════════════════════════════════════

def per_patient_spearman(df, score, *, patients=None, min_pep=MIN_PEP,
                         label_col=LABEL_COL, return_perpat=False):
    """逐病人 Spearman(score, label), 跨病人 Fisher-z 加权聚合 + 95%CI。

    score : df 列名 (str) 或与 df 等长 array/Series (fusion 返回值)。
    患者内 n_pep>=min_pep 才算 rho (否则该患者 rho=NaN, 不进聚合)。
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
        np.array(rhos, float), np.array(ns, float))
    if return_perpat:
        return rho_bar, ci_lo, ci_hi, n_used, n_dropped, rhos_by_pat, ns_by_pat
    return rho_bar, ci_lo, ci_hi, n_used, n_dropped


def best_pooling_for_tool(df, tool, *, patients=None, min_pep=MIN_PEP):
    """该工具 8 pooling 各算 per-patient Fisher-z, 返回 (best_pooling, best_rho, all: dict)。
    缺列/全 NaN 的 pooling 跳过。用于 R2 最优 pooling + R3/R5/R6 维度集取各工具最优 pooling 列。
    """
    out = {}
    for pl in POOLINGS:
        c = pool_col(tool, pl)
        if c not in df.columns or df[c].notna().sum() == 0:
            out[pl] = np.nan
            continue
        rho, *_ = per_patient_spearman(df, c, patients=patients, min_pep=min_pep)
        out[pl] = rho
    valid = {k: v for k, v in out.items() if v is not None and not np.isnan(v)}
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


def ensure_out_dir():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    return OUT_DIR


def r6(v, d=6):
    """安全 round (None/NaN -> np.nan)。"""
    if v is None:
        return np.nan
    try:
        fv = float(v)
    except (TypeError, ValueError):
        return np.nan
    return round(fv, d) if not np.isnan(fv) else np.nan
