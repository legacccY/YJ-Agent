#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
parse_seq2neo_official.py — Seq2Neo cnn_results.csv → bb_idx 对齐的官方合表列
服务: quantimmu-bench Phase0 官方数据工具补跑舰队 (lever=Seq2Neo, bonus 升正式)

作用:
  读 HPC 拉回的 Seq2Neo `cnn_results.csv` → 按 (Peptide, HLA无星号) 精确 join
  master_backbone_official.csv → 产 scripts/out_official/Seq2Neo_official.csv
  (列 bb_idx, MT_Seq2Neo)。1761 行对齐 backbone, 缺 → 留空 NaN, 禁肽级兜底造数。

cnn_results.csv 列名 (官方源 _cnn.py::file_process 核实, 非臆测):
  file_process 把输入列重命名为 ["Peptide","HLA","IC50","TAP"], hlatopseudoseq 去星并
  merge 加 pseudosequence 列, 末尾 origin_input["immunogenicity"]=scoring, to_csv(index=None)。
  => cnn_results.csv 列 = Peptide, HLA, IC50, TAP, pseudosequence, immunogenicity
  - peptide 列 = `Peptide`
  - HLA 列    = `HLA` (无星号; hlatopseudoseq 内 a.replace("*","") 已去星)
  - 分数列    = `immunogenicity` (CNN sigmoid 输出 0-1)
  (默认列名已按官方源钉死; 仍留 --pep-col/--hla-col/--score-col 兜底覆盖。)

方向 (官方源核实):
  immunogenicity = sigmoid 末层输出 ∈ [0,1], **越大越免疫原** (阈值 >0.5)。
  与 benchmark 其他工具方向一致, **不翻转**。

WT: Seq2Neo CNN 无独立 WT 免疫原分 (我们 backbone 只喂 MT_Subpeptide) → MT-only,
  仅产 MT_Seq2Neo 列 (用 official_io.write_official_mt_only)。

Join 铁律 (沿用 parse_improve / parse_icerfire 既定做法):
  按内容 (MT_Subpeptide, HLA无星号) 精确 join, 不靠行序 (Seq2Neo 内部 merge 会重排)。
  一个 (pep,hla) 可对多 bb_idx (同肽同等位多 backbone 行), 全赋同分。缺即 NaN, 绝不兜底。
  覆盖率 <100% 正常来源: (a) HLA 不在 class1_pseudosequences.csv → inner merge 丢弃;
  (b) 肽长越界被 prep 跳过; (c) netMHCpan/netCTLpan 对个别等位/肽不支持。

输入: --results cnn_results.csv、--backbone master_backbone_official.csv
输出: scripts/out_official/Seq2Neo_official.csv
跑法: python scripts/hpc_official/parse_seq2neo_official.py (主线本地跑, 我不跑)
依赖: 标准库 + official_io.py。Windows/HPC: pathlib + utf-8。
许可红线: Seq2Neo(AFL-3.0) + netCTLpan/netMHCpan(DTU 学术许可), 发表前确认引用+条款合规。
"""

import argparse
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from official_io import (  # noqa: E402
    load_backbone_bb_order,
    write_official_mt_only,
    write_official_mt_wt,
)

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

TOOL = "Seq2Neo"

DEFAULT_PEP_COL = "Peptide"          # _cnn.py file_process 重命名
DEFAULT_HLA_COL = "HLA"              # 无星号
DEFAULT_SCORE_COL = "immunogenicity"  # sigmoid 0-1, 越大越免疫原


def norm_hla(h: str) -> str:
    """去星 + 去空格, 与 prep_seq2neo_official.norm_hla_seq2neo 一致。"""
    return str(h).strip().replace("*", "").replace(" ", "")


def clean_pep(s: str) -> str:
    s = str(s).strip()
    return "" if s.lower() in ("nan", "none", "<na>", "") else s


def load_cnn_results(path: Path, pep_col: str, hla_col: str, score_col: str) -> dict:
    """读 cnn_results.csv → {(Peptide, HLA无星号): immunogenicity(float)}。"""
    lookup = {}
    dups = 0
    n_nan = 0
    with open(path, newline="", encoding="utf-8") as f:
        rd = csv.DictReader(f)
        fields = rd.fieldnames or []
        for col, what in ((pep_col, "peptide"), (hla_col, "HLA"), (score_col, "score")):
            if col not in fields:
                raise KeyError(
                    f"cnn_results.csv 缺 {what} 列 '{col}'。实际列名: {fields}。"
                    f"用 --pep-col/--hla-col/--score-col 覆盖。"
                )
        print(f"[parse_seq2neo] cnn_results 列={fields}; "
              f"用 pep='{pep_col}' hla='{hla_col}' score='{score_col}'", file=sys.stderr)
        for r in rd:
            pep = clean_pep(r.get(pep_col, ""))
            hla = norm_hla(r.get(hla_col, ""))
            val = str(r.get(score_col, "")).strip()
            if not pep or not hla:
                continue
            try:
                v = float(val)
            except (TypeError, ValueError):
                n_nan += 1
                continue
            if v != v:  # NaN
                n_nan += 1
                continue
            key = (pep, hla)
            if key in lookup:
                dups += 1
            lookup[key] = v
    if dups:
        print(f"[parse_seq2neo] ⚠️ {dups} 个重复 (Peptide,HLA) key, 取最后一次。", file=sys.stderr)
    print(f"[parse_seq2neo] 读入 {len(lookup)} 个唯一 (Peptide,HLA) 分 (NaN/空跳过={n_nan})",
          file=sys.stderr)
    return lookup


def build_backbone_index(backbone: Path, pep_col: str = "MT_Subpeptide") -> dict:
    """读 backbone → {(<pep_col>, HLA无星号): [bb_idx_str, ...]}。
    pep_col=MT_Subpeptide 建 MT 索引（默认）；pep_col=WT_Subpeptide 建 WT 索引。"""
    idx = {}
    with open(backbone, newline="", encoding="utf-8") as f:
        rd = csv.DictReader(f)
        for r in rd:
            bb = r["bb_idx"].strip()
            pep = clean_pep(r.get(pep_col, ""))
            hla = norm_hla(r.get("HLA_Allele", ""))
            if not pep or not hla:
                continue
            idx.setdefault((pep, hla), []).append(bb)
    return idx


def map_pairs_to_bb(bb_index: dict, lookup: dict) -> tuple:
    """(pep,hla) 命中 lookup → 广播回该对的所有 bb_idx。返回 (bb→分, 命中对数, 未命中对数, 命中等位集)。"""
    out = {}
    hit_pairs = miss_pairs = 0
    alleles = set()
    for (pep, hla), bbs in bb_index.items():
        if (pep, hla) in lookup:
            v = round(lookup[(pep, hla)], 6)
            for bb in bbs:
                out[bb] = v
            hit_pairs += 1
            alleles.add(hla)
        else:
            miss_pairs += 1
    return out, hit_pairs, miss_pairs, alleles


def main():
    script_dir = Path(__file__).resolve().parent
    out_dir = script_dir.parent / "out_official"
    default_results = out_dir / "seq2neo_inputs" / "seq2neo_out" / "cnn_results.csv"
    default_backbone = out_dir / "master_backbone_official.csv"
    default_out = out_dir / "Seq2Neo_official.csv"

    ap = argparse.ArgumentParser(description="Parse Seq2Neo cnn_results.csv → Seq2Neo_official.csv")
    ap.add_argument("--results", default=str(default_results),
                    help="MT 侧 cnn_results.csv（MT_Subpeptide 打分）")
    ap.add_argument("--wt-results", default="",
                    help="WT 侧 cnn_results.csv（WT_Subpeptide 打分）。给了则输出 3 列 "
                         "bb_idx,MT_Seq2Neo,WT_Seq2Neo；不给则维持 2 列 MT-only（向后兼容 9mer）。")
    ap.add_argument("--backbone", default=str(default_backbone))
    ap.add_argument("--out", default=str(default_out))
    ap.add_argument("--pep-col", default=DEFAULT_PEP_COL)
    ap.add_argument("--hla-col", default=DEFAULT_HLA_COL)
    ap.add_argument("--score-col", default=DEFAULT_SCORE_COL)
    args = ap.parse_args()

    backbone = Path(args.backbone)
    if not backbone.exists():
        raise FileNotFoundError(f"backbone 不存在: {backbone}")
    bb_order = load_backbone_bb_order(backbone)
    mt_index = build_backbone_index(backbone, pep_col="MT_Subpeptide")

    results = Path(args.results)
    if not results.exists():
        print(f"[parse_seq2neo] WARNING: MT cnn_results 不存在: {results} (HPC 跑完拉回?)。"
              f"MT_Seq2Neo 全 NaN。", file=sys.stderr)
        lookup = {}
    else:
        lookup = load_cnn_results(results, args.pep_col, args.hla_col, args.score_col)

    mt_map, hit_pairs, miss_pairs, alleles = map_pairs_to_bb(mt_index, lookup)
    print(f"[parse_seq2neo] [MT] backbone 唯一(pep,hla)对={len(mt_index)}  "
          f"命中={hit_pairs}  未命中={miss_pairs}", file=sys.stderr)

    if args.wt_results:
        wt_index = build_backbone_index(backbone, pep_col="WT_Subpeptide")
        wt_results = Path(args.wt_results)
        if not wt_results.exists():
            print(f"[parse_seq2neo] WARNING: WT cnn_results 不存在: {wt_results}。"
                  f"WT_Seq2Neo 全 NaN。", file=sys.stderr)
            wt_lookup = {}
        else:
            wt_lookup = load_cnn_results(wt_results, args.pep_col, args.hla_col, args.score_col)
        wt_map, wt_hit, wt_miss, wt_alleles = map_pairs_to_bb(wt_index, wt_lookup)
        print(f"[parse_seq2neo] [WT] backbone 唯一(pep,hla)对={len(wt_index)}  "
              f"命中={wt_hit}  未命中={wt_miss}", file=sys.stderr)
        write_official_mt_wt(Path(args.out), TOOL, bb_order, mt_map, wt_map,
                             n_distinct_alleles_mt=len(alleles))
        print("[parse_seq2neo] 方向: MT_Seq2Neo/WT_Seq2Neo = immunogenicity (sigmoid 0-1, "
              "越大越免疫原, 不翻转)。许可: Seq2Neo AFL-3.0 + netCTLpan/netMHCpan DTU 学术许可, "
              "发表前确认条款。", file=sys.stderr)
    else:
        write_official_mt_only(Path(args.out), TOOL, bb_order, mt_map,
                               n_distinct_alleles_mt=len(alleles))
        print("[parse_seq2neo] 方向: MT_Seq2Neo = immunogenicity (sigmoid 0-1, 越大越免疫原, 不翻转)。"
              " 许可: Seq2Neo AFL-3.0 + netCTLpan/netMHCpan DTU 学术许可, 发表前确认条款。",
              file=sys.stderr)


if __name__ == "__main__":
    main()
