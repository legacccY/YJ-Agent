"""
test_benchmark.py — Unit tests for synth_breaks + metrics.

Tests:
  1. synth_breaks: creatis algorithm correctness
     - Given fixed seed, output is reproducible
     - Binarisation threshold ≥0.1 (not 0.5)
     - mask_broken is subset of GT (zero-leakage)
     - mask_broken actually has fewer foreground pixels than GT (gaps deleted)
     - GapRecords extracted (may be 0 on thin synthetic masks)
     - severity grid: Medium size_max=8 nb_deco=100

  2. metrics: DSC / ASSD / epsilon_beta0 correctness
     - DSC(pred, pred) == 1.0
     - DSC(pred, empty) == 0.0
     - DSC known-value case
     - ASSD(pred, pred) == 0.0
     - ASSD known-value case (disjoint shifted masks)
     - epsilon_beta0 perfect case == 0.0
     - epsilon_beta0 extra component case

  3. Betti-err (Entry 9, L2/L6 cross-validation)
     - solid disk: β1=0, β0=1
     - ring/donut: β1=1, β0=1
     - two components: β0=2, β1=0
     - betti_error perfect case = 0
     - betti_error ring-vs-solid detects β1 difference

  4. APLS (Entry 9, L2/L6 cross-validation)
     - identical masks → APLS near 1.0
     - empty pred → APLS = 0.0
     - APLS ∈ [0, 1]
     - compute_all_metrics keys present
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

_repo_root = Path(__file__).parent.parent
_src_dir = _repo_root / 'src'
if str(_src_dir) not in sys.path:
    sys.path.insert(0, str(_src_dir))

from benchmark.synth_breaks import (
    apply_breaks,
    apply_breaks_all_severities,
    SEVERITY_GRID,
    _create_disconnections,
    _disc,
    _create_artefact,
)
from benchmark.metrics import (
    dice_coefficient,
    assd,
    count_components,
    count_loops,
    epsilon_beta0,
    betti_error,
    apls,
    success_rate,
    reid_rate,
    compute_all_metrics,
)


# ===========================================================================
#  Fixtures: simple synthetic vessel masks
# ===========================================================================

def _make_horizontal_line_mask(H=64, W=64, row=32, thickness=2) -> np.ndarray:
    """A horizontal vessel running the full width."""
    mask = np.zeros((H, W), dtype=np.uint8)
    r0 = max(0, row - thickness // 2)
    r1 = min(H, row + thickness // 2 + 1)
    mask[r0:r1, :] = 1
    return mask


def _make_cross_mask(H=64, W=64) -> np.ndarray:
    """A + shaped mask with two components (horizontal + vertical)."""
    mask = np.zeros((H, W), dtype=np.uint8)
    mask[H // 2 - 1:H // 2 + 2, :] = 1   # horizontal bar
    mask[:, W // 2 - 1:W // 2 + 2] = 1   # vertical bar
    return mask


# ===========================================================================
#  1. synth_breaks — _disc helper
# ===========================================================================

class TestDiscHelper:

    def test_disc_fills_center(self):
        img = np.zeros((20, 20))
        img = _disc(img, 10, 10, 3)
        assert img[10, 10] == 1

    def test_disc_boundary_safe(self):
        """Disc near edge should not raise IndexError."""
        img = np.zeros((20, 20))
        img = _disc(img, 0, 0, 5)   # centre at corner
        assert img[0, 0] == 1

    def test_disc_radius_zero(self):
        img = np.zeros((10, 10))
        img = _disc(img, 5, 5, 0)
        assert img[5, 5] == 1

    def test_disc_area_approx(self):
        """Disc area should be approximately π*r^2."""
        img = np.zeros((50, 50))
        r = 8
        img = _disc(img, 25, 25, r)
        area = img.sum()
        expected = np.pi * r ** 2
        # Accept ±20% tolerance for discrete approximation
        assert abs(area - expected) / expected < 0.20, (
            f"Disc area {area} far from expected {expected:.1f}"
        )


# ===========================================================================
#  2. synth_breaks — _create_disconnections
# ===========================================================================

class TestCreateDisconnections:

    def _line_mask(self):
        return _make_horizontal_line_mask(H=64, W=64, row=32, thickness=3)

    def test_reproducible_with_seed(self):
        """Same seed → identical output."""
        gt = self._line_mask().astype(np.float64)
        img1, disc1 = _create_disconnections(gt, nb_disconnection=10, size_max=8, rng_seed=42)
        img2, disc2 = _create_disconnections(gt, nb_disconnection=10, size_max=8, rng_seed=42)
        np.testing.assert_array_equal(img1, img2)
        np.testing.assert_array_equal(disc1, disc2)

    def test_different_seed_different_output(self):
        """Different seeds → different (with high probability) disconnections."""
        gt = self._line_mask().astype(np.float64)
        img1, _ = _create_disconnections(gt, nb_disconnection=50, size_max=8, rng_seed=1)
        img2, _ = _create_disconnections(gt, nb_disconnection=50, size_max=8, rng_seed=2)
        # They should differ with high probability (50 draws on a line)
        assert not np.array_equal(img1, img2), "Expected different results with different seeds"

    def test_binarise_threshold_is_01(self):
        """Output values must be exactly {0.0, 1.0} (binarised at ≥0.1)."""
        gt = self._line_mask().astype(np.float64)
        img, disc = _create_disconnections(gt, nb_disconnection=20, size_max=8, rng_seed=7)
        unique_img = set(np.unique(img).tolist())
        unique_disc = set(np.unique(disc).tolist())
        assert unique_img.issubset({0.0, 1.0}), f"img has non-binary values: {unique_img}"
        assert unique_disc.issubset({0.0, 1.0}), f"disc has non-binary values: {unique_disc}"

    def test_output_is_subset_of_gt(self):
        """image (GT minus erosions) must be subset of original GT."""
        gt = self._line_mask().astype(np.float64)
        img, _ = _create_disconnections(gt, nb_disconnection=30, size_max=8, rng_seed=3)
        # No pixel can appear in output that wasn't in GT
        leaked = (img > 0) & (gt == 0)
        assert not np.any(leaked), "Zero-leakage violated: new pixels created outside GT"

    def test_fewer_pixels_than_gt(self):
        """Disconnected mask should have fewer foreground pixels than GT."""
        gt = self._line_mask().astype(np.float64)
        img, _ = _create_disconnections(gt, nb_disconnection=50, size_max=8, rng_seed=9)
        assert img.sum() < gt.sum(), "Expected disconnected mask to have fewer fg pixels"

    def test_degenerate_empty_gt(self):
        """Empty GT → returns empty output without error."""
        gt = np.zeros((32, 32), dtype=np.float64)
        img, disc = _create_disconnections(gt, nb_disconnection=10, size_max=8, rng_seed=0)
        assert img.sum() == 0
        assert disc.sum() == 0


# ===========================================================================
#  3. synth_breaks — apply_breaks public API
# ===========================================================================

class TestApplyBreaks:

    def test_mask_broken_is_subset_of_gt(self):
        gt = _make_horizontal_line_mask()
        result = apply_breaks(gt, gap_size=8, nb_deco=50, seed=42)
        leaked = (result.mask_broken > 0) & (gt == 0)
        assert not np.any(leaked), "mask_broken has pixels outside GT"

    def test_reproducible(self):
        gt = _make_horizontal_line_mask()
        r1 = apply_breaks(gt, gap_size=8, nb_deco=30, seed=17)
        r2 = apply_breaks(gt, gap_size=8, nb_deco=30, seed=17)
        np.testing.assert_array_equal(r1.mask_broken, r2.mask_broken)

    def test_result_dtype(self):
        gt = _make_horizontal_line_mask()
        result = apply_breaks(gt, gap_size=8, nb_deco=20, seed=0)
        assert result.mask_broken.dtype == np.uint8, (
            f"mask_broken dtype {result.mask_broken.dtype} != uint8"
        )

    def test_vessel_segment_map_positive_where_gt(self):
        gt = _make_horizontal_line_mask()
        result = apply_breaks(gt, gap_size=8, nb_deco=20, seed=0)
        # vessel_segment_map should have positive labels inside GT
        assert (result.vessel_segment_map[gt > 0] > 0).any(), (
            "vessel_segment_map has no positive labels inside GT"
        )

    def test_gaps_list_is_list(self):
        gt = _make_horizontal_line_mask()
        result = apply_breaks(gt, gap_size=8, nb_deco=20, seed=0)
        assert isinstance(result.gaps, list)

    def test_gap_records_have_correct_fields(self):
        gt = _make_cross_mask()
        result = apply_breaks(gt, gap_size=8, nb_deco=50, seed=5)
        for g in result.gaps:
            assert hasattr(g, 'gap_id')
            assert hasattr(g, 'center_yx')
            assert hasattr(g, 'radius')
            assert hasattr(g, 'segment_id_left')
            assert hasattr(g, 'segment_id_right')
            assert g.sigma == pytest.approx(0.8)  # official sigma
            assert isinstance(g.center_yx, tuple) and len(g.center_yx) == 2

    def test_severity_grid_medium_params(self):
        """Medium severity must use size_max=8, nb_deco=100 (creatis official)."""
        assert SEVERITY_GRID['Medium']['size_max'] == 8
        assert SEVERITY_GRID['Medium']['nb_deco'] == 100

    def test_apply_breaks_all_severities_returns_all_keys(self):
        gt = _make_horizontal_line_mask()
        results = apply_breaks_all_severities(gt, base_seed=0)
        for key in ('Easy', 'Medium', 'Hard', 'Extreme'):
            assert key in results, f"Missing severity key: {key}"

    def test_apply_breaks_all_severities_different_outputs(self):
        """Different severities → generally different mask_broken."""
        gt = _make_horizontal_line_mask()
        results = apply_breaks_all_severities(gt, base_seed=0)
        # Easy and Extreme should differ (different size_max)
        easy = results['Easy'].mask_broken
        extreme = results['Extreme'].mask_broken
        assert not np.array_equal(easy, extreme), (
            "Easy and Extreme severities produced identical masks"
        )


# ===========================================================================
#  4. metrics — DSC
# ===========================================================================

class TestDSC:

    def test_perfect_overlap(self):
        pred = np.array([[1, 1, 0],
                         [0, 1, 0]], dtype=np.uint8)
        assert dice_coefficient(pred, pred) == pytest.approx(1.0)

    def test_no_overlap(self):
        pred = np.array([[1, 0], [0, 0]], dtype=np.uint8)
        gt   = np.array([[0, 1], [0, 0]], dtype=np.uint8)
        assert dice_coefficient(pred, gt) == pytest.approx(0.0)

    def test_both_empty(self):
        assert dice_coefficient(np.zeros((4, 4)), np.zeros((4, 4))) == pytest.approx(1.0)

    def test_known_value(self):
        """pred = [1,1,0,0], gt = [1,0,0,1] → intersection=1, denom=4 → DSC=0.5"""
        pred = np.array([[1, 1, 0, 0]])
        gt   = np.array([[1, 0, 0, 1]])
        # |pred|=2, |gt|=2, intersection=1, DSC = 2*1/(2+2) = 0.5
        assert dice_coefficient(pred, gt) == pytest.approx(0.5)

    def test_symmetry(self):
        a = np.random.randint(0, 2, (16, 16), dtype=np.uint8)
        b = np.random.randint(0, 2, (16, 16), dtype=np.uint8)
        assert dice_coefficient(a, b) == pytest.approx(dice_coefficient(b, a))


# ===========================================================================
#  5. metrics — ASSD
# ===========================================================================

class TestASSd:

    def test_identical_masks(self):
        mask = np.zeros((20, 20), dtype=np.uint8)
        mask[8:12, 5:15] = 1
        assert assd(mask, mask) == pytest.approx(0.0, abs=1e-6)

    def test_both_empty(self):
        assert assd(np.zeros((10, 10)), np.zeros((10, 10))) == pytest.approx(0.0)

    def test_one_empty(self):
        pred = np.zeros((10, 10), dtype=np.uint8)
        gt = np.ones((10, 10), dtype=np.uint8)
        result = assd(pred, gt)
        assert result == float('inf'), f"Expected inf for empty pred, got {result}"

    def test_shifted_mask(self):
        """
        pred = single pixel at (5,5), gt = single pixel at (5,8).
        ASSD should be exactly 3.0 pixels (Manhattan=3, but EDT is Euclidean = 3.0).
        """
        pred = np.zeros((20, 20), dtype=np.uint8)
        pred[5, 5] = 1
        gt = np.zeros((20, 20), dtype=np.uint8)
        gt[5, 8] = 1
        result = assd(pred, gt)
        assert result == pytest.approx(3.0, abs=0.5), (
            f"Expected ASSD≈3.0 for 3-pixel shift, got {result}"
        )

    def test_symmetry(self):
        a = np.zeros((20, 20), dtype=np.uint8)
        a[5:10, 5:10] = 1
        b = np.zeros((20, 20), dtype=np.uint8)
        b[10:15, 10:15] = 1
        assert assd(a, b) == pytest.approx(assd(b, a), abs=1e-6)


# ===========================================================================
#  6. metrics — epsilon_beta0
# ===========================================================================

class TestEpsilonBeta0:

    def test_perfect(self):
        pred = np.array([[1, 0, 0, 1]], dtype=np.uint8)
        gt   = np.array([[1, 0, 0, 1]], dtype=np.uint8)
        # both have 2 components → eps=0
        assert epsilon_beta0(pred, gt) == pytest.approx(0.0)

    def test_extra_component(self):
        """pred has extra component: β0_pred=3, β0_gt=2 → eps = 1/2 = 0.5"""
        pred = np.zeros((5, 15), dtype=np.uint8)
        pred[2, 0] = 1
        pred[2, 7] = 1
        pred[2, 14] = 1   # 3 isolated pixels = 3 components
        gt = np.zeros((5, 15), dtype=np.uint8)
        gt[2, 0] = 1
        gt[2, 14] = 1     # 2 isolated pixels = 2 components
        eps = epsilon_beta0(pred, gt)
        assert eps == pytest.approx(0.5, abs=1e-6)

    def test_empty_gt(self):
        """gt empty → β0_gt=0 → denominator clamped to 1 → no div-by-zero"""
        pred = np.zeros((5, 5), dtype=np.uint8)
        pred[2, 2] = 1   # 1 component
        gt = np.zeros((5, 5), dtype=np.uint8)
        eps = epsilon_beta0(pred, gt)
        assert eps == pytest.approx(1.0 / max(0, 1))   # |1-0|/max(0,1) = 1.0


# ===========================================================================
#  7. metrics — compute_all_metrics keys and types
# ===========================================================================

class TestComputeAllMetrics:

    def test_keys_present(self):
        gt = _make_horizontal_line_mask(H=32, W=32)
        result = apply_breaks(gt, gap_size=8, nb_deco=10, seed=0)
        metrics = compute_all_metrics(gt, gt, result, compute_assd=False)
        for key in ('dsc', 'assd', 'epsilon_beta0', 'success_rate', 'reid_rate',
                    'beta0_pred', 'beta0_gt', 'n_gaps', 'n_gaps_closed',
                    'n_gaps_reidentified'):
            assert key in metrics, f"Missing key: {key}"

    def test_perfect_reconstruction_dsc(self):
        """Using GT as pred → DSC should be 1.0"""
        gt = _make_horizontal_line_mask(H=32, W=32)
        result = apply_breaks(gt, gap_size=8, nb_deco=5, seed=0)
        metrics = compute_all_metrics(gt, gt, result, compute_assd=False)
        assert metrics['dsc'] == pytest.approx(1.0)

    def test_perfect_reconstruction_eps_b0(self):
        """Using GT as pred → ε_β0 should be 0.0"""
        gt = _make_horizontal_line_mask(H=32, W=32)
        result = apply_breaks(gt, gap_size=8, nb_deco=5, seed=0)
        metrics = compute_all_metrics(gt, gt, result, compute_assd=False)
        assert metrics['epsilon_beta0'] == pytest.approx(0.0)

    def test_assd_skipped_when_disabled(self):
        gt = _make_horizontal_line_mask(H=32, W=32)
        result = apply_breaks(gt, gap_size=8, nb_deco=5, seed=0)
        metrics = compute_all_metrics(gt, gt, result, compute_assd=False)
        import math
        assert math.isnan(metrics['assd'])

    def test_n_gaps_matches_gaps_list(self):
        gt = _make_cross_mask(H=64, W=64)
        result = apply_breaks(gt, gap_size=8, nb_deco=50, seed=99)
        metrics = compute_all_metrics(gt, gt, result, compute_assd=False)
        assert metrics['n_gaps'] == len(result.gaps)

    def test_betti_keys_present(self):
        """compute_all_metrics must include betti_err and apls keys."""
        gt = _make_horizontal_line_mask(H=32, W=32)
        result = apply_breaks(gt, gap_size=8, nb_deco=5, seed=0)
        metrics = compute_all_metrics(gt, gt, result, compute_assd=False, compute_apls=False)
        for key in ('betti_err_total', 'beta0_err', 'beta1_err',
                    'beta1_pred', 'beta1_gt', 'apls'):
            assert key in metrics, f"Missing key: {key}"


# ===========================================================================
#  8. Betti-err — topological error (Entry 9, L2/L6 cross-validation)
# ===========================================================================

class TestBettiError:

    def _solid_square(self, H=20, W=20, pad=3) -> np.ndarray:
        """Solid filled square: β0=1, β1=0."""
        m = np.zeros((H, W), dtype=np.uint8)
        m[pad:H-pad, pad:W-pad] = 1
        return m

    def _ring(self) -> np.ndarray:
        """Donut / ring: β0=1, β1=1 (one hole)."""
        m = np.zeros((20, 20), dtype=np.uint8)
        m[2:18, 2:18] = 1
        m[6:14, 6:14] = 0   # punch hole
        return m

    def test_solid_has_zero_loops(self):
        """Solid square: β1 = 0."""
        sq = self._solid_square()
        assert count_loops(sq) == 0

    def test_ring_has_one_loop(self):
        """Ring / donut: β1 = 1 (one enclosed hole)."""
        ring = self._ring()
        assert count_loops(ring) == 1

    def test_two_components_b0(self):
        """Two isolated pixels → β0=2, β1=0."""
        m = np.zeros((10, 20), dtype=np.uint8)
        m[5, 2] = 1
        m[5, 17] = 1
        assert count_components(m) == 2
        assert count_loops(m) == 0

    def test_betti_error_perfect(self):
        """betti_error(pred==gt) → all errors = 0."""
        sq = self._solid_square()
        be = betti_error(sq, sq)
        assert be['beta0_err'] == 0
        assert be['beta1_err'] == 0
        assert be['betti_err_total'] == 0

    def test_betti_error_ring_vs_solid(self):
        """
        GT = ring (β1=1), pred = solid (β1=0) → β1_err=1, betti_err_total≥1.
        Both have β0=1 so β0_err=0.
        """
        ring = self._ring()
        solid = self._solid_square()
        be = betti_error(solid, ring)   # pred=solid, gt=ring
        assert be['beta0_err'] == 0, "Both are 1 component"
        assert be['beta1_err'] == 1, f"Expected β1_err=1, got {be['beta1_err']}"
        assert be['betti_err_total'] == 1

    def test_betti_error_extra_component(self):
        """pred has extra component → β0_err ≥ 1."""
        m = np.zeros((10, 30), dtype=np.uint8)
        m[5, 2] = 1
        m[5, 27] = 1   # two components
        single = np.zeros((10, 30), dtype=np.uint8)
        single[5, 2] = 1   # one component
        be = betti_error(m, single)   # pred=two, gt=one
        assert be['beta0_err'] == 1
        assert be['betti_err_total'] >= 1

    def test_empty_masks(self):
        """Both empty → β0=0, β1=0, errors=0."""
        empty = np.zeros((10, 10), dtype=np.uint8)
        be = betti_error(empty, empty)
        assert be['betti_err_total'] == 0

    def test_betti_error_returns_dict_keys(self):
        sq = self._solid_square()
        be = betti_error(sq, sq)
        for k in ('beta0_pred', 'beta0_gt', 'beta0_err',
                  'beta1_pred', 'beta1_gt', 'beta1_err', 'betti_err_total'):
            assert k in be, f"Missing key: {k}"


# ===========================================================================
#  9. APLS — Average Path Length Similarity (Entry 9, L2/L6 cross-validation)
# ===========================================================================

class TestAPLS:

    def test_identical_masks_near_one(self):
        """
        APLS(pred==gt) should be 1.0 (zero path-length difference).
        """
        gt = _make_horizontal_line_mask(H=32, W=64, row=16, thickness=1)
        result = apls(gt, gt, min_path_length=5.0, control_node_stride=3)
        assert result == pytest.approx(1.0, abs=1e-5), (
            f"APLS(identical) expected 1.0, got {result}"
        )

    def test_empty_gt_returns_zero(self):
        """Empty GT skeleton → APLS = 0.0 (undefined)."""
        gt   = np.zeros((20, 20), dtype=np.uint8)
        pred = _make_horizontal_line_mask(H=20, W=20)
        result = apls(pred, gt, min_path_length=5.0)
        assert result == pytest.approx(0.0)

    def test_empty_pred_returns_zero(self):
        """Empty pred skeleton → all paths missing → APLS = 0.0."""
        gt   = _make_horizontal_line_mask(H=20, W=20)
        pred = np.zeros((20, 20), dtype=np.uint8)
        result = apls(pred, gt, min_path_length=5.0)
        assert result == pytest.approx(0.0)

    def test_apls_in_range(self):
        """APLS must be in [0, 1]."""
        gt   = _make_horizontal_line_mask(H=32, W=64, row=16, thickness=1)
        pred = _make_horizontal_line_mask(H=32, W=64, row=16, thickness=2)
        result = apls(pred, gt, min_path_length=5.0, control_node_stride=5)
        assert 0.0 <= result <= 1.0, f"APLS out of range: {result}"

    def test_apls_compute_disabled(self):
        """compute_all_metrics with compute_apls=False → apls=nan."""
        import math
        gt = _make_horizontal_line_mask(H=32, W=32)
        result = apply_breaks(gt, gap_size=8, nb_deco=5, seed=0)
        metrics = compute_all_metrics(gt, gt, result,
                                      compute_assd=False, compute_apls=False)
        assert math.isnan(metrics['apls']), "Expected nan when compute_apls=False"

    def test_apls_compute_enabled(self):
        """compute_all_metrics with compute_apls=True → apls is a float in [0,1]."""
        gt = _make_horizontal_line_mask(H=32, W=64, row=16, thickness=1)
        result = apply_breaks(gt, gap_size=8, nb_deco=5, seed=0)
        metrics = compute_all_metrics(gt, gt, result,
                                      compute_assd=False, compute_apls=True,
                                      apls_min_path_length=3.0,
                                      apls_control_stride=3)
        val = metrics['apls']
        assert 0.0 <= val <= 1.0, f"APLS out of range: {val}"
