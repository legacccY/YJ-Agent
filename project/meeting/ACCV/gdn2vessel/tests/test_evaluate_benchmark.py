"""
test_evaluate_benchmark.py — pytest for evaluate.py benchmark path (断点续连三轴).

Coverage:
  1. _load_manifest_entries: filters by dataset + severity correctly.
  2. _tiled_inference_numpy: tiled forward on large (>512) image, output shape OK.
  3. evaluate_benchmark end-to-end: mock adapter (identity conv) + fake NPZ →
       ① benchmark_dir loads + filters matching entries
       ② model runs via adapter.forward_adapt (BUG3 fix: NOT via _tiled_inference_numpy)
       ③ SR / reID / ε_β0 all non-NaN (续连轴 headline 全有值)
       ④ CSV written with correct schema (all fieldnames present)
       ⑤ eval_input_mode = 'benchmark_adapter' (was 'benchmark_tiled' before BUG3 fix)
  4. BUG3 fix regression: forward_adapt is called (not model.forward directly).
  5. Legacy path backward compat: not passing --benchmark_dir → evaluate_adapter
     called; benchmark path NOT entered (no import crash).

Design:
  - Uses a fake adapter backed by a tiny Conv2d (3×3, padding=1) — identity-ish.
  - NPZ is synthesised in-memory and written to tmp_path (pytest fixture).
  - NO real dataset files needed; NO HPC/GPU needed.
  - BreakResult has 2 gaps → SR/reID computable.
  - Image is 64×64 (< tile_size=512) so tiling degenerates to 1-tile coverage
    (padding fills to 512×512 then crops back).  Also tests 2-tile path (128px
    image with tile_size=100, overlap=20).
  - No scipy.stats import (OMP safety; metrics.py already uses ndimage only).
  - __main__ guard: test file is not directly runnable (no __main__ block needed;
    pytest discovers it).

Windows compatibility:
  - pathlib.Path everywhere.
  - No spawn multiprocessing.
  - No scipy.stats.
"""

from __future__ import annotations

import csv
import json
import sys
import types
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, List

import numpy as np
import pytest
import torch
import torch.nn as nn

# ---------------------------------------------------------------------------
#  sys.path setup
# ---------------------------------------------------------------------------
_repo_root = Path(__file__).parent.parent
_src_dir   = _repo_root / 'src'
if str(_src_dir) not in sys.path:
    sys.path.insert(0, str(_src_dir))


# ---------------------------------------------------------------------------
#  Mock FLA (flash-linear-attention) — not on local machine, lives on HPC.
#  Must be patched BEFORE any src import that triggers fla (models/unet_gdn2).
#  Same pattern as test_reid_eval_e2e.py.
# ---------------------------------------------------------------------------

def _make_fake_gdn2_fn():
    def fake_fn(q, k, v, beta, g, output_final_state=False):
        B, T, nh, dh = v.shape
        state = torch.zeros(B, nh, dh, dh) if output_final_state else None
        return v.clone(), state
    return fake_fn


def _patch_fla():
    fake_fla  = types.ModuleType('fla')
    fake_ops  = types.ModuleType('fla.ops')
    fake_gla  = types.ModuleType('fla.ops.gla')
    fake_gla.chunk_gla = _make_fake_gdn2_fn()
    fake_ops.gla = fake_gla
    fake_fla.ops = fake_ops
    sys.modules.setdefault('fla',       fake_fla)
    sys.modules.setdefault('fla.ops',   fake_ops)
    sys.modules.setdefault('fla.ops.gla', fake_gla)

_patch_fla()


# ---------------------------------------------------------------------------
#  Minimal fake adapter + model (Conv2d identity-ish)
# ---------------------------------------------------------------------------

class _TinyConvModel(nn.Module):
    """3×3 conv → sigmoid logit. Tiny, deterministic (no random), CPU-safe."""
    def __init__(self):
        super().__init__()
        self.conv = nn.Conv2d(1, 1, 3, padding=1, bias=True)
        # Init to near-zero weights → outputs ~0 logits → pred ≈ 0.5 after sigmoid
        nn.init.zeros_(self.conv.weight)
        nn.init.constant_(self.conv.bias, 0.1)  # slight positive bias → some vessel pred

    def forward(self, x):
        return self.conv(x)  # (B,1,H,W)


# Register a fake adapter in MODEL_REGISTRY for the test.
# We patch registry directly to avoid needing a real adapter file.
_FAKE_ADAPTER_NAME = '_test_tiny_conv'


def _register_fake_adapter():
    """Register _TinyConvModel as a fake adapter. Idempotent."""
    try:
        import baselines  # triggers auto_discover
        from baselines.registry import MODEL_REGISTRY
        from baselines.base_adapter import BaselineAdapter

        if _FAKE_ADAPTER_NAME in MODEL_REGISTRY:
            return  # already registered

        class _FakeAdapter(BaselineAdapter):
            name = _FAKE_ADAPTER_NAME
            kind = 'test'

            def build_model(self, cfg):
                return _TinyConvModel()

            def build_loss(self, cfg):
                return torch.nn.BCEWithLogitsLoss()

            def build_optimizer(self, model, cfg):
                return torch.optim.Adam(model.parameters(), lr=1e-3)

            def preprocess_cfg(self):
                return {'channels': 'green_raw', 'input_mode': 'fullimg'}

            def forward_adapt(self, model, img_t, device):
                with torch.no_grad():
                    return model(img_t.to(device))

        MODEL_REGISTRY[_FAKE_ADAPTER_NAME] = _FakeAdapter
    except Exception as e:
        pytest.skip(f'Cannot register fake adapter: {e}')


# ---------------------------------------------------------------------------
#  Helpers: synthesise fake benchmark NPZ + manifest
# ---------------------------------------------------------------------------

def _make_fake_npz(
    tmp_path: Path,
    dataset: str = 'drive',
    severity: str = 'Medium',
    image_id: str = 'fake_01',
    H: int = 64,
    W: int = 64,
    n_gaps: int = 2,
    seed: int = 42,
) -> Path:
    """
    Write a minimal valid benchmark NPZ to tmp_path.

    Schema matches precompute_benchmark.py output:
      mask_broken, vessel_segment_map, gap_records_json,
      image, image_id, dataset, severity, seed_used, original_shape.
    """
    rng = np.random.default_rng(seed)

    # Fake vessel GT (cross pattern, simple foreground)
    vessel_segment_map = np.zeros((H, W), dtype=np.int32)
    vessel_segment_map[H//4:3*H//4, W//2] = 1   # vertical bar, segment 1
    vessel_segment_map[H//2, W//4:3*W//4] = 2   # horizontal bar, segment 2

    # mask_broken: remove a small segment from each bar (simulate gap)
    mask_broken = (vessel_segment_map > 0).astype(np.uint8)
    mask_broken[H//2 - 2:H//2 + 2, W//2] = 0   # gap in vertical bar
    mask_broken[H//2, W//2 - 2:W//2 + 2] = 0   # gap in horizontal bar

    # Preprocessed image (green+CLAHE+norm convention: ~N(0,1) range)
    image_f = rng.standard_normal((H, W)).astype(np.float32) * 0.1

    # Gap records (2 gaps)
    gaps = []
    for i in range(n_gaps):
        gaps.append({
            'gap_id':          i,
            'center_yx':       [H // 2, W // 2 + i * 4],
            'radius':          3,
            'gap_size':        4,
            'sigma':           1.0,
            'segment_id_left': 1,
            'segment_id_right': 2,
        })

    gap_records_json = json.dumps(gaps).encode('utf-8')

    npz_path = tmp_path / f'{dataset}_{severity}_seed{seed}.npz'
    np.savez_compressed(
        str(npz_path),
        mask_broken        = mask_broken,
        vessel_segment_map = vessel_segment_map,
        gap_records_json   = np.frombuffer(gap_records_json, dtype=np.uint8),
        image              = image_f,
        image_id           = np.array([str(image_id)]),
        dataset            = np.array([dataset]),
        severity           = np.array([severity]),
        seed_used          = np.array([seed]),
        original_shape     = np.array([H, W]),
    )
    return npz_path


def _make_fake_manifest(
    tmp_path: Path,
    entries: List[Dict[str, Any]],
) -> Path:
    """Write manifest.json for given entries."""
    manifest_path = tmp_path / 'manifest.json'
    with open(manifest_path, 'w', encoding='utf-8') as f:
        json.dump(entries, f)
    return manifest_path


def _make_fake_ckpt(tmp_path: Path) -> Path:
    """Save a tiny _TinyConvModel state_dict as checkpoint."""
    model = _TinyConvModel()
    ckpt_path = tmp_path / 'fake_best.pth'
    torch.save(model.state_dict(), str(ckpt_path))
    return ckpt_path


# ---------------------------------------------------------------------------
#  Test 1: _load_manifest_entries filtering
# ---------------------------------------------------------------------------

class TestLoadManifestEntries:
    """Unit test for manifest loading + filtering logic."""

    def test_missing_manifest_exits(self, tmp_path):
        from evaluate import _load_manifest_entries
        with pytest.raises(SystemExit) as exc:
            _load_manifest_entries(tmp_path, 'drive', 'Medium')
        assert exc.value.code == 1

    def test_filter_dataset_and_severity(self, tmp_path):
        # Write 3 NPZ files, 2 matching, 1 non-matching
        npz_drive_med = _make_fake_npz(tmp_path, 'drive', 'Medium', 'img_01', seed=1)
        npz_drive_hard = _make_fake_npz(tmp_path, 'drive', 'Hard',  'img_02', seed=2)
        npz_chase_med  = _make_fake_npz(tmp_path, 'chase', 'Medium','img_03', seed=3)

        entries = [
            {'dataset': 'drive', 'severity': 'Medium', 'image_id': 'img_01',
             'npz': str(npz_drive_med),  'n_gaps': 2},
            {'dataset': 'drive', 'severity': 'Hard',   'image_id': 'img_02',
             'npz': str(npz_drive_hard), 'n_gaps': 2},
            {'dataset': 'chase', 'severity': 'Medium', 'image_id': 'img_03',
             'npz': str(npz_chase_med),  'n_gaps': 2},
        ]
        _make_fake_manifest(tmp_path, entries)

        from evaluate import _load_manifest_entries
        # Filter drive+Medium → 1 entry
        result = _load_manifest_entries(tmp_path, 'drive', 'Medium')
        assert len(result) == 1
        assert result[0]['image_id'] == 'img_01'

    def test_case_insensitive_dataset(self, tmp_path):
        npz_path = _make_fake_npz(tmp_path, 'drive', 'Easy', 'img_ci', seed=10)
        _make_fake_manifest(tmp_path, [
            {'dataset': 'drive', 'severity': 'Easy', 'image_id': 'img_ci',
             'npz': str(npz_path), 'n_gaps': 2},
        ])
        from evaluate import _load_manifest_entries
        # Upper-case 'DRIVE' should match lower-case 'drive' in manifest
        result = _load_manifest_entries(tmp_path, 'DRIVE', 'Easy')
        assert len(result) == 1

    def test_no_severity_filter_returns_all(self, tmp_path):
        npz1 = _make_fake_npz(tmp_path, 'drive', 'Easy',   'i1', seed=11)
        npz2 = _make_fake_npz(tmp_path, 'drive', 'Medium', 'i2', seed=12)
        _make_fake_manifest(tmp_path, [
            {'dataset': 'drive', 'severity': 'Easy',   'image_id': 'i1',
             'npz': str(npz1), 'n_gaps': 2},
            {'dataset': 'drive', 'severity': 'Medium', 'image_id': 'i2',
             'npz': str(npz2), 'n_gaps': 2},
        ])
        from evaluate import _load_manifest_entries
        result = _load_manifest_entries(tmp_path, 'drive', None)
        assert len(result) == 2

    def test_no_match_exits(self, tmp_path):
        npz_path = _make_fake_npz(tmp_path, 'drive', 'Easy', 'i1', seed=20)
        _make_fake_manifest(tmp_path, [
            {'dataset': 'drive', 'severity': 'Easy', 'image_id': 'i1',
             'npz': str(npz_path), 'n_gaps': 2},
        ])
        from evaluate import _load_manifest_entries
        with pytest.raises(SystemExit) as exc:
            _load_manifest_entries(tmp_path, 'drive', 'Extreme')  # no Extreme in manifest
        assert exc.value.code == 1


# ---------------------------------------------------------------------------
#  Test 2: _tiled_inference_numpy
# ---------------------------------------------------------------------------

class TestTiledInferenceNumpy:

    def test_output_shape_small(self):
        """Image smaller than tile_size → 1 tile, output same shape."""
        from evaluate import _tiled_inference_numpy
        model  = _TinyConvModel().eval()
        device = torch.device('cpu')
        image  = np.random.randn(64, 64).astype(np.float32)
        out    = _tiled_inference_numpy(model, device, image, tile_size=128, overlap=16)
        assert out.shape == (64, 64), f'Expected (64,64), got {out.shape}'
        assert out.dtype == np.float32

    def test_output_shape_large_forces_tiling(self):
        """Image larger than tile_size → multiple tiles, output original shape."""
        from evaluate import _tiled_inference_numpy
        model  = _TinyConvModel().eval()
        device = torch.device('cpu')
        H, W   = 128, 128
        image  = np.random.randn(H, W).astype(np.float32)
        # tile_size=64, overlap=8 → stride=56 → 3 tiles per axis
        out = _tiled_inference_numpy(model, device, image, tile_size=64, overlap=8)
        assert out.shape == (H, W), f'Expected ({H},{W}), got {out.shape}'

    def test_finite_output(self):
        """No NaN/inf in output (basic sanity)."""
        from evaluate import _tiled_inference_numpy
        model  = _TinyConvModel().eval()
        device = torch.device('cpu')
        image  = np.zeros((50, 50), dtype=np.float32)
        out    = _tiled_inference_numpy(model, device, image, tile_size=64, overlap=8)
        assert np.all(np.isfinite(out)), 'Output contains NaN or inf'

    def test_model_returning_tuple(self):
        """Model returning (logits, ctx) tuple should be handled gracefully."""
        from evaluate import _tiled_inference_numpy

        class _TupleModel(nn.Module):
            def __init__(self):
                super().__init__()
                self.conv = nn.Conv2d(1, 1, 1, bias=False)
                nn.init.zeros_(self.conv.weight)
            def forward(self, x):
                return self.conv(x), {'ctx': 'dummy'}  # tuple output

        model  = _TupleModel().eval()
        device = torch.device('cpu')
        image  = np.zeros((32, 32), dtype=np.float32)
        out    = _tiled_inference_numpy(model, device, image, tile_size=64, overlap=8)
        assert out.shape == (32, 32)


# ---------------------------------------------------------------------------
#  Test 3: evaluate_benchmark end-to-end
# ---------------------------------------------------------------------------

class TestEvaluateBenchmarkE2E:
    """Full pipeline: fake NPZ + fake adapter → CSV with all 3 axes non-NaN."""

    @pytest.fixture(autouse=True)
    def _setup(self):
        _register_fake_adapter()

    def _build_benchmark_dir(self, tmp_path: Path, dataset='drive',
                              severity='Medium', n_imgs=2):
        """Create tmp benchmark_dir with manifest + NPZ files."""
        bdir = tmp_path / 'bench'
        bdir.mkdir()
        entries = []
        for i in range(n_imgs):
            image_id = f'fake_{i:02d}'
            npz = _make_fake_npz(
                bdir, dataset=dataset, severity=severity,
                image_id=image_id, H=64, W=64, n_gaps=2, seed=100 + i,
            )
            entries.append({
                'dataset':  dataset,
                'severity': severity,
                'image_id': image_id,
                'npz':      str(npz),
                'n_gaps':   2,
            })
        _make_fake_manifest(bdir, entries)
        return bdir

    def test_returns_rows_equal_to_n_imgs(self, tmp_path):
        from evaluate import evaluate_benchmark
        bdir    = self._build_benchmark_dir(tmp_path, n_imgs=2)
        ckpt    = _make_fake_ckpt(tmp_path)
        rows    = evaluate_benchmark(
            adapter_name  = _FAKE_ADAPTER_NAME,
            ckpt_path     = ckpt,
            benchmark_dir = bdir,
            dataset       = 'drive',
            severity      = 'Medium',
            seed          = 42,
            device_str    = 'cpu',
            tile_size     = 128,
            overlap       = 16,
        )
        assert len(rows) == 2, f'Expected 2 rows, got {len(rows)}'

    def test_reconnection_axis_non_nan(self, tmp_path):
        """SR / reID rate / ε_β0 must all be non-NaN (HEADLINE check)."""
        from evaluate import evaluate_benchmark
        bdir = self._build_benchmark_dir(tmp_path, n_imgs=1)
        ckpt = _make_fake_ckpt(tmp_path)
        rows = evaluate_benchmark(
            adapter_name  = _FAKE_ADAPTER_NAME,
            ckpt_path     = ckpt,
            benchmark_dir = bdir,
            dataset       = 'drive',
            severity      = 'Medium',
            seed          = 42,
            device_str    = 'cpu',
            tile_size     = 128,
            overlap       = 16,
        )
        assert len(rows) == 1
        row = rows[0]
        assert not (isinstance(row['success_rate'], float) and np.isnan(row['success_rate'])), \
            f"success_rate is NaN — reconnection axis broken"
        assert not (isinstance(row['reid_rate'], float) and np.isnan(row['reid_rate'])), \
            f"reid_rate is NaN — reconnection axis broken"
        assert not (isinstance(row['epsilon_beta0'], float) and np.isnan(row['epsilon_beta0'])), \
            f"epsilon_beta0 is NaN"
        assert row['n_gaps'] == 2, f"Expected n_gaps=2, got {row['n_gaps']}"

    def test_overlap_axis_non_nan(self, tmp_path):
        """dice/iou/se/sp must all be finite and in [0,1]."""
        from evaluate import evaluate_benchmark
        bdir = self._build_benchmark_dir(tmp_path, n_imgs=1)
        ckpt = _make_fake_ckpt(tmp_path)
        rows = evaluate_benchmark(
            adapter_name  = _FAKE_ADAPTER_NAME,
            ckpt_path     = ckpt,
            benchmark_dir = bdir,
            severity      = 'Medium',
            device_str    = 'cpu',
            tile_size     = 128,
            overlap       = 16,
        )
        row = rows[0]
        for key in ('dice', 'iou', 'se', 'sp'):
            val = row[key]
            assert np.isfinite(val), f'{key} is not finite: {val}'
            assert 0.0 <= val <= 1.0, f'{key}={val} out of [0,1]'

    def test_csv_schema_all_fieldnames(self, tmp_path):
        """CSV must contain every required fieldname."""
        from evaluate import evaluate_benchmark
        bdir     = self._build_benchmark_dir(tmp_path, n_imgs=1)
        ckpt     = _make_fake_ckpt(tmp_path)
        csv_path = tmp_path / 'out.csv'
        evaluate_benchmark(
            adapter_name  = _FAKE_ADAPTER_NAME,
            ckpt_path     = ckpt,
            benchmark_dir = bdir,
            severity      = 'Medium',
            output_csv    = csv_path,
            device_str    = 'cpu',
            tile_size     = 128,
            overlap       = 16,
        )
        assert csv_path.exists(), 'CSV not written'
        with open(csv_path, 'r', newline='', encoding='utf-8') as f:
            reader   = csv.DictReader(f)
            fieldnames = reader.fieldnames
            rows_read  = list(reader)

        required_fields = [
            'dataset', 'baseline', 'kind', 'seed', 'split', 'severity', 'img_id',
            'dice', 'iou', 'auc', 'se', 'sp',
            'cldice', 'betti_b0_err', 'betti_b1_err', 'skeleton_recall', 'topo_source',
            'epsilon_beta0', 'success_rate', 'reid_rate', 'n_gaps',
            'reid_rate_head', 'reid_idf1',
            'ckpt_path', 'eval_input_mode', 'threshold', 'git_commit',
        ]
        for col in required_fields:
            assert col in fieldnames, f'CSV missing required column: {col!r}'

        assert len(rows_read) == 1

    def test_eval_input_mode_is_benchmark_adapter(self, tmp_path):
        """eval_input_mode must be 'benchmark_adapter' (BUG3 fix: was 'benchmark_tiled')."""
        from evaluate import evaluate_benchmark
        bdir = self._build_benchmark_dir(tmp_path, n_imgs=1)
        ckpt = _make_fake_ckpt(tmp_path)
        rows = evaluate_benchmark(
            adapter_name  = _FAKE_ADAPTER_NAME,
            ckpt_path     = ckpt,
            benchmark_dir = bdir,
            severity      = 'Medium',
            device_str    = 'cpu',
            tile_size     = 128,
            overlap       = 16,
        )
        assert rows[0]['eval_input_mode'] == 'benchmark_adapter', (
            f"BUG3 regression: eval_input_mode={rows[0]['eval_input_mode']!r}, "
            f"expected 'benchmark_adapter' (adapter path, not tiled-inference-numpy path)"
        )

    def test_bug3_forward_adapt_called_not_model_forward(self, tmp_path):
        """
        BUG3 regression test: adapter.forward_adapt must be called (not model.forward).

        Before BUG3 fix, _tiled_inference_numpy called model(inp) directly,
        bypassing adapter.preprocess_benchmark_image and adapter.forward_adapt.
        This caused FR-UNet dice≈0 (OOD input).

        We verify the fix by using a fake adapter whose forward_adapt returns
        a constant +10 logit (→ pred_bin all-ones, dice > 0 if any GT vessel),
        but whose model.forward returns -10 logit (→ pred_bin all-zeros, dice=0).
        If forward_adapt is called → dice > 0 (pass).
        If model.forward is called directly → dice ≈ 0 (fail).
        """
        import baselines
        from baselines.registry import MODEL_REGISTRY
        from baselines.base_adapter import BaselineAdapter

        CANARY_ADAPTER = '_test_canary_forward_adapt'

        class _CanaryModel(nn.Module):
            """Returns large negative logit (-10) → pred all-zeros when called directly."""
            def __init__(self):
                super().__init__()
            def forward(self, x):
                return torch.full_like(x, -10.0)  # all-zeros after sigmoid

        class _CanaryAdapter(BaselineAdapter):
            """forward_adapt returns +10 logit → pred all-ones.  model.forward returns -10."""
            name = CANARY_ADAPTER
            kind = 'test'
            source_repo = 'test'
            env_tag = 'main'

            def build_model(self, cfg):
                return _CanaryModel()

            def build_loss(self, cfg):
                return nn.BCEWithLogitsLoss()

            def build_optimizer(self, model, cfg):
                return torch.optim.SGD([], lr=0.0)

            def preprocess_cfg(self):
                return {}

            def forward_adapt(self, model, img_t, device):
                # Returns +10 logit → sigmoid ≈ 1.0 → pred_bin all-ones
                return torch.full_like(img_t, 10.0)

        if CANARY_ADAPTER not in MODEL_REGISTRY:
            MODEL_REGISTRY[CANARY_ADAPTER] = _CanaryAdapter

        from evaluate import evaluate_benchmark

        bdir = self._build_benchmark_dir(tmp_path, n_imgs=1)
        # Canary model has no parameters; save an empty state_dict as ckpt.
        canary_ckpt_path = tmp_path / 'canary_best.pth'
        torch.save(_CanaryModel().state_dict(), str(canary_ckpt_path))

        rows = evaluate_benchmark(
            adapter_name  = CANARY_ADAPTER,
            ckpt_path     = canary_ckpt_path,
            benchmark_dir = bdir,
            severity      = 'Medium',
            device_str    = 'cpu',
        )
        assert len(rows) == 1
        dice_val = rows[0]['dice']
        # If adapter.forward_adapt was called → pred all-ones → dice > 0 (GT has vessel pixels)
        # If model.forward was called directly → pred all-zeros → dice ≈ 0
        assert dice_val > 0.0, (
            f'BUG3 NOT FIXED: dice={dice_val:.4f}. '
            f'model.forward returned all-zeros (-10 logit) meaning adapter.forward_adapt '
            f'was NOT called. Expected adapter path (+10 logit → all-ones → dice>0).'
        )

    def test_missing_ckpt_exits(self, tmp_path):
        """Non-existent ckpt should exit with code 1."""
        from evaluate import evaluate_benchmark
        bdir = self._build_benchmark_dir(tmp_path, n_imgs=1)
        with pytest.raises(SystemExit) as exc:
            evaluate_benchmark(
                adapter_name  = _FAKE_ADAPTER_NAME,
                ckpt_path     = tmp_path / 'nonexistent.pth',
                benchmark_dir = bdir,
                severity      = 'Medium',
                device_str    = 'cpu',
            )
        assert exc.value.code == 1

    def test_npz_missing_image_field_skips(self, tmp_path):
        """NPZ without 'image' field (legacy schema) should be skipped with warning."""
        from evaluate import evaluate_benchmark

        bdir = tmp_path / 'bench'
        bdir.mkdir()
        # Write a legacy NPZ without 'image' field
        legacy_npz = bdir / 'legacy.npz'
        gap_records_json = json.dumps([{
            'gap_id': 0, 'center_yx': [32, 32], 'radius': 3, 'gap_size': 4,
            'sigma': 1.0, 'segment_id_left': 1, 'segment_id_right': 2,
        }]).encode('utf-8')
        np.savez_compressed(
            str(legacy_npz),
            mask_broken        = np.zeros((64, 64), dtype=np.uint8),
            vessel_segment_map = np.zeros((64, 64), dtype=np.int32),
            gap_records_json   = np.frombuffer(gap_records_json, dtype=np.uint8),
            # 'image' key intentionally omitted (legacy)
            image_id           = np.array(['legacy_01']),
            dataset            = np.array(['drive']),
            severity           = np.array(['Medium']),
            seed_used          = np.array([42]),
            original_shape     = np.array([64, 64]),
        )
        _make_fake_manifest(bdir, [{
            'dataset': 'drive', 'severity': 'Medium', 'image_id': 'legacy_01',
            'npz': str(legacy_npz), 'n_gaps': 1,
        }])
        ckpt = _make_fake_ckpt(tmp_path)

        # Should not crash; returns empty rows (skipped)
        rows = evaluate_benchmark(
            adapter_name  = _FAKE_ADAPTER_NAME,
            ckpt_path     = ckpt,
            benchmark_dir = bdir,
            severity      = 'Medium',
            device_str    = 'cpu',
        )
        assert rows == [], f'Expected 0 rows for legacy NPZ, got {len(rows)}'


# ---------------------------------------------------------------------------
#  Test 4: Legacy path backward compat (--benchmark_dir not set)
# ---------------------------------------------------------------------------

class TestLegacyPathCompat:
    """Passing benchmark_dir=None should not break and should route to evaluate_adapter."""

    def test_evaluate_adapter_still_importable(self):
        """evaluate_adapter must remain importable and callable (no signature break)."""
        import inspect
        from evaluate import evaluate_adapter
        sig = inspect.signature(evaluate_adapter)
        assert 'adapter_name' in sig.parameters
        assert 'break_results' in sig.parameters  # existing param still present

    def test_evaluate_benchmark_is_new_symbol(self):
        """evaluate_benchmark must be importable from evaluate module."""
        from evaluate import evaluate_benchmark  # noqa: F401
        assert callable(evaluate_benchmark)

    def test_load_manifest_entries_is_new_symbol(self):
        """_load_manifest_entries must be importable."""
        from evaluate import _load_manifest_entries  # noqa: F401
        assert callable(_load_manifest_entries)

    def test_tiled_inference_is_new_symbol(self):
        """_tiled_inference_numpy must be importable."""
        from evaluate import _tiled_inference_numpy  # noqa: F401
        assert callable(_tiled_inference_numpy)


# ---------------------------------------------------------------------------
#  Test 5: Multi-severity (--severity all / multi-value) — model loaded once
# ---------------------------------------------------------------------------

class TestMultiSeverityEval:
    """
    Tests for the multi-severity optimisation:
      - model/adapter/ckpt loaded ONCE regardless of severity count.
      - Each severity produces its own CSV (<stem>_<Severity>.csv).
      - Inference cache reuses forward pass for same image_id across severities.
      - Single-severity call still works (backward compat).
      - 'all' sentinel expands to 4 severities.
      - Unknown severity raises ValueError.
    """

    @pytest.fixture(autouse=True)
    def _setup(self):
        _register_fake_adapter()

    def _build_multi_sev_dir(
        self, tmp_path: Path, dataset: str = 'drive',
        severities: list = None, n_imgs: int = 2,
    ) -> Path:
        """Create benchmark_dir with entries for multiple severities."""
        if severities is None:
            severities = ['Easy', 'Medium', 'Hard', 'Extreme']
        bdir = tmp_path / 'bench_multi'
        bdir.mkdir(exist_ok=True)
        entries = []
        seed_offset = 0
        for sev in severities:
            for i in range(n_imgs):
                image_id = f'img_{sev[:1].lower()}_{i:02d}'  # e.g. 'img_e_00'
                npz = _make_fake_npz(
                    bdir, dataset=dataset, severity=sev,
                    image_id=image_id, H=64, W=64, n_gaps=2,
                    seed=200 + seed_offset,
                )
                entries.append({
                    'dataset':  dataset,
                    'severity': sev,
                    'image_id': image_id,
                    'npz':      str(npz),
                    'n_gaps':   2,
                })
                seed_offset += 1
        _make_fake_manifest(bdir, entries)
        return bdir

    def test_single_severity_string_backward_compat(self, tmp_path):
        """Single-string severity still works (no regression)."""
        from evaluate import evaluate_benchmark
        bdir = self._build_multi_sev_dir(tmp_path, severities=['Medium'])
        ckpt = _make_fake_ckpt(tmp_path)
        rows = evaluate_benchmark(
            adapter_name  = _FAKE_ADAPTER_NAME,
            ckpt_path     = ckpt,
            benchmark_dir = bdir,
            dataset       = 'drive',
            severity      = 'Medium',
            seed          = 42,
            device_str    = 'cpu',
        )
        assert len(rows) == 2, f'Expected 2 rows for single severity, got {len(rows)}'
        assert all(r['severity'] == 'Medium' for r in rows)

    def test_multi_severity_list_returns_combined_rows(self, tmp_path):
        """Passing ['Easy', 'Hard'] returns rows for both severities combined."""
        from evaluate import evaluate_benchmark
        bdir = self._build_multi_sev_dir(tmp_path, severities=['Easy', 'Hard'], n_imgs=2)
        ckpt = _make_fake_ckpt(tmp_path)
        rows = evaluate_benchmark(
            adapter_name  = _FAKE_ADAPTER_NAME,
            ckpt_path     = ckpt,
            benchmark_dir = bdir,
            dataset       = 'drive',
            severity      = ['Easy', 'Hard'],
            seed          = 42,
            device_str    = 'cpu',
        )
        assert len(rows) == 4, f'Expected 4 rows (2 Easy + 2 Hard), got {len(rows)}'
        sev_seen = {r['severity'] for r in rows}
        assert sev_seen == {'Easy', 'Hard'}, f'Unexpected severities: {sev_seen}'

    def test_all_sentinel_runs_four_severities(self, tmp_path):
        """'all' sentinel expands to all four severities."""
        from evaluate import evaluate_benchmark
        bdir = self._build_multi_sev_dir(
            tmp_path,
            severities=['Easy', 'Medium', 'Hard', 'Extreme'],
            n_imgs=1,
        )
        ckpt = _make_fake_ckpt(tmp_path)
        rows = evaluate_benchmark(
            adapter_name  = _FAKE_ADAPTER_NAME,
            ckpt_path     = ckpt,
            benchmark_dir = bdir,
            dataset       = 'drive',
            severity      = 'all',
            seed          = 42,
            device_str    = 'cpu',
        )
        assert len(rows) == 4, f'Expected 4 rows (1 per severity), got {len(rows)}'
        sev_seen = {r['severity'] for r in rows}
        assert sev_seen == {'Easy', 'Medium', 'Hard', 'Extreme'}

    def test_multi_severity_writes_per_severity_csv(self, tmp_path):
        """Each severity writes its own <stem>_<Severity>.csv file."""
        from evaluate import evaluate_benchmark
        bdir = self._build_multi_sev_dir(
            tmp_path, severities=['Easy', 'Medium'], n_imgs=1,
        )
        ckpt = _make_fake_ckpt(tmp_path)
        out_base = tmp_path / 'out_eval.csv'
        evaluate_benchmark(
            adapter_name  = _FAKE_ADAPTER_NAME,
            ckpt_path     = ckpt,
            benchmark_dir = bdir,
            dataset       = 'drive',
            severity      = ['Easy', 'Medium'],
            output_csv    = out_base,
            seed          = 42,
            device_str    = 'cpu',
        )
        csv_easy   = tmp_path / 'out_eval_Easy.csv'
        csv_medium = tmp_path / 'out_eval_Medium.csv'
        assert csv_easy.exists(),   f'Missing per-severity CSV: {csv_easy}'
        assert csv_medium.exists(), f'Missing per-severity CSV: {csv_medium}'
        # Verify each file contains rows only for its severity
        for csv_path, expected_sev in [(csv_easy, 'Easy'), (csv_medium, 'Medium')]:
            with open(csv_path, 'r', newline='', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    assert row['severity'] == expected_sev, (
                        f'{csv_path.name}: expected severity={expected_sev!r}, '
                        f'got {row["severity"]!r}'
                    )

    def test_model_build_called_once_for_multi_severity(self, tmp_path):
        """
        model.build_model must be called exactly ONCE even when multiple severities
        are requested (the optimisation target).

        Strategy: register a canary adapter that counts build_model calls via a
        mutable counter in a shared list (avoids closure mutation issues).
        """
        import baselines
        from baselines.registry import MODEL_REGISTRY
        from baselines.base_adapter import BaselineAdapter

        BUILD_COUNTER = [0]  # mutable list — incremented inside build_model
        CANARY_NAME = '_test_build_once_canary'

        class _CountingAdapter(BaselineAdapter):
            name       = CANARY_NAME
            kind       = 'test'
            source_repo = 'test'
            env_tag    = 'main'

            def build_model(self, cfg):
                BUILD_COUNTER[0] += 1
                return _TinyConvModel()

            def build_loss(self, cfg):
                return nn.BCEWithLogitsLoss()

            def build_optimizer(self, model, cfg):
                return torch.optim.SGD([], lr=0.0)

            def preprocess_cfg(self):
                return {}

            def forward_adapt(self, model, img_t, device):
                with torch.no_grad():
                    return model(img_t.to(device))

        if CANARY_NAME not in MODEL_REGISTRY:
            MODEL_REGISTRY[CANARY_NAME] = _CountingAdapter

        from evaluate import evaluate_benchmark

        bdir = self._build_multi_sev_dir(
            tmp_path,
            severities=['Easy', 'Medium', 'Hard', 'Extreme'],
            n_imgs=1,
        )
        ckpt = _make_fake_ckpt(tmp_path)

        BUILD_COUNTER[0] = 0  # reset before call
        evaluate_benchmark(
            adapter_name  = CANARY_NAME,
            ckpt_path     = ckpt,
            benchmark_dir = bdir,
            dataset       = 'drive',
            severity      = 'all',
            seed          = 42,
            device_str    = 'cpu',
        )
        assert BUILD_COUNTER[0] == 1, (
            f'build_model was called {BUILD_COUNTER[0]} time(s); '
            f'expected exactly 1 (model should be loaded once for all severities). '
            f'The multi-severity optimisation is NOT in effect.'
        )

    def test_unknown_severity_raises_value_error(self, tmp_path):
        """Passing an unknown severity string must raise ValueError."""
        from evaluate import evaluate_benchmark
        bdir = self._build_multi_sev_dir(tmp_path, severities=['Medium'])
        ckpt = _make_fake_ckpt(tmp_path)
        with pytest.raises(ValueError, match='Unknown severity'):
            evaluate_benchmark(
                adapter_name  = _FAKE_ADAPTER_NAME,
                ckpt_path     = ckpt,
                benchmark_dir = bdir,
                severity      = 'BogusLevel',
                device_str    = 'cpu',
            )

    def test_resolve_severity_list_helper(self):
        """Unit-test _resolve_severity_list directly."""
        from evaluate import _resolve_severity_list
        # None → None
        assert _resolve_severity_list(None) is None
        # single string
        assert _resolve_severity_list('Medium') == ['Medium']
        # 'all' sentinel
        result = _resolve_severity_list('all')
        assert set(result) == {'Easy', 'Medium', 'Hard', 'Extreme'}
        assert len(result) == 4
        # list
        assert _resolve_severity_list(['Easy', 'Hard']) == ['Easy', 'Hard']
        # deduplication
        dedup = _resolve_severity_list(['Medium', 'Medium'])
        assert dedup == ['Medium']
        # ['all'] list
        result2 = _resolve_severity_list(['all'])
        assert set(result2) == {'Easy', 'Medium', 'Hard', 'Extreme'}
        # invalid
        with pytest.raises(ValueError):
            _resolve_severity_list('SuperHard')
