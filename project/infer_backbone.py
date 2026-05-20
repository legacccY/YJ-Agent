"""Backbone-agnostic inference for BMVC §5.4 universality study.

After train_resnet50.py / train_vit_tiny.py finishes, this script loads the
best checkpoint and runs inference on:

  (a) degraded ISIC val (3 levels of each ISIC val image — used to fit QCTS
      because we need a q-bar distribution to recover alpha)
  (b) ITB subsets (LQ / HQ / Edge / Diverse — used to evaluate QCTS)

Outputs npy files per dataset into results/backbones/{name}/:
  degraded_val_logits.npy      (N, 2)
  degraded_val_qbar.npy        (N,)
  degraded_val_targets.npy     (N,)
  degraded_val_ids.npy         (N,)  isic_id strings
  itb_logits.npy               (M, 2)
  itb_qbar.npy                 (M,)
  itb_targets.npy              (M,)
  itb_subset.npy               (M,)  subset name per row
  itb_ids.npy                  (M,)

Usage:
    python project/infer_backbone.py \\
        --ckpt project/checkpoints/resnet50/best_resnet50.pth \\
        --output-dir project/results/backbones/resnet50

The backbone type is auto-detected from the ckpt['cfg']['backbone']['name'].
"""
import argparse
import os
import sys
from pathlib import Path

import cv2
import numpy as np
import pandas as pd
import torch
import torch.nn as nn
from torch.utils.data import DataLoader, Dataset
from torchvision import models, transforms
from tqdm import tqdm

THIS_DIR = Path(__file__).resolve().parent
if str(THIS_DIR) not in sys.path:
    sys.path.insert(0, str(THIS_DIR))

ROOT = Path("D:/YJ-Agent")
QUALITY_CSV = ROOT / "data/quality_labels_all.csv"
SPLIT_CSV = ROOT / "data/isic_split.csv"
METADATA_CSV = ROOT / "data/raw/isic2020/train-metadata.csv"
ITB_SUBSETS_CSV = THIS_DIR / "results/itb_subsets.csv"

IMAGENET_MEAN = [0.485, 0.456, 0.406]
IMAGENET_STD = [0.229, 0.224, 0.225]

os.environ.setdefault("OMP_NUM_THREADS", "1")


def build_eval_transform(img_size: int) -> transforms.Compose:
    return transforms.Compose([
        transforms.ToPILImage(),
        transforms.Resize(int(img_size * 1.14)),
        transforms.CenterCrop(img_size),
        transforms.ToTensor(),
        transforms.Normalize(mean=IMAGENET_MEAN, std=IMAGENET_STD),
    ])


class PathDataset(Dataset):
    """Loads images directly from a list of (path, qbar, target, id, [subset])."""

    def __init__(self, df: pd.DataFrame, img_size: int, has_subset: bool = False):
        self.df = df.reset_index(drop=True)
        self.transform = build_eval_transform(img_size)
        self.has_subset = has_subset

    def __len__(self):
        return len(self.df)

    def __getitem__(self, idx):
        row = self.df.iloc[idx]
        img = cv2.imread(str(row["image_path"]))
        if img is None:
            img = np.zeros((224, 224, 3), dtype=np.uint8)
        img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        out = {
            "image": self.transform(img),
            "qbar": float(row["qbar"]),
            "target": int(row["target"]),
            "isic_id": row["isic_id"],
        }
        if self.has_subset:
            out["subset"] = row["subset"]
        return out


def collate(batch):
    keys = batch[0].keys()
    out = {}
    for k in keys:
        if k == "image":
            out[k] = torch.stack([b[k] for b in batch], dim=0)
        elif k in ("qbar",):
            out[k] = torch.tensor([b[k] for b in batch], dtype=torch.float32)
        elif k in ("target",):
            out[k] = torch.tensor([b[k] for b in batch], dtype=torch.long)
        else:
            out[k] = [b[k] for b in batch]
    return out


def build_backbone(name: str, num_classes: int, **kwargs) -> nn.Module:
    name = name.lower()
    if name == "resnet50":
        weights = getattr(models.ResNet50_Weights, kwargs.get("weights", "IMAGENET1K_V2"))
        net = models.resnet50(weights=weights)
        in_feat = net.fc.in_features
        dropout = kwargs.get("dropout", 0.0)
        net.fc = nn.Sequential(nn.Dropout(p=dropout), nn.Linear(in_feat, num_classes))
        return net
    # Any timm model (deit, vit, convnext, swin, etc.)
    import timm
    if timm.is_model(name):
        return timm.create_model(
            name, pretrained=False, num_classes=num_classes,
            drop_rate=kwargs.get("drop_rate", 0.0),
            drop_path_rate=kwargs.get("drop_path_rate", 0.0),
        )
    raise ValueError(f"Unknown backbone: {name}")


def build_degraded_val_df() -> pd.DataFrame:
    """Each ISIC val image × 3 degradation levels, joined with target + qbar."""
    q = pd.read_csv(QUALITY_CSV)
    q = q[q["source"] == "isic2020"].copy()
    q["isic_id"] = q["original_path"].str.extract(r"(ISIC_\d+)", expand=False)
    split = pd.read_csv(SPLIT_CSV)
    val_ids = set(split[split["split"] == "val"]["isic_id"])
    q = q[q["isic_id"].isin(val_ids)].copy()
    meta = pd.read_csv(METADATA_CSV)[["isic_id", "target"]]
    q = q.merge(meta, on="isic_id", how="inner")
    q["qbar"] = q[["sharpness", "brightness", "completeness", "color_temp", "contrast"]].mean(axis=1)
    q["image_path"] = q["degraded_path"]
    df = q[["isic_id", "image_path", "target", "qbar", "level"]].reset_index(drop=True)
    print(f"[degraded_val] {len(df)} rows  ({df['level'].value_counts().to_dict()})")
    return df


def build_itb_df() -> pd.DataFrame:
    df = pd.read_csv(ITB_SUBSETS_CSV)[["subset", "isic_id", "image_path", "target", "qbar"]]
    print(f"[itb] {len(df)} rows  ({df['subset'].value_counts().to_dict()})")
    return df


@torch.no_grad()
def run_inference(model, df: pd.DataFrame, img_size: int, batch_size: int,
                  device, has_subset: bool):
    ds = PathDataset(df, img_size=img_size, has_subset=has_subset)
    loader = DataLoader(ds, batch_size=batch_size, shuffle=False, num_workers=0,
                        collate_fn=collate, pin_memory=True)
    model.eval()
    all_logits, all_qbar, all_targets, all_ids = [], [], [], []
    all_subsets = []
    for batch in tqdm(loader, desc="infer", leave=False):
        x = batch["image"].to(device, non_blocking=True)
        logits = model(x).float().cpu().numpy()
        all_logits.append(logits)
        all_qbar.append(batch["qbar"].numpy())
        all_targets.append(batch["target"].numpy())
        all_ids.extend(batch["isic_id"])
        if has_subset:
            all_subsets.extend(batch["subset"])
    out = {
        "logits": np.concatenate(all_logits, axis=0),
        "qbar":   np.concatenate(all_qbar, axis=0),
        "targets": np.concatenate(all_targets, axis=0),
        "ids":    np.array(all_ids),
    }
    if has_subset:
        out["subset"] = np.array(all_subsets)
    return out


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--ckpt", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--img-size", type=int, default=224)
    parser.add_argument("--batch-size", type=int, default=128)
    parser.add_argument("--backbone-name", default=None,
                        help="Override ckpt cfg backbone name (resnet50 / deit_tiny_patch16_224 / etc.)")
    args = parser.parse_args()

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"[load] ckpt={args.ckpt}")
    ckpt = torch.load(args.ckpt, map_location=device, weights_only=False)
    cfg_dict = ckpt.get("cfg", {})
    backbone_cfg = cfg_dict.get("backbone", {})

    if args.backbone_name:
        backbone_name = args.backbone_name
        kwargs = {}
    else:
        backbone_name = backbone_cfg.get("name", "resnet50")
        kwargs = {k: v for k, v in backbone_cfg.items() if k not in ("name", "num_classes")}
    print(f"[load] backbone={backbone_name}  kwargs={kwargs}")

    num_classes = backbone_cfg.get("num_classes", 2)
    model = build_backbone(backbone_name, num_classes=num_classes, **kwargs).to(device)
    model.load_state_dict(ckpt["model"])
    print(f"[load] params={sum(p.numel() for p in model.parameters())/1e6:.2f}M")

    # (a) degraded ISIC val
    deg_df = build_degraded_val_df()
    deg = run_inference(model, deg_df, args.img_size, args.batch_size, device, has_subset=False)
    np.save(out_dir / "degraded_val_logits.npy", deg["logits"])
    np.save(out_dir / "degraded_val_qbar.npy", deg["qbar"])
    np.save(out_dir / "degraded_val_targets.npy", deg["targets"])
    np.save(out_dir / "degraded_val_ids.npy", deg["ids"])
    print(f"[saved] degraded_val_*.npy  ({deg['logits'].shape})")

    # (b) ITB subsets
    itb_df = build_itb_df()
    itb = run_inference(model, itb_df, args.img_size, args.batch_size, device, has_subset=True)
    np.save(out_dir / "itb_logits.npy", itb["logits"])
    np.save(out_dir / "itb_qbar.npy", itb["qbar"])
    np.save(out_dir / "itb_targets.npy", itb["targets"])
    np.save(out_dir / "itb_subset.npy", itb["subset"])
    np.save(out_dir / "itb_ids.npy", itb["ids"])
    print(f"[saved] itb_*.npy  ({itb['logits'].shape})")

    print(f"\n[done] Inference complete -> {out_dir}")


if __name__ == "__main__":
    main()
