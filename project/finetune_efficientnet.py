"""Fine-tune EfficientNet-B3 on ISIC2020 original (clean) images.

Pipeline:
  1. Load ISIC2020 original images from train split (70% by isic_id)
  2. Fine-tune EfficientNet-B3 with comprehensive augmentation
  3. Select best checkpoint by val AUC (not accuracy)
  4. Save to D:/YJ-Agent/checkpoints/efficientnet_b3_isic.pth

Expected: val AUC ~0.83–0.87 after 20 epochs on RTX 4070.

Usage:
    python finetune_efficientnet.py
"""

import os
import time
from pathlib import Path

import numpy as np
import pandas as pd
import torch
import torch.nn as nn
from PIL import Image
from sklearn.metrics import roc_auc_score
from torch.utils.data import DataLoader, Dataset, WeightedRandomSampler
from torchvision import transforms
from torchvision.models import EfficientNet_B3_Weights, efficientnet_b3
from tqdm import tqdm

META_CSV  = "D:/YJ-Agent/data/raw/isic2020/train-metadata.csv"
SPLIT_CSV = "D:/YJ-Agent/data/isic_split.csv"
IMG_DIR   = "D:/YJ-Agent/data/raw/isic2020/train-image/image"
OUT_CKPT  = "D:/YJ-Agent/checkpoints/efficientnet_b3_isic.pth"
EPOCHS    = 25
BATCH     = 32
LR        = 1e-4
SEED      = 42

TRAIN_TFM = transforms.Compose([
    transforms.RandomResizedCrop(224, scale=(0.7, 1.0)),
    transforms.RandomHorizontalFlip(),
    transforms.RandomVerticalFlip(),
    transforms.RandomRotation(90),
    transforms.ColorJitter(brightness=0.3, contrast=0.3, saturation=0.3, hue=0.1),
    transforms.ToTensor(),
    transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
])
VAL_TFM = transforms.Compose([
    transforms.Resize(256),
    transforms.CenterCrop(224),
    transforms.ToTensor(),
    transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
])


class ISICDataset(Dataset):
    def __init__(self, meta_csv, split_csv, split, img_dir, transform):
        meta = pd.read_csv(meta_csv)[["isic_id", "target"]]
        splits = pd.read_csv(split_csv)
        df = meta.merge(splits, on="isic_id").query(f"split == '{split}'").reset_index(drop=True)
        self.df = df
        self.img_dir = Path(img_dir)
        self.transform = transform

    def __len__(self):
        return len(self.df)

    def __getitem__(self, idx):
        row = self.df.iloc[idx]
        img = Image.open(self.img_dir / f"{row['isic_id']}.jpg").convert("RGB")
        return self.transform(img), int(row["target"])

    @property
    def targets(self):
        return self.df["target"].values


def build_sampler(targets):
    counts = np.bincount(targets)
    weights = 1.0 / counts[targets]
    return WeightedRandomSampler(torch.from_numpy(weights).float(), len(weights), replacement=True)


def run_epoch(phase, loader, model, criterion, optimizer, scaler, device):
    is_train = phase == "train"
    model.train(is_train)
    total_loss, all_probs, all_targets = 0.0, [], []

    for imgs, targets in tqdm(loader, desc=phase, leave=False):
        imgs, targets = imgs.to(device), targets.to(device)
        with torch.set_grad_enabled(is_train):
            with torch.amp.autocast("cuda"):
                logits = model(imgs)
                loss = criterion(logits, targets)
        if is_train:
            optimizer.zero_grad()
            scaler.scale(loss).backward()
            scaler.step(optimizer)
            scaler.update()
        total_loss += loss.item()
        probs = torch.softmax(logits.detach(), dim=-1)[:, 1].cpu().numpy()
        all_probs.extend(probs)
        all_targets.extend(targets.cpu().numpy())

    auc = float(roc_auc_score(all_targets, all_probs))
    return total_loss / len(loader), auc


def main():
    torch.manual_seed(SEED)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"Device: {device}")

    train_ds = ISICDataset(META_CSV, SPLIT_CSV, "train", IMG_DIR, TRAIN_TFM)
    val_ds   = ISICDataset(META_CSV, SPLIT_CSV, "val",   IMG_DIR, VAL_TFM)
    print(f"Train: {len(train_ds)}  Val: {len(val_ds)}")
    print(f"Melanoma rate: {train_ds.targets.mean()*100:.1f}%")

    train_loader = DataLoader(
        train_ds, batch_size=BATCH, sampler=build_sampler(train_ds.targets),
        num_workers=4, multiprocessing_context="spawn", pin_memory=False, persistent_workers=True,
    )
    val_loader = DataLoader(
        val_ds, batch_size=BATCH * 2, shuffle=False,
        num_workers=4, multiprocessing_context="spawn", pin_memory=False, persistent_workers=True,
    )

    model = efficientnet_b3(weights=EfficientNet_B3_Weights.DEFAULT)
    in_features = model.classifier[1].in_features  # 1536
    model.classifier = nn.Sequential(
        nn.Dropout(p=0.3, inplace=True),
        nn.Linear(in_features, 2),
    )
    model = model.to(device)

    # class-weighted CE for imbalance
    pos_rate = train_ds.targets.mean()
    class_weights = torch.tensor([pos_rate, 1 - pos_rate], dtype=torch.float32).to(device)
    criterion = nn.CrossEntropyLoss(weight=class_weights)

    optimizer = torch.optim.AdamW(model.parameters(), lr=LR, weight_decay=1e-4)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=EPOCHS)
    scaler    = torch.amp.GradScaler("cuda")

    Path(OUT_CKPT).parent.mkdir(parents=True, exist_ok=True)
    best_auc = 0.0

    for epoch in range(EPOCHS):
        t0 = time.time()
        tr_loss, tr_auc = run_epoch("train", train_loader, model, criterion, optimizer, scaler, device)
        vl_loss, vl_auc = run_epoch("val",   val_loader,   model, criterion, optimizer, scaler, device)
        scheduler.step()
        elapsed = time.time() - t0

        print(
            f"Epoch {epoch+1}/{EPOCHS} | "
            f"tr_loss={tr_loss:.4f} tr_AUC={tr_auc:.4f} | "
            f"val_loss={vl_loss:.4f} val_AUC={vl_auc:.4f} | "
            f"{elapsed:.0f}s"
        )

        if vl_auc > best_auc:
            best_auc = vl_auc
            torch.save({
                "epoch": epoch,
                "model": model.state_dict(),
                "val_auc": vl_auc,
                "in_features": in_features,
            }, OUT_CKPT)
            print(f"  => Best val AUC: {best_auc:.4f}")

    print(f"\nDone. Best val AUC: {best_auc:.4f}  ->  {OUT_CKPT}")


if __name__ == "__main__":
    main()
