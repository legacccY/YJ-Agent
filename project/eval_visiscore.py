"""VisiScore-Net evaluation script.

Compares VisiScore-Net against BRISQUE on the validation split.
Outputs per-dimension PLCC/SRCC and inference speed.

Usage:
    python eval_visiscore.py --config configs/visiscore.yaml --ckpt D:/YJ-Agent/checkpoints/best_visiscore.pth
    python eval_visiscore.py --config configs/visiscore.yaml --ckpt D:/YJ-Agent/checkpoints/best_visiscore.pth --n_samples 500
"""
import argparse
import time
from pathlib import Path

import numpy as np
import pandas as pd
import torch
from omegaconf import OmegaConf
from torch.utils.data import DataLoader, Subset
from tqdm import tqdm

from data.dataset import SkinPairedDataset
from models.visiscore import VisiScoreNet


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="configs/visiscore.yaml")
    parser.add_argument("--ckpt", default="D:/YJ-Agent/checkpoints/best_visiscore.pth")
    parser.add_argument("--n_samples", type=int, default=None, help="Limit val samples for quick eval")
    parser.add_argument("--out", default="results/eval_report_visiscore.md")
    return parser.parse_args()


def _plcc(x, y):
    x, y = x - x.mean(), y - y.mean()
    denom = np.sqrt((x ** 2).sum()) * np.sqrt((y ** 2).sum())
    return float((x * y).sum() / (denom + 1e-8))


def _srcc(x, y):
    rx = np.argsort(np.argsort(x)).astype(float)
    ry = np.argsort(np.argsort(y)).astype(float)
    return _plcc(rx, ry)


def brisque_score(img_tensor):
    """img_tensor: (3, H, W) float32 [0,1] → scalar BRISQUE (lower = better quality)."""
    from brisque import BRISQUE
    brisque_obj = BRISQUE()
    img_np = (img_tensor.permute(1, 2, 0).numpy() * 255).astype(np.uint8)
    try:
        score = brisque_obj.score(img_np)
        return float(score) if np.isfinite(score) else None
    except Exception:
        return None


def build_val_indices(cfg):
    df = pd.read_csv(cfg.data.labels_csv)
    orig_ids = df["original_path"].unique()
    rng = np.random.default_rng(42)
    rng.shuffle(orig_ids)
    n_val = max(1, int(len(orig_ids) * 0.1))
    val_orig = set(orig_ids[:n_val])
    val_idx = [i for i, p in enumerate(df["original_path"]) if p in val_orig]
    return val_idx


def eval_visiscore(model, val_loader, device, cfg):
    model.eval()
    all_preds, all_labels = [], []
    total_time = 0.0
    n_imgs = 0
    with torch.no_grad():
        for deg, clean, labels in tqdm(val_loader, desc="VisiScore eval"):
            deg = deg.to(device)
            t0 = time.perf_counter()
            with torch.amp.autocast("cuda", enabled=cfg.train.amp):
                pred = model(deg)
            torch.cuda.synchronize()
            total_time += time.perf_counter() - t0
            n_imgs += deg.shape[0]
            all_preds.append(pred.cpu().float())
            all_labels.append(labels.float())
    preds = torch.cat(all_preds).numpy()
    labels = torch.cat(all_labels).numpy()
    return preds, labels, total_time / n_imgs * 1000  # ms per image


def eval_brisque(val_dataset, val_indices, n_samples):
    """Compute BRISQUE on degraded images; use sharpness label as proxy ground truth."""
    from brisque import BRISQUE
    brisque_obj = BRISQUE()
    indices = val_indices[:n_samples] if n_samples else val_indices

    brisque_scores, sharpness_labels = [], []
    for idx in tqdm(indices, desc="BRISQUE eval"):
        deg, _, labels = val_dataset[idx]
        img_np = (deg.permute(1, 2, 0).numpy() * 255).astype(np.uint8)
        try:
            s = brisque_obj.score(img_np)
            if np.isfinite(s):
                brisque_scores.append(float(s))
                sharpness_labels.append(float(labels[0]))
        except Exception:
            pass

    return np.array(brisque_scores), np.array(sharpness_labels)


def write_report(out_path, dim_names, visi_plccs, visi_srccs, avg_ms,
                 brisque_plcc, brisque_srcc, n_val):
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# VisiScore-Net 评估报告",
        "",
        f"- 验证集样本数：{n_val}",
        f"- VisiScore 推理速度：{avg_ms:.1f} ms/张",
        "",
        "## 各维度 PLCC / SRCC",
        "",
        "| 维度 | PLCC | SRCC | 是否达标 (≥0.7) |",
        "|------|------|------|----------------|",
    ]
    for name, p, s in zip(dim_names, visi_plccs, visi_srccs):
        ok = "✅" if p >= 0.7 and s >= 0.7 else "⚠️"
        lines.append(f"| {name} | {p:.3f} | {s:.3f} | {ok} |")
    avg_p = float(np.mean(visi_plccs))
    avg_s = float(np.mean(visi_srccs))
    ok_avg = "✅" if avg_p >= 0.7 and avg_s >= 0.7 else "⚠️"
    lines += [
        f"| **平均** | **{avg_p:.3f}** | **{avg_s:.3f}** | {ok_avg} |",
        "",
        "## 与 BRISQUE 对比（sharpness 维度）",
        "",
        "| 模型 | PLCC | SRCC |",
        "|------|------|------|",
        f"| VisiScore-Net (sharpness) | {visi_plccs[0]:.3f} | {visi_srccs[0]:.3f} |",
        f"| BRISQUE | {brisque_plcc:.3f} | {brisque_srcc:.3f} |",
        "",
        "## 结论",
        "",
    ]
    beat = visi_plccs[0] > brisque_plcc
    lines.append(
        f"VisiScore-Net sharpness 维度 PLCC={'高于' if beat else '低于'} BRISQUE "
        f"({visi_plccs[0]:.3f} vs {brisque_plcc:.3f})。"
    )
    lines.append(
        f"推理速度 {avg_ms:.1f} ms/张，{'达标' if avg_ms < 100 else '未达标'} (<100 ms 要求)。"
    )
    Path(out_path).write_text("\n".join(lines), encoding="utf-8")
    print(f"\n报告已写入 {out_path}")


def main():
    args = parse_args()
    cfg = OmegaConf.load(args.config)

    cache_dir = getattr(cfg.data, "cache_dir", None)
    dataset = SkinPairedDataset(cfg.data.labels_csv, img_size=224, cache_dir=cache_dir)

    val_indices = build_val_indices(cfg)
    n_samples = args.n_samples or len(val_indices)
    val_indices_sub = val_indices[:n_samples]
    val_ds = Subset(dataset, val_indices_sub)

    val_loader = DataLoader(
        val_ds, batch_size=64, shuffle=False,
        num_workers=2,
        multiprocessing_context="spawn",
        persistent_workers=True,
    )

    device = torch.device("cuda" if cfg.device.cuda and torch.cuda.is_available() else "cpu")
    model = VisiScoreNet(
        backbone=cfg.model.backbone,
        pretrained=False,
        num_dims=cfg.model.num_quality_dims,
    ).to(device)
    ckpt = torch.load(args.ckpt, map_location=device)
    model.load_state_dict(ckpt["model"])
    print(f"Loaded checkpoint from {args.ckpt} (epoch {ckpt['epoch']+1})")

    dim_names = ["sharpness", "brightness", "completeness", "color_temp", "contrast"]

    preds, labels, avg_ms = eval_visiscore(model, val_loader, device, cfg)
    visi_plccs = [_plcc(preds[:, d], labels[:, d]) for d in range(5)]
    visi_srccs = [_srcc(preds[:, d], labels[:, d]) for d in range(5)]

    print("\n=== VisiScore-Net ===")
    for name, p, s in zip(dim_names, visi_plccs, visi_srccs):
        print(f"  {name}: PLCC={p:.3f}  SRCC={s:.3f}")
    print(f"  平均: PLCC={np.mean(visi_plccs):.3f}  SRCC={np.mean(visi_srccs):.3f}")
    print(f"  推理速度: {avg_ms:.1f} ms/张")

    print("\n=== BRISQUE（sharpness 维度对比，取前 500 张）===")
    brisque_scores, sharp_labels = eval_brisque(dataset, val_indices, n_samples=min(500, n_samples))
    # BRISQUE 越低代表质量越好，与 sharpness label 负相关，取反后算相关
    brisque_plcc = _plcc(-brisque_scores, sharp_labels)
    brisque_srcc = _srcc(-brisque_scores, sharp_labels)
    print(f"  BRISQUE: PLCC={brisque_plcc:.3f}  SRCC={brisque_srcc:.3f}")

    write_report(
        args.out, dim_names, visi_plccs, visi_srccs, avg_ms,
        brisque_plcc, brisque_srcc, len(val_indices_sub),
    )


if __name__ == "__main__":
    main()
