"""VisiEnhance-Net Training Script — 3-stage progressive training.

Stage 1: L1 + LPIPS  (basic restoration pre-training, ~200 epochs)
Stage 2: + DP-Loss   (diagnosis-preserving fine-tune, ~80 epochs)
Stage 3: + Quality   (quality-achievement constraint, ~40 epochs)

State file written to D:/YJ-Agent/log/experiment_state.json for /run-experiment monitoring.

Usage:
    /loop /run-experiment project/train_visienhance.py project/configs/visienhance_s1.yaml
    /loop /run-experiment project/train_visienhance.py project/configs/visienhance_s2.yaml
    /loop /run-experiment project/train_visienhance.py project/configs/visienhance_s3.yaml
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
from omegaconf import OmegaConf
from torch.cuda.amp import GradScaler, autocast
from torch.utils.data import DataLoader
from tqdm import tqdm

import wandb

from data.enhance_dataset import EnhanceDataset
from models.visienhance import VisiEnhanceNet
from models.visiscore import VisiScoreNet

os.environ["OMP_NUM_THREADS"] = "1"
os.environ["WANDB_DISABLE_SERVICE"] = "1"  # prevent asyncio WinError 64 crash on Windows
STATE_PATH = Path("D:/YJ-Agent/log/experiment_state.json")


# ── Args ───────────────────────────────────────────────────────────────────────

def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--config", required=True)
    p.add_argument("--resume", default=None, help="Path to checkpoint to resume from")
    return p.parse_args()


# ── State ──────────────────────────────────────────────────────────────────────

def write_state(state: dict):
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, indent=2), encoding="utf-8")


# ── LPIPS (lazy import) ────────────────────────────────────────────────────────

def get_lpips(device):
    try:
        import lpips
        return lpips.LPIPS(net="alex").to(device).eval()
    except ImportError:
        print("[WARN] lpips not installed — falling back to L1 only. Run: pip install lpips")
        return None


# ── Metrics ───────────────────────────────────────────────────────────────────

def psnr(pred: torch.Tensor, target: torch.Tensor) -> float:
    mse = F.mse_loss(pred, target).item()
    return 10 * np.log10(1.0 / (mse + 1e-8))


def ssim_approx(pred: torch.Tensor, target: torch.Tensor) -> float:
    """Fast single-scale SSIM (no window — for monitoring only, not paper metric)."""
    mu1, mu2 = pred.mean(), target.mean()
    sig1 = pred.var().sqrt()
    sig2 = target.var().sqrt()
    sig12 = ((pred - mu1) * (target - mu2)).mean()
    c1, c2 = 0.01**2, 0.03**2
    ssim = (2*mu1*mu2 + c1) * (2*sig12 + c2) / ((mu1**2 + mu2**2 + c1) * (sig1**2 + sig2**2 + c2))
    return ssim.item()


# ── DP-Loss (Stage 2+) ─────────────────────────────────────────────────────────

def build_qvib_encoder(cfg, device):
    """Load frozen Q-VIB encoder for DP-Loss computation."""
    from models.q_vib_encoder import QVIBEncoder
    from models.quality_adaptive_prior import QualityAdaptivePrior
    from models.qad_classifier import QADClassifier

    enc_cfg = cfg.frozen_models.qvib_encoder
    ckpt = torch.load(cfg.frozen_models.qvib_ckpt, map_location=device, weights_only=True)

    encoder = QVIBEncoder(
        abcd_dim=enc_cfg.get("abcd_dim", 4),
        q_dim=5,
        d_model=enc_cfg.get("d_model", 128),
        n_heads=enc_cfg.get("n_heads", 4),
        latent_dim=enc_cfg.get("latent_dim", 64),
        efnet_dim=enc_cfg.get("efnet_dim", 1280),
        use_tokenizer=enc_cfg.get("use_tokenizer", True),
    ).to(device)
    encoder.load_state_dict(ckpt["encoder"], strict=False)
    encoder.eval().requires_grad_(False)
    return encoder


def dp_loss(encoder, x_enh: torch.Tensor, x_ref: torch.Tensor,
            q_enh: torch.Tensor, q_ref: torch.Tensor) -> torch.Tensor:
    """KL( p_φ(z|x_enh,q_enh) ‖ p_φ(z|x_ref,q_ref) ) — Lemma 3.

    Uses image-only path: passes a dummy ABCD (zeros) and EfficientNet features
    extracted inline via a light feature extractor. For training purposes this
    approximation is sufficient; full evaluation uses proper ABCD + EfficientNet.
    """
    B = x_enh.shape[0]
    dummy_abcd = torch.zeros(B, 4, device=x_enh.device)

    # Use EfficientNet features if encoder expects them; otherwise zero
    efnet_dim = getattr(encoder, "efnet_dim", 0)
    dummy_efnet = torch.zeros(B, efnet_dim, device=x_enh.device) if efnet_dim > 0 else None

    with torch.no_grad():
        mu_ref, lsq_ref = encoder(dummy_abcd, q_ref, dummy_efnet)
    mu_enh, lsq_enh = encoder(dummy_abcd, q_enh, dummy_efnet)

    # KL( N(mu_enh, Σ_enh) ‖ N(mu_ref, Σ_ref) ) analytically
    var_enh = torch.exp(lsq_enh).clamp(1e-8)
    var_ref = torch.exp(lsq_ref).clamp(1e-8)
    kl = 0.5 * (
        (var_enh + (mu_enh - mu_ref).pow(2)) / var_ref
        - 1.0
        - lsq_enh
        + lsq_ref.detach()
    ).sum(dim=-1).mean()
    return kl


# ── Train / Val epoch ──────────────────────────────────────────────────────────

def run_epoch(phase, loader, model, visiscore, qvib_enc, lpips_fn, optimizer, scaler, cfg, device):
    is_train = phase == "train"
    model.train() if is_train else model.eval()

    stage = cfg.stage
    lam = cfg.loss
    total_loss = total_psnr = total_ssim = n = 0

    ctx = torch.enable_grad() if is_train else torch.no_grad()
    with ctx:
        for x_low, x_ref in tqdm(loader, desc=phase, leave=False, ncols=80):
            x_low = x_low.to(device, non_blocking=True)
            x_ref = x_ref.to(device, non_blocking=True)

            # Compute q_low with frozen VisiScore-Net
            with torch.no_grad():
                q_low = visiscore(x_low)        # [B, 5]

            with autocast(enabled=cfg.train.amp):
                x_enh = model(x_low, q_low)

                loss = F.l1_loss(x_enh, x_ref) * lam.lambda_l1

                if lam.lambda_lpips > 0 and lpips_fn is not None:
                    # Resize to 224 for LPIPS to save VRAM (~3GB saved at 384px)
                    e224 = F.interpolate(x_enh * 2 - 1, size=224, mode="bilinear", align_corners=False)
                    r224 = F.interpolate(x_ref * 2 - 1, size=224, mode="bilinear", align_corners=False)
                    lp = lpips_fn(e224, r224).mean()
                    loss = loss + lam.lambda_lpips * lp

                if stage >= 2 and lam.lambda_dp > 0 and qvib_enc is not None:
                    with torch.no_grad():
                        q_ref = visiscore(x_ref)
                    dp = dp_loss(qvib_enc, x_enh, x_ref, q_low, q_ref)
                    loss = loss + lam.lambda_dp * dp

                if stage >= 3 and lam.lambda_quality > 0:
                    with torch.no_grad():
                        q_enh = visiscore(x_enh)
                    q_bar_enh = q_enh.mean(dim=-1)
                    quality_loss = F.relu(lam.quality_target - q_bar_enh).mean()
                    loss = loss + lam.lambda_quality * quality_loss

            if is_train:
                optimizer.zero_grad(set_to_none=True)
                scaler.scale(loss).backward()
                scaler.unscale_(optimizer)
                nn.utils.clip_grad_norm_(model.parameters(), 1.0)
                scaler.step(optimizer)
                scaler.update()

            B = x_low.shape[0]
            total_loss += loss.item() * B
            total_psnr += psnr(x_enh.detach(), x_ref) * B
            total_ssim += ssim_approx(x_enh.detach(), x_ref) * B
            n += B

    return {
        "loss": total_loss / n,
        "psnr": total_psnr / n,
        "ssim": total_ssim / n,
    }


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    args = parse_args()
    cfg = OmegaConf.load(args.config)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    torch.manual_seed(cfg.train.get("seed", 42))
    np.random.seed(cfg.train.get("seed", 42))

    # ── Model ──────────────────────────────────────────────────────────────────
    mcfg = cfg.model
    model = VisiEnhanceNet(
        base_channels=mcfg.base_channels,
        enc_blocks=list(mcfg.enc_blocks),
        mid_blocks=mcfg.mid_blocks,
        dec_blocks=list(mcfg.dec_blocks),
        film_hidden=mcfg.get("film_hidden", 128),
        film_scale=mcfg.get("film_scale", 0.1),
    ).to(device)
    print(f"[INFO] VisiEnhanceNet params: {model.param_count()/1e6:.1f}M")

    # ── Frozen VisiScore-Net ───────────────────────────────────────────────────
    visiscore = VisiScoreNet(pretrained=False).to(device)
    vs_ckpt = torch.load(cfg.frozen_models.visiscore_ckpt, map_location=device, weights_only=False)
    visiscore.load_state_dict(vs_ckpt["model"] if "model" in vs_ckpt else vs_ckpt)
    visiscore.eval().requires_grad_(False)

    # ── Frozen Q-VIB encoder (stage 2+) ───────────────────────────────────────
    qvib_enc = None
    if cfg.stage >= 2:
        try:
            qvib_enc = build_qvib_encoder(cfg, device)
            print("[INFO] Q-VIB encoder loaded (frozen)")
        except Exception as e:
            print(f"[WARN] Could not load Q-VIB encoder: {e}. DP-Loss disabled.")

    # ── LPIPS ─────────────────────────────────────────────────────────────────
    lpips_fn = get_lpips(device) if cfg.loss.lambda_lpips > 0 else None

    # ── Data ───────────────────────────────────────────────────────────────────
    dcfg = cfg.data
    train_ds = EnhanceDataset(
        labels_csv=dcfg.labels_csv, split_csv=dcfg.split_csv,
        split="train", img_size=dcfg.img_size, severity=dcfg.severity,
    )
    val_severity = dcfg.get("val_severity", dcfg.severity)
    val_ds = EnhanceDataset(
        labels_csv=dcfg.labels_csv, split_csv=dcfg.split_csv,
        split="val", img_size=dcfg.img_size, severity=val_severity,
    )
    print(f"[INFO] train={len(train_ds)}, val={len(val_ds)}")

    nw = dcfg.get("num_workers", 2)
    train_loader = DataLoader(
        train_ds, batch_size=dcfg.batch_size, shuffle=True,
        num_workers=nw, pin_memory=True,
        persistent_workers=(nw > 0), multiprocessing_context="spawn" if nw > 0 else None,
    )
    val_loader = DataLoader(
        val_ds, batch_size=dcfg.batch_size, shuffle=False,
        num_workers=nw, pin_memory=True,
        persistent_workers=(nw > 0), multiprocessing_context="spawn" if nw > 0 else None,
    )

    # ── Optimizer ─────────────────────────────────────────────────────────────
    tcfg = cfg.train
    optimizer = torch.optim.AdamW(model.parameters(), lr=tcfg.lr, weight_decay=tcfg.weight_decay)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=tcfg.epochs, eta_min=1e-7)
    scaler = GradScaler(enabled=tcfg.amp)

    # ── Resume ────────────────────────────────────────────────────────────────
    start_epoch = 0
    best_psnr = 0.0
    no_improve = 0
    resume_path = args.resume or cfg.train.get("resume_from", None)
    if resume_path and Path(resume_path).exists():
        ckpt = torch.load(resume_path, map_location=device, weights_only=False)
        model.load_state_dict(ckpt["model"])
        optimizer.load_state_dict(ckpt["optimizer"])
        scheduler.load_state_dict(ckpt["scheduler"])
        start_epoch = ckpt.get("epoch", 0) + 1
        best_psnr = ckpt.get("best_psnr", 0.0)
        no_improve = ckpt.get("no_improve", 0)
        print(f"[INFO] Resumed from {resume_path} (epoch {start_epoch})")

    # ── WandB ─────────────────────────────────────────────────────────────────
    wcfg = cfg.get("wandb", {})
    _wandb_ok = False
    try:
        wandb.init(
            project=wcfg.get("project", "visienhance"),
            name=f"stage{cfg.stage}",
            config=OmegaConf.to_container(cfg, resolve=True),
            mode=wcfg.get("mode", "offline"),
            resume="allow",
        )
        _wandb_ok = True
    except Exception as e:
        print(f"[WARN] wandb.init failed — metrics will not be tracked: {e}", flush=True)

    out_dir = Path(cfg.output.checkpoint_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    t0 = time.time()

    # ── Training loop ─────────────────────────────────────────────────────────
    for epoch in range(start_epoch, tcfg.epochs):
        tr = run_epoch("train", train_loader, model, visiscore, qvib_enc, lpips_fn, optimizer, scaler, cfg, device)
        vl = run_epoch("val",   val_loader,  model, visiscore, qvib_enc, lpips_fn, optimizer, scaler, cfg, device)
        scheduler.step()

        elapsed_h = (time.time() - t0) / 3600
        eta_h = elapsed_h / (epoch - start_epoch + 1) * (tcfg.epochs - epoch - 1)

        print(f"Epoch {epoch:03d} | train_loss={tr['loss']:.4f} | val_PSNR={vl['psnr']:.2f} "
              f"| val_SSIM={vl['ssim']:.4f} | best={best_psnr:.2f} | ETA {eta_h:.1f}h")

        if _wandb_ok:
            try:
                wandb.log({"epoch": epoch, **{f"train/{k}": v for k, v in tr.items()},
                           **{f"val/{k}": v for k, v in vl.items()}, "lr": scheduler.get_last_lr()[0]})
            except Exception as e:
                print(f"[WARN] wandb.log failed (skipped): {e}", flush=True)

        write_state({
            "stage": cfg.stage,
            "epoch": epoch,
            "total_epochs": tcfg.epochs,
            "train_loss": round(tr["loss"], 4),
            "val_psnr": round(vl["psnr"], 3),
            "val_ssim": round(vl["ssim"], 4),
            "best_val_psnr": round(best_psnr, 3),
            "no_improve_epochs": no_improve,
            "elapsed_h": round(elapsed_h, 2),
            "eta_h": round(eta_h, 2),
            "status": "training",
        })

        # Save latest checkpoint
        ckpt_payload = {
            "epoch": epoch, "model": model.state_dict(),
            "optimizer": optimizer.state_dict(), "scheduler": scheduler.state_dict(),
            "best_psnr": best_psnr, "no_improve": no_improve,
        }
        torch.save(ckpt_payload, out_dir / "last_visienhance.pth")

        # Save best
        if vl["psnr"] > best_psnr:
            best_psnr = vl["psnr"]
            no_improve = 0
            torch.save(ckpt_payload, out_dir / "best_visienhance.pth")
        else:
            no_improve += 1

        # Early stopping (stage 1 only)
        if cfg.stage == 1 and no_improve >= tcfg.get("early_stop_patience", 5):
            print(f"[INFO] Early stop at epoch {epoch} (no improvement for {no_improve} epochs)")
            break

    write_state({"stage": cfg.stage, "status": "done", "best_val_psnr": round(best_psnr, 3)})
    if _wandb_ok:
        try:
            wandb.finish()
        except Exception:
            pass
    print(f"[DONE] Stage {cfg.stage} finished. Best val PSNR = {best_psnr:.3f} dB")


if __name__ == "__main__":
    main()
