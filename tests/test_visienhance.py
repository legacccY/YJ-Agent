"""Smoke tests for VisiEnhanceNet — Plan A config.

Run: pytest tests/test_visienhance.py -v
"""

import sys
from pathlib import Path

import pytest
import torch

sys.path.insert(0, str(Path(__file__).parent.parent / "project"))

from models.visienhance import VisiEnhanceNet


PLAN_A = dict(base_channels=64, enc_blocks=[2, 2, 2], mid_blocks=6, dec_blocks=[2, 2, 2])


def test_param_count():
    model = VisiEnhanceNet(**PLAN_A)
    n = model.param_count()
    assert 12_000_000 < n < 20_000_000, f"Unexpected param count: {n/1e6:.1f}M"


def test_forward_shape():
    model = VisiEnhanceNet(**PLAN_A).eval()
    x = torch.rand(1, 3, 128, 128)
    q = torch.rand(1, 5)
    with torch.no_grad():
        out = model(x, q)
    assert out.shape == (1, 3, 128, 128), f"Bad output shape: {out.shape}"


def test_output_range():
    model = VisiEnhanceNet(**PLAN_A).eval()
    x = torch.rand(1, 3, 128, 128)
    q = torch.rand(1, 5)
    with torch.no_grad():
        out = model(x, q)
    assert out.min() >= 0.0 and out.max() <= 1.0, "Output out of [0,1]"


def test_film_identity_at_perfect_quality():
    """At q=1 (defect=0), FiLM gamma≈0 and beta≈0 (zero-init), so output ≈ x."""
    model = VisiEnhanceNet(**PLAN_A).eval()
    x = torch.rand(1, 3, 128, 128)
    q = torch.ones(1, 5)
    with torch.no_grad():
        out = model(x, q)
    # conv_out zero-init → residual≈0 → out≈x (within float32 tol)
    assert torch.allclose(out, x, atol=1e-4), "FiLM identity property violated"


@pytest.mark.skipif(not torch.cuda.is_available(), reason="CUDA not available")
def test_forward_cuda():
    model = VisiEnhanceNet(**PLAN_A).cuda().eval()
    x = torch.rand(1, 3, 128, 128, device="cuda")
    q = torch.rand(1, 5, device="cuda")
    with torch.no_grad():
        out = model(x, q)
    assert out.shape == (1, 3, 128, 128)


@pytest.mark.skipif(not torch.cuda.is_available(), reason="CUDA not available")
def test_amp_forward():
    from torch.cuda.amp import autocast
    model = VisiEnhanceNet(**PLAN_A).cuda().eval()
    x = torch.rand(1, 3, 128, 128, device="cuda")
    q = torch.rand(1, 5, device="cuda")
    with torch.no_grad(), autocast():
        out = model(x, q)
    assert out.shape == (1, 3, 128, 128)
