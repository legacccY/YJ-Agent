#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
nested_lopo_ensemble.py
=======================
服务: QuantImmuBench G3 §3.3.3 表8 — Nested-LOPO (双层留一病人) 无泄漏严格性卖点
约束对齐: LEDGER §5 九约束 + 大纲 §3.3.3

为什么要双层 (相对 lopo_eval.py 单层)
------------------------------------
  lopo_eval.py = 单层 LOPO: 外层留一病人当 test, 但超参 θ (Ridge α / fusion 法)
  在全体患者上选 → θ 偷看了 test 病人 → 超参层面有泄漏风险 (optimistic bias)。
  Nested-LOPO 把超参选择关进内层:
    外层 (outer): 留一 DS2 病人 p 当 test, p 的数据完全隔离 (训练/选参都不碰)。
    内层 (inner): 在 "其余病人" 上再做一轮 LOPO 选 θ* (绝不含 p)。
    用 θ* 训 "其余病人" → 在 p 上评测 = lopo_test_rho (无泄漏的诚实估计)。
  oracle 对照: 用全数据 (含 p) 选一个全局 θ_oracle 的 "作弊" 上界。
  LOPO ρ̄ ≈ oracle ρ̄  ⇒ 超参选择没有过拟合 = 零泄漏证据 (大纲 §3.3.3 表8)。

超参空间 θ (内层选, fusion 法选择 × Ridge 正则强度)
---------------------------------------------------
  θ ∈ { fixavg }  ∪  { ridge@dof_target | dof_target ∈ DOF_GRID }
    - fixavg          : 零参数, 6 工具 z-score 等权平均 (LEDGER §3 命门定理)
    - ridge@dof_target: Ridge, 折内 alpha grid 选 eff_DOF≈dof_target (约束⑨ 2-3)
  即同时在 "用不用学习型融合 (fusion 法选择)" 与 "正则强度" 两个轴上选。
  注: gbdt 仅敏感性对照, 不入主选择 θ 空间 (与 lopo_eval 一致)。

无泄漏红线 (G2/G3 卖点的全部意义)
---------------------------------
  内层选 θ* 时, 训练折与评测折都只取 inner_pool = (全体患者 - 外层 test 病人 p),
  外层 test 病人 p 的任何行 (特征 / 标签 / 统计) 绝不参与内层。impute/标准化均折内做。

患者口径 (照 lopo_eval, 不擅改)
------------------------------
  - 主聚合只纳 DS2 9 患者 [101,102,104,105,106,107,108,109,110] (LEDGER 约束④)。
  - 外层 fold = DS2 患者 (逐个留一)。DS1 6 患者仅作训练池, 不当外层 test。
  - 训练池含 DS1+DS2 (照 lopo_eval: train = 全体 - held-out)。
  - 内层选择/外层评测指标只算 DS2 per-patient Spearman, Fisher-z 加权聚合。
  - n_i < min_pep (默认 4) 的患者 ρ_i=NaN 不进聚合 (约束④)。

复用 (不重造)
-------------
  从 lopo_eval.py import: spearman_np, fisherz_weighted_agg, find_ridge_alpha,
  impute_fold, FEATURE_SETS, DS1_PATIENTS, DS2_PATIENTS。

输出
----
  quantimmune/results/nested_lopo.csv
    每个外层 DS2 fold 一行:
      patient_id, dataset, n_pep, theta_selected, lopo_test_rho, oracle_rho
    末尾汇总行 (patient_id=SUMMARY):
      LOPO Fisher-z ρ̄ vs oracle Fisher-z ρ̄ + 一致性 (diff / 配对 Spearman) = 零过拟合证据
  quantimmune/results/nested_lopo.summary.json  (机读汇总 + θ_oracle + θ 空间)

跑法 (主线跑, 我不跑)
--------------------
  python quantimmune/nested_lopo_ensemble.py --features surv6 --target raw_sfc
  python quantimmune/nested_lopo_ensemble.py --features surv6 --target raw_sfc --shuffle --seed 42
"""

import sys
import json
import argparse
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

HERE = Path(__file__).resolve().parent
# 保证可 import 同目录的 lopo_eval (复用其读矩阵/分 fold/Spearman 逻辑, 不重造)
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from lopo_eval import (  # noqa: E402
    spearman_np,
    fisherz_weighted_agg,
    find_ridge_alpha,
    impute_fold,
    FEATURE_SETS,
    DS1_PATIENTS,
    DS2_PATIENTS,
    FISHER_CLIP,
)

DEFAULT_MATRIX = HERE / "model_matrix_v2.csv"  # E0 产出 183 行 (task 指定)
RESULTS_DIR = HERE / "results"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

# ── 超参空间 θ (内层选择) ──────────────────────────────────────────────────────
# DOF_GRID: eff_DOF 目标网格, 居中 LEDGER §5 约束⑨ 的 2-3 区间。
# TODO(researcher 确认): grid 取值为 coder 按约束⑨ 选的合理候选, 非官方源 — 如需
#   更细 (如 1.5~3.5) 或直接给 alpha grid, 请 researcher/planner 在 LEDGER 登记后改。
DOF_GRID = [2.0, 2.5, 3.0]


def build_theta_space():
    """θ 空间 = fusion 法选择 (fixavg vs ridge) × Ridge 正则强度 (dof_target grid)。"""
    thetas = [{"method": "fixavg", "dof_target": None, "name": "fixavg"}]
    for d in DOF_GRID:
        thetas.append({"method": "ridge", "dof_target": float(d),
                       "name": f"ridge@dof{d:g}"})
    return thetas


# ── 折内 fit + predict (faithful 复刻 lopo_eval 单折逻辑) ───────────────────────
def build_y_train(train_df: pd.DataFrame, target: str) -> np.ndarray:
    """训练目标向量 (行序与 train_df 一致)。
    patient_centered: 每患者内减均值 (LEDGER §5 约束⑦); 等价 lopo_eval 的逐患者中心化。
    """
    if target == "patient_centered":
        y = train_df["Elispot"].astype(float)
        means = train_df.groupby("Patient_ID")["Elispot"].transform("mean")
        return (y - means).values.astype(float)
    return train_df["Elispot"].values.astype(float)


def fit_predict(train_df: pd.DataFrame, test_df: pd.DataFrame, theta: dict,
                feature_cols: list, target: str) -> tuple:
    """折内填补 → 标准化 → 按 θ 拟合 → 预测 test。返回 (pred ndarray | None, info dict)。
    防泄漏: train_df 已排除所有不该见的患者; impute/标准化只用 train_df 统计。
    """
    train_f, test_f = impute_fold(train_df, test_df, feature_cols)
    X_train = train_f[feature_cols].values.astype(float)
    X_test = test_f[feature_cols].values.astype(float)
    y_train = build_y_train(train_f, target)

    valid = ~np.isnan(y_train)
    X_train, y_train = X_train[valid], y_train[valid]
    if len(X_train) == 0:
        return None, {}

    # 标准化 (基于训练折)
    X_mean = np.nanmean(X_train, axis=0)
    X_std = np.nanstd(X_train, axis=0)
    X_std[X_std < 1e-10] = 1.0
    Xtr = (X_train - X_mean) / X_std
    Xte = (X_test - X_mean) / X_std

    info = {}
    if theta["method"] == "fixavg":
        pred = np.nanmean(Xte, axis=1)  # 零参数等权平均
    elif theta["method"] == "ridge":
        alpha_best, dof = find_ridge_alpha(Xtr, target_dof=theta["dof_target"])
        m = Ridge(alpha=alpha_best, fit_intercept=True)
        m.fit(Xtr, y_train)
        pred = m.predict(Xte)
        info = {"alpha": float(alpha_best), "dof": float(dof)}
    else:
        raise ValueError(f"unknown theta method: {theta['method']}")
    return pred, info


# ── 一轮 LOPO over 指定患者集 → per-patient ρ ──────────────────────────────────
def lopo_perpatient(df: pd.DataFrame, patients: list, theta: dict,
                    feature_cols: list, target: str, min_pep: int) -> dict:
    """在患者集 `patients` 上跑一轮 LOPO (逐个留一, 训其余)。
    返回 {patient_id: (rho, n_pep, dataset)}。
    关键: 训练折严格 = patients 中除当前 held-out 外的患者 (调用方保证 patients 不含
    任何不该见的病人, 如外层 test 病人 p)。
    """
    sub = df[df["Patient_ID"].isin(patients)]
    out = {}
    for p in patients:
        test = sub[sub["Patient_ID"] == p]
        train = sub[sub["Patient_ID"] != p]
        ds = test["Dataset"].iloc[0] if len(test) else "?"
        n = len(test)
        if n < min_pep:
            out[p] = (np.nan, n, ds)
            continue
        pred, _ = fit_predict(train, test, theta, feature_cols, target)
        if pred is None:
            out[p] = (np.nan, n, ds)
            continue
        y = test["Elispot"].values.astype(float)
        out[p] = (spearman_np(pred, y), n, ds)
    return out


def agg_ds2(perpat: dict) -> float:
    """对 per-patient dict 取 DS2 患者的 Fisher-z 加权聚合 ρ̄ (主选择/评测指标)。"""
    rhos, ns = [], []
    for _, (rho, n, ds) in perpat.items():
        if ds == "DS2" and not np.isnan(rho):
            rhos.append(rho)
            ns.append(n)
    if not rhos:
        return np.nan
    rho_bar, _, _, _, _ = fisherz_weighted_agg(rhos, ns)
    return rho_bar


def fisherz_mean(rhos: list, ns: list) -> tuple:
    """Fisher-z 加权聚合 (薄封装, 返回 rho_bar, ci_lo, ci_hi, n_used)。"""
    if not rhos:
        return np.nan, np.nan, np.nan, 0
    rho_bar, lo, hi, n_used, _ = fisherz_weighted_agg(rhos, ns)
    return rho_bar, lo, hi, n_used


# ── 主函数 ────────────────────────────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser(
        description="QuantImmuBench Nested-LOPO (双层留一病人, 无泄漏严格性) §3.3.3 表8")
    ap.add_argument("--matrix", default=str(DEFAULT_MATRIX),
                    help="model_matrix_v2.csv 路径 (默认 v2, E0 产出)")
    ap.add_argument("--features",
                    choices=list(FEATURE_SETS.keys()),
                    default="surv6", help="特征集 (默认 surv6, 复用 lopo_eval 定义)")
    ap.add_argument("--target", choices=["raw_sfc", "patient_centered"],
                    default="raw_sfc", help="训练目标 (默认 raw_sfc)")
    ap.add_argument("--shuffle", action="store_true",
                    help="打乱 SFC 标签 (R0 防泄漏对照; 期望 LOPO≈oracle≈0)")
    ap.add_argument("--seed", type=int, default=42, help="随机种子 (默认 42)")
    ap.add_argument("--min_pep", type=int, default=4,
                    help="患者内最少肽数才算 rho (默认 4, LEDGER 约束④)")
    args = ap.parse_args()

    rng = np.random.default_rng(args.seed)

    # ── 读 model_matrix ────────────────────────────────────────────────────────
    matrix_path = Path(args.matrix)
    if not matrix_path.exists():
        sys.exit(f"[ERR] model_matrix 不存在: {matrix_path}")
    df = pd.read_csv(matrix_path, encoding="utf-8")
    print(f"[info] matrix: {matrix_path.name} {df.shape}, "
          f"患者数: {df['Patient_ID'].nunique()}")

    # ── 特征列解析 (复用 lopo_eval FEATURE_SETS) ──────────────────────────────
    desired = FEATURE_SETS[args.features]
    feature_cols = [c for c in desired if c in df.columns]
    missing = [c for c in desired if c not in df.columns]
    if missing:
        print(f"[warn] 特征列缺失已忽略: {missing}")
    if not feature_cols:
        sys.exit(f"[ERR] 特征集 '{args.features}' 无有效列")
    print(f"[info] 特征集 '{args.features}': {len(feature_cols)} 列 = {feature_cols}")

    # ── 标签打乱 (R0 防泄漏对照) ─────────────────────────────────────────────
    if args.shuffle:
        print(f"[shuffle] 打乱 Elispot (seed={args.seed}); 期望 LOPO≈oracle≈0")
        df = df.copy()
        df["Elispot"] = rng.permutation(df["Elispot"].values)

    all_patients = sorted(df["Patient_ID"].unique())
    # 外层 fold = 数据中实际存在的 DS2 患者 (照 lopo_eval 主聚合口径)
    ds2_outer = [p for p in all_patients if p in DS2_PATIENTS]
    print(f"[info] 全体患者 ({len(all_patients)}): {all_patients}")
    print(f"[info] 外层 DS2 fold ({len(ds2_outer)}): {ds2_outer}")

    thetas = build_theta_space()
    theta_names = [t["name"] for t in thetas]
    print(f"[info] θ 空间 ({len(thetas)}): {theta_names}")

    # ── ORACLE: 用全数据 (含 test) 选一个全局 θ_oracle 的作弊上界 ───────────────
    # 对每个 θ, 在全体患者上跑整轮 LOPO, 取 DS2 聚合 ρ̄; argmax = θ_oracle。
    # 各 θ 的 full-LOPO per-patient ρ 缓存, 供取 oracle_rho[p]。
    print(f"\n{'='*78}\n[ORACLE] 全数据选 θ (作弊上界, 含外层 test 病人)\n{'='*78}")
    oracle_perpat_by_theta = {}
    oracle_agg = {}
    for t in thetas:
        pp = lopo_perpatient(df, all_patients, t, feature_cols,
                             args.target, args.min_pep)
        oracle_perpat_by_theta[t["name"]] = pp
        oracle_agg[t["name"]] = agg_ds2(pp)
        print(f"  θ={t['name']:>14}  DS2 ρ̄={oracle_agg[t['name']]:+.4f}")
    # argmax (NaN 视为 -inf)
    theta_oracle = max(
        theta_names,
        key=lambda nm: (oracle_agg[nm] if not np.isnan(oracle_agg[nm]) else -np.inf))
    oracle_perpat = oracle_perpat_by_theta[theta_oracle]
    print(f"[ORACLE] θ_oracle = {theta_oracle}  "
          f"(DS2 ρ̄={oracle_agg[theta_oracle]:+.4f})")

    # ── NESTED OUTER: 逐个留一 DS2 病人, 内层在其余病人上选 θ* ──────────────────
    print(f"\n{'='*78}\n[NESTED] 外层留一 + 内层无泄漏选 θ\n{'='*78}")
    print(f"{'patient':>9} {'ds':>4} {'n':>4} {'theta*':>14} "
          f"{'lopo_rho':>9} {'oracle_rho':>10}")
    print(f"{'-'*78}")

    rows = []
    for p in ds2_outer:
        # 内层池 = 全体患者 - 外层 test 病人 p (绝不含 p; 含 DS1 训练池)
        inner_pool = [q for q in all_patients if q != p]

        # 内层: 对每个 θ 在 inner_pool 上跑 LOPO, 取 DS2 聚合, 选 θ*
        inner_agg = {}
        for t in thetas:
            pp = lopo_perpatient(df, inner_pool, t, feature_cols,
                                 args.target, args.min_pep)
            inner_agg[t["name"]] = agg_ds2(pp)
        theta_star_name = max(
            theta_names,
            key=lambda nm: (inner_agg[nm] if not np.isnan(inner_agg[nm])
                            else -np.inf))
        theta_star = next(t for t in thetas if t["name"] == theta_star_name)

        # 外层评测: 用 θ* 在 inner_pool 上训, 预测 p (p 首次也是唯一一次被用于评测)
        test = df[df["Patient_ID"] == p]
        train = df[df["Patient_ID"].isin(inner_pool)]
        ds = test["Dataset"].iloc[0] if len(test) else "?"
        n = len(test)
        if n < args.min_pep:
            lopo_rho = np.nan
        else:
            pred, _ = fit_predict(train, test, theta_star, feature_cols, args.target)
            lopo_rho = (spearman_np(pred, test["Elispot"].values.astype(float))
                        if pred is not None else np.nan)

        oracle_rho = oracle_perpat.get(p, (np.nan, n, ds))[0]

        rows.append(dict(
            patient_id=p, dataset=ds, n_pep=n,
            theta_selected=theta_star_name,
            lopo_test_rho=round(lopo_rho, 6) if not np.isnan(lopo_rho) else np.nan,
            oracle_rho=round(oracle_rho, 6) if not np.isnan(oracle_rho) else np.nan,
        ))
        lr = f"{lopo_rho:+.4f}" if not np.isnan(lopo_rho) else "   NaN"
        orr = f"{oracle_rho:+.4f}" if not np.isnan(oracle_rho) else "    NaN"
        print(f"{str(p):>9} {ds:>4} {n:>4} {theta_star_name:>14} {lr:>9} {orr:>10}")

    print(f"{'='*78}")

    # ── 汇总: LOPO ρ̄ vs oracle ρ̄ + 一致性 (零过拟合证据) ──────────────────────
    out_df = pd.DataFrame(rows)
    valid = out_df[out_df["dataset"] == "DS2"].copy()

    lopo_pairs = valid[["lopo_test_rho", "n_pep"]].dropna()
    orc_pairs = valid[["oracle_rho", "n_pep"]].dropna()

    lopo_bar, lopo_lo, lopo_hi, lopo_n = fisherz_mean(
        lopo_pairs["lopo_test_rho"].tolist(), lopo_pairs["n_pep"].tolist())
    orc_bar, orc_lo, orc_hi, orc_n = fisherz_mean(
        orc_pairs["oracle_rho"].tolist(), orc_pairs["n_pep"].tolist())

    diff = (lopo_bar - orc_bar) if not (np.isnan(lopo_bar) or np.isnan(orc_bar)) \
        else np.nan
    # 配对一致性: 同时有 lopo 与 oracle 的患者, 两列 per-patient ρ 的 Spearman
    paired = valid[["lopo_test_rho", "oracle_rho"]].dropna()
    pair_spearman = (spearman_np(paired["lopo_test_rho"].values,
                                 paired["oracle_rho"].values)
                     if len(paired) >= 2 else np.nan)
    mean_abs_dev = (float(np.mean(np.abs(
        paired["lopo_test_rho"].values - paired["oracle_rho"].values)))
        if len(paired) > 0 else np.nan)

    # 汇总行写入 CSV (patient_id=SUMMARY)
    summary_row = dict(
        patient_id="SUMMARY", dataset="DS2",
        n_pep=int(valid["n_pep"].sum()),
        theta_selected=f"oracle={theta_oracle}",
        lopo_test_rho=round(lopo_bar, 6) if not np.isnan(lopo_bar) else np.nan,
        oracle_rho=round(orc_bar, 6) if not np.isnan(orc_bar) else np.nan,
    )
    out_df_full = pd.concat([out_df, pd.DataFrame([summary_row])],
                            ignore_index=True)

    _suffix = "_shuffle" if args.shuffle else ""
    out_csv = RESULTS_DIR / f"nested_lopo{_suffix}.csv"
    out_df_full.to_csv(out_csv, index=False, encoding="utf-8")

    print(f"\n{'─'*64}")
    print(f"LOPO   (嵌套无泄漏) Fisher-z ρ̄ = {lopo_bar:+.4f}  "
          f"95%CI [{lopo_lo:+.4f}, {lopo_hi:+.4f}]  (n={lopo_n})")
    print(f"ORACLE (全数据作弊) Fisher-z ρ̄ = {orc_bar:+.4f}  "
          f"95%CI [{orc_lo:+.4f}, {orc_hi:+.4f}]  (n={orc_n})")
    print(f"一致性: Δ(LOPO-oracle) = {diff:+.4f}  |  配对 Spearman = "
          f"{pair_spearman:+.4f}  |  mean|Δ_perpatient| = {mean_abs_dev:.4f}")
    print(f"  → Δ≈0 且配对 Spearman≈1 ⇒ 超参选择零过拟合 (无泄漏证据, §3.3.3 表8)")
    print(f"[saved] {out_csv}")

    # ── summary JSON ───────────────────────────────────────────────────────────
    def _f(v):
        if v is None or (isinstance(v, float) and np.isnan(v)):
            return None
        return round(float(v), 6)

    summary = {
        "design": "nested-LOPO (outer leave-one-DS2-patient, inner LOPO θ-selection)",
        "leakage_guard": "inner θ-selection never touches outer test patient p",
        "features": args.features,
        "feature_cols": feature_cols,
        "target": args.target,
        "shuffled": args.shuffle,
        "seed": args.seed,
        "min_pep": args.min_pep,
        "theta_space": theta_names,
        "dof_grid": DOF_GRID,
        "theta_oracle": theta_oracle,
        "oracle_agg_by_theta": {k: _f(v) for k, v in oracle_agg.items()},
        "outer_folds": ds2_outer,
        "lopo_fisherz_rho": _f(lopo_bar),
        "lopo_ci_lo": _f(lopo_lo),
        "lopo_ci_hi": _f(lopo_hi),
        "lopo_n_used": lopo_n,
        "oracle_fisherz_rho": _f(orc_bar),
        "oracle_ci_lo": _f(orc_lo),
        "oracle_ci_hi": _f(orc_hi),
        "oracle_n_used": orc_n,
        "consistency_delta_lopo_minus_oracle": _f(diff),
        "consistency_paired_spearman": _f(pair_spearman),
        "consistency_mean_abs_dev": _f(mean_abs_dev),
        "theta_selected_per_fold": {
            str(r["patient_id"]): r["theta_selected"] for r in rows},
    }
    out_json = RESULTS_DIR / f"nested_lopo{_suffix}.summary.json"

    def _json_default(o):
        if isinstance(o, np.integer):
            return int(o)
        if isinstance(o, np.floating):
            return float(o)
        return str(o)

    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False, default=_json_default)
    print(f"[saved] {out_json}")
    print(f"\n[DONE] nested-LOPO 完成 → 填大纲 §3.3.3 表8 (LOPO vs oracle 一致性)")


if __name__ == "__main__":
    main()
