"""EDL baseline ITB inference — BMVC Table 1.

Loads best_edl.pth, runs on ITB-LQ + ITB-HQ subsets,
computes AUC / ECE / QCDI / rho(entropy, qbar).

Output: project/results/edl/itb_predictions.csv
        project/results/edl/itb_metrics.json

Usage:
    python project/scripts/infer_edl_itb.py
    python project/scripts/infer_edl_itb.py --ckpt project/checkpoints/edl/best_edl.pth
"""
import argparse
import json
import os
import sys
from pathlib import Path

import cv2
import numpy as np
import pandas as pd
import timm
import torch
import torch.nn as nn
import torch.nn.functional as F
from scipy.special import expit
from scipy.stats import spearmanr
from sklearn.metrics import roc_auc_score
from torch.utils.data import DataLoader, Dataset
from torchvision import transforms
from tqdm import tqdm

ROOT = Path("D:/YJ-Agent")
THIS_DIR = Path(__file__).resolve().parent.parent  # project/
ITB_SUBSETS_CSV = THIS_DIR / "results/itb_subsets.csv"
CKPT_DEFAULT = THIS_DIR / "checkpoints/edl/best_edl.pth"
OUT_DIR = THIS_DIR / "results/edl"

os.environ.setdefault("OMP_NUM_THREADS", "1")

IMAGENET_MEAN = [0.485, 0.456, 0.406]
IMAGENET_STD  = [0.229, 0.224, 0.225]


# ── EDL helpers ───────────────────────────────────────────────────────────────

def edl_probs(logits: np.ndarray, activation: str = "relu") -> tuple:
    """Return (prob_pos, uncertainty, entropy) from raw logits."""
    if activation == "relu":
        evidence = np.maximum(logits, 0.0)
    else:
        evidence = np.log1p(np.exp(logits))
    alpha = evidence + 1.0
    alpha0 = alpha.sum(axis=-1)
    prob_pos = alpha[:, 1] / alpha0
    uncertainty = logits.shape[-1] / alpha0  # Dempster-Shafer vacuity
    H = -(prob_pos * np.log(prob_pos + 1e-9) + (1 - prob_pos) * np.log(1 - prob_pos + 1e-9))
    return prob_pos, uncertainty, H


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


def bootstrap_ece(probs, targets, n_iter=1000, seed=0):
    rng = np.random.default_rng(seed)
    n = len(probs)
    vals = [compute_ece(probs[rng.integers(0, n, n)], targets[rng.integers(0, n, n)])
            for _ in range(n_iter)]
    return float(np.percentile(vals, 2.5)), float(np.percentile(vals, 97.5))


def bootstrap_auc(probs, targets, n_iter=1000, seed=0):
    rng = np.random.default_rng(seed)
    n = len(probs)
    vals = []
    for _ in range(n_iter):
        idx = rng.integers(0, n, n)
        try:
            vals.append(float(roc_auc_score(targets[idx], probs[idx])))
        except Exception:
            pass
    return float(np.percentile(vals, 2.5)), float(np.percentile(vals, 97.5))


# ── Dataset ───────────────────────────────────────────────────────────────────

class ITBDataset(Dataset):
    def __init__(self, df: pd.DataFrame, img_size: int = 300):
        self.df = df.reset_index(drop=True)
        self.tfm = transforms.Compose([
            transforms.ToPILImage(),
            transforms.Resize(int(img_size * 1.14)),
            transforms.CenterCrop(img_size),
            transforms.ToTensor(),
            transforms.Normalize(mean=IMAGENET_MEAN, std=IMAGENET_STD),
        ])

    def __len__(self):
        return len(self.df)

    def __getitem__(self, idx):
        row = self.df.iloc[idx]
        img = cv2.imread(str(row["image_path"]))
        if img is None:
            img = np.zeros((300, 300, 3), dtype=np.uint8)
        img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        return {
            "image": self.tfm(img),
            "target": int(row["target"]),
            "qbar": float(row.get("qbar", 0.5)),
            "isic_id": str(row["isic_id"]),
            "subset": str(row["subset"]),
        }


def collate(batch):
    return {
        "image":   torch.stack([b["image"] for b in batch]),
        "target":  torch.tensor([b["target"] for b in batch], dtype=torch.long),
        "qbar":    [b["qbar"] for b in batch],
        "isic_id": [b["isic_id"] for b in batch],
        "subset":  [b["subset"] for b in batch],
    }


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--ckpt", default=str(CKPT_DEFAULT))
    parser.add_argument("--img-size", type=int, default=300)
    parser.add_argument("--batch-size", type=int, default=32)
    args = parser.parse_args()

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    # Load checkpoint
    ckpt = torch.load(args.ckpt, map_location=device, weights_only=False)
    cfg_dict = ckpt.get("cfg", {})
    backbone_name = cfg_dict.get("backbone", {}).get("name", "efficientnet_b3")
    activation = cfg_dict.get("train", {}).get("evidence_activation", "relu")
    img_size = cfg_dict.get("data", {}).get("img_size", args.img_size)
    drop_rate = cfg_dict.get("backbone", {}).get("drop_rate", 0.3)

    model = timm.create_model(backbone_name, pretrained=False, num_classes=2,
                               drop_rate=drop_rate).to(device)
    model.load_state_dict(ckpt["model"])
    model.eval()
    print(f"[model] {backbone_name}  img_size={img_size}  activation={activation}")

    # Load all 4 ITB subsets (for global rho matching Table 1 baseline computation)
    itb_df = pd.read_csv(ITB_SUBSETS_CSV)
    for s in ["ITB-LQ", "ITB-HQ", "ITB-Edge", "ITB-Diverse"]:
        n = len(itb_df[itb_df.subset == s])
        print(f"[data] {s}={n}")

    ds = ITBDataset(itb_df, img_size=img_size)
    loader = DataLoader(ds, batch_size=args.batch_size, shuffle=False,
                        num_workers=0, collate_fn=collate, pin_memory=True)

    all_logits, all_targets, all_qbar, all_ids, all_subsets = [], [], [], [], []

    with torch.no_grad():
        for batch in tqdm(loader, desc="EDL infer"):
            x = batch["image"].to(device)
            logits = model(x).float().cpu().numpy()
            all_logits.append(logits)
            all_targets.extend(batch["target"].tolist())
            all_qbar.extend(batch["qbar"])
            all_ids.extend(batch["isic_id"])
            all_subsets.extend(batch["subset"])

    logits = np.concatenate(all_logits, 0)
    targets = np.array(all_targets)
    qbar = np.array(all_qbar)
    subsets = np.array(all_subsets)

    prob_pos, uncertainty, entropy = edl_probs(logits, activation)

    # Save per-image predictions
    pred_df = pd.DataFrame({
        "isic_id": all_ids,
        "subset": all_subsets,
        "target": targets,
        "qbar": qbar,
        "prob_pos": prob_pos,
        "uncertainty": uncertainty,
        "entropy": entropy,
    })
    pred_df.to_csv(OUT_DIR / "itb_predictions.csv", index=False)
    print(f"[saved] {OUT_DIR / 'itb_predictions.csv'}")

    # Compute metrics per subset
    metrics = {}
    for subset in ["ITB-LQ", "ITB-HQ", "ITB-Edge", "ITB-Diverse"]:
        m = subsets == subset
        p, t, q, H = prob_pos[m], targets[m], qbar[m], entropy[m]
        try:
            auc = float(roc_auc_score(t, p))
            auc_lo, auc_hi = bootstrap_auc(p, t)
        except Exception:
            auc = float("nan"); auc_lo = auc_hi = float("nan")
        ece = compute_ece(p, t)
        ece_lo, ece_hi = bootstrap_ece(p, t)
        rho, pval = spearmanr(H, q)
        metrics[subset] = {
            "n": int(m.sum()), "auc": round(auc, 4),
            "auc_ci": [round(auc_lo, 4), round(auc_hi, 4)],
            "ece": round(ece, 4), "ece_ci": [round(ece_lo, 4), round(ece_hi, 4)],
            "rho": round(float(rho), 4), "pval": float(pval),
        }
        print(f"  [{subset}] n={m.sum()}  AUC={auc:.4f} [{auc_lo:.4f},{auc_hi:.4f}]  "
              f"ECE={ece:.4f} [{ece_lo:.4f},{ece_hi:.4f}]  rho={rho:.4f}  p={pval:.2e}")

    # QCDI = ECE-LQ - ECE-HQ  (only LQ and HQ used for QCDI)
    qcdi = metrics["ITB-LQ"]["ece"] - metrics["ITB-HQ"]["ece"]
    # Global rho across both subsets
    rho_global, pval_global = spearmanr(entropy, qbar)
    metrics["global"] = {
        "qcdi": round(qcdi, 4),
        "rho": round(float(rho_global), 4),
        "pval": float(pval_global),
    }
    print(f"  [global] QCDI={qcdi:+.4f}  rho={rho_global:.4f}  p={pval_global:.2e}")

    with open(OUT_DIR / "itb_metrics.json", "w") as f:
        json.dump(metrics, f, indent=2)
    print(f"[saved] {OUT_DIR / 'itb_metrics.json'}")
    print("\nDone. Use these numbers for Table 1 EDL row.")


if __name__ == "__main__":
    main()
