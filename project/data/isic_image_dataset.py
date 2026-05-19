"""ISIC 2020 image classification dataset for BMVC §5.4 backbone universality.

Loads raw ISIC 2020 images by isic_id, returns (image_tensor, target_int).
Used by train_resnet50.py / train_vit_tiny.py — pure backbone baselines,
no ABCD / quality tokens.

Split source: D:/YJ-Agent/data/isic_split.csv (train 23188 / val 3312 / test 6626)
"""
from pathlib import Path

import cv2
import numpy as np
import pandas as pd
import torch
from torch.utils.data import Dataset
from torchvision import transforms

ISIC_IMAGE_ROOT = Path("D:/YJ-Agent/data/raw/isic2020/train-image/image")
METADATA_CSV = Path("D:/YJ-Agent/data/raw/isic2020/train-metadata.csv")
SPLIT_CSV = Path("D:/YJ-Agent/data/isic_split.csv")

IMAGENET_MEAN = [0.485, 0.456, 0.406]
IMAGENET_STD = [0.229, 0.224, 0.225]


def build_transform(img_size: int, train: bool) -> transforms.Compose:
    if train:
        return transforms.Compose([
            transforms.ToPILImage(),
            transforms.RandomResizedCrop(img_size, scale=(0.7, 1.0)),
            transforms.RandomHorizontalFlip(),
            transforms.RandomVerticalFlip(),
            transforms.ColorJitter(brightness=0.1, contrast=0.1, saturation=0.1),
            transforms.ToTensor(),
            transforms.Normalize(mean=IMAGENET_MEAN, std=IMAGENET_STD),
        ])
    return transforms.Compose([
        transforms.ToPILImage(),
        transforms.Resize(int(img_size * 1.14)),
        transforms.CenterCrop(img_size),
        transforms.ToTensor(),
        transforms.Normalize(mean=IMAGENET_MEAN, std=IMAGENET_STD),
    ])


class ISICImageDataset(Dataset):
    """Returns (image_tensor[3,H,W], target_int, isic_id_str)."""

    def __init__(
        self,
        split: str,
        img_size: int = 224,
        image_root: str | Path = ISIC_IMAGE_ROOT,
        metadata_csv: str | Path = METADATA_CSV,
        split_csv: str | Path = SPLIT_CSV,
    ):
        assert split in {"train", "val", "test"}, f"unknown split {split}"
        self.image_root = Path(image_root)
        meta = pd.read_csv(metadata_csv)[["isic_id", "target"]]
        sp = pd.read_csv(split_csv)
        df = meta.merge(sp, on="isic_id", how="inner")
        df = df[df["split"] == split].reset_index(drop=True)

        missing = ~df["isic_id"].map(lambda x: (self.image_root / f"{x}.jpg").exists())
        if missing.any():
            n_missing = int(missing.sum())
            print(f"[ISICImageDataset] {split}: dropping {n_missing} samples without image file")
            df = df[~missing].reset_index(drop=True)

        self.df = df
        self.split = split
        self.transform = build_transform(img_size, train=(split == "train"))

        targets = self.df["target"].values
        n_pos = int((targets == 1).sum())
        n_neg = int((targets == 0).sum())
        self.class_weights = torch.tensor(
            [1.0, n_neg / max(n_pos, 1)], dtype=torch.float32
        )

    def __len__(self) -> int:
        return len(self.df)

    def __getitem__(self, idx: int):
        row = self.df.iloc[idx]
        path = self.image_root / f"{row['isic_id']}.jpg"
        img = cv2.imread(str(path))
        if img is None:
            img = np.zeros((224, 224, 3), dtype=np.uint8)
        img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        tensor = self.transform(img)
        target = int(row["target"])
        return tensor, target, row["isic_id"]


def isic_collate(batch):
    imgs = torch.stack([b[0] for b in batch], dim=0)
    targets = torch.tensor([b[1] for b in batch], dtype=torch.long)
    ids = [b[2] for b in batch]
    return {"image": imgs, "target": targets, "isic_id": ids}
