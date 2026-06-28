# -*- coding: utf-8 -*-
"""
parse_predig_hpc.py — Phase B：解析 PredIG singularity 输出，位置 join 回贴 bb_idx。

本脚本 = scripts/phaseB/run_predig_101102.py 的 parse 段拆分（HPC 路径变体），逻辑零改动。
PredIG 输出无 protein_name 但**严格保输入行序**（output[i] ↔ input[i]）：
读 workdir/input.csv（prep 写，记 epitope/HLA 防错序）+ workdir/meta.csv（同序 bb_idx,side）
+ workdir/out.csv（singularity 产），位置 join 恢复 (bb_idx, side) → PredIG 分，回贴每行。
断言 output[i].epitope/HLA == input[i] 防工具丢/重排行。

产出: $QIB_BASE/phaseB/PredIG_101102.csv   列: bb_idx, MT_PredIG, WT_PredIG
方向: PredIG 分越高越免疫原（官方原始方向，无翻转）。

用法:
    python parse_predig_hpc.py [--smoke N] [--backbone ...] [--workdir ...] [--out ...]
    --smoke N: 只做位置 join + 打印分数区间，不写正式 CSV。
环境变量覆盖: QIB_BASE / PREDIG_BACKBONE / PREDIG_WORKDIR / PREDIG_OUT
"""
import argparse
import csv
import math
import os
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# ── HPC 路径默认（实证本项目部署）─────────────────────────────────────────────
HPC_BASE = os.environ.get("QIB_BASE", "/gpfs/work/bio/jiayu2403/quantimmu")
DEFAULT_BACKBONE = os.environ.get("PREDIG_BACKBONE", f"{HPC_BASE}/phaseB/backbone_101102.csv")
DEFAULT_WORKDIR = os.environ.get("PREDIG_WORKDIR", f"{HPC_BASE}/phaseB/predig_work")
DEFAULT_OUT = os.environ.get("PREDIG_OUT", f"{HPC_BASE}/phaseB/PredIG_101102.csv")


def read_predig_out(path: Path):
    """读 PredIG out.csv → list[dict]，校验含 epitope/HLA_allele/PredIG 列。"""
    with open(path, newline="", encoding="utf-8") as f:
        out_rows = list(csv.DictReader(f))
    if not out_rows:
        raise RuntimeError(f"PredIG 输出为空: {path}")
    need = {"epitope", "HLA_allele", "PredIG"}
    have = set(out_rows[0].keys())
    if not need.issubset(have):
        raise RuntimeError(f"PredIG 输出缺列 {need - have}，实际列: {sorted(have)}")
    return out_rows


def read_input_meta(input_csv: Path, meta_csv: Path):
    """读 prep 写的 input.csv（epitope/HLA_allele...）+ 并行 meta.csv（bb_idx,side）。"""
    with open(input_csv, newline="", encoding="utf-8") as f:
        records = list(csv.DictReader(f))
    with open(meta_csv, newline="", encoding="utf-8") as f:
        meta = [(m["bb_idx"], m["side"]) for m in csv.DictReader(f)]
    if len(records) != len(meta):
        raise RuntimeError(
            f"input.csv({len(records)}) 与 meta.csv({len(meta)}) 行数不符，无法位置 join"
        )
    return records, meta


def position_join(out_rows, records, meta):
    """
    位置 join：PredIG 严格保输入行序 → output[i] ↔ records[i] ↔ meta[i]。
    断言 epitope/HLA 一致防错序，返回 (bb_idx, side) → PredIG_score。
    """
    n_out, n_in = len(out_rows), len(records)
    if n_out != n_in:
        raise RuntimeError(
            f"PredIG 行数不符: output={n_out} != input={n_in}（位置 join 不可用，"
            "检查工具是否丢/并行重排了行）"
        )
    joined = {}
    for i, (orow, irec, (bb_idx, side)) in enumerate(zip(out_rows, records, meta)):
        oe = (orow.get("epitope") or "").strip().upper()
        oh = (orow.get("HLA_allele") or "").strip()
        ie = (irec.get("epitope") or "").strip().upper()
        ih = (irec.get("HLA_allele") or "").strip()
        if oe != ie or oh != ih:
            raise RuntimeError(
                f"PredIG 位置 join 断言失败 @行{i}: "
                f"output=({oe},{oh}) != input=({ie},{ih})。"
                "输出行序被打乱，不能位置 join。"
            )
        try:
            val = float((orow.get("PredIG") or "").strip())
        except ValueError:
            val = float("nan")
        joined[(bb_idx, side)] = val
    return joined


def main():
    ap = argparse.ArgumentParser(description="Phase B PredIG parse（HPC 位置 join 回贴 bb_idx）")
    ap.add_argument("--smoke", type=int, default=0, help="只做位置 join + 打印区间，不写 CSV")
    ap.add_argument("--backbone", default=DEFAULT_BACKBONE, help="订正源 backbone_101102.csv（只读，定全量行）")
    ap.add_argument("--workdir", default=DEFAULT_WORKDIR, help="singularity 工作目录（含 input.csv/meta.csv/out.csv）")
    ap.add_argument("--out", default=DEFAULT_OUT, help="输出 PredIG_101102.csv 路径")
    args = ap.parse_args()

    backbone = Path(args.backbone)
    workdir = Path(args.workdir)
    input_csv = workdir / "input.csv"
    meta_csv = workdir / "meta.csv"
    out_csv = workdir / "out.csv"
    out_path = Path(args.out)

    for p in (backbone, input_csv, meta_csv, out_csv):
        if not p.exists():
            raise SystemExit(f"[FAIL] 缺文件: {p}")

    records, meta = read_input_meta(input_csv, meta_csv)
    out_rows = read_predig_out(out_csv)
    print(f"[parse] input={len(records)} 行 | meta={len(meta)} 行 | PredIG 输出={len(out_rows)} 行")

    joined = position_join(out_rows, records, meta)
    vals = [v for v in joined.values() if not math.isnan(v)]
    if vals:
        print(f"[parse] PredIG 分 range [{min(vals):.4f}, {max(vals):.4f}]"
              f"（应 ∈[0,1]，越高越免疫原）")
        oob = [v for v in vals if v < 0 or v > 1]
        if oob:
            print(f"[parse][WARN] {len(oob)} 个分数越界 [0,1]，首个={oob[0]}")

    if args.smoke:
        print(f"\n[smoke] 位置 join 通过、分数区间合理（{len(records)} 行）。未产 CSV。")
        return

    # ── 回贴 bb_idx，写 PredIG_101102.csv（全量 backbone 行）─────────────────────
    with open(backbone, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    def fmt(bb_idx, side):
        v = joined.get((bb_idx, side))
        if v is None or (isinstance(v, float) and math.isnan(v)):
            return ""  # NaN → 空（pandas 读为 NaN）
        return str(round(v, 6))

    c_mt = c_wt = c_mt_nan = c_wt_nan = 0
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["bb_idx", "MT_PredIG", "WT_PredIG"])
        w.writeheader()
        for r in rows:
            bb_idx = r["bb_idx"]
            mt_s = fmt(bb_idx, "MT")
            wt_s = fmt(bb_idx, "WT")
            c_mt += mt_s != ""
            c_wt += wt_s != ""
            c_mt_nan += mt_s == ""
            c_wt_nan += wt_s == ""
            w.writerow({"bb_idx": bb_idx, "MT_PredIG": mt_s, "WT_PredIG": wt_s})

    print(f"\n[parse] 写 {out_path}  ({len(rows)} 行)")
    print(f"[parse]   MT_PredIG: {c_mt} found / {c_mt_nan} NaN")
    print(f"[parse]   WT_PredIG: {c_wt} found / {c_wt_nan} NaN")
    print(f"[parse]   方向：PredIG 分越高越免疫原（无翻转）")


if __name__ == "__main__":
    main()
