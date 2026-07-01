#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
R1_official.py
==============
服务: QuantImmuBench 大纲 §3.1 (图1 / 表5) —— 30 工具 max-pool 单工具基线。
对应大纲: paper/QuanImmu-Paper-Outline.md §3.1 "单工具排序能力 (max-pool)"。

★ 2026-07-01 Part D Phase 3 口径 (干净表 + 新评判标准, 见 04_LOG):
  输入 = 干净表 pooled_clean_9mer.csv (130×1536, 含突变去噪 + 51 pooling 变体 + peplen 列)。
  headline 单工具用 **零选择 <tool>_max** (B5, 不 in-sample 挑 pooling)。评判两口径并列:
    · 裸等权 (raw): per_patient_spearman(equal) —— 旧口径, 排序主键。
    · 控肽长 (lenctrl, B2): per_patient_partial_spearman(ctrl='peplen') —— 隔离「肽长搭便车」
      伪迹 (如 HLAthena 裸 ρ~0.6 疑因偏爱长肽; 控肽长后预期回落 ~0.25, 让伪迹现形)。
  CI 一律 cluster-bootstrap over patients (B4, 2000×), 弃固定效应过窄 CI; 裸/控肽长各一组。
  【旧 count-clean 注释已删】: 干净表不带 count_conf 列, 混杂改由 B2 偏相关在度量层直接控。

做什么:
  对 30 工具各取其 max-pool 列 <Tool>_max, 在 DS2 9 患者上算 per-patient Spearman
  (score vs Elispot 连续 SFC), 跨患者 Fisher-z 等权聚合。每工具一行, 裸 + 控肽长两版 rho +
  bootstrap 95%CI。排序按裸 rho, 但控肽长列让肽长伪迹现形。后续 R2 才比各 pooling。

输入 (只读干净表):
  data/frozen/pooled_clean_9mer.csv  (130 肽级行, 9 患者, 含 peplen)
输出 (analysis/official/):
  R1_single_maxpool_official.csv  —— 列:
    Tool, pending_DTU,
    fisherz_rho_raw, ci_lo_raw, ci_hi_raw,            (裸等权 + bootstrap CI)
    fisherz_rho_lenctrl, ci_lo_lenctrl, ci_hi_lenctrl, (控肽长偏相关 + bootstrap CI)
    n_pat, n_dropped,
    rho_p101, rho_p102, ..., rho_p110  (各患者裸 per-patient rho)

复用旧骨架:
  · per-patient Spearman + Fisher-z 等权 → _official_common.per_patient_spearman
  · 控肽长偏相关 (B2) → per_patient_partial_spearman(ctrl='peplen')
  · bootstrap CI (B4) → bootstrap_patient_ci
  · 各患者 rho 单列输出 → 照 per_patient_spearman_multimethod.py 的 rho_p<id> 列布局。

跑法 (主线跑, 我不跑):
  python analysis/official/R1_official.py
  python analysis/official/R1_official.py --input data/frozen/pooled_clean_allwindow.csv
"""

import sys
import argparse
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _official_common import (                              # noqa: E402
    load_frozen, present_patients, per_patient_spearman,
    per_patient_partial_spearman, bootstrap_patient_ci, pool_col,
    TOOLS_30, DTU_TOOLS, DS2_PATIENTS, MIN_PEP, FROZEN_POOLED, ensure_out_dir, r6,
)


def main():
    ap = argparse.ArgumentParser(
        description="R1 官方: 30 工具 max-pool 单工具 per-patient Spearman 基线 (§3.1)")
    ap.add_argument("--input", default=str(FROZEN_POOLED), help="干净肽级表路径")
    ap.add_argument("--min_pep", type=int, default=MIN_PEP,
                    help=f"患者内最少肽数才算 rho (默认 {MIN_PEP})")
    ap.add_argument("--ctrl", default="peplen", help="控制变量列 (B2 偏相关, 默认 peplen)")
    ap.add_argument("--n_boot", type=int, default=2000, help="bootstrap 重采样次数 (B4)")
    ap.add_argument("--seed", type=int, default=42, help="bootstrap 随机种子")
    args = ap.parse_args()

    df = load_frozen(args.input)
    pats = present_patients(df)
    print(f"[info] 干净表: {df.shape}; DS2 患者({len(pats)})={pats}; min_pep={args.min_pep}; "
          f"ctrl={args.ctrl}; n_boot={args.n_boot}")

    rows = []
    for tool in TOOLS_30:
        col = pool_col(tool, "max")
        if col not in df.columns:
            print(f"[warn] {tool}: 缺列 {col}, 跳过")
            continue
        # 裸等权 per-patient Spearman (排序主键) + 各患者 rho
        rho_raw, _cl0, _ch0, nu, nd, rhos_by, _ns_by = per_patient_spearman(
            df, col, patients=pats, min_pep=args.min_pep, return_perpat=True)
        # 控肽长偏相关 (B2)
        rho_len, _cl1, _ch1, nu_len, nd_len = per_patient_partial_spearman(
            df, col, ctrl=args.ctrl, patients=pats, min_pep=args.min_pep)
        # bootstrap 95%CI (B4): 裸 + 控肽长各一组
        _, cl_raw, ch_raw, _ = bootstrap_patient_ci(
            df, col, n_boot=args.n_boot, seed=args.seed, patients=pats, min_pep=args.min_pep)
        _, cl_len, ch_len, _ = bootstrap_patient_ci(
            df, col, n_boot=args.n_boot, seed=args.seed, ctrl=args.ctrl,
            patients=pats, min_pep=args.min_pep)
        row = {
            "Tool": tool,
            "pending_DTU": tool in DTU_TOOLS,   # DTU 受限工具标记, 结果照常算
            "fisherz_rho_raw": r6(rho_raw, 4),
            "ci_lo_raw": r6(cl_raw, 4),
            "ci_hi_raw": r6(ch_raw, 4),
            "fisherz_rho_lenctrl": r6(rho_len, 4),
            "ci_lo_lenctrl": r6(cl_len, 4),
            "ci_hi_lenctrl": r6(ch_len, 4),
            "n_pat": int(nu),
            "n_dropped": int(nd),
        }
        for pid in DS2_PATIENTS:
            row[f"rho_p{pid}"] = r6(rhos_by.get(pid, np.nan), 4)
        rows.append(row)
        rr = f"{rho_raw:+.4f}" if rho_raw is not None and not np.isnan(rho_raw) else "  NaN "
        rl = f"{rho_len:+.4f}" if rho_len is not None and not np.isnan(rho_len) else "  NaN "
        cir = (f"[{cl_raw:+.3f},{ch_raw:+.3f}]"
               if cl_raw is not None and not np.isnan(cl_raw) else "[n/a]")
        print(f"  {tool:16s} raw={rr} {cir:>18} | lenctrl={rl}  n_pat={nu} dropped={nd}")

    if not rows:
        sys.exit("[ERR] 无工具产出, CSV 未写")

    out_df = pd.DataFrame(rows).sort_values("fisherz_rho_raw", ascending=False)
    out_dir = ensure_out_dir()
    out_path = out_dir / "R1_single_maxpool_official.csv"
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("# R1_single_maxpool_official.csv\n")
        f.write("# QuantImmuBench §3.1 表5: 30 工具 max-pool 单工具 per-patient Spearman 基线\n")
        f.write(f"# 输入={Path(args.input).name}; DS2 9 患者; Elispot 连续 SFC; headline 零选择 <tool>_max (B5)\n")
        f.write("# fisherz_rho_raw=裸等权跨患者 Fisher-z; fisherz_rho_lenctrl=控肽长偏相关(B2, ctrl=peplen)\n")
        f.write(f"# ci_*=cluster-bootstrap over patients 95%CI (B4, n_boot={args.n_boot}, seed={args.seed}); 排序按 raw\n")
        f.write("# rho_p<id>=各患者裸 per-patient rho; pending_DTU=True 为 DTU 受限工具(结果照常算, 部署受 DTU 同意约束)\n")
        out_df.to_csv(f, index=False)
    print(f"\n[saved] {out_path}  shape={out_df.shape}")
    print("[DONE] R1")


if __name__ == "__main__":
    main()
