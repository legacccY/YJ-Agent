"""
base_vessel.py — BaseVesselDataset: shared preprocessing pipeline for all retinal/vessel datasets.

Extracted from drive.py (green channel + CLAHE + normalize + FOV + pad + crop/__getitem__).
Subclasses only override:
  _img_path(sid) / _gt_path(sid) / _mask_path(sid)
  TRAIN_IDS / VAL_IDS / TEST_IDS (class attrs, deterministic lists)
  _load_image(sid) → np.ndarray (H,W) float32 normlised  [override if not RGB/green-channel]
  _load_gt(sid)    → np.ndarray (H,W) uint8 {0,1}
  _load_fov(sid)   → np.ndarray (H,W) uint8 {0,1}

__getitem__ returns dict consistent with drive.py:
  {'image': (1,H,W) float32, 'gt': (1,H,W) float32, 'fov': (1,H,W) float32, 'id': sid}

Windows training rules (spawn / no pin_memory) applied at DataLoader call site, not here.
"""

from __future__ import annotations

import random
from pathlib import Path
from typing import List, Optional, Sequence, Tuple, Union

import cv2
import numpy as np
import torch
from torch.utils.data import Dataset

# --------------------------------------------------------------------------- #
#  Shared constants — from drive.py convention
# --------------------------------------------------------------------------- #

# Green-channel ImageNet-style normalisation constants
# TODO: confirm exact per-dataset mean/std via offline sweep per dataset;
#       these follow drive.py convention; researcher should update per-dataset
GREEN_MEAN = 0.5
GREEN_STD = 0.1

CLAHE_CLIP = 2.0   # clip_limit — standard retinal fundus (FR-UNet / SA-UNet)
CLAHE_TILE = 8     # tile_grid_size
PAD_MULTIPLE = 32  # pad to multiple for encoder divisibility


# --------------------------------------------------------------------------- #
#  Shared helpers (mirrors drive.py exactly — do not drift)
# --------------------------------------------------------------------------- #

def apply_clahe(green_channel: np.ndarray,
                clip_limit: float = CLAHE_CLIP,
                tile_grid_size: int = CLAHE_TILE) -> np.ndarray:
    """CLAHE on uint8 green channel. Standard retinal fundus preprocessing."""
    assert green_channel.dtype == np.uint8
    clahe = cv2.createCLAHE(clipLimit=clip_limit,
                             tileGridSize=(tile_grid_size, tile_grid_size))
    return clahe.apply(green_channel)


def pad_to_multiple(img: np.ndarray, multiple: int = PAD_MULTIPLE) -> Tuple[np.ndarray, Tuple]:
    """Zero-pad H and W to nearest multiple of `multiple`.
    Returns (padded_array, (top, left, bottom, right)) padding applied.
    Mirrors drive.py exactly.
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
#  BaseVesselDataset
# --------------------------------------------------------------------------- #

class BaseVesselDataset(Dataset):
    """
    Abstract base for retinal vessel segmentation datasets.

    Subclass protocol:
      1. Define class attrs: TRAIN_IDS, VAL_IDS, TEST_IDS (List[any])
      2. Override: _img_path, _gt_path, _mask_path
      3. Optionally override: _load_image, _load_gt, _load_fov
         (defaults: green-channel CLAHE for image; thresholded gray for gt/fov)

    Anti-leakage contract (RED LINE 1):
      - TEST_IDS must be disjoint from TRAIN_IDS and VAL_IDS.
      - __init__ asserts this at construction time via _check_split_disjoint().
      - 'test' split is exposed for benchmark evaluation ONLY — never mixed with
        training data. verify_no_leakage.py provides a stronger file-path check.

    Tile inference:
      patch_size=None → pad_to_multiple only (full image, for inference/benchmark).
      patch_size=512  → random crop during training (512×512 = 1024 bottleneck tokens).
    """

    # Subclasses MUST override these
    TRAIN_IDS: List = []
    VAL_IDS: List = []
    TEST_IDS: List = []

    def __init__(
        self,
        data_root: str,
        split: str = 'train',
        patch_size: Optional[int] = 512,
        augment: bool = False,
        clahe_clip: float = CLAHE_CLIP,
        pad_multiple: int = PAD_MULTIPLE,
        skip_missing: bool = False,
        color_mode: str = 'green',
    ):
        """
        Args:
            data_root:    Dataset root directory.
            split:        'train' | 'val' | 'test' | 'all'
            patch_size:   512 for training random crop; None for full-image pad.
            augment:      H-flip / V-flip / 90° rot (train only).
            clahe_clip:   CLAHE clip limit.
            pad_multiple: Pad H/W to multiple of this.
            skip_missing: If True, skip missing files instead of raising (for HPC
                          path validation before data is fully copied).
            color_mode:   'green' (default) — CLAHE + normalize green channel → (1,H,W);
                          'rgb'             — /255 only, no CLAHE → (3,H,W).
                          Only CS-Net uses 'rgb' (官方 ToTensor RGB, iMED-Lab/CS-Net).
                          All other 11 baselines keep 'green' (default, no behaviour change).
        """
        if color_mode not in ('green', 'rgb'):
            raise ValueError(
                f"BaseVesselDataset color_mode must be 'green' or 'rgb', got {color_mode!r}"
            )
        super().__init__()
        self.data_root = Path(data_root)
        self.split = split
        self.patch_size = patch_size
        self.augment = augment
        self.clahe_clip = clahe_clip
        self.pad_multiple = pad_multiple
        self.skip_missing = skip_missing
        self.color_mode = color_mode

        # Anti-leakage: validate split disjointness at class definition level
        self._check_split_disjoint()

        if split == 'train':
            self.ids = list(self.TRAIN_IDS)
        elif split == 'val':
            self.ids = list(self.VAL_IDS)
        elif split == 'test':
            self.ids = list(self.TEST_IDS)
        elif split == 'all':
            self.ids = list(self.TRAIN_IDS) + list(self.VAL_IDS)
        else:
            raise ValueError(f"split must be 'train'/'val'/'test'/'all', got {split!r}")

        # Validate paths exist (skip_missing allows deferred HPC validation)
        if not skip_missing:
            for sid in self.ids:
                img_p = self._img_path(sid)
                gt_p = self._gt_path(sid)
                if not img_p.exists():
                    raise FileNotFoundError(f"{self.__class__.__name__}: image not found: {img_p}")
                if not gt_p.exists():
                    raise FileNotFoundError(f"{self.__class__.__name__}: GT not found: {gt_p}")

    # ---------------------------------------------------------------------- #
    #  Anti-leakage: split disjoint check (RED LINE 1)
    # ---------------------------------------------------------------------- #

    @classmethod
    def _check_split_disjoint(cls):
        """Assert train / val / test ID sets are disjoint. Called at __init__."""
        train_set = set(cls.TRAIN_IDS)
        val_set = set(cls.VAL_IDS)
        test_set = set(cls.TEST_IDS)

        assert train_set.isdisjoint(val_set), (
            f"{cls.__name__}: TRAIN_IDS ∩ VAL_IDS = {train_set & val_set}"
        )
        assert train_set.isdisjoint(test_set), (
            f"{cls.__name__}: TRAIN_IDS ∩ TEST_IDS = {train_set & test_set}"
        )
        assert val_set.isdisjoint(test_set), (
            f"{cls.__name__}: VAL_IDS ∩ TEST_IDS = {val_set & test_set}"
        )

    # ---------------------------------------------------------------------- #
    #  Path helpers — subclasses MUST override
    # ---------------------------------------------------------------------- #

    def _img_path(self, sid) -> Path:
        raise NotImplementedError

    def _gt_path(self, sid) -> Path:
        raise NotImplementedError

    def _mask_path(self, sid) -> Path:
        """FOV mask path. Return path that may not exist (fallback = all-ones)."""
        raise NotImplementedError

    # ---------------------------------------------------------------------- #
    #  Loading primitives — subclasses may override for non-standard formats
    # ---------------------------------------------------------------------- #

    def _load_image(self, sid) -> np.ndarray:
        """Load image → float32 array.

        color_mode='green' (default):
            → (H, W) float32, green channel + CLAHE + normalize(0.5, 0.1).
            Used by all 11 baselines except CS-Net.

        color_mode='rgb':
            → (H, W, 3) float32, RGB /255 only, no CLAHE, no mean/std subtract.
            Matches CS-Net official dataloader: Image.open → transforms.ToTensor()
            (source: iMED-Lab/CS-Net dataloader/drive.py, confirmed 2026-06-25).

        Override in subclasses that have non-RGB or special format.
        """
        img_bgr = cv2.imread(str(self._img_path(sid)))
        assert img_bgr is not None, f"cv2 failed to read {self._img_path(sid)}"

        if self.color_mode == 'rgb':
            # RGB /255 — CS-Net official pipeline (no CLAHE, no normalization)
            img_rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
            return img_rgb.astype(np.float32) / 255.0   # (H, W, 3)

        # Default: green channel + CLAHE + normalize
        green = img_bgr[:, :, 1]  # green channel index=1 in BGR
        green_clahe = apply_clahe(green, clip_limit=self.clahe_clip)
        img_f = green_clahe.astype(np.float32) / 255.0
        img_f = (img_f - GREEN_MEAN) / GREEN_STD
        return img_f  # (H, W)

    def _load_gt(self, sid) -> np.ndarray:
        """Load GT mask → (H,W) uint8 {0,1}."""
        gt_raw = cv2.imread(str(self._gt_path(sid)), cv2.IMREAD_GRAYSCALE)
        assert gt_raw is not None, f"cv2 failed to read GT {self._gt_path(sid)}"
        return (gt_raw > 127).astype(np.uint8)

    def _load_fov(self, sid) -> np.ndarray:
        """Load FOV mask → (H,W) uint8 {0,1}. Fallback to all-ones if no mask file."""
        mask_path = self._mask_path(sid)
        if mask_path.exists():
            mask_raw = cv2.imread(str(mask_path), cv2.IMREAD_GRAYSCALE)
            if mask_raw is not None:
                return (mask_raw > 127).astype(np.uint8)
        # No FOV mask: use full image as valid region
        img_bgr = cv2.imread(str(self._img_path(sid)))
        h, w = img_bgr.shape[:2]
        return np.ones((h, w), dtype=np.uint8)

    def _load_sample(self, sid):
        """Load image + GT + FOV. Returns (img_f, gt, fov) all (H,W)."""
        img = self._load_image(sid)
        gt = self._load_gt(sid)
        fov = self._load_fov(sid)
        return img, gt, fov

    # ---------------------------------------------------------------------- #
    #  Augmentation (mirrors drive.py exactly)
    # ---------------------------------------------------------------------- #

    def _augment(self, img, gt, mask):
        """Random H-flip, V-flip, 90° rotation.
        Works for both (H,W) green and (H,W,3) RGB images.
        """
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
            # np.rot90 rotates in the first two axes (H,W) regardless of extra dims
            img = np.rot90(img, k).copy()
            gt = np.rot90(gt, k).copy()
            mask = np.rot90(mask, k).copy()
        return img, gt, mask

    # ---------------------------------------------------------------------- #
    #  Patch extraction (mirrors drive.py exactly)
    # ---------------------------------------------------------------------- #

    def _random_crop(self, img, gt, mask, size):
        h, w = img.shape[:2]
        if h < size or w < size:
            pad_h = max(0, size - h)
            pad_w = max(0, size - w)
            if img.ndim == 3:
                # (H, W, C) RGB mode
                img = np.pad(img, ((0, pad_h), (0, pad_w), (0, 0)), mode='reflect')
            else:
                img = np.pad(img, ((0, pad_h), (0, pad_w)), mode='reflect')
            gt = np.pad(gt, ((0, pad_h), (0, pad_w)), mode='constant')
            mask = np.pad(mask, ((0, pad_h), (0, pad_w)), mode='constant')
            h, w = img.shape[:2]
        y0 = random.randint(0, h - size)
        x0 = random.randint(0, w - size)
        return (img[y0:y0 + size, x0:x0 + size],
                gt[y0:y0 + size, x0:x0 + size],
                mask[y0:y0 + size, x0:x0 + size])

    def _center_pad(self, img, gt, mask):
        """Pad to pad_multiple boundary for full-image inference."""
        img_p, _ = pad_to_multiple(img, self.pad_multiple)
        gt_p, _ = pad_to_multiple(gt, self.pad_multiple)
        mask_p, _ = pad_to_multiple(mask, self.pad_multiple)
        return img_p, gt_p, mask_p

    # ---------------------------------------------------------------------- #
    #  __len__ / __getitem__ (dict contract identical to drive.py)
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

        # → tensor
        if self.color_mode == 'rgb':
            # img shape: (H, W, 3) → (3, H, W)
            img_t = torch.from_numpy(img).permute(2, 0, 1)   # (3, H, W)
        else:
            # img shape: (H, W) → (1, H, W)
            img_t = torch.from_numpy(img).unsqueeze(0)        # (1, H, W)
        gt_t = torch.from_numpy(gt.astype(np.float32)).unsqueeze(0)
        fov_t = torch.from_numpy(fov_mask.astype(np.float32)).unsqueeze(0)

        return {
            'image': img_t,   # (1,H,W) green or (3,H,W) RGB depending on color_mode
            'gt': gt_t,       # (1, H, W) float32 {0,1}
            'fov': fov_t,     # (1, H, W) float32 {0,1}
            'id': sid,
        }

    # ---------------------------------------------------------------------- #
    #  Tile inference helpers (512 sliding window for high-res datasets)
    # ---------------------------------------------------------------------- #

    def get_tiles(self, sid, tile_size: int = 512, overlap: int = 64) -> List[dict]:
        """
        Sliding-window tile extraction for inference on high-res images.
        Returns list of dicts each with: image (1,tile,tile), coords (y0,x0,y1,x1), id.

        gap_size_margin: tiles are generated such that any single tile boundary
        is at least (gap_size_margin) pixels from nearest tile edge, preventing
        benchmark gaps from spanning tile boundaries.
        Caller responsibility: pass gap_size+margin when filtering gap centres.
        """
        img, gt, fov = self._load_sample(sid)
        # Pad to tile_size multiple so last tile is full
        img_p, pad_info = pad_to_multiple(img, tile_size)
        gt_p, _ = pad_to_multiple(gt, tile_size)
        fov_p, _ = pad_to_multiple(fov, tile_size)
        H, W = img_p.shape

        stride = tile_size - overlap
        tiles = []
        for y0 in range(0, H - tile_size + 1, stride):
            for x0 in range(0, W - tile_size + 1, stride):
                y1 = y0 + tile_size
                x1 = x0 + tile_size
                img_tile = img_p[y0:y1, x0:x1]
                gt_tile = gt_p[y0:y1, x0:x1]
                fov_tile = fov_p[y0:y1, x0:x1]
                tiles.append({
                    'image': torch.from_numpy(img_tile).unsqueeze(0),
                    'gt': torch.from_numpy(gt_tile.astype(np.float32)).unsqueeze(0),
                    'fov': torch.from_numpy(fov_tile.astype(np.float32)).unsqueeze(0),
                    'coords': (y0, x0, y1, x1),  # in padded space
                    'pad_info': pad_info,          # (top,left,bottom,right)
                    'original_shape': img.shape,   # (H_orig, W_orig)
                    'id': sid,
                })
        return tiles

    def get_test_ids(self) -> List:
        """Return deterministic test split IDs (for benchmark evaluation)."""
        return list(self.TEST_IDS)

    def get_train_ids(self) -> List:
        return list(self.TRAIN_IDS)

    def get_val_ids(self) -> List:
        return list(self.VAL_IDS)
