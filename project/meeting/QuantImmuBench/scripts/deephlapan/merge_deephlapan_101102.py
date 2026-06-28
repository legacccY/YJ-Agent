#!/usr/bin/env python
# -*- coding: utf-8 -*-
# ===========================================================================
# merge_deephlapan_101102.py — Phase B deepHLApan 输出回映到 bb_idx
# 服务: QuantImmuBench / Phase B / lever=HLA-AUDIT 填合表缺口
#
# 镜像 scripts/remerge_fixed.py::merge_deephlapan 的自然键回贴逻辑:
#   key = (subpeptide, HLA_no_star)  →  immunogenic score（合表用此分）
#   deepHLApan context-free → 同 (subpep, HLA) 同分，所有匹配 bb_idx 全填。
#
# 输入:
#   scripts/out/phaseB/backbone_101102.csv          （订正真值，4018 行，全 bb_idx）
#   scripts/out/phaseB/deephlapan_out_101102/*_predicted_result.csv （docker 产出）
#     输出列: Annotation,HLA,Peptide,binding score,immunogenic score
# 产出:
#   scripts/out/phaseB/deepHLApan_101102.csv
#     列: bb_idx, MT_deepHLApan, WT_deepHLApan   （值 = immunogenic score，未匹配=NaN）
#
# 用法（主线跑，docker 完成后）:
#   python scripts/deephlapan/merge_deephlapan_101102.py
# ===========================================================================

import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]          # QuantImmuBench/
PHASEB = ROOT / "scripts" / "out" / "phaseB"
BACKBONE = PHASEB / "backbone_101102.csv"
OUT_DIR = PHASEB / "deephlapan_out_101102"
OUT_CSV = PHASEB / "deepHLApan_101102.csv"

# immunogenic score 列名变体（兼容 remerge_fixed 的容错）
IMMUNO_CANDIDATES = ("immunogenic score", "immunogenic_score", "immunogenicity")


def hla_no_star(hla_std: str) -> str:
    """HLA-A*66:01 → HLA-A66:01（去星号，保留 HLA- 前缀）。"""
    return str(hla_std).replace("*", "").strip()


def load_scores(out_dir: Path) -> dict:
    """解析 docker 输出 *_predicted_result.csv，返回 {(peptide, hla_ns): immuno_score}。"""
    if not out_dir.exists():
        raise SystemExit(f"[ERROR] 输出目录不存在: {out_dir}（先跑 docker）")
    csv_files = sorted(out_dir.glob("*_predicted_result.csv"))
    if not csv_files:
        csv_files = sorted(out_dir.glob("*.csv"))
    if not csv_files:
        raise SystemExit(f"[ERROR] {out_dir} 下无 csv 产出")

    lut = {}
    for f in csv_files:
        with f.open(encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            cols = {c.lower().strip(): c for c in (reader.fieldnames or [])}
            pep_col = cols.get("peptide")
            hla_col = cols.get("hla")
            imm_col = next((cols[c] for c in IMMUNO_CANDIDATES if c in cols), None)
            if not (pep_col and hla_col and imm_col):
                print(f"[WARN] {f.name} 缺必需列(peptide/HLA/immunogenic)，跳过")
                continue
            for row in reader:
                pep = str(row[pep_col]).strip()
                hla_ns = hla_no_star(row[hla_col])
                val = str(row[imm_col]).strip()
                if val == "" or val.lower() == "nan":
                    continue
                # 同键重复（理论上同分）保留首个
                lut.setdefault((pep, hla_ns), float(val))
    return lut


def main() -> None:
    if not BACKBONE.exists():
        raise SystemExit(f"[ERROR] backbone 不存在: {BACKBONE}")

    lut = load_scores(OUT_DIR)
    print(f"[merge] 输出查找表条目: {len(lut)}")

    rows_out = []
    mt_hit = wt_hit = total = 0
    with BACKBONE.open(encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            total += 1
            bb_idx = row["bb_idx"]
            hla_ns = hla_no_star(row["HLA_Allele"])
            mt = str(row["MT_Subpeptide"]).strip()
            wt = str(row["WT_Subpeptide"]).strip()
            mt_score = lut.get((mt, hla_ns), "")
            wt_score = lut.get((wt, hla_ns), "")
            if mt_score != "":
                mt_hit += 1
            if wt_score != "":
                wt_hit += 1
            rows_out.append([bb_idx, mt_score, wt_score])

    with OUT_CSV.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["bb_idx", "MT_deepHLApan", "WT_deepHLApan"])
        w.writerows(rows_out)

    print(f"[merge] backbone 行: {total}")
    print(f"[merge] MT_deepHLApan 非空: {mt_hit}/{total}")
    print(f"[merge] WT_deepHLApan 非空: {wt_hit}/{total}")
    print(f"[merge] 写出: {OUT_CSV}")


if __name__ == "__main__":
    main()
