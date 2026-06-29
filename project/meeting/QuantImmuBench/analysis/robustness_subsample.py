#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
robustness_subsample.py
=======================
服务: QuantImmuBench § G3 §3.3.4 + G4 lever (子采样删突变鲁棒性 —— 论文核心图 3)
对应大纲: §2.6 Evaluation/Robustness + §3.3.4 (图 3 / 表 9), 附录 A robustness_subsample.py

定位:
  大纲三大核心图之一「图 3 fusion 鲁棒性」目前 0 csv 支撑 (GAP_ROADMAP §3.3.4:「最关键的
  声称未坐实缺口」)。本脚本生成图 3 / 表 9 的底层数据: 在主分析集 DS2 上, 病人内随机删
  10%/20% 突变 × 30 个固定种子, 对每种 fusion (及单工具 max 对照) 重算 per-patient
  Spearman 主指标, 跨种子聚合 子采样均值 / 中位 / 胜率, 检验「点估计 vs 鲁棒性」。

  ★ 直接 import analysis/fusion_12methods.py 的 API, 不重造 fusion / 主指标:
      apply_fusion / per_patient_spearman / METHOD_ORDER / DIM_SETS
    口径与 fusion_12methods.csv / fusion_study.csv 逐位可比。

════════════════════════════════════════════════════════════════════════════════
权威规格来源 (按真源排序, 不臆造)
════════════════════════════════════════════════════════════════════════════════
  1. reference/EXPERIMENT_MATRIX_three_checks.md 实验 3 (planner 定稿, 派单依据):
       「每 seed 病人内随机删 10%/20% 突变 (保每病人 >=min_pep=4) -> 重跑全 12 fusion
         per-patient LOPO -> 跨 30 seed 聚合 (子采样均值/中位/胜率)。
        网格: 删比例 {0%对照,10%,20%} × 12 法 × 30 seed (0..29 固定列出)。」
  2. paper/QuanImmu-Paper-Outline.md §3.3.4 (袁老师定稿权威框架):
       「图 3 / 表 9: 7 维 × fusion 的子采样均值 —— geomean 在 10%(+0.4643) 与
        20%(+0.4488) 双双第一; max 满数据虚高(+0.4834)但子采样塌陷 (点估计陷阱)。」
       => 主维度集 = 7 维 (DIM7 = SURV6 + pool_netAffneg_top20)。

  ⚠️ 大纲声称值 (geomean 10% +0.4643 / 20% +0.4488 / max 满数据 +0.4834) 全为大纲
     声称、本地 0 csv 支撑。本脚本如实输出实测; 若不复现, 诚实呈现, 不调参凑数
     (headline 是否成立 = 拍板点, 不在本脚本内硬凑)。

════════════════════════════════════════════════════════════════════════════════
口径决策 (查到的照真源, 查不到的标 [TODO] 给合理默认 + 注释)
════════════════════════════════════════════════════════════════════════════════
  · 删突变口径 = 病人内随机删 (per-patient)。真源: 实验矩阵实验 3 明文「病人内随机删」,
    大纲 §3.3.4「删 10%/20% 突变」未细分但允许按病人。每病人独立按 drop_frac 抽样删,
    并强制保底 keep >= min_pep(=4) (实验矩阵明文)。★ 只删整行 (突变), 绝不碰标签列。
  · 主维度集 = 7 维 (DIM7), 大纲 §3.3.4 图 3 明文「7 维 × fusion」。--ndim 可改。
  · 种子 = 0..29 共 30 个固定种子 (实验矩阵明文); 每 (drop_frac, seed) 用独立可复现
    SeedSequence([seed, int(drop_frac*1000)]) -> 10%/20% 抽样互相独立且 bit 可复现。
  · 0% 对照 = 满数据单次确定性跑 (seed=-1), 用于「满数据虚高 vs 子采样均值」对照。
  · max baseline 单工具对照: 任务要求加单工具 max 对照。本实现把 7 维各维列本身当
    「单工具 max-pool 分」(model_matrix 各列已是突变级分), 全部作为 single::<col> 行
    一并子采样, 供 writer 任选; 指定「max baseline」= 满数据 rho 最高的单工具 (在 0%
    对照上确定性选出, 跨种子固定 -> 避免逐种子 selection-on-test)。--baseline-col 可覆盖。
  · 胜率 (winrate) [部分 TODO 定义: 大纲/实验矩阵只写「胜率」未给确切式]: 本实现给两口径:
      - win_rate_top1   : 在该 drop_frac 下, 该 fusion 法在多少比例 seed 里 rho 为
                          12 fusion 法中最大 (= 大纲「geomean 双双第一」直接对应)。
      - win_rate_vs_base: 该法在多少比例 seed 里 rho > max baseline 单工具 (同种子配对)。
    主口径 = win_rate_top1 (对应大纲 headline)。

Windows 规范: UTF-8 stdout, 纯 numpy/pandas (禁 scipy, 防 OMP Error #15), 零 GPU,
            pathlib 路径, np.random.default_rng (可复现)。

输入:  quantimmune/model_matrix_v2.csv (E0 产物, 183 行)
输出 (analysis/):
  robustness_subsample_results.csv  —— 长表: method, kind, drop_frac, seed, fisherz_rho, n_pat
  robustness_subsample_summary.csv  —— 每 (method, drop_frac): full_data_rho / mean_rho /
                                       median_rho / std_rho / win_rate_top1 / win_rate_vs_base /
                                       rank / n_seeds

跑法 (主线跑, 我不跑):
  python analysis/robustness_subsample.py
  python analysis/robustness_subsample.py --ndim 7 --seeds 0-29 --drop 0.10,0.20
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

# ── 复用 fusion_12methods 的 fusion 引擎 + 主指标 (不重造) ──────────────────────
sys.path.insert(0, str(HERE))
from fusion_12methods import (                    # noqa: E402
    apply_fusion,
    per_patient_spearman,
    METHOD_ORDER,
    DIM_SETS,
)
from fusion_study import (                        # noqa: E402
    MIN_PEP,
    DS2_PATIENTS,
)

DEFAULT_MATRIX = ROOT / "quantimmune" / "model_matrix_v2.csv"
DEFAULT_SEEDS = list(range(30))                   # 0..29 固定 (实验矩阵实验 3)
DEFAULT_DROPS = [0.10, 0.20]                      # 大纲 §3.3.4 删 10% / 20%
DEFAULT_NDIM = 7                                  # 大纲图 3 = 7 维 × fusion


# ═══════════════════════════════════════════════════════════════════════════════
# 病人内随机删突变 (per-patient subsample) —— 只删整行, 绝不碰标签
# ═══════════════════════════════════════════════════════════════════════════════

def subsample_per_patient(df: pd.DataFrame, patients: list, drop_frac: float,
                          seed: int, min_pep: int) -> pd.DataFrame:
    """每病人独立随机删 drop_frac 比例突变, 强制保底 keep >= min_pep。

    真源: EXPERIMENT_MATRIX_three_checks.md 实验 3「病人内随机删 ... 保每病人 >=min_pep=4」。
    ★ 仅丢弃整行 (突变), 保留行的全部列含标签列 Elispot 原样 -> 不碰标签 (leak-free)。

    参数:
      patients : 参与的病人 ID list (其余病人原样保留, 不在主分析聚合内即可)。
      drop_frac: 删除比例 (0=满数据)。
      seed     : 种子; 与 drop_frac 组合成独立可复现 SeedSequence。
    返回: 子采样后的 df (行子集, 列不变, index 保持原值)。
    """
    if drop_frac <= 0:
        return df.copy()

    # 每 (drop_frac, seed) 独立且 bit 可复现; int(drop_frac*1000) 区分 10%/20%
    rng = np.random.default_rng([int(seed), int(round(drop_frac * 1000))])

    keep_index = []
    for pat in sorted(patients):
        idx = df.index[df["Patient_ID"] == pat].to_numpy()
        n = len(idx)
        if n == 0:
            continue
        n_drop = int(round(n * drop_frac))
        n_keep = n - n_drop
        if n_keep < min_pep:                      # 保底: 每病人 >= min_pep (实验矩阵明文)
            n_keep = min(min_pep, n)
        if n_keep >= n:
            keep_index.extend(idx.tolist())
            continue
        perm = rng.permutation(idx)
        keep_index.extend(perm[:n_keep].tolist())

    # 不在 patients 内的病人行原样保留 (apply_fusion 只按 patients 聚合, 保留无害且口径透明)
    other_idx = df.index[~df["Patient_ID"].isin(patients)].to_numpy()
    keep_index.extend(other_idx.tolist())
    return df.loc[sorted(set(keep_index))].copy()


# ═══════════════════════════════════════════════════════════════════════════════
# 单次评测: 给定 (子采样 df, method/kind) -> (rho, n_pat)
# ═══════════════════════════════════════════════════════════════════════════════

def _eval_fusion(sub_df, dim_cols, method, patients, seed, min_pep):
    """fusion 法: apply_fusion -> per_patient_spearman。"""
    s = apply_fusion(sub_df, dim_cols, method, patients=patients,
                     seed=seed, min_pep=min_pep)
    rho, _, _, n_used = per_patient_spearman(
        sub_df, s, patients=patients, min_pep=min_pep)
    return rho, n_used


def _eval_single(sub_df, col, patients, min_pep):
    """单工具对照: 直接用该维列 (已是突变级分) 算 per-patient Spearman。"""
    if col not in sub_df.columns:
        return np.nan, 0
    rho, _, _, n_used = per_patient_spearman(
        sub_df, col, patients=patients, min_pep=min_pep)
    return rho, n_used


# ═══════════════════════════════════════════════════════════════════════════════
# 主程序
# ═══════════════════════════════════════════════════════════════════════════════

def _parse_seeds(spec: str) -> list:
    """'0-29' / '0,1,2' / '0-9,15,20-22' -> sorted unique int list。"""
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
        description="robustness_subsample.py — QuantImmuBench §3.3.4 图 3 子采样鲁棒性")
    ap.add_argument("--matrix", default=str(DEFAULT_MATRIX),
                    help="model_matrix_v2.csv 路径")
    ap.add_argument("--ndim", type=int, default=DEFAULT_NDIM,
                    choices=sorted(DIM_SETS.keys()),
                    help=f"主维度集 (默认 {DEFAULT_NDIM}, 大纲图 3 = 7 维)")
    ap.add_argument("--seeds", default="0-29",
                    help="种子列表 (默认 0-29 共 30 个, 实验矩阵实验 3)")
    ap.add_argument("--drop", default="0.10,0.20",
                    help="删除比例列表 (默认 0.10,0.20; 0% 对照自动加)")
    ap.add_argument("--min_pep", type=int, default=MIN_PEP,
                    help=f"病人内保底/聚合最少肽数 (默认 {MIN_PEP})")
    ap.add_argument("--baseline_col", default=None,
                    help="指定 max baseline 单工具列; 默认=满数据 rho 最高单工具")
    args = ap.parse_args()

    matrix_path = Path(args.matrix)
    if not matrix_path.exists():
        sys.exit(f"[ERR] model_matrix 不存在: {matrix_path}")
    df = pd.read_csv(matrix_path, encoding="utf-8")
    print(f"[info] matrix: {df.shape}, 病人={df['Patient_ID'].nunique()}")

    # 主分析集 DS2
    patients = sorted([p for p in DS2_PATIENTS if p in df["Patient_ID"].unique()])
    print(f"[info] DS2 主分析病人 = {patients} (n={len(patients)})")

    # 维度集 (剔除缺失列 + warn, 与 fusion_12methods 同协议)
    dim_cols_all = DIM_SETS[args.ndim]
    dim_cols = [c for c in dim_cols_all if c in df.columns]
    miss = [c for c in dim_cols_all if c not in df.columns]
    if miss:
        print(f"[warn] {args.ndim} 维缺失列已剔除: {miss}")
    print(f"[info] {args.ndim} 维 fusion 维度 = {dim_cols}")

    seeds = _parse_seeds(args.seeds)
    drops = sorted({round(float(x), 4) for x in args.drop.split(",")})
    print(f"[info] seeds = {len(seeds)} 个 ({seeds[0]}..{seeds[-1]}); drop_frac = {drops}")

    fusion_methods = list(METHOD_ORDER)            # 12 法
    single_cols = list(dim_cols)                    # 单工具对照 = 各维列

    # ── 网格规模回报 ──────────────────────────────────────────────────────────
    n_methods = len(fusion_methods) + len(single_cols)
    n_sub = len(drops) * len(seeds) * n_methods
    n_full = n_methods                              # 0% 对照单次
    print(f"[info] 网格: {len(fusion_methods)} fusion + {len(single_cols)} single = "
          f"{n_methods} 法 × {len(drops)} drop × {len(seeds)} seed = {n_sub} 子采样评测 "
          f"+ {n_full} 满数据对照 = {n_sub + n_full} 次")

    rows = []

    def _rho_of(method, kind, sub_df, seed):
        if kind == "fusion":
            return _eval_fusion(sub_df, dim_cols, method, patients, seed, args.min_pep)
        return _eval_single(sub_df, method, patients, args.min_pep)

    # ── (a) 0% 满数据对照 (确定性, seed=-1) ────────────────────────────────────
    full_rho = {}   # method -> 满数据 rho (供 summary 对照 + 选 baseline)
    print("\n[0% 满数据对照]")
    for method in fusion_methods:
        rho, n = _rho_of(method, "fusion", df, 42)
        full_rho[method] = rho
        rows.append(dict(method=method, kind="fusion", drop_frac=0.0,
                         seed=-1, fisherz_rho=rho, n_pat=n))
    for col in single_cols:
        rho, n = _rho_of(col, "single", df, 42)
        full_rho[col] = rho
        rows.append(dict(method=col, kind="single", drop_frac=0.0,
                         seed=-1, fisherz_rho=rho, n_pat=n))

    # 指定 max baseline 单工具 = 满数据 rho 最高单工具 (确定性, 跨种子固定)
    if args.baseline_col and args.baseline_col in single_cols:
        baseline_col = args.baseline_col
    else:
        valid_single = {c: full_rho[c] for c in single_cols
                        if full_rho[c] is not None and not np.isnan(full_rho[c])}
        baseline_col = max(valid_single, key=valid_single.get) if valid_single else None
    print(f"[info] max baseline 单工具 = {baseline_col} "
          f"(满数据 rho={full_rho.get(baseline_col, float('nan')):+.4f})")

    # ── (b) 子采样 (drop_frac × seed) ──────────────────────────────────────────
    for drop_frac in drops:
        print(f"\n[删 {drop_frac*100:.0f}%] {len(seeds)} seed ...")
        for seed in seeds:
            sub_df = subsample_per_patient(df, patients, drop_frac, seed, args.min_pep)
            for method in fusion_methods:
                rho, n = _rho_of(method, "fusion", sub_df, seed)
                rows.append(dict(method=method, kind="fusion", drop_frac=drop_frac,
                                 seed=seed, fisherz_rho=rho, n_pat=n))
            for col in single_cols:
                rho, n = _rho_of(col, "single", sub_df, seed)
                rows.append(dict(method=col, kind="single", drop_frac=drop_frac,
                                 seed=seed, fisherz_rho=rho, n_pat=n))

    long_df = pd.DataFrame(rows)

    # ── 写长表 ────────────────────────────────────────────────────────────────
    res_path = HERE / "robustness_subsample_results.csv"
    with open(res_path, "w", encoding="utf-8") as f:
        f.write("# robustness_subsample_results.csv\n")
        f.write("# QuantImmuBench §3.3.4 图 3: 病人内随机删突变子采样鲁棒性 (长表)\n")
        f.write(f"# 主分析集 DS2 病人={patients}; 维度集={args.ndim} 维 {dim_cols}\n")
        f.write("# kind=fusion(12 法)/single(单工具对照=各维列); drop_frac=删除比例(0=满数据)\n")
        f.write("# seed=-1 表 0% 满数据确定性对照; 子采样 seed=0..29; fisherz_rho=DS2 per-patient Fisher-z 加权 rho\n")
        f.write("# 病人内随机删, 保每病人>=min_pep; 只删整行不碰标签\n")
        long_df.to_csv(f, index=False)
    print(f"\n[saved] {res_path}  ({len(long_df)} 行)")

    # ── 汇总 summary (每 method × drop_frac 一行, 仅子采样 drop_frac) ───────────
    def _safe(arr):
        a = np.asarray(arr, dtype=float)
        return a[~np.isnan(a)]

    sum_rows = []
    for drop_frac in drops:
        sub = long_df[(long_df["drop_frac"] == drop_frac)]
        # 逐种子: fusion top1 表 (用于 win_rate_top1) + baseline rho (用于 vs_base)
        fus = sub[sub["kind"] == "fusion"]
        # 每 seed fusion 法 rho 宽表
        piv = fus.pivot_table(index="seed", columns="method",
                              values="fisherz_rho", aggfunc="first")
        # 每 seed top1 法 (在有效值中取最大)
        top1_per_seed = piv.idxmax(axis=1, skipna=True)   # Series: seed -> 法名
        n_seed_valid_top1 = top1_per_seed.notna().sum()
        # baseline 每 seed rho
        if baseline_col is not None:
            base = sub[(sub["method"] == baseline_col)].set_index("seed")["fisherz_rho"]
        else:
            base = pd.Series(dtype=float)

        for method in fusion_methods + single_cols:
            kind = "fusion" if method in fusion_methods else "single"
            mser = sub[sub["method"] == method].set_index("seed")["fisherz_rho"]
            vals = _safe(mser.values)

            # win_rate_top1: 仅 fusion (大纲 headline = fusion 中第一)
            if kind == "fusion" and n_seed_valid_top1 > 0:
                wins_top1 = (top1_per_seed == method).sum()
                win_top1 = float(wins_top1) / float(n_seed_valid_top1)
            else:
                win_top1 = np.nan

            # win_rate_vs_base: 同种子配对, method rho > baseline rho
            if baseline_col is not None and method != baseline_col and len(base) > 0:
                common = mser.index.intersection(base.index)
                m = mser.reindex(common).values.astype(float)
                b = base.reindex(common).values.astype(float)
                ok = ~np.isnan(m) & ~np.isnan(b)
                win_base = float(np.sum(m[ok] > b[ok])) / float(np.sum(ok)) if ok.any() else np.nan
            else:
                win_base = np.nan

            sum_rows.append(dict(
                method=method, kind=kind, drop_frac=drop_frac,
                full_data_rho=round(float(full_rho.get(method, np.nan)), 6)
                if not np.isnan(full_rho.get(method, np.nan)) else np.nan,
                mean_rho=round(float(np.mean(vals)), 6) if len(vals) else np.nan,
                median_rho=round(float(np.median(vals)), 6) if len(vals) else np.nan,
                std_rho=round(float(np.std(vals, ddof=1)), 6) if len(vals) > 1 else np.nan,
                win_rate_top1=round(win_top1, 4) if not np.isnan(win_top1) else np.nan,
                win_rate_vs_base=round(win_base, 4) if not np.isnan(win_base) else np.nan,
                n_seeds=int(len(vals)),
            ))

    sum_df = pd.DataFrame(sum_rows)
    # rank: 每 drop_frac 内按 mean_rho 降序 (1=最高)
    sum_df["rank"] = (
        sum_df.groupby("drop_frac")["mean_rho"]
        .rank(ascending=False, method="min")
        .astype("Int64")
    )

    sum_path = HERE / "robustness_subsample_summary.csv"
    with open(sum_path, "w", encoding="utf-8") as f:
        f.write("# robustness_subsample_summary.csv\n")
        f.write("# QuantImmuBench §3.3.4 图 3: 子采样鲁棒性汇总 (每 method × drop_frac 一行)\n")
        f.write(f"# 主分析集 DS2; 维度集={args.ndim} 维; max baseline 单工具={baseline_col}\n")
        f.write("# full_data_rho=满数据(0%)点估计; mean/median/std_rho=跨种子子采样统计\n")
        f.write("# win_rate_top1=该 fusion 法在多少比例 seed 里为 12 fusion 中第一 (大纲 headline 口径)\n")
        f.write("# win_rate_vs_base=该法在多少比例 seed 里 rho>max baseline 单工具 (配对); rank=该 drop_frac 内按 mean_rho 排名\n")
        sum_df.to_csv(f, index=False)
    print(f"[saved] {sum_path}  ({len(sum_df)} 行)")

    # ── 控制台速览: 各 drop_frac top-5 by mean_rho ──────────────────────────────
    for drop_frac in drops:
        d = sum_df[sum_df["drop_frac"] == drop_frac].sort_values(
            "mean_rho", ascending=False).head(6)
        print(f"\n[删 {drop_frac*100:.0f}% top by mean_rho]")
        for _, r in d.iterrows():
            print(f"  {r['method']:<24s} mean={r['mean_rho']:+.4f} "
                  f"med={r['median_rho']:+.4f} full={r['full_data_rho']:+.4f} "
                  f"win_top1={r['win_rate_top1']} rank={r['rank']}")
    print("\n[DONE]")


if __name__ == "__main__":
    main()
