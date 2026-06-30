#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
p0_reuse_decision.py
服务: quantimmu-bench / Phase 0 数据地基重建 (03_EXPERIMENT_PLAN.md §3)

逐肽判定: 旧预测能否复用 / 需重跑 (全工具 or 仅新 HLA 等位)。

================== 输入 ==================
  data/frozen/ds2_official_groundtruth.csv    (p0a 产, 130 肽真源)
  data/frozen/patient_hla.csv                 (p0b 产, 逐患者新 HLA-I 等位)
  scripts/out/merged_all_tools_29tools.xlsx   (旧预测, 子肽×HLA 长表)
    用 Patient_ID/Peptide_ID 构旧肽键集; HLA_Allele 列取旧等位集

================== 判定逻辑 ==================
  新肽不在旧预测            -> rerun_full     (全工具补跑, 用全部新等位)
  患者 HLA 变更 (P104) 的肽 -> rerun_partial  (仅补跑新增/变更等位, 如 A3001)
  其余                     -> reuse          (旧预测可直接复用)

================== 输出 ==================
  data/frozen/REUSE_DECISION.csv
    列: mut_key, Patient_ID, Peptide_ID, status, reason,
        in_old_predictions, hla_changed
  data/frozen/RERUN_PEPTIDE_LIST.csv
    列: mut_key, Patient_ID, Peptide_ID, Vaccine_Peptide, status,
        hla_alleles_to_run (分号连), n_alleles

================== 已核地基事实 (校验门断言/预期) ==================
  - 29 肽在旧预测完全缺失 -> rerun_full (预期 29)
  - HLA 新旧仅 P104 DIFF (新 A3001 vs 旧 A0301); P104 共 17 肽 -> rerun_partial
  - 校验门: assert reuse + rerun_full + rerun_partial == 130

================== 跑法 ==================
  python analysis/phase0/p0_reuse_decision.py
"""

import sys
from pathlib import Path

import pandas as pd

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

HERE = Path(__file__).resolve().parent
ROOT = Path(__file__).resolve().parents[2]

FROZEN_DIR = ROOT / "data" / "frozen"
GT_CSV = FROZEN_DIR / "ds2_official_groundtruth.csv"
HLA_CSV = FROZEN_DIR / "patient_hla.csv"
OLD_MERGED = ROOT / "scripts" / "out" / "merged_all_tools_29tools.xlsx"

OUT_DECISION = FROZEN_DIR / "REUSE_DECISION.csv"
OUT_RERUN = FROZEN_DIR / "RERUN_PEPTIDE_LIST.csv"

EXPECTED_RERUN_FULL = 29       # 旧预测缺失肽 (地基事实)
EXPECTED_HLA_DIFF_PATIENT = 104


def _need(p, who):
    if not p.exists():
        raise SystemExit(f"[ERR] 依赖缺失: {p}  (先跑 {who})")


def main():
    _need(GT_CSV, "p0a_build_groundtruth.py")
    _need(HLA_CSV, "p0b_patient_hla.py")
    if not OLD_MERGED.exists():
        raise SystemExit(f"[ERR] 旧预测不存在: {OLD_MERGED}")

    gt = pd.read_csv(GT_CSV)
    gt["Patient_ID"] = gt["Patient_ID"].astype(int)
    gt["Peptide_ID"] = gt["Peptide_ID"].astype(str)
    print(f"[info] 新 GT 肽数: {len(gt)}")

    hla = pd.read_csv(HLA_CSV)
    hla["Patient_ID"] = hla["Patient_ID"].astype(int)
    new_hla_by_pt = (hla.groupby("Patient_ID")["hla_allele_std"]
                        .apply(lambda s: set(s)).to_dict())

    # ── 旧预测: 肽键集 + 逐患者旧等位集 ──────────────────────────────────
    print(f"[info] 读旧预测 (大文件, 取必要列): {OLD_MERGED}")
    old = pd.read_excel(OLD_MERGED, engine="openpyxl",
                        usecols=["Patient_ID", "Peptide_ID", "HLA_Allele"])
    old["Patient_ID"] = old["Patient_ID"].astype(int)
    old["Peptide_ID"] = old["Peptide_ID"].astype(str)
    old["mut_key"] = old["Patient_ID"].astype(str) + "|" + old["Peptide_ID"]
    old_keys = set(old["mut_key"].unique())
    print(f"[info] 旧预测 distinct 肽键: {len(old_keys)}")

    old_hla_by_pt = (old.dropna(subset=["HLA_Allele"])
                        .groupby("Patient_ID")["HLA_Allele"]
                        .apply(lambda s: set(str(x).strip() for x in s)).to_dict())

    # ── HLA 变更检测 (新 vs 旧) ───────────────────────────────────────────
    hla_changed_pt = {}    # pid -> bool
    added_by_pt = {}       # pid -> set(新增/变更等位 = 新 - 旧)
    print(f"\n[info] HLA 新旧比对:")
    for pid in sorted(new_hla_by_pt):
        new_set = new_hla_by_pt.get(pid, set())
        old_set = old_hla_by_pt.get(pid, set())
        changed = (new_set != old_set)
        hla_changed_pt[pid] = changed
        added_by_pt[pid] = new_set - old_set
        if changed:
            print(f"         P{pid} DIFF  新-旧={sorted(new_set - old_set)}  "
                  f"旧-新={sorted(old_set - new_set)}")
        else:
            print(f"         P{pid} match ({len(new_set)} 等位)")

    diff_patients = sorted(p for p, c in hla_changed_pt.items() if c)
    print(f"[info] HLA 变更患者: {diff_patients} (地基事实: 仅 P{EXPECTED_HLA_DIFF_PATIENT})")
    if diff_patients != [EXPECTED_HLA_DIFF_PATIENT]:
        print(f"[warn] HLA 变更患者集 {diff_patients} != 预期 [{EXPECTED_HLA_DIFF_PATIENT}] "
              f"-- 与地基事实不符, 请人工复核 (不擅自掩盖)")

    # ── 逐肽判定 ─────────────────────────────────────────────────────────
    dec_rows, rerun_rows = [], []
    for r in gt.itertuples(index=False):
        pid = int(r.Patient_ID)
        key = r.mut_key
        in_old = key in old_keys
        changed = hla_changed_pt.get(pid, False)
        new_set = new_hla_by_pt.get(pid, set())

        if not in_old:
            status, reason = "rerun_full", "new peptide absent from old predictions"
            alleles = sorted(new_set)
        elif changed:
            status, reason = "rerun_partial", f"patient HLA changed (P{pid}), rerun new allele(s)"
            alleles = sorted(added_by_pt.get(pid, set()))
        else:
            status, reason = "reuse", "present in old predictions, HLA unchanged"
            alleles = []

        dec_rows.append({
            "mut_key": key, "Patient_ID": pid, "Peptide_ID": r.Peptide_ID,
            "status": status, "reason": reason,
            "in_old_predictions": in_old, "hla_changed": changed,
        })
        if status != "reuse":
            rerun_rows.append({
                "mut_key": key, "Patient_ID": pid, "Peptide_ID": r.Peptide_ID,
                "Vaccine_Peptide": r.Vaccine_Peptide, "status": status,
                "hla_alleles_to_run": ";".join(alleles), "n_alleles": len(alleles),
            })

    dec = pd.DataFrame(dec_rows)
    rerun = pd.DataFrame(rerun_rows)

    # ── 校验门 ────────────────────────────────────────────────────────────
    n_reuse = int((dec["status"] == "reuse").sum())
    n_full = int((dec["status"] == "rerun_full").sum())
    n_partial = int((dec["status"] == "rerun_partial").sum())
    print(f"\n[info] 判定汇总: reuse={n_reuse}  rerun_full={n_full}  rerun_partial={n_partial}")
    print(f"[info] rerun_full 预期 {EXPECTED_RERUN_FULL} (旧预测缺失肽)")
    if n_full != EXPECTED_RERUN_FULL:
        print(f"[warn] rerun_full={n_full} != 预期 {EXPECTED_RERUN_FULL} -- 请人工复核地基")

    assert n_reuse + n_full + n_partial == 130, (
        f"[P0-reuse] FAIL: reuse+rerun={n_reuse + n_full + n_partial} != 130")
    print(f"[P0-reuse] PASS: reuse + rerun_full + rerun_partial == 130")

    # ── 写出 ─────────────────────────────────────────────────────────────
    FROZEN_DIR.mkdir(parents=True, exist_ok=True)
    dec.to_csv(OUT_DECISION, index=False, encoding="utf-8")
    rerun.to_csv(OUT_RERUN, index=False, encoding="utf-8")
    print(f"\n[saved] {OUT_DECISION}  shape={dec.shape}")
    print(f"[saved] {OUT_RERUN}  shape={rerun.shape}  (待补跑肽)")
    print("[DONE] p0_reuse_decision 完成")


if __name__ == "__main__":
    main()
