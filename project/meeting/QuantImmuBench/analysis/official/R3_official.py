#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
R3_official.py
==============
服务: QuantImmuBench 大纲 §3.3.1 (表6) —— 12 fusion 法 × {3,4,6,7} 维 LOPO 整合。
对应大纲: paper/QuanImmu-Paper-Outline.md §3.3.1 "多维 fusion 对比 (表6)"。

★ 2026-07-01 Part D Phase 3 口径 (干净表 + 新评判标准, 见 04_LOG):
  · [B5 零选择] 每工具维度列 headline 用零选择 <tool>_max, 去 in-sample pooling selection;
    另出一组用 best-pooling 维度 (best_pooling_for_tool) 作补充对照 (标 in-sample 上界)。
  · [affinity 两版] AFFINITY_PROXY=netMHCpan_BA 维度: 零选择组同出两版 —— netAffneg
    (netMHCpan_BA_topk_k20_a0, 对齐 outline §3.2 亲和聚合) 与 _max, 两版都出 (dim_config 标注)。
  · [B2/B4] 12 fusion 每个加控肽长版 rho (fusion 分数走 per_patient_partial_spearman(ctrl=
    'peplen')) + cluster-bootstrap over patients 95%CI (对裸 fusion 分数)。
  【旧 count-clean 注释已删】: best_pooling_for_tool 不再 count-clean (干净表无 count_conf 列);
    混杂改由 B2 偏相关在度量层控。

做什么:
  12 fusion 法 (8 无监督 rank 融合 + 4 学习型 LOPO) × 4 个维度集 {3,4,6,7} 维 × 维度配置
  (max/aff=max、max/aff=netaff、best 上界), 在 DS2 9 患者上算 per-patient Spearman (病人内
  rank 融合, 学习型 patient-level LOPO 无泄漏), Fisher-z 等权聚合。验大纲: geomean 为唯一
  过双重检验法则。

输入 (只读干净表):
  data/frozen/pooled_clean_9mer.csv
输出 (analysis/official/):
  R3_fusion_12methods_official.csv  —— 列: method, ndim, dim_config, dims,
                                       rho_raw, rho_lenctrl, ci_lo, ci_hi, n_pat

复用旧骨架:
  · 12 fusion 法 + apply_fusion + per-patient Spearman → _official_common
  · 控肽长偏相关 (B2) → per_patient_partial_spearman; bootstrap CI (B4) → bootstrap_patient_ci
  · 维度集 {3,4,6,7} 扩展口径 ← fusion_12methods.py DIM3/DIM4/DIM6/DIM7。

★★★ 维度集成员 = selection (TODO 待袁老师/朱同学确认 outline 表6):
    6 维=旧 surv6 口径; 3/4/7 维按 fusion_12methods 同源扩展。旧 pool_netAffneg_top20
    (亲和-negative top20 合成列) = 干净表 netMHCpan_BA_topk_k20_a0 (netAffneg), 对齐 outline §3.2。

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
    load_frozen, present_patients, per_patient_spearman,
    per_patient_partial_spearman, bootstrap_patient_ci, apply_fusion,
    best_pooling_for_tool, pool_col, METHOD_ORDER, MIN_PEP, FROZEN_POOLED,
    ensure_out_dir, r6,
)

# ═══════════════════════════════════════════════════════════════════════════════
# 维度集成员 (工具短名, TODO 待袁/朱确认 outline 表6):
#   · 6 维 = surv6 (PredIG/IMPROVE/pTuneos/PRIME/ImmuneApp/deepHLApan) —— 旧 SURV6_TOOLS
#   · 3 维 = [亲和代理, PRIME, deepHLApan] —— 旧 DIM3=[pool_netAffneg_top20,PRIME,deepHLApan]
#   · 4 维 = 3 维 + PredIG —— 旧 DIM4=DIM3+MT_PredIG
#   · 7 维 = 6 维 surv6 + 亲和代理 —— 旧 DIM7=SURV6+pool_netAffneg_top20
# ═══════════════════════════════════════════════════════════════════════════════
AFFINITY_PROXY = "netMHCpan_BA"                     # 旧 pool_netAffneg_top20 对应工具
AFFINITY_NETAFF_COL = "netMHCpan_BA_topk_k20_a0"    # netAffneg 列 (对齐 outline §3.2)
SURV6 = ["PredIG", "IMPROVE", "pTuneos", "PRIME", "ImmuneApp", "deepHLApan"]
DIM_TOOLSETS = {
    3: [AFFINITY_PROXY, "PRIME", "deepHLApan"],
    4: [AFFINITY_PROXY, "PRIME", "deepHLApan", "PredIG"],
    6: list(SURV6),
    7: list(SURV6) + [AFFINITY_PROXY],
}

# 维度配置 (dim_config): 各出一组维度列
#   · max/aff=max   零选择, 亲和代理用 _max      (B5 headline)
#   · max/aff=netaff 零选择, 亲和代理用 netAffneg (B5 headline, 对齐 §3.2)
#   · best          in-sample 最优 pooling       (上界补充对照)
DIM_CONFIGS = ["max/aff=max", "max/aff=netaff", "best"]


def resolve_dim_cols(df, tools, pats, min_pep, dim_config):
    """按 dim_config 把工具集解析成 dim_cols。缺工具/无有效 pooling 警告并剔除。
    返回 (cols, used_labels)。
      · max/aff=max   : 各工具 <tool>_max (含亲和代理)。
      · max/aff=netaff: 亲和代理用 netAffneg 列, 其余 <tool>_max。
      · best          : 各工具 best_pooling_for_tool (in-sample 上界)。
    """
    cols, used = [], []
    for t in tools:
        if dim_config == "best":
            best_pl, _rho, _all = best_pooling_for_tool(df, t, patients=pats, min_pep=min_pep)
            if best_pl is None:
                print(f"[warn] {t}: 无有效 pooling(best), 剔除该维")
                continue
            col, lbl = pool_col(t, best_pl), f"{t}_{best_pl}"
        else:
            if t == AFFINITY_PROXY and dim_config == "max/aff=netaff":
                col, lbl = AFFINITY_NETAFF_COL, AFFINITY_NETAFF_COL
            else:
                col, lbl = pool_col(t, "max"), f"{t}_max"
        if col not in df.columns or df[col].notna().sum() == 0:
            print(f"[warn] {t}: 列 {col} 缺失或全空, 剔除该维")
            continue
        cols.append(col)
        used.append(lbl)
    return cols, used


def main():
    ap = argparse.ArgumentParser(
        description="R3 官方: 12 fusion × {3,4,6,7} 维 LOPO per-patient Spearman (§3.3.1 表6)")
    ap.add_argument("--input", default=str(FROZEN_POOLED), help="干净肽级表路径")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--min_pep", type=int, default=MIN_PEP)
    ap.add_argument("--ctrl", default="peplen", help="控制变量列 (B2 偏相关, 默认 peplen)")
    ap.add_argument("--n_boot", type=int, default=2000, help="bootstrap 重采样次数 (B4)")
    args = ap.parse_args()

    df = load_frozen(args.input)
    pats = present_patients(df)
    print(f"[info] 干净表: {df.shape}; DS2 患者({len(pats)})={pats}; seed={args.seed}; "
          f"ctrl={args.ctrl}; n_boot={args.n_boot}")

    rows = []
    for dim_config in DIM_CONFIGS:
        for ndim in sorted(DIM_TOOLSETS.keys()):
            # aff=netaff 仅对含亲和代理的维度集 (3/4/7) 与 aff=max 不同; 6 维无亲和代理 → 跳过重复
            if dim_config == "max/aff=netaff" and AFFINITY_PROXY not in DIM_TOOLSETS[ndim]:
                continue
            dim_cols, used = resolve_dim_cols(df, DIM_TOOLSETS[ndim], pats,
                                              args.min_pep, dim_config)
            print("\n" + "=" * 72)
            print(f"[{ndim}维 · {dim_config}] tools={DIM_TOOLSETS[ndim]} -> 列={used}")
            print("=" * 72)
            if len(dim_cols) < 2:
                print(f"[warn] {ndim}维/{dim_config} 有效列<2, 跳过")
                continue
            for method in METHOD_ORDER:
                s = apply_fusion(df, dim_cols, method, patients=pats, seed=args.seed)
                s_arr = np.asarray(s.values, dtype=float)   # index 对齐 df, 供 bootstrap
                rho_raw, _cl, _ch, nu, _nd = per_patient_spearman(
                    df, s_arr, patients=pats, min_pep=args.min_pep)
                rho_len, _, _, _, _ = per_patient_partial_spearman(
                    df, s_arr, ctrl=args.ctrl, patients=pats, min_pep=args.min_pep)
                _, ci_lo, ci_hi, _ = bootstrap_patient_ci(
                    df, s_arr, n_boot=args.n_boot, seed=args.seed,
                    patients=pats, min_pep=args.min_pep)
                rows.append(dict(method=method, ndim=ndim, dim_config=dim_config,
                                 dims=";".join(used), rho_raw=r6(rho_raw),
                                 rho_lenctrl=r6(rho_len), ci_lo=r6(ci_lo),
                                 ci_hi=r6(ci_hi), n_pat=int(nu)))
                rr = f"{rho_raw:+.4f}" if not np.isnan(rho_raw) else "  NaN "
                rl = f"{rho_len:+.4f}" if not np.isnan(rho_len) else "  NaN "
                ci = (f"[{ci_lo:+.4f},{ci_hi:+.4f}]"
                      if ci_lo is not None and not np.isnan(ci_lo) else "[n/a]")
                print(f"  {method:<20s} raw={rr} lenctrl={rl} CI{ci} n_pat={nu}")

    if not rows:
        sys.exit("[ERR] 无产出, CSV 未写")
    out_df = pd.DataFrame(rows)
    out_dir = ensure_out_dir()
    out_path = out_dir / "R3_fusion_12methods_official.csv"
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("# R3_fusion_12methods_official.csv\n")
        f.write("# QuantImmuBench §3.3.1 表6: 12 fusion 法 × {3,4,6,7} 维 × 维度配置 LOPO per-patient Spearman\n")
        f.write(f"# 输入={Path(args.input).name}; DS2 9 患者; 无监督法不碰标签, 学习型 LOPO 无泄漏\n")
        f.write("# dim_config: max/aff=max & max/aff=netaff = 零选择 headline(B5, 亲和代理分别 _max / netMHCpan_BA_topk_k20_a0); best = in-sample 上界补充对照\n")
        f.write(f"# rho_raw=裸等权; rho_lenctrl=控肽长偏相关(B2, ctrl={args.ctrl}); ci_*=cluster-bootstrap over patients 95%CI(B4, 裸分数)\n")
        f.write("# ★ 维度集成员=selection, TODO 待袁/朱确认; dims=实际使用的列(分号分隔)\n")
        out_df.to_csv(f, index=False)
    print(f"\n[saved] {out_path}  shape={out_df.shape}")
    print("[DONE] R3")


if __name__ == "__main__":
    main()
