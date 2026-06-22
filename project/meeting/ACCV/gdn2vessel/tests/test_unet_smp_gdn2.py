"""
Shape / contract tests for UNetSmpGDN2 (smp backbone + GDN-2 bottleneck).

All tests run on CPU with tiny mock tensors — NO GPU / FLA / smp required.
Both smp and FLA are stubbed/mocked so these pass in CI without real packages.

Tests:
  1. _pad_to_stride     — pad/crop round-trip: output shape == input shape
  2. Token count        — 576×608 → bottleneck 18×19 = 342 ≤ 1024
  3. Token guard        — input too large → AssertionError with message
  4. GT isolation       — UNetSmpGDN2.forward must NOT accept 'gt' parameter
  5. use_memory=False   — plain smp path; memory attribute is None
  6. forward shape      — with mocked smp+GDN2: output (B,1,H,W) == input shape
  7. return_reid_ctx     — o_seq / H_bot / W_bot in returned dict
  8. pad/crop asymmetry — odd H, odd W: crop gives back exact original shape
"""

from __future__ import annotations

import inspect
import math
import sys
import types
from pathlib import Path
from typing import List, Optional, Tuple
from unittest.mock import MagicMock, patch

import torch
import torch.nn as nn
import torch.nn.functional as F
import pytest

# --------------------------------------------------------------------------- #
#  Path setup
# --------------------------------------------------------------------------- #

_repo_root = Path(__file__).parent.parent
_src_dir = _repo_root / 'src'
if str(_src_dir) not in sys.path:
    sys.path.insert(0, str(_src_dir))

# --------------------------------------------------------------------------- #
#  Mock FLA (same approach as test_shapes.py)
# --------------------------------------------------------------------------- #

def _make_fake_gdn2_fn():
    """Identity pass-through fake for naive_chunk_gated_delta_rule."""
    def fake_fn(q, k, v, beta, g, output_final_state=False):
        out = v.clone()  # (B, T, nh, dh)
        if output_final_state:
            return out, None
        return out, None
    return fake_fn


def _patch_fla():
    fake_fla   = types.ModuleType('fla')
    fake_ops   = types.ModuleType('fla.ops')
    fake_gdr   = types.ModuleType('fla.ops.gated_delta_rule')
    fake_naive = types.ModuleType('fla.ops.gated_delta_rule.naive')
    fake_chunk = types.ModuleType('fla.ops.gated_delta_rule.chunk')
    fake_naive.naive_chunk_gated_delta_rule = _make_fake_gdn2_fn()
    fake_chunk.chunk_gated_delta_rule       = _make_fake_gdn2_fn()
    sys.modules.setdefault('fla',                                 fake_fla)
    sys.modules.setdefault('fla.ops',                             fake_ops)
    sys.modules.setdefault('fla.ops.gated_delta_rule',            fake_gdr)
    sys.modules.setdefault('fla.ops.gated_delta_rule.naive',      fake_naive)
    sys.modules.setdefault('fla.ops.gated_delta_rule.chunk',      fake_chunk)


_patch_fla()

# --------------------------------------------------------------------------- #
#  Mock smp (segmentation_models_pytorch)
#
#  Strategy: build a minimal fake smp.Unet that:
#    - .encoder(x)         → returns fake feature list
#    - .decoder(*features) → returns fake decoder output
#    - .segmentation_head  → nn.Identity (passthrough)
#    - encoder.out_channels → (3, 64, 64, 128, 256, 512) for resnet34
# --------------------------------------------------------------------------- #

_STRIDE = 32
_BOTTLENECK_CH = 512

class _FakeEncoder(nn.Module):
    """Minimal encoder stub: x (B,C,H,W) → list of 6 fake feature maps."""
    def __init__(self, bottleneck_ch: int = _BOTTLENECK_CH, stride: int = _STRIDE):
        super().__init__()
        self.out_channels = (3, 64, 64, 128, 256, bottleneck_ch)
        self._stride = stride
        # Identity 1x1 conv to make bottleneck_ch feature (fake, no real processing)
        self._proj = nn.Conv2d(1, bottleneck_ch, 1, bias=False)

    def forward(self, x: torch.Tensor) -> List[torch.Tensor]:
        B, C, H, W = x.shape
        device = x.device
        # features[0]: original-resolution 3ch (or C-ch) — skip0
        f0 = x[:, :1, :, :].expand(B, 3, H, W)              # (B,3,H,W) — fake
        # features[1..4]: progressively smaller (fake zeros, right shapes)
        f1 = torch.zeros(B, 64,  H // 2,  W // 2,  device=device)
        f2 = torch.zeros(B, 64,  H // 4,  W // 4,  device=device)
        f3 = torch.zeros(B, 128, H // 8,  W // 8,  device=device)
        f4 = torch.zeros(B, 256, H // 16, W // 16, device=device)
        # features[5]: bottleneck at stride-32
        # Use proj to get real gradient path (tests that memory module can receive it)
        f5 = self._proj(x)  # (B, bottleneck_ch, H, W) — then downsample
        f5 = F.adaptive_avg_pool2d(f5, (H // self._stride, W // self._stride))
        return [f0, f1, f2, f3, f4, f5]


class _FakeDecoder(nn.Module):
    """Decoder stub: returns upsampled version of bottleneck to input resolution."""
    def forward(self, *features: torch.Tensor) -> torch.Tensor:
        # features[0] has original H, W; use its spatial size as target
        # features[-1] is the bottleneck — upsample to features[0] resolution
        target_h, target_w = features[0].shape[-2], features[0].shape[-1]
        bot = features[-1]  # (B, 512, H_bot, W_bot)
        # Upsample + reduce to 1ch (fake decoder output)
        up = F.interpolate(bot, size=(target_h, target_w), mode='bilinear',
                           align_corners=False)
        # Return as single-channel (seg head will handle final projection)
        return up[:, :1, :, :]  # (B, 1, H, W)


class _FakeUnet(nn.Module):
    """Minimal smp.Unet stub."""
    def __init__(self, encoder_name, encoder_weights, in_channels, classes,
                 activation, decoder_attention_type, **kwargs):
        super().__init__()
        self.encoder = _FakeEncoder()
        self.decoder = _FakeDecoder()
        # segmentation_head: identity (already 1ch from decoder stub)
        self.segmentation_head = nn.Identity()

    def forward(self, x):
        features = self.encoder(x)
        dec = self.decoder(*features)
        return self.segmentation_head(dec)


def _patch_smp():
    """Insert fake smp into sys.modules so unet_smp_gdn2.py uses it."""
    fake_smp = types.ModuleType('segmentation_models_pytorch')
    fake_smp.Unet = _FakeUnet
    sys.modules['segmentation_models_pytorch'] = fake_smp
    # Also patch the _SMP_AVAILABLE flag after import
    return fake_smp


_patch_smp()

# Now safe to import the module under test
# Override _SMP_AVAILABLE so the import guard does not raise
import importlib
# Import fresh (FLA + smp both mocked above)
from models import unet_smp_gdn2 as _mod
_mod._SMP_AVAILABLE = True  # override the ImportError guard for tests

from models.unet_smp_gdn2 import (
    UNetSmpGDN2,
    _pad_to_stride,
    _crop_to_original,
    _RESNET_STRIDE,
    _MAX_SEQ_LEN,
)

# --------------------------------------------------------------------------- #
#  Test 1: _pad_to_stride / _crop_to_original round-trip
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("H,W", [
    (576, 608),   # already aligned → no padding
    (565, 584),   # DRIVE full image → pad to (576, 608)
    (100, 100),   # needs padding to (128, 128)
    (1, 1),       # extreme small → pad to (32, 32)
    (31, 33),     # odd sizes on both axes
])
def test_pad_crop_roundtrip(H, W):
    """_pad_to_stride then _crop_to_original must recover exact original shape."""
    x = torch.randn(2, 1, H, W)
    x_pad, pad_hw = _pad_to_stride(x, _RESNET_STRIDE)
    # Padded dims must be multiples of stride
    H_pad, W_pad = x_pad.shape[-2], x_pad.shape[-1]
    assert H_pad % _RESNET_STRIDE == 0, f"H_pad={H_pad} not divisible by {_RESNET_STRIDE}"
    assert W_pad % _RESNET_STRIDE == 0, f"W_pad={W_pad} not divisible by {_RESNET_STRIDE}"
    # Crop back
    x_out = _crop_to_original(x_pad, pad_hw, H, W)
    assert x_out.shape == (2, 1, H, W), f"Round-trip shape mismatch: {x_out.shape}"
    # Values must be identical (reflect pad then crop should be lossless)
    assert torch.allclose(x_out, x), "Round-trip values changed"


# --------------------------------------------------------------------------- #
#  Test 2: Token count for DRIVE full image input
# --------------------------------------------------------------------------- #

def test_drive_bottleneck_tokens():
    """565×584 → pad 576×608 → bottleneck 18×19 = 342 ≤ 1024 tokens."""
    x = torch.zeros(1, 1, 565, 584)
    x_pad, _ = _pad_to_stride(x, _RESNET_STRIDE)
    H_pad, W_pad = x_pad.shape[-2], x_pad.shape[-1]
    assert H_pad == 576, f"H_pad={H_pad}, expected 576"
    assert W_pad == 608, f"W_pad={W_pad}, expected 608"
    n_tokens = (H_pad // _RESNET_STRIDE) * (W_pad // _RESNET_STRIDE)
    assert n_tokens == 342, f"Token count {n_tokens}, expected 342"
    assert n_tokens <= _MAX_SEQ_LEN, f"Token count {n_tokens} > {_MAX_SEQ_LEN}"


# --------------------------------------------------------------------------- #
#  Test 3: Token count guard — input too large → AssertionError
# --------------------------------------------------------------------------- #

def test_forward_token_guard_raises():
    """
    Input that would produce >1024 bottleneck tokens must raise AssertionError.
    Max safe: 1024×1024 → bottleneck 32×32 = 1024 (exactly at limit, passes).
    1024+32=1056 wide → bottleneck 33×32 = 1056 > 1024 → must raise.
    """
    model = UNetSmpGDN2(
        in_channels=1, classes=1,
        encoder_name='resnet34', encoder_weights=None,
        use_memory=False,   # skip memory for this structural test
    )
    model.eval()
    # 1024+32 = 1056 wide (nearest 32-multiple above 1024+1 = 1057 → 1088)
    # Use 1025 → pad to 1056 → W_bot = 1056/32 = 33; H = 32 → H_bot=1; 1*33=33 OK
    # For >1024 tokens: need H_bot * W_bot > 1024, e.g. H=1025, W=1025
    # 1025 → pad to 1056 → bot = 33×33 = 1089 > 1024
    x_toolarge = torch.randn(1, 1, 1025, 1025)
    with pytest.raises(AssertionError, match=r'[Tt]oken'):
        with torch.no_grad():
            model(x_toolarge)


# --------------------------------------------------------------------------- #
#  Test 4: GT isolation — forward must NOT accept 'gt' parameter
# --------------------------------------------------------------------------- #

def test_no_gt_parameter():
    """UNetSmpGDN2.forward must not have a 'gt' parameter."""
    sig = inspect.signature(UNetSmpGDN2.forward)
    param_names = list(sig.parameters.keys())
    assert 'gt' not in param_names, (
        f"UNetSmpGDN2.forward must NOT have 'gt' param. Got: {param_names}"
    )
    # Also check GDN2MemoryModule (imported transitively)
    from models.unet_gdn2 import GDN2MemoryModule
    sig_mem = inspect.signature(GDN2MemoryModule.forward)
    assert 'gt' not in sig_mem.parameters, "GDN2MemoryModule.forward must not have 'gt'"


# --------------------------------------------------------------------------- #
#  Test 5: use_memory=False → self.memory is None (pure smp path)
# --------------------------------------------------------------------------- #

def test_use_memory_false_memory_is_none():
    """use_memory=False: memory attribute must be None."""
    model = UNetSmpGDN2(
        in_channels=1, classes=1,
        encoder_name='resnet34', encoder_weights=None,
        use_memory=False,
    )
    assert model.memory is None, "use_memory=False should set memory=None"


# --------------------------------------------------------------------------- #
#  Test 6: forward output shape matches input (use_memory=True)
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("B,H,W", [
    (1, 64,  64),    # small square; bottleneck 2×2 = 4 tokens
    (2, 96,  128),   # rectangular; 96/32=3, 128/32=4 → 12 tokens
    (1, 565, 584),   # DRIVE full-image; pad→576×608, bot=18×19=342 tokens
])
def test_forward_shape_memory_on(B, H, W):
    """Output (B,1,H,W) == input shape with GDN-2 memory enabled."""
    model = UNetSmpGDN2(
        in_channels=1, classes=1,
        encoder_name='resnet34', encoder_weights=None,
        use_memory=True, backend='naive',
        use_frangi=False,   # skip frangi for speed (no real feature map in fake encoder)
    )
    model.eval()
    x = torch.randn(B, 1, H, W)
    with torch.no_grad():
        out = model(x)
    assert out.shape == (B, 1, H, W), (
        f"Expected ({B},1,{H},{W}), got {tuple(out.shape)}"
    )


@pytest.mark.parametrize("B,H,W", [
    (1, 64,  64),
    (1, 565, 584),
])
def test_forward_shape_memory_off(B, H, W):
    """Output (B,1,H,W) == input shape with use_memory=False (plain smp path)."""
    model = UNetSmpGDN2(
        in_channels=1, classes=1,
        encoder_name='resnet34', encoder_weights=None,
        use_memory=False,
    )
    model.eval()
    x = torch.randn(B, 1, H, W)
    with torch.no_grad():
        out = model(x)
    assert out.shape == (B, 1, H, W), (
        f"Expected ({B},1,{H},{W}), got {tuple(out.shape)}"
    )


# --------------------------------------------------------------------------- #
#  Test 7: return_reid_ctx dict — o_seq / H_bot / W_bot present and correct shape
# --------------------------------------------------------------------------- #

def test_return_reid_ctx_keys_and_shapes():
    """
    return_reid_ctx=True: check o_seq shape and H_bot/W_bot values.
    H=64, W=64 → bottleneck 2×2=4 tokens.
    o_seq shape: (B, T, n_heads*d_head) = (1, 4, 64).
    """
    B, H, W = 1, 64, 64
    d_head, n_heads = 64, 1
    model = UNetSmpGDN2(
        in_channels=1, classes=1,
        encoder_name='resnet34', encoder_weights=None,
        use_memory=True, backend='naive',
        d_head=d_head, n_heads=n_heads,
        use_frangi=False,
    )
    model.eval()
    x = torch.randn(B, 1, H, W)
    with torch.no_grad():
        out, ctx = model(x, return_reid_ctx=True)
    # Output shape
    assert out.shape == (B, 1, H, W), f"logits shape: {out.shape}"
    # Context keys
    assert 'o_seq' in ctx
    assert 'H_bot' in ctx
    assert 'W_bot' in ctx
    # Bottleneck dims
    H_bot_exp = math.ceil(H / _RESNET_STRIDE)
    W_bot_exp = math.ceil(W / _RESNET_STRIDE)
    assert ctx['H_bot'] == H_bot_exp, f"H_bot {ctx['H_bot']} != {H_bot_exp}"
    assert ctx['W_bot'] == W_bot_exp, f"W_bot {ctx['W_bot']} != {W_bot_exp}"
    # o_seq shape: (B, T, n_heads*d_head)
    T = H_bot_exp * W_bot_exp
    o_seq = ctx['o_seq']
    assert o_seq is not None, "o_seq should not be None when use_memory=True"
    assert o_seq.shape == (B, T, n_heads * d_head), (
        f"o_seq shape {tuple(o_seq.shape)}, expected ({B},{T},{n_heads*d_head})"
    )


def test_return_reid_ctx_memory_off():
    """return_reid_ctx=True with use_memory=False: o_seq is None."""
    model = UNetSmpGDN2(
        in_channels=1, classes=1,
        encoder_name='resnet34', encoder_weights=None,
        use_memory=False,
    )
    model.eval()
    x = torch.randn(1, 1, 64, 64)
    with torch.no_grad():
        out, ctx = model(x, return_reid_ctx=True)
    assert ctx['o_seq'] is None, "o_seq must be None when use_memory=False"


# --------------------------------------------------------------------------- #
#  Test 8: pad/crop asymmetry — odd H and odd W recover exact shapes
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("H,W", [
    (565, 584),   # DRIVE canonical
    (511, 513),   # both flanking 512
    (1,   33),    # extreme asymmetry
    (33,  1),
])
def test_pad_crop_asymmetric(H, W):
    """Asymmetric / odd inputs must recover precisely (not +/-1 pixel)."""
    x = torch.arange(float(H * W)).reshape(1, 1, H, W)
    x_pad, pad_hw = _pad_to_stride(x, _RESNET_STRIDE)
    x_out = _crop_to_original(x_pad, pad_hw, H, W)
    assert x_out.shape == (1, 1, H, W), f"Shape mismatch: {x_out.shape}"
    assert torch.allclose(x_out, x), f"Value mismatch for H={H}, W={W}"
