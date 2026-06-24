#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
患者分层检查 —— 补救红队 🟠-4：DS2 的肽来自少数患者，肽间非独立 (同患者 HLA/抗原背景共享)，
按肽 bootstrap 会高估有效自由度。本脚本量化「患者聚集」程度并给患者级评估。

输入:
  --ds2     data/Elispot_Dataset2.xlsx (取 Patient_ID + Peptide_ID + Elispot)
  --perpep  analysis/plotdata_perpep.csv (取各工具逐肽分数, max-agg)
            ※ perpep 的 Peptide_ID 形如 '16097-101-10'，中段 = 患者号，
              脚本会优先用 ds2 的显式 Patient_ID 映射，缺失时从 Peptide_ID 反解 (split('-')[1])。

Patient_ID 列 fallback (列名不同时按序尝试):
  ['Patient_ID', 'Patient', 'PatientID', 'patient_id', 'Subject', 'Sample_ID']

统计:
  ① 每患者贡献肽数 / 阴性肽数 (看 n_neg≈11 个阴性是否集中在 1-2 患者) -> 打印分布。
  ② 各工具 per-patient 内 Spearman (score vs Elispot SFC)，>=3 肽的患者才算，再做患者间均值。
  ③ 患者分层 bootstrap AUC：按【患者】整体重抽样 (一个患者的所有肽一起进/出)，
     而非按肽，得到更诚实的 CI 宽度。对照按肽 bootstrap 看 CI 被低估多少。

输出:
  analysis/patient_strat_ds2.csv
    含两段: per_patient_summary (每患者肽数/阴性数) + per_tool (患者内Spearman均值 +
            按患者 bootstrap AUC 点估计与 CI)。用 'section' 列区分。
  并打印一句话判断: 有效自由度是否 << n_pep (患者数 vs 肽数)。

跑法 (主线):
  python analysis/patient_strat_check.py
"""
import argparse
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
DS2 = ROOT / "data" / "Elispot_Dataset2.xlsx"
PERPEP = HERE / "plotdata_perpep.csv"
OUT_CSV = HERE / "patient_strat_ds2.csv"

PATIENT_COL_CANDIDATES = ["Patient_ID", "Patient", "PatientID", "patient_id",
                          "Subject", "Sample_ID"]
N_BOOT = 2000
SEED = 20260624
MIN_PEP_FOR_SPEARMAN = 3  # 患者内算 Spearman 的最少肽数


def spearman_np(x, y):
    """纯 numpy Spearman (rank Pearson)，避免 scipy.stats 与 torch 抢 OpenMP。"""
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


def auc_safe(y, s):
    m = ~np.isnan(s)
    y, s = y[m], s[m]
    if len(np.unique(y)) < 2:
        return np.nan
    return roc_auc_score(y, s)


def find_patient_col(df):
    for c in PATIENT_COL_CANDIDATES:
        if c in df.columns:
            return c
    return None


def patient_from_peptide_id(pid):
    """从 '16097-101-10' 反解患者号 -> '101'。"""
    if not isinstance(pid, str):
        return None
    parts = pid.split("-")
    return parts[1] if len(parts) >= 3 else None


def main():
    ap = argparse.ArgumentParser(description="患者分层 / 聚集检查")
    ap.add_argument("--ds2", default=str(DS2))
    ap.add_argument("--perpep", default=str(PERPEP))
    args = ap.parse_args()

    ds2_path = Path(args.ds2)
    if not ds2_path.exists():
        raise SystemExit(f"[ERR] 缺 {ds2_path}")
    ds2 = pd.read_excel(ds2_path)

    pcol = find_patient_col(ds2)
    if pcol is None:
        print(f"[warn] DS2 未找到患者列 (试过 {PATIENT_COL_CANDIDATES})，"
              f"将从 Peptide_ID 反解患者号。")
    else:
        print(f"[info] DS2 患者列 = '{pcol}'")

    if "Peptide_ID" not in ds2.columns or "Elispot" not in ds2.columns:
        raise SystemExit("[ERR] DS2 缺 Peptide_ID / Elispot 列")

    # 建 Peptide_ID -> patient 映射
    pep2pat = {}
    for _, r in ds2.iterrows():
        pid = r["Peptide_ID"]
        pat = (str(r[pcol]) if (pcol and pd.notna(r[pcol]))
               else patient_from_peptide_id(pid))
        if pid is not None and pat is not None:
            pep2pat[pid] = pat

    # ---- 读分数 (perpep, max-agg) ----
    perpep_path = Path(args.perpep)
    if not perpep_path.exists():
        raise SystemExit(f"[ERR] 缺 {perpep_path}")
    pp = pd.read_csv(perpep_path)
    pp = pp[pp["Aggregation"] == "max"].copy()
    pp["patient"] = pp["Peptide_ID"].map(lambda x: pep2pat.get(x, patient_from_peptide_id(x)))
    pp = pp.dropna(subset=["patient"])
    pp["pos"] = (pp["Elispot"].astype(float) > 0).astype(int)  # >0 阳性 (n_neg=11 口径)

    tools = sorted(pp["Tool"].unique())

    # ---- ① per-patient summary (用任一工具的肽全集，肽集对所有工具一致) ----
    base = pp.drop_duplicates("Peptide_ID")[["Peptide_ID", "patient", "Elispot", "pos"]]
    summ_rows = []
    for pat, g in base.groupby("patient"):
        summ_rows.append({
            "section": "per_patient_summary",
            "patient": pat,
            "n_pep": int(len(g)),
            "n_neg": int((g["pos"] == 0).sum()),
            "n_pos": int((g["pos"] == 1).sum()),
        })
    summ = pd.DataFrame(summ_rows).sort_values("n_neg", ascending=False)

    n_patients = base["patient"].nunique()
    n_pep_total = base["Peptide_ID"].nunique()
    n_neg_total = int((base["pos"] == 0).sum())
    # 阴性集中度：贡献阴性肽最多的前 2 患者占了多少阴性
    neg_by_pat = base[base["pos"] == 0].groupby("patient").size().sort_values(ascending=False)
    top2_neg = int(neg_by_pat.head(2).sum()) if len(neg_by_pat) else 0

    # ---- ② per-tool: 患者内 Spearman 均值 + ③ 按患者 bootstrap AUC ----
    rng = np.random.default_rng(SEED)
    patients = sorted(base["patient"].unique())
    pat2idx = {p: i for i, p in enumerate(patients)}

    tool_rows = []
    for tool in tools:
        sub = pp[pp["Tool"] == tool].drop_duplicates("Peptide_ID")
        # 患者内 Spearman
        in_pat_rhos = []
        for pat, g in sub.groupby("patient"):
            if len(g) >= MIN_PEP_FOR_SPEARMAN:
                rho = spearman_np(g["score"].values, g["Elispot"].values)
                if not np.isnan(rho):
                    in_pat_rhos.append(rho)
        mean_in_pat_rho = float(np.mean(in_pat_rhos)) if in_pat_rhos else np.nan

        # 点估计 AUC (全肽)
        y_all = sub["pos"].values.astype(float)
        s_all = sub["score"].values.astype(float)
        pt_auc = auc_safe(pd.Series(y_all), pd.Series(s_all))

        # 按患者 bootstrap: 每次有放回抽 n_patients 个患者，取其全部肽
        pat_groups = {p: sub[sub["patient"] == p] for p in patients}
        boots = []
        for _ in range(N_BOOT):
            pick = rng.integers(0, len(patients), len(patients))
            ys, ss = [], []
            for j in pick:
                gp = pat_groups[patients[j]]
                ys.append(gp["pos"].values.astype(float))
                ss.append(gp["score"].values.astype(float))
            yb = np.concatenate(ys)
            sb = np.concatenate(ss)
            mb = ~np.isnan(sb)
            yb, sb = yb[mb], sb[mb]
            if len(np.unique(yb)) < 2:
                continue
            boots.append(roc_auc_score(yb, sb))
        boots = np.array(boots)
        if len(boots):
            lo, hi = np.percentile(boots, [2.5, 97.5])
        else:
            lo = hi = np.nan

        tool_rows.append({
            "section": "per_tool",
            "patient": "",  # 占位对齐列
            "Tool": tool,
            "n_pep": int(len(sub)),
            "n_patients_with_ge3pep": int(len(in_pat_rhos)),
            "mean_within_patient_spearman": round(mean_in_pat_rho, 4) if not np.isnan(mean_in_pat_rho) else np.nan,
            "AUC_point": round(pt_auc, 4) if not np.isnan(pt_auc) else np.nan,
            "AUC_patientBoot_CI_lo": round(lo, 4) if not np.isnan(lo) else np.nan,
            "AUC_patientBoot_CI_hi": round(hi, 4) if not np.isnan(hi) else np.nan,
            "AUC_patientBoot_CI_width": round(hi - lo, 4) if not np.isnan(hi) else np.nan,
        })

    # ---- 合并写出 (两段堆叠) ----
    out = pd.concat([summ, pd.DataFrame(tool_rows)], ignore_index=True, sort=False)
    out.to_csv(OUT_CSV, index=False)

    print("\n=== per-patient summary (按阴性肽数降序) ===")
    print(summ.to_string(index=False))
    print(f"\n患者数 = {n_patients} | 肽总数 = {n_pep_total} | 阴性肽总数 = {n_neg_total}")
    print(f"贡献阴性肽最多的前 2 患者占了 {top2_neg}/{n_neg_total} 个阴性肽 "
          f"({top2_neg / n_neg_total:.0%})" if n_neg_total else "无阴性肽")

    print("\n=== per-tool (患者内 Spearman + 按患者 bootstrap AUC) ===")
    print(pd.DataFrame(tool_rows).to_string(index=False))

    print(f"\nsaved -> {OUT_CSV}")
    # 一句话判断
    eff = "<<" if n_patients < n_pep_total / 3 else ("<" if n_patients < n_pep_total else "≈")
    print(f"\n[判断] 有效自由度 ≈ 患者数 {n_patients} {eff} 肽数 {n_pep_total}："
          f"{'肽间高度患者聚集，按肽 bootstrap 显著高估自由度，应以患者级 CI 为准' if eff in ('<<','<') else '聚集不明显'}。")


if __name__ == "__main__":
    main()
