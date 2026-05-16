"""Unit + smoke tests for VisiEnhance-Net.

Run: pytest tests/test_visienhance.py -v
"""

import torch
import pytest
from models.visienhance import VisiEnhanceNet, NAFBlock, FiLMLayer, LayerNorm2d, SimpleGate


# ── Fixtures ───────────────────────────────────────────────────────────────────

@pytest.fixture
def small_model():
    return VisiEnhanceNet(base_channels=8, enc_blocks=[1, 1], mid_blocks=2, dec_blocks=[1, 1])


@pytest.fixture
def default_model():
    return VisiEnhanceNet()


# ── Component tests ────────────────────────────────────────────────────────────

def test_layer_norm_2d_shape():
    ln = LayerNorm2d(16)
    x = torch.randn(2, 16, 32, 32)
    assert ln(x).shape == x.shape


def test_simple_gate_halves_channels():
    sg = SimpleGate()
    x = torch.randn(2, 16, 8, 8)
    out = sg(x)
    assert out.shape == (2, 8, 8, 8)


def test_nafblock_shape():
    block = NAFBlock(32)
    x = torch.randn(2, 32, 64, 64)
    assert block(x).shape == x.shape


def test_nafblock_residual_contributes():
    """Output should differ from input (non-trivial block)."""
    block = NAFBlock(16)
    x = torch.randn(2, 16, 16, 16)
    assert not torch.allclose(block(x), x, atol=1e-5)


def test_film_layer_identity_at_zero_defect():
    """At q_defect=0 (perfect quality), FiLM should be near-identity (zero-init output)."""
    film = FiLMLayer(q_dim=5, channels=16)
    feat = torch.randn(2, 16, 8, 8)
    q_defect = torch.zeros(2, 5)
    out = film(feat, q_defect)
    # Zero-init ensures γ=β=0 → output == feat exactly at init
    assert torch.allclose(out, feat, atol=1e-6), "FiLM should be identity at zero defect"


def test_film_layer_modulates_at_nonzero():
    film = FiLMLayer(q_dim=5, channels=16)
    # Break zero-init by taking a gradient step
    opt = torch.optim.SGD(film.parameters(), lr=0.1)
    feat = torch.ones(1, 16, 4, 4)
    q_defect = torch.ones(1, 5)
    loss = film(feat, q_defect).sum()
    loss.backward()
    opt.step()
    # After gradient step, modulation should kick in
    out = film(feat, q_defect)
    assert not torch.allclose(out, feat, atol=1e-6)


# ── VisiEnhanceNet smoke tests ─────────────────────────────────────────────────

def test_forward_shape(small_model):
    x = torch.rand(2, 3, 128, 128)
    q = torch.rand(2, 5)
    out = small_model(x, q)
    assert out.shape == x.shape, f"Expected {x.shape}, got {out.shape}"


def test_output_clamped(small_model):
    """Output must be in [0, 1]."""
    x = torch.rand(1, 3, 64, 64)
    q = torch.rand(1, 5)
    out = small_model(x, q)
    assert out.min().item() >= 0.0 - 1e-6
    assert out.max().item() <= 1.0 + 1e-6


def test_near_identity_at_perfect_quality():
    """At q=1 (zero defect), output should be close to input (residual near zero)."""
    model = VisiEnhanceNet(base_channels=8, enc_blocks=[1, 1], mid_blocks=1, dec_blocks=[1, 1])
    x = torch.rand(1, 3, 64, 64)
    q = torch.ones(1, 5)   # perfect quality → q_defect=0 → FiLM ≈ identity
    out = model(x, q)
    # conv_out zero-init → residual ≈ 0 at init → output ≈ input
    assert torch.allclose(out, x.clamp(0, 1), atol=1e-4), (
        f"Expected near-identity at perfect quality, max diff: {(out - x).abs().max():.6f}"
    )


def test_param_count():
    model = VisiEnhanceNet()
    n = model.param_count()
    assert n > 500_000, "Model too small (check base_channels)"
    assert n < 200_000_000, "Model unreasonably large"
    print(f"\n  param count: {n/1e6:.2f}M")


def test_gradient_flows(small_model):
    x = torch.rand(1, 3, 64, 64, requires_grad=False)
    q = torch.rand(1, 5)
    out = small_model(x, q)
    loss = out.mean()
    loss.backward()
    for name, p in small_model.named_parameters():
        assert p.grad is not None, f"No gradient for {name}"


def test_different_resolutions(small_model):
    """Model should handle arbitrary HxW (as long as divisible by 2^n_levels)."""
    for h, w in [(128, 128), (256, 192), (384, 384)]:
        x = torch.rand(1, 3, h, w)
        q = torch.rand(1, 5)
        out = small_model(x, q)
        assert out.shape == (1, 3, h, w)


def test_batch_consistency(small_model):
    """Single-image and batched outputs must match."""
    small_model.eval()
    x = torch.rand(3, 3, 64, 64)
    q = torch.rand(3, 5)
    with torch.no_grad():
        batch_out = small_model(x, q)
        for i in range(3):
            single_out = small_model(x[i:i+1], q[i:i+1])
            assert torch.allclose(batch_out[i], single_out[0], atol=1e-5)
