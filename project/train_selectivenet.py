"""SelectiveNet 훈련 스크립트 (R6 baseline).

SelectiveNet (Geifman & El-Yaniv, ICML 2019):
  - f(x): classifier head (logits over K classes)
  - g(x): selection head (scalar in [0,1] — "select = predict")
  - h(x): auxiliary classifier head (prevents g from always abstaining)
  - Selective loss:
      L_sel  = alpha * selective_risk(f, g) + (1-alpha) * CE(h(x), y)
      selective_risk = sum_i L(f(x_i)) * g(x_i) / sum_i g(x_i)
    + lambda * Psi(coverage_hat, c)
    where Psi(a) = max(0, a)^2, coverage_hat = mean(g)
  - Official hyperparams (Geifman & El-Yaniv 2019 paper + official GitHub):
      alpha = 0.5  (balance classifier vs auxiliary)
      lambda = 32  (coverage penalty weight)
      coverage targets c ∈ {0.70, 0.75, 0.80, 0.85, 0.90, 0.95}
    See: github.com/geifmany/selectivenet (official implementation)

Architecture:
  Backbone = frozen QVIBEncoder (same as stdvib) + frozen QADClassifier (f head)
  New trainable heads: g_head (selection), h_head (auxiliary classifier)
  Input to g/h: QVIBEncoder latent mu (latent_dim=64)

서비스: ICLR→ACCV C2 lever (query-for-retake vs SOTA selective-prediction, R6)
디자인: 공식 SelectiveNet 손실 그대로, backbone freezing = 효율적 접근 (head-only ~5min)

红线:
  ① SelectiveNet 공식 초파라미터 그대로 (lambda=32, alpha=0.5)
  ② 복현 편차 금지
  ③ 학습 후 checkpoints/selectivenet_c{cov}/best.pth 저장
  ④ 불시동 — 주선 Start-Process 기다림

Usage:
  # Train for one coverage target c=0.80:
  python project/train_selectivenet.py --coverage 0.80

  # Train all 6 coverage targets (run in sequence):
  python project/train_selectivenet.py --coverage all

  # Smoke test (CPU, 2 steps, no save):
  python project/train_selectivenet.py --coverage 0.80 --smoke

Windows:
  DataLoader: multiprocessing_context='spawn', pin_memory=False
  Path: pathlib.Path
  OMP: os.environ OMP_NUM_THREADS=1

Output:
  D:/YJ-Agent/checkpoints/selectivenet_c{cov}/best.pth  (per coverage target)
  D:/YJ-Agent/project/results/selectivenet_train_summary.json
"""

import argparse
import json
import os
import sys
from pathlib import Path

os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")
os.environ.setdefault("OMP_NUM_THREADS", "1")

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
from sklearn.metrics import roc_auc_score
from torch.utils.data import DataLoader, WeightedRandomSampler
from tqdm import tqdm

ROOT = Path("D:/YJ-Agent/project")
DATA_ROOT = Path("D:/YJ-Agent/data")
CKPT_ROOT = Path("D:/YJ-Agent/checkpoints")

sys.path.insert(0, str(ROOT))
from models.q_vib_encoder import QVIBEncoder
from models.qad_classifier import QADClassifier
from data.qad_dataset import QADDataset, SCORE_COLS

# ── Official SelectiveNet hyperparameters (Geifman & El-Yaniv 2019, ICML)
# Source: https://github.com/geifmany/selectivenet (official repo)
ALPHA = 0.5        # balance between selective risk and auxiliary CE
LAMBDA = 32        # coverage constraint penalty weight
COVERAGE_TARGETS = [0.70, 0.75, 0.80, 0.85, 0.90, 0.95]

# Training schedule
TRAIN_EPOCHS = 50      # head-only fine-tune: 50 epochs sufficient (frozen backbone)
LR = 1e-3              # head-only lr (standard for linear probe / head fine-tune)
BATCH_SIZE = 512
WEIGHT_DECAY = 1e-4
LATENT_DIM = 64        # QVIBEncoder latent_dim (from configs/qad.yaml)
HIDDEN_DIM = 128       # g/h head hidden dim
NUM_CLASSES = 2

DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")


# ── SelectiveNet heads (g + h), trained on top of frozen encoder ──────────────

class SelectionHead(nn.Module):
    """g(x): selection function -> scalar in [0, 1]."""
    def __init__(self, input_dim: int = LATENT_DIM, hidden_dim: int = HIDDEN_DIM):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(input_dim, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, 1),
            nn.Sigmoid(),
        )

    def forward(self, z: torch.Tensor) -> torch.Tensor:
        return self.net(z).squeeze(-1)  # (B,)


class AuxClassifierHead(nn.Module):
    """h(x): auxiliary classifier -> same output space as f."""
    def __init__(self, input_dim: int = LATENT_DIM, hidden_dim: int = HIDDEN_DIM, num_classes: int = NUM_CLASSES):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(input_dim, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, num_classes),
        )

    def forward(self, z: torch.Tensor) -> torch.Tensor:
        return self.net(z)  # (B, K)


# ── SelectiveNet loss (official formulation) ──────────────────────────────────

def selective_loss(
    logits_f: torch.Tensor,   # (B, K) from frozen f
    logits_h: torch.Tensor,   # (B, K) from trainable h
    g: torch.Tensor,           # (B,) selection scores
    targets: torch.Tensor,     # (B,) int labels
    alpha: float = ALPHA,
    lambda_: float = LAMBDA,
    coverage_target: float = 0.80,
) -> tuple[torch.Tensor, dict]:
    """
    Selective loss from Geifman & El-Yaniv 2019, eq (1):
      L = alpha * selective_risk + (1-alpha) * CE_aux
        + lambda * Psi(coverage_hat - c)^2
    Psi(a) = max(0, a)^2
    """
    B = logits_f.shape[0]

    # Classification loss on each sample (cross-entropy)
    ce_per_sample = F.cross_entropy(logits_f, targets, reduction="none")  # (B,)

    # Selective risk: empirical coverage-weighted CE
    coverage_hat = g.mean()
    # Normalise by coverage (with eps to avoid div-by-zero)
    selective_risk = (ce_per_sample * g).sum() / (g.sum() + 1e-8)

    # Auxiliary CE (all samples, no selection weighting)
    ce_aux = F.cross_entropy(logits_h, targets)

    # Coverage constraint penalty: Psi(a) = max(0, a)^2
    psi = torch.clamp(coverage_hat - coverage_target, min=0.0) ** 2

    loss = alpha * selective_risk + (1.0 - alpha) * ce_aux + lambda_ * psi

    info = {
        "loss": loss.item(),
        "selective_risk": selective_risk.item(),
        "ce_aux": ce_aux.item(),
        "coverage_hat": coverage_hat.item(),
        "psi": psi.item(),
    }
    return loss, info


# ── Dataset / DataLoader ──────────────────────────────────────────────────────

def build_loaders(smoke: bool = False):
    common_kwargs = dict(
        quality_csv=DATA_ROOT / "quality_labels_all.csv",
        metadata_csv=DATA_ROOT / "raw/isic2020/train-metadata.csv",
        abcd_cache_csv=DATA_ROOT / "abcd_cache.csv",
        efnet_features_npy=DATA_ROOT / "efficientnet_features.npy",
        efnet_index_csv=DATA_ROOT / "efficientnet_index.csv",
        split_csv=DATA_ROOT / "isic_split.csv",
    )
    train_ds = QADDataset(**common_kwargs, split="train")
    val_ds   = QADDataset(**common_kwargs, split="val")

    if smoke:
        from torch.utils.data import Subset
        train_ds = Subset(train_ds, list(range(min(64, len(train_ds)))))
        val_ds   = Subset(val_ds,   list(range(min(32, len(val_ds)))))

    # Weighted sampler for class imbalance
    if hasattr(train_ds, 'class_weights'):
        cw = train_ds.class_weights
    elif hasattr(getattr(train_ds, 'dataset', train_ds), 'class_weights'):
        cw = train_ds.dataset.class_weights
    else:
        cw = torch.ones(NUM_CLASSES)

    targets_list = []
    ds_for_targets = train_ds.dataset if hasattr(train_ds, 'dataset') else train_ds
    indices = train_ds.indices if hasattr(train_ds, 'indices') else range(len(train_ds))
    for i in indices:
        targets_list.append(ds_for_targets.df.iloc[i]["target"])
    sample_weights = torch.tensor([float(cw[int(t)]) for t in targets_list])
    sampler = WeightedRandomSampler(sample_weights, num_samples=len(sample_weights), replacement=True)

    train_loader = DataLoader(
        train_ds, batch_size=BATCH_SIZE, sampler=sampler,
        num_workers=2, pin_memory=False,
        multiprocessing_context="spawn",
    )
    val_loader = DataLoader(
        val_ds, batch_size=BATCH_SIZE, shuffle=False,
        num_workers=2, pin_memory=False,
        multiprocessing_context="spawn",
    )
    return train_loader, val_loader


# ── Load frozen backbone ──────────────────────────────────────────────────────

def load_frozen_backbone():
    """Load stdvib encoder + classifier (f head), freeze all params."""
    ckpt_path = CKPT_ROOT / "stdvib/best_qad.pth"
    ckpt = torch.load(ckpt_path, map_location=DEVICE, weights_only=False)
    encoder = QVIBEncoder(
        abcd_dim=4, q_dim=5, d_model=128, n_heads=4,
        latent_dim=LATENT_DIM, efnet_dim=1280,
    ).to(DEVICE)
    classifier = QADClassifier(
        latent_dim=LATENT_DIM, hidden_dim=128, num_classes=NUM_CLASSES,
    ).to(DEVICE)
    encoder.load_state_dict(ckpt["encoder"])
    classifier.load_state_dict(ckpt["classifier"])
    # Disable tokenizer (same as stdvib baseline in run_experiments.py)
    encoder.tokenizer.forward = lambda q: torch.zeros(q.shape[0], device=DEVICE)

    for p in encoder.parameters():
        p.requires_grad_(False)
    for p in classifier.parameters():
        p.requires_grad_(False)
    encoder.eval()
    classifier.eval()
    return encoder, classifier


# ── Training loop ─────────────────────────────────────────────────────────────

def train_one_coverage(
    coverage_target: float,
    smoke: bool = False,
) -> dict:
    print(f"\n{'='*60}")
    print(f"SelectiveNet: coverage_target={coverage_target:.2f}  device={DEVICE}")
    print(f"  alpha={ALPHA}  lambda={LAMBDA}  epochs={1 if smoke else TRAIN_EPOCHS}")

    ckpt_dir = CKPT_ROOT / f"selectivenet_c{int(coverage_target*100):02d}"
    ckpt_dir.mkdir(parents=True, exist_ok=True)

    encoder, f_head = load_frozen_backbone()
    g_head = SelectionHead(LATENT_DIM, HIDDEN_DIM).to(DEVICE)
    h_head = AuxClassifierHead(LATENT_DIM, HIDDEN_DIM, NUM_CLASSES).to(DEVICE)

    optimizer = torch.optim.Adam(
        list(g_head.parameters()) + list(h_head.parameters()),
        lr=LR, weight_decay=WEIGHT_DECAY,
    )

    train_loader, val_loader = build_loaders(smoke=smoke)
    n_epochs = 1 if smoke else TRAIN_EPOCHS

    best_val_risk = float("inf")
    best_state = None
    history = []

    for epoch in range(n_epochs):
        g_head.train(); h_head.train()
        running_info = {k: 0.0 for k in ["loss","selective_risk","ce_aux","coverage_hat","psi"]}
        n_batches = 0

        for batch in tqdm(train_loader, desc=f"epoch {epoch+1}/{n_epochs}", leave=False):
            abcd    = batch["abcd"].to(DEVICE)
            q       = batch["q"].to(DEVICE)
            ef      = batch["efnet_feat"].to(DEVICE)
            targets = batch["target"].to(DEVICE)

            with torch.no_grad():
                mu, lsq = encoder(abcd, q, efnet_feat=ef)
                logits_f = f_head(mu)

            g = g_head(mu.detach())
            logits_h = h_head(mu.detach())

            loss, info = selective_loss(
                logits_f, logits_h, g, targets,
                alpha=ALPHA, lambda_=LAMBDA,
                coverage_target=coverage_target,
            )

            optimizer.zero_grad()
            loss.backward()
            optimizer.step()

            for k in running_info:
                running_info[k] += info[k]
            n_batches += 1

        if smoke:
            print(f"  Smoke step done — loss={running_info['loss']/n_batches:.4f}")
            return {"coverage_target": coverage_target, "smoke": True}

        train_summary = {k: v / n_batches for k, v in running_info.items()}

        # Validation
        g_head.eval(); h_head.eval()
        val_risks, val_coverages = [], []
        all_probs, all_targets = [], []

        with torch.no_grad():
            for batch in val_loader:
                abcd    = batch["abcd"].to(DEVICE)
                q       = batch["q"].to(DEVICE)
                ef      = batch["efnet_feat"].to(DEVICE)
                targets_b = batch["target"].to(DEVICE)

                mu, _ = encoder(abcd, q, efnet_feat=ef)
                logits_f = f_head(mu)
                g = g_head(mu)

                # Selective risk on val
                ce_per = F.cross_entropy(logits_f, targets_b, reduction="none")
                cov = g.mean().item()
                s_risk = (ce_per * g).sum().item() / (g.sum().item() + 1e-8)
                val_risks.append(s_risk)
                val_coverages.append(cov)

                probs = F.softmax(logits_f, -1)[:, 1]
                all_probs.extend(probs.cpu().tolist())
                all_targets.extend(targets_b.cpu().tolist())

        val_risk = float(np.mean(val_risks))
        val_cov  = float(np.mean(val_coverages))
        try:
            val_auc = roc_auc_score(all_targets, all_probs)
        except Exception:
            val_auc = float("nan")

        print(f"  ep {epoch+1:3d}  train_loss={train_summary['loss']:.4f}  "
              f"val_risk={val_risk:.4f}  val_cov={val_cov:.3f}  val_auc={val_auc:.4f}")

        if val_risk < best_val_risk:
            best_val_risk = val_risk
            best_state = {
                "epoch": epoch + 1,
                "coverage_target": coverage_target,
                "val_risk": val_risk,
                "val_coverage": val_cov,
                "val_auc": val_auc,
                "g_head": {k: v.cpu() for k, v in g_head.state_dict().items()},
                "h_head": {k: v.cpu() for k, v in h_head.state_dict().items()},
                "alpha": ALPHA,
                "lambda": LAMBDA,
            }

        history.append({
            "epoch": epoch + 1,
            **train_summary,
            "val_risk": val_risk,
            "val_coverage": val_cov,
            "val_auc": val_auc,
        })

    # Save best
    torch.save(best_state, ckpt_dir / "best.pth")
    print(f"  Saved best ckpt -> {ckpt_dir}/best.pth  (ep {best_state['epoch']}, val_risk={best_val_risk:.4f})")

    result = {
        "coverage_target": coverage_target,
        "best_epoch": best_state["epoch"],
        "best_val_risk": best_val_risk,
        "best_val_coverage": best_state["val_coverage"],
        "best_val_auc": best_state["val_auc"],
        "ckpt": str(ckpt_dir / "best.pth"),
    }
    return result


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--coverage", default="0.80",
                    help="Coverage target, e.g. 0.80, or 'all' for all 6 targets")
    ap.add_argument("--smoke", action="store_true",
                    help="Dry-run: 1 batch per epoch, CPU, no save")
    ap.add_argument("--cpu", action="store_true", help="Force CPU (smoke test)")
    args = ap.parse_args()

    if args.cpu or args.smoke:
        global DEVICE
        DEVICE = torch.device("cpu")

    if args.coverage == "all":
        targets = COVERAGE_TARGETS
    else:
        targets = [float(args.coverage)]

    all_results = []
    for c in targets:
        r = train_one_coverage(c, smoke=args.smoke)
        all_results.append(r)

    if not args.smoke:
        out = ROOT / "results/selectivenet_train_summary.json"
        with open(out, "w") as f:
            json.dump(all_results, f, indent=2)
        print(f"\nTrain summary saved -> {out}")

    print("\n=== Done ===")
    for r in all_results:
        if args.smoke:
            print(f"  c={r['coverage_target']:.2f}: smoke pass")
        else:
            print(f"  c={r['coverage_target']:.2f}: best_risk={r['best_val_risk']:.4f}  "
                  f"ep={r['best_epoch']}  ckpt={r['ckpt']}")


if __name__ == "__main__":
    main()
