#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
parse_transhla_official.py — TransHLA transhla_raw.csv → bb_idx 对齐的官方合表列
服务: quantimmu-bench §改动②③ 8-11mer 全量重跑（slice_local_b, lever=TransHLA）

作用（仿 parse_repitope_official.py 的 HLA-agnostic 广播，但对齐 master_backbone bb_idx）:
  读 run_transhla.py 产的 transhla_raw.csv（列 peptide, prob, label）→ 建
  {peptide大写: prob} 查找表 → 广播回 master_backbone_official.csv（17088 行）的
  MT_Subpeptide / WT_Subpeptide → 产 scripts/out_rerun_official_8to11/TransHLA_official.csv
  （列 bb_idx, MT_TransHLA, WT_TransHLA；17088 行对齐 backbone）。

★ HLA-agnostic ★ TransHLA 只依赖肽序列、不吃 HLA（首个无需 allele 的 epitope detector）
  → 按【肽】广播：同一肽的所有 backbone 行（含各 allele）填同值。缺（超长/未打分）→ NaN。
  与 Repitope 同 caveat：benchmark 报告须标注同肽各 allele 同值。

★ 方向 ★ prob = 「是表位」概率 [0-1]，越高越免疫原，**不翻转** → MT_TransHLA/WT_TransHLA = prob。

★ 长度 ★ TransHLA_I 支持 8-14mer；backbone 全 8-11 → 全在支持范围。run 阶段未覆盖的肽 → NaN。

输入: --raw transhla_raw.csv、--backbone master_backbone_official.csv
输出: scripts/out_rerun_official_8to11/TransHLA_official.csv
跑法（主线本地跑，我不跑）:
  python scripts/hpc_official/parse_transhla_official.py \
    --raw      HPC/deploy/transhla/transhla_raw.csv \
    --backbone scripts/out_rerun/master_backbone_official.csv \
    --out      scripts/out_rerun_official_8to11/TransHLA_official.csv
依赖: 标准库 + official_io.py。Windows/HPC: pathlib + utf-8。许可: TransHLA MIT（数字可发表）。
"""

import argparse
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from official_io import load_backbone_bb_order, write_official_mt_wt  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

TOOL = "TransHLA"


def clean_pep(s: str) -> str:
    s = str(s).strip().upper()
    return "" if s in ("NAN", "NONE", "<NA>", "") else s


def load_score_map(raw_path: Path) -> dict:
    """读 transhla_raw.csv → {peptide大写: prob(float)}（HLA-agnostic 肽-only）。"""
    lookup = {}
    n_dup = n_nan = 0
    with open(raw_path, newline="", encoding="utf-8") as f:
        rd = csv.DictReader(f)
        fields = rd.fieldnames or []
        for col in ("peptide", "prob"):
            if col not in fields:
                raise KeyError(f"transhla_raw.csv 缺列 '{col}'。实际列: {fields}")
        for r in rd:
            pep = clean_pep(r.get("peptide", ""))
            val = str(r.get("prob", "")).strip()
            if not pep:
                continue
            try:
                v = float(val)
            except (TypeError, ValueError):
                n_nan += 1
                continue
            if v != v:  # NaN
                n_nan += 1
                continue
            if pep in lookup:
                n_dup += 1
            lookup[pep] = v
    if n_dup:
        print(f"[parse_transhla] ⚠️ {n_dup} 个重复肽 key，取最后一次。", file=sys.stderr)
    print(f"[parse_transhla] 读入 {len(lookup)} 个唯一肽分（NaN/空跳过={n_nan}）", file=sys.stderr)
    return lookup


def main():
    script_dir = Path(__file__).resolve().parent
    default_raw = script_dir.parent.parent / "HPC" / "deploy" / "transhla" / "transhla_raw.csv"
    default_backbone = script_dir.parent / "out_rerun" / "master_backbone_official.csv"
    default_out = script_dir.parent / "out_rerun_official_8to11" / "TransHLA_official.csv"

    ap = argparse.ArgumentParser(description="Parse TransHLA transhla_raw.csv → TransHLA_official.csv (bb_idx 对齐)")
    ap.add_argument("--raw", default=str(default_raw))
    ap.add_argument("--backbone", default=str(default_backbone))
    ap.add_argument("--out", default=str(default_out))
    args = ap.parse_args()

    backbone = Path(args.backbone)
    if not backbone.exists():
        raise FileNotFoundError(f"backbone 不存在: {backbone}")
    bb_order = load_backbone_bb_order(backbone)

    raw = Path(args.raw)
    if not raw.exists():
        print(f"[parse_transhla] WARNING: transhla_raw.csv 不存在: {raw}（run 完拉回?）。全 NaN。",
              file=sys.stderr)
        lookup = {}
    else:
        lookup = load_score_map(raw)

    mt_map = {}
    wt_map = {}
    with open(backbone, newline="", encoding="utf-8") as f:
        rd = csv.DictReader(f)
        for r in rd:
            bb = r["bb_idx"].strip()
            mt = clean_pep(r.get("MT_Subpeptide", ""))
            wt = clean_pep(r.get("WT_Subpeptide", ""))
            if mt and mt in lookup:
                mt_map[bb] = round(lookup[mt], 6)
            if wt and wt in lookup:
                wt_map[bb] = round(lookup[wt], 6)

    write_official_mt_wt(Path(args.out), TOOL, bb_order, mt_map, wt_map)
    print("[parse_transhla] 方向: MT_TransHLA/WT_TransHLA = prob (是表位概率 0-1, 越大越免疫原, 不翻转)。"
          " ⚠️ HLA-agnostic: 同肽各 allele 同值（报告须标 caveat，同 Repitope）。许可: MIT。",
          file=sys.stderr)


if __name__ == "__main__":
    main()
