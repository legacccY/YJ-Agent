#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
R5_permutation_null.py
======================
服务: QuantImmuBench 大纲 §3.3.3 (表8) —— Nested-LOPO 整合分的 *正式* 置换零分布 (permutation null)。
对应 lever: 把 R5_official.py 现有的 **单次** shuffle null (--shuffle --seed S) 升级成
  ≥1000 次独立置换构成的 null 分布 + 单侧经验 p 值 (含 +1 修正)。

为什么要升级 (命门):
  R5_official.py --shuffle --seed S 只做 *一次* 标签置换 → 一个 lopo_fisherz_rho 点。单次
  置换方差极大 (实测 seed 1/7/42/123 → −0.10/−0.17/+0.28/+0.15, 中心≈0 但剧烈波动),
  单点不能当 null 分布, 也算不出经验 p。本 harness 跑 N 次独立置换聚成 null 分布, 与真值
  (未置换 LOPO ρ̄) 比对出经验 p, 砸实「整合分显著高于随机」这一 §3.3.3 命门。

真值来源 (real_lopo_rho):
  analysis/official/R5_nested_lopo_official.summary.json 的 "lopo_fisherz_rho" = 0.274922
  (输入 pooled_clean_9mer.csv, shuffled=false, seed=42; DS2 9 患者; 整合维度 SURV6 各 <tool>_max)。
  可用 --real 覆盖 (若真值重算后变动, 以 summary.json 为准)。

计算一致性声明 (复现零偏离):
  · 置换机制与 R5_official.main() line 149-153 逐字一致:
        rng = np.random.default_rng(seed)
        df = df.copy(); df[LABEL_COL] = rng.permutation(df[LABEL_COL].values)
    (第 i 次用 seed = seed0 + i, 各次独立可复现; 每次都从 canonical 未置换标签重新 permute,
     故 seed=S 的一次 == R5_official.py --shuffle --seed S 的置换, 逐位相同。)
  · nested-LOPO 计算 **不另写一套**: 直接 import R5_official.compute_lopo_rho —— 该函数是
    从 R5_official.main() line 182-220 的外层循环 *原样抽出* (仅抽函数, 计算一字未改), R5 主
    脚本本身也改为调用它, 故 harness 与 R5 用的是同一份 LOPO 代码, 结果字节一致。
  · oracle 作弊上界与 lopo_fisherz_rho 计算解耦 (oracle 只写 out_df 的 oracle_rho 列供
    一致性核对, 不进 lopo_bar), 故 harness 调用时传空 oracle_pp={}, lopo_bar 与传真 oracle 时相同。
  · 整合维度 (SURV6)、θ 空间 (fixavg + ridge@dof{2,2.5,3})、min_pep、pool_col 口径全部从
    R5_official / _official_common import, 与 R5 完全同一套常量, 绝不硬编码另一份。

经验 p 定义 (单侧, 上尾, Phipson-Smyth +1 修正):
    p = (#{null_rho >= real_lopo_rho} + 1) / (n_perm + 1)
  分子只数有效 (非 NaN) 的 null; 分母固定 n_perm+1 (含 +1 防 p=0)。real 落在 null 上尾越远 → p 越小。
  另报 real 在 null 分布的经验分位 (fraction of null <= real)。

输入 (只读 canonical, 只加载一次):
  data/frozen/pooled_clean_9mer.csv  (--input 可切; 默认 = FROZEN_POOLED)
输出 (analysis/official/):
  R5_permutation_null.summary.json   —— n_perm/null 描述统计/real/经验 p/分位 (机读汇总)
  R5_permutation_null_draws.csv      —— 每次置换的 seed + lopo_null (供复核/画 null 直方图)

跑法 (★ 主线跑, coder 不跑, 连烟测都不跑):
  python analysis/official/R5_permutation_null.py --nperm 1000
  # 先小样标定 ETA (进度行会打印 rate/ETA), 再决定跑满:
  python analysis/official/R5_permutation_null.py --nperm 20

Windows: UTF-8 stdout, pathlib 路径, 纯 numpy/pandas/sklearn, 禁 scipy (随 _official_common 口径)。
"""

import sys
import csv
import json
import time
import argparse
from pathlib import Path

import numpy as np
import pandas as pd

# Windows 必要: UTF-8 stdout (与 _official_common 同口径; import 它也会 reconfigure, 此处兜底)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

HERE = Path(__file__).resolve().parent                     # analysis/official/
sys.path.insert(0, str(HERE))

from _official_common import (                              # noqa: E402
    load_frozen, present_patients, pool_col,
    MIN_PEP, LABEL_COL, FROZEN_POOLED, ensure_out_dir,
)
# ★ 同一份 LOPO 计算 (R5 抽出的函数) + 同一套整合维度/θ 空间常量, 绝不另写。
from R5_official import compute_lopo_rho, build_theta_space, SURV6  # noqa: E402

# R5_nested_lopo_official.summary.json 的 lopo_fisherz_rho (真 LOPO ρ̄, 未置换)。--real 可覆盖。
REAL_LOPO_RHO = 0.274922


def build_feature_cols(df):
    """整合维度列 = SURV6 各工具零选择 <tool>_max。
    ★ 与 R5_official.main() 内联建列逐字一致 (SURV6 顺序 + pool_col(t,'max') + 缺列/全空剔除)。
    标签置换只 permute Elispot 列, 不动工具列, 故在 canonical (未置换) df 上建一次即可, 与
    R5 在置换后 df 上建列结果相同。返回 (feature_cols, used)。
    """
    feature_cols, used = [], []
    for t in SURV6:
        col = pool_col(t, "max")
        if col not in df.columns or df[col].notna().sum() == 0:
            print(f"[warn] {t}: 列 {col} 缺失或全空, 剔除")
            continue
        feature_cols.append(col)
        used.append(col)
    return feature_cols, used


def one_permutation(df_canon, feature_cols, thetas, pats, seed, min_pep):
    """单次置换 + nested-LOPO, 返回 lopo_fisherz_rho (float, 可能 NaN)。

    ★ 置换机制逐字复制自 R5_official.main() line 149-153 (rng.default_rng(seed) → copy →
      permute LABEL_COL); 每次从 df_canon (canonical 未置换标签) 新拷贝再 permute, 保证
      seed=S 的一次与 R5 --shuffle --seed S 的置换逐位相同。
    LOPO 用 R5 抽出的 compute_lopo_rho (计算一字未改); oracle_pp={} 不影响 lopo_bar (见头注)。
    """
    rng = np.random.default_rng(seed)
    work = df_canon.copy()
    work[LABEL_COL] = rng.permutation(work[LABEL_COL].values)
    lopo_bar, *_ = compute_lopo_rho(
        work, feature_cols, thetas, pats, {}, min_pep, LABEL_COL, verbose=False)
    return lopo_bar


def main():
    ap = argparse.ArgumentParser(
        description="R5 置换零分布: 多次标签置换 nested-LOPO null + 单侧经验 p (§3.3.3 命门)")
    ap.add_argument("--input", default=str(FROZEN_POOLED), help="冻结肽级表路径 (canonical)")
    ap.add_argument("--nperm", type=int, default=1000, help="置换次数 (默认 1000)")
    ap.add_argument("--seed0", type=int, default=0,
                    help="起始 seed; 第 i 次 (0-based) 用 seed0+i (默认 0)")
    ap.add_argument("--min_pep", type=int, default=MIN_PEP, help="患者内最少肽数 (默认同 R5)")
    ap.add_argument("--real", type=float, default=REAL_LOPO_RHO,
                    help="真 LOPO ρ̄ (默认 = R5 summary.json lopo_fisherz_rho 0.274922)")
    args = ap.parse_args()

    df = load_frozen(args.input)                 # ★ canonical 表只加载一次
    pats = present_patients(df)
    feature_cols, used = build_feature_cols(df)
    thetas = build_theta_space()
    theta_names = [t["name"] for t in thetas]

    print(f"[info] 输入={Path(args.input).name}; DS2 患者({len(pats)})={pats}")
    print(f"[info] 整合维度(零选择 max)={used}")
    print(f"[info] θ 空间={theta_names}; min_pep={args.min_pep}")
    print(f"[info] 真值 real_lopo_rho={args.real:+.6f}  (来源 R5 summary.json)")
    print(f"[info] 跑 {args.nperm} 次置换 (seed {args.seed0}..{args.seed0 + args.nperm - 1}); "
          f"经验 p = (#null>=real + 1)/(nperm + 1)")

    draws = []                                   # list[(seed, lopo_null_float_or_nan)]
    t0 = time.time()
    for i in range(args.nperm):
        seed = args.seed0 + i
        rho = one_permutation(df, feature_cols, thetas, pats, seed, args.min_pep)
        rho_f = float(rho) if rho is not None and not np.isnan(rho) else np.nan
        draws.append((seed, rho_f))
        if (i + 1) % 100 == 0:                   # 每 100 次一行进度 (后台跑可见未卡死)
            elapsed = time.time() - t0
            rate = (i + 1) / elapsed if elapsed > 0 else float("nan")
            eta = (args.nperm - (i + 1)) / rate if rate and rate > 0 else float("nan")
            valid_so_far = [r for _, r in draws if not np.isnan(r)]
            cur_mean = float(np.mean(valid_so_far)) if valid_so_far else float("nan")
            print(f"[progress] {i + 1}/{args.nperm} perms | {elapsed:.0f}s "
                  f"({rate:.2f}/s, ETA {eta:.0f}s) | null mean so far={cur_mean:+.4f}",
                  flush=True)

    # ── draws CSV (每次置换一行, 供复核/画 null 直方图) ──────────────────────────
    out_dir = ensure_out_dir()
    draws_csv = out_dir / "R5_permutation_null_draws.csv"
    with open(draws_csv, "w", encoding="utf-8", newline="") as f:
        f.write("# R5_permutation_null_draws.csv\n")
        f.write("# QuantImmuBench §3.3.3: nested-LOPO 标签置换零分布, 每行一次置换\n")
        f.write(f"# 输入={Path(args.input).name}; 整合维度={used}; min_pep={args.min_pep}\n")
        f.write(f"# 置换机制/LOPO 计算与 R5_official.py --shuffle 逐位一致; real_lopo_rho={args.real}\n")
        w = csv.writer(f)
        w.writerow(["seed", "lopo_null"])
        for seed, rho_f in draws:
            w.writerow([seed, "" if np.isnan(rho_f) else f"{rho_f:.6f}"])
    print(f"\n[saved] {draws_csv}")

    # ── null 描述统计 + 单侧经验 p ─────────────────────────────────────────────
    nulls = np.array([r for _, r in draws], dtype=float)
    valid = nulls[~np.isnan(nulls)]
    n_valid = int(valid.size)
    n_nan = int(args.nperm - n_valid)
    real = float(args.real)

    def _f(v):
        if v is None or (isinstance(v, float) and np.isnan(v)):
            return None
        return round(float(v), 6)

    if n_valid == 0:
        sys.exit("[ERR] 全部置换 lopo 都是 NaN, 无法出 null 分布 (检查 min_pep/输入表)。")

    n_ge = int(np.sum(valid >= real))            # 上尾: null >= real
    p_emp = (n_ge + 1) / (args.nperm + 1)        # 单侧经验 p (+1 修正)
    real_pctile = float(np.mean(valid <= real))  # real 在 null 的经验分位 (CDF 位置)

    summary = {
        "design": "permutation null for nested-LOPO integration (multi-shuffle upgrade of R5 single --shuffle)",
        "input": Path(args.input).name,
        "integration_dims": used,
        "theta_space": theta_names,
        "min_pep": int(args.min_pep),
        "n_perm": int(args.nperm),
        "seed0": int(args.seed0),
        "seed_range": [int(args.seed0), int(args.seed0 + args.nperm - 1)],
        "n_valid": n_valid,
        "n_nan": n_nan,
        # ── null 分布描述统计 ──
        "null_mean": _f(np.mean(valid)),
        "null_std": _f(np.std(valid, ddof=1)) if n_valid > 1 else None,  # 样本标准差 (ddof=1)
        "null_median": _f(np.median(valid)),
        "null_q2.5": _f(np.percentile(valid, 2.5)),
        "null_q97.5": _f(np.percentile(valid, 97.5)),
        "null_min": _f(np.min(valid)),
        "null_max": _f(np.max(valid)),
        # ── 真值 vs null ──
        "real_lopo_rho": _f(real),
        "real_lopo_rho_source": "R5_nested_lopo_official.summary.json lopo_fisherz_rho",
        "n_null_ge_real": n_ge,
        "empirical_p_onesided": _f(p_emp),
        "empirical_p_formula": "(#{null >= real} + 1) / (n_perm + 1)  [one-sided upper tail, +1 corrected]",
        "real_percentile_in_null": _f(real_pctile),  # fraction of null <= real
        "consistency_note": (
            "置换机制 + nested-LOPO 均复用 R5_official (compute_lopo_rho 抽自 main line 182-220, "
            "计算未改); seed=S 的一次 == R5_official.py --shuffle --seed S, 逐位一致。"
        ),
    }
    out_json = out_dir / "R5_permutation_null.summary.json"
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)
    print(f"[saved] {out_json}")

    std_txt = f"{summary['null_std']:+.4f}" if summary["null_std"] is not None else "NA"
    print(f"\n[NULL] n_valid={n_valid}/{args.nperm} (nan={n_nan}) | "
          f"mean={_f(np.mean(valid)):+.4f} std={std_txt} "
          f"median={_f(np.median(valid)):+.4f} "
          f"[q2.5,q97.5]=[{_f(np.percentile(valid, 2.5)):+.4f},"
          f"{_f(np.percentile(valid, 97.5)):+.4f}]")
    print(f"[TEST] real={real:+.6f} | #null>=real={n_ge} | "
          f"经验 p(单侧,+1)={p_emp:.4g} | real 分位={real_pctile:.4f}")
    print("[DONE] R5_permutation_null")


if __name__ == "__main__":
    main()
