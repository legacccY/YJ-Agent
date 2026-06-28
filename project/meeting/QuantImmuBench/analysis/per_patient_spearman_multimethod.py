#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
per_patient_spearman_multimethod.py
服务: quantimmu-bench / DS2 per-patient Spearman 多聚合方法

================== 输入 ==================
  scripts/out/merged_all_tools_9tools.xlsx  (优先; 不存在退 _8tools.xlsx)
  子肽×HLA 行; 工具列自动检测所有 MT_* 开头列; 真值列 Elispot; 患者 Patient_ID
  只在 DS2 子集运算 (Dataset == 'DS2'; DS1 全阳无患者分组, 不参与 per-patient)

================== 算法 (每工具) ==================
  1. 子肽×HLA -> 肽级单分: groupby(Peptide_ID).agg(sub_agg), 默认 max
     (工具分数越高越免疫原, 无需翻转)
  2. 每患者内 spearman_np(peptide_score, Elispot), >=3 肽才算, 得 rho_i + n_i
  3. 全局对照 rho_global (全 DS2 肽放一起)
  4. 7 种聚合 (严格按 reference/AGGREGATION_METHODS.md):
       Fisher-z 固定效应加权  [主报, rho=±1 clip ±0.9999; n<=3 剔出加权]
       中位数                 [主报, 稳健]
       简单均值               [次报, 描述性]
       Hunter-Schmidt 加权    [次报, sum(n*rho)/sum(n)]
       几何均值 via v=(1+rho)/2  [次报, 描述性, 无 CI]
       幂平均 M2 (RMS) via v     [次报, 描述性, 无 CI]
       UWLS+3 (Stanley-Doucouliagos 2025, df=n+1 偏差校正; TODO 精确公式)
  5. 跨患者分布: min / max / std(rho_i)

================== 输出 ==================
  analysis/per_patient_spearman_<NN>tools.csv
    每工具一行; 列: Tool, n_patients, rho_global, fisherz_weighted,
      fisherz_ci_lo, fisherz_ci_hi, fisherz_n_used, fisherz_n_dropped,
      median, simple_mean, hs_weighted, geometric_mean, power_mean_p2,
      uwls3, rho_min, rho_max, rho_std,
      rho_p101..rho_p110, n_p101..n_p110
  stdout: 每工具摘要 + 全局 vs Fisher-z 差值

================== 统计警告 ==================
  1. n_i=6-16 -> 单 rho_i 95%CI 约 ±0.6-0.7; 聚合 CI 仍很宽, 不可过度解读。
  2. K=9 -> 不用随机效应 (tau^2 估计 K<10 不稳; BMC Med Res Methodol 2015)。
  3. 几何/幂平均经 (1+rho)/2 变换, 描述性非推断, 不构造 CI。
  4. 主结论以 Fisher-z 加权 + 中位数为准; 其余作探索/敏感性对照。
  5. UWLS+3: TODO 精确公式待核 Stanley-Doucouliagos 2025 (PMC12631149)。

================== 跑法 ==================
  python analysis/per_patient_spearman_multimethod.py
  python analysis/per_patient_spearman_multimethod.py --input scripts/out/merged_all_tools_9tools.xlsx
  python analysis/per_patient_spearman_multimethod.py --sub_agg mean  # 子肽聚合用 mean
  python analysis/per_patient_spearman_multimethod.py --min_pep 4     # 患者内最少肽数
"""

import sys
import argparse
from pathlib import Path

import numpy as np
import pandas as pd

# UTF-8 stdout (Windows 必要)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent

# ── 常量 ─────────────────────────────────────────────────────────────────────
PATIENT_COL_CANDIDATES = ["Patient_ID", "Patient", "PatientID", "patient_id",
                           "Subject", "Sample_ID"]
MIN_PEP_DEFAULT = 3       # 患者内算 Spearman 的最少肽数
FISHER_CLIP = 0.9999      # rho=±1 → arctanh(±inf); clip 到此
FISHER_MIN_N = 3          # n<=3 → Var 分母 n-3<=0; 剔出 Fisher-z 加权

# DS2 中 9 个患者 (101~110, 无 103)
ALL_PATIENTS = [101, 102, 104, 105, 106, 107, 108, 109, 110]


# ── 纯 numpy Spearman (复用 patient_strat_check.py, 禁 scipy 防 OMP Error #15) ──
def spearman_np(x, y):
    """纯 numpy Spearman (rank Pearson), 避免 scipy.stats 与 torch 抢 OpenMP。"""
    x = np.asarray(x, float)
    y = np.asarray(y, float)
    m = ~(np.isnan(x) | np.isnan(y))
    x, y = x[m], y[m]
    n = len(x)
    if n < 3 or len(np.unique(x)) < 2 or len(np.unique(y)) < 2:
        return np.nan
    rx = pd.Series(x).rank().values
    ry = pd.Series(y).rank().values
    rx -= rx.mean()
    ry -= ry.mean()
    denom = np.sqrt((rx ** 2).sum() * (ry ** 2).sum())
    if denom == 0:
        return np.nan
    return float((rx * ry).sum() / denom)


# ── Patient_ID 工具 (复用 patient_strat_check.py) ────────────────────────────
def find_patient_col(df):
    """按候选列名依序查找患者列, 返回首个命中列名或 None。"""
    for c in PATIENT_COL_CANDIDATES:
        if c in df.columns:
            return c
    return None


def patient_from_peptide_id(pid):
    """从 '16097-101-10' 形式 Peptide_ID 反解患者号字符串 -> '101'。"""
    if not isinstance(pid, str):
        return None
    parts = pid.split("-")
    return parts[1] if len(parts) >= 3 else None


# ── 子肽聚合辅助 ──────────────────────────────────────────────────────────────
def _agg_array(arr, method):
    """子肽分数数组 → 肽级标量; method in {max, mean, top3mean}。
    返回 round(8) 消除多 tie 工具求和顺序浮点噪声 (H 窗 POOLING_STUDY §4 反哺,
    pTuneos 等 83 tie 工具 ~1e-16 浮点经 Spearman tie-break 放大成 0.005 级 rho 漂移)。"""
    arr = np.asarray(arr, float)
    arr = arr[~np.isnan(arr)]
    if len(arr) == 0:
        return np.nan
    if method == "max":
        return round(float(arr.max()), 8)
    if method == "mean":
        return round(float(arr.mean()), 8)
    if method == "top3mean":
        k = min(3, len(arr))
        return round(float(np.sort(arr)[-k:].mean()), 8)
    raise ValueError(f"未知 sub_agg 方法: {method}")


# ── 7 种聚合方法 (严格按 AGGREGATION_METHODS.md) ─────────────────────────────

def fisherz_weighted(rhos, ns):
    """
    Fisher-z 固定效应加权均值 + 95% CI (主报方法).
    Spearman 专用方差: Var(z_i) = (1 + rho_i^2/2) / (n_i - 3)
    [Fieller-Hartley-Pearson 1957, Biometrika 44:470]
    rho=±1 → clip ±FISHER_CLIP; n_i<=3 → Var 分母<=0, 剔出并记录。
    返回: (rho_bar, ci_lo, ci_hi, n_used, n_dropped)
    """
    rhos = np.asarray(rhos, float)
    ns = np.asarray(ns, float)

    # 过滤 NaN
    valid = ~np.isnan(rhos)
    rhos, ns = rhos[valid], ns[valid]

    # 剔出 n<=FISHER_MIN_N (Var 分母 n-3 <= 0)
    keep = ns > FISHER_MIN_N
    n_dropped = int((~keep).sum())
    rhos_k, ns_k = rhos[keep], ns[keep]

    if len(rhos_k) == 0:
        return np.nan, np.nan, np.nan, 0, n_dropped

    # clip rho=±1
    rhos_k = np.clip(rhos_k, -FISHER_CLIP, FISHER_CLIP)

    z = np.arctanh(rhos_k)
    var_z = (1.0 + rhos_k ** 2 / 2.0) / (ns_k - 3.0)
    w = 1.0 / var_z
    sum_w = w.sum()

    z_bar = (w * z).sum() / sum_w
    rho_bar = float(np.tanh(z_bar))
    ci_lo = float(np.tanh(z_bar - 1.96 / np.sqrt(sum_w)))
    ci_hi = float(np.tanh(z_bar + 1.96 / np.sqrt(sum_w)))

    return rho_bar, ci_lo, ci_hi, int(keep.sum()), n_dropped


def uwls3_agg(rhos, ns):
    """
    UWLS+3 (Stanley-Doucouliagos 2025, PMC12631149).
    K<10 时偏差降至 <0.01; 作 Fisher-z 的现代替代补充。
    本实现解读: df = n_i + 1 (替代标准 n_i - 3), 即
      Var_uwls(z_i) = (1 + rho_i^2/2) / (n_i + 1)
    TODO: 精确公式待核对原文 (本实现为合理近似, 存疑处见 AGGREGATION_METHODS.md)。
    返回: rho_uwls3 (单值, 无 CI)
    """
    rhos = np.asarray(rhos, float)
    ns = np.asarray(ns, float)

    valid = ~np.isnan(rhos)
    rhos, ns = rhos[valid], ns[valid]
    if len(rhos) == 0:
        return np.nan

    rhos = np.clip(rhos, -FISHER_CLIP, FISHER_CLIP)
    z = np.arctanh(rhos)

    # UWLS+3: 用 n+1 作为 df, 分母恒正, 无需过滤小 n
    var_uwls = (1.0 + rhos ** 2 / 2.0) / (ns + 1.0)
    # 防极端情况 (var 极小造成 w 爆炸)
    var_uwls = np.maximum(var_uwls, 1e-10)

    w = 1.0 / var_uwls
    z_bar = (w * z).sum() / w.sum()
    return float(np.tanh(z_bar))


def geometric_mean_rho(rhos):
    """
    几何均值 via v=(1+rho)/2 变换 (描述性, 无文献专门背书).
    rho_GM = 2 * exp(mean(ln(v))) - 1
    任一患者 rho=-1 → v=0 → 拖底效应。
    v clip 到 1e-15 避免 log(0)=-inf 污染均值。
    """
    rhos = np.asarray(rhos, float)
    rhos = rhos[~np.isnan(rhos)]
    if len(rhos) == 0:
        return np.nan
    v = (1.0 + rhos) / 2.0
    v = np.clip(v, 1e-15, 1.0)
    return float(2.0 * np.exp(np.mean(np.log(v))) - 1.0)


def power_mean_p2(rhos):
    """
    幂平均 M2 (RMS) via v=(1+rho)/2 变换 (描述性, 无文献背书).
    rho_M2 = 2 * sqrt(mean(v^2)) - 1
    p=2 对高相关患者有奖励效应。
    """
    rhos = np.asarray(rhos, float)
    rhos = rhos[~np.isnan(rhos)]
    if len(rhos) == 0:
        return np.nan
    v = (1.0 + rhos) / 2.0
    return float(2.0 * np.sqrt(np.mean(v ** 2)) - 1.0)


def hs_weighted(rhos, ns):
    """
    Hunter-Schmidt 样本量加权: sum(n_i * rho_i) / sum(n_i).
    [psychometrics 传统; 本场景 n_i 两倍内, 与简单均值差异小]
    """
    rhos = np.asarray(rhos, float)
    ns = np.asarray(ns, float)
    valid = ~np.isnan(rhos)
    rhos, ns = rhos[valid], ns[valid]
    if len(rhos) == 0 or ns.sum() == 0:
        return np.nan
    return float((ns * rhos).sum() / ns.sum())


# ── 输入解析 ──────────────────────────────────────────────────────────────────
def resolve_xlsx(root: Path, arg_input):
    """优先 9tools xlsx, 退 8tools。"""
    if arg_input is not None:
        p = Path(arg_input)
        if not p.is_absolute():
            p = root / p
        if p.exists():
            return p
        raise SystemExit(f"[ERR] 指定输入不存在: {p}")
    for name in ["merged_all_tools_9tools.xlsx", "merged_all_tools_8tools.xlsx"]:
        p = root / "scripts" / "out" / name
        if p.exists():
            return p
    raise SystemExit("[ERR] 找不到 merged_all_tools_9tools.xlsx 或 _8tools.xlsx "
                     f"(查找目录: {root / 'scripts' / 'out'})")


def col_to_toolname(col):
    """MT_列名 -> 工具短名; IMPROVE 特例处理。"""
    name = col[3:]   # strip "MT_"
    if name.startswith("IMPROVE"):
        return "IMPROVE"
    return name


# ── 主函数 ────────────────────────────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser(
        description="DS2 per-patient Spearman 多聚合方法 (quantimmu-bench)")
    ap.add_argument("--input", default=None,
                    help="合并表路径 (默认自动找 9tools/8tools xlsx)")
    ap.add_argument("--sub_agg", choices=["max", "mean", "top3mean"], default="max",
                    help="子肽×HLA -> 肽级分数聚合方式 (默认 max)")
    ap.add_argument("--min_pep", type=int, default=MIN_PEP_DEFAULT,
                    help=f"患者内算 Spearman 的最少肽数 (默认 {MIN_PEP_DEFAULT})")
    args = ap.parse_args()

    # ── 读数据 ────────────────────────────────────────────────────────────────
    xlsx_path = resolve_xlsx(ROOT, args.input)
    nn_str = "9tools" if "9tools" in xlsx_path.name else "8tools"
    print(f"[info] 输入: {xlsx_path}")
    print(f"[info] sub_agg={args.sub_agg}  min_pep={args.min_pep}")

    df = pd.read_excel(xlsx_path)
    print(f"[info] 总行数: {len(df)}  列数: {len(df.columns)}")

    # ── DS2 筛选 ──────────────────────────────────────────────────────────────
    if "Dataset" not in df.columns:
        raise SystemExit("[ERR] 缺 'Dataset' 列, 无法筛 DS2")
    ds2 = df[df["Dataset"] == "DS2"].copy()
    print(f"[info] DS2 行数: {len(ds2)}")
    if ds2.empty:
        raise SystemExit("[ERR] DS2 子集为空, 请检查 Dataset 列值")

    for req in ["Elispot", "Peptide_ID"]:
        if req not in ds2.columns:
            raise SystemExit(f"[ERR] 缺列 '{req}'")

    # ── 患者 ID 处理 (Patient_ID 列优先, 缺失退 Peptide_ID 反解) ─────────────
    pcol = find_patient_col(ds2)
    if pcol is None:
        print(f"[warn] 未找到患者列 (试过 {PATIENT_COL_CANDIDATES}), 从 Peptide_ID 反解")
    else:
        print(f"[info] 患者列 = '{pcol}'")

    # 定义 get_patient 闭包 (pcol 捕获)
    def get_patient(row):
        if pcol is not None and pd.notna(row[pcol]):
            return str(row[pcol])
        return patient_from_peptide_id(row["Peptide_ID"])

    ds2["_patient"] = ds2.apply(get_patient, axis=1)
    before = len(ds2)
    ds2 = ds2.dropna(subset=["_patient"])
    if len(ds2) < before:
        print(f"[warn] {before - len(ds2)} 行无法解析患者 ID, 已丢弃")

    patients_in_data = sorted(ds2["_patient"].unique(),
                               key=lambda x: int(x) if str(x).isdigit() else 0)
    print(f"[info] DS2 患者 ({len(patients_in_data)}): {patients_in_data}")

    # ── 工具列自动检测 ────────────────────────────────────────────────────────
    # 排除: 序列字符串列 (FullPeptide/Subpeptide) + pTuneos 子特征 (非独立工具) + 任何非数值列
    EXCLUDE = {"MT_FullPeptide", "MT_Subpeptide", "MT_NOAH", "MT_NetCleave",
               "MT_Stab_peptide", "MT_TCR_contact"}
    mt_cols = []
    for c in ds2.columns:
        if not c.startswith("MT_") or c in EXCLUDE:
            continue
        ds2[c] = pd.to_numeric(ds2[c], errors="coerce")   # 强制数值, 非数值→NaN
        if ds2[c].notna().any():
            mt_cols.append(c)
    if not mt_cols:
        raise SystemExit("[ERR] 未找到有效数值 MT_* 工具列")
    tools = {col_to_toolname(c): c for c in mt_cols}
    print(f"[info] 检测到 {len(tools)} 个工具列: {list(tools.keys())}")

    # ── 肽级元信息 (Peptide_ID -> _patient, Elispot) ─────────────────────────
    # 每个 Peptide_ID 内 Elispot/患者唯一; 取 first (drop_duplicates)
    pep_info = (ds2.drop_duplicates("Peptide_ID")
                   [["Peptide_ID", "_patient", "Elispot"]]
                   .set_index("Peptide_ID"))

    # ── 逐工具计算 ────────────────────────────────────────────────────────────
    results = []

    print("\n" + "=" * 90)
    print(f"{'Tool':22s}  {'rho_global':>10}  {'fisher_z':>9}  "
          f"{'CI':>14}  {'median':>8}  {'n_valid_pat':>11}  {'global-fisherz':>14}")
    print("=" * 90)

    for tool_name, mt_col in tools.items():
        if mt_col not in ds2.columns:
            print(f"[warn] {tool_name}: 列 {mt_col} 不存在, 跳过")
            continue

        # 子肽×HLA → 肽级: groupby(Peptide_ID) 聚合
        valid_sub = ds2[ds2[mt_col].notna()][["Peptide_ID", mt_col]].copy()
        if valid_sub.empty:
            print(f"[warn] {tool_name}: 无有效分数, 跳过")
            continue

        sub_agg_method = args.sub_agg
        pep_scores = (
            valid_sub.groupby("Peptide_ID")[mt_col]
                     .agg(lambda arr: _agg_array(arr.values, sub_agg_method))
                     .rename("peptide_score")
        )

        # 合并患者/Elispot
        pep_df = (pep_scores.to_frame()
                             .join(pep_info[["_patient", "Elispot"]], how="inner")
                             .dropna(subset=["Elispot", "peptide_score"]))
        if pep_df.empty:
            print(f"[warn] {tool_name}: 合并后无有效肽, 跳过")
            continue

        # 全局 Spearman (DS2 所有肽)
        rho_global = spearman_np(pep_df["peptide_score"].values,
                                 pep_df["Elispot"].values)

        # per-patient Spearman
        pat_rhos = {}   # str(patient) -> rho (nan 若不满足 min_pep)
        pat_ns   = {}   # str(patient) -> n_pep (有分数的肽数)

        for pat, g in pep_df.groupby("_patient"):
            pat_key = str(pat)
            n_pep = len(g)
            if n_pep >= args.min_pep:
                rho = spearman_np(g["peptide_score"].values, g["Elispot"].values)
            else:
                rho = np.nan
            pat_rhos[pat_key] = rho
            pat_ns[pat_key]   = n_pep

        # 只用满足 min_pep 且 rho 非 NaN 的患者做聚合
        valid_pairs = [(r, pat_ns[p]) for p, r in pat_rhos.items()
                       if not np.isnan(r)]
        if not valid_pairs:
            print(f"[warn] {tool_name}: 无患者满足 >={args.min_pep} 肽条件, 跳过")
            continue

        rhos_arr = np.array([v[0] for v in valid_pairs])
        ns_arr   = np.array([v[1] for v in valid_pairs], float)
        n_patients_valid = len(rhos_arr)

        # ─ 7 种聚合 ─
        fz_rho, fz_ci_lo, fz_ci_hi, fz_n_used, fz_n_drop = \
            fisherz_weighted(rhos_arr, ns_arr)
        med     = float(np.median(rhos_arr))
        smean   = float(np.mean(rhos_arr))
        hs      = hs_weighted(rhos_arr, ns_arr)
        gm      = geometric_mean_rho(rhos_arr)
        pm2     = power_mean_p2(rhos_arr)
        uwls3_v = uwls3_agg(rhos_arr, ns_arr)

        # 跨患者分布
        rho_min = float(rhos_arr.min())
        rho_max = float(rhos_arr.max())
        rho_std = (float(rhos_arr.std(ddof=1)) if len(rhos_arr) > 1 else np.nan)

        # ─ 组装结果行 ─
        def _r4(v):
            return round(float(v), 4) if (v is not None and not np.isnan(v)) else np.nan

        row = {
            "Tool":              tool_name,
            "n_patients":        n_patients_valid,
            "rho_global":        _r4(rho_global),
            "fisherz_weighted":  _r4(fz_rho),
            "fisherz_ci_lo":     _r4(fz_ci_lo),
            "fisherz_ci_hi":     _r4(fz_ci_hi),
            "fisherz_n_used":    fz_n_used,
            "fisherz_n_dropped": fz_n_drop,
            "median":            _r4(med),
            "simple_mean":       _r4(smean),
            "hs_weighted":       _r4(hs),
            "geometric_mean":    _r4(gm),
            "power_mean_p2":     _r4(pm2),
            "uwls3":             _r4(uwls3_v),
            "rho_min":           _r4(rho_min),
            "rho_max":           _r4(rho_max),
            "rho_std":           _r4(rho_std),
        }

        # 各患者列 rho_p<id> + n_p<id>  (ALL_PATIENTS = 101,102,104..110)
        for pid in ALL_PATIENTS:
            pid_s = str(pid)
            rho_v = pat_rhos.get(pid_s, np.nan)
            row[f"rho_p{pid_s}"] = _r4(rho_v) if not np.isnan(rho_v) else np.nan
            row[f"n_p{pid_s}"]   = pat_ns.get(pid_s, 0)

        results.append(row)

        # stdout 摘要
        diff = (_r4(fz_rho) - _r4(rho_global)) if (
            not np.isnan(fz_rho) and not np.isnan(rho_global)) else float("nan")
        ci_str = (f"[{fz_ci_lo:+.3f},{fz_ci_hi:+.3f}]"
                  if not np.isnan(fz_ci_lo) else "[  n/a  ,  n/a  ]")
        print(f"  {tool_name:20s}  {rho_global:+10.4f}  {fz_rho:+9.4f}  "
              f"{ci_str:>16}  {med:+8.4f}  {n_patients_valid:>11d}  {diff:+14.4f}")

    print("=" * 90)

    if not results:
        raise SystemExit("[ERR] 所有工具均无有效结果, CSV 未写出")

    # ── 写出 CSV ──────────────────────────────────────────────────────────────
    out_df = pd.DataFrame(results)
    out_csv = HERE / f"per_patient_spearman_{nn_str}.csv"
    out_df.to_csv(out_csv, index=False, encoding="utf-8")
    print(f"\n[saved] {out_csv}  shape={out_df.shape}")

    # ── 警告块 (审稿必知) ─────────────────────────────────────────────────────
    print("\n[STATISTICAL WARNINGS - per AGGREGATION_METHODS.md]")
    print("  1. n_i=6-16 -> 单 rho_i 95%CI 约 ±0.6-0.7; 任何聚合值的 CI 仍很宽, 不可过度解读。")
    print("  2. K=9 (小) -> 不用随机效应 (tau^2 估计不稳, BMC Med Res Methodol 2015)。")
    print("  3. 几何/幂平均描述性非推断 (经 (1+rho)/2 变换); 无统计 CI, 仅探索对照。")
    print("  4. 主结论以 fisherz_weighted + median 为准; 其余作敏感性检查。")
    print("  5. UWLS+3: df=n+1 近似实现; TODO 精确公式待核 Stanley-Doucouliagos 2025 (PMC12631149)。")
    print(f"\n[DONE] per-patient Spearman 多聚合完成 -> {out_csv}")


if __name__ == "__main__":
    main()
