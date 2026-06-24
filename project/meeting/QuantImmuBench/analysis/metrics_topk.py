#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Top-K / ISSR / MCC 方法学补强 —— 现有 metrics_ds2_8tools.csv 只有 AUC/AUPRC/Spearman，
缺学界标准的「排序质量」指标。本脚本补:
  - AUPRC            (重算确认，与现有一致)
  - PPV@top-10/25/50 (ISSR, Immunogenic Sequence Selection Rate:
                      取分数最高的 K 条肽里有多少是真免疫原性肽 = precision@K)
  - MCC at Youden    (在 ROC Youden's J 最优阈值处的 Matthews 相关系数)
对齐 PredIG / IMPROVE 论文的报告规范 (它们都报 top-K recovery + MCC)。

输入 (二选一, --source):
  perpep (默认): analysis/plotdata_perpep.csv —— 含旧 5 工具 ×3 聚合口径 (max/mean/top3mean)，
                 标签 pos_gt0 / pos_gt10。与 bootstrap_ci.py / metrics 同源。
  merged       : scripts/out/merged_all_tools_8tools.xlsx —— 全 8 工具，按 Peptide_ID 聚合
                 MT_<tool> 列为 max/mean/top3mean，标签由 Elispot 阈值生成。

阈值 (Threshold 列, 对齐 metrics_ds2_8tools.csv):
  >0   : Elispot > 0   为阳性
  >10  : Elispot > 10  为阳性
  >median: Elispot > 该数据集中位数 为阳性

输出:
  analysis/metrics_topk_ds2.csv
  列: Tool,Aggregation,Threshold,n_pep,n_pos,n_neg,AUPRC,
      PPV_top10,PPV_top25,PPV_top50,MCC_youden,Youden_thr

跑法 (主线):
  python analysis/metrics_topk.py                 # 默认 perpep, 5 工具
  python analysis/metrics_topk.py --source merged # 全 8 工具
"""
import argparse
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score, roc_curve, matthews_corrcoef

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
PERPEP = HERE / "plotdata_perpep.csv"
MERGED = ROOT / "scripts" / "out" / "merged_all_tools_8tools.xlsx"
OUT_CSV = HERE / "metrics_topk_ds2.csv"

TOPK_LIST = [10, 25, 50]
AGGS = ["max", "mean", "top3mean"]

# merged 表里 8 工具的 MT_ 分数列 (IMPROVE 列名特殊)
MERGED_TOOL_COLS = {
    "DeepImmuno": "MT_DeepImmuno",
    "PredIG": "MT_PredIG",
    "NeoTImmuML": "MT_NeoTImmuML",
    "IMPROVE": "MT_IMPROVE_mean_prediction_rf",
    "pTuneos": "MT_pTuneos",
    "PRIME": "MT_PRIME",
    "ImmuneApp": "MT_ImmuneApp",
    "deepHLApan": "MT_deepHLApan",
}


def ppv_at_k(y, s, k):
    """precision@K: 分数降序前 K 条里阳性比例 (ISSR)。k>n 时用 n。"""
    m = ~np.isnan(s)
    y, s = y[m], s[m]
    if len(y) == 0:
        return np.nan
    k = min(k, len(y))
    order = np.argsort(-s, kind="mergesort")  # 稳定排序，平分时保持原序
    top = order[:k]
    return float(y[top].sum()) / k


def mcc_youden(y, s):
    """在 ROC Youden's J 最优阈值处算 MCC。返回 (mcc, thr)。"""
    m = ~np.isnan(s)
    y, s = y[m], s[m]
    if len(np.unique(y)) < 2:
        return np.nan, np.nan
    fpr, tpr, thr = roc_curve(y, s)
    j = tpr - fpr
    best = int(np.argmax(j))
    t = thr[best]
    pred = (s >= t).astype(int)
    if len(np.unique(pred)) < 2:
        return 0.0, float(t)
    return float(matthews_corrcoef(y, pred)), float(t)


def auprc_safe(y, s):
    m = ~np.isnan(s)
    y, s = y[m], s[m]
    if len(np.unique(y)) < 2:
        return np.nan
    return float(average_precision_score(y, s))


def labels_for(elispot, thr_name):
    """根据 Threshold 名生成 0/1 标签。elispot = np.array of float Elispot。"""
    if thr_name == ">0":
        return (elispot > 0).astype(int)
    if thr_name == ">10":
        return (elispot > 10).astype(int)
    if thr_name == ">median":
        med = np.nanmedian(elispot)
        return (elispot > med).astype(int)
    raise ValueError(thr_name)


def rows_from_perpep():
    df = pd.read_csv(PERPEP)
    tools = sorted(df["Tool"].unique())
    out = []
    for tool in tools:
        for agg in AGGS:
            sub = df[(df["Tool"] == tool) & (df["Aggregation"] == agg)].copy()
            if sub.empty:
                continue
            # 每肽一行；Elispot 与 score 对齐
            sub = sub.drop_duplicates("Peptide_ID")
            elis = sub["Elispot"].values.astype(float)
            score = sub["score"].values.astype(float)
            for thr in [">0", ">10", ">median"]:
                y = labels_for(elis, thr)
                out.append(_metric_row(tool, agg, thr, y, score))
    return out


def rows_from_merged():
    df = pd.read_excel(MERGED)
    if "Peptide_ID" not in df.columns or "Elispot" not in df.columns:
        raise SystemExit("[ERR] merged 表缺 Peptide_ID / Elispot 列")
    out = []
    for tool, col in MERGED_TOOL_COLS.items():
        if col not in df.columns:
            print(f"[warn] merged 表无列 {col}，跳过 {tool}")
            continue
        for agg in AGGS:
            g = df.groupby("Peptide_ID")
            elis = g["Elispot"].first()
            if agg == "max":
                sc = g[col].max()
            elif agg == "mean":
                sc = g[col].mean()
            else:  # top3mean
                sc = g[col].apply(lambda v: v.dropna().nlargest(3).mean())
            merged = pd.concat([elis, sc], axis=1)
            merged.columns = ["Elispot", "score"]
            merged = merged.dropna(subset=["Elispot"])
            e = merged["Elispot"].values.astype(float)
            s = merged["score"].values.astype(float)
            for thr in [">0", ">10", ">median"]:
                y = labels_for(e, thr)
                out.append(_metric_row(tool, agg, thr, y, s))
    return out


def _metric_row(tool, agg, thr, y, score):
    mcc, ythr = mcc_youden(y, score)
    row = {
        "Tool": tool, "Aggregation": agg, "Threshold": thr,
        "n_pep": int(len(y)), "n_pos": int(y.sum()), "n_neg": int((y == 0).sum()),
        "AUPRC": round(auprc_safe(y, score), 4) if not np.isnan(auprc_safe(y, score)) else np.nan,
        "MCC_youden": round(mcc, 4) if not np.isnan(mcc) else np.nan,
        "Youden_thr": round(ythr, 4) if not np.isnan(ythr) else np.nan,
    }
    for k in TOPK_LIST:
        v = ppv_at_k(y, score, k)
        row[f"PPV_top{k}"] = round(v, 4) if not np.isnan(v) else np.nan
    # 列顺序: 把 PPV 放 AUPRC 后、MCC 前
    ordered = {kk: row[kk] for kk in
               ["Tool", "Aggregation", "Threshold", "n_pep", "n_pos", "n_neg", "AUPRC",
                f"PPV_top{TOPK_LIST[0]}", f"PPV_top{TOPK_LIST[1]}", f"PPV_top{TOPK_LIST[2]}",
                "MCC_youden", "Youden_thr"]}
    return ordered


def main():
    ap = argparse.ArgumentParser(description="Top-K / ISSR / MCC 指标补强")
    ap.add_argument("--source", choices=["perpep", "merged"], default="perpep")
    args = ap.parse_args()

    if args.source == "perpep":
        if not PERPEP.exists():
            raise SystemExit(f"[ERR] 缺 {PERPEP}")
        rows = rows_from_perpep()
    else:
        if not MERGED.exists():
            raise SystemExit(f"[ERR] 缺 {MERGED}")
        rows = rows_from_merged()

    res = pd.DataFrame(rows)
    res.to_csv(OUT_CSV, index=False)
    print(f"=== metrics_topk (source={args.source}) ===")
    print(res.to_string(index=False))
    print(f"\nsaved -> {OUT_CSV}")
    print("PPV_topK = ISSR (前 K 高分肽里真阳性比例)；MCC_youden = Youden 阈值处 Matthews 相关系数")


if __name__ == "__main__":
    main()
