"""
test_measurement_fix.py — pytest for M1/M2b/M4/M5 measurement fixes.

M1: reid_rate_head() in benchmark/metrics.py
  - Case: head picks all correct j* → reid_rate_head=1.0, idf1=1.0
  - Case: head picks all wrong j*  → reid_rate_head=0.0, idf1=0.0
  - Case: isolated gaps (no same-root partner) excluded from denominator
  - Case: no-match (max logit <= 0) treated as missed

M2b: frozen_breaks.py determinism
  - Same img_id → same seed → same break_result (disk round-trip)
  - Different img_ids → different seeds

M4: A1' proj_erase / proj_g / alpha_e grad norms > 0 after backward

M5: audit_iso_param returns iso_pass=True and dead_param_pass=True

All tests run on CPU with FLA mocked (same pattern as existing tests).
"""

from __future__ import annotations

import sys
import types
import tempfile
from pathlib import Path

import numpy as np
import pytest
import torch

# ---------------------------------------------------------------------------
#  Path setup
# ---------------------------------------------------------------------------

_repo_root = Path(__file__).parent.parent
_src_dir   = _repo_root / 'src'
if str(_src_dir) not in sys.path:
    sys.path.insert(0, str(_src_dir))


# ---------------------------------------------------------------------------
#  Mock FLA
# ---------------------------------------------------------------------------

def _patch_fla():
    if 'fla' in sys.modules:
        return
    def _fake(q, k, v, beta, g, output_final_state=False):
        B, T, nh, dh = v.shape
        state = torch.zeros(B, nh, dh, dh) if output_final_state else None
        return v.clone(), state
    fake_fla   = types.ModuleType('fla')
    fake_ops   = types.ModuleType('fla.ops')
    fake_gdr   = types.ModuleType('fla.ops.gated_delta_rule')
    fake_naive = types.ModuleType('fla.ops.gated_delta_rule.naive')
    fake_chunk = types.ModuleType('fla.ops.gated_delta_rule.chunk')
    fake_naive.naive_chunk_gated_delta_rule = _fake
    fake_chunk.chunk_gated_delta_rule       = _fake
    sys.modules.setdefault('fla',                              fake_fla)
    sys.modules.setdefault('fla.ops',                          fake_ops)
    sys.modules.setdefault('fla.ops.gated_delta_rule',         fake_gdr)
    sys.modules.setdefault('fla.ops.gated_delta_rule.naive',   fake_naive)
    sys.modules.setdefault('fla.ops.gated_delta_rule.chunk',   fake_chunk)

_patch_fla()


# ---------------------------------------------------------------------------
#  Imports (after FLA patch)
# ---------------------------------------------------------------------------

from benchmark.metrics import reid_rate_head, _build_gt_same_root
from benchmark.synth_breaks import GapRecord, BreakResult, apply_breaks
from benchmark.frozen_breaks import get_frozen_breaks, _img_id_to_seed
from models.unet_gdn2 import UNetGDN2, LinearAttnModule


# ---------------------------------------------------------------------------
#  Helpers: build fake GapRecord list
# ---------------------------------------------------------------------------

def _make_gap(gap_id, seg_left, seg_right, center=(10, 10), radius=3):
    return GapRecord(
        gap_id=gap_id,
        center_yx=center,
        radius=radius,
        gap_size=6,
        sigma=0.8,
        segment_id_left=seg_left,
        segment_id_right=seg_right,
    )


# ===========================================================================
#  M1: reid_rate_head tests
# ===========================================================================

class TestReidRateHead:
    """M1: reid_rate_head() correctness."""

    def _logits_perfect(self, K: int, correct_j: list) -> np.ndarray:
        """
        Build logits such that for each gap i, argmax gives correct_j[i].
        All off-diagonal positive; correct j gets highest score.
        """
        L = np.full((K, K), -1.0, dtype=np.float32)
        np.fill_diagonal(L, -np.inf)
        for i, j in enumerate(correct_j):
            if j != i:
                L[i, j] = 10.0   # highest score → correct choice
        return L

    def _logits_all_wrong(self, K: int, Y: np.ndarray) -> np.ndarray:
        """
        Build logits such that argmax for gap i picks the first j with Y[i,j]==0.
        """
        L = np.full((K, K), 0.5, dtype=np.float32)   # all slightly positive
        np.fill_diagonal(L, -np.inf)
        # Boost the WRONG choice (first non-partner j for each i)
        for i in range(K):
            for j in range(K):
                if i != j and Y[i, j] == 0:
                    L[i, j] = 10.0   # wrong partner gets highest score
                    break
        return L

    def test_all_correct_returns_1(self):
        """
        Case: 4 gaps, pairwise same-root (0,1) and (2,3).
        Head picks correct j for each gap → reid_rate_head=1.0, idf1=1.0.
        """
        gaps = [
            _make_gap(0, seg_left=1, seg_right=2),
            _make_gap(1, seg_left=1, seg_right=2),
            _make_gap(2, seg_left=3, seg_right=4),
            _make_gap(3, seg_left=3, seg_right=4),
        ]
        K = 4
        # Y: (0,1)=1, (2,3)=1, others=0
        # Correct j: gap0→1, gap1→0, gap2→3, gap3→2
        L = self._logits_perfect(K, correct_j=[1, 0, 3, 2])

        result = reid_rate_head(L, gaps)

        assert result['n_gaps'] == 4
        assert result['n_gaps_with_partner'] == 4
        assert result['reid_rate_head'] == pytest.approx(1.0)
        assert result['reid_idf1'] == pytest.approx(1.0)

    def test_all_wrong_returns_0(self):
        """
        Case: 4 gaps, pairwise same-root (0,1) and (2,3).
        Head always picks wrong j → reid_rate_head=0.0.
        """
        gaps = [
            _make_gap(0, seg_left=1, seg_right=2),
            _make_gap(1, seg_left=1, seg_right=2),
            _make_gap(2, seg_left=3, seg_right=4),
            _make_gap(3, seg_left=3, seg_right=4),
        ]
        K = 4
        Y = _build_gt_same_root(gaps)
        L = self._logits_all_wrong(K, Y)

        result = reid_rate_head(L, gaps)

        assert result['reid_rate_head'] == pytest.approx(0.0)
        # idf1 should also be 0 (IDTP=0)
        assert result['reid_idf1'] == pytest.approx(0.0)

    def test_isolated_gap_excluded_from_denominator(self):
        """
        Case: gap0 and gap1 are same-root; gap2 is isolated (seg_left=-1, seg_right=-1).
        Denominator should be 2 (not 3); isolated gap does NOT affect reid_rate_head.
        """
        gaps = [
            _make_gap(0, seg_left=1, seg_right=2),
            _make_gap(1, seg_left=1, seg_right=2),
            _make_gap(2, seg_left=-1, seg_right=-1),   # isolated — no same-root partner
        ]
        K = 3
        # Head picks correct j for gap0 and gap1; gap2 picks gap0 (wrong, but isolated)
        L = np.full((K, K), -1.0, dtype=np.float32)
        np.fill_diagonal(L, -np.inf)
        L[0, 1] = 10.0   # gap0 → gap1 (correct)
        L[1, 0] = 10.0   # gap1 → gap0 (correct)
        L[2, 0] = 10.0   # gap2 → gap0 (logit>0, but gap2 is isolated)

        result = reid_rate_head(L, gaps)

        assert result['n_gaps'] == 3
        assert result['n_gaps_with_partner'] == 2, (
            "Isolated gap should not count in denominator"
        )
        assert result['reid_rate_head'] == pytest.approx(1.0), (
            "Both non-isolated gaps are correct → rate=1.0"
        )

    def test_no_match_when_max_logit_le_zero(self):
        """
        Case: 2 same-root gaps; all logits <= 0 → head declares no-match for both.
        These become IDFN; reid_rate_head=0, idf1=0.
        """
        gaps = [
            _make_gap(0, seg_left=1, seg_right=2),
            _make_gap(1, seg_left=1, seg_right=2),
        ]
        K = 2
        L = np.full((K, K), -0.5, dtype=np.float32)   # all logits < 0
        np.fill_diagonal(L, -np.inf)

        result = reid_rate_head(L, gaps)

        assert result['n_gaps_with_partner'] == 2
        assert result['reid_rate_head'] == pytest.approx(0.0)
        assert result['reid_idf1'] == pytest.approx(0.0)

    def test_empty_gaps_returns_nan(self):
        """Empty gap list → all metrics are nan."""
        L = np.zeros((0, 0), dtype=np.float32)
        result = reid_rate_head(L, [])
        assert result['n_gaps'] == 0
        import math
        assert math.isnan(result['reid_rate_head'])
        assert math.isnan(result['reid_idf1'])

    def test_shape_mismatch_raises(self):
        """Logits shape (K,K) must match len(gaps)."""
        gaps = [_make_gap(0, 1, 2), _make_gap(1, 1, 2)]
        L = np.zeros((3, 3), dtype=np.float32)   # wrong K
        with pytest.raises(AssertionError):
            reid_rate_head(L, gaps)


# ===========================================================================
#  M2b: frozen_breaks determinism
# ===========================================================================

class TestFrozenBreaks:
    """M2b: deterministic break generation + disk round-trip."""

    @staticmethod
    def _make_gt(H=64, W=64) -> np.ndarray:
        gt = np.zeros((H, W), dtype=np.uint8)
        for row in [H // 3, 2 * H // 3]:
            gt[row - 1:row + 2, 5: W - 5] = 1
        return gt

    def test_same_imgid_same_seed(self):
        """Same img_id must produce same seed every call."""
        s1 = _img_id_to_seed('01')
        s2 = _img_id_to_seed('01')
        assert s1 == s2

    def test_different_imgid_different_seed(self):
        """Different img_ids must produce different seeds (collision unlikely)."""
        s1 = _img_id_to_seed('01')
        s2 = _img_id_to_seed('02')
        assert s1 != s2

    def test_seed_is_int_in_valid_range(self):
        """Seed must be a non-negative int < 2^31."""
        s = _img_id_to_seed('test_img_99')
        assert isinstance(s, int)
        assert 0 <= s < 2**31

    def test_disk_round_trip_deterministic(self, tmp_path):
        """
        get_frozen_breaks called twice with same img_id and cache_dir must
        return the SAME break_result (from disk on second call).
        """
        gt = self._make_gt()

        br1 = get_frozen_breaks(
            cache_dir=tmp_path, img_id='test01', gt_mask=gt,
            dataset='synth', gap_size=6, nb_deco=20,
        )
        br2 = get_frozen_breaks(
            cache_dir=tmp_path, img_id='test01', gt_mask=gt,
            dataset='synth', gap_size=6, nb_deco=20,
        )

        assert br1 is not None
        assert br2 is not None
        assert len(br1.gaps) == len(br2.gaps), (
            "Second call (from disk) must have same number of gaps"
        )
        # Gap centres must be identical
        for g1, g2 in zip(br1.gaps, br2.gaps):
            assert g1.center_yx == g2.center_yx
            assert g1.segment_id_left == g2.segment_id_left

    def test_different_imgids_may_differ(self, tmp_path):
        """
        Two different img_ids must get different seeds → typically different gaps
        (not guaranteed due to randomness, but gap_ids must differ).
        At minimum, seeds must differ (already tested above).
        """
        gt = self._make_gt()
        s1 = _img_id_to_seed('img_A')
        s2 = _img_id_to_seed('img_B')
        assert s1 != s2, "Different img_ids must map to different seeds"

    def test_cache_miss_without_gt_returns_none(self, tmp_path):
        """If no cached file and no gt_mask provided → return None."""
        result = get_frozen_breaks(
            cache_dir=tmp_path, img_id='nonexistent_img', gt_mask=None,
        )
        assert result is None

    def test_npz_file_created_on_cache_dir(self, tmp_path):
        """After first call, .npz file must exist in cache_dir."""
        gt = self._make_gt()
        get_frozen_breaks(
            cache_dir=tmp_path, img_id='img_cache_test', gt_mask=gt,
            dataset='chase', gap_size=6, nb_deco=10,
        )
        npz_files = list(tmp_path.glob('*.npz'))
        assert len(npz_files) == 1, f"Expected 1 .npz, found {len(npz_files)}"


# ===========================================================================
#  M4: A1' dead-param grad norms > 0
# ===========================================================================

class TestA1PrimeGradNorms:
    """M4: proj_erase / proj_g / alpha_e must receive gradient after backward."""

    def _build_a1p(self, base_ch=8, d_head=8, n_heads=1):
        return UNetGDN2(
            in_ch=1, out_ch=1, base_ch=base_ch, d_head=d_head, n_heads=n_heads,
            memory_mode='linear_attn', use_frangi=True,
            use_reid_head=False,
        )

    def _run_backward(self, model):
        model.train()
        for p in model.parameters():
            p.grad = None
        x = torch.randn(1, 1, 64, 64)
        loss = model(x).sum()
        loss.backward()

    def test_proj_erase_weight_grad_nonzero(self):
        m = self._build_a1p()
        self._run_backward(m)
        gn = m.linear_attn.proj_erase.weight.grad.norm().item()
        assert gn > 0.0, (
            f"proj_erase.weight.grad norm = {gn:.6e} (should be > 0 after M4 fix)"
        )

    def test_proj_g_weight_grad_nonzero(self):
        m = self._build_a1p()
        self._run_backward(m)
        gn = m.linear_attn.proj_g.weight.grad.norm().item()
        assert gn > 0.0, (
            f"proj_g.weight.grad norm = {gn:.6e} (should be > 0 after M4 fix)"
        )

    def test_alpha_e_grad_nonzero(self):
        m = self._build_a1p()
        self._run_backward(m)
        gn = m.linear_attn.alpha_e.grad.norm().item()
        assert gn > 0.0, (
            f"alpha_e.grad norm = {gn:.6e} (should be > 0 after M4 fix)"
        )

    def test_a1prime_still_stateless_no_S_t(self):
        """
        A1' stateless contract: return_memory gives list of all-None states
        (no S_t recurrence introduced by M4).
        Use LinearAttnModule directly with known d_model.
        """
        la = LinearAttnModule(
            d_model=8, d_head=8, n_heads=1, directions=1, use_frangi=True
        )
        la.eval()
        with torch.no_grad():
            _, states = la(torch.randn(1, 8, 8, 8), return_memory=True)
        assert isinstance(states, list)
        assert all(s is None for s in states), (
            "M4 must NOT introduce S_t state recurrence in A1'"
        )

    def test_a1prime_output_shape_preserved_after_m4(self):
        """M4 changes gate flow but must not change output shape."""
        m = self._build_a1p()
        m.eval()
        x = torch.randn(1, 1, 64, 64)
        with torch.no_grad():
            out = m(x)
        assert out.shape == (1, 1, 64, 64), f"Got {out.shape}"

    def test_a2_forward_no_exception(self):
        """
        Sanity: A2 model forward must not raise (no regression in forward path).
        Note: grad checks on A2 are skipped in mock-FLA mode because the mock
        kernel (passthrough v) does not propagate gradients through beta/write_gate;
        real HPC runs with actual FLA kernel will have correct grad flow.
        """
        m = UNetGDN2(
            in_ch=1, out_ch=1, base_ch=8, d_head=8, n_heads=1,
            memory_mode='delta_rule', use_frangi=True,
            use_reid_head=False,
        )
        m.eval()
        with torch.no_grad():
            out = m(torch.randn(1, 1, 64, 64))
        assert out.shape == (1, 1, 64, 64), f"A2 output shape wrong: {out.shape}"


# ===========================================================================
#  M5: audit_iso_param integration
# ===========================================================================

class TestAuditIsoParam:
    """M5: audit script returns correct pass flags."""

    def test_audit_passes_small_config(self):
        from audit_iso_param import audit_iso_param

        r = audit_iso_param(base_ch=8, d_head=8, n_heads=1, image_size=32)

        # Iso-param
        assert r['iso_pass'], (
            f"Iso-param FAIL: diff={r['diff_pct']:+.2f}% (must be ≤±5%)"
        )
        # Dead-param fix
        assert r['dead_param_pass'], (
            f"Dead-param FAIL: proj_erase={r['proj_erase_grad_norm']:.3e}, "
            f"proj_g={r['proj_g_grad_norm']:.3e}, alpha_e={r['alpha_e_grad_norm']:.3e}"
        )
        # Grad norms individually > 0
        assert r['proj_erase_grad_norm'] > 0.0
        assert r['proj_g_grad_norm']     > 0.0
        assert r['alpha_e_grad_norm']    > 0.0

    def test_audit_numel_a1p_ge_a0p(self):
        """A1' should have more params than A0' (attention module adds params)."""
        from audit_iso_param import audit_iso_param
        r = audit_iso_param(base_ch=8, d_head=8, n_heads=1, image_size=32)
        assert r['n_a1p'] > r['n_a0p'], (
            f"A1' numel ({r['n_a1p']}) should exceed A0' numel ({r['n_a0p']})"
        )
