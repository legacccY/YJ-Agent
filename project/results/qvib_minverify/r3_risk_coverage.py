"""
R3 risk-coverage（胜负手）：predictive entropy 排序做 selective prediction
AURC + risk-coverage 曲线 png，F vs A vs D，ITB-LQ
输出: r3_risk_coverage.csv, r3_aurc_summary.json, r3_risk_coverage_curve.png
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


def risk_coverage_curve(probs, targets, entropy):
    """
    Selective prediction: sort by entropy ascending (most certain first).
    At each coverage threshold, compute risk = error rate on retained samples.
    Returns coverages array, risks array.
    Risk = 1 - accuracy on retained (binary classification).
    """
    n = len(probs)
    order = np.argsort(entropy)  # ascending: most certain first
    probs_sorted = probs[order]
    targets_sorted = targets[order]

    preds_sorted = (probs_sorted >= 0.5).astype(int)
    correct_sorted = (preds_sorted == targets_sorted).astype(float)

    coverages = []
    risks = []
    # coverage = fraction retained; vary from 1/n to 1
    for k in range(1, n + 1):
        cov = k / n
        risk = 1.0 - correct_sorted[:k].mean()
        coverages.append(cov)
        risks.append(risk)

    return np.array(coverages), np.array(risks)


def aurc(coverages, risks):
    """Area Under Risk-Coverage curve via trapezoidal rule."""
    return float(np.trapz(risks, coverages))


def bootstrap_aurc(probs, targets, entropy, n_boot=1000, rng=None):
    if rng is None:
        rng = np.random.default_rng(42)
    n = len(probs)
    boot_vals = np.empty(n_boot)
    for i in range(n_boot):
        idx = rng.integers(0, n, size=n)
        c, r = risk_coverage_curve(probs[idx], targets[idx], entropy[idx])
        boot_vals[i] = aurc(c, r)
    return boot_vals


def main():
    df = pd.read_csv(PRED_CSV)
    lq = df[df['subset'] == 'ITB-LQ'].copy()
    print(f"ITB-LQ n={len(lq)}")

    targets_baseline = ['A', 'D', 'F']
    names = {'A': 'EfficientNet-B3 (Direct)', 'D': 'Std VIB', 'F': 'Q-VIB Full'}

    rows = []
    results = {}
    curve_data = {}

    for code in targets_baseline:
        sub = lq[lq['baseline'] == code]
        p = sub['prob_pos'].values.astype(float)
        y = sub['target'].values.astype(float)
        H = entropy_binary(p)

        cov, risk = risk_coverage_curve(p, y, H)
        aurc_val = aurc(cov, risk)
        boot = bootstrap_aurc(p, y, H, N_BOOT, rng)
        ci_lo, ci_hi = np.percentile(boot, [2.5, 97.5])

        row = {
            'baseline': code,
            'baseline_name': names[code],
            'n': len(sub),
            'AURC': round(aurc_val, 5),
            'CI_lo': round(ci_lo, 5),
            'CI_hi': round(ci_hi, 5),
        }
        rows.append(row)
        results[code] = row
        curve_data[code] = (cov, risk, names[code])
        print(f"  {code} ({names[code]}): AURC={aurc_val:.5f} [{ci_lo:.5f}, {ci_hi:.5f}]")

    result_df = pd.DataFrame(rows)
    result_df.to_csv(os.path.join(OUT_DIR, 'r3_risk_coverage.csv'), index=False)

    # Key: F AURC < A AURC? (lower = better selective prediction)
    f_aurc = results['F']['AURC']
    a_aurc = results['A']['AURC']
    f_better_than_a = f_aurc < a_aurc

    # CI overlap check F vs A
    f_lo, f_hi = results['F']['CI_lo'], results['F']['CI_hi']
    a_lo, a_hi = results['A']['CI_lo'], results['A']['CI_hi']
    ci_overlap_fa = not (f_lo > a_hi or a_lo > f_hi)

    summary = {
        'AURC_F': round(f_aurc, 5),
        'AURC_A': round(a_aurc, 5),
        'AURC_D': round(results['D']['AURC'], 5),
        'F_AURC_lt_A': bool(f_better_than_a),
        'F_vs_A_CI_overlap': bool(ci_overlap_fa),
        'verdict': ('PASS (F AURC < A, F wins selective prediction)' if (f_better_than_a and not ci_overlap_fa)
                    else ('MARGINAL (F < A but CI overlaps)' if (f_better_than_a and ci_overlap_fa)
                          else 'FAIL (F AURC >= A, no selective prediction win)')),
    }
    print(f"\nF AURC={f_aurc:.5f} vs A AURC={a_aurc:.5f}, F<A={f_better_than_a}, CI_overlap={ci_overlap_fa}")
    print(f"VERDICT: {summary['verdict']}")

    with open(os.path.join(OUT_DIR, 'r3_aurc_summary.json'), 'w') as f:
        json.dump(summary, f, indent=2)

    # Plot
    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt

        colors = {'A': '#2196F3', 'D': '#FF9800', 'F': '#E91E63'}
        fig, ax = plt.subplots(figsize=(7, 5))
        for code in targets_baseline:
            cov, risk, name = curve_data[code]
            ax.plot(cov, risk, color=colors[code], label=f"{code}: {name}\nAURC={results[code]['AURC']:.4f}", lw=1.8)
        ax.set_xlabel('Coverage', fontsize=12)
        ax.set_ylabel('Risk (1 - Accuracy)', fontsize=12)
        ax.set_title('Risk-Coverage Curve — ITB-LQ\n(lower AURC = better selective prediction)', fontsize=11)
        ax.legend(fontsize=9)
        ax.grid(True, alpha=0.3)
        fig.tight_layout()
        png_path = os.path.join(OUT_DIR, 'r3_risk_coverage_curve.png')
        fig.savefig(png_path, dpi=150)
        plt.close()
        print(f"Curve saved: {png_path}")
        summary['curve_png'] = png_path
        with open(os.path.join(OUT_DIR, 'r3_aurc_summary.json'), 'w') as f:
            json.dump(summary, f, indent=2)
    except ImportError:
        print("matplotlib not available, skipping plot")
        summary['curve_png'] = None

    print(f"\nOutputs: r3_risk_coverage.csv, r3_aurc_summary.json, r3_risk_coverage_curve.png")
    return summary


if __name__ == '__main__':
    main()
