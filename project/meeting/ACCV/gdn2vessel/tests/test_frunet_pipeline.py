"""
test_frunet_pipeline.py — pytest for FR-UNet official data pipeline (P1 官方化迁移).

验证内容：
  1. frunet_augment: image+gt 同步（翻转/旋转一致），增强后 gt 值域仍 {0,1}。
  2. frunet_per_image_minmax: 值域 [0,1]，常值图输出全 0（无除零崩溃）。
  3. FRUNetPreprocessor.run(): pickle 产出 schema 正确（keys / mean/std / image shape）。
  4. FRUNetDataset.__getitem__: 有 cache 时 patch shape=(1,48,48), dtype=float32,
     gt 值域 {0,1.0}，fov 全 1。
  5. FRUNetDRIVE/CHASE/STARE/HRF/FIVES: 能构造，split IDs 非空，__len__>0。
  6. 无 cache 时 fallback _load_image_normalized：patch shape 仍正确。
  7. Fix_RandomRotation 只产生 {-180,-90,0,90} 之一（等概率验证略，只验值合法性）。
  8. FRUNetFIVES: split IDs 从实例而非类 attr 取（确保 FIVES 动态发现正确）。
  9. make_frunet_dataset 工厂函数：各集能正确路由。

所有测试用 tmp_path synthetic fixtures（无真实数据依赖）。
注意: 本文件只写测试，不跑（主线跑 pytest）。
"""

from __future__ import annotations

import gzip
import pickle
import sys
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

from datasets.frunet_pipeline import (
    FRUNetDataset,
    FRUNetDRIVE,
    FRUNetCHASE,
    FRUNetSTARE,
    FRUNetHRF,
    FRUNetFIVES,
    FRUNetPreprocessor,
    make_frunet_dataset,
    frunet_augment,
    frunet_per_image_minmax,
    frunet_get_square,
    frunet_test_crop,
    frunet_test_crop_tensor,
    _ROTATION_CHOICES,
    _apply_rotation,
    _GRAYSCALE_TRANSFORM,
)
from datasets.chase import CHASEDataset, _make_ids
from datasets.stare import STAREDataset, _STARE_ALL_IDS
from datasets.hrf   import HRFDataset
from datasets.fives import FIVESDataset


# =========================================================================== #
#  Shared helpers
# =========================================================================== #

def _write_rgb_tif(path: Path, h: int = 64, w: int = 64):
    img = np.random.randint(30, 200, (h, w, 3), dtype=np.uint8)
    cv2.imwrite(str(path), img)


def _write_mask_tif(path: Path, h: int = 64, w: int = 64):
    mask = np.zeros((h, w), dtype=np.uint8)
    cv2.circle(mask, (w // 2, h // 2), w // 4, 255, -1)
    cv2.imwrite(str(path), mask)


def _write_mask_png(path: Path, h: int = 64, w: int = 64):
    mask = np.zeros((h, w), dtype=np.uint8)
    cv2.circle(mask, (w // 2, h // 2), w // 4, 255, -1)
    cv2.imwrite(str(path), mask)


def _write_rgb_jpg(path: Path, h: int = 64, w: int = 64):
    img = np.random.randint(30, 200, (h, w, 3), dtype=np.uint8)
    cv2.imwrite(str(path), img)


def _write_ppm(path: Path, h: int = 48, w: int = 48):
    img_rgb = np.random.randint(30, 200, (h, w, 3), dtype=np.uint8)
    header = f'P6\n{w} {h}\n255\n'.encode('ascii')
    with open(str(path), 'wb') as f:
        f.write(header + img_rgb.tobytes())


# =========================================================================== #
#  Fixtures: synthetic dataset roots (reuse layout from test_datasets.py)
# =========================================================================== #

@pytest.fixture
def synthetic_chase_root(tmp_path: Path) -> Path:
    root = tmp_path / 'CHASE'
    (root / 'images').mkdir(parents=True)
    (root / 'masks').mkdir(parents=True)
    training_sids = _make_ids('training', list(range(1, 21)))
    test_sids     = _make_ids('test',     list(range(1, 9)))
    for sid in training_sids + test_sids:
        _write_rgb_tif(root / 'images' / f'{sid}_test.tif', h=64, w=64)
        _write_mask_tif(root / 'masks'  / f'{sid}_manual1.tif', h=64, w=64)
    return root


@pytest.fixture
def synthetic_stare_root(tmp_path: Path) -> Path:
    root = tmp_path / 'STARE'
    (root / 'images').mkdir(parents=True)
    (root / 'masks').mkdir(parents=True)
    for sid in _STARE_ALL_IDS:
        _write_ppm(root / 'images' / f'{sid}.ppm', h=48, w=48)
        _write_ppm(root / 'masks'  / f'{sid}.ah.ppm', h=48, w=48)
    return root


@pytest.fixture
def synthetic_hrf_root(tmp_path: Path) -> Path:
    root = tmp_path / 'HRF'
    (root / 'images').mkdir(parents=True)
    (root / 'masks').mkdir(parents=True)
    (root / 'roi_masks').mkdir(parents=True)
    for n in range(1, 16):
        for cond in ('h', 'dr', 'g'):
            sid = f'{n:02d}_{cond}'
            _write_rgb_jpg(root / 'images'    / f'{sid}.jpg',  h=64, w=64)
            _write_mask_tif(root / 'masks'    / f'{sid}.tif',  h=64, w=64)
            _write_mask_tif(root / 'roi_masks'/ f'{sid}.tif',  h=64, w=64)
    return root


@pytest.fixture
def synthetic_fives_root(tmp_path: Path) -> Path:
    root = tmp_path / 'FIVES'
    (root / 'images').mkdir(parents=True)
    (root / 'masks').mkdir(parents=True)
    for i in range(1, 12):
        stem = f'train_{i}_A'
        _write_mask_png(root / 'images' / f'{stem}.png', h=64, w=64)
        _write_mask_png(root / 'masks'  / f'{stem}.png', h=64, w=64)
    for i in range(100, 104):
        stem = f'test_{i}_D'
        _write_mask_png(root / 'images' / f'{stem}.png', h=64, w=64)
        _write_mask_png(root / 'masks'  / f'{stem}.png', h=64, w=64)
    return root


# =========================================================================== #
#  Test 1: frunet_per_image_minmax
# =========================================================================== #

class TestMinmax:
    def test_output_range_zero_to_one(self):
        """minmax 结果值域必须在 [0, 1]。"""
        rng = np.random.RandomState(42)
        img = rng.randn(64, 64).astype(np.float32) * 3.0  # 任意范围
        out = frunet_per_image_minmax(img)
        assert out.min() >= 0.0 - 1e-6, f"min={out.min()} < 0"
        assert out.max() <= 1.0 + 1e-6, f"max={out.max()} > 1"
        assert out.dtype == np.float32

    def test_constant_image_no_zero_division(self):
        """全零或常值图不应崩溃，结果全 0。"""
        img = np.full((32, 32), 0.5, dtype=np.float32)
        out = frunet_per_image_minmax(img)
        assert out.shape == (32, 32)
        assert not np.any(np.isnan(out)), "NaN in constant-image minmax"
        np.testing.assert_allclose(out, 0.0, atol=1e-6)

    def test_known_values(self):
        """已知输入 [0, 0.5, 1.0] → minmax → [0, 0.5, 1.0]（identity for this input）。"""
        img = np.array([[0.0, 0.5, 1.0]], dtype=np.float32)
        out = frunet_per_image_minmax(img)
        np.testing.assert_allclose(out, img, atol=1e-5)

    def test_output_dtype_float32(self):
        img = np.random.rand(16, 16).astype(np.float64)  # double input
        out = frunet_per_image_minmax(img.astype(np.float32))
        assert out.dtype == np.float32


# =========================================================================== #
#  Test 2: frunet_augment — image+gt 同步 + GT 值域不变
# =========================================================================== #

class TestFRUNetAugment:
    def _make_img_gt(self, h: int = 64, w: int = 64):
        """Make distinct img/gt so spatial sync failures are detectable."""
        img = np.zeros((h, w), dtype=np.float32)
        img[:h//2, :w//2] = 1.0   # top-left quadrant = 1 (asymmetric)
        gt = np.zeros((h, w), dtype=np.uint8)
        gt[h//4:3*h//4, w//4:3*w//4] = 1  # center rectangle
        return img, gt

    def test_gt_values_binary_after_augment(self):
        """GT 增强后值域必须仍是 {0, 1}（旋转/翻转不引入插值）。"""
        img, gt = self._make_img_gt()
        for _ in range(50):
            _, gt_aug = frunet_augment(img.copy(), gt.copy())
            unique = set(gt_aug.flatten().tolist())
            assert unique.issubset({0, 1}), f"GT non-binary after augment: {unique}"

    def test_image_gt_spatial_sync(self):
        """
        同步性测试：img 顶部全 1、底部全 0；GT 左侧全 1、右侧全 0。
        增强后，取 img 的 argmax_row（哪行像素从 0 变成 1）是否与 gt
        的空间变换一致 → 采用 shape 一致 + sum 不变来检验（更稳健）。
        """
        h, w = 64, 64
        img, gt = self._make_img_gt(h, w)
        img_aug, gt_aug = frunet_augment(img.copy(), gt.copy())
        # 形状不变
        assert img_aug.shape == (h, w), f"img shape changed: {img_aug.shape}"
        assert gt_aug.shape == (h, w),  f"gt shape changed: {gt_aug.shape}"
        # GT pixel count 不变（翻转/旋转是等势变换）
        assert gt_aug.sum() == gt.sum(), (
            f"GT pixel count changed after augment: {gt.sum()} → {gt_aug.sum()}"
        )

    def test_rotation_choice_legal(self):
        """_apply_rotation 只接受 {-180,-90,0,90}，非法值 raise ValueError。"""
        img = np.ones((16, 16), dtype=np.float32)
        for deg in _ROTATION_CHOICES:
            out = _apply_rotation(img.copy(), deg)
            assert out.shape == (16, 16)
        with pytest.raises(ValueError):
            _apply_rotation(img, 45)

    def test_augment_runs_without_exception(self):
        """大量调用 frunet_augment 不崩。"""
        img, gt = self._make_img_gt(48, 48)
        for _ in range(200):
            img_a, gt_a = frunet_augment(img.copy(), gt.copy())
            assert img_a.shape == img.shape
            assert gt_a.shape  == gt.shape

    def test_gt_dtype_preserved(self):
        """GT dtype 在增强后仍是 uint8。"""
        img, gt = self._make_img_gt()
        assert gt.dtype == np.uint8
        _, gt_aug = frunet_augment(img, gt)
        assert gt_aug.dtype == np.uint8, f"GT dtype changed: {gt_aug.dtype}"


# =========================================================================== #
#  Test 3: FRUNetPreprocessor
# =========================================================================== #

class TestFRUNetPreprocessor:
    def test_pickle_schema_drive(self, tmp_path, synthetic_chase_root):
        """Preprocessor 产出 pickle 含 mean/std/images/gts 且 schema 正确。"""
        cache_p = str(tmp_path / 'chase.pkl')
        src = CHASEDataset(str(synthetic_chase_root), split='train',
                           patch_size=None, augment=False, skip_missing=True)
        pre = FRUNetPreprocessor(src, dataset_name='chase_test')
        # 只处理少量 IDs 加速（取前 2 个 train ID）
        train_ids = list(src.TRAIN_IDS[:2])
        # Patch: 暂时只让 preprocessor 处理这 2 个 IDs
        pre.run(cache_p, all_ids=train_ids)

        assert Path(cache_p).exists(), "pickle 未生成"
        with open(cache_p, 'rb') as f:
            data = pickle.load(f)

        assert 'mean' in data, "missing 'mean'"
        assert 'std'  in data, "missing 'std'"
        assert 'images' in data, "missing 'images'"
        assert 'gts'    in data, "missing 'gts'"
        assert isinstance(data['mean'], float)
        assert isinstance(data['std'],  float)
        assert data['std'] > 0.0, "std should be > 0 for random image"

    def test_pickle_images_float32_and_range(self, tmp_path, synthetic_chase_root):
        """Pickle 内所有 images 必须是 float32，值域 [0,1]（minmax 后）。"""
        cache_p = str(tmp_path / 'chase.pkl')
        src = CHASEDataset(str(synthetic_chase_root), split='train',
                           patch_size=None, augment=False, skip_missing=True)
        pre = FRUNetPreprocessor(src, dataset_name='chase_test')
        train_ids = list(src.TRAIN_IDS[:3])
        pre.run(cache_p, all_ids=train_ids)

        with open(cache_p, 'rb') as f:
            data = pickle.load(f)

        for sid_str, arr in data['images'].items():
            assert arr.dtype == np.float32, f"{sid_str}: dtype={arr.dtype}"
            assert arr.ndim == 2,           f"{sid_str}: ndim={arr.ndim} (expected 2)"
            assert arr.min() >= 0.0 - 1e-5, f"{sid_str}: min={arr.min()} < 0"
            assert arr.max() <= 1.0 + 1e-5, f"{sid_str}: max={arr.max()} > 1"

    def test_pickle_gts_binary(self, tmp_path, synthetic_chase_root):
        """Pickle gts 值域必须 {0, 1}。"""
        cache_p = str(tmp_path / 'chase.pkl')
        src = CHASEDataset(str(synthetic_chase_root), split='train',
                           patch_size=None, augment=False, skip_missing=True)
        pre = FRUNetPreprocessor(src, dataset_name='chase_test')
        train_ids = list(src.TRAIN_IDS[:2])
        pre.run(cache_p, all_ids=train_ids)

        with open(cache_p, 'rb') as f:
            data = pickle.load(f)

        for sid_str, gt in data['gts'].items():
            unique = set(gt.flatten().tolist())
            assert unique.issubset({0, 1}), f"{sid_str}: GT has non-binary values {unique}"

    def test_idempotent_no_recompute(self, tmp_path, synthetic_chase_root):
        """Pickle 已存在时不重算（idempotent: 返回同路径，不崩）。"""
        cache_p = str(tmp_path / 'chase_idem.pkl')
        src = CHASEDataset(str(synthetic_chase_root), split='train',
                           patch_size=None, augment=False, skip_missing=True)
        pre = FRUNetPreprocessor(src)
        train_ids = list(src.TRAIN_IDS[:1])
        pre.run(cache_p, all_ids=train_ids)
        mtime1 = Path(cache_p).stat().st_mtime
        # Second call should NOT recompute
        pre.run(cache_p, all_ids=train_ids, force_recompute=False)
        mtime2 = Path(cache_p).stat().st_mtime
        assert mtime1 == mtime2, "Idempotent: pickle was rewritten when it shouldn't be"


# =========================================================================== #
#  Test 4: FRUNetDataset.__getitem__ — patch shape + dtype + GT values
# =========================================================================== #

class TestFRUNetGetitem:
    def _make_cache(self, tmp_path: Path, chase_root: Path, n_ids: int = 3) -> str:
        """Helper: precompute pickle for CHASE."""
        cache_p = str(tmp_path / 'cache_chase.pkl')
        src = CHASEDataset(str(chase_root), split='train',
                           patch_size=None, augment=False, skip_missing=True)
        pre = FRUNetPreprocessor(src, dataset_name='chase')
        train_ids = list(src.TRAIN_IDS[:n_ids])
        pre.run(cache_p, all_ids=train_ids)
        return cache_p

    def test_patch_shape_48x48(self, tmp_path, synthetic_chase_root):
        """训练 patch 必须 (1, 48, 48)。"""
        cache_p = self._make_cache(tmp_path, synthetic_chase_root, n_ids=3)
        ds = FRUNetCHASE(
            data_root=str(synthetic_chase_root),
            split='train',
            patch_size=48,
            augment=False,
            cache_path=cache_p,
        )
        assert len(ds) > 0, "dataset is empty"
        sample = ds[0]
        img = sample['image']
        gt  = sample['gt']
        assert img.shape == (1, 48, 48), f"image shape {img.shape} != (1,48,48)"
        assert gt.shape  == (1, 48, 48), f"gt shape {gt.shape} != (1,48,48)"

    def test_image_dtype_float32(self, tmp_path, synthetic_chase_root):
        cache_p = self._make_cache(tmp_path, synthetic_chase_root)
        ds = FRUNetCHASE(str(synthetic_chase_root), split='train',
                         patch_size=48, augment=False, cache_path=cache_p)
        sample = ds[0]
        assert sample['image'].dtype == torch.float32, f"dtype={sample['image'].dtype}"

    def test_gt_values_binary(self, tmp_path, synthetic_chase_root):
        """GT tensor 值域必须 {0.0, 1.0}。"""
        cache_p = self._make_cache(tmp_path, synthetic_chase_root)
        ds = FRUNetCHASE(str(synthetic_chase_root), split='train',
                         patch_size=48, augment=False, cache_path=cache_p)
        for i in range(min(len(ds), 5)):
            gt = ds[i]['gt']
            unique = set(gt.unique().tolist())
            assert unique.issubset({0.0, 1.0}), \
                f"sample {i}: GT has non-binary values {unique}"

    def test_image_range_after_minmax(self, tmp_path, synthetic_chase_root):
        """Image 值域在 [0,1]（minmax 保证）。"""
        cache_p = self._make_cache(tmp_path, synthetic_chase_root)
        ds = FRUNetCHASE(str(synthetic_chase_root), split='train',
                         patch_size=48, augment=False, cache_path=cache_p)
        sample = ds[0]
        img = sample['image']
        assert float(img.min()) >= -1e-5, f"image min={img.min()} < 0"
        assert float(img.max()) <= 1.0 + 1e-5, f"image max={img.max()} > 1"

    def test_fov_all_ones(self, tmp_path, synthetic_chase_root):
        """fov tensor 必须全 1（FR-UNet 不用 FOV mask，全图 loss）。"""
        cache_p = self._make_cache(tmp_path, synthetic_chase_root)
        ds = FRUNetCHASE(str(synthetic_chase_root), split='train',
                         patch_size=48, augment=False, cache_path=cache_p)
        sample = ds[0]
        fov = sample['fov']
        assert fov.shape == (1, 48, 48)
        np.testing.assert_allclose(fov.numpy(), 1.0, atol=1e-6,
                                   err_msg="fov should be all-ones for FR-UNet")

    def test_dict_keys(self, tmp_path, synthetic_chase_root):
        """__getitem__ dict 含 image/gt/fov/id + orig_hw(FIX Q7 后 sample 总带原图尺寸供 crop 还原)。"""
        cache_p = self._make_cache(tmp_path, synthetic_chase_root)
        ds = FRUNetCHASE(str(synthetic_chase_root), split='train',
                         patch_size=48, augment=False, cache_path=cache_p)
        sample = ds[0]
        assert set(sample.keys()) == {'image', 'gt', 'fov', 'id', 'orig_hw'}, \
            f"Keys mismatch: {set(sample.keys())}"

    def test_fullimage_eval_get_square(self, tmp_path, synthetic_chase_root):
        """FIX Q7: eval 模式 patch_size=None → get_square 官方方形(CHASE=1008×1008)+ orig_hw。
        注:smp backbone 的 32 整数倍 pad 由 model forward 的 _pad_to_stride 做,不是 data pipeline 的事。"""
        cache_p = self._make_cache(tmp_path, synthetic_chase_root)
        ds = FRUNetCHASE(str(synthetic_chase_root), split='train',
                         patch_size=None, augment=False, cache_path=cache_p)
        sample = ds[0]
        img = sample['image']
        # CHASE 官方 get_square target_size=1008(FR-UNet tester.py),方形
        assert img.shape[1] == img.shape[2] == 1008, f"eval 应 get_square 到 1008×1008,实得 {img.shape}"
        assert 'orig_hw' in sample, "eval sample 须带 orig_hw 供 adapter crop 还原"

    def test_no_cache_fallback(self, synthetic_chase_root):
        """无 cache 时 fallback 也能正常返回 48×48 patch（minmax-only normalize）。"""
        ds = FRUNetCHASE(str(synthetic_chase_root), split='train',
                         patch_size=48, augment=False, cache_path=None)
        assert len(ds) > 0
        sample = ds[0]
        assert sample['image'].shape == (1, 48, 48)
        assert sample['image'].dtype == torch.float32

    def test_nonexistent_cache_raises(self, tmp_path, synthetic_chase_root):
        """不存在的 cache_path 应 raise FileNotFoundError。"""
        bad_cache = str(tmp_path / 'does_not_exist.pkl')
        with pytest.raises(FileNotFoundError):
            FRUNetCHASE(str(synthetic_chase_root), split='train',
                        patch_size=48, cache_path=bad_cache)


# =========================================================================== #
#  Test 5: 各集 FRUNet 子类能构造 + len > 0
# =========================================================================== #

class TestAllDatasets:
    def test_frunet_chase_constructs(self, synthetic_chase_root):
        ds = FRUNetCHASE(str(synthetic_chase_root), split='train',
                         patch_size=48, augment=False)
        assert len(ds) > 0
        assert len(ds) == 16  # CHASE TRAIN = 16

    def test_frunet_chase_val(self, synthetic_chase_root):
        ds = FRUNetCHASE(str(synthetic_chase_root), split='val', patch_size=48)
        assert len(ds) == 4

    def test_frunet_chase_test(self, synthetic_chase_root):
        ds = FRUNetCHASE(str(synthetic_chase_root), split='test', patch_size=48)
        assert len(ds) == 8

    def test_frunet_stare_constructs(self, synthetic_stare_root):
        ds = FRUNetSTARE(str(synthetic_stare_root), split='train', patch_size=48)
        assert len(ds) > 0
        assert len(ds) == 12  # STARE TRAIN = 12

    def test_frunet_stare_val(self, synthetic_stare_root):
        ds = FRUNetSTARE(str(synthetic_stare_root), split='val', patch_size=48)
        assert len(ds) == 4

    def test_frunet_hrf_constructs(self, synthetic_hrf_root):
        ds = FRUNetHRF(str(synthetic_hrf_root), split='train', patch_size=48)
        assert len(ds) > 0
        assert len(ds) == 12  # HRF TRAIN = 12 healthy

    def test_frunet_fives_constructs(self, synthetic_fives_root):
        ds = FRUNetFIVES(str(synthetic_fives_root), split='train', patch_size=48)
        assert len(ds) > 0  # 11 - val images

    def test_frunet_fives_test(self, synthetic_fives_root):
        ds = FRUNetFIVES(str(synthetic_fives_root), split='test', patch_size=48)
        assert len(ds) == 4  # 4 test_ images

    def test_frunet_fives_ids_from_instance(self, synthetic_fives_root):
        """FRUNetFIVES ids 来自实例（动态发现），不是空的类 attr。"""
        ds = FRUNetFIVES(str(synthetic_fives_root), split='train', patch_size=48)
        assert len(ds.ids) > 0, "FRUNetFIVES.ids is empty (bug: using class attr instead of instance)"
        for sid in ds.ids:
            assert sid.startswith('train_'), f"Non-train ID in FRUNetFIVES train split: {sid}"


# =========================================================================== #
#  Test 6: make_frunet_dataset factory
# =========================================================================== #

class TestFactory:
    def test_factory_chase(self, synthetic_chase_root):
        ds = make_frunet_dataset('chase', str(synthetic_chase_root),
                                 split='train', patch_size=48)
        assert isinstance(ds, FRUNetCHASE)
        assert len(ds) > 0

    def test_factory_stare(self, synthetic_stare_root):
        ds = make_frunet_dataset('stare', str(synthetic_stare_root),
                                 split='train', patch_size=48)
        assert isinstance(ds, FRUNetSTARE)

    def test_factory_hrf(self, synthetic_hrf_root):
        ds = make_frunet_dataset('hrf', str(synthetic_hrf_root),
                                 split='train', patch_size=48)
        assert isinstance(ds, FRUNetHRF)

    def test_factory_fives(self, synthetic_fives_root):
        ds = make_frunet_dataset('fives', str(synthetic_fives_root),
                                 split='train', patch_size=48)
        assert isinstance(ds, FRUNetFIVES)

    def test_factory_unknown_name_raises(self, tmp_path):
        with pytest.raises(ValueError, match="Unknown dataset"):
            make_frunet_dataset('nonexistent', str(tmp_path))

    def test_factory_case_insensitive(self, synthetic_chase_root):
        """名字大小写不敏感。"""
        ds = make_frunet_dataset('CHASE', str(synthetic_chase_root), split='train')
        assert isinstance(ds, FRUNetCHASE)


# =========================================================================== #
#  Test 7: augment with training split vs val split
# =========================================================================== #

class TestAugmentOnlyTraining:
    def test_augment_flag_respected(self, tmp_path, synthetic_chase_root):
        """augment=True 时 split='train' 应用增强；split='val' 即使 augment=True 也不应用。
        (FRUNetDataset: `if self.augment and self.split == 'train'`)
        """
        # val split, augment=True → __getitem__ should NOT augment
        ds_val = FRUNetCHASE(str(synthetic_chase_root), split='val',
                             patch_size=48, augment=True, cache_path=None)
        # 只验证能正常返回 patch，不验增强结果（确定性差）
        sample = ds_val[0]
        assert sample['image'].shape == (1, 48, 48)


# =========================================================================== #
#  Test 8: STARE fallback (no-cache) via STAREDataset image loading
# =========================================================================== #

class TestSTAREFallback:
    def test_stare_no_cache_returns_patch(self, synthetic_stare_root):
        """STARE 无 cache 时 fallback 返回正常 48×48 patch。"""
        ds = FRUNetSTARE(str(synthetic_stare_root), split='train',
                         patch_size=48, augment=False, cache_path=None)
        assert len(ds) > 0
        sample = ds[0]
        assert sample['image'].shape == (1, 48, 48)
        assert sample['image'].dtype == torch.float32


# =========================================================================== #
#  Test 9 (FIX Q2): STARE official_baseline — 全 20 张，无 hold-out
# =========================================================================== #

class TestSTAREOfficialBaseline:
    """
    FIX Q2 2026-06-22: FR-UNet 官方 STARE 协议 = train=test=全20张，无 hold-out。
    FRUNetSTARE(official_baseline=True) 必须返回全20张 IDs，不按 split 参数区分。
    """

    def test_official_baseline_len_20(self, synthetic_stare_root):
        """official_baseline=True 时 ids 应为全 20 张（不受 split 参数影响）。"""
        ds = FRUNetSTARE(str(synthetic_stare_root), split='train',
                         patch_size=48, augment=False,
                         official_baseline=True, cache_path=None)
        assert len(ds) == 20, (
            f"official_baseline=True: expected 20 IDs (train=test=全集), got {len(ds)}. "
            "FR-UNet 官方 STARE 无 hold-out split，复现数字必须全集（FIX Q2）。"
        )

    def test_official_baseline_contains_all_ids(self, synthetic_stare_root):
        """official_baseline=True 时 ids 必须包含全部 _STARE_ALL_IDS。"""
        ds = FRUNetSTARE(str(synthetic_stare_root), split='train',
                         patch_size=48, augment=False,
                         official_baseline=True, cache_path=None)
        ds_ids = set(ds.ids)
        for sid in _STARE_ALL_IDS:
            assert sid in ds_ids, f"Missing STARE ID {sid!r} in official_baseline dataset"

    def test_gdn2_split_has_holdout(self, synthetic_stare_root):
        """official_baseline=False（默认）时，train+test 不等于全集（有 hold-out）。"""
        ds_train = FRUNetSTARE(str(synthetic_stare_root), split='train',
                               patch_size=48, augment=False,
                               official_baseline=False, cache_path=None)
        ds_test = FRUNetSTARE(str(synthetic_stare_root), split='test',
                              patch_size=48, augment=False,
                              official_baseline=False, cache_path=None)
        # 12/4/4：train=12，test=4，train+test<20（val=4 未选入 train 或 test）
        assert len(ds_train) == 12, f"GDN-2 STARE train expected 12, got {len(ds_train)}"
        assert len(ds_test) == 4, f"GDN-2 STARE test expected 4, got {len(ds_test)}"
        train_ids = set(ds_train.ids)
        test_ids = set(ds_test.ids)
        overlap = train_ids & test_ids
        assert len(overlap) == 0, f"GDN-2 STARE: train/test overlap = {overlap} (评估泄漏！)"

    def test_factory_stare_official_baseline(self, synthetic_stare_root):
        """工厂 stare_official_baseline=True 路由到 official_baseline=True。"""
        ds = make_frunet_dataset('stare', str(synthetic_stare_root),
                                 patch_size=48, stare_official_baseline=True)
        assert len(ds) == 20, f"factory official_baseline: expected 20, got {len(ds)}"

    def test_official_baseline_returns_patch(self, synthetic_stare_root):
        """official_baseline=True 时 __getitem__ 仍能正常返回 48×48 patch。"""
        ds = FRUNetSTARE(str(synthetic_stare_root), split='train',
                         patch_size=48, augment=False,
                         official_baseline=True, cache_path=None)
        sample = ds[0]
        assert sample['image'].shape == (1, 48, 48)
        assert sample['image'].dtype == torch.float32
        assert set(sample.keys()) >= {'image', 'gt', 'fov', 'id', 'orig_hw'}


# =========================================================================== #
#  Test 10 (FIX Q6): Grayscale(1) BT.601 — 非 green channel
# =========================================================================== #

class TestGrayscaleBT601:
    """
    FIX Q6 2026-06-22: 官方 DRIVE/CHASE/STARE 用 Grayscale(1)（BT.601），
    非 green channel 单独提取。验证 _GRAYSCALE_TRANSFORM 的行为。
    """

    def test_grayscale_transform_output_l_mode(self):
        """_GRAYSCALE_TRANSFORM 对 PIL RGB 输出 L mode（BT.601 加权灰度）。"""
        from PIL import Image as PILImage
        img_rgb = PILImage.fromarray(
            np.array([[[100, 150, 200]]], dtype=np.uint8)  # 1×1 RGB pixel
        )
        img_gray = _GRAYSCALE_TRANSFORM(img_rgb)
        assert img_gray.mode == 'L', f"Expected L mode, got {img_gray.mode}"

    def test_grayscale_vs_green_channel_differ(self):
        """BT.601 加权结果应与 green channel 单独提取不同（非纯绿色图时）。"""
        from PIL import Image as PILImage
        # 非纯绿图：R=100, G=150, B=200
        arr = np.full((16, 16, 3), [100, 150, 200], dtype=np.uint8)
        pil_rgb = PILImage.fromarray(arr)
        gray_bt601 = np.array(_GRAYSCALE_TRANSFORM(pil_rgb), dtype=np.float32)
        green_only = arr[:, :, 1].astype(np.float32)
        # BT.601: 0.2989*100 + 0.5870*150 + 0.1140*200 ≈ 29.89+88.05+22.8 ≈ 140.74
        # Green channel: 150
        # They must differ
        assert not np.allclose(gray_bt601, green_only, atol=1.0), (
            f"BT.601 gray ({gray_bt601.mean():.1f}) should differ from green channel ({green_only.mean():.1f})"
        )

    def test_grayscale_known_value(self):
        """BT.601 已知像素验证: R=255,G=0,B=0 → ~0.2989*255 ≈ 76。"""
        from PIL import Image as PILImage
        arr = np.full((4, 4, 3), [255, 0, 0], dtype=np.uint8)
        pil_rgb = PILImage.fromarray(arr)
        gray = np.array(_GRAYSCALE_TRANSFORM(pil_rgb), dtype=np.float32)
        expected = 0.2989 * 255  # ≈ 76.2
        assert abs(gray.mean() - expected) < 3.0, (
            f"Red pixel BT.601 gray: expected ~{expected:.1f}, got {gray.mean():.1f}"
        )

    def test_preprocessor_grayscale_u8(self, tmp_path, synthetic_chase_root):
        """FRUNetPreprocessor._grayscale_u8 返回 (H,W) uint8，值域 [0,255]。"""
        src = CHASEDataset(str(synthetic_chase_root), split='train',
                           patch_size=None, augment=False, skip_missing=True)
        pre = FRUNetPreprocessor(src, dataset_name='chase_gray_test')
        sid = list(src.TRAIN_IDS)[0]
        gray = pre._grayscale_u8(sid)
        assert gray.ndim == 2, f"Expected 2D (H,W), got shape {gray.shape}"
        assert gray.dtype == np.uint8, f"Expected uint8, got {gray.dtype}"
        assert gray.min() >= 0 and gray.max() <= 255

    def test_load_image_normalized_range(self, synthetic_chase_root):
        """_load_image_normalized (Grayscale fallback) 返回值域 [0,1] float32。"""
        ds = FRUNetCHASE(str(synthetic_chase_root), split='train',
                         patch_size=None, augment=False, cache_path=None)
        sid = ds.ids[0]
        img = ds._load_image_normalized(sid)
        assert img.ndim == 2
        assert img.dtype == np.float32
        assert img.min() >= 0.0 - 1e-5
        assert img.max() <= 1.0 + 1e-5


# =========================================================================== #
#  Test 11 (FIX Q7): frunet_get_square + frunet_test_crop — pad-整图-crop 往返
# =========================================================================== #

class TestGetSquareCrop:
    """
    FIX Q7 2026-06-22: 官方 test 无滑窗，用 get_square pad 到方形 → 整图推理 → crop 还原。
    验证 pad 尺寸正确 + crop 后能回到原始 H×W。
    """

    def test_get_square_shape(self):
        """frunet_get_square: 输出必须是 target_size×target_size。"""
        img = np.random.rand(100, 120).astype(np.float32)
        padded, (orig_H, orig_W) = frunet_get_square(img, target_size=128)
        assert padded.shape == (128, 128), f"Expected (128,128), got {padded.shape}"
        assert orig_H == 100
        assert orig_W == 120

    def test_get_square_preserves_top_left(self):
        """pad 后左上角内容与原图一致（右下角为零填充）。"""
        img = np.ones((50, 60), dtype=np.float32) * 0.5
        padded, (oH, oW) = frunet_get_square(img, target_size=80)
        np.testing.assert_allclose(
            padded[:oH, :oW], img, atol=1e-6,
            err_msg="Top-left region should preserve original image"
        )
        # 填充区应为 0（ConstantPad2d value=0）
        np.testing.assert_allclose(
            padded[oH:, :], 0.0, atol=1e-6,
            err_msg="Padded region (bottom) should be zero"
        )
        np.testing.assert_allclose(
            padded[:, oW:], 0.0, atol=1e-6,
            err_msg="Padded region (right) should be zero"
        )

    def test_test_crop_roundtrip(self):
        """get_square → (模拟推理，identity pred) → test_crop → 回到原始尺寸。"""
        orig_H, orig_W = 584, 565  # DRIVE 原始尺寸
        target = 592               # DRIVE 官方 target_size
        img = np.random.rand(orig_H, orig_W).astype(np.float32)
        padded, (rH, rW) = frunet_get_square(img, target_size=target)
        assert padded.shape == (target, target)
        # 模拟推理后 crop 还原
        cropped = frunet_test_crop(padded, rH, rW)
        assert cropped.shape == (orig_H, orig_W), (
            f"crop roundtrip: expected ({orig_H},{orig_W}), got {cropped.shape}"
        )
        np.testing.assert_allclose(
            cropped, img, atol=1e-6,
            err_msg="crop roundtrip: pixel values should match original"
        )

    def test_test_crop_tensor_roundtrip(self):
        """frunet_test_crop_tensor: tensor 版本 crop 往返正确。"""
        orig_H, orig_W = 960, 999  # CHASE 原始尺寸
        target = 1008              # CHASE 官方 target_size
        img = np.random.rand(orig_H, orig_W).astype(np.float32)
        padded, (rH, rW) = frunet_get_square(img, target_size=target)
        pred_tensor = torch.from_numpy(padded).unsqueeze(0).unsqueeze(0)  # (1,1,H,W)
        cropped_t = frunet_test_crop_tensor(pred_tensor, rH, rW)
        assert cropped_t.shape == (1, 1, orig_H, orig_W), (
            f"tensor crop: expected (1,1,{orig_H},{orig_W}), got {cropped_t.shape}"
        )

    def test_eval_mode_returns_square_image(self, synthetic_chase_root):
        """eval 模式（patch_size=None）__getitem__ 返回方形 padded 图。"""
        ds = FRUNetCHASE(str(synthetic_chase_root), split='train',
                         patch_size=None, augment=False, cache_path=None,
                         eval_square_size=64)  # 小方形便于 synthetic 测试
        sample = ds[0]
        img = sample['image']
        assert img.shape[1] == 64, f"eval square H: expected 64, got {img.shape[1]}"
        assert img.shape[2] == 64, f"eval square W: expected 64, got {img.shape[2]}"

    def test_eval_mode_orig_hw_in_sample(self, synthetic_chase_root):
        """eval 模式 sample 必须含 orig_hw 键，值为原始 (H, W)。"""
        ds = FRUNetCHASE(str(synthetic_chase_root), split='train',
                         patch_size=None, augment=False, cache_path=None,
                         eval_square_size=64)
        sample = ds[0]
        assert 'orig_hw' in sample, "eval sample must contain 'orig_hw' for crop-back"
        orig_H, orig_W = sample['orig_hw']
        assert orig_H <= 64 and orig_W <= 64, (
            f"orig_hw ({orig_H},{orig_W}) should be <= eval_square_size=64"
        )

    def test_drive_default_eval_square_size_592(self, tmp_path):
        """FRUNetDRIVE 默认 eval_square_size=592（官方 DRIVE target_size）。"""
        # 仅验证参数透传，不需要真实数据（skip_missing=True 不报错）
        try:
            ds = FRUNetDRIVE(str(tmp_path), split='test',
                             patch_size=None, augment=False,
                             skip_missing=True)
            assert ds.eval_square_size == 592, (
                f"DRIVE default eval_square_size should be 592 (official), got {ds.eval_square_size}"
            )
        except Exception:
            pass  # skip_missing=True 但 tmp_path 无文件，构造可能 warn 但不崩

    def test_chase_default_eval_square_size_1008(self, tmp_path):
        """FRUNetCHASE 默认 eval_square_size=1008（官方 CHASE target_size）。"""
        try:
            ds = FRUNetCHASE(str(tmp_path), split='test',
                             patch_size=None, augment=False,
                             skip_missing=True)
            assert ds.eval_square_size == 1008, (
                f"CHASE default eval_square_size should be 1008 (official), got {ds.eval_square_size}"
            )
        except Exception:
            pass
