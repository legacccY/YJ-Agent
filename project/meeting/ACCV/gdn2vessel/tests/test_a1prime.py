"""
test_a1prime.py — A1' iso-parametric linear attention ablation arm tests.

Validates (ACCEPTANCE_CRITERIA P4 pre-registered 2026-06-20):
  1. LinearAttnModule instantiates correctly (same param structure as GDN2MemoryModule).
  2. numel(A1') == numel(A2) within ≤±5% (iso-parametric hard constraint).
  3. A1' forward shape matches A2 / A0' (drop-in compatible at bottleneck).
  4. A1' API parity: _last_o_seq, return_memory=True, no 'gt' in signatures.
  5. UNetGDN2(memory_mode='linear_attn') instantiates and forward runs.
  6. build_model(reid_feat_source='linear_attn') → A1' arm config correct.
  7. Three-arm numel print: A2 / A1' / A0' — confirms iso-param.
  8. A1' forward backward (gradient flows through LinearAttnModule).
  9. A1' reid_ctx path: o_seq non-None, memory_states list of None.
 10. backward compat: use_memory=True still gives delta_rule; use_memory=False gives cnn.

All tests run on CPU; FLA is mocked (same pattern as test_gdn2_p2.py).
"""

from __future__ import annotations

import inspect
import sys
import types
from pathlib import Path

import pytest
import torch

# --------------------------------------------------------------------------- #
#  Path setup
# --------------------------------------------------------------------------- #

_repo_root = Path(__file__).parent.parent
_src_dir = _repo_root / 'src'
if str(_src_dir) not in sys.path:
    sys.path.insert(0, str(_src_dir))


# --------------------------------------------------------------------------- #
#  Mock FLA (no real kernel needed for CPU tests)
# --------------------------------------------------------------------------- #

def _make_fake_gdn2_fn():
    """Minimal mock: returns v as output + optional zero final_state."""
    def fake_fn(q, k, v, beta, g, output_final_state=False):
        B, T, nh, dh = v.shape
        state = torch.zeros(B, nh, dh, dh) if output_final_state else None
        return v.clone(), state
    return fake_fn


def _patch_fla():
    fake_fla   = types.ModuleType('fla')
    fake_ops   = types.ModuleType('fla.ops')
    fake_gdr   = types.ModuleType('fla.ops.gated_delta_rule')
    fake_naive = types.ModuleType('fla.ops.gated_delta_rule.naive')
    fake_chunk = types.ModuleType('fla.ops.gated_delta_rule.chunk')
    fake_naive.naive_chunk_gated_delta_rule = _make_fake_gdn2_fn()
    fake_chunk.chunk_gated_delta_rule       = _make_fake_gdn2_fn()
    sys.modules.setdefault('fla',                              fake_fla)
    sys.modules.setdefault('fla.ops',                          fake_ops)
    sys.modules.setdefault('fla.ops.gated_delta_rule',         fake_gdr)
    sys.modules.setdefault('fla.ops.gated_delta_rule.naive',   fake_naive)
    sys.modules.setdefault('fla.ops.gated_delta_rule.chunk',   fake_chunk)


_patch_fla()


# --------------------------------------------------------------------------- #
#  Imports
# --------------------------------------------------------------------------- #

from models.unet_gdn2 import (
    GDN2MemoryModule,
    LinearAttnModule,
    UNetGDN2,
)
from train_reid_pilot import build_model


# --------------------------------------------------------------------------- #
#  Helper: tiny args for build_model
# --------------------------------------------------------------------------- #

def _tiny_args(
    reid_feat_source: str = 'linear_attn',
    no_detach_memory: bool = False,
    reid_breakpoint_source: str = 'gt_skeleton',
):
    class A:
        pass
    a = A()
    a.reid_feat_source       = reid_feat_source
    a.no_detach_memory       = no_detach_memory
    a.reid_breakpoint_source = reid_breakpoint_source
    a.base_ch   = 8
    a.d_head    = 8
    a.n_heads   = 1
    a.reid_d_id = 8
    a.backend   = 'naive'
    return a


# --------------------------------------------------------------------------- #
#  1. LinearAttnModule instantiation
# --------------------------------------------------------------------------- #

class TestLinearAttnModuleInstantiation:

    def _make_la(self, d_model=16, d_head=8, n_heads=1, use_frangi=True):
        return LinearAttnModule(
            d_model=d_model,
            d_head=d_head,
            n_heads=n_heads,
            directions=1,
            use_frangi=use_frangi,
        )

    def test_instantiates_no_error(self):
        la = self._make_la()
        assert la is not None

    def test_has_all_projection_layers(self):
        """A1' must have the same projection layers as GDN2MemoryModule."""
        la = self._make_la(d_model=16)
        for attr in ['proj_q', 'proj_k', 'proj_v',
                     'proj_write', 'proj_erase', 'proj_g', 'proj_out', 'norm']:
            assert hasattr(la, attr), f"LinearAttnModule missing attribute: {attr}"

    def test_has_frangi_when_use_frangi_true(self):
        la = self._make_la(use_frangi=True)
        assert hasattr(la, 'frangi') and la.frangi is not None
        assert la.alpha_w is not None
        assert la.alpha_e is not None

    def test_frangi_absent_when_use_frangi_false(self):
        la = self._make_la(use_frangi=False)
        assert la.frangi is None
        assert la.alpha_w is None
        assert la.alpha_e is None

    def test_no_gdn2_kernel_attr(self):
        """LinearAttnModule must NOT store _gdn2_fn (it is stateless)."""
        la = self._make_la()
        assert not hasattr(la, '_gdn2_fn'), (
            "LinearAttnModule should not have _gdn2_fn (stateless, no FLA kernel)"
        )


# --------------------------------------------------------------------------- #
#  2. numel(A1') == numel(A2) within ±5% (ACCEPTANCE hard constraint)
# --------------------------------------------------------------------------- #

class TestIsometricNurel:
    """
    ACCEPTANCE_CRITERIA P4 preregistered: full-model trainable numel(A1') vs
    numel(A2) must differ by ≤±5%.  Failure here blocks the ablation.
    """

    # Configs mirroring the production pilot defaults:
    #   base_ch=32, d_head=64, n_heads=1
    @pytest.mark.parametrize("base_ch,d_head,n_heads", [
        (8,  8,  1),   # small (fast CI)
        (32, 64, 1),   # production pilot defaults
    ])
    def test_numel_diff_within_5pct(self, base_ch, d_head, n_heads):
        """
        Three-arm numel comparison.  A1' vs A2 must be ≤±5%.
        Printed to stdout for paper footnote / audit trail.
        """
        def count(model):
            return sum(p.numel() for p in model.parameters() if p.requires_grad)

        # A2: stateful delta-rule associative memory
        m_a2 = UNetGDN2(
            in_ch=1, out_ch=1, base_ch=base_ch,
            d_head=d_head, n_heads=n_heads,
            memory_mode='delta_rule',
            use_frangi=True,
            use_reid_head=True, reid_d_id=d_head,
            reid_feat_source='memory',
        )
        # A1': stateless linear attention (iso-param)
        m_a1p = UNetGDN2(
            in_ch=1, out_ch=1, base_ch=base_ch,
            d_head=d_head, n_heads=n_heads,
            memory_mode='linear_attn',
            use_frangi=True,
            use_reid_head=True, reid_d_id=d_head,
            reid_feat_source='linear_attn',
        )
        # A0': pure CNN (no attention module)
        m_a0p = UNetGDN2(
            in_ch=1, out_ch=1, base_ch=base_ch,
            d_head=d_head, n_heads=n_heads,
            memory_mode='cnn',
            use_frangi=False,
            use_reid_head=True, reid_d_id=d_head,
            reid_feat_source='cnn',
        )

        n_a2  = count(m_a2)
        n_a1p = count(m_a1p)
        n_a0p = count(m_a0p)

        diff_pct = abs(n_a1p - n_a2) / max(n_a2, 1) * 100.0

        print(f"\n[numel audit] base_ch={base_ch} d_head={d_head} n_heads={n_heads}")
        print(f"  A2  (delta_rule):   {n_a2:,}")
        print(f"  A1' (linear_attn):  {n_a1p:,}  (diff vs A2: {diff_pct:+.2f}%)")
        print(f"  A0' (cnn):          {n_a0p:,}")

        assert diff_pct <= 5.0, (
            f"ACCEPTANCE FAIL: numel(A1')={n_a1p:,} vs numel(A2)={n_a2:,} "
            f"diff={diff_pct:.2f}% > 5% threshold. "
            f"Adjust LinearAttnModule projection dims to align."
        )

    def test_a1prime_has_more_numel_than_a0prime(self):
        """A1' (has attention module) should have strictly more params than A0' (pure CNN)."""
        def count(model):
            return sum(p.numel() for p in model.parameters() if p.requires_grad)

        m_a1p = UNetGDN2(
            in_ch=1, out_ch=1, base_ch=8, d_head=8, n_heads=1,
            memory_mode='linear_attn', use_frangi=True,
            use_reid_head=True, reid_d_id=8, reid_feat_source='linear_attn',
        )
        m_a0p = UNetGDN2(
            in_ch=1, out_ch=1, base_ch=8, d_head=8, n_heads=1,
            memory_mode='cnn', use_frangi=False,
            use_reid_head=True, reid_d_id=8, reid_feat_source='cnn',
        )
        assert count(m_a1p) > count(m_a0p), (
            "A1' should have more params than A0' (attention module adds params)"
        )


# --------------------------------------------------------------------------- #
#  3. Forward shape
# --------------------------------------------------------------------------- #

class TestLinearAttnForwardShape:

    def test_output_shape_matches_input(self):
        """LinearAttnModule output shape == input shape."""
        la = LinearAttnModule(
            d_model=8, d_head=8, n_heads=1, directions=1, use_frangi=False
        )
        la.eval()
        x = torch.randn(1, 8, 8, 8)   # 64 tokens < 1024
        with torch.no_grad():
            out = la(x)
        assert out.shape == x.shape, f"Expected {x.shape}, got {out.shape}"

    @pytest.mark.parametrize("directions", [1, 2, 4])
    def test_output_shape_multidir(self, directions):
        """Shape must be preserved for all direction counts."""
        la = LinearAttnModule(
            d_model=8, d_head=8, n_heads=1, directions=directions, use_frangi=False
        )
        la.eval()
        x = torch.randn(1, 8, 8, 8)
        with torch.no_grad():
            out = la(x)
        assert out.shape == x.shape, (
            f"directions={directions}: expected {x.shape}, got {out.shape}"
        )

    def test_at_seq_limit_passes(self):
        """32×32 = 1024 tokens — exactly at limit, must not raise."""
        la = LinearAttnModule(d_model=8, d_head=8, n_heads=1, use_frangi=False)
        la.eval()
        with torch.no_grad():
            out = la(torch.randn(1, 8, 32, 32))
        assert out.shape == (1, 8, 32, 32)

    def test_over_seq_limit_raises(self):
        """33×32 = 1056 > 1024 — must raise AssertionError."""
        la = LinearAttnModule(d_model=8, d_head=8, n_heads=1, use_frangi=False)
        la.eval()
        with pytest.raises(AssertionError):
            la(torch.randn(1, 8, 33, 32))


# --------------------------------------------------------------------------- #
#  4. API parity with GDN2MemoryModule
# --------------------------------------------------------------------------- #

class TestLinearAttnAPIParity:

    def test_last_o_seq_set_after_forward(self):
        """_last_o_seq must be set after forward (ReIDReadoutHead reads it)."""
        la = LinearAttnModule(d_model=8, d_head=8, n_heads=1, use_frangi=False)
        la.eval()
        x = torch.randn(1, 8, 8, 8)
        with torch.no_grad():
            la(x)
        assert hasattr(la, '_last_o_seq'), "_last_o_seq not set after forward"
        T = 8 * 8
        assert la._last_o_seq.shape == (1, T, 8 * 1), (
            f"_last_o_seq shape wrong: {la._last_o_seq.shape}"
        )

    def test_return_memory_gives_tuple(self):
        """return_memory=True must return (out, states_list) tuple."""
        la = LinearAttnModule(d_model=8, d_head=8, n_heads=1, use_frangi=False)
        la.eval()
        x = torch.randn(1, 8, 8, 8)
        with torch.no_grad():
            result = la(x, return_memory=True)
        assert isinstance(result, tuple), "return_memory=True should give tuple"
        out, states = result
        assert out.shape == x.shape
        assert isinstance(states, list)
        assert all(s is None for s in states), (
            "A1' states_list should contain all None (no stateful memory)"
        )

    def test_no_gt_in_forward_signature(self):
        """LinearAttnModule.forward must not accept GT."""
        sig = inspect.signature(LinearAttnModule.forward)
        bad = {'gt', 'target', 'label', 'mask_gt', 'segmentation'}
        found = bad & set(sig.parameters.keys())
        assert not found, f"LinearAttnModule.forward has GT-like params: {found}"

    def test_no_gt_in_init_signature(self):
        """LinearAttnModule.__init__ must not accept GT."""
        sig = inspect.signature(LinearAttnModule.__init__)
        bad = {'gt', 'target', 'label', 'mask_gt', 'segmentation'}
        found = bad & set(sig.parameters.keys())
        assert not found, f"LinearAttnModule.__init__ has GT-like params: {found}"


# --------------------------------------------------------------------------- #
#  5. UNetGDN2 with memory_mode='linear_attn'
# --------------------------------------------------------------------------- #

class TestUNetGDN2A1Prime:

    def test_instantiates_with_linear_attn_mode(self):
        """memory_mode='linear_attn' must not raise."""
        m = UNetGDN2(
            in_ch=1, out_ch=1, base_ch=8, d_head=8, n_heads=1,
            memory_mode='linear_attn', use_frangi=True,
            use_reid_head=True, reid_d_id=8, reid_feat_source='linear_attn',
        )
        assert m is not None
        assert m.memory_mode == 'linear_attn'
        assert m.memory is None, "A1' should NOT have GDN2MemoryModule"
        assert m.linear_attn is not None, "A1' should have LinearAttnModule"
        assert isinstance(m.linear_attn, LinearAttnModule)

    def test_forward_shape_a1prime(self):
        """A1' arm: forward produces correct logit shape."""
        m = UNetGDN2(
            in_ch=1, out_ch=1, base_ch=8, d_head=8, n_heads=1,
            memory_mode='linear_attn', use_frangi=True,
            use_reid_head=True, reid_d_id=8, reid_feat_source='linear_attn',
        )
        m.eval()
        x = torch.randn(1, 1, 64, 64)
        with torch.no_grad():
            logits = m(x)
        assert logits.shape == (1, 1, 64, 64), f"Got {logits.shape}"

    def test_reid_ctx_o_seq_not_none_a1prime(self):
        """A1' arm: return_reid_ctx=True gives non-None o_seq."""
        m = UNetGDN2(
            in_ch=1, out_ch=1, base_ch=8, d_head=8, n_heads=1,
            memory_mode='linear_attn', use_frangi=True,
            use_reid_head=True, reid_d_id=8, reid_feat_source='linear_attn',
        )
        m.eval()
        x = torch.randn(1, 1, 64, 64)
        with torch.no_grad():
            logits, ctx = m(x, return_reid_ctx=True)
        assert ctx['o_seq'] is not None, "A1' arm: o_seq should not be None"
        assert ctx['memory_state'] is not None, "A1' arm: memory_state should be a list"
        assert all(s is None for s in ctx['memory_state']), (
            "A1' states should all be None (no stateful memory)"
        )

    def test_backward_passes_a1prime(self):
        """A1' arm: backward through seg loss must not crash."""
        m = UNetGDN2(
            in_ch=1, out_ch=1, base_ch=8, d_head=8, n_heads=1,
            memory_mode='linear_attn', use_frangi=True,
            use_reid_head=True, reid_d_id=8, reid_feat_source='linear_attn',
        )
        m.train()
        x = torch.randn(2, 1, 64, 64)
        gt = (torch.rand(2, 1, 64, 64) > 0.7).float()
        fov = torch.ones(2, 1, 64, 64)
        logits = m(x)
        prob = torch.sigmoid(logits)
        loss = ((prob - gt) ** 2 * fov).sum()
        loss.backward()
        # Check at least linear_attn params get gradient
        for name, param in m.linear_attn.named_parameters():
            if param.requires_grad:
                assert param.grad is not None, (
                    f"LinearAttnModule param '{name}' has no gradient after backward"
                )
                break  # at least one is enough

    def test_three_arm_memory_mode_properties(self):
        """All three memory_mode values produce correct attribute states."""
        # A2
        m2 = UNetGDN2(in_ch=1, out_ch=1, base_ch=8, d_head=8, n_heads=1,
                      memory_mode='delta_rule', use_reid_head=False)
        assert m2.memory is not None
        assert m2.linear_attn is None
        assert m2.memory_mode == 'delta_rule'
        assert m2.use_memory is True

        # A1'
        m1p = UNetGDN2(in_ch=1, out_ch=1, base_ch=8, d_head=8, n_heads=1,
                       memory_mode='linear_attn', use_reid_head=False)
        assert m1p.memory is None
        assert m1p.linear_attn is not None
        assert m1p.memory_mode == 'linear_attn'
        assert m1p.use_memory is False   # linear_attn != delta_rule

        # A0'
        m0p = UNetGDN2(in_ch=1, out_ch=1, base_ch=8, d_head=8, n_heads=1,
                       memory_mode='cnn', use_reid_head=False)
        assert m0p.memory is None
        assert m0p.linear_attn is None
        assert m0p.memory_mode == 'cnn'
        assert m0p.use_memory is False


# --------------------------------------------------------------------------- #
#  6. build_model A1' arm config
# --------------------------------------------------------------------------- #

class TestBuildModelA1Prime:

    def test_build_a1prime_arm(self):
        """build_model with linear_attn → A1' config."""
        args = _tiny_args(reid_feat_source='linear_attn')
        model = build_model(args)
        assert model.memory_mode == 'linear_attn'
        assert model.linear_attn is not None
        assert model.memory is None
        assert model.reid_head.feat_source == 'linear_attn'
        assert model.reid_head.detach_memory_train is True

    def test_build_a1prime_signature_no_gt(self):
        """build_model A1': linear_attn forward must not accept 'gt' (R5 guard)."""
        args = _tiny_args(reid_feat_source='linear_attn')
        model = build_model(args)
        sig = inspect.signature(model.linear_attn.forward)
        bad = {'gt', 'target', 'gt_mask', 'label', 'annotation'}
        found = bad & set(sig.parameters.keys())
        assert not found, f"R5 VIOLATED: LinearAttnModule.forward has GT-like params: {found}"

    def test_build_all_three_arms_no_error(self):
        """All three arms must build without assertion errors."""
        for src in ('memory', 'linear_attn', 'cnn'):
            args = _tiny_args(reid_feat_source=src)
            model = build_model(args)
            assert model is not None, f"build_model failed for reid_feat_source={src}"
            assert model.reid_head is not None
            assert model.reid_head.feat_source == src


# --------------------------------------------------------------------------- #
#  7. Three-arm numel print (standalone utility, run-always)
# --------------------------------------------------------------------------- #

class TestThreeArmNumelPrint:
    """
    Prints three-arm numel to stdout for paper footnote and audit.
    Not a functional gate beyond the ±5% check in TestIsometricNurel —
    this is the reference printout format matching ACCEPTANCE requirement
    'Three臂 numel 实测值写进论文表脚注留痕'.
    """

    def test_print_three_arm_numel_pilot_defaults(self):
        """
        Production pilot defaults: base_ch=32, d_head=64, n_heads=1.
        Prints A2 / A1' / A0' numel for paper table footnote.
        """
        def count(model):
            return sum(p.numel() for p in model.parameters() if p.requires_grad)

        m_a2 = UNetGDN2(
            in_ch=1, out_ch=1, base_ch=32, d_head=64, n_heads=1,
            memory_mode='delta_rule', use_frangi=True,
            use_reid_head=True, reid_d_id=64, reid_feat_source='memory',
        )
        m_a1p = UNetGDN2(
            in_ch=1, out_ch=1, base_ch=32, d_head=64, n_heads=1,
            memory_mode='linear_attn', use_frangi=True,
            use_reid_head=True, reid_d_id=64, reid_feat_source='linear_attn',
        )
        m_a0p = UNetGDN2(
            in_ch=1, out_ch=1, base_ch=32, d_head=64, n_heads=1,
            memory_mode='cnn', use_frangi=False,
            use_reid_head=True, reid_d_id=64, reid_feat_source='cnn',
        )

        n_a2  = count(m_a2)
        n_a1p = count(m_a1p)
        n_a0p = count(m_a0p)
        diff_a1p_a2 = (n_a1p - n_a2) / max(n_a2, 1) * 100.0

        print("\n" + "=" * 60)
        print("[THREE-ARM NUMEL AUDIT] base_ch=32, d_head=64, n_heads=1")
        print(f"  A2  (delta_rule):   {n_a2:>12,}  (headline)")
        print(f"  A1' (linear_attn):  {n_a1p:>12,}  (diff vs A2: {diff_a1p_a2:+.3f}%)")
        print(f"  A0' (cnn):          {n_a0p:>12,}  (zero-hypothesis)")
        print("=" * 60)

        # Hard gate (≤±5%)
        assert abs(diff_a1p_a2) <= 5.0, (
            f"ACCEPTANCE FAIL: numel(A1') vs numel(A2) diff={diff_a1p_a2:.2f}% > 5%"
        )


# --------------------------------------------------------------------------- #
#  8 & 9. Backward + reid_ctx gradient isolation (A1' arm)
# --------------------------------------------------------------------------- #

class TestA1PrimeGradientIsolation:
    """
    When detach_memory_train=True (default), reid loss backward must NOT
    produce gradients in LinearAttnModule parameters.
    """

    def _run_reid_backward_a1prime(self, detach: bool = True):
        from models.reid_loss import compute_match_loss
        from train_reid_pilot import seg_loss

        args = _tiny_args(reid_feat_source='linear_attn', no_detach_memory=not detach)
        model = build_model(args)
        model.train()

        for p in model.parameters():
            p.grad = None

        B, H, W = 2, 64, 64
        x   = torch.randn(B, 1, H, W)
        gt  = (torch.rand(B, 1, H, W) > 0.7).float()
        fov = torch.ones(B, 1, H, W)

        logits, reid_ctx = model(x, return_reid_ctx=True)
        l_seg = seg_loss(logits, gt, fov)

        dec_feat = reid_ctx['dec_feat']
        H_dec, W_dec = dec_feat.shape[-2], dec_feat.shape[-1]
        K = 4
        positions = torch.zeros(B, K, 2)
        positions[..., 0] = H_dec / 2
        positions[..., 1] = W_dec / 2

        o_seq = reid_ctx['o_seq']
        assert o_seq is not None, "A1' arm must give non-None o_seq"

        reid_logits = model.reid_head(
            o_seq=o_seq,
            dec_feat=dec_feat,
            breakpoint_positions=positions,
        )
        labels = torch.zeros(B, K, K)
        labels[:, 0, 1] = 1.0
        labels[:, 1, 0] = 1.0

        l_reid = compute_match_loss(reid_logits, labels)
        l_reid.backward()

        return model

    def test_linear_attn_params_no_grad_when_detach_on(self):
        """
        detach=True: reid loss backward must produce 0/None grad in LinearAttnModule.
        """
        model = self._run_reid_backward_a1prime(detach=True)
        for name, param in model.linear_attn.named_parameters():
            assert param.grad is None or param.grad.abs().max().item() == 0.0, (
                f"LinearAttnModule param '{name}' has nonzero gradient after reid loss "
                f"backward (detach=True) — detach barriers not working for A1' arm!"
            )

    def test_reid_head_params_get_grad_when_detach_on(self):
        """reid_head params must get gradient even when detach=True."""
        model = self._run_reid_backward_a1prime(detach=True)
        for name, param in model.reid_head.named_parameters():
            assert param.grad is not None, (
                f"reid_head param '{name}' has no gradient"
            )
            assert param.grad.abs().sum().item() > 0, (
                f"reid_head param '{name}' gradient is all-zero"
            )


# --------------------------------------------------------------------------- #
#  10. Backward compat: use_memory flag
# --------------------------------------------------------------------------- #

class TestBackwardCompat:

    def test_use_memory_true_gives_delta_rule(self):
        """use_memory=True (old API) → memory_mode='delta_rule'."""
        m = UNetGDN2(in_ch=1, out_ch=1, base_ch=8, use_memory=True,
                     use_reid_head=False)
        assert m.memory_mode == 'delta_rule'
        assert m.memory is not None
        assert m.linear_attn is None
        assert m.use_memory is True

    def test_use_memory_false_gives_cnn(self):
        """use_memory=False (old API) → memory_mode='cnn'."""
        m = UNetGDN2(in_ch=1, out_ch=1, base_ch=8, use_memory=False,
                     use_reid_head=False)
        assert m.memory_mode == 'cnn'
        assert m.memory is None
        assert m.linear_attn is None
        assert m.use_memory is False

    def test_memory_mode_overrides_use_memory(self):
        """Explicit memory_mode wins over use_memory (new API takes priority)."""
        # Contradictory: use_memory=False but memory_mode='delta_rule'
        m = UNetGDN2(in_ch=1, out_ch=1, base_ch=8,
                     use_memory=False, memory_mode='delta_rule',
                     use_reid_head=False)
        assert m.memory_mode == 'delta_rule'
        assert m.memory is not None
