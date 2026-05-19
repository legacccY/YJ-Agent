"""ImageNet-C style corruption robustness test — BMVC §5.4 / §5.5 appendix.

用 imagecorruptions 对 ITB-LQ 或 ISIC val 测试集做 15 种腐蚀 × 5 级别推理，
输出每个 (corruption, severity) 的 AUC / ECE，保存到 CSV。

Usage:
    python project/scripts/test_corruption_robustness.py \\
        --ckpt project/checkpoints/resnet50/best_resnet50.pth \\
        --output-dir project/results/backbones/resnet50 \\
        --split itb-lq

    python project/scripts/test_corruption_robustness.py \\
        --ckpt project/checkpoints/vit_tiny/best_vit_tiny_patch16_224.pth \\
        --output-dir project/results/backbones/vit_tiny \\
        --split itb-lq
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

THIS_DIR = Path(__file__).resolve().parent.parent  # project/
ROOT = Path("D:/YJ-Agent")
SPLIT_CSV = ROOT / "data/isic_split.csv"
METADATA_CSV = ROOT / "data/raw/isic2020/train-metadata.csv"
IMAGE_ROOT = ROOT / "data/raw/isic2020/train-image/image"
ITB_SUBSETS_CSV = THIS_DIR / "results/itb_subsets.csv"
QUALITY_CSV = ROOT / "data/quality_labels_all.csv"

IMAGENET_MEAN = [0.485, 0.456, 0.406]
IMAGENET_STD  = [0.229, 0.224, 0.225]

os.environ.setdefault("OMP_NUM_THREADS", "1")

# imagecorruptions 全部 15 种腐蚀类型
CORRUPTIONS = [
    "gaussian_noise", "shot_noise", "impulse_noise",
    "defocus_blur", "motion_blur", "zoom_blur",
    "snow", "frost", "fog", "brightness",
    "contrast", "elastic_transform", "pixelate", "jpeg_compression",
]  # glass_blur excluded: pure-Python pixel loop is O(H*W) per image, prohibitively slow
SEVERITIES = [1, 2, 3, 4, 5]


# ── Model ──────────────────────────────────────────────────────────────────────

def build_backbone(name: str, num_classes: int, **kwargs) -> nn.Module:
    name = name.lower()
    if name == "resnet50":
        weights = getattr(models.ResNet50_Weights, kwargs.get("weights", "IMAGENET1K_V2"))
        net = models.resnet50(weights=weights)
        in_feat = net.fc.in_features
        dropout = kwargs.get("dropout", 0.0)
        net.fc = nn.Sequential(nn.Dropout(p=dropout), nn.Linear(in_feat, num_classes))
        return net
    if name.startswith("deit") or name.startswith("vit"):
        import timm
        return timm.create_model(
            name, pretrained=False, num_classes=num_classes,
            drop_rate=kwargs.get("drop_rate", 0.0),
            drop_path_rate=kwargs.get("drop_path_rate", 0.0),
        )
    raise ValueError(f"Unknown backbone: {name}")


def load_model(ckpt_path: str, device):
    ckpt = torch.load(ckpt_path, map_location=device, weights_only=False)
    cfg = ckpt.get("cfg", {})
    b_cfg = cfg.get("backbone", {})
    name = b_cfg.get("name", "resnet50")
    kwargs = {k: v for k, v in b_cfg.items() if k not in ("name", "num_classes")}
    num_classes = b_cfg.get("num_classes", 2)
    model = build_backbone(name, num_classes=num_classes, **kwargs).to(device)
    model.load_state_dict(ckpt["model"])
    model.eval()
    print(f"[model] {name}  {sum(p.numel() for p in model.parameters())/1e6:.2f}M params")
    return model, cfg


# ── Dataset ────────────────────────────────────────────────────────────────────

def build_eval_transform(img_size: int) -> transforms.Compose:
    return transforms.Compose([
        transforms.ToPILImage(),
        transforms.Resize(int(img_size * 1.14)),
        transforms.CenterCrop(img_size),
        transforms.ToTensor(),
        transforms.Normalize(mean=IMAGENET_MEAN, std=IMAGENET_STD),
    ])


class CorruptionDataset(Dataset):
    """Loads raw images + applies imagecorruptions on-the-fly."""

    def __init__(self, df: pd.DataFrame, img_size: int,
                 corruption: str | None, severity: int | None):
        self.df = df.reset_index(drop=True)
        self.transform = build_eval_transform(img_size)
        self.corruption = corruption
        self.severity = severity

    def __len__(self):
        return len(self.df)

    def __getitem__(self, idx):
        row = self.df.iloc[idx]
        img = cv2.imread(str(row["image_path"]))
        if img is None:
            img = np.zeros((224, 224, 3), dtype=np.uint8)
        img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)  # HxWxC uint8

        if self.corruption is not None:
            from imagecorruptions import corrupt
            img = corrupt(img, corruption_name=self.corruption,
                          severity=self.severity)

        return {
            "image": self.transform(img),
            "target": int(row["target"]),
            "isic_id": row["isic_id"],
        }


def collate(batch):
    return {
        "image":   torch.stack([b["image"] for b in batch]),
        "target":  torch.tensor([b["target"] for b in batch], dtype=torch.long),
        "isic_id": [b["isic_id"] for b in batch],
    }


# ── Metrics ────────────────────────────────────────────────────────────────────

from sklearn.metrics import roc_auc_score
from scipy.special import expit


def compute_ece(probs: np.ndarray, targets: np.ndarray, n_bins: int = 15) -> float:
    bins = np.linspace(0, 1, n_bins + 1)
    ece = 0.0
    for lo, hi in zip(bins[:-1], bins[1:]):
        mask = (probs >= lo) & (probs < hi)
        if mask.sum() == 0:
            continue
        acc = targets[mask].mean()
        conf = probs[mask].mean()
        ece += mask.mean() * abs(acc - conf)
    return float(ece)


def eval_logits(logits: np.ndarray, targets: np.ndarray) -> dict:
    binary_logit = logits[:, 1] - logits[:, 0]
    probs = expit(binary_logit)
    try:
        auc = float(roc_auc_score(targets, probs))
    except Exception:
        auc = float("nan")
    ece = compute_ece(probs, targets)
    return {"auc": auc, "ece": ece, "n": len(targets)}


# ── Data loading ───────────────────────────────────────────────────────────────

def load_split_df(split: str) -> pd.DataFrame:
    """Return DataFrame with [isic_id, image_path, target] for the requested split."""
    if split == "itb-lq":
        df = pd.read_csv(ITB_SUBSETS_CSV)
        df = df[df["subset"] == "ITB-LQ"][["isic_id", "image_path", "target"]].copy()
        print(f"[data] ITB-LQ: {len(df)} images")
        return df

    if split in ("val", "test"):
        split_df = pd.read_csv(SPLIT_CSV)
        ids = set(split_df[split_df["split"] == split]["isic_id"])
        meta = pd.read_csv(METADATA_CSV)[["isic_id", "target"]]
        meta = meta[meta["isic_id"].isin(ids)].copy()
        meta["image_path"] = meta["isic_id"].apply(
            lambda x: str(IMAGE_ROOT / f"{x}.jpg")
        )
        print(f"[data] ISIC2020 {split}: {len(meta)} images")
        return meta.reset_index(drop=True)

    raise ValueError(f"Unknown split: {split!r}. Use itb-lq / val / test")


# ── Main ───────────────────────────────────────────────────────────────────────

@torch.no_grad()
def run_corruption(model, df, img_size, batch_size, device,
                   corruption, severity) -> dict:
    ds = CorruptionDataset(df, img_size=img_size,
                           corruption=corruption, severity=severity)
    loader = DataLoader(ds, batch_size=batch_size, shuffle=False,
                        num_workers=0, collate_fn=collate, pin_memory=True)
    all_logits, all_targets = [], []
    for batch in loader:
        x = batch["image"].to(device, non_blocking=True)
        logits = model(x).float().cpu().numpy()
        all_logits.append(logits)
        all_targets.append(batch["target"].numpy())
    logits = np.concatenate(all_logits, 0)
    targets = np.concatenate(all_targets, 0)
    return eval_logits(logits, targets)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--ckpt", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--split", default="itb-lq",
                        choices=["itb-lq", "val", "test"])
    parser.add_argument("--img-size", type=int, default=224)
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--corruptions", nargs="+", default=CORRUPTIONS,
                        help="Subset of corruptions to run (default: all 15)")
    parser.add_argument("--severities", nargs="+", type=int, default=SEVERITIES)
    args = parser.parse_args()

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    model, cfg = load_model(args.ckpt, device)
    img_size = cfg.get("data", {}).get("img_size", args.img_size)
    df = load_split_df(args.split)

    # ── Clean baseline (no corruption) ─────────────────────────────────────
    print("\n[clean] running baseline...")
    clean = run_corruption(model, df, img_size, args.batch_size, device, None, None)
    print(f"  AUC={clean['auc']:.4f}  ECE={clean['ece']:.4f}  n={clean['n']}")

    rows = [{"corruption": "clean", "severity": 0, **clean}]

    # ── Per corruption × severity ───────────────────────────────────────────
    total = len(args.corruptions) * len(args.severities)
    pbar = tqdm(total=total, desc="corruptions")
    for corr in args.corruptions:
        for sev in args.severities:
            res = run_corruption(model, df, img_size, args.batch_size, device, corr, sev)
            rows.append({"corruption": corr, "severity": sev, **res})
            pbar.set_postfix(corr=corr, sev=sev, auc=f"{res['auc']:.3f}")
            pbar.update(1)
    pbar.close()

    # ── Save ────────────────────────────────────────────────────────────────
    result_df = pd.DataFrame(rows)
    out_path = out_dir / f"corruption_robustness_{args.split}.csv"
    result_df.to_csv(out_path, index=False)
    print(f"\n[saved] {out_path}")

    # ── Quick summary ────────────────────────────────────────────────────────
    avg = result_df[result_df["corruption"] != "clean"].groupby("corruption")[["auc", "ece"]].mean()
    avg = avg.sort_values("auc", ascending=False)
    print("\n=== Mean AUC / ECE per corruption type (across severities) ===")
    print(avg.to_string(float_format="{:.4f}".format))

    mce_auc = result_df[result_df["corruption"] != "clean"]["auc"].mean()
    mce_ece = result_df[result_df["corruption"] != "clean"]["ece"].mean()
    print(f"\nMean Corruption Error  AUC={mce_auc:.4f}  ECE={mce_ece:.4f}")
    print(f"Clean baseline         AUC={clean['auc']:.4f}  ECE={clean['ece']:.4f}")


if __name__ == "__main__":
    main()
