# -*- coding: utf-8 -*-
"""
run_deepimmuno_official.py — DeepImmuno 新官方数据 prep + parse（WSL 跑推理在中间）。
服务 quantimmu-bench / W3 immml / G1 工具补齐.

DeepImmuno(github.com/frankligy/DeepImmuno): CNN, 9/10mer ONLY, HLA=HLA-A*0201(带星去冒号4位).
输出 immunogenicity ∈[0,1] 越高越免疫原 no flip. repo+权重在 WSL /root/quantimmu/tools_repos/DeepImmuno.

两 mode:
  prep:  uniq_pep_hla.csv → deepimmuno_input.csv(逗号无表头 peptide,convHLA, 仅9/10mer)
                          + deepimmuno_hla_map.csv(convHLA→origHLA 回映射)
  parse: deepimmuno-cnn-result.txt(TSV peptide/HLA/immunogenicity) → deepimmuno_raw_official.csv
                          (peptide, HLA_Allele=orig带星冒号, score)  ← 供 build_official --key hla
HLA 转换: HLA-A*66:01 → HLA-A*6601 (去冒号). 回映射用 map.
"""
import sys
import csv
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
WORK = ROOT / "scripts" / "out_official" / "immml_work"
UNIQ = ROOT / "scripts" / "out_official" / "newtools" / "uniq_pep_hla.csv"
INP = WORK / "deepimmuno_input.csv"
HMAP = WORK / "deepimmuno_hla_map.csv"
RESULT = WORK / "deepimmuno_out" / "deepimmuno-cnn-result.txt"
RAW = WORK / "deepimmuno_raw_official.csv"


def conv_hla(h):
    # HLA-A*66:01 → HLA-A*6601 (去冒号)
    return h.replace(":", "")


def prep():
    rows = []
    mp = {}
    with open(UNIQ, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            pep = r["peptide"].strip().upper()
            if len(pep) not in (9, 10):
                continue
            orig = r["HLA_Allele"].strip()
            ch = conv_hla(orig)
            rows.append((pep, ch))
            mp[(pep, ch)] = orig
    WORK.mkdir(parents=True, exist_ok=True)
    seen = set()
    with open(INP, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        for pep, ch in rows:
            if (pep, ch) in seen:
                continue
            seen.add((pep, ch))
            w.writerow([pep, ch])
    with open(HMAP, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f); w.writerow(["peptide", "convHLA", "origHLA"])
        for (pep, ch), orig in mp.items():
            w.writerow([pep, ch, orig])
    print(f"[prep] deepimmuno_input rows(distinct)={len(seen)} (9/10mer only)  map={len(mp)}")


def parse():
    # 回映射 (peptide, convHLA) → origHLA
    mp = {}
    with open(HMAP, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            mp[(r["peptide"].upper(), r["convHLA"])] = r["origHLA"]
    out = []
    n_skip = 0
    with open(RESULT, newline="", encoding="utf-8") as f:
        rd = csv.reader(f, delimiter="\t")
        header = next(rd)
        for row in rd:
            if len(row) < 3:
                continue
            pep, hla, score = row[0].strip().upper(), row[1].strip(), row[2].strip()
            orig = mp.get((pep, hla))
            if orig is None:
                n_skip += 1; continue
            try:
                sc = float(score)
            except ValueError:
                continue
            out.append((pep, orig, sc))
    with open(RAW, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f); w.writerow(["peptide", "HLA_Allele", "score"])
        for pep, orig, sc in out:
            w.writerow([pep, orig, sc])
    print(f"[parse] deepimmuno_raw_official rows={len(out)}  unmapped_skip={n_skip}")
    print(f"[parse] wrote {RAW}")


if __name__ == "__main__":
    {"prep": prep, "parse": parse}[sys.argv[1]]()
