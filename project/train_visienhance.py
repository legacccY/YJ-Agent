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

# OpenMP/MKL env must be set before numpy/torch import, else intermittent
# OMP Error #15 (libiomp5md.dll already initialized) can abort the process,
# especially under detached Start-Process launches.
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")
os.environ.setdefault("OMP_NUM_THREADS", "1")

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
from omegaconf import OmegaConf
from torch.cuda.amp import GradScaler, autocast
from torch.utils.data import DataLoader
from tqdm import tqdm

os.environ.setdefault("WANDB_DISABLE_SERVICE", "true")  # fix WinError 64 on Windows
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
    p.add_argument("--model-only", action="store_true",
                   help="Load only model weights (skip optimizer/scheduler) — use for cross-stage resume")
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
    # ⚠️ 口径：batch 聚合 MSE → dB（训练监控用，偏保守 ~4-5 dB）。
    # 论文/验收报告须用 per-image PSNR（scripts/eval_nocrop_e1.py 的 psnr_perimg_*）。
    # 口径定义见 project/ACCEPTANCE_CRITERIA.md「PSNR 口径定义」专节。
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


_IMAGENET_MEAN = (0.485, 0.456, 0.406)
_IMAGENET_STD = (0.229, 0.224, 0.225)


def build_efnet_extractor(device):
    """Frozen, differentiable EfficientNet-B0 feature extractor (1280-D).

    Mirrors precompute_efficientnet.py: features → avgpool → flatten on
    ImageNet-normalised 224px input. Params frozen (requires_grad_(False)) but
    the graph stays differentiable so gradients flow back through x_enh.
    """
    from torchvision.models import EfficientNet_B0_Weights, efficientnet_b0
    base = efficientnet_b0(weights=EfficientNet_B0_Weights.DEFAULT)
    extractor = nn.Sequential(base.features, base.avgpool, nn.Flatten()).to(device).eval()
    extractor.requires_grad_(False)
    return extractor


def _efnet_feats(extractor, x: torch.Tensor) -> torch.Tensor:
    """x in [0,1] RGB at any size → ImageNet-normalised 224 → (B, 1280)."""
    mean = torch.tensor(_IMAGENET_MEAN, device=x.device).view(1, 3, 1, 1)
    std = torch.tensor(_IMAGENET_STD, device=x.device).view(1, 3, 1, 1)
    x224 = F.interpolate(x, size=224, mode="bilinear", align_corners=False)
    return extractor((x224 - mean) / std)


def dp_loss(encoder, efnet_extractor, visiscore,
            x_enh: torch.Tensor, x_ref: torch.Tensor) -> torch.Tensor:
    """KL( p_φ(z|x_enh) ‖ p_φ(z|x_ref) ) — Lemma 3.

    Real image path: x_enh (with grad) and x_ref (detached target) each go
    through the frozen VisiScore-Net (q) and frozen EfficientNet-B0 (visual
    token). Gradients flow into VisiEnhance via the x_enh branch, so the KL is
    no longer constant w.r.t. the enhancer. The previous all-zeros dummy path
    produced zero gradient and silently disabled DP-Loss.

    ABCD clinical tokens are unavailable at enhancement-training time; we pass
    zeros for both branches (identical → cancels), so the KL is driven by the
    image-derived visual token + quality vector, which is what Stage 2 optimises.
    """
    B = x_enh.shape[0]
    dummy_abcd = torch.zeros(B, 4, device=x_enh.device)
    efnet_dim = getattr(encoder, "efnet_dim", 0)

    # Reference branch: frozen target, no grad.
    with torch.no_grad():
        q_ref = visiscore(x_ref)
        feat_ref = _efnet_feats(efnet_extractor, x_ref) if efnet_dim > 0 else None
        mu_ref, lsq_ref = encoder(dummy_abcd, q_ref, feat_ref)

    # Enhanced branch: carries gradient through VisiScore + EfficientNet into x_enh.
    q_enh = visiscore(x_enh)
    feat_enh = _efnet_feats(efnet_extractor, x_enh) if efnet_dim > 0 else None
    mu_enh, lsq_enh = encoder(dummy_abcd, q_enh, feat_enh)

    # KL( N(mu_enh, Σ_enh) ‖ N(mu_ref, Σ_ref) ) analytically.
    var_enh = torch.exp(lsq_enh).clamp(1e-8)
    var_ref = torch.exp(lsq_ref).clamp(1e-8)
    kl = 0.5 * (
        (var_enh + (mu_enh - mu_ref).pow(2)) / var_ref
        - 1.0
        - lsq_enh
        + lsq_ref.detach()
    ).sum(dim=-1).mean()
    return kl


# ── B3-sourced DP-Loss + pos-hinge (Stage 2 v2) ─────────────────────────────────
# Root cause of dangerous_flip↑ in v1: DP-Loss used Q-VIB/B0 latent (ABCD zeroed,
# no diagnosis signal) while eval uses the B3 oracle → train/eval mismatch. v2 makes
# DP-Loss and eval share the same B3 classifier, plus an explicit pos-hinge so true
# melanomas are not flipped to benign by enhancement.

_B3_CROP = 224


def build_b3(ckpt_path, device):
    """Frozen, differentiable EfficientNet-B3 melanoma classifier (eval oracle).

    Mirrors eval_stage2_compare.load_b3: torchvision efficientnet_b3 + 2-class head.
    Params frozen (requires_grad_(False)) but graph stays differentiable so
    gradients flow back into VisiEnhance through x_enh.
    """
    from torchvision.models import efficientnet_b3
    net = efficientnet_b3(weights=None)
    net.classifier = nn.Sequential(nn.Dropout(p=0.3, inplace=True),
                                   nn.Linear(net.classifier[1].in_features, 2))
    ck = torch.load(ckpt_path, map_location=device, weights_only=False)
    missing, unexpected = net.load_state_dict(ck["model"] if "model" in ck else ck, strict=False)
    assert not missing and not unexpected, f"b3 load mismatch: {missing[:3]} / {unexpected[:3]}"
    net.to(device).eval().requires_grad_(False)
    return net


def _b3_logits(b3, x: torch.Tensor) -> torch.Tensor:
    """x in [0,1] RGB @256 → center-crop 224 → ImageNet-norm → B3 logits.

    Identical preprocessing to eval_diag_paired.center_crop_224 + _NORM, so the
    training objective is on the exact same input the eval metric scores.
    """
    o = (x.shape[-1] - _B3_CROP) // 2
    xc = x[..., o:o + _B3_CROP, o:o + _B3_CROP]
    mean = torch.tensor(_IMAGENET_MEAN, device=x.device).view(1, 3, 1, 1)
    std = torch.tensor(_IMAGENET_STD, device=x.device).view(1, 3, 1, 1)
    return b3((xc - mean) / std)


def dp_loss_b3(b3, x_enh, x_ref, y, margin):
    """B3-sourced diagnosis-preserving loss + pos-hinge.

      kl    = KL( softmax B3(enh) ‖ softmax B3(ref) )   [Lemma 3 方向]
      hinge = mean_{y==1} relu(margin − p_enh[:, mel])   真阳增强后 mel 概率不准掉破 margin
    """
    with torch.no_grad():
        logp_ref = F.log_softmax(_b3_logits(b3, x_ref), dim=-1)   # detached target
    logp_enh = F.log_softmax(_b3_logits(b3, x_enh), dim=-1)       # carries grad
    p_enh = logp_enh.exp()
    kl = (p_enh * (logp_enh - logp_ref)).sum(dim=-1).mean()
    pos = (y == 1)
    if pos.any():
        hinge = F.relu(margin - p_enh[pos, 1]).mean()
    else:
        hinge = torch.zeros((), device=x_enh.device)
    return kl, hinge


# ── Train / Val epoch ──────────────────────────────────────────────────────────

def run_epoch(phase, loader, model, visiscore, qvib_enc, efnet_extractor, lpips_fn, optimizer, scaler, cfg, device, b3=None):
    is_train = phase == "train"
    model.train() if is_train else model.eval()

    stage = cfg.stage
    lam = cfg.loss
    total_loss = total_psnr = total_ssim = n = 0
    # Per-component accumulators (raw, un-weighted) — DP is the Stage 2 success
    # metric (plan: "DP-Loss 收敛到 < 0.05"). Previously never logged → flying blind.
    total_l1 = total_lpips = total_dp = total_hinge = 0.0

    ctx = torch.enable_grad() if is_train else torch.no_grad()
    with ctx:
        for batch in tqdm(loader, desc=phase, leave=False, ncols=80):
            if len(batch) == 3:
                x_low, x_ref, y = batch
                y = y.to(device, non_blocking=True)
            else:
                x_low, x_ref = batch
                y = None
            x_low = x_low.to(device, non_blocking=True)
            x_ref = x_ref.to(device, non_blocking=True)

            # Compute q_low with frozen VisiScore-Net
            with torch.no_grad():
                q_low = visiscore(x_low)        # [B, 5]

            l1_val = lp_val = dp_val = hinge_val = 0.0
            with autocast(enabled=cfg.train.amp):
                x_enh = model(x_low, q_low)

                l1 = F.l1_loss(x_enh, x_ref)
                l1_val = l1.item()
                loss = l1 * lam.lambda_l1

                if lam.lambda_lpips > 0 and lpips_fn is not None:
                    # Resize to 224 for LPIPS to save VRAM (~3GB saved at 384px)
                    e224 = F.interpolate(x_enh * 2 - 1, size=224, mode="bilinear", align_corners=False)
                    r224 = F.interpolate(x_ref * 2 - 1, size=224, mode="bilinear", align_corners=False)
                    lp = lpips_fn(e224, r224).mean()
                    lp_val = lp.item()
                    loss = loss + lam.lambda_lpips * lp

                if stage >= 2 and lam.lambda_dp > 0 and b3 is not None:
                    # v2: B3-sourced DP-Loss + pos-hinge (train/eval same oracle).
                    dp, hinge = dp_loss_b3(b3, x_enh, x_ref, y, lam.get("hinge_margin", 0.5))
                    dp_val = dp.item()
                    hinge_val = hinge.item()
                    loss = loss + lam.lambda_dp * dp + lam.get("lambda_hinge", 0.0) * hinge
                elif stage >= 2 and lam.lambda_dp > 0 and qvib_enc is not None:
                    # v1: legacy Q-VIB latent DP-Loss.
                    dp = dp_loss(qvib_enc, efnet_extractor, visiscore, x_enh, x_ref)
                    dp_val = dp.item()
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
            total_l1 += l1_val * B
            total_lpips += lp_val * B
            total_dp += dp_val * B
            total_hinge += hinge_val * B
            n += B

    return {
        "loss": total_loss / n,
        "psnr": total_psnr / n,
        "ssim": total_ssim / n,
        "l1": total_l1 / n,
        "lpips": total_lpips / n,
        "dp": total_dp / n,
        "hinge": total_hinge / n,
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
    efnet_extractor = None
    if cfg.stage >= 2:
        try:
            qvib_enc = build_qvib_encoder(cfg, device)
            print("[INFO] Q-VIB encoder loaded (frozen)")
            if getattr(qvib_enc, "efnet_dim", 0) > 0:
                efnet_extractor = build_efnet_extractor(device)
                print("[INFO] EfficientNet-B0 extractor loaded (frozen, differentiable) for DP-Loss")
        except Exception as e:
            print(f"[WARN] Could not load Q-VIB encoder: {e}. DP-Loss disabled.")

    # ── Frozen B3 oracle (stage 2 v2: B3-sourced DP-Loss + pos-hinge) ──────────
    b3 = None
    if cfg.stage >= 2 and cfg.frozen_models.get("b3_ckpt", None):
        b3 = build_b3(cfg.frozen_models.b3_ckpt, device)
        print("[INFO] EfficientNet-B3 oracle loaded (frozen, differentiable) for v2 DP-Loss + pos-hinge")

    # ── LPIPS ─────────────────────────────────────────────────────────────────
    lpips_fn = get_lpips(device) if cfg.loss.lambda_lpips > 0 else None

    # ── Data ───────────────────────────────────────────────────────────────────
    dcfg = cfg.data
    train_ds = EnhanceDataset(
        labels_csv=dcfg.labels_csv, split_csv=dcfg.split_csv,
        split="train", img_size=dcfg.img_size, severity=dcfg.severity,
        meta_csv=dcfg.get("meta_csv", None),
        return_target=(b3 is not None),
        pos_oversample=dcfg.get("pos_oversample", 1),
    )
    val_severity = dcfg.get("val_severity", dcfg.severity)
    val_ds = EnhanceDataset(
        labels_csv=dcfg.labels_csv, split_csv=dcfg.split_csv,
        split="val", img_size=dcfg.img_size, severity=val_severity,
        meta_csv=dcfg.get("meta_csv", None),
        return_target=(b3 is not None),
        pos_oversample=1,
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
    # model_only can be set via CLI (--model-only) OR config (train.model_only).
    # Config form is safer for cross-stage resume launched by /run-experiment,
    # which auto-passes --resume but NOT --model-only → without this, a Stage 2
    # start from a Stage 1 checkpoint would wrongly load Stage 1's optimizer/
    # scheduler/epoch and silently corrupt the fine-tune.
    model_only = args.model_only or cfg.train.get("model_only", False)
    if resume_path and Path(resume_path).exists():
        ckpt = torch.load(resume_path, map_location=device, weights_only=False)
        _raw_model.load_state_dict(ckpt["model"])
        if not model_only:
            optimizer.load_state_dict(ckpt["optimizer"])
            scheduler.load_state_dict(ckpt["scheduler"])
            start_epoch = ckpt.get("epoch", 0) + 1
            best_psnr = ckpt.get("best_psnr", 0.0)
            no_improve = ckpt.get("no_improve", 0)
        print(f"[INFO] Resumed from {resume_path} (epoch {start_epoch}, model-only={model_only})")

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
        tr = run_epoch("train", train_loader, model, visiscore, qvib_enc, efnet_extractor, lpips_fn, optimizer, scaler, cfg, device, b3=b3)
        vl = run_epoch("val",   val_loader,  model, visiscore, qvib_enc, efnet_extractor, lpips_fn, optimizer, scaler, cfg, device, b3=b3)
        scheduler.step()

        elapsed_h = (time.time() - t0) / 3600
        eta_h = elapsed_h / (epoch - start_epoch + 1) * (tcfg.epochs - epoch - 1)

        dp_str = ""
        if cfg.stage >= 2:
            dp_str = (f"| train_DP={tr['dp']:.4f} | val_DP={vl['dp']:.4f} "
                      f"| train_H={tr['hinge']:.4f} | val_H={vl['hinge']:.4f} ")
        print(f"Epoch {epoch:03d} | train_loss={tr['loss']:.4f} | val_PSNR={vl['psnr']:.2f} "
              f"| val_SSIM={vl['ssim']:.4f} {dp_str}| best={best_psnr:.2f} | ETA {eta_h:.1f}h")

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
            "train_dp": round(tr["dp"], 5),
            "val_dp": round(vl["dp"], 5),
            "train_hinge": round(tr["hinge"], 5),
            "val_hinge": round(vl["hinge"], 5),
            "train_l1": round(tr["l1"], 5),
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
