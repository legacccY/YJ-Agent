#!/usr/bin/env python
"""
QuantImmuBench 覆盖修复战役 — 最终 remerge patch（Entry 48 收尾）。

把 8 工具的 FULL130 全量重跑新分 patch 进 merged_all_tools_30_official.csv，
只填 NaN 格（不覆盖已有分），产副本 *_covfix.csv（canonical 不动）。

匹配键 = (MT_Subpeptide, HLA_Allele)。HLA 带星。
符号约定：MHCnuggets = -ic50（越大越强）；其余直接用工具原分。
HLA 加星：DeepNetBim/Seq2Neo 输出无星（HLA-A24:02）→ re.sub 补星；其余已带星。

用法：python scripts/patch_covfix_8tools.py
"""
import re
import sys
import pandas as pd

HERE = "/d/YJ-Agent/project/meeting/QuantImmuBench"  # 仅注释参考，路径用相对
MERGED_IN = "scripts/out/merged_all_tools_30_official.csv"
MERGED_OUT = "scripts/out/merged_all_tools_30_official_covfix.csv"
COVDIR = "scripts/out_official/coverage_fix"

# tool -> (merged 列名, raw 文件前缀, raw pep 列, raw HLA 列, raw 值列, 负号?)
SPEC = {
    "MHCnuggets":    ("MT_MHCnuggets",    "mhcnuggets",    "peptide",  "HLA_Allele", "ic50",                True),
    "MHCseqNet":     ("MT_MHCseqNet",     "mhcseqnet",     "peptide",  "HLA_Allele", "prob",                False),
    "netMHCstabpan": ("MT_netMHCstabpan", "netmhcstabpan", "peptide",  "HLA_Allele", "pred",                False),
    "andy90":        ("MT_andy90",        "andy90",        "peptide",  "HLA",        "amplitude",           False),
    "MUNIS":         ("MT_MUNIS",         "munis",         "peptide",  "HLA_Allele", "score",               False),
    "ImmuGenX":      ("MT_ImmuGenX",      "immugenx",      "peptide",  "HLA_Allele", "ImmugenX",            False),
    "DeepNetBim":    ("MT_DeepNetBim",    "deepnetbim",    "sequence", "mhc",        "immuno_probability",  False),
    "Seq2Neo":       ("MT_Seq2Neo",       "seq2neo",       "Peptide",  "HLA",        "immunogenicity",      False),
}

STAR_RE = re.compile(r"^(HLA-[ABC])(\d)")
def add_star(h):
    return STAR_RE.sub(r"\1*\2", str(h))

def main():
    m = pd.read_csv(MERGED_IN, low_memory=False)
    print(f"merged in: {len(m)} rows, {m['MT_FullPeptide'].nunique()} peptides")
    mkey = list(zip(m["MT_Subpeptide"].astype(str), m["HLA_Allele"].astype(str)))

    summary = []
    for tool, (col, pref, pc, hc, vc, neg) in SPEC.items():
        raw = pd.read_csv(f"{COVDIR}/{pref}_raw_FULL130.csv")
        hla = raw[hc].map(add_star)
        val = -raw[vc].astype(float) if neg else raw[vc].astype(float)
        lut = {}
        for p, h, v in zip(raw[pc].astype(str), hla.astype(str), val):
            lut[(p, h)] = v  # 键唯一(已核 dup=0)

        cov_before = m.loc[m[col].notna(), "MT_FullPeptide"].nunique()
        filled = 0
        newvals = m[col].copy()
        nan_mask = m[col].isna().to_numpy()
        colvals = newvals.to_numpy(dtype=object)
        for i, is_nan in enumerate(nan_mask):
            if not is_nan:
                continue
            v = lut.get(mkey[i])
            if v is not None:
                colvals[i] = v
                filled += 1
        m[col] = pd.array(colvals, dtype="float64")
        cov_after = m.loc[m[col].notna(), "MT_FullPeptide"].nunique()
        summary.append((tool, col, cov_before, cov_after, filled))
        print(f"{tool:14s} {col:20s} pep {cov_before}->{cov_after}  (+{filled} cells)")

    m.to_csv(MERGED_OUT, index=False)
    print(f"\nwrote {MERGED_OUT}: {len(m)} rows")
    print("\n=== SUMMARY (peptide coverage) ===")
    for tool, col, b, a, f in summary:
        flag = "OK" if a == 130 else f"!! only {a}"
        print(f"  {tool:14s} {b}->{a} [{flag}]")

if __name__ == "__main__":
    main()
