"""
DRIVE retinal vessel dataset.

Standard preprocessing (common in FR-UNet / SA-UNet papers on DRIVE):
  - Green channel extraction: retinal vessels have highest contrast in G channel
  - CLAHE (Contrast Limited Adaptive Histogram Equalization): standard for fundus images
  - Normalise to [0, 1] then ImageNet-style standardise (mean/std over green channel)
  - Only compute loss / metrics inside FOV mask

Typical DRIVE usage:
  - 20 training images (with GT + FOV mask) → split 16/4 train/val by default.
  - 20 test images have no public GT; not used here.

Super-param note:
  - patch_size=512, patch_stride=512 (full-image crop after pad) is common.
    FR-UNet (Liu et al., MedIA 2022) uses 64×64 patches; SA-UNet uses 48×48.
    We default to full 512×512 pad-crop so that spatial sequence at deepest encoder
    (32×32 = 1024 tokens) stays at the ≤1K GDN-2 sequence limit.
  - CLAHE clip_limit=2.0, tile_grid_size=8 — standard for retinal fundus
    (Zhuang et al., 2019; FR-UNet ref).
"""

from __future__ import annotations

import os
import random
from pathlib import Path
from typing import Optional, Tuple

import cv2
import numpy as np
import torch
from torch.utils.data import Dataset

# --------------------------------------------------------------------------- #
#  Constants (DRIVE-specific, verified from image inspection)
# --------------------------------------------------------------------------- #
DRIVE_IMG_H = 584
DRIVE_IMG_W = 565

# Green-channel statistics (approximate; recomputed per training set is ideal)
# TODO: confirm exact per-dataset mean/std via offline sweep; these are common
#       values used in FR-UNet / SA-UNet DRIVE experiments
GREEN_MEAN = 0.5
GREEN_STD = 0.1


# --------------------------------------------------------------------------- #
#  Preprocessing helpers
# --------------------------------------------------------------------------- #

def apply_clahe(green_channel: np.ndarray,
                clip_limit: float = 2.0,
                tile_grid_size: int = 8) -> np.ndarray:
    """CLAHE on uint8 green channel.  Standard retinal fundus preprocessing."""
    assert green_channel.dtype == np.uint8
    clahe = cv2.createCLAHE(clipLimit=clip_limit,
                             tileGridSize=(tile_grid_size, tile_grid_size))
    return clahe.apply(green_channel)


def pad_to_multiple(img: np.ndarray, multiple: int = 32) -> Tuple[np.ndarray, Tuple]:
    """Zero-pad H and W to nearest multiple of `multiple`.
    Returns padded array and (pad_top, pad_left) for inverse crop.
    """
    h, w = img.shape[:2]
    pad_h = (multiple - h % multiple) % multiple
    pad_w = (multiple - w % multiple) % multiple
    if img.ndim == 2:
        padded = np.pad(img, ((0, pad_h), (0, pad_w)), mode='constant')
    else:
        padded = np.pad(img, ((0, pad_h), (0, pad_w), (0, 0)), mode='constant')
    return padded, (0, 0, pad_h, pad_w)  # top, left, bottom, right


# --------------------------------------------------------------------------- #
#  Dataset
# --------------------------------------------------------------------------- #

class DRIVEDataset(Dataset):
    """
    DRIVE retinal vessel segmentation dataset.

    Directory layout (standard DRIVE download):
        data_root/
            training/
                images/       <id>_training.tif
                1st_manual/   <id>_manual1.gif
                mask/         <id>_training_mask.gif
            test/
                images/       <id>_test.tif
                mask/         <id>_test_mask.gif   (no GT available publicly)

    Args:
        data_root:   Path to DRIVE root (contains training/ and test/)
        split:       'train' | 'val' | 'all'
                     'train'/'val' index into training/ (20 images).
                     Indices 0..15 → train (16 images), 16..19 → val (4 images).
        patch_size:  Square patch side for random crop training.  None = no crop.
        augment:     Apply random flip/rotation (train split only).
        clahe_clip:  CLAHE clip limit. Default 2.0.
        pad_multiple: Pad image to multiple of this before crop.
    """

    TRAINING_IDS = list(range(21, 41))  # 21..40
    # Default 16/4 train/val split (deterministic, fixed)
    TRAIN_IDS = list(range(21, 37))   # 21..36
    VAL_IDS = list(range(37, 41))     # 37..40

    def __init__(
        self,
        data_root: str,
        split: str = 'train',
        patch_size: Optional[int] = 512,
        augment: bool = False,
        clahe_clip: float = 2.0,
        pad_multiple: int = 32,
    ):
        super().__init__()
        self.data_root = Path(data_root)
        self.split = split
        self.patch_size = patch_size
        self.augment = augment
        self.clahe_clip = clahe_clip
        self.pad_multiple = pad_multiple

        if split == 'train':
            self.ids = self.TRAIN_IDS
        elif split == 'val':
            self.ids = self.VAL_IDS
        elif split == 'all':
            self.ids = self.TRAINING_IDS
        else:
            raise ValueError(f"split must be 'train'/'val'/'all', got {split!r}")

        # Verify paths exist
        for sid in self.ids:
            img_path = self._img_path(sid)
            gt_path = self._gt_path(sid)
            if not img_path.exists():
                raise FileNotFoundError(f"DRIVE image not found: {img_path}")
            if not gt_path.exists():
                raise FileNotFoundError(f"DRIVE GT not found: {gt_path}")

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
    #  Core loading + preprocessing
    # ---------------------------------------------------------------------- #

    def _load_sample(self, sid: int):
        """Load one DRIVE sample, apply green-channel + CLAHE preprocessing."""
        # --- image ---
        img_bgr = cv2.imread(str(self._img_path(sid)))  # BGR uint8
        assert img_bgr is not None, f"cv2 failed to read {self._img_path(sid)}"
        green = img_bgr[:, :, 1]  # green channel (index 1 in BGR)
        green_clahe = apply_clahe(green, clip_limit=self.clahe_clip)

        # Normalise: [0,255] → float32 → standardise
        img_f = green_clahe.astype(np.float32) / 255.0
        img_f = (img_f - GREEN_MEAN) / GREEN_STD  # (H, W)

        # --- GT ---
        gt_pil = cv2.imread(str(self._gt_path(sid)), cv2.IMREAD_GRAYSCALE)
        assert gt_pil is not None
        gt = (gt_pil > 127).astype(np.uint8)  # {0,1}

        # --- FOV mask ---
        mask_path = self._mask_path(sid)
        if mask_path.exists():
            mask_raw = cv2.imread(str(mask_path), cv2.IMREAD_GRAYSCALE)
            fov_mask = (mask_raw > 127).astype(np.uint8)
        else:
            fov_mask = np.ones_like(gt, dtype=np.uint8)

        return img_f, gt, fov_mask

    # ---------------------------------------------------------------------- #
    #  Augmentation
    # ---------------------------------------------------------------------- #

    def _augment(self, img, gt, mask):
        """Random H-flip, V-flip, 90° rotation."""
        if random.random() > 0.5:
            img = np.fliplr(img).copy()
            gt = np.fliplr(gt).copy()
            mask = np.fliplr(mask).copy()
        if random.random() > 0.5:
            img = np.flipud(img).copy()
            gt = np.flipud(gt).copy()
            mask = np.flipud(mask).copy()
        k = random.randint(0, 3)
        if k > 0:
            img = np.rot90(img, k).copy()
            gt = np.rot90(gt, k).copy()
            mask = np.rot90(mask, k).copy()
        return img, gt, mask

    # ---------------------------------------------------------------------- #
    #  Patch extraction
    # ---------------------------------------------------------------------- #

    def _random_crop(self, img, gt, mask, size):
        h, w = img.shape[:2]
        if h < size or w < size:
            # pad first
            pad_h = max(0, size - h)
            pad_w = max(0, size - w)
            img = np.pad(img, ((0, pad_h), (0, pad_w)), mode='reflect')
            gt = np.pad(gt, ((0, pad_h), (0, pad_w)), mode='constant')
            mask = np.pad(mask, ((0, pad_h), (0, pad_w)), mode='constant')
            h, w = img.shape[:2]
        y0 = random.randint(0, h - size)
        x0 = random.randint(0, w - size)
        return (img[y0:y0+size, x0:x0+size],
                gt[y0:y0+size, x0:x0+size],
                mask[y0:y0+size, x0:x0+size])

    def _center_pad(self, img, gt, mask):
        """Pad to pad_multiple boundary for full-image inference."""
        img_p, _ = pad_to_multiple(img, self.pad_multiple)
        gt_p, _ = pad_to_multiple(gt, self.pad_multiple)
        mask_p, _ = pad_to_multiple(mask, self.pad_multiple)
        return img_p, gt_p, mask_p

    # ---------------------------------------------------------------------- #
    #  __len__ / __getitem__
    # ---------------------------------------------------------------------- #

    def __len__(self):
        return len(self.ids)

    def __getitem__(self, idx):
        sid = self.ids[idx]
        img, gt, fov_mask = self._load_sample(sid)

        if self.augment:
            img, gt, fov_mask = self._augment(img, gt, fov_mask)

        if self.patch_size is not None:
            img, gt, fov_mask = self._random_crop(img, gt, fov_mask, self.patch_size)
        else:
            img, gt, fov_mask = self._center_pad(img, gt, fov_mask)

        # --- to tensor ---
        # img: (H, W) → (1, H, W)   float32
        # gt:  (H, W) → (1, H, W)   float32 {0,1}
        # fov: (H, W) → (1, H, W)   float32 {0,1}
        img_t = torch.from_numpy(img).unsqueeze(0)          # (1, H, W)
        gt_t = torch.from_numpy(gt.astype(np.float32)).unsqueeze(0)
        fov_t = torch.from_numpy(fov_mask.astype(np.float32)).unsqueeze(0)

        return {
            'image': img_t,    # (1, H, W)  normalised green channel
            'gt': gt_t,        # (1, H, W)  {0,1}
            'fov': fov_t,      # (1, H, W)  {0,1} FOV mask
            'id': sid,
        }
