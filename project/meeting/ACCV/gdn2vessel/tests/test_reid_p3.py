"""
Phase-3 unit tests for gdn2vessel Claim 2: ReIDReadoutHead + reid_loss.

Test categories:
  1. Gradient isolation (致命-1 — CRITICAL red line)
       Backward through L_match must NOT create gradients in o_seq / dec_feat
       tensors that simulate upstream memory/encoder parameters.
  2. Head signature: no 'gt' parameter in forward.
  3. Shape / symmetry / diagonal assertions on match logits.
  4. Ablation flag A3 (detach_memory_train=False): gradients ARE allowed.
  5. ReIDLoss combined loss: output is scalar, reid off → equals seg_loss.
  6. L_match: label=1 pair should have lower loss than label=0 pair.
  7. Detach presence: inspect that .detach() is called inside head.forward.

All tests run on CPU; no FLA / GPU required.
FLA is mocked (same pattern as test_shapes.py / test_gdn2_p2.py).
"""

from __future__ import annotations

import inspect
import sys
import types
from pathlib import Path

import pytest
import torch
import torch.nn as nn

# --------------------------------------------------------------------------- #
#  Path setup
# --------------------------------------------------------------------------- #

_repo_root = Path(__file__).parent.parent
_src_dir = _repo_root / 'src'
if str(_src_dir) not in sys.path:
    sys.path.insert(0, str(_src_dir))


# --------------------------------------------------------------------------- #
#  Mock FLA
# --------------------------------------------------------------------------- #

def _make_fake_gdn2_fn():
    def fake_fn(q, k, v, beta, g, output_final_state=False):
        # Minimal mock: return v as output + a plausible final state
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
    fake_chunk.chunk_gated_delta_rule = _make_fake_gdn2_fn()
    sys.modules.setdefault('fla', fake_fla)
    sys.modules.setdefault('fla.ops', fake_ops)
    sys.modules.setdefault('fla.ops.gated_delta_rule', fake_gdr)
    sys.modules.setdefault('fla.ops.gated_delta_rule.naive', fake_naive)
    sys.modules.setdefault('fla.ops.gated_delta_rule.chunk', fake_chunk)


_patch_fla()

from models.unet_gdn2 import ReIDReadoutHead, UNetGDN2
from models.reid_loss import (
    ReIDLoss,
    compute_match_loss,
    compute_contrastive_loss,
    compute_reid_combined_loss,
)


# --------------------------------------------------------------------------- #
#  Helpers
# --------------------------------------------------------------------------- #

def _make_head(
    d_head: int = 16,
    n_heads: int = 1,
    dec_ch: int = 32,
    d_id: int = 16,
    detach_memory_train: bool = True,
) -> ReIDReadoutHead:
    return ReIDReadoutHead(
        d_head=d_head,
        n_heads=n_heads,
        dec_ch=dec_ch,
        d_id=d_id,
        detach_memory_train=detach_memory_train,
    )


def _make_inputs(B: int = 2, K: int = 4, T: int = 16,
                 nh: int = 1, dh: int = 16, dec_ch: int = 32,
                 H_dec: int = 8, W_dec: int = 8):
    """Create mock tensors simulating memory + decoder outputs."""
    # o_seq: (B, T, nh*dh)
    o_seq    = torch.randn(B, T, nh * dh, requires_grad=True)
    # dec_feat: (B, dec_ch, H_dec, W_dec)
    dec_feat = torch.randn(B, dec_ch, H_dec, W_dec, requires_grad=True)
    # breakpoint_positions: (B, K, 2) float in [0, H_dec) x [0, W_dec)
    pos = torch.rand(B, K, 2)
    pos[..., 0] = pos[..., 0] * (H_dec - 1)
    pos[..., 1] = pos[..., 1] * (W_dec - 1)
    return o_seq, dec_feat, pos


# ===========================================================================
# 1. Gradient isolation (致命-1 — CRITICAL red line)
#    L_match backward must NOT touch o_seq / dec_feat upstream gradients
#    when detach_memory_train=True.
# ===========================================================================

class TestGradientIsolation:

    def _run_and_backward(self, detach: bool):
        """
        Forward pass through ReIDReadoutHead + L_match backward.
        Returns (o_seq.grad, dec_feat.grad).
        """
        B, K, T, nh, dh, dec_ch = 2, 4, 16, 1, 16, 32
        head = _make_head(d_head=dh, n_heads=nh, dec_ch=dec_ch, d_id=16,
                          detach_memory_train=detach)
        o_seq, dec_feat, pos = _make_inputs(B=B, K=K, T=T,
                                            nh=nh, dh=dh, dec_ch=dec_ch)
        # Make sure inputs have grad enabled
        o_seq.requires_grad_(True)
        dec_feat.requires_grad_(True)

        logits = head(o_seq, dec_feat, pos)  # (B, K, K)

        # Binary same-root labels (synthetic): i<K/2 same root as j<K/2, etc.
        labels = torch.zeros(B, K, K)
        labels[:, :K//2, :K//2] = 1.0
        labels[:, K//2:, K//2:] = 1.0

        loss = compute_match_loss(logits, labels)
        loss.backward()

        return o_seq.grad, dec_feat.grad

    def test_detach_on__o_seq_grad_is_none(self):
        """
        ★ Critical: detach_memory_train=True → L_match backward must not
        produce gradient in o_seq (simulates upstream memory parameters).
        """
        o_grad, _ = self._run_and_backward(detach=True)
        assert o_grad is None, (
            f"detach=True: o_seq.grad should be None (detach1 barrier), "
            f"got grad with norm={o_grad.norm().item():.4f}"
        )

    def test_detach_on__dec_feat_grad_is_none(self):
        """
        ★ Critical: detach_memory_train=True → L_match backward must not
        produce gradient in dec_feat (simulates upstream encoder/decoder params).
        """
        _, df_grad = self._run_and_backward(detach=True)
        assert df_grad is None, (
            f"detach=True: dec_feat.grad should be None (detach3 barrier), "
            f"got grad with norm={df_grad.norm().item():.4f}"
        )

    def test_detach_off__o_seq_grad_exists(self):
        """
        Ablation A3 sanity: detach_memory_train=False → gradients flow back
        (this is the ablation-only path that demonstrates detach is load-bearing).
        """
        o_grad, _ = self._run_and_backward(detach=False)
        assert o_grad is not None, (
            "detach=False (A3 ablation): o_seq.grad should exist"
        )
        assert o_grad.abs().sum() > 0, (
            "detach=False: o_seq.grad is all-zero — gradient not flowing"
        )

    def test_detach_off__dec_feat_grad_exists(self):
        """Ablation A3: dec_feat.grad should exist when detach=False."""
        _, df_grad = self._run_and_backward(detach=False)
        assert df_grad is not None, (
            "detach=False (A3 ablation): dec_feat.grad should exist"
        )
        assert df_grad.abs().sum() > 0

    def test_head_params_get_grad_when_detach_on(self):
        """
        Head's own parameters (mem_proj/loc_proj/fuse/log_temp) MUST receive
        gradients even when the upstream detaches are active.
        """
        B, K, T, nh, dh, dec_ch = 2, 4, 16, 1, 16, 32
        head = _make_head(d_head=dh, n_heads=nh, dec_ch=dec_ch, d_id=16,
                          detach_memory_train=True)
        o_seq, dec_feat, pos = _make_inputs(B=B, K=K, T=T,
                                            nh=nh, dh=dh, dec_ch=dec_ch)
        logits = head(o_seq, dec_feat, pos)
        labels = torch.zeros(B, K, K)
        labels[:, 0, 1] = 1.0
        labels[:, 1, 0] = 1.0
        loss = compute_match_loss(logits, labels)
        loss.backward()

        for name, param in head.named_parameters():
            assert param.grad is not None, (
                f"Head param '{name}' has no gradient — loss not flowing into head"
            )
            assert param.grad.abs().sum() > 0, (
                f"Head param '{name}' gradient is all-zero"
            )

    def test_memory_state_detach(self):
        """
        memory_state passed to head.forward must be detached when detach=True.
        Verify by checking that a fake memory state tensor gets no gradient.
        """
        B, K, T, nh, dh, dec_ch = 1, 3, 9, 1, 16, 32
        head = _make_head(d_head=dh, n_heads=nh, dec_ch=dec_ch, d_id=16,
                          detach_memory_train=True)
        o_seq, dec_feat, pos = _make_inputs(B=B, K=K, T=T,
                                            nh=nh, dh=dh, dec_ch=dec_ch,
                                            H_dec=4, W_dec=4)
        # Fake memory state (B, nh, dh, dh)
        mem_state = torch.randn(B, nh, dh, dh, requires_grad=True)

        logits = head(o_seq, dec_feat, pos, memory_state=mem_state)
        labels = torch.zeros(B, K, K)
        loss = compute_match_loss(logits, labels)
        loss.backward()

        # mem_state should have no gradient (detach2 barrier)
        assert mem_state.grad is None, (
            f"memory_state.grad should be None (detach2 barrier); "
            f"got norm={mem_state.grad.norm().item():.4f}"
        )


# ===========================================================================
# 2. Signature: no 'gt' param in forward
# ===========================================================================

_GT_LIKE = {'gt', 'target', 'label', 'mask_gt', 'segmentation',
            'gt_mask', 'ann', 'annotation'}


class TestHeadSignature:

    def test_no_gt_in_forward(self):
        sig = inspect.signature(ReIDReadoutHead.forward)
        bad = _GT_LIKE & set(sig.parameters.keys())
        assert not bad, f"ReIDReadoutHead.forward has GT-like params: {bad}"

    def test_no_gt_in_init(self):
        sig = inspect.signature(ReIDReadoutHead.__init__)
        bad = _GT_LIKE & set(sig.parameters.keys())
        assert not bad, f"ReIDReadoutHead.__init__ has GT-like params: {bad}"

    def test_forward_accepts_breakpoint_positions(self):
        """forward must accept breakpoint_positions as argument."""
        sig = inspect.signature(ReIDReadoutHead.forward)
        assert 'breakpoint_positions' in sig.parameters


# ===========================================================================
# 3. Shape / symmetry / diagonal assertions
# ===========================================================================

class TestLogitProperties:

    def _get_logits(self, B=2, K=5):
        T, nh, dh, dec_ch = 16, 1, 16, 32
        head = _make_head(d_head=dh, n_heads=nh, dec_ch=dec_ch, d_id=16)
        head.eval()
        o_seq, dec_feat, pos = _make_inputs(B=B, K=K, T=T,
                                            nh=nh, dh=dh, dec_ch=dec_ch)
        with torch.no_grad():
            logits = head(o_seq, dec_feat, pos)
        return logits

    def test_output_shape(self):
        """logits must be (B, K, K)."""
        B, K = 2, 5
        logits = self._get_logits(B=B, K=K)
        assert logits.shape == (B, K, K), f"Expected ({B},{K},{K}), got {logits.shape}"

    def test_diagonal_is_neg_inf(self):
        """Diagonal must be -inf (self-match excluded)."""
        logits = self._get_logits(B=1, K=4)
        diag = torch.diagonal(logits[0])
        assert torch.all(diag == float('-inf')), (
            f"Diagonal should be -inf, got {diag}"
        )

    def test_symmetric(self):
        """logits[b, i, j] == logits[b, j, i] (symmetric cosine similarity)."""
        logits = self._get_logits(B=2, K=4)
        # Set diagonal to 0 for symmetry check (diagonal is -inf on both sides)
        K = logits.shape[-1]
        diag_mask = torch.eye(K, dtype=torch.bool)
        l = logits.clone()
        l[:, diag_mask] = 0.0
        assert torch.allclose(l, l.transpose(1, 2), atol=1e-5), (
            "logits are not symmetric"
        )

    def test_off_diagonal_finite(self):
        """Off-diagonal entries must be finite (not NaN/inf from bad ops)."""
        logits = self._get_logits(B=2, K=4)
        K = logits.shape[-1]
        diag_mask = torch.eye(K, dtype=torch.bool)
        off_diag = logits[:, ~diag_mask]
        assert torch.isfinite(off_diag).all(), (
            f"Off-diagonal logits contain non-finite values: {off_diag}"
        )

    @pytest.mark.parametrize("K", [2, 3, 6])
    def test_shape_various_K(self, K):
        logits = self._get_logits(B=1, K=K)
        assert logits.shape == (1, K, K)


# ===========================================================================
# 4. UNetGDN2 + reid_ctx interface (return_reid_ctx=True)
# ===========================================================================

class TestUNetGDN2ReIDCtx:

    def _make_model(self, use_reid_head=False):
        return UNetGDN2(
            in_ch=1, out_ch=1, base_ch=8,
            d_head=8, n_heads=1,
            use_memory=True, backend='naive',
            use_reid_head=use_reid_head,
            dec_feat_layer='dec3',
            reid_d_id=8,
        )

    def test_forward_default_returns_logits_only(self):
        """Default return_reid_ctx=False → returns logits tensor only."""
        model = self._make_model()
        model.eval()
        x = torch.randn(1, 1, 64, 64)
        with torch.no_grad():
            out = model(x)
        assert isinstance(out, torch.Tensor), (
            f"Expected Tensor, got {type(out)}"
        )
        assert out.shape == (1, 1, 64, 64)

    def test_forward_with_reid_ctx_returns_tuple(self):
        """return_reid_ctx=True → returns (logits, dict)."""
        model = self._make_model()
        model.eval()
        x = torch.randn(1, 1, 64, 64)
        with torch.no_grad():
            out = model(x, return_reid_ctx=True)
        assert isinstance(out, tuple) and len(out) == 2, (
            f"Expected 2-tuple, got {type(out)}"
        )
        logits, ctx = out
        assert isinstance(logits, torch.Tensor)
        assert logits.shape == (1, 1, 64, 64)
        assert isinstance(ctx, dict)

    def test_reid_ctx_keys(self):
        """reid_ctx must contain o_seq / memory_state / dec_feat / H_bot / W_bot."""
        model = self._make_model()
        model.eval()
        x = torch.randn(1, 1, 64, 64)
        with torch.no_grad():
            _, ctx = model(x, return_reid_ctx=True)
        for key in ('o_seq', 'memory_state', 'dec_feat', 'H_bot', 'W_bot'):
            assert key in ctx, f"Missing key '{key}' in reid_ctx"

    def test_o_seq_shape(self):
        """o_seq in reid_ctx must be (B, T, nh*d_head)."""
        model = self._make_model()
        model.eval()
        x = torch.randn(1, 1, 64, 64)
        with torch.no_grad():
            _, ctx = model(x, return_reid_ctx=True)
        o_seq = ctx['o_seq']
        # bottleneck for 64×64 image with base_ch=8: H_bot=4, W_bot=4, T=16
        # nh=1, d_head=8 → nh*d_head=8
        assert o_seq is not None, "o_seq is None — memory not returning o_seq"
        assert o_seq.shape[-1] == 1 * 8, (
            f"o_seq last dim should be nh*d_head=8, got {o_seq.shape}"
        )

    def test_dec_feat_shape_dec3(self):
        """dec_feat for dec_feat_layer='dec3' must be (B, 4b, H/4, W/4)."""
        model = self._make_model()
        model.eval()
        x = torch.randn(1, 1, 64, 64)
        with torch.no_grad():
            _, ctx = model(x, return_reid_ctx=True)
        dec_feat = ctx['dec_feat']
        # base_ch=8 → dec3 channels = 4*8=32; H/4=16, W/4=16
        assert dec_feat.shape == (1, 32, 16, 16), (
            f"dec_feat shape: expected (1,32,16,16), got {dec_feat.shape}"
        )

    def test_reid_ctx_no_memory_when_use_memory_false(self):
        """When use_memory=False, o_seq and memory_state should be None."""
        model = UNetGDN2(in_ch=1, out_ch=1, base_ch=8, use_memory=False)
        model.eval()
        x = torch.randn(1, 1, 64, 64)
        with torch.no_grad():
            _, ctx = model(x, return_reid_ctx=True)
        assert ctx['o_seq'] is None, "o_seq should be None when use_memory=False"
        assert ctx['memory_state'] is None, (
            "memory_state should be None when use_memory=False"
        )


# ===========================================================================
# 5. reid_loss: scalar output, reid off → equals seg_loss
# ===========================================================================

class TestReIDLoss:

    def test_loss_is_scalar(self):
        """Combined loss must be a scalar tensor."""
        seg_loss = torch.tensor(0.5, requires_grad=True)
        B, K = 2, 4
        logits = torch.randn(B, K, K)
        labels = (torch.rand(B, K, K) > 0.5).float()
        loss = compute_reid_combined_loss(seg_loss, logits, labels)
        assert loss.shape == (), f"Loss must be scalar, got shape {loss.shape}"

    def test_reid_off_equals_seg_loss(self):
        """When reid_logits=None, total loss must equal seg_loss exactly."""
        seg_loss = torch.tensor(1.23)
        total = compute_reid_combined_loss(seg_loss, None, None)
        assert torch.allclose(total, seg_loss), (
            f"With reid off, total={total.item()} != seg_loss={seg_loss.item()}"
        )

    def test_reid_on_greater_than_seg_loss(self):
        """When reid_logits present and labels are non-trivial, loss > seg_loss."""
        seg_loss = torch.tensor(0.5)
        B, K = 2, 4
        # All positive labels → BCE on sigmoid(logits~0)≈0.5 → positive loss
        logits = torch.zeros(B, K, K)
        labels = torch.ones(B, K, K)
        total = compute_reid_combined_loss(seg_loss, logits, labels,
                                           lambda_reid=0.1, lambda_c=0.05)
        assert total.item() > seg_loss.item(), (
            f"Expected total > seg_loss; total={total.item()}, seg={seg_loss.item()}"
        )

    def test_reid_loss_class_forward(self):
        """ReIDLoss module wraps the same computation."""
        loss_fn = ReIDLoss(lambda_reid=0.1, lambda_c=0.05)
        seg_loss = torch.tensor(0.4)
        B, K = 2, 3
        logits = torch.randn(B, K, K)
        labels = (torch.rand(B, K, K) > 0.5).float()
        total = loss_fn(seg_loss, logits, labels)
        assert total.shape == ()

    def test_compute_match_loss_positive_label_lower(self):
        """
        For perfectly-matched positive pair (logit >> 0), BCE loss should be
        lower than for a negative pair (logit >> 0 but label=0).
        """
        # Positive pair: high logit + label=1 → low loss
        B, K = 1, 3
        # Construct logits: pair (0,1) gets high positive logit
        logits_pos = torch.full((B, K, K), -5.0)
        logits_pos[:, 0, 1] = 5.0
        logits_pos[:, 1, 0] = 5.0
        # Exclude diagonal
        diag = torch.eye(K, dtype=torch.bool)
        logits_pos[:, diag] = float('-inf')

        labels_pos = torch.zeros(B, K, K)
        labels_pos[:, 0, 1] = 1.0
        labels_pos[:, 1, 0] = 1.0

        loss_pos = compute_match_loss(logits_pos, labels_pos)

        # Negative pair: same high logit but label=0 → high loss
        labels_neg = torch.zeros(B, K, K)
        loss_neg = compute_match_loss(logits_pos, labels_neg)

        assert loss_pos.item() < loss_neg.item(), (
            f"Positive-pair loss {loss_pos.item():.4f} should be < "
            f"negative-pair loss {loss_neg.item():.4f}"
        )

    def test_backward_through_combined_loss(self):
        """Combined loss must be differentiable w.r.t. seg_loss & head params."""
        head = _make_head(d_head=16, n_heads=1, dec_ch=32, d_id=16)
        o_seq, dec_feat, pos = _make_inputs()
        B, K = o_seq.shape[0], pos.shape[1]

        logits = head(o_seq, dec_feat, pos)
        labels = (torch.rand(B, K, K) > 0.5).float()

        seg_loss = torch.tensor(0.3, requires_grad=True)
        total = compute_reid_combined_loss(seg_loss, logits, labels)
        total.backward()

        assert seg_loss.grad is not None, "seg_loss has no gradient"
        for name, p in head.named_parameters():
            assert p.grad is not None, f"head param '{name}' has no gradient"


# ===========================================================================
# 6. Detach presence: source code inspection
#    Verify that .detach() calls appear before first use of o_seq/dec_feat
#    inside ReIDReadoutHead.forward.
# ===========================================================================

class TestDetachPresenceInSource:

    def _get_forward_source(self) -> str:
        return inspect.getsource(ReIDReadoutHead.forward)

    def test_detach1_present_in_source(self):
        """o_seq.detach() must appear in forward source (★detach1)."""
        src = self._get_forward_source()
        assert 'o_seq.detach()' in src or 'detach1' in src, (
            "★detach1 (o_seq.detach()) not found in ReIDReadoutHead.forward source"
        )

    def test_detach3_present_in_source(self):
        """dec_feat.detach() must appear in forward source (★detach3)."""
        src = self._get_forward_source()
        assert 'dec_feat.detach()' in src or 'detach3' in src, (
            "★detach3 (dec_feat.detach()) not found in ReIDReadoutHead.forward source"
        )

    def test_detach2_present_in_source(self):
        """memory_state detach must appear in forward source (★detach2)."""
        src = self._get_forward_source()
        assert 'detach2' in src or 'memory_state.detach()' in src or \
               's.detach()' in src, (
            "★detach2 (memory_state.detach()) not found in ReIDReadoutHead.forward source"
        )


# ===========================================================================
# 7. Ablation flags: init params preserved on the head object
# ===========================================================================

class TestAblationFlags:

    def test_feat_source_stored(self):
        head = _make_head()
        assert head.feat_source == 'memory'

    def test_cnn_feat_source_valid(self):
        head = ReIDReadoutHead(d_head=8, n_heads=1, dec_ch=16, d_id=8,
                               feat_source='cnn')
        assert head.feat_source == 'cnn'

    def test_invalid_feat_source_raises(self):
        with pytest.raises(AssertionError):
            ReIDReadoutHead(d_head=8, n_heads=1, dec_ch=16, d_id=8,
                            feat_source='invalid')

    def test_detach_memory_train_default_true(self):
        head = _make_head()
        assert head.detach_memory_train is True

    def test_breakpoint_source_stored(self):
        head = ReIDReadoutHead(d_head=8, n_heads=1, dec_ch=16, d_id=8,
                               breakpoint_source='pred_skeleton')
        assert head.breakpoint_source == 'pred_skeleton'

    def test_invalid_breakpoint_source_raises(self):
        with pytest.raises(AssertionError):
            ReIDReadoutHead(d_head=8, n_heads=1, dec_ch=16, d_id=8,
                            breakpoint_source='bad_source')

    def test_log_temp_is_parameter(self):
        """log_temp must be nn.Parameter (learnable temperature scaling)."""
        head = _make_head()
        assert isinstance(head.log_temp, nn.Parameter), (
            "log_temp must be nn.Parameter"
        )
        assert head.log_temp.shape == (1,)


# ===========================================================================
# 8. GDN2MemoryModule return_memory=True (待 HPC 真验 with real FLA)
#    Basic smoke: with mock FLA, verify shape contracts hold.
# ===========================================================================

class TestMemoryModuleReturnMemory:

    def test_return_memory_false_returns_tensor(self):
        """Default return_memory=False: output is a single (B,C,H,W) tensor."""
        from models.unet_gdn2 import GDN2MemoryModule
        mem = GDN2MemoryModule(d_model=8, d_head=8, n_heads=1,
                               backend='naive', use_frangi=False)
        mem.eval()
        x = torch.randn(1, 8, 4, 4)
        with torch.no_grad():
            out = mem(x)
        assert isinstance(out, torch.Tensor)
        assert out.shape == x.shape

    def test_return_memory_true_returns_tuple(self):
        """return_memory=True: output is (Tensor, List)."""
        from models.unet_gdn2 import GDN2MemoryModule
        mem = GDN2MemoryModule(d_model=8, d_head=8, n_heads=1,
                               backend='naive', use_frangi=False)
        mem.eval()
        x = torch.randn(1, 8, 4, 4)
        with torch.no_grad():
            out = mem(x, return_memory=True)
        assert isinstance(out, tuple) and len(out) == 2, (
            f"Expected 2-tuple, got {type(out)}"
        )
        feat, states = out
        assert isinstance(feat, torch.Tensor)
        assert feat.shape == x.shape
        assert isinstance(states, list)

    def test_return_memory_states_length_equals_directions(self):
        """states_list length must equal number of scan directions."""
        from models.unet_gdn2 import GDN2MemoryModule
        for dirs in [1, 2, 4]:
            mem = GDN2MemoryModule(d_model=8, d_head=8, n_heads=1,
                                   backend='naive', directions=dirs,
                                   use_frangi=False)
            mem.eval()
            x = torch.randn(1, 8, 4, 4)
            with torch.no_grad():
                _, states = mem(x, return_memory=True)
            assert len(states) == dirs, (
                f"dirs={dirs}: expected {dirs} states, got {len(states)}"
            )

    def test_last_o_seq_exposed(self):
        """After forward, _last_o_seq must be set on the module."""
        from models.unet_gdn2 import GDN2MemoryModule
        mem = GDN2MemoryModule(d_model=8, d_head=8, n_heads=1,
                               backend='naive', use_frangi=False)
        mem.eval()
        x = torch.randn(1, 8, 4, 4)
        with torch.no_grad():
            mem(x)
        assert hasattr(mem, '_last_o_seq'), "_last_o_seq not set after forward"
        # (B=1, T=4*4=16, nh*dh=1*8=8)
        assert mem._last_o_seq.shape == (1, 16, 8), (
            f"_last_o_seq shape: {mem._last_o_seq.shape}"
        )

    # NOTE: Full integration test with real FLA (output_final_state=True kernel call)
    #   must run on HPC with fla installed.  Marked xfail locally.
    @pytest.mark.xfail(reason="Requires real FLA kernel with output_final_state "
                               "support — run on HPC only")
    def test_final_state_shape_with_real_fla(self):
        """
        HPC-only: final_state from real naive_chunk_gated_delta_rule must be
        (B, nh, d_head, d_head) per direction.
        # TODO: confirm shape from FLA source
        #   fla.ops.gated_delta_rule.naive.naive_chunk_gated_delta_rule
        #   with output_final_state=True.
        """
        import fla  # noqa: F401 — will fail locally, xfail catches it
        from models.unet_gdn2 import GDN2MemoryModule
        B, d_model, d_head, n_heads = 1, 8, 8, 1
        mem = GDN2MemoryModule(d_model=d_model, d_head=d_head, n_heads=n_heads,
                               backend='naive', use_frangi=False)
        x = torch.randn(B, d_model, 4, 4)
        _, states = mem(x, return_memory=True)
        assert states[0] is not None, "Real FLA should return non-None final state"
        assert states[0].shape == (B, n_heads, d_head, d_head)
