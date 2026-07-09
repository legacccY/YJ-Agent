#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
parse_neoag_official.py — neoag neoag_raw.csv → bb_idx 对齐的官方合表列
服务: quantimmu-bench §改动②③ 8-11mer 全量重跑（slice_local_b, lever=neoag）

作用（仿 HPC/deploy/neoag/parse_output.py，但对齐 master_backbone bb_idx）:
  读 run_neoag.py 产的 neoag_raw.csv（列 mt_peptide, wt_peptide, score）→ 建
  {(MT大写, WT大写): score} 查找表（肽-对级）→ 广播回 master_backbone_official.csv（17088 行）
  的 (MT_Subpeptide, WT_Subpeptide) 对 → 产
  scripts/out_rerun_official_8to11/Neoag_official.csv（列 bb_idx, MT_Neoag；17088 行对齐 backbone）。

★ 肽-对级 + HLA-agnostic ★ neoag 吃 (mut, wt, 位号) 出一个 neoantigen 免疫原分，不吃 HLA
  → 按 (MT,WT) 对广播：同对各 allele 行填同值。prep 阶段被 skip 的对（MT==WT/多残基差异/
  MT≠WT 长度/超 8-11mer）在 raw 中无分 → 对应 bb_idx 诚实 NaN，绝不兜底。

★ WT_Neoag ★ neoag 不对 WT 单独打 neoantigen 分 → 无 WT 列（MT-only，同 pTuneos/TSCAPE 官方口径）。
  （若收口合表需 WT_Neoag 占位列，主线在 merge 阶段补结构性 NaN；本 official 表只出 MT_Neoag。）

★ 方向（⚠️TODO 官方未核，沿用 9mer 版）★ GBM immunogenicity 分默认「越高越免疫原」→
  FLIP=False 直接用。主窗 clone github.com/vincentlaboratories/neoag 核实后：若越低越免疫原
  → 加 --flip（取负）。**与 9mer 版口径完全一致，不擅改**（复现零偏离）。

输入: --raw neoag_raw.csv、--backbone master_backbone_official.csv
输出: scripts/out_rerun_official_8to11/Neoag_official.csv
跑法（主线本地跑，我不跑）:
  python scripts/hpc_official/parse_neoag_official.py \
    --raw      HPC/deploy/neoag/rerun/neoag_raw.csv \
    --backbone scripts/out_rerun/master_backbone_official.csv \
    --out      scripts/out_rerun_official_8to11/Neoag_official.csv
依赖: 标准库 + official_io.py。Windows/HPC: pathlib + utf-8。许可: neoag non-commercial research（数字可发表）。
"""

import argparse
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from official_io import load_backbone_bb_order, write_official_mt_only  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

TOOL = "Neoag"


def clean_pep(s: str) -> str:
    s = str(s).strip().upper()
    return "" if s in ("NAN", "NONE", "<NA>", "") else s


def load_pair_score_map(raw_path: Path, flip: bool) -> dict:
    """读 neoag_raw.csv → {(MT大写, WT大写): score(float)}（肽-对级，HLA-agnostic）。"""
    lookup = {}
    n_dup = n_bad = 0
    with open(raw_path, newline="", encoding="utf-8") as f:
        rd = csv.DictReader(f)
        fields = rd.fieldnames or []
        for col in ("mt_peptide", "wt_peptide", "score"):
            if col not in fields:
                raise KeyError(f"neoag_raw.csv 缺列 '{col}'。实际列: {fields}")
        for r in rd:
            mt = clean_pep(r.get("mt_peptide", ""))
            wt = clean_pep(r.get("wt_peptide", ""))
            val = str(r.get("score", "")).strip()
            if not mt or not wt:
                continue
            try:
                v = float(val)
            except (TypeError, ValueError):
                n_bad += 1
                continue
            if v != v:  # NaN
                n_bad += 1
                continue
            if flip:
                v = -v
            key = (mt, wt)
            if key in lookup:
                n_dup += 1
            lookup[key] = v
    if n_dup:
        print(f"[parse_neoag] ⚠️ {n_dup} 个重复 (MT,WT) 对，取最后一次。", file=sys.stderr)
    print(f"[parse_neoag] 读入 {len(lookup)} 个唯一 (MT,WT) 对分（bad/空跳过={n_bad}，FLIP={flip}）",
          file=sys.stderr)
    return lookup


def main():
    script_dir = Path(__file__).resolve().parent
    default_raw = script_dir.parent.parent / "HPC" / "deploy" / "neoag" / "rerun" / "neoag_raw.csv"
    default_backbone = script_dir.parent / "out_rerun" / "master_backbone_official.csv"
    default_out = script_dir.parent / "out_rerun_official_8to11" / "Neoag_official.csv"

    ap = argparse.ArgumentParser(description="Parse neoag neoag_raw.csv → Neoag_official.csv (bb_idx 对齐)")
    ap.add_argument("--raw", default=str(default_raw))
    ap.add_argument("--backbone", default=str(default_backbone))
    ap.add_argument("--out", default=str(default_out))
    ap.add_argument("--flip", action="store_true",
                    help="翻转分数方向（取负）。⚠️仅当官方确认越低越免疫原时用（默认不翻，沿用 9mer 版）")
    args = ap.parse_args()

    backbone = Path(args.backbone)
    if not backbone.exists():
        raise FileNotFoundError(f"backbone 不存在: {backbone}")
    bb_order = load_backbone_bb_order(backbone)

    raw = Path(args.raw)
    if not raw.exists():
        print(f"[parse_neoag] WARNING: neoag_raw.csv 不存在: {raw}（run 完拉回?）。全 NaN。", file=sys.stderr)
        lookup = {}
    else:
        lookup = load_pair_score_map(raw, args.flip)

    mt_map = {}
    n_hit = n_nowt = 0
    with open(backbone, newline="", encoding="utf-8") as f:
        rd = csv.DictReader(f)
        for r in rd:
            bb = r["bb_idx"].strip()
            mt = clean_pep(r.get("MT_Subpeptide", ""))
            wt = clean_pep(r.get("WT_Subpeptide", ""))
            if not wt:
                n_nowt += 1
            if mt and wt and (mt, wt) in lookup:
                mt_map[bb] = round(lookup[(mt, wt)], 6)
                n_hit += 1

    print(f"[parse_neoag] 命中 bb_idx={n_hit}  无 WT 的 backbone 行={n_nowt}（必 NaN，非 bug）",
          file=sys.stderr)
    write_official_mt_only(Path(args.out), TOOL, bb_order, mt_map)
    print(f"[parse_neoag] 方向: MT_Neoag = GBM immunogenicity 分（FLIP={args.flip}，越高越免疫原）。"
          " ⚠️TODO 官方方向未核（沿用 9mer 版）。WT_Neoag 无独立分（MT-only）。"
          " ⚠️ HLA-agnostic: 同 (MT,WT) 对各 allele 同值。许可: non-commercial research。",
          file=sys.stderr)


if __name__ == "__main__":
    main()
