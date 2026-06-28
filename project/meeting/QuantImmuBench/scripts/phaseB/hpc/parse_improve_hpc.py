# -*- coding: utf-8 -*-
"""
parse_improve_hpc.py — Phase B：把 IMPROVE Predict 输出解析回 bb_idx 对齐的合表列。

在 HPC 上跑（由 run_improve_hpc.sh 调用）。读 Predict 的 Simple 输出 tsv
（含 Mut_peptide / Norm_peptide / HLA_allele / mean_prediction_rf），
按 (Mut|Norm|HLA) 键经 improve_input_map.csv 把分数广播回所有共享该肽的 bb_idx。

产出: IMPROVE_101102.csv  列 = bb_idx, MT_IMPROVE_mean_prediction_rf
  - 列名 MT_IMPROVE_mean_prediction_rf 与原合表完全一致（只填 MT 列，无 WT）。
  - 方向照原：mean_prediction_rf 越高 → 免疫原性越强（连续 0-1），不翻转。

服务: quantimmu-bench Phase B IMPROVE 101/102 重推理（lever=IMPROVE）。
"""
import os
import sys
import csv
import json
import argparse

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

OUT_COL = "MT_IMPROVE_mean_prediction_rf"


def norm_hla(s):
    return str(s).replace("*", "").strip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pred", required=True, help="IMPROVE Predict 输出 tsv（含 mean_prediction_rf）")
    ap.add_argument("--map-csv", required=True, help="prep 产的 improve_input_map.csv")
    ap.add_argument("--out", required=True, help="输出 IMPROVE_101102.csv")
    args = ap.parse_args()

    # 读映射 (key -> [bb_idx])
    key2bb = {}
    with open(args.map_csv, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            key2bb[r["key"]] = json.loads(r["bb_indices"])
    print(f"[parse] 映射键数={len(key2bb)} <- {args.map_csv}")

    # 读 Predict 输出，按 (Mut|Norm|HLA) 取 mean_prediction_rf
    bb2score = {}
    n_pred = 0
    n_nokey = 0
    with open(args.pred, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f, delimiter="\t"):
            mut = str(r.get("Mut_peptide", "")).strip()
            norm = str(r.get("Norm_peptide", "")).strip()
            hla = norm_hla(r.get("HLA_allele", ""))
            val = r.get("mean_prediction_rf", "")
            if val in ("", "nan", "NaN", None):
                continue
            n_pred += 1
            key = f"{mut}|{norm}|{hla}"
            bbs = key2bb.get(key)
            if bbs is None:
                n_nokey += 1
                continue
            for bb in bbs:
                bb2score[bb] = val

    # 写输出
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["bb_idx", OUT_COL])
        for bb, val in bb2score.items():
            w.writerow([bb, val])

    print(f"[parse] Predict 有效行={n_pred} | 未匹配映射键={n_nokey} | 回填 bb_idx={len(bb2score)}")
    print(f"[parse] 写 {args.out}（列: bb_idx, {OUT_COL}）")
    # 自校验：前 3 行
    for bb, val in list(bb2score.items())[:3]:
        print(f"        bb_idx={bb}\t{OUT_COL}={val}")


if __name__ == "__main__":
    main()
