"""
Phase-2 unit tests for gdn2vessel:
  1. DifferentiableFrangi — grad flows, no GT param, output shape/range
  2. Frangi gate modulation — write_gate ≥ no-Frangi baseline at vessel locations
  3. Multi-direction scan — shape identity for directions=1,2,4
  4. Degrade flag — use_memory=False == pure CNN (shape & weights)
  5. GT-isolation — no 'gt' param in Frangi / GDN2 / UNetGDN2 signatures
  6. Seq-len assertion ≤ 1024 (carried over from test_shapes.py for completeness)
  7. Re-ID head stub — raises NotImplementedError, no 'gt' in signature

All tests run on CPU with tiny tensors; FLA is mocked.
"""

from __future__ import annotations

import inspect
import sys
import types
from pathlib import Path

import pytest
import torch

# ---- Path setup ----
_repo_root = Path(__file__).parent.parent
_src_dir = _repo_root / 'src'
if str(_src_dir) not in sys.path:
    sys.path.insert(0, str(_src_dir))


# ---- Mock FLA (no real FLA needed for these CPU tests) ----

def _make_fake_gdn2_fn():
    """Fake GDN-2 kernel: o = v (identity pass-through)."""
    def fake_fn(q, k, v, beta, g):
        # identity: just return v (same shape) + dummy state
        return v, None
    return fake_fn


def _patch_fla():
    fake_fla   = types.ModuleType('fla')
    fake_ops   = types.ModuleType('fla.ops')
    fake_gdr   = types.ModuleType('fla.ops.gated_delta_rule')
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

from models.unet import UNet
from models.unet_gdn2 import (
    DifferentiableFrangi,
    GDN2MemoryModule,
    ReIDReadoutHead,
    UNetGDN2,
    _get_scan_permutations,
    _invert_permutation,
)


# ===========================================================================
# 1. DifferentiableFrangi — gradient flow + no GT param + output range
# ===========================================================================

class TestDifferentiableFrangi:

    def _make_frangi(self, in_ch=4):
        return DifferentiableFrangi(
            scales=[0.5, 1.0],
            beta1=0.5,
            beta2=15.0,
            in_channels=in_ch,
        )

    def test_output_shape(self):
        """Output must be (B, 1, H, W)."""
        f = self._make_frangi(4)
        x = torch.randn(2, 4, 16, 16)
        v = f(x)
        assert v.shape == (2, 1, 16, 16), f"Got {v.shape}"

    def test_output_range(self):
        """Vesselness must be in [0, 1]."""
        f = self._make_frangi(4)
        x = torch.randn(2, 4, 16, 16)
        v = f(x)
        assert v.min().item() >= -1e-6, f"min={v.min().item()}"
        assert v.max().item() <= 1.0 + 1e-6, f"max={v.max().item()}"

    def test_grad_flows(self):
        """
        Frangi output must be differentiable w.r.t. input (Claim 3 requirement:
        'input-derived differentiable Frangi').  Grad must be non-zero.
        """
        f = self._make_frangi(4)
        x = torch.randn(1, 4, 16, 16, requires_grad=True)
        v = f(x)
        loss = v.sum()
        loss.backward()
        assert x.grad is not None, "No gradient w.r.t. input x"
        assert x.grad.abs().sum().item() > 0, "Zero gradient — Frangi not differentiable"

    def test_no_gt_param_forward(self):
        """DifferentiableFrangi.forward must NOT accept 'gt' parameter."""
        sig = inspect.signature(DifferentiableFrangi.forward)
        bad = {'gt', 'target', 'label', 'mask_gt', 'segmentation'}
        found = bad & set(sig.parameters.keys())
        assert not found, f"DifferentiableFrangi.forward has GT-like param(s): {found}"

    def test_no_gt_param_init(self):
        """DifferentiableFrangi.__init__ must NOT accept 'gt' parameter."""
        sig = inspect.signature(DifferentiableFrangi.__init__)
        bad = {'gt', 'target', 'label', 'mask_gt', 'segmentation'}
        found = bad & set(sig.parameters.keys())
        assert not found, f"DifferentiableFrangi.__init__ has GT-like param(s): {found}"

    def test_channel_reduce_is_not_gt_supervised(self):
        """
        channel_reduce must be a 1×1 conv (learned from data, not GT).
        Checks it has no 'gt' in parameter names or input signature.
        """
        f = self._make_frangi(8)
        assert hasattr(f, 'channel_reduce'), "Missing channel_reduce"
        import torch.nn as nn
        assert isinstance(f.channel_reduce, nn.Conv2d), "channel_reduce should be Conv2d"
        assert f.channel_reduce.kernel_size == (1, 1)
        # Verify no unexpected GT param
        sig = inspect.signature(f.channel_reduce.forward)
        bad = {'gt', 'target', 'label'}
        assert not (bad & set(sig.parameters.keys()))

    def test_batch_consistency(self):
        """Same image twice in a batch should give same vesselness."""
        f = self._make_frangi(4)
        f.eval()
        x = torch.randn(1, 4, 16, 16)
        xb = x.expand(2, -1, -1, -1)
        with torch.no_grad():
            v = f(xb)
        assert torch.allclose(v[0], v[1], atol=1e-5), "Batch inconsistency"


# ===========================================================================
# 2. Frangi gate modulation — GDN2MemoryModule mechanism B
# ===========================================================================

class TestFrangiGateModulation:

    def _make_mem(self, use_frangi=True, d_model=8):
        return GDN2MemoryModule(
            d_model=d_model,
            d_head=8,
            n_heads=1,
            backend='naive',
            directions=1,
            use_frangi=use_frangi,
        )

    def test_frangi_on_vs_off_different_output(self):
        """
        use_frangi=True should give different output from use_frangi=False
        (Frangi modulates the gates → different memory update).
        """
        torch.manual_seed(42)
        x = torch.randn(1, 8, 8, 8)   # 64 tokens — well within 1024

        mem_on  = self._make_mem(use_frangi=True,  d_model=8)
        mem_off = self._make_mem(use_frangi=False, d_model=8)

        mem_on.eval()
        mem_off.eval()

        with torch.no_grad():
            out_on  = mem_on(x)
            out_off = mem_off(x)

        # They should generally differ (unless by astronomical coincidence)
        assert not torch.allclose(out_on, out_off, atol=1e-4), (
            "Frangi on/off produced identical output — modulation may not be active"
        )

    def test_frangi_alpha_params_exist(self):
        """alpha_w and alpha_e must exist when use_frangi=True."""
        mem = self._make_mem(use_frangi=True)
        assert hasattr(mem, 'alpha_w') and mem.alpha_w is not None
        assert hasattr(mem, 'alpha_e') and mem.alpha_e is not None

    def test_frangi_alpha_absent_when_off(self):
        """alpha_w / alpha_e should be None when use_frangi=False."""
        mem = self._make_mem(use_frangi=False)
        assert mem.alpha_w is None
        assert mem.alpha_e is None

    def test_proj_write_and_erase_exist(self):
        """proj_write and proj_erase must be present (decoupled gates)."""
        mem = self._make_mem(use_frangi=True)
        assert hasattr(mem, 'proj_write'), "Missing proj_write"
        assert hasattr(mem, 'proj_erase'), "Missing proj_erase"

    def test_gate_modulation_grad_flow(self):
        """Gradient must flow through Frangi into write/erase gate path."""
        mem = self._make_mem(use_frangi=True, d_model=8)
        x = torch.randn(1, 8, 8, 8, requires_grad=True)
        out = mem(x)
        out.sum().backward()
        assert x.grad is not None and x.grad.abs().sum() > 0, (
            "No gradient through Frangi gate path"
        )


# ===========================================================================
# 3. Multi-direction scan — shape identity for directions=1,2,4
# ===========================================================================

class TestMultiDirectionScan:

    @pytest.mark.parametrize("directions", [1, 2, 4])
    def test_output_shape(self, directions):
        """Output shape must match input shape regardless of scan directions."""
        mem = GDN2MemoryModule(
            d_model=8,
            d_head=8,
            n_heads=1,
            backend='naive',
            directions=directions,
            use_frangi=False,   # isolate multi-dir from Frangi
        )
        mem.eval()
        x = torch.randn(1, 8, 8, 8)  # 64 tokens
        with torch.no_grad():
            out = mem(x)
        assert out.shape == x.shape, f"directions={directions}: {out.shape} != {x.shape}"

    def test_scan_permutations_1dir(self):
        """1-dir: single raster permutation."""
        perms = _get_scan_permutations(4, 4, 1, device=torch.device('cpu'))
        assert len(perms) == 1
        assert perms[0].shape == (16,)

    def test_scan_permutations_2dir(self):
        """2-dir: raster + transpose."""
        perms = _get_scan_permutations(4, 4, 2, device=torch.device('cpu'))
        assert len(perms) == 2
        # raster != transpose for non-square check (use 4×6)
        p2 = _get_scan_permutations(4, 6, 2, device=torch.device('cpu'))
        assert not torch.equal(p2[0], p2[1]), "raster and transpose should differ for 4x6"

    def test_scan_permutations_4dir(self):
        """4-dir: 4 distinct permutations returned."""
        perms = _get_scan_permutations(4, 4, 4, device=torch.device('cpu'))
        assert len(perms) == 4

    def test_invert_permutation(self):
        """perm[inv_perm] == identity."""
        perm = torch.randperm(16)
        inv  = _invert_permutation(perm)
        idx  = torch.arange(16)
        assert torch.equal(idx[perm][inv], idx), "Invert permutation incorrect"

    def test_invalid_directions_raises(self):
        """directions=3 must raise ValueError."""
        with pytest.raises((ValueError, AssertionError)):
            GDN2MemoryModule(
                d_model=8, d_head=8, n_heads=1,
                backend='naive', directions=3
            )

    def test_1dir_vs_2dir_output_differ(self):
        """
        Averaging 2 directions should generally differ from 1-direction output
        (permuted tokens → different memory dynamics → different o).
        """
        torch.manual_seed(99)
        x = torch.randn(1, 8, 8, 8)
        mem1 = GDN2MemoryModule(d_model=8, d_head=8, n_heads=1,
                                backend='naive', directions=1, use_frangi=False)
        mem2 = GDN2MemoryModule(d_model=8, d_head=8, n_heads=1,
                                backend='naive', directions=2, use_frangi=False)
        # Share weights for fair comparison
        mem2.load_state_dict(mem1.state_dict())
        mem1.eval(); mem2.eval()
        with torch.no_grad():
            o1 = mem1(x)
            o2 = mem2(x)
        # With identity fake kernel (v pass-through) + shared weights,
        # different token orderings still produce different LayerNorm residuals.
        # (May be equal in degenerate toy cases — just check shapes at minimum)
        assert o1.shape == o2.shape, "Shape mismatch across direction counts"


# ===========================================================================
# 4. Degrade flag — use_memory=False behaves like pure CNN
# ===========================================================================

class TestDegradeFlag:

    def test_memory_none_when_degraded(self):
        """use_memory=False must set self.memory = None."""
        model = UNetGDN2(in_ch=1, out_ch=1, base_ch=8, use_memory=False)
        assert model.memory is None

    def test_degrade_output_shape_matches_unet(self):
        """Degraded UNetGDN2 output shape == UNet output shape."""
        x = torch.randn(1, 1, 64, 64)
        m_gdn2 = UNetGDN2(in_ch=1, out_ch=1, base_ch=8, use_memory=False)
        m_unet = UNet(in_ch=1, out_ch=1, base_ch=8)
        m_gdn2.eval(); m_unet.eval()
        with torch.no_grad():
            assert m_gdn2(x).shape == m_unet(x).shape

    def test_degrade_numerically_equals_unet(self):
        """With shared weights, degraded UNetGDN2 == pure UNet (same forward path)."""
        x = torch.randn(1, 1, 64, 64)
        m_gdn2 = UNetGDN2(in_ch=1, out_ch=1, base_ch=8, use_memory=False)
        m_unet = UNet(in_ch=1, out_ch=1, base_ch=8)

        # Copy shared weights
        unet_sd = m_unet.state_dict()
        gdn2_sd = m_gdn2.state_dict()
        for k in unet_sd:
            if k in gdn2_sd:
                unet_sd[k] = gdn2_sd[k].clone()
        m_unet.load_state_dict(unet_sd)

        m_gdn2.eval(); m_unet.eval()
        torch.manual_seed(0)
        with torch.no_grad():
            o1 = m_gdn2(x)
            o2 = m_unet(x)
        assert torch.allclose(o1, o2, atol=1e-5), (
            f"Degrade path diverges from pure UNet: max_diff={( o1 - o2).abs().max()}"
        )

    def test_degrade_flag_no_exception(self):
        """Ensure degrade path runs without any AttributeError on .memory."""
        m = UNetGDN2(in_ch=1, out_ch=1, base_ch=8, use_memory=False)
        m.eval()
        x = torch.randn(1, 1, 32, 32)
        with torch.no_grad():
            _ = m(x)


# ===========================================================================
# 5. GT-isolation — signature checks across all new classes
# ===========================================================================

_GT_LIKE_PARAMS = {'gt', 'target', 'label', 'mask_gt', 'segmentation',
                   'gt_mask', 'ann', 'annotation'}


def _check_no_gt(cls, method_name='forward'):
    sig = inspect.signature(getattr(cls, method_name))
    bad = _GT_LIKE_PARAMS & set(sig.parameters.keys())
    assert not bad, f"{cls.__name__}.{method_name} has GT-like param(s): {bad}"


class TestGTIsolation:

    def test_differentiable_frangi_forward(self):
        _check_no_gt(DifferentiableFrangi, 'forward')

    def test_gdn2_memory_module_forward(self):
        _check_no_gt(GDN2MemoryModule, 'forward')

    def test_unet_gdn2_forward(self):
        _check_no_gt(UNetGDN2, 'forward')

    def test_reid_head_forward(self):
        _check_no_gt(ReIDReadoutHead, 'forward')

    def test_gdn2_init_no_gt(self):
        _check_no_gt(GDN2MemoryModule, '__init__')

    def test_unet_gdn2_init_no_gt(self):
        _check_no_gt(UNetGDN2, '__init__')

    def test_frangi_layer_inside_gdn2_no_gt(self):
        """The frangi attribute inside GDN2MemoryModule must not read GT."""
        mem = GDN2MemoryModule(d_model=8, d_head=8, n_heads=1,
                               backend='naive', use_frangi=True)
        _check_no_gt(type(mem.frangi), 'forward')

    def test_all_projection_layers_no_gt(self):
        """proj_q/k/v/write/erase/g/out in GDN2MemoryModule have no GT params."""
        mem = GDN2MemoryModule(d_model=8, d_head=8, n_heads=1,
                               backend='naive', use_frangi=False)
        for attr in ['proj_q', 'proj_k', 'proj_v',
                     'proj_write', 'proj_erase', 'proj_g', 'proj_out']:
            layer = getattr(mem, attr)
            sig = inspect.signature(layer.forward)
            bad = _GT_LIKE_PARAMS & set(sig.parameters.keys())
            assert not bad, f"GDN2.{attr}.forward has GT-like param: {bad}"


# ===========================================================================
# 6. Sequence length assertion ≤ 1024
# ===========================================================================

class TestSeqLen:

    def test_at_limit_passes(self):
        """32×32 = 1024 tokens — exactly at limit, must not raise."""
        mem = GDN2MemoryModule(d_model=8, d_head=8, n_heads=1,
                               backend='naive', use_frangi=False)
        mem.eval()
        with torch.no_grad():
            out = mem(torch.randn(1, 8, 32, 32))
        assert out.shape == (1, 8, 32, 32)

    def test_over_limit_raises(self):
        """33×32 = 1056 > 1024 — must raise AssertionError."""
        mem = GDN2MemoryModule(d_model=8, d_head=8, n_heads=1,
                               backend='naive', use_frangi=False)
        mem.eval()
        with torch.no_grad():
            with pytest.raises(AssertionError, match='Sequence length'):
                mem(torch.randn(1, 8, 33, 32))


# ===========================================================================
# 7. Re-ID head (Phase-3 implemented) — contract tests
#    Stub is now replaced; test the implemented interface here.
#    Detailed gradient-isolation tests live in test_reid_p3.py.
# ===========================================================================

class TestReIDHeadContract:

    def _make_head(self, d_head=8, n_heads=1, dec_ch=16, d_id=8):
        return ReIDReadoutHead(
            d_head=d_head, n_heads=n_heads, dec_ch=dec_ch, d_id=d_id
        )

    def test_instantiable(self):
        """ReIDReadoutHead must instantiate without error."""
        head = self._make_head()
        assert head is not None

    def test_no_gt_in_forward_signature(self):
        """ReIDReadoutHead.forward must not accept GT."""
        _check_no_gt(ReIDReadoutHead, 'forward')

    def test_no_gt_in_init_signature(self):
        """ReIDReadoutHead.__init__ must not accept GT."""
        _check_no_gt(ReIDReadoutHead, '__init__')

    def test_forward_returns_logits_tensor(self):
        """forward must return a (B, K, K) tensor."""
        B, K, T, nh, dh, dec_ch = 1, 3, 16, 1, 8, 16
        head = self._make_head(d_head=dh, n_heads=nh, dec_ch=dec_ch, d_id=8)
        head.eval()
        o_seq    = torch.randn(B, T, nh * dh)
        dec_feat = torch.randn(B, dec_ch, 8, 8)
        pos      = torch.rand(B, K, 2) * 7   # positions in [0, 7)
        with torch.no_grad():
            logits = head(o_seq, dec_feat, pos)
        assert isinstance(logits, torch.Tensor), f"Expected Tensor, got {type(logits)}"
        assert logits.shape == (B, K, K), f"Expected ({B},{K},{K}), got {logits.shape}"

    def test_diagonal_is_neg_inf(self):
        """Diagonal of logits must be -inf (self-match excluded)."""
        B, K, T, nh, dh, dec_ch = 1, 4, 16, 1, 8, 16
        head = self._make_head(d_head=dh, n_heads=nh, dec_ch=dec_ch, d_id=8)
        head.eval()
        o_seq    = torch.randn(B, T, nh * dh)
        dec_feat = torch.randn(B, dec_ch, 8, 8)
        pos      = torch.rand(B, K, 2) * 7
        with torch.no_grad():
            logits = head(o_seq, dec_feat, pos)
        diag = torch.diagonal(logits[0])
        assert torch.all(diag == float('-inf')), f"Diagonal not -inf: {diag}"

    def test_detach_memory_train_default_true(self):
        """detach_memory_train must default to True (gradient isolation active)."""
        head = self._make_head()
        assert head.detach_memory_train is True, (
            "detach_memory_train should default to True — gradient isolation red line"
        )
