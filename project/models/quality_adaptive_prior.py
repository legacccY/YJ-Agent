"""Quality-Adaptive Prior for Q-VIB.

Implements Eqs. (7-9) from the Q-VIB theoretical framework:
  r_psi(z|q) = N(0, sigma^2(q_bar) * I_d)                 Eq. (7)
  sigma^2(q_bar) = sigma0^2 + (1-sigma0^2)*sigmoid(-alpha*(q_bar-tau))  Eq. (8)
  KL(p_phi || r_psi) = 0.5 * sum_j [(mu_j^2+sigma_j^2)/sigma^2 - 1 - log(sigma_j^2/sigma^2)]  Eq. (9)

Lemma 1: sigma^2(q_bar) is strictly decreasing in q_bar (proved in theory doc).
  => low-quality inputs get wider prior => higher KL => more compressed z => higher entropy predictions
"""

import torch
import torch.nn as nn


class QualityAdaptivePrior(nn.Module):
    """Quality-adaptive isotropic Gaussian prior.

    Args:
        sigma0_sq: Prior variance at perfect quality (q_bar=1). Default 0.1.
        tau: Quality threshold for sigmoid transition. Default 0.5.
        alpha: Transition sharpness. Default 5.0.
    """

    def __init__(self, sigma0_sq: float = 0.1, tau: float = 0.5, alpha: float = 5.0):
        super().__init__()
        self.register_buffer("sigma0_sq", torch.tensor(sigma0_sq))
        self.register_buffer("tau", torch.tensor(tau))
        self.register_buffer("alpha", torch.tensor(alpha))

    def prior_variance(self, q: torch.Tensor) -> torch.Tensor:
        """Compute prior variance sigma^2(q_bar) per sample.

        Args:
            q: Quality vector, shape (B, 5), values in [0, 1].
        Returns:
            sigma_sq: shape (B,), strictly decreasing in q_bar (Lemma 1).
        """
        q_bar = q.mean(dim=-1)  # (B,)
        sigma_sq = self.sigma0_sq + (1.0 - self.sigma0_sq) * torch.sigmoid(
            -self.alpha * (q_bar - self.tau)
        )
        return sigma_sq  # (B,)

    def kl_divergence(
        self,
        mu: torch.Tensor,
        log_sigma_sq: torch.Tensor,
        q: torch.Tensor,
    ) -> torch.Tensor:
        """Analytic KL( N(mu, diag(sigma^2)) || N(0, prior_var*I) ) per sample.

        Implements Eq. (9):
          KL = 0.5 * sum_j [ (mu_j^2 + sigma_j^2) / prior_var - 1 - log(sigma_j^2/prior_var) ]

        Args:
            mu: Encoder mean, shape (B, d).
            log_sigma_sq: Encoder log variance, shape (B, d).
            q: Quality vector, shape (B, 5).
        Returns:
            kl: Per-sample KL, shape (B,).
        """
        prior_var = self.prior_variance(q).unsqueeze(-1)  # (B, 1)

        sigma_sq = torch.exp(log_sigma_sq).clamp(1e-8, 1e2)
        prior_var = prior_var.clamp(1e-8, 1e2)

        kl = 0.5 * (
            (mu.pow(2) + sigma_sq) / prior_var
            - 1.0
            - log_sigma_sq
            + torch.log(prior_var)
        ).sum(dim=-1)  # (B,)

        return kl

    def forward(self, mu, log_sigma_sq, q):
        return self.kl_divergence(mu, log_sigma_sq, q)
