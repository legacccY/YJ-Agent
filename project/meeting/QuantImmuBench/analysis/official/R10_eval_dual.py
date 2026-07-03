#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
R10_eval_dual.py
================
服务: QuantImmuBench §3.3 集成框架 / C2 融合负检验 (预期 NULL)。
对应冻结判据: PREREG_R10_featfusion.md §2/§3/§4/§6 (confirmatory / 归因闸 / 双指标 / 功效)。

做什么 (读 R10_leak_free_lopo.py 的 OOF, 出双指标评测):
  ① 主指标 = per-patient Fisher-z Spearman(OOF 分, Elispot SFC 连续), 等权聚合。与 R1-R9 同源
     → 与最强单 netMHCpan_BA_max / geomean 旧基线严格可比。逐 (层×模型×标签) 报 raw + 控肽长 ρ̄
     + cluster-bootstrap over patients 95%CI + 配对检验 (paired_patient_test) vs 最强单(raw &
     ctrl='peplen') + vs geomean。
  ② 副指标 = 130 肽级 AUPRC(vs 二元标签), cluster bootstrap over patients **BCa** CI + 配对
     ΔAUPRC vs 最强单。★ 独立 estimand, 仅 exploratory 附注, 绝不当 headline (PREREG §4)。
  ③ shuffle 对照 = 读 R10_featfusion_oof_shuffle.csv (若在), 验 per-patient ρ̄≈0 / AUPRC 塌
     prevalence。任一层 shuffle 仍显著 → 全线作废 (泄漏)。
  ④ 功效前置 = 配对检验有效 K + MDE (最小可达 p=2/2^K)。K=9→0.0039; K=5→0.0625(够不到 0.05)。
  ⑤ 归因闸 (PREREG §3) = confirmatory「赢」须 L1 logistic ρ̄ > max(单工具, covariate-only)。
  ⑥ confirmatory (PREREG §2) = L1 logistic(标签 pval<0.05) 控肽长 paired vs 最强单; 其余
     exploratory 走 Holm 校正。

━━━ 输入 (只读) ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  R10_featfusion_oof.csv (+ _shuffle 版, 若在)   ← R10_leak_free_lopo.py
  data/frozen/pooled_clean_9mer.csv              (Elispot / peplen / netMHCpan_BA_max / SURV6 max)
  data/OFFICIAL...MOESM4.xlsx 'In Vitro'          (二元标签, AUPRC 用; 复用 lopo 的 load 逻辑)

━━━ 输出 (analysis/official/) ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  R10_featfusion_eval_main.csv     —— 逐(层×模型×标签) 主指标 ρ̄/CI + 配对检验。
  R10_featfusion_eval_auprc.csv    —— 逐(层×模型×标签) AUPRC BCa CI + 配对 ΔAUPRC (exploratory)。
  R10_featfusion_eval_summary.json —— confirmatory 结论 + 归因闸 + 有效K/MDE + shuffle + Holm。

━━━ 跑法 (主线跑, 我不跑) ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  python analysis/official/R10_leak_free_lopo.py           # 先产正常 OOF
  python analysis/official/R10_leak_free_lopo.py --shuffle  # 再产 shuffle OOF
  python analysis/official/R10_eval_dual.py                 # 本脚本评测

Windows 规范: UTF-8 stdout, pathlib, 纯 numpy/pandas + sklearn.metrics; 纯 numpy Spearman/置换(禁 scipy.stats)。
"""

import sys
import json
import math
import argparse
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _official_common import (                              # noqa: E402
    load_frozen, present_patients, per_patient_spearman,
    per_patient_partial_spearman, paired_patient_test, bootstrap_patient_ci,
    apply_fusion, pool_col, FROZEN_POOLED, MIN_PEP, r6, ensure_out_dir,
)
from R10_leak_free_lopo import load_binary_labels           # noqa: E402  复用标签口径

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

HERE = Path(__file__).resolve().parent
OOF_CSV = HERE / "R10_featfusion_oof.csv"
OOF_SHUFFLE_CSV = HERE / "R10_featfusion_oof_shuffle.csv"

STRONGEST_SINGLE = "netMHCpan_BA_max"       # PREREG §0/§2 固定最强单工具
SURV6 = ["PredIG", "IMPROVE", "pTuneos", "PRIME", "ImmuneApp", "deepHLApan"]
GEOMEAN_DIMS = [f"{t}_max" for t in SURV6]   # geomean 旧基线 = SURV6 max 病人内 geomean 融合
CTRL = "peplen"
N_BOOT_AUPRC = 2000
SEED = 42


# ═══════════════════════════════════════════════════════════════════════════════
# 正态 CDF / 逆 CDF (纯 numpy, BCa 用; 禁 scipy.stats)
# ═══════════════════════════════════════════════════════════════════════════════
def _norm_cdf(x):
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _norm_ppf(p):
    """标准正态逆 CDF (Acklam 有理逼近, 精度足够 BCa)。p∈(0,1)。"""
    if p <= 0.0:
        return -np.inf
    if p >= 1.0:
        return np.inf
    a = [-3.969683028665376e+01, 2.209460984245205e+02, -2.759285104469687e+02,
         1.383577518672690e+02, -3.066479806614716e+01, 2.506628277459239e+00]
    b = [-5.447609879822406e+01, 1.615858368580409e+02, -1.556989798598866e+02,
         6.680131188771972e+01, -1.328068155288572e+01]
    c = [-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e+00,
         -2.549732539343734e+00, 4.374664141464968e+00, 2.938163982698783e+00]
    d = [7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e+00,
         3.754408661907416e+00]
    plow, phigh = 0.02425, 1 - 0.02425
    if p < plow:
        q = math.sqrt(-2 * math.log(p))
        return (((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5]) / \
               ((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1)
    if p > phigh:
        q = math.sqrt(-2 * math.log(1 - p))
        return -(((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5]) / \
                ((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1)
    q = p - 0.5
    r = q * q
    return (((((a[0]*r+a[1])*r+a[2])*r+a[3])*r+a[4])*r+a[5])*q / \
           (((((b[0]*r+b[1])*r+b[2])*r+b[3])*r+b[4])*r+1)


# ═══════════════════════════════════════════════════════════════════════════════
# 肽级 AUPRC + cluster bootstrap over patients BCa CI
# ═══════════════════════════════════════════════════════════════════════════════
def _auprc(y, s):
    from sklearn.metrics import average_precision_score
    m = ~(np.isnan(y) | np.isnan(s))
    y, s = y[m], s[m]
    if len(np.unique(y)) < 2:
        return np.nan
    return float(average_precision_score(y, s))


def auprc_bca(df, score, y, patients, *, n_boot=N_BOOT_AUPRC, seed=SEED):
    """肽级 AUPRC + cluster-bootstrap over patients 的 BCa 95%CI (病人结构 correct)。
    resample 病人(有放回) 汇其肽 → AUPRC; jackknife 留一病人 → 加速度 a; z0 从 boot<point 比例。
    返回 (point, ci_lo, ci_hi, n_pos, n_neg)。
    """
    rng = np.random.default_rng(seed)
    pat_ids = df["Patient_ID"].values.astype(int)
    m = ~(np.isnan(y) | np.isnan(score))
    n_pos = int(np.nansum((y[m] == 1))); n_neg = int(np.nansum((y[m] == 0)))
    point = _auprc(y, score)
    if np.isnan(point):
        return point, np.nan, np.nan, n_pos, n_neg

    # cluster bootstrap
    boot = []
    for _ in range(n_boot):
        samp = rng.choice(patients, size=len(patients), replace=True)
        idx = np.concatenate([np.where(pat_ids == p)[0] for p in samp])
        v = _auprc(y[idx], score[idx])
        if not np.isnan(v):
            boot.append(v)
    boot = np.asarray(boot, float)
    if len(boot) < 20:
        return point, np.nan, np.nan, n_pos, n_neg

    # jackknife over patients (加速度)
    jack = []
    for p in patients:
        idx = np.where(pat_ids != p)[0]
        v = _auprc(y[idx], score[idx])
        if not np.isnan(v):
            jack.append(v)
    jack = np.asarray(jack, float)

    # BCa 参数
    prop = float(np.mean(boot < point))
    prop = min(max(prop, 1e-6), 1 - 1e-6)
    z0 = _norm_ppf(prop)
    if len(jack) >= 2:
        jbar = jack.mean()
        num = np.sum((jbar - jack) ** 3)
        den = 6.0 * (np.sum((jbar - jack) ** 2) ** 1.5)
        a_hat = float(num / den) if den > 1e-12 else 0.0
    else:
        a_hat = 0.0

    def _bca_pct(alpha):
        za = _norm_ppf(alpha)
        adj = z0 + (z0 + za) / (1.0 - a_hat * (z0 + za))
        return _norm_cdf(adj) * 100.0

    lo_pct, hi_pct = _bca_pct(0.025), _bca_pct(0.975)
    lo_pct = min(max(lo_pct, 0.1), 99.9); hi_pct = min(max(hi_pct, 0.1), 99.9)
    ci_lo = float(np.percentile(boot, min(lo_pct, hi_pct)))
    ci_hi = float(np.percentile(boot, max(lo_pct, hi_pct)))
    return point, ci_lo, ci_hi, n_pos, n_neg


def paired_delta_auprc_cluster(df, s_a, s_b, y, patients, *, n_boot=N_BOOT_AUPRC, seed=SEED):
    """配对 ΔAUPRC = AUPRC(A)-AUPRC(B), cluster bootstrap over patients 百分位 CI + 双侧近似 p。
    (配对 BCa 复杂, 此处用 cluster 百分位; exploratory 附注用途足够。)
    """
    rng = np.random.default_rng(seed)
    pat_ids = df["Patient_ID"].values.astype(int)
    da = _auprc(y, s_a); db = _auprc(y, s_b)
    delta = da - db if not (np.isnan(da) or np.isnan(db)) else np.nan
    boot = []
    for _ in range(n_boot):
        samp = rng.choice(patients, size=len(patients), replace=True)
        idx = np.concatenate([np.where(pat_ids == p)[0] for p in samp])
        aa = _auprc(y[idx], s_a[idx]); bb = _auprc(y[idx], s_b[idx])
        if not (np.isnan(aa) or np.isnan(bb)):
            boot.append(aa - bb)
    boot = np.asarray(boot, float)
    if len(boot) < 20:
        return dict(delta=delta, ci_lo=np.nan, ci_hi=np.nan, p=np.nan)
    ci_lo = float(np.percentile(boot, 2.5)); ci_hi = float(np.percentile(boot, 97.5))
    p = 2.0 * min(float(np.mean(boot <= 0)), float(np.mean(boot >= 0)))
    return dict(delta=delta, ci_lo=ci_lo, ci_hi=ci_hi, p=min(p, 1.0))


# ═══════════════════════════════════════════════════════════════════════════════
# Holm 校正 (纯 numpy)
# ═══════════════════════════════════════════════════════════════════════════════
def holm(pvals):
    """Holm-Bonferroni 校正; 返回与输入同序的校正后 p (NaN 保持 NaN)。"""
    items = [(i, p) for i, p in enumerate(pvals) if p is not None and not np.isnan(p)]
    if not items:
        return [np.nan] * len(pvals)
    items.sort(key=lambda t: t[1])
    m = len(items)
    out = [np.nan] * len(pvals)
    prev = 0.0
    for rank, (i, p) in enumerate(items):
        adj = min(1.0, (m - rank) * p)
        adj = max(adj, prev)                 # 单调不减
        out[i] = adj; prev = adj
    return out


# ═══════════════════════════════════════════════════════════════════════════════
# OOF → 对齐 pooled 的分数向量
# ═══════════════════════════════════════════════════════════════════════════════
def oof_score_vector(oof_df, df, layer, model, label_kind):
    """取 (layer,model,label_kind) 的 OOF, 按 mut_key 对齐 pooled df 行。
    rf 多 seed → 取均值; 返回 (mean_score ndarray, per_seed dict{seed:ndarray} 仅 rf)。
    """
    sub = oof_df[(oof_df.layer == layer) & (oof_df.model == model) &
                 (oof_df.label_kind == label_kind)]
    key = df["mut_key"].values
    if model == "rf":
        per_seed = {}
        for s, g in sub.groupby("seed"):
            mp = dict(zip(g["mut_key"], g["oof"]))
            per_seed[int(s)] = np.array([mp.get(k, np.nan) for k in key], float)
        if not per_seed:
            return np.full(len(df), np.nan), {}
        mean = np.nanmean(np.column_stack(list(per_seed.values())), axis=1)
        return mean, per_seed
    mp = dict(zip(sub["mut_key"], sub["oof"]))
    return np.array([mp.get(k, np.nan) for k in key], float), {}


# ═══════════════════════════════════════════════════════════════════════════════
# 主流程
# ═══════════════════════════════════════════════════════════════════════════════
def main():
    ap = argparse.ArgumentParser(description="R10 双指标评测 (§3.3 融合负检验)")
    ap.add_argument("--oof", default=str(OOF_CSV))
    ap.add_argument("--input", default=str(FROZEN_POOLED))
    ap.add_argument("--min_pep", type=int, default=MIN_PEP)
    args = ap.parse_args()

    df = load_frozen(args.input).reset_index(drop=True)
    pats = present_patients(df)
    if not Path(args.oof).exists():
        sys.exit(f"[ERR] 先跑 R10_leak_free_lopo.py; 缺 {args.oof}")
    oof_df = pd.read_csv(args.oof, comment="#", encoding="utf-8")
    layers = [l for l in ["L0", "L1", "L2", "L3", "L4", "covariate_only"]
              if l in set(oof_df.layer.unique())]
    models = sorted(oof_df.model.unique())
    label_kinds = list(oof_df.label_kind.unique())

    # ── 基线分 ─────────────────────────────────────────────────────────────────
    if STRONGEST_SINGLE not in df.columns:
        sys.exit(f"[ERR] 缺最强单工具列 {STRONGEST_SINGLE}")
    single = df[STRONGEST_SINGLE].values.astype(float)
    geomean = np.asarray(apply_fusion(df, GEOMEAN_DIMS, "geomean", patients=pats).values, float)
    single_raw = per_patient_spearman(df, single, patients=pats, min_pep=args.min_pep)[0]
    single_len = per_patient_partial_spearman(df, single, ctrl=CTRL, patients=pats,
                                              min_pep=args.min_pep)[0]
    geo_raw = per_patient_spearman(df, geomean, patients=pats, min_pep=args.min_pep)[0]
    print(f"[baseline] {STRONGEST_SINGLE} ρ̄raw={single_raw:+.4f} 控肽长={single_len:+.4f}; "
          f"geomean(SURV6) ρ̄raw={geo_raw:+.4f}")

    # ── 二元标签 (AUPRC 用) ────────────────────────────────────────────────────
    lab_map = load_binary_labels()
    y_pval = np.array([lab_map.get(mk, np.nan) for mk in df["mut_key"].values], float)
    sfc = pd.to_numeric(df["Elispot"], errors="coerce").values.astype(float)
    y_sfc = np.where(~np.isnan(sfc), (sfc > 0).astype(float), np.nan)
    y_by_kind = {"pval<0.05": y_pval, "Elispot>0": y_sfc}

    # ── ④ 功效前置: 有效 K (以 confirmatory 对照的一个代表跑一次拿 K) ────────────
    #    K = paired_patient_test 过滤后配对病人数; 用 geomean vs single 探一次 (结构同 OOF 对照)。
    _, _, K_probe = paired_patient_test(df, geomean, single, patients=pats, min_pep=args.min_pep)
    mde_p = 2.0 / (2 ** K_probe) if K_probe > 0 else np.nan
    print(f"[power] 有效配对病人 K≈{K_probe}; 最小可达双侧 p=2/2^K={mde_p:.4g} "
          f"({'≥0.05 功效充足' if (not np.isnan(mde_p) and mde_p <= 0.05) else '够不到0.05, 功效不足'})")

    # ── 主指标 + AUPRC 逐 (层×模型×标签) ───────────────────────────────────────
    main_rows, auprc_rows = [], []
    exploratory_p = []           # (标识, p) 收集供 Holm
    confirmatory = None
    gate = {}

    for layer in layers:
        for model in models:
            for lk in label_kinds:
                score, per_seed = oof_score_vector(oof_df, df, layer, model, lk)
                if np.all(np.isnan(score)):
                    continue
                # 主指标 (vs Elispot 连续)
                rho_raw, cl, ch, nu, _ = per_patient_spearman(
                    df, score, patients=pats, min_pep=args.min_pep)
                rho_len = per_patient_partial_spearman(
                    df, score, ctrl=CTRL, patients=pats, min_pep=args.min_pep)[0]
                _, blo, bhi, _ = bootstrap_patient_ci(
                    df, score, n_boot=2000, seed=SEED, patients=pats, min_pep=args.min_pep)
                # rf 多 seed → ρ̄ 均值±std
                rho_std = np.nan
                if model == "rf" and per_seed:
                    seed_rhos = [per_patient_spearman(df, v, patients=pats,
                                                      min_pep=args.min_pep)[0]
                                 for v in per_seed.values()]
                    seed_rhos = [x for x in seed_rhos if not np.isnan(x)]
                    rho_std = float(np.std(seed_rhos)) if seed_rhos else np.nan
                # 配对检验 vs 最强单 (raw + 控肽长) + vs geomean
                d_s_raw, p_s_raw, K1 = paired_patient_test(
                    df, score, single, patients=pats, min_pep=args.min_pep)
                d_s_len, p_s_len, K2 = paired_patient_test(
                    df, score, single, ctrl=CTRL, patients=pats, min_pep=args.min_pep)
                d_g, p_g, K3 = paired_patient_test(
                    df, score, geomean, patients=pats, min_pep=args.min_pep)

                is_conf = (layer == "L1" and model == "logistic" and lk == "pval<0.05")
                role = "CONFIRMATORY" if is_conf else "exploratory"
                main_rows.append(dict(
                    layer=layer, model=model, label_kind=lk, role=role, n_pat=int(nu),
                    rho_raw=r6(rho_raw), rho_lenctrl=r6(rho_len), rho_seed_std=r6(rho_std),
                    ci_lo=r6(blo), ci_hi=r6(bhi),
                    d_vs_single_raw=r6(d_s_raw), p_vs_single_raw=r6(p_s_raw), K_single_raw=K1,
                    d_vs_single_len=r6(d_s_len), p_vs_single_len=r6(p_s_len), K_single_len=K2,
                    d_vs_geomean=r6(d_g), p_vs_geomean=r6(p_g), K_geomean=K3))

                # confirmatory 记录 (控肽长 vs 最强单)
                if is_conf:
                    confirmatory = dict(layer=layer, model=model, label_kind=lk,
                                        rho_lenctrl=r6(rho_len), single_len=r6(single_len),
                                        d_vs_single_len=r6(d_s_len),
                                        p_vs_single_len=r6(p_s_len), K=K2,
                                        win_direction=bool((d_s_len or 0) > 0),
                                        significant=bool((p_s_len is not None)
                                                         and not np.isnan(p_s_len)
                                                         and p_s_len < 0.05))
                else:
                    if p_s_len is not None and not np.isnan(p_s_len):
                        exploratory_p.append((f"{layer}/{model}/{lk}:vs_single_len", float(p_s_len)))

                # 归因闸材料 (控肽长 ρ̄): L1 logistic 与 covariate_only logistic
                if model == "logistic" and lk == "pval<0.05":
                    if layer == "L1":
                        gate["full_L1_len"] = rho_len
                    if layer == "covariate_only":
                        gate["covonly_len"] = rho_len

                # ② AUPRC (副指标, exploratory)
                yb = y_by_kind.get(lk)
                if yb is not None and len(np.unique(yb[~np.isnan(yb)])) >= 2:
                    ap_pt, alo, ahi, npos, nneg = auprc_bca(df, score, yb, pats)
                    dd = paired_delta_auprc_cluster(df, score, single, yb, pats)
                    prevalence = npos / (npos + nneg) if (npos + nneg) else np.nan
                    auprc_rows.append(dict(
                        layer=layer, model=model, label_kind=lk, role=role,
                        AUPRC=r6(ap_pt, 4), bca_lo=r6(alo, 4), bca_hi=r6(ahi, 4),
                        prevalence=r6(prevalence, 4), n_pos=npos, n_neg=nneg,
                        dAUPRC_vs_single=r6(dd["delta"], 4),
                        dAUPRC_ci_lo=r6(dd["ci_lo"], 4), dAUPRC_ci_hi=r6(dd["ci_hi"], 4),
                        dAUPRC_p=r6(dd["p"], 4)))

    # ── ⑤ 归因闸 ───────────────────────────────────────────────────────────────
    full_len = gate.get("full_L1_len", np.nan)
    cov_len = gate.get("covonly_len", np.nan)
    gate_pass = (not np.isnan(full_len)) and (full_len > single_len) and \
                (np.isnan(cov_len) or full_len > cov_len)
    print(f"[归因闸] L1 logistic 控肽长 ρ̄={full_len:+.4f} vs 单工具={single_len:+.4f} "
          f"vs covariate-only={cov_len:+.4f} → {'PASS' if gate_pass else 'FAIL'}")

    # ── ③ shuffle 对照 ─────────────────────────────────────────────────────────
    shuffle_check = None
    if OOF_SHUFFLE_CSV.exists():
        sh = pd.read_csv(OOF_SHUFFLE_CSV, comment="#", encoding="utf-8")
        rows = []
        max_abs_rho, min_p = 0.0, 1.0
        for layer in [l for l in layers if l in set(sh.layer.unique())]:
            for model in sorted(sh.model.unique()):
                for lk in sh.label_kind.unique():
                    sc, _ = oof_score_vector(sh, df, layer, model, lk)
                    if np.all(np.isnan(sc)):
                        continue
                    rr = per_patient_spearman(df, sc, patients=pats, min_pep=args.min_pep)[0]
                    _, pp, _ = paired_patient_test(df, sc, single, patients=pats,
                                                   min_pep=args.min_pep)
                    yb = y_by_kind.get(lk)
                    au = (_auprc(yb, sc) if (yb is not None and
                          len(np.unique(yb[~np.isnan(yb)])) >= 2) else np.nan)
                    rows.append(dict(layer=layer, model=model, label_kind=lk,
                                     rho_raw=r6(rr), auprc=r6(au, 4),
                                     p_vs_single=r6(pp)))
                    if not np.isnan(rr):
                        max_abs_rho = max(max_abs_rho, abs(rr))
                    if pp is not None and not np.isnan(pp):
                        min_p = min(min_p, pp)
        leak = (max_abs_rho > 0.15) or (min_p < 0.05)
        shuffle_check = dict(rows=rows, max_abs_rho=r6(max_abs_rho),
                             min_paired_p=r6(min_p),
                             verdict=("LEAK_SUSPECTED_全线作废" if leak
                                      else "OK_塌回零_无泄漏"))
        print(f"[shuffle] max|ρ̄|={max_abs_rho:.4f} min配对p={min_p:.4f} → "
              f"{shuffle_check['verdict']}")
    else:
        print("[shuffle] 未找到 R10_featfusion_oof_shuffle.csv (跑 --shuffle 后再评; 防泄漏对照缺)")

    # ── ⑥ Holm 校正 exploratory ────────────────────────────────────────────────
    holm_p = holm([p for _, p in exploratory_p])
    exploratory_holm = [dict(test=exploratory_p[i][0], p_raw=r6(exploratory_p[i][1]),
                             p_holm=r6(holm_p[i])) for i in range(len(exploratory_p))]

    # ── 写 CSV ─────────────────────────────────────────────────────────────────
    out_dir = ensure_out_dir()
    main_df = pd.DataFrame(main_rows)
    mpath = out_dir / "R10_featfusion_eval_main.csv"
    with open(mpath, "w", encoding="utf-8", newline="") as f:
        f.write("# R10_featfusion_eval_main.csv — 主指标 per-patient Spearman(OOF vs Elispot SFC)\n")
        f.write("# 与 R1-R9 同源可比; d_vs_*=配对 Fisher-z 差(paired_patient_test), p_vs_*=符号置换 p。\n")
        f.write(f"# 最强单={STRONGEST_SINGLE}(ρ̄raw={r6(single_raw)},控肽长={r6(single_len)}); "
                f"geomean(SURV6) raw={r6(geo_raw)}。\n")
        f.write("# role=CONFIRMATORY 仅 L1/logistic/pval<0.05 控肽长 vs 最强单(PREREG §2); 余 exploratory→Holm。\n")
        main_df.to_csv(f, index=False)
    print(f"[saved] {mpath}  shape={main_df.shape}")

    au_df = pd.DataFrame(auprc_rows)
    apath = out_dir / "R10_featfusion_eval_auprc.csv"
    with open(apath, "w", encoding="utf-8", newline="") as f:
        f.write("# R10_featfusion_eval_auprc.csv — 肽级 AUPRC (副指标, EXPLORATORY, 非 headline)\n")
        f.write("# 独立 estimand(混病人内/间+疫苗肽选择效应); cluster bootstrap over patients BCa CI。\n")
        f.write("# dAUPRC_vs_single=配对 ΔAUPRC(cluster 百分位 CI + 双侧近似 p)。绝不当 headline(PREREG §4)。\n")
        au_df.to_csv(f, index=False)
    print(f"[saved] {apath}  shape={au_df.shape}")

    # ── 写 summary.json ────────────────────────────────────────────────────────
    def _clean(o):
        if isinstance(o, (np.integer,)): return int(o)
        if isinstance(o, (np.floating,)): return float(o)
        if isinstance(o, np.bool_): return bool(o)
        return str(o)

    summary = {
        "service": "QuantImmuBench §3.3 集成框架 / C2 融合负检验 (预期 NULL)",
        "prereg": "PREREG_R10_featfusion.md",
        "input": Path(args.input).name,
        "strongest_single": STRONGEST_SINGLE,
        "single_rho_raw": r6(single_raw), "single_rho_lenctrl": r6(single_len),
        "geomean_rho_raw": r6(geo_raw),
        "power": {"effective_K": int(K_probe), "min_achievable_p": r6(mde_p),
                  "sufficient": bool((not np.isnan(mde_p)) and mde_p <= 0.05),
                  "note": "K<6 → confirmatory 功效不足, 未拒 NULL 不可读成证明整合无效 (PREREG §6)"},
        "confirmatory": confirmatory,
        "attribution_gate": {
            "full_L1_logistic_lenctrl": r6(full_len),
            "single_lenctrl": r6(single_len),
            "covariate_only_lenctrl": r6(cov_len),
            "pass": bool(gate_pass),
            "rule": "confirmatory 赢须 full > max(单工具, covariate-only) (PREREG §3)"},
        "confirmatory_verdict": _confirm_verdict(confirmatory, gate_pass, K_probe, mde_p),
        "shuffle_check": shuffle_check,
        "exploratory_holm": exploratory_holm,
        "note_三分流": "预期 NULL; ①真显著(过闸)②肽级显著per-patient不③都不显著 任一诚实呈报(PREREG §4)",
    }
    spath = out_dir / "R10_featfusion_eval_summary.json"
    with open(spath, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False, default=_clean)
    print(f"[saved] {spath}")
    print(f"\n[CONFIRMATORY 结论] {summary['confirmatory_verdict']}")
    print("[DONE] R10_eval_dual")


def _confirm_verdict(conf, gate_pass, K, mde_p):
    """confirmatory 三分流裁决文案 (PREREG §2/§3/§6)。"""
    if conf is None:
        return "confirmatory(L1 logistic) 无有效 OOF, 无法裁决"
    if not np.isnan(mde_p) and mde_p > 0.05:
        return (f"功效不足(K={K}, min p={mde_p:.4g}>0.05): 未能拒绝 NULL, "
                f"不可读成证明整合无效 (PREREG §6)")
    sig = conf.get("significant"); win = conf.get("win_direction")
    if sig and win and gate_pass:
        return "① confirmatory 真显著且过归因闸 → 罕见: 有条件的方法贡献 (需复核)"
    if sig and win and not gate_pass:
        return "confirmatory 显著但归因闸 FAIL → 学到 driver/indel 粗规律非整合工具, 不算成立"
    return ("③ confirmatory 不显著(预期主线): 连喂真免疫学特征学习融合也打不过最强单工具 "
            f"(p_vs_single_len={conf.get('p_vs_single_len')})")


if __name__ == "__main__":
    main()
