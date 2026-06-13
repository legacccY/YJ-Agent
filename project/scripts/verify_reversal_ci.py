"""Bootstrap-CI verification of the TS-reversal forward decomposition (BMVC §5.2 / A1).

Recomputes the three-way forward Spearman correlations rho_a (MC) -> rho_b (det-mu)
-> rho_c (det+TS) directly from per-sample probabilities, with 95% bootstrap CIs on
each rho and on the a->b flip. This hardens the submitted point estimates
(rho_a=-0.163, rho_b=+0.241) with interval evidence for rebuttal.

Pure recompute from results/forward_ablation_stdvib.csv -- no model forward, no GPU,
does NOT touch the sealed meeting/BMVC/ directory.

Run:  python scripts/verify_reversal_ci.py
Out:  results/reversal_ci_verification.csv
"""
from pathlib import Path
import numpy as np
import pandas as pd
from scipy.stats import spearmanr

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "results" / "forward_ablation_stdvib.csv"
OUT = ROOT / "results" / "reversal_ci_verification.csv"

B = 5000          # bootstrap resamples
SEED = 0          # fixed -> reproducible CIs


def entropy(p):
    p = np.clip(p, 1e-12, 1.0 - 1e-12)
    return -(p * np.log(p) + (1.0 - p) * np.log1p(-p))


def main():
    df = pd.read_csv(SRC)
    q = df["qbar"].values
    n = len(df)
    rng = np.random.default_rng(SEED)

    forwards = {  # label -> column of per-sample positive-class prob
        "rho_a_MC": "p_mc",
        "rho_b_det_mu": "p_det",
        "rho_c_det_TS": "p_ts",
    }

    rows = []
    point = {}
    for label, col in forwards.items():
        h = entropy(df[col].values)
        rho = spearmanr(h, q).statistic
        point[label] = rho
        boot = np.empty(B)
        for b in range(B):
            idx = rng.integers(0, n, n)
            boot[b] = spearmanr(h[idx], q[idx]).statistic
        lo, hi = np.percentile(boot, [2.5, 97.5])
        rows.append(dict(quantity=label, value=round(rho, 4),
                         ci_lo=round(lo, 4), ci_hi=round(hi, 4),
                         crosses_zero=bool(lo < 0 < hi)))

    # paired bootstrap on the a->b flip (the substantive, non-mathematical step)
    ha, hb = entropy(df["p_mc"].values), entropy(df["p_det"].values)
    diffs = np.empty(B)
    for b in range(B):
        idx = rng.integers(0, n, n)
        diffs[b] = spearmanr(hb[idx], q[idx]).statistic - spearmanr(ha[idx], q[idx]).statistic
    lo, hi = np.percentile(diffs, [2.5, 97.5])
    rows.append(dict(quantity="delta_rho_a_to_b", value=round(point["rho_b_det_mu"] - point["rho_a_MC"], 4),
                     ci_lo=round(lo, 4), ci_hi=round(hi, 4), crosses_zero=bool(lo < 0 < hi)))
    rows.append(dict(quantity="delta_rho_b_to_c_TS_step",
                     value=float(point["rho_c_det_TS"] - point["rho_b_det_mu"]),
                     ci_lo=np.nan, ci_hi=np.nan, crosses_zero=False))

    out = pd.DataFrame(rows)
    out.insert(0, "n_samples", n)
    out.insert(1, "n_bootstrap", B)
    out.to_csv(OUT, index=False)
    print(out.to_string(index=False))
    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    main()
