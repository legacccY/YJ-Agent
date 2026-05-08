"""ITB 评估指标计算。"""
import numpy as np
from sklearn.metrics import roc_auc_score, f1_score, accuracy_score, roc_curve


def compute_binary_ece(prob_pos: np.ndarray, targets: np.ndarray, n_bins: int = 10) -> float:
    """Classwise ECE for binary classification.

    Bins by prob_pos directly (not max-confidence), computes |fraction_positive - mean_prob|.
    Correct for imbalanced datasets where max-confidence ECE is dominated by the negative class.
    """
    bins = np.linspace(0, 1, n_bins + 1)
    ece = 0.0
    n = len(targets)
    for lo, hi in zip(bins[:-1], bins[1:]):
        mask = (prob_pos >= lo) & (prob_pos < hi)
        if mask.sum() < 3:
            continue
        frac_pos = targets[mask].mean()
        mean_prob = prob_pos[mask].mean()
        ece += (mask.sum() / n) * abs(frac_pos - mean_prob)
    return float(ece)


def compute_qbar_ece(prob_pos: np.ndarray, targets: np.ndarray, qbar: np.ndarray, n_bins: int = 5) -> list[dict]:
    """Classwise ECE and entropy per q̄ quantile bin."""
    edges = np.percentile(qbar, np.linspace(0, 100, n_bins + 1))
    results = []
    for lo, hi in zip(edges[:-1], edges[1:]):
        mask = (qbar >= lo) & (qbar <= hi)
        if mask.sum() < 5:
            continue
        ece = compute_binary_ece(prob_pos[mask], targets[mask])
        probs2 = np.stack([1 - prob_pos[mask], prob_pos[mask]], axis=1).clip(1e-9)
        entropy = float(-(probs2 * np.log(probs2)).sum(-1).mean())
        entropy_sem = float((-(probs2 * np.log(probs2)).sum(-1)).std() / np.sqrt(mask.sum()))
        auc = (float(roc_auc_score(targets[mask], prob_pos[mask]))
               if targets[mask].sum() > 0 and targets[mask].sum() < mask.sum() else float("nan"))
        results.append({
            "q_lo": float(lo), "q_hi": float(hi), "n": int(mask.sum()),
            "ece": ece, "auc": auc,
            "q_mean": float(qbar[mask].mean()),
            "entropy_mean": entropy, "entropy_sem": entropy_sem,
        })
    return results


def sensitivity_at_specificity(
    prob_pos: np.ndarray,
    targets: np.ndarray,
    target_spec: float = 0.95,
) -> float:
    """Sensitivity (TPR) at a fixed specificity level (clinical operating point).

    For melanoma screening, specificity >= 95% is the standard clinical threshold
    (Codella et al., ISIC 2018).  Returns NaN when the subset is all-positive or
    all-negative (AUC undefined).

    Args:
        prob_pos: Predicted positive probabilities, shape (N,).
        targets: Binary ground-truth labels, shape (N,).
        target_spec: Desired specificity level (default 0.95 → 95% specificity).

    Returns:
        Sensitivity (TPR) at the highest threshold where FPR <= 1 - target_spec.
    """
    if targets.sum() == 0 or targets.sum() == len(targets):
        return float("nan")
    fpr, tpr, _ = roc_curve(targets, prob_pos)
    # fpr = 1 - specificity; find first idx where fpr <= 1 - target_spec
    idx = np.searchsorted(fpr, 1.0 - target_spec)
    idx = min(idx, len(tpr) - 1)
    return float(tpr[idx])


def summary_metrics(prob_pos: np.ndarray, targets: np.ndarray, qbar: np.ndarray) -> dict:
    probs2 = np.stack([1 - prob_pos, prob_pos], axis=1)
    preds = probs2.argmax(-1)
    auc = (float(roc_auc_score(targets, prob_pos))
           if targets.sum() > 0 and targets.sum() < len(targets) else float("nan"))
    entropy_per_sample = -(probs2.clip(1e-9) * np.log(probs2.clip(1e-9))).sum(-1)
    sens95 = sensitivity_at_specificity(prob_pos, targets, target_spec=0.95)
    return {
        "auc": auc,
        "acc": float(accuracy_score(targets, preds)),
        "f1": float(f1_score(targets, preds, zero_division=0)),
        "ece": compute_binary_ece(prob_pos, targets),
        "mean_entropy": float(entropy_per_sample.mean()),
        "sensitivity_at_95spec": sens95,
        "qbar_ece_segments": compute_qbar_ece(prob_pos, targets, qbar),
    }
