"""
CHASE_DB1 retinal vessel dataset.

Kaggle pack (umairinayat/retinal-vessel-segmentation-datasets) layout
(confirmed via local ls 2026-06-20):

  <data_root>/
    images/
      training_01_test.tif  ..  training_20_test.tif   (20 training images)
      test_01_test.tif      ..  test_08_test.tif        (8 test images)
    masks/
      training_01_manual1.tif .. training_20_manual1.tif
      test_01_manual1.tif   .. test_08_manual1.tif

  Resolution: 960×999 (h×w, confirmed via cv2.imread)
  No official FOV mask → circular estimate at 90% of min(H,W)/2

Official split convention (Fraz 2012; FR-UNet / SA-UNet follow the same):
  Training set: 20 images (training_01 .. training_20)
  Test set:     8 images  (test_01 .. test_08)
  Val: last 4 of training (training_17 .. training_20), train = first 16.

Reference:
  Fraz et al., "An Ensemble Classification-Based Approach Applied to Retinal
  Blood Vessel Segmentation" (IEEE TBME 2012).
  Official DB: https://researchdata.kingston.ac.uk/96/ (CC-BY)

HPC root:  /gpfs/work/bio/jiayu2403/gdn2vessel/data/vessel/CHASE/
Local root: D:/YJ-Agent/data/vessel/CHASE/
(True root from .portfolio/datasets.json key='vessel_collection_kaggle')
"""

from __future__ import annotations

from pathlib import Path
from typing import List

import cv2
import numpy as np

from datasets.base_vessel import BaseVesselDataset, apply_clahe, GREEN_MEAN, GREEN_STD


# --------------------------------------------------------------------------- #
#  CHASE_DB1 split IDs
#
#  Kaggle pack uses numeric string IDs "01" .. "20" for training
#  and "01" .. "08" for test.  We prefix to distinguish, but the path
#  helpers use the prefix to select the correct subdir filenames.
#
#  Internal ID convention: "<prefix>_<nn>" e.g. "training_01", "test_01"
# --------------------------------------------------------------------------- #

def _make_ids(prefix: str, numbers: List[int]) -> List[str]:
    return [f'{prefix}_{n:02d}' for n in numbers]


class CHASEDataset(BaseVesselDataset):
    """
    CHASE_DB1 retinal vessel dataset — manual1 (first annotator) GT.

    Split (deterministic, Kaggle pack structure):
      TRAIN_IDS: training_01 .. training_16  (16 images)
      VAL_IDS:   training_17 .. training_20  (4 images)
      TEST_IDS:  test_01 .. test_08          (8 images, held-out benchmark)

    Total: 20 training (16+4) + 8 test = 28.
    FOV: No official mask → circular estimate ~90% min(H,W)/2.
    """

    TRAIN_IDS: List[str] = _make_ids('training', list(range(1, 17)))   # 16 images
    VAL_IDS:   List[str] = _make_ids('training', list(range(17, 21)))  # 4 images
    TEST_IDS:  List[str] = _make_ids('test',     list(range(1, 9)))    # 8 images

    def _img_path(self, sid: str) -> Path:
        # sid example: "training_01" or "test_03"
        return self.data_root / 'images' / f'{sid}_test.tif'

    def _gt_path(self, sid: str) -> Path:
        return self.data_root / 'masks' / f'{sid}_manual1.tif'

    def _mask_path(self, sid: str) -> Path:
        # No official FOV mask; path will not exist → fallback to circular estimate
        return self.data_root / 'masks' / f'{sid}_FOV.png'

    def _load_fov(self, sid: str) -> np.ndarray:
        """CHASE: no official FOV mask. Circular estimate ~90% min(H,W)/2."""
        mask_path = self._mask_path(sid)
        if mask_path.exists():
            mask_raw = cv2.imread(str(mask_path), cv2.IMREAD_GRAYSCALE)
            if mask_raw is not None:
                return (mask_raw > 127).astype(np.uint8)

        # Build circular estimate from image shape
        img_bgr = cv2.imread(str(self._img_path(sid)))
        assert img_bgr is not None, f'cv2 failed to read CHASE image {self._img_path(sid)}'
        h, w = img_bgr.shape[:2]
        fov = np.zeros((h, w), dtype=np.uint8)
        cy, cx = h // 2, w // 2
        r = int(0.90 * min(h, w) / 2)
        cv2.circle(fov, (cx, cy), r, 1, -1)
        return fov
