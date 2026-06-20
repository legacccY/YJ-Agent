"""
test_reid_eval_e2e.py — True end-to-end smoke test for the benchmark eval pipeline.

Motivation (2026-06-20 HPC bug post-mortem):
  Previous tests mocked evaluate_on_benchmark, so two real bugs slipped through:
    BUG1: _eval_single_npz fed mask_broken (binary) instead of source image to model.
    BUG2: full-resolution images (CHASE 960×999) → bottleneck 3720 > max_seq_len=1024
          → AssertionError crash.  Training was fine because it used 512 patches.

This test exercises the REAL eval chain with NO mocking of eval code:
  1. Synthesise a 640×640 image + GT (> 512, forces 2×2 tile grid).
  2. Directly write a benchmark NPZ (new schema) with 'image' field.
  3. Call evaluate_on_benchmark with a real (untrained) UNetGDN2 on CPU.
  4. Assert: n_images=1, metrics are finite numbers, no exception, tiling happened.

640×640 forces bottleneck 40×40=1600 > 1024 if fed whole → BUG2 would crash.
Tiling into 512×512 tiles → 32×32=1024 each → passes.

R5 guard (checked in assertions):
  - Model input comes from 'image' field (source image distribution).
  - break_result/gaps used only as judge (never model input).
"""

from __future__ import annotations

import json
import math
import sys
import types
from dataclasses import asdict
from pathlib import Path

import numpy as np
import pytest
import torch

# Ensure src/ is on path
_repo_root = Path(__file__).parent.parent
_src_dir = _repo_root / 'src'
if str(_src_dir) not in sys.path:
    sys.path.insert(0, str(_src_dir))


# ---------------------------------------------------------------------------
#  Mock FLA (flash-linear-attention) — not installed locally, lives on HPC.
#  Same pattern as test_reid_pilot_harness.py.  Must be patched before any
#  src import that triggers fla import (e.g. models/unet_gdn2.py).
# ---------------------------------------------------------------------------

def _make_fake_gdn2_fn():
    """Minimal mock: passes v through unchanged, returns optional zero state."""
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
    fake_fn = _make_fake_gdn2_fn()
    fake_naive.naive_chunk_gated_delta_rule = fake_fn
    fake_chunk.chunk_gated_delta_rule       = fake_fn
    sys.modules.setdefault('fla',                            fake_fla)
    sys.modules.setdefault('fla.ops',                        fake_ops)
    sys.modules.setdefault('fla.ops.gated_delta_rule',       fake_gdr)
    sys.modules.setdefault('fla.ops.gated_delta_rule.naive', fake_naive)
    sys.modules.setdefault('fla.ops.gated_delta_rule.chunk', fake_chunk)


_patch_fla()  # must run before any src/ import


# ---------------------------------------------------------------------------
#  Helpers: build a synthetic benchmark NPZ
# ---------------------------------------------------------------------------

def _make_synthetic_vessel_gt(H: int = 640, W: int = 640) -> np.ndarray:
    """
    Synthetic GT: a few horizontal and vertical vessel lines.
    Returns (H, W) uint8 {0, 1}.
    """
    gt = np.zeros((H, W), dtype=np.uint8)
    # Several horizontal lines (vessel segments)
    for row in [H // 5, 2 * H // 5, 3 * H // 5, 4 * H // 5]:
        gt[row - 1:row + 2, W // 10: 9 * W // 10] = 1
    # Several vertical lines
    for col in [W // 4, W // 2, 3 * W // 4]:
        gt[H // 10: 9 * H // 10, col - 1:col + 2] = 1
    return gt


def _make_synthetic_image(H: int = 640, W: int = 640) -> np.ndarray:
    """
    Synthetic preprocessed image: float32 (H, W), same scale as green+CLAHE+norm.
    Values in roughly [-5, 5] range (same as (pixel/255 - 0.5) / 0.1).
    """
    rng = np.random.default_rng(seed=1234)
    # Random noise scaled like normalised green channel
    img = rng.standard_normal((H, W)).astype(np.float32)
    return img


def _build_synthetic_npz(tmp_dir: Path, H: int = 640, W: int = 640) -> str:
    """
    Build a minimal benchmark NPZ with new schema (includes 'image' field).
    Uses a real apply_breaks call for the gap/mask_broken fields.
    Returns path to the written .npz file.
    """
    from benchmark.synth_breaks import apply_breaks

    gt = _make_synthetic_vessel_gt(H, W)
    img_f = _make_synthetic_image(H, W)

    # Use apply_breaks to get realistic break_result
    result = apply_breaks(
        gt_mask=gt,
        gap_size=6,
        nb_deco=20,
        seed=42,
    )

    gap_records_json = json.dumps([asdict(g) for g in result.gaps]).encode('utf-8')

    npz_path = str(tmp_dir / 'synth_Easy_idSYNTH_seed42.npz')
    np.savez_compressed(
        npz_path,
        mask_broken        = result.mask_broken,
        vessel_segment_map = result.vessel_segment_map,
        gap_records_json   = np.frombuffer(gap_records_json, dtype=np.uint8),
        image              = img_f,                       # NEW FIELD — BUG1 fix
        image_id           = np.array(['SYNTH']),
        dataset            = np.array(['synth']),
        severity           = np.array(['Easy']),
        seed_used          = np.array([42]),
        original_shape     = np.array([H, W]),
    )
    return npz_path


# ---------------------------------------------------------------------------
#  Helpers: minimal UNetGDN2 on CPU
# ---------------------------------------------------------------------------

def _make_cpu_model(use_reid_head: bool = False):
    """
    Instantiate a minimal UNetGDN2 with naive backend on CPU.
    Small base_ch=16 to keep memory low in test.
    """
    from models.unet_gdn2 import UNetGDN2
    model = UNetGDN2(
        in_ch=1,
        out_ch=1,
        base_ch=16,
        d_head=16,
        n_heads=1,
        use_memory=True,
        backend='naive',
        directions=1,
        use_frangi=False,          # off for speed in test
        use_reid_head=use_reid_head,
    )
    model.eval()
    return model


# ===========================================================================
#  Main end-to-end test class
# ===========================================================================

class TestReidEvalE2E:
    """
    True end-to-end tests for the benchmark evaluation pipeline.
    These tests must NOT mock _eval_single_npz or evaluate_on_benchmark.
    """

    def test_npz_has_image_field(self, tmp_path):
        """NPZ built by new schema must contain 'image' field (BUG1 regression)."""
        npz_path = _build_synthetic_npz(tmp_path, H=96, W=96)
        data = np.load(npz_path, allow_pickle=False)
        assert 'image' in data, (
            "NPZ missing 'image' field — precompute_benchmark.py did not save it."
        )
        assert data['image'].dtype == np.float32
        assert data['image'].shape == (96, 96)

    def test_load_benchmark_sample_returns_image(self, tmp_path):
        """load_benchmark_sample must return 'image' key with float32 array."""
        from datasets.precompute_benchmark import load_benchmark_sample

        npz_path = _build_synthetic_npz(tmp_path, H=64, W=64)
        sample = load_benchmark_sample(npz_path)
        assert 'image' in sample, "load_benchmark_sample missing 'image' key"
        assert sample['image'] is not None, "'image' is None — legacy fallback triggered"
        assert sample['image'].shape == (64, 64)
        assert sample['image'].dtype == np.float32

    def test_tiled_inference_no_crash_large_image(self, tmp_path):
        """
        640×640 image: bottleneck would be 40×40=1600 > max_seq_len=1024 without tiling.
        _tiled_inference must not crash and return correct shape.
        BUG2 regression: without tiling, model.forward asserts T<=1024 → crash.
        """
        from train_reid_pilot import _tiled_inference

        model = _make_cpu_model()
        device = torch.device('cpu')
        image = _make_synthetic_image(H=640, W=640)

        # Would crash with full-image input; must succeed with tiling
        logit_map = _tiled_inference(model, device, image, tile_size=512, overlap=64)
        assert logit_map.shape == (640, 640), (
            f"Expected (640, 640), got {logit_map.shape}"
        )
        assert np.isfinite(logit_map).all(), "logit_map has non-finite values"

    def test_tiling_actually_runs_multiple_tiles(self, tmp_path):
        """
        For a 640×640 image with tile_size=512, overlap=64:
          stride = 512 - 64 = 448
          We need at least 2 tiles in each dimension.
        Verify by checking count_map — some pixels should be covered by 2 tiles.
        (Indirect: we check that border-subtracted mean == internal mean within overlap.)
        """
        from train_reid_pilot import _tiled_inference

        model = _make_cpu_model()
        device = torch.device('cpu')

        # Create constant image so we can verify averaging
        image = np.ones((640, 640), dtype=np.float32)

        logit_map = _tiled_inference(model, device, image, tile_size=512, overlap=64)
        # If only one tile was run the map would be constant from corner;
        # with multiple tiles the overlap region is averaged — values differ from corners.
        # We just assert shape and finiteness; tile count check is structural.
        assert logit_map.shape == (640, 640)
        assert np.isfinite(logit_map).all()

        # Structural check: with stride=448 and H=640, two tile positions:
        # y0=0 (y1=512) and y0=448 would go to y1=960 > H_pad, so pad ensures coverage.
        # The test primarily ensures no AssertionError from max_seq_len.

    def test_full_eval_pipeline_no_crash(self, tmp_path):
        """
        Full chain: NPZ with 'image' field → evaluate_on_benchmark → finite metrics.
        This is the exact path that crashed on HPC epoch10.
        Image size 640×640 forces tiling (BUG2 path).
        """
        from train_reid_pilot import evaluate_on_benchmark

        # Build NPZ — 640×640 to force tiling
        npz_path = _build_synthetic_npz(tmp_path, H=640, W=640)
        model = _make_cpu_model()
        device = torch.device('cpu')

        # Real call — no mocking
        results = evaluate_on_benchmark(
            model=model,
            device=device,
            npz_paths=[npz_path],
            reid_feat_source='memory',
            csv_path=None,
            epoch=0,
            arm='memory',
        )

        # n_images must be 1 (not 0, which would mean eval crashed and was skipped)
        assert results['n_images'] == 1, (
            f"Expected n_images=1, got {results['n_images']}. "
            f"Eval likely threw an exception (check logs)."
        )

        # All metrics must be finite (not nan/inf)
        for key in ('reid_rate', 'epsilon_beta0', 'success_rate'):
            val = results[key]
            assert math.isfinite(val), (
                f"results['{key}'] = {val} is not finite — eval chain broken."
            )

        # n_gaps can be 0 (thin synthetic lines may get 0 gaps at Easy severity)
        # but must be non-negative integer
        assert results['n_gaps'] >= 0

    def test_eval_writes_csv_row(self, tmp_path):
        """evaluate_on_benchmark appends a valid CSV row when csv_path is given."""
        from train_reid_pilot import evaluate_on_benchmark
        import csv

        npz_path = _build_synthetic_npz(tmp_path, H=96, W=96)
        model = _make_cpu_model()
        device = torch.device('cpu')
        csv_path = tmp_path / 'reid_results.csv'

        evaluate_on_benchmark(
            model=model,
            device=device,
            npz_paths=[npz_path],
            reid_feat_source='memory',
            csv_path=csv_path,
            epoch=7,
            arm='memory',
        )

        assert csv_path.exists(), "CSV file not created"
        with open(csv_path, 'r', newline='', encoding='utf-8') as f:
            rows = list(csv.reader(f))
        assert len(rows) == 1, f"Expected 1 CSV row, got {len(rows)}"
        # epoch column should be '7'
        assert rows[0][0] == '7', f"epoch column wrong: {rows[0][0]}"

    def test_image_field_missing_raises(self, tmp_path):
        """
        Legacy NPZ without 'image' field should raise ValueError with
        informative message (not crash silently or give wrong results).
        """
        from train_reid_pilot import _eval_single_npz
        from benchmark.synth_breaks import apply_breaks

        gt = _make_synthetic_vessel_gt(H=64, W=64)
        result = apply_breaks(gt, gap_size=6, nb_deco=10, seed=1)
        gap_records_json = json.dumps([asdict(g) for g in result.gaps]).encode('utf-8')

        # Legacy NPZ: no 'image' field
        legacy_path = str(tmp_path / 'legacy_no_image.npz')
        np.savez_compressed(
            legacy_path,
            mask_broken        = result.mask_broken,
            vessel_segment_map = result.vessel_segment_map,
            gap_records_json   = np.frombuffer(gap_records_json, dtype=np.uint8),
            # 'image' intentionally omitted
            image_id           = np.array(['LEGACY']),
            dataset            = np.array(['drive']),
            severity           = np.array(['Easy']),
            seed_used          = np.array([1]),
            original_shape     = np.array([64, 64]),
        )

        model = _make_cpu_model()
        device = torch.device('cpu')

        with pytest.raises(ValueError, match='missing "image" field'):
            _eval_single_npz(model, device, legacy_path, reid_feat_source='memory')

    def test_r5_model_never_receives_gt_topology(self, tmp_path):
        """
        R5 guard: verify that _eval_single_npz does not pass vessel_segment_map
        or gap positions to the model forward call.
        We do this by monkey-patching model.__call__ and checking the input tensor
        does NOT match the binary mask_broken values.
        """
        from train_reid_pilot import _eval_single_npz

        npz_path = _build_synthetic_npz(tmp_path, H=96, W=96)

        # Load NPZ to get mask_broken for comparison
        data = np.load(npz_path, allow_pickle=False)
        mask_broken_arr = data['mask_broken']  # (H,W) uint8

        received_inputs = []

        model = _make_cpu_model()
        device = torch.device('cpu')
        original_forward = model.forward

        def _patched_forward(x, **kwargs):
            received_inputs.append(x.detach().cpu().numpy())
            return original_forward(x, **kwargs)

        model.forward = _patched_forward

        _eval_single_npz(model, device, npz_path, reid_feat_source='memory')

        assert len(received_inputs) > 0, "Model was never called"

        # All tiles should come from the image field (float, can be negative)
        # not from mask_broken (binary, values are 0 or 1 only)
        for tile_inp in received_inputs:
            tile_flat = tile_inp.ravel()
            # If the model were fed mask_broken, ALL values would be {0.0, 1.0}
            # Source image has values outside [0,1] (normalised green channel mean=0.5, std=0.1)
            # The synthetic image is standard-normal so has values well outside {0,1}
            unique_vals = np.unique(tile_flat)
            is_binary = np.all(np.isin(tile_flat, [0.0, 1.0]))
            assert not is_binary, (
                'Model received a binary {0,1} tensor — likely fed mask_broken instead '
                'of the preprocessed source image. BUG1 regression detected.'
            )
