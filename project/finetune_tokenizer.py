"""Fine-tune Q-VIB (model F) tokenizer with auxiliary quality prediction loss.

Diagnosis: the quality tokenizer delta output shows r=0.052 correlation with qbar
(not significant). LQ delta ~ HQ delta, meaning the tokenizer did not learn quality-
dependent behaviour during the original training run.

Fix: add auxiliary loss term that forces the tokenizer to predict qbar from its
scalar output delta:
  L_total = L_cls + beta * L_KL + gamma * MSE(sigmoid(delta/3), qbar_mean)

This makes delta discriminative w.r.t. image quality while keeping the primary
classification and information-bottleneck objectives intact.

Usage (via /loop):
  /loop /run-experiment project/finetune_tokenizer.py

Or directly (for debugging only, not recommended for long runs):
  cd D:/YJ-Agent/project && python finetune_tokenizer.py

Output:
  D:/YJ-Agent/checkpoints/efnet_tokft/best_qad.pth
  Prints tokenizer delta vs qbar Pearson r before and after fine-tuning.
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
from omegaconf import OmegaConf
from scipy.stats import pearsonr
from sklearn.metrics import roc_auc_score
from torch.utils.data import DataLoader, WeightedRandomSampler
from tqdm import tqdm

from data.qad_dataset import QADDataset, qad_collate_fn
from models.q_vib_encoder import QVIBEncoder
from models.q_vib_loss import QVIBLoss
from models.qad_classifier import QADClassifier
from models.quality_adaptive_prior import QualityAdaptivePrior

# ── Paths ─────────────────────────────────────────────────────────────────────
CHECKPOINT_IN  = Path("D:/YJ-Agent/checkpoints/efnet/best_qad.pth")
CHECKPOINT_OUT = Path("D:/YJ-Agent/checkpoints/efnet_tokft/best_qad.pth")
STATE_PATH     = Path("D:/YJ-Agent/log/experiment_state.json")
CONFIG_PATH    = Path("D:/YJ-Agent/project/configs/qad_efnet.yaml")

os.environ["OMP_NUM_THREADS"] = "1"

# ── Hyper-parameters ──────────────────────────────────────────────────────────
FINETUNE_EPOCHS  = 10
GAMMA            = 0.5    # weight for auxiliary quality regression loss
LR               = 3e-4   # slightly lower than original training lr
WEIGHT_DECAY     = 1e-4
SEED             = 42


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--config", default=str(CONFIG_PATH))
    p.add_argument("--checkpoint_in", default=str(CHECKPOINT_IN))
    p.add_argument("--checkpoint_out", default=str(CHECKPOINT_OUT))
    p.add_argument("--epochs", type=int, default=FINETUNE_EPOCHS)
    p.add_argument("--gamma", type=float, default=GAMMA,
                   help="Weight for auxiliary quality regression loss")
    p.add_argument("--lr", type=float, default=LR)
    return p.parse_args()


def write_state(state: dict):
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, indent=2), encoding="utf-8")


def build_sampler(dataset: QADDataset) -> WeightedRandomSampler:
    """Over-sample minority class to handle class imbalance."""
    targets = dataset.df["target"].values
    weights = np.where(targets == 1,
                       float(dataset.class_weights[1]),
                       float(dataset.class_weights[0]))
    return WeightedRandomSampler(
        weights=torch.from_numpy(weights).float(),
        num_samples=len(weights),
        replacement=True,
    )


@torch.no_grad()
def measure_tokenizer_correlation(
    encoder: QVIBEncoder,
    loader: DataLoader,
    device: torch.device,
) -> float:
    """Compute Pearson r between tokenizer delta and mean quality score qbar.

    Returns float correlation coefficient. NaN if insufficient data.
    """
    encoder.eval()
    all_delta, all_qbar = [], []

    for batch in tqdm(loader, desc="measuring delta-qbar correlation", leave=False):
        q = batch["q"].to(device)
        abcd = batch["abcd"].to(device)
        efnet_feat = batch["efnet_feat"].to(device) if "efnet_feat" in batch else None

        # Compute tokenizer delta directly (not full forward pass)
        delta = encoder.tokenizer(q)  # (B,)

        qbar = q.mean(dim=-1)  # (B,) — mean of 5 quality dimensions

        all_delta.extend(delta.cpu().numpy().tolist())
        all_qbar.extend(qbar.cpu().numpy().tolist())

    if len(all_delta) < 10:
        return float("nan")

    r, p = pearsonr(all_delta, all_qbar)
    print(f"  delta-qbar Pearson r = {r:.4f}  (p={p:.4f})")
    return float(r)


def auxiliary_tokenizer_loss(
    encoder: QVIBEncoder,
    q: torch.Tensor,
    gamma: float,
) -> torch.Tensor:
    """MSE loss: sigmoid(delta/3) should predict qbar.

    Rationale:
      - sigmoid(delta/3) maps delta ∈ (-∞, +∞) to (0, 1), matching the qbar range.
      - Dividing by 3 before sigmoid keeps gradients large near delta=0.
      - Encourages |delta| to be large for high-quality images and small for low-quality,
        making the tokenizer discriminative w.r.t. image quality.

    Args:
        encoder: QVIBEncoder with a .tokenizer attribute.
        q: Quality vector (B, 5), values in [0, 1].
        gamma: Loss weight.

    Returns:
        Scalar auxiliary loss (gamma * MSE).
    """
    delta = encoder.tokenizer(q)           # (B,) — scalar attention bias
    delta_sigmoid = torch.sigmoid(delta / 3.0)  # map to (0, 1)
    qbar = q.mean(dim=-1)                  # (B,) — mean quality
    return gamma * F.mse_loss(delta_sigmoid, qbar)


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
    gamma: float,
) -> dict:
    train = phase == "train"
    encoder.train(train)
    classifier.train(train)

    total_loss = total_ce = total_kl = total_aux = total_acc = 0.0
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

                # Primary Q-VIB ELBO loss (CE + beta * KL)
                base_loss, info = loss_fn(logits, targets, mu, log_sigma_sq, q, weight=class_w)

                # Auxiliary tokenizer quality regression loss
                aux_loss = auxiliary_tokenizer_loss(encoder, q, gamma)

                loss = base_loss + aux_loss

        if train:
            optimizer.zero_grad()
            loss.backward()
            nn.utils.clip_grad_norm_(
                list(encoder.parameters()) + list(classifier.parameters()), 1.0
            )
            optimizer.step()
            loss_fn.step()

        total_loss += loss.item()
        total_ce   += info["ce"]
        total_kl   += info["kl"]
        total_aux  += aux_loss.item()
        total_acc  += (logits.detach().argmax(dim=-1) == targets).float().mean().item()
        n_batches  += 1

        if not train:
            probs = torch.softmax(logits.detach(), dim=-1)[:, 1].cpu().numpy()
            all_probs.extend(probs)
            all_targets.extend(targets.cpu().numpy())

    result = {
        "loss": total_loss / n_batches,
        "ce":   total_ce   / n_batches,
        "kl":   total_kl   / n_batches,
        "aux":  total_aux  / n_batches,
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
    torch.manual_seed(SEED)
    np.random.seed(SEED)

    cfg = OmegaConf.load(args.config)
    device = torch.device("cuda" if cfg.device.cuda and torch.cuda.is_available() else "cpu")
    print(f"Device: {device}")
    print(f"Fine-tuning checkpoint: {args.checkpoint_in}")
    print(f"Output: {args.checkpoint_out}")
    print(f"Epochs: {args.epochs}, gamma: {args.gamma}, lr: {args.lr}")

    # ── Dataset ───────────────────────────────────────────────────────────────
    abcd_cache = cfg.data.get("abcd_cache_csv", None)
    if abcd_cache is None:
        raise ValueError("abcd_cache_csv must be set in config. Run precompute_abcd.py first.")

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

    # ── Models ────────────────────────────────────────────────────────────────
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

    # ── Load F checkpoint ─────────────────────────────────────────────────────
    ckpt_path = Path(args.checkpoint_in)
    if not ckpt_path.exists():
        raise FileNotFoundError(
            f"Checkpoint not found: {ckpt_path}\n"
            "Run train_qad.py first to produce the F checkpoint."
        )
    ckpt = torch.load(ckpt_path, map_location=device)
    encoder.load_state_dict(ckpt["encoder"])
    classifier.load_state_dict(ckpt["classifier"])
    print(f"Loaded checkpoint from epoch {ckpt.get('epoch', '?')}")

    # ── Measure BEFORE fine-tuning ────────────────────────────────────────────
    print("\n=== Tokenizer delta-qbar correlation BEFORE fine-tuning ===")
    r_before = measure_tokenizer_correlation(encoder, val_loader, device)

    # ── Optimizer: fine-tune all params (tokenizer + rest) ───────────────────
    params = list(encoder.parameters()) + list(classifier.parameters())
    optimizer = torch.optim.AdamW(params, lr=args.lr, weight_decay=WEIGHT_DECAY)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=args.epochs)

    # ── State file ────────────────────────────────────────────────────────────
    state = {
        "status": "running",
        "experiment": {
            "script": "finetune_tokenizer.py",
            "gamma": args.gamma,
            "epochs": args.epochs,
            "r_before": r_before,
        },
        "process": {"pid": os.getpid(), "is_alive": True},
        "progress": {
            "current_epoch": 0, "total_epochs": args.epochs,
            "last_loss": None, "last_val_metric": None, "val_metric_history": [],
        },
        "checkpoint": {
            "save_dir": str(Path(args.checkpoint_out).parent),
            "last_path": None, "best_path": None,
        },
        "error": {"type": None, "message": None},
    }
    write_state(state)

    ckpt_dir = Path(args.checkpoint_out).parent
    ckpt_dir.mkdir(parents=True, exist_ok=True)

    best_val_metric = -1.0
    best_r = r_before

    print("\n=== Starting fine-tuning ===")
    for epoch in range(args.epochs):
        t0 = time.time()
        tr = run_epoch("train", train_loader, encoder, classifier, loss_fn,
                       optimizer, device, cfg, epoch, args.gamma)
        vl = run_epoch("val", val_loader, encoder, classifier, loss_fn,
                       None, device, cfg, epoch, args.gamma)
        scheduler.step()

        elapsed = time.time() - t0
        val_auc = vl.get("auc", float("nan"))
        print(
            f"Epoch {epoch+1}/{args.epochs} | "
            f"tr_loss={tr['loss']:.4f} ce={tr['ce']:.4f} kl={tr['kl']:.4f} aux={tr['aux']:.4f} | "
            f"val_loss={vl['loss']:.4f} val_AUC={val_auc:.4f} val_aux={vl['aux']:.4f} | "
            f"beta={tr['beta']:.1e} | {elapsed:.0f}s"
        )

        val_metric = val_auc if val_auc == val_auc else vl["acc"]

        ckpt_data = {
            "epoch": epoch,
            "encoder": encoder.state_dict(),
            "classifier": classifier.state_dict(),
            "optimizer": optimizer.state_dict(),
            "best_val_metric": best_val_metric,
            "gamma": args.gamma,
            "r_before": r_before,
        }
        last_path = ckpt_dir / "last_qad.pth"
        torch.save(ckpt_data, last_path)

        if val_metric > best_val_metric:
            best_val_metric = val_metric
            torch.save(ckpt_data, Path(args.checkpoint_out))
            print(f"  => Best val metric: {best_val_metric:.4f} — saved to {args.checkpoint_out}")

        state["progress"].update({
            "current_epoch": epoch, "total_epochs": args.epochs,
            "last_loss": round(tr["loss"], 4),
            "last_val_metric": round(val_metric, 4) if val_metric == val_metric else None,
        })
        state["progress"]["val_metric_history"].append(
            round(val_metric, 4) if val_metric == val_metric else None
        )
        state["checkpoint"]["last_path"] = str(last_path)
        if val_metric >= best_val_metric:
            state["checkpoint"]["best_path"] = str(args.checkpoint_out)
        write_state(state)

    # ── Measure AFTER fine-tuning (load best checkpoint) ─────────────────────
    print("\n=== Tokenizer delta-qbar correlation AFTER fine-tuning ===")
    best_ckpt = torch.load(Path(args.checkpoint_out), map_location=device)
    encoder.load_state_dict(best_ckpt["encoder"])
    r_after = measure_tokenizer_correlation(encoder, val_loader, device)

    print("\n=== Fine-tuning summary ===")
    print(f"  delta-qbar Pearson r BEFORE: {r_before:.4f}")
    print(f"  delta-qbar Pearson r AFTER:  {r_after:.4f}")
    print(f"  Best val metric: {best_val_metric:.4f}")
    print(f"  Checkpoint saved to: {args.checkpoint_out}")

    state["status"] = "done"
    state["experiment"]["r_after"] = r_after
    state["experiment"]["r_improvement"] = r_after - r_before
    write_state(state)
    print("Fine-tuning complete.")


if __name__ == "__main__":
    main()
