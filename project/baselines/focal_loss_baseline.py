"""Focal Loss + Label Smoothing Baseline (Baseline H).

MLP (1284D -> 256 -> 128 -> 2) trained with Focal Loss (gamma=2.0) + Label Smoothing (eps=0.1).
Input: EfficientNet-B0 features 1280D + ABCD 4D = 1284D.
Standard calibration baseline for comparison with Q-VIB.

Reference: Lin et al. (2017) Focal Loss for Dense Object Detection.

Usage:
    cd D:/YJ-Agent/project
    python -m baselines.focal_loss_baseline

Outputs:
    D:/YJ-Agent/checkpoints/focal/best.pth       (model state + epoch + val_auc)
    D:/YJ-Agent/log/focal_train.log              (training log)
    D:/YJ-Agent/log/experiment_state.json        (monitor state)
"""

import json
import os
import sys
import time
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
from sklearn.metrics import roc_auc_score
from torch.utils.data import DataLoader, WeightedRandomSampler

sys.path.insert(0, str(Path(__file__).parent.parent))
from data.qad_dataset import QADDataset, qad_collate_fn

os.environ["OMP_NUM_THREADS"] = "1"

# ── Paths ──────────────────────────────────────────────────────────────────────
CKPT_DIR  = Path("D:/YJ-Agent/checkpoints/focal")
LOG_PATH  = Path("D:/YJ-Agent/log/focal_train.log")
STATE_PATH = Path("D:/YJ-Agent/log/experiment_state.json")

DATA_QUALITY_CSV = "D:/YJ-Agent/data/quality_labels_all.csv"
DATA_META_CSV    = "D:/YJ-Agent/data/raw/isic2020/train-metadata.csv"
DATA_ABCD_CSV    = "D:/YJ-Agent/data/abcd_cache.csv"
DATA_EFNET_NPY   = "D:/YJ-Agent/data/efficientnet_features.npy"
DATA_EFNET_IDX   = "D:/YJ-Agent/data/efficientnet_index.csv"
DATA_SPLIT_CSV   = "D:/YJ-Agent/data/isic_split.csv"

# ── Hyperparameters ────────────────────────────────────────────────────────────
INPUT_DIM    = 1284   # 1280 (efnet) + 4 (abcd)
HIDDEN_DIMS  = [256, 128]
NUM_CLASSES  = 2
DROPOUT      = 0.3
FOCAL_GAMMA  = 2.0
LABEL_SMOOTH = 0.1
LR           = 1e-4
WEIGHT_DECAY = 1e-4
BATCH_SIZE   = 256
EPOCHS       = 30
DEVICE       = torch.device("cuda" if torch.cuda.is_available() else "cpu")


# ── Utility ────────────────────────────────────────────────────────────────────

def write_state(state: dict):
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, indent=2), encoding="utf-8")


def log(msg: str):
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(line + "\n")


# ── Model ──────────────────────────────────────────────────────────────────────

class FocalMLP(nn.Module):
    """MLP: 1284 -> 256 (ReLU+Dropout) -> 128 (ReLU+Dropout) -> 2."""

    def __init__(self, input_dim: int = INPUT_DIM, dropout: float = DROPOUT):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(input_dim, 256),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(256, 128),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(128, NUM_CLASSES),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.net(x)


# ── Loss ───────────────────────────────────────────────────────────────────────

class FocalLoss(nn.Module):
    """Focal Loss with label smoothing.

    CE is computed with label smoothing (eps), then modulated by (1 - pt)^gamma.
    Following Lin et al. 2017.
    """

    def __init__(self, gamma: float = FOCAL_GAMMA, eps: float = LABEL_SMOOTH,
                 weight: torch.Tensor | None = None):
        super().__init__()
        self.gamma = gamma
        self.eps   = eps
        self.register_buffer("weight", weight)

    def forward(self, logits: torch.Tensor, targets: torch.Tensor) -> torch.Tensor:
        # Label-smoothed cross-entropy probabilities
        num_classes = logits.size(-1)
        # Standard CE with label smoothing
        log_probs = F.log_softmax(logits, dim=-1)               # (B, C)
        # Smooth targets
        with torch.no_grad():
            smooth_targets = torch.full_like(log_probs, self.eps / (num_classes - 1))
            smooth_targets.scatter_(1, targets.unsqueeze(1), 1.0 - self.eps)

        # Per-sample smooth CE: -(sum_c smooth_targets_c * log_probs_c)
        ce = -(smooth_targets * log_probs).sum(dim=-1)          # (B,)

        # Focal weight: (1 - p_t)^gamma, where p_t = softmax prob for true class
        with torch.no_grad():
            probs = log_probs.exp()                              # (B, C)
            pt = probs.gather(1, targets.unsqueeze(1)).squeeze(1)  # (B,)
            focal_weight = (1.0 - pt).pow(self.gamma)

        loss = focal_weight * ce                                  # (B,)

        # Class weighting (for imbalance)
        if self.weight is not None:
            cw = self.weight.to(logits.device)
            sample_weight = cw[targets]
            loss = loss * sample_weight

        return loss.mean()


# ── Data ───────────────────────────────────────────────────────────────────────

def build_loaders():
    common = dict(
        quality_csv=DATA_QUALITY_CSV,
        metadata_csv=DATA_META_CSV,
        abcd_cache_csv=DATA_ABCD_CSV,
        efnet_features_npy=DATA_EFNET_NPY,
        efnet_index_csv=DATA_EFNET_IDX,
        split_csv=DATA_SPLIT_CSV,
        source_filter=["isic2020"],
    )
    train_ds = QADDataset(split="train", **common)
    val_ds   = QADDataset(split="val",   **common)

    # Class-weighted sampler for 1.75% minority class
    targets = train_ds.df["target"].values
    weights = np.where(
        targets == 1,
        float(train_ds.class_weights[1]),
        float(train_ds.class_weights[0]),
    )
    sampler = WeightedRandomSampler(
        weights=torch.from_numpy(weights).float(),
        num_samples=len(weights),
        replacement=True,
    )

    loader_kwargs = dict(
        batch_size=BATCH_SIZE,
        num_workers=0,
        collate_fn=qad_collate_fn,
        pin_memory=False,
    )
    train_loader = DataLoader(train_ds, sampler=sampler, **loader_kwargs)
    val_loader   = DataLoader(val_ds,   shuffle=False,   **loader_kwargs)
    return train_loader, val_loader, train_ds.class_weights


# ── Training ───────────────────────────────────────────────────────────────────

def run_epoch(phase: str, loader: DataLoader, model: FocalMLP,
              loss_fn: FocalLoss, optimizer, scaler, epoch: int) -> dict:
    training = phase == "train"
    model.train(training)

    total_loss = 0.0
    n_batches  = 0
    all_probs, all_targets = [], []

    for batch in loader:
        abcd    = batch["abcd"].to(DEVICE)           # (B, 4)
        efnet   = batch["efnet_feat"].to(DEVICE)     # (B, 1280)
        targets = batch["target"].to(DEVICE)

        x = torch.cat([efnet, abcd], dim=-1)         # (B, 1284)

        with torch.set_grad_enabled(training):
            with torch.amp.autocast("cuda", enabled=(DEVICE.type == "cuda")):
                logits = model(x)
                loss   = loss_fn(logits, targets)

        if training:
            optimizer.zero_grad()
            if scaler is not None:
                scaler.scale(loss).backward()
                scaler.unscale_(optimizer)
                nn.utils.clip_grad_norm_(model.parameters(), 1.0)
                scaler.step(optimizer)
                scaler.update()
            else:
                loss.backward()
                nn.utils.clip_grad_norm_(model.parameters(), 1.0)
                optimizer.step()

        total_loss += loss.item()
        n_batches  += 1

        if not training:
            with torch.no_grad():
                probs = torch.softmax(logits, dim=-1)[:, 1].cpu().numpy()
            all_probs.extend(probs)
            all_targets.extend(targets.cpu().numpy())

    result = {"loss": total_loss / n_batches}
    if not training and len(set(all_targets)) > 1:
        result["auc"] = float(roc_auc_score(all_targets, all_probs))
    else:
        result["auc"] = float("nan")
    return result


def train():
    log(f"Focal+LS Baseline H  |  device={DEVICE}  |  epochs={EPOCHS}")
    log(f"gamma={FOCAL_GAMMA}  eps={LABEL_SMOOTH}  lr={LR}  wd={WEIGHT_DECAY}  bs={BATCH_SIZE}")

    CKPT_DIR.mkdir(parents=True, exist_ok=True)

    train_loader, val_loader, class_weights = build_loaders()
    log(f"Train: {len(train_loader.dataset)} samples  Val: {len(val_loader.dataset)} samples")
    log(f"Class weights: {class_weights.tolist()}")

    model  = FocalMLP().to(DEVICE)
    loss_fn = FocalLoss(gamma=FOCAL_GAMMA, eps=LABEL_SMOOTH,
                        weight=class_weights.to(DEVICE))
    optimizer = torch.optim.Adam(model.parameters(), lr=LR, weight_decay=WEIGHT_DECAY)
    scaler = torch.amp.GradScaler("cuda") if DEVICE.type == "cuda" else None

    best_auc   = 0.0
    best_epoch = 0

    state = {
        "status": "running",
        "experiment": {"script": "baselines/focal_loss_baseline.py"},
        "process": {"pid": os.getpid(), "is_alive": True},
        "progress": {
            "current_epoch": 0, "total_epochs": EPOCHS,
            "last_loss": None, "last_val_metric": None, "val_metric_history": [],
        },
        "checkpoint": {"save_dir": str(CKPT_DIR), "best_path": None},
        "error": {"type": None, "message": None},
    }
    write_state(state)

    for epoch in range(EPOCHS):
        t0 = time.time()
        tr = run_epoch("train", train_loader, model, loss_fn, optimizer, scaler, epoch)
        vl = run_epoch("val",   val_loader,   model, loss_fn, None,      None,   epoch)
        elapsed = time.time() - t0

        val_auc = vl.get("auc", float("nan"))
        log(
            f"Epoch {epoch+1:02d}/{EPOCHS} | "
            f"tr_loss={tr['loss']:.4f} | "
            f"val_loss={vl['loss']:.4f}  val_AUC={val_auc:.4f} | "
            f"{elapsed:.0f}s"
        )

        # Early-stop check: epoch 1 sanity gate
        if epoch == 0 and val_auc == val_auc and val_auc < 0.55:
            msg = (f"EARLY ABORT: val AUC after epoch 1 = {val_auc:.4f} < 0.55. "
                   f"Possible issue with loss/lr. Stopping.")
            log(msg)
            state["status"] = "error"
            state["error"]["type"] = "low_val_auc"
            state["error"]["message"] = msg
            write_state(state)
            return

        if val_auc == val_auc and val_auc > best_auc:
            best_auc   = val_auc
            best_epoch = epoch + 1
            ckpt = {
                "model": model.state_dict(),
                "epoch": epoch,
                "val_auc": best_auc,
            }
            torch.save(ckpt, CKPT_DIR / "best.pth")
            log(f"  => Best val AUC: {best_auc:.4f}  (epoch {best_epoch})")

        state["progress"].update({
            "current_epoch": epoch + 1,
            "last_loss": round(tr["loss"], 4),
            "last_val_metric": round(val_auc, 4) if val_auc == val_auc else None,
        })
        state["progress"]["val_metric_history"].append(
            round(val_auc, 4) if val_auc == val_auc else None
        )
        if best_auc > 0:
            state["checkpoint"]["best_path"] = str(CKPT_DIR / "best.pth")
        write_state(state)

    state["status"] = "done"
    write_state(state)
    log(f"Training complete. Best val AUC = {best_auc:.4f} at epoch {best_epoch}.")


if __name__ == "__main__":
    train()
