# -*- coding: utf-8 -*-
"""
parse_repitope_official.py — Repitope 官方结果回贴 → Repitope_official.csv
============================================================================
本地跑（HPC 结果 Repitope_scores.csv 拉回后）。Repitope = HLA-agnostic（纯肽免疫原，
与等位无关），故按【肽】广播到 master_backbone_official.csv 的所有 backbone 行。

输入：
  --scores   repitope_out/Repitope_scores.csv  （run_repitope.R 产出；列：
             Peptide, ImmunogenicityScore, ImmunogenicityScore.cv）
  --backbone scripts/out_official/master_backbone_official.csv （1761 行，含
             MT_Subpeptide / WT_Subpeptide，均 9-mer）

输出：
  scripts/out_official/Repitope_official.csv   列：bb_idx, MT_Repitope, WT_Repitope
  1761 行，对齐 master_backbone_official.csv。

回贴规则（HLA-agnostic 广播）：
  - 建 peptide(大写) → ImmunogenicityScore 字典（唯一肽分）。
  - 每行 MT_Repitope = 字典.get(MT_Subpeptide大写)，WT_Repitope = 字典.get(WT_Subpeptide大写)。
  - 同一肽 → 所有出现它的 backbone 行拿同一分（广播）。
  - 精确肽匹配缺 → NaN（空），绝不兜底造数 / 不用别的肽回填。
  - WT_Subpeptide 多为空（indel 肽无 WT）→ 留空，不报错。

方向：ImmunogenicityScore 越高越免疫原（probability estimate，约 0-1），无翻转。

用法：
  python parse_repitope_official.py \
      --scores   scripts/out_official/repitope_out/Repitope_scores.csv \
      --backbone scripts/out_official/master_backbone_official.csv \
      --out      scripts/out_official/Repitope_official.csv
"""
import argparse
import csv
import math
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEFAULT_OFFICIAL = HERE.parent / "out_official"


def parse_args():
    p = argparse.ArgumentParser(description="Repitope 官方结果回贴 → Repitope_official.csv")
    p.add_argument("--scores",
                   default=str(DEFAULT_OFFICIAL / "repitope_out" / "Repitope_scores.csv"),
                   help="run_repitope.R 产出的 Repitope_scores.csv")
    p.add_argument("--backbone",
                   default=str(DEFAULT_OFFICIAL / "master_backbone_official.csv"),
                   help="master_backbone_official.csv（1761 行）")
    p.add_argument("--out",
                   default=str(DEFAULT_OFFICIAL / "Repitope_official.csv"),
                   help="输出 CSV 路径")
    return p.parse_args()


def load_score_map(scores_path: Path) -> dict:
    """读 Repitope_scores.csv → {peptide_upper: ImmunogenicityScore(float)}。"""
    score_map = {}
    with open(scores_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        if "Peptide" not in reader.fieldnames or "ImmunogenicityScore" not in reader.fieldnames:
            raise SystemExit(
                f"[FAIL] {scores_path} 列不符，实际列={reader.fieldnames}；"
                f"期望含 Peptide, ImmunogenicityScore")
        for row in reader:
            pep = (row.get("Peptide") or "").strip().upper()
            raw = (row.get("ImmunogenicityScore") or "").strip()
            if not pep or raw == "" or raw.upper() == "NA":
                continue
            try:
                score_map[pep] = float(raw)
            except ValueError:
                continue
    return score_map


def main():
    args = parse_args()
    scores_path = Path(args.scores).resolve()
    backbone_path = Path(args.backbone).resolve()
    out_path = Path(args.out).resolve()

    if not backbone_path.exists():
        raise SystemExit(f"[FAIL] backbone 不存在: {backbone_path}")

    if scores_path.exists():
        score_map = load_score_map(scores_path)
        print(f"[scores] 读入 {len(score_map)} 个唯一肽分 ← {scores_path}")
    else:
        score_map = {}
        print(f"[WARN] 结果不存在: {scores_path} → 全列 NaN（HPC 未跑/未拉回）")

    out_path.parent.mkdir(parents=True, exist_ok=True)

    def fmt(pep: str) -> str:
        v = score_map.get(pep)
        if v is None or (isinstance(v, float) and math.isnan(v)):
            return ""  # 缺 → 空（pandas 读为 NaN），不兜底造数
        return str(round(v, 6))

    n_rows = n_mt = n_wt = n_mt_nan = n_wt_nan = 0
    with open(backbone_path, newline="", encoding="utf-8") as fin, \
         open(out_path, "w", newline="", encoding="utf-8") as fout:
        reader = csv.DictReader(fin)
        writer = csv.DictWriter(fout, fieldnames=["bb_idx", "MT_Repitope", "WT_Repitope"])
        writer.writeheader()
        for r in reader:
            n_rows += 1
            mt = (r.get("MT_Subpeptide") or "").strip().upper()
            wt = (r.get("WT_Subpeptide") or "").strip().upper()
            mt_s = fmt(mt) if mt else ""
            wt_s = fmt(wt) if wt else ""  # 空 WT（indel 肽）→ 留空
            n_mt += mt_s != ""
            n_wt += wt_s != ""
            n_mt_nan += mt_s == ""
            n_wt_nan += wt_s == ""
            writer.writerow({"bb_idx": r["bb_idx"], "MT_Repitope": mt_s, "WT_Repitope": wt_s})

    print(f"\n[parse] 写 {out_path}  ({n_rows} 行)")
    print(f"[parse]   MT_Repitope: {n_mt} found / {n_mt_nan} NaN")
    print(f"[parse]   WT_Repitope: {n_wt} found / {n_wt_nan} NaN")
    print(f"[parse]   方向：ImmunogenicityScore 越高越免疫原（无翻转）")
    if n_rows != 1761:
        print(f"[WARN] 行数 {n_rows} != 1761，确认 backbone 是否为 master_backbone_official.csv")


if __name__ == "__main__":
    main()
