#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""result_to_raw.py - bridge DeepNetBim official result_prediction.txt -> deepnetbim_raw.csv
   official output cols (TAB): mhc, sequence, pred_affinity, pred_immuno, immuno_probability
   parse_output.py expects raw cols: mhc, sequence, immuno_probability
"""
import sys, csv
src = sys.argv[1]
dst = sys.argv[2]
rows = list(csv.DictReader(open(src), delimiter="\t"))
with open(dst, "w", newline="") as fo:
    w = csv.writer(fo)
    w.writerow(["mhc", "sequence", "immuno_probability"])
    for r in rows:
        w.writerow([r["mhc"].strip(), r["sequence"].strip(), r["immuno_probability"].strip()])
print("bridged", len(rows), "rows ->", dst)
