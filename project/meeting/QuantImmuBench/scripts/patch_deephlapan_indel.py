#!/usr/bin/env python
"""
deepHLApan indel 覆盖修复 patch。
把 deepHLApan 对 28 indel 肽的 9mer 子肽 context-free 单肽 immunogenic score
patch 进 merged 副本的 MT_deepHLApan 列（只填 NaN，不覆盖）。
键 = (MT_Subpeptide, HLA_Allele 带星)。deepHLApan 输出 HLA 无星 → 补星。

参数化 I/O（2026-07-04 消灭原地覆写）：
  --in  输入 merged_covfix (默认 scripts/out/merged_all_tools_30_official_covfix.csv)
  --out 输出 merged 副本 (默认 *_covfix_final.csv, **不再覆写 --in**)
  --raw deepHLApan 预测结果 csv (默认 INDEL raw; SNV110 那 1 长肽的 90 子肽在
        deephlapan_out_SNV110/... 另一 raw, 需第二次调用本脚本补, 见 rebuild_canonical.py)
  计算逻辑 (lut 构建 / add_star / 只填 NaN 不覆盖) 一字未动, 仅改 I/O 路径。

用法:
  python scripts/patch_deephlapan_indel.py                    # 默认: 读 _covfix 写 _covfix_final (INDEL raw)
  python scripts/patch_deephlapan_indel.py --in A.csv --out B.csv --raw <SNV110_result.csv>
"""
import re
import argparse
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]   # QuantImmuBench/
DEFAULT_MERGED = ROOT / "scripts" / "out" / "merged_all_tools_30_official_covfix.csv"
DEFAULT_OUT = ROOT / "scripts" / "out" / "merged_all_tools_30_official_covfix_final.csv"
DEFAULT_RAW = (ROOT / "scripts" / "out_official" / "coverage_fix"
               / "deephlapan_out_INDEL" / "deephlapan_input_INDEL_predicted_result.csv")
COL = "MT_deepHLApan"   # deepHLApan headline = immunogenic score (context-free 单肽)

STAR_RE = re.compile(r"^(HLA-[ABC])(\d)")
def add_star(h):
    return STAR_RE.sub(r"\1*\2", str(h))

def main():
    ap = argparse.ArgumentParser(
        description="deepHLApan raw 分 patch 进 merged 副本 MT_deepHLApan (只填 NaN, 不覆写输入)")
    ap.add_argument("--in", dest="in_path", default=str(DEFAULT_MERGED),
                    help="输入 merged_covfix csv")
    ap.add_argument("--out", dest="out_path", default=str(DEFAULT_OUT),
                    help="输出 merged 副本 csv (不覆写 --in)")
    ap.add_argument("--raw", dest="raw_path", default=str(DEFAULT_RAW),
                    help="deepHLApan 预测结果 csv (INDEL 或 SNV110)")
    args = ap.parse_args()
    MERGED = args.in_path      # 输入路径 (原硬编码常量 → 参数)
    RAW = args.raw_path        # deepHLApan raw (原硬编码 INDEL → 参数, 支持 SNV110)
    OUT = args.out_path        # 输出路径 (不再等于 MERGED, 消灭原地覆写)

    # ── 以下填 NaN 计算逻辑一字未动 (lut 构建 / add_star / 只填 NaN 不覆盖) ──
    m = pd.read_csv(MERGED, low_memory=False)
    raw = pd.read_csv(RAW)
    # deepHLApan 输出列: Annotation,HLA,Peptide,binding score,immunogenic score
    lut = {}
    for pep, hla, imm in zip(raw["Peptide"].astype(str),
                             raw["HLA"].map(add_star).astype(str),
                             raw["immunogenic score"].astype(float)):
        lut[(pep, hla)] = imm  # (已核 dup=0)

    cov_before = m.loc[m[COL].notna(), "Peptide_ID"].nunique()
    newvals = m[COL].copy()
    filled = 0
    for i, (pep, hla, cur) in enumerate(zip(m["MT_Subpeptide"].astype(str),
                                            m["HLA_Allele"].astype(str),
                                            m[COL])):
        if pd.isna(cur) and (pep, hla) in lut:
            newvals.iloc[i] = lut[(pep, hla)]
            filled += 1
    m[COL] = newvals
    cov_after = m.loc[m[COL].notna(), "Peptide_ID"].nunique()
    m.to_csv(OUT, index=False)   # 写 OUT (不覆写输入 MERGED)
    print(f"[patch] {RAW.split('/')[-1] if isinstance(RAW, str) else RAW} -> {OUT}")
    print(f"[patch] MT_deepHLApan 填 {filled} 格; 覆盖肽 {cov_before} -> {cov_after}")
    print(f"[lut] indel (subpep,HLA) 对: {len(lut)}")

if __name__ == "__main__":
    main()
