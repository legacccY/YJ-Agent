#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Q2_rank_corr_matrix.py
======================
服务: QuantImmuBench §3.3.4 (geomean fusion 措辞) + 回答袁老师问题二 ——
  坐实备忘里「geomean 与 mean_rank 秩相关 ≈0.97、与 median ≈0.90」这类近亲程度的具体数字。
对应大纲: paper/QuanImmu-Paper-Outline.md §3.3.4。

做什么 (8 个无监督 fusion 法两两秩相关矩阵):
  · 8 法 (SURV6 max 维经 apply_fusion 得每行综合分):
      geomean / mean_rank / median / powmean / max / min / weighted_mean_rank / softmax_rank。
  · 病人内秩相关: 对每病人, 两两 fusion 法的综合分做 Spearman (纯 numpy spearman_np, 禁 scipy);
    跨病人取均值 → N×N 均值矩阵。也算全体 pooled 版本 (130 肽当一个池子直接 Spearman)。
  · 顶部注释 summary: geomean-mean_rank / geomean-median 的病人内均值 + IQR + [min,max]。

输入 (只读干净表): data/frozen/pooled_clean_9mer.csv (130 肽 / 9 患者 / 9mer)。
输出 (analysis/official/):
  Q2_rank_corr_matrix.csv        — 病人内均值 N×N 矩阵 (行列=方法名) + 顶部注释 summary。
  Q2_rank_corr_matrix_pooled.csv — 全体 pooled N×N 矩阵 (对照)。
  Q2_rank_corr_perpatient.json   — 每病人一个 N×N 矩阵 (dict: patient_id -> {method_a: {method_b: rho}})。

跑法 (主线跑, 本脚本绝不自跑):
  cd D:/YJ-Agent/project/meeting/QuantImmuBench/analysis/official
  python Q2_rank_corr_matrix.py
"""

import sys
import json
import argparse
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _official_common import (                              # noqa: E402
    load_frozen, present_patients, apply_fusion, pool_col, spearman_np,
    MIN_PEP, FROZEN_POOLED, ensure_out_dir,
)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# ── 整合维度 (★ TODO 待袁/朱确认, 同 R3/R5/R7 SURV6) ─────────────────────────────
SURV6 = ["PredIG", "IMPROVE", "pTuneos", "PRIME", "ImmuneApp", "deepHLApan"]

# 8 无监督 fusion 法 (apply_fusion 方法名, 顺序即矩阵行列序)。
FUSION_METHODS = ["geomean", "mean_rank", "median", "powmean", "max", "min",
                  "weighted_mean_rank", "softmax_rank"]

# summary 重点关注的两对近亲 (回应备忘 0.97 / 0.90)。
FOCUS_PAIRS = [("geomean", "mean_rank"), ("geomean", "median")]


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


def _iqr(vals):
    """返回 (q25, q75) —— 忽略 NaN。"""
    v = np.asarray([x for x in vals if not np.isnan(x)], float)
    if len(v) == 0:
        return np.nan, np.nan
    return float(np.percentile(v, 25)), float(np.percentile(v, 75))


def main():
    ap = argparse.ArgumentParser(
        description="Q2 官方: 8 无监督 fusion 法两两秩相关矩阵 (§3.3.4)")
    ap.add_argument("--input", default=str(FROZEN_POOLED), help="干净肽级表路径")
    ap.add_argument("--min_pep", type=int, default=MIN_PEP)
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    df = load_frozen(args.input)
    pats = present_patients(df)
    print(f"[info] 干净表 {df.shape}; DS2 患者({len(pats)})={pats}; min_pep={args.min_pep}")

    surv6_cols, surv6_used = build_surv6_cols(df)
    print(f"[dims] SURV6 max 维={surv6_used}")

    # ── 8 法综合分 (病人内 rank fusion, leak-free), 对齐 df 行 ────────────────────
    fused = {}
    for m in FUSION_METHODS:
        arr = np.asarray(apply_fusion(df, surv6_cols, m, patients=pats, seed=args.seed).values,
                         dtype=float)
        fused[m] = arr
    M = FUSION_METHODS
    N = len(M)

    # ── 病人内两两 Spearman → 逐病人 N×N 矩阵 + 跨病人均值矩阵 ────────────────────
    df = df.reset_index(drop=True)   # 保证 fused 数组 index 与 df 行对齐 (apply_fusion 已按 df.index)
    perpat = {}                       # patient_id -> N×N list of rho (病人内)
    perpat_pairvals = {(a, b): [] for a in M for b in M}   # 跨病人收集, 供均值矩阵
    for p in pats:
        mask = (df["Patient_ID"] == p).values
        if int(mask.sum()) < args.min_pep:
            continue
        mat = np.full((N, N), np.nan)
        for i in range(N):
            for j in range(N):
                if i == j:
                    mat[i, j] = 1.0
                    continue
                rho = spearman_np(fused[M[i]][mask], fused[M[j]][mask])
                mat[i, j] = rho
                perpat_pairvals[(M[i], M[j])].append(rho)
        perpat[int(p)] = mat

    mean_mat = np.full((N, N), np.nan)
    for i in range(N):
        for j in range(N):
            vals = [v for v in perpat_pairvals[(M[i], M[j])] if not np.isnan(v)]
            mean_mat[i, j] = float(np.mean(vals)) if len(vals) else np.nan

    # ── 全体 pooled 版本 (130 肽当一个池子) ──────────────────────────────────────
    pooled_mat = np.full((N, N), np.nan)
    for i in range(N):
        for j in range(N):
            pooled_mat[i, j] = 1.0 if i == j else spearman_np(fused[M[i]], fused[M[j]])

    # ── summary (病人内均值 + IQR + [min,max]) ───────────────────────────────────
    summary_lines = []
    for a, b in FOCUS_PAIRS:
        vals = [v for v in perpat_pairvals[(a, b)] if not np.isnan(v)]
        if len(vals):
            mean_v = float(np.mean(vals))
            q25, q75 = _iqr(vals)
            mn, mx = float(np.min(vals)), float(np.max(vals))
        else:
            mean_v = q25 = q75 = mn = mx = np.nan
        pooled_v = pooled_mat[M.index(a), M.index(b)]
        summary_lines.append(
            f"# {a}-{b}: 病人内均值={mean_v:.4f} IQR=[{q25:.4f},{q75:.4f}] "
            f"[min,max]=[{mn:.4f},{mx:.4f}]; pooled={pooled_v:.4f} (n_pat={len(vals)})")
        print(summary_lines[-1])

    out_dir = ensure_out_dir()

    # ── 写病人内均值矩阵 CSV (带 summary 注释) ───────────────────────────────────
    mean_df = pd.DataFrame(np.round(mean_mat, 6), index=M, columns=M)
    out_csv = out_dir / "Q2_rank_corr_matrix.csv"
    with open(out_csv, "w", encoding="utf-8", newline="") as f:
        f.write("# Q2_rank_corr_matrix.csv — §3.3.4 8 无监督 fusion 法两两秩相关 (病人内均值 N×N)\n")
        f.write(f"# 口径: 官方 130 肽 / 9 患者 / 9mer; 输入={Path(args.input).name}; SURV6 max 维={surv6_used} (★TODO 待袁/朱确认)\n")
        f.write("# 值 = 病人内 Spearman(fusion_a 分, fusion_b 分) 跨病人算术均值 (纯 numpy, 禁 scipy)。\n")
        for ln in summary_lines:
            f.write(ln + "\n")
        mean_df.to_csv(f)
    print(f"\n[saved] {out_csv}")

    # ── 写 pooled 矩阵 CSV (对照) ────────────────────────────────────────────────
    pooled_df = pd.DataFrame(np.round(pooled_mat, 6), index=M, columns=M)
    pooled_csv = out_dir / "Q2_rank_corr_matrix_pooled.csv"
    with open(pooled_csv, "w", encoding="utf-8", newline="") as f:
        f.write("# Q2_rank_corr_matrix_pooled.csv — 全体 pooled 版 (130 肽当一个池子, 对照病人内均值版)\n")
        f.write(f"# 输入={Path(args.input).name}; SURV6 max 维={surv6_used}\n")
        pooled_df.to_csv(f)
    print(f"[saved] {pooled_csv}")

    # ── 写逐病人矩阵 JSON ────────────────────────────────────────────────────────
    perpat_json = {}
    for pid, mat in perpat.items():
        perpat_json[str(pid)] = {
            M[i]: {M[j]: (None if np.isnan(mat[i, j]) else round(float(mat[i, j]), 6))
                   for j in range(N)}
            for i in range(N)
        }
    out_json = out_dir / "Q2_rank_corr_perpatient.json"
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump({"methods": M, "per_patient": perpat_json}, f,
                  indent=2, ensure_ascii=False)
    print(f"[saved] {out_json}")
    print("[DONE] Q2_rank_corr_matrix")


if __name__ == "__main__":
    main()
