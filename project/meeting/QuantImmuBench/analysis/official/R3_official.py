#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
R3_official.py
==============
服务: QuantImmuBench 大纲 §3.3.1 (表6) —— 12 fusion 法 × {3,4,6,7} 维 LOPO 整合。
对应大纲: paper/QuanImmu-Paper-Outline.md §3.3.1 "多维 fusion 对比 (表6)"。

做什么:
  12 fusion 法 (8 无监督 rank 融合 + 4 学习型 LOPO) × 4 个维度集 {3,4,6,7} 维,
  在 DS2 9 患者上算 per-patient Spearman (病人内 rank 融合, 学习型 patient-level
  LOPO 无泄漏), Fisher-z 等权聚合 + 95%CI。验大纲: geomean 为唯一过双重检验法则。

输入 (只读冻结表):
  data/frozen/pooled_peptide_level_30tools.csv
输出 (analysis/official/):
  R3_fusion_12methods_official.csv  —— 列: method, ndim, dims, fisherz_rho,
                                       ci_low, ci_high, n_pat

复用旧骨架:
  · 12 fusion 法 + apply_fusion + per-patient Spearman → _official_common
    (= analysis/fusion_12methods.py 全套引擎, 改读冻结表)。
  · 维度集 {3,4,6,7} 扩展口径 ← fusion_12methods.py DIM3/DIM4/DIM6/DIM7。

★★★ 维度集成员 = selection, 见下方 DIM_TOOLSETS 定义 (第 ~70 行起):
    TODO 待袁老师/朱同学确认 outline 表6 实际用哪些工具 + 哪个 pooling 列。
    本脚本不擅自创新成员: 6 维=旧 surv6 口径; 3/4/7 维按 fusion_12methods 同源扩展,
    旧脚本的 pool_netAffneg_top20 (亲和-negative 合成列) 冻结表无对应, 暂以
    netMHCpan_BA 最优 pooling 作亲和代理 [TODO 待确认]。各工具 pooling 列取其 R2 最优。

跑法 (主线跑, 我不跑):
  python analysis/official/R3_official.py
  python analysis/official/R3_official.py --seed 42
"""

import sys
import argparse
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _official_common import (                              # noqa: E402
    load_frozen, present_patients, per_patient_spearman, apply_fusion,
    best_pooling_for_tool, pool_col, METHOD_ORDER, MIN_PEP, FROZEN_POOLED,
    ensure_out_dir, r6,
)

# ═══════════════════════════════════════════════════════════════════════════════
# ★ TODO: 维度集成员 = selection, 待袁老师/朱同学确认 outline 表6 用哪些工具。
#   不擅自创新成员。下列为旧 fusion_12methods.py 同源口径迁到冻结表 (工具短名):
#     · 6 维 = surv6 (PredIG/IMPROVE/pTuneos/PRIME/ImmuneApp/deepHLApan) —— 旧 SURV6_TOOLS
#     · 3 维 = [亲和代理, PRIME, deepHLApan] —— 旧 DIM3=[pool_netAffneg_top20,PRIME,deepHLApan]
#              冻结表无 pool_netAffneg_top20, 暂用 netMHCpan_BA 作亲和代理 [TODO 待确认]
#     · 4 维 = 3 维 + PredIG —— 旧 DIM4=DIM3+MT_PredIG
#     · 7 维 = 6 维 surv6 + 亲和代理(netMHCpan_BA) —— 旧 DIM7=SURV6+pool_netAffneg_top20
#   每工具用其 R2 最优 pooling 列 (best_pooling_for_tool 内部确定, 与 §3.2 一致)。
# ═══════════════════════════════════════════════════════════════════════════════
AFFINITY_PROXY = "netMHCpan_BA"   # TODO 待确认: 旧 pool_netAffneg_top20 的冻结表代理
SURV6 = ["PredIG", "IMPROVE", "pTuneos", "PRIME", "ImmuneApp", "deepHLApan"]
DIM_TOOLSETS = {
    3: [AFFINITY_PROXY, "PRIME", "deepHLApan"],
    4: [AFFINITY_PROXY, "PRIME", "deepHLApan", "PredIG"],
    6: list(SURV6),
    7: list(SURV6) + [AFFINITY_PROXY],
}


def resolve_dim_cols(df, tools, pats, min_pep):
    """每工具取 R2 最优 pooling 列 -> dim_cols。缺工具警告并剔除。"""
    cols, used = [], []
    for t in tools:
        best_pl, _rho, _all = best_pooling_for_tool(df, t, patients=pats, min_pep=min_pep)
        if best_pl is None:
            print(f"[warn] {t}: 无有效 pooling, 剔除该维")
            continue
        cols.append(pool_col(t, best_pl))
        used.append(f"{t}_{best_pl}")
    return cols, used


def main():
    ap = argparse.ArgumentParser(
        description="R3 官方: 12 fusion × {3,4,6,7} 维 LOPO per-patient Spearman (§3.3.1 表6)")
    ap.add_argument("--input", default=str(FROZEN_POOLED), help="冻结肽级表路径")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--min_pep", type=int, default=MIN_PEP)
    args = ap.parse_args()

    df = load_frozen(args.input)
    pats = present_patients(df)
    print(f"[info] 冻结表: {df.shape}; DS2 患者({len(pats)})={pats}; seed={args.seed}")

    rows = []
    for ndim in sorted(DIM_TOOLSETS.keys()):
        dim_cols, used = resolve_dim_cols(df, DIM_TOOLSETS[ndim], pats, args.min_pep)
        print("\n" + "=" * 72)
        print(f"[{ndim} 维] tools={DIM_TOOLSETS[ndim]}  -> 列(各 R2 最优 pooling)={used}")
        print("=" * 72)
        if len(dim_cols) < 2:
            print(f"[warn] {ndim} 维有效列<2, 跳过")
            continue
        for method in METHOD_ORDER:
            s = apply_fusion(df, dim_cols, method, patients=pats, seed=args.seed)
            rho, cl, ch, nu, _nd = per_patient_spearman(
                df, s, patients=pats, min_pep=args.min_pep)
            rows.append(dict(method=method, ndim=ndim, dims=";".join(used),
                             fisherz_rho=r6(rho), ci_low=r6(cl), ci_high=r6(ch),
                             n_pat=int(nu)))
            ci = f"[{cl:+.4f},{ch:+.4f}]" if cl is not None and not np.isnan(cl) else "[n/a]"
            print(f"  {method:<20s} rho={rho:+.4f} CI{ci} n_pat={nu}")

    if not rows:
        sys.exit("[ERR] 无产出, CSV 未写")
    out_df = pd.DataFrame(rows)
    out_dir = ensure_out_dir()
    out_path = out_dir / "R3_fusion_12methods_official.csv"
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("# R3_fusion_12methods_official.csv\n")
        f.write("# QuantImmuBench §3.3.1 表6: 12 fusion 法 × {3,4,6,7} 维 LOPO per-patient Spearman\n")
        f.write(f"# 输入={Path(args.input).name}; DS2 9 患者; 无监督法不碰标签, 学习型 LOPO 无泄漏\n")
        f.write("# ★ 维度集成员=selection, TODO 待袁/朱确认 (见脚本 DIM_TOOLSETS); 各维取 R2 最优 pooling 列\n")
        f.write("# dims=该维度集实际使用的 <Tool>_<pooling> 列 (分号分隔)\n")
        out_df.to_csv(f, index=False)
    print(f"\n[saved] {out_path}  shape={out_df.shape}")
    print("[DONE] R3")


if __name__ == "__main__":
    main()
