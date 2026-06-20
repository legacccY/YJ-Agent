"""
HRF (High-Resolution Fundus) retinal vessel dataset.

Official split: 15 training images / 30 test images (45 total).
  15 training: images 01-15
  30 test: images 01-30
  NOTE: HRF train/test share overlapping numeric IDs but are in separate
        subdirectories (healthy/glaucomatous/diabetic retinopathy sub-splits).
        The 15 training images are from the 'training' subset;
        the 30 test images are from the full evaluation set.

  TODO: Confirm exact directory layout in Kaggle pack after HPC ls.
        The pack may use flat images/ masks/ roi_masks/ with all 45 images.
        In that case, split by filename prefix convention.

Directory layout (Kaggle pack, verified from datasets.json):
  <data_root>/
    images/         (all images, .jpg or .tif)
    masks/          (GT vessel masks, .tif or .png)
    roi_masks/      (FOV masks, .tif — official HRF FOV masks available!)
                    Use roi_masks/ as FOV.

HPC root:  /gpfs/work/bio/jiayu2403/gdn2vessel/data/vessel/HRF/
Local root: D:/YJ-Agent/data/vessel/HRF/
(True root from .portfolio/datasets.json key='vessel_collection_kaggle')

Resolution: 3504×2336 (very high-res — tile inference required for benchmark).
FOV: Official ROI masks available as .tif in roi_masks/ subdirectory.

Reference:
  Budai et al., "Robust Vessel Segmentation in Fundus Images" (2013).
  https://www5.cs.fau.de/research/data/fundus-images/
"""

from __future__ import annotations

from pathlib import Path
from typing import List

import cv2
import numpy as np

from datasets.base_vessel import BaseVesselDataset


# --------------------------------------------------------------------------- #
#  HRF IDs
#  Kaggle pack layout: all 45 images in images/ + masks/ + roi_masks/.
#  Naming convention (from HRF official): 01_dr.jpg, 02_g.jpg, 03_h.jpg, ...
#  Pattern: <two_digit_number>_<condition>.{jpg,tif}
#    condition codes: dr=diabetic retinopathy, g=glaucoma, h=healthy
#  15 healthy (h): 01_h .. 15_h
#  15 diabetic (dr): 01_dr .. 15_dr
#  15 glaucomatous (g): 01_g .. 15_g
#  Total: 45 images
#
#  Official split: 15 train / 30 test
#  Common convention (FR-UNet / SA-UNet): train = 15 healthy; test = 30 (dr+g)
#  OR: train = first 15 across conditions; test = remaining 30.
#
#  TODO: Confirm exact split used by FR-UNet/SA-UNet and which images are train
#        after HPC ls shows the actual filenames in the Kaggle pack.
#        Using condition-based split below (healthy=train, dr+g=test) as
#        the most common FR-UNet convention. Update if researcher confirms
#        a different canonical split.
#
#  Format of IDs here: "<nn>_<cond>" e.g. "01_h", "02_dr", "03_g"
# --------------------------------------------------------------------------- #

def _hrf_ids(numbers: List[int], cond: str) -> List[str]:
    return [f'{n:02d}_{cond}' for n in numbers]


_HEALTHY_IDS = _hrf_ids(range(1, 16), 'h')     # 15 healthy (train)
_DR_IDS      = _hrf_ids(range(1, 16), 'dr')    # 15 diabetic retinopathy (test)
_GLAUCOMA_IDS = _hrf_ids(range(1, 16), 'g')    # 15 glaucoma (test)


class HRFDataset(BaseVesselDataset):
    """
    HRF retinal vessel dataset — official FOV masks.

    Split (deterministic):
      TRAIN_IDS: 15 healthy images (01_h .. 15_h)     — 12 train
      VAL_IDS:   3 healthy images (13_h, 14_h, 15_h)  — 3 val
      TEST_IDS:  30 images (15 dr + 15 glaucoma)       — held-out benchmark

    Note: val is carved from training healthy images.
    Test uses all pathological images (dr + glaucoma) as held-out set.

    High-res: 3504×2336. Use get_tiles(tile_size=512) for inference.
    """

    # 12 train + 3 val from healthy; 30 test from dr+glaucoma
    TRAIN_IDS: List[str] = _HEALTHY_IDS[:12]        # 01_h .. 12_h
    VAL_IDS:   List[str] = _HEALTHY_IDS[12:]        # 13_h, 14_h, 15_h
    TEST_IDS:  List[str] = _DR_IDS + _GLAUCOMA_IDS  # 30 held-out

    def _img_path(self, sid: str) -> Path:
        # TODO: confirm extension (.jpg vs .tif) after HPC ls
        jpg = self.data_root / 'images' / f'{sid}.jpg'
        tif = self.data_root / 'images' / f'{sid}.tif'
        if jpg.exists():
            return jpg
        return tif

    def _gt_path(self, sid: str) -> Path:
        # TODO: confirm GT extension (.tif vs .png) after HPC ls
        tif = self.data_root / 'masks' / f'{sid}.tif'
        png = self.data_root / 'masks' / f'{sid}.png'
        if tif.exists():
            return tif
        return png

    def _mask_path(self, sid: str) -> Path:
        # HRF official FOV masks in roi_masks/ as .tif
        # TODO: confirm exact filename pattern after HPC ls
        tif = self.data_root / 'roi_masks' / f'{sid}_mask.tif'
        tif2 = self.data_root / 'roi_masks' / f'{sid}.tif'
        if tif.exists():
            return tif
        return tif2

    def _load_gt(self, sid: str) -> np.ndarray:
        """Load HRF GT tif → (H,W) uint8 {0,1}."""
        gt_raw = cv2.imread(str(self._gt_path(sid)), cv2.IMREAD_GRAYSCALE)
        assert gt_raw is not None, f"cv2 failed to read HRF GT {self._gt_path(sid)}"
        return (gt_raw > 127).astype(np.uint8)

    def _load_fov(self, sid: str) -> np.ndarray:
        """HRF has official FOV masks in roi_masks/. Load as binary mask."""
        mask_path = self._mask_path(sid)
        if mask_path.exists():
            mask_raw = cv2.imread(str(mask_path), cv2.IMREAD_GRAYSCALE)
            if mask_raw is not None:
                return (mask_raw > 127).astype(np.uint8)

        # Fallback: full-image mask (should not happen if data is complete)
        img_bgr = cv2.imread(str(self._img_path(sid)))
        assert img_bgr is not None, f"cv2 failed to read HRF image {self._img_path(sid)}"
        h, w = img_bgr.shape[:2]
        return np.ones((h, w), dtype=np.uint8)
