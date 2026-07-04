#!/usr/bin/env python
"""
deepHLApan indel 覆盖修复 patch。
把 deepHLApan 对 28 indel 肽的 9mer 子肽 context-free 单肽 immunogenic score
patch 进 merged_all_tools_30_official_covfix.csv 的 MT_deepHLApan 列（只填 NaN，不覆盖）。
键 = (MT_Subpeptide, HLA_Allele 带星)。deepHLApan 输出 HLA 无星 → 补星。
用法: python scripts/patch_deephlapan_indel.py
"""
import re
import pandas as pd

MERGED = "scripts/out/merged_all_tools_30_official_covfix.csv"
RAW = "scripts/out_official/coverage_fix/deephlapan_out_INDEL/deephlapan_input_INDEL_predicted_result.csv"
COL = "MT_deepHLApan"   # deepHLApan headline = immunogenic score (context-free 单肽)

STAR_RE = re.compile(r"^(HLA-[ABC])(\d)")
def add_star(h):
    return STAR_RE.sub(r"\1*\2", str(h))

def main():
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
    m.to_csv(MERGED, index=False)
    print(f"[patch] MT_deepHLApan 填 {filled} 格; 覆盖肽 {cov_before} -> {cov_after}")
    print(f"[lut] indel (subpep,HLA) 对: {len(lut)}")

if __name__ == "__main__":
    main()
