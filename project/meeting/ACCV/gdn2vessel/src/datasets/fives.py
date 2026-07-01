"""
FIVES retinal vessel dataset.

Kaggle pack (umairinayat/retinal-vessel-segmentation-datasets) layout
(confirmed via local ls 2026-06-20):

  <data_root>/
    images/
      train_1_A.png .. train_600_*.png   (600 training images)
      test_100_D.png .. test_*.png        (200 test images)
    masks/
      train_1_A.png .. (matching GT names)
      test_100_D.png ..

  NOTE: official figshare release uses train/{Original,Ground Truth}/
  + test/{Original,Ground Truth}/ subdirs. The Kaggle pack flattens
  everything into images/ + masks/ and encodes split in the filename prefix
  (train_ vs test_). IDs are full stems (e.g. "train_1_A", "test_100_D").

  Resolution: 2048×2048 per image (native on disk).
  FOV: No official mask → full-image all-ones.

  FIVES input strategy (DECIDED 2026-07-01, 用户拍板 — L4 dataset expansion):
    Resize whole image to 512×512 at the DATASET layer (image + GT + FOV all
    downsampled to 512²), NOT tiled and NOT random-cropped at native 2048².
    Rationale:
      - Official口径: FIVES paper (arXiv 2406.14994) "resampled to 512×512" +
        CLAHE clip2/grid8×8; empirically FIVES optimal at 256–876px.
      - Feeding native 2048² into base random_crop(512) would show the model
        only 1/16 of the retina FOV per crop = severe field-of-view starvation.
      - Resize-512 saves ~16–21× compute vs native 2048² and makes break gap_size
        (pixels) comparable across DRIVE(565²)/CHASE(999²)/STARE(605×700)/FIVES.
    Downsample interpolation:
      - image: cv2.INTER_AREA (proper anti-aliased downsampling, 4× reduction).
      - GT / FOV: cv2.INTER_NEAREST (keep labels strictly binary; standard for
        segmentation masks). See note in _load_gt on connectivity caveat.
    CLAHE clip_limit=2.0, tile 8×8 = base_vessel default = official FIVES口径.

Reference:
  Jin et al., "FIVES: A Fundus Image Dataset for AI-based Vessel Segmentation"
  Scientific Data 2022. figshare: https://doi.org/10.6084/m9.figshare.19688169

HPC root:  /gpfs/work/bio/jiayu2403/gdn2vessel/data/vessel/FIVES/
Local root: D:/YJ-Agent/data/vessel/FIVES/
(True root from .portfolio/datasets.json key='vessel_collection_kaggle')
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import List

import cv2
import numpy as np

from datasets.base_vessel import (
    BaseVesselDataset,
    apply_clahe,
    GREEN_MEAN,
    GREEN_STD,
)

# FIVES input resolution — resize whole 2048² image to this (用户拍板 2026-07-01).
FIVES_RESIZE = 512


# --------------------------------------------------------------------------- #
#  Dynamic ID discovery from flat images/ directory (prefix-based split)
# --------------------------------------------------------------------------- #

def _discover_fives_ids(img_dir: Path, prefix: str) -> List[str]:
    """Return sorted stems that start with `prefix` ('train_' or 'test_')."""
    if not img_dir.exists():
        return []
    stems = sorted(
        p.stem
        for p in img_dir.iterdir()
        if p.suffix.lower() in ('.png', '.jpg', '.tif', '.bmp')
        and p.name.startswith(prefix)
    )
    return stems


class FIVESDataset(BaseVesselDataset):
    """
    FIVES fundus image dataset — flat Kaggle layout (train_*/test_* filenames).

    Split:
      TRAIN_IDS: stems starting with 'train_' from images/ (600 images)
      VAL_IDS:   last ~10% carved from training (default 60 images)
      TEST_IDS:  stems starting with 'test_' from images/  (200 images)

    IDs are full filename stems (e.g. "train_42_G", "test_100_D").
    Discovered dynamically from disk — not hardcoded, since filenames vary.
    Anti-leakage: train_*/test_* are structurally disjoint by prefix.

    Native 2048² on disk → resized to resize_to² (default 512) at load time
    (_load_image / _load_gt / _load_fov all return resize_to² arrays). See module
    docstring "FIVES input strategy" (用户拍板 2026-07-01).
    """

    # Class-level defaults (empty); populated per-instance in __init__
    TRAIN_IDS: List[str] = []
    VAL_IDS:   List[str] = []
    TEST_IDS:  List[str] = []

    def __init__(self, data_root: str, split: str = 'train',
                 resize_to: int = FIVES_RESIZE, **kwargs):
        # resize_to: whole-image resize target (default 512, official FIVES口径).
        # Set before super().__init__ so overridden _load_* can read it.
        self.resize_to = int(resize_to)
        root = Path(data_root)
        img_dir = root / 'images'

        all_train = _discover_fives_ids(img_dir, 'train_')
        all_test  = _discover_fives_ids(img_dir, 'test_')

        # Carve val from training (last 10%, min 1)
        n_val   = min(60, max(1, len(all_train) // 10)) if all_train else 0
        n_train = len(all_train) - n_val

        self._train_ids = all_train[:n_train]
        self._val_ids   = all_train[n_train:]
        self._test_ids  = all_test

        # Temporarily patch class attrs so BaseVesselDataset._check_split_disjoint passes
        _orig_train = FIVESDataset.TRAIN_IDS
        _orig_val   = FIVESDataset.VAL_IDS
        _orig_test  = FIVESDataset.TEST_IDS
        FIVESDataset.TRAIN_IDS = self._train_ids
        FIVESDataset.VAL_IDS   = self._val_ids
        FIVESDataset.TEST_IDS  = self._test_ids
        try:
            super().__init__(data_root=data_root, split=split, **kwargs)
        finally:
            FIVESDataset.TRAIN_IDS = _orig_train
            FIVESDataset.VAL_IDS   = _orig_val
            FIVESDataset.TEST_IDS  = _orig_test

        # Override ids set by parent (parent used old class attrs temporarily patched)
        if split == 'train':
            self.ids = list(self._train_ids)
        elif split == 'val':
            self.ids = list(self._val_ids)
        elif split == 'test':
            self.ids = list(self._test_ids)
        elif split == 'all':
            self.ids = list(self._train_ids) + list(self._val_ids)

    @classmethod
    def _check_split_disjoint(cls):
        """Override: skip check when class attrs are empty defaults.
        When patched during __init__, the real check runs correctly.
        """
        if not cls.TRAIN_IDS and not cls.TEST_IDS:
            return
        super()._check_split_disjoint()

    # ---------------------------------------------------------------------- #
    #  Path helpers — flat images/ + masks/ layout, stem as ID
    # ---------------------------------------------------------------------- #

    def _img_path(self, sid: str) -> Path:
        # sid is the full stem e.g. "train_42_G" or "test_100_D"
        return self.data_root / 'images' / f'{sid}.png'

    def _gt_path(self, sid: str) -> Path:
        return self.data_root / 'masks' / f'{sid}.png'

    def _mask_path(self, sid: str) -> Path:
        # No official FOV mask
        return self.data_root / 'fov_masks' / f'{sid}.png'

    # ---------------------------------------------------------------------- #
    #  Load overrides — resize whole 2048² image to resize_to² (用户拍板 2026-07-01)
    #  Order (matches official FIVES): resize raw → then CLAHE (green mode).
    # ---------------------------------------------------------------------- #

    def _load_image(self, sid: str) -> np.ndarray:
        """Load FIVES image, resize to resize_to² (INTER_AREA), then base pipeline.

        Respects color_mode (set by BaseVesselDataset.__init__):
          'green' (default 11 baselines): green channel + CLAHE + normalize → (S,S)
          'rgb'   (CS-Net only):          RGB /255, no CLAHE                 → (S,S,3)
        """
        img_bgr = cv2.imread(str(self._img_path(sid)))
        assert img_bgr is not None, f'cv2 failed to read FIVES image {self._img_path(sid)}'
        # Downsample whole image 2048² → resize_to² (anti-aliased area average).
        img_bgr = cv2.resize(img_bgr, (self.resize_to, self.resize_to),
                             interpolation=cv2.INTER_AREA)

        if self.color_mode == 'rgb':
            # CS-Net口径: RGB /255 only (resize done above; forward_adapt no-op resizes).
            img_rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
            return img_rgb.astype(np.float32) / 255.0   # (S, S, 3)

        # Default green + CLAHE(clip2/grid8) + normalize — mirrors base_vessel._load_image.
        green = img_bgr[:, :, 1]
        green_clahe = apply_clahe(green, clip_limit=self.clahe_clip)
        img_f = green_clahe.astype(np.float32) / 255.0
        img_f = (img_f - GREEN_MEAN) / GREEN_STD
        return img_f  # (S, S)

    def _load_gt(self, sid: str) -> np.ndarray:
        """Load FIVES GT, resize to resize_to² (INTER_NEAREST, keep binary).

        NOTE: 4× downsample of thin vessel labels can fragment 1-px vessels →
        spurious pre-existing breaks. Standard nearest-label口径 chosen (no official
        FIVES GT interpolation spec). If gap-count sanity looks off, flag to
        researcher/analyst; do NOT silently switch interpolation (预登记 frozen).
        """
        gt_raw = cv2.imread(str(self._gt_path(sid)), cv2.IMREAD_GRAYSCALE)
        assert gt_raw is not None, f'cv2 failed to read FIVES GT {self._gt_path(sid)}'
        gt_r = cv2.resize(gt_raw, (self.resize_to, self.resize_to),
                          interpolation=cv2.INTER_NEAREST)
        return (gt_r > 127).astype(np.uint8)

    def _load_fov(self, sid: str) -> np.ndarray:
        """FIVES: no official FOV mask → full-image all-ones at resize_to²."""
        mask_path = self._mask_path(sid)
        if mask_path.exists():
            mask_raw = cv2.imread(str(mask_path), cv2.IMREAD_GRAYSCALE)
            if mask_raw is not None:
                mask_r = cv2.resize(mask_raw, (self.resize_to, self.resize_to),
                                    interpolation=cv2.INTER_NEAREST)
                return (mask_r > 127).astype(np.uint8)

        # No FOV mask: full-image valid region at resized resolution.
        return np.ones((self.resize_to, self.resize_to), dtype=np.uint8)
