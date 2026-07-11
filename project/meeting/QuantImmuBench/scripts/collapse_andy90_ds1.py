#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
collapse_andy90_ds1.py — andy90 raw (HLA,peptide,amplitude) → bb_idx official 格式

andy90 amplitude = self×foreign/binding，是 (肽,HLA) 纯函数。按 backbone 的
(MT_Subpeptide,HLA)/(WT_Subpeptide,HLA) 逐格 lookup amplitude → MT_Andy90/WT_Andy90，
写成与其他 28 工具一致的 out_ds1_official/Andy90_official.csv（bb_idx,MT_Andy90,WT_Andy90）。
方向：amplitude 越高越免疫原，直接用不翻转。
"""
import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "hpc_official"))
from official_io import load_backbone_bb_order, write_official_mt_wt  # noqa: E402

BACKBONE = ROOT / "scripts" / "out_ds1" / "master_backbone_official.csv"
RAW = ROOT / "HPC" / "deploy" / "andy90_immpred" / "andy90_raw_ds1.csv"
OUT = ROOT / "scripts" / "out_ds1_official" / "Andy90_official.csv"

# raw lookup (peptide, HLA) -> amplitude
lut = {}
with open(RAW, encoding="utf-8", newline="") as f:
    for row in csv.DictReader(f):
        try:
            lut[(row["peptide"], row["HLA"])] = float(row["amplitude"])
        except (ValueError, KeyError):
            continue
print(f"[collapse] andy90 raw lookup: {len(lut)} (肽,HLA) 键")

bb_order = load_backbone_bb_order(BACKBONE)
mt_map, wt_map = {}, {}
alleles = set()
with open(BACKBONE, encoding="utf-8", newline="") as f:
    for row in csv.DictReader(f):
        bb = row["bb_idx"]
        hla = row["HLA_Allele"]
        mt = lut.get((row["MT_Subpeptide"], hla))
        wt = lut.get((row["WT_Subpeptide"], hla))
        if mt is not None:
            mt_map[bb] = mt
            alleles.add(hla)
        if wt is not None:
            wt_map[bb] = wt

write_official_mt_wt(OUT, "Andy90", bb_order, mt_map, wt_map, n_distinct_alleles_mt=len(alleles))
print(f"[collapse] MT填充={len(mt_map)}/{len(bb_order)}  WT={len(wt_map)}  distinct等位={len(alleles)}")
print(f"[collapse] → {OUT}")
