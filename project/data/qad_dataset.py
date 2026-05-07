"""QAD Dataset: pairs degraded skin images with diagnostic labels + quality scores.

Joins:
  quality_labels_all.csv  (degraded_path, original_path, q1..q5, level, source)
  train-metadata.csv      (isic_id, target)
  abcd_cache.csv          (degraded_path, A, B, C, D)  -- pre-computed ABCD features
  efficientnet_index.csv  (degraded_path, efnet_row_idx)  -- optional EfficientNet index
  efficientnet_features.npy (N, 1280) float32 array       -- optional EfficientNet features

Cache mode (fast, for training):
  Pass abcd_cache_csv -> loads pre-computed ABCD, no live segmentation.
  Pass efnet_features_npy + efnet_index_csv -> also returns EfficientNet features (1280D).

Image mode (for eval with MobileSAM, legacy):
  abcd_cache_csv=None -> returns raw image.

__getitem__ returns (cache mode):
  abcd: torch.Tensor (4,)
  efnet_feat: torch.Tensor (1280,)  -- only when EfficientNet cache loaded
  q: torch.Tensor (5,)
  target: int
  level: str
  isic_id: str
"""

import re
from pathlib import Path

import cv2
import numpy as np
import pandas as pd
import torch
from torch.utils.data import Dataset


def _extract_isic_id(path_str: str) -> str | None:
    m = re.search(r"(ISIC_\d+)", str(path_str))
    return m.group(1) if m else None


SCORE_COLS = ["sharpness", "brightness", "completeness", "color_temp", "contrast"]
IMG_SIZE = 224


class QADDataset(Dataset):
    """Dataset for Q-VIB training and evaluation.

    Args:
        quality_csv: Path to quality_labels_all.csv.
        metadata_csv: Path to ISIC2020 train-metadata.csv.
        abcd_cache_csv: Pre-computed abcd_cache.csv (None = image mode).
        efnet_features_npy: Pre-computed EfficientNet features .npy (optional).
        efnet_index_csv: Index CSV mapping degraded_path -> efnet_row_idx (optional).
        levels: Filter by degradation level (None = all).
        source_filter: Filter by 'source' column.
    """

    def __init__(
        self,
        quality_csv: str | Path,
        metadata_csv: str | Path,
        abcd_cache_csv: str | Path | None = None,
        efnet_features_npy: str | Path | None = None,
        efnet_index_csv: str | Path | None = None,
        split_csv: str | Path | None = None,
        split: str | None = None,
        levels: list[str] | None = None,
        img_size: int = IMG_SIZE,
        source_filter: list[str] | None = None,
    ):
        q_df = pd.read_csv(quality_csv)
        meta_df = pd.read_csv(metadata_csv)[["isic_id", "target"]]

        q_df["isic_id"] = q_df["original_path"].apply(_extract_isic_id)
        df = q_df.merge(meta_df, on="isic_id", how="inner")

        # Proper train/val/test split by original image ID (no leakage)
        if split_csv is not None and split is not None:
            split_df = pd.read_csv(split_csv)[["isic_id", "split"]]
            df = df.merge(split_df, on="isic_id", how="inner")
            df = df[df["split"] == split]

        if levels:
            df = df[df["level"].isin(levels)]
        if source_filter:
            df = df[df["source"].isin(source_filter)]

        # Join pre-computed ABCD cache
        self._cache_mode = abcd_cache_csv is not None
        if self._cache_mode:
            cache_df = pd.read_csv(abcd_cache_csv)[["degraded_path", "A", "B", "C", "D"]]
            df = df.merge(cache_df, on="degraded_path", how="inner")

        self.df = df.reset_index(drop=True)
        self.img_size = img_size

        # EfficientNet feature cache
        self._efnet_features: np.ndarray | None = None
        self._efnet_path_to_idx: dict | None = None
        if efnet_features_npy is not None and efnet_index_csv is not None:
            self._efnet_features = np.load(efnet_features_npy)
            idx_df = pd.read_csv(efnet_index_csv)
            self._efnet_path_to_idx = dict(
                zip(idx_df["degraded_path"].astype(str), idx_df["efnet_row_idx"])
            )

        # Class weights for imbalanced training
        counts = self.df["target"].value_counts().sort_index()
        total = counts.sum()
        self._class_weights = torch.tensor(
            [total / (len(counts) * c) for c in counts.values],
            dtype=torch.float32,
        )

    def __len__(self) -> int:
        return len(self.df)

    @property
    def class_weights(self) -> torch.Tensor:
        return self._class_weights

    def __getitem__(self, idx: int) -> dict:
        row = self.df.iloc[idx]
        q = torch.tensor(row[SCORE_COLS].values.astype(np.float32), dtype=torch.float32)

        result = {
            "q": q,
            "target": int(row["target"]),
            "level": str(row["level"]),
            "isic_id": str(row["isic_id"]),
        }

        if self._cache_mode:
            result["abcd"] = torch.tensor(
                [row["A"], row["B"], row["C"], row["D"]], dtype=torch.float32
            )
        else:
            img = cv2.imread(str(row["degraded_path"]))
            if img is None:
                img = cv2.imread(str(row["original_path"]))
            if img is None:
                img = np.zeros((self.img_size, self.img_size, 3), dtype=np.uint8)
            else:
                img = cv2.resize(img, (self.img_size, self.img_size))
            result["image_bgr"] = img

        # Attach EfficientNet features if cache is loaded
        if self._efnet_features is not None and self._efnet_path_to_idx is not None:
            row_idx = self._efnet_path_to_idx.get(str(row["degraded_path"]), None)
            if row_idx is not None:
                result["efnet_feat"] = torch.from_numpy(
                    self._efnet_features[int(row_idx)].copy()
                )
            else:
                result["efnet_feat"] = torch.zeros(self._efnet_features.shape[1])

        return result


def qad_collate_fn(batch: list[dict]) -> dict:
    """Collate for cache mode (abcd tensor) or image mode (raw BGR), with optional efnet."""
    out: dict = {
        "q": torch.stack([b["q"] for b in batch]),
        "target": torch.tensor([b["target"] for b in batch], dtype=torch.long),
        "level": [b["level"] for b in batch],
        "isic_id": [b["isic_id"] for b in batch],
    }
    if "abcd" in batch[0]:
        out["abcd"] = torch.stack([b["abcd"] for b in batch])
    else:
        out["images_bgr"] = [b["image_bgr"] for b in batch]

    if "efnet_feat" in batch[0]:
        out["efnet_feat"] = torch.stack([b["efnet_feat"] for b in batch])

    return out
