import torch, sys
print(f"PyTorch: {torch.__version__}")
print(f"CUDA available: {torch.cuda.is_available()}")
if torch.cuda.is_available():
    print(f"Device: {torch.cuda.get_device_name(0)}")
    print(f"CUDA version: {torch.version.cuda}")

"""VisiScore-Net training script.

Usage:
    python train_visiscore.py --config configs/visiscore.yaml
    python train_visiscore.py --config configs/visiscore.yaml --resume D:/YJ-Agent/checkpoints/last_visiscore.pth
"""
import argparse
from pathlib import Path

import torch
import torch.cuda.amp as amp
from omegaconf import OmegaConf
from torch.utils.data import DataLoader, random_split
from tqdm import tqdm

import numpy as np
from data.dataset import SkinPairedDataset
from models.losses import VisiScoreLoss
from models.visiscore import VisiScoreNet


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="configs/visiscore.yaml")
    parser.add_argument("--resume", default=None, help="Path to checkpoint for resuming training")
    return parser.parse_args()


def train():
    args = parse_args()
    cfg = OmegaConf.load(args.config)
    torch.manual_seed(cfg.train.seed)

    try:
        import wandb
        wandb.init(
            project=cfg.wandb.project,
            entity=cfg.wandb.entity or None,
            mode=cfg.wandb.mode,
            config=OmegaConf.to_container(cfg, resolve=True),
        )
    except Exception as e:
        print(f"[warn] wandb init failed: {e}")

    cache_dir = getattr(cfg.data, 'cache_dir', None)
    dataset = SkinPairedDataset(cfg.data.labels_csv, img_size=224, cache_dir=cache_dir)

    # 按原图 ID 分组，避免同一张图的不同退化版本同时出现在 train 和 val
    import pandas as pd, numpy as np
    df = pd.read_csv(cfg.data.labels_csv)
    orig_ids = df["original_path"].unique()
    rng = np.random.default_rng(cfg.train.seed)
    rng.shuffle(orig_ids)
    n_val_imgs = max(1, int(len(orig_ids) * 0.1))
    val_orig = set(orig_ids[:n_val_imgs])
    train_idx = [i for i, p in enumerate(df["original_path"]) if p not in val_orig]
    val_idx   = [i for i, p in enumerate(df["original_path"]) if p in val_orig]
    from torch.utils.data import Subset
    train_ds = Subset(dataset, train_idx)
    val_ds   = Subset(dataset, val_idx)
    train_loader = DataLoader(
        train_ds, batch_size=cfg.train.batch_size, shuffle=True,
        num_workers=cfg.data.num_workers, pin_memory=cfg.data.pin_memory,
        multiprocessing_context='spawn' if cfg.data.num_workers > 0 else None,
        persistent_workers=cfg.data.num_workers > 0,
    )
    val_loader = DataLoader(
        val_ds, batch_size=cfg.train.batch_size, shuffle=False,
        num_workers=cfg.data.num_workers, pin_memory=cfg.data.pin_memory,
        multiprocessing_context='spawn' if cfg.data.num_workers > 0 else None,
        persistent_workers=cfg.data.num_workers > 0,
    )

    device = torch.device("cuda" if cfg.device.cuda and torch.cuda.is_available() else "cpu")
    model = VisiScoreNet(
        backbone=cfg.model.backbone,
        pretrained=cfg.model.pretrained,
        num_dims=cfg.model.num_quality_dims,
    ).to(device)
    criterion = VisiScoreLoss().to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=cfg.train.lr, weight_decay=cfg.train.weight_decay)
    scaler = torch.amp.GradScaler('cuda', enabled=cfg.train.amp)

    ckpt_dir = Path(cfg.output.checkpoint_dir)
    ckpt_dir.mkdir(parents=True, exist_ok=True)
    start_epoch = 0
    best_val_loss = float("inf")
    best_plcc = -1.0

    if args.resume:
        ckpt = torch.load(args.resume, map_location=device)
        model.load_state_dict(ckpt["model"])
        optimizer.load_state_dict(ckpt["optimizer"])
        scaler.load_state_dict(ckpt["scaler"])
        start_epoch = ckpt["epoch"] + 1
        best_val_loss = ckpt.get("best_val_loss", best_val_loss)
        best_plcc = ckpt.get("best_plcc", best_plcc)
        print(f"[resume] from epoch {start_epoch}, best_val_loss={best_val_loss:.4f}")

    for epoch in range(start_epoch, cfg.train.epochs):
        model.train()
        total_loss = 0.0
        for deg, clean, labels in tqdm(train_loader, desc=f"Epoch [{epoch+1}/{cfg.train.epochs}]"):
            deg, clean, labels = deg.to(device), clean.to(device), labels.to(device)
            with torch.amp.autocast('cuda', enabled=cfg.train.amp):
                pred_deg = model(deg)
                pred_clean = model(clean)
                loss = criterion(pred_deg, pred_clean, labels)
            optimizer.zero_grad()
            scaler.scale(loss).backward()
            scaler.step(optimizer)
            scaler.update()
            total_loss += loss.item()

        avg_train = total_loss / len(train_loader)
        print(f"Epoch [{epoch+1}/{cfg.train.epochs}] loss={avg_train:.4f}")

        model.eval()
        val_loss = 0.0
        all_preds, all_targets = [], []
        with torch.no_grad():
            for deg, clean, labels in val_loader:
                deg, clean, labels = deg.to(device), clean.to(device), labels.to(device)
                with torch.amp.autocast('cuda', enabled=cfg.train.amp):
                    pred_deg = model(deg)
                    pred_clean = model(clean)
                    loss = criterion(pred_deg, pred_clean, labels)
                val_loss += loss.item()
                all_preds.append(pred_deg.cpu().float())
                all_targets.append(labels.cpu().float())
        avg_val = val_loss / len(val_loader)
        preds_np = torch.cat(all_preds).numpy()
        tgts_np  = torch.cat(all_targets).numpy()
        dim_names = ["sharpness", "brightness", "completeness", "color_temp", "contrast"]
        def _plcc(x, y):
            x, y = x - x.mean(), y - y.mean()
            denom = (np.sqrt((x**2).sum()) * np.sqrt((y**2).sum()))
            return float((x * y).sum() / (denom + 1e-8))

        def _srcc(x, y):
            rx = np.argsort(np.argsort(x)).astype(float)
            ry = np.argsort(np.argsort(y)).astype(float)
            return _plcc(rx, ry)

        plccs, srccs = [], []
        for d in range(5):
            plccs.append(_plcc(preds_np[:, d], tgts_np[:, d]))
            srccs.append(_srcc(preds_np[:, d], tgts_np[:, d]))
        avg_plcc = float(np.mean(plccs)); avg_srcc = float(np.mean(srccs))
        print(f"Epoch [{epoch+1}/{cfg.train.epochs}] val_loss={avg_val:.4f} | PLCC={avg_plcc:.3f} SRCC={avg_srcc:.3f}")
        for d, name in enumerate(dim_names):
            print(f"  {name}: PLCC={plccs[d]:.3f} SRCC={srccs[d]:.3f}")

        state = {
            "epoch": epoch,
            "model": model.state_dict(),
            "optimizer": optimizer.state_dict(),
            "scaler": scaler.state_dict(),
            "best_val_loss": best_val_loss,
            "best_plcc": best_plcc,
        }
        last_path = ckpt_dir / "last_visiscore.pth"
        torch.save(state, last_path)
        print(f"Saved checkpoint last.pth → {last_path}")

        if avg_plcc > best_plcc:
            best_plcc = avg_plcc
            best_val_loss = avg_val
            best_path = ckpt_dir / "best_visiscore.pth"
            torch.save(state, best_path)
            print(f"New best PLCC={best_plcc:.3f} val_loss={best_val_loss:.4f}, saved best.pth → {best_path}")

        try:
            import wandb
            wandb.log({"train_loss": avg_train, "val_loss": avg_val, "avg_plcc": avg_plcc, "avg_srcc": avg_srcc, "epoch": epoch + 1})
        except Exception:
            pass

    print("Training complete.")
    try:
        import wandb
        wandb.finish()
    except Exception:
        pass


if __name__ == "__main__":
    train()
