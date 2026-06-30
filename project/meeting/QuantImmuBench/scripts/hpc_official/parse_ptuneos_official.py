# -*- coding: utf-8 -*-
"""parse_ptuneos_official.py — pTuneos Pre&RecNeo 官方数据结果回贴
====================================================================
服务项目: quantimmu-bench  lever: pTuneos 官方数据补跑（免疫原 model_pro）

本地跑（容器输出 ptuneos_official_output.tsv 拉回后）。把 wrapper 产出的 model_pro
按 **精确 (MT_pep, WT_pep, HLA_type)** 三元组回贴 master_backbone_official.csv 的
bb_idx，产出 1761 行 CSV：

    scripts/out_official/pTuneos_official.csv   列：bb_idx, MT_pTuneos

★ 口径（与 phaseB run_ptuneos_101102.py 完全一致）★
  - pTuneos Pre&RecNeo 的 model_pro 本就是「突变肽 vs 其野生型种系」的**不对称免疫原性
    分**（Self_similarity / WT_Binding_EL 特征已内含 MT-vs-WT 差异），**无独立 WT 分**
    → 只产 MT_pTuneos 一列，不产 WT_pTuneos。
  - 方向：model_pro 越高越免疫原（官方原始方向，无翻转，0-1 概率）。

★ 数据完整性铁律 ★
  - 回贴只做精确 (MT_pep, WT_pep, HLA_type) 匹配（key 全大写、strip）；
  - 缺该精确分 → 该 bb_idx 留 NaN（空字符串），**绝不肽级兜底 / 绝不拿别行的分回填**；
  - backbone 中 WT_Subpeptide 为空（frameshift/INDEL/passenger，frozen 无 WT 配对）→
    pTuneos 不可打分 → 直接 NaN，不送匹配。
  - 实测预期覆盖 ≈ **244 / 1761**（13.9%；244 = backbone 中有非空 WT 的 SNV 子肽行）。
    NaN 偏多是工具适用面（需 MT/WT 配对），非 bug、非没跑完。

运行示例：
    python scripts/hpc_official/parse_ptuneos_official.py \
        --ptuneos-out scripts/out_official/ptuneos/work_official/ptuneos_official_output.tsv \
        --backbone    scripts/out_official/master_backbone_official.csv \
        --out-dir     scripts/out_official
"""
import argparse
import csv
import math
import sys
from pathlib import Path

STD_AA = set("ACDEFGHIKLMNPQRSTVWY")  # wrapper 只吃标准 20 氨基酸


def is_clean_pep(p: str) -> bool:
    return bool(p) and all(c in STD_AA for c in p)


def norm(s) -> str:
    return ("" if s is None else str(s)).strip()


def load_scores(out_tsv: Path) -> dict:
    """读容器输出 TSV → {(MT_pep, WT_pep, HLA_type): model_pro_float}。
    key 全大写肽 + 原格 HLA（与 backbone 回贴 key 一致构造）。"""
    score = {}
    with open(out_tsv, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f, delimiter="\t")
        for c in ("MT_pep", "WT_pep", "HLA_type", "model_pro"):
            if c not in (reader.fieldnames or []):
                raise SystemExit(
                    f"[FATAL] 容器输出缺列 {c}；实际列={reader.fieldnames}")
        for row in reader:
            mt = norm(row["MT_pep"]).upper()
            wt = norm(row["WT_pep"]).upper()
            hla = norm(row["HLA_type"])
            raw = norm(row["model_pro"])
            try:
                v = float(raw)
            except (TypeError, ValueError):
                v = float("nan")
            score[(mt, wt, hla)] = v
    return score


def main():
    ap = argparse.ArgumentParser(
        description="pTuneos 官方数据 model_pro 回贴 bb_idx")
    ap.add_argument("--ptuneos-out", required=True,
                    help="容器输出 ptuneos_official_output.tsv（含 model_pro）")
    ap.add_argument("--backbone", required=True,
                    help="master_backbone_official.csv（含 bb_idx + MT/WT_Subpeptide + HLA_Allele）")
    ap.add_argument("--out-dir", required=True,
                    help="输出目录（写 pTuneos_official.csv）")
    args = ap.parse_args()

    out_tsv = Path(args.ptuneos_out)
    backbone = Path(args.backbone)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    if not out_tsv.exists():
        raise SystemExit(f"[FATAL] 容器输出不存在: {out_tsv}")
    if not backbone.exists():
        raise SystemExit(f"[FATAL] backbone 不存在: {backbone}")

    score = load_scores(out_tsv)
    n_valid_score = sum(1 for v in score.values() if not (isinstance(v, float) and math.isnan(v)))
    print(f"[load] 容器输出 {len(score)} 条；其中非 NaN model_pro = {n_valid_score}")

    with open(backbone, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    def lookup(mt, wt, hla):
        v = score.get((mt, wt, hla))
        if v is None or (isinstance(v, float) and math.isnan(v)):
            return ""
        return repr(float(v))  # 全精度写出，不提前 round（核数交 verifier）

    out_path = out_dir / "pTuneos_official.csv"
    n_found = n_nan = n_nowt = n_scorable = 0
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["bb_idx", "MT_pTuneos"])
        w.writeheader()
        for r in rows:
            hla = norm(r.get("HLA_Allele"))
            mt = norm(r.get("MT_Subpeptide")).upper()
            wt = norm(r.get("WT_Subpeptide")).upper()
            # pTuneos 需 MT+WT 配对；无 WT / 非标准肽 → 不可打分 → NaN
            scorable = bool(hla) and is_clean_pep(mt) and is_clean_pep(wt)
            if not is_clean_pep(wt):
                n_nowt += 1
            cell = lookup(mt, wt, hla) if scorable else ""
            if scorable:
                n_scorable += 1
            if cell != "":
                n_found += 1
            else:
                n_nan += 1
            w.writerow({"bb_idx": r["bb_idx"], "MT_pTuneos": cell})

    print(f"\n[parse] 写 {out_path}  ({len(rows)} 行)")
    print(f"[parse]   可打分行(MT+WT 干净+有HLA) = {n_scorable}")
    print(f"[parse]   MT_pTuneos: {n_found} found / {n_nan} NaN")
    print(f"[parse]   其中 {n_nowt} 行无干净 WT（frameshift/INDEL）→ 必然 NaN，非 bug")
    print(f"[parse]   方向：model_pro 越高越免疫原（0-1 概率，无翻转）")
    if n_scorable and n_found < n_scorable:
        print(f"[parse]   ⚠️ 可打分 {n_scorable} 但仅回贴 {n_found}："
              f"差额 = 该 (MT,WT,HLA) 在容器输出缺/为 NaN（HLA 不被 netMHCpan-4.0 覆盖等），诚实留空")


if __name__ == "__main__":
    main()
