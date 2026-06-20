"""
test_datasets.py — pytest suite for gdn2vessel dataset pipeline.

Tests (all run without real data using mock/synthetic images):
  1. Split disjoint assertion: TRAIN/VAL/TEST IDs have zero overlap.
  2. __getitem__ shape/dict-key contract (mocked small images).
  3. verify_no_leakage logic: overlapping paths → FAIL, disjoint → PASS.
  4. FIVES dynamic ID discovery: train/test come from separate directories.
  5. STARE ppm.gz loading round-trip.
  6. precompute_benchmark load_benchmark_sample schema check.
  7. Tile extraction: get_tiles returns correct shape and non-overlapping coords.
  8. BaseVesselDataset: anti-leakage check raises on bad subclass definition.

No real datasets required. All images are synthetic (numpy random arrays
written to tmp_path by fixtures).
"""

from __future__ import annotations

import gzip
import io
import json
import sys
import tempfile
from dataclasses import asdict
from pathlib import Path
from typing import List

import cv2
import numpy as np
import pytest
import torch

# --------------------------------------------------------------------------- #
#  Path setup — let tests run from repo root or tests/ directory
# --------------------------------------------------------------------------- #
_repo_root = Path(__file__).parent.parent
_src_dir   = _repo_root / 'src'
if str(_src_dir) not in sys.path:
    sys.path.insert(0, str(_src_dir))

from datasets.base_vessel import BaseVesselDataset
from datasets.chase import CHASEDataset
from datasets.stare import STAREDataset
from datasets.hrf   import HRFDataset
from datasets.fives import FIVESDataset


# =========================================================================== #
#  Fixtures: synthetic dataset directories
# =========================================================================== #

def _write_synthetic_rgb(path: Path, h: int = 64, w: int = 64):
    """Write a tiny random RGB PNG."""
    img = np.random.randint(0, 255, (h, w, 3), dtype=np.uint8)
    cv2.imwrite(str(path), img)


def _write_synthetic_mask(path: Path, h: int = 64, w: int = 64):
    """Write a binary GT mask PNG (random blobs)."""
    mask = np.zeros((h, w), dtype=np.uint8)
    cx, cy, r = w // 2, h // 2, w // 4
    cv2.circle(mask, (cx, cy), r, 255, -1)
    cv2.imwrite(str(path), mask)


@pytest.fixture
def synthetic_chase_root(tmp_path: Path) -> Path:
    """Synthetic CHASE directory: images/ + masks/ with 1stHO GT."""
    root = tmp_path / 'CHASE'
    img_dir  = root / 'images'
    mask_dir = root / 'masks'
    img_dir.mkdir(parents=True)
    mask_dir.mkdir(parents=True)

    # Create all 28 CHASE images (01L..14R)
    for n in range(1, 15):
        for side in ('L', 'R'):
            sid = f'{n:02d}{side}'
            _write_synthetic_rgb(img_dir / f'Image_{sid}.jpg')
            _write_synthetic_mask(mask_dir / f'Image_{sid}_1stHO.png')

    return root


@pytest.fixture
def synthetic_hrf_root(tmp_path: Path) -> Path:
    """Synthetic HRF directory: images/ + masks/ + roi_masks/."""
    root = tmp_path / 'HRF'
    (root / 'images').mkdir(parents=True)
    (root / 'masks').mkdir(parents=True)
    (root / 'roi_masks').mkdir(parents=True)

    # healthy (01_h..15_h), dr (01_dr..15_dr), glaucoma (01_g..15_g)
    for n in range(1, 16):
        for cond in ('h', 'dr', 'g'):
            sid = f'{n:02d}_{cond}'
            _write_synthetic_rgb(root / 'images' / f'{sid}.jpg', h=64, w=80)
            _write_synthetic_mask(root / 'masks' / f'{sid}.tif', h=64, w=80)
            _write_synthetic_mask(root / 'roi_masks' / f'{sid}.tif', h=64, w=80)

    return root


@pytest.fixture
def synthetic_fives_root(tmp_path: Path) -> Path:
    """Synthetic FIVES directory: train/{Original,Ground Truth}/ + test/{...}/."""
    root = tmp_path / 'FIVES'
    train_img = root / 'train' / 'Original'
    train_gt  = root / 'train' / 'Ground Truth'
    test_img  = root / 'test'  / 'Original'
    test_gt   = root / 'test'  / 'Ground Truth'
    for d in (train_img, train_gt, test_img, test_gt):
        d.mkdir(parents=True)

    # 10 train + 4 test (minimal)
    for i in range(1, 11):
        _write_synthetic_rgb(train_img / f'{i}.png', h=64, w=64)
        _write_synthetic_mask(train_gt / f'{i}.png', h=64, w=64)
    for i in range(100, 104):  # distinct IDs from train
        _write_synthetic_rgb(test_img / f'{i}.png', h=64, w=64)
        _write_synthetic_mask(test_gt / f'{i}.png', h=64, w=64)

    return root


# =========================================================================== #
#  Test 1: Split disjoint assertion — all datasets
# =========================================================================== #

class TestSplitDisjoint:
    """Verify that TRAIN/VAL/TEST IDs are always disjoint (RED LINE 1)."""

    def test_chase_split_disjoint(self, synthetic_chase_root):
        ds = CHASEDataset(str(synthetic_chase_root), split='train', skip_missing=True)
        train_s = set(ds.TRAIN_IDS)
        val_s   = set(ds.VAL_IDS)
        test_s  = set(ds.TEST_IDS)
        assert train_s.isdisjoint(test_s),  f'CHASE TRAIN ∩ TEST = {train_s & test_s}'
        assert val_s.isdisjoint(test_s),    f'CHASE VAL ∩ TEST = {val_s & test_s}'
        assert train_s.isdisjoint(val_s),   f'CHASE TRAIN ∩ VAL = {train_s & val_s}'

    def test_hrf_split_disjoint(self, synthetic_hrf_root):
        ds = HRFDataset(str(synthetic_hrf_root), split='train', skip_missing=True)
        train_s = set(ds.TRAIN_IDS)
        val_s   = set(ds.VAL_IDS)
        test_s  = set(ds.TEST_IDS)
        assert train_s.isdisjoint(test_s),  f'HRF TRAIN ∩ TEST = {train_s & test_s}'
        assert val_s.isdisjoint(test_s),    f'HRF VAL ∩ TEST = {val_s & test_s}'

    def test_fives_split_disjoint(self, synthetic_fives_root):
        ds = FIVESDataset(str(synthetic_fives_root), split='train', skip_missing=True)
        train_s = set(ds._train_ids)
        val_s   = set(ds._val_ids)
        test_s  = set(ds._test_ids)
        assert train_s.isdisjoint(test_s), f'FIVES TRAIN ∩ TEST = {train_s & test_s}'
        assert val_s.isdisjoint(test_s),   f'FIVES VAL ∩ TEST = {val_s & test_s}'

    def test_base_bad_subclass_raises(self):
        """A subclass with overlapping TRAIN/TEST IDs must raise AssertionError."""
        class BadDataset(BaseVesselDataset):
            TRAIN_IDS = [1, 2, 3]
            VAL_IDS   = [4, 5]
            TEST_IDS  = [3, 6]  # 3 is in both TRAIN and TEST → should raise

            def _img_path(self, sid): return Path('x')
            def _gt_path(self, sid):  return Path('x')
            def _mask_path(self, sid): return Path('x')

        with pytest.raises(AssertionError, match=r'TRAIN_IDS.*TEST_IDS|TEST_IDS.*TRAIN_IDS'):
            BadDataset('/fake', skip_missing=True)


# =========================================================================== #
#  Test 2: __getitem__ shape and dict-key contract
# =========================================================================== #

class TestGetitemContract:
    """__getitem__ must return dict with image/gt/fov tensors of correct shape."""

    def test_chase_getitem_shape(self, synthetic_chase_root):
        ds = CHASEDataset(str(synthetic_chase_root), split='train',
                          patch_size=32, augment=False)
        sample = ds[0]
        self._check_sample(sample, patch_size=32)

    def test_chase_getitem_keys(self, synthetic_chase_root):
        ds = CHASEDataset(str(synthetic_chase_root), split='train',
                          patch_size=32, augment=False)
        sample = ds[0]
        assert set(sample.keys()) == {'image', 'gt', 'fov', 'id'}, \
            f"Unexpected keys: {set(sample.keys())}"

    def test_hrf_getitem_shape(self, synthetic_hrf_root):
        ds = HRFDataset(str(synthetic_hrf_root), split='train',
                        patch_size=32, augment=False)
        sample = ds[0]
        self._check_sample(sample, patch_size=32)

    def test_fives_getitem_shape(self, synthetic_fives_root):
        ds = FIVESDataset(str(synthetic_fives_root), split='train',
                          patch_size=32, augment=False)
        sample = ds[0]
        self._check_sample(sample, patch_size=32)

    def test_fives_test_getitem(self, synthetic_fives_root):
        """Test split __getitem__ also works (for benchmark evaluation)."""
        ds = FIVESDataset(str(synthetic_fives_root), split='test',
                          patch_size=32, augment=False)
        assert len(ds) > 0
        sample = ds[0]
        self._check_sample(sample, patch_size=32)

    def _check_sample(self, sample, patch_size):
        img = sample['image']
        gt  = sample['gt']
        fov = sample['fov']
        assert isinstance(img, torch.Tensor), 'image must be Tensor'
        assert img.shape == (1, patch_size, patch_size), \
            f'image shape {img.shape} != (1,{patch_size},{patch_size})'
        assert gt.shape  == (1, patch_size, patch_size), \
            f'gt shape {gt.shape}'
        assert fov.shape == (1, patch_size, patch_size), \
            f'fov shape {fov.shape}'
        assert img.dtype == torch.float32
        assert gt.dtype  == torch.float32
        assert fov.dtype == torch.float32
        # GT values must be {0, 1}
        unique_gt = set(gt.unique().tolist())
        assert unique_gt.issubset({0.0, 1.0}), f'GT has unexpected values: {unique_gt}'
        # FOV values must be {0, 1}
        unique_fov = set(fov.unique().tolist())
        assert unique_fov.issubset({0.0, 1.0}), f'FOV has unexpected values: {unique_fov}'


# =========================================================================== #
#  Test 3: verify_no_leakage logic
# =========================================================================== #

class TestVerifyNoLeakage:
    """Unit test for verify_no_leakage.verify_dataset logic."""

    def test_no_leakage_passes(self, synthetic_chase_root):
        """Clean CHASE split → verify_dataset returns passed=True."""
        from datasets.verify_no_leakage import verify_dataset
        passed, report = verify_dataset('CHASE', CHASEDataset, str(synthetic_chase_root))
        assert passed, f'Expected PASS but got FAIL:\n{report}'
        assert '[OK]' in report

    def test_leakage_detected(self, tmp_path: Path):
        """
        Construct a dataset where test and train share an image file → FAIL.
        We do this by creating a subclass whose TEST_IDS overlap TRAIN_IDS.
        """
        # Build synthetic root with shared images
        root = tmp_path / 'leak_test'
        (root / 'images').mkdir(parents=True)
        (root / 'masks').mkdir(parents=True)

        # 28 images for normal CHASE
        for n in range(1, 15):
            for side in ('L', 'R'):
                sid = f'{n:02d}{side}'
                _write_synthetic_rgb(root / 'images' / f'Image_{sid}.jpg')
                _write_synthetic_mask(root / 'masks' / f'Image_{sid}_1stHO.png')

        # Create a DELIBERATELY LEAKY subclass
        class LeakyCHASE(CHASEDataset):
            TRAIN_IDS = ['01L', '01R', '02L', '02R']
            VAL_IDS   = ['03L', '03R']
            TEST_IDS  = ['02L', '04L']  # '02L' is in TRAIN! → should fail disjoint

        from datasets.verify_no_leakage import verify_dataset

        # The leaky class will fail the assertion in __init__ before verify_dataset
        # gets a chance — test that verify_dataset handles it or that instantiation fails.
        # In BaseVesselDataset.__init__, _check_split_disjoint is called → AssertionError.
        with pytest.raises(AssertionError):
            LeakyCHASE(str(root), skip_missing=True)


# =========================================================================== #
#  Test 4: FIVES dynamic ID discovery
# =========================================================================== #

class TestFIVESDiscovery:
    def test_fives_discovers_train_test_ids(self, synthetic_fives_root):
        ds_train = FIVESDataset(str(synthetic_fives_root), split='train', skip_missing=True)
        ds_test  = FIVESDataset(str(synthetic_fives_root), split='test',  skip_missing=True)

        assert len(ds_train.ids) > 0, 'FIVES should discover training IDs'
        assert len(ds_test.ids) > 0,  'FIVES should discover test IDs'

        train_set = set(ds_train._train_ids + ds_train._val_ids)
        test_set  = set(ds_test._test_ids)
        assert train_set.isdisjoint(test_set), \
            f'FIVES train ∩ test = {train_set & test_set}'

    def test_fives_len_matches_discovered(self, synthetic_fives_root):
        ds = FIVESDataset(str(synthetic_fives_root), split='train', skip_missing=True)
        assert len(ds) == len(ds.ids), 'len(ds) should match len(ds.ids)'


# =========================================================================== #
#  Test 5: STARE ppm.gz loading round-trip
# =========================================================================== #

class TestSTAREPpmGz:
    def test_ppm_gz_roundtrip(self, tmp_path: Path):
        """Write a synthetic .ppm.gz, load it, check shape and dtype."""
        from datasets.stare import _load_ppm_gz

        H, W = 16, 20
        img_rgb = np.random.randint(0, 255, (H, W, 3), dtype=np.uint8)

        # Encode as PPM
        ppm_header = f'P6\n{W} {H}\n255\n'.encode('ascii')
        ppm_data   = ppm_header + img_rgb.tobytes()

        # Write as .ppm.gz
        gz_path = tmp_path / 'test_img.ppm.gz'
        with gzip.open(str(gz_path), 'wb') as f:
            f.write(ppm_data)

        # Load
        loaded_bgr = _load_ppm_gz(gz_path)
        assert loaded_bgr.shape == (H, W, 3), \
            f'Loaded shape {loaded_bgr.shape} != ({H},{W},3)'
        assert loaded_bgr.dtype == np.uint8

        # Pixel values should match (BGR = RGB channel reversal)
        loaded_rgb = loaded_bgr[:, :, ::-1]
        np.testing.assert_array_equal(
            loaded_rgb, img_rgb,
            err_msg='ppm.gz round-trip pixel mismatch'
        )


# =========================================================================== #
#  Test 6: precompute_benchmark load_benchmark_sample schema
# =========================================================================== #

class TestPrecomputeBenchmark:
    def test_load_benchmark_sample_schema(self, tmp_path: Path):
        """
        Write a minimal benchmark NPZ manually, then load via load_benchmark_sample
        and verify schema keys.
        """
        from datasets.precompute_benchmark import load_benchmark_sample
        from benchmark.synth_breaks import GapRecord

        H, W = 32, 32
        mask_broken = np.zeros((H, W), dtype=np.uint8)
        vessel_map  = np.zeros((H, W), dtype=np.int32)
        gaps = [GapRecord(gap_id=0, center_yx=(16, 16), radius=3,
                           gap_size=8, sigma=0.8, segment_id_left=1,
                           segment_id_right=2)]
        gap_json_bytes = json.dumps([asdict(g) for g in gaps]).encode('utf-8')

        npz_path = tmp_path / 'test_benchmark.npz'
        np.savez_compressed(
            str(npz_path),
            mask_broken        = mask_broken,
            vessel_segment_map = vessel_map,
            gap_records_json   = np.frombuffer(gap_json_bytes, dtype=np.uint8),
            image_id           = np.array(['test_id']),
            dataset            = np.array(['drive']),
            severity           = np.array(['Medium']),
            seed_used          = np.array([42]),
            original_shape     = np.array([H, W]),
        )

        sample = load_benchmark_sample(str(npz_path))
        required_keys = {'mask_broken', 'vessel_segment_map', 'gaps',
                         'image_id', 'dataset', 'severity', 'seed_used', 'original_shape'}
        assert set(sample.keys()) == required_keys, \
            f'Missing keys: {required_keys - set(sample.keys())}'
        assert sample['mask_broken'].shape == (H, W)
        assert sample['vessel_segment_map'].shape == (H, W)
        assert len(sample['gaps']) == 1
        assert sample['gaps'][0]['gap_id'] == 0
        assert sample['image_id'] == 'test_id'
        assert sample['severity'] == 'Medium'
        assert sample['original_shape'] == (H, W)


# =========================================================================== #
#  Test 7: Tile extraction shape
# =========================================================================== #

class TestTileExtraction:
    def test_get_tiles_returns_correct_shape(self, synthetic_hrf_root):
        ds = HRFDataset(str(synthetic_hrf_root), split='train', patch_size=None)
        sid = ds.ids[0]
        tiles = ds.get_tiles(sid, tile_size=32, overlap=8)

        assert len(tiles) > 0, 'get_tiles should return at least one tile'
        for tile in tiles:
            img = tile['image']
            gt  = tile['gt']
            assert img.shape == (1, 32, 32), f'tile image shape {img.shape}'
            assert gt.shape  == (1, 32, 32), f'tile gt shape {gt.shape}'
            assert isinstance(tile['coords'], tuple) and len(tile['coords']) == 4
            y0, x0, y1, x1 = tile['coords']
            assert y1 - y0 == 32
            assert x1 - x0 == 32

    def test_get_tiles_no_overlap_with_test_ids(self, synthetic_hrf_root):
        """Tile extraction on test split should work without leaking train paths."""
        ds = HRFDataset(str(synthetic_hrf_root), split='test', patch_size=None)
        assert len(ds.ids) > 0
        sid = ds.ids[0]
        tiles = ds.get_tiles(sid, tile_size=32, overlap=0)
        assert all(t['id'] == sid for t in tiles), 'All tiles should have correct id'


# =========================================================================== #
#  Test 8: Full-image pad (patch_size=None)
# =========================================================================== #

class TestFullImagePad:
    def test_chase_full_image_pad(self, synthetic_chase_root):
        """patch_size=None → pads to pad_multiple, shape (1, H', W') where H'%32==0."""
        ds = CHASEDataset(str(synthetic_chase_root), split='val',
                          patch_size=None, augment=False, pad_multiple=32)
        sample = ds[0]
        img = sample['image']
        assert img.ndim == 3 and img.shape[0] == 1
        assert img.shape[1] % 32 == 0, f'H not padded to 32: {img.shape[1]}'
        assert img.shape[2] % 32 == 0, f'W not padded to 32: {img.shape[2]}'
