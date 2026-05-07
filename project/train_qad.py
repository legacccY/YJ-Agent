"""Q-VIB / QAD Training Script.

Pipeline per batch:
  1. Segmenter(image_bgr) -> mask
  2. extract_abcd(image_bgr, mask) -> abcd (B, 4)
  3. VisiScore-Net(image_tensor) [frozen] -> q  (skipped: q already in dataset CSV)
  4. QVIBEncoder(abcd, q) -> mu, log_sigma_sq
  5. reparameterize -> z
  6. QADClassifier(z) -> logits
  7. QVIBLoss(logits, target, mu, log_sigma_sq, q) -> loss

State file (for run-experiment monitor):
  D:/YJ-Agent/log/experiment_state.json

Usage:
    python train_qad.py --config configs/qad.yaml
    python train_qad.py --config configs/qad.yaml --resume D:/YJ-Agent/checkpoints/last_qad.pth
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
from omegaconf import OmegaConf
from sklearn.metrics import roc_auc_score
from torch.utils.data import DataLoader, WeightedRandomSampler
from tqdm import tqdm

import wandb

from data.qad_dataset import QADDataset, qad_collate_fn
from models.q_vib_encoder import QVIBEncoder
from models.q_vib_loss import QVIBLoss
from models.qad_classifier import QADClassifier
from models.quality_adaptive_prior import QualityAdaptivePrior

STATE_PATH = Path("D:/YJ-Agent/log/experiment_state.json")
os.environ["OMP_NUM_THREADS"] = "1"


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--config", default="configs/qad.yaml")
    p.add_argument("--resume", default=None)
    return p.parse_args()


def write_state(state: dict):
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, indent=2), encoding="utf-8")


def build_sampler(dataset: QADDataset) -> WeightedRandomSampler:
    """Over-sample minority class to handle 56:1 imbalance."""
    targets = dataset.df["target"].values
    weights = np.where(targets == 1,
                       float(dataset.class_weights[1]),
                       float(dataset.class_weights[0]))
    return WeightedRandomSampler(
        weights=torch.from_numpy(weights).float(),
        num_samples=len(weights),
        replacement=True,
    )


def accuracy(logits: torch.Tensor, targets: torch.Tensor) -> float:
    return (logits.argmax(dim=-1) == targets).float().mean().item()


def run_epoch(
    phase: str,
    loader: DataLoader,
    encoder: QVIBEncoder,
    classifier: QADClassifier,
    loss_fn: QVIBLoss,
    optimizer,
    device: torch.device,
    cfg,
    epoch: int,
) -> dict:
    train = phase == "train"
    encoder.train(train)
    classifier.train(train)

    total_loss = total_ce = total_kl = total_acc = 0.0
    n_batches = 0
    class_w = loss_fn._class_weights.to(device) if hasattr(loss_fn, "_class_weights") else None
    all_probs, all_targets = [], []

    for batch in tqdm(loader, desc=f"{phase} epoch {epoch+1}", leave=False):
        abcd = batch["abcd"].to(device)
        q = batch["q"].to(device)
        targets = batch["target"].to(device)
        efnet_feat = batch["efnet_feat"].to(device) if "efnet_feat" in batch else None

        with torch.set_grad_enabled(train):
            with torch.amp.autocast("cuda", enabled=cfg.train.amp):
                mu, log_sigma_sq = encoder(abcd, q, efnet_feat=efnet_feat)
                z = encoder.reparameterize(mu, log_sigma_sq)
                logits = classifier(z)
                loss, info = loss_fn(logits, targets, mu, log_sigma_sq, q, weight=class_w)

        if train:
            optimizer.zero_grad()
            loss.backward()
            nn.utils.clip_grad_norm_(
                list(encoder.parameters()) + list(classifier.parameters()), 1.0
            )
            optimizer.step()
            loss_fn.step()

        total_loss += loss.item()
        total_ce += info["ce"]
        total_kl += info["kl"]
        total_acc += accuracy(logits.detach(), targets)
        n_batches += 1

        if not train:
            probs = torch.softmax(logits.detach(), dim=-1)[:, 1].cpu().numpy()
            all_probs.extend(probs)
            all_targets.extend(targets.cpu().numpy())

    result = {
        "loss": total_loss / n_batches,
        "ce":   total_ce   / n_batches,
        "kl":   total_kl   / n_batches,
        "acc":  total_acc  / n_batches,
        "beta": info["beta"],
    }
    if not train and len(set(all_targets)) > 1:
        result["auc"] = float(roc_auc_score(all_targets, all_probs))
    else:
        result["auc"] = float("nan")
    return result


def main():
    args = parse_args()
    cfg = OmegaConf.load(args.config)
    torch.manual_seed(cfg.train.seed)

    device = torch.device("cuda" if cfg.device.cuda and torch.cuda.is_available() else "cpu")
    print(f"Device: {device}")

    abcd_cache = cfg.data.get("abcd_cache_csv", None)
    if abcd_cache is None:
        raise ValueError("abcd_cache_csv must be set in config. Run precompute_abcd.py first.")

    # Dataset (cache mode: loads pre-computed ABCD, no live segmentation)
    efnet_npy = cfg.data.get("efnet_features_npy", None)
    efnet_idx = cfg.data.get("efnet_index_csv", None)
    split_csv = cfg.data.get("split_csv", None)

    train_ds = QADDataset(
        quality_csv=cfg.data.labels_csv,
        metadata_csv=cfg.data.metadata_csv,
        abcd_cache_csv=abcd_cache,
        efnet_features_npy=efnet_npy,
        efnet_index_csv=efnet_idx,
        split_csv=split_csv,
        split="train" if split_csv else None,
        levels=cfg.data.get("levels", None),
        source_filter=cfg.data.get("source_filter", None),
    )
    val_ds = QADDataset(
        quality_csv=cfg.data.labels_csv,
        metadata_csv=cfg.data.metadata_csv,
        abcd_cache_csv=abcd_cache,
        efnet_features_npy=efnet_npy,
        efnet_index_csv=efnet_idx,
        split_csv=split_csv,
        split="val" if split_csv else None,
    )
    print(f"Train: {len(train_ds)} samples  Val: {len(val_ds)} samples")
    print(f"Class weights: {train_ds.class_weights.tolist()}")

    sampler = build_sampler(train_ds)
    train_loader = DataLoader(
        train_ds, batch_size=cfg.train.batch_size, sampler=sampler,
        num_workers=cfg.data.num_workers, collate_fn=qad_collate_fn,
        multiprocessing_context="spawn", persistent_workers=True, pin_memory=False,
    )
    val_loader = DataLoader(
        val_ds, batch_size=cfg.train.batch_size, shuffle=False,
        num_workers=cfg.data.num_workers, collate_fn=qad_collate_fn,
        multiprocessing_context="spawn", persistent_workers=True, pin_memory=False,
    )

    # Models
    prior = QualityAdaptivePrior(
        sigma0_sq=cfg.model.prior.sigma0_sq,
        tau=cfg.model.prior.tau,
        alpha=cfg.model.prior.alpha,
    ).to(device)

    encoder = QVIBEncoder(
        abcd_dim=4, q_dim=5,
        d_model=cfg.model.encoder.d_model,
        n_heads=cfg.model.encoder.n_heads,
        latent_dim=cfg.model.encoder.latent_dim,
        efnet_dim=cfg.model.encoder.get("efnet_dim", 0),
        use_tokenizer=cfg.model.encoder.get("use_tokenizer", True),
    ).to(device)

    classifier = QADClassifier(
        latent_dim=cfg.model.encoder.latent_dim,
        hidden_dim=cfg.model.classifier.hidden_dim,
        num_classes=cfg.model.classifier.num_classes,
    ).to(device)

    loss_fn = QVIBLoss(
        prior=prior,
        beta_max=cfg.train.beta_max,
        warmup_steps=cfg.train.beta_warmup_steps,
    ).to(device)
    loss_fn._class_weights = train_ds.class_weights

    params = list(encoder.parameters()) + list(classifier.parameters())
    optimizer = torch.optim.AdamW(params, lr=cfg.train.lr, weight_decay=cfg.train.weight_decay)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=cfg.train.epochs)

    start_epoch = 0
    best_acc = 0.0
    if args.resume:
        ckpt = torch.load(args.resume, map_location=device)
        encoder.load_state_dict(ckpt["encoder"])
        classifier.load_state_dict(ckpt["classifier"])
        optimizer.load_state_dict(ckpt["optimizer"])
        start_epoch = ckpt["epoch"] + 1
        best_acc = ckpt.get("best_acc", 0.0)
        print(f"Resumed from epoch {start_epoch}")

    # wandb
    wandb.init(
        project=cfg.wandb.project,
        entity=cfg.wandb.entity,
        mode=cfg.wandb.get("mode", "online"),
        config=OmegaConf.to_container(cfg, resolve=True),
        name=f"qad-beta{cfg.train.beta_max}",
    )

    ckpt_dir = Path(cfg.output.checkpoint_dir)
    ckpt_dir.mkdir(parents=True, exist_ok=True)

    state = {
        "status": "running",
        "experiment": {"script": "train_qad.py", "config": args.config},
        "process": {"pid": os.getpid(), "is_alive": True},
        "progress": {
            "current_epoch": start_epoch, "total_epochs": cfg.train.epochs,
            "last_loss": None, "last_val_metric": None, "val_metric_history": [],
        },
        "checkpoint": {
            "save_dir": str(ckpt_dir),
            "last_path": args.resume, "best_path": None,
        },
        "error": {"type": None, "message": None},
    }
    write_state(state)

    for epoch in range(start_epoch, cfg.train.epochs):
        t0 = time.time()
        tr = run_epoch("train", train_loader, encoder, classifier, loss_fn,
                       optimizer, device, cfg, epoch)
        vl = run_epoch("val", val_loader, encoder, classifier, loss_fn,
                       None, device, cfg, epoch)
        scheduler.step()

        elapsed = time.time() - t0
        val_auc = vl.get("auc", float("nan"))
        print(
            f"Epoch {epoch+1}/{cfg.train.epochs} | "
            f"tr_loss={tr['loss']:.4f} ce={tr['ce']:.4f} kl={tr['kl']:.4f} acc={tr['acc']:.3f} | "
            f"val_loss={vl['loss']:.4f} val_acc={vl['acc']:.3f} val_AUC={val_auc:.4f} | "
            f"beta={tr['beta']:.1e} | {elapsed:.0f}s"
        )

        wandb.log({
            "epoch": epoch + 1,
            "train/loss": tr["loss"], "train/ce": tr["ce"],
            "train/kl": tr["kl"], "train/acc": tr["acc"],
            "val/loss": vl["loss"], "val/acc": vl["acc"], "val/auc": val_auc,
            "train/beta": tr["beta"],
        })

        # Use AUC as primary metric for best checkpoint (falls back to acc if AUC unavailable)
        val_metric = val_auc if val_auc == val_auc else vl["acc"]

        ckpt_data = {
            "epoch": epoch, "encoder": encoder.state_dict(),
            "classifier": classifier.state_dict(),
            "optimizer": optimizer.state_dict(), "best_acc": best_acc,
        }
        last_path = ckpt_dir / "last_qad.pth"
        torch.save(ckpt_data, last_path)

        if val_metric > best_acc:
            best_acc = val_metric
            best_path = ckpt_dir / "best_qad.pth"
            torch.save(ckpt_data, best_path)
            print(f"  => Best val AUC: {best_acc:.4f}")

        # Update state.json
        state["progress"].update({
            "current_epoch": epoch, "total_epochs": cfg.train.epochs,
            "last_loss": round(tr["loss"], 4),
            "last_val_metric": round(val_metric, 4),
        })
        state["progress"]["val_metric_history"].append(round(val_metric, 4))
        state["checkpoint"]["last_path"] = str(last_path)
        if val_metric >= best_acc:
            state["checkpoint"]["best_path"] = str(best_path)
        write_state(state)

    state["status"] = "done"
    write_state(state)
    print("Training complete.")
    wandb.finish()


if __name__ == "__main__":
    main()
