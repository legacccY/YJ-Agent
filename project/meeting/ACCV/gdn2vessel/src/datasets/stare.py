"""
STARE (STructured Analysis of the Retina) vessel dataset.

Kaggle pack (umairinayat/retinal-vessel-segmentation-datasets) layout
(confirmed via local ls 2026-06-20):

  <data_root>/
    images/
      im0001.ppm          (plain PPM, NOT gzipped in this pack)
      im0001.ppm.png      (PNG copy at 512×512, do NOT use — resized, non-canonical)
      im0002.ppm  ..  im0324.ppm  (20 images total, non-sequential IDs)
    masks/
      im0001.ah.ppm       (Hoover "ah" annotation, plain PPM)
      im0001.ah.ppm.png   (PNG copy — do NOT use for GT, resized+not binary-clean)
      im0001.vk.ppm       (Kouznetsova annotation — not used)
      ...

  We read *.ppm (plain PPM, 605×700) for images and *.ah.ppm for GT.
  The *.ppm.gz path is supported as fallback for HPC packs that gzip them.

  Resolution: 605×700 (h×w, confirmed via cv2.imread).
  Annotation: ah (Adam Hoover) — primary GT used by all major papers.
  FOV: No official mask → circular estimate ~90% min(H,W)/2.

Split convention (datasets.json: 'STARE 20 LOO'):
  LOO (leave-one-out) is the strict official evaluation protocol: train on 19,
  test on 1, repeat for all 20. We expose this via split='loo' + loo_index.
  For training baselines (single split), we use a deterministic 16/4 split
  (train=first 16 IDs, test=last 4) consistent with FR-UNet / SA-UNet.
  Val = last 4 of TRAIN_IDS (training_13..16 ≈ ids[12:16]).

  # TODO: Verify exact LOO vs fixed-split protocol used by FR-UNet / SA-UNet
  #       on STARE. Numbers here follow the most common literature convention.
  #       If researcher confirms LOO only, set split='loo' + loo_index in trainer.

Reference:
  Hoover et al., "Locating Blood Vessels in Retinal Images by Piecewise Threshold
  Probing of a Matched Filter Response" (IEEE TMI 2000).
  Data: http://cecas.clemson.edu/~ahoover/stare/

HPC root:  /gpfs/work/bio/jiayu2403/gdn2vessel/data/vessel/STARE/
Local root: D:/YJ-Agent/data/vessel/STARE/
(True root from .portfolio/datasets.json key='vessel_collection_kaggle')
"""

from __future__ import annotations

import gzip
import io
from pathlib import Path
from typing import List, Optional, Tuple

import cv2
import numpy as np

try:
    from PIL import Image as PILImage
    _HAS_PIL = True
except ImportError:
    _HAS_PIL = False

from datasets.base_vessel import BaseVesselDataset, apply_clahe, GREEN_MEAN, GREEN_STD


# --------------------------------------------------------------------------- #
#  STARE image IDs — non-sequential (confirmed from Kaggle pack 2026-06-20)
# --------------------------------------------------------------------------- #

_STARE_ALL_IDS: List[str] = [
    'im0001', 'im0002', 'im0003', 'im0004', 'im0005',
    'im0044', 'im0077', 'im0081', 'im0082', 'im0139',
    'im0162', 'im0163', 'im0235', 'im0236', 'im0239',
    'im0240', 'im0255', 'im0291', 'im0319', 'im0324',
]

assert len(_STARE_ALL_IDS) == 20, 'STARE should have exactly 20 images'


# --------------------------------------------------------------------------- #
#  PPM / ppm.gz loading helper
# --------------------------------------------------------------------------- #

def _load_ppm_gz(path: Path) -> np.ndarray:
    """Load a gzip-compressed PPM file. Returns (H,W,3) uint8 BGR array."""
    with gzip.open(str(path), 'rb') as f:
        ppm_bytes = f.read()
    if _HAS_PIL:
        img_pil = PILImage.open(io.BytesIO(ppm_bytes))
        img_rgb = np.array(img_pil)         # (H,W,3) RGB
        return img_rgb[:, :, ::-1].copy()   # RGB → BGR
    else:
        # Manual PPM P6 header parse
        lines = ppm_bytes.split(b'\n')
        header_lines: List[bytes] = []
        idx = 0
        while len(header_lines) < 3:
            line = lines[idx].strip()
            if not line.startswith(b'#'):
                header_lines.append(line)
            idx += 1
        assert header_lines[0] == b'P6', f'Expected P6 PPM, got {header_lines[0]}'
        w, h = map(int, header_lines[1].split())
        maxval = int(header_lines[2])
        header_end = ppm_bytes.index(b'\n', ppm_bytes.index(str(maxval).encode())) + 1
        pixel_data = ppm_bytes[header_end:]
        img_rgb = np.frombuffer(pixel_data, dtype=np.uint8).reshape(h, w, 3)
        return img_rgb[:, :, ::-1].copy()   # RGB → BGR


# --------------------------------------------------------------------------- #
#  STAREDataset
# --------------------------------------------------------------------------- #

class STAREDataset(BaseVesselDataset):
    """
    STARE retinal vessel dataset — ah (Hoover) annotation.

    Two split modes:
      1. Deterministic 12/4/4 (default — for baseline training):
           TRAIN_IDS: first 12 of _STARE_ALL_IDS
           VAL_IDS:   next 4
           TEST_IDS:  last 4 (held-out benchmark)

      2. Leave-One-Out (LOO) — for strict evaluation:
           Pass split='loo' and loo_index=i (0..19) to __init__.
           TRAIN_IDS = all 20 except index i; TEST_IDS = [id_i].
           # TODO: LOO trainer integration with loop runner (main-line task).

    Image format: .ppm (plain PPM in Kaggle pack, 605×700).
    Fallback: .ppm.gz (for HPC packs that compress — gracefully handled).
    """

    # Deterministic 12 / 4 / 4 split (default)
    TRAIN_IDS: List[str] = _STARE_ALL_IDS[:12]
    VAL_IDS:   List[str] = _STARE_ALL_IDS[12:16]
    TEST_IDS:  List[str] = _STARE_ALL_IDS[16:]

    def __init__(
        self,
        data_root: str,
        split: str = 'train',
        loo_index: Optional[int] = None,
        **kwargs,
    ):
        """
        Args:
            loo_index: If split='loo', the held-out image index (0-based in
                       _STARE_ALL_IDS). All others become the training set.
                       Ignored when split != 'loo'.
        """
        if split == 'loo' and loo_index is not None:
            # Dynamic LOO split — override class attrs for this instance
            test_id = _STARE_ALL_IDS[loo_index]
            train_ids = [x for x in _STARE_ALL_IDS if x != test_id]

            _orig_train = STAREDataset.TRAIN_IDS
            _orig_val   = STAREDataset.VAL_IDS
            _orig_test  = STAREDataset.TEST_IDS
            STAREDataset.TRAIN_IDS = train_ids
            STAREDataset.VAL_IDS   = []
            STAREDataset.TEST_IDS  = [test_id]
            try:
                # Map 'loo' → 'all' for parent (train+val → all 19 training)
                super().__init__(data_root=data_root, split='all', **kwargs)
            finally:
                STAREDataset.TRAIN_IDS = _orig_train
                STAREDataset.VAL_IDS   = _orig_val
                STAREDataset.TEST_IDS  = _orig_test
            self.ids = train_ids
            self.split = 'loo'
        else:
            super().__init__(data_root=data_root, split=split, **kwargs)

    # ---------------------------------------------------------------------- #
    #  Path helpers — Kaggle pack: plain .ppm, fallback .ppm.gz
    # ---------------------------------------------------------------------- #

    def _img_path(self, sid: str) -> Path:
        ppm     = self.data_root / 'images' / f'{sid}.ppm'
        ppm_gz  = self.data_root / 'images' / f'{sid}.ppm.gz'
        if ppm.exists():
            return ppm
        return ppm_gz  # fallback; FileNotFoundError raised by BaseVesselDataset if missing

    def _gt_path(self, sid: str) -> Path:
        plain = self.data_root / 'masks' / f'{sid}.ah.ppm'
        gz    = self.data_root / 'masks' / f'{sid}.ah.ppm.gz'
        if plain.exists():
            return plain
        return gz

    def _mask_path(self, sid: str) -> Path:
        # No official FOV mask → non-existent → fallback circular estimate
        return self.data_root / 'masks' / f'{sid}.fov.png'

    # ---------------------------------------------------------------------- #
    #  Override load primitives for .ppm / .ppm.gz format
    # ---------------------------------------------------------------------- #

    def _load_image(self, sid: str) -> np.ndarray:
        """Load STARE image (ppm or ppm.gz) → (H,W) float32 normalised green."""
        img_path = self._img_path(sid)
        if ''.join(img_path.suffixes) == '.ppm.gz':
            img_bgr = _load_ppm_gz(img_path)
        else:
            img_bgr = cv2.imread(str(img_path))
            assert img_bgr is not None, f'cv2 failed to read STARE image {img_path}'

        green = img_bgr[:, :, 1]
        green_clahe = apply_clahe(green, clip_limit=self.clahe_clip)
        img_f = green_clahe.astype(np.float32) / 255.0
        img_f = (img_f - GREEN_MEAN) / GREEN_STD
        return img_f  # (H, W)

    def _load_gt(self, sid: str) -> np.ndarray:
        """Load STARE GT (ppm or ppm.gz, ah annotation) → (H,W) uint8 {0,1}."""
        gt_path = self._gt_path(sid)
        if ''.join(gt_path.suffixes) == '.ppm.gz':
            gt_bgr  = _load_ppm_gz(gt_path)
            gt_gray = cv2.cvtColor(gt_bgr, cv2.COLOR_BGR2GRAY)
        else:
            gt_gray = cv2.imread(str(gt_path), cv2.IMREAD_GRAYSCALE)
            assert gt_gray is not None, f'cv2 failed to read STARE GT {gt_path}'

        return (gt_gray > 127).astype(np.uint8)

    def _load_fov(self, sid: str) -> np.ndarray:
        """STARE: no official FOV → circular estimate ~90% min(H,W)/2."""
        mask_path = self._mask_path(sid)
        if mask_path.exists():
            mask_raw = cv2.imread(str(mask_path), cv2.IMREAD_GRAYSCALE)
            if mask_raw is not None:
                return (mask_raw > 127).astype(np.uint8)

        # Derive shape from image
        img_path = self._img_path(sid)
        if ''.join(img_path.suffixes) == '.ppm.gz':
            img_bgr = _load_ppm_gz(img_path)
        else:
            img_bgr = cv2.imread(str(img_path))
            assert img_bgr is not None

        h, w = img_bgr.shape[:2]
        fov = np.zeros((h, w), dtype=np.uint8)
        cy, cx = h // 2, w // 2
        r = int(0.90 * min(h, w) / 2)
        cv2.circle(fov, (cx, cy), r, 1, -1)
        return fov
