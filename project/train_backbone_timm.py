"""Generic timm backbone training for BMVC §5.4 universality study.

Supports any timm model with a .head classifier (ConvNeXt, Swin, ViT, etc.).
Outputs val/test logits so run_qcts_backbone.py can fit QCTS.

State file: D:/YJ-Agent/log/experiment_state.json

Usage:
    /loop /run-experiment project/train_backbone_timm.py project/configs/convnext_tiny.yaml
    /loop /run-experiment project/train_backbone_timm.py project/configs/swin_tiny.yaml

Dry-run:
    python project/train_backbone_timm.py --config project/configs/convnext_tiny.yaml --dry-run
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
    p.add_argument("--config", required=True)
    p.add_argument("--resume", default=None)
    p.add_argument("--seed", type=int, default=None)
    p.add_argument("--ckpt-dir", default=None)
    p.add_argument("--dry-run", action="store_true")
    return p.parse_args()


def write_state(state: dict):
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, indent=2), encoding="utf-8")


def build_model(cfg) -> nn.Module:
    return timm.create_model(
        cfg.backbone.name,
        pretrained=cfg.backbone.pretrained,
        num_classes=cfg.backbone.num_classes,
        drop_rate=cfg.backbone.get("drop_rate", 0.0),
        drop_path_rate=cfg.backbone.get("drop_path_rate", 0.0),
    )


def build_sampler(dataset: ISICImageDataset) -> WeightedRandomSampler:
    targets = dataset.df["target"].values
    w_pos = float(dataset.class_weights[1])
    weights = np.where(targets == 1, w_pos, 1.0)
    return WeightedRandomSampler(
        weights=torch.from_numpy(weights).float(),
        num_samples=len(weights),
        replacement=True,
    )


def cosine_factor(epoch: int, total: int, warmup: int) -> float:
    if epoch < warmup:
        return (epoch + 1) / max(warmup, 1)
    progress = (epoch - warmup) / max(total - warmup, 1)
    return 0.5 * (1.0 + np.cos(np.pi * progress))


@torch.no_grad()
def evaluate(model, loader, device, cfg, collect_logits: bool = False):
    model.eval()
    total_loss = total_acc = 0.0
    n_batches = 0
    all_probs, all_targets, all_logits, all_ids = [], [], [], []
    for batch in tqdm(loader, desc="eval", leave=False):
        x = batch["image"].to(device, non_blocking=True)
        y = batch["target"].to(device, non_blocking=True)
        with torch.amp.autocast("cuda", enabled=cfg.train.amp):
            logits = model(x)
            loss = F.cross_entropy(logits, y, label_smoothing=cfg.train.label_smoothing)
        probs = torch.softmax(logits.float(), dim=-1)[:, 1]
        total_loss += loss.item()
        total_acc += (logits.argmax(-1) == y).float().mean().item()
        n_batches += 1
        all_probs.extend(probs.cpu().numpy())
        all_targets.extend(y.cpu().numpy())
        if collect_logits:
            all_logits.append(logits.float().cpu().numpy())
            all_ids.extend(batch["isic_id"])
    out = {
        "loss": total_loss / max(n_batches, 1),
        "acc":  total_acc / max(n_batches, 1),
        "auc":  float(roc_auc_score(all_targets, all_probs))
                if len(set(all_targets)) > 1 else float("nan"),
    }
    if collect_logits:
        out["logits"] = np.concatenate(all_logits, axis=0)
        out["targets"] = np.array(all_targets)
        out["isic_ids"] = np.array(all_ids)
    return out


def train_one_epoch(model, loader, optimizer, scaler, device, cfg, epoch):
    model.train()
    total_loss = total_acc = 0.0
    n_batches = 0
    for batch in tqdm(loader, desc=f"train ep {epoch+1}", leave=False):
        x = batch["image"].to(device, non_blocking=True)
        y = batch["target"].to(device, non_blocking=True)
        optimizer.zero_grad()
        with torch.amp.autocast("cuda", enabled=cfg.train.amp):
            logits = model(x)
            loss = F.cross_entropy(logits, y, label_smoothing=cfg.train.label_smoothing)
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
        total_acc += (logits.argmax(-1) == y).float().mean().item()
        n_batches += 1
    return {"loss": total_loss / max(n_batches, 1), "acc": total_acc / max(n_batches, 1)}


def main():
    args = parse_args()
    cfg = OmegaConf.load(args.config)
    if args.seed is not None:
        cfg.train.seed = args.seed
    if args.ckpt_dir is not None:
        cfg.output.checkpoint_dir = args.ckpt_dir

    torch.manual_seed(cfg.train.seed)
    np.random.seed(cfg.train.seed)

    device = torch.device("cuda" if cfg.device.cuda and torch.cuda.is_available() else "cpu")
    bb_name = cfg.backbone.name
    safe_name = bb_name.replace("/", "_")
    print(f"[train_backbone_timm] backbone={bb_name}  device={device}  seed={cfg.train.seed}")

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
    print(f"{bb_name} params: {n_params/1e6:.2f}M  pretrained={cfg.backbone.pretrained}")

    lr_head = cfg.train.lr
    lr_backbone = cfg.train.get("lr_backbone", cfg.train.lr * 0.1)
    # timm standardises classifier as model.head for ViT/ConvNeXt/Swin
    try:
        head_params = list(model.head.parameters())
    except AttributeError:
        head_params = list(model.get_classifier().parameters())
    head_ids = {id(p) for p in head_params}
    backbone_params = [p for p in model.parameters() if id(p) not in head_ids]
    optimizer = torch.optim.AdamW([
        {"params": backbone_params, "lr": lr_backbone, "initial_lr": lr_backbone},
        {"params": head_params,    "lr": lr_head,     "initial_lr": lr_head},
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
        print(f"Resumed from epoch {start_epoch}, best_metric={best_metric:.4f}")

    ckpt_dir = Path(cfg.output.checkpoint_dir)
    logits_dir = Path(cfg.output.logits_dir)
    ckpt_dir.mkdir(parents=True, exist_ok=True)
    logits_dir.mkdir(parents=True, exist_ok=True)

    if args.dry_run:
        print("[dry-run] one batch forward+backward...")
        model.train()
        batch = next(iter(train_loader))
        x = batch["image"].to(device); y = batch["target"].to(device)
        with torch.amp.autocast("cuda", enabled=cfg.train.amp and device.type == "cuda"):
            logits = model(x)
            loss = F.cross_entropy(logits, y)
        print(f"[dry-run] loss={loss.item():.4f}  logits.shape={tuple(logits.shape)}")
        if cfg.train.amp and device.type == "cuda":
            scaler.scale(loss).backward()
        else:
            loss.backward()
        print("[dry-run] OK")
        return

    wandb.init(
        project=cfg.wandb.project,
        entity=cfg.wandb.entity,
        mode=cfg.wandb.get("mode", "offline"),
        config=OmegaConf.to_container(cfg, resolve=True),
        name=cfg.wandb.get("run_name", safe_name),
    )

    state = {
        "status": "running",
        "experiment": {"script": "train_backbone_timm.py", "config": args.config,
                       "backbone": bb_name},
        "process": {"pid": os.getpid(), "is_alive": True},
        "progress": {
            "current_epoch": start_epoch, "total_epochs": cfg.train.epochs,
            "last_loss": None, "last_val_metric": None,
            "val_metric_history": [],
        },
        "checkpoint": {"save_dir": str(ckpt_dir), "last_path": args.resume, "best_path": None},
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
        vl = evaluate(model, val_loader, device, cfg)
        elapsed = time.time() - t0
        print(
            f"ep {epoch+1}/{cfg.train.epochs} | "
            f"lr={lr_now:.2e} tr_loss={tr['loss']:.4f} | "
            f"val_loss={vl['loss']:.4f} val_auc={vl['auc']:.4f} | "
            f"{elapsed:.0f}s"
        )

        wandb.log({
            "epoch": epoch + 1, "lr": lr_now,
            "train/loss": tr["loss"], "train/acc": tr["acc"],
            "val/loss": vl["loss"], "val/acc": vl["acc"], "val/auc": vl["auc"],
        })

        ckpt_data = {
            "epoch": epoch, "model": model.state_dict(),
            "optimizer": optimizer.state_dict(),
            "scaler": scaler.state_dict() if cfg.train.amp else None,
            "best_metric": best_metric, "cfg": OmegaConf.to_container(cfg, resolve=True),
        }
        last_path = ckpt_dir / f"last_{safe_name}.pth"
        torch.save(ckpt_data, last_path)

        metric_key = cfg.output.get("best_metric", "auc")
        val_metric = vl.get(metric_key, vl["acc"])
        if not np.isnan(val_metric) and val_metric > best_metric:
            best_metric = val_metric
            best_path = ckpt_dir / f"best_{safe_name}.pth"
            torch.save(ckpt_data, best_path)
            print(f"  => best val {metric_key}={best_metric:.4f}")

        state["progress"].update({
            "current_epoch": epoch + 1, "total_epochs": cfg.train.epochs,
            "last_loss": round(tr["loss"], 4),
            "last_val_metric": round(float(val_metric), 4) if not np.isnan(val_metric) else None,
        })
        state["progress"]["val_metric_history"].append(
            round(float(val_metric), 4) if not np.isnan(val_metric) else None
        )
        state["checkpoint"]["last_path"] = str(last_path)
        if best_path is not None:
            state["checkpoint"]["best_path"] = str(best_path)
        write_state(state)

    if best_path is not None:
        ckpt = torch.load(best_path, map_location=device, weights_only=False)
        model.load_state_dict(ckpt["model"])
        print(f"[export] loaded best ckpt (val {cfg.output.best_metric}={best_metric:.4f})")

    print("[export] running val + test logits...")
    val_out = evaluate(model, val_loader, device, cfg, collect_logits=True)
    test_out = evaluate(model, test_loader, device, cfg, collect_logits=True)
    np.save(logits_dir / "val_logits.npy", val_out["logits"])
    np.save(logits_dir / "val_targets.npy", val_out["targets"])
    np.save(logits_dir / "val_ids.npy", val_out["isic_ids"])
    np.save(logits_dir / "test_logits.npy", test_out["logits"])
    np.save(logits_dir / "test_targets.npy", test_out["targets"])
    np.save(logits_dir / "test_ids.npy", test_out["isic_ids"])
    print(f"[export] val_auc={val_out['auc']:.4f}  test_auc={test_out['auc']:.4f}")
    print(f"[export] saved to {logits_dir}")

    state["status"] = "done"
    state["progress"]["last_val_metric"] = round(float(best_metric), 4)
    write_state(state)
    wandb.finish()
    print("Training complete.")


if __name__ == "__main__":
    main()
