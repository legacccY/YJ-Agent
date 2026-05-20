"""ITB: Image Triage Benchmark — evaluation protocol for quality-stratified calibration."""
from .metrics import ece, qcdi, spearman_rho, bootstrap_ci
from .evaluate import evaluate_on_itb

__all__ = ["ece", "qcdi", "spearman_rho", "bootstrap_ci", "evaluate_on_itb"]
