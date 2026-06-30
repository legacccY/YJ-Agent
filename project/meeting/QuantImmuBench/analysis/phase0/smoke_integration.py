#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
smoke_integration.py
服务: quantimmu-bench / Phase 0 收口集成烟测闸 (主窗 W0 orchestrator)

地基冻结前的放行闸: 验 merged_30 -> p0e pooled -> per-patient Spearman
能在 9 患者全算出非 NaN, 且无 silent dropna (退回旧肽集). 闸过才解锁 R1-R9。

================== 跑序 ==================
  1) python scripts/merge_official_30.py            (产 merged_all_tools_30_official.csv)
  2) python analysis/phase0/p0e_pool_to_peptide.py  (产 pooled_peptide_level_30tools.csv)
  3) python analysis/phase0/smoke_integration.py    (本闸)

================== 闸门 (全 PASS 才放行) ==================
  [S1] pooled 表存在且 130 行
  [S2] GT 9 患者全在 (101,102,104-110), 每患者 ≥8 肽
  [S3] 选 ≥1 个 130-全覆盖工具 (如 IEDB_Calis), 每 op 在 9 患者全算出非 NaN
       (Fisher-z 等权聚合也非 NaN)
  [S4] 无 silent dropna: 每患者参与 Spearman 的肽数 == 该患者 GT 肽数
       (pooled 分非 NaN 数 == GT 肽数; 缺 1 即报警 -> 说明长表未覆盖该肽)
  [S5] 补跑肽真的进了分析: 43 补跑肽中 ≥1 在每患者(若该患者有补跑肽)的有效集里
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parents[2]
FROZEN = ROOT / "data" / "frozen"
POOLED = FROZEN / "pooled_peptide_level_30tools.csv"
GT = FROZEN / "ds2_official_groundtruth.csv"
RERUN = FROZEN / "RERUN_PEPTIDE_LIST.csv"

EXPECT_PATIENTS = [101, 102, 104, 105, 106, 107, 108, 109, 110]
# 130-全覆盖参照工具 (官方已补跑齐). 收口时 30 工具齐可换更多。
ANCHOR_TOOLS = ["IEDB_Calis", "ImmuneApp", "PRIME"]
OPS = ["max", "mean", "geomean", "top3mean"]


def spearman_np(x, y):
    x = np.asarray(x, float); y = np.asarray(y, float)
    m = ~(np.isnan(x) | np.isnan(y))
    x, y = x[m], y[m]
    n = len(x)
    if n < 3 or len(np.unique(x)) < 2 or len(np.unique(y)) < 2:
        return np.nan, n
    rx = pd.Series(x).rank().values; ry = pd.Series(y).rank().values
    rx -= rx.mean(); ry -= ry.mean()
    den = np.sqrt((rx**2).sum() * (ry**2).sum())
    return (float((rx*ry).sum()/den) if den else np.nan), n


def fisher_z_mean(rhos):
    r = np.asarray([x for x in rhos if not np.isnan(x)], float)
    if len(r) == 0:
        return np.nan
    r = np.clip(r, -0.999999, 0.999999)
    z = np.arctanh(r)
    return float(np.tanh(z.mean()))


def main():
    fails = []

    # [S1]
    if not POOLED.exists():
        raise SystemExit(f"[S1] FAIL: pooled 不存在 {POOLED} (先跑 merge_official_30 + p0e)")
    pooled = pd.read_csv(POOLED)
    pooled["Patient_ID"] = pooled["Patient_ID"].astype(int)
    if len(pooled) != 130:
        fails.append(f"[S1] pooled 行数={len(pooled)} != 130")
    else:
        print(f"[S1] PASS: pooled 130 行")

    gt = pd.read_csv(GT); gt["Patient_ID"] = gt["Patient_ID"].astype(int)

    # [S2]
    pats = sorted(gt["Patient_ID"].unique())
    if pats != EXPECT_PATIENTS:
        fails.append(f"[S2] 患者集 {pats} != {EXPECT_PATIENTS}")
    per_pat_n = gt.groupby("Patient_ID").size()
    bad = per_pat_n[per_pat_n < 8]
    if len(bad):
        fails.append(f"[S2] 患者 <8 肽: {bad.to_dict()}")
    if not fails or all("[S2]" not in f for f in fails):
        print(f"[S2] PASS: 9 患者 每患者肽数 {per_pat_n.to_dict()}")

    # [S3]+[S4] per-patient Spearman, 无 silent dropna
    print("\n[S3/S4] === per-patient Spearman (anchor 工具) ===")
    for tool in ANCHOR_TOOLS:
        for op in OPS:
            col = f"{tool}_{op}"
            if col not in pooled.columns:
                fails.append(f"[S3] 缺列 {col}")
                continue
            rhos = {}
            dropna_warn = []
            for pid in EXPECT_PATIENTS:
                sub = pooled[pooled["Patient_ID"] == pid]
                gt_n = int((gt["Patient_ID"] == pid).sum())
                valid_n = int(sub[col].notna().sum())
                if valid_n != gt_n:
                    dropna_warn.append(f"P{pid}:{valid_n}/{gt_n}")
                rho, n = spearman_np(sub[col].values, sub["Elispot"].values)
                rhos[pid] = rho
            n_nan = sum(np.isnan(v) for v in rhos.values())
            fz = fisher_z_mean(list(rhos.values()))
            tag = "✅" if n_nan == 0 and not np.isnan(fz) else "❌"
            print(f"   {col:24s} {tag} 9患者NaN={n_nan} Fisher-z均={fz:.4f}"
                  + (f"  ⚠ dropna {dropna_warn}" if dropna_warn else ""))
            if n_nan > 0:
                fails.append(f"[S3] {col} 有 {n_nan} 患者 Spearman=NaN")
            if dropna_warn:
                fails.append(f"[S4] {col} silent dropna: {dropna_warn}")

    # [S5] 补跑肽真进分析
    rer = pd.read_csv(RERUN)
    rerun_keys = set(rer["mut_key"])
    pooled_keys = set(pooled["mut_key"]) if "mut_key" in pooled.columns else set()
    if not pooled_keys:
        # pooled 用 Patient_ID|Peptide_ID 重建
        pooled["mut_key"] = pooled["Patient_ID"].astype(str) + "|" + pooled["Peptide_ID"].astype(str)
        pooled_keys = set(pooled["mut_key"])
    rerun_in = rerun_keys & pooled_keys
    print(f"\n[S5] 补跑肽进 pooled: {len(rerun_in)}/{len(rerun_keys)}")
    if len(rerun_in) != len(rerun_keys):
        fails.append(f"[S5] 补跑肽缺失 pooled: {sorted(rerun_keys - pooled_keys)}")
    # 用 anchor 工具确认补跑肽有真分 (非全 NaN)
    anchor_col = f"{ANCHOR_TOOLS[0]}_max"
    if anchor_col in pooled.columns:
        rr = pooled[pooled["mut_key"].isin(rerun_keys)]
        n_scored = int(rr[anchor_col].notna().sum())
        print(f"[S5] 补跑肽在 {anchor_col} 有分: {n_scored}/{len(rerun_keys)}")
        if n_scored < len(rerun_keys):
            fails.append(f"[S5] {anchor_col} 补跑肽有 {len(rerun_keys)-n_scored} 个无分")

    # ── 汇总 ──
    print("\n" + "=" * 50)
    if fails:
        print(f"[GATE] ❌ FAIL ({len(fails)} 条) — 不放行 R1-R9:")
        for f in fails:
            print("   -", f)
        raise SystemExit(1)
    print("[GATE] ✅ PASS — 集成烟测全闸过, 可解锁 R1-R9 分析")


if __name__ == "__main__":
    main()
