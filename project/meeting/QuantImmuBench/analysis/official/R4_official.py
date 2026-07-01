#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
R4_official.py
==============
服务: QuantImmuBench 大纲 §3.3.2 (表7) —— 维度留一消融 + 4 加权方式对比。
对应大纲: paper/QuanImmu-Paper-Outline.md §3.3.2 "Ablation test (表7)"。

★ 2026-07-01 Part D Phase 3b 干净口径 (见 04_LOG):
  · 输入 = 干净表 pooled_clean_9mer.csv (130×1536, 含 peplen)。
  · [B5 零选择] 维度集各工具 headline 用零选择 <tool>_max, 去 in-sample pooling selection
    (旧脚本用 best_pooling_for_tool 挑最优 pooling = 乐观选择偏 + 会捡回肽长混杂, 已弃)。
  · [B2 控肽长] 每 (维度留一/加权) 变体主指标加控肽长版对照 fusion_rho_lenctrl
    (per_patient_partial_spearman(ctrl='peplen'))。
  · [B4 bootstrap] CI 一律 cluster-bootstrap over patients (对裸 fusion 分数), 弃固定效应过窄 CI。
  【旧 count-clean / best-pooling 注释已删】: 干净表不带 count_conf 列, 混杂改由 B2 偏相关控。

做什么 (两类消融, 实测为准不照搬大纲声称):
  (1) 维度留一 (leave-one-dimension-out): 主维度集上逐个去 1 维 → 剩余维 fusion,
      看 per-patient Spearman 掉多少 → 标最承重维。大纲声称 deepHLApan 最承重。
  (2) 加权 ablation: 全维集上比 4 加权方案 (rho/softmax_rho/inv_var/learned_simplex)
      vs 等权 uniform。大纲声称: 加权一律塌回等权。
  主维度集 = 6 维 SURV6 (主分析), 7 维对照; 主 fusion = geomean, mean_rank 对照。
  加权方案用标签 → 一律 patient-level LOPO 无泄漏 (权重只用训练折病人算)。

输入 (只读干净表):
  data/frozen/pooled_clean_9mer.csv
输出 (analysis/official/):
  R4_ablation_official.csv  —— long format:
    section=leave_one_out : 每 (ndim,fusion,variant) 一行 (variant=__full__ 为全维基线),
                            含 fusion_rho(裸) / fusion_rho_lenctrl / ci_lo/ci_hi(bootstrap) /
                            delta_vs_full (最负=最承重维)。
    section=weighting     : 每 (ndim,variant=加权方案) 一行, delta_vs_full = vs uniform 等权。

复用旧骨架:
  · 引擎 apply_fusion / per_patient_spearman → _official_common
  · 控肽长偏相关 (B2) → per_patient_partial_spearman; bootstrap CI (B4) → bootstrap_patient_ci
  · 维度留一 + 加权 LOPO + 最承重维判定 ← analysis/sixdim_ablation_weights.py 整套逻辑

★ 维度集成员 = selection (同 R3), TODO 待袁/朱确认 (见下方 SURV6 / DIM7_TOOLS)。
  4 种加权方案数学形式: 大纲表7 未给, 为标准 + 合理默认, 标 [TODO 待对账]。

跑法 (主线跑, 我不跑):
  python analysis/official/R4_official.py
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
    pool_col, spearman_np, fisherz_weighted_agg,
    _fit_simplex, MIN_PEP, LABEL_COL, FROZEN_POOLED, ensure_out_dir, r6,
)

# ── 维度集成员 (★ TODO 待袁/朱确认, 同 R3; 各工具零选择 <tool>_max) ────────────────
AFFINITY_PROXY = "netMHCpan_BA"   # TODO: 旧 pool_netAffneg_top20 冻结表代理
SURV6 = ["PredIG", "IMPROVE", "pTuneos", "PRIME", "ImmuneApp", "deepHLApan"]
DIM7_TOOLS = list(SURV6) + [AFFINITY_PROXY]
ABLATION_TOOLSETS = {6: list(SURV6), 7: DIM7_TOOLS}

FUSION_METHODS_ABLATION = ["geomean", "mean_rank"]
# 4 加权方案 (含等权基线 uniform); 数学形式 [TODO 待朱对账] —— 标准+合理默认:
#   rho            : w_d = max(rho_bar_d, 0)            按各维 per-patient Fisher-z 加权
#   softmax_rho    : w_d = softmax(rho_bar_d / T)       软加权, T=1 [TODO T 待对账]
#   inv_var        : w_d = max(rho_bar_d,0)/(se_d+eps)  逆标准误加权
#   learned_simplex: w = argmin‖Rw-y‖² s.t. w>=0,Σw=1   rank 空间单纯形学习
WEIGHT_SCHEMES = ["uniform", "rho", "softmax_rho", "inv_var", "learned_simplex"]
EPS = 1e-9


def resolve_dim_cols(df, tools, pats, min_pep):
    """[B5 零选择] 各工具用 <tool>_max, 不 in-sample 挑 pooling。缺列/全空剔除。
    返回 (cols, used_labels)。"""
    cols, used = [], []
    for t in tools:
        col = pool_col(t, "max")
        if col not in df.columns or df[col].notna().sum() == 0:
            print(f"[warn] {t}: 列 {col} 缺失或全空, 剔除该维")
            continue
        cols.append(col)
        used.append(f"{t}_max")
    return cols, used


def eval_metrics(df, score, pats, min_pep, ctrl, n_boot, seed):
    """一个 fusion 分数 → (rho_raw, rho_lenctrl, ci_lo, ci_hi, n_pat)。
    rho_raw=裸 per-patient Fisher-z; rho_lenctrl=控肽长偏相关(B2);
    ci_*=cluster-bootstrap over patients 95%CI(B4, 对裸分数)。"""
    s_arr = np.asarray(score.values if hasattr(score, "values") else score, float)
    rho_raw, _cl, _ch, nu, _nd = per_patient_spearman(
        df, s_arr, patients=pats, min_pep=min_pep)
    rho_len, _, _, _, _ = per_patient_partial_spearman(
        df, s_arr, ctrl=ctrl, patients=pats, min_pep=min_pep)
    _, ci_lo, ci_hi, _ = bootstrap_patient_ci(
        df, s_arr, n_boot=n_boot, seed=seed, patients=pats, min_pep=min_pep)
    return rho_raw, rho_len, ci_lo, ci_hi, nu


# ── 加权 LOPO mean-rank (照搬 sixdim_ablation_weights.py) ───────────────────────

def _patient_rank_matrix(df, dim_cols, patients):
    rank_df = pd.DataFrame(np.nan, index=df.index, columns=dim_cols, dtype=float)
    for pat, g in df.groupby("Patient_ID"):
        if pat not in patients:
            continue
        sub = g[dim_cols].astype(float)
        filled = sub.fillna(sub.mean()).fillna(0.0)
        for c in dim_cols:
            rank_df.loc[g.index, c] = filled[c].rank(method="average").values
    return rank_df


def _dim_per_patient_rhos(df, dim_col, patients, label_col, min_pep):
    rhos, ns = [], []
    for pat in patients:
        g = df[df["Patient_ID"] == pat]
        n = len(g)
        x = g[dim_col].values.astype(float)
        y = g[label_col].values.astype(float)
        rho = spearman_np(x, y) if n >= min_pep else np.nan
        rhos.append(rho)
        ns.append(float(n))
    return np.array(rhos, float), np.array(ns, float)


def _compute_weights(df_train, dim_cols, train_pats, scheme, label_col, min_pep, T=1.0):
    D = len(dim_cols)
    if scheme == "uniform":
        return np.ones(D) / D
    rho_bars, ses = [], []
    for c in dim_cols:
        rhos, ns = _dim_per_patient_rhos(df_train, c, train_pats, label_col, min_pep)
        rb, _, _, _nu, _nd = fisherz_weighted_agg(rhos, ns)
        valid = rhos[~np.isnan(rhos)]
        se = (np.std(valid, ddof=1) / np.sqrt(len(valid)) if len(valid) > 1 else 1.0)
        rho_bars.append(rb)
        ses.append(se)
    rho_bars = np.nan_to_num(np.array(rho_bars, float), nan=0.0)
    ses = np.array(ses, float)
    if scheme == "rho":
        w = np.maximum(rho_bars, 0.0)
    elif scheme == "softmax_rho":
        z = rho_bars / T
        z = z - np.max(z)
        e = np.exp(z)
        w = e / e.sum()
    elif scheme == "inv_var":
        w = np.maximum(rho_bars, 0.0) / (ses + EPS)
    else:
        raise ValueError(f"未知非学习加权方案: {scheme}")
    s = w.sum()
    if not np.isfinite(s) or s <= 0:
        return np.ones(D) / D
    return w / s


def weighted_lopo_fusion(df, dim_cols, scheme, patients, *,
                         label_col=LABEL_COL, min_pep=MIN_PEP, T=1.0):
    score = pd.Series(np.nan, index=df.index, dtype=float)
    rank_df = _patient_rank_matrix(df, dim_cols, patients)
    for pat in patients:
        train_pats = [p for p in patients if p != pat]
        test_idx = df[df["Patient_ID"] == pat].index
        if len(test_idx) == 0 or len(train_pats) == 0:
            continue
        if scheme == "learned_simplex":
            df_train = df[df["Patient_ID"].isin(train_pats)]
            R_train = rank_df.loc[df_train.index].values.astype(float)
            y_train = df_train[label_col].values.astype(float)
            valid = ~np.isnan(y_train)
            if valid.sum() == 0:
                w = np.ones(len(dim_cols)) / len(dim_cols)
            else:
                yc = y_train[valid] - y_train[valid].mean()
                w = _fit_simplex(R_train[valid], yc)
        else:
            df_train = df[df["Patient_ID"].isin(train_pats)]
            w = _compute_weights(df_train, dim_cols, train_pats, scheme,
                                 label_col, min_pep, T)
        R_test = rank_df.loc[test_idx].values.astype(float)
        score.loc[test_idx] = R_test @ w
    return score


def main():
    ap = argparse.ArgumentParser(
        description="R4 官方: 维度留一 + 加权对比 (§3.3.2 表7)")
    ap.add_argument("--input", default=str(FROZEN_POOLED), help="干净肽级表路径")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--min_pep", type=int, default=MIN_PEP)
    ap.add_argument("--ctrl", default="peplen", help="控制变量列 (B2 偏相关, 默认 peplen)")
    ap.add_argument("--n_boot", type=int, default=2000, help="bootstrap 重采样次数 (B4)")
    args = ap.parse_args()

    df = load_frozen(args.input)
    pats = present_patients(df)
    print(f"[info] 干净表: {df.shape}; DS2 患者({len(pats)})={pats}; "
          f"ctrl={args.ctrl}; n_boot={args.n_boot}")

    rows = []
    for ndim in sorted(ABLATION_TOOLSETS.keys()):
        dim_cols, used = resolve_dim_cols(df, ABLATION_TOOLSETS[ndim], pats, args.min_pep)
        print("\n" + "=" * 72)
        print(f"[{ndim} 维 · 零选择 max] 列={used}")
        print("=" * 72)
        if len(dim_cols) < 2:
            print(f"[warn] {ndim} 维有效列<2, 跳过")
            continue

        for fmethod in FUSION_METHODS_ABLATION:
            # (A) 全维基线
            s_full = apply_fusion(df, dim_cols, fmethod, patients=pats, seed=args.seed)
            rho_full, rho_full_len, cl_f, ch_f, nu_f = eval_metrics(
                df, s_full, pats, args.min_pep, args.ctrl, args.n_boot, args.seed)
            rows.append(dict(section="leave_one_out", ndim=ndim, fusion_method=fmethod,
                             variant="__full__", fusion_rho=r6(rho_full),
                             fusion_rho_lenctrl=r6(rho_full_len),
                             ci_lo=r6(cl_f), ci_hi=r6(ch_f), n_pat=int(nu_f),
                             delta_vs_full=0.0))
            print(f"  [LOO {fmethod}] FULL({ndim}d) rho={rho_full:+.4f} "
                  f"lenctrl={rho_full_len:+.4f} (n={nu_f})")

            # 维度留一
            loo = []
            for drop, drop_used in zip(dim_cols, used):
                dims_m = [c for c in dim_cols if c != drop]
                s_m = apply_fusion(df, dims_m, fmethod, patients=pats, seed=args.seed)
                rho_m, rho_m_len, cl_m, ch_m, nu_m = eval_metrics(
                    df, s_m, pats, args.min_pep, args.ctrl, args.n_boot, args.seed)
                delta = (rho_m - rho_full
                         if not (np.isnan(rho_m) or np.isnan(rho_full)) else np.nan)
                rows.append(dict(section="leave_one_out", ndim=ndim,
                                 fusion_method=fmethod, variant=drop_used,
                                 fusion_rho=r6(rho_m), fusion_rho_lenctrl=r6(rho_m_len),
                                 ci_lo=r6(cl_m), ci_hi=r6(ch_m), n_pat=int(nu_m),
                                 delta_vs_full=r6(delta)))
                loo.append((drop_used, delta))
                print(f"      drop {drop_used:<26s} rho={rho_m:+.4f} Δ={delta:+.4f}")
            valid_loo = [(d, x) for d, x in loo if not np.isnan(x)]
            if valid_loo:
                lb = min(valid_loo, key=lambda t: t[1])
                print(f"    >> 最承重维 [{ndim}d|{fmethod}]: {lb[0]} (Δ={lb[1]:+.4f})")

            # (B) 加权对比 (仅 fmethod=mean_rank 的 rank 空间; geomean 时不重复跑加权)
            if fmethod == "mean_rank":
                rho_uniform = None
                for scheme in WEIGHT_SCHEMES:
                    s_w = weighted_lopo_fusion(df, dim_cols, scheme, pats,
                                               min_pep=args.min_pep)
                    rho_w, rho_w_len, cl_w, ch_w, nu_w = eval_metrics(
                        df, s_w, pats, args.min_pep, args.ctrl, args.n_boot, args.seed)
                    if scheme == "uniform":
                        rho_uniform = rho_w
                    delta_w = (rho_w - rho_uniform
                               if (rho_uniform is not None
                                   and not (np.isnan(rho_w) or np.isnan(rho_uniform)))
                               else np.nan)
                    rows.append(dict(section="weighting", ndim=ndim,
                                     fusion_method="weighted_mean_rank", variant=scheme,
                                     fusion_rho=r6(rho_w), fusion_rho_lenctrl=r6(rho_w_len),
                                     ci_lo=r6(cl_w), ci_hi=r6(ch_w), n_pat=int(nu_w),
                                     delta_vs_full=r6(delta_w)))
                    print(f"  [WEIGHT {scheme:<16s}] rho={rho_w:+.4f} "
                          f"lenctrl={rho_w_len:+.4f} Δvs等权={delta_w:+.4f} (n={nu_w})")

    out_df = pd.DataFrame(rows)
    out_dir = ensure_out_dir()
    out_path = out_dir / "R4_ablation_official.csv"
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("# R4_ablation_official.csv\n")
        f.write("# QuantImmuBench §3.3.2 表7: 维度留一消融 + 加权对比 (干净口径, 本地实证)\n")
        f.write(f"# 输入={Path(args.input).name}; DS2 9 患者; 维度零选择 <tool>_max(B5); 主集6维SURV6, 7维对照; geomean/mean_rank\n")
        f.write("# section=leave_one_out: variant=去掉的维(__full__=全维); delta_vs_full 最负=最承重维\n")
        f.write("# section=weighting: variant=加权方案(uniform=等权基线); delta_vs_full=vs等权\n")
        f.write(f"# fusion_rho=裸等权; fusion_rho_lenctrl=控肽长偏相关(B2, ctrl={args.ctrl}); ci_*=cluster-bootstrap over patients 95%CI(B4, 裸分数)\n")
        f.write("# ★ 维度集成员 + 4 加权方案形式=TODO 待袁/朱确认; 加权用标签一律 LOPO 无泄漏\n")
        out_df.to_csv(f, index=False)
    print(f"\n[saved] {out_path}  shape={out_df.shape}")
    print("[DONE] R4")


if __name__ == "__main__":
    main()
