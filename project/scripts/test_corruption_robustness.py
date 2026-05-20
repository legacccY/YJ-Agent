"""ImageNet-C style corruption robustness test — BMVC §5.4 / §5.5 appendix.

18 corruption types × 5 severity levels × ITB-LQ.
Outputs Raw / Std-TS / QCTS calibration comparison per (corruption, severity).

Usage:
    python project/scripts/test_corruption_robustness.py \\
        --ckpt project/checkpoints/resnet50/best_resnet50.pth \\
        --output-dir project/results/backbones/resnet50 \\
        --split itb-lq \\
        --qcts-params project/results/backbones/resnet50/qcts_params.json

    python project/scripts/test_corruption_robustness.py \\
        --ckpt project/checkpoints/vit_tiny/best_vit_tiny_patch16_224.pth \\
        --output-dir project/results/backbones/vit_tiny \\
        --split itb-lq \\
        --qcts-params project/results/backbones/vit_tiny/qcts_params.json
"""
import argparse
import json
import os
import sys
from pathlib import Path

import cv2
import numpy as np
import pandas as pd
import torch
import torch.nn as nn
from scipy.special import expit
from sklearn.metrics import roc_auc_score
from torch.utils.data import DataLoader, Dataset
from torchvision import models, transforms
from tqdm import tqdm

THIS_DIR = Path(__file__).resolve().parent.parent  # project/
ROOT = Path("D:/YJ-Agent")
SPLIT_CSV = ROOT / "data/isic_split.csv"
METADATA_CSV = ROOT / "data/raw/isic2020/train-metadata.csv"
IMAGE_ROOT = ROOT / "data/raw/isic2020/train-image/image"
ITB_SUBSETS_CSV = THIS_DIR / "results/itb_subsets.csv"

IMAGENET_MEAN = [0.485, 0.456, 0.406]
IMAGENET_STD  = [0.229, 0.224, 0.225]

os.environ.setdefault("OMP_NUM_THREADS", "1")

# 18 corruption types (glass_blur excluded: O(H*W) pure-Python loop, prohibitively slow)
CORRUPTIONS = [
    # Standard 15 - 1 (glass_blur)
    "gaussian_noise", "shot_noise", "impulse_noise",
    "defocus_blur", "motion_blur", "zoom_blur",
    "snow", "frost", "fog", "brightness",
    "contrast", "elastic_transform", "pixelate", "jpeg_compression",
    # Extra 4
    "speckle_noise", "gaussian_blur", "spatter", "saturate",
]
SEVERITIES = [1, 2, 3, 4, 5]


# ── QCTS math ─────────────────────────────────────────────────────────────────

def softplus(x: np.ndarray) -> np.ndarray:
    return np.log1p(np.exp(x))


def qcts_temperature(T0: float, alpha: float, qbar: np.ndarray) -> np.ndarray:
    return softplus(T0 + alpha * (1.0 - qbar))


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
    import timm
    if timm.is_model(name):
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
            "qbar": float(row.get("qbar", 0.5)),
            "isic_id": row["isic_id"],
        }


def collate(batch):
    return {
        "image":   torch.stack([b["image"] for b in batch]),
        "target":  torch.tensor([b["target"] for b in batch], dtype=torch.long),
        "qbar":    torch.tensor([b["qbar"] for b in batch], dtype=torch.float32),
        "isic_id": [b["isic_id"] for b in batch],
    }


# ── Metrics ────────────────────────────────────────────────────────────────────

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


def eval_three_methods(logits: np.ndarray, targets: np.ndarray, qbar: np.ndarray,
                       T_ts: float, T0: float, alpha: float) -> dict:
    """Compute AUC + ECE + rho(H, qbar) for raw / ts / qcts on the same logits."""
    out = {}
    for method in ("raw", "ts", "qcts"):
        if method == "raw":
            probs = expit(logits)
        elif method == "ts":
            probs = expit(logits / T_ts)
        else:
            T = np.maximum(qcts_temperature(T0, alpha, qbar), 1e-3)
            probs = expit(logits / T)
        try:
            auc = float(roc_auc_score(targets, probs))
        except Exception:
            auc = float("nan")
        ece = compute_ece(probs, targets)
        H = -(probs * np.log(probs + 1e-9) + (1 - probs) * np.log(1 - probs + 1e-9))
        from scipy.stats import spearmanr
        rho, pval = spearmanr(H, qbar)
        out[f"{method}_auc"] = auc
        out[f"{method}_ece"] = ece
        out[f"{method}_rho"] = float(rho)
        out[f"{method}_rho_pval"] = float(pval)
    return out


# ── Data loading ───────────────────────────────────────────────────────────────

def load_split_df(split: str) -> pd.DataFrame:
    if split == "itb-lq":
        df = pd.read_csv(ITB_SUBSETS_CSV)
        df = df[df["subset"] == "ITB-LQ"][["isic_id", "image_path", "target", "qbar"]].copy()
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
        meta["qbar"] = 0.5  # no qbar for full val; TS/QCTS will degrade to near-constant T
        print(f"[data] ISIC2020 {split}: {len(meta)} images")
        return meta.reset_index(drop=True)

    raise ValueError(f"Unknown split: {split!r}. Use itb-lq / val / test")


# ── Main ───────────────────────────────────────────────────────────────────────

@torch.no_grad()
def run_corruption(model, df, img_size, batch_size, device,
                   corruption, severity,
                   T_ts: float, T0: float, alpha: float) -> dict:
    ds = CorruptionDataset(df, img_size=img_size,
                           corruption=corruption, severity=severity)
    loader = DataLoader(ds, batch_size=batch_size, shuffle=False,
                        num_workers=0, collate_fn=collate, pin_memory=True)
    all_logits, all_targets, all_qbar = [], [], []
    for batch in loader:
        x = batch["image"].to(device, non_blocking=True)
        logits = model(x).float().cpu().numpy()
        all_logits.append(logits)
        all_targets.append(batch["target"].numpy())
        all_qbar.append(batch["qbar"].numpy())

    logits_2col = np.concatenate(all_logits, 0)
    targets = np.concatenate(all_targets, 0)
    qbar = np.concatenate(all_qbar, 0)
    scalar_logits = logits_2col[:, 1] - logits_2col[:, 0]

    metrics = eval_three_methods(scalar_logits, targets, qbar, T_ts, T0, alpha)
    metrics["n"] = len(targets)
    return metrics


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--ckpt", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--split", default="itb-lq",
                        choices=["itb-lq", "val", "test"])
    parser.add_argument("--img-size", type=int, default=224)
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--corruptions", nargs="+", default=CORRUPTIONS)
    parser.add_argument("--severities", nargs="+", type=int, default=SEVERITIES)
    parser.add_argument("--qcts-params", default=None,
                        help="Path to qcts_params.json (auto-detected from --output-dir if omitted)")
    args = parser.parse_args()

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # Load QCTS params
    params_path = args.qcts_params or str(out_dir / "qcts_params.json")
    with open(params_path) as f:
        qp = json.load(f)
    T0, alpha, T_ts = qp["T0"], qp["alpha"], qp["T_ts"]
    print(f"[qcts] T0={T0:.4f}  alpha={alpha:.4f}  T_ts={T_ts:.4f}")

    model, cfg = load_model(args.ckpt, device)
    img_size = cfg.get("data", {}).get("img_size", args.img_size)
    df = load_split_df(args.split)

    # ── Clean baseline ──────────────────────────────────────────────────────
    print("\n[clean] running baseline...")
    clean = run_corruption(model, df, img_size, args.batch_size, device,
                           None, None, T_ts, T0, alpha)
    print(f"  Raw AUC={clean['raw_auc']:.4f} ECE={clean['raw_ece']:.4f}  "
          f"TS AUC={clean['ts_auc']:.4f} ECE={clean['ts_ece']:.4f}  "
          f"QCTS AUC={clean['qcts_auc']:.4f} ECE={clean['qcts_ece']:.4f}")

    rows = [{"corruption": "clean", "severity": 0, **clean}]

    # ── Per corruption × severity ───────────────────────────────────────────
    total = len(args.corruptions) * len(args.severities)
    pbar = tqdm(total=total, desc="corruptions")
    for corr in args.corruptions:
        for sev in args.severities:
            res = run_corruption(model, df, img_size, args.batch_size, device,
                                 corr, sev, T_ts, T0, alpha)
            rows.append({"corruption": corr, "severity": sev, **res})
            pbar.set_postfix(corr=corr[:10], sev=sev,
                             raw=f"{res['raw_auc']:.3f}",
                             qcts=f"{res['qcts_auc']:.3f}")
            pbar.update(1)
    pbar.close()

    # ── Save ────────────────────────────────────────────────────────────────
    result_df = pd.DataFrame(rows)
    out_path = out_dir / f"corruption_robustness_{args.split}.csv"
    result_df.to_csv(out_path, index=False)
    print(f"\n[saved] {out_path}")

    # ── Summary ──────────────────────────────────────────────────────────────
    corrupted = result_df[result_df["corruption"] != "clean"]
    print("\n=== Mean AUC per corruption (across severities) ===")
    avg = corrupted.groupby("corruption")[["raw_auc", "ts_auc", "qcts_auc"]].mean()
    avg = avg.sort_values("raw_auc", ascending=False)
    print(avg.to_string(float_format="{:.4f}".format))

    for method in ("raw", "ts", "qcts"):
        mce_auc = corrupted[f"{method}_auc"].mean()
        mce_ece = corrupted[f"{method}_ece"].mean()
        print(f"\n[{method}] Mean Corruption  AUC={mce_auc:.4f}  ECE={mce_ece:.4f}")
    print(f"\n[clean] baseline  Raw AUC={clean['raw_auc']:.4f}  "
          f"QCTS AUC={clean['qcts_auc']:.4f}")


if __name__ == "__main__":
    main()
