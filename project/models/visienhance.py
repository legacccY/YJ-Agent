"""VisiEnhance-Net: Diagnosis-Preserving Quality Enhancement.

NAFNet backbone (Chen et al., ECCV 2022) with FiLM quality conditioning
(Perez et al., AAAI 2018).

FiLM injection: quality defect vector q̃ = 1-q conditions per-channel affine
transforms after every NAFBlock. At q=1 (perfect quality), q̃=0 → FiLM ≈ identity.

Proposition 3 (theory doc): Enhancement raises q̄ → tightens Q-VIB prior → lowers H(ŷ).
Lemma 3: DP-Loss = KL(p_φ(z|x_enh) ‖ p_φ(z|x_ref)) ≤ ε ⟹ I(Z_enh;Y) ≥ I(Z_ref;Y) - βε.
"""

import torch
import torch.nn as nn
import torch.nn.functional as F


class LayerNorm2d(nn.Module):
    """LayerNorm applied along channel dim for [B, C, H, W] feature maps."""

    def __init__(self, channels: int, eps: float = 1e-6):
        super().__init__()
        self.norm = nn.LayerNorm(channels, eps=eps)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.norm(x.permute(0, 2, 3, 1)).permute(0, 3, 1, 2)


class SimpleGate(nn.Module):
    """Split channels in half and multiply. Replaces nonlinear activation."""

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        x1, x2 = x.chunk(2, dim=1)
        return x1 * x2


class NAFBlock(nn.Module):
    """Nonlinear Activation Free Block (Chen et al., ECCV 2022).

    Two residual sub-blocks:
    1. Depthwise path: norm → expand → DWconv → SimpleGate → SCA → project
    2. FFN path:       norm → expand → SimpleGate → project

    Learnable per-channel residual scales (res_scale1/2) for stable deep training.
    """

    def __init__(self, channels: int, dw_expand: int = 2, ffn_expand: int = 2):
        super().__init__()
        dw_ch = channels * dw_expand

        self.norm1 = LayerNorm2d(channels)
        self.conv1 = nn.Conv2d(channels, dw_ch, 1, bias=True)
        self.conv2 = nn.Conv2d(dw_ch, dw_ch, 3, padding=1, groups=dw_ch, bias=True)
        self.conv3 = nn.Conv2d(dw_ch // 2, channels, 1, bias=True)
        self.sca = nn.Sequential(
            nn.AdaptiveAvgPool2d(1),
            nn.Conv2d(dw_ch // 2, dw_ch // 2, 1, bias=True),
        )

        ffn_ch = channels * ffn_expand
        self.norm2 = LayerNorm2d(channels)
        self.conv4 = nn.Conv2d(channels, ffn_ch, 1, bias=True)
        self.conv5 = nn.Conv2d(ffn_ch // 2, channels, 1, bias=True)

        self.sg = SimpleGate()
        self.res_scale1 = nn.Parameter(torch.ones(1, channels, 1, 1) * 1e-2)
        self.res_scale2 = nn.Parameter(torch.ones(1, channels, 1, 1) * 1e-2)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        h = self.norm1(x)
        h = self.conv1(h)
        h = self.conv2(h)
        h = self.sg(h)
        h = h * self.sca(h)
        h = self.conv3(h)
        y = x + h * self.res_scale1

        h = self.conv4(self.norm2(y))
        h = self.sg(h)
        h = self.conv5(h)
        return y + h * self.res_scale2


class FiLMLayer(nn.Module):
    """Feature-wise Linear Modulation conditioned on quality defect vector q̃ = 1-q.

    F' = (1 + film_scale·γ(q̃)) ⊙ F + film_scale·β(q̃)

    Output layers zero-initialized → near-identity at start.
    film_scale=0.1 limits initial modulation magnitude.
    """

    def __init__(self, q_dim: int, channels: int, hidden: int = 128, film_scale: float = 0.1):
        super().__init__()
        self.film_scale = film_scale
        self.mlp_gamma = nn.Sequential(
            nn.Linear(q_dim, hidden), nn.ReLU(inplace=True), nn.Linear(hidden, channels)
        )
        self.mlp_beta = nn.Sequential(
            nn.Linear(q_dim, hidden), nn.ReLU(inplace=True), nn.Linear(hidden, channels)
        )
        nn.init.zeros_(self.mlp_gamma[-1].weight)
        nn.init.zeros_(self.mlp_gamma[-1].bias)
        nn.init.zeros_(self.mlp_beta[-1].weight)
        nn.init.zeros_(self.mlp_beta[-1].bias)

    def forward(self, feat: torch.Tensor, q_defect: torch.Tensor) -> torch.Tensor:
        """
        Args:
            feat:     [B, C, H, W]
            q_defect: [B, q_dim]  (= 1 - q)
        """
        g = self.mlp_gamma(q_defect).unsqueeze(-1).unsqueeze(-1)
        b = self.mlp_beta(q_defect).unsqueeze(-1).unsqueeze(-1)
        return (1.0 + self.film_scale * g) * feat + self.film_scale * b


class VisiEnhanceNet(nn.Module):
    """VisiEnhance-Net: NAFNet U-Net with per-block FiLM quality conditioning.

    Architecture (default base_channels=32, 2 encoder levels):
      Conv_in(3→32)
      → Enc0(32, 2×NAFBlock) + FiLM → Down(32→64)
      → Enc1(64, 2×NAFBlock) + FiLM → Down(64→128)
      → Mid(128, 4×NAFBlock) + FiLM
      → Up(128→64) + Skip(64) → Dec0(64, 2×NAFBlock) + FiLM
      → Up(64→32)  + Skip(32) → Dec1(32, 2×NAFBlock) + FiLM
      → Conv_out(32→3) [residual: x_enh = clamp(x + residual)]

    Args:
        in_channels:   Input channels (3).
        base_channels: Base channel width; doubles per encoder level.
        enc_blocks:    NAFBlocks per encoder level.
        mid_blocks:    NAFBlocks in bottleneck.
        dec_blocks:    NAFBlocks per decoder level.
        q_dim:         Quality vector dim (5).
        film_hidden:   Hidden dim in each FiLM MLP.
        film_scale:    FiLM modulation scale at init.
    """

    def __init__(
        self,
        in_channels: int = 3,
        base_channels: int = 32,
        enc_blocks: list | None = None,
        mid_blocks: int = 4,
        dec_blocks: list | None = None,
        q_dim: int = 5,
        film_hidden: int = 128,
        film_scale: float = 0.1,
    ):
        super().__init__()
        if enc_blocks is None:
            enc_blocks = [2, 2]
        if dec_blocks is None:
            dec_blocks = [2, 2]
        assert len(enc_blocks) == len(dec_blocks)
        n = len(enc_blocks)

        ch = [base_channels * (2**i) for i in range(n + 1)]

        self.conv_in = nn.Conv2d(in_channels, ch[0], 3, padding=1, bias=True)

        self.enc_blocks = nn.ModuleList()
        self.enc_films = nn.ModuleList()
        self.downsamplers = nn.ModuleList()
        for i in range(n):
            self.enc_blocks.append(nn.Sequential(*[NAFBlock(ch[i]) for _ in range(enc_blocks[i])]))
            self.enc_films.append(FiLMLayer(q_dim, ch[i], film_hidden, film_scale))
            self.downsamplers.append(nn.Conv2d(ch[i], ch[i + 1], 2, stride=2, bias=True))

        self.mid_blocks = nn.Sequential(*[NAFBlock(ch[n]) for _ in range(mid_blocks)])
        self.mid_film = FiLMLayer(q_dim, ch[n], film_hidden, film_scale)

        self.upsamplers = nn.ModuleList()
        self.dec_blocks = nn.ModuleList()
        self.dec_films = nn.ModuleList()
        for i in reversed(range(n)):
            self.upsamplers.append(nn.ConvTranspose2d(ch[i + 1], ch[i], 2, stride=2, bias=True))
            self.dec_blocks.append(nn.Sequential(*[NAFBlock(ch[i]) for _ in range(dec_blocks[i])]))
            self.dec_films.append(FiLMLayer(q_dim, ch[i], film_hidden, film_scale))

        self.conv_out = nn.Conv2d(ch[0], in_channels, 3, padding=1, bias=True)
        nn.init.zeros_(self.conv_out.weight)
        nn.init.zeros_(self.conv_out.bias)

    def forward(self, x: torch.Tensor, q: torch.Tensor) -> torch.Tensor:
        """
        Args:
            x: Low-quality image  [B, 3, H, W], float in [0, 1].
            q: Quality vector     [B, 5],        float in [0, 1].
        Returns:
            x_enh: Enhanced image [B, 3, H, W], float in [0, 1].
        """
        qd = 1.0 - q  # defect vector

        feat = self.conv_in(x)

        skips = []
        for enc, film, down in zip(self.enc_blocks, self.enc_films, self.downsamplers):
            feat = film(enc(feat), qd)
            skips.append(feat)
            feat = down(feat)

        feat = self.mid_film(self.mid_blocks(feat), qd)

        skips = list(reversed(skips))
        for i, (up, dec, film) in enumerate(zip(self.upsamplers, self.dec_blocks, self.dec_films)):
            feat = up(feat)
            skip = skips[i]
            if feat.shape != skip.shape:
                feat = F.interpolate(feat, size=skip.shape[2:], mode="bilinear", align_corners=False)
            feat = film(dec(feat + skip), qd)

        residual = self.conv_out(feat)
        return (x + residual).clamp(0.0, 1.0)

    def param_count(self) -> int:
        return sum(p.numel() for p in self.parameters())
