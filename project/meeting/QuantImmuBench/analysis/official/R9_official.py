#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
R9_official.py
==============
服务: QuantImmuBench 大纲 补充材料 —— Pearson 对照 + 逐病人 Spearman 分布 (ds1 gated)。
对应大纲: paper/QuanImmu-Paper-Outline.md 补充 (全 Pearson 对照表 / 逐病人分布 / ds1 复现 /
          30 种子明细[R6 已出] / 配对检验完整统计[R7 已出])。

★ 2026-07-01 Part D Phase 3b 干净口径 (见 04_LOG):
  · 输入 = 干净表 pooled_clean_9mer.csv (含 peplen)。
  · [B5 零选择] 最强单工具 + SURV6 fusion 一律 <tool>_max (去 in-sample pooling selection)。
  · [B2 控肽长] Pearson 对照表加 spearman_rho_lenctrl 列; 逐病人分布加 single/fusion 的
    控肽长偏相关列 (per_patient_partial_spearman ctrl='peplen')。

做什么:
  ① Pearson 对照 (与 R1 平行): 30 工具 max-pool, 主指标从 Spearman 换 per-patient Pearson,
     Fisher-z 等权聚合同法 (纯 numpy Pearson, 禁 scipy)。每工具附 spearman_rho +
     spearman_rho_lenctrl 列便于对照「Spearman vs Pearson 一致性」与肽长效应。
  ② 逐病人 Spearman 分布: 对最强单工具 + SURV6 geomean fusion (max 维), 输出每病人 rho
     (裸 + 控肽长), summary 报 min/max/median (验大纲「0.17–0.80 剧烈波动」口径; 数字以实测为准)。
  ③ ds1 复现: 冻结表纯 DS2, 无 ds1 pooling 冻结表 → 查有无, 没有则 summary 标 GATED, 不造数。

输入 (只读干净表):
  data/frozen/pooled_clean_9mer.csv
输出 (analysis/official/):
  R9_single_maxpool_pearson_official.csv  —— 30 工具 max-pool per-patient Pearson (附 spearman_rho + spearman_rho_lenctrl 对照)
  R9_perpatient_distribution_official.csv —— 每病人: single_rho / fusion_rho (裸 + 控肽长)
  R9_supplementary_official.summary.json  —— Pearson↔Spearman 一致性 + 分布统计(裸+控肽长) + ds1 gated 状态

复用旧骨架:
  · 30 工具 max-pool 布局 + rho_p<id> 列 ← R1_official.py
  · Fisher-z 加权聚合 / SURV6 geomean fusion / FULL_COV 最强单工具 ← _official_common / R5 / R7
  · 逐病人 rho 输出 ← per_patient_spearman/partial(return_perpat=True)

★ TODO / GATED:
  · SURV6 成员 = selection, 待袁/朱确认。
  · ds1 (Elispot_Dataset1.xlsx) 未在官方 pooling 管线冻结 → 独立 gated, 本脚本不造数。

跑法 (主线跑, 我不跑):
  python analysis/official/R9_official.py
"""

import sys
import json
import argparse
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _official_common import (                              # noqa: E402
    load_frozen, present_patients, per_patient_spearman,
    per_patient_partial_spearman, apply_fusion, pool_col, fisherz_weighted_agg,
    TOOLS_30, DTU_TOOLS, DS2_PATIENTS, MIN_PEP, LABEL_COL,
    FROZEN_POOLED, ROOT, ensure_out_dir, r6,
)

SURV6 = ["PredIG", "IMPROVE", "pTuneos", "PRIME", "ImmuneApp", "deepHLApan"]


# ═══════════════════════════════════════════════════════════════════════════════
# 纯 numpy Pearson + per-patient Pearson (镜像 per_patient_spearman, 换相关公式)
# ═══════════════════════════════════════════════════════════════════════════════

def pearson_np(x, y):
    """纯 numpy Pearson 相关; 样本不足/常量列返回 NaN。禁 scipy (防 OMP)。"""
    x = np.asarray(x, float)
    y = np.asarray(y, float)
    m = ~(np.isnan(x) | np.isnan(y))
    x, y = x[m], y[m]
    n = len(x)
    if n < 2:
        return np.nan
    xd = x - x.mean()
    yd = y - y.mean()
    denom = np.sqrt((xd ** 2).sum() * (yd ** 2).sum())
    if denom == 0:
        return np.nan
    return float((xd * yd).sum() / denom)


def per_patient_pearson(df, col, *, patients, min_pep, label_col=LABEL_COL,
                        return_perpat=False):
    """逐病人 Pearson(col, label), 跨病人 Fisher-z 加权聚合 (口径同 per_patient_spearman)。"""
    rhos, ns, rhos_by, ns_by = [], [], {}, {}
    for pat in patients:
        g = df[df["Patient_ID"] == pat]
        n = len(g)
        x = g[col].values.astype(float)
        y = g[label_col].values.astype(float)
        rho = pearson_np(x, y) if n >= min_pep else np.nan
        rhos.append(rho)
        ns.append(float(n))
        rhos_by[pat] = rho
        ns_by[pat] = n
    rb, lo, hi, nu, nd = fisherz_weighted_agg(np.array(rhos, float), np.array(ns, float))
    if return_perpat:
        return rb, lo, hi, nu, nd, rhos_by, ns_by
    return rb, lo, hi, nu, nd


def strongest_single(df, pats, min_pep):
    """[B5 零选择] 全覆盖(130 肽)池 <tool>_max per-patient Fisher-z 最高单工具。
    返回 (col, tool, 'max', full_cov_n)。"""
    n = len(df)
    full_cov = [t for t in TOOLS_30
                if f"{t}_max" in df.columns and int(df[f"{t}_max"].notna().sum()) == n]
    best_tool, best_rho, best_col = None, -np.inf, None
    for t in full_cov:
        col = pool_col(t, "max")
        rho, *_ = per_patient_spearman(df, col, patients=pats, min_pep=min_pep)
        if rho is not None and not np.isnan(rho) and rho > best_rho:
            best_tool, best_rho, best_col = t, rho, col
    return best_col, best_tool, "max", len(full_cov)


def _dist_stats(vals):
    v = np.array([x for x in vals if x is not None and not np.isnan(x)], float)
    if len(v) == 0:
        return dict(min=None, max=None, median=None, n=0)
    return dict(min=r6(float(v.min()), 4), max=r6(float(v.max()), 4),
                median=r6(float(np.median(v)), 4), n=int(len(v)))


def main():
    ap = argparse.ArgumentParser(
        description="R9 官方: Pearson 对照 + 逐病人分布 (补充材料; ds1 gated)")
    ap.add_argument("--input", default=str(FROZEN_POOLED), help="干净肽级表路径")
    ap.add_argument("--min_pep", type=int, default=MIN_PEP)
    ap.add_argument("--ctrl", default="peplen", help="控制变量列 (B2 偏相关, 默认 peplen)")
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    df = load_frozen(args.input)
    pats = present_patients(df)
    print(f"[info] 干净表 {df.shape}; DS2 患者({len(pats)})={pats}; min_pep={args.min_pep}; "
          f"ctrl={args.ctrl}")

    # ── ① Pearson 对照 (与 R1 平行, 附 spearman_rho + spearman_rho_lenctrl) ─────────
    rows = []
    for tool in TOOLS_30:
        col = pool_col(tool, "max")
        if col not in df.columns:
            print(f"[warn] {tool}: 缺列 {col}, 跳过")
            continue
        p_rb, p_lo, p_hi, p_nu, p_nd, p_by, _ = per_patient_pearson(
            df, col, patients=pats, min_pep=args.min_pep, return_perpat=True)
        s_rb, *_ = per_patient_spearman(df, col, patients=pats, min_pep=args.min_pep)
        s_len, *_ = per_patient_partial_spearman(
            df, col, ctrl=args.ctrl, patients=pats, min_pep=args.min_pep)
        row = {
            "Tool": tool, "pending_DTU": tool in DTU_TOOLS,
            "pearson_rho": r6(p_rb, 4), "ci_lo": r6(p_lo, 4), "ci_hi": r6(p_hi, 4),
            "n_pat": int(p_nu), "n_dropped": int(p_nd),
            "spearman_rho": r6(s_rb, 4),
            "spearman_rho_lenctrl": r6(s_len, 4),
        }
        for pid in DS2_PATIENTS:
            row[f"rho_p{pid}"] = r6(p_by.get(pid, np.nan), 4)
        rows.append(row)
    pear_df = pd.DataFrame(rows).sort_values("pearson_rho", ascending=False)

    out_dir = ensure_out_dir()
    pear_csv = out_dir / "R9_single_maxpool_pearson_official.csv"
    with open(pear_csv, "w", encoding="utf-8") as f:
        f.write("# R9_single_maxpool_pearson_official.csv\n")
        f.write("# QuantImmuBench 补充: 30 工具 max-pool per-patient Pearson (与 R1 Spearman 平行)\n")
        f.write(f"# 输入={Path(args.input).name}; DS2 9 患者; Elispot 连续 SFC\n")
        f.write("# pearson_rho=跨患者 Fisher-z 等权聚合 Pearson; spearman_rho=R1 口径对照列\n")
        f.write(f"# spearman_rho_lenctrl=控肽长偏相关(B2, ctrl={args.ctrl}); 与 spearman_rho 对比看肽长效应\n")
        f.write("# rho_p<id>=各患者 per-patient Pearson; pending_DTU=DTU 受限工具\n")
        pear_df.to_csv(f, index=False)
    print(f"[saved] {pear_csv}  shape={pear_df.shape}")

    # Pearson↔Spearman 一致性 (跨工具的两指标排序相关)
    pv = pear_df["pearson_rho"].values.astype(float)
    sv = pear_df["spearman_rho"].values.astype(float)
    mask = ~(np.isnan(pv) | np.isnan(sv))
    from _official_common import spearman_np
    consistency = spearman_np(pv[mask], sv[mask]) if mask.sum() >= 2 else np.nan

    # ── ② 逐病人 Spearman 分布 (最强单工具 + SURV6 geomean fusion, max 维; 裸 + 控肽长) ──
    single_col, s_tool, s_pool, full_cov_n = strongest_single(df, pats, args.min_pep)
    _sb, _sl, _sh, _snu, _snd, single_by, ns_by = per_patient_spearman(
        df, single_col, patients=pats, min_pep=args.min_pep, return_perpat=True)
    _, _, _, _, _, single_len_by, _ = per_patient_partial_spearman(
        df, single_col, ctrl=args.ctrl, patients=pats, min_pep=args.min_pep,
        return_perpat=True)

    surv6_cols, surv6_used = [], []
    for t in SURV6:
        col = pool_col(t, "max")
        if col not in df.columns or df[col].notna().sum() == 0:
            continue
        surv6_cols.append(col)
        surv6_used.append(f"{t}_max")
    fusion_score = apply_fusion(df, surv6_cols, "geomean", patients=pats, seed=args.seed)
    fusion_arr = np.asarray(fusion_score.values, dtype=float)
    _fb, _fl, _fh, _fnu, _fnd, fusion_by, _ = per_patient_spearman(
        df, fusion_arr, patients=pats, min_pep=args.min_pep, return_perpat=True)
    _, _, _, _, _, fusion_len_by, _ = per_patient_partial_spearman(
        df, fusion_arr, ctrl=args.ctrl, patients=pats, min_pep=args.min_pep,
        return_perpat=True)

    dist_rows = []
    for pid in pats:
        dist_rows.append(dict(
            patient_id=int(pid), n_pep=int(ns_by.get(pid, 0)),
            single_rho=r6(single_by.get(pid, np.nan), 4),
            single_rho_lenctrl=r6(single_len_by.get(pid, np.nan), 4),
            fusion_rho=r6(fusion_by.get(pid, np.nan), 4),
            fusion_rho_lenctrl=r6(fusion_len_by.get(pid, np.nan), 4)))
    dist_df = pd.DataFrame(dist_rows)

    dist_csv = out_dir / "R9_perpatient_distribution_official.csv"
    with open(dist_csv, "w", encoding="utf-8") as f:
        f.write("# R9_perpatient_distribution_official.csv\n")
        f.write("# QuantImmuBench 补充: 逐病人 Spearman 分布 (最强单工具 + SURV6 geomean fusion, max 维)\n")
        f.write(f"# 输入={Path(args.input).name}; DS2 患者={pats}\n")
        f.write(f"# 最强单工具={single_col}(限全覆盖{full_cov_n}池); SURV6 geomean 维度={surv6_used}\n")
        f.write(f"# single_rho/fusion_rho=病人内裸 Spearman(score,Elispot); *_lenctrl=控肽长偏相关(B2, ctrl={args.ctrl}, ≥4点)\n")
        f.write("# 验大纲'逐病人剧烈波动'口径\n")
        dist_df.to_csv(f, index=False)
    print(f"[saved] {dist_csv}  shape={dist_df.shape}")

    single_dist = _dist_stats([single_by.get(p, np.nan) for p in pats])
    fusion_dist = _dist_stats([fusion_by.get(p, np.nan) for p in pats])
    single_dist_len = _dist_stats([single_len_by.get(p, np.nan) for p in pats])
    fusion_dist_len = _dist_stats([fusion_len_by.get(p, np.nan) for p in pats])
    print(f"[dist] 最强单工具 per-patient 裸: min={single_dist['min']} "
          f"max={single_dist['max']} median={single_dist['median']}")
    print(f"[dist] SURV6 geomean per-patient 裸: min={fusion_dist['min']} "
          f"max={fusion_dist['max']} median={fusion_dist['median']}")

    # ── ③ ds1 复现: 查有无 ds1 pooling 冻结表 ───────────────────────────────────
    ds1_candidates = [
        ROOT / "data" / "frozen" / "pooled_clean_ds1_9mer.csv",
        ROOT / "data" / "frozen" / "pooled_peptide_level_30tools_ds1.csv",
        ROOT / "data" / "frozen" / "ds1_pooled_peptide_level_30tools.csv",
        ROOT / "data" / "frozen" / "pooled_peptide_level_30tools_dataset1.csv",
    ]
    ds1_found = [str(p.name) for p in ds1_candidates if p.exists()]
    if ds1_found:
        ds1_status = f"AVAILABLE — 发现 ds1 冻结表 {ds1_found}, 可补 ds1 复现 (需补实现)"
    else:
        ds1_status = ("GATED — ds1 (Elispot_Dataset1.xlsx) 未在官方 pooling 管线冻结, "
                      "需先跑 ds1 30 工具 pooling→冻结, 独立 gated, 本脚本不造数")
    print(f"[ds1] {ds1_status}")

    # ── summary.json ────────────────────────────────────────────────────────────
    summary = {
        "section": "supplementary (Pearson contrast + per-patient distribution + ds1 gated)",
        "input": Path(args.input).name,
        "patients": pats,
        "pearson_vs_spearman": {
            "cross_tool_rank_consistency_spearman": r6(consistency, 4),
            "note": "跨 30 工具的 Pearson↔Spearman ρ̄ 排序一致性 (高=两指标结论一致)",
        },
        "perpatient_distribution": {
            "strongest_single": single_col,
            "strongest_single_full_cov_pool": full_cov_n,
            "single_rho_dist_raw": single_dist,
            "single_rho_dist_lenctrl": single_dist_len,
            "surv6_geomean_dims": surv6_used,
            "surv6_geomean_dims_TODO": "SURV6 成员=selection, 待袁/朱确认",
            "fusion_rho_dist_raw": fusion_dist,
            "fusion_rho_dist_lenctrl": fusion_dist_len,
            "outline_ref": "大纲称逐病人 Spearman 0.17–0.80 剧烈波动; 数字以本表实测为准",
        },
        "ds1_status": ds1_status,
        "note_30seed": "30 种子明细见 R6_robustness_official_results.csv (R6 已出)",
        "note_paired": "配对检验完整统计见 R7_paired_significance_official.* (R7 已出)",
        "seed": args.seed,
    }
    out_json = out_dir / "R9_supplementary_official.summary.json"

    def _jd(o):
        if isinstance(o, np.integer): return int(o)
        if isinstance(o, np.floating): return float(o)
        if isinstance(o, (np.bool_,)): return bool(o)
        return str(o)

    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False, default=_jd)
    print(f"[saved] {out_json}")
    print("[DONE] R9")


if __name__ == "__main__":
    main()
