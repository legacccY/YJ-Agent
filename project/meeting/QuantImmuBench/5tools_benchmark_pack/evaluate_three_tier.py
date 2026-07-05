# -*- coding: utf-8 -*-
"""
evaluate_three_tier.py — 5 工具 × 130 肽 三层横评（复现 PPT 结果表）

输入：tool_outputs/ 里 5 个工具已存的推理输出 + data/ 里 130 肽 ELISpot ground truth
输出：results/metrics_three_tier.csv + results/per_patient_details.csv

评估口径（已对 expected_results/ 逐值核验，diff=0）：
  1) pooling：每个 Peptide_ID 取该肽所有「子肽 × HLA」分数的 max（方向统一：越大越免疫原）
  2) 每工具用的分数列：
       DeepHLApan → MT_DHL_immunogenic_score
       PRIME      → Score_bestAllele（PRIME 原生 raw 输出，按子肽序列映射）
       ImmuneApp  → MT_ImmuneApp_Score
       HLAthena   → HLAthena_presentation_score（本身已是肽级提呈分）
       MHLAPre    → MT_MHLAPre_Score
  3) Tier-1（主指标）患者内 Fisher-Z 加权 Spearman：
       每位患者内算 Spearman ρ → 偏差校正 z = arctanh(clip(ρ,±0.999)) − ρ/(2(n−1))
       → 逆方差加权 w = n−3 → z̄ = Σ(w·z)/Σw → ρ_agg = tanh(z̄)
       95%CI = tanh(z̄ ± 1.96/√Σw)；仅计入肽数 n≥4 的患者
  4) Tier-2（对照）全局 Spearman：130 肽混合算一次
  5) Tier-3（辅助）AUC：label = ELISpot>0（有无免疫反应二分类）

注意：HLAthena 是「提呈」工具（presentation），不是免疫原性工具，仅作 baseline 单列，
      不与免疫原性工具 apples-to-apples 排名。MHLAPre 为自训复刻版且训练/预测同批数据
      （AUC≈0.997 是数据泄露产物），诚实评估见 dataset_scripts/mhlapre_groupkfold_cv.py。
"""
import os
import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from sklearn.metrics import roc_auc_score

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS_DIR = os.path.join(HERE, "tool_outputs")
DATA_DIR = os.path.join(HERE, "data")
OUT_DIR = os.path.join(HERE, "results")
os.makedirs(OUT_DIR, exist_ok=True)

BB = ["Patient_ID", "Peptide_ID", "Elispot", "MT_Subpeptide", "HLA_Allele"]

# 工具元信息：(merged 文件, 分数列, 是否免疫原性工具, DOI, caveat)
TOOL_META = {
    "MHLAPre":    ("MHLAPre_merged_results.xlsx",    "MT_MHLAPre_Score",           True,
                   "N/A (community model, no official weights)",
                   "*** Self-trained replica: official weights unavailable. Interpret with extreme caution."),
    "PRIME":      (None,                             "Score_bestAllele",           True,
                   "10.1016/j.cels.2022.12.002", "Depends on MixMHCpred; no DTU license"),
    "ImmuneApp":  ("ImmuneApp_merged_results.xlsx",  "MT_ImmuneApp_Score",         True,
                   "10.1038/s41467-024-53296-0", "TF 1.15 legacy env; MIT license"),
    "DeepHLApan": ("DeepHLApan_merged_results.xlsx", "MT_DHL_immunogenic_score",   True,
                   "10.3389/fimmu.2019.02559",
                   "Training data may overlap IEDB ELISpot positives; potential data leakage"),
    "HLAthena":   ("HLAthena_merged_results.xlsx",   "HLAthena_presentation_score", False,
                   "10.1038/s41587-019-0322-9",
                   "PRESENTATION proxy only - not designed for immunogenicity. Reference only; do NOT rank against immunogenicity tools."),
}


def peptide_level_scores(df, score_col):
    """max-pool 子肽×HLA → 每 Peptide_ID 一个分；返回 (Patient_ID, Peptide_ID, score, el)。"""
    d = df.dropna(subset=[score_col])
    g = d.groupby(["Patient_ID", "Peptide_ID"]).agg(
        score=(score_col, "max"), el=("Elispot", "first")
    ).reset_index()
    return g


def load_backbone():
    """从 DeepHLApan merged 取干净 backbone（含全部 130 肽的子肽×HLA 展开）。"""
    return pd.read_excel(os.path.join(TOOLS_DIR, "DeepHLApan_merged_results.xlsx"))


def prime_peptide_scores(backbone):
    """PRIME 的 merged 文件损坏 → 直接从原生 raw 输出取 Score_bestAllele，按子肽序列贴回 backbone。"""
    raw = pd.read_csv(os.path.join(TOOLS_DIR, "PRIME_dataset2_MT_prime.txt"),
                      sep="\t", skiprows=11)
    pmap = dict(zip(raw["Peptide"], raw["Score_bestAllele"]))
    bb = backbone[BB].copy()
    bb["PRIME"] = bb["MT_Subpeptide"].map(pmap)
    return peptide_level_scores(bb, "PRIME")


def fisher_z_weighted(g):
    """患者内 Fisher-Z 加权 Spearman（偏差校正 + 逆方差权重 n-3）。
    返回 (rho_agg, ci_lo, ci_hi, n_patients, per_patient_rows)。"""
    zs, ws, rows = [], [], []
    for pid, sub in g.groupby("Patient_ID"):
        n = len(sub)
        if n < 4:
            continue
        r, _ = spearmanr(sub.score, sub.el)
        if np.isnan(r):
            continue
        z = np.arctanh(np.clip(r, -0.999, 0.999)) - r / (2 * (n - 1))
        w = n - 3
        zs.append(z); ws.append(w)
        rows.append({"patient": pid, "n": n, "rho": r, "z": z, "weight": w})
    zs, ws = np.array(zs), np.array(ws)
    zbar = np.sum(zs * ws) / np.sum(ws)
    se = 1.0 / np.sqrt(np.sum(ws))
    return (np.tanh(zbar), np.tanh(zbar - 1.96 * se), np.tanh(zbar + 1.96 * se),
            len(zs), rows)


def main():
    backbone = load_backbone()

    tool_scores = {}
    for tool, (fname, col, _is_imm, _doi, _cav) in TOOL_META.items():
        if tool == "PRIME":
            tool_scores[tool] = prime_peptide_scores(backbone)
        else:
            df = backbone if fname == "DeepHLApan_merged_results.xlsx" \
                else pd.read_excel(os.path.join(TOOLS_DIR, fname))
            tool_scores[tool] = peptide_level_scores(df, col)

    metrics_rows, per_patient_rows = [], []
    for tool, g in tool_scores.items():
        _f, _c, is_imm, doi, cav = TOOL_META[tool]
        fz, lo, hi, npat, pp = fisher_z_weighted(g)
        gr, gp = spearmanr(g.score, g.el)
        lab = (g.el > 0).astype(int)
        auc = roc_auc_score(lab, g.score)
        metrics_rows.append({
            "Tool": tool,
            "is_immunogenicity_tool": is_imm,
            "n_peptides_total": 130,
            "n_peptides_covered": len(g),
            "FisherZ_rho": round(fz, 4),
            "FisherZ_95CI": "[%.3f, %.3f]" % (lo, hi),
            "FisherZ_n_patients": npat,
            "FisherZ_n_peptides": len(g),
            "FisherZ_significant": bool(lo > 0 or hi < 0),
            "Global_rho": round(gr, 4),
            "Global_p": round(gp, 6),
            "Global_n": len(g),
            "Global_significant": bool(gp < 0.05),
            "AUC": round(auc, 4),
            "AUC_n_pos": int(lab.sum()),
            "AUC_n_neg": int((1 - lab).sum()),
            "DOI": doi,
            "Caveat": cav,
        })
        for row in pp:
            per_patient_rows.append({**row, "Tool": tool})

    # 主指标降序（免疫原性工具优先看，HLAthena 单列）
    metrics = pd.DataFrame(metrics_rows).sort_values(
        "FisherZ_rho", ascending=False).reset_index(drop=True)
    metrics.to_csv(os.path.join(OUT_DIR, "metrics_three_tier.csv"), index=False)
    pd.DataFrame(per_patient_rows).to_csv(
        os.path.join(OUT_DIR, "per_patient_details.csv"), index=False)

    # 控制台速览
    print("\n=== 5 工具三层横评（主指标 = 患者内 Fisher-Z 加权 Spearman）===")
    print(metrics[["Tool", "is_immunogenicity_tool", "FisherZ_rho",
                   "FisherZ_95CI", "Global_rho", "AUC"]].to_string(index=False))
    print("\n结果已写入 results/metrics_three_tier.csv + results/per_patient_details.csv")
    return metrics


if __name__ == "__main__":
    main()
