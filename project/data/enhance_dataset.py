"""EnhanceDataset: pre-computed paired dataset for VisiEnhance-Net.

Uses already-degraded images from data/paired_dataset/{light,medium,heavy}/
paired with originals from quality_labels_all.csv.  No runtime degradation —
just read two image files, which keeps DataLoader fast and GPU utilisation high.

Each item returns (x_low, x_ref):
  x_low = pre-degraded image (already on disk, already 256px)
  x_ref = original high-quality image resized to img_size

Note: degraded_path images are already 256px; originals are resized to match.
"""

from pathlib import Path

import cv2
import numpy as np
import pandas as pd
import torch
from torch.utils.data import Dataset
from torchvision import transforms

_TO_TENSOR = transforms.ToTensor()


class EnhanceDataset(Dataset):
    """Paired dataset loading pre-computed degraded / original image pairs.

    Args:
        labels_csv:  quality_labels_all.csv — has degraded_path, original_path,
                     sharpness/brightness/completeness/color_temp/contrast, level.
        split_csv:   isic_split.csv — has isic_id + split columns.
        split:       'train' | 'val' | 'test'.
        img_size:    Both images resized to this square size.
        severity:    'light' | 'medium' | 'heavy' | 'mixed' (all three levels).
    """

    def __init__(
        self,
        labels_csv: str,
        split_csv: str,
        split: str = "train",
        img_size: int = 256,
        severity: str = "mixed",
    ):
        self.img_size = img_size

        labels = pd.read_csv(labels_csv)
        splits = pd.read_csv(split_csv)

        labels["isic_id"] = labels["original_path"].apply(lambda p: Path(p).stem)
        valid_ids = set(splits.loc[splits["split"] == split, "isic_id"].astype(str))

        df = labels[labels["isic_id"].isin(valid_ids)]

        if severity != "mixed":
            df = df[df["level"] == severity]

        # Keep only rows where both files exist
        df = df[
            df["degraded_path"].apply(lambda p: Path(p).exists()) &
            df["original_path"].apply(lambda p: Path(p).exists())
        ]
        self.df = df.reset_index(drop=True)

    def __len__(self) -> int:
        return len(self.df)

    def __getitem__(self, idx: int):
        row = self.df.iloc[idx]

        low_bgr = cv2.imread(str(row["degraded_path"]))
        ref_bgr = cv2.imread(str(row["original_path"]))

        if low_bgr is None or ref_bgr is None:
            t = torch.zeros(3, self.img_size, self.img_size)
            return t, t

        if low_bgr.shape[:2] != (self.img_size, self.img_size):
            low_bgr = cv2.resize(low_bgr, (self.img_size, self.img_size), interpolation=cv2.INTER_AREA)
        if ref_bgr.shape[:2] != (self.img_size, self.img_size):
            ref_bgr = cv2.resize(ref_bgr, (self.img_size, self.img_size), interpolation=cv2.INTER_AREA)

        x_low = _TO_TENSOR(cv2.cvtColor(low_bgr, cv2.COLOR_BGR2RGB))
        x_ref = _TO_TENSOR(cv2.cvtColor(ref_bgr, cv2.COLOR_BGR2RGB))
        return x_low, x_ref


# ── Keep degradation helpers for eval_visienhance.py compatibility ─────────────

import random

_DEG_CFG = {
    "mild":     {"blur_sigma": (0.5, 1.2), "brightness": (0.85, 1.0), "contrast": (0.85, 1.0), "color_shift": 0.04},
    "moderate": {"blur_sigma": (1.2, 2.5), "brightness": (0.55, 0.84), "contrast": (0.55, 0.84), "color_shift": 0.10},
    "severe":   {"blur_sigma": (2.5, 4.5), "brightness": (0.30, 0.54), "contrast": (0.30, 0.54), "color_shift": 0.18},
}
_DEG_PROBS = {"blur": 0.70, "brightness": 0.65, "contrast": 0.60, "color_shift": 0.50}


def _degrade_numpy(img: np.ndarray, severity: str, rng: random.Random) -> np.ndarray:
    cfg = _DEG_CFG[severity]
    out = img.astype(np.float32)
    if rng.random() < _DEG_PROBS["blur"]:
        sigma = rng.uniform(*cfg["blur_sigma"])
        ksize = int(2 * np.ceil(3 * sigma) + 1)
        out = cv2.GaussianBlur(out, (ksize, ksize), sigma)
    if rng.random() < _DEG_PROBS["brightness"]:
        out = np.clip(out * rng.uniform(*cfg["brightness"]), 0, 255)
    if rng.random() < _DEG_PROBS["contrast"]:
        alpha = rng.uniform(*cfg["contrast"])
        mean = out.mean(axis=(0, 1), keepdims=True)
        out = np.clip(alpha * (out - mean) + mean, 0, 255)
    if rng.random() < _DEG_PROBS["color_shift"]:
        shift = cfg["color_shift"] * 255
        for c in range(3):
            out[:, :, c] = np.clip(out[:, :, c] + rng.uniform(-shift, shift), 0, 255)
    return out.astype(np.uint8)
