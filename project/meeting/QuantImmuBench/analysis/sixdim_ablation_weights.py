#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
sixdim_ablation_weights.py
==========================
服务: QuantImmuBench § G3 lever (维度 ablation + 加权对比, 对应大纲 §3.3.2 表 7)
对应大纲: §3.3.2 Ablation test (表 7) — 附录 A 已指定本脚本名。

定位:
  对多维 fusion 做两类消融, 复现/检验大纲 §3.3.2 的两条声称 (实测为准, 不照搬):
    (1) 维度留一 (leave-one-dimension-out): 在主维度集上逐个去掉 1 维 → 剩余维 fusion,
        看 per-patient Spearman 掉多少 → 标出最"承重"维。
        大纲声称: ds2 deephlapan_Imm 最承重 (与亲和力/PRIME 最正交)。
    (2) 加权 ablation: 全维集上比 4 种加权方案 vs 等权。
        大纲声称: 加权一律塌回等权 (不帮忙)。

  ★ 不重造引擎 — 直接 import E2 的 fusion_12methods (apply_fusion / per_patient_spearman /
    DIM_SETS / _fit_simplex), 保证与 §3.3.1 表 6 口径完全一致、零破坏。学习/标签型权重
    一律 patient-level LOPO 无泄漏 (留一病人, 权重只用其余病人的标签算)。

════════════════════════════════════════════════════════════════════════════════
设计依据 (planner/coder 决策, 朱同学最终拍板)
════════════════════════════════════════════════════════════════════════════════

主维度集 = 6 维 SURV6 (主分析), 7 维 (= SURV6 + pool_netAffneg_top20) 作对照。
  依据: ① 本脚本名 "sixdim_*" + 大纲附录 A 指定 → 6 维为主集;
        ② 大纲 §3.3.2 称 "ds2 deephlapan_Imm 最承重", SURV6 含 MT_deepHLApan ✓;
        ③ 7 维是大纲 §3.3.4 robustness/§3.4 部署的主推集, 故并跑对照, 看承重维是否一致。
  SURV6 = MT_PredIG / MT_IMPROVE_mean_prediction_rf / MT_pTuneos / MT_PRIME /
          MT_ImmuneApp / MT_deepHLApan  (照搬 fusion_study.SURV6_TOOLS)。

主 fusion 法 = geomean (大纲 §3.3 明确唯一过双重检验的法则), mean_rank 作对照。
  两法都跑两类消融, 看承重维 / 加权结论是否随 fusion 法变。

主分析数据集 = DS2 (9 病人, 与 §3.3.1 表 6 一致); DS1 (6 病人) 作敏感性并跑。

4 种加权方案 vs 等权 (大纲 §3.3.2 只写 "4 种加权方式", 未给确切定义):
  ⚠️ [TODO 待朱 sixdim_ablation_weights.py 原版对账] —— 大纲表 7 未列 4 种加权的数学形式。
     以下为 4 种标准 + 合理默认的维度加权方案 (全在病人内 rank 空间做加权 mean-rank,
     与等权基线 = uniform weighted-mean-rank = mean_rank 同质可比, 最干净地验证
     "加权是否塌回等权"), 凡大纲未明确处均标 TODO, 绝不臆造成权威:

    基线  uniform        w_d = 1/D                          (等权 = mean_rank, 对照锚点)
    ─────────────────────────────────────────────────────────────────────────────
    1.   rho            w_d = max(rho_bar_d, 0)             按各维与标签的 per-patient
                        Spearman (Fisher-z 加权均值) 加权, 负相关维清零。
    2.   softmax_rho    w_d = softmax(rho_bar_d / T), T=1   软加权, 所有维有正权重,
                        强相关维更大。 [TODO T 待对账]。
    3.   inv_var        w_d = max(rho_bar_d, 0)/(se_d+eps)  逆"标准误"加权 (meta-analysis
                        逆方差思想): per-patient rho 跨病人越稳 (se 越小) 权重越大,
                        且乘 max(rho,0) 保方向。 [TODO 确切逆方差形式待对账]。
    4.   learned_simplex w = argmin‖R w − y‖² s.t. w>=0,Σw=1 单纯形约束学习权重
                        (复用 fusion_12methods._fit_simplex), 在 rank 空间拟合标签。
                        [TODO: §3.3.1 constrained 在标准化原始分空间, 此处在 rank 空间
                        与其余 3 种同质, 确切定义待对账]。

  无泄漏铁律: 方案 1-4 都用到标签, 故 patient-level LOPO —— 留一病人, 权重(rho_bar_d/
             se_d/simplex w)只用其余病人计算, 再应用到留出病人的病人内 rank。

最承重维判定法:
  对每个 dropped_dim, delta = rho(去掉该维) − rho(全维基线)。delta 最负 (去掉后 rho 掉
  最多) 的维 = 最承重。脚本末尾自动打印每个 (dataset, ndim, fusion) 的最承重维。

Windows 规范: UTF-8 stdout, 禁 scipy (OMP Error #15), 纯 numpy/pandas, 零 GPU, pathlib。

输入:  quantimmune/model_matrix_v2.csv (E0 产物, 183 行)
输出 (analysis/ablation_dim_weights.csv) — long format, section 列区分两部分:
  section=leave_one_out: 每 (dataset,ndim,fusion,dropped_dim) 一行 (dropped_dim="__full__"
                         为全维基线), 含 fusion_rho / delta_vs_full。
  section=weighting    : 每 (dataset,ndim,fusion,weight_scheme) 一行, delta_vs_full = vs
                         uniform 等权基线。

跑法 (主线跑, 我不跑):
  python analysis/sixdim_ablation_weights.py
  python analysis/sixdim_ablation_weights.py --matrix quantimmune/model_matrix_v2.csv --seed 42
"""

import sys
import argparse
from pathlib import Path

import numpy as np
import pandas as pd

# Windows 必要: UTF-8 stdout
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

HERE = Path(__file__).resolve().parent           # analysis/
ROOT = HERE.parent                                # QuantImmuBench/

# ── 复用 E2 引擎 (不改原脚本, 仅 import) ────────────────────────────────────────
sys.path.insert(0, str(HERE))
from fusion_12methods import (                    # noqa: E402
    apply_fusion,
    per_patient_spearman,
    DIM_SETS,
    _fit_simplex,
)
from fusion_study import (                        # noqa: E402
    spearman_np,
    fisherz_weighted_agg,
    MIN_PEP,
    DS1_PATIENTS,
    DS2_PATIENTS,
)

DEFAULT_MATRIX = ROOT / "quantimmune" / "model_matrix_v2.csv"

# 主维度集 = 6 维 SURV6; 7 维作对照 (见模块 docstring 设计依据)
ABLATION_NDIMS = [6, 7]

# 主 fusion 法 + 对照
FUSION_METHODS_ABLATION = ["geomean", "mean_rank"]

# 加权方案 (含等权基线 uniform; 其余 4 种 vs 等权)
WEIGHT_SCHEMES = ["uniform", "rho", "softmax_rho", "inv_var", "learned_simplex"]

EPS = 1e-9


# ═══════════════════════════════════════════════════════════════════════════════
# 病人内 rank 矩阵 (照抄 apply_fusion 无监督分支的 rank 逻辑, 保证口径一致)
# 病人内均值填补 (无泄漏: 不碰标签/他人), 全 NaN 维填 0, 各维升序 rank (分大→rank 大)。
# ═══════════════════════════════════════════════════════════════════════════════

def _patient_rank_matrix(df: pd.DataFrame, dim_cols: list,
                         patients: list) -> pd.DataFrame:
    """返回 index 对齐的病人内 rank DataFrame (仅 patients 内行有值)。"""
    rank_df = pd.DataFrame(np.nan, index=df.index, columns=dim_cols, dtype=float)
    for pat, g in df.groupby("Patient_ID"):
        if pat not in patients:
            continue
        sub = g[dim_cols].astype(float)
        filled = sub.fillna(sub.mean()).fillna(0.0)
        for c in dim_cols:
            rank_df.loc[g.index, c] = filled[c].rank(method="average").values
    return rank_df


# ═══════════════════════════════════════════════════════════════════════════════
# 各维 per-patient Spearman (逐病人 rho list, 供加权方案算权重)
# ═══════════════════════════════════════════════════════════════════════════════

def _dim_per_patient_rhos(df: pd.DataFrame, dim_col: str, patients: list,
                          label_col: str, min_pep: int):
    """返回 (rhos, ns): 第 dim_col 维对每个病人的 Spearman(score, label) 与肽数。"""
    rhos, ns = [], []
    for pat in patients:
        pat_df = df[df["Patient_ID"] == pat]
        n = len(pat_df)
        x = pat_df[dim_col].values.astype(float)
        y = pat_df[label_col].values.astype(float)
        rho = spearman_np(x, y) if n >= min_pep else np.nan
        rhos.append(rho)
        ns.append(float(n))
    return np.array(rhos, dtype=float), np.array(ns, dtype=float)


def _compute_weights(df_train: pd.DataFrame, dim_cols: list, train_pats: list,
                     scheme: str, label_col: str, min_pep: int,
                     T: float = 1.0) -> np.ndarray:
    """在训练折 (df_train, train_pats) 上算各维权重 w (归一化, 和为 1)。
    无泄漏: 只用训练折病人的标签。退化 (全非正/全 NaN) → 回退等权。
    """
    D = len(dim_cols)
    if scheme == "uniform":
        return np.ones(D) / D

    rho_bars, ses = [], []
    for c in dim_cols:
        rhos, ns = _dim_per_patient_rhos(df_train, c, train_pats, label_col, min_pep)
        rb, _, _, _nu, _nd = fisherz_weighted_agg(rhos, ns)
        valid = rhos[~np.isnan(rhos)]
        se = (np.std(valid, ddof=1) / np.sqrt(len(valid))
              if len(valid) > 1 else 1.0)
        rho_bars.append(rb)
        ses.append(se)
    rho_bars = np.nan_to_num(np.array(rho_bars, dtype=float), nan=0.0)
    ses = np.array(ses, dtype=float)

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
        return np.ones(D) / D   # 退化保护 → 等权
    return w / s


# ═══════════════════════════════════════════════════════════════════════════════
# LOPO 加权 mean-rank fusion (uniform/rho/softmax_rho/inv_var/learned_simplex)
# 留一病人 → 训练折算权重 (无泄漏) → 留出病人的病人内 rank 加权求和。
# uniform 等价于 mean_rank (sanity 锚点)。
# ═══════════════════════════════════════════════════════════════════════════════

def weighted_lopo_fusion(df: pd.DataFrame, dim_cols: list, scheme: str,
                         patients: list, *, label_col: str = "Elispot",
                         min_pep: int = MIN_PEP, T: float = 1.0) -> pd.Series:
    """对 dim_cols 用某加权方案做 LOPO 加权 mean-rank, 返回每行综合分 (index 对齐)。"""
    score = pd.Series(np.nan, index=df.index, dtype=float)
    rank_df = _patient_rank_matrix(df, dim_cols, patients)

    for pat in patients:
        train_pats = [p for p in patients if p != pat]
        test_idx = df[df["Patient_ID"] == pat].index
        if len(test_idx) == 0 or len(train_pats) == 0:
            continue

        if scheme == "learned_simplex":
            # rank 空间单纯形拟合 (复用 _fit_simplex), 标签居中 (intercept 对排名无影响)
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


# ═══════════════════════════════════════════════════════════════════════════════
# 主程序
# ═══════════════════════════════════════════════════════════════════════════════

def _r(v, d=6):
    return round(float(v), d) if (v is not None and not np.isnan(float(v))) else np.nan


def main():
    ap = argparse.ArgumentParser(
        description="sixdim_ablation_weights.py — QuantImmuBench G3 §3.3.2: 维度留一 + 加权对比")
    ap.add_argument("--matrix", default=str(DEFAULT_MATRIX),
                    help="model_matrix_v2.csv 路径")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--min_pep", type=int, default=MIN_PEP,
                    help=f"病人内最少肽数才算 rho (默认 {MIN_PEP})")
    args = ap.parse_args()

    matrix_path = Path(args.matrix)
    if not matrix_path.exists():
        sys.exit(f"[ERR] model_matrix 不存在: {matrix_path}")
    df = pd.read_csv(matrix_path, encoding="utf-8")
    print(f"[info] matrix: {df.shape}, 病人={df['Patient_ID'].nunique()}")

    ds2 = sorted([p for p in DS2_PATIENTS if p in df["Patient_ID"].unique()])
    ds1 = sorted([p for p in DS1_PATIENTS if p in df["Patient_ID"].unique()])
    datasets = [("DS2", ds2), ("DS1", ds1)]
    print(f"[info] DS2 (主分析) = {ds2}")
    print(f"[info] DS1 (敏感性) = {ds1}")

    rows = []

    for ds_name, pats in datasets:
        if not pats:
            print(f"[warn] {ds_name} 无病人, 跳过")
            continue

        for ndim in ABLATION_NDIMS:
            dims_all = DIM_SETS[ndim]
            present = [c for c in dims_all if c in df.columns]
            miss = [c for c in dims_all if c not in df.columns]
            print("\n" + "=" * 74)
            print(f"[{ds_name} | {ndim} 维] dims={present}"
                  + (f"  (缺失剔除: {miss})" if miss else ""))
            print("=" * 74)

            for fmethod in FUSION_METHODS_ABLATION:
                # ── (A) 全维基线 ──
                s_full = apply_fusion(df, present, fmethod, patients=pats,
                                      seed=args.seed, min_pep=args.min_pep)
                rho_full, cl_f, ch_f, nu_f = per_patient_spearman(
                    df, s_full, patients=pats, min_pep=args.min_pep)
                rows.append({
                    "section": "leave_one_out", "dataset": ds_name, "ndim": ndim,
                    "fusion_method": fmethod, "variant": "__full__",
                    "fusion_rho": _r(rho_full), "ci_low": _r(cl_f),
                    "ci_high": _r(ch_f), "n_pat": int(nu_f),
                    "delta_vs_full": 0.0,
                })
                print(f"  [LOO {fmethod}] FULL({ndim}d)  rho={rho_full:+.4f}  (n={nu_f})")

                # ── 维度留一 ──
                loo = []
                for drop in present:
                    dims_m = [c for c in present if c != drop]
                    s_m = apply_fusion(df, dims_m, fmethod, patients=pats,
                                       seed=args.seed, min_pep=args.min_pep)
                    rho_m, cl_m, ch_m, nu_m = per_patient_spearman(
                        df, s_m, patients=pats, min_pep=args.min_pep)
                    delta = (rho_m - rho_full
                             if not (np.isnan(rho_m) or np.isnan(rho_full)) else np.nan)
                    rows.append({
                        "section": "leave_one_out", "dataset": ds_name, "ndim": ndim,
                        "fusion_method": fmethod, "variant": drop,
                        "fusion_rho": _r(rho_m), "ci_low": _r(cl_m),
                        "ci_high": _r(ch_m), "n_pat": int(nu_m),
                        "delta_vs_full": _r(delta),
                    })
                    loo.append((drop, delta))
                    print(f"      drop {drop:<32s} rho={rho_m:+.4f}  Δ={delta:+.4f}")

                # 最承重维 = delta 最负
                valid_loo = [(d, x) for d, x in loo if not np.isnan(x)]
                if valid_loo:
                    load_bearing = min(valid_loo, key=lambda t: t[1])
                    print(f"    >> 最承重维 [{ds_name}|{ndim}d|{fmethod}]: "
                          f"{load_bearing[0]} (Δ={load_bearing[1]:+.4f})")

                # ── (B) 加权对比 (全维集) ──
                rho_uniform = None
                for scheme in WEIGHT_SCHEMES:
                    s_w = weighted_lopo_fusion(df, present, scheme, pats,
                                               min_pep=args.min_pep)
                    rho_w, cl_w, ch_w, nu_w = per_patient_spearman(
                        df, s_w, patients=pats, min_pep=args.min_pep)
                    if scheme == "uniform":
                        rho_uniform = rho_w
                    delta_w = (rho_w - rho_uniform
                               if (rho_uniform is not None
                                   and not (np.isnan(rho_w) or np.isnan(rho_uniform)))
                               else np.nan)
                    rows.append({
                        "section": "weighting", "dataset": ds_name, "ndim": ndim,
                        "fusion_method": "weighted_mean_rank", "variant": scheme,
                        "fusion_rho": _r(rho_w), "ci_low": _r(cl_w),
                        "ci_high": _r(ch_w), "n_pat": int(nu_w),
                        "delta_vs_full": _r(delta_w),  # 此处 = Δ vs uniform 等权
                    })
                    print(f"  [WEIGHT {scheme:<16s}] rho={rho_w:+.4f}  "
                          f"Δvs等权={delta_w:+.4f}  (n={nu_w})")

    out_df = pd.DataFrame(rows)
    out_path = HERE / "ablation_dim_weights.csv"
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("# ablation_dim_weights.csv\n")
        f.write("# QuantImmuBench G3 §3.3.2 表7: 维度留一消融 + 加权对比 (本地实证, 不照搬大纲)\n")
        f.write("# section=leave_one_out: variant=dropped_dim (__full__=全维基线); "
                "delta_vs_full=rho(去该维)-rho(全维), 最负=最承重维\n")
        f.write("# section=weighting: variant=加权方案 (uniform=等权基线); "
                "delta_vs_full=rho(该方案)-rho(uniform等权)\n")
        f.write("# 主集=6维SURV6, 7维对照; 主fusion=geomean, mean_rank对照; "
                "主分析=DS2, DS1敏感性\n")
        f.write("# 加权方案 1-4 用标签, 一律 patient-level LOPO 无泄漏 (权重只用训练折病人算)\n")
        f.write("# fusion_rho=per-patient Spearman Fisher-z 加权; ci_low/high=95%CI; "
                "n_pat=有效病人数\n")
        out_df.to_csv(f, index=False)
    print(f"\n[saved] {out_path}")
    print("[DONE]")


if __name__ == "__main__":
    main()
