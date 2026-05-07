"""Extract features from fine-tuned EfficientNet-B3 on all degraded images.

Outputs:
  D:/YJ-Agent/data/finetuned_features.npy   -- (N, 1536) float32
  D:/YJ-Agent/data/finetuned_index.csv      -- degraded_path, row_idx

Usage:
    python precompute_finetuned_features.py
"""

from pathlib import Path

import cv2
import numpy as np
import pandas as pd
import torch
import torch.nn as nn
from torch.utils.data import DataLoader, Dataset
from torchvision import transforms
from torchvision.models import EfficientNet_B3_Weights, efficientnet_b3
from tqdm import tqdm

LABELS_CSV = "D:/YJ-Agent/data/quality_labels_all.csv"
CKPT       = "D:/YJ-Agent/checkpoints/efficientnet_b3_isic.pth"
OUT_NPY    = "D:/YJ-Agent/data/finetuned_features.npy"
OUT_IDX    = "D:/YJ-Agent/data/finetuned_index.csv"
BATCH_SIZE = 128
IMG_SIZE   = 224
NUM_WORKERS = 4

TFM = transforms.Compose([
    transforms.ToTensor(),
    transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
])


class ImagePathDataset(Dataset):
    def __init__(self, paths):
        self.paths = paths

    def __len__(self):
        return len(self.paths)

    def __getitem__(self, i):
        img = cv2.imread(str(self.paths[i]))
        if img is None:
            img = np.zeros((IMG_SIZE, IMG_SIZE, 3), dtype=np.uint8)
        else:
            img = cv2.resize(img, (IMG_SIZE, IMG_SIZE))
        img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        return TFM(img), i


def main():
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"Device: {device}")

    if Path(OUT_NPY).exists() and Path(OUT_IDX).exists():
        print("Output already exists. Delete to recompute.")
        return

    df = pd.read_csv(LABELS_CSV)
    paths = df["degraded_path"].tolist()
    N = len(paths)
    print(f"Total images: {N}")

    # Load fine-tuned model, strip classifier
    base = efficientnet_b3(weights=None)
    in_features = base.classifier[1].in_features
    base.classifier = nn.Sequential(nn.Dropout(p=0.3, inplace=True), nn.Linear(in_features, 2))
    ckpt = torch.load(CKPT, map_location=device)
    base.load_state_dict(ckpt["model"])

    # Feature extractor: up to avg pool
    extractor = nn.Sequential(base.features, base.avgpool, nn.Flatten()).to(device).eval()

    dataset = ImagePathDataset(paths)
    loader  = DataLoader(dataset, batch_size=BATCH_SIZE, num_workers=NUM_WORKERS,
                         multiprocessing_context="spawn", pin_memory=False)

    feat_dim = ckpt.get("in_features", in_features)
    features = np.zeros((N, feat_dim), dtype=np.float32)

    with torch.no_grad():
        for imgs, idxs in tqdm(loader, desc="Finetuned features"):
            feats = extractor(imgs.to(device)).cpu().numpy()
            features[idxs.numpy()] = feats

    np.save(OUT_NPY, features)
    pd.DataFrame({"degraded_path": paths, "efnet_row_idx": range(N)}).to_csv(OUT_IDX, index=False)
    print(f"Saved ({N}, {feat_dim}) -> {OUT_NPY}")


if __name__ == "__main__":
    main()
