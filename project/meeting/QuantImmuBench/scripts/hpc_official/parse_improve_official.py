# -*- coding: utf-8 -*-
"""
parse_improve_official.py — IMPROVE predict 输出 -> bb_idx 对齐的官方合表列
服务: quantimmu-bench Phase0 官方数据工具补跑舰队 (lever=IMPROVE)

输入:
  --pred    predict_local.py 的 Simple 输出 tsv (含 Mut_peptide/Norm_peptide/HLA_allele/mean_prediction_rf)
  --map-csv scripts/out_official/improve_input_map.csv  (列: key,backbone_indices; key=Mut|WT|HLA, HLA 无星)
  --master  scripts/out_official/master_backbone_official.csv  (取全 bb_idx 0..N, 保证输出对齐 1761 行)
  --out     IMPROVE_official.csv

输出:
  列 = bb_idx, MT_IMPROVE
  - 1761 行 (与 master 对齐), 精确(肽,等位)匹配缺 -> 空 (NaN), 禁肽级兜底造数。
  - MT_IMPROVE = mean_prediction_rf (0-1, 越高越免疫原), 不翻转。
  - WT_IMPROVE: IMPROVE 不产 WT 独立免疫原分 (WT 肽只作 DAI/RankEL_wt 内部特征), 故无此列。

键对齐细节:
  predict 输出 HLA_allele 沿用输入格式 (HLA-A66:01, 无星); master 用 HLA-A*66:01 (有星)。
  但 map 的 key 也是无星 (与 predict 一致), 且 map 已编码 bb_idx 对齐, 故 parse 只走 map, 不直接碰 master 的 HLA 格式。
  WT 为空时 predict 的 Norm_peptide 为空 -> key = Mut||HLA, 与 map 一致。
"""
import os
import sys
import csv
import json
import argparse

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

OUT_COL = "MT_IMPROVE"


def norm_hla(s):
    return str(s).replace("*", "").strip()


def clean_pep(s):
    s = str(s).strip()
    return "" if s.lower() in ("nan", "none", "<na>") else s


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pred", required=True)
    ap.add_argument("--map-csv", required=True)
    ap.add_argument("--master", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    # 1. 读 map: key -> [bb_idx]
    key2bb = {}
    with open(args.map_csv, newline="", encoding="utf-8") as f:
        rd = csv.DictReader(f)
        idx_col = "backbone_indices" if "backbone_indices" in rd.fieldnames else "bb_indices"
        for r in rd:
            key2bb[r["key"]] = json.loads(r[idx_col])
    print(f"[parse] 映射键数={len(key2bb)} (idx列={idx_col}) <- {args.map_csv}")

    # 2. 读 master: 全 bb_idx (保证输出 1761 行对齐)
    all_bb = []
    with open(args.master, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            all_bb.append(int(r["bb_idx"]))
    all_bb = sorted(set(all_bb))
    print(f"[parse] master bb_idx: {len(all_bb)} 行 ({all_bb[0]}..{all_bb[-1]})")

    # 3. 读 predict 输出
    bb2score = {}
    n_pred = n_nokey = 0
    with open(args.pred, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f, delimiter="\t"):
            mut = clean_pep(r.get("Mut_peptide", ""))
            norm = clean_pep(r.get("Norm_peptide", ""))
            hla = norm_hla(r.get("HLA_allele", ""))
            val = str(r.get("mean_prediction_rf", "")).strip()
            if val.lower() in ("", "nan", "none", "<na>"):
                continue
            n_pred += 1
            key = f"{mut}|{norm}|{hla}"
            bbs = key2bb.get(key)
            if bbs is None:
                n_nokey += 1
                continue
            for bb in bbs:
                bb2score[int(bb)] = val

    # 4. 写全 1761 行 (缺 -> 空)
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    n_filled = 0
    with open(args.out, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["bb_idx", OUT_COL])
        for bb in all_bb:
            v = bb2score.get(bb, "")
            if v != "":
                n_filled += 1
            w.writerow([bb, v])

    print(f"[parse] predict有效行={n_pred} | 未匹配map键={n_nokey} | 回填bb_idx={n_filled}/{len(all_bb)} "
          f"({n_filled/max(len(all_bb),1)*100:.1f}%)")
    print(f"[parse] 写 {args.out} (列: bb_idx, {OUT_COL})")
    shown = 0
    for bb in all_bb:
        if bb in bb2score:
            print(f"        bb_idx={bb}\t{OUT_COL}={bb2score[bb]}")
            shown += 1
            if shown >= 3:
                break


if __name__ == "__main__":
    main()
