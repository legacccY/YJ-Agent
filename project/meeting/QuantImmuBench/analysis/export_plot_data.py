"""
export_plot_data.py
服务: quantimmu-bench
功能: 从 merged_all_tools_4tools.xlsx 导出 R 画图用 tidy CSV
      - plotdata_perpep.csv   (per-peptide 聚合分 + Elispot)
      - plotdata_roc.csv      (ROC 曲线点, agg=max/mean, >0 和 >10)
聚合逻辑照搬 benchmark_analysis.py, 保证数字与 metrics_ds2.csv 对得上.
输出目录: 与本脚本同目录 (analysis/)
"""
import os, sys
import pandas as pd
import numpy as np
from sklearn.metrics import roc_curve, roc_auc_score

# ── 路径 ──────────────────────────────────────────────────────────────────────
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_PATH  = os.path.join(SCRIPT_DIR, "..", "scripts", "out", "merged_all_tools_5tools.xlsx")
OUT_DIR    = SCRIPT_DIR

# 工具列映射 (照搬 benchmark_analysis.py)
TOOLS = {
    "DeepImmuno":  "MT_DeepImmuno",
    "PredIG":      "MT_PredIG",
    "IMPROVE":     "MT_IMPROVE_mean_prediction_rf",
    "NeoTImmuML":  "MT_NeoTImmuML",
    "pTuneos":     "MT_pTuneos",
}

# ── 读数据 ────────────────────────────────────────────────────────────────────
print(f"Reading: {DATA_PATH}")
df   = pd.read_excel(DATA_PATH)
ds2  = df[df["Dataset"] == "DS2"].copy()

# per-peptide Elispot (first occurrence, 每 Peptide_ID 内 Elispot 同值)
ds2_pep = ds2.drop_duplicates("Peptide_ID")[["Peptide_ID", "Elispot"]].set_index("Peptide_ID")
elispot_vals = ds2_pep["Elispot"]

# ── 聚合函数 (照搬原脚本) ──────────────────────────────────────────────────────
def agg_pep(sub, col):
    """返回 {Peptide_ID: {max, mean, top3mean}}"""
    valid = sub[sub[col].notna()].copy()
    if valid.empty:
        return {}
    out = {}
    for pid, grp in valid.groupby("Peptide_ID")[col]:
        arr = grp.values
        k   = min(3, len(arr))
        out[pid] = {
            "max":      float(arr.max()),
            "mean":     float(arr.mean()),
            "top3mean": float(np.sort(arr)[-k:].mean()),
        }
    return out

pep_scores = {t: agg_pep(ds2, c) for t, c in TOOLS.items()}

# ── 1. plotdata_perpep.csv ────────────────────────────────────────────────────
perpep_rows = []
for tname, pd_ in pep_scores.items():
    if not pd_:
        continue
    for pid, agg_dict in pd_.items():
        el = float(elispot_vals.loc[pid]) if pid in elispot_vals.index else np.nan
        for agg_method, score in agg_dict.items():
            perpep_rows.append({
                "Peptide_ID": pid,
                "Tool":       tname,
                "Aggregation": agg_method,
                "score":      score,
                "Elispot":    el,
                "pos_gt0":    int(el > 0)   if not np.isnan(el) else np.nan,
                "pos_gt10":   int(el > 10)  if not np.isnan(el) else np.nan,
            })

perpep_df = pd.DataFrame(perpep_rows)
perpep_path = os.path.join(OUT_DIR, "plotdata_perpep.csv")
perpep_df.to_csv(perpep_path, index=False)
print(f"Saved: {perpep_path}  shape={perpep_df.shape}")

# ── 2. plotdata_roc.csv ───────────────────────────────────────────────────────
THRESHOLDS = {">0": 0, ">10": 10}
AGG_METHODS = ["max", "mean"]

roc_rows = []
for tname, pd_ in pep_scores.items():
    if not pd_:
        continue
    pids = list(pd_.keys())
    el   = elispot_vals.loc[pids].values

    for agg_method in AGG_METHODS:
        sc = np.array([pd_[p][agg_method] for p in pids])

        for thr_name, thr_val in THRESHOLDS.items():
            labs = (el > thr_val).astype(int)
            npos = int(labs.sum())
            nneg = int((1 - labs).sum())
            if npos == 0 or nneg == 0:
                continue
            auc_val = roc_auc_score(labs, sc)
            fpr, tpr, _ = roc_curve(labs, sc)
            for f, t in zip(fpr, tpr):
                roc_rows.append({
                    "Tool":        tname,
                    "Aggregation": agg_method,
                    "Threshold":   thr_name,
                    "fpr":         float(f),
                    "tpr":         float(t),
                    "auc":         round(float(auc_val), 4),
                })

roc_df   = pd.DataFrame(roc_rows)
roc_path = os.path.join(OUT_DIR, "plotdata_roc.csv")
roc_df.to_csv(roc_path, index=False)
print(f"Saved: {roc_path}  shape={roc_df.shape}")

print("\nDone. Files ready for R:")
print(f"  {perpep_path}")
print(f"  {roc_path}")
print(f"  {os.path.join(OUT_DIR, 'metrics_ds2.csv')}  (already exists, R reads directly)")
