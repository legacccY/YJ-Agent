#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
build_ds1_newcut.py — DS1 (Elispot_Dataset1.xlsx) 适配器

把 DS1（6 例黑色素瘤 / 82 肽 / 全 9mer / ELISpot 全阳）转成与 DS2
(`data/frozen/newcut_subpep_hla_{MT,WT}.for_tools.csv`) **完全同 schema** 的
for_tools 表 + groundtruth 表，供全 30 工具批跑（S3，拍板点）。

DS1 与 DS2 的关键差异（决定适配逻辑）：
  - DS1 每条肽本身就是 9mer（非长肽 SLP 滑窗）→ 每肽只有「1 个窗」，
    window_size=9, subpep_pos=0, subpep_seq = 该 9mer 本身。
  - 突变位点由 MT vs WT 单点 diff 求得（0-indexed）→ abs_subpep_pos。
  - source 统一标 SLP（与 DS2 的 short-epitope-from-SLP 口径一致，便于同栏合并）。
  - Patient_ID 保持 1-6，与 DS2 的 101-110 天然不撞。

输出（不覆盖任何 DS2 文件，全部带 .DS1. 中缀）：
  data/frozen/newcut_subpep_hla_MT.DS1.for_tools.csv
  data/frozen/newcut_subpep_hla_WT.DS1.for_tools.csv
  data/frozen/ds1_official_groundtruth.csv

用法：
  python scripts/build_ds1_newcut.py --check     # 只烟测，不写盘（打印统计 + schema 校验）
  python scripts/build_ds1_newcut.py             # 真正写盘
"""
import argparse
import csv
import os
import sys

import openpyxl

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)  # QuantImmuBench/
SRC_XLSX = os.path.join(ROOT, "data", "Elispot_Dataset1.xlsx")
FROZEN = os.path.join(ROOT, "data", "frozen")

# DS2 MT for_tools 的权威列顺序（11 列；build 前会用它比对 DS2 真表头，防漂移）
FOR_TOOLS_COLS = [
    "mut_key", "Patient_ID", "Peptide_ID", "Vaccine_Peptide", "subpep_seq",
    "subpep_pos", "window_size", "hla_allele_std", "abs_subpep_pos",
    "source", "consistency_flag",
]
# DS2 WT for_tools 的权威列顺序（13 列，与 MT 不对称：多 WT_FullPeptide + side）。
# _build_wt_lookup 按 (mut_key, subpep_pos, hla) 查 (subpep_seq=WT子肽, WT_FullPeptide=WT全长)。
# 约定同 DS2：Vaccine_Peptide = MT 全长（配对锚），subpep_seq/WT_FullPeptide = WT 序列，side='WT'。
WT_FOR_TOOLS_COLS = [
    "mut_key", "Patient_ID", "Peptide_ID", "Vaccine_Peptide", "WT_FullPeptide",
    "subpep_seq", "subpep_pos", "window_size", "hla_allele_std", "side",
    "abs_subpep_pos", "source", "consistency_flag",
]
# DS2 groundtruth 的权威列顺序
GT_COLS = [
    "mut_key", "Patient_ID", "Peptide_ID", "Vaccine_Peptide", "Short_Epitope",
    "Gene_and_Protein_Change", "Elispot", "Treatment", "Variant_Type",
    "Mutation_type", "TPM_PurifiedTumorRNA", "CCF", "Clonal",
    "HLA_of_best_short_epitope",
]

DS2_MT = os.path.join(FROZEN, "newcut_subpep_hla_MT.for_tools.csv")
DS2_WT = os.path.join(FROZEN, "newcut_subpep_hla_WT.for_tools.csv")
DS2_GT = os.path.join(FROZEN, "ds2_official_groundtruth.csv")


def load_ds1():
    """读 DS1 xlsx → list[dict]，每条含 pid/gene/mutation/mt/wt/hlas/elispot/uniprot/pos。"""
    wb = openpyxl.load_workbook(SRC_XLSX, data_only=True)
    ws = wb["All_Peptides"]
    rows = list(ws.iter_rows(values_only=True))
    recs = []
    for r in rows[1:]:
        pid, gene, mut, mt, wt, plen = r[0], r[1], r[2], r[3], r[4], r[5]
        hlas = [a for a in r[6:12] if a]          # HLA Allele-1..6，去空
        elispot, uniprot, pos = r[12], r[13], r[14]
        recs.append(dict(pid=int(pid), gene=gene, mutation=mut, mt=mt, wt=wt,
                         plen=int(plen), hlas=hlas, elispot=elispot,
                         uniprot=uniprot, pos=pos))
    return recs


def mut_pos0(mt, wt):
    """MT vs WT 单点 diff 的 0-indexed 位置；非单点 → 抛错（DS1 已核 82/82 单点）。"""
    diffs = [i for i in range(len(mt)) if i < len(wt) and mt[i] != wt[i]]
    if len(diffs) != 1:
        raise ValueError(f"非单点突变 MT={mt} WT={wt} diffs={diffs}")
    return diffs[0]


def peptide_id(rec, idx):
    """构造稳定 Peptide_ID：<pid>-<gene>-<pos>（无 gene/pos 时退化到序号）。"""
    tag = rec["gene"] or "NA"
    pos = rec["pos"] if rec["pos"] not in (None, "") else idx
    return f"{rec['pid']}-{tag}-{pos}"


def build_rows(recs):
    """→ (mt_rows, wt_rows, gt_rows)，均为 list[dict]，键对齐 FOR_TOOLS_COLS/GT_COLS。

    DS1 源数据含 1 对同序列/HLA 但 ELISpot 不同的记录（GRM4 患者6，381 vs 286，同一肽
    两次测量）→ base Peptide_ID 撞车时加 -r<n> 后缀保唯一，82 条全留不合并不丢；
    工具输入按肽×HLA 去重（newtools universe）只算一次，评估各配自己的 ELISpot。
    """
    mt_rows, wt_rows, gt_rows = [], [], []
    id_seen = {}
    for idx, rec in enumerate(recs, start=1):
        pid = rec["pid"]
        base_id = peptide_id(rec, idx)
        id_seen[base_id] = id_seen.get(base_id, 0) + 1
        pep_id = base_id if id_seen[base_id] == 1 else f"{base_id}-r{id_seen[base_id]}"
        mkey = f"{pid}|{pep_id}"
        ap = mut_pos0(rec["mt"], rec["wt"])
        # for_tools：每 HLA 展开一行
        for allele in rec["hlas"]:
            common = dict(mut_key=mkey, Patient_ID=pid, Peptide_ID=pep_id,
                          subpep_pos=0, window_size=rec["plen"],
                          hla_allele_std=allele, abs_subpep_pos=ap,
                          source="SLP", consistency_flag="OK")
            # MT 行（11 列）：Vaccine_Peptide/subpep_seq 均为 MT 9mer
            mt_rows.append(dict(common, Vaccine_Peptide=rec["mt"], subpep_seq=rec["mt"]))
            # WT 行（13 列，对齐 DS2 WT）：Vaccine_Peptide=MT 全长(配对锚)，
            # subpep_seq/WT_FullPeptide=WT 9mer，side='WT' → 与 MT 同 (mut_key,pos,hla) 键可配
            wt_rows.append(dict(common, Vaccine_Peptide=rec["mt"],
                                WT_FullPeptide=rec["wt"], subpep_seq=rec["wt"], side="WT"))
        # groundtruth：每肽 1 行（DS1 缺的临床字段留空）
        gt_rows.append(dict(
            mut_key=mkey, Patient_ID=pid, Peptide_ID=pep_id,
            Vaccine_Peptide=rec["mt"], Short_Epitope=rec["mt"],
            Gene_and_Protein_Change=f"{rec['gene']}|{rec['mutation']}",
            Elispot=rec["elispot"], Treatment="", Variant_Type="SNV",
            Mutation_type="", TPM_PurifiedTumorRNA="", CCF="", Clonal="",
            HLA_of_best_short_epitope="",
        ))
    return mt_rows, wt_rows, gt_rows


def write_csv(path, cols, rows):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)


def read_header(path):
    with open(path, encoding="utf-8") as f:
        return next(csv.reader(f))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true",
                    help="只烟测不写盘：打印统计 + 对 DS2 校验 schema")
    args = ap.parse_args()

    recs = load_ds1()
    mt_rows, wt_rows, gt_rows = build_rows(recs)

    # --- schema 校验：拿 DS2 真表头逐列比对，防我方列漂移（MT/WT/GT 三张分别核）---
    ds2_ft_hdr = read_header(DS2_MT)
    ds2_wt_hdr = read_header(DS2_WT)
    ds2_gt_hdr = read_header(DS2_GT)
    ft_ok = (ds2_ft_hdr == FOR_TOOLS_COLS)
    wt_ok = (ds2_wt_hdr == WT_FOR_TOOLS_COLS)
    gt_ok = (ds2_gt_hdr == GT_COLS)

    # --- 统计 ---
    from collections import Counter
    pc = Counter(r["pid"] for r in recs)
    per_patient_mt = Counter(r["Patient_ID"] for r in mt_rows)

    print("=" * 60)
    print("DS1 适配器烟测" if args.check else "DS1 适配器写盘")
    print("=" * 60)
    print(f"源肽数            : {len(recs)}  (预期 82)")
    print(f"患者分布(ID:肽数) : {dict(sorted(pc.items()))}")
    print(f"MT for_tools 行数 : {len(mt_rows)}  (预期 325)")
    print(f"WT for_tools 行数 : {len(wt_rows)}  (预期 325)")
    print(f"groundtruth 行数  : {len(gt_rows)}  (预期 82)")
    print(f"每患者 MT 行数    : {dict(sorted(per_patient_mt.items()))}")
    print("-" * 60)
    print(f"MT for_tools schema 对 DS2 : {'PASS' if ft_ok else 'FAIL'}")
    if not ft_ok:
        print(f"   DS2 : {ds2_ft_hdr}")
        print(f"   本表: {FOR_TOOLS_COLS}")
    print(f"WT for_tools schema 对 DS2 : {'PASS' if wt_ok else 'FAIL'}")
    if not wt_ok:
        print(f"   DS2 : {ds2_wt_hdr}")
        print(f"   本表: {WT_FOR_TOOLS_COLS}")
    print(f"groundtruth schema 对 DS2  : {'PASS' if gt_ok else 'FAIL'}")
    if not gt_ok:
        print(f"   DS2 : {ds2_gt_hdr}")
        print(f"   本表: {GT_COLS}")
    print("-" * 60)
    print("样本 MT 行:", {k: mt_rows[0][k] for k in FOR_TOOLS_COLS})
    print("样本 WT 行:", {k: wt_rows[0][k] for k in WT_FOR_TOOLS_COLS})

    ok = ft_ok and wt_ok and gt_ok
    if args.check:
        print("\n[--check] 未写盘。")
        return 0 if ok else 1

    out_mt = os.path.join(FROZEN, "newcut_subpep_hla_MT.DS1.for_tools.csv")
    out_wt = os.path.join(FROZEN, "newcut_subpep_hla_WT.DS1.for_tools.csv")
    out_gt = os.path.join(FROZEN, "ds1_official_groundtruth.csv")
    write_csv(out_mt, FOR_TOOLS_COLS, mt_rows)
    write_csv(out_wt, WT_FOR_TOOLS_COLS, wt_rows)
    write_csv(out_gt, GT_COLS, gt_rows)
    print(f"\n已写:\n  {out_mt}\n  {out_wt}\n  {out_gt}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
