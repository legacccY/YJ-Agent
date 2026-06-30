#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
p0a_build_groundtruth.py
服务: quantimmu-bench / Phase 0 数据地基重建 (03_EXPERIMENT_PLAN.md §3)

从官方 ELISPOT xlsx 的「In Vitro」sheet 构建冻结的 ground-truth 表。

================== 输入 (只读, 禁改) ==================
  data/OFFICIAL_DO_NOT_TOUCH/ELISPOT_OFFICIAL_Braun2025_MOESM4.xlsx
  sheet = "In Vitro"  (130 肽 / 9 患者: 101,102,104-110，缺 103)

================== 输出 ==================
  data/frozen/ds2_official_groundtruth.csv
    列: mut_key, Patient_ID, Peptide_ID, Vaccine_Peptide, Short_Epitope,
        Gene_and_Protein_Change, Elispot, Treatment, Variant_Type,
        Mutation_type, TPM_PurifiedTumorRNA, CCF, Clonal,
        HLA_of_best_short_epitope
  mut_key = "<Patient_ID>|<Peptide_ID>" (如 "101|16097-101-3")

================== 校验门 (assert + print) ==================
  [P0-a1] 行数 == 130
  [P0-a2] Elispot 非空 == 130
  [P0-a3] Elispot>0 == 118; Elispot<=0 == 12
  [P0-a4] 患者集 == {101,102,104,105,106,107,108,109,110}
  [P0-a5] 每患者肽数全 >= 4

================== 跑法 ==================
  python analysis/phase0/p0a_build_groundtruth.py
"""

import sys
from pathlib import Path

import pandas as pd

# UTF-8 stdout (Windows 必要)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

HERE = Path(__file__).resolve().parent
ROOT = Path(__file__).resolve().parents[2]   # QuantImmuBench 根

OFFICIAL_XLSX = (ROOT / "data" / "OFFICIAL_DO_NOT_TOUCH"
                 / "ELISPOT_OFFICIAL_Braun2025_MOESM4.xlsx")
SHEET = "In Vitro"
FROZEN_DIR = ROOT / "data" / "frozen"
OUT_CSV = FROZEN_DIR / "ds2_official_groundtruth.csv"

EXPECTED_PATIENTS = {101, 102, 104, 105, 106, 107, 108, 109, 110}

# 输出列 (源列名 -> 输出列名, 此处同名直读)
SOURCE_COLS = [
    "Patient_ID", "Peptide_ID", "Vaccine_Peptide", "Short_Epitope",
    "Gene_and_Protein_Change", "Elispot", "Treatment", "Variant_Type",
    "Mutation_type", "TPM_PurifiedTumorRNA", "CCF", "Clonal",
    "HLA_of_best_short_epitope",
]


def main():
    if not OFFICIAL_XLSX.exists():
        raise SystemExit(f"[ERR] 官方 xlsx 不存在: {OFFICIAL_XLSX}")

    print(f"[info] 读官方 (只读): {OFFICIAL_XLSX}")
    df = pd.read_excel(OFFICIAL_XLSX, sheet_name=SHEET, engine="openpyxl")
    print(f"[info] sheet='{SHEET}' 原始 shape={df.shape}")

    # 必需列检查 (fail-loud)
    missing = [c for c in SOURCE_COLS if c not in df.columns]
    if missing:
        print(f"[ERR] 缺列: {missing}")
        print(f"[ERR] 实际列: {list(df.columns)}")
        raise SystemExit("[ERR] 官方 xlsx 列名与预期不符，停止 (不臆造)")

    out = df[SOURCE_COLS].copy()

    # Patient_ID 转 int (用于 mut_key 与患者集校验)
    out["Patient_ID"] = out["Patient_ID"].astype(int)
    out["Peptide_ID"] = out["Peptide_ID"].astype(str)
    out["mut_key"] = out["Patient_ID"].astype(str) + "|" + out["Peptide_ID"]

    # 列顺序: mut_key 在首
    cols = ["mut_key"] + SOURCE_COLS
    out = out[cols]

    # ── 校验门 ────────────────────────────────────────────────────────────
    n = len(out)
    assert n == 130, f"[P0-a1] FAIL: 行数={n} != 130"
    print(f"[P0-a1] PASS: 行数 == 130")

    n_elispot = int(out["Elispot"].notna().sum())
    assert n_elispot == 130, f"[P0-a2] FAIL: Elispot 非空={n_elispot} != 130"
    print(f"[P0-a2] PASS: Elispot 非空 == 130")

    n_pos = int((out["Elispot"] > 0).sum())
    n_nonpos = int((out["Elispot"] <= 0).sum())
    assert n_pos == 118, f"[P0-a3] FAIL: Elispot>0={n_pos} != 118"
    assert n_nonpos == 12, f"[P0-a3] FAIL: Elispot<=0={n_nonpos} != 12"
    print(f"[P0-a3] PASS: Elispot>0 == 118; Elispot<=0 == 12")

    patients = set(out["Patient_ID"].unique())
    assert patients == EXPECTED_PATIENTS, (
        f"[P0-a4] FAIL: 患者集={sorted(patients)} != {sorted(EXPECTED_PATIENTS)}")
    print(f"[P0-a4] PASS: 患者集 == {sorted(EXPECTED_PATIENTS)}")

    per_pt = out.groupby("Patient_ID").size()
    min_n = int(per_pt.min())
    assert min_n >= 4, f"[P0-a5] FAIL: 最小患者肽数={min_n} < 4\n{per_pt.to_string()}"
    print(f"[P0-a5] PASS: 每患者肽数全 >= 4 (min={min_n})")
    print("[info] 逐患者肽数:")
    for pid, cnt in per_pt.items():
        print(f"         P{pid}: {int(cnt)}")

    # ── 写出 ─────────────────────────────────────────────────────────────
    FROZEN_DIR.mkdir(parents=True, exist_ok=True)
    out.to_csv(OUT_CSV, index=False, encoding="utf-8")
    print(f"\n[saved] {OUT_CSV}  shape={out.shape}")
    print("[DONE] p0a_build_groundtruth 完成")


if __name__ == "__main__":
    main()
