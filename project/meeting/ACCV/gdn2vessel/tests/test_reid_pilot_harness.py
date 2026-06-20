"""
test_reid_pilot_harness.py — Smoke tests for train_reid_pilot.py harness.

Test suite:
  1. Import: harness importable without FLA / GPU.
  2. Partial-corr utility: correctness on synthetic data (known r).
  3. 2-step forward + backward pass (naive FLA mock, synthetic tensors).
  4. Gradient isolation assertion: reid loss does NOT update memory params.
  5. Ablation flag switching: A2(memory) vs A0'(cnn) correctly toggles use_memory.
  6. State.json schema: write_state produces valid JSON with expected keys.
  7. _sample_breakpoint_positions: output shape + label symmetry.
  8. build_model: detach assertion + reid_head presence on both arms.
  9. Multi-NPZ benchmark aggregation: load_benchmark_npz_list + evaluate_on_benchmark
     multi-file path (mock NPZ + mock model, verifies n/csv-row count).

All tests run on CPU; FLA is mocked (same pattern as existing test_gdn2_p2.py).
No real data needed; all tensors are synthetic.
"""

from __future__ import annotations

import json
import sys
import types
import tempfile
from pathlib import Path

import numpy as np
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
#  Imports from src
# --------------------------------------------------------------------------- #

from train_reid_pilot import (   # noqa: E402
    partial_corr_numpy,
    _pearson_r,
    _residuals_after_ols,
    write_state,
    build_model,
    seg_loss,
    _sample_breakpoint_positions,
    load_benchmark_npz_list,
    evaluate_on_benchmark,
)
from models.reid_loss import compute_match_loss, compute_reid_combined_loss
from models.unet_gdn2 import ReIDReadoutHead, UNetGDN2


# --------------------------------------------------------------------------- #
#  Fixtures
# --------------------------------------------------------------------------- #

def _tiny_args(
    reid_feat_source: str = 'memory',
    no_detach_memory: bool = False,
    reid_breakpoint_source: str = 'gt_skeleton',
):
    """Minimal argparse.Namespace substitute for build_model."""
    class A:
        pass
    a = A()
    a.reid_feat_source         = reid_feat_source
    a.no_detach_memory         = no_detach_memory
    a.reid_breakpoint_source   = reid_breakpoint_source
    a.base_ch   = 8
    a.d_head    = 8
    a.n_heads   = 1
    a.reid_d_id = 8
    a.backend   = 'naive'
    return a


def _make_batch(B: int = 2, H: int = 64, W: int = 64):
    """Synthetic batch mimicking DRIVEDataset output."""
    return {
        'image': torch.randn(B, 1, H, W),
        'gt':    (torch.rand(B, 1, H, W) > 0.7).float(),
        'fov':   torch.ones(B, 1, H, W),
    }


# ===========================================================================
# 1. Import smoke
# ===========================================================================

class TestImport:

    def test_train_reid_pilot_importable(self):
        """Module must import without FLA / GPU."""
        import train_reid_pilot  # noqa: F401

    def test_partial_corr_importable(self):
        assert callable(partial_corr_numpy)

    def test_write_state_importable(self):
        assert callable(write_state)

    def test_build_model_importable(self):
        assert callable(build_model)


# ===========================================================================
# 2. Partial-correlation utility
# ===========================================================================

class TestPartialCorrNumpy:

    def test_perfect_corr_after_control(self):
        """
        X = random binary (memory indicator).
        Y = X * 2 + noise (strong X→Y relationship).
        Z = unrelated noise.
        Partial corr(X, Y | Z) should be strongly positive.
        """
        rng = np.random.RandomState(0)
        n = 200
        X = (rng.rand(n) > 0.5).astype(float)
        Z = rng.randn(n)
        Y = X * 2.0 + 0.1 * rng.randn(n)   # Y determined by X, not Z
        res = partial_corr_numpy(X, Y, Z, n_resample=200, rng_seed=0)
        assert res['r'] > 0.8, f"Expected high r; got r={res['r']:.4f}"
        assert res['ci_lower'] > 0, f"CI lower should be > 0; got {res['ci_lower']:.4f}"
        assert res['PASS'] is True

    def test_no_corr_after_control(self):
        """
        X = random binary, Y = Z * 2 + noise (Y caused by Z, not X).
        partial_corr(X, Y | Z) should be near zero.
        """
        rng = np.random.RandomState(1)
        n = 200
        Z = rng.randn(n)
        X = (rng.rand(n) > 0.5).astype(float)
        Y = Z * 2.0 + 0.1 * rng.randn(n)   # Y caused by Z, not X
        res = partial_corr_numpy(X, Y, Z, n_resample=200, rng_seed=1)
        assert abs(res['r']) < 0.3, f"Expected near-zero r; got r={res['r']:.4f}"

    def test_output_keys(self):
        X = np.array([1.0, 0.0, 1.0, 0.0])
        Y = np.array([0.9, 0.1, 0.8, 0.2])
        Z = np.array([0.5, 0.4, 0.6, 0.3])
        res = partial_corr_numpy(X, Y, Z, n_resample=50, rng_seed=42)
        for key in ('r', 'ci_lower', 'ci_upper', 'n', 'PASS'):
            assert key in res, f"Missing key '{key}' in partial_corr result"

    def test_ci_ordering(self):
        """ci_lower ≤ r ≤ ci_upper."""
        rng = np.random.RandomState(2)
        n = 50
        X = rng.randn(n)
        Y = X + rng.randn(n) * 0.5
        Z = rng.randn(n)
        res = partial_corr_numpy(X, Y, Z, n_resample=200, rng_seed=2)
        assert res['ci_lower'] <= res['r'] + 1e-6
        assert res['r'] - 1e-6 <= res['ci_upper']

    def test_pearson_r_known_value(self):
        """_pearson_r on perfectly correlated arrays should return 1.0."""
        a = np.array([1.0, 2.0, 3.0, 4.0])
        r = _pearson_r(a, a)
        assert abs(r - 1.0) < 1e-6, f"Expected r=1.0, got {r}"

    def test_residuals_after_ols_shape(self):
        """_residuals_after_ols must return same-length array."""
        X = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
        Z = np.array([0.1, 0.2, 0.3, 0.4, 0.5])
        res = _residuals_after_ols(X, Z)
        assert res.shape == X.shape


# ===========================================================================
# 3. 2-step forward + backward (synthetic tensors, no real data)
# ===========================================================================

class TestForwardBackward:

    def _run_forward(self, reid_feat_source: str = 'memory'):
        args = _tiny_args(reid_feat_source=reid_feat_source)
        model = build_model(args)
        model.train()
        batch = _make_batch(B=2, H=64, W=64)
        img = batch['image']
        gt  = batch['gt']
        fov = batch['fov']

        logits, reid_ctx = model(img, return_reid_ctx=True)
        return model, logits, reid_ctx, gt, fov

    def test_forward_memory_arm(self):
        """A2 arm: forward completes, logits shape correct."""
        _, logits, reid_ctx, _, _ = self._run_forward('memory')
        assert logits.shape == (2, 1, 64, 64), f"Got {logits.shape}"
        assert reid_ctx['o_seq'] is not None, "o_seq should not be None for memory arm"

    def test_forward_cnn_arm(self):
        """A0' arm: forward completes, o_seq is None (no GDN-2)."""
        _, logits, reid_ctx, _, _ = self._run_forward('cnn')
        assert logits.shape == (2, 1, 64, 64)
        assert reid_ctx['o_seq'] is None, "o_seq should be None for CNN arm"

    def test_backward_seg_loss(self):
        """Seg loss backward must succeed without RuntimeError."""
        args = _tiny_args()
        model = build_model(args)
        model.train()
        optimizer = torch.optim.Adam(model.parameters(), lr=1e-3)
        batch = _make_batch()
        optimizer.zero_grad()
        logits, _ = model(batch['image'], return_reid_ctx=True)
        l = seg_loss(logits, batch['gt'], batch['fov'])
        l.backward()
        optimizer.step()
        assert l.item() >= 0

    def test_backward_combined_reid_loss(self):
        """
        Combined seg + reid loss backward must succeed.
        Uses synthetic same-root labels (not from real dataset).
        """
        args = _tiny_args()
        model = build_model(args)
        model.train()
        optimizer = torch.optim.Adam(model.parameters(), lr=1e-3)
        batch = _make_batch(B=2, H=64, W=64)

        optimizer.zero_grad()
        logits, reid_ctx = model(batch['image'], return_reid_ctx=True)
        l_seg = seg_loss(logits, batch['gt'], batch['fov'])

        # Synthetic re-ID inputs
        K = 4
        B = 2
        dec_feat = reid_ctx['dec_feat']       # (B, dec_ch, H_dec, W_dec)
        H_dec, W_dec = dec_feat.shape[-2], dec_feat.shape[-1]
        positions = torch.rand(B, K, 2)
        positions[..., 0] *= (H_dec - 1)
        positions[..., 1] *= (W_dec - 1)

        o_seq = reid_ctx['o_seq']             # (B, T, nh*dh)
        reid_logits = model.reid_head(
            o_seq=o_seq,
            dec_feat=dec_feat,
            breakpoint_positions=positions,
        )
        labels = torch.zeros(B, K, K)
        labels[:, 0, 1] = 1.0
        labels[:, 1, 0] = 1.0

        total = compute_reid_combined_loss(l_seg, reid_logits, labels,
                                           lambda_reid=0.1, lambda_c=0.05)
        total.backward()
        optimizer.step()
        assert total.item() >= 0


# ===========================================================================
# 4. Gradient isolation: reid loss must NOT update memory parameters
# ===========================================================================

class TestGradientIsolationHarness:
    """
    Critical red-line test (ACCEPTANCE P4, 致命-1 guard):
    When detach_memory_train=True (default), the re-ID loss backward must NOT
    produce gradients in GDN2MemoryModule parameters.
    """

    def _run_reid_backward(self, detach: bool = True):
        args = _tiny_args(
            reid_feat_source='memory',
            no_detach_memory=not detach,
        )
        model = build_model(args)
        model.train()

        # Zero all gradients
        for p in model.parameters():
            p.grad = None

        batch = _make_batch(B=2, H=64, W=64)
        logits, reid_ctx = model(batch['image'], return_reid_ctx=True)
        l_seg = seg_loss(logits, batch['gt'], batch['fov'])

        dec_feat = reid_ctx['dec_feat']
        H_dec, W_dec = dec_feat.shape[-2], dec_feat.shape[-1]
        B, K = 2, 4
        positions = torch.zeros(B, K, 2)
        positions[..., 0] = H_dec / 2
        positions[..., 1] = W_dec / 2

        reid_logits = model.reid_head(
            o_seq=reid_ctx['o_seq'],
            dec_feat=reid_ctx['dec_feat'],
            breakpoint_positions=positions,
        )
        labels = torch.zeros(B, K, K)
        labels[:, 0, 1] = 1.0
        labels[:, 1, 0] = 1.0

        # Backward on ONLY the reid loss, not seg_loss
        # This isolates whether reid loss alone can reach memory params.
        l_reid = compute_match_loss(reid_logits, labels)
        l_reid.backward()

        return model

    def test_memory_params_no_grad_when_detach_on(self):
        """
        ★ Critical: detach_memory_train=True → reid loss backward must produce
        zero/None gradient in ALL GDN2MemoryModule parameters.
        """
        model = self._run_reid_backward(detach=True)
        if model.memory is None:
            pytest.skip("No memory module in this arm")
        for name, param in model.memory.named_parameters():
            assert param.grad is None or param.grad.abs().max().item() == 0.0, (
                f"Memory param '{name}' has nonzero gradient after reid loss backward "
                f"(detach=True) — detach barriers not working! "
                f"grad_norm={param.grad.norm().item():.6f if param.grad is not None else 'None'}"
            )

    def test_reid_head_params_get_grad_when_detach_on(self):
        """
        Head's own parameters (mem_proj/loc_proj/fuse/log_temp) MUST receive
        gradients — the loss DOES update the head, just not the memory.
        """
        model = self._run_reid_backward(detach=True)
        for name, param in model.reid_head.named_parameters():
            assert param.grad is not None, (
                f"reid_head param '{name}' has no gradient — loss not reaching head"
            )
            assert param.grad.abs().sum().item() > 0, (
                f"reid_head param '{name}' gradient is all-zero"
            )

    def test_memory_params_DO_get_grad_when_a3_ablation(self):
        """
        A3 ablation (detach=False): memory params SHOULD get gradient.
        This verifies that the detach IS load-bearing (demonstrates the
        guard is not trivially disabled).
        """
        model = self._run_reid_backward(detach=False)
        if model.memory is None:
            pytest.skip("No memory module in CNN arm")
        any_grad = False
        for name, param in model.memory.named_parameters():
            if param.grad is not None and param.grad.abs().sum().item() > 0:
                any_grad = True
                break
        assert any_grad, (
            "A3 ablation (detach=False): expected at least one memory param "
            "to receive gradient, but none did — gradient not flowing through memory"
        )


# ===========================================================================
# 5. Ablation flag switching: A2 vs A0' correctly sets use_memory
# ===========================================================================

class TestAblationFlagSwitching:

    def test_a2_memory_arm_use_memory_true(self):
        """A2 (memory): model.memory should be non-None (GDN-2 active)."""
        args = _tiny_args(reid_feat_source='memory')
        model = build_model(args)
        assert model.memory is not None, "A2 arm: GDN-2 memory should be active"
        assert model.reid_head.feat_source == 'memory'

    def test_a0_cnn_arm_use_memory_false(self):
        """A0' (cnn): model.memory should be None (no GDN-2)."""
        args = _tiny_args(reid_feat_source='cnn')
        model = build_model(args)
        assert model.memory is None, "A0' arm: GDN-2 memory should be disabled"
        assert model.reid_head.feat_source == 'cnn'

    def test_a2_reid_ctx_o_seq_not_none(self):
        """A2 arm: return_reid_ctx gives non-None o_seq."""
        args = _tiny_args(reid_feat_source='memory')
        model = build_model(args)
        model.eval()
        x = torch.randn(1, 1, 64, 64)
        with torch.no_grad():
            _, ctx = model(x, return_reid_ctx=True)
        assert ctx['o_seq'] is not None

    def test_a0_reid_ctx_o_seq_is_none(self):
        """A0' arm: return_reid_ctx gives None o_seq (no memory to read)."""
        args = _tiny_args(reid_feat_source='cnn')
        model = build_model(args)
        model.eval()
        x = torch.randn(1, 1, 64, 64)
        with torch.no_grad():
            _, ctx = model(x, return_reid_ctx=True)
        assert ctx['o_seq'] is None

    def test_a3_detach_flag_stored(self):
        """A3 ablation flag correctly stored on reid_head."""
        args_on  = _tiny_args(no_detach_memory=False)  # detach=True (default)
        args_off = _tiny_args(no_detach_memory=True)   # detach=False (A3 ablation)
        model_on  = build_model(args_on)
        model_off = build_model(args_off)
        assert model_on.reid_head.detach_memory_train  is True
        assert model_off.reid_head.detach_memory_train is False

    def test_a4_bp_source_stored(self):
        """A4 breakpoint source correctly stored on reid_head."""
        args = _tiny_args(reid_breakpoint_source='pred_skeleton')
        model = build_model(args)
        assert model.reid_head.breakpoint_source == 'pred_skeleton'

    def test_both_arms_have_reid_head(self):
        """Both A2 and A0' must have use_reid_head=True (same head, different feature)."""
        for src in ('memory', 'cnn'):
            args = _tiny_args(reid_feat_source=src)
            model = build_model(args)
            assert model.reid_head is not None, (
                f"Arm {src}: reid_head must be present"
            )
            assert model.use_reid_head is True


# ===========================================================================
# 6. write_state: produces valid JSON with expected keys
# ===========================================================================

class TestWriteState:

    def test_write_state_basic(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / 'state.json'
            write_state(path, epoch=5, train_loss=0.42, val_dice=0.81,
                        best_dice=0.83, status='running',
                        reid_feat_source='memory')
            assert path.exists()
            with open(path, 'r') as f:
                s = json.load(f)
            for key in ('epoch', 'train_loss', 'val_dice', 'best_dice', 'status',
                        'reid_feat_source'):
                assert key in s, f"Missing key '{key}' in state.json"
            assert s['epoch'] == 5
            assert s['status'] == 'running'
            assert s['reid_feat_source'] == 'memory'

    def test_write_state_with_benchmark_metrics(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / 'state.json'
            bench = {
                'reid_rate':     0.72,
                'epsilon_beta0': 0.15,
                'success_rate':  0.88,
                'n_gaps':        98,
            }
            write_state(path, epoch=10, train_loss=0.3, val_dice=0.85,
                        best_dice=0.85, status='running',
                        benchmark_metrics=bench,
                        reid_feat_source='cnn')
            with open(path, 'r') as f:
                s = json.load(f)
            assert 'reid_rate' in s
            assert 'epsilon_beta0' in s
            assert abs(s['reid_rate'] - 0.72) < 1e-4
            assert s['n_gaps'] == 98

    def test_write_state_with_partial_corr(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / 'state.json'
            pc = {'r': 0.35, 'ci_lower': 0.12, 'ci_upper': 0.55, 'n': 40,
                  'PASS': True}
            write_state(path, epoch=50, train_loss=0.2, val_dice=0.88,
                        best_dice=0.88, status='done',
                        partial_corr_result=pc,
                        reid_feat_source='memory')
            with open(path, 'r') as f:
                s = json.load(f)
            assert 'partial_corr' in s
            assert s['partial_corr']['PASS'] is True

    def test_state_json_atomic_write(self):
        """No .tmp file should be left after write_state."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / 'state.json'
            write_state(path, 1, 0.5, 0.7, 0.7, 'running')
            tmp_path = path.with_suffix('.tmp')
            assert not tmp_path.exists(), ".tmp file not cleaned up (atomic rename failed)"


# ===========================================================================
# 7. _sample_breakpoint_positions: shape + label symmetry
# ===========================================================================

class TestSampleBreakpointPositions:
    """
    Tests _sample_breakpoint_positions with a synthetic GT batch.
    Uses real apply_breaks under the hood, so requires scipy.ndimage + skimage.
    """

    @pytest.mark.filterwarnings('ignore')
    def test_positions_shape(self):
        """Positions must be (B, n_bps, 2)."""
        B, H, W, n_bps = 2, 64, 64, 6
        gt_batch = (torch.rand(B, 1, H, W) > 0.5).float()
        device = torch.device('cpu')
        positions, labels = _sample_breakpoint_positions(gt_batch, n_bps, device)
        assert positions.shape == (B, n_bps, 2), (
            f"Expected ({B},{n_bps},2), got {positions.shape}"
        )

    @pytest.mark.filterwarnings('ignore')
    def test_labels_shape(self):
        """Labels must be (B, n_bps, n_bps)."""
        B, H, W, n_bps = 2, 64, 64, 6
        gt_batch = (torch.rand(B, 1, H, W) > 0.5).float()
        device = torch.device('cpu')
        positions, labels = _sample_breakpoint_positions(gt_batch, n_bps, device)
        assert labels.shape == (B, n_bps, n_bps), (
            f"Expected ({B},{n_bps},{n_bps}), got {labels.shape}"
        )

    @pytest.mark.filterwarnings('ignore')
    def test_labels_symmetric(self):
        """Same-root labels must be symmetric: label[i,j] == label[j,i]."""
        B, H, W, n_bps = 2, 64, 64, 6
        gt_batch = (torch.rand(B, 1, H, W) > 0.7).float()
        device = torch.device('cpu')
        _, labels = _sample_breakpoint_positions(gt_batch, n_bps, device)
        for b in range(B):
            diff = (labels[b] - labels[b].t()).abs().max().item()
            assert diff < 1e-6, (
                f"Batch {b}: labels not symmetric, max |L-L^T|={diff}"
            )

    @pytest.mark.filterwarnings('ignore')
    def test_labels_diagonal_zero(self):
        """Self-matching entries (diagonal) must be 0.0."""
        B, H, W, n_bps = 1, 64, 64, 6
        gt_batch = (torch.rand(B, 1, H, W) > 0.5).float()
        device = torch.device('cpu')
        _, labels = _sample_breakpoint_positions(gt_batch, n_bps, device)
        for b in range(B):
            diag = torch.diagonal(labels[b])
            assert diag.abs().max().item() == 0.0, (
                f"Diagonal of same-root labels should be 0; got {diag}"
            )

    @pytest.mark.filterwarnings('ignore')
    def test_positions_in_valid_range(self):
        """Position values must be non-negative (coords in pixel space)."""
        B, H, W, n_bps = 2, 64, 64, 6
        gt_batch = (torch.rand(B, 1, H, W) > 0.5).float()
        device = torch.device('cpu')
        positions, _ = _sample_breakpoint_positions(gt_batch, n_bps, device)
        assert (positions >= 0).all(), "Some positions are negative"


# ===========================================================================
# 8. build_model assertions
# ===========================================================================

class TestBuildModel:

    def test_a2_assertions_pass(self):
        """build_model for A2 arm must not raise any assertion."""
        args = _tiny_args(reid_feat_source='memory')
        model = build_model(args)  # should not raise
        assert model is not None

    def test_a0_assertions_pass(self):
        """build_model for A0' arm must not raise any assertion."""
        args = _tiny_args(reid_feat_source='cnn')
        model = build_model(args)  # should not raise
        assert model is not None

    def test_reid_head_present_both_arms(self):
        for src in ('memory', 'cnn'):
            model = build_model(_tiny_args(reid_feat_source=src))
            assert isinstance(model.reid_head, ReIDReadoutHead), (
                f"reid_head should be ReIDReadoutHead for arm {src}"
            )

    def test_gdn2_memory_signature_no_gt(self):
        """
        R5 assertion: GDN2MemoryModule.forward must not accept a 'gt' parameter.
        build_model enforces this via inspect.signature check.
        """
        import inspect
        from models.unet_gdn2 import GDN2MemoryModule
        sig = inspect.signature(GDN2MemoryModule.forward)
        gt_like = {'gt', 'target', 'gt_mask', 'label', 'annotation'}
        bad = gt_like & set(sig.parameters.keys())
        assert not bad, (
            f"R5 VIOLATED: GDN2MemoryModule.forward has GT-like params: {bad}"
        )

    def test_frangi_signature_no_gt(self):
        """Frangi forward must not accept GT (R5 input-derived check)."""
        import inspect
        from models.unet_gdn2 import DifferentiableFrangi
        sig = inspect.signature(DifferentiableFrangi.forward)
        gt_like = {'gt', 'target', 'gt_mask', 'label'}
        bad = gt_like & set(sig.parameters.keys())
        assert not bad, (
            f"R5 VIOLATED: DifferentiableFrangi.forward has GT-like params: {bad}"
        )


# ===========================================================================
# 9. Multi-NPZ benchmark aggregation (mock NPZ + mock model)
# ===========================================================================

def _make_mock_npz(tmpdir: Path, image_id: str, severity: str = 'Medium',
                   H: int = 32, W: int = 32, n_gaps: int = 3) -> str:
    """
    Write a minimal benchmark NPZ (same schema as precompute_benchmark.py).
    vessel_segment_map has small labelled regions to give non-trivial metrics.
    """
    import json as _json

    rng = np.random.RandomState(hash(image_id) % (2**31))

    # Build a simple vessel_segment_map (2 segments) and broken mask
    vsm = np.zeros((H, W), dtype=np.int32)
    vsm[2:10, 2:15] = 1   # segment 1
    vsm[15:25, 5:20] = 2  # segment 2
    mask_broken = (vsm > 0).astype(np.uint8)
    # Punch a small gap
    mask_broken[5:7, 8:11] = 0

    # Minimal gap records — one gap per 'n_gaps' (simplified)
    gaps = []
    for i in range(n_gaps):
        gaps.append({
            'gap_id':           i,
            'center_yx':        [5, 8 + i],
            'radius':           2,
            'gap_size':         2,
            'sigma':            1.0,
            'segment_id_left':  1,
            'segment_id_right': 1,
        })
    gap_bytes = _json.dumps(gaps).encode('utf-8')

    npz_name = f'mock_{severity}_id{image_id}_seed42.npz'
    npz_path = tmpdir / npz_name
    np.savez_compressed(
        str(npz_path),
        mask_broken        = mask_broken,
        vessel_segment_map = vsm,
        gap_records_json   = np.frombuffer(gap_bytes, dtype=np.uint8),
        image_id           = np.array([image_id]),
        dataset            = np.array(['mock']),
        severity           = np.array([severity]),
        seed_used          = np.array([42]),
        original_shape     = np.array([H, W]),
    )
    return str(npz_path)


def _make_mock_manifest(tmpdir: Path, npz_paths: list[str],
                        dataset: str = 'mock', severity: str = 'Medium') -> Path:
    import json as _json
    entries = []
    for i, p in enumerate(npz_paths):
        entries.append({
            'dataset':  dataset,
            'severity': severity,
            'image_id': str(i),
            'npz':      p,
            'n_gaps':   3,
            'status':   'computed',
        })
    manifest_path = tmpdir / 'manifest.json'
    with open(manifest_path, 'w') as f:
        _json.dump(entries, f)
    return manifest_path


class _TrivialModel(nn.Module):
    """Minimal nn.Module that returns an all-zeros (1,1,H,W) logit for any input."""
    def __init__(self):
        super().__init__()
        self.dummy = nn.Parameter(torch.zeros(1))  # gives it parameters

    def forward(self, x, return_reid_ctx=False):
        logits = torch.zeros_like(x[:, :1, :, :])
        if return_reid_ctx:
            return logits, {'o_seq': None, 'dec_feat': logits, 'memory_state': None}
        return logits


class TestMultiNpzBenchmarkAggregation:
    """
    Tests for load_benchmark_npz_list and evaluate_on_benchmark multi-file path.
    Uses mock NPZs (no real vessel data), patches _eval_single_npz so no
    real benchmark.metrics import needed.
    """

    # ------------------------------------------------------------------ #
    #  load_benchmark_npz_list
    # ------------------------------------------------------------------ #

    def test_single_file_mode_returns_list_of_one(self, tmp_path):
        """--benchmark_npz single file → list of exactly one path."""
        dummy = tmp_path / 'dummy.npz'
        dummy.write_bytes(b'')
        result = load_benchmark_npz_list(
            benchmark_npz=str(dummy),
            benchmark_dir=None,
            dataset=None,
            severity=None,
        )
        assert result == [str(dummy)], f"Expected single-element list, got {result}"

    def test_dir_mode_missing_manifest_returns_empty(self, tmp_path):
        """benchmark_dir without manifest.json → [] + warning (no raise)."""
        result = load_benchmark_npz_list(
            benchmark_npz=None,
            benchmark_dir=str(tmp_path),
            dataset='drive',
            severity='Medium',
        )
        assert result == []

    def test_dir_mode_filters_by_dataset_and_severity(self, tmp_path):
        """manifest with mixed entries → only matching (dataset,severity) returned."""
        npz1 = _make_mock_npz(tmp_path, 'img1', severity='Medium')
        npz2 = _make_mock_npz(tmp_path, 'img2', severity='Hard')   # different severity
        import json as _json
        manifest = [
            {'dataset': 'mock', 'severity': 'Medium', 'image_id': 'img1', 'npz': npz1, 'n_gaps': 3},
            {'dataset': 'mock', 'severity': 'Hard',   'image_id': 'img2', 'npz': npz2, 'n_gaps': 3},
        ]
        (tmp_path / 'manifest.json').write_text(_json.dumps(manifest))

        result = load_benchmark_npz_list(
            benchmark_npz=None,
            benchmark_dir=str(tmp_path),
            dataset='mock',
            severity='Medium',
        )
        assert result == [npz1], f"Expected only Medium NPZ, got {result}"

    def test_dir_mode_no_filter_returns_all(self, tmp_path):
        """No dataset/severity filter → all manifest entries returned."""
        npz1 = _make_mock_npz(tmp_path, 'img1', severity='Medium')
        npz2 = _make_mock_npz(tmp_path, 'img2', severity='Hard')
        import json as _json
        manifest = [
            {'dataset': 'mock', 'severity': 'Medium', 'image_id': 'img1', 'npz': npz1, 'n_gaps': 3},
            {'dataset': 'mock', 'severity': 'Hard',   'image_id': 'img2', 'npz': npz2, 'n_gaps': 3},
        ]
        (tmp_path / 'manifest.json').write_text(_json.dumps(manifest))

        result = load_benchmark_npz_list(
            benchmark_npz=None,
            benchmark_dir=str(tmp_path),
            dataset=None,
            severity=None,
        )
        assert set(result) == {npz1, npz2}

    def test_none_both_inputs_returns_empty(self):
        """Neither benchmark_npz nor benchmark_dir → []."""
        result = load_benchmark_npz_list(
            benchmark_npz=None, benchmark_dir=None, dataset=None, severity=None)
        assert result == []

    # ------------------------------------------------------------------ #
    #  evaluate_on_benchmark (mock _eval_single_npz via monkeypatch)
    # ------------------------------------------------------------------ #

    def test_aggregate_n_equals_n_npz(self, tmp_path, monkeypatch):
        """
        evaluate_on_benchmark with 3 mock NPZs → n_images=3, aggregated means correct.
        Monkeypatches _eval_single_npz to return controllable per-image dicts.
        """
        import train_reid_pilot as _hrn

        call_log = []
        def _fake_eval(model, device, npz_path, reid_feat_source):
            idx = call_log.__len__()
            call_log.append(npz_path)
            return {
                'image_id':      f'img{idx}',
                'dataset':       'mock',
                'severity':      'Medium',
                'reid_rate':     0.1 * (idx + 1),   # 0.1, 0.2, 0.3
                'epsilon_beta0': 0.05,
                'success_rate':  0.8,
                'n_gaps':        5,
            }
        monkeypatch.setattr(_hrn, '_eval_single_npz', _fake_eval)

        npz_paths = [str(tmp_path / f'fake{i}.npz') for i in range(3)]
        model  = _TrivialModel()
        device = torch.device('cpu')

        result = evaluate_on_benchmark(
            model=model, device=device,
            npz_paths=npz_paths, reid_feat_source='memory',
            csv_path=None, epoch=1, arm='memory',
        )

        assert result['n_images'] == 3, f"Expected n_images=3, got {result['n_images']}"
        assert abs(result['reid_rate'] - 0.2) < 1e-5, (
            f"Expected mean reid_rate=0.2, got {result['reid_rate']}")
        assert result['n_gaps'] == 15, f"Expected n_gaps=15, got {result['n_gaps']}"

    def test_csv_rows_written_per_image(self, tmp_path, monkeypatch):
        """
        evaluate_on_benchmark must write exactly n_images rows to csv_path,
        one per image (not one aggregate row).
        """
        import train_reid_pilot as _hrn

        def _fake_eval(model, device, npz_path, reid_feat_source):
            return {
                'image_id':      Path(npz_path).stem,
                'dataset':       'mock',
                'severity':      'Medium',
                'reid_rate':     0.5,
                'epsilon_beta0': 0.1,
                'success_rate':  0.9,
                'n_gaps':        4,
            }
        monkeypatch.setattr(_hrn, '_eval_single_npz', _fake_eval)

        npz_paths = [str(tmp_path / f'fake{i}.npz') for i in range(3)]
        csv_path  = tmp_path / 'reid_results.csv'

        # Write header first (matches production flow)
        with open(csv_path, 'w', newline='', encoding='utf-8') as cf:
            import csv as _csv
            w = _csv.writer(cf)
            w.writerow(['epoch', 'image_id', 'severity', 'dataset',
                        'reid_rate', 'epsilon_beta0', 'success_rate', 'n_gaps', 'arm'])

        model  = _TrivialModel()
        device = torch.device('cpu')
        evaluate_on_benchmark(
            model=model, device=device,
            npz_paths=npz_paths, reid_feat_source='cnn',
            csv_path=csv_path, epoch=5, arm='cnn',
        )

        # Count data rows (excluding header)
        with open(csv_path, 'r', newline='', encoding='utf-8') as cf:
            import csv as _csv
            rows = list(_csv.DictReader(cf))

        assert len(rows) == 3, (
            f"Expected 3 per-image rows in CSV, got {len(rows)}: {rows}")
        assert rows[0]['arm'] == 'cnn'
        assert rows[0]['severity'] == 'Medium'
        assert rows[0]['epoch'] == '5'

    def test_empty_npz_list_returns_zeros(self):
        """Empty npz_paths → zero aggregate (no crash)."""
        model  = _TrivialModel()
        device = torch.device('cpu')
        result = evaluate_on_benchmark(
            model=model, device=device,
            npz_paths=[], reid_feat_source='memory',
        )
        assert result['n_images'] == 0
        assert result['reid_rate'] == 0.0

    def test_partial_error_still_aggregates(self, tmp_path, monkeypatch):
        """
        If one NPZ raises an exception, the rest are still aggregated
        and n_images counts only successes.
        """
        import train_reid_pilot as _hrn

        call_count = {'n': 0}
        def _fake_eval_with_error(model, device, npz_path, reid_feat_source):
            i = call_count['n']
            call_count['n'] += 1
            if i == 1:
                raise RuntimeError('simulated NPZ corruption')
            return {
                'image_id':      f'img{i}',
                'dataset':       'mock',
                'severity':      'Medium',
                'reid_rate':     0.6,
                'epsilon_beta0': 0.1,
                'success_rate':  0.85,
                'n_gaps':        3,
            }
        monkeypatch.setattr(_hrn, '_eval_single_npz', _fake_eval_with_error)

        npz_paths = [str(tmp_path / f'fake{i}.npz') for i in range(3)]
        model  = _TrivialModel()
        device = torch.device('cpu')

        result = evaluate_on_benchmark(
            model=model, device=device,
            npz_paths=npz_paths, reid_feat_source='memory',
        )
        # 2 of 3 NPZs should succeed
        assert result['n_images'] == 2, (
            f"Expected n_images=2 (1 error skipped), got {result['n_images']}")
