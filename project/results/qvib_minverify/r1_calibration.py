"""
R1 校准增量：ECE + bootstrap 95% CI，ITB-LQ，F vs D vs A
输出: r1_calibration.csv, r1_calibration_summary.json
"""
import numpy as np
import pandas as pd
import json
import os

PRED_CSV = os.path.join(os.path.dirname(__file__), '../itb_predictions.csv')
OUT_DIR = os.path.dirname(__file__)
N_BOOT = 1000
N_BINS = 10
SEED = 42

rng = np.random.default_rng(SEED)


def ece(probs, labels, n_bins=10):
    """Expected Calibration Error, equal-width bins."""
    bins = np.linspace(0, 1, n_bins + 1)
    ece_val = 0.0
    for i in range(n_bins):
        mask = (probs >= bins[i]) & (probs < bins[i + 1])
        if i == n_bins - 1:
            mask = (probs >= bins[i]) & (probs <= bins[i + 1])
        n = mask.sum()
        if n == 0:
            continue
        acc = labels[mask].mean()
        conf = probs[mask].mean()
        ece_val += (n / len(probs)) * abs(acc - conf)
    return ece_val


def bootstrap_ece(probs, labels, n_boot=1000, n_bins=10, rng=None):
    if rng is None:
        rng = np.random.default_rng(42)
    n = len(probs)
    boot_vals = np.empty(n_boot)
    for i in range(n_boot):
        idx = rng.integers(0, n, size=n)
        boot_vals[i] = ece(probs[idx], labels[idx], n_bins)
    return boot_vals


def main():
    df = pd.read_csv(PRED_CSV)
    lq = df[df['subset'] == 'ITB-LQ'].copy()
    print(f"ITB-LQ n={len(lq)}, baselines: {lq['baseline'].unique()}")

    targets = ['A', 'D', 'F']
    names = {'A': 'EfficientNet-B3 (Direct)', 'D': 'Std VIB', 'F': 'Q-VIB Full'}
    rows = []
    results = {}

    for code in targets:
        sub = lq[lq['baseline'] == code]
        probs = sub['prob_pos'].values.astype(float)
        labels = sub['target'].values.astype(float)
        ece_val = ece(probs, labels, N_BINS)
        boot = bootstrap_ece(probs, labels, N_BOOT, N_BINS, rng)
        ci_lo, ci_hi = np.percentile(boot, [2.5, 97.5])
        rows.append({
            'baseline': code,
            'baseline_name': names[code],
            'n': len(sub),
            'ECE': round(ece_val, 5),
            'CI_lo': round(ci_lo, 5),
            'CI_hi': round(ci_hi, 5),
        })
        results[code] = {'ECE': ece_val, 'CI_lo': ci_lo, 'CI_hi': ci_hi}
        print(f"  {code} ({names[code]}): ECE={ece_val:.4f} [{ci_lo:.4f}, {ci_hi:.4f}]")

    result_df = pd.DataFrame(rows)
    result_df.to_csv(os.path.join(OUT_DIR, 'r1_calibration.csv'), index=False)

    # F vs D delta ECE + CI
    f_ece = results['F']['ECE']
    d_ece = results['D']['ECE']
    delta = f_ece - d_ece
    # Bootstrap delta
    lq_f = lq[lq['baseline'] == 'F']
    lq_d = lq[lq['baseline'] == 'D']
    p_f = lq_f['prob_pos'].values.astype(float)
    y_f = lq_f['target'].values.astype(float)
    p_d = lq_d['prob_pos'].values.astype(float)
    y_d = lq_d['target'].values.astype(float)

    n_f = len(p_f)
    n_d = len(p_d)
    delta_boot = np.empty(N_BOOT)
    for i in range(N_BOOT):
        idx_f = rng.integers(0, n_f, size=n_f)
        idx_d = rng.integers(0, n_d, size=n_d)
        delta_boot[i] = ece(p_f[idx_f], y_f[idx_f], N_BINS) - ece(p_d[idx_d], y_d[idx_d], N_BINS)

    dci_lo, dci_hi = np.percentile(delta_boot, [2.5, 97.5])
    contains_zero = (dci_lo <= 0 <= dci_hi)

    summary = {
        'ECE_F': round(f_ece, 5),
        'ECE_D': round(d_ece, 5),
        'ECE_A': round(results['A']['ECE'], 5),
        'delta_F_minus_D': round(delta, 5),
        'delta_CI_lo': round(dci_lo, 5),
        'delta_CI_hi': round(dci_hi, 5),
        'delta_CI_contains_zero': bool(contains_zero),
        'verdict': 'FAIL (CI contains 0, no calibration gain)' if contains_zero else 'PASS (CI excludes 0)',
    }
    print(f"\nF-D delta ECE={delta:.4f} CI=[{dci_lo:.4f}, {dci_hi:.4f}] contains_zero={contains_zero}")
    print(f"VERDICT: {summary['verdict']}")

    with open(os.path.join(OUT_DIR, 'r1_calibration_summary.json'), 'w') as f:
        json.dump(summary, f, indent=2)

    print(f"\nOutputs: r1_calibration.csv, r1_calibration_summary.json")
    return summary


if __name__ == '__main__':
    main()
