"""Q-VIB Encoder: p_phi(z | x, q).

Architecture:
  - 4 ABCD clinical tokens: each scalar projected to d_model (interpretable)
  - 1 EfficientNet visual token: 1280D CNN feature projected to d_model (optional)
  - Single Transformer layer with quality-modulated self-attention (delta from QualityTokenizer)
  - Mean pool -> concat q_proj -> Linear -> (mu, log_sigma_sq), shape (B, latent_dim)

When efnet_feat is None, falls back to ABCD-only (4 tokens), preserving
backward compatibility with old checkpoints (set efnet_dim=0 in that case).

Reparameterization:
  z = mu + sigma * eps,  eps ~ N(0, I)     (Appendix A.1)

Theorem 1 applicability: delta is injected into the single Transformer
self-attention layer, keeping attention drift bounded regardless of token count.
"""

import math

import torch
import torch.nn as nn
import torch.nn.functional as F

from models.quality_tokenizer import QualityTokenizer


class QVIBEncoder(nn.Module):
    """Quality-conditional stochastic encoder.

    Args:
        abcd_dim: ABCD feature count (default 4).
        q_dim: Quality vector dimension (default 5).
        d_model: Token embedding dimension.
        n_heads: Attention heads in the single Transformer layer.
        latent_dim: Latent space dimension d.
        efnet_dim: EfficientNet feature dimension (0 = disabled).
        tokenizer_hidden: Hidden dim for quality tokenizer MLP.
        tokenizer_out: Output dim for quality tokenizer (m in Theorem 1).
        spectral_norm: Apply spectral norm to tokenizer.
    """

    def __init__(
        self,
        abcd_dim: int = 4,
        q_dim: int = 5,
        d_model: int = 64,
        n_heads: int = 4,
        latent_dim: int = 32,
        efnet_dim: int = 0,
        use_tokenizer: bool = True,
        tokenizer_hidden: int = 128,
        tokenizer_out: int = 64,
        spectral_norm: bool = True,
    ):
        super().__init__()
        self.d_model = d_model
        self.n_heads = n_heads
        self.latent_dim = latent_dim
        self.abcd_dim = abcd_dim
        self.efnet_dim = efnet_dim
        self.use_tokenizer = use_tokenizer

        # Project each ABCD scalar to a d_model-dim token (one token per scalar)
        self.feature_proj = nn.Linear(1, d_model)

        # Optional EfficientNet visual token (1280D -> d_model)
        self.efnet_proj = nn.Linear(efnet_dim, d_model) if efnet_dim > 0 else None

        # Quality tokenizer (Eq. 10) — disabled for Std VIB / Adaptive Prior baselines
        self.tokenizer = QualityTokenizer(
            q_dim=q_dim,
            hidden_dim=tokenizer_hidden,
            out_dim=tokenizer_out,
            spectral=spectral_norm,
        )

        # Quality vector concatenated to global representation
        self.q_proj = nn.Linear(q_dim, d_model)

        # Single Transformer encoder layer
        self.norm1 = nn.LayerNorm(d_model)
        self.norm2 = nn.LayerNorm(d_model)
        self.qkv = nn.Linear(d_model, 3 * d_model, bias=False)
        self.out_proj = nn.Linear(d_model, d_model)
        self.ffn = nn.Sequential(
            nn.Linear(d_model, d_model * 2),
            nn.GELU(),
            nn.Linear(d_model * 2, d_model),
        )

        # Pool output + q_proj -> (mu, log_sigma_sq)
        self.head = nn.Linear(d_model * 2, latent_dim * 2)

        self._init_weights()

    def _init_weights(self):
        for m in self.modules():
            if isinstance(m, nn.Linear):
                nn.init.xavier_uniform_(m.weight)
                if m.bias is not None:
                    nn.init.zeros_(m.bias)

    def _attention(self, x: torch.Tensor, delta: torch.Tensor) -> torch.Tensor:
        """Self-attention with quality bias injection (Eq. 10-11).

        Args:
            x: Token sequence (B, n_tokens, d_model).
            delta: Scalar attention bias per sample (B,).
        """
        B, N, D = x.shape
        head_dim = D // self.n_heads

        qkv = self.qkv(x).reshape(B, N, 3, self.n_heads, head_dim).permute(2, 0, 3, 1, 4)
        q_vec, k_vec, v_vec = qkv[0], qkv[1], qkv[2]

        attn_logits = (q_vec @ k_vec.transpose(-2, -1)) / math.sqrt(head_dim)
        attn_logits = attn_logits + delta.view(B, 1, 1, 1)  # broadcast quality bias
        attn_weights = F.softmax(attn_logits, dim=-1)
        out = (attn_weights @ v_vec).permute(0, 2, 1, 3).reshape(B, N, D)
        return self.out_proj(out)

    def forward(
        self,
        abcd: torch.Tensor,
        q: torch.Tensor,
        efnet_feat: torch.Tensor | None = None,
    ) -> tuple[torch.Tensor, torch.Tensor]:
        """Encode ABCD + optional EfficientNet features to (mu, log_sigma_sq).

        Args:
            abcd: ABCD features (B, 4), values in [0, 1].
            q: Quality vector from VisiScore-Net (B, 5), values in [0, 1].
            efnet_feat: EfficientNet-B0 features (B, efnet_dim), optional.
        Returns:
            mu: (B, latent_dim)
            log_sigma_sq: (B, latent_dim), clamped [-10, 2]
        """
        # 4 ABCD scalar tokens
        tokens = self.feature_proj(abcd.unsqueeze(-1))  # (B, 4, d_model)

        # Append EfficientNet visual token if provided
        if efnet_feat is not None and self.efnet_proj is not None:
            efnet_token = self.efnet_proj(efnet_feat).unsqueeze(1)  # (B, 1, d_model)
            tokens = torch.cat([tokens, efnet_token], dim=1)         # (B, 5, d_model)

        # Quality attention bias — zero for Std VIB / Adaptive Prior ablations
        if self.use_tokenizer:
            delta = self.tokenizer(q)  # (B,)
        else:
            delta = torch.zeros(tokens.shape[0], device=tokens.device)

        # Transformer layer with residual
        tokens = tokens + self._attention(self.norm1(tokens), delta)
        tokens = tokens + self.ffn(self.norm2(tokens))

        # Mean pool + quality projection
        pooled = tokens.mean(dim=1)               # (B, d_model)
        q_feat = self.q_proj(q)                   # (B, d_model)
        combined = torch.cat([pooled, q_feat], dim=-1)  # (B, d_model * 2)

        out = self.head(combined)                  # (B, latent_dim * 2)
        mu, log_sigma_sq = out.chunk(2, dim=-1)
        log_sigma_sq = log_sigma_sq.clamp(-10.0, 2.0)

        return mu, log_sigma_sq

    def reparameterize(self, mu: torch.Tensor, log_sigma_sq: torch.Tensor) -> torch.Tensor:
        """z = mu + sigma * eps,  eps ~ N(0, I)."""
        return mu + torch.exp(0.5 * log_sigma_sq) * torch.randn_like(mu)
