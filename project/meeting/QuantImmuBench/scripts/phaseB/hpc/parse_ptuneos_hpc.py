# -*- coding: utf-8 -*-
"""
parse_ptuneos_hpc.py — Phase B / pTuneos Pre&RecNeo（HPC singularity 版）的 parse 步。
服务项目: quantimmu-bench  lever: pTuneos Pre&RecNeo benchmark（P101/P102 重推理）

读 prep 产的 bb_idx 映射 + 容器 wrapper 输出（含 model_pro）→ model_pro 贴回 bb_idx
→ 写合表列 $BASE/phaseB/pTuneos_101102.csv（列 = bb_idx, MT_pTuneos）。

口径:
  · 合表只一列 MT_pTuneos = model_pro(MT_pep=MT_sub, WT_pep=WT_sub, HLA)（原部署口径，无 WT 列）。
  · 方向 model_pro 越高越免疫原（官方原始方向，无翻转）。
  · emitted=0 的 bb_idx → MT_pTuneos 留空；emitted=1 但容器未给分（netMHCpan 未覆盖该 allele
    → wrapper 输出 model_pro=NaN）→ 同样留空。两者都不该混进数值列。
"""
import argparse
import csv
import math


def parse_container_output(out_tsv):
    """读容器输出 TSV → {(MT_pep, WT_pep, HLA_type): model_pro_float}。
    列含 MT_pep / WT_pep / HLA_type / ... / model_pro（wrapper 以 tab 分隔写）。"""
    score = {}
    with open(out_tsv, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f, delimiter="\t")
        for c in ("MT_pep", "WT_pep", "HLA_type", "model_pro"):
            if c not in (reader.fieldnames or []):
                raise SystemExit(
                    "[FAIL] 容器输出缺列 {}；实际列={}".format(c, reader.fieldnames))
        for row in reader:
            mt = (row["MT_pep"] or "").strip().upper()
            wt = (row["WT_pep"] or "").strip().upper()
            hla = (row["HLA_type"] or "").strip()
            raw = (row["model_pro"] or "").strip()
            try:
                v = float(raw)
            except (TypeError, ValueError):
                v = float("nan")
            score[(mt, wt, hla)] = v
    return score


def main():
    ap = argparse.ArgumentParser(description="pTuneos HPC parse：model_pro -> bb_idx 合表列")
    ap.add_argument("--map-csv", required=True, help="prep 产的 bb_idx 映射 CSV")
    ap.add_argument("--output-tsv", required=True, help="容器 wrapper 输出 TSV（含 model_pro）")
    ap.add_argument("--out", required=True, help="最终合表列 CSV（bb_idx,MT_pTuneos）")
    args = ap.parse_args()

    score = parse_container_output(args.output_tsv)
    print("[parse] 容器输出 {} 条 model_pro".format(len(score)))

    with open(args.map_csv, newline="", encoding="utf-8") as f:
        map_rows = list(csv.DictReader(f))

    n_found = n_blank = n_nan = 0
    with open(args.out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["bb_idx", "MT_pTuneos"])
        w.writeheader()
        for mr in map_rows:
            mt_s = ""
            if str(mr.get("emitted", "0")).strip() == "1":
                key = (mr["MT_pep"].strip().upper(),
                       mr["WT_pep"].strip().upper(),
                       mr["HLA_type"].strip())
                v = score.get(key)
                if v is None or (isinstance(v, float) and math.isnan(v)):
                    n_nan += 1            # 送了但无分（allele 未覆盖 / 容器漏）→ 留空
                else:
                    mt_s = str(round(v, 6))
                    n_found += 1
            if mt_s == "":
                n_blank += 1
            w.writerow({"bb_idx": mr["bb_idx"], "MT_pTuneos": mt_s})

    print("[parse] 写 {}  ({} 行)".format(args.out, len(map_rows)))
    print("[parse]   MT_pTuneos: {} found / {} blank（含 {} 送容器但 NaN：netMHCpan 未覆盖该 allele）"
          .format(n_found, n_blank, n_nan))
    print("[parse]   方向：model_pro 越高越免疫原（无翻转）")
    if n_found == 0:
        raise SystemExit("[FAIL] MT_pTuneos 全空 → 容器输出/映射键对不上，核 prep 的 input.tsv 与容器 stdout")


if __name__ == "__main__":
    main()
