"""
Pilot training script for gdn2vessel (关 3 DRIVE pilot).

Usage:
    python src/train_pilot.py --model unet --data_root /path/to/DRIVE
    python src/train_pilot.py --model unet_gdn2 --data_root /path/to/DRIVE

CLI args:
    --model          'unet' | 'unet_gdn2'
    --data_root      path to DRIVE root (contains training/ and test/)
    --output_dir     where to save checkpoints + state.json
    --epochs         max epochs (default 100)
    --lr             learning rate (default 1e-3)
    --batch_size     (default 2)
    --patch_size     training patch size (default 512)
    --num_workers    DataLoader workers (default 0 on Windows; set 2 on HPC Linux)
    --use_memory     (flag) for unet_gdn2 — keep memory on (default True)
    --no_memory      degrade unet_gdn2 to pure CNN
    --backend        'naive' | 'chunk' (default 'naive')
    --patience       early-stop patience in epochs (default 20)
    --base_ch        U-Net base channels (default 32)
    --seed           random seed (default 42)
    --smoke          if set, run 2 steps and exit (for CI smoke test)

Outputs (in output_dir/):
    state.json       live training state (written every epoch)
    best.pth         best checkpoint by val Dice

state.json schema:
    {
      "epoch": int,
      "train_loss": float,
      "val_dice": float,
      "best_dice": float,
      "status": "running" | "done" | "error"
    }

Windows compatibility:
  - multiprocessing_context='spawn' (DataLoader)
  - pin_memory=False
  - if __name__ == '__main__' guard
"""

from __future__ import annotations

import argparse
import json
import os
import random
import sys
import time
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
from torch.utils.data import DataLoader

# NOTE: src/ must be on sys.path when running as 'python src/train_pilot.py'
# from the project root. Alternatively: python -m src.train_pilot
_src_dir = Path(__file__).parent
if str(_src_dir) not in sys.path:
    sys.path.insert(0, str(_src_dir))


# --------------------------------------------------------------------------- #
#  Loss
# --------------------------------------------------------------------------- #

def dice_loss(pred_prob: torch.Tensor, target: torch.Tensor,
              mask: torch.Tensor, eps: float = 1e-6) -> torch.Tensor:
    """Soft Dice loss computed only inside FOV mask."""
    pred_flat = (pred_prob * mask).reshape(pred_prob.shape[0], -1)
    tgt_flat = (target * mask).reshape(target.shape[0], -1)
    intersection = (pred_flat * tgt_flat).sum(1)
    denom = pred_flat.sum(1) + tgt_flat.sum(1)
    dice = (2 * intersection + eps) / (denom + eps)
    return 1.0 - dice.mean()


def bce_loss(logits: torch.Tensor, target: torch.Tensor,
             mask: torch.Tensor) -> torch.Tensor:
    """Binary cross-entropy computed only inside FOV mask."""
    bce = nn.functional.binary_cross_entropy_with_logits(
        logits, target, reduction='none')
    # Zero out outside-FOV pixels and mean over FOV pixels
    n_valid = mask.sum().clamp(min=1)
    return (bce * mask).sum() / n_valid


def combined_loss(logits, target, mask, bce_weight=0.5, dice_weight=0.5):
    prob = torch.sigmoid(logits)
    l_bce = bce_loss(logits, target, mask)
    l_dice = dice_loss(prob, target, mask)
    return bce_weight * l_bce + dice_weight * l_dice


# --------------------------------------------------------------------------- #
#  Metrics (pure numpy, no scipy — avoids OMP Error #15 on Windows)
# --------------------------------------------------------------------------- #

def dice_coeff_np(pred_bin: np.ndarray, target: np.ndarray,
                  mask: np.ndarray, eps: float = 1e-6) -> float:
    """Dice coefficient computed inside FOV mask, pure numpy."""
    p = pred_bin[mask > 0]
    t = target[mask > 0]
    intersection = (p * t).sum()
    denom = p.sum() + t.sum()
    return float((2 * intersection + eps) / (denom + eps))


# --------------------------------------------------------------------------- #
#  Training / validation loops
# --------------------------------------------------------------------------- #

def train_epoch(model, loader, optimizer, device):
    model.train()
    total_loss = 0.0
    for batch in loader:
        img = batch['image'].to(device)
        gt = batch['gt'].to(device)
        fov = batch['fov'].to(device)

        optimizer.zero_grad()
        logits = model(img)
        loss = combined_loss(logits, gt, fov)
        loss.backward()
        optimizer.step()
        total_loss += loss.item()
    return total_loss / max(len(loader), 1)


@torch.no_grad()
def val_epoch(model, loader, device):
    model.eval()
    dice_scores = []
    for batch in loader:
        img = batch['image'].to(device)
        gt = batch['gt'].to(device)
        fov = batch['fov'].to(device)

        logits = model(img)
        prob = torch.sigmoid(logits)
        pred_bin = (prob > 0.5).float()

        # Compute Dice per sample (numpy)
        for b in range(img.shape[0]):
            d = dice_coeff_np(
                pred_bin[b, 0].cpu().numpy(),
                gt[b, 0].cpu().numpy(),
                fov[b, 0].cpu().numpy(),
            )
            dice_scores.append(d)

    return float(np.mean(dice_scores)) if dice_scores else 0.0


# --------------------------------------------------------------------------- #
#  Checkpoint + state.json
# --------------------------------------------------------------------------- #

def write_state(path: Path, epoch: int, train_loss: float,
                val_dice: float, best_dice: float, status: str):
    state = {
        'epoch': epoch,
        'train_loss': round(float(train_loss), 6),
        'val_dice': round(float(val_dice), 6),
        'best_dice': round(float(best_dice), 6),
        'status': status,
    }
    tmp = path.with_suffix('.tmp')
    with open(tmp, 'w') as f:
        json.dump(state, f, indent=2)
    tmp.replace(path)  # atomic rename


def save_ckpt(model, path: Path):
    torch.save(model.state_dict(), path)


# --------------------------------------------------------------------------- #
#  Main
# --------------------------------------------------------------------------- #

def build_model(args):
    if args.model == 'unet':
        from models.unet import UNet
        return UNet(in_ch=1, out_ch=1, base_ch=args.base_ch)
    elif args.model == 'unet_gdn2':
        from models.unet_gdn2 import UNetGDN2
        use_memory = not args.no_memory
        return UNetGDN2(
            in_ch=1,
            out_ch=1,
            base_ch=args.base_ch,
            use_memory=use_memory,
            backend=args.backend,
        )
    else:
        raise ValueError(f"Unknown model: {args.model!r}. Use 'unet' or 'unet_gdn2'.")


def parse_args():
    p = argparse.ArgumentParser(description='gdn2vessel pilot training')
    p.add_argument('--model', default='unet_gdn2',
                   choices=['unet', 'unet_gdn2'])
    p.add_argument('--data_root', required=True,
                   help='Path to DRIVE root directory')
    p.add_argument('--output_dir', default='outputs/pilot')
    p.add_argument('--epochs', type=int, default=100)
    p.add_argument('--lr', type=float, default=1e-3)
    # TODO: FR-UNet uses lr=1e-3 (Adam) — common DRIVE baseline.
    #       Verify against official FR-UNet config if needed.
    p.add_argument('--batch_size', type=int, default=2)
    p.add_argument('--patch_size', type=int, default=512)
    p.add_argument('--num_workers', type=int, default=0,
                   help='DataLoader workers. 0=safe on Windows (spawn issues). '
                        'Use 2-4 on HPC Linux.')
    p.add_argument('--no_memory', action='store_true',
                   help='Degrade unet_gdn2 to pure CNN (no GDN-2 module)')
    p.add_argument('--backend', default='naive', choices=['naive', 'chunk'])
    p.add_argument('--patience', type=int, default=20)
    p.add_argument('--base_ch', type=int, default=32)
    p.add_argument('--seed', type=int, default=42)
    p.add_argument('--smoke', action='store_true',
                   help='Run 2 mini-steps and exit (CI smoke test)')
    return p.parse_args()


def main():
    args = parse_args()

    # Reproducibility
    random.seed(args.seed)
    np.random.seed(args.seed)
    torch.manual_seed(args.seed)

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    state_path = output_dir / 'state.json'
    ckpt_path = output_dir / 'best.pth'

    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    print(f'[train_pilot] device={device}  model={args.model}  '
          f'backend={args.backend if args.model == "unet_gdn2" else "N/A"}')

    # Dataset
    from datasets.drive import DRIVEDataset
    train_ds = DRIVEDataset(
        data_root=args.data_root,
        split='train',
        patch_size=args.patch_size,
        augment=True,
    )
    val_ds = DRIVEDataset(
        data_root=args.data_root,
        split='val',
        patch_size=args.patch_size,
        augment=False,
    )

    # DataLoader — spawn + pin_memory=False for Windows compatibility
    loader_kwargs = dict(
        batch_size=args.batch_size,
        num_workers=args.num_workers,
        pin_memory=False,
    )
    if args.num_workers > 0:
        loader_kwargs['multiprocessing_context'] = 'spawn'

    train_loader = DataLoader(train_ds, shuffle=True, **loader_kwargs)
    val_loader = DataLoader(val_ds, shuffle=False, **loader_kwargs)

    # Model
    model = build_model(args).to(device)
    n_params = sum(p.numel() for p in model.parameters() if p.requires_grad)
    print(f'[train_pilot] model params = {n_params:,}')

    optimizer = torch.optim.Adam(model.parameters(), lr=args.lr)
    # LR scheduler: ReduceLROnPlateau on val Dice
    scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(
        optimizer, mode='max', factor=0.5, patience=10, min_lr=1e-6)

    best_dice = 0.0
    no_improve = 0

    write_state(state_path, 0, 0.0, 0.0, 0.0, 'running')

    for epoch in range(1, args.epochs + 1):
        t0 = time.time()
        train_loss = train_epoch(model, train_loader, optimizer, device)
        val_dice = val_epoch(model, val_loader, device)
        elapsed = time.time() - t0

        scheduler.step(val_dice)

        improved = val_dice > best_dice
        if improved:
            best_dice = val_dice
            save_ckpt(model, ckpt_path)
            no_improve = 0
        else:
            no_improve += 1

        write_state(state_path, epoch, train_loss, val_dice, best_dice, 'running')

        print(f'[epoch {epoch:03d}/{args.epochs}] '
              f'loss={train_loss:.4f}  val_dice={val_dice:.4f}  '
              f'best={best_dice:.4f}  {"*" if improved else ""}  '
              f'({elapsed:.1f}s)')

        # Smoke test: exit after 2 epochs
        if args.smoke and epoch >= 2:
            print('[smoke] 2-step smoke done — exiting.')
            write_state(state_path, epoch, train_loss, val_dice, best_dice, 'done')
            return

        # Early stopping
        if no_improve >= args.patience:
            print(f'[train_pilot] early stop at epoch {epoch} '
                  f'(no improvement for {args.patience} epochs)')
            break

    write_state(state_path, epoch, train_loss, val_dice, best_dice, 'done')
    print(f'[train_pilot] done. best val Dice = {best_dice:.4f}')


if __name__ == '__main__':
    main()
