#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
QuantImmune Phase0 命门实测：IEDB tcell_full_v3 连续 magnitude 填充率 + 肿瘤/neoepitope 子集量。

承重前提（袁 QuantImmune 立项地基）：
  连续 ground-truth magnitude（SFC/%tetramer/SI）在肿瘤/neoepitope 子集
  跨 ≥2 独立 study (PMID) 且 ≥10^3 正例 → PASS；否则 FAIL（命中率回退方向=拍板点）。

输入：data/tcell_full_v3.csv（IEDB 全量 T cell assay 导出，双表头 header=[0,1]，~573k 行 1.34GB）。
  不联网。zip 下载/解压由主线另行完成。

输出：analysis/phase0_fillrate_measured.csv（分层计数表）+ stdout PASS/FAIL 判定。

红线：数字一律从 csv 实测，不臆想；分块读防爆内存；列名用实测扁平名。
"""
import sys
from pathlib import Path
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
CSV = ROOT / "data" / "tcell_full_v3.csv"
OUT = HERE / "phase0_fillrate_measured.csv"

# 实测扁平列名（Section - Field）
C_QUANT = "Assay - Quantitative measurement"
C_METHOD = "Assay - Method"
C_QUAL = "Assay - Qualitative Measurement"
C_PEP = "Epitope - Name"
C_REL = "Related Object - Epitope Relation"
C_DIS = "1st in vivo Process - Disease"
C_DIS2 = "2nd in vivo Process - Disease"
C_ORG = "Epitope - Source Organism"
C_PMID = "Reference - PMID"

USE = [C_QUANT, C_METHOD, C_QUAL, C_PEP, C_REL, C_DIS, C_DIS2, C_ORG, C_PMID]

# 肿瘤 disease 关键词（宽匹配）
TUMOR_KW = ["cancer", "carcinoma", "melanoma", "neoplasm", "tumor", "tumour",
            "leukemia", "leukaemia", "lymphoma", "glioma", "glioblastoma",
            "sarcoma", "myeloma", "blastoma", "adenocarcinoma", "malignant",
            "metasta"]
# neoepitope / mutant 关键词（Epitope Relation / Source Organism）
NEO_KW = ["neo", "mutant", "mutation", "tumor", "neoplasm"]

# 连续 magnitude 相关功能 assay（强度量）
MAG_METHODS = ["elispot", "tetramer", "multimer", "ics", "intracellular"]


def is_tumor(disease):
    if not isinstance(disease, str):
        return False
    d = disease.lower()
    return any(k in d for k in TUMOR_KW)


def is_neo(rel, org):
    s = ""
    if isinstance(rel, str):
        s += rel.lower()
    if isinstance(org, str):
        s += " " + org.lower()
    return any(k in s for k in NEO_KW)


def is_mag_method(m):
    if not isinstance(m, str):
        return False
    ml = m.lower()
    return any(k in ml for k in MAG_METHODS)


def main():
    if not CSV.exists():
        sys.exit(f"[ERR] {CSV} 不存在；先解压 iedb_tcell_full_v3.zip。")

    agg = {
        "total_rows": 0,
        "quant_notnull": 0,
        "quant_notnull_pos": 0,
        "mag_method_rows": 0,            # ELISPOT/tetramer/ICS 总行
        "mag_quant_notnull": 0,         # 上者 quant 非空
        "mag_quant_pos": 0,             # 上者 quant 非空 + Positive
        "tumor_mag_quant": 0,           # 肿瘤 disease + mag method + quant 非空
        "tumor_mag_quant_pos": 0,
        "neo_mag_quant": 0,             # neoepitope(relation/org) + mag + quant
        "neo_mag_quant_pos": 0,
        "tumor_OR_neo_mag_quant_pos": 0,
    }
    pmids_all_magpos = set()
    pmids_tumor_magpos = set()
    pmids_neo_magpos = set()
    pmids_tumorORneo_magpos = set()
    peps_tumorORneo_magpos = set()
    method_quant = {}   # method -> [total, quant_notnull]

    reader = pd.read_csv(CSV, header=[0, 1], chunksize=50000, low_memory=False)
    for chunk in reader:
        chunk.columns = [f"{a} - {b}" for a, b in chunk.columns]
        for c in USE:
            if c not in chunk.columns:
                sys.exit(f"[ERR] 缺列 {c}；实际列样例: {chunk.columns[:5].tolist()}")
        n = len(chunk)
        agg["total_rows"] += n

        quant = pd.to_numeric(chunk[C_QUANT], errors="coerce")
        qnn = quant.notna()
        pos = chunk[C_QUAL].astype(str).str.lower().str.startswith("pos")
        agg["quant_notnull"] += int(qnn.sum())
        agg["quant_notnull_pos"] += int((qnn & pos).sum())

        magm = chunk[C_METHOD].apply(is_mag_method)
        agg["mag_method_rows"] += int(magm.sum())
        magq = magm & qnn
        agg["mag_quant_notnull"] += int(magq.sum())
        agg["mag_quant_pos"] += int((magq & pos).sum())

        # per-method quant fill
        for m, sub in chunk.groupby(C_METHOD):
            mq = pd.to_numeric(sub[C_QUANT], errors="coerce").notna()
            t, q = method_quant.get(m, [0, 0])
            method_quant[m] = [t + len(sub), q + int(mq.sum())]

        tumor = chunk[C_DIS].apply(is_tumor) | chunk[C_DIS2].apply(is_tumor)
        neo = [is_neo(r, o) for r, o in zip(chunk[C_REL], chunk[C_ORG])]
        neo = pd.Series(neo, index=chunk.index)

        tmq = magq & tumor
        nmq = magq & neo
        agg["tumor_mag_quant"] += int(tmq.sum())
        agg["tumor_mag_quant_pos"] += int((tmq & pos).sum())
        agg["neo_mag_quant"] += int(nmq.sum())
        agg["neo_mag_quant_pos"] += int((nmq & pos).sum())
        tn = magq & (tumor | neo) & pos
        agg["tumor_OR_neo_mag_quant_pos"] += int(tn.sum())

        # PMID/peptide 集合
        for mask, pset in [(magq & pos, pmids_all_magpos),
                           (tmq & pos, pmids_tumor_magpos),
                           (nmq & pos, pmids_neo_magpos),
                           (tn, pmids_tumorORneo_magpos)]:
            for v in chunk.loc[mask, C_PMID].dropna().unique():
                pset.add(str(v))
        for v in chunk.loc[tn, C_PEP].dropna().unique():
            p = str(v).strip().upper()
            if p:
                peps_tumorORneo_magpos.add(p)

    # 写分层表
    rows = []
    for k, v in agg.items():
        rows.append({"metric": k, "count": v})
    rows.append({"metric": "distinct_PMID_mag_quant_pos_allDisease", "count": len(pmids_all_magpos)})
    rows.append({"metric": "distinct_PMID_tumor_mag_quant_pos", "count": len(pmids_tumor_magpos)})
    rows.append({"metric": "distinct_PMID_neo_mag_quant_pos", "count": len(pmids_neo_magpos)})
    rows.append({"metric": "distinct_PMID_tumorORneo_mag_quant_pos", "count": len(pmids_tumorORneo_magpos)})
    rows.append({"metric": "distinct_peptides_tumorORneo_mag_quant_pos", "count": len(peps_tumorORneo_magpos)})
    pd.DataFrame(rows).to_csv(OUT, index=False)

    # per-method 表
    mq_df = pd.DataFrame(
        [{"method": m, "total": t, "quant_notnull": q,
          "fill_pct": round(100 * q / t, 3) if t else 0}
         for m, (t, q) in sorted(method_quant.items(), key=lambda x: -x[1][1])]
    )
    mq_df.to_csv(HERE / "phase0_method_quant_fill.csv", index=False)

    print("=== IEDB tcell_full_v3 实测（全 csv，分块）===")
    print(f"总行数: {agg['total_rows']}  (API 报 573409，应吻合)")
    print(f"quant 非空(全方法): {agg['quant_notnull']}  其中 Positive: {agg['quant_notnull_pos']}")
    print(f"ELISPOT/tetramer/ICS 行: {agg['mag_method_rows']}  quant非空: {agg['mag_quant_notnull']}  +Positive: {agg['mag_quant_pos']}")
    print(f"\n--- 肿瘤/neoepitope 子集（命门）---")
    print(f"肿瘤(disease) × mag × quant非空: {agg['tumor_mag_quant']}  +Pos: {agg['tumor_mag_quant_pos']}  PMID数: {len(pmids_tumor_magpos)}")
    print(f"neo(relation/org) × mag × quant非空: {agg['neo_mag_quant']}  +Pos: {agg['neo_mag_quant_pos']}  PMID数: {len(pmids_neo_magpos)}")
    print(f"(肿瘤 OR neo) × mag × quant非空 × Positive: {agg['tumor_OR_neo_mag_quant_pos']}  PMID数: {len(pmids_tumorORneo_magpos)}  unique肽: {len(peps_tumorORneo_magpos)}")
    print("\n--- 前 8 方法 quant 填充 ---")
    print(mq_df.head(8).to_string(index=False))

    # 判据
    npos = agg["tumor_OR_neo_mag_quant_pos"]
    nstudy = len(pmids_tumorORneo_magpos)
    verdict = "PASS" if (npos >= 1000 and nstudy >= 2) else "FAIL"
    print(f"\n=== PHASE0 判据（肿瘤/neo 连续 magnitude 正例 ≥10^3 且 ≥2 study）===")
    print(f"正例={npos}  study={nstudy}  →  {verdict}")
    print(f"\n表 -> {OUT}\n方法填充 -> {HERE/'phase0_method_quant_fill.csv'}")


if __name__ == "__main__":
    main()
