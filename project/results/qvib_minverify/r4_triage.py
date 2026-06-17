"""
R4 triage 复核：读 results/dca/ 现有产物，核 C-β（triage 反超）
若有 triage_results.csv 直接读；补算 F 的 sens_auto（itb_predictions.csv 里有 F）
输出: r4_triage_summary.json
"""
import numpy as np
import pandas as pd
import json
import os

PRED_CSV = os.path.join(os.path.dirname(__file__), '../itb_predictions.csv')
DCA_DIR = os.path.join(os.path.dirname(__file__), '../dca')
OUT_DIR = os.path.dirname(__file__)


def entropy_binary(p):
    p = np.clip(p, 1e-12, 1 - 1e-12)
    return -p * np.log(p) - (1 - p) * np.log(1 - p)


def compute_triage_at_referral(probs, targets, qbar=None, referral_rate=0.2, use_joint=False):
    """
    Triage: route lowest-confidence cases to specialist.
    Confidence = 1 - entropy (or combined with qbar if use_joint).
    Referral = bottom `referral_rate` fraction by confidence → referred to specialist.
    Auto-diagnosed = rest.
    sens_auto = sensitivity among auto-diagnosed positives.
    """
    H = entropy_binary(probs)
    if use_joint and qbar is not None:
        # joint score: lower entropy AND lower qbar = more confident
        # normalize both to [0,1] then average
        H_norm = (H - H.min()) / (H.max() - H.min() + 1e-12)
        q_norm = (qbar - qbar.min()) / (qbar.max() - qbar.min() + 1e-12)
        uncertainty = 0.5 * H_norm + 0.5 * q_norm
    else:
        uncertainty = H

    n = len(probs)
    n_refer = int(np.round(referral_rate * n))
    # Sort by uncertainty descending: most uncertain first = referred
    order_desc = np.argsort(-uncertainty)
    referred_idx = order_desc[:n_refer]
    auto_idx = order_desc[n_refer:]

    auto_mask = np.zeros(n, dtype=bool)
    auto_mask[auto_idx] = True

    preds = (probs >= 0.5).astype(int)
    positives = (targets == 1)

    # sens_auto: among positives, what fraction were auto-diagnosed correctly
    pos_auto = positives & auto_mask
    pos_all = positives.sum()
    tp_auto = (preds[pos_auto] == 1).sum() if pos_auto.sum() > 0 else 0
    sens_auto = tp_auto / pos_all if pos_all > 0 else 0.0

    actual_referral = n_refer / n
    missed_pos = positives[referred_idx].sum()
    missed_pos_rate = missed_pos / pos_all if pos_all > 0 else 0.0

    return {
        'referral_rate': round(actual_referral, 4),
        'sens_auto': round(sens_auto, 4),
        'missed_positive_rate': round(missed_pos_rate, 4),
        'n_refer': int(n_refer),
        'n_auto': int(n - n_refer),
        'n_positives': int(pos_all),
    }


def main():
    # Load existing triage results
    triage_csv = os.path.join(DCA_DIR, 'triage_results.csv')
    dca_summary_json = os.path.join(DCA_DIR, 'dca_summary.json')

    existing_triage = None
    dca_summary = None

    if os.path.exists(triage_csv):
        existing_triage = pd.read_csv(triage_csv)
        print(f"Loaded triage_results.csv: {existing_triage.shape}, baselines={existing_triage['baseline'].unique()}")
    else:
        print("WARNING: triage_results.csv not found")

    if os.path.exists(dca_summary_json):
        with open(dca_summary_json) as f:
            dca_summary = json.load(f)
        print(f"Loaded dca_summary.json")

    # Load predictions for all baselines including F
    df = pd.read_csv(PRED_CSV)
    lq = df[df['subset'] == 'ITB-LQ'].copy()
    print(f"\nITB-LQ n={len(lq)}, baselines available: {sorted(lq['baseline'].unique())}")

    # Compute triage for F, A, D at 20% referral
    referral_rate = 0.20
    targets_baseline = ['A', 'D', 'F']
    names = {'A': 'EfficientNet-B3 (Direct)', 'D': 'Std VIB', 'F': 'Q-VIB Full'}

    computed = {}
    print(f"\n=== Computed triage @{referral_rate*100:.0f}% referral (entropy-based) ===")
    for code in targets_baseline:
        sub = lq[lq['baseline'] == code]
        p = sub['prob_pos'].values.astype(float)
        y = sub['target'].values.astype(float)
        q = sub['qbar'].values.astype(float) if 'qbar' in sub.columns else None

        res_entropy = compute_triage_at_referral(p, y, q, referral_rate, use_joint=False)
        res_joint = compute_triage_at_referral(p, y, q, referral_rate, use_joint=True) if q is not None else None

        computed[code] = {'entropy': res_entropy, 'joint': res_joint}
        print(f"  {code} ({names[code]}): entropy-only sens_auto={res_entropy['sens_auto']:.4f} missed_pos={res_entropy['missed_positive_rate']:.4f}")
        if res_joint:
            print(f"    joint(entropy+qbar) sens_auto={res_joint['sens_auto']:.4f} missed_pos={res_joint['missed_positive_rate']:.4f}")

    # Check DCA summary existing numbers
    existing_sens_auto = {}
    if dca_summary and 'triage_at_20pct_referral' in dca_summary:
        print("\n=== Existing dca_summary triage@20% ===")
        for method, vals in dca_summary['triage_at_20pct_referral'].items():
            print(f"  {method}: sens_auto={vals.get('sens_auto', 'N/A')}")
            existing_sens_auto[method] = vals.get('sens_auto', None)

    # Key question: C-β — does F's triage beat A?
    f_sens = computed['F']['entropy']['sens_auto']
    a_sens = computed['A']['entropy']['sens_auto']
    d_sens = computed['D']['entropy']['sens_auto']
    f_beats_a = f_sens > a_sens

    # Also check joint version
    f_sens_joint = computed['F']['joint']['sens_auto'] if computed['F']['joint'] else None
    f_beats_a_joint = (f_sens_joint > a_sens) if f_sens_joint is not None else None

    # Net benefit from DCA
    dca_f_nb = None
    dca_a_nb = None
    if dca_summary and 'dca_max_nb' in dca_summary:
        # Map method names
        for k, v in dca_summary['dca_max_nb'].items():
            if 'Q-VIB' in k and 'TokFT' not in k:
                pass  # F not in old summary (used G/D only)
        dca_f_nb = dca_summary['dca_max_nb'].get('Q-VIB Full', None)
        dca_a_nb = dca_summary['dca_max_nb'].get('EfficientNet-B3', None)

    summary = {
        'sens_auto_F_entropy': f_sens,
        'sens_auto_A_entropy': a_sens,
        'sens_auto_D_entropy': d_sens,
        'sens_auto_F_joint_entropy_qbar': f_sens_joint,
        'F_beats_A_entropy': bool(f_beats_a),
        'F_beats_A_joint': bool(f_beats_a_joint) if f_beats_a_joint is not None else None,
        'dca_max_nb_F': dca_f_nb,
        'dca_max_nb_A': dca_a_nb,
        'existing_dca_summary_triage': existing_sens_auto,
        'referral_rate_used': referral_rate,
        'verdict': ('PASS (C-β: F sens_auto > A at 20% referral)' if f_beats_a
                    else 'FAIL (C-β: F sens_auto <= A, triage not better)'),
    }
    print(f"\nC-β triage@20%: F sens_auto={f_sens:.4f} vs A sens_auto={a_sens:.4f}")
    print(f"F beats A (entropy): {f_beats_a}")
    print(f"VERDICT: {summary['verdict']}")

    with open(os.path.join(OUT_DIR, 'r4_triage_summary.json'), 'w') as f:
        json.dump(summary, f, indent=2)

    print(f"\nOutput: r4_triage_summary.json")
    return summary


if __name__ == '__main__':
    main()
