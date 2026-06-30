#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
p0b_patient_hla.py
服务: quantimmu-bench / Phase 0 数据地基重建 (03_EXPERIMENT_PLAN.md §3)

从官方 xlsx「In Vitro」的 6 个 HLA 列 (HLA-1..HLA-6) 构建逐患者 HLA-I 等位表。

================== 输入 (只读, 禁改) ==================
  data/OFFICIAL_DO_NOT_TOUCH/ELISPOT_OFFICIAL_Braun2025_MOESM4.xlsx  sheet="In Vitro"
  HLA 列原始格式如 "B5701" / "A0201" / "C0602"

================== HLA 标准化 ==================
  B5701 -> HLA-B*57:01    A0201 -> HLA-A*02:01    C0602 -> HLA-C*06:02
  只保留 HLA-I 位点 (A/B/C)；空格跳过；去重 (P109 重复 B4402)。

================== 输出 ==================
  data/frozen/patient_hla.csv
    列: Patient_ID, hla_allele_raw, hla_allele_std, locus  (一行=一个等位)

================== 校验门 ==================
  [P0-b1] 每患者等位数 2-6
  [P0-b2] 所有 std 匹配 ^HLA-[ABC]\\*\\d{2}:\\d{2}$
  [P0-b3] 打印逐患者等位清单供人工抽核 (特别 P101/P102/P104)

================== 跑法 ==================
  python analysis/phase0/p0b_patient_hla.py
"""

import re
import sys
from pathlib import Path

import pandas as pd

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

HERE = Path(__file__).resolve().parent
ROOT = Path(__file__).resolve().parents[2]

OFFICIAL_XLSX = (ROOT / "data" / "OFFICIAL_DO_NOT_TOUCH"
                 / "ELISPOT_OFFICIAL_Braun2025_MOESM4.xlsx")
SHEET = "In Vitro"
FROZEN_DIR = ROOT / "data" / "frozen"
OUT_CSV = FROZEN_DIR / "patient_hla.csv"

HLA_COLS = ["HLA-1", "HLA-2", "HLA-3", "HLA-4", "HLA-5", "HLA-6"]

# 原始 raw 解析: 位点字母(A/B/C) + 数字(field1) + 末 2 位(field2)
#   "B5701" -> locus=B field1=57 field2=01
#   "A3001" -> locus=A field1=30 field2=01
# 先剥离可能存在的 HLA- / * / : 前后缀，再按纯 token 解析。
TOKEN_RE = re.compile(r"^([ABC])(\d+?)(\d{2})$", re.IGNORECASE)
STD_RE = re.compile(r"^HLA-[ABC]\*\d{2}:\d{2}$")


def std_hla(raw):
    """B5701 -> HLA-B*57:01；非 A/B/C 或无法解析返回 (None, None)。"""
    if raw is None:
        return None, None
    s = str(raw).strip()
    if s == "" or s.lower() in ("nan", "none"):
        return None, None
    s_clean = s.replace("HLA-", "").replace("HLA_", "").replace("*", "").replace(":", "")
    m = TOKEN_RE.match(s_clean)
    if not m:
        return None, None
    locus = m.group(1).upper()
    field1 = m.group(2)
    field2 = m.group(3)
    if len(field1) < 2:
        field1 = field1.zfill(2)
    std = f"HLA-{locus}*{field1}:{field2}"
    return std, locus


def main():
    if not OFFICIAL_XLSX.exists():
        raise SystemExit(f"[ERR] 官方 xlsx 不存在: {OFFICIAL_XLSX}")

    print(f"[info] 读官方 (只读): {OFFICIAL_XLSX}")
    df = pd.read_excel(OFFICIAL_XLSX, sheet_name=SHEET, engine="openpyxl")

    missing = [c for c in (["Patient_ID"] + HLA_COLS) if c not in df.columns]
    if missing:
        print(f"[ERR] 缺列: {missing}")
        print(f"[ERR] 实际列: {list(df.columns)}")
        raise SystemExit("[ERR] HLA 列名与预期不符，停止 (不臆造)")

    df = df.copy()
    df["Patient_ID"] = df["Patient_ID"].astype(int)

    # 每患者取首行 (同患者 6 个 HLA 列跨肽一致)
    rows = []
    skipped_raw = []
    for pid, grp in df.groupby("Patient_ID"):
        first = grp.iloc[0]
        seen_std = set()
        for col in HLA_COLS:
            raw = first[col]
            std, locus = std_hla(raw)
            if std is None:
                # 空格 / 非 A/B/C 跳过
                if not (raw is None or str(raw).strip() == ""
                        or str(raw).strip().lower() in ("nan", "none")):
                    skipped_raw.append((pid, col, raw))
                continue
            if std in seen_std:        # 去重 (P109 重复 B4402)
                continue
            seen_std.add(std)
            rows.append({
                "Patient_ID": pid,
                "hla_allele_raw": str(raw).strip(),
                "hla_allele_std": std,
                "locus": locus,
            })

    out = pd.DataFrame(rows).sort_values(["Patient_ID", "locus", "hla_allele_std"])
    out = out.reset_index(drop=True)

    if skipped_raw:
        print(f"[warn] {len(skipped_raw)} 个非 A/B/C 或无法解析 token 被跳过:")
        for pid, col, raw in skipped_raw:
            print(f"         P{pid} {col}={raw!r}")

    # ── 校验门 ────────────────────────────────────────────────────────────
    per_pt = out.groupby("Patient_ID").size()
    bad = per_pt[(per_pt < 2) | (per_pt > 6)]
    assert bad.empty, f"[P0-b1] FAIL: 等位数越界 (2-6):\n{bad.to_string()}"
    print(f"[P0-b1] PASS: 每患者等位数 2-6")

    bad_std = out[~out["hla_allele_std"].str.match(STD_RE)]
    assert bad_std.empty, (
        f"[P0-b2] FAIL: std 不匹配正则:\n{bad_std.to_string(index=False)}")
    print(f"[P0-b2] PASS: 所有 std 匹配 ^HLA-[ABC]\\*\\d{{2}}:\\d{{2}}$")

    # [P0-b3] 逐患者清单
    print(f"[P0-b3] 逐患者 HLA-I 等位清单 (人工抽核 P101/P102/P104):")
    for pid, grp in out.groupby("Patient_ID"):
        alleles = grp["hla_allele_std"].tolist()
        flag = "  <== 抽核" if pid in (101, 102, 104) else ""
        print(f"         P{pid} ({len(alleles)}): {', '.join(alleles)}{flag}")

    # ── 写出 ─────────────────────────────────────────────────────────────
    FROZEN_DIR.mkdir(parents=True, exist_ok=True)
    out.to_csv(OUT_CSV, index=False, encoding="utf-8")
    print(f"\n[saved] {OUT_CSV}  shape={out.shape}")
    print("[DONE] p0b_patient_hla 完成")


if __name__ == "__main__":
    main()
