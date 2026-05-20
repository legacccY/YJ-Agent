"""QCTS calibrator: T(qbar) = softplus(T0 + alpha * (1 - qbar))."""
from __future__ import annotations

import numpy as np
from scipy.optimize import minimize


def _softplus(x: np.ndarray) -> np.ndarray:
    return np.log1p(np.exp(x))


def _temperature(params: list[float], qbar: np.ndarray) -> np.ndarray:
    T0, alpha = params
    return _softplus(T0 + alpha * (1.0 - qbar))


def _nll(params: list[float], logit: np.ndarray, qbar: np.ndarray, tgt: np.ndarray) -> float:
    T = _temperature(params, qbar)
    p = 1.0 / (1.0 + np.exp(-logit / T))
    p = np.clip(p, 1e-9, 1 - 1e-9)
    return float(-np.mean(tgt * np.log(p) + (1 - tgt) * np.log(1 - p)))


class QCTSCalibrator:
    """Quality-Conditioned Temperature Scaling.

    Usage:
        cal = QCTSCalibrator()
        cal.fit(val_logits, val_qbar, val_targets)
        prob = cal.predict(test_logits, test_qbar)
    """

    def __init__(self, n_seeds: int = 3):
        self.n_seeds = n_seeds
        self.T0_: float | None = None
        self.alpha_: float | None = None
        self._seed_results: list[dict] = []

    def fit(
        self,
        logits: np.ndarray,
        qbar: np.ndarray,
        targets: np.ndarray,
    ) -> "QCTSCalibrator":
        """Fit (T0, alpha) by minimising NLL on a validation set.

        Args:
            logits:  Raw binary logits from the frozen backbone [N].
            qbar:    Per-image quality scores in [0, 1] [N].
            targets: Binary ground-truth labels [N].
        """
        best_nll, best_params = np.inf, [1.0, 0.5]

        inits = [
            (0.5, 0.3), (0.5, 0.6), (0.5, 1.0),
            (1.0, 0.3), (1.0, 0.6), (1.0, 1.0),
            (1.5, 0.3), (1.5, 0.6), (1.5, 1.0),
        ]

        for t0_init, a_init in inits:
            res = minimize(
                _nll,
                [t0_init, a_init],
                args=(logits, qbar, targets),
                method="L-BFGS-B",
                bounds=[(0.01, 5.0), (-1.0, 3.0)],
                options={"maxiter": 200},
            )
            if res.fun < best_nll:
                best_nll = res.fun
                best_params = res.x.tolist()
            self._seed_results.append({"T0": res.x[0], "alpha": res.x[1], "nll": res.fun})

        self.T0_, self.alpha_ = best_params
        return self

    def predict(self, logits: np.ndarray, qbar: np.ndarray) -> np.ndarray:
        """Return calibrated positive-class probabilities."""
        assert self.T0_ is not None, "Call fit() before predict()."
        T = _temperature([self.T0_, self.alpha_], qbar)
        return 1.0 / (1.0 + np.exp(-logits / T))

    def temperature(self, qbar: float | np.ndarray) -> float | np.ndarray:
        """Return T(qbar) for visualisation."""
        assert self.T0_ is not None
        return _temperature([self.T0_, self.alpha_], np.asarray(qbar))

    def __repr__(self) -> str:
        if self.T0_ is None:
            return "QCTSCalibrator(unfitted)"
        return f"QCTSCalibrator(T0={self.T0_:.4f}, alpha={self.alpha_:.4f})"
