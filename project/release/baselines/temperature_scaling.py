"""Standard temperature scaling (Guo et al. 2017)."""
import numpy as np
from scipy.optimize import minimize


class TemperatureScaling:
    """Standard single-scalar temperature scaling."""

    def __init__(self):
        self.T_: float | None = None

    def fit(self, logits: np.ndarray, targets: np.ndarray) -> "TemperatureScaling":
        def nll(log_T):
            T = np.exp(log_T[0])
            p = np.clip(1 / (1 + np.exp(-logits / T)), 1e-9, 1 - 1e-9)
            return -float(np.mean(targets * np.log(p) + (1 - targets) * np.log(1 - p)))

        res = minimize(nll, [0.0], method="L-BFGS-B")
        self.T_ = float(np.exp(res.x[0]))
        return self

    def predict(self, logits: np.ndarray) -> np.ndarray:
        assert self.T_ is not None
        return 1.0 / (1.0 + np.exp(-logits / self.T_))
