#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
R1_official.py
==============
服务: QuantImmuBench 大纲 §3.1 (图1 / 表5) —— 30 工具 max-pool 单工具基线。
对应大纲: paper/QuanImmu-Paper-Outline.md §3.1 "单工具排序能力 (max-pool)"。

做什么:
  对 30 工具各取其 max-pool 列 <Tool>_max, 在 DS2 9 患者上算 per-patient Spearman
  (score vs Elispot 连续 SFC), 跨患者 Fisher-z 等权聚合 + 95%CI。每工具一行。
  这是「不聚合花哨, 就用峰值分」的基线, 后续 R2 才比各 pooling。

输入 (只读冻结表):
  data/frozen/pooled_peptide_level_30tools.csv  (130 肽级行, 9 患者)
输出 (analysis/official/):
  R1_single_maxpool_official.csv  —— 列:
    Tool, pending_DTU, fisherz_rho, ci_lo, ci_hi, n_pat, n_dropped,
    rho_p101, rho_p102, ..., rho_p110  (各患者 per-patient rho)

复用旧骨架:
  · per-patient Spearman + Fisher-z 加权 → _official_common.per_patient_spearman
    (= fusion_12methods.per_patient_spearman 口径)。
  · 各患者 rho 单列输出 → 照 per_patient_spearman_multimethod.py 的 rho_p<id> 列布局。

跑法 (主线跑, 我不跑):
  python analysis/official/R1_official.py
  python analysis/official/R1_official.py --input data/frozen/pooled_peptide_level_30tools.csv
"""

import sys
import argparse
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _official_common import (                              # noqa: E402
    load_frozen, present_patients, per_patient_spearman, pool_col,
    TOOLS_30, DTU_TOOLS, DS2_PATIENTS, MIN_PEP, FROZEN_POOLED, ensure_out_dir, r6,
)


def main():
    ap = argparse.ArgumentParser(
        description="R1 官方: 30 工具 max-pool 单工具 per-patient Spearman 基线 (§3.1)")
    ap.add_argument("--input", default=str(FROZEN_POOLED), help="冻结肽级表路径")
    ap.add_argument("--min_pep", type=int, default=MIN_PEP,
                    help=f"患者内最少肽数才算 rho (默认 {MIN_PEP})")
    args = ap.parse_args()

    df = load_frozen(args.input)
    pats = present_patients(df)
    print(f"[info] 冻结表: {df.shape}; DS2 患者({len(pats)})={pats}; min_pep={args.min_pep}")

    rows = []
    for tool in TOOLS_30:
        col = pool_col(tool, "max")
        if col not in df.columns:
            print(f"[warn] {tool}: 缺列 {col}, 跳过")
            continue
        rho, cl, ch, nu, nd, rhos_by, _ns_by = per_patient_spearman(
            df, col, patients=pats, min_pep=args.min_pep, return_perpat=True)
        row = {
            "Tool": tool,
            "pending_DTU": tool in DTU_TOOLS,   # DTU 受限工具标记, 结果照常算
            "fisherz_rho": r6(rho, 4),
            "ci_lo": r6(cl, 4),
            "ci_hi": r6(ch, 4),
            "n_pat": int(nu),
            "n_dropped": int(nd),
        }
        for pid in DS2_PATIENTS:
            row[f"rho_p{pid}"] = r6(rhos_by.get(pid, np.nan), 4)
        rows.append(row)
        ci = f"[{cl:+.3f},{ch:+.3f}]" if cl is not None and not np.isnan(cl) else "[n/a]"
        print(f"  {tool:16s} rho={rho:+.4f} {ci:>18} n_pat={nu} dropped={nd}")

    if not rows:
        sys.exit("[ERR] 无工具产出, CSV 未写")

    out_df = pd.DataFrame(rows).sort_values("fisherz_rho", ascending=False)
    out_dir = ensure_out_dir()
    out_path = out_dir / "R1_single_maxpool_official.csv"
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("# R1_single_maxpool_official.csv\n")
        f.write("# QuantImmuBench §3.1 表5: 30 工具 max-pool 单工具 per-patient Spearman 基线\n")
        f.write("# 输入=data/frozen/pooled_peptide_level_30tools.csv; DS2 9 患者; Elispot 连续 SFC\n")
        f.write("# fisherz_rho=跨患者 Fisher-z 等权聚合; ci_lo/ci_hi=95%CI; rho_p<id>=各患者 per-patient rho\n")
        f.write("# pending_DTU=True 为 DTU 受限工具(结果照常算, 部署/对外受 DTU 同意约束)\n")
        out_df.to_csv(f, index=False)
    print(f"\n[saved] {out_path}  shape={out_df.shape}")
    print("[DONE] R1")


if __name__ == "__main__":
    main()
