"""Core calibration metrics for ITB evaluation."""
import numpy as np
from scipy.stats import spearmanr


def ece(prob: np.ndarray, targets: np.ndarray, n_bins: int = 15) -> float:
    """Expected Calibration Error (equal-width bins)."""
    bins = np.linspace(0, 1, n_bins + 1)
    total, n = 0.0, len(targets)
    for lo, hi in zip(bins[:-1], bins[1:]):
        m = (prob >= lo) & (prob < hi)
        if m.sum() < 3:
            continue
        total += (m.sum() / n) * abs(targets[m].mean() - prob[m].mean())
    return float(total)


def qcdi(
    prob: np.ndarray,
    targets: np.ndarray,
    qbar: np.ndarray,
    tau_lq: float = 0.45,
    tau_hq: float = 0.50,
    n_bins: int = 15,
) -> dict:
    """Quality-Calibration Degradation Index.

    Returns dict with ece_lq, ece_hq, qcdi, n_lq, n_hq.
    """
    lq = qbar < tau_lq
    hq = qbar > tau_hq
    e_lq = ece(prob[lq], targets[lq], n_bins) if lq.sum() >= 10 else float("nan")
    e_hq = ece(prob[hq], targets[hq], n_bins) if hq.sum() >= 10 else float("nan")
    return {
        "ece_lq": e_lq,
        "ece_hq": e_hq,
        "qcdi": e_lq - e_hq if not (np.isnan(e_lq) or np.isnan(e_hq)) else float("nan"),
        "n_lq": int(lq.sum()),
        "n_hq": int(hq.sum()),
    }


def spearman_rho(entropy: np.ndarray, qbar: np.ndarray) -> tuple[float, float]:
    """Spearman rank correlation between predictive entropy and quality score."""
    rho, p = spearmanr(entropy, qbar)
    return float(rho), float(p)


def binary_entropy(prob_pos: np.ndarray) -> np.ndarray:
    p = np.clip(prob_pos, 1e-9, 1 - 1e-9)
    return -(p * np.log(p) + (1 - p) * np.log(1 - p))


def bootstrap_ci(
    stat_fn,
    *arrays: np.ndarray,
    n_boot: int = 10000,
    ci: float = 0.95,
    seed: int = 42,
) -> tuple[float, float]:
    """Percentile bootstrap confidence interval for any statistic."""
    rng = np.random.default_rng(seed)
    n = len(arrays[0])
    boots = []
    for _ in range(n_boot):
        idx = rng.integers(0, n, size=n)
        boots.append(stat_fn(*[a[idx] for a in arrays]))
    alpha = (1 - ci) / 2
    return float(np.percentile(boots, 100 * alpha)), float(np.percentile(boots, 100 * (1 - alpha)))
