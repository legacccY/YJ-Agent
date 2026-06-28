"""
F-pilot 预登记单工具地板 per-patient 生成器 (quantimmu-bench)
服务: LEDGER §5 约束③ 去偏地板 —— 在同 15 患者/同口径上算单工具 per-patient Spearman,
       输出与 lopo_eval.py 同格式的 per_patient.csv, 供 paired_bootstrap.py 当 baseline。
单工具无训练 → per-patient ρ 直接算(肽级 score vs SFC), 不存在 LOPO 拟合。
口径与 lopo_eval 主聚合一致: 仅 DS2 9 患者进主分析(in_main_analysis=True), DS1 仅敏感性; n_pep<4 记 NaN。
跑: python quantimmune/make_floor_perpatient.py
输出: quantimmune/results/floor_<tool>.per_patient.csv  (tool ∈ PRIME, deepHLApan, PredIG, IMPROVE)
"""
import os
import numpy as np
import pandas as pd
from scipy.stats import spearmanr

HERE = os.path.dirname(os.path.abspath(__file__))
MATRIX = os.path.join(HERE, "model_matrix.csv")
OUTDIR = os.path.join(HERE, "results")
os.makedirs(OUTDIR, exist_ok=True)

# 预登记地板工具 -> model_matrix 列名
FLOOR_TOOLS = {
    "PRIME": "MT_PRIME",
    "deepHLApan": "MT_deepHLApan",
    "PredIG": "MT_PredIG",
    "IMPROVE": "MT_IMPROVE_mean_prediction_rf",
}
N_MIN = 4  # n_pep<4 的患者 ρ 记 NaN (与 lopo_eval 一致)


def fisher_z(rho):
    rho = np.clip(rho, -0.999999, 0.999999)
    return np.arctanh(rho)


def main():
    m = pd.read_csv(MATRIX, encoding="utf-8")
    for tool, col in FLOOR_TOOLS.items():
        rows = []
        for pid, g in m.groupby("Patient_ID"):
            ds = g["Dataset"].iloc[0]
            sub = g[[col, "Elispot"]].dropna()
            n = len(sub)
            if n >= N_MIN and sub[col].nunique() > 1 and sub["Elispot"].nunique() > 1:
                rho = spearmanr(sub[col], sub["Elispot"]).correlation
            else:
                rho = np.nan
            in_main = (ds == "DS2") and not np.isnan(rho)
            rows.append({
                "Patient_ID": pid,
                "Dataset": ds,
                "n_pep": n,
                "rho": rho,
                "rho_z": fisher_z(rho) if not np.isnan(rho) else np.nan,
                "in_main_analysis": in_main,
                "note": "single-tool floor (no training)" if ds == "DS2" else "DS1: sensitivity only",
            })
        out = pd.DataFrame(rows)
        path = os.path.join(OUTDIR, f"floor_{tool}.per_patient.csv")
        out.to_csv(path, index=False, encoding="utf-8")
        # 报 DS2 主聚合 Fisher-z 加权
        main_df = out[out["in_main_analysis"]].copy()
        zs = main_df["rho"].dropna().apply(fisher_z)
        ns = main_df.loc[main_df["rho"].notna(), "n_pep"]
        rhos = main_df["rho"].dropna()
        w = (ns - 3) / (1 + rhos.values ** 2 / 2)
        zbar = np.sum(w.values * zs.values) / np.sum(w.values)
        print(f"[{tool}] DS2 floor Fisher-z rho_bar = {np.tanh(zbar):+.4f}  median={main_df['rho'].median():+.4f}  (n_patients={main_df['rho'].notna().sum()})  -> {path}")


if __name__ == "__main__":
    main()
