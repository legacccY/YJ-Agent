#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Phase0 命门核查：IEDB tcell_full_v3 连续/序数/响应频率填充率（肿瘤子集）。
回答退守路线 A(序数三档)/B(响应频率)/连续 SFC 的 GT 可得性 ≥10³ 跨 ≥2 study?
0 GPU。读 IEDB tcell_full_v3.zip（双层表头）。
用法: python analysis/phase0_fillrate_check.py <path_to_tcell_full_v3.zip_or_csv>
输出: analysis/phase0_fillrate_actual.csv + 打印 PASS/FAIL 判断
"""
import sys, zipfile, io, re
import pandas as pd
import numpy as np
from pathlib import Path
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

HERE = Path(__file__).resolve().parent
OUT = HERE / "phase0_fillrate_actual.csv"

def load(src):
    src = Path(src)
    if src.suffix == ".zip":
        zf = zipfile.ZipFile(src)
        name = [n for n in zf.namelist() if n.lower().endswith(".csv")][0]
        print(f"[info] zip 内 csv = {name}")
        raw = zf.read(name)
        # IEDB tcell_full = 双层表头
        df = pd.read_csv(io.BytesIO(raw), header=[0,1], low_memory=False)
    else:
        df = pd.read_csv(src, header=[0,1], low_memory=False)
    # 拼接 MultiIndex 列名 -> "L0 - L1"
    df.columns = [f"{a} - {b}".strip() if "Unnamed" not in str(b) else str(a).strip()
                  for a,b in df.columns]
    return df

def find_col(df, *keywords):
    """返回第一个列名同时含全部 keyword(小写) 的列"""
    for c in df.columns:
        cl = c.lower()
        if all(k.lower() in cl for k in keywords):
            return c
    return None

def main():
    if len(sys.argv) < 2:
        sys.exit("用法: python analysis/phase0_fillrate_check.py <tcell_full_v3.zip|csv>")
    df = load(sys.argv[1])
    print(f"[info] 总行数 {len(df)}, 列数 {len(df.columns)}")
    print("[info] 列名样例(前40):")
    for c in df.columns[:40]:
        print("   ", c)

    # 定位关键列（IEDB 字段名可能各版本不同，多关键词 fuzzy）
    col_qual = find_col(df, "qualitative") or find_col(df, "measurement", "qualitative")
    col_quant = find_col(df, "quantitative")
    col_tested = find_col(df, "subjects tested") or find_col(df, "number", "tested")
    col_resp = (find_col(df, "subjects positive") or find_col(df, "subjects responded")
                or find_col(df, "number", "responded"))
    col_method = find_col(df, "method") or find_col(df, "assay", "method")
    col_disease = find_col(df, "disease")
    col_pmid = find_col(df, "pubmed") or find_col(df, "reference", "id") or find_col(df, "pmid")
    col_epi = find_col(df, "epitope", "name") or find_col(df, "description") or find_col(df, "linear", "sequence")
    print("\n[定位列]")
    for nm,c in [("qualitative",col_qual),("quantitative",col_quant),("tested",col_tested),
                 ("responded",col_resp),("method",col_method),("disease",col_disease),
                 ("pmid",col_pmid),("epitope",col_epi)]:
        print(f"  {nm:12s} -> {c}")

    rows = []
    def rec(section, key, val):
        rows.append({"section":section,"key":key,"value":val})

    # 肿瘤子集 mask
    if col_disease:
        dl = df[col_disease].astype(str).str.lower()
        tumor = dl.str.contains("cancer|neoplasm|tumor|tumour|carcinoma|melanoma|sarcoma|leukemia|lymphoma|myeloma|glioma", regex=True, na=False)
    else:
        tumor = pd.Series([False]*len(df))
    print(f"\n[肿瘤子集] {int(tumor.sum())} / {len(df)} 行")
    rec("subset","total_rows",len(df))
    rec("subset","tumor_rows",int(tumor.sum()))

    # === 1. 序数三档 (A) ===
    if col_qual:
        vc_all = df[col_qual].value_counts(dropna=False)
        print("\n=== 1. Qualitative Measure 全库 value_counts ===")
        print(vc_all.head(20).to_string())
        for k,v in vc_all.head(20).items():
            rec("qualitative_all",str(k),int(v))
        vc_t = df.loc[tumor, col_qual].value_counts(dropna=False)
        print("\n=== Qualitative Measure 肿瘤子集 ===")
        print(vc_t.head(20).to_string())
        for k,v in vc_t.head(20).items():
            rec("qualitative_tumor",str(k),int(v))
        # 三档 intermediate 专项 + 跨 PMID
        for lvl in ["high","intermediate","low"]:
            m = tumor & df[col_qual].astype(str).str.lower().str.contains(lvl, na=False) & \
                df[col_qual].astype(str).str.lower().str.contains("positive", na=False)
            n = int(m.sum())
            npmid = df.loc[m, col_pmid].nunique() if col_pmid else -1
            print(f"  肿瘤 Positive-{lvl}: n={n}, 跨PMID={npmid}")
            rec("ordinal_tumor",f"positive_{lvl}_n",n)
            rec("ordinal_tumor",f"positive_{lvl}_pmid",npmid)

    # === 2. 连续 quantitative (原 Phase0) ===
    if col_quant:
        nonnull_all = df[col_quant].notna().sum()
        nonnull_t = df.loc[tumor, col_quant].notna().sum()
        print(f"\n=== 2. Quantitative measurement 非空: 全库 {nonnull_all}/{len(df)} ({100*nonnull_all/len(df):.1f}%), 肿瘤 {nonnull_t}/{int(tumor.sum())} ===")
        rec("quantitative","nonnull_all",int(nonnull_all))
        rec("quantitative","nonnull_tumor",int(nonnull_t))
        if col_pmid:
            rec("quantitative","tumor_nonnull_pmid", int(df.loc[tumor & df[col_quant].notna(), col_pmid].nunique()))

    # === 3. 响应频率 (B) ===
    if col_tested and col_resp:
        t = pd.to_numeric(df[col_tested], errors="coerce")
        r = pd.to_numeric(df[col_resp], errors="coerce")
        both = t.notna() & r.notna()
        ge4 = both & (t >= 4)
        ge4_t = ge4 & tumor
        print(f"\n=== 3. responded/tested: 两者非空 {int(both.sum())}, ≥4 tested {int(ge4.sum())}, ≥4 tested 肿瘤 {int(ge4_t.sum())} ===")
        rec("freq","both_nonnull",int(both.sum()))
        rec("freq","ge4_tested_all",int(ge4.sum()))
        rec("freq","ge4_tested_tumor",int(ge4_t.sum()))
        if col_pmid:
            rec("freq","ge4_tumor_pmid",int(df.loc[ge4_t, col_pmid].nunique()))
        # responded/tested 比值直方图（肿瘤 ≥4）
        frac = (r[ge4_t]/t[ge4_t]).dropna()
        if len(frac):
            mid = ((frac>0.2)&(frac<0.8)).mean()
            print(f"  肿瘤≥4 比值: n={len(frac)}, 中间值(0.2-0.8)占比={mid:.1%}, 直方:")
            h = pd.cut(frac, bins=[0,0.01,0.2,0.5,0.8,0.99,1.0], include_lowest=True).value_counts().sort_index()
            print(h.to_string())
            rec("freq","mid_frac_ratio",round(float(mid),3))
            for k,v in h.items():
                rec("freq_hist",str(k),int(v))

    pd.DataFrame(rows).to_csv(OUT, index=False)
    print(f"\n[saved] {OUT}")

    # === 判定 ===
    print("\n" + "="*60)
    print("命门判定（≥10³ 跨 ≥2 study）:")
    def getval(sec,key):
        for x in rows:
            if x["section"]==sec and x["key"]==key: return x["value"]
        return None
    ord_int = getval("ordinal_tumor","positive_intermediate_n")
    quant_t = getval("quantitative","nonnull_tumor")
    freq_t = getval("freq","ge4_tested_tumor")
    print(f"  A 序数中间档(肿瘤): n={ord_int} → {'退化二分风险' if (ord_int or 0)<100 else '中间档够'}")
    print(f"  B 响应频率(肿瘤≥4): n={freq_t}")
    print(f"  连续 quantitative(肿瘤): n={quant_t}")
    print("="*60)

if __name__ == "__main__":
    main()
