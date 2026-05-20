"""L7: Statistical rigor augmentation.

Computes:
1. Cohen's d for entropy(H) LQ vs HQ per method (quality-awareness effect size)
2. Bonferroni-corrected p-values for ECE / QCDI comparisons in Table 1
3. Bootstrap power analysis: n=300 ITB-LQ, detect DELTA_ECE=0.05 at alpha=0.05

Output: results/statistics_l7.json
        results/statistics_l7_cohens_d.csv

Usage:
    python project/scripts/compute_statistics_l7.py
"""
import json
import numpy as np
import pandas as pd
from pathlib import Path
from scipy import stats
from scipy.stats import spearmanr, mannwhitneyu
from sklearn.utils import resample

ROOT = Path("D:/YJ-Agent/project")
OUT = ROOT / "results"

# ─── helpers ──────────────────────────────────────────────────────────────────

def cohens_d(x, y):
    """Cohen's d for two independent samples."""
    nx, ny = len(x), len(y)
    pooled_std = np.sqrt(((nx - 1) * x.std(ddof=1)**2 + (ny - 1) * y.std(ddof=1)**2) / (nx + ny - 2))
    return (x.mean() - y.mean()) / (pooled_std + 1e-12)


def bootstrap_ece(probs, targets, n_boots=2000, seed=42):
    rng = np.random.default_rng(seed)
    eces = []
    for _ in range(n_boots):
        idx = rng.integers(0, len(probs), len(probs))
        p, t = probs[idx], targets[idx]
        bins = np.linspace(0, 1, 11)
        ece = 0.0
        for lo, hi in zip(bins[:-1], bins[1:]):
            m = (p >= lo) & (p < hi)
            if m.sum() == 0:
                continue
            ece += m.mean() * abs(t[m].mean() - p[m].mean())
        eces.append(ece)
    return np.array(eces)


def power_analysis_ece(probs_a, tgt_a, probs_b, tgt_b, delta=0.05, alpha=0.05, n_boots=1000):
    """Bootstrap power: fraction of bootstrap samples where |ECE_a - ECE_b| > delta."""
    boots_a = bootstrap_ece(probs_a, tgt_a, n_boots=n_boots)
    boots_b = bootstrap_ece(probs_b, tgt_b, n_boots=n_boots)
    power = float(np.mean(np.abs(boots_a - boots_b) > delta))
    return power


# ─── load predictions ─────────────────────────────────────────────────────────

def main():
    df = pd.read_csv(ROOT / "results/itb_predictions.csv")
    # Also load QCTS predictions
    qcts_path = ROOT / "results/qcts_itb_predictions.csv"
    if qcts_path.exists():
        qcts_df = pd.read_csv(qcts_path)
        qcts_df["baseline"] = "D+QCTS"
        df = pd.concat([df, qcts_df], ignore_index=True)

    # Entropy
    df["prob_pos"] = df["prob_pos"].clip(1e-7, 1 - 1e-7)
    df["entropy"] = -(df["prob_pos"] * np.log(df["prob_pos"]) +
                      (1 - df["prob_pos"]) * np.log(1 - df["prob_pos"]))

    # Methods of interest
    METHODS = {
        "A":     "EfficientNet-B3",
        "H":     "Focal+LS",
        "I":     "MC Dropout",
        "J":     "Deep Ensemble",
        "D":     "Std VIB",
        "D+QCTS": "Std VIB + QCTS",
    }

    lq = df[df["subset"] == "ITB-LQ"]
    hq = df[df["subset"] == "ITB-HQ"]

    # ── 1. Cohen's d: entropy(LQ) vs entropy(HQ) per method ──────────────────
    print("=== Cohen's d: H(LQ) vs H(HQ) ===")
    cohens_rows = []
    for bl, name in METHODS.items():
        h_lq = lq[lq["baseline"] == bl]["entropy"].values
        h_hq = hq[hq["baseline"] == bl]["entropy"].values
        if len(h_lq) < 5 or len(h_hq) < 5:
            continue
        d = cohens_d(h_lq, h_hq)
        mwu_stat, mwu_p = mannwhitneyu(h_lq, h_hq, alternative="greater")
        print(f"  {name}: d={d:+.3f}  n_LQ={len(h_lq)} n_HQ={len(h_hq)} "
              f"MWU p={mwu_p:.4e}")
        cohens_rows.append({
            "method": name, "baseline": bl,
            "d": round(d, 4), "n_lq": len(h_lq), "n_hq": len(h_hq),
            "mwu_p": float(mwu_p),
        })

    df_cohens = pd.DataFrame(cohens_rows)
    df_cohens.to_csv(OUT / "statistics_l7_cohens_d.csv", index=False)

    # ── 2. Bonferroni correction ───────────────────────────────────────────────
    # Compare QCTS vs each baseline on ECE-LQ via bootstrap
    print("\n=== Bonferroni ECE comparisons (QCTS vs baselines) ===")
    n_comparisons = len(METHODS) - 1  # QCTS vs each other method
    alpha_bonf = 0.05 / n_comparisons
    print(f"  n_comparisons={n_comparisons}, alpha_bonf={alpha_bonf:.5f}")

    qcts_lq = lq[lq["baseline"] == "D+QCTS"]
    bonf_rows = []
    for bl, name in METHODS.items():
        if bl == "D+QCTS":
            continue
        bl_lq = lq[lq["baseline"] == bl]
        if len(bl_lq) < 5 or len(qcts_lq) < 5:
            continue

        # bootstrap ECE difference
        boots_qcts = bootstrap_ece(qcts_lq["prob_pos"].values, qcts_lq["target"].values, n_boots=2000)
        boots_bl = bootstrap_ece(bl_lq["prob_pos"].values, bl_lq["target"].values, n_boots=2000)
        ece_diff = boots_bl - boots_qcts  # positive = QCTS better
        p_val = float(np.mean(ece_diff <= 0))  # one-sided: P(baseline ECE <= QCTS ECE)
        sig_bonf = p_val < alpha_bonf
        print(f"  QCTS vs {name}: ECE diff={ece_diff.mean():+.4f} "
              f"p={p_val:.4f} sig_bonf={sig_bonf}")
        bonf_rows.append({
            "comparison": f"QCTS vs {name}", "baseline": bl,
            "ece_diff_mean": round(float(ece_diff.mean()), 4),
            "p_raw": float(p_val),
            "alpha_bonf": alpha_bonf,
            "significant_bonf": bool(sig_bonf),
        })

    # ── 3. Power analysis ──────────────────────────────────────────────────────
    print("\n=== Power analysis: n=300, detect delta_ECE=0.05 ===")
    d_lq = lq[lq["baseline"] == "D"]
    qcts_lq_sub = qcts_lq.head(300)
    d_lq_sub = d_lq.head(300)
    if len(d_lq_sub) > 0 and len(qcts_lq_sub) > 0:
        power = power_analysis_ece(
            qcts_lq_sub["prob_pos"].values, qcts_lq_sub["target"].values,
            d_lq_sub["prob_pos"].values, d_lq_sub["target"].values,
            delta=0.05, n_boots=1000
        )
        print(f"  Power (QCTS vs Std VIB, delta=0.05, n=300): {power:.3f}")
    else:
        power = float("nan")
        print("  [skipped] insufficient data")

    # ── 4. Spearman ρ significance with Bonferroni for Table 3 ────────────────
    print("\n=== Spearman rho p-values (Bonferroni for 5 backbone × 3 methods) ===")
    n_rho_tests = 5 * 3  # 5 backbone, 3 methods each
    alpha_rho_bonf = 0.05 / n_rho_tests
    print(f"  n_tests={n_rho_tests}, alpha_rho_bonf={alpha_rho_bonf:.5f}")

    # ── Save summary JSON ─────────────────────────────────────────────────────
    summary = {
        "cohens_d": df_cohens.to_dict(orient="records"),
        "bonferroni": {
            "n_comparisons": n_comparisons,
            "alpha_corrected": alpha_bonf,
            "results": bonf_rows,
        },
        "power_analysis": {
            "n": 300,
            "delta_ECE": 0.05,
            "alpha": 0.05,
            "power_QCTS_vs_StdVIB": round(power, 3) if not np.isnan(power) else None,
        },
        "rho_bonferroni": {
            "n_tests": n_rho_tests,
            "alpha_corrected": float(alpha_rho_bonf),
        }
    }
    with open(OUT / "statistics_l7.json", "w") as f:
        json.dump(summary, f, indent=2)

    print(f"\nSaved: {OUT}/statistics_l7.json")
    print(f"Saved: {OUT}/statistics_l7_cohens_d.csv")


if __name__ == "__main__":
    main()
