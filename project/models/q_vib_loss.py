"""Q-VIB ELBO Loss.

Implements Eq. (6) from the Q-VIB theoretical framework:
  L_QVIB = E_eps[-log q_theta(y|z)] + beta * KL(p_phi(z|x,q) || r_psi(z|q))

where z = mu + sigma * eps, eps ~ N(0, I)  [reparameterization, Appendix A.1]

Beta annealing schedule (Appendix A.3):
  beta(t) = beta_max * min(1, t / T_warmup)
"""

import torch
import torch.nn as nn
import torch.nn.functional as F

from models.quality_adaptive_prior import QualityAdaptivePrior


class QVIBLoss(nn.Module):
    """Q-VIB ELBO loss with KL annealing.

    Args:
        prior: QualityAdaptivePrior instance.
        beta_max: Maximum KL weight after warmup.
        warmup_steps: Number of training steps for linear beta ramp.
    """

    def __init__(
        self,
        prior: QualityAdaptivePrior,
        beta_max: float = 1e-3,
        warmup_steps: int = 2000,
    ):
        super().__init__()
        self.prior = prior
        self.beta_max = beta_max
        self.warmup_steps = warmup_steps
        self.register_buffer("_step", torch.tensor(0, dtype=torch.long))

    def current_beta(self) -> float:
        t = self._step.item()
        return self.beta_max * min(1.0, t / max(1, self.warmup_steps))

    def step(self):
        """Call once per training iteration."""
        self._step += 1

    def forward(
        self,
        logits: torch.Tensor,
        targets: torch.Tensor,
        mu: torch.Tensor,
        log_sigma_sq: torch.Tensor,
        q: torch.Tensor,
        weight: torch.Tensor | None = None,
    ) -> tuple[torch.Tensor, dict]:
        """Compute Q-VIB ELBO loss.

        Args:
            logits: Classifier output, shape (B, K).
            targets: Ground-truth class indices, shape (B,).
            mu: Encoder mean, shape (B, d).
            log_sigma_sq: Encoder log variance, shape (B, d).
            q: Quality vector, shape (B, 5).
            weight: Per-class loss weight for class imbalance, shape (K,).
        Returns:
            loss: Scalar total loss.
            info: Dict with ce, kl, beta values for logging.
        """
        # Cross-entropy term: E[-log q_theta(y|z)]
        ce = F.cross_entropy(logits, targets, weight=weight)

        # KL term: KL(p_phi || r_psi) with quality-adaptive prior (Eq. 9)
        kl_per_sample = self.prior.kl_divergence(mu, log_sigma_sq, q)
        kl = kl_per_sample.mean()

        beta = self.current_beta()
        loss = ce + beta * kl

        return loss, {"ce": ce.item(), "kl": kl.item(), "beta": beta}
