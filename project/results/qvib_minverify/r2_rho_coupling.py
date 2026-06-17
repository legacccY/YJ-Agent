"""
R2 rho 耦合：ρ(predictive_entropy, qbar)，F/D/E，ITB-LQ + ITB-HQ
Pearson + Spearman r + p-value（纯 numpy，不用 scipy.stats）+ bootstrap 95% CI
输出: r2_rho_coupling.csv, r2_rho_summary.json
"""
import numpy as np
import pandas as pd
import json
import os

PRED_CSV = os.path.join(os.path.dirname(__file__), '../itb_predictions.csv')
OUT_DIR = os.path.dirname(__file__)
N_BOOT = 1000
SEED = 42

rng = np.random.default_rng(SEED)


def entropy_binary(p):
    p = np.clip(p, 1e-12, 1 - 1e-12)
    return -p * np.log(p) - (1 - p) * np.log(1 - p)


def pearson_r(x, y):
    xm = x - x.mean()
    ym = y - y.mean()
    denom = np.sqrt((xm ** 2).sum() * (ym ** 2).sum())
    if denom == 0:
        return 0.0
    return (xm * ym).sum() / denom


def spearman_r(x, y):
    """Spearman via rank then Pearson."""
    rx = _rank(x)
    ry = _rank(y)
    return pearson_r(rx, ry)


def _rank(x):
    """Average rank (numpy implementation)."""
    n = len(x)
    sorter = np.argsort(x)
    ranks = np.empty(n)
    ranks[sorter] = np.arange(n) + 1.0
    # handle ties: average rank
    # sort then find tie blocks
    sorted_x = x[sorter]
    i = 0
    while i < n:
        j = i + 1
        while j < n and sorted_x[j] == sorted_x[i]:
            j += 1
        avg = (sorter[i:j] + 1).mean()
        for k in range(i, j):
            ranks[sorter[k]] = avg
        i = j
    return ranks


def pearson_pvalue(r, n):
    """t-statistic based p-value (two-tailed)."""
    if abs(r) >= 1.0:
        return 0.0
    t = r * np.sqrt((n - 2) / (1 - r ** 2))
    # p-value approximation using erf-based normal CDF for large n
    # For moderate n use t-distribution approximation via regularized beta
    return _t_pvalue(t, n - 2)


def _t_pvalue(t, df):
    """Two-tailed p-value for t-statistic with df degrees of freedom.
    Uses approximation: for df>1, via incomplete beta function approximation.
    For df>30, close to normal.
    """
    # Use normal approximation for large df (df>30 gives <1% error)
    if df > 30:
        z = abs(t)
        p = 2 * (1 - _norm_cdf(z))
        return p
    # For small df, use series expansion of incomplete beta
    x = df / (df + t ** 2)
    p = _regularized_incomplete_beta(df / 2, 0.5, x)
    return float(p)


def _norm_cdf(x):
    """Normal CDF via erf."""
    return 0.5 * (1 + _erf(x / np.sqrt(2)))


def _erf(x):
    """erf approximation (Abramowitz & Stegun 7.1.26)."""
    t = 1.0 / (1.0 + 0.3275911 * abs(x))
    poly = t * (0.254829592 + t * (-0.284496736 + t * (1.421413741 + t * (-1.453152027 + t * 1.061405429))))
    result = 1.0 - poly * np.exp(-x ** 2)
    return np.where(x >= 0, result, -result) if isinstance(x, np.ndarray) else (result if x >= 0 else -result)


def _regularized_incomplete_beta(a, b, x):
    """Simplified regularized incomplete beta I_x(a,b) via continued fraction.
    Enough precision for p-value indication purposes.
    """
    # Use scipy-style continued fraction (Lentz) -- pure python
    if x < 0 or x > 1:
        return 0.0
    if x == 0:
        return 0.0
    if x == 1:
        return 1.0
    lbeta = _log_beta(a, b)
    front = np.exp(np.log(x) * a + np.log(1 - x) * b - lbeta) / a
    return front * _betacf(a, b, x)


def _log_beta(a, b):
    return _lgamma(a) + _lgamma(b) - _lgamma(a + b)


def _lgamma(x):
    # Stirling approximation for lgamma
    return float(np.log(np.math.gamma(float(x))))


def _betacf(a, b, x, max_iter=200, tol=1e-8):
    """Continued fraction for incomplete beta (Numerical Recipes)."""
    qab = a + b
    qap = a + 1
    qam = a - 1
    c = 1.0
    d = 1.0 - qab * x / qap
    if abs(d) < 1e-30:
        d = 1e-30
    d = 1.0 / d
    h = d
    for m in range(1, max_iter + 1):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        if abs(d) < 1e-30:
            d = 1e-30
        c = 1.0 + aa / c
        if abs(c) < 1e-30:
            c = 1e-30
        d = 1.0 / d
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d
        if abs(d) < 1e-30:
            d = 1e-30
        c = 1.0 + aa / c
        if abs(c) < 1e-30:
            c = 1e-30
        d = 1.0 / d
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < tol:
            break
    return h


def bootstrap_r(x, y, r_fn, n_boot=1000, rng=None):
    if rng is None:
        rng = np.random.default_rng(42)
    n = len(x)
    boot = np.empty(n_boot)
    for i in range(n_boot):
        idx = rng.integers(0, n, size=n)
        boot[i] = r_fn(x[idx], y[idx])
    return boot


def main():
    df = pd.read_csv(PRED_CSV)
    targets_baseline = ['D', 'E', 'F']
    names = {'D': 'Std VIB', 'E': 'Adaptive Prior', 'F': 'Q-VIB Full'}
    subsets = ['ITB-LQ', 'ITB-HQ']

    rows = []
    results_by_code = {}

    for subset in subsets:
        sub_df = df[df['subset'] == subset]
        print(f"\n=== {subset} ===")
        for code in targets_baseline:
            sub = sub_df[sub_df['baseline'] == code]
            if len(sub) == 0:
                print(f"  {code}: no data")
                continue
            p = sub['prob_pos'].values.astype(float)
            qbar = sub['qbar'].values.astype(float)
            H = entropy_binary(p)
            n = len(sub)

            r_p = pearson_r(H, qbar)
            r_s = spearman_r(H, qbar)
            pval_p = pearson_pvalue(r_p, n)
            pval_s = pearson_pvalue(r_s, n)  # approx p-val for Spearman

            boot_p = bootstrap_r(H, qbar, pearson_r, N_BOOT, rng)
            boot_s = bootstrap_r(H, qbar, spearman_r, N_BOOT, rng)
            ci_p = np.percentile(boot_p, [2.5, 97.5])
            ci_s = np.percentile(boot_s, [2.5, 97.5])

            row = {
                'subset': subset,
                'baseline': code,
                'baseline_name': names[code],
                'n': n,
                'pearson_r': round(r_p, 4),
                'pearson_pval': round(pval_p, 6),
                'pearson_CI_lo': round(ci_p[0], 4),
                'pearson_CI_hi': round(ci_p[1], 4),
                'spearman_r': round(r_s, 4),
                'spearman_pval': round(pval_s, 6),
                'spearman_CI_lo': round(ci_s[0], 4),
                'spearman_CI_hi': round(ci_s[1], 4),
            }
            rows.append(row)
            results_by_code[(subset, code)] = row
            print(f"  {code} ({names[code]}): Pearson r={r_p:.4f} p={pval_p:.4f} CI=[{ci_p[0]:.4f},{ci_p[1]:.4f}] | Spearman r={r_s:.4f} p={pval_s:.4f} CI=[{ci_s[0]:.4f},{ci_s[1]:.4f}]")

    result_df = pd.DataFrame(rows)
    result_df.to_csv(os.path.join(OUT_DIR, 'r2_rho_coupling.csv'), index=False)

    # Key comparison: F vs D in ITB-LQ, does F have significantly stronger rho?
    lq_f = results_by_code.get(('ITB-LQ', 'F'), {})
    lq_d = results_by_code.get(('ITB-LQ', 'D'), {})
    ci_overlap = False
    if lq_f and lq_d:
        # CIs overlap if F_lo < D_hi AND D_lo < F_hi (Pearson)
        f_lo, f_hi = lq_f['pearson_CI_lo'], lq_f['pearson_CI_hi']
        d_lo, d_hi = lq_d['pearson_CI_lo'], lq_d['pearson_CI_hi']
        ci_overlap = not (f_lo > d_hi or d_lo > f_hi)

    summary = {
        'ITB_LQ_pearson_r': {k: results_by_code.get(('ITB-LQ', k), {}).get('pearson_r', None) for k in targets_baseline},
        'ITB_LQ_spearman_r': {k: results_by_code.get(('ITB-LQ', k), {}).get('spearman_r', None) for k in targets_baseline},
        'ITB_HQ_pearson_r': {k: results_by_code.get(('ITB-HQ', k), {}).get('pearson_r', None) for k in targets_baseline},
        'F_vs_D_CI_overlap_Pearson_ITB_LQ': ci_overlap,
        'verdict': 'FAIL (F rho CI overlaps D, no significant coupling gain)' if ci_overlap else 'PASS (F rho CI does not overlap D)',
    }
    print(f"\nF vs D CI overlap (Pearson, ITB-LQ): {ci_overlap}")
    print(f"VERDICT: {summary['verdict']}")

    with open(os.path.join(OUT_DIR, 'r2_rho_summary.json'), 'w') as f:
        json.dump(summary, f, indent=2)

    print(f"\nOutputs: r2_rho_coupling.csv, r2_rho_summary.json")
    return summary


if __name__ == '__main__':
    main()
