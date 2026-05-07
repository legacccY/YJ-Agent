"""Precompute EfficientNet-B0 (ImageNet pretrained) features for all degraded images.

Outputs:
  D:/YJ-Agent/data/efficientnet_features.npy  -- (N, 1280) float32 array
  D:/YJ-Agent/data/efficientnet_index.csv     -- degraded_path, efnet_row_idx

Speed: ~500 img/sec on RTX 4070, ~5 min for 149100 images.
Resume: delete output files and rerun to recompute.
"""

from pathlib import Path

import cv2
import numpy as np
import pandas as pd
import torch
import torch.nn as nn
from torch.utils.data import DataLoader, Dataset
from torchvision import transforms
from torchvision.models import EfficientNet_B0_Weights, efficientnet_b0
from tqdm import tqdm

LABELS_CSV = "D:/YJ-Agent/data/quality_labels_all.csv"
OUT_NPY    = "D:/YJ-Agent/data/efficientnet_features.npy"
OUT_IDX    = "D:/YJ-Agent/data/efficientnet_index.csv"
BATCH_SIZE = 256
IMG_SIZE   = 224
NUM_WORKERS = 4


class ImagePathDataset(Dataset):
    def __init__(self, paths: list[str]):
        self.paths = paths
        self.tfm = transforms.Compose([
            transforms.ToTensor(),
            transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
        ])

    def __len__(self) -> int:
        return len(self.paths)

    def __getitem__(self, i: int):
        img = cv2.imread(str(self.paths[i]))
        if img is None:
            img = np.zeros((IMG_SIZE, IMG_SIZE, 3), dtype=np.uint8)
        else:
            img = cv2.resize(img, (IMG_SIZE, IMG_SIZE))
        img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        return self.tfm(img), i


def main():
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"Device: {device}")

    if Path(OUT_NPY).exists() and Path(OUT_IDX).exists():
        print("Output files already exist. Delete them to recompute.")
        return

    df = pd.read_csv(LABELS_CSV)
    paths = df["degraded_path"].tolist()
    N = len(paths)
    print(f"Total images: {N}")

    base = efficientnet_b0(weights=EfficientNet_B0_Weights.DEFAULT)
    extractor = nn.Sequential(base.features, base.avgpool, nn.Flatten()).to(device).eval()

    dataset = ImagePathDataset(paths)
    loader = DataLoader(
        dataset, batch_size=BATCH_SIZE, num_workers=NUM_WORKERS,
        multiprocessing_context="spawn", pin_memory=False,
    )

    features = np.zeros((N, 1280), dtype=np.float32)

    with torch.no_grad():
        for imgs, idxs in tqdm(loader, desc="EfficientNet features"):
            feats = extractor(imgs.to(device)).cpu().numpy()
            features[idxs.numpy()] = feats

    np.save(OUT_NPY, features)
    pd.DataFrame({
        "degraded_path": paths,
        "efnet_row_idx": range(N),
    }).to_csv(OUT_IDX, index=False)

    print(f"Saved {N} features -> {OUT_NPY}")
    print(f"Index   -> {OUT_IDX}")


if __name__ == "__main__":
    main()
