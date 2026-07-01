#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Q2_taylor_verification.py
=========================
服务: QuantImmuBench §3.3.4 (geomean fusion 措辞) + 回答袁老师问题二 ——
  数值验证「geomean ≈ mean_rank」的泰勒展开近似: G ≈ A·(1 − s²/(2A²)) = A − s²/(2A),
  即 mean_rank(A) 与 geomean(G) 的差 ≈ 病人内 rank 方差 s² 的一半除以均值 A。
对应大纲: paper/QuanImmu-Paper-Outline.md §3.3.4。

数学 (逐肽 i, 病人内对 6 维 rank 向量 R[i,:]):
  A_i = mean(R[i,:])                              (mean_rank 融合分, 算术均值)
  G_i = exp(mean(log(R[i,:]))) = geomean(R[i,:])  (geomean 融合分, 几何均值)
  s²_i = var(R[i,:])  (population 方差, 分母 D=6, 即 np.var ddof=0 = np.mean 的方差)
  实际修正 corr_actual = A_i − G_i
  理论修正 corr_theory = s²_i / (2·A_i)          (二阶泰勒: ln(G)=ln(A) − s²/(2A²) ⇒ A−G≈s²/(2A))
  残差 residual = corr_actual − corr_theory
  相对误差% rel_err_pct = residual / corr_actual × 100  (corr_actual≈0 时给 NaN 防除零爆)

方法 (病人内 rank 逻辑照抄 _official_common.apply_fusion 无监督分支):
  每病人组: SURV6 6 维 max 分 fillna(列均值).fillna(0) → rank(method='average') 得 R (肽×6)。
  纯 numpy, 禁 scipy (防 OMP #15)。

输入 (只读干净表): data/frozen/pooled_clean_9mer.csv (130 肽 / 9 患者 / 9mer)。
输出 (analysis/theory/, 不存在则脚本内 os.makedirs):
  Q2_taylor_verification.csv — 逐肽: mut_key,Patient_ID,A_i,G_i,s2_i,corr_actual,corr_theory,
                               residual,rel_err_pct + 顶部注释 (公式 + 全体残差中位/95分位)。
  ★ 本脚本不画图 (画图后续单独派), 只出 csv。

跑法 (主线跑, 本脚本绝不自跑):
  cd D:/YJ-Agent/project/meeting/QuantImmuBench
  python analysis/theory/Q2_taylor_verification.py
"""

import os
import sys
import argparse
from pathlib import Path

import numpy as np
import pandas as pd

# 引擎在 analysis/official/; 本脚本在 analysis/theory/ → 把 official 加进 sys.path 复用。
HERE = Path(__file__).resolve().parent                    # analysis/theory/
ANALYSIS = HERE.parent                                    # analysis/
OFFICIAL = ANALYSIS / "official"
sys.path.insert(0, str(OFFICIAL))
from _official_common import (                             # noqa: E402
    load_frozen, present_patients, pool_col, MIN_PEP, FROZEN_POOLED,
)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# ── 整合维度 (★ TODO 待袁/朱确认, 同 R3/R5/R7 SURV6) ─────────────────────────────
SURV6 = ["PredIG", "IMPROVE", "pTuneos", "PRIME", "ImmuneApp", "deepHLApan"]

GEO_EPS = 1e-9   # 同 _official_common.fuse_geomean 的 eps (rank>=1 时几乎无影响)


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


def main():
    ap = argparse.ArgumentParser(
        description="Q2 官方: geomean≈mean_rank 泰勒展开逐肽数值验证 (§3.3.4)")
    ap.add_argument("--input", default=str(FROZEN_POOLED), help="干净肽级表路径")
    ap.add_argument("--min_pep", type=int, default=MIN_PEP)
    args = ap.parse_args()

    df = load_frozen(args.input)
    pats = present_patients(df)
    print(f"[info] 干净表 {df.shape}; DS2 患者({len(pats)})={pats}; min_pep={args.min_pep}")

    surv6_cols, surv6_used = build_surv6_cols(df)
    D = len(surv6_cols)
    print(f"[dims] SURV6 max 维(D={D})={surv6_used}")
    if "mut_key" not in df.columns:
        sys.exit("[ERR] 干净表缺 mut_key 列")

    rows = []
    # ── 病人内 rank (照抄 apply_fusion 无监督分支: fillna(列均值).fillna(0) → rank average) ──
    for pat, g in df.groupby("Patient_ID"):
        if pat not in pats:
            continue
        if len(g) < args.min_pep:
            continue
        sub = g[surv6_cols].astype(float)
        filled = sub.fillna(sub.mean()).fillna(0.0)
        R = np.column_stack([
            filled[c].rank(method="average").values.astype(float) for c in surv6_cols])  # (n_pep, D)
        mut_keys = g["mut_key"].values
        for k in range(R.shape[0]):
            r = R[k, :]
            A = float(np.mean(r))
            G = float(np.exp(np.mean(np.log(np.maximum(r, GEO_EPS)))))
            s2 = float(np.var(r))                 # population 方差 (ddof=0, 分母 D)
            corr_actual = A - G
            corr_theory = s2 / (2.0 * A) if A > 0 else np.nan
            residual = corr_actual - corr_theory
            # corr_actual≈0 (方差为 0, 全维同 rank) → 相对误差无意义, 给 NaN
            rel_err_pct = (residual / corr_actual * 100.0) if abs(corr_actual) > 1e-12 else np.nan
            rows.append(dict(
                mut_key=mut_keys[k], Patient_ID=int(pat),
                A_i=round(A, 6), G_i=round(G, 6), s2_i=round(s2, 6),
                corr_actual=round(corr_actual, 6), corr_theory=round(corr_theory, 6),
                residual=round(residual, 6),
                rel_err_pct=(round(rel_err_pct, 4) if not np.isnan(rel_err_pct) else np.nan),
            ))

    out_df = pd.DataFrame(rows)
    n = len(out_df)
    res = out_df["residual"].values.astype(float)
    res_valid = res[~np.isnan(res)]
    res_med = float(np.median(res_valid)) if len(res_valid) else np.nan
    res_p95 = float(np.percentile(np.abs(res_valid), 95)) if len(res_valid) else np.nan
    relp = out_df["rel_err_pct"].values.astype(float)
    relp_valid = np.abs(relp[~np.isnan(relp)])
    relp_med = float(np.median(relp_valid)) if len(relp_valid) else np.nan
    print(f"[summary] 逐肽 n={n}; residual 中位={res_med:.6f}; |residual| 95分位={res_p95:.6f}; "
          f"|rel_err%| 中位={relp_med:.4f}")

    out_dir = HERE
    os.makedirs(out_dir, exist_ok=True)          # analysis/theory/ 不存在则建
    out_csv = out_dir / "Q2_taylor_verification.csv"
    with open(out_csv, "w", encoding="utf-8", newline="") as f:
        f.write("# Q2_taylor_verification.csv — §3.3.4 geomean≈mean_rank 泰勒展开逐肽数值验证\n")
        f.write("# 公式: ln(G)=ln(A) − s²/(2A²) ⇒ 实际修正 A−G ≈ 理论修正 s²/(2A) (二阶泰勒)。\n")
        f.write(f"# 口径: 官方 130 肽 / 9 患者 / 9mer; 输入={Path(args.input).name}; SURV6 max 维(D={D})={surv6_used} (★TODO 待袁/朱确认)。\n")
        f.write("# A_i=mean(rank), G_i=geomean(rank), s2_i=var(rank, 分母 D 即 population); "
                "corr_actual=A−G, corr_theory=s²/(2A), residual=actual−theory, rel_err_pct=residual/actual×100。\n")
        f.write(f"# 全体残差: 中位={res_med:.6f}, |残差| 95分位={res_p95:.6f}, |rel_err%| 中位={relp_med:.4f} (n={n})。\n")
        out_df.to_csv(f, index=False)
    print(f"\n[saved] {out_csv}")
    print("[DONE] Q2_taylor_verification (只出 csv, 不画图)")


if __name__ == "__main__":
    main()
