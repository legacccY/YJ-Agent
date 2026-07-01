#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
R5_official.py
==============
服务: QuantImmuBench 大纲 §3.3.3 (表8) —— Nested-LOPO 整合 vs 最强单工具 + shuffle null。
对应大纲: paper/QuanImmu-Paper-Outline.md §3.3.3 "Nested-LOPO 无泄漏整合 (表8)"。

★ 2026-07-01 Part D Phase 3 口径 (干净表 + 新评判标准, 见 04_LOG):
  输入 = 干净表 pooled_clean_9mer.csv (含突变去噪 + 51 pooling 变体 + peplen 列)。
  · [B5 零选择] 整合维度 SURV6 各工具用 <tool>_max (去 in-sample pooling selection);
    最强单工具亦在全覆盖池里用 <tool>_max 挑 per-patient ρ̄ 最高者 (零 pooling 选择)。
  · [B2] LOPO 整合分 + 最强单工具主指标各加控肽长版对照 (per_patient_partial_spearman,
    ctrl='peplen'), 隔离「肽长搭便车」伪迹。
  【旧 count-clean 注释已删】: 干净表不带 count_conf 列, 混杂改由 B2 偏相关在度量层控。

做什么:
  双层留一病人 (nested-LOPO): 外层留一 DS2 病人当 test (完全隔离), 内层在其余病人上再
  LOPO 选超参 θ* (fixavg / ridge@dof grid), 用 θ* 训其余病人评测留出病人 = 无泄漏诚实估计。
  oracle 对照 = 全数据 (含 test) 选全局 θ 的作弊上界。LOPO ρ̄ ≈ oracle ρ̄ ⇒ 超参选择零泄漏。
  另加: 整合 vs 最强单工具 (满数据 per-patient Fisher-z 最高单工具) + shuffle null (打乱
  标签, 期望 LOPO≈oracle≈0)。整合维度 = 6 维 SURV6 (各 R2 最优 pooling 列)。

  ⚠️ 冻结表纯 DS2 9 患者 (无 DS1 训练池), 故内层池=其余 8 患者 (旧骨架含 DS1 增强, 此处无)。

输入 (只读干净表):
  data/frozen/pooled_clean_9mer.csv
输出 (analysis/official/):
  R5_nested_lopo_official.csv          —— 每外层 DS2 fold 一行 + SUMMARY 行
  R5_nested_lopo_official.summary.json —— 机读汇总 (LOPO vs oracle + 最强单工具 + θ 空间)

复用旧骨架:
  · nested-LOPO 双层 + θ 空间 + oracle + 一致性 ← quantimmune/nested_lopo_ensemble.py 整套
  · spearman_np / fisherz / impute_fold / find_ridge_alpha → _official_common

★ selection 已裁决 (2026-07-01, 对齐 outline §2.2 9mer 主分析):
  · DS2 口径 = 130 肽 / 9 患者 (官方数据红线, Entry31 已拍)。
  · 整合维度 SURV6 成员 = 保持现状 (outline 抽象「6维」既有具体化, 朱同学传承, 同 R3)。
  · 全覆盖池门槛 FULL_COV = 保持 (outline §3.1 领先单工具皆全覆盖)。
  · 输入默认 = 9mer 主分析表 (FROZEN_POOLED 已指向 _9mer.csv); --input 可切全窗补充。
  · 仅 DTU consent 保留为外部 pending (法律授权, 非写作阻塞)。

跑法 (主线跑, 我不跑):
  python analysis/official/R5_official.py
  python analysis/official/R5_official.py --shuffle --seed 42   # R0 防泄漏对照
"""

import sys
import json
import argparse
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _official_common import (                              # noqa: E402
    load_frozen, present_patients, per_patient_spearman,
    per_patient_partial_spearman, pool_col, spearman_np, fisherz_weighted_agg,
    impute_fold, find_ridge_alpha,
    TOOLS_30, MIN_PEP, LABEL_COL, FROZEN_POOLED, ensure_out_dir,
)

# ── 整合维度 (★ TODO 待袁/朱确认成员, 同 R3 SURV6; [B5] 各工具用零选择 <tool>_max) ──
SURV6 = ["PredIG", "IMPROVE", "pTuneos", "PRIME", "ImmuneApp", "deepHLApan"]
DOF_GRID = [2.0, 2.5, 3.0]   # eff_DOF 目标网格 (旧 nested_lopo_ensemble.py 同口径)


def build_theta_space():
    thetas = [{"method": "fixavg", "dof_target": None, "name": "fixavg"}]
    for d in DOF_GRID:
        thetas.append({"method": "ridge", "dof_target": float(d),
                       "name": f"ridge@dof{d:g}"})
    return thetas


def fit_predict(train_df, test_df, theta, feature_cols, label_col):
    """折内填补→标准化→按 θ 拟合→预测 test。返回 pred ndarray | None。
    防泄漏: train_df 已排除不该见的病人; impute/标准化只用 train_df 统计。
    """
    train_f, test_f = impute_fold(train_df, test_df, feature_cols)
    X_train = train_f[feature_cols].values.astype(float)
    X_test = test_f[feature_cols].values.astype(float)
    y_train = train_f[label_col].values.astype(float)
    valid = ~np.isnan(y_train)
    X_train, y_train = X_train[valid], y_train[valid]
    if len(X_train) == 0:
        return None
    X_mean = np.nanmean(X_train, axis=0)
    X_std = np.nanstd(X_train, axis=0)
    X_std[X_std < 1e-10] = 1.0
    Xtr = (X_train - X_mean) / X_std
    Xte = (X_test - X_mean) / X_std
    if theta["method"] == "fixavg":
        return np.nanmean(Xte, axis=1)
    if theta["method"] == "ridge":
        alpha_best, _ = find_ridge_alpha(Xtr, target_dof=theta["dof_target"])
        m = Ridge(alpha=alpha_best, fit_intercept=True)
        m.fit(Xtr, y_train)
        return m.predict(Xte)
    raise ValueError(f"unknown theta method: {theta['method']}")


def lopo_perpatient(df, patients, theta, feature_cols, label_col, min_pep):
    """在 patients 上跑一轮 LOPO (逐个留一, 训其余)。返回 {pat: (rho, n)}。"""
    sub = df[df["Patient_ID"].isin(patients)]
    out = {}
    for p in patients:
        test = sub[sub["Patient_ID"] == p]
        train = sub[sub["Patient_ID"] != p]
        n = len(test)
        if n < min_pep:
            out[p] = (np.nan, n)
            continue
        pred = fit_predict(train, test, theta, feature_cols, label_col)
        if pred is None:
            out[p] = (np.nan, n)
            continue
        out[p] = (spearman_np(pred, test[label_col].values.astype(float)), n)
    return out


def agg(perpat):
    rhos, ns = [], []
    for _, (rho, n) in perpat.items():
        if not np.isnan(rho):
            rhos.append(rho)
            ns.append(n)
    if not rhos:
        return np.nan
    rb, _, _, _, _ = fisherz_weighted_agg(rhos, ns)
    return rb


def main():
    ap = argparse.ArgumentParser(
        description="R5 官方: Nested-LOPO 整合 vs 最强单工具 + shuffle null (§3.3.3 表8)")
    ap.add_argument("--input", default=str(FROZEN_POOLED), help="冻结肽级表路径")
    ap.add_argument("--shuffle", action="store_true",
                    help="打乱 Elispot (R0 防泄漏对照; 期望 LOPO≈oracle≈0)")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--min_pep", type=int, default=MIN_PEP)
    ap.add_argument("--ctrl", default="peplen", help="控制变量列 (B2 偏相关, 默认 peplen)")
    args = ap.parse_args()

    df = load_frozen(args.input)
    pats = present_patients(df)
    rng = np.random.default_rng(args.seed)
    if args.shuffle:
        print(f"[shuffle] 打乱 Elispot (seed={args.seed}); 期望 LOPO≈oracle≈0")
        df = df.copy()
        df[LABEL_COL] = rng.permutation(df[LABEL_COL].values)

    # 整合维度 = SURV6 各工具零选择 <tool>_max (B5)
    feature_cols, used = [], []
    for t in SURV6:
        col = pool_col(t, "max")
        if col not in df.columns or df[col].notna().sum() == 0:
            print(f"[warn] {t}: 列 {col} 缺失或全空, 剔除")
            continue
        feature_cols.append(col)
        used.append(col)
    print(f"[info] DS2 患者({len(pats)})={pats}; 整合维度(零选择 max)={used}")

    thetas = build_theta_space()
    theta_names = [t["name"] for t in thetas]

    # ── ORACLE: 全数据选 θ (作弊上界) ──────────────────────────────────────────
    oracle_pp_by_theta, oracle_agg = {}, {}
    for t in thetas:
        pp = lopo_perpatient(df, pats, t, feature_cols, LABEL_COL, args.min_pep)
        oracle_pp_by_theta[t["name"]] = pp
        oracle_agg[t["name"]] = agg(pp)
    theta_oracle = max(theta_names,
                       key=lambda nm: (oracle_agg[nm] if not np.isnan(oracle_agg[nm])
                                       else -np.inf))
    oracle_pp = oracle_pp_by_theta[theta_oracle]
    print(f"[ORACLE] θ_oracle={theta_oracle} (ρ̄={oracle_agg[theta_oracle]:+.4f})")

    # ── NESTED OUTER: 逐个留一 DS2 病人, 内层选 θ* ──────────────────────────────
    rows = []
    lopo_pred = pd.Series(np.nan, index=df.index, dtype=float)  # [B2] 收集外层 test 预测供控肽长
    for p in pats:
        inner_pool = [q for q in pats if q != p]
        inner_agg = {}
        for t in thetas:
            pp = lopo_perpatient(df, inner_pool, t, feature_cols, LABEL_COL, args.min_pep)
            inner_agg[t["name"]] = agg(pp)
        theta_star_name = max(theta_names,
                              key=lambda nm: (inner_agg[nm] if not np.isnan(inner_agg[nm])
                                              else -np.inf))
        theta_star = next(t for t in thetas if t["name"] == theta_star_name)

        test = df[df["Patient_ID"] == p]
        train = df[df["Patient_ID"].isin(inner_pool)]
        n = len(test)
        if n < args.min_pep:
            lopo_rho = np.nan
        else:
            pred = fit_predict(train, test, theta_star, feature_cols, LABEL_COL)
            lopo_rho = (spearman_np(pred, test[LABEL_COL].values.astype(float))
                        if pred is not None else np.nan)
            if pred is not None:
                lopo_pred.loc[test.index] = np.asarray(pred, dtype=float)
        oracle_rho = oracle_pp.get(p, (np.nan, n))[0]
        rows.append(dict(patient_id=p, n_pep=n, theta_selected=theta_star_name,
                         lopo_test_rho=round(lopo_rho, 6) if not np.isnan(lopo_rho) else np.nan,
                         oracle_rho=round(oracle_rho, 6) if not np.isnan(oracle_rho) else np.nan))
        lr = f"{lopo_rho:+.4f}" if not np.isnan(lopo_rho) else "NaN"
        orr = f"{oracle_rho:+.4f}" if not np.isnan(oracle_rho) else "NaN"
        print(f"  p{p} n={n} θ*={theta_star_name:>12} lopo={lr:>8} oracle={orr:>8}")

    out_df = pd.DataFrame(rows)
    lopo_pairs = out_df[["lopo_test_rho", "n_pep"]].dropna()
    orc_pairs = out_df[["oracle_rho", "n_pep"]].dropna()
    lopo_bar, lopo_lo, lopo_hi, lopo_n, _ = fisherz_weighted_agg(
        lopo_pairs["lopo_test_rho"].tolist(), lopo_pairs["n_pep"].tolist())
    orc_bar, orc_lo, orc_hi, orc_n, _ = fisherz_weighted_agg(
        orc_pairs["oracle_rho"].tolist(), orc_pairs["n_pep"].tolist())
    diff = (lopo_bar - orc_bar) if not (np.isnan(lopo_bar) or np.isnan(orc_bar)) else np.nan
    paired = out_df[["lopo_test_rho", "oracle_rho"]].dropna()
    pair_sp = (spearman_np(paired["lopo_test_rho"].values, paired["oracle_rho"].values)
               if len(paired) >= 2 else np.nan)
    mad = (float(np.mean(np.abs(paired["lopo_test_rho"].values
                                - paired["oracle_rho"].values)))
           if len(paired) > 0 else np.nan)

    # ── [B2] LOPO 整合分控肽长版对照 (对累积外层 test 预测算逐病人偏 Spearman(|peplen)) ──
    lopo_len_bar, lopo_len_lo, lopo_len_hi, _lnu, _ = per_patient_partial_spearman(
        df, lopo_pred.values, ctrl=args.ctrl, patients=pats, min_pep=args.min_pep)

    # ── 最强单工具 [B5 零选择 <tool>_max, 满数据 per-patient Fisher-z 最高单工具] ─────
    # 防稀疏虚高: 限全覆盖(130肽)工具池。Seq2Neo/netMHCstabpan(43肽)/NeoaPred(14肽) 等
    # 覆盖不全工具 per-patient 仅 2-3 肽算 spearman → 虚高假象(Seq2Neo ρ̄ 虚高 vs R1 max=-0.058)
    # ★ TODO: 全覆盖池=数据质量默认门槛, 待袁老师/朱同学确认 outline 表8 最强单工具是否纳入稀疏覆盖工具
    FULL_COV = [t for t in TOOLS_30
                if f"{t}_max" in df.columns and int(df[f"{t}_max"].notna().sum()) == len(df)]
    best_tool, best_tool_rho = None, -np.inf
    for t in FULL_COV:
        col = pool_col(t, "max")                          # 零选择 max, 不 in-sample 挑 pooling
        rho, *_ = per_patient_spearman(df, col, patients=pats, min_pep=args.min_pep)
        if not np.isnan(rho) and rho > best_tool_rho:
            best_tool, best_tool_rho = t, rho
    best_tool_pool = "max"
    # 最强单工具控肽长版对照
    best_tool_rho_len = np.nan
    if best_tool is not None:
        best_tool_rho_len, *_ = per_patient_partial_spearman(
            df, pool_col(best_tool, "max"), ctrl=args.ctrl, patients=pats, min_pep=args.min_pep)
    print(f"[single] 最强单工具={best_tool}_max ρ̄={best_tool_rho:+.4f} "
          f"(控肽长 ρ̄={best_tool_rho_len:+.4f}; 限全覆盖{len(FULL_COV)}工具池防虚高)")
    print(f"[integration] LOPO 控肽长版 ρ̄={lopo_len_bar:+.4f}")

    summary_row = dict(patient_id="SUMMARY", n_pep=int(out_df["n_pep"].sum()),
                       theta_selected=f"oracle={theta_oracle}",
                       lopo_test_rho=round(lopo_bar, 6) if not np.isnan(lopo_bar) else np.nan,
                       oracle_rho=round(orc_bar, 6) if not np.isnan(orc_bar) else np.nan)
    out_df_full = pd.concat([out_df, pd.DataFrame([summary_row])], ignore_index=True)

    out_dir = ensure_out_dir()
    suffix = "_shuffle" if args.shuffle else ""
    out_csv = out_dir / f"R5_nested_lopo_official{suffix}.csv"
    with open(out_csv, "w", encoding="utf-8") as f:
        f.write("# R5_nested_lopo_official.csv\n")
        f.write("# QuantImmuBench §3.3.3 表8: nested-LOPO 整合 vs oracle vs 最强单工具\n")
        f.write(f"# 输入={Path(args.input).name}; DS2 9 患者(无 DS1 训练池); 整合维度={used}\n")
        f.write("# 外层留一 DS2 病人, 内层 LOPO 选 θ*(fixavg/ridge@dof); oracle=全数据选 θ 作弊上界\n")
        f.write("# LOPO ρ̄≈oracle ρ̄ ⇒ 超参选择零过拟合(无泄漏证据); ★整合维度=TODO 待袁/朱确认\n")
        out_df_full.to_csv(f, index=False)
    print(f"\n[saved] {out_csv}")

    def _f(v):
        if v is None or (isinstance(v, float) and np.isnan(v)):
            return None
        return round(float(v), 6)

    summary = {
        "design": "nested-LOPO (outer leave-one-DS2, inner LOPO θ-selection)",
        "leakage_guard": "inner θ-selection never touches outer test patient",
        "input": str(Path(args.input).name),
        "integration_dims": used,
        "integration_dims_TODO": "成员=selection, 待袁/朱确认 outline 表8",
        "shuffled": args.shuffle, "seed": args.seed, "min_pep": args.min_pep,
        "theta_space": theta_names, "dof_grid": DOF_GRID,
        "theta_oracle": theta_oracle,
        "oracle_agg_by_theta": {k: _f(v) for k, v in oracle_agg.items()},
        "lopo_fisherz_rho": _f(lopo_bar), "lopo_ci_lo": _f(lopo_lo),
        "lopo_ci_hi": _f(lopo_hi), "lopo_n_used": lopo_n,
        "lopo_fisherz_rho_lenctrl": _f(lopo_len_bar),   # [B2] 控肽长版整合分
        "lenctrl_var": args.ctrl,
        "oracle_fisherz_rho": _f(orc_bar), "oracle_ci_lo": _f(orc_lo),
        "oracle_ci_hi": _f(orc_hi), "oracle_n_used": orc_n,
        "consistency_delta_lopo_minus_oracle": _f(diff),
        "consistency_paired_spearman": _f(pair_sp),
        "consistency_mean_abs_dev": _f(mad),
        "strongest_single_tool": f"{best_tool}_{best_tool_pool}" if best_tool else None,
        "strongest_single_rho": _f(best_tool_rho if best_tool else np.nan),
        "strongest_single_rho_lenctrl": _f(best_tool_rho_len if best_tool else np.nan),
        "integration_minus_single": _f(lopo_bar - best_tool_rho)
        if (best_tool and not np.isnan(lopo_bar)) else None,
        "theta_selected_per_fold": {str(r["patient_id"]): r["theta_selected"] for r in rows},
    }
    out_json = out_dir / f"R5_nested_lopo_official{suffix}.summary.json"

    def _jd(o):
        if isinstance(o, np.integer): return int(o)
        if isinstance(o, np.floating): return float(o)
        return str(o)

    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False, default=_jd)
    print(f"[saved] {out_json}")
    print(f"\nLOPO ρ̄={lopo_bar:+.4f}  oracle ρ̄={orc_bar:+.4f}  Δ={diff:+.4f}  "
          f"配对Spearman={pair_sp:+.4f}")
    print(f"整合 vs 最强单工具({best_tool}): {lopo_bar:+.4f} vs {best_tool_rho:+.4f}")
    print("[DONE] R5")


if __name__ == "__main__":
    main()
