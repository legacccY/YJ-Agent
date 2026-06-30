# -*- coding: utf-8 -*-
"""
build_official_from_raw.py — 通用：把某工具 raw 输出 join 回官方 backbone，
产 scripts/out_official/<Tool>_official.csv（列 bb_idx, MT_<Tool>[, WT_<Tool>]）。

服务: quantimmu-bench / W3 immml slice / G1 工具补齐（新官方 RCC 数据 43 补跑肽）。

铁律（防造数）:
  - 精确匹配：HLA-aware 工具按 (subpeptide_upper, HLA_Allele) 对级查表；
    HLA-agnostic 按 peptide_upper；pair 工具(neoag)按 (MT_upper, WT_upper)。
  - 缺 → 诚实 NaN，**禁肽级兜底 / 禁别等位回填**（merge_prime 造数 bug 教训）。
  - HLA 匹配：先按 backbone 带星 'HLA-A*66:01' 直配；raw 若去星('HLA-A66:01')
    或 2 字段，统一 normalize（去 '*'、保 ':' 前 2 字段、大写）再配。

用法:
  python build_official_from_raw.py \
     --tool MUNIS --raw HPC/deploy/munis/munis_raw_official.csv \
     --pep-col peptide --hla-col HLA_Allele --score-col score \
     [--flip] [--key hla|pep|pair] [--mt-col mt_peptide --wt-col wt_peptide]

输出: scripts/out_official/<Tool>_official.csv
"""
import argparse
import sys
from pathlib import Path

import pandas as pd
import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
BACKBONE = ROOT / "scripts" / "out_official" / "master_backbone_official.csv"
OUTDIR = ROOT / "scripts" / "out_official"


def norm_hla(s):
    """带星/去星统一为 'HLA-A*66:01' 的 normalize 键: 去星 + 截前 2 字段 + 大写。"""
    if s is None or (isinstance(s, float) and np.isnan(s)):
        return None
    s = str(s).strip().upper().replace("*", "")
    if ":" in s:
        s = ":".join(s.split(":")[:2])
    return s


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tool", required=True, help="工具名，用于列名 MT_<Tool>")
    ap.add_argument("--raw", required=True, help="工具 raw csv 路径(相对 ROOT 或绝对)")
    ap.add_argument("--key", default="hla", choices=["hla", "pep", "pair"],
                    help="hla=按(pep,HLA); pep=按肽(HLA-agnostic); pair=按(MT,WT)")
    ap.add_argument("--pep-col", default="peptide")
    ap.add_argument("--hla-col", default="HLA_Allele")
    ap.add_argument("--score-col", default="score")
    ap.add_argument("--mt-col", default="mt_peptide")
    ap.add_argument("--wt-col", default="wt_peptide")
    ap.add_argument("--flip", action="store_true", help="score 取负(越低越免疫原→翻向)")
    args = ap.parse_args()

    raw_path = Path(args.raw)
    if not raw_path.is_absolute():
        raw_path = ROOT / raw_path
    bb = pd.read_csv(BACKBONE)
    raw = pd.read_csv(raw_path)
    n_bb = len(bb)

    sign = -1.0 if args.flip else 1.0
    tool = args.tool
    out = pd.DataFrame({"bb_idx": bb["bb_idx"]})
    mt_col_out = f"MT_{tool}"
    wt_col_out = f"WT_{tool}"

    def lookup_series(subpep_series, hla_series):
        vals = []
        for i, sp in enumerate(subpep_series):
            if pd.isna(sp):
                vals.append(np.nan); continue
            key = _make_key(sp, hla_series.iloc[i] if hla_series is not None else None)
            vals.append(score_map.get(key, np.nan))
        return vals

    if args.key == "pair":
        # neoag: (MT,WT) 对级, HLA-agnostic
        sc = raw[args.score_col].astype(float) * sign
        score_map = {}
        for mt, wt, v in zip(raw[args.mt_col].astype(str).str.upper(),
                             raw[args.wt_col].astype(str).str.upper(), sc):
            score_map[(mt, wt)] = v
        mt_vals, wt_vals = [], []
        for mt, wt in zip(bb["MT_Subpeptide"], bb["WT_Subpeptide"]):
            if pd.isna(mt) or pd.isna(wt):
                mt_vals.append(np.nan)
            else:
                mt_vals.append(score_map.get((str(mt).upper(), str(wt).upper()), np.nan))
            wt_vals.append(np.nan)  # neoag 不对 WT 单独打分
        out[mt_col_out] = mt_vals
        out[wt_col_out] = wt_vals
    elif args.key == "pep":
        sc = raw[args.score_col].astype(float) * sign
        score_map = {p.upper(): v for p, v in zip(raw[args.pep_col].astype(str), sc)}
        out[mt_col_out] = [score_map.get(str(p).upper(), np.nan) if pd.notna(p) else np.nan
                           for p in bb["MT_Subpeptide"]]
        out[wt_col_out] = [score_map.get(str(p).upper(), np.nan) if pd.notna(p) else np.nan
                           for p in bb["WT_Subpeptide"]]
    else:  # hla-aware
        sc = raw[args.score_col].astype(float) * sign
        score_map = {}
        for p, h, v in zip(raw[args.pep_col].astype(str), raw[args.hla_col], sc):
            score_map[(p.upper(), norm_hla(h))] = v
        out[mt_col_out] = [score_map.get((str(p).upper(), norm_hla(h)), np.nan)
                           if pd.notna(p) else np.nan
                           for p, h in zip(bb["MT_Subpeptide"], bb["HLA_Allele"])]
        out[wt_col_out] = [score_map.get((str(p).upper(), norm_hla(h)), np.nan)
                           if pd.notna(p) else np.nan
                           for p, h in zip(bb["WT_Subpeptide"], bb["HLA_Allele"])]

    out_path = OUTDIR / f"{tool}_official.csv"
    out.to_csv(out_path, index=False)
    mt_nonnull = out[mt_col_out].notna().sum()
    wt_nonnull = out[wt_col_out].notna().sum()
    print(f"[build] {tool}: rows={len(out)} (backbone {n_bb}) "
          f"MT非空={mt_nonnull} WT非空={wt_nonnull}")
    print(f"[build] wrote {out_path}")
    if len(out) != n_bb:
        print("[WARN] 行数 != backbone!"); sys.exit(1)


if __name__ == "__main__":
    main()
