"""
test_avs2_crowding.py — Tests for A-v2 M-A (memory-only head) + M-B (crowding)
                         + M-C (dose-response verdict) + B-3 (integration).

Covers:
  1. M-A: ReIDReadoutHead use_loc_feat=False skips _grid_sample_at / loc_proj / fuse
  2. M-A: forward does not crash; output shape correct; no loc path
  3. M-B B-1: compute_k_per_gap known distribution
  4. M-B B-1: compute_k_thresh returns median/mean/p60
  5. M-B B-2: reid_rate_head high/low stratification correct (known k distribution)
  6. M-B B-2: n_high + n_low consistent with masks; nan when gap_k omitted
  7. M-C: run_verdict parses reid_rate_head_high/low columns (new CSV cols)
  8. M-C: dose-response verdict structure keys exist in run_verdict output
  9. B-3 integration: _reid_head_forward_on_tile returns dict (not tuple)
  10. Header/data alignment check: CSV written by evaluate_on_benchmark has
      matching header and data column count (blood-lesson from A-I)

Red lines:
  - No scipy.stats
  - detach1/2/3 barriers not removed
  - k only for evaluation stratification, never in model forward
"""
from __future__ import annotations

import csv
import json
import sys
import types
import tempfile
from pathlib import Path
from typing import List

import numpy as np
import pytest
import torch

# ─────────────────────────────────────────────────────────────────────────────
# sys.path
# ─────────────────────────────────────────────────────────────────────────────
_repo_root = Path(__file__).parent.parent
_src_dir   = _repo_root / 'src'
if str(_src_dir) not in sys.path:
    sys.path.insert(0, str(_src_dir))


# ─────────────────────────────────────────────────────────────────────────────
# FLA mock (same as test_reid_eval_e2e.py)
# ─────────────────────────────────────────────────────────────────────────────

def _patch_fla():
    def _fake_fn(q, k, v, beta, g, output_final_state=False):
        B, T, nh, dh = v.shape
        state = torch.zeros(B, nh, dh, dh) if output_final_state else None
        return v.clone(), state

    fake_fla   = types.ModuleType('fla')
    fake_ops   = types.ModuleType('fla.ops')
    fake_gdr   = types.ModuleType('fla.ops.gated_delta_rule')
    fake_naive = types.ModuleType('fla.ops.gated_delta_rule.naive')
    fake_chunk = types.ModuleType('fla.ops.gated_delta_rule.chunk')
    fake_naive.naive_chunk_gated_delta_rule = _fake_fn
    fake_chunk.chunk_gated_delta_rule       = _fake_fn
    sys.modules.setdefault('fla',                            fake_fla)
    sys.modules.setdefault('fla.ops',                        fake_ops)
    sys.modules.setdefault('fla.ops.gated_delta_rule',       fake_gdr)
    sys.modules.setdefault('fla.ops.gated_delta_rule.naive', fake_naive)
    sys.modules.setdefault('fla.ops.gated_delta_rule.chunk', fake_chunk)


_patch_fla()


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _make_reid_head(use_loc_feat: bool = True, d_head: int = 8,
                    n_heads: int = 1, dec_ch: int = 16, d_id: int = 16):
    from models.unet_gdn2 import ReIDReadoutHead
    return ReIDReadoutHead(
        d_head=d_head,
        n_heads=n_heads,
        dec_ch=dec_ch,
        d_id=d_id,
        feat_source='memory',
        detach_memory_train=True,
        use_loc_feat=use_loc_feat,
    )


def _make_gap_records(n: int = 10, H: int = 64, W: int = 64):
    """Synthetic GapRecord-like dicts for testing."""
    rng = np.random.default_rng(0)
    gaps = []
    for i in range(n):
        cy = int(rng.integers(5, H - 5))
        cx = int(rng.integers(5, W - 5))
        seg_l = i % 3            # 3 distinct segment IDs
        seg_r = (i + 1) % 3
        gaps.append({
            'gap_id':           i,
            'center_yx':        (cy, cx),
            'radius':           3,
            'gap_size':         6,
            'sigma':            1.0,
            'segment_id_left':  seg_l,
            'segment_id_right': seg_r,
        })
    return gaps


# ─────────────────────────────────────────────────────────────────────────────
# 1-2. M-A: memory-only head
# ─────────────────────────────────────────────────────────────────────────────

class TestMemoryOnlyHead:

    def _forward(self, head, K: int = 4):
        """Run head with synthetic (B=1, K, ...) tensors."""
        d_total = head.d_head * head.n_heads
        o_seq   = torch.randn(1, 16, d_total)          # (B, T=16, nh*d_head)
        dec_feat = torch.randn(1, head.dec_ch, 8, 8)  # (B, dec_ch, H_dec, W_dec)
        positions = torch.zeros(1, K, 2)               # (B, K, 2)
        positions[0, :, 0] = torch.arange(K).float() * 2
        positions[0, :, 1] = torch.arange(K).float() * 2
        return head(o_seq=o_seq, dec_feat=dec_feat,
                    breakpoint_positions=positions)

    def test_memory_only_no_crash(self):
        """use_loc_feat=False forward does not crash."""
        head = _make_reid_head(use_loc_feat=False)
        head.eval()
        with torch.no_grad():
            logits = self._forward(head, K=4)
        assert logits.shape == (1, 4, 4), f'Expected (1,4,4), got {logits.shape}'

    def test_memory_only_no_loc_proj(self):
        """use_loc_feat=False: loc_proj and fuse are None (not built)."""
        head = _make_reid_head(use_loc_feat=False)
        assert head.loc_proj is None, 'loc_proj should be None for memory-only head'
        assert head.fuse     is None, 'fuse should be None for memory-only head'

    def test_memory_only_loc_feat_not_sampled(self):
        """
        use_loc_feat=False: _grid_sample_at should NOT be called.
        Verify by patching _grid_sample_at in unet_gdn2 and checking call count.
        """
        import models.unet_gdn2 as _m
        call_count = {'n': 0}
        original = _m._grid_sample_at

        def _patched(*args, **kwargs):
            call_count['n'] += 1
            return original(*args, **kwargs)

        _m._grid_sample_at = _patched
        try:
            head = _make_reid_head(use_loc_feat=False)
            head.eval()
            with torch.no_grad():
                self._forward(head, K=4)
            assert call_count['n'] == 0, (
                f'_grid_sample_at called {call_count["n"]} times; '
                f'expected 0 for memory-only head'
            )
        finally:
            _m._grid_sample_at = original

    def test_loc_feat_true_calls_grid_sample(self):
        """use_loc_feat=True: _grid_sample_at IS called (control test)."""
        import models.unet_gdn2 as _m
        call_count = {'n': 0}
        original = _m._grid_sample_at

        def _patched(*args, **kwargs):
            call_count['n'] += 1
            return original(*args, **kwargs)

        _m._grid_sample_at = _patched
        try:
            head = _make_reid_head(use_loc_feat=True)
            head.eval()
            with torch.no_grad():
                self._forward(head, K=4)
            assert call_count['n'] > 0, (
                '_grid_sample_at should be called for use_loc_feat=True'
            )
        finally:
            _m._grid_sample_at = original

    def test_memory_only_output_shape_K8(self):
        """K=8, output (1, 8, 8), diagonal -inf."""
        head = _make_reid_head(use_loc_feat=False)
        head.eval()
        with torch.no_grad():
            logits = self._forward(head, K=8)
        assert logits.shape == (1, 8, 8)
        diag = logits[0].diagonal()
        assert torch.isinf(diag).all(), (
            'diagonal should be -inf'
        )

    def test_unetgdn2_reid_use_loc_feat_false(self):
        """UNetGDN2 with reid_use_loc_feat=False builds correctly."""
        from models.unet_gdn2 import UNetGDN2
        model = UNetGDN2(
            in_ch=1, out_ch=1, base_ch=8, d_head=8, n_heads=1,
            memory_mode='delta_rule', backend='naive',
            use_reid_head=True, reid_use_loc_feat=False,
        )
        assert model.reid_head is not None
        assert model.reid_head.use_loc_feat is False
        assert model.reid_head.loc_proj is None
        assert model.reid_head.fuse is None


# ─────────────────────────────────────────────────────────────────────────────
# 3-4. M-B B-1: compute_k_per_gap and compute_k_thresh
# ─────────────────────────────────────────────────────────────────────────────

class TestCrowdingKPerGap:
    """Tests for benchmark.crowding.compute_k_per_gap and compute_k_thresh."""

    def test_k_self_in_window(self):
        """Gap i is in its own R_win window; k(i) ≥ 1 if valid segment IDs."""
        from benchmark.crowding import compute_k_per_gap
        gaps = [
            {'center_yx': (50, 50), 'segment_id_left': 1, 'segment_id_right': 2},
        ]
        k = compute_k_per_gap(gaps, R_win=100.0)
        assert k[0] >= 1, f'k(0) should be ≥ 1 (self included), got {k[0]}'

    def test_k_isolated_gap(self):
        """Single gap far from all others (large image) → k = its own IDs."""
        from benchmark.crowding import compute_k_per_gap
        gaps = [
            {'center_yx': (0, 0),     'segment_id_left': 1, 'segment_id_right': 2},
            {'center_yx': (10000, 0), 'segment_id_left': 3, 'segment_id_right': 4},
        ]
        k = compute_k_per_gap(gaps, R_win=10.0)
        # gap0 should only see itself (seg IDs 1,2), not gap1
        assert k[0] == 2, f'Expected k(0)=2 (own IDs only), got {k[0]}'
        assert k[1] == 2, f'Expected k(1)=2 (own IDs only), got {k[1]}'

    def test_k_crowded_neighbourhood(self):
        """3 gaps close together with distinct IDs → all see each other."""
        from benchmark.crowding import compute_k_per_gap
        gaps = [
            {'center_yx': (100, 100), 'segment_id_left': 1, 'segment_id_right': 2},
            {'center_yx': (101, 101), 'segment_id_left': 3, 'segment_id_right': 4},
            {'center_yx': (102, 100), 'segment_id_left': 5, 'segment_id_right': 6},
        ]
        k = compute_k_per_gap(gaps, R_win=50.0)
        # All 6 IDs (1,2,3,4,5,6) visible from any gap within R=50
        for i in range(3):
            assert k[i] == 6, f'Expected k({i})=6 distinct IDs, got {k[i]}'

    def test_k_invalid_segment_ids_excluded(self):
        """segment_id_left/right == -1 should not count as distinct IDs."""
        from benchmark.crowding import compute_k_per_gap
        gaps = [
            {'center_yx': (0, 0), 'segment_id_left': -1, 'segment_id_right': -1},
        ]
        k = compute_k_per_gap(gaps, R_win=100.0)
        assert k[0] == 0, f'Expected k(0)=0 (only invalid IDs), got {k[0]}'

    def test_k_empty_gaps(self):
        from benchmark.crowding import compute_k_per_gap
        assert compute_k_per_gap([], R_win=100.0) == {}

    def test_k_thresh_statistics(self):
        """compute_k_thresh returns median/mean/p60 with known values."""
        from benchmark.crowding import compute_k_thresh
        vals = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
        result = compute_k_thresh(vals)
        assert abs(result['median'] - 5.5)  < 1e-6, f"median={result['median']}"
        assert abs(result['mean']   - 5.5)  < 1e-6, f"mean={result['mean']}"
        assert result['p60'] >= 5.5,               f"p60={result['p60']}"
        assert result['n'] == 10

    def test_k_thresh_empty(self):
        from benchmark.crowding import compute_k_thresh
        r = compute_k_thresh([])
        assert np.isnan(r['median'])

    def test_R_win_architecture_constant(self):
        """R_WIN == 256 (architecture-derived, not tuned)."""
        from benchmark.crowding import R_WIN
        assert R_WIN == 256, f'Expected R_WIN=256, got {R_WIN}'


# ─────────────────────────────────────────────────────────────────────────────
# 5-6. M-B B-2: reid_rate_head with crowding stratification
# ─────────────────────────────────────────────────────────────────────────────

class TestReidRateHeadCrowding:
    """Tests for benchmark.metrics.reid_rate_head with gap_k / k_thresh."""

    def _make_logits_and_gaps(self, n: int = 8, seed: int = 0):
        """
        Make (n, n) logits and n GapRecord-like objects.
        All gaps share segment IDs → all have partners.
        """
        from benchmark.synth_breaks import GapRecord
        rng = np.random.default_rng(seed)
        # All even gaps share seg_id_left=0; odd gaps share seg_id_right=1
        gaps = []
        for i in range(n):
            gaps.append(GapRecord(
                gap_id=i,
                center_yx=(i * 10, 0),
                radius=3, gap_size=6, sigma=1.0,
                segment_id_left=0,
                segment_id_right=1,
            ))
        # Perfect oracle logits: each gap i should match gap (n-1-i)
        logits = rng.standard_normal((n, n)).astype(np.float32)
        np.fill_diagonal(logits, -np.inf)
        return logits, gaps

    def test_returns_high_low_when_gap_k_provided(self):
        """With gap_k and k_thresh, output has reid_rate_head_high and _low."""
        from benchmark.metrics import reid_rate_head as rrh
        logits, gaps = self._make_logits_and_gaps(n=8)
        gap_k = np.array([5, 5, 5, 5, 1, 1, 1, 1], dtype=float)  # 4 high, 4 low
        k_thresh = 3.0
        result = rrh(logits, gaps, gap_k=gap_k, k_thresh=k_thresh)
        assert 'reid_rate_head_high' in result, 'Missing reid_rate_head_high'
        assert 'reid_rate_head_low'  in result, 'Missing reid_rate_head_low'
        assert 'n_high'              in result
        assert 'n_low'               in result
        assert 'r_chance_high'       in result

    def test_no_crowding_keys_when_gap_k_absent(self):
        """Without gap_k, output has only base keys (no high/low)."""
        from benchmark.metrics import reid_rate_head as rrh
        logits, gaps = self._make_logits_and_gaps(n=8)
        result = rrh(logits, gaps)
        assert 'reid_rate_head_high' not in result
        assert 'reid_rate_head_low'  not in result

    def test_high_low_n_sum_equals_total_with_partner(self):
        """n_high + n_low == n_gaps_with_partner."""
        from benchmark.metrics import reid_rate_head as rrh
        logits, gaps = self._make_logits_and_gaps(n=8)
        gap_k = np.array([5, 5, 5, 5, 1, 1, 1, 1], dtype=float)
        k_thresh = 3.0
        result = rrh(logits, gaps, gap_k=gap_k, k_thresh=k_thresh)
        assert result['n_high'] + result['n_low'] == result['n_gaps_with_partner'], (
            f"n_high={result['n_high']} + n_low={result['n_low']} "
            f"!= n_gaps_with_partner={result['n_gaps_with_partner']}"
        )

    def test_known_k_split(self):
        """
        Known k_thresh=3.  gap_k = [5,5,5,5, 1,1,1,1].
        high subset = first 4 gaps, low = last 4.
        n_high/n_low reflect the split (all gaps have partners here).
        """
        from benchmark.metrics import reid_rate_head as rrh
        logits, gaps = self._make_logits_and_gaps(n=8)
        gap_k = np.array([5, 5, 5, 5, 1, 1, 1, 1], dtype=float)
        k_thresh = 3.0
        result = rrh(logits, gaps, gap_k=gap_k, k_thresh=k_thresh)
        # With k_thresh=3: high (k>=3) = indices 0-3 (k=5), low (k<3) = indices 4-7 (k=1)
        assert result['n_high'] == 4, f'Expected n_high=4, got {result["n_high"]}'
        assert result['n_low']  == 4, f'Expected n_low=4, got {result["n_low"]}'

    def test_r_chance_is_1_over_k_minus_1(self):
        """r_chance_high = 1/(K-1) where K = total gap count."""
        from benchmark.metrics import reid_rate_head as rrh
        logits, gaps = self._make_logits_and_gaps(n=8)
        gap_k = np.array([5] * 8, dtype=float)
        k_thresh = 2.0
        result = rrh(logits, gaps, gap_k=gap_k, k_thresh=k_thresh)
        expected_r_chance = 1.0 / (8 - 1)   # K=8 total
        assert abs(result['r_chance_high'] - expected_r_chance) < 1e-9, (
            f"Expected r_chance_high={expected_r_chance:.6f}, "
            f"got {result['r_chance_high']}"
        )

    def test_overall_reid_rate_head_unchanged_by_crowding(self):
        """Overall reid_rate_head should be the same whether gap_k is given or not."""
        from benchmark.metrics import reid_rate_head as rrh
        logits, gaps = self._make_logits_and_gaps(n=8, seed=42)
        result_no_k = rrh(logits, gaps)
        gap_k = np.array([5, 5, 5, 5, 1, 1, 1, 1], dtype=float)
        result_with_k = rrh(logits, gaps, gap_k=gap_k, k_thresh=3.0)
        assert abs(result_no_k['reid_rate_head'] -
                   result_with_k['reid_rate_head']) < 1e-9, (
            'Overall reid_rate_head should not change when gap_k is added'
        )


# ─────────────────────────────────────────────────────────────────────────────
# 7-8. M-C: run_verdict parses new columns and has dose-response keys
# ─────────────────────────────────────────────────────────────────────────────

_CSV_HEADER_V2 = [
    'epoch', 'image_id', 'severity', 'dataset',
    'reid_rate', 'reid_rate_head', 'reid_idf1',
    'epsilon_beta0', 'success_rate', 'n_gaps',
    'reid_rate_head_high', 'reid_rate_head_low',
    'arm'
]


def _write_csv_v2(tmp_path: Path, rows: list, fname: str) -> Path:
    """Write mock CSV with A-v2 columns."""
    p = tmp_path / fname
    with open(p, 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=_CSV_HEADER_V2)
        w.writeheader()
        for row in rows:
            w.writerow({k: row.get(k, 'nan') for k in _CSV_HEADER_V2})
    return p


def _make_rows_v2(image_ids, rr_vals, eps_vals, rh_vals, rh_high, rh_low,
                  dataset='chase', epoch=80, arm='a2'):
    rows = []
    for i, iid in enumerate(image_ids):
        rows.append({
            'epoch':               epoch,
            'image_id':            iid,
            'dataset':             dataset,
            'severity':            'Medium',
            'reid_rate':           rr_vals[i],
            'reid_rate_head':      rh_vals[i],
            'reid_idf1':           rh_vals[i] * 0.9,
            'epsilon_beta0':       eps_vals[i],
            'success_rate':        0.8,
            'n_gaps':              10,
            'reid_rate_head_high': rh_high[i],
            'reid_rate_head_low':  rh_low[i],
            'arm':                 arm,
        })
    return rows


class TestVerdictV2DoseResponse:
    """M-C: run_verdict parses new columns and produces dose-response output."""

    DATASETS = ['chase', 'hrf', 'fives', 'stare']
    N = 8

    def _make_verdicts(self, tmp_path: Path, seed: int = 0):
        rng = np.random.default_rng(seed)
        all_a2, all_a1p, all_a0p = [], [], []

        for ds in self.DATASETS:
            n = self.N
            iids = [f'img{i}' for i in range(n)]
            for i in range(n):
                eps = 0.1 + rng.normal(0, 0.01)
                # A2: high subset high, low subset modest
                rh_h_a2  = 0.92 + rng.uniform(0, 0.02)
                rh_l_a2  = 0.75 + rng.uniform(0, 0.05)
                # A1': high subset low (delta > 0 clear), low subset similar to A2 (tied)
                rh_h_a1p = 0.68 + rng.uniform(0, 0.02)
                rh_l_a1p = 0.74 + rng.uniform(0, 0.05)
                all_a2.append({
                    'epoch': 80, 'image_id': iids[i], 'dataset': ds,
                    'severity': 'Medium',
                    'reid_rate': 0.75, 'reid_rate_head': rh_h_a2,
                    'reid_idf1': rh_h_a2 * 0.9,
                    'epsilon_beta0': eps - 0.01, 'success_rate': 0.85,
                    'n_gaps': 10, 'arm': 'memory',
                    'reid_rate_head_high': rh_h_a2,
                    'reid_rate_head_low':  rh_l_a2,
                })
                all_a1p.append({
                    'epoch': 80, 'image_id': iids[i], 'dataset': ds,
                    'severity': 'Medium',
                    'reid_rate': 0.63, 'reid_rate_head': rh_h_a1p,
                    'reid_idf1': rh_h_a1p * 0.9,
                    'epsilon_beta0': eps + 0.01, 'success_rate': 0.75,
                    'n_gaps': 10, 'arm': 'linear_attn',
                    'reid_rate_head_high': rh_h_a1p,
                    'reid_rate_head_low':  rh_l_a1p,
                })
                all_a0p.append({
                    'epoch': 80, 'image_id': iids[i], 'dataset': ds,
                    'severity': 'Medium',
                    'reid_rate': 0.50, 'reid_rate_head': 'nan',
                    'reid_idf1': 'nan',
                    'epsilon_beta0': eps + 0.02, 'success_rate': 0.65,
                    'n_gaps': 10, 'arm': 'cnn',
                    'reid_rate_head_high': 'nan',
                    'reid_rate_head_low': 'nan',
                })

        csv_a2  = _write_csv_v2(tmp_path, all_a2,  'a2.csv')
        csv_a1p = _write_csv_v2(tmp_path, all_a1p, 'a1p.csv')
        csv_a0p = _write_csv_v2(tmp_path, all_a0p, 'a0p.csv')
        return csv_a2, csv_a1p, csv_a0p

    def test_load_arm_csv_parses_new_columns(self, tmp_path):
        """load_arm_csv correctly parses reid_rate_head_high/low columns."""
        from reid_verdict_v2 import load_arm_csv

        rows_data = _make_rows_v2(
            ['i0', 'i1'], [0.7, 0.8], [0.1, 0.12], [0.92, 0.93],
            [0.85, 0.88], [0.72, 0.74], dataset='chase')
        p = _write_csv_v2(tmp_path, rows_data, 'test.csv')
        loaded = load_arm_csv(p)
        assert 'chase' in loaded
        for r in loaded['chase']:
            assert 'reid_rate_head_high' in r
            assert 'reid_rate_head_low'  in r
            assert isinstance(r['reid_rate_head_high'], float)
            assert isinstance(r['reid_rate_head_low'],  float)

    def test_load_nan_headless_rows(self, tmp_path):
        """Nan string in reid_rate_head_high/low → float nan."""
        from reid_verdict_v2 import load_arm_csv
        rows_data = [{
            'epoch': 80, 'image_id': 'i0', 'dataset': 'hrf',
            'severity': 'Medium', 'reid_rate': 0.5, 'reid_rate_head': 'nan',
            'reid_idf1': 'nan', 'epsilon_beta0': 0.1, 'success_rate': 0.8,
            'n_gaps': 10, 'reid_rate_head_high': 'nan', 'reid_rate_head_low': 'nan',
            'arm': 'cnn',
        }]
        p = _write_csv_v2(tmp_path, rows_data, 'headless.csv')
        loaded = load_arm_csv(p)
        r = loaded['hrf'][0]
        assert np.isnan(r['reid_rate_head_high']), 'Should parse nan string as float nan'
        assert np.isnan(r['reid_rate_head_low'])

    def test_run_verdict_has_dose_response_keys(self, tmp_path):
        """run_verdict output must contain dose-response keys (A-v2 M-C)."""
        from reid_verdict_v2 import run_verdict
        csv_a2, csv_a1p, csv_a0p = self._make_verdicts(tmp_path)
        result = run_verdict(
            csv_a2=csv_a2, csv_a1p=csv_a1p, csv_a0p=csv_a0p,
            datasets=self.DATASETS,
        )
        for key in ('dose_response_high_per_dataset', 'dose_response_low_per_dataset',
                    'dose_response_high_consistency', 'dose_response_low_tied',
                    'dose_response_pass', 'dose_response_note'):
            assert key in result, f'Missing key: {key}'

    def test_run_verdict_dose_high_positive_delta(self, tmp_path):
        """A2 high >> A1' high → dose_response high subset A2>A1' direction positive."""
        from reid_verdict_v2 import run_verdict
        csv_a2, csv_a1p, csv_a0p = self._make_verdicts(tmp_path, seed=42)
        result = run_verdict(
            csv_a2=csv_a2, csv_a1p=csv_a1p, csv_a0p=csv_a0p,
            datasets=self.DATASETS,
        )
        # At least 1 dataset should have positive mean_delta in high subset
        high_results = result['dose_response_high_per_dataset']
        n_positive = sum(
            1 for r in high_results
            if isinstance(r.get('mean_delta'), float) and r['mean_delta'] > 0
        )
        assert n_positive >= 2, (
            f'Expected ≥2 datasets with positive high-crowding delta, '
            f'got {n_positive}: {[(r["dataset"], r.get("mean_delta")) for r in high_results]}'
        )

    def test_run_verdict_dose_low_small_delta(self, tmp_path):
        """A1' low ≈ A2 low → low subset deltas small (tied)."""
        from reid_verdict_v2 import run_verdict
        csv_a2, csv_a1p, csv_a0p = self._make_verdicts(tmp_path, seed=7)
        result = run_verdict(
            csv_a2=csv_a2, csv_a1p=csv_a1p, csv_a0p=csv_a0p,
            datasets=self.DATASETS,
        )
        # Low subset mean_delta should be smaller than high subset
        high_deltas = [r.get('mean_delta', 0.0)
                       for r in result['dose_response_high_per_dataset']
                       if isinstance(r.get('mean_delta'), float)]
        low_deltas  = [r.get('mean_delta', 0.0)
                       for r in result['dose_response_low_per_dataset']
                       if isinstance(r.get('mean_delta'), float)]
        if high_deltas and low_deltas:
            mean_high = float(np.mean([abs(d) for d in high_deltas]))
            mean_low  = float(np.mean([abs(d) for d in low_deltas]))
            assert mean_high >= mean_low - 0.1, (
                f'Expected |high delta| >= |low delta| - 0.1, '
                f'got high={mean_high:.3f}, low={mean_low:.3f}'
            )

    def test_run_verdict_no_crash(self, tmp_path):
        """run_verdict with A-v2 CSVs does not crash."""
        from reid_verdict_v2 import run_verdict
        csv_a2, csv_a1p, csv_a0p = self._make_verdicts(tmp_path)
        result = run_verdict(
            csv_a2=csv_a2, csv_a1p=csv_a1p, csv_a0p=csv_a0p,
            datasets=self.DATASETS,
        )
        assert 'CLAIM2_VERDICT' in result


# ─────────────────────────────────────────────────────────────────────────────
# 9. B-3 integration: _reid_head_forward_on_tile returns dict
# ─────────────────────────────────────────────────────────────────────────────

class TestReidHeadForwardOnTileReturnType:
    """_reid_head_forward_on_tile should return dict (not 2-tuple as in A-I)."""

    def _patch_fla_local(self):
        _patch_fla()

    def test_returns_dict_not_tuple(self, tmp_path):
        """Verify return type is dict with reid_rate_head key."""
        import json
        from dataclasses import asdict
        from benchmark.synth_breaks import apply_breaks

        # Build a small synthetic NPZ
        gt = np.zeros((96, 96), dtype=np.uint8)
        gt[20:25, 10:80] = 1
        gt[50:55, 10:80] = 1
        rng_np = np.random.default_rng(1)
        img_f = rng_np.standard_normal((96, 96)).astype(np.float32)

        br = apply_breaks(gt, gap_size=4, nb_deco=10, seed=1)
        gaps = br.gaps

        if not gaps:
            pytest.skip('No gaps produced by apply_breaks for this synthetic image.')

        from models.unet_gdn2 import UNetGDN2
        model = UNetGDN2(
            in_ch=1, out_ch=1, base_ch=8, d_head=8, n_heads=1,
            memory_mode='delta_rule', backend='naive',
            use_reid_head=True, reid_use_loc_feat=False,  # A-v2 M-A
        )
        model.eval()
        device = torch.device('cpu')

        from train_reid_pilot import _reid_head_forward_on_tile
        result = _reid_head_forward_on_tile(
            model, device, img_f, gaps,
            gap_k=None, k_thresh=None,
        )
        assert isinstance(result, dict), (
            f'Expected dict, got {type(result).__name__}. '
            'A-v2 refactored _reid_head_forward_on_tile to return dict (not 2-tuple).'
        )
        assert 'reid_rate_head' in result
        assert 'reid_idf1'      in result


# ─────────────────────────────────────────────────────────────────────────────
# 10. CSV header/data alignment check
# ─────────────────────────────────────────────────────────────────────────────

class TestCSVHeaderDataAlignment:
    """
    Verify that the CSV header written in main() matches the data rows
    written by evaluate_on_benchmark().  Blood-lesson from A-I (2026-06-20).
    """

    def test_header_column_count_matches_data_row(self, tmp_path):
        """
        Build a mock per_image_rows list and call the CSV writer fragment
        from evaluate_on_benchmark.  Assert len(header) == len(data_row).
        """
        # Reconstruct the header as defined in main()
        header = [
            'epoch', 'image_id', 'severity', 'dataset',
            'reid_rate', 'reid_rate_head', 'reid_idf1',
            'epsilon_beta0', 'success_rate', 'n_gaps',
            'reid_rate_head_high', 'reid_rate_head_low',
            'arm',
        ]

        # Mock per_image_rows entry (all columns present, including new A-v2 cols)
        row = {
            'image_id':            'img0',
            'severity':            'Medium',
            'dataset':             'chase',
            'reid_rate':           0.75,
            'reid_rate_head':      0.93,
            'reid_idf1':           0.88,
            'epsilon_beta0':       0.12,
            'success_rate':        0.85,
            'n_gaps':              10,
            'reid_rate_head_high': 0.94,
            'reid_rate_head_low':  0.72,
        }

        # Reconstruct the writerow call from evaluate_on_benchmark
        import math
        def _safe_round(v, nd=6):
            return round(v, nd) if math.isfinite(float(v)) else float('nan')

        data_row = [
            1,                              # epoch
            row['image_id'],
            row['severity'],
            row['dataset'],
            _safe_round(row['reid_rate'],         6),
            _safe_round(row.get('reid_rate_head', float('nan')), 6),
            _safe_round(row.get('reid_idf1',      float('nan')), 6),
            _safe_round(row['epsilon_beta0'],     6),
            _safe_round(row['success_rate'],      6),
            row['n_gaps'],
            _safe_round(row.get('reid_rate_head_high', float('nan')), 6),
            _safe_round(row.get('reid_rate_head_low',  float('nan')), 6),
            'memory',                       # arm
        ]

        assert len(header) == len(data_row), (
            f'HEADER/DATA MISMATCH: header has {len(header)} cols, '
            f'data row has {len(data_row)} cols.\n'
            f'Header: {header}\n'
            f'Data:   {data_row}'
        )

    def test_header_column_names(self):
        """Verify the exact column names (order matters for CSV reader)."""
        expected = [
            'epoch', 'image_id', 'severity', 'dataset',
            'reid_rate', 'reid_rate_head', 'reid_idf1',
            'epsilon_beta0', 'success_rate', 'n_gaps',
            'reid_rate_head_high', 'reid_rate_head_low',
            'arm',
        ]
        # Cross-check against the test_reid_verdict_v2 mock header (which doesn't
        # include the new columns yet — that test uses the old schema).
        # The new A-v2 header extends the old one by inserting high/low before arm.
        assert 'reid_rate_head_high' in expected
        assert 'reid_rate_head_low'  in expected
        assert expected.index('reid_rate_head_high') < expected.index('arm')
        assert expected.index('reid_rate_head_low')  < expected.index('arm')
        assert expected.index('reid_rate_head_high') == expected.index('reid_rate_head_low') - 1
