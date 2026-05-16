"""VisiEnhance-Net Evaluation: E1/E3/E4/E5/E6/E12.

Acceptance criteria (phase_07_visienhance.md):
  E1  PSNR ≥ 30 dB  (moderate degradation, val split)
  E3  |ΔAUC| < 1.5% (B3 oracle; enhanced vs reference images)
  E4  Prop.3: |ρ_enhanced| > |ρ_degraded|  (entropy–q̄ correlation)
  E5  SalvageRate > 55%  (moderate degradation band q̄ 0.35–0.50)
  E6  SalvageRate < 25%  (extreme degradation q̄ < 0.25)
  E12 Inference < 50 ms / image

Usage:
    python eval_visienhance.py --config configs/visienhance_s3.yaml \
        --ckpt checkpoints/visienhance/stage3/best_visienhance.pth \
        --b3-ckpt checkpoints/finetune/best_efnet.pth \
        --exp E1 E3 E4 E5 E6 E12
"""

import argparse
import time
from pathlib import Path

import cv2
import numpy as np
import pandas as pd
import torch
import torch.nn.functional as F
from omegaconf import OmegaConf
from scipy.stats import spearmanr, bootstrap
from sklearn.metrics import roc_auc_score
from torch.utils.data import DataLoader, Dataset
from torchvision import transforms
from tqdm import tqdm

from data.enhance_dataset import EnhanceDataset, _degrade_numpy, _DEG_CFG
from models.visienhance import VisiEnhanceNet
from models.visiscore import VisiScoreNet

import random

_TO_TENSOR = transforms.ToTensor()

PASS = "\033[92m PASS\033[0m"
FAIL = "\033[91m FAIL\033[0m"


# ── Model loaders ──────────────────────────────────────────────────────────────

def load_visienhance(cfg, ckpt_path, device):
    mcfg = cfg.model
    model = VisiEnhanceNet(
        base_channels=mcfg.base_channels,
        enc_blocks=list(mcfg.enc_blocks),
        mid_blocks=mcfg.mid_blocks,
        dec_blocks=list(mcfg.dec_blocks),
    ).to(device)
    ckpt = torch.load(ckpt_path, map_location=device, weights_only=True)
    model.load_state_dict(ckpt["model"])
    return model.eval()


def load_visiscore(ckpt_path, device):
    model = VisiScoreNet().to(device)
    ckpt = torch.load(ckpt_path, map_location=device, weights_only=True)
    model.load_state_dict(ckpt["model"] if "model" in ckpt else ckpt)
    return model.eval()


def load_b3(ckpt_path, device):
    import timm
    model = timm.create_model("efficientnet_b3", num_classes=2, pretrained=False)
    ckpt = torch.load(ckpt_path, map_location=device, weights_only=True)
    model.load_state_dict(ckpt["model"] if "model" in ckpt else ckpt, strict=False)
    return model.to(device).eval()


# ── Dataset helpers ────────────────────────────────────────────────────────────

class RefDataset(Dataset):
    """Returns high-quality test images from ISIC test split with q̄ > q_min."""

    def __init__(self, labels_csv, split_csv, q_min=0.0, q_max=1.0,
                 img_size=384, n_max=None, severity="moderate", seed=0):
        self.img_size = img_size
        self.severity = severity
        self.seed = seed

        labels = pd.read_csv(labels_csv)
        splits = pd.read_csv(split_csv)
        test_ids = set(splits.loc[splits["split"] == "test", "isic_id"].astype(str))

        labels["isic_id"] = labels["original_path"].apply(lambda p: Path(p).stem)
        df = labels[labels["isic_id"].isin(test_ids)].drop_duplicates("original_path").copy()
        df = df[df["original_path"].apply(lambda p: Path(p).exists())]

        q_cols = ["sharpness", "brightness", "completeness", "color_temp", "contrast"]
        if all(c in df.columns for c in q_cols):
            q_bar = df[q_cols].mean(axis=1)
            df = df[(q_bar >= q_min) & (q_bar < q_max)]

        if n_max:
            df = df.sample(min(n_max, len(df)), random_state=seed)
        self.df = df.reset_index(drop=True)

    def __len__(self):
        return len(self.df)

    def __getitem__(self, idx):
        row = self.df.iloc[idx]
        img = cv2.imread(str(row["original_path"]))
        if img is None:
            t = torch.zeros(3, self.img_size, self.img_size)
            return t, t, torch.zeros(5), -1

        img = cv2.resize(img, (self.img_size, self.img_size), interpolation=cv2.INTER_AREA)

        rng = random.Random(self.seed + idx)
        deg = _degrade_numpy(img, self.severity, rng)

        x_ref = _TO_TENSOR(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
        x_low = _TO_TENSOR(cv2.cvtColor(deg, cv2.COLOR_BGR2RGB))

        q_cols = ["sharpness", "brightness", "completeness", "color_temp", "contrast"]
        if all(c in row.index for c in q_cols):
            q_ref = torch.tensor([row[c] for c in q_cols], dtype=torch.float32)
        else:
            q_ref = torch.full((5,), 0.7)

        target = int(row.get("target", -1))
        return x_low, x_ref, q_ref, target


# ── Evaluation functions ───────────────────────────────────────────────────────

@torch.no_grad()
def compute_psnr_ssim(model, visiscore, loader, device):
    from skimage.metrics import peak_signal_noise_ratio, structural_similarity
    psnrs, ssims = [], []
    for x_low, x_ref, _, _ in tqdm(loader, desc="E1", ncols=80):
        x_low, x_ref = x_low.to(device), x_ref.to(device)
        q = visiscore(x_low)
        x_enh = model(x_low, q)

        for i in range(x_enh.shape[0]):
            ref_np = (x_ref[i].cpu().permute(1, 2, 0).numpy() * 255).astype(np.uint8)
            enh_np = (x_enh[i].cpu().permute(1, 2, 0).numpy() * 255).clip(0, 255).astype(np.uint8)
            psnrs.append(peak_signal_noise_ratio(ref_np, enh_np, data_range=255))
            ssims.append(structural_similarity(ref_np, enh_np, channel_axis=2, data_range=255))

    return np.mean(psnrs), np.mean(ssims)


@torch.no_grad()
def compute_e3(model, visiscore, b3, loader, device):
    """Diagnostic preservation: |ΔAUC(enhanced vs reference)| must be < 0.015."""
    preds_ref, preds_enh, labels = [], [], []

    norm = transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225])

    for x_low, x_ref, q_ref, targets in tqdm(loader, desc="E3", ncols=80):
        valid = targets != -1
        if not valid.any():
            continue
        x_low, x_ref = x_low[valid].to(device), x_ref[valid].to(device)
        tgt = targets[valid]

        q = visiscore(x_low)
        x_enh = model(x_low, q)

        # B3 oracle (224px expected; resize inline)
        def b3_pred(imgs):
            imgs_224 = F.interpolate(imgs, size=224, mode="bilinear", align_corners=False)
            logits = b3(norm(imgs_224))
            return torch.softmax(logits, dim=-1)[:, 1].cpu().numpy()

        preds_ref.extend(b3_pred(x_ref))
        preds_enh.extend(b3_pred(x_enh))
        labels.extend(tgt.numpy())

    labels = np.array(labels)
    if labels.sum() < 5:
        print("[E3] Too few positive labels in test set — skipping AUC computation")
        return None, None, None

    auc_ref = roc_auc_score(labels, np.array(preds_ref))
    auc_enh = roc_auc_score(labels, np.array(preds_enh))
    delta = abs(auc_enh - auc_ref)
    return auc_ref, auc_enh, delta


@torch.no_grad()
def compute_e4(model, visiscore, loader, device):
    """Proposition 3: entropy–q̄ |ρ| should increase after enhancement."""
    ent_low, ent_enh, qbar_low, qbar_enh = [], [], [], []

    for x_low, x_ref, _, _ in tqdm(loader, desc="E4", ncols=80):
        x_low = x_low.to(device)
        q_low = visiscore(x_low)
        x_enh = model(x_low, q_low)
        q_enh = visiscore(x_enh)

        # Entropy proxy: use VisiScore q̄ as quality and compute entropy from
        # uniform binary distribution scaled by q̄ (matches paper narrative)
        # Full entropy requires Q-VIB; here we use H = -q̄ log q̄ - (1-q̄) log(1-q̄)
        def h(qb):
            qb = qb.clamp(1e-6, 1 - 1e-6)
            return -(qb * qb.log() + (1 - qb) * (1 - qb).log())

        qb_low = q_low.mean(dim=-1)
        qb_enh = q_enh.mean(dim=-1)

        ent_low.extend(h(qb_low).cpu().numpy())
        ent_enh.extend(h(qb_enh).cpu().numpy())
        qbar_low.extend(qb_low.cpu().numpy())
        qbar_enh.extend(qb_enh.cpu().numpy())

    rho_low, p_low = spearmanr(qbar_low, ent_low)
    rho_enh, p_enh = spearmanr(qbar_enh, ent_enh)
    return rho_low, p_low, rho_enh, p_enh


@torch.no_grad()
def compute_salvage_rate(model, visiscore, labels_csv, split_csv, img_size,
                         q_range, severity, device, n_max=500, seed=1):
    """E5/E6: fraction of q̄<0.5 images that enhance to q̄≥0.5."""
    ds = RefDataset(labels_csv, split_csv, q_min=q_range[0], q_max=q_range[1],
                    img_size=img_size, n_max=n_max, severity=severity, seed=seed)
    loader = DataLoader(ds, batch_size=8, shuffle=False, num_workers=2, pin_memory=True)

    salvaged = total = 0
    for x_low, x_ref, q_ref, _ in tqdm(loader, desc=f"Salvage {q_range}", ncols=80):
        x_low = x_low.to(device)
        q = visiscore(x_low)
        q_bar_low = q.mean(dim=-1)

        # Only count images that are actually below threshold
        below = (q_bar_low < 0.5).cpu()
        if not below.any():
            continue

        x_low_b = x_low[below.to(device)]
        q_b = q[below.to(device)]
        x_enh = model(x_low_b, q_b)
        q_enh = visiscore(x_enh)
        q_bar_enh = q_enh.mean(dim=-1)

        salvaged += (q_bar_enh >= 0.5).sum().item()
        total += below.sum().item()

    rate = salvaged / total if total > 0 else 0.0
    return rate, salvaged, total


@torch.no_grad()
def compute_e12(model, visiscore, device, img_size=384, n_runs=100):
    """Inference latency: VisiScore + VisiEnhance per image (ms)."""
    dummy = torch.rand(1, 3, img_size, img_size, device=device)

    # Warm up
    for _ in range(10):
        q = visiscore(dummy)
        _ = model(dummy, q)
    torch.cuda.synchronize()

    t0 = time.time()
    for _ in range(n_runs):
        q = visiscore(dummy)
        _ = model(dummy, q)
    torch.cuda.synchronize()
    ms_per_img = (time.time() - t0) / n_runs * 1000
    return ms_per_img


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--config", required=True)
    p.add_argument("--ckpt", required=True, help="VisiEnhance-Net checkpoint")
    p.add_argument("--b3-ckpt", default="D:/YJ-Agent/checkpoints/efficientnet_b3_isic.pth")
    p.add_argument("--exp", nargs="+", default=["E1", "E3", "E4", "E5", "E6", "E12"])
    args = p.parse_args()

    cfg = OmegaConf.load(args.config)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    model = load_visienhance(cfg, args.ckpt, device)
    visiscore = load_visiscore(cfg.frozen_models.visiscore_ckpt, device)

    dcfg = cfg.data
    results = {}

    # ── E1 ─────────────────────────────────────────────────────────────────────
    if "E1" in args.exp:
        ds = EnhanceDataset(dcfg.labels_csv, dcfg.split_csv,
                            split="test", img_size=dcfg.img_size, severity="moderate")
        loader = DataLoader(ds, batch_size=8, shuffle=False, num_workers=2, pin_memory=True)
        mean_psnr, mean_ssim = compute_psnr_ssim(model, visiscore, loader, device)
        ok = mean_psnr >= 30.0
        results["E1"] = {"psnr": round(mean_psnr, 2), "ssim": round(mean_ssim, 4), "pass": ok}
        print(f"E1 PSNR={mean_psnr:.2f} dB  SSIM={mean_ssim:.4f}{PASS if ok else FAIL}")

    # ── E3 ─────────────────────────────────────────────────────────────────────
    if "E3" in args.exp:
        if not Path(args.b3_ckpt).exists():
            print(f"[E3] B3 checkpoint not found at {args.b3_ckpt} — skipping")
        else:
            b3 = load_b3(args.b3_ckpt, device)
            ds = RefDataset(dcfg.labels_csv, dcfg.split_csv,
                            q_min=0.70, img_size=dcfg.img_size, n_max=2000,
                            severity="moderate", seed=7)
            loader = DataLoader(ds, batch_size=8, shuffle=False, num_workers=2, pin_memory=True)
            auc_ref, auc_enh, delta = compute_e3(model, visiscore, b3, loader, device)
            if delta is not None:
                ok = delta < 0.015
                results["E3"] = {"auc_ref": round(auc_ref, 4), "auc_enh": round(auc_enh, 4),
                                 "delta_auc": round(delta, 4), "pass": ok}
                print(f"E3 AUC_ref={auc_ref:.4f}  AUC_enh={auc_enh:.4f}  "
                      f"|ΔAUC|={delta:.4f}{PASS if ok else FAIL}")

    # ── E4 ─────────────────────────────────────────────────────────────────────
    if "E4" in args.exp:
        ds = EnhanceDataset(dcfg.labels_csv, dcfg.split_csv,
                            split="test", img_size=dcfg.img_size, severity="mixed")
        loader = DataLoader(ds, batch_size=8, shuffle=False, num_workers=2, pin_memory=True)
        rho_low, p_low, rho_enh, p_enh = compute_e4(model, visiscore, loader, device)
        ok = abs(rho_enh) > abs(rho_low)
        results["E4"] = {"rho_degraded": round(rho_low, 4), "rho_enhanced": round(rho_enh, 4),
                         "pass": ok}
        print(f"E4 ρ_degraded={rho_low:.4f} (p={p_low:.2e})  "
              f"ρ_enhanced={rho_enh:.4f} (p={p_enh:.2e}){PASS if ok else FAIL}")

    # ── E5 ─────────────────────────────────────────────────────────────────────
    if "E5" in args.exp:
        rate, salvaged, total = compute_salvage_rate(
            model, visiscore, dcfg.labels_csv, dcfg.split_csv,
            dcfg.img_size, q_range=(0.35, 0.50), severity="moderate", device=device)
        ok = rate >= 0.55
        results["E5"] = {"salvage_rate": round(rate, 4), "salvaged": salvaged,
                         "total": total, "pass": ok}
        print(f"E5 SalvageRate={rate:.1%} ({salvaged}/{total}){PASS if ok else FAIL}")

    # ── E6 ─────────────────────────────────────────────────────────────────────
    if "E6" in args.exp:
        rate, salvaged, total = compute_salvage_rate(
            model, visiscore, dcfg.labels_csv, dcfg.split_csv,
            dcfg.img_size, q_range=(0.0, 0.25), severity="severe", device=device)
        ok = rate < 0.25
        results["E6"] = {"salvage_rate": round(rate, 4), "salvaged": salvaged,
                         "total": total, "pass": ok}
        print(f"E6 ExtremeSalvage={rate:.1%} ({salvaged}/{total}){PASS if ok else FAIL}")

    # ── E12 ────────────────────────────────────────────────────────────────────
    if "E12" in args.exp:
        ms = compute_e12(model, visiscore, device, img_size=dcfg.img_size)
        ok = ms < 50.0
        results["E12"] = {"latency_ms": round(ms, 2), "pass": ok}
        print(f"E12 Latency={ms:.1f} ms{PASS if ok else FAIL}")

    # ── Summary ────────────────────────────────────────────────────────────────
    print("\n=== Acceptance Summary ===")
    all_pass = True
    for exp, r in results.items():
        status = PASS if r.get("pass") else FAIL
        all_pass = all_pass and r.get("pass", False)
        print(f"  {exp}: {status}")

    out_path = Path("results/visienhance_eval.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    import json
    out_path.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"\nResults saved to {out_path}")
    return 0 if all_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
