#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
compare_countclean_vs_dirty.py
==============================
服务: QuantImmuBench 论文 —— count-clean pooling lever 的「脏 vs 干净」口径对照诊断。
对应 04_LOG Entry 38; 权威框架 paper/QuanImmu-Paper-Outline.md §3.2 / §3.3.4。

一句话 (它回答什么):
  「排除 count 混杂 pooling 后, outline 的 headline 复现多少?」
  背景 (数字 Bash 核): n_subpep (一突变候选子肽数) 自身对 ELISpot per-patient Spearman
  ≈ +0.36, 比多数工具真分还高 = 巨大 count 混杂; sum pooling 机械 ∝ n_subpep
  (outline §3.2 自警 sum≈n_subpep 数子肽数作弊)。旧口径 (脏) best_pooling_for_tool
  不管混杂在 8 pooling 里挑最优 → 21/29 挑到 sum, 「聚合打败 max」大半是假象。
  干净口径 = 只在 count_conf_<tool>_<pooling>==False 里选, 隔离工具真 skill。

出三块对照 (脏=全池 best; 干净=count-clean best):
  §3.2 max 最优性 —— 全 30 工具, 按类别 (呈递/免疫原) 统计「max 即最优」工具数 +
      中位 gap(best−max); 脏 vs 干净。
  §3.3.4 fusion 冠军 —— DIM7 fusion (维度列各工具取最优 pooling), geomean/powmean/
      mean_rank/median 各 per-patient Fisher-z + 谁第一; 脏 vs 干净各排一次。
  n_subpep 混杂 —— n_subpep 自身 ρ vs ELISpot; 各工具 clean-best pooling 与 n_subpep
      的 (全肽) Spearman, 确认已去混杂 (|ρ|<=0.5)。

输入 (只读冻结表, 不改):
  data/frozen/pooled_peptide_level_30tools_9mer.csv  (9mer 主分析; --input 可切全窗)
  依赖冻结表 count_conf_<tool>_<pooling> 布尔列 (p0e 算, |Spearman(pooled,n_subpep)|>0.5)。
输出 (analysis/official/):
  DIAG_countclean_vs_dirty.csv          —— 每工具一行 §3.2 max 最优性对照 (脏 vs 干净)
  DIAG_countclean_vs_dirty.summary.json —— §3.2 类别汇总 + §3.3.4 fusion 冠军 + n_subpep 混杂
  + 全部打印到 stdout。

类别 (outline §3.2, 与 30 工具交集):
  呈递 = {netMHCpan_BA, netMHCpan_EL, MHCflurry, HLAthena, MixMHCpred, BigMHC_EL,
         TransHLA, MHCseqNet, MHCnuggets, netMHCstabpan} ∩ 30 工具 = 8 个
         (MixMHCpred/BigMHC_EL 不在 30 工具名册, 交集自动剔); 其余 22 = 免疫原。

跑法 (主线跑, 我不跑):
  python analysis/official/compare_countclean_vs_dirty.py
  python analysis/official/compare_countclean_vs_dirty.py --input data/frozen/pooled_peptide_level_30tools.csv

Windows 规范: UTF-8 stdout, pathlib, 纯 numpy/pandas, 零 scipy.stats, 零 GPU。
"""

import sys
import json
import argparse
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _official_common import (                              # noqa: E402
    load_frozen, present_patients, per_patient_spearman, best_pooling_for_tool,
    apply_fusion, pool_col, spearman_np, is_count_confounded,
    TOOLS_30, MIN_PEP, LABEL_COL, FROZEN_POOLED, ensure_out_dir,
)

# ── 类别 (outline §3.2; 与 30 工具名册交集, 缺席者 warn) ────────────────────────
PRESENTATION_10 = [
    "netMHCpan_BA", "netMHCpan_EL", "MHCflurry", "HLAthena", "MixMHCpred",
    "BigMHC_EL", "TransHLA", "MHCseqNet", "MHCnuggets", "netMHCstabpan",
]

# ── DIM7 fusion 维度 (同 R6/R7 SURV6 + 亲和代理; ★TODO 待袁/朱确认) ─────────────
AFFINITY_PROXY = "netMHCpan_BA"
SURV6 = ["PredIG", "IMPROVE", "pTuneos", "PRIME", "ImmuneApp", "deepHLApan"]
DIM7_TOOLS = list(SURV6) + [AFFINITY_PROXY]

# fusion 冠军对照的 4 无监督法 (task 指定; 均在 _official_common.UNSUPERVISED_FUSIONS)
FUSION_METHODS = ["geomean", "powmean", "mean_rank", "median"]

# 「max≈最优」的 gap 容差 (诊断用, 明标; 主计数以 exact best_pl=='max' 为准)
APPROX_TOL = 0.02


def _rho_of_col(df, col, pats, min_pep):
    """某列 per-patient Fisher-z ρ̄ (标量), 缺列/全 NaN 返回 NaN。"""
    if col not in df.columns or df[col].notna().sum() == 0:
        return np.nan
    rho, *_ = per_patient_spearman(df, col, patients=pats, min_pep=min_pep)
    return rho


def category_of(tool, present_pres):
    return "presentation" if tool in present_pres else "immunogenic"


def build_dim_cols(df, pats, min_pep, count_clean):
    """DIM7 各工具最优 pooling 列 (count_clean 控口径); 返回 (cols, used_labels)。"""
    cols, used = [], []
    for t in DIM7_TOOLS:
        bp, _r, _a = best_pooling_for_tool(df, t, patients=pats, min_pep=min_pep,
                                           count_clean=count_clean)
        if bp is None:
            print(f"[warn] DIM7 {t}: 无有效 pooling (count_clean={count_clean}), 剔除")
            continue
        cols.append(pool_col(t, bp))
        used.append(f"{t}_{bp}")
    return cols, used


def fusion_champion(df, pats, min_pep, count_clean, seed):
    """DIM7 fusion 各法 per-patient Fisher-z + 冠军 (某口径)。返回 dict。"""
    dim_cols, used = build_dim_cols(df, pats, min_pep, count_clean)
    scores = {}
    for m in FUSION_METHODS:
        s = apply_fusion(df, dim_cols, m, patients=pats, seed=seed)
        rho, *_ = per_patient_spearman(df, s, patients=pats, min_pep=min_pep)
        scores[m] = None if rho is None or np.isnan(rho) else float(rho)
    valid = {k: v for k, v in scores.items() if v is not None}
    champ = max(valid, key=valid.get) if valid else None
    return {
        "dim_cols_used": used,
        "fusion_rho": {k: (round(v, 6) if v is not None else None)
                       for k, v in scores.items()},
        "champion": champ,
        "champion_rho": round(valid[champ], 6) if champ else None,
    }


def main():
    ap = argparse.ArgumentParser(
        description="count-clean vs dirty 口径对照诊断 (§3.2 max 最优性 + §3.3.4 fusion 冠军)")
    ap.add_argument("--input", default=str(FROZEN_POOLED), help="冻结肽级表路径")
    ap.add_argument("--min_pep", type=int, default=MIN_PEP)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--approx_tol", type=float, default=APPROX_TOL,
                    help="max≈最优 的 gap 容差 (诊断用)")
    args = ap.parse_args()

    df = load_frozen(args.input)
    pats = present_patients(df)
    n_pep = len(df)
    print(f"[info] 冻结表 {df.shape}; DS2 患者({len(pats)})={pats}; min_pep={args.min_pep}")

    present_pres = [t for t in PRESENTATION_10 if t in TOOLS_30]
    missing_pres = [t for t in PRESENTATION_10 if t not in TOOLS_30]
    if missing_pres:
        print(f"[warn] 呈递类中不在 30 工具名册 (交集剔除): {missing_pres}")
    print(f"[info] 类别: 呈递 {len(present_pres)} {present_pres}; "
          f"免疫原 {len(TOOLS_30) - len(present_pres)}")

    # ── §3.2 每工具 max 最优性对照 ──────────────────────────────────────────────
    rows = []
    for t in TOOLS_30:
        cat = category_of(t, present_pres)
        max_col = pool_col(t, "max")
        max_rho = _rho_of_col(df, max_col, pats, args.min_pep)

        d_bp, d_rho, d_all = best_pooling_for_tool(
            df, t, patients=pats, min_pep=args.min_pep, count_clean=False)
        c_bp, c_rho, c_all = best_pooling_for_tool(
            df, t, patients=pats, min_pep=args.min_pep, count_clean=True)

        d_gap = (d_rho - max_rho) if not (np.isnan(d_rho) or np.isnan(max_rho)) else np.nan
        c_gap = (c_rho - max_rho) if not (np.isnan(c_rho) or np.isnan(max_rho)) else np.nan

        # clean-best pooling 与 n_subpep 全肽 Spearman (确认去混杂; 对齐 count_conf 定义)
        cb_ns_rho = np.nan
        if c_bp is not None:
            cb_col = pool_col(t, c_bp)
            if cb_col in df.columns:
                cb_ns_rho = spearman_np(df[cb_col].values, df["n_subpep"].values)

        rows.append(dict(
            tool=t, category=cat, n_valid_max=int(df[max_col].notna().sum()),
            max_rho=_r(max_rho),
            dirty_best_pl=d_bp, dirty_best_rho=_r(d_rho), dirty_gap=_r(d_gap),
            dirty_max_is_best=int(d_bp == "max") if d_bp else 0,
            clean_best_pl=c_bp, clean_best_rho=_r(c_rho), clean_gap=_r(c_gap),
            clean_max_is_best=int(c_bp == "max") if c_bp else 0,
            clean_max_approx_best=int((not np.isnan(c_gap)) and c_gap <= args.approx_tol),
            clean_all_confounded=int(bool(c_all.get("__all_confounded__", False))),
            cleanbest_nsubpep_rho=_r(cb_ns_rho),
        ))
    tbl = pd.DataFrame(rows)

    # ── §3.2 类别汇总 (脏 vs 干净) ──────────────────────────────────────────────
    def _cat_agg(sub):
        return dict(
            n_tools=int(len(sub)),
            dirty_max_is_best=int(sub["dirty_max_is_best"].sum()),
            clean_max_is_best=int(sub["clean_max_is_best"].sum()),
            clean_max_approx_best=int(sub["clean_max_approx_best"].sum()),
            dirty_median_gap=_r(np.nanmedian(sub["dirty_gap"].values.astype(float))),
            clean_median_gap=_r(np.nanmedian(sub["clean_gap"].values.astype(float))),
            n_all_confounded=int(sub["clean_all_confounded"].sum()),
        )

    maxopt = {
        "overall": _cat_agg(tbl),
        "presentation": _cat_agg(tbl[tbl["category"] == "presentation"]),
        "immunogenic": _cat_agg(tbl[tbl["category"] == "immunogenic"]),
        "approx_tol": args.approx_tol,
    }

    print("\n===== §3.2 max 最优性 (脏=全池 best; 干净=count-clean best) =====")
    for k in ("overall", "presentation", "immunogenic"):
        a = maxopt[k]
        print(f"[{k:13s}] n={a['n_tools']:2d} | max=best 脏 {a['dirty_max_is_best']:2d}"
              f" → 干净 {a['clean_max_is_best']:2d} (≈最优 {a['clean_max_approx_best']:2d}"
              f"@tol{args.approx_tol}) | 中位 gap 脏 {a['dirty_median_gap']:+.4f}"
              f" → 干净 {a['clean_median_gap']:+.4f} | 全混杂 {a['n_all_confounded']}")

    # ── §3.3.4 fusion 冠军 (脏 vs 干净) ─────────────────────────────────────────
    print("\n===== §3.3.4 DIM7 fusion 冠军 (脏 vs 干净) =====")
    fc_dirty = fusion_champion(df, pats, args.min_pep, count_clean=False, seed=args.seed)
    fc_clean = fusion_champion(df, pats, args.min_pep, count_clean=True, seed=args.seed)
    for label, fc in (("脏(全池)", fc_dirty), ("干净(clean)", fc_clean)):
        ranked = sorted([(m, r) for m, r in fc["fusion_rho"].items() if r is not None],
                        key=lambda kv: kv[1], reverse=True)
        rank_str = ", ".join(f"{m}={r:+.4f}" for m, r in ranked)
        print(f"[{label:11s}] 维度={fc['dim_cols_used']}")
        print(f"              {rank_str}  → 冠军={fc['champion']} ({fc['champion_rho']})")

    # ── n_subpep 混杂 ───────────────────────────────────────────────────────────
    ns_self_rho, *_ = per_patient_spearman(df, "n_subpep", patients=pats,
                                           min_pep=args.min_pep)
    cb_ns = tbl["cleanbest_nsubpep_rho"].values.astype(float)
    cb_ns_valid = cb_ns[~np.isnan(cb_ns)]
    n_still_conf = int(np.sum(np.abs(cb_ns_valid) > 0.5))
    print("\n===== n_subpep 混杂诊断 =====")
    print(f"[n_subpep] 自身 per-patient ρ vs ELISpot = {ns_self_rho:+.4f} "
          f"(巨大 count 混杂: 比多数工具真分还高)")
    print(f"[clean-best] 各工具 clean-best pooling 与 n_subpep 全肽 |ρ|: "
          f"中位={np.nanmedian(np.abs(cb_ns_valid)):.4f} 最大={np.nanmax(np.abs(cb_ns_valid)):.4f}"
          f"; 仍 |ρ|>0.5 的工具数={n_still_conf} (应≈0 = 已去混杂)")

    # ── 写 CSV (每工具一行 §3.2) ────────────────────────────────────────────────
    out_dir = ensure_out_dir()
    out_csv = out_dir / "DIAG_countclean_vs_dirty.csv"
    with open(out_csv, "w", encoding="utf-8") as f:
        f.write("# DIAG_countclean_vs_dirty.csv\n")
        f.write("# QuantImmuBench count-clean lever 对照: §3.2 每工具 max 最优性 (脏 vs 干净)\n")
        f.write(f"# 输入={Path(args.input).name}; DS2 患者={pats}; min_pep={args.min_pep}; 肽={n_pep}\n")
        f.write("# 脏=全池 best_pooling; 干净=count-clean best (排除 count_conf==True pooling)\n")
        f.write(f"# gap=best_rho-max_rho; max_is_best=best pooling 是否为 max; approx_tol={args.approx_tol}\n")
        f.write("# cleanbest_nsubpep_rho=clean-best pooling 列与 n_subpep 全肽 Spearman (确认去混杂)\n")
        f.write(f"# [headline] max=best: overall 脏{maxopt['overall']['dirty_max_is_best']}"
                f"→干净{maxopt['overall']['clean_max_is_best']}; "
                f"免疫原 {maxopt['immunogenic']['clean_max_is_best']}/"
                f"{maxopt['immunogenic']['n_tools']}(≈{maxopt['immunogenic']['clean_max_approx_best']}); "
                f"n_subpep 自身 ρ={_r(ns_self_rho, 4)}\n")
        tbl.to_csv(f, index=False)
    print(f"\n[saved] {out_csv}")

    # ── 写 summary.json ─────────────────────────────────────────────────────────
    summary = {
        "lever": "count-clean pooling (排除 count 混杂 pooling, 隔离工具真 skill)",
        "log_ref": "04_LOG Entry 38",
        "input": Path(args.input).name,
        "patients": [int(p) for p in pats],
        "n_peptides": int(n_pep),
        "min_pep": args.min_pep,
        "categories": {
            "presentation_requested": PRESENTATION_10,
            "presentation_present": present_pres,
            "presentation_missing_from_30tools": missing_pres,
            "n_presentation": len(present_pres),
            "n_immunogenic": len(TOOLS_30) - len(present_pres),
        },
        "sec3_2_max_optimality": maxopt,
        "sec3_3_4_fusion_champion": {
            "dirty": fc_dirty,
            "clean": fc_clean,
            "methods": FUSION_METHODS,
            "dim7_TODO": "DIM7=SURV6+netMHCpan_BA, selection 待袁/朱确认 (同 R6/R7)",
        },
        "n_subpep_confounding": {
            "n_subpep_self_perpatient_rho": _r(ns_self_rho),
            "cleanbest_nsubpep_abs_rho_median": _r(np.nanmedian(np.abs(cb_ns_valid))),
            "cleanbest_nsubpep_abs_rho_max": _r(np.nanmax(np.abs(cb_ns_valid))),
            "n_tools_still_confounded_gt0p5": n_still_conf,
        },
    }
    out_json = out_dir / "DIAG_countclean_vs_dirty.summary.json"

    def _jd(o):
        if isinstance(o, np.integer): return int(o)
        if isinstance(o, np.floating): return float(o)
        return str(o)

    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False, default=_jd)
    print(f"[saved] {out_json}")
    print("[DONE] compare_countclean_vs_dirty")


def _r(v, d=6):
    """安全 round (None/NaN -> np.nan)。"""
    if v is None:
        return np.nan
    try:
        fv = float(v)
    except (TypeError, ValueError):
        return np.nan
    return round(fv, d) if not np.isnan(fv) else np.nan


if __name__ == "__main__":
    main()
