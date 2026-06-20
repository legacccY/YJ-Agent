"""
reid_verdict_v2.py — Statistically-valid re-judgment of 致命-2 (re-ID 可归因).

WHY v2: the original `partial_corr_only` pooled 8 images x multiple epochs into
n=96 rows and ran partial correlation on them.  That is pseudoreplication
(Hurlbert 1984): the 96 rows are NOT independent — only 8 test images are.
n=96 is inflated, the CI is falsely narrow, the verdict (FAIL) is statistically
invalid, NOT evidence that memory has no effect.

This script re-analyses the SAME pilot data with the correct statistics
(no retraining).  Methodology from researcher fan-out (2026-06-20):
  - main test  : per-image PAIRED exact permutation test (n=8, 2^8=256 enum)
                 + paired Wilcoxon signed-rank cross-check + rank-biserial r
  - aux test   : linear mixed-effects model with random intercept per image,
                 reid_rate ~ C(memory_on) + epsilon_beta0 + (1|image_id)
                 (the random intercept is what correctly handles the repeated
                 per-image measurements that pseudoreplication ignored).

PRE-REGISTERED DUAL CRITERION (fixed BEFORE running, anti-HARKing):
  PASS  iff
    (permutation one-sided p < 0.05  AND  rank-biserial r > 0.5)
    AND
    (LMM C(memory_on)[T.1] coef > 0  AND  p < 0.05)
  Any sub-criterion failing  ->  cannot claim independent contribution.

PRE-REGISTERED checkpoint rule (objective, no cherry-pick):
  Each arm contributes its LAST eval epoch = its most-trained / converged state
  (A0' early-stopped at ep46 so ep40 is its final eval; A2 final eval ep80).

CAVEAT: n=8 images is LOW power.  Even a PASS here is PRELIMINARY and must be
confirmed on an expanded test set (more datasets/severities) before any paper
claim.  This pilot only tells us whether the direction justifies that full run.
"""
from __future__ import annotations
import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

RESULTS = Path(__file__).resolve().parent.parent / 'results' / 'reid_pilot_chase_20260620'
A2_CSV = RESULTS / 'a2_memory_reid_results.csv'
A0_CSV = RESULTS / 'a0_cnn_reid_results.csv'

# ------- pre-registered thresholds (hardcoded BEFORE computing) ------------- #
P_THRESH = 0.05
R_THRESH = 0.50            # rank-biserial (large effect)
LMM_P_THRESH = 0.05
# --------------------------------------------------------------------------- #


def load(csv):
    df = pd.read_csv(csv)
    df['epoch'] = pd.to_numeric(df['epoch'], errors='coerce')
    df = df.dropna(subset=['epoch'])
    df['epoch'] = df['epoch'].astype(int)
    for c in ('reid_rate', 'epsilon_beta0', 'success_rate'):
        df[c] = pd.to_numeric(df[c], errors='coerce')
    return df


def rank_biserial_from_wilcoxon(deltas):
    """rank-biserial r for one-sample (paired) Wilcoxon = (W+ - W-) / sum|ranks|."""
    d = np.asarray(deltas, dtype=float)
    d = d[d != 0]
    if len(d) == 0:
        return 0.0
    ranks = stats.rankdata(np.abs(d))
    r_plus = ranks[d > 0].sum()
    r_minus = ranks[d < 0].sum()
    return float((r_plus - r_minus) / ranks.sum())


def main():
    a2 = load(A2_CSV)
    a0 = load(A0_CSV)

    a2_ep = int(a2['epoch'].max())   # last eval epoch (most-trained)
    a0_ep = int(a0['epoch'].max())
    print(f'[checkpoint rule] A2 last-eval epoch={a2_ep}, A0 last-eval epoch={a0_ep}')

    a2_last = a2[a2['epoch'] == a2_ep].set_index('image_id')
    a0_last = a0[a0['epoch'] == a0_ep].set_index('image_id')
    imgs = sorted(set(a2_last.index) & set(a0_last.index))
    print(f'[pairing] n_images={len(imgs)} -> {imgs}')

    r_a2 = a2_last.loc[imgs, 'reid_rate'].to_numpy(dtype=float)
    r_a0 = a0_last.loc[imgs, 'reid_rate'].to_numpy(dtype=float)
    deltas = r_a2 - r_a0

    print('\n=== per-image reid_rate (A2 memory vs A0 cnn) ===')
    for im, x2, x0, d in zip(imgs, r_a2, r_a0, deltas):
        print(f'  {im}: A2={x2:.4f}  A0={x0:.4f}  delta={d:+.4f}')
    print(f'  mean A2={r_a2.mean():.4f}  mean A0={r_a0.mean():.4f}  '
          f'mean delta={deltas.mean():+.4f}  (A2 wins {int((deltas>0).sum())}/{len(deltas)})')

    # ---- main: exact paired permutation test, one-sided H1: delta > 0 ----- #
    def stat(x, y):
        return np.mean(x - y)
    perm = stats.permutation_test(
        (r_a2, r_a0), stat, permutation_type='samples',
        alternative='greater', n_resamples=10000, vectorized=False)
    # n=8 -> 2^8=256 < 10000 -> scipy does EXACT enumeration
    p_perm = float(perm.pvalue)

    # paired Wilcoxon cross-check (one-sided greater)
    try:
        w = stats.wilcoxon(r_a2, r_a0, alternative='greater')
        p_wil = float(w.pvalue)
    except Exception as e:
        p_wil = float('nan')
        print(f'  [wilcoxon] skipped: {e}')

    rbis = rank_biserial_from_wilcoxon(deltas)

    print('\n=== MAIN: per-image paired test (n=8) ===')
    print(f'  exact permutation (one-sided greater) p={p_perm:.4f}')
    print(f'  paired Wilcoxon  (one-sided greater)  p={p_wil:.4f}')
    print(f'  rank-biserial r = {rbis:.4f}')

    # ---- aux: LMM with random intercept per image (all epochs) ------------- #
    lmm_coef = lmm_p = None
    lmm_note = ''
    try:
        import statsmodels.formula.api as smf
        a2c = a2.copy(); a2c['memory_on'] = 1
        a0c = a0.copy(); a0c['memory_on'] = 0
        pooled = pd.concat([a2c, a0c], ignore_index=True)
        pooled = pooled.dropna(subset=['reid_rate', 'epsilon_beta0', 'image_id'])
        md = smf.mixedlm('reid_rate ~ C(memory_on) + epsilon_beta0',
                         pooled, groups=pooled['image_id'])
        mf = md.fit(method='lbfgs')
        key = [k for k in mf.params.index if 'memory_on' in k][0]
        lmm_coef = float(mf.params[key])
        lmm_p = float(mf.pvalues[key])
        print('\n=== AUX: linear mixed-effects model (1|image_id), all epochs ===')
        print(f'  reid_rate ~ C(memory_on) + epsilon_beta0 + (1|image_id)')
        print(f'  n_obs={int(mf.nobs)}  n_groups={pooled["image_id"].nunique()}')
        print(f'  {key}: coef={lmm_coef:+.4f}  p={lmm_p:.4f}')
    except Exception as e:
        lmm_note = f'LMM skipped: {e}'
        print(f'\n=== AUX: LMM ===\n  TODO {lmm_note}')

    # ---- pre-registered dual verdict -------------------------------------- #
    main_pass = (p_perm < P_THRESH) and (rbis > R_THRESH)
    lmm_pass = (lmm_coef is not None and lmm_coef > 0 and lmm_p < LMM_P_THRESH)
    overall = bool(main_pass and lmm_pass)

    print('\n=== PRE-REGISTERED DUAL VERDICT ===')
    print(f'  [main] permutation p<{P_THRESH} AND rank-biserial r>{R_THRESH}: '
          f'{main_pass}  (p={p_perm:.4f}, r={rbis:.4f})')
    print(f'  [aux ] LMM memory_on coef>0 AND p<{LMM_P_THRESH}: '
          f'{lmm_pass}  (coef={lmm_coef}, p={lmm_p})')
    print(f'  OVERALL: {"PASS" if overall else "FAIL"}')
    print('  NOTE: n=8 images = LOW power. Even PASS is PRELIMINARY; must be '
          'confirmed on expanded test set (more datasets/severities).')

    out = {
        'checkpoint_rule': f'each arm last eval epoch (A2={a2_ep}, A0={a0_ep})',
        'n_images': len(imgs),
        'per_image_delta': {im: float(d) for im, d in zip(imgs, deltas)},
        'mean_delta': float(deltas.mean()),
        'a2_wins': int((deltas > 0).sum()),
        'permutation_p_onesided': p_perm,
        'wilcoxon_p_onesided': p_wil,
        'rank_biserial_r': rbis,
        'lmm_memory_coef': lmm_coef,
        'lmm_memory_p': lmm_p,
        'lmm_note': lmm_note,
        'pre_registered_criterion':
            f'(perm p<{P_THRESH} AND r>{R_THRESH}) AND (LMM coef>0 AND p<{LMM_P_THRESH})',
        'main_pass': main_pass,
        'lmm_pass': lmm_pass,
        'overall_verdict': 'PASS' if overall else 'FAIL',
        'power_note': 'n=8 LOW power; PASS is preliminary, confirm on expanded set',
    }
    (RESULTS / 'verdict_v2.json').write_text(json.dumps(out, indent=2), encoding='utf-8')
    print(f'\n[written] {RESULTS / "verdict_v2.json"}')

    # ---- fig3: per-image paired delta bar --------------------------------- #
    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        fig, ax = plt.subplots(figsize=(7, 4))
        colors = ['#2c7fb8' if d > 0 else '#d95f0e' for d in deltas]
        ax.bar(range(len(imgs)), deltas, color=colors)
        ax.axhline(0, color='k', lw=0.8)
        ax.set_xticks(range(len(imgs)))
        ax.set_xticklabels(imgs, rotation=45, ha='right')
        ax.set_ylabel('reid_rate delta (A2 memory - A0 cnn)')
        ax.set_title(f'Per-image re-ID delta (A2@ep{a2_ep} vs A0@ep{a0_ep})\n'
                     f'perm p={p_perm:.3f}, r={rbis:.2f}, A2 wins {int((deltas>0).sum())}/8')
        fig.tight_layout()
        fig.savefig(RESULTS / 'fig3_paired_delta.png', dpi=130)
        print(f'[written] {RESULTS / "fig3_paired_delta.png"}')
    except Exception as e:
        print(f'[fig3 skipped] {e}')


if __name__ == '__main__':
    main()
