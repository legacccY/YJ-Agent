"""QAD Classifier: q_theta(y | z).

Maps latent code z to K-class logits.
"""

import torch
import torch.nn as nn


class QADClassifier(nn.Module):
    """Simple MLP classifier operating on latent code z.

    Args:
        latent_dim: Input latent dimension (matches QVIBEncoder.latent_dim).
        hidden_dim: Hidden layer width.
        num_classes: Number of output classes (2 for binary melanoma/benign).
        dropout: Dropout rate.
    """

    def __init__(
        self,
        latent_dim: int = 32,
        hidden_dim: int = 64,
        num_classes: int = 2,
        dropout: float = 0.2,
    ):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(latent_dim, hidden_dim),
            nn.LayerNorm(hidden_dim),
            nn.GELU(),
            nn.Dropout(dropout),
            nn.Linear(hidden_dim, num_classes),
        )

    def forward(self, z: torch.Tensor) -> torch.Tensor:
        """
        Args:
            z: Latent code, shape (B, latent_dim).
        Returns:
            logits: shape (B, num_classes).
        """
        return self.net(z)
