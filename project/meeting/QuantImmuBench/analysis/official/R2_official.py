#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
R2_official.py
==============
服务: QuantImmuBench 大纲 §3.2 (图2 洗牌图) —— 30 工具 × 8 pooling 全扫。
对应大纲: paper/QuanImmu-Paper-Outline.md §3.2 "聚合方式 (pooling) 影响"。

做什么:
  30 工具 × 8 pooling (max,mean,geomean,sum,softmax,top3mean,topk_w,rankdecay) 各算
  DS2 per-patient Fisher-z 聚合 rho。每工具找最优 pooling, 比 max vs best 的提升。
  验大纲关键发现: 结合/亲和类 (netMHCpan_BA/EL, MHCflurry) 靠 topk 聚合提升;
  免疫原类 max 即峰 (best≈max)。本脚本如实输出实测, headline 是否成立=拍板点, 不凑数。

输入 (只读冻结表):
  data/frozen/pooled_peptide_level_30tools.csv
输出 (analysis/official/):
  R2_pooling_sweep_official.csv  —— 长表: Tool, pooling, pending_DTU, fisherz_rho,
                                    ci_lo, ci_hi, n_pat, n_dropped  (30×8 行)
  R2_best_per_tool.csv           —— 每工具一行: Tool, pending_DTU, max_rho,
                                    best_pooling, best_rho, gain_best_minus_max

复用旧骨架:
  · per-patient Spearman + Fisher-z → _official_common.per_patient_spearman
  · pooling sweep "每工具 8 pooling 各算 rho 找最优" 思路 ← per_patient_spearman_multimethod
    的 sub_agg 多聚合对比 + GAP_ROADMAP §3.2 pooling 研究口径。

跑法 (主线跑, 我不跑):
  python analysis/official/R2_official.py
"""

import sys
import argparse
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _official_common import (                              # noqa: E402
    load_frozen, present_patients, per_patient_spearman, pool_col,
    TOOLS_30, POOLINGS, DTU_TOOLS, MIN_PEP, FROZEN_POOLED, ensure_out_dir, r6,
)


def main():
    ap = argparse.ArgumentParser(
        description="R2 官方: 30 工具 × 8 pooling sweep per-patient Fisher-z (§3.2)")
    ap.add_argument("--input", default=str(FROZEN_POOLED), help="冻结肽级表路径")
    ap.add_argument("--min_pep", type=int, default=MIN_PEP)
    args = ap.parse_args()

    df = load_frozen(args.input)
    pats = present_patients(df)
    print(f"[info] 冻结表: {df.shape}; DS2 患者({len(pats)})={pats}; "
          f"sweep {len(TOOLS_30)}工具×{len(POOLINGS)}pooling")

    sweep_rows = []
    best_rows = []
    for tool in TOOLS_30:
        is_dtu = tool in DTU_TOOLS
        per_pool = {}   # pooling -> rho
        for pl in POOLINGS:
            col = pool_col(tool, pl)
            if col not in df.columns or df[col].notna().sum() == 0:
                per_pool[pl] = np.nan
                sweep_rows.append(dict(Tool=tool, pooling=pl, pending_DTU=is_dtu,
                                       fisherz_rho=np.nan, ci_lo=np.nan, ci_hi=np.nan,
                                       n_pat=0, n_dropped=0))
                continue
            rho, cl, ch, nu, nd = per_patient_spearman(
                df, col, patients=pats, min_pep=args.min_pep)
            per_pool[pl] = rho
            sweep_rows.append(dict(Tool=tool, pooling=pl, pending_DTU=is_dtu,
                                   fisherz_rho=r6(rho, 4), ci_lo=r6(cl, 4),
                                   ci_hi=r6(ch, 4), n_pat=int(nu), n_dropped=int(nd)))

        max_rho = per_pool.get("max", np.nan)
        valid = {k: v for k, v in per_pool.items()
                 if v is not None and not np.isnan(v)}
        if not valid:
            print(f"[warn] {tool}: 全 pooling 无有效 rho, 跳过 best")
            continue
        best_pl = max(valid, key=valid.get)
        best_rho = valid[best_pl]
        gain = (best_rho - max_rho
                if max_rho is not None and not np.isnan(max_rho) else np.nan)
        best_rows.append(dict(Tool=tool, pending_DTU=is_dtu, max_rho=r6(max_rho, 4),
                              best_pooling=best_pl, best_rho=r6(best_rho, 4),
                              gain_best_minus_max=r6(gain, 4)))
        print(f"  {tool:16s} max={max_rho if max_rho is not None else float('nan'):+.4f} "
              f"best={best_rho:+.4f}@{best_pl:<9s} gain={gain:+.4f}")

    sweep_df = pd.DataFrame(sweep_rows)
    best_df = pd.DataFrame(best_rows).sort_values(
        "gain_best_minus_max", ascending=False)

    out_dir = ensure_out_dir()
    sweep_path = out_dir / "R2_pooling_sweep_official.csv"
    with open(sweep_path, "w", encoding="utf-8") as f:
        f.write("# R2_pooling_sweep_official.csv\n")
        f.write("# QuantImmuBench §3.2 图2: 30 工具 × 8 pooling per-patient Fisher-z 全扫 (长表)\n")
        f.write(f"# 输入={Path(args.input).name}; DS2 9 患者; pooling={POOLINGS}\n")
        f.write("# pending_DTU=True 为 DTU 受限工具(结果照常算); fisherz_rho=Fisher-z 等权聚合\n")
        sweep_df.to_csv(f, index=False)
    print(f"\n[saved] {sweep_path}  shape={sweep_df.shape}")

    best_path = out_dir / "R2_best_per_tool.csv"
    with open(best_path, "w", encoding="utf-8") as f:
        f.write("# R2_best_per_tool.csv\n")
        f.write("# QuantImmuBench §3.2: 每工具 max vs 最优 pooling 提升\n")
        f.write("# gain_best_minus_max>0 = 该工具靠非 max 聚合受益 (验大纲: 亲和/结合类靠 topk)\n")
        f.write("# gain≈0 = max 即峰 (验大纲: 免疫原类)\n")
        best_df.to_csv(f, index=False)
    print(f"[saved] {best_path}  shape={best_df.shape}")
    print("[DONE] R2")


if __name__ == "__main__":
    main()
