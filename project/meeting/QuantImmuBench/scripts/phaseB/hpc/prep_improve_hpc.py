# -*- coding: utf-8 -*-
"""
prep_improve_hpc.py — Phase B：把 HPC 上的 backbone_101102.csv 转成 IMPROVE 输入。

在 HPC 上跑（由 run_improve_hpc.sh 调用），只读传入的 backbone csv。
产出两份：
  improve_input.tsv      —— IMPROVE feature_calc 的输入（去重后的 肽×HLA 行）
  improve_input_map.csv  —— (Mut|Norm|HLA) 键 → bb_idx 列表，给 parse 回填合表

口径（与原 86 肽严格一致，见 scripts/improve/run_feature_calc.sh）：
  - Mut_peptide  = MT_Subpeptide（订正 backbone 的子肽）
  - Norm_peptide = WT_Subpeptide（野生型子肽，列名喂 IMPROVE 时用 Norm_peptide）
  - HLA_allele   = HLA_Allele 去掉星号：HLA-A*66:01 -> HLA-A66:01
                   （原 improve_input.tsv 就是 `HLA-A24:02` 无星号格式，netMHCpan-4.1 口径）
  - 仅保留 8-12mer（IMPROVE/netMHCpan 适用区间）；区间外的 bb_idx 不进输入，
    合表里保持 NaN（patch_101102 视作「不适用」，与原口径一致，不补不改）。
  - feature_calc 按 (MHC, PeptMut, PeptNorm) 去重 → 这里同键去重，多 bb_idx 共享一行分数。

服务: quantimmu-bench Phase B IMPROVE 101/102 重推理（lever=IMPROVE）。
"""
import os
import sys
import csv
import json
import argparse

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def norm_hla(s):
    """HLA-A*66:01 -> HLA-A66:01（去星号，与原 improve_input 无星号格式一致）。"""
    return str(s).replace("*", "").strip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--backbone", required=True, help="HPC backbone_101102.csv 绝对路径（只读）")
    ap.add_argument("--input-tsv", required=True, help="输出 improve_input.tsv")
    ap.add_argument("--map-csv", required=True, help="输出 improve_input_map.csv")
    args = ap.parse_args()

    rows = []
    with open(args.backbone, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            rows.append(r)
    print(f"[prep] 读 backbone: {len(rows)} 行 <- {args.backbone}")

    # (mut|norm|hla) -> [bb_idx,...]；同时按出现顺序保留去重输入行
    key2bb = {}
    seen = []  # [(mut, norm, hla)] 去重后的输入顺序
    n_lenskip = 0
    for r in rows:
        mut = str(r["MT_Subpeptide"]).strip()
        norm = str(r["WT_Subpeptide"]).strip()
        hla = norm_hla(r["HLA_Allele"])
        bb = str(r["bb_idx"]).strip()
        # 长度门：IMPROVE/netMHCpan 仅 8-12mer
        if not (8 <= len(mut) <= 12):
            n_lenskip += 1
            continue
        key = f"{mut}|{norm}|{hla}"
        if key not in key2bb:
            key2bb[key] = []
            seen.append((mut, norm, hla))
        key2bb[key].append(bb)

    # 写 IMPROVE 输入 tsv（列名与原 improve_input.tsv 一致：Mut_peptide/WT_peptide/HLA_allele）
    # 注：原 input 用 WT_peptide 列名，run_feature_calc.sh Step1 再 rename 成 Norm_peptide；
    #     这里直接写 WT_peptide 保持与原输入字节级一致。
    os.makedirs(os.path.dirname(args.input_tsv), exist_ok=True)
    with open(args.input_tsv, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, delimiter="\t")
        w.writerow(["Mut_peptide", "WT_peptide", "HLA_allele"])
        for mut, norm, hla in seen:
            w.writerow([mut, norm, hla])

    # 写映射 csv（key, bb_idx_json）
    os.makedirs(os.path.dirname(args.map_csv), exist_ok=True)
    with open(args.map_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["key", "bb_indices"])
        for key, bbs in key2bb.items():
            w.writerow([key, json.dumps(bbs)])

    n_bb_total = sum(len(v) for v in key2bb.values())
    print(f"[prep] 去重输入行={len(seen)} | 覆盖 bb_idx={n_bb_total} | 长度门跳过(非8-12mer)={n_lenskip}")
    print(f"[prep] 写 {args.input_tsv}")
    print(f"[prep] 写 {args.map_csv}")
    # 自校验：前 3 行
    for mut, norm, hla in seen[:3]:
        print(f"        {mut}\t{norm}\t{hla}")


if __name__ == "__main__":
    main()
