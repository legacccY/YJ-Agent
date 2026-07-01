#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
R6_official.py
==============
服务: QuantImmuBench 大纲 §3.3.4 (图3 / 表9) —— fusion 子采样删突变鲁棒性。
对应大纲: paper/QuanImmu-Paper-Outline.md §3.3.4 "鲁棒性 (图3 / 表9)"。

★ 2026-07-01 Part D Phase 3 口径 (干净表 + 新评判标准, 见 04_LOG):
  输入 = 干净表 pooled_clean_9mer.csv (含突变去噪 + 51 pooling 变体 + peplen 列)。
  · [B5 零选择] 7 维各工具用 <tool>_max (去 in-sample pooling selection); 删10/20%×种子
    鲁棒性 + win_top1 口径不变, 只是维度改零选择 max。
  · [B2] 满数据(0%)fusion + 单工具主指标各加控肽长版对照 (per_patient_partial_spearman,
    ctrl='peplen'); 子采样各 seed 仍走裸 Spearman (鲁棒性/win_top1 语义不变)。
  【旧 count-clean 注释已删】: 干净表不带 count_conf 列, 混杂改由 B2 偏相关在度量层控。

做什么:
  主分析集 DS2 上, 病人内随机删 10%/20% 突变 × 30 个固定种子 (0..29), 对每种 fusion
  (12 法) + 单工具对照重算 per-patient Spearman, 跨种子聚合 子采样均值/中位/胜率,
  检验「满数据点估计 vs 子采样鲁棒性」。验大纲: geomean 在 10%/20% 双双第一;
  max 满数据虚高但子采样塌陷 (点估计陷阱)。如实输出实测, headline 成立与否=拍板点, 不凑数。
  主维度集 = 7 维 (SURV6 + 亲和代理), 各工具取 R2 最优 pooling 列。

输入 (只读干净表):
  data/frozen/pooled_clean_9mer.csv
输出 (analysis/official/):
  R6_robustness_official_results.csv  —— 长表: method, kind, drop_frac, seed, fisherz_rho, n_pat
  R6_robustness_official_summary.csv  —— 每 (method,drop_frac): full_data_rho / mean / median /
                                        std / win_rate_top1 / win_rate_vs_base / rank / n_seeds

复用旧骨架:
  · 病人内随机删 (保底 min_pep) + 30 seed + 子采样均值/中位/胜率 ← analysis/robustness_subsample.py
  · fusion 引擎 + 主指标 → _official_common (apply_fusion / per_patient_spearman)

★ 维度集成员 = selection (同 R3 DIM7), TODO 待袁/朱确认。

跑法 (主线跑, 我不跑):
  python analysis/official/R6_official.py
  python analysis/official/R6_official.py --seeds 0-29 --drop 0.10,0.20
"""

import sys
import argparse
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _official_common import (                              # noqa: E402
    load_frozen, present_patients, per_patient_spearman,
    per_patient_partial_spearman, apply_fusion, pool_col, METHOD_ORDER,
    MIN_PEP, FROZEN_POOLED, ensure_out_dir,
)

# ── 主维度集 7 维 (★ TODO 待袁/朱确认成员, 同 R3 DIM7; [B5] 各工具用零选择 <tool>_max) ──
AFFINITY_PROXY = "netMHCpan_BA"   # 旧 pool_netAffneg_top20 对应工具 (此处零选择用 _max)
SURV6 = ["PredIG", "IMPROVE", "pTuneos", "PRIME", "ImmuneApp", "deepHLApan"]
DIM7_TOOLS = list(SURV6) + [AFFINITY_PROXY]


def subsample_per_patient(df, patients, drop_frac, seed, min_pep):
    """每病人独立随机删 drop_frac 比例突变, 强制保底 keep>=min_pep。只删整行, 不碰标签。
    照搬 robustness_subsample.py: 每 (drop_frac,seed) 独立 bit 可复现 SeedSequence。
    """
    if drop_frac <= 0:
        return df.copy()
    rng = np.random.default_rng([int(seed), int(round(drop_frac * 1000))])
    keep_index = []
    for pat in sorted(patients):
        idx = df.index[df["Patient_ID"] == pat].to_numpy()
        n = len(idx)
        if n == 0:
            continue
        n_keep = n - int(round(n * drop_frac))
        if n_keep < min_pep:
            n_keep = min(min_pep, n)
        if n_keep >= n:
            keep_index.extend(idx.tolist())
            continue
        perm = rng.permutation(idx)
        keep_index.extend(perm[:n_keep].tolist())
    other = df.index[~df["Patient_ID"].isin(patients)].to_numpy()
    keep_index.extend(other.tolist())
    return df.loc[sorted(set(keep_index))].copy()


def _parse_seeds(spec):
    out = set()
    for part in str(spec).split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            a, b = part.split("-")
            out.update(range(int(a), int(b) + 1))
        else:
            out.add(int(part))
    return sorted(out)


def main():
    ap = argparse.ArgumentParser(
        description="R6 官方: fusion 子采样删突变鲁棒性 (§3.3.4 图3/表9)")
    ap.add_argument("--input", default=str(FROZEN_POOLED), help="冻结肽级表路径")
    ap.add_argument("--seeds", default="0-29", help="种子列表 (默认 0-29 共 30 个)")
    ap.add_argument("--drop", default="0.10,0.20", help="删除比例 (0% 对照自动加)")
    ap.add_argument("--min_pep", type=int, default=MIN_PEP)
    ap.add_argument("--ctrl", default="peplen", help="控制变量列 (B2 偏相关, 默认 peplen)")
    ap.add_argument("--baseline_col", default=None,
                    help="指定 max baseline 单工具列; 默认=满数据 rho 最高单工具")
    args = ap.parse_args()

    df = load_frozen(args.input)
    pats = present_patients(df)
    # 7 维各工具零选择 <tool>_max (B5)
    dim_cols, used = [], []
    for t in DIM7_TOOLS:
        col = pool_col(t, "max")
        if col not in df.columns or df[col].notna().sum() == 0:
            print(f"[warn] {t}: 列 {col} 缺失或全空, 剔除")
            continue
        dim_cols.append(col)
        used.append(col)
    print(f"[info] DS2 患者({len(pats)})={pats}; 7 维(零选择 max)={used}")

    seeds = _parse_seeds(args.seeds)
    drops = sorted({round(float(x), 4) for x in args.drop.split(",")})
    fusion_methods = list(METHOD_ORDER)
    single_cols = list(dim_cols)
    print(f"[info] seeds={len(seeds)}({seeds[0]}..{seeds[-1]}); drop={drops}; "
          f"{len(fusion_methods)}fusion+{len(single_cols)}single")

    def _rho(method, kind, sub_df, seed):
        if kind == "fusion":
            s = apply_fusion(sub_df, dim_cols, method, patients=pats, seed=seed)
            rho, _, _, nu, _ = per_patient_spearman(sub_df, s, patients=pats,
                                                    min_pep=args.min_pep)
            return rho, nu
        if method not in sub_df.columns:
            return np.nan, 0
        rho, _, _, nu, _ = per_patient_spearman(sub_df, method, patients=pats,
                                                min_pep=args.min_pep)
        return rho, nu

    rows = []
    # (a) 0% 满数据对照 (裸 + [B2] 控肽长版主指标)
    full_rho = {}
    full_rho_len = {}     # [B2] method -> 控肽长偏相关 ρ̄ (仅 0% 满数据主指标)
    print("\n[0% 满数据对照]")
    for m in fusion_methods:
        s = apply_fusion(df, dim_cols, m, patients=pats, seed=42)
        s_arr = np.asarray(s.values, dtype=float)
        rho, _, _, n, _ = per_patient_spearman(df, s_arr, patients=pats, min_pep=args.min_pep)
        rho_len, *_ = per_patient_partial_spearman(
            df, s_arr, ctrl=args.ctrl, patients=pats, min_pep=args.min_pep)
        full_rho[m] = rho
        full_rho_len[m] = rho_len
        rows.append(dict(method=m, kind="fusion", drop_frac=0.0, seed=-1,
                         fisherz_rho=rho, n_pat=n))
    for c in single_cols:
        rho, n = _rho(c, "single", df, 42)
        rho_len, *_ = per_patient_partial_spearman(
            df, c, ctrl=args.ctrl, patients=pats, min_pep=args.min_pep)
        full_rho[c] = rho
        full_rho_len[c] = rho_len
        rows.append(dict(method=c, kind="single", drop_frac=0.0, seed=-1,
                         fisherz_rho=rho, n_pat=n))

    if args.baseline_col and args.baseline_col in single_cols:
        baseline_col = args.baseline_col
    else:
        vs = {c: full_rho[c] for c in single_cols
              if full_rho[c] is not None and not np.isnan(full_rho[c])}
        baseline_col = max(vs, key=vs.get) if vs else None
    print(f"[info] max baseline 单工具={baseline_col} "
          f"(满数据 rho={full_rho.get(baseline_col, float('nan')):+.4f})")

    # (b) 子采样
    for drop_frac in drops:
        print(f"\n[删 {drop_frac*100:.0f}%] {len(seeds)} seed ...")
        for seed in seeds:
            sub = subsample_per_patient(df, pats, drop_frac, seed, args.min_pep)
            for m in fusion_methods:
                rho, n = _rho(m, "fusion", sub, seed)
                rows.append(dict(method=m, kind="fusion", drop_frac=drop_frac,
                                 seed=seed, fisherz_rho=rho, n_pat=n))
            for c in single_cols:
                rho, n = _rho(c, "single", sub, seed)
                rows.append(dict(method=c, kind="single", drop_frac=drop_frac,
                                 seed=seed, fisherz_rho=rho, n_pat=n))

    long_df = pd.DataFrame(rows)
    out_dir = ensure_out_dir()
    res_path = out_dir / "R6_robustness_official_results.csv"
    with open(res_path, "w", encoding="utf-8") as f:
        f.write("# R6_robustness_official_results.csv\n")
        f.write("# QuantImmuBench §3.3.4 图3: 病人内随机删突变子采样鲁棒性 (长表)\n")
        f.write(f"# 输入={Path(args.input).name}; DS2 患者={pats}; 7 维={used}\n")
        f.write("# kind=fusion(12法)/single(单工具=各维列); drop_frac=删除比例(0=满数据); seed=-1=0%确定性\n")
        f.write("# 病人内随机删, 保每病人>=min_pep; 只删整行不碰标签; ★维度集=TODO 待袁/朱确认\n")
        long_df.to_csv(f, index=False)
    print(f"\n[saved] {res_path} ({len(long_df)} 行)")

    # ── 汇总 ──
    def _safe(a):
        a = np.asarray(a, float)
        return a[~np.isnan(a)]

    sum_rows = []
    for drop_frac in drops:
        sub = long_df[long_df["drop_frac"] == drop_frac]
        fus = sub[sub["kind"] == "fusion"]
        piv = fus.pivot_table(index="seed", columns="method",
                              values="fisherz_rho", aggfunc="first")
        top1 = piv.idxmax(axis=1, skipna=True)
        n_top1 = top1.notna().sum()
        base = (sub[sub["method"] == baseline_col].set_index("seed")["fisherz_rho"]
                if baseline_col else pd.Series(dtype=float))
        for method in fusion_methods + single_cols:
            kind = "fusion" if method in fusion_methods else "single"
            mser = sub[sub["method"] == method].set_index("seed")["fisherz_rho"]
            vals = _safe(mser.values)
            if kind == "fusion" and n_top1 > 0:
                win_top1 = float((top1 == method).sum()) / float(n_top1)
            else:
                win_top1 = np.nan
            if baseline_col and method != baseline_col and len(base) > 0:
                common = mser.index.intersection(base.index)
                m = mser.reindex(common).values.astype(float)
                b = base.reindex(common).values.astype(float)
                ok = ~np.isnan(m) & ~np.isnan(b)
                win_base = float(np.sum(m[ok] > b[ok])) / float(np.sum(ok)) if ok.any() else np.nan
            else:
                win_base = np.nan
            fr = full_rho.get(method, np.nan)
            frl = full_rho_len.get(method, np.nan)
            sum_rows.append(dict(
                method=method, kind=kind, drop_frac=drop_frac,
                full_data_rho=round(float(fr), 6) if fr is not None and not np.isnan(fr) else np.nan,
                full_data_rho_lenctrl=round(float(frl), 6) if frl is not None and not np.isnan(frl) else np.nan,
                mean_rho=round(float(np.mean(vals)), 6) if len(vals) else np.nan,
                median_rho=round(float(np.median(vals)), 6) if len(vals) else np.nan,
                std_rho=round(float(np.std(vals, ddof=1)), 6) if len(vals) > 1 else np.nan,
                win_rate_top1=round(win_top1, 4) if not np.isnan(win_top1) else np.nan,
                win_rate_vs_base=round(win_base, 4) if not np.isnan(win_base) else np.nan,
                n_seeds=int(len(vals))))
    sum_df = pd.DataFrame(sum_rows)
    sum_df["rank"] = (sum_df.groupby("drop_frac")["mean_rho"]
                      .rank(ascending=False, method="min").astype("Int64"))

    sum_path = out_dir / "R6_robustness_official_summary.csv"
    with open(sum_path, "w", encoding="utf-8") as f:
        f.write("# R6_robustness_official_summary.csv\n")
        f.write("# QuantImmuBench §3.3.4 图3/表9: 子采样鲁棒性汇总 (每 method × drop_frac 一行)\n")
        f.write(f"# DS2; 7 维={used}; max baseline 单工具={baseline_col}\n")
        f.write(f"# full_data_rho=满数据(0%)裸点估计; full_data_rho_lenctrl=满数据控肽长偏相关(B2, ctrl={args.ctrl})\n")
        f.write("# mean/median/std_rho=跨30种子子采样统计(裸)\n")
        f.write("# win_rate_top1=该 fusion 法在多少比例 seed 里为 12 法中第一(大纲 headline 口径)\n")
        f.write("# win_rate_vs_base=该法在多少比例 seed 里 rho>max baseline; rank=该 drop 内按 mean_rho 排名\n")
        sum_df.to_csv(f, index=False)
    print(f"[saved] {sum_path} ({len(sum_df)} 行)")

    for drop_frac in drops:
        d = sum_df[sum_df["drop_frac"] == drop_frac].sort_values(
            "mean_rho", ascending=False).head(6)
        print(f"\n[删 {drop_frac*100:.0f}% top by mean_rho]")
        for _, r in d.iterrows():
            print(f"  {r['method']:<24s} mean={r['mean_rho']:+.4f} "
                  f"med={r['median_rho']:+.4f} full={r['full_data_rho']:+.4f} "
                  f"win_top1={r['win_rate_top1']} rank={r['rank']}")
    print("\n[DONE] R6")


if __name__ == "__main__":
    main()
