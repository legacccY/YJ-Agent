#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
p0c_subpep_expansion.py
服务: quantimmu-bench / Phase 0 数据地基重建 (03_EXPERIMENT_PLAN.md §3)

对需重跑的肽: Vaccine_Peptide 滑窗成短表位 × 患者待补 HLA 等位。
=> 给工具补跑用的输入展开表 (工具补跑本身另跑, 本脚本只产展开表)。

================== 输入 ==================
  data/frozen/RERUN_PEPTIDE_LIST.csv   (p0_reuse_decision 产)
    用 Vaccine_Peptide 滑窗, hla_alleles_to_run 提供目标等位

================== 滑窗口径 ==================
  --window 9     主口径: 仅 9mer 滑窗 (9AAonly, 默认)
  --window 8-11  补充: 8/9/10/11mer 滑窗

================== 输出 ==================
  data/frozen/subpep_hla_expansion.csv
    列: mut_key, Patient_ID, Peptide_ID, Vaccine_Peptide,
        subpep_seq, subpep_pos(1-based), window_size, hla_allele_std

================== 校验门 ==================
  [P0-c1] 每 Peptide_ID >= 1 行
  [P0-c2] 无空 subpep_seq
  [P0-c3] subpep 长度全 ∈ 目标窗

================== 跑法 ==================
  python analysis/phase0/p0c_subpep_expansion.py            # 9mer 默认
  python analysis/phase0/p0c_subpep_expansion.py --window 8-11
"""

import sys
import argparse
from pathlib import Path

import pandas as pd

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

HERE = Path(__file__).resolve().parent
ROOT = Path(__file__).resolve().parents[2]

FROZEN_DIR = ROOT / "data" / "frozen"
RERUN_CSV = FROZEN_DIR / "RERUN_PEPTIDE_LIST.csv"
OUT_CSV = FROZEN_DIR / "subpep_hla_expansion.csv"


def parse_window(spec):
    """'9' -> [9]; '8-11' -> [8,9,10,11]。"""
    spec = str(spec).strip()
    if "-" in spec:
        lo, hi = spec.split("-")
        lo, hi = int(lo), int(hi)
        if lo > hi:
            lo, hi = hi, lo
        return list(range(lo, hi + 1))
    return [int(spec)]


def slide(seq, w):
    """长度 w 滑窗, 返回 [(subpep, pos_1based), ...]。"""
    seq = "" if seq is None else str(seq).strip()
    out = []
    for i in range(0, len(seq) - w + 1):
        out.append((seq[i:i + w], i + 1))
    return out


def main():
    ap = argparse.ArgumentParser(description="子肽×HLA 展开 (重跑肽补推输入)")
    ap.add_argument("--window", default="9",
                    help="滑窗口径: '9' (默认主口径) 或 '8-11' (补充)")
    args = ap.parse_args()

    windows = parse_window(args.window)
    print(f"[info] 滑窗口径: {windows}")

    if not RERUN_CSV.exists():
        raise SystemExit(f"[ERR] 依赖缺失: {RERUN_CSV}  (先跑 p0_reuse_decision.py)")

    rerun = pd.read_csv(RERUN_CSV)
    rerun["Patient_ID"] = rerun["Patient_ID"].astype(int)
    rerun["Peptide_ID"] = rerun["Peptide_ID"].astype(str)
    print(f"[info] 待重跑肽数: {len(rerun)}")

    rows = []
    no_allele = []
    for r in rerun.itertuples(index=False):
        raw_alleles = "" if pd.isna(r.hla_alleles_to_run) else str(r.hla_alleles_to_run)
        alleles = [a for a in raw_alleles.split(";") if a.strip()]
        if not alleles:
            no_allele.append((r.Peptide_ID, r.status))
            continue
        vp = "" if pd.isna(r.Vaccine_Peptide) else str(r.Vaccine_Peptide).strip()
        for w in windows:
            for subpep, pos in slide(vp, w):
                for allele in alleles:
                    rows.append({
                        "mut_key": r.mut_key,
                        "Patient_ID": int(r.Patient_ID),
                        "Peptide_ID": r.Peptide_ID,
                        "Vaccine_Peptide": vp,
                        "subpep_seq": subpep,
                        "subpep_pos": pos,
                        "window_size": w,
                        "hla_allele_std": allele.strip(),
                    })

    if no_allele:
        print(f"[warn] {len(no_allele)} 肽无待补等位 (hla_alleles_to_run 空), 已跳过:")
        for pid, st in no_allele:
            print(f"         {pid} ({st})")

    out = pd.DataFrame(rows)
    if out.empty:
        raise SystemExit("[ERR] 展开结果为空 -- 检查 RERUN 列表与窗口设置")

    # ── 校验门 ────────────────────────────────────────────────────────────
    expanded_peps = set(out["Peptide_ID"].unique())
    # 有等位的重跑肽 (应被展开的肽)
    with_allele = set(
        rerun[rerun["hla_alleles_to_run"].fillna("").str.strip() != ""]["Peptide_ID"]
    )
    missing = with_allele - expanded_peps
    assert not missing, f"[P0-c1] FAIL: 以下肽未展开 (<1 行): {sorted(missing)}"
    print(f"[P0-c1] PASS: 每待重跑肽 (有等位) >= 1 行 (展开肽数={len(expanded_peps)})")

    n_empty = int((out["subpep_seq"].fillna("").str.strip() == "").sum())
    assert n_empty == 0, f"[P0-c2] FAIL: 空 subpep_seq 行数={n_empty}"
    print(f"[P0-c2] PASS: 无空 subpep_seq")

    lens = out["subpep_seq"].str.len()
    bad_len = out[~lens.isin(windows)]
    assert bad_len.empty, (
        f"[P0-c3] FAIL: {len(bad_len)} 行 subpep 长度不在 {windows}:\n"
        f"{bad_len[['Peptide_ID', 'subpep_seq']].head().to_string(index=False)}")
    print(f"[P0-c3] PASS: subpep 长度全 ∈ {windows}")

    # ── 写出 ─────────────────────────────────────────────────────────────
    FROZEN_DIR.mkdir(parents=True, exist_ok=True)
    out.to_csv(OUT_CSV, index=False, encoding="utf-8")
    print(f"\n[saved] {OUT_CSV}  shape={out.shape}")
    print(f"[info] 展开统计: {len(expanded_peps)} 肽 × 窗口{windows} -> {len(out)} 子肽×HLA 行")
    print("[DONE] p0c_subpep_expansion 完成")


if __name__ == "__main__":
    main()
