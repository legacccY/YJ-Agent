"""
Shape / contract tests for gdn2vessel pilot models.

These tests run on CPU with tiny mock tensors — no GPU / FLA required.
FLA is mocked for the GDN2 tests so they pass on machines without FLA installed.

Tests:
  1. UNet forward — output shape matches input spatial dims
  2. UNetGDN2 forward (mocked FLA) — output shape matches
  3. Sequence length assertion: ≤1024 enforced in GDN2MemoryModule
  4. GT-isolation: GDN2MemoryModule.forward / UNetGDN2.forward take no gt arg
  5. Degrade flag: use_memory=False → UNetGDN2 behaves like UNet (same output shape)
  6. DRIVE dataset sanity: loads one sample, checks tensor shapes and dtype
"""

from __future__ import annotations

import inspect
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest
import torch

# --------------------------------------------------------------------------- #
#  Path setup — allow running from repo root or tests/ directory
# --------------------------------------------------------------------------- #

_repo_root = Path(__file__).parent.parent
_src_dir = _repo_root / 'src'
if str(_src_dir) not in sys.path:
    sys.path.insert(0, str(_src_dir))

# --------------------------------------------------------------------------- #
#  Mock FLA to avoid import errors on machines without FLA installed
# --------------------------------------------------------------------------- #

def _make_fake_gdn2_fn():
    """Returns a fake naive_chunk_gated_delta_rule that passes through v.

    FLA kernel signature: fn(q, k, v, beta, g) -> (o, final_state)
      q, k, v : (B, T, nh, dh)
      beta, g  : (B, T, nh)        — scalar gates per (token, head)
      o        : (B, T, nh, dh)    — same layout as v

    The mock just returns v unchanged (identity pass-through).
    NOTE: do NOT do `v * g` here — g has shape (B,T,nh) which would
    broadcast incorrectly against v's (B,T,nh,dh).
    """
    def fake_fn(q, k, v, beta, g):
        # Identity pass-through; shape must match (B, T, nh, dh)
        return v.clone(), None
    return fake_fn


def _patch_fla():
    """
    Insert a mock fla module tree so models/unet_gdn2.py can import without
    the real FLA package being installed.
    """
    fake_fla = types.ModuleType('fla')
    fake_ops = types.ModuleType('fla.ops')
    fake_gdr = types.ModuleType('fla.ops.gated_delta_rule')
    fake_naive = types.ModuleType('fla.ops.gated_delta_rule.naive')
    fake_chunk = types.ModuleType('fla.ops.gated_delta_rule.chunk')

    fake_naive.naive_chunk_gated_delta_rule = _make_fake_gdn2_fn()
    fake_chunk.chunk_gated_delta_rule = _make_fake_gdn2_fn()

    sys.modules.setdefault('fla', fake_fla)
    sys.modules.setdefault('fla.ops', fake_ops)
    sys.modules.setdefault('fla.ops.gated_delta_rule', fake_gdr)
    sys.modules.setdefault('fla.ops.gated_delta_rule.naive', fake_naive)
    sys.modules.setdefault('fla.ops.gated_delta_rule.chunk', fake_chunk)


_patch_fla()

# Now safe to import models
from models.unet import UNet
from models.unet_gdn2 import GDN2MemoryModule, UNetGDN2


# --------------------------------------------------------------------------- #
#  Test 1: UNet forward shape
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("B,H,W", [(1, 64, 64), (2, 128, 128)])
def test_unet_forward_shape(B, H, W):
    model = UNet(in_ch=1, out_ch=1, base_ch=16)
    model.eval()
    with torch.no_grad():
        x = torch.randn(B, 1, H, W)
        out = model(x)
    assert out.shape == (B, 1, H, W), f"Expected ({B},1,{H},{W}), got {out.shape}"


# --------------------------------------------------------------------------- #
#  Test 2: UNetGDN2 forward shape (memory on)
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("B,H,W", [(1, 64, 64), (2, 128, 128)])
def test_unet_gdn2_forward_shape(B, H, W):
    """
    UNetGDN2 with use_memory=True: output shape should equal input shape.
    Spatial dims H=64, W=64 → bottleneck 4×4 = 16 tokens ≤ 1024. OK.
    """
    model = UNetGDN2(in_ch=1, out_ch=1, base_ch=16, use_memory=True, backend='naive')
    model.eval()
    with torch.no_grad():
        x = torch.randn(B, 1, H, W)
        out = model(x)
    assert out.shape == (B, 1, H, W), f"Expected ({B},1,{H},{W}), got {out.shape}"


# --------------------------------------------------------------------------- #
#  Test 3: Sequence length assertion — ≤1024 enforced
# --------------------------------------------------------------------------- #

def test_gdn2_seq_len_assertion_passes():
    """32×32 = 1024 tokens: exactly at limit — should not raise."""
    d_model = 16
    mem = GDN2MemoryModule(d_model=d_model, d_head=16, n_heads=1, backend='naive')
    mem.eval()
    with torch.no_grad():
        x = torch.randn(1, d_model, 32, 32)  # T = 32*32 = 1024
        out = mem(x)
    assert out.shape == x.shape


def test_gdn2_seq_len_assertion_fails():
    """33×32 = 1056 tokens > 1024: must raise AssertionError."""
    d_model = 16
    mem = GDN2MemoryModule(d_model=d_model, d_head=16, n_heads=1, backend='naive')
    mem.eval()
    with torch.no_grad():
        x = torch.randn(1, d_model, 33, 32)  # T = 33*32 = 1056 > 1024
        with pytest.raises(AssertionError, match=r'Sequence length'):
            mem(x)


# --------------------------------------------------------------------------- #
#  Test 4: GT isolation — no gt parameter in forward signatures
# --------------------------------------------------------------------------- #

def test_gdn2_memory_module_no_gt_param():
    """GDN2MemoryModule.forward must NOT accept a 'gt' parameter."""
    sig = inspect.signature(GDN2MemoryModule.forward)
    param_names = list(sig.parameters.keys())
    assert 'gt' not in param_names, (
        f"GDN2MemoryModule.forward should NOT have 'gt' param. Got: {param_names}"
    )


def test_unet_gdn2_no_gt_param():
    """UNetGDN2.forward must NOT accept a 'gt' parameter."""
    sig = inspect.signature(UNetGDN2.forward)
    param_names = list(sig.parameters.keys())
    assert 'gt' not in param_names, (
        f"UNetGDN2.forward should NOT have 'gt' param. Got: {param_names}"
    )


def test_gdn2_proj_no_gt_param():
    """All projection layers in GDN2MemoryModule must not reference GT in their forward."""
    mem = GDN2MemoryModule(d_model=16, d_head=16, n_heads=1, backend='naive')
    proj_names = ['proj_q', 'proj_k', 'proj_v', 'proj_write', 'proj_erase', 'proj_g', 'proj_out']
    for name in proj_names:
        layer = getattr(mem, name)
        sig = inspect.signature(layer.forward)
        for pname in sig.parameters:
            assert pname not in ('gt', 'target', 'label', 'mask_gt'), (
                f"{name}.forward has suspicious GT-like param: {pname}"
            )


# --------------------------------------------------------------------------- #
#  Test 5: Degrade flag (use_memory=False → same output shape as UNet)
# --------------------------------------------------------------------------- #

def test_unet_gdn2_degrade_shape():
    """use_memory=False: UNetGDN2 degrades to pure CNN path, shape identical."""
    model_gdn2 = UNetGDN2(in_ch=1, out_ch=1, base_ch=16, use_memory=False)
    model_unet = UNet(in_ch=1, out_ch=1, base_ch=16)
    model_gdn2.eval()
    model_unet.eval()

    x = torch.randn(1, 1, 64, 64)
    with torch.no_grad():
        out_gdn2 = model_gdn2(x)
        out_unet = model_unet(x)

    assert out_gdn2.shape == out_unet.shape, (
        f"Degrade shape mismatch: {out_gdn2.shape} vs {out_unet.shape}"
    )
    # When use_memory=False, self.memory is None (assert the flag works)
    assert model_gdn2.memory is None, "use_memory=False should set memory=None"


def test_unet_gdn2_degrade_is_pure_cnn():
    """With same weights (copied), use_memory=False output == UNet output."""
    # Build both with same base_ch
    model_gdn2 = UNetGDN2(in_ch=1, out_ch=1, base_ch=16, use_memory=False)
    model_unet = UNet(in_ch=1, out_ch=1, base_ch=16)

    # Copy shared encoder/decoder/head weights from gdn2 → unet
    # (they share the same layer names)
    shared_keys = [k for k in model_unet.state_dict() if k in model_gdn2.state_dict()]
    unet_sd = model_unet.state_dict()
    gdn2_sd = model_gdn2.state_dict()
    for k in shared_keys:
        unet_sd[k] = gdn2_sd[k].clone()
    model_unet.load_state_dict(unet_sd)

    model_gdn2.eval()
    model_unet.eval()

    torch.manual_seed(0)
    x = torch.randn(1, 1, 64, 64)
    with torch.no_grad():
        out_gdn2 = model_gdn2(x)
        out_unet = model_unet(x)

    assert torch.allclose(out_gdn2, out_unet, atol=1e-5), (
        "Degrade path output should equal pure UNet output (same weights)"
    )


# --------------------------------------------------------------------------- #
#  Test 6: DRIVE dataset tensor shapes and dtypes
# --------------------------------------------------------------------------- #

def test_drive_dataset_shapes():
    """
    Load DRIVE dataset from local path.
    If data not available, skip gracefully.
    """
    drive_root = Path(_repo_root.parent.parent.parent.parent.parent) / 'data' / 'vessel' / 'DRIVE'
    # Try several candidate paths
    candidates = [
        Path('D:/YJ-Agent/data/vessel/DRIVE'),
        drive_root,
    ]
    data_root = None
    for c in candidates:
        if c.exists() and (c / 'training').exists():
            data_root = c
            break

    if data_root is None:
        pytest.skip("DRIVE dataset not found; skipping dataset shape test")

    from datasets.drive import DRIVEDataset
    ds = DRIVEDataset(
        data_root=str(data_root),
        split='val',       # 4 images, quick
        patch_size=256,    # small patch for speed
        augment=False,
    )
    assert len(ds) > 0, "Dataset is empty"

    sample = ds[0]
    img = sample['image']
    gt = sample['gt']
    fov = sample['fov']

    assert img.shape == (1, 256, 256), f"image shape {img.shape}"
    assert gt.shape == (1, 256, 256), f"gt shape {gt.shape}"
    assert fov.shape == (1, 256, 256), f"fov shape {fov.shape}"
    assert img.dtype == torch.float32
    assert gt.dtype == torch.float32
    assert fov.dtype == torch.float32
    # GT values must be {0, 1}
    assert set(gt.unique().tolist()).issubset({0.0, 1.0}), (
        f"GT has unexpected values: {gt.unique()}"
    )
    # FOV values must be {0, 1}
    assert set(fov.unique().tolist()).issubset({0.0, 1.0}), (
        f"FOV has unexpected values: {fov.unique()}"
    )
