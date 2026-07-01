#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
R7_official.py
==============
服务: QuantImmuBench 大纲 §3.3.5 —— 整合 vs 最强单工具 配对显著性检验 (诚实呈现「统计持平」)。
对应大纲: paper/QuanImmu-Paper-Outline.md §3.3.5。

★ 2026-07-01 Part D Phase 3b 干净口径 (见 04_LOG):
  · 输入 = 干净表 pooled_clean_9mer.csv (含 peplen)。
  · [B5 零选择] 整合维度 = SURV6 各工具 <tool>_max 的 geomean fusion (max 维, 去 in-sample
    pooling selection); 最强单工具 = 全覆盖(130 肽)池里 <tool>_max per-patient Fisher-z 最高者
    (零选择 max, 防稀疏虚高)。旧脚本用 best_pooling_for_tool 已弃。
  · [B4 引擎] 配对显著性一律用引擎新 paired_patient_test (弃旧自实现的符号翻转/配对 t):
    每病人算两法 per-patient (partial) Spearman 的 Fisher-z 差, 纯 numpy 双侧符号置换检验。
  · [B2 控肽长] 裸 + 控肽长(ctrl='peplen')各出 Δz̄ / p; 控肽长版隔离肽长混杂。
  【弃 scipy.special.betainc + 旧手写置换/t 检验】: 全走引擎, 满足「禁 scipy.stats」硬约束。

做什么 (把「排名次序 != 显著差异」这句话做成可核查的统计):
  · 整合 = SURV6 各工具 <tool>_max 的 geomean fusion (病人内 rank fusion, leak-free)。
  · 最强单工具 = 全覆盖(130 肽)池里 per-patient Fisher-z 最高单工具 (零选择 max, 防稀疏虚高)。
  · 配对单元 = 病人。每病人 Δz = arctanh(fusion_rho_p) - arctanh(single_rho_p)。
  · 报告:
      ① Δz̄ / p (裸 + 控肽长两版, 引擎 paired_patient_test 双侧符号置换检验)。
      ② Δ = 整合 Fisher-z ρ̄ − 单工具 Fisher-z ρ̄ (配对病人集上重算, ρ̄ 空间, 口径一致)。
      ③ 驱动病人诊断: 留一病人重算 Δ, 看去掉哪个病人后 Δ 变化最大 (识别 P101 式单病人驱动)。
      ④ bootstrap over patients (纯 numpy resample 病人) 给 Δ 的 95% CI。
  大纲原文口径参考: ds2 Δ≈+0.038、p≈0.70、主要由单一病人 P101 驱动 —— 如实输出实测值, 不凑。

输入 (只读干净表):
  data/frozen/pooled_clean_9mer.csv
输出 (analysis/official/):
  R7_paired_significance_official.csv          —— 每病人一行 (patient_id,n_pep,fusion_rho,single_rho,delta_z) + SUMMARY 行
  R7_paired_significance_official.summary.json —— Δz̄/p (裸+控肽长) / Δ(ρ̄差) / driver_patient /
                                                 delta_leave_one_out / bootstrap_ci

复用旧骨架:
  · geomean fusion / per-patient Fisher-z / fisherz_weighted_agg → _official_common
  · 配对显著性 → _official_common.paired_patient_test (引擎新一等公民)
  · Fisher-z 变换 clip 常量 (FISHER_CLIP) → _official_common

★ selection 已裁决 (2026-07-01, 对齐 outline §2.2 9mer 主分析):
  · DS2 口径 = 130 肽 / 9 患者 (官方数据红线, Entry31 已拍)。
  · 整合维度 SURV6 成员 = 保持现状 (outline 抽象「6维」既有具体化, 朱同学传承, 同 R3/R5)。
  · 最强单工具限全覆盖池 = 保持 (outline §3.1 领先单工具皆全覆盖)。
  · 仅 DTU consent 保留为外部 pending (法律授权, 非写作阻塞)。

跑法 (主线跑, 我不跑):
  python analysis/official/R7_official.py
  python analysis/official/R7_official.py --n_boot 2000 --seed 42
"""

import sys
import json
import argparse
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _official_common import (                              # noqa: E402
    load_frozen, present_patients, per_patient_spearman, paired_patient_test,
    apply_fusion, pool_col, fisherz_weighted_agg,
    TOOLS_30, MIN_PEP, FISHER_CLIP, FROZEN_POOLED, ensure_out_dir,
)

# ── 整合维度 (★ TODO 待袁/朱确认, 同 R3/R5 SURV6; 各工具零选择 <tool>_max) ──────────
SURV6 = ["PredIG", "IMPROVE", "pTuneos", "PRIME", "ImmuneApp", "deepHLApan"]


def build_surv6_cols(df):
    """[B5 零选择] SURV6 各工具 <tool>_max 列名; 返回 (cols, used_labels)。缺列剔除。"""
    cols, used = [], []
    for t in SURV6:
        col = pool_col(t, "max")
        if col not in df.columns or df[col].notna().sum() == 0:
            print(f"[warn] {t}: 列 {col} 缺失或全空, 剔除该维")
            continue
        cols.append(col)
        used.append(f"{t}_max")
    return cols, used


def strongest_single(df, pats, min_pep):
    """[B5 零选择] 全覆盖(130 肽)工具池里 <tool>_max per-patient Fisher-z 最高单工具
    (防稀疏虚高)。返回 (best_tool, best_col, best_rho, full_cov_tools)。"""
    n = len(df)
    full_cov = [t for t in TOOLS_30
                if f"{t}_max" in df.columns and int(df[f"{t}_max"].notna().sum()) == n]
    best_tool, best_rho, best_col = None, -np.inf, None
    for t in full_cov:
        col = pool_col(t, "max")
        rho, *_ = per_patient_spearman(df, col, patients=pats, min_pep=min_pep)
        if rho is not None and not np.isnan(rho) and rho > best_rho:
            best_tool, best_rho, best_col = t, rho, col
    return best_tool, best_col, best_rho, full_cov


def _z(rho):
    """Fisher-z 变换, clip 防 arctanh(±1)=inf (同 common)。"""
    return float(np.arctanh(np.clip(rho, -FISHER_CLIP, FISHER_CLIP)))


def _agg_rho(rhos, ns):
    """Fisher-z 加权 ρ̄ (仅取标量), 输入病人 rho/n 列表。"""
    rb, _, _, _, _ = fisherz_weighted_agg(np.asarray(rhos, float), np.asarray(ns, float))
    return rb


def main():
    ap = argparse.ArgumentParser(
        description="R7 官方: 整合 vs 最强单工具 配对显著性检验 (§3.3.5)")
    ap.add_argument("--input", default=str(FROZEN_POOLED), help="干净肽级表路径")
    ap.add_argument("--min_pep", type=int, default=MIN_PEP)
    ap.add_argument("--ctrl", default="peplen", help="控制变量列 (B2 偏相关, 默认 peplen)")
    ap.add_argument("--n_perm", type=int, default=10000,
                    help="符号置换检验次数 (K<=20 时引擎自动精确枚举 2^K, 忽略此值)")
    ap.add_argument("--n_boot", type=int, default=2000, help="病人 bootstrap 重采样次数")
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    df = load_frozen(args.input)
    pats = present_patients(df)
    print(f"[info] 干净表 {df.shape}; DS2 患者({len(pats)})={pats}; min_pep={args.min_pep}; "
          f"ctrl={args.ctrl}")

    # ── 整合分 (SURV6 geomean fusion, max 维) 的 per-patient rho ──────────────────
    surv6_cols, surv6_used = build_surv6_cols(df)
    fusion_score = apply_fusion(df, surv6_cols, "geomean", patients=pats, seed=args.seed)
    fusion_arr = np.asarray(fusion_score.values, dtype=float)   # index 对齐 df
    f_bar, f_lo, f_hi, f_nu, f_nd, f_rhos_by, f_ns_by = per_patient_spearman(
        df, fusion_arr, patients=pats, min_pep=args.min_pep, return_perpat=True)
    print(f"[fusion] SURV6 geomean(max 维)={surv6_used}")
    print(f"[fusion] ρ̄={f_bar:+.4f} CI=[{f_lo:+.4f},{f_hi:+.4f}] n_pat={f_nu}")

    # ── 最强单工具 (全覆盖池零选择 max) 的 per-patient rho ────────────────────────
    s_tool, single_col, s_rho0, full_cov = strongest_single(df, pats, args.min_pep)
    s_bar, s_lo, s_hi, s_nu, s_nd, s_rhos_by, s_ns_by = per_patient_spearman(
        df, single_col, patients=pats, min_pep=args.min_pep, return_perpat=True)
    print(f"[single] 最强单工具={single_col} ρ̄={s_bar:+.4f} CI=[{s_lo:+.4f},{s_hi:+.4f}] "
          f"(限全覆盖{len(full_cov)}工具池防虚高)")

    # ── ① 配对显著性 (引擎 paired_patient_test): 裸 + 控肽长两版 Δz̄ / p ────────────
    dz_raw, p_raw, K_raw = paired_patient_test(
        df, fusion_arr, single_col, ctrl=None, patients=pats,
        min_pep=args.min_pep, n_perm=args.n_perm, seed=args.seed)
    dz_len, p_len, K_len = paired_patient_test(
        df, fusion_arr, single_col, ctrl=args.ctrl, patients=pats,
        min_pep=args.min_pep, n_perm=args.n_perm, seed=args.seed)
    print(f"[test·裸]    Δz̄={dz_raw:+.4f} p={p_raw:.4f} (K={K_raw})")
    print(f"[test·控肽长] Δz̄={dz_len:+.4f} p={p_len:.4f} (K={K_len})")

    # ── 配对病人集 (裸: 两侧 rho 均非 NaN) → 供 Δ(ρ̄) / driver / bootstrap ──────────
    paired_pats = [p for p in pats
                   if not np.isnan(f_rhos_by.get(p, np.nan))
                   and not np.isnan(s_rhos_by.get(p, np.nan))]
    if len(paired_pats) < 2:
        sys.exit(f"[ERR] 配对病人不足 (n={len(paired_pats)}), 无法做配对诊断")

    f_rhos = np.array([f_rhos_by[p] for p in paired_pats], float)
    s_rhos = np.array([s_rhos_by[p] for p in paired_pats], float)
    ns = np.array([f_ns_by[p] for p in paired_pats], float)   # n_pep 与 score 无关, 两侧同值
    delta_z = np.array([_z(fr) - _z(sr) for fr, sr in zip(f_rhos, s_rhos)], float)
    n = len(paired_pats)

    # ── ② 口径一致的 Δ(ρ̄): 配对病人集上各自 Fisher-z 加权后作差 ────────────────────
    fusion_bar_p = _agg_rho(f_rhos, ns)
    single_bar_p = _agg_rho(s_rhos, ns)
    delta_full = fusion_bar_p - single_bar_p
    print(f"\n[Δ] 整合 ρ̄={fusion_bar_p:+.4f} − 单工具 ρ̄={single_bar_p:+.4f} = Δ={delta_full:+.4f}")

    # ── ③ 驱动病人诊断: 留一病人重算 Δ, 看去掉谁 Δ 变化最大 ──────────────────────
    delta_loo = {}
    for j, p in enumerate(paired_pats):
        keep = [k for k in range(n) if k != j]
        d_loo = _agg_rho(f_rhos[keep], ns[keep]) - _agg_rho(s_rhos[keep], ns[keep])
        delta_loo[p] = d_loo
    change = {p: abs(delta_full - d) for p, d in delta_loo.items()}
    driver = max(change, key=change.get)
    print(f"[driver] 去掉后 Δ 变化最大的病人 = P{driver} "
          f"(Δ_full={delta_full:+.4f} → Δ_loo={delta_loo[driver]:+.4f}, "
          f"|Δ|变化={change[driver]:.4f})")

    # ── ④ bootstrap over patients: 重采样病人重算 Δ → 95% CI ────────────────────
    rng = np.random.default_rng(args.seed)
    boot = np.empty(args.n_boot, float)
    for b in range(args.n_boot):
        idx = rng.integers(0, n, n)
        boot[b] = _agg_rho(f_rhos[idx], ns[idx]) - _agg_rho(s_rhos[idx], ns[idx])
    boot_valid = boot[~np.isnan(boot)]
    boot_lo = float(np.percentile(boot_valid, 2.5)) if len(boot_valid) else np.nan
    boot_hi = float(np.percentile(boot_valid, 97.5)) if len(boot_valid) else np.nan
    print(f"[boot] Δ 95%CI = [{boot_lo:+.4f}, {boot_hi:+.4f}] "
          f"(n_boot={args.n_boot}, 有效={len(boot_valid)})")

    # ── 写 CSV (每病人一行 + SUMMARY) ───────────────────────────────────────────
    def _r(v, d=6):
        return round(float(v), d) if v is not None and not np.isnan(v) else np.nan

    rows = []
    for j, p in enumerate(paired_pats):
        rows.append(dict(patient_id=int(p), n_pep=int(ns[j]),
                         fusion_rho=_r(f_rhos[j], 4), single_rho=_r(s_rhos[j], 4),
                         delta_z=_r(delta_z[j], 4)))
    summary_row = dict(patient_id="SUMMARY", n_pep=int(ns.sum()),
                       fusion_rho=_r(fusion_bar_p, 4), single_rho=_r(single_bar_p, 4),
                       delta_z=_r(delta_full, 4))
    out_df = pd.concat([pd.DataFrame(rows), pd.DataFrame([summary_row])],
                       ignore_index=True)

    out_dir = ensure_out_dir()
    out_csv = out_dir / "R7_paired_significance_official.csv"
    with open(out_csv, "w", encoding="utf-8") as f:
        f.write("# R7_paired_significance_official.csv\n")
        f.write("# QuantImmuBench §3.3.5: 整合(SURV6 geomean, max 维) vs 最强单工具(全覆盖池零选择 max) 配对显著性\n")
        f.write(f"# 输入={Path(args.input).name}; DS2 配对病人={paired_pats}\n")
        f.write(f"# 整合维度(SURV6, ★TODO)={surv6_used}; 最强单工具={single_col}(限全覆盖{len(full_cov)}池)\n")
        f.write("# fusion_rho/single_rho=病人内 Spearman; delta_z=arctanh(fusion)-arctanh(single)\n")
        f.write("# SUMMARY 行 fusion_rho/single_rho=Fisher-z 加权 ρ̄, delta_z=Δ(ρ̄差); Δz̄/p(裸+控肽长)见 summary.json\n")
        out_df.to_csv(f, index=False)
    print(f"\n[saved] {out_csv}")

    # ── 写 summary.json ─────────────────────────────────────────────────────────
    summary = {
        "section": "§3.3.5 paired significance (integration vs strongest single tool)",
        "input": Path(args.input).name,
        "paired_patients": [int(p) for p in paired_pats],
        "n_paired": int(n),
        "integration": {
            "method": "SURV6 geomean fusion (max 维, 零选择 B5)",
            "dims": surv6_used,
            "dims_TODO": "SURV6 成员=selection, 待袁/朱确认 outline",
            "fisherz_rho": _r(fusion_bar_p),
            "fisherz_rho_allpat": _r(f_bar), "ci_lo": _r(f_lo), "ci_hi": _r(f_hi),
        },
        "strongest_single": {
            "tool_pooling": single_col,
            "full_cov_pool_size": len(full_cov),
            "selection": "全覆盖(130肽)池零选择 <tool>_max 里 per-patient Fisher-z 最高, 防稀疏虚高",
            "fisherz_rho": _r(single_bar_p),
            "fisherz_rho_allpat": _r(s_bar), "ci_lo": _r(s_lo), "ci_hi": _r(s_hi),
        },
        "paired_test_raw": {   # ① 引擎 paired_patient_test (裸)
            "delta_zbar": _r(dz_raw, 4), "p_permutation": _r(p_raw, 6),
            "K_paired": int(K_raw),
            "note": "每病人 arctanh(fusion)-arctanh(single) 均值; 双侧符号置换(K<=20 精确枚举 2^K)",
        },
        "paired_test_lenctrl": {   # ① 引擎 paired_patient_test (控肽长 B2)
            "delta_zbar": _r(dz_len, 4), "p_permutation": _r(p_len, 6),
            "K_paired": int(K_len),
            "ctrl": args.ctrl,
            "note": "两法均用控肽长偏相关(ctrl=peplen), 隔离肽长混杂后重算 Δz̄/p",
        },
        "delta_integration_minus_single_rho": _r(delta_full),   # ② ρ̄ 空间
        "driver_patient": int(driver),
        "driver_abs_delta_change": _r(change[driver]),
        "delta_leave_one_out": {str(int(p)): _r(d) for p, d in delta_loo.items()},
        "bootstrap_ci_lo": _r(boot_lo), "bootstrap_ci_hi": _r(boot_hi),   # ④
        "n_boot": args.n_boot,
        "seed": args.seed,
        "interpretation": "排名次序 != 显著差异; p 大 & CI 跨 0 ⇒ 统计持平 (诚实呈现, 数字以实测为准)",
    }
    out_json = out_dir / "R7_paired_significance_official.summary.json"

    def _jd(o):
        if isinstance(o, np.integer): return int(o)
        if isinstance(o, np.floating): return float(o)
        return str(o)

    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False, default=_jd)
    print(f"[saved] {out_json}")
    print("[DONE] R7")


if __name__ == "__main__":
    main()
