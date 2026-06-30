# -*- coding: utf-8 -*-
"""
parse_predig_official.py — 解析 PredIG official 输出 → PredIG_official.csv，对齐 backbone。

PredIG 输出（predig_out.csv）无 protein_name 但**严格保输入行序**（output[i] ↔ input[i]），
故三方按行序位置对齐：
  predig_out.csv   (PredIG 产，列 epitope,HLA_allele,PredIG,...) — 2005 行
  predig_input.csv (喂工具的输入，列 epitope,HLA_allele,protein_seq,protein_name) — 2005 行
  predig_input_map.csv (列 key,backbone_indices) — 2005 行，把每个输入行映射到 backbone bb_idx 列表

对齐三道防线（任一不符即报错停，绝不静默造数）：
  1. out[i].epitope/HLA_allele == input[i].epitope/HLA_allele  （防工具丢/重排行）
  2. 由 input[i] 重建 key == map[i].key                         （防 input 与 map 错位）
  3. side（MT/WT）由 protein_name 里的 |MT|/|WT| 判定

每个输入行的 PredIG 分按 map 的 backbone_indices 回贴到对应 bb_idx 的 MT/WT 列。
backbone 全集（bb_idx universe）= master_backbone_official.csv（1761 行）。
精确(肽,等位)匹配缺 → 该 (bb_idx, side) = NaN（空），禁肽级兜底造数。

产出: PredIG_official.csv   列: bb_idx, MT_PredIG, WT_PredIG   （1761 行）
方向: PredIG 分越高越免疫原（官方原始方向，无翻转）。

用法:
    python parse_predig_official.py [--out-csv ...] [--input-csv ...] [--map-csv ...]
                                    [--backbone ...] [--out ...]
环境变量覆盖默认 HPC 路径: QIB_BASE
"""
import argparse
import ast
import csv
import math
import os
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

HPC_BASE = os.environ.get("QIB_BASE", "/gpfs/work/bio/jiayu2403/quantimmu")
OFFICIAL = f"{HPC_BASE}/official_inputs/out_official"
DEFAULT_OUT_CSV   = f"{HPC_BASE}/official_inputs/predig_out/predig_out.csv"
DEFAULT_INPUT_CSV = f"{OFFICIAL}/predig_input.csv"
DEFAULT_MAP_CSV   = f"{OFFICIAL}/predig_input_map.csv"
DEFAULT_BACKBONE  = f"{OFFICIAL}/master_backbone_official.csv"
DEFAULT_OUT       = f"{HPC_BASE}/official_inputs/predig_out/PredIG_official.csv"


def read_csv(path: Path):
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def build_key(rec):
    """重建 map key = epitope|HLA_allele|protein_seq|protein_name（与 prep 写 map 时一致）。"""
    return "|".join([
        (rec.get("epitope") or "").strip(),
        (rec.get("HLA_allele") or "").strip(),
        (rec.get("protein_seq") or "").strip(),
        (rec.get("protein_name") or "").strip(),
    ])


def side_of(protein_name: str):
    """从 protein_name（形如 bbid|MT|win9|pos1|HLA-...）判 MT/WT。"""
    pn = protein_name or ""
    if "|MT|" in pn:
        return "MT"
    if "|WT|" in pn:
        return "WT"
    return None


def main():
    ap = argparse.ArgumentParser(description="PredIG official → PredIG_official.csv（按 map 对齐 bb_idx）")
    ap.add_argument("--out-csv",   default=DEFAULT_OUT_CSV,  help="PredIG 工具输出 predig_out.csv")
    ap.add_argument("--input-csv", default=DEFAULT_INPUT_CSV, help="喂工具的 predig_input.csv（位置对齐 + 防错序）")
    ap.add_argument("--map-csv",   default=DEFAULT_MAP_CSV,   help="predig_input_map.csv（key→backbone_indices）")
    ap.add_argument("--backbone",  default=DEFAULT_BACKBONE,  help="master_backbone_official.csv（定 bb_idx 全集）")
    ap.add_argument("--out",       default=DEFAULT_OUT,       help="输出 PredIG_official.csv 路径")
    args = ap.parse_args()

    paths = {k: Path(v) for k, v in vars(args).items()}
    for k in ("out_csv", "input_csv", "map_csv", "backbone"):
        if not paths[k].exists():
            raise SystemExit(f"[FAIL] 缺文件 --{k.replace('_','-')}: {paths[k]}")

    out_rows = read_csv(paths["out_csv"])
    in_rows  = read_csv(paths["input_csv"])
    map_rows = read_csv(paths["map_csv"])

    # ── 列校验 ───────────────────────────────────────────────────────────────
    if not out_rows:
        raise SystemExit(f"[FAIL] PredIG 输出为空: {paths['out_csv']}")
    need = {"epitope", "HLA_allele", "PredIG"}
    have = set(out_rows[0].keys())
    if not need.issubset(have):
        raise SystemExit(f"[FAIL] PredIG 输出缺列 {need - have}；实际列: {sorted(have)}")

    n = len(out_rows)
    if not (len(in_rows) == len(map_rows) == n):
        raise SystemExit(
            f"[FAIL] 行数不符无法位置对齐: out={n} input={len(in_rows)} map={len(map_rows)}"
        )
    print(f"[parse] 三方各 {n} 行（out/input/map）")

    # ── 位置 join + 三道断言，回贴到 (bb_idx, side) → PredIG 分 ─────────────────
    joined = {}            # (bb_idx_str, side) -> float
    n_assigned = n_nan_score = 0
    for i, (orow, irec, mrow) in enumerate(zip(out_rows, in_rows, map_rows)):
        # 防线1：输出↔输入 epitope/HLA 一致（防工具丢/重排行）
        oe = (orow.get("epitope") or "").strip().upper()
        oh = (orow.get("HLA_allele") or "").strip()
        ie = (irec.get("epitope") or "").strip().upper()
        ih = (irec.get("HLA_allele") or "").strip()
        if oe != ie or oh != ih:
            raise SystemExit(
                f"[FAIL] 位置 join 断言失败 @行{i}: out=({oe},{oh}) != input=({ie},{ih})。"
                "输出行序被打乱，不能位置 join。"
            )
        # 防线2：input 重建 key == map key（防 input/map 错位）
        k_in = build_key(irec)
        k_map = (mrow.get("key") or "").strip()
        if k_in != k_map:
            raise SystemExit(
                f"[FAIL] input↔map key 不符 @行{i}:\n  input={k_in}\n  map  ={k_map}"
            )
        # 防线3：side 由 protein_name 判
        side = side_of(irec.get("protein_name", ""))
        if side is None:
            raise SystemExit(f"[FAIL] @行{i} protein_name 无 |MT|/|WT|: {irec.get('protein_name')}")

        # PredIG 分
        try:
            val = float((orow.get("PredIG") or "").strip())
        except ValueError:
            val = float("nan")
            n_nan_score += 1

        # backbone_indices: 形如 "[0]" / "[0, 1]"
        try:
            idxs = ast.literal_eval((mrow.get("backbone_indices") or "[]").strip())
        except (ValueError, SyntaxError):
            raise SystemExit(f"[FAIL] @行{i} backbone_indices 解析失败: {mrow.get('backbone_indices')}")
        if not isinstance(idxs, (list, tuple)):
            idxs = [idxs]

        for bb in idxs:
            joined[(str(bb), side)] = val
            n_assigned += 1

    print(f"[parse] 回贴 {n_assigned} 个 (bb_idx,side) 单元（含 {n_nan_score} 个工具分非数值）")

    # ── 写 PredIG_official.csv（bb_idx 全集 = backbone，缺则 NaN）──────────────
    bb_rows = read_csv(paths["backbone"])
    if not bb_rows or "bb_idx" not in bb_rows[0]:
        raise SystemExit(f"[FAIL] backbone 缺 bb_idx 列: {paths['backbone']}")

    def fmt(bb_idx, side):
        v = joined.get((str(bb_idx), side))
        if v is None or (isinstance(v, float) and math.isnan(v)):
            return ""  # NaN → 空（pandas 读为 NaN）
        return str(round(v, 6))

    c_mt = c_wt = c_mt_nan = c_wt_nan = 0
    out_path = paths["out"]
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["bb_idx", "MT_PredIG", "WT_PredIG"])
        w.writeheader()
        for r in bb_rows:
            bb_idx = r["bb_idx"]
            mt_s = fmt(bb_idx, "MT")
            wt_s = fmt(bb_idx, "WT")
            c_mt += mt_s != ""
            c_wt += wt_s != ""
            c_mt_nan += mt_s == ""
            c_wt_nan += wt_s == ""
            w.writerow({"bb_idx": bb_idx, "MT_PredIG": mt_s, "WT_PredIG": wt_s})

    print(f"\n[parse] 写 {out_path}  ({len(bb_rows)} 行)")
    print(f"[parse]   MT_PredIG: {c_mt} found / {c_mt_nan} NaN")
    print(f"[parse]   WT_PredIG: {c_wt} found / {c_wt_nan} NaN")
    print(f"[parse]   方向：PredIG 分越高越免疫原（无翻转）")


if __name__ == "__main__":
    main()
