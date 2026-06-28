#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
_explore_factors_framework.py
服务: quantimmu-bench benchmark 扩张 v2 E-analysis 窗 § factors 节点 (Spearman 因素分析)
数据源: scripts/out/merged_all_tools_9tools.xlsx (shape ~34247 x 42)
        每行 = (Peptide_ID x Window 滑窗子肽 x HLA_Allele) 组合

6 因素分析 (每个因素 dump 一个 SPEARMAN_FACTORS_<factor>.csv 到 analysis/):
  1. aggregation      — 聚合方式 (max/mean/top3mean) x 工具 x Spearman_rho (DS2)
  2. perpatient       — per-patient vs 全局 rho (DS2, max-agg)
                        -> SPEARMAN_FACTORS_perpatient_global.csv
                        -> SPEARMAN_FACTORS_perpatient_within.csv
  3. length           — 肽长分层: DS1_all / DS2_all / DS2_len8/9/10/11plus (max-agg)
  4. threshold        — 阈值 (>0 / >10 / >median) x AUC_ROC 分类可分性 (DS2, max-agg)
  5. bootstrap        — 肽级 bootstrap Spearman CI (DS2, max-agg, B=2000, seed=42)
  6. toolconsistency  — 工具两两预测分 Spearman rho 热图数据 (DS2, max-agg)

口径备注:
  - HLAthena = MHC-I presentation proxy (预测提呈非免疫原性), ELISpot 上预期近随机
  - 聚合 NaN 处理: 某肽某工具全 NaN -> 记 NaN, 不参与该工具 Spearman
  - Spearman: 连续 Elispot vs 连续工具分 (阈值仅用于 AUC 分类视角, 因素 4)
  - IMPROVE 列名 = MT_IMPROVE_mean_prediction_rf; pTuneos 列名 = MT_pTuneos
  - NOAH/NetCleave/Stab_peptide/TCR_contact 是 IMPROVE 中间特征列, 不是独立工具, 不算

跑法 (主线, 本脚本不自跑):
  python analysis/_explore_factors_framework.py
"""
import os
import sys

import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from sklearn.metrics import roc_auc_score

# ── 路径 ─────────────────────────────────────────────────────────────────────
SD = os.path.dirname(os.path.abspath(__file__))
PROJ = os.path.join(SD, "..")
MERGED_9 = os.path.join(PROJ, "scripts", "out", "merged_all_tools_9tools.xlsx")
OUT_DIR = SD  # SPEARMAN_FACTORS_*.csv 输出到 analysis/

# ── 9 工具显式列映射 (IMPROVE/pTuneos 列名特殊) ───────────────────────────────
# HLAthena = MHC-I presentation proxy; near-random on ELISpot
TOOL_COLS = {
    "DeepImmuno":  "MT_DeepImmuno",
    "PredIG":      "MT_PredIG",
    "NeoTImmuML":  "MT_NeoTImmuML",
    "IMPROVE":     "MT_IMPROVE_mean_prediction_rf",
    "pTuneos":     "MT_pTuneos",
    "PRIME":       "MT_PRIME",
    "ImmuneApp":   "MT_ImmuneApp",
    "deepHLApan":  "MT_deepHLApan",
    "HLAthena":    "MT_HLAthena",  # presentation proxy, NOT immunogenicity
}
PROXY_TOOLS = {"HLAthena"}

# 各 csv 公共注释头
CSV_COMMENT = (
    "# quantimmu-bench E-analysis factors | 口径: Peptide_ID 聚合分 vs Elispot 连续 Spearman\n"
    "# HLAthena = MHC-I presentation proxy (NOT immunogenicity tool); near-random on ELISpot\n"
    "# 聚合 NaN 处理: 某肽某工具全 NaN -> 记 NaN, 不参与该工具 Spearman\n"
)


# ── 工具函数 ──────────────────────────────────────────────────────────────────

def spearman_safe(x, y):
    """安全版 spearmanr: 过滤 NaN、常数列、n<3。返回 (rho, pval, n_valid)."""
    ax = np.asarray(x, dtype=float)
    ay = np.asarray(y, dtype=float)
    mask = ~(np.isnan(ax) | np.isnan(ay))
    xv, yv = ax[mask], ay[mask]
    n = int(mask.sum())
    if n < 3:
        return np.nan, np.nan, n
    if float(np.std(xv)) == 0.0 or float(np.std(yv)) == 0.0:
        return np.nan, np.nan, n
    rho, pval = spearmanr(xv, yv)
    return float(rho), float(pval), n


def agg_scores_series(g, col, agg):
    """对 groupby 对象 g 的 col 列做 agg 聚合，返回 Series(Peptide_ID -> score)。
    pandas groupby .max()/.mean() 默认 skipna=True，全 NaN 组返回 NaN (符合口径)。
    """
    if agg == "max":
        return g[col].max()
    elif agg == "mean":
        return g[col].mean()
    elif agg == "top3mean":
        def _t3(v):
            vd = v.dropna()
            if len(vd) == 0:
                return np.nan
            return float(vd.nlargest(3).mean())
        return g[col].apply(_t3)
    else:
        raise ValueError(f"Unknown agg: {agg}")


def build_per_peptide(df, dataset_filter, agg):
    """
    把子肽行聚合到 Peptide_ID 级别。

    参数:
      df             : 原始宽表 DataFrame (merged_all_tools_9tools.xlsx)
      dataset_filter : 'DS1' / 'DS2' / None (不过滤)
      agg            : 'max' / 'mean' / 'top3mean'

    返回:
      DataFrame, 列:
        Peptide_ID, Patient_ID, Dataset, Peptide_Length, Elispot,
        <工具名> (每个工具一列, 聚合分; 全 NaN 的工具列保持 NaN)
    """
    work = df if dataset_filter is None else df[df["Dataset"] == dataset_filter].copy()
    if work.empty:
        return pd.DataFrame()

    # 结构列: 同 Peptide_ID 内取 first (一致)
    meta = work.groupby("Peptide_ID", sort=False).agg(
        Patient_ID=("Patient_ID", "first"),
        Dataset=("Dataset", "first"),
        Peptide_Length=("Peptide_Length", "first"),
        Elispot=("Elispot", "first"),
    ).reset_index()

    g = work.groupby("Peptide_ID", sort=False)
    for tool_name, col in TOOL_COLS.items():
        if col not in work.columns:
            print(f"    [warn] 缺列 {col} ({tool_name}), 全 NaN")
            meta[tool_name] = np.nan
            continue
        sc = agg_scores_series(g, col, agg)
        sc.name = tool_name
        meta = meta.merge(sc.reset_index(), on="Peptide_ID", how="left")

    return meta


def write_csv(path, df, comment=None):
    """写 csv 到 path, 首部写 comment (# 开头多行注释)。utf-8 编码。"""
    with open(path, "w", encoding="utf-8") as fo:
        if comment:
            fo.write(comment)
        df.to_csv(fo, index=False)
    print(f"    -> saved: {os.path.basename(path)}  shape={df.shape}")


def _r(v):
    """round to 4dp if not NaN, else NaN."""
    return round(float(v), 4) if (v == v) else np.nan


# ── 因素 1: 聚合方式 x Spearman ──────────────────────────────────────────────

def factor1_aggregation(df):
    """DS2, 9 工具 x 3 聚合 (max/mean/top3mean) -> Spearman_rho + pval + n_valid."""
    print("[Factor 1] 聚合方式 x Spearman (DS2, max/mean/top3mean x 9 tools)")
    rows = []
    for agg in ["max", "mean", "top3mean"]:
        pp = build_per_peptide(df, dataset_filter="DS2", agg=agg)
        if pp.empty:
            print(f"    [warn] DS2 empty for agg={agg}")
            continue
        el = pp["Elispot"].values.astype(float)
        for tool_name in TOOL_COLS:
            if tool_name not in pp.columns:
                continue
            sc = pp[tool_name].values.astype(float)
            rho, pval, n = spearman_safe(sc, el)
            rows.append({
                "Tool":          tool_name,
                "Aggregation":   agg,
                "Spearman_rho":  _r(rho),
                "pval":          _r(pval),
                "n_valid":       n,
                "is_proxy":      int(tool_name in PROXY_TOOLS),
            })

    res = pd.DataFrame(rows)
    out_path = os.path.join(OUT_DIR, "SPEARMAN_FACTORS_aggregation.csv")
    write_csv(
        out_path, res,
        comment=CSV_COMMENT +
        "# Factor 1: DS2, 3 种聚合方式 (max/mean/top3mean) x 9 工具 Spearman_rho\n",
    )
    return res


# ── 因素 2: per-patient vs 全局 rho ──────────────────────────────────────────

def factor2_perpatient(df):
    """DS2 + agg=max。全局 rho + per-Patient_ID rho (n_i<4 -> rho_i=NaN)。"""
    print("[Factor 2] per-patient vs 全局 rho (DS2, max)")
    pp = build_per_peptide(df, dataset_filter="DS2", agg="max")
    if pp.empty:
        print("    [warn] DS2 empty")
        return

    el_all = pp["Elispot"].values.astype(float)

    # ---- 2a: 全局 rho ----
    global_rows = []
    for tool_name in TOOL_COLS:
        if tool_name not in pp.columns:
            continue
        sc = pp[tool_name].values.astype(float)
        rho, pval, n = spearman_safe(sc, el_all)
        global_rows.append({
            "Tool":        tool_name,
            "global_rho":  _r(rho),
            "global_pval": _r(pval),
            "global_n":    n,
            "is_proxy":    int(tool_name in PROXY_TOOLS),
        })
    gdf = pd.DataFrame(global_rows)
    p_global = os.path.join(OUT_DIR, "SPEARMAN_FACTORS_perpatient_global.csv")
    write_csv(
        p_global, gdf,
        comment=CSV_COMMENT +
        "# Factor 2a: DS2 max-agg 全局 Spearman_rho (所有肽一起)\n",
    )

    # ---- 2b: per-patient rho ----
    within_rows = []
    for tool_name in TOOL_COLS:
        if tool_name not in pp.columns:
            continue
        for pid, grp in pp.groupby("Patient_ID"):
            # n_i = 两列都非 NaN 的行数
            mask_i = grp["Elispot"].notna() & grp[tool_name].notna()
            n_i = int(mask_i.sum())
            if n_i < 4:
                within_rows.append({
                    "Tool":       tool_name,
                    "Patient_ID": pid,
                    "n_i":        n_i,
                    "rho_i":      np.nan,
                    "pval_i":     np.nan,
                    "is_proxy":   int(tool_name in PROXY_TOOLS),
                })
                continue
            sc_i = grp[tool_name].values.astype(float)
            el_i = grp["Elispot"].values.astype(float)
            rho_i, pval_i, _ = spearman_safe(sc_i, el_i)
            within_rows.append({
                "Tool":       tool_name,
                "Patient_ID": pid,
                "n_i":        n_i,
                "rho_i":      _r(rho_i),
                "pval_i":     _r(pval_i),
                "is_proxy":   int(tool_name in PROXY_TOOLS),
            })
    wdf = pd.DataFrame(within_rows)
    p_within = os.path.join(OUT_DIR, "SPEARMAN_FACTORS_perpatient_within.csv")
    write_csv(
        p_within, wdf,
        comment=CSV_COMMENT +
        "# Factor 2b: DS2 max-agg per-Patient_ID Spearman_rho; n_i<4 -> rho_i=NaN\n",
    )


# ── 因素 3: 肽长分层 ──────────────────────────────────────────────────────────

def _bin_length(l):
    """DS2 整肽长 -> 桶名。DS2 为长肽 (实测 15-29mer, 被滑窗切成 8-14 子肽)。
    按整肽长三分桶: short 15-18 / mid 19-22 / long 23+。
    用于检验「长肽切更多子肽 -> best-binder max 是否系统虚高」假说。"""
    try:
        l = int(l)
    except (TypeError, ValueError):
        return "DS2_len_unknown"
    if l <= 18:
        return "DS2_len15to18"
    elif l <= 22:
        return "DS2_len19to22"
    else:
        return "DS2_len23plus"


def factor3_length(df):
    """DS1_all / DS2_all + DS2 内按 Peptide_Length 桶 Spearman_rho (max-agg, n_valid>=6 才算)."""
    print("[Factor 3] 肽长分层 DS1 vs DS2 (max)")

    # 先打印 Peptide_Length 分布（确认 DS1 是否全 9mer 等）
    for ds in ["DS1", "DS2"]:
        sub = df[df["Dataset"] == ds].drop_duplicates("Peptide_ID")
        dist = sub["Peptide_Length"].value_counts().sort_index()
        total = len(sub)
        print(f"    {ds} Peptide_Length 分布 (n_pep={total}):")
        print("      " + " | ".join(f"len{k}:{v}" for k, v in dist.items()))

    rows = []

    # DS1 整体
    pp_ds1 = build_per_peptide(df, dataset_filter="DS1", agg="max")
    if not pp_ds1.empty:
        el = pp_ds1["Elispot"].values.astype(float)
        for tool_name in TOOL_COLS:
            if tool_name not in pp_ds1.columns:
                continue
            sc = pp_ds1[tool_name].values.astype(float)
            rho, pval, n = spearman_safe(sc, el)
            rows.append({
                "Tool":         tool_name,
                "stratum":      "DS1_all",
                "n":            n,
                "Spearman_rho": _r(rho),
                "pval":         _r(pval),
                "is_proxy":     int(tool_name in PROXY_TOOLS),
            })

    # DS2 整体
    pp_ds2 = build_per_peptide(df, dataset_filter="DS2", agg="max")
    if not pp_ds2.empty:
        el_all = pp_ds2["Elispot"].values.astype(float)
        for tool_name in TOOL_COLS:
            if tool_name not in pp_ds2.columns:
                continue
            sc = pp_ds2[tool_name].values.astype(float)
            rho, pval, n = spearman_safe(sc, el_all)
            rows.append({
                "Tool":         tool_name,
                "stratum":      "DS2_all",
                "n":            n,
                "Spearman_rho": _r(rho),
                "pval":         _r(pval),
                "is_proxy":     int(tool_name in PROXY_TOOLS),
            })

        # DS2 内按 Peptide_Length 分桶 (8/9/10/11+)
        # 用 Peptide_Length = 整肽长 (非 Window_Size)
        pp_ds2 = pp_ds2.copy()
        pp_ds2["_len_bin"] = pp_ds2["Peptide_Length"].apply(
            lambda x: _bin_length(x) if pd.notna(x) else "DS2_len_unknown"
        )
        for bin_name, grp in pp_ds2.groupby("_len_bin"):
            el_b = grp["Elispot"].values.astype(float)
            for tool_name in TOOL_COLS:
                if tool_name not in grp.columns:
                    continue
                sc_b = grp[tool_name].values.astype(float)
                mask_b = ~(np.isnan(sc_b) | np.isnan(el_b))
                n_valid = int(mask_b.sum())
                if n_valid < 6:
                    rows.append({
                        "Tool":         tool_name,
                        "stratum":      bin_name,
                        "n":            n_valid,
                        "Spearman_rho": np.nan,
                        "pval":         np.nan,
                        "is_proxy":     int(tool_name in PROXY_TOOLS),
                    })
                    continue
                rho, pval, n = spearman_safe(sc_b, el_b)
                rows.append({
                    "Tool":         tool_name,
                    "stratum":      bin_name,
                    "n":            n,
                    "Spearman_rho": _r(rho),
                    "pval":         _r(pval),
                    "is_proxy":     int(tool_name in PROXY_TOOLS),
                })

    res = pd.DataFrame(rows)
    out_path = os.path.join(OUT_DIR, "SPEARMAN_FACTORS_length.csv")
    write_csv(
        out_path, res,
        comment=CSV_COMMENT +
        "# Factor 3: 肽长分层 DS1_all / DS2_all / DS2_len8/9/10/11plus\n"
        "# n<6 的桶 Spearman_rho=NaN; Peptide_Length = 整肽长 (非 Window_Size)\n",
    )
    return res


# ── 因素 4: 阈值 x AUC ───────────────────────────────────────────────────────

def _auc_safe(y, s):
    """安全 AUC: 过滤 s 的 NaN, 需 >=2 类。返回 float or NaN."""
    y = np.asarray(y, dtype=float)
    s = np.asarray(s, dtype=float)
    mask = ~np.isnan(s)
    y, s = y[mask], s[mask]
    if len(np.unique(y)) < 2:
        return np.nan
    return float(roc_auc_score(y, s))


def factor4_threshold(df):
    """DS2 + max-agg. 三阈值 (>0 / >10 / >median) -> AUC_ROC + n_pos/n_neg."""
    print("[Factor 4] 阈值 x AUC_ROC (DS2, max)")
    pp = build_per_peptide(df, dataset_filter="DS2", agg="max")
    if pp.empty:
        print("    [warn] DS2 empty")
        return
    el = pp["Elispot"].values.astype(float)
    med = float(np.nanmedian(el))
    thresholds = {">0": 0.0, ">10": 10.0, ">median": med}

    rows = []
    for tool_name in TOOL_COLS:
        if tool_name not in pp.columns:
            continue
        sc = pp[tool_name].values.astype(float)
        for thr_name, thr_val in thresholds.items():
            labs = (el > thr_val).astype(int)
            n_pos = int(labs.sum())
            n_neg = int((labs == 0).sum())
            auc = _auc_safe(labs, sc)
            rows.append({
                "Tool":      tool_name,
                "Threshold": thr_name,
                "n_pos":     n_pos,
                "n_neg":     n_neg,
                "AUC_ROC":   _r(auc),
                "is_proxy":  int(tool_name in PROXY_TOOLS),
            })

    res = pd.DataFrame(rows)
    out_path = os.path.join(OUT_DIR, "SPEARMAN_FACTORS_threshold.csv")
    write_csv(
        out_path, res,
        comment=CSV_COMMENT +
        f"# Factor 4: DS2 max-agg x 三阈值 (>0 / >10 / >median={med:.2f}) x AUC_ROC\n"
        "# 注: Spearman 不受阈值影响; 此因素看分类可分性随阈值的变化\n",
    )
    return res


# ── 因素 5: Bootstrap rho 稳定性 ─────────────────────────────────────────────

def factor5_bootstrap(df, n_boot=2000, seed=42):
    """DS2 + max-agg, B=2000 boots, seed=42. 肽级有放回重抽 -> rho CI (2.5/97.5)."""
    print(f"[Factor 5] Bootstrap rho 稳定性 (DS2, max, B={n_boot}, seed={seed})")
    pp = build_per_peptide(df, dataset_filter="DS2", agg="max")
    if pp.empty:
        print("    [warn] DS2 empty")
        return
    rng = np.random.default_rng(seed)
    el_all = pp["Elispot"].values.astype(float)

    rows = []
    for tool_name in TOOL_COLS:
        if tool_name not in pp.columns:
            continue
        sc = pp[tool_name].values.astype(float)
        rho_pt, _, n_valid = spearman_safe(sc, el_all)

        # 仅在两列都非 NaN 的肽上 bootstrap
        valid_idx = np.where(~(np.isnan(sc) | np.isnan(el_all)))[0]
        n_v = len(valid_idx)
        if n_v < 3:
            rows.append({
                "Tool":            tool_name,
                "rho_point":       _r(rho_pt),
                "rho_median_boot": np.nan,
                "ci_low":          np.nan,
                "ci_high":         np.nan,
                "rho_std_boot":    np.nan,
                "n_valid":         n_v,
                "is_proxy":        int(tool_name in PROXY_TOOLS),
            })
            continue

        sc_v = sc[valid_idx]
        el_v = el_all[valid_idx]
        boots = []
        for _ in range(n_boot):
            idx = rng.integers(0, n_v, n_v)
            sb, eb = sc_v[idx], el_v[idx]
            if float(np.std(sb)) == 0.0 or float(np.std(eb)) == 0.0:
                continue
            rho_b, _ = spearmanr(sb, eb)
            boots.append(float(rho_b))

        if len(boots) < 10:
            rows.append({
                "Tool":            tool_name,
                "rho_point":       _r(rho_pt),
                "rho_median_boot": np.nan,
                "ci_low":          np.nan,
                "ci_high":         np.nan,
                "rho_std_boot":    np.nan,
                "n_valid":         n_valid,
                "is_proxy":        int(tool_name in PROXY_TOOLS),
            })
            continue

        boots = np.array(boots)
        ci_lo, ci_hi = np.percentile(boots, [2.5, 97.5])
        rows.append({
            "Tool":            tool_name,
            "rho_point":       _r(rho_pt),
            "rho_median_boot": _r(float(np.median(boots))),
            "ci_low":          _r(float(ci_lo)),
            "ci_high":         _r(float(ci_hi)),
            "rho_std_boot":    _r(float(np.std(boots))),
            "n_valid":         n_valid,
            "is_proxy":        int(tool_name in PROXY_TOOLS),
        })

    res = pd.DataFrame(rows)
    out_path = os.path.join(OUT_DIR, "SPEARMAN_FACTORS_bootstrap.csv")
    write_csv(
        out_path, res,
        comment=CSV_COMMENT +
        f"# Factor 5: DS2 max-agg 肽级 bootstrap Spearman CI (B={n_boot}, seed={seed})\n"
        "# ci_low/ci_high = 2.5/97.5 百分位; CI 跨 0 = 该工具 rho 在此样本量下不稳\n",
    )
    return res


# ── 因素 6: 工具间一致性 (热图数据) ──────────────────────────────────────────

def factor6_toolconsistency(df):
    """DS2 + max-agg. 9 工具两两预测分 Spearman rho -> 长表 (可 pivot 成 9x9 热图)."""
    print("[Factor 6] 工具间 Spearman rho 热图数据 (DS2, max)")
    pp = build_per_peptide(df, dataset_filter="DS2", agg="max")
    if pp.empty:
        print("    [warn] DS2 empty")
        return
    tools = [t for t in TOOL_COLS if t in pp.columns]

    rows = []
    for i, ta in enumerate(tools):
        for j, tb in enumerate(tools):
            if j <= i:
                continue  # 上三角, 避免重复 + 自身对
            sa = pp[ta].values.astype(float)
            sb = pp[tb].values.astype(float)
            mask = ~(np.isnan(sa) | np.isnan(sb))
            n_common = int(mask.sum())
            if n_common < 3:
                rows.append({
                    "Tool_A":      ta,
                    "Tool_B":      tb,
                    "Spearman_rho": np.nan,
                    "pval":        np.nan,
                    "n_common":    n_common,
                })
                continue
            rho, pval = spearmanr(sa[mask], sb[mask])
            rows.append({
                "Tool_A":      ta,
                "Tool_B":      tb,
                "Spearman_rho": _r(float(rho)),
                "pval":        _r(float(pval)),
                "n_common":    n_common,
            })

    res = pd.DataFrame(rows)
    out_path = os.path.join(OUT_DIR, "SPEARMAN_FACTORS_toolconsistency.csv")
    write_csv(
        out_path, res,
        comment=CSV_COMMENT +
        "# Factor 6: DS2 max-agg 工具两两预测分 Spearman rho (仅两工具都非 NaN 的肽)\n"
        "# pivot Tool_A x Tool_B 得 9x9 热图; 高 rho = 预测方向相似/冗余\n",
    )
    return res


# ── main ─────────────────────────────────────────────────────────────────────

def main():
    # 数据源检查
    if not os.path.exists(MERGED_9):
        print(f"[ERR] 找不到数据源: {MERGED_9}", file=sys.stderr)
        sys.exit(1)

    print("=== _explore_factors_framework.py: 加载 9tools xlsx ===")
    df = pd.read_excel(MERGED_9, engine="openpyxl")
    print(f"  loaded: shape={df.shape}")

    # 列完整性检查
    missing_cols = []
    for tool_name, col in TOOL_COLS.items():
        if col not in df.columns:
            missing_cols.append(f"{tool_name}({col})")
    if missing_cols:
        print(f"  [warn] 以下工具列不在 xlsx 中, 将全 NaN: {missing_cols}")

    # 检查疑似 DTU 工具列 (netMHCpan 直接输出, 非 IMPROVE 主路)
    for c in df.columns:
        if "netMHCpan" in c and c not in TOOL_COLS.values():
            print(f"  [pending-DTU] 疑似 DTU 工具列 {c}, 本框架跳过, 需人工确认")

    # 数据集分布
    if "Dataset" in df.columns:
        print(f"  Dataset 分布: {df['Dataset'].value_counts().to_dict()}")
    else:
        print("  [warn] 无 Dataset 列, 部分因素将无法按 DS1/DS2 分层")

    print()

    # ---- 6 因素顺序执行 ----
    factor1_aggregation(df)
    print()

    factor2_perpatient(df)
    print()

    factor3_length(df)
    print()

    factor4_threshold(df)
    print()

    factor5_bootstrap(df, n_boot=2000, seed=42)
    print()

    factor6_toolconsistency(df)

    print()
    print("=== 全部因素 csv 已 dump 到 analysis/ ===")
    print("  SPEARMAN_FACTORS_aggregation.csv")
    print("  SPEARMAN_FACTORS_perpatient_global.csv")
    print("  SPEARMAN_FACTORS_perpatient_within.csv")
    print("  SPEARMAN_FACTORS_length.csv")
    print("  SPEARMAN_FACTORS_threshold.csv")
    print("  SPEARMAN_FACTORS_bootstrap.csv")
    print("  SPEARMAN_FACTORS_toolconsistency.csv")


if __name__ == "__main__":
    main()
