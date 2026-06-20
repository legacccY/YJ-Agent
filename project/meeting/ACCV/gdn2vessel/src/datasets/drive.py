"""
DRIVE retinal vessel dataset — BaseVesselDataset subclass.

Standard preprocessing (common in FR-UNet / SA-UNet papers on DRIVE):
  - Green channel extraction: retinal vessels have highest contrast in G channel
  - CLAHE (Contrast Limited Adaptive Histogram Equalization): standard for fundus images
  - Normalise to [0, 1] then ImageNet-style standardise (mean/std over green channel)
  - Only compute loss / metrics inside FOV mask (FOV mask is a .gif file)

Typical DRIVE usage:
  - 20 training images (with GT + FOV mask) → split 16/4 train/val by default.
  - 20 test images have NO public GT; not used here (see TEST_IDS TODO below).

Super-param note:
  - patch_size=512, patch_stride=512 (full-image crop after pad) is common.
    FR-UNet (Liu et al., MedIA 2022) uses 64×64 patches; SA-UNet uses 48×48.
    We default to full 512×512 pad-crop so that spatial sequence at deepest encoder
    (32×32 = 1024 tokens) stays at the ≤1K GDN-2 sequence limit.
  - CLAHE clip_limit=2.0, tile_grid_size=8 — standard for retinal fundus
    (Zhuang et al., 2019; FR-UNet ref).

Directory layout (standard DRIVE download):
    data_root/
        training/
            images/       <id>_training.tif   (RGB .tif, read via cv2)
            1st_manual/   <id>_manual1.gif     (binary GT, read via PIL — cv2 returns
                                                silent all-zeros for this .gif; confirmed
                                                2026-06-20 with local data)
            mask/         <id>_training_mask.gif  (FOV mask, same PIL requirement)
        test/
            images/       <id>_test.tif
            mask/         <id>_test_mask.gif   (no GT available publicly)

NOTE on .gif loading:
    cv2.imread reads DRIVE .gif files without error but returns an all-zeros
    array (confirmed locally 2026-06-20: cv2 GT/mask unique = {0} despite
    valid vessel annotations).  PIL reads them correctly (unique = {0, 255}).
    DRIVEDataset therefore overrides _load_gt and _load_fov to use PIL.

HPC root:  /gpfs/work/bio/jiayu2403/gdn2vessel/data/vessel/DRIVE/
Local root: D:/YJ-Agent/data/vessel/DRIVE/
(True root from .portfolio/datasets.json key='vessel_collection_kaggle')
"""

from __future__ import annotations

from pathlib import Path
from typing import List

import cv2
import numpy as np

try:
    from PIL import Image as PILImage
    _HAS_PIL = True
except ImportError:
    _HAS_PIL = False

from datasets.base_vessel import BaseVesselDataset, apply_clahe, GREEN_MEAN, GREEN_STD


# --------------------------------------------------------------------------- #
#  DRIVE-specific image dimension (informational only; not enforced at runtime)
# --------------------------------------------------------------------------- #
DRIVE_IMG_H = 584
DRIVE_IMG_W = 565


# --------------------------------------------------------------------------- #
#  DRIVEDataset
# --------------------------------------------------------------------------- #

class DRIVEDataset(BaseVesselDataset):
    """
    DRIVE retinal vessel segmentation dataset — BaseVesselDataset subclass.

    All pipeline logic (CLAHE, pad/crop, augmentation, __getitem__, __len__,
    get_tiles) is inherited from BaseVesselDataset.  This subclass only
    provides DRIVE-specific:
      - TRAIN_IDS / VAL_IDS / TEST_IDS class attrs
      - _img_path / _gt_path / _mask_path path helpers
      - _load_gt / _load_fov overrides (PIL required — cv2 reads .gif silently wrong)

    Split (deterministic, from 20 training images with GT):
      TRAIN_IDS: 21..36  (16 images)
      VAL_IDS:   37..40  (4 images)
      TEST_IDS:  1..20   (官方标准 test，主 Dice 表用；需重下官方 test GT)
    """

    TRAIN_IDS: List[int] = list(range(21, 37))   # 21..36 (16 images)
    VAL_IDS:   List[int] = list(range(37, 41))   # 37..40 (4 images)

    # ✅ 裁定（用户 2026-06-20，不降质量）: DRIVE **标准 20/20 split 主 Dice 表保留**
    #   （train 21-40 / test 01-20，与所有 DRIVE 论文同口径，可比 SOTA）→ TEST_IDS=01-20。
    #   ⚠️ 数据动作: 现 Kaggle pack(umairinayat)缺 test/1st_manual GT，须**重下官方完整包**补
    #   test GT(原版含 test/1st_manual/*_manual1.gif，见 Entry16 来源)。补前 test 评估不可跑。
    #   断点续连 benchmark 另走 CHASE(8张官方 held-out test GT)，与本标准 split 正交。
    TEST_IDS: List[int] = list(range(1, 21))   # 01..20 官方标准 test（需重下 GT）

    # ---------------------------------------------------------------------- #
    #  Path helpers
    # ---------------------------------------------------------------------- #

    def _img_path(self, sid: int) -> Path:
        return self.data_root / 'training' / 'images' / f'{sid}_training.tif'

    def _gt_path(self, sid: int) -> Path:
        return self.data_root / 'training' / '1st_manual' / f'{sid}_manual1.gif'

    def _mask_path(self, sid: int) -> Path:
        return self.data_root / 'training' / 'mask' / f'{sid}_training_mask.gif'

    # ---------------------------------------------------------------------- #
    #  Override _load_gt and _load_fov: DRIVE GT/mask are .gif files.
    #
    #  cv2.imread reads DRIVE .gif without error but silently returns an
    #  all-zeros array (confirmed locally 2026-06-20: all pixel values = 0
    #  regardless of actual content).  PIL.Image reads them correctly.
    #  These overrides use PIL with cv2 as a last-resort fallback.
    # ---------------------------------------------------------------------- #

    def _load_gt(self, sid: int) -> np.ndarray:
        """Load DRIVE GT mask (.gif) → (H,W) uint8 {0,1}.
        PIL is required: cv2.imread returns silent all-zeros for DRIVE .gif files
        (confirmed 2026-06-20; cv2 unique={0}, PIL unique={0,255}).
        """
        gt_path = self._gt_path(sid)

        if _HAS_PIL:
            gt_arr = np.array(PILImage.open(str(gt_path)).convert('L'))
            return (gt_arr > 127).astype(np.uint8)

        # Fallback to cv2 (may silently return all-zeros for .gif — documented risk)
        gt_raw = cv2.imread(str(gt_path), cv2.IMREAD_GRAYSCALE)
        assert gt_raw is not None, (
            f"cv2 failed to read DRIVE GT {gt_path}. "
            "Install Pillow (pip install Pillow) for reliable .gif support."
        )
        return (gt_raw > 127).astype(np.uint8)

    def _load_fov(self, sid: int) -> np.ndarray:
        """Load DRIVE FOV mask (.gif) → (H,W) uint8 {0,1}.
        PIL is required: same cv2/.gif issue as _load_gt.
        Fallback to all-ones (full image) if mask file is missing.
        """
        mask_path = self._mask_path(sid)

        if not mask_path.exists():
            # No FOV mask: use full image as valid region
            img_bgr = cv2.imread(str(self._img_path(sid)))
            assert img_bgr is not None, f"cv2 failed to read DRIVE image {self._img_path(sid)}"
            h, w = img_bgr.shape[:2]
            return np.ones((h, w), dtype=np.uint8)

        if _HAS_PIL:
            mask_arr = np.array(PILImage.open(str(mask_path)).convert('L'))
            return (mask_arr > 127).astype(np.uint8)

        # Fallback to cv2 (may silently return all-zeros for .gif — documented risk)
        mask_raw = cv2.imread(str(mask_path), cv2.IMREAD_GRAYSCALE)
        if mask_raw is not None:
            return (mask_raw > 127).astype(np.uint8)

        # If cv2 returns None (not all-zeros), use full-image fallback
        img_bgr = cv2.imread(str(self._img_path(sid)))
        h, w = img_bgr.shape[:2]
        return np.ones((h, w), dtype=np.uint8)
