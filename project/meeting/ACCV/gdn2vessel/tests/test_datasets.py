"""
test_datasets.py — pytest suite for gdn2vessel dataset pipeline.

All tests run WITHOUT real datasets. Fixtures write tiny synthetic images
to tmp_path using the EXACT filenames/layouts that each Dataset class expects
(confirmed from HPC ls 2026-06-20, reflected in production dataset code).

CHASE  layout: images/{sid}_test.tif + masks/{sid}_manual1.tif
               sids: training_01..training_20 + test_01..test_08
STARE  layout: images/{sid}.ppm + masks/{sid}.ah.ppm  (plain PPM, NOT gzipped)
               sids: im0001..im0324 (20 non-sequential IDs from _STARE_ALL_IDS)
HRF    layout: images/{sid}.jpg  + masks/{sid}.tif  + roi_masks/{sid}.tif
               sids: 01_h..15_h / 01_dr..15_dr / 01_g..15_g
FIVES  layout: images/train_<n>_<tag>.png + masks/train_<n>_<tag>.png  (flat dir)
               test images: images/test_<n>_<tag>.png + masks/test_<n>_<tag>.png
"""

from __future__ import annotations

import gzip
import io
import json
import struct
import sys
from dataclasses import asdict
from pathlib import Path
from typing import List

import cv2
import numpy as np
import pytest
import torch

# --------------------------------------------------------------------------- #
#  Path setup
# --------------------------------------------------------------------------- #
_repo_root = Path(__file__).parent.parent
_src_dir   = _repo_root / 'src'
if str(_src_dir) not in sys.path:
    sys.path.insert(0, str(_src_dir))

from datasets.base_vessel import BaseVesselDataset
from datasets.chase import CHASEDataset, _make_ids
from datasets.stare import STAREDataset, _STARE_ALL_IDS, _load_ppm_gz
from datasets.hrf   import HRFDataset
from datasets.fives import FIVESDataset


# =========================================================================== #
#  Shared synthetic image writers
# =========================================================================== #

def _write_rgb_tif(path: Path, h: int = 64, w: int = 64):
    """Write tiny random RGB .tif (cv2 handles tif extension)."""
    img = np.random.randint(30, 200, (h, w, 3), dtype=np.uint8)
    cv2.imwrite(str(path), img)


def _write_rgb_jpg(path: Path, h: int = 64, w: int = 64):
    """Write tiny random RGB .jpg."""
    img = np.random.randint(30, 200, (h, w, 3), dtype=np.uint8)
    cv2.imwrite(str(path), img)


def _write_mask_tif(path: Path, h: int = 64, w: int = 64):
    """Write binary mask as .tif (circles for vessel-like GT)."""
    mask = np.zeros((h, w), dtype=np.uint8)
    cv2.circle(mask, (w // 2, h // 2), w // 4, 255, -1)
    cv2.imwrite(str(path), mask)


def _write_mask_png(path: Path, h: int = 64, w: int = 64):
    """Write binary mask as .png."""
    mask = np.zeros((h, w), dtype=np.uint8)
    cv2.circle(mask, (w // 2, h // 2), w // 4, 255, -1)
    cv2.imwrite(str(path), mask)


def _write_ppm(path: Path, h: int = 32, w: int = 40):
    """Write a plain P6 PPM file (not gzipped — matches Kaggle pack)."""
    img_rgb = np.random.randint(30, 200, (h, w, 3), dtype=np.uint8)
    header = f'P6\n{w} {h}\n255\n'.encode('ascii')
    with open(str(path), 'wb') as f:
        f.write(header + img_rgb.tobytes())


def _write_ppm_gz(path: Path, h: int = 32, w: int = 40):
    """Write a gzip-compressed P6 PPM file (fallback format)."""
    img_rgb = np.random.randint(30, 200, (h, w, 3), dtype=np.uint8)
    header = f'P6\n{w} {h}\n255\n'.encode('ascii')
    with gzip.open(str(path), 'wb') as f:
        f.write(header + img_rgb.tobytes())


# =========================================================================== #
#  Fixtures: synthetic dataset directories
#  File names MUST match what the Dataset classes expect (HPC-ls-confirmed).
# =========================================================================== #

@pytest.fixture
def synthetic_chase_root(tmp_path: Path) -> Path:
    """
    CHASE layout (HPC-ls confirmed):
      images/{sid}_test.tif   where sid in training_01..training_20, test_01..test_08
      masks/{sid}_manual1.tif
    """
    root = tmp_path / 'CHASE'
    (root / 'images').mkdir(parents=True)
    (root / 'masks').mkdir(parents=True)

    # 20 training + 8 test = 28 images
    training_sids = _make_ids('training', list(range(1, 21)))  # training_01..training_20
    test_sids     = _make_ids('test',     list(range(1, 9)))   # test_01..test_08

    for sid in training_sids + test_sids:
        _write_rgb_tif(root / 'images' / f'{sid}_test.tif')
        _write_mask_tif(root / 'masks' / f'{sid}_manual1.tif')

    return root


@pytest.fixture
def synthetic_stare_root(tmp_path: Path) -> Path:
    """
    STARE layout (HPC-ls confirmed):
      images/{sid}.ppm   (plain PPM, 20 non-sequential IDs from _STARE_ALL_IDS)
      masks/{sid}.ah.ppm
    """
    root = tmp_path / 'STARE'
    (root / 'images').mkdir(parents=True)
    (root / 'masks').mkdir(parents=True)

    for sid in _STARE_ALL_IDS:
        _write_ppm(root / 'images' / f'{sid}.ppm', h=32, w=40)
        _write_ppm(root / 'masks'  / f'{sid}.ah.ppm', h=32, w=40)

    return root


@pytest.fixture
def synthetic_hrf_root(tmp_path: Path) -> Path:
    """
    HRF layout:
      images/{nn}_{cond}.jpg     (n=01..15, cond=h/dr/g)
      masks/{nn}_{cond}.tif
      roi_masks/{nn}_{cond}.tif
    """
    root = tmp_path / 'HRF'
    (root / 'images').mkdir(parents=True)
    (root / 'masks').mkdir(parents=True)
    (root / 'roi_masks').mkdir(parents=True)

    for n in range(1, 16):
        for cond in ('h', 'dr', 'g'):
            sid = f'{n:02d}_{cond}'
            _write_rgb_jpg(root / 'images'    / f'{sid}.jpg',  h=64, w=80)
            _write_mask_tif(root / 'masks'    / f'{sid}.tif',  h=64, w=80)
            _write_mask_tif(root / 'roi_masks'/ f'{sid}.tif',  h=64, w=80)

    return root


@pytest.fixture
def synthetic_fives_root(tmp_path: Path) -> Path:
    """
    FIVES flat layout (HPC-ls confirmed):
      images/train_<n>_<tag>.png   (600 training; use small subset here)
      images/test_<n>_<tag>.png    (200 test; distinct prefix)
      masks/train_<n>_<tag>.png
      masks/test_<n>_<tag>.png
    IDs are full stems. train_* and test_* prefixes enforce disjointness.
    """
    root = tmp_path / 'FIVES'
    (root / 'images').mkdir(parents=True)
    (root / 'masks').mkdir(parents=True)

    # 10 train + 4 test (small subset sufficient for tests)
    tags = ['A', 'D', 'G', 'N', 'V']  # FIVES uses condition tags
    for i in range(1, 11):
        tag = tags[i % len(tags)]
        stem = f'train_{i}_{tag}'
        _write_mask_png(root / 'images' / f'{stem}.png', h=64, w=64)
        _write_mask_png(root / 'masks'  / f'{stem}.png', h=64, w=64)

    for i in range(100, 104):  # test_ stems — distinct from train_ by prefix
        tag = tags[i % len(tags)]
        stem = f'test_{i}_{tag}'
        _write_mask_png(root / 'images' / f'{stem}.png', h=64, w=64)
        _write_mask_png(root / 'masks'  / f'{stem}.png', h=64, w=64)

    return root


# =========================================================================== #
#  Test 1: Split disjoint assertion
# =========================================================================== #

class TestSplitDisjoint:
    """TRAIN/VAL/TEST IDs must always be disjoint (RED LINE 1)."""

    def test_chase_split_disjoint(self, synthetic_chase_root):
        ds = CHASEDataset(str(synthetic_chase_root), split='train')
        train_s = set(ds.TRAIN_IDS)
        val_s   = set(ds.VAL_IDS)
        test_s  = set(ds.TEST_IDS)
        assert train_s.isdisjoint(test_s),  f'CHASE TRAIN ∩ TEST = {train_s & test_s}'
        assert val_s.isdisjoint(test_s),    f'CHASE VAL ∩ TEST   = {val_s & test_s}'
        assert train_s.isdisjoint(val_s),   f'CHASE TRAIN ∩ VAL  = {train_s & val_s}'

    def test_stare_split_disjoint(self, synthetic_stare_root):
        ds = STAREDataset(str(synthetic_stare_root), split='train')
        train_s = set(ds.TRAIN_IDS)
        val_s   = set(ds.VAL_IDS)
        test_s  = set(ds.TEST_IDS)
        assert train_s.isdisjoint(test_s)
        assert val_s.isdisjoint(test_s)
        assert train_s.isdisjoint(val_s)

    def test_hrf_split_disjoint(self, synthetic_hrf_root):
        ds = HRFDataset(str(synthetic_hrf_root), split='train')
        train_s = set(ds.TRAIN_IDS)
        val_s   = set(ds.VAL_IDS)
        test_s  = set(ds.TEST_IDS)
        assert train_s.isdisjoint(test_s),  f'HRF TRAIN ∩ TEST = {train_s & test_s}'
        assert val_s.isdisjoint(test_s),    f'HRF VAL ∩ TEST   = {val_s & test_s}'

    def test_fives_split_disjoint(self, synthetic_fives_root):
        ds = FIVESDataset(str(synthetic_fives_root), split='train')
        train_s = set(ds._train_ids)
        val_s   = set(ds._val_ids)
        test_s  = set(ds._test_ids)
        assert train_s.isdisjoint(test_s), f'FIVES TRAIN ∩ TEST = {train_s & test_s}'
        assert val_s.isdisjoint(test_s),   f'FIVES VAL ∩ TEST   = {val_s & test_s}'

    def test_base_bad_subclass_raises(self):
        """Subclass with overlapping TRAIN/TEST must raise AssertionError at init."""
        class BadDataset(BaseVesselDataset):
            TRAIN_IDS = [1, 2, 3]
            VAL_IDS   = [4, 5]
            TEST_IDS  = [3, 6]  # 3 is in both TRAIN and TEST

            def _img_path(self, sid): return Path('x')
            def _gt_path(self, sid):  return Path('x')
            def _mask_path(self, sid): return Path('x')

        with pytest.raises(AssertionError):
            BadDataset('/fake', skip_missing=True)


# =========================================================================== #
#  Test 2: __getitem__ shape and dict-key contract
# =========================================================================== #

class TestGetitemContract:
    """__getitem__ must return dict with image/gt/fov tensors of correct shape."""

    def _check_sample(self, sample, patch_size: int):
        img = sample['image']
        gt  = sample['gt']
        fov = sample['fov']
        assert isinstance(img, torch.Tensor), 'image must be Tensor'
        assert img.shape  == (1, patch_size, patch_size), f'image {img.shape}'
        assert gt.shape   == (1, patch_size, patch_size), f'gt {gt.shape}'
        assert fov.shape  == (1, patch_size, patch_size), f'fov {fov.shape}'
        assert img.dtype  == torch.float32
        assert gt.dtype   == torch.float32
        assert fov.dtype  == torch.float32
        assert set(gt.unique().tolist()).issubset({0.0, 1.0}), \
            f'GT has unexpected values: {gt.unique()}'
        assert set(fov.unique().tolist()).issubset({0.0, 1.0}), \
            f'FOV has unexpected values: {fov.unique()}'

    def test_chase_getitem_keys(self, synthetic_chase_root):
        ds = CHASEDataset(str(synthetic_chase_root), split='train', patch_size=32)
        sample = ds[0]
        assert set(sample.keys()) == {'image', 'gt', 'fov', 'id'}

    def test_chase_getitem_shape(self, synthetic_chase_root):
        ds = CHASEDataset(str(synthetic_chase_root), split='train',
                          patch_size=32, augment=False)
        self._check_sample(ds[0], 32)

    def test_chase_val_getitem_shape(self, synthetic_chase_root):
        ds = CHASEDataset(str(synthetic_chase_root), split='val',
                          patch_size=32, augment=False)
        assert len(ds) == 4
        self._check_sample(ds[0], 32)

    def test_chase_test_getitem_shape(self, synthetic_chase_root):
        """Test split __getitem__ for benchmark evaluation (RED LINE 1 — test only)."""
        ds = CHASEDataset(str(synthetic_chase_root), split='test',
                          patch_size=32, augment=False)
        assert len(ds) == 8
        self._check_sample(ds[0], 32)

    def test_stare_getitem_shape(self, synthetic_stare_root):
        ds = STAREDataset(str(synthetic_stare_root), split='train',
                          patch_size=32, augment=False)
        self._check_sample(ds[0], 32)

    def test_stare_test_getitem_shape(self, synthetic_stare_root):
        ds = STAREDataset(str(synthetic_stare_root), split='test',
                          patch_size=32, augment=False)
        assert len(ds) == 4
        self._check_sample(ds[0], 32)

    def test_hrf_getitem_shape(self, synthetic_hrf_root):
        ds = HRFDataset(str(synthetic_hrf_root), split='train',
                        patch_size=32, augment=False)
        self._check_sample(ds[0], 32)

    def test_fives_getitem_shape(self, synthetic_fives_root):
        ds = FIVESDataset(str(synthetic_fives_root), split='train',
                          patch_size=32, augment=False)
        assert len(ds) > 0
        self._check_sample(ds[0], 32)

    def test_fives_test_getitem_shape(self, synthetic_fives_root):
        ds = FIVESDataset(str(synthetic_fives_root), split='test',
                          patch_size=32, augment=False)
        assert len(ds) > 0
        self._check_sample(ds[0], 32)


# =========================================================================== #
#  Test 3: verify_no_leakage logic
# =========================================================================== #

class TestVerifyNoLeakage:
    def test_no_leakage_passes_chase(self, synthetic_chase_root):
        from datasets.verify_no_leakage import verify_dataset
        passed, report = verify_dataset('CHASE', CHASEDataset, str(synthetic_chase_root))
        assert passed, f'Expected PASS:\n{report}'

    def test_leakage_detected_at_init(self, tmp_path: Path):
        """
        A subclass with TRAIN ∩ TEST overlap must raise AssertionError at __init__.
        verify_no_leakage relies on BaseVesselDataset._check_split_disjoint as first
        line of defence; the ID-level check fires before file-path check.
        """
        class LeakyCHASE(CHASEDataset):
            # Override to create deliberate overlap
            TRAIN_IDS = ['training_01', 'training_02']
            VAL_IDS   = ['training_03']
            TEST_IDS  = ['training_02', 'test_01']  # training_02 in both TRAIN and TEST

        with pytest.raises(AssertionError):
            LeakyCHASE('/fake', skip_missing=True)


# =========================================================================== #
#  Test 4: FIVES dynamic ID discovery
# =========================================================================== #

class TestFIVESDiscovery:
    def test_discovers_train_test_ids(self, synthetic_fives_root):
        ds_train = FIVESDataset(str(synthetic_fives_root), split='train', skip_missing=True)
        ds_test  = FIVESDataset(str(synthetic_fives_root), split='test',  skip_missing=True)

        assert len(ds_train.ids) > 0, 'Should discover training IDs'
        assert len(ds_test.ids)  > 0, 'Should discover test IDs'

        train_set = set(ds_train._train_ids + ds_train._val_ids)
        test_set  = set(ds_test._test_ids)
        assert train_set.isdisjoint(test_set), \
            f'FIVES train ∩ test = {train_set & test_set}'

    def test_train_prefix_only_in_train(self, synthetic_fives_root):
        """All discovered train IDs start with 'train_'."""
        ds = FIVESDataset(str(synthetic_fives_root), split='train', skip_missing=True)
        for sid in ds._train_ids + ds._val_ids:
            assert sid.startswith('train_'), f'Non-train ID in training set: {sid}'

    def test_test_prefix_only_in_test(self, synthetic_fives_root):
        """All discovered test IDs start with 'test_'."""
        ds = FIVESDataset(str(synthetic_fives_root), split='test', skip_missing=True)
        for sid in ds._test_ids:
            assert sid.startswith('test_'), f'Non-test ID in test set: {sid}'

    def test_len_matches_discovered(self, synthetic_fives_root):
        ds = FIVESDataset(str(synthetic_fives_root), split='train', skip_missing=True)
        assert len(ds) == len(ds.ids)


# =========================================================================== #
#  Test 5: STARE PPM loading (plain + gzip)
# =========================================================================== #

class TestSTAREPPM:
    def test_plain_ppm_round_trip(self, tmp_path: Path):
        """Write plain .ppm, load via cv2 (STAREDataset path), check shape."""
        H, W = 16, 20
        img_rgb = np.random.randint(0, 255, (H, W, 3), dtype=np.uint8)
        header  = f'P6\n{W} {H}\n255\n'.encode('ascii')
        ppm_path = tmp_path / 'test.ppm'
        with open(str(ppm_path), 'wb') as f:
            f.write(header + img_rgb.tobytes())

        # cv2 can read PPM directly
        loaded = cv2.imread(str(ppm_path))
        assert loaded is not None, 'cv2 failed to read plain PPM'
        assert loaded.shape == (H, W, 3)

    def test_ppm_gz_round_trip(self, tmp_path: Path):
        """Write .ppm.gz, load via _load_ppm_gz, verify pixel values."""
        H, W = 16, 20
        img_rgb = np.random.randint(0, 255, (H, W, 3), dtype=np.uint8)
        header  = f'P6\n{W} {H}\n255\n'.encode('ascii')
        gz_path = tmp_path / 'test.ppm.gz'
        with gzip.open(str(gz_path), 'wb') as f:
            f.write(header + img_rgb.tobytes())

        loaded_bgr = _load_ppm_gz(gz_path)
        assert loaded_bgr.shape == (H, W, 3)
        loaded_rgb = loaded_bgr[:, :, ::-1]
        np.testing.assert_array_equal(loaded_rgb, img_rgb,
                                      err_msg='ppm.gz round-trip pixel mismatch')

    def test_stare_getitem_uses_ppm(self, synthetic_stare_root):
        """STAREDataset should load plain .ppm files from the Kaggle pack layout."""
        ds = STAREDataset(str(synthetic_stare_root), split='train',
                          patch_size=32, augment=False)
        sample = ds[0]
        assert sample['image'].shape == (1, 32, 32)
        assert sample['gt'].dtype == torch.float32


# =========================================================================== #
#  Test 6: precompute_benchmark schema
# =========================================================================== #

class TestPrecomputeBenchmark:
    def test_load_benchmark_sample_schema(self, tmp_path: Path):
        from datasets.precompute_benchmark import load_benchmark_sample
        from benchmark.synth_breaks import GapRecord

        H, W = 32, 32
        gaps = [GapRecord(gap_id=0, center_yx=(16, 16), radius=3,
                           gap_size=8, sigma=0.8,
                           segment_id_left=1, segment_id_right=2)]
        gap_json = json.dumps([asdict(g) for g in gaps]).encode('utf-8')

        npz_path = tmp_path / 'bench.npz'
        np.savez_compressed(
            str(npz_path),
            mask_broken        = np.zeros((H, W), dtype=np.uint8),
            vessel_segment_map = np.zeros((H, W), dtype=np.int32),
            gap_records_json   = np.frombuffer(gap_json, dtype=np.uint8),
            image_id           = np.array(['sid_01']),
            dataset            = np.array(['chase']),
            severity           = np.array(['Medium']),
            seed_used          = np.array([42]),
            original_shape     = np.array([H, W]),
        )

        sample = load_benchmark_sample(str(npz_path))
        required = {'mask_broken', 'vessel_segment_map', 'gaps',
                    'image_id', 'dataset', 'severity', 'seed_used', 'original_shape'}
        assert set(sample.keys()) == required
        assert sample['mask_broken'].shape == (H, W)
        assert len(sample['gaps']) == 1
        assert sample['gaps'][0]['gap_id'] == 0
        assert sample['image_id'] == 'sid_01'
        assert sample['severity'] == 'Medium'


# =========================================================================== #
#  Test 7: Tile extraction shape (get_tiles)
# =========================================================================== #

class TestTileExtraction:
    def test_get_tiles_shape(self, synthetic_hrf_root):
        ds = HRFDataset(str(synthetic_hrf_root), split='train', patch_size=None)
        sid = ds.ids[0]
        tiles = ds.get_tiles(sid, tile_size=32, overlap=0)

        assert len(tiles) > 0
        for tile in tiles:
            assert tile['image'].shape == (1, 32, 32), f"tile image {tile['image'].shape}"
            assert tile['gt'].shape    == (1, 32, 32), f"tile gt {tile['gt'].shape}"
            y0, x0, y1, x1 = tile['coords']
            assert y1 - y0 == 32 and x1 - x0 == 32

    def test_get_tiles_id_correct(self, synthetic_hrf_root):
        ds = HRFDataset(str(synthetic_hrf_root), split='test', patch_size=None)
        sid = ds.ids[0]
        tiles = ds.get_tiles(sid, tile_size=32, overlap=0)
        assert all(t['id'] == sid for t in tiles)

    def test_get_tiles_chase(self, synthetic_chase_root):
        ds = CHASEDataset(str(synthetic_chase_root), split='test', patch_size=None)
        sid = ds.ids[0]
        tiles = ds.get_tiles(sid, tile_size=32, overlap=0)
        assert len(tiles) > 0
        for t in tiles:
            assert t['image'].shape == (1, 32, 32)


# =========================================================================== #
#  Test 8: Full-image pad (patch_size=None)
# =========================================================================== #

class TestFullImagePad:
    def test_chase_fullimg_pad(self, synthetic_chase_root):
        ds = CHASEDataset(str(synthetic_chase_root), split='val',
                          patch_size=None, augment=False, pad_multiple=32)
        sample = ds[0]
        img = sample['image']
        assert img.ndim == 3 and img.shape[0] == 1
        assert img.shape[1] % 32 == 0, f'H not multiple of 32: {img.shape[1]}'
        assert img.shape[2] % 32 == 0, f'W not multiple of 32: {img.shape[2]}'

    def test_stare_fullimg_pad(self, synthetic_stare_root):
        ds = STAREDataset(str(synthetic_stare_root), split='val',
                          patch_size=None, augment=False, pad_multiple=32)
        sample = ds[0]
        img = sample['image']
        assert img.shape[1] % 32 == 0
        assert img.shape[2] % 32 == 0
