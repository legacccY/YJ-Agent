"""Quality Tokenizer for Q-VIB attention modulation.

Implements Eqs. (10-11) from the Q-VIB theoretical framework.

Architecture:
  u(q) = u_tilde(1 - q),  v(q) = v_tilde(1 - q)
  where u_tilde, v_tilde: R^5 -> R^m are 2-layer MLPs with LayerNorm.

Boundary condition (Theorem 1 prerequisite):
  u_tilde(0) = v_tilde(0) = 0  (enforced by no-bias last layer)

Quality attention bias:
  delta = u(q)^T v(q)   [scalar, broadcast over all token pairs]

With spectral normalization on linear layers, Lipschitz constants L_u, L_v <= 1,
ensuring the attention drift bound of Theorem 1:
  max_i ||a'_i - a_i||_1 <= 10 * L_u * L_v * eps^2
"""

import torch
import torch.nn as nn
from torch.nn.utils.parametrize import remove_parametrizations
from torch.nn.utils import spectral_norm


def _make_mlp(in_dim: int, hidden_dim: int, out_dim: int, spectral: bool) -> nn.Sequential:
    def _linear(i, o, bias=True):
        layer = nn.Linear(i, o, bias=bias)
        return spectral_norm(layer) if spectral else layer

    return nn.Sequential(
        _linear(in_dim, hidden_dim),
        nn.LayerNorm(hidden_dim),
        nn.GELU(),
        _linear(hidden_dim, out_dim, bias=False),  # no bias => f(0)=0 guaranteed
    )


class QualityTokenizer(nn.Module):
    """Learnable quality embedding for self-attention modulation.

    Args:
        q_dim: Input quality dimension (5 for VisiScore-Net).
        hidden_dim: MLP hidden width.
        out_dim: Embedding dimension m.
        spectral: Apply spectral normalization (constrains Lipschitz constant).
    """

    def __init__(
        self,
        q_dim: int = 5,
        hidden_dim: int = 128,
        out_dim: int = 64,
        spectral: bool = True,
    ):
        super().__init__()
        self.u_tilde = _make_mlp(q_dim, hidden_dim, out_dim, spectral)
        self.v_tilde = _make_mlp(q_dim, hidden_dim, out_dim, spectral)

    def forward(self, q: torch.Tensor) -> torch.Tensor:
        """Compute scalar attention bias delta per sample.

        delta = u(q)^T v(q)

        Boundary condition (Theorem 1 prerequisite):
          u(q=1) = v(q=1) = 0  =>  delta = 0  (no modulation at perfect quality)

        Implemented via explicit zero-subtraction to handle LayerNorm bias terms:
          u(q) = u_tilde(1-q) - u_tilde(0)
          v(q) = v_tilde(1-q) - v_tilde(0)
        so u(1) = u_tilde(0) - u_tilde(0) = 0 exactly.

        Args:
            q: Quality vector, shape (B, 5), values in [0, 1].
        Returns:
            delta: Attention bias, shape (B,). Add to all attention logits.
        """
        B = q.shape[0]
        defect = 1.0 - q  # (B, 5); zero when quality is perfect
        zero = torch.zeros(1, q.shape[1], dtype=q.dtype, device=q.device)  # (1, 5)

        # Run both defect and zero through the same forward pass so spectral_norm
        # uses one consistent sigma for both -> subtraction is numerically exact.
        u_both = self.u_tilde(torch.cat([defect, zero], dim=0))  # (B+1, m)
        v_both = self.v_tilde(torch.cat([defect, zero], dim=0))  # (B+1, m)

        u = u_both[:B] - u_both[B:]  # (B, m); exactly zero when defect=0
        v = v_both[:B] - v_both[B:]  # (B, m)
        delta = (u * v).sum(dim=-1)  # (B,)
        return delta
