# -*- coding: utf-8 -*-
"""
patch_covfix_8to11.py — QuantImmuBench 覆盖修复 8-11mer 口径(另窗)
服务: quantimmu-bench §2.2 可变窗补充口径 lever=补满覆盖(8-11mer)

【2026-07-04 迁移】原在 _scratch/patch_covfix_8to11.py, 提升进 scripts/ (消灭游击层)。
  ROOT = parents[1] 在 _scratch/ 与 scripts/ 下均解析到 QuantImmuBench/ (两者都在 ROOT 下一层),
  故迁移后路径不变、行为一致。计算逻辑(star/PATCHES/填 NaN)一字未动, 仅新增 --in/--out 参数。
  原 _scratch/ 那份保留(归档是主线的活)。

把主窗 9mer coverage_fix 的 <tool>_raw_FULL130.csv 新分 patch 进 merged_30 的
【副本】merged_all_tools_30_official_covfix_8to11.csv (绝不覆写 canonical)。
只填原表 NaN 格; 匹配键=(MT_Subpeptide, HLA_Allele带星)。

阶段1(本脚本, coverage-only 基线): 仅 patch 9mer 覆盖修复分 → 缺肽经 max-pool 用 9mer
  子肽在 --w811 口径下被覆盖上(Entry 48 line57「求覆盖不缺」路)。
阶段2(后续): C 类工具(netMHCstabpan/Seq2Neo/DeepNetBim)8-11mer 重跑分再叠加 patch,
  产严格 8-11 口径。本脚本可接受额外 <tool>_raw_FULL130_8to11.csv 覆盖同 col。

符号约定(Entry 48): MHCnuggets=-ic50; netMHCstabpan=pred; 其余直接用值列。

用法:
  python scripts/patch_covfix_8to11.py                     # 默认: base -> _covfix_8to11.csv
  python scripts/patch_covfix_8to11.py --in base.csv --out staging.csv   # rebuild 驱动用它写 staging
"""
import re
import argparse
import pathlib
import pandas as pd
import numpy as np

ROOT = pathlib.Path(__file__).resolve().parents[1]  # QuantImmuBench/
CANON = ROOT / "scripts" / "out" / "merged_all_tools_30_official.csv"
CF = ROOT / "scripts" / "out_official" / "coverage_fix"
OUT = ROOT / "scripts" / "out" / "merged_all_tools_30_official_covfix_8to11.csv"


def star(h: str) -> str:
    return re.sub(r"^(HLA-[ABC])(\d)", r"\1*\2", str(h))


# (col_in_merged, raw_file, pep_col, hla_col, value_col, sign)
PATCHES = [
    ("MT_MHCnuggets",    "mhcnuggets_raw_FULL130.csv",    "peptide",  "HLA_Allele", "ic50",              -1),
    ("MT_MHCseqNet",     "mhcseqnet_raw_FULL130.csv",     "peptide",  "HLA_Allele", "prob",               1),
    ("MT_netMHCstabpan", "netmhcstabpan_raw_FULL130.csv", "peptide",  "HLA_Allele", "pred",               1),
    ("MT_andy90",        "andy90_raw_FULL130.csv",        "peptide",  "HLA",        "amplitude",          1),
    ("MT_MUNIS",         "munis_raw_FULL130.csv",         "peptide",  "HLA_Allele", "score",              1),
    ("MT_ImmuGenX",      "immugenx_raw_FULL130.csv",      "peptide",  "HLA_Allele", "ImmugenX",           1),
    ("MT_DeepNetBim",    "deepnetbim_raw_FULL130.csv",    "sequence", "mhc",        "immuno_probability", 1),
    ("MT_Seq2Neo",       "seq2neo_raw_FULL130.csv",       "Peptide",  "HLA",        "immunogenicity",     1),
    ("MT_HLAthena",      "hlathena_raw_FULL130.csv",      "peptide",  "HLA_Allele", "MSi",                1),
]

# 阶段2 严格 8-11 口径升级(C 类: canonical 里 9mer-only 但工具支持 8-11 的重跑分)。
# 在基础 9mer patch 之后再叠加(只填 NaN → 9mer 行已被基础 patch 填好保持不动,
# 8/10/11 行由此填上)→ 这 2 工具在 8-11 口径下有真实多长度子肽分,不再暗藏只 9mer。
PATCHES_8TO11 = [
    ("MT_netMHCstabpan", "netmhcstabpan_raw_FULL130_8to11.csv", "peptide", "HLA_Allele", "pred",          1),
    ("MT_Seq2Neo",       "seq2neo_raw_FULL130_8to11.csv",       "Peptide", "HLA",        "immunogenicity", 1),
]


def main():
    ap = argparse.ArgumentParser(
        description="9 工具 8-11mer 覆盖修复分 patch 进 merged 副本 (只填 NaN, canonical 不动)")
    ap.add_argument("--in", dest="in_path", default=str(CANON),
                    help="输入 base merged csv")
    ap.add_argument("--out", dest="out_path", default=str(OUT),
                    help="输出 _covfix_8to11 副本 csv")
    args = ap.parse_args()
    canon_path = args.in_path
    out_path = args.out_path

    m = pd.read_csv(canon_path, low_memory=False)
    m["_key"] = m["MT_Subpeptide"].astype(str) + "|" + m["HLA_Allele"].astype(str)
    print(f"[canon] rows={len(m)} cols={len(m.columns)}")

    for col, rawf, pc, hc, vc, sign in PATCHES:
        if col not in m.columns:
            print(f"[SKIP] {col} 不在 merged 列"); continue
        raw = pd.read_csv(CF / rawf)
        v = pd.to_numeric(raw[vc], errors="coerce") * sign
        amap = {}
        for p, h, val in zip(raw[pc].astype(str), raw[hc].astype(str), v):
            if pd.notna(val):
                amap[f"{p}|{star(h)}"] = float(val)
        before_nan = m[col].isna().sum()
        # fill only NaN cells whose key is in amap
        mask = m[col].isna() & m["_key"].isin(amap)
        m.loc[mask, col] = m.loc[mask, "_key"].map(amap)
        after_nan = m[col].isna().sum()
        print(f"[{col:18s}] raw_keys={len(amap):5d} filled={before_nan-after_nan:5d} "
              f"(NaN {before_nan}->{after_nan})")

    # 阶段2: 叠加严格 8-11 重跑分(若 raw 已就绪)
    for col, rawf, pc, hc, vc, sign in PATCHES_8TO11:
        rawp = CF / rawf
        if not rawp.exists():
            print(f"[8-11 SKIP] {col}: {rawf} 未就绪(重跑未回)"); continue
        raw = pd.read_csv(rawp)
        v = pd.to_numeric(raw[vc], errors="coerce") * sign
        amap = {}
        for p, h, val in zip(raw[pc].astype(str), raw[hc].astype(str), v):
            if pd.notna(val):
                amap.setdefault(f"{p}|{star(h)}", float(val))  # 去重键保首个
        before_nan = m[col].isna().sum()
        mask = m[col].isna() & m["_key"].isin(amap)
        m.loc[mask, col] = m.loc[mask, "_key"].map(amap)
        after_nan = m[col].isna().sum()
        print(f"[8-11 {col:15s}] raw_keys={len(amap):5d} filled(8/10/11)={before_nan-after_nan:5d} "
              f"(NaN {before_nan}->{after_nan})")

    m = m.drop(columns=["_key"])
    m.to_csv(out_path, index=False, encoding="utf-8")
    print(f"\n[OUT] {out_path}  rows={len(m)}")


if __name__ == "__main__":
    main()
