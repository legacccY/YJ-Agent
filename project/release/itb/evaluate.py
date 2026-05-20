"""Run ITB evaluation for a set of predictions."""
import json
from pathlib import Path

import numpy as np
import pandas as pd

from .metrics import qcdi as compute_qcdi, binary_entropy, spearman_rho, bootstrap_ci


def evaluate_on_itb(
    prob_pos: np.ndarray,
    targets: np.ndarray,
    qbar: np.ndarray,
    subset: np.ndarray,
    method_name: str = "model",
    n_boot: int = 10000,
) -> dict:
    """Compute the full ITB evaluation report for one method.

    Args:
        prob_pos: Predicted positive-class probabilities [N].
        targets:  Binary ground-truth labels [N].
        qbar:     Per-image quality scores in [0, 1] [N].
        subset:   ITB subset label ('ITB-LQ', 'ITB-HQ', ...) [N].
        method_name: Display name for the method.
        n_boot:   Bootstrap resamples for CIs.

    Returns:
        dict with ECE/QCDI/rho metrics and bootstrap CIs.
    """
    entropy = binary_entropy(prob_pos)
    result = {"method": method_name, "n_total": len(prob_pos)}

    # ── QCDI on full ITB-LQ/HQ pool ─────────────────────────────────────────
    q = compute_qcdi(prob_pos, targets, qbar)
    result.update(q)

    # ── Spearman rho (full pool) ─────────────────────────────────────────────
    rho, rho_p = spearman_rho(entropy, qbar)
    result["rho"] = rho
    result["rho_p"] = rho_p

    # Bootstrap CI on rho
    def _rho(e, q):
        from scipy.stats import spearmanr
        return spearmanr(e, q).statistic

    ci_lo, ci_hi = bootstrap_ci(_rho, entropy, qbar, n_boot=n_boot)
    result["rho_ci"] = [ci_lo, ci_hi]

    # ── Per-subset ECE ───────────────────────────────────────────────────────
    from .metrics import ece
    for sub in ["ITB-LQ", "ITB-HQ", "ITB-Edge", "ITB-Diverse"]:
        m = subset == sub
        if m.sum() < 5:
            continue
        result[f"ece_{sub.lower().replace('-', '_')}"] = ece(prob_pos[m], targets[m])

    # Bootstrap CI on QCDI
    lq_mask = qbar < 0.45
    hq_mask = qbar > 0.50
    if lq_mask.sum() >= 10 and hq_mask.sum() >= 10:
        def _qcdi_stat(p, t, q):
            lq, hq = q < 0.45, q > 0.50
            return ece(p[lq], t[lq]) - ece(p[hq], t[hq])

        qcdi_lo, qcdi_hi = bootstrap_ci(
            _qcdi_stat, prob_pos, targets, qbar, n_boot=n_boot
        )
        result["qcdi_ci"] = [qcdi_lo, qcdi_hi]

    return result
