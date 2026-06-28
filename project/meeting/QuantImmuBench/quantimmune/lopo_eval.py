#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
lopo_eval.py
============
服务: quantimmu-bench F-pilot — LOPO (Leave-One-Patient-Out) 评估引擎
约束对齐: LEDGER §5 九约束全程遵守

核心设计
--------
  - 15 折 patient-level LOPO (留 1 患者, 训其余 14 全部肽)
  - 防泄漏: 缺失值折内填补 (训练折均值, 禁全局统计), 标签打乱在 shuffle 前折外做
  - per-patient Spearman ρ_i (纯 numpy, 禁 scipy 防 OMP Error #15)
  - n_i < 4 的患者 ρ_i = NaN, 不进聚合 (LEDGER 约束④)
  - 主聚合只纳 DS2 9 患者; DS1 6 患者仅记录敏感性 (LEDGER 约束④)
  - Fisher-z 加权聚合 + 中位数 (复用 per_patient_spearman_multimethod.py 公式)
  - Ridge 有效 DOF: eff_DOF = sum(d^2 / (d^2 + alpha)), 折内 alpha grid 搜索使 eff_DOF≈2-3

模型
----
  ridge  — sklearn Ridge, 折内嵌套 alpha grid 选 eff_DOF≈2-3 (LEDGER §5 约束⑨)
  fixavg — 6 存活工具 z-score 后等权平均, 零参数 (LEDGER §3 命门定理)
  gbdt   — GradientBoosting max_depth<=2, 仅敏感性对照 (LEDGER §5 约束⑨)

特征集 (--features)
-------------------
  all9            — 9 工具全部 (含死工具, 敏感性)
  surv6           — 6 存活工具 (推荐, 默认)
  surv6+seq       — surv6 + Tier-1 序列特征 (H3 假设验证, LEDGER §2)
  redundant-pruned— surv6 减去 IMPROVE (IMPROVE-PRIME r=0.69, 留 PRIME, LEDGER §5 约束⑨)

目标 (--target)
---------------
  raw_sfc         — 原始 SFC 值 (默认)
  patient_centered— SFC 减去训练折该患者内均值 (防 ridge 用工具分当患者均值代理,
                     LEDGER §5 约束⑦). 评估 Spearman ρ 仍在原始 SFC 上 (rank 不变)

开关
----
  --shuffle        打乱 SFC 标签 (R0 防泄漏对照, 期望 ρ≈0; LEDGER §5 约束⑤)
  --seed INT       随机种子 (默认 42)
  --whitelist PATH 只用白名单肽 (R11 IEDB 过滤敏感性, LEDGER §5 约束⑥)
  --min_pep INT    患者内最少肽数才算 ρ (默认 4, LEDGER §5 约束④)

输入
----
  quantimmune/model_matrix.csv  (build_model_matrix.py 产出)

输出 (quantimmune/results/)
----
  lopo_{model}_{features}_{target}[_shuffle{seed}].per_patient.csv
    列: Patient_ID, Dataset, n_pep, rho, rho_z, in_main_analysis, note
  lopo_{model}_{features}_{target}[_shuffle{seed}].summary.json
    ds2_fisherz_rho, ci_lo/hi, median, effective_dof_*, ridge_weights_*, ...

跑法
----
  python quantimmune/lopo_eval.py --model ridge --features surv6 --target raw_sfc
  python quantimmune/lopo_eval.py --model fixavg --features surv6 --target raw_sfc
  python quantimmune/lopo_eval.py --model ridge --features surv6 --shuffle --seed 42
  python quantimmune/lopo_eval.py --model gbdt --features surv6 --target raw_sfc
"""

import sys
import json
import argparse
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge
from sklearn.ensemble import GradientBoostingRegressor

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
DEFAULT_MATRIX = HERE / "model_matrix.csv"
RESULTS_DIR = HERE / "results"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

# ── 患者集合 ──────────────────────────────────────────────────────────────────
DS1_PATIENTS = [1, 2, 3, 4, 5, 6]
DS2_PATIENTS = [101, 102, 104, 105, 106, 107, 108, 109, 110]
ALL_PATIENTS = DS1_PATIENTS + DS2_PATIENTS

# ── 特征集定义 (LEDGER §5 约束⑨ 预登记) ─────────────────────────────────────
# 死工具: DeepImmuno / NeoTImmuML / HLAthena (fisherz ≤ 0.03)
# 冗余剪枝: IMPROVE-PRIME r=0.69, 留 PRIME
_ALL9_TOOLS = [
    "MT_DeepImmuno", "MT_PredIG", "MT_IMPROVE_mean_prediction_rf",
    "MT_NeoTImmuML", "MT_pTuneos", "MT_PRIME",
    "MT_ImmuneApp", "MT_deepHLApan", "MT_HLAthena",
]
_SURV6_TOOLS = [
    "MT_PredIG", "MT_IMPROVE_mean_prediction_rf", "MT_pTuneos",
    "MT_PRIME", "MT_ImmuneApp", "MT_deepHLApan",
]
_REDPRUNED_TOOLS = [
    "MT_PredIG", "MT_pTuneos", "MT_PRIME",
    "MT_ImmuneApp", "MT_deepHLApan",
]  # surv6 - IMPROVE (IMPROVE-PRIME 冗余簇, 留 PRIME)
_SEQ_FEATURES = [
    "seq_length", "seq_n_mutations", "seq_blosum62_mut_score",
    "seq_mutation_rel_pos", "seq_kd_hydro_mt", "seq_kd_hydro_diff",
    "seq_aromatic_mt",
]  # seq_foreignness 全 NaN 不入模

FEATURE_SETS = {
    "all9":             _ALL9_TOOLS,
    "surv6":            _SURV6_TOOLS,
    "surv6+seq":        _SURV6_TOOLS + _SEQ_FEATURES,
    "redundant-pruned": _REDPRUNED_TOOLS,
}

FISHER_CLIP = 0.9999
FISHER_MIN_N = 3  # n<=3 → Var(z) 分母 <=0, 不进 Fisher-z 加权


# ── 纯 numpy Spearman (禁 scipy 防 OMP Error #15) ────────────────────────────
def spearman_np(x, y):
    """纯 numpy Spearman rank correlation. 返回 NaN 若样本不足。"""
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


# ── Fisher-z 加权聚合 (复用 per_patient_spearman_multimethod.py 公式) ─────────
def fisherz_weighted_agg(rhos, ns):
    """
    Fisher-z 固定效应加权均值 + 95% CI.
    Spearman 专用方差: Var(z_i) = (1 + rho_i^2/2) / (n_i - 3)
    [Fieller-Hartley-Pearson 1957, Biometrika 44:470]
    n_i <= FISHER_MIN_N 剔出。
    返回 (rho_bar, ci_lo, ci_hi, n_used, n_dropped)
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


# ── Ridge 有效自由度 ──────────────────────────────────────────────────────────
def effective_dof(X: np.ndarray, alpha: float) -> float:
    """eff_DOF = sum(d^2 / (d^2 + alpha)), d = singular values of X.
    用 SVD 计算, 避免构造 n×n 矩阵。
    """
    _, s, _ = np.linalg.svd(X, full_matrices=False)
    return float(np.sum(s ** 2 / (s ** 2 + alpha)))


def find_ridge_alpha(X: np.ndarray, target_dof: float = 2.5,
                     n_grid: int = 200) -> tuple:
    """在 logspace 网格上搜索使 eff_DOF 最接近 target_dof 的 alpha。
    返回 (alpha_best, dof_achieved)。
    """
    # 根据 X 的尺度估算搜索范围
    _, s, _ = np.linalg.svd(X, full_matrices=False)
    s_sq_max = float(s[0] ** 2) if len(s) > 0 else 1.0
    # alpha 范围: 1e-3 * s_sq_max 到 1e7 * s_sq_max
    alpha_grid = np.logspace(
        np.log10(max(s_sq_max * 1e-3, 1e-4)),
        np.log10(s_sq_max * 1e7 + 1.0),
        n_grid,
    )
    dofs = np.array([effective_dof(X, a) for a in alpha_grid])
    idx = int(np.argmin(np.abs(dofs - target_dof)))
    return float(alpha_grid[idx]), float(dofs[idx])


# ── 折内缺失值填补 (防泄漏) ────────────────────────────────────────────────────
def impute_fold(train_df: pd.DataFrame, test_df: pd.DataFrame,
                feature_cols: list) -> tuple:
    """
    折内填补策略: 训练折各特征列均值 → 填入训练和测试折缺失值。
    防泄漏: 严格不用含 held-out 患者的统计 (train_df 已排除 held-out 患者)。
    返回 (train_filled, test_filled) — 不修改原 DataFrame。
    """
    train_f = train_df.copy()
    test_f = test_df.copy()
    for col in feature_cols:
        if col not in train_f.columns:
            continue
        col_mean = train_f[col].mean()  # 训练折均值 (不含 held-out)
        if np.isnan(col_mean):
            col_mean = 0.0  # 全 NaN 兜底填 0
        train_f[col] = train_f[col].fillna(col_mean)
        if col in test_f.columns:
            test_f[col] = test_f[col].fillna(col_mean)
    return train_f, test_f


# ── 主函数 ────────────────────────────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser(
        description="F-pilot LOPO 评估引擎 (quantimmu-bench)")
    ap.add_argument("--matrix", default=str(DEFAULT_MATRIX),
                    help="model_matrix.csv 路径")
    ap.add_argument("--model", choices=["ridge", "fixavg", "gbdt"],
                    default="ridge", help="模型类型 (默认 ridge)")
    ap.add_argument("--features",
                    choices=["all9", "surv6", "surv6+seq", "redundant-pruned"],
                    default="surv6", help="特征集 (默认 surv6)")
    ap.add_argument("--target", choices=["raw_sfc", "patient_centered"],
                    default="raw_sfc", help="训练目标 (默认 raw_sfc)")
    ap.add_argument("--shuffle", action="store_true",
                    help="打乱 SFC 标签 (R0 防泄漏对照; 期望 rho≈0)")
    ap.add_argument("--seed", type=int, default=42, help="随机种子 (默认 42)")
    ap.add_argument("--min_pep", type=int, default=4,
                    help="患者内最少肽数才算 rho (默认 4, LEDGER 约束④)")
    ap.add_argument("--whitelist", default=None,
                    help="IEDB 白名单 CSV (只用白名单肽, R11 敏感性)")
    ap.add_argument("--dof_target", type=float, default=2.5,
                    help="Ridge 目标有效 DOF (默认 2.5, 对应约束⑨ 2-3)")
    args = ap.parse_args()

    rng = np.random.default_rng(args.seed)

    # ── 读 model_matrix ────────────────────────────────────────────────────────
    matrix_path = Path(args.matrix)
    if not matrix_path.exists():
        sys.exit(f"[ERR] model_matrix.csv 不存在: {matrix_path}\n"
                 f"      请先运行: python quantimmune/build_model_matrix.py")

    df = pd.read_csv(matrix_path, encoding="utf-8")
    print(f"[info] model_matrix: {df.shape}, 患者数: {df['Patient_ID'].nunique()}")

    # ── 白名单过滤 (R11) ───────────────────────────────────────────────────────
    if args.whitelist:
        wl_path = Path(args.whitelist)
        if not wl_path.exists():
            sys.exit(f"[ERR] 白名单文件不存在: {wl_path}")
        wl = pd.read_csv(wl_path, encoding="utf-8")
        # 白名单列名: 'peptide' (MT_Subpeptide/MT_FullPeptide 序列)
        # 与 Peptide_ID 不直接对应; 通过 MT_FullPeptide 匹配
        wl_peps = set(wl["peptide"].str.upper().dropna())
        if "MT_FullPeptide" in df.columns:
            before = len(df)
            df = df[df["MT_FullPeptide"].str.upper().isin(wl_peps)].copy()
            print(f"[info] 白名单过滤: {before} → {len(df)} 肽")
        else:
            print("[warn] 白名单过滤: model_matrix 无 MT_FullPeptide 列, 跳过")

    # ── 特征列解析 ────────────────────────────────────────────────────────────
    desired_feats = FEATURE_SETS[args.features]
    # 只用 matrix 中实际存在的特征列
    feature_cols = [c for c in desired_feats if c in df.columns]
    missing_feats = [c for c in desired_feats if c not in df.columns]
    if missing_feats:
        print(f"[warn] 以下特征列在 matrix 中不存在, 已忽略: {missing_feats}")
    if not feature_cols:
        sys.exit(f"[ERR] 特征集 '{args.features}' 无任何有效列, 检查 model_matrix.csv")
    print(f"[info] 特征集 '{args.features}': {len(feature_cols)} 列 = {feature_cols}")

    # ── 标签打乱 (R0 防泄漏对照) ─────────────────────────────────────────────
    if args.shuffle:
        print(f"[shuffle] 打乱 SFC 标签 (seed={args.seed}), 期望 rho≈0 → 管道干净")
        df = df.copy()
        df["Elispot"] = rng.permutation(df["Elispot"].values)

    # ── 患者列表 ──────────────────────────────────────────────────────────────
    patients_in_data = sorted(df["Patient_ID"].unique())
    print(f"[info] 患者 ({len(patients_in_data)}): {patients_in_data}")

    # ── LOPO 主循环 ───────────────────────────────────────────────────────────
    per_patient_rows = []
    fold_dofs = []
    fold_alphas = []
    fold_weights = []  # 每折 Ridge 权重 (最后一折存入 summary)

    print(f"\n{'='*80}")
    print(f"model={args.model}  features={args.features}  target={args.target}  "
          f"shuffle={args.shuffle}  seed={args.seed}")
    print(f"{'='*80}")
    print(f"{'Patient':>10} {'Dataset':>8} {'n_pep':>6} {'rho':>8} {'main':>6}  note")
    print(f"{'-'*80}")

    for pat in patients_in_data:
        test_mask = (df["Patient_ID"] == pat)
        train_df_raw = df[~test_mask].copy()
        test_df_raw  = df[test_mask].copy()

        n_test = len(test_df_raw)
        dataset = test_df_raw["Dataset"].iloc[0] if n_test > 0 else "?"

        # DS 判定
        is_ds2 = (dataset == "DS2")

        # 少于 min_pep 肽 → 不算 rho
        if n_test < args.min_pep:
            note = f"n_pep={n_test}<{args.min_pep}, rho=NaN"
            row = dict(Patient_ID=pat, Dataset=dataset, n_pep=n_test,
                       rho=np.nan, rho_z=np.nan,
                       in_main_analysis=False, note=note)
            per_patient_rows.append(row)
            print(f"{str(pat):>10} {dataset:>8} {n_test:>6}  {'NaN':>8} {'  N':>6}  {note}")
            continue

        # ── 折内缺失值填补 (防泄漏, LEDGER 约束⑤) ────────────────────────────
        train_df, test_df = impute_fold(train_df_raw, test_df_raw, feature_cols)

        # ── 构造特征矩阵和目标向量 ─────────────────────────────────────────────
        X_train = train_df[feature_cols].values.astype(float)
        X_test  = test_df[feature_cols].values.astype(float)
        y_eval  = test_df["Elispot"].values.astype(float)  # 评估总用原始 SFC

        # 训练目标: raw_sfc 或 patient_centered
        if args.target == "patient_centered":
            # 对训练折中每个患者内中心化 (LEDGER §5 约束⑦)
            y_train_list = []
            for p2, g in train_df.groupby("Patient_ID"):
                centered = g["Elispot"].values.astype(float)
                pat_mean = np.nanmean(centered)
                y_train_list.append(centered - pat_mean)
            y_train = np.concatenate(y_train_list) if y_train_list else \
                      train_df["Elispot"].values.astype(float)
            # 重排为与 X_train 对应顺序
            train_order = train_df.index.tolist()
            y_train_ordered = np.empty(len(train_df))
            idx = 0
            for p2, g in train_df.groupby("Patient_ID"):
                pat_indices = g.index.tolist()
                pat_mean = np.nanmean(g["Elispot"].values.astype(float))
                for orig_idx in pat_indices:
                    pos = train_order.index(orig_idx)
                    y_train_ordered[pos] = g.loc[orig_idx, "Elispot"] - pat_mean
            y_train = y_train_ordered
        else:
            y_train = train_df["Elispot"].values.astype(float)

        # NaN 处理: 丢弃训练行中目标为 NaN 的样本
        valid_train = ~np.isnan(y_train)
        X_train = X_train[valid_train]
        y_train = y_train[valid_train]
        if len(X_train) == 0:
            note = "训练集目标全 NaN, 跳过"
            per_patient_rows.append(dict(Patient_ID=pat, Dataset=dataset, n_pep=n_test,
                                         rho=np.nan, rho_z=np.nan,
                                         in_main_analysis=False, note=note))
            print(f"{str(pat):>10} {dataset:>8} {n_test:>6}  {'NaN':>8} {'  N':>6}  {note}")
            continue

        # ── 标准化 (基于训练折) ────────────────────────────────────────────────
        X_mean = np.nanmean(X_train, axis=0)
        X_std  = np.nanstd(X_train, axis=0)
        X_std[X_std < 1e-10] = 1.0  # 防零除
        X_train_s = (X_train - X_mean) / X_std
        X_test_s  = (X_test  - X_mean) / X_std

        # ── 模型拟合 + 预测 ────────────────────────────────────────────────────
        pred = None
        dof = np.nan
        alpha_used = np.nan
        weights = {}

        if args.model == "ridge":
            alpha_best, dof_achieved = find_ridge_alpha(
                X_train_s, target_dof=args.dof_target)
            model = Ridge(alpha=alpha_best, fit_intercept=True)
            model.fit(X_train_s, y_train)
            pred = model.predict(X_test_s)
            dof = dof_achieved
            alpha_used = alpha_best
            weights = {fc: float(c) for fc, c in zip(feature_cols, model.coef_)}
            fold_dofs.append(dof)
            fold_alphas.append(alpha_used)
            fold_weights.append(weights)

        elif args.model == "fixavg":
            # 零参数: z-score 后等权平均 (LEDGER §3 命门定理推荐)
            pred = np.nanmean(X_test_s, axis=1)
            dof = 0.0
            weights = {fc: 1.0 / len(feature_cols) for fc in feature_cols}
            fold_dofs.append(0.0)

        elif args.model == "gbdt":
            # 仅敏感性: max_depth<=2 (LEDGER §5 约束⑨)
            gbdt = GradientBoostingRegressor(
                max_depth=2, n_estimators=100, random_state=args.seed,
                subsample=0.8)
            gbdt.fit(X_train_s, y_train)
            pred = gbdt.predict(X_test_s)
            dof = np.nan
            weights = {fc: float(imp)
                       for fc, imp in zip(feature_cols, gbdt.feature_importances_)}
            fold_weights.append(weights)

        # ── per-patient Spearman ρ ─────────────────────────────────────────────
        # 评估始终用原始 SFC (Spearman rank 不受中心化影响)
        rho_i = spearman_np(pred, y_eval)
        rho_z = float(np.arctanh(np.clip(rho_i, -FISHER_CLIP, FISHER_CLIP))) \
                if not np.isnan(rho_i) else np.nan

        # DS1 折记录但不进主聚合 (LEDGER §5 约束④)
        in_main = is_ds2 and not np.isnan(rho_i) and (n_test >= args.min_pep)
        note = "" if is_ds2 else "DS1: sensitivity only"
        if np.isnan(rho_i):
            note += " rho=NaN (signal issue)"

        row = dict(Patient_ID=pat, Dataset=dataset, n_pep=n_test,
                   rho=round(rho_i, 6) if not np.isnan(rho_i) else np.nan,
                   rho_z=round(rho_z, 6) if not np.isnan(rho_z) else np.nan,
                   in_main_analysis=in_main, note=note.strip())
        per_patient_rows.append(row)

        main_flag = "  Y" if in_main else "  N"
        rho_str = f"{rho_i:+.4f}" if not np.isnan(rho_i) else "   NaN"
        dof_str = f"dof={dof:.1f}" if not np.isnan(dof) else ""
        print(f"{str(pat):>10} {dataset:>8} {n_test:>6} {rho_str:>8} {main_flag:>6}  "
              f"{dof_str}")

    print(f"{'='*80}")

    # ── 汇总: DS2 主聚合 ───────────────────────────────────────────────────────
    ppr_df = pd.DataFrame(per_patient_rows)

    ds2_main = ppr_df[ppr_df["in_main_analysis"] == True]
    ds2_rhos = ds2_main["rho"].values.astype(float)
    ds2_ns   = ds2_main["n_pep"].values.astype(float)

    if len(ds2_rhos) == 0:
        print("[warn] 无有效 DS2 患者 ρ, 无法聚合")
        fz_rho = fz_ci_lo = fz_ci_hi = np.nan
        fz_n_used = fz_n_dropped = 0
        median_rho = np.nan
    else:
        fz_rho, fz_ci_lo, fz_ci_hi, fz_n_used, fz_n_dropped = \
            fisherz_weighted_agg(ds2_rhos, ds2_ns)
        median_rho = float(np.nanmedian(ds2_rhos))

    # DS1 敏感性聚合 (仅参考)
    ds1_rows = ppr_df[ppr_df["Dataset"] == "DS1"]
    ds1_rhos = ds1_rows["rho"].dropna().values.astype(float)
    ds1_ns   = ds1_rows.loc[ds1_rows["rho"].notna(), "n_pep"].values.astype(float)
    if len(ds1_rhos) > 0:
        ds1_fz, ds1_fz_lo, ds1_fz_hi, _, _ = fisherz_weighted_agg(ds1_rhos, ds1_ns)
        ds1_median = float(np.nanmedian(ds1_rhos))
    else:
        ds1_fz = ds1_fz_lo = ds1_fz_hi = ds1_median = np.nan

    print(f"\n{'─'*60}")
    print(f"DS2 主结论 (n={fz_n_used} 患者纳聚合, {fz_n_dropped} 剔出):")
    print(f"  Fisher-z ρ̄ = {fz_rho:+.4f}  95%CI [{fz_ci_lo:+.4f}, {fz_ci_hi:+.4f}]")
    print(f"  中位数 ρ   = {median_rho:+.4f}")
    if fold_dofs:
        print(f"  有效 DOF   = {np.mean(fold_dofs):.2f} ± {np.std(fold_dofs):.2f} (均值±SD, {len(fold_dofs)} 折)")
    print(f"DS1 敏感性 (非主结论): Fisher-z ρ̄ = {ds1_fz:+.4f} "
          f"CI [{ds1_fz_lo:+.4f},{ds1_fz_hi:+.4f}]  median={ds1_median:+.4f}")

    # Ridge 权重检查: 是否塌单工具 (H2 验证)
    if fold_weights and args.model == "ridge":
        last_w = fold_weights[-1]
        w_arr = np.array(list(last_w.values()))
        w_abs = np.abs(w_arr)
        if w_abs.sum() > 0:
            top_frac = w_abs.max() / w_abs.sum()
            print(f"  Ridge 权重最大占比 (最后折): {top_frac:.2%} "
                  f"({'⚠️ 疑似塌单工具' if top_frac > 0.8 else 'OK'})")
        print(f"  Ridge 权重 (最后折): "
              + ", ".join(f"{k.replace('MT_','')}: {v:+.3f}" for k, v in last_w.items()))

    # ── 写出 per-patient CSV ───────────────────────────────────────────────────
    tag = f"lopo_{args.model}_{args.features.replace('+','_')}_{args.target}"
    if args.shuffle:
        tag += f"_shuffle{args.seed}"

    out_csv = RESULTS_DIR / f"{tag}.per_patient.csv"
    ppr_df.to_csv(out_csv, index=False, encoding="utf-8")
    print(f"\n[saved] {out_csv}")

    # ── 写出 summary JSON ─────────────────────────────────────────────────────
    def _f(v):
        """float or None for JSON serialization."""
        if v is None or (isinstance(v, float) and np.isnan(v)):
            return None
        return round(float(v), 6)

    summary = {
        "model": args.model,
        "features": args.features,
        "target": args.target,
        "shuffled": args.shuffle,
        "seed": args.seed,
        "min_pep": args.min_pep,
        "dof_target": args.dof_target,
        "n_patients_total": len(patients_in_data),
        "ds2_fisherz_rho":    _f(fz_rho),
        "ds2_fisherz_ci_lo":  _f(fz_ci_lo),
        "ds2_fisherz_ci_hi":  _f(fz_ci_hi),
        "ds2_fisherz_n_used": fz_n_used,
        "ds2_fisherz_n_dropped": fz_n_dropped,
        "ds2_median_rho":     _f(median_rho),
        "ds1_fisherz_rho":    _f(ds1_fz),
        "ds1_fisherz_ci_lo":  _f(ds1_fz_lo),
        "ds1_fisherz_ci_hi":  _f(ds1_fz_hi),
        "ds1_median_rho":     _f(ds1_median),
        "effective_dof_mean": _f(float(np.mean(fold_dofs))) if fold_dofs else None,
        "effective_dof_std":  _f(float(np.std(fold_dofs))) if fold_dofs else None,
        "effective_dof_per_fold": [_f(d) for d in fold_dofs] if fold_dofs else [],
        "ridge_alpha_per_fold":   [_f(a) for a in fold_alphas] if fold_alphas else [],
        "ridge_weights_last_fold": (
            {k: _f(v) for k, v in fold_weights[-1].items()}
            if fold_weights else {}
        ),
        "feature_cols": feature_cols,
    }

    out_json = RESULTS_DIR / f"{tag}.summary.json"
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)
    print(f"[saved] {out_json}")
    print(f"\n[DONE] 下一步: python quantimmune/paired_bootstrap.py "
          f"--meta results/{tag}.per_patient.csv --baseline results/lopo_fixavg_surv6_raw_sfc.per_patient.csv")


if __name__ == "__main__":
    main()
