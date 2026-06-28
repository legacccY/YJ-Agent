# -*- coding: utf-8 -*-
"""
prep_ptuneos_hpc.py — Phase B / pTuneos Pre&RecNeo（HPC singularity 版）的 prep 步。
服务项目: quantimmu-bench  lever: pTuneos Pre&RecNeo benchmark（P101/P102 重推理）

唯一订正输入源 = HPC 上 $BASE/phaseB/backbone_101102.csv（主线已上传，闸门1 过：
HLA_Allele==订正真值）。本步只读它，绝不读旧 ptuneos 输入文件。

输出（写到 --work 目录，后续被绑挂为容器 /work）:
  1. ptuneos_input_101102.tsv  容器 wrapper 输入，3 列 MT_pep<TAB>WT_pep<TAB>HLA_type
     —— 仅 **MT 套** (MT_pep=MT_Subpeptide, WT_pep=WT_Subpeptide, HLA)，唯一去重。
        合表只有一列 MT_pTuneos（无 WT 列）→ 不产 WT 自配对套（与本期框架约定一致）。
  2. ptuneos_map_101102.csv    全量 bb_idx 映射，列 = bb_idx,MT_pep,WT_pep,HLA_type,emitted
     —— emitted=1 的行进了容器输入；emitted=0（非标准氨基酸/空肽/无 HLA）回贴时留空。
        parse 步只读此 map + 容器输出，不再回读 backbone（单一清洗点在此，防口径漂移）。

口径（与原 86 肽 ELISpot 跑分一致，见 TOOLS/pTuneos.md + run_ptuneos_101102.py）:
  · 跑 Pre&RecNeo 识别子模型（输出 model_pro，RF 5 特征），方向越高越免疫原。
  · 只送标准 20 氨基酸的干净肽（否则容器内 hydro_vector KeyError）。
  · HLA 保留 backbone 原格式 'HLA-A*66:01'，容器 wrapper 内部 .replace('*','') 喂 netMHCpan。
"""
import argparse
import csv
from collections import OrderedDict

STD_AA = set("ACDEFGHIKLMNPQRSTVWY")  # 仅标准 20 氨基酸送工具


def is_clean_pep(p):
    return bool(p) and all(c in STD_AA for c in p)


def main():
    ap = argparse.ArgumentParser(description="pTuneos HPC prep：backbone -> 容器输入 TSV + bb_idx map")
    ap.add_argument("--backbone", required=True, help="HPC 上 backbone_101102.csv 绝对路径")
    ap.add_argument("--input-tsv", required=True, help="输出容器输入 TSV 路径")
    ap.add_argument("--map-csv", required=True, help="输出 bb_idx 映射 CSV 路径")
    ap.add_argument("--smoke", type=int, default=0,
                    help="只把前 N 个 unique 三元组写入容器输入（验工具能跑，不影响 map 全量）")
    args = ap.parse_args()

    with open(args.backbone, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    # ── 建 map（全量 bb_idx）+ 收集 unique MT 三元组 ────────────────────────────
    triples = OrderedDict()   # (mt, wt, hla) -> None，仅作有序去重集
    map_rows = []
    for r in rows:
        bb_idx = r.get("bb_idx", "")
        hla = (r.get("HLA_Allele") or "").strip()
        mt = (r.get("MT_Subpeptide") or "").strip().upper()
        wt = (r.get("WT_Subpeptide") or "").strip().upper()
        emitted = 0
        if hla and is_clean_pep(mt) and is_clean_pep(wt):
            triples.setdefault((mt, wt, hla), None)
            emitted = 1
        map_rows.append({
            "bb_idx": bb_idx,
            "MT_pep": mt if emitted else "",
            "WT_pep": wt if emitted else "",
            "HLA_type": hla if emitted else "",
            "emitted": emitted,
        })

    all_keys = list(triples.keys())
    if args.smoke:
        all_keys = all_keys[:args.smoke]

    # ── 写容器输入 TSV ────────────────────────────────────────────────────────
    with open(args.input_tsv, "w", newline="", encoding="utf-8") as f:
        f.write("MT_pep\tWT_pep\tHLA_type\n")
        for (mt, wt, hla) in all_keys:
            f.write("{}\t{}\t{}\n".format(mt, wt, hla))

    # ── 写 bb_idx 映射 CSV ────────────────────────────────────────────────────
    with open(args.map_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["bb_idx", "MT_pep", "WT_pep", "HLA_type", "emitted"])
        w.writeheader()
        for mr in map_rows:
            w.writerow(mr)

    n_emit = sum(mr["emitted"] for mr in map_rows)
    hla_set = sorted({k[2] for k in all_keys})
    print("[prep] backbone={} 行 | emitted(可跑)={} | unique 三元组={}{}".format(
        len(rows), n_emit, len(all_keys), " (smoke 截断)" if args.smoke else ""))
    print("[prep]   HLA 集合 = {}".format(hla_set))
    print("[prep]   写容器输入 {}".format(args.input_tsv))
    print("[prep]   写 bb_idx 映射 {}".format(args.map_csv))


if __name__ == "__main__":
    main()
