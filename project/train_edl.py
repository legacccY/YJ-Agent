"""Evidential Deep Learning (EDL) baseline — BMVC Table 1.

Sensoy et al. 2018 "Evidential Deep Learning to Quantify Classification Uncertainty".
EfficientNet-B3 backbone with Dirichlet evidence output.

Probability for calibration: alpha_1 / (alpha_0 + alpha_1)
Uncertainty:                  2 / (alpha_0 + alpha_1)

State file: D:/YJ-Agent/log/experiment_state.json

Usage:
    /loop /run-experiment project/train_edl.py project/configs/edl.yaml
"""
import argparse
import json
import os
import sys
import time
from pathlib import Path

import numpy as np
import timm
import torch
import torch.nn as nn
import torch.nn.functional as F
from omegaconf import OmegaConf
from sklearn.metrics import roc_auc_score
from torch.utils.data import DataLoader, WeightedRandomSampler
from tqdm import tqdm

import wandb

THIS_DIR = Path(__file__).resolve().parent
if str(THIS_DIR) not in sys.path:
    sys.path.insert(0, str(THIS_DIR))

from data.isic_image_dataset import ISICImageDataset, isic_collate

STATE_PATH = Path("D:/YJ-Agent/log/experiment_state.json")
os.environ.setdefault("OMP_NUM_THREADS", "1")


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--config", default="configs/edl.yaml")
    p.add_argument("--resume", default=None)
    p.add_argument("--seed", type=int, default=None)
    p.add_argument("--dry-run", action="store_true")
    return p.parse_args()


def write_state(state: dict):
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, indent=2), encoding="utf-8")


# ── EDL loss ──────────────────────────────────────────────────────────────────

def get_evidence(logits: torch.Tensor, activation: str) -> torch.Tensor:
    if activation == "relu":
        return F.relu(logits)
    return F.softplus(logits)


def kl_dirichlet_uniform(alpha: torch.Tensor) -> torch.Tensor:
    """KL(Dir(alpha) || Dir(1)) — scalar per sample."""
    K = alpha.shape[-1]
    S = alpha.sum(dim=-1, keepdim=True)
    ones = torch.ones_like(alpha)
    log_B_alpha = torch.lgamma(alpha).sum(-1) - torch.lgamma(S.squeeze(-1))
    log_B_ones = torch.lgamma(torch.tensor(float(K), device=alpha.device))
    psi_diff = torch.digamma(alpha) - torch.digamma(S)
    sum_term = ((alpha - ones) * psi_diff).sum(-1)
    return log_B_alpha - log_B_ones + sum_term


def edl_loss(logits: torch.Tensor, targets: torch.Tensor,
             epoch: int, annealing_epochs: int, activation: str) -> torch.Tensor:
    """MSE + annealed KL divergence (Sensoy 2018 Eq. 3 + 4)."""
    K = logits.shape[-1]
    evidence = get_evidence(logits, activation)
    alpha = evidence + 1.0
    S = alpha.sum(dim=-1, keepdim=True)

    y = F.one_hot(targets, num_classes=K).float()

    # MSE term
    p = alpha / S
    mse = ((y - p) ** 2 + p * (1 - p) / (S + 1)).sum(-1).mean()

    # KL term on α̃ (remove evidence of correct class)
    alpha_tilde = y + (1.0 - y) * alpha
    kl = kl_dirichlet_uniform(alpha_tilde)
    lam = min(1.0, epoch / max(annealing_epochs, 1))
    return mse + lam * kl.mean()


# ── Model & sampler ──────────────────────────────────────────────────────────

def build_model(cfg) -> nn.Module:
    model = timm.create_model(
        cfg.backbone.name,
        pretrained=cfg.backbone.pretrained,
        num_classes=cfg.backbone.num_classes,
        drop_rate=cfg.backbone.get("drop_rate", 0.0),
    )
    return model


def build_sampler(dataset: ISICImageDataset) -> WeightedRandomSampler:
    targets = dataset.df["target"].values
    w_pos = float(dataset.class_weights[1])
    weights = np.where(targets == 1, w_pos, 1.0)
    return WeightedRandomSampler(
        weights=torch.from_numpy(weights).float(),
        num_samples=len(weights), replacement=True,
    )


def cosine_factor(epoch: int, total: int, warmup: int) -> float:
    if epoch < warmup:
        return (epoch + 1) / max(warmup, 1)
    progress = (epoch - warmup) / max(total - warmup, 1)
    return 0.5 * (1.0 + np.cos(np.pi * progress))


# ── Eval ─────────────────────────────────────────────────────────────────────

@torch.no_grad()
def evaluate(model, loader, device, cfg, epoch: int, collect: bool = False):
    model.eval()
    activation = cfg.train.get("evidence_activation", "relu")
    total_loss = 0.0
    n_batches = 0
    all_probs, all_targets, all_logits, all_ids = [], [], [], []

    for batch in tqdm(loader, desc="eval", leave=False):
        x = batch["image"].to(device, non_blocking=True)
        y = batch["target"].to(device, non_blocking=True)
        with torch.amp.autocast("cuda", enabled=cfg.train.amp):
            logits = model(x)
            loss = edl_loss(logits, y, epoch,
                            cfg.train.annealing_epochs, activation)
        evidence = get_evidence(logits.float(), activation)
        alpha = evidence + 1.0
        S = alpha.sum(-1)
        prob = (alpha[:, 1] / S).cpu().numpy()

        total_loss += loss.item()
        n_batches += 1
        all_probs.extend(prob)
        all_targets.extend(y.cpu().numpy())
        if collect:
            all_logits.append(logits.float().cpu().numpy())
            all_ids.extend(batch["isic_id"])

    targets_arr = np.array(all_targets)
    probs_arr = np.array(all_probs)
    auc = float(roc_auc_score(targets_arr, probs_arr)) if len(set(targets_arr)) > 1 else float("nan")
    out = {"loss": total_loss / max(n_batches, 1), "auc": auc}
    if collect:
        out["logits"] = np.concatenate(all_logits, 0)
        out["targets"] = targets_arr
        out["isic_ids"] = np.array(all_ids)
        out["probs"] = probs_arr
    return out


# ── Train one epoch ───────────────────────────────────────────────────────────

def train_one_epoch(model, loader, optimizer, scaler, device, cfg, epoch):
    model.train()
    activation = cfg.train.get("evidence_activation", "relu")
    annealing_epochs = cfg.train.annealing_epochs
    total_loss = 0.0
    n_batches = 0
    for batch in tqdm(loader, desc=f"train ep {epoch+1}", leave=False):
        x = batch["image"].to(device, non_blocking=True)
        y = batch["target"].to(device, non_blocking=True)
        optimizer.zero_grad()
        with torch.amp.autocast("cuda", enabled=cfg.train.amp):
            logits = model(x)
            loss = edl_loss(logits, y, epoch, annealing_epochs, activation)
        if cfg.train.amp:
            scaler.scale(loss).backward()
            scaler.unscale_(optimizer)
            nn.utils.clip_grad_norm_(model.parameters(), cfg.train.grad_clip)
            scaler.step(optimizer)
            scaler.update()
        else:
            loss.backward()
            nn.utils.clip_grad_norm_(model.parameters(), cfg.train.grad_clip)
            optimizer.step()
        total_loss += loss.item()
        n_batches += 1
    return {"loss": total_loss / max(n_batches, 1)}


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    args = parse_args()
    cfg = OmegaConf.load(args.config)
    if args.seed is not None:
        cfg.train.seed = args.seed
    torch.manual_seed(cfg.train.seed)
    np.random.seed(cfg.train.seed)

    device = torch.device("cuda" if cfg.device.cuda and torch.cuda.is_available() else "cpu")
    print(f"[train_edl] device={device}  config={args.config}")

    train_ds = ISICImageDataset(
        split="train", img_size=cfg.data.img_size,
        image_root=cfg.data.image_root, metadata_csv=cfg.data.metadata_csv,
        split_csv=cfg.data.split_csv,
    )
    val_ds = ISICImageDataset(
        split="val", img_size=cfg.data.img_size,
        image_root=cfg.data.image_root, metadata_csv=cfg.data.metadata_csv,
        split_csv=cfg.data.split_csv,
    )
    test_ds = ISICImageDataset(
        split="test", img_size=cfg.data.img_size,
        image_root=cfg.data.image_root, metadata_csv=cfg.data.metadata_csv,
        split_csv=cfg.data.split_csv,
    )
    print(f"sizes: train={len(train_ds)} val={len(val_ds)} test={len(test_ds)}")

    sampler = build_sampler(train_ds)
    nw = 0 if args.dry_run else cfg.data.num_workers
    pw = nw > 0
    mp_ctx = "spawn" if nw > 0 else None
    train_loader = DataLoader(
        train_ds, batch_size=cfg.train.batch_size, sampler=sampler,
        num_workers=nw, collate_fn=isic_collate,
        multiprocessing_context=mp_ctx, persistent_workers=pw, pin_memory=True,
    )
    val_loader = DataLoader(
        val_ds, batch_size=cfg.train.batch_size, shuffle=False,
        num_workers=nw, collate_fn=isic_collate,
        multiprocessing_context=mp_ctx, persistent_workers=pw, pin_memory=True,
    )
    test_loader = DataLoader(
        test_ds, batch_size=cfg.train.batch_size, shuffle=False,
        num_workers=nw, collate_fn=isic_collate,
        multiprocessing_context=mp_ctx, persistent_workers=pw, pin_memory=True,
    )

    model = build_model(cfg).to(device)
    n_params = sum(p.numel() for p in model.parameters())
    print(f"{cfg.backbone.name} params: {n_params/1e6:.2f}M")

    # Layer-wise LR: backbone vs classifier head
    lr_head = cfg.train.lr
    lr_backbone = cfg.train.get("lr_backbone", cfg.train.lr * 0.1)
    head_params = list(model.classifier.parameters()) if hasattr(model, "classifier") \
        else list(model.head.parameters()) if hasattr(model, "head") \
        else list(model.get_classifier().parameters())
    head_ids = {id(p) for p in head_params}
    backbone_params = [p for p in model.parameters() if id(p) not in head_ids]
    optimizer = torch.optim.AdamW([
        {"params": backbone_params, "lr": lr_backbone, "initial_lr": lr_backbone},
        {"params": head_params,     "lr": lr_head,     "initial_lr": lr_head},
    ], weight_decay=cfg.train.weight_decay)
    scaler = torch.amp.GradScaler("cuda", enabled=cfg.train.amp)

    start_epoch = 0
    best_metric = -1.0
    best_path = None
    if args.resume:
        ckpt = torch.load(args.resume, map_location=device, weights_only=False)
        model.load_state_dict(ckpt["model"])
        optimizer.load_state_dict(ckpt["optimizer"])
        if "scaler" in ckpt and cfg.train.amp:
            scaler.load_state_dict(ckpt["scaler"])
        start_epoch = ckpt["epoch"] + 1
        best_metric = ckpt.get("best_metric", -1.0)
        print(f"Resumed from epoch {start_epoch}, best={best_metric:.4f}")

    ckpt_dir = Path(cfg.output.checkpoint_dir)
    logits_dir = Path(cfg.output.logits_dir)
    ckpt_dir.mkdir(parents=True, exist_ok=True)
    logits_dir.mkdir(parents=True, exist_ok=True)

    if args.dry_run:
        print("[dry-run] one batch forward+backward...")
        model.train()
        batch = next(iter(train_loader))
        x = batch["image"].to(device)
        y = batch["target"].to(device)
        with torch.amp.autocast("cuda", enabled=cfg.train.amp and device.type == "cuda"):
            logits = model(x)
            loss = edl_loss(logits, y, 0, cfg.train.annealing_epochs,
                            cfg.train.get("evidence_activation", "relu"))
        print(f"[dry-run] loss={loss.item():.4f}  logits.shape={tuple(logits.shape)}")
        scaler.scale(loss).backward() if cfg.train.amp and device.type == "cuda" else loss.backward()
        print("[dry-run] OK")
        return

    wandb.init(
        project=cfg.wandb.project, entity=cfg.wandb.entity,
        mode=cfg.wandb.get("mode", "offline"),
        config=OmegaConf.to_container(cfg, resolve=True),
        name=cfg.wandb.get("run_name", "edl"),
    )

    state = {
        "status": "running",
        "experiment": {"script": "train_edl.py", "config": args.config},
        "process": {"pid": os.getpid(), "is_alive": True},
        "progress": {
            "current_epoch": start_epoch, "total_epochs": cfg.train.epochs,
            "last_loss": None, "last_val_metric": None,
            "val_metric_history": [], "kl_history": [],
        },
        "checkpoint": {
            "save_dir": str(ckpt_dir), "last_path": args.resume, "best_path": None,
        },
        "error": {"type": None, "message": None},
    }
    write_state(state)

    for epoch in range(start_epoch, cfg.train.epochs):
        factor = cosine_factor(epoch, cfg.train.epochs, cfg.train.warmup_epochs)
        for g in optimizer.param_groups:
            g["lr"] = g["initial_lr"] * factor
        lr_now = factor * cfg.train.lr

        t0 = time.time()
        tr = train_one_epoch(model, train_loader, optimizer, scaler, device, cfg, epoch)
        vl = evaluate(model, val_loader, device, cfg, epoch)
        elapsed = time.time() - t0
        print(
            f"ep {epoch+1}/{cfg.train.epochs} | lr={lr_now:.2e} "
            f"tr_loss={tr['loss']:.4f} | val_loss={vl['loss']:.4f} val_auc={vl['auc']:.4f} | {elapsed:.0f}s"
        )
        wandb.log({
            "epoch": epoch + 1, "lr": lr_now,
            "train/loss": tr["loss"],
            "val/loss": vl["loss"], "val/auc": vl["auc"],
        })

        ckpt_data = {
            "epoch": epoch, "model": model.state_dict(),
            "optimizer": optimizer.state_dict(),
            "scaler": scaler.state_dict() if cfg.train.amp else None,
            "best_metric": best_metric, "cfg": OmegaConf.to_container(cfg, resolve=True),
        }
        last_path = ckpt_dir / "last_edl.pth"
        torch.save(ckpt_data, last_path)

        val_metric = vl["auc"]
        if not np.isnan(val_metric) and val_metric > best_metric:
            best_metric = val_metric
            best_path = ckpt_dir / "best_edl.pth"
            torch.save(ckpt_data, best_path)
            print(f"  => best val AUC={best_metric:.4f}")

        state["progress"].update({
            "current_epoch": epoch + 1, "total_epochs": cfg.train.epochs,
            "last_loss": round(tr["loss"], 4),
            "last_val_metric": round(float(val_metric), 4) if not np.isnan(val_metric) else None,
        })
        state["progress"]["val_metric_history"].append(
            round(float(val_metric), 4) if not np.isnan(val_metric) else None
        )
        state["checkpoint"]["last_path"] = str(last_path)
        if best_path:
            state["checkpoint"]["best_path"] = str(best_path)
        write_state(state)

    # Export: load best, save logits + probs (for calibration eval)
    if best_path:
        ckpt = torch.load(best_path, map_location=device, weights_only=False)
        model.load_state_dict(ckpt["model"])
        print(f"[export] loaded best (val AUC={best_metric:.4f})")

    for split, loader in [("val", val_loader), ("test", test_loader)]:
        out = evaluate(model, loader, device, cfg, cfg.train.epochs - 1, collect=True)
        np.save(logits_dir / f"{split}_logits.npy", out["logits"])
        np.save(logits_dir / f"{split}_targets.npy", out["targets"])
        np.save(logits_dir / f"{split}_ids.npy", out["isic_ids"])
        np.save(logits_dir / f"{split}_probs.npy", out["probs"])
        print(f"[export] {split}: auc={out['auc']:.4f}  n={len(out['targets'])}")

    state["status"] = "done"
    write_state(state)
    wandb.finish()
    print("Training complete.")


if __name__ == "__main__":
    main()
