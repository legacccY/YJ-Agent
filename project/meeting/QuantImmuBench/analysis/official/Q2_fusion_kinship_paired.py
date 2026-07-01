#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Q2_fusion_kinship_paired.py
===========================
服务: QuantImmuBench §3.3.4 (geomean fusion 措辞) + 回答袁老师问题二 ——
  geomean / mean_rank / median 这三个「数学近亲」的 fusion 法, 差异到底多大、是否显著?
对应大纲: paper/QuanImmu-Paper-Outline.md §3.3.4。

做什么 (patient-level 配对显著性, 复用 R7 范式 + 引擎 paired_patient_test):
  · 三个融合分 (SURV6 各工具 <tool>_max 的 rank fusion, leak-free): geomean / mean_rank / median。
  · 三对近亲两两比: (geomean,mean_rank)、(geomean,median)、(mean_rank,median)。
  · 每对跑病人配对符号置换检验: 裸(ctrl=None) + 控肽长(ctrl='peplen') 各出 Δz̄ / p。
    Δz̄ = 配对病人「两法 per-patient Fisher-z 差」的均值; p = 双侧符号置换 (K<=20 精确枚举 2^K)。
  · 顺带记每法 per_patient_spearman 的 Fisher-z ρ̄ + 95%CI (点估参照)。
  · ci_lo_raw/ci_hi_raw = 裸配对 Δz̄ 的 cluster-bootstrap-over-patients 95%CI (与 dz_raw/p_raw 同族)。
  · driver_patient = |Δz|(该病人两法 Fisher-z 差) 最大的病人 (识别单病人驱动)。

输入 (只读干净表): data/frozen/pooled_clean_9mer.csv (130 肽 / 9 患者 / 9mer 口径)。
输出 (analysis/official/):
  Q2_fusion_kinship_paired.csv — 每对一行, 列见文件头注释。

跑法 (主线跑, 本脚本绝不自跑):
  cd D:/YJ-Agent/project/meeting/QuantImmuBench/analysis/official
  python Q2_fusion_kinship_paired.py
  python Q2_fusion_kinship_paired.py --n_boot 2000 --seed 42
"""

import sys
import argparse
import itertools
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _official_common import (                              # noqa: E402
    load_frozen, present_patients, per_patient_spearman, paired_patient_test,
    apply_fusion, pool_col, MIN_PEP, FISHER_CLIP, FISHER_MIN_N,
    FROZEN_POOLED, ensure_out_dir,
)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# ── 整合维度 (★ TODO 待袁/朱确认, 同 R3/R5/R7 SURV6; 各工具零选择 <tool>_max) ──────────
SURV6 = ["PredIG", "IMPROVE", "pTuneos", "PRIME", "ImmuneApp", "deepHLApan"]

# 三个「数学近亲」融合法 + 三对两两比 (apply_fusion 方法名)。
KIN_METHODS = ["geomean", "mean_rank", "median"]
KIN_PAIRS = [("geomean", "mean_rank"), ("geomean", "median"), ("mean_rank", "median")]


def build_surv6_cols(df):
    """[B5 零选择] SURV6 各工具 <tool>_max 列名; 返回 (cols, used_labels)。缺列剔除。(照抄 R7)"""
    cols, used = [], []
    for t in SURV6:
        col = pool_col(t, "max")
        if col not in df.columns or df[col].notna().sum() == 0:
            print(f"[warn] {t}: 列 {col} 缺失或全空, 剔除该维")
            continue
        cols.append(col)
        used.append(f"{t}_max")
    return cols, used


def _z(rho):
    """Fisher-z 变换, clip 防 arctanh(±1)=inf (同 common)。"""
    return float(np.arctanh(np.clip(rho, -FISHER_CLIP, FISHER_CLIP)))


def per_patient_zdiff(df, arr_a, arr_b, pats, min_pep):
    """两法各自 per-patient Spearman → 配对病人 (两侧非缺 & n>FISHER_MIN_N) 的 z 差数组 + 病人列表。
    返回 (diffs: np.array, kept_pats: list) —— diffs[i] = arctanh(rho_a[p]) - arctanh(rho_b[p])。
    """
    _, _, _, _, _, ra, na = per_patient_spearman(
        df, arr_a, patients=pats, min_pep=min_pep, return_perpat=True)
    _, _, _, _, _, rb, nb = per_patient_spearman(
        df, arr_b, patients=pats, min_pep=min_pep, return_perpat=True)
    diffs, kept = [], []
    for p in pats:
        va, vb = ra.get(p, np.nan), rb.get(p, np.nan)
        if np.isnan(va) or np.isnan(vb):
            continue
        if na.get(p, 0) <= FISHER_MIN_N or nb.get(p, 0) <= FISHER_MIN_N:
            continue
        diffs.append(_z(va) - _z(vb))
        kept.append(p)
    return np.asarray(diffs, float), kept


def main():
    ap = argparse.ArgumentParser(
        description="Q2 官方: geomean/mean_rank/median 三近亲融合法配对显著性 (§3.3.4)")
    ap.add_argument("--input", default=str(FROZEN_POOLED), help="干净肽级表路径")
    ap.add_argument("--min_pep", type=int, default=MIN_PEP)
    ap.add_argument("--ctrl", default="peplen", help="控制变量列 (B2 偏相关, 默认 peplen)")
    ap.add_argument("--n_perm", type=int, default=10000,
                    help="符号置换次数 (K<=20 引擎自动精确枚举 2^K, 忽略此值)")
    ap.add_argument("--n_boot", type=int, default=2000, help="病人 bootstrap 重采样次数")
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    df = load_frozen(args.input)
    pats = present_patients(df)
    print(f"[info] 干净表 {df.shape}; DS2 患者({len(pats)})={pats}; min_pep={args.min_pep}; "
          f"ctrl={args.ctrl}")

    surv6_cols, surv6_used = build_surv6_cols(df)
    print(f"[dims] SURV6 max 维={surv6_used}")

    # ── 三个近亲融合分 (病人内 rank fusion, leak-free) ────────────────────────────
    fused = {}
    rho_bar, ci = {}, {}
    for m in KIN_METHODS:
        arr = np.asarray(apply_fusion(df, surv6_cols, m, patients=pats, seed=args.seed).values,
                         dtype=float)
        fused[m] = arr
        rb, lo, hi, nu, nd = per_patient_spearman(df, arr, patients=pats, min_pep=args.min_pep)
        rho_bar[m] = rb
        ci[m] = (lo, hi)
        print(f"[fusion:{m:10s}] ρ̄={rb:+.4f} CI=[{lo:+.4f},{hi:+.4f}] n_pat={nu}")

    # ── 三对配对检验 ─────────────────────────────────────────────────────────────
    rng = np.random.default_rng(args.seed)
    rows = []
    for a, b in KIN_PAIRS:
        # ① 引擎配对置换: 裸 + 控肽长
        dz_raw, p_raw, K_raw = paired_patient_test(
            df, fused[a], fused[b], ctrl=None, patients=pats,
            min_pep=args.min_pep, n_perm=args.n_perm, seed=args.seed)
        dz_len, p_len, K_len = paired_patient_test(
            df, fused[a], fused[b], ctrl=args.ctrl, patients=pats,
            min_pep=args.min_pep, n_perm=args.n_perm, seed=args.seed)

        # ② 裸配对病人 z 差 → driver + cluster bootstrap CI
        diffs, kept = per_patient_zdiff(df, fused[a], fused[b], pats, args.min_pep)
        if len(diffs) == 0:
            driver = np.nan
            boot_lo, boot_hi = np.nan, np.nan
        else:
            j = int(np.argmax(np.abs(diffs)))
            driver = kept[j]
            K = len(diffs)
            boot = np.empty(args.n_boot, float)
            for bi in range(args.n_boot):
                idx = rng.integers(0, K, K)
                boot[bi] = float(diffs[idx].mean())
            boot_lo = float(np.percentile(boot, 2.5))
            boot_hi = float(np.percentile(boot, 97.5))

        rows.append(dict(
            method_a=a, method_b=b,
            rho_bar_a=_r(rho_bar[a]), rho_bar_b=_r(rho_bar[b]),
            dz_raw=_r(dz_raw), p_raw=_r(p_raw),
            dz_lenctrl=_r(dz_len), p_lenctrl=_r(p_len),
            K=int(K_raw),
            ci_lo_raw=_r(boot_lo), ci_hi_raw=_r(boot_hi),
            driver_patient=(int(driver) if not (isinstance(driver, float) and np.isnan(driver))
                            else np.nan),
        ))
        print(f"[pair] {a} vs {b}: 裸 Δz̄={dz_raw:+.4f} p={p_raw:.4f} | "
              f"控肽长 Δz̄={dz_len:+.4f} p={p_len:.4f} (K={K_raw}) driver=P{driver}")

    out_df = pd.DataFrame(rows)

    out_dir = ensure_out_dir()
    out_csv = out_dir / "Q2_fusion_kinship_paired.csv"
    with open(out_csv, "w", encoding="utf-8", newline="") as f:
        f.write("# Q2_fusion_kinship_paired.csv — §3.3.4 geomean/mean_rank/median 三近亲融合法配对显著性\n")
        f.write(f"# 口径: 官方 130 肽 / 9 患者 / 9mer; 输入={Path(args.input).name}; SURV6 max 维={surv6_used} (★TODO 待袁/朱确认)\n")
        f.write("# dz_raw/dz_lenctrl=配对病人「两法 per-patient Fisher-z 差」均值 (裸/控肽长); p=双侧符号置换(K<=20 精确 2^K);\n")
        f.write("# rho_bar_a/b=各法 per-patient Fisher-z ρ̄; ci_lo_raw/ci_hi_raw=裸 Δz̄ 的 cluster-bootstrap-over-patients 95%CI;\n")
        f.write("# K=配对病人数; driver_patient=|该病人两法 Fisher-z 差| 最大的病人。\n")
        out_df.to_csv(f, index=False)
    print(f"\n[saved] {out_csv}")
    print("[DONE] Q2_fusion_kinship_paired")


def _r(v, d=6):
    if v is None:
        return np.nan
    try:
        fv = float(v)
    except (TypeError, ValueError):
        return np.nan
    return round(fv, d) if not np.isnan(fv) else np.nan


if __name__ == "__main__":
    main()
