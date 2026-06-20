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

  Resolution: 2048×2048 per image.
  FOV: No official mask → full-image all-ones.

  FIVES evaluation strategy:
    Full-image 2048×2048 is very large for direct inference.
    Options (chose at adapter level or evaluate.py caller):
      a) Sliding-window tiles: 512×512, stride 448 (overlap 64) via get_tiles()
      b) Resize to 512×512 at adapter forward_adapt()
    # TODO: confirm which strategy adapters use for FIVES 2048×2048 inference.
    #       dataset returns tiles via get_tiles(); resize is adapter-side concern.

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

from datasets.base_vessel import BaseVesselDataset


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

    High-res: 2048×2048. Use get_tiles(tile_size=512, overlap=64) for inference.
    # TODO: confirm preferred inference strategy (tile vs resize) with main-line.
    """

    # Class-level defaults (empty); populated per-instance in __init__
    TRAIN_IDS: List[str] = []
    VAL_IDS:   List[str] = []
    TEST_IDS:  List[str] = []

    def __init__(self, data_root: str, split: str = 'train', **kwargs):
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

    def _load_fov(self, sid: str) -> np.ndarray:
        """FIVES: no official FOV mask → full-image (all ones)."""
        mask_path = self._mask_path(sid)
        if mask_path.exists():
            mask_raw = cv2.imread(str(mask_path), cv2.IMREAD_GRAYSCALE)
            if mask_raw is not None:
                return (mask_raw > 127).astype(np.uint8)

        # Fall back to full-image valid region
        img_bgr = cv2.imread(str(self._img_path(sid)))
        assert img_bgr is not None, f'cv2 failed to read FIVES image {self._img_path(sid)}'
        h, w = img_bgr.shape[:2]
        return np.ones((h, w), dtype=np.uint8)
