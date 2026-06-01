"""VisiEnhance-Net before/after demo grid.

Renders N test-split samples as rows of [degraded | enhanced | clean(ref)]
with per-sample PSNR, so the enhancement quality can be judged by eye.

Usage:
    python scripts/make_visienhance_demo.py \
        --config configs/visienhance_s1_planA_nocrop.yaml \
        --ckpt checkpoints/visienhance/stage1_planA_nocrop/best_visienhance.pth \
        --n 8 --out demo_nocrop_ep51.png --seed 7
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
import torch
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from omegaconf import OmegaConf
from skimage.metrics import peak_signal_noise_ratio, structural_similarity

from data.enhance_dataset import EnhanceDataset
from models.visienhance import VisiEnhanceNet
from models.visiscore import VisiScoreNet


def load_visienhance(cfg, ckpt_path, device):
    m = cfg.model
    model = VisiEnhanceNet(
        base_channels=m.base_channels,
        enc_blocks=list(m.enc_blocks),
        mid_blocks=m.mid_blocks,
        dec_blocks=list(m.dec_blocks),
    ).to(device)
    ckpt = torch.load(ckpt_path, map_location=device, weights_only=False)
    model.load_state_dict(ckpt["model"])
    return model.eval()


def load_visiscore(ckpt_path, device):
    model = VisiScoreNet().to(device)
    ckpt = torch.load(ckpt_path, map_location=device, weights_only=False)
    model.load_state_dict(ckpt["model"] if "model" in ckpt else ckpt)
    return model.eval()


def to_np(t):
    return (t.cpu().permute(1, 2, 0).numpy() * 255).clip(0, 255).astype(np.uint8)


@torch.no_grad()
def main():
    p = argparse.ArgumentParser()
    p.add_argument("--config", required=True)
    p.add_argument("--ckpt", required=True)
    p.add_argument("--n", type=int, default=8)
    p.add_argument("--out", default="demo_visienhance.png")
    p.add_argument("--seed", type=int, default=7)
    args = p.parse_args()

    cfg = OmegaConf.load(args.config)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    model = load_visienhance(cfg, args.ckpt, device)
    visiscore = load_visiscore(cfg.frozen_models.visiscore_ckpt, device)

    d = cfg.data
    ds = EnhanceDataset(d.labels_csv, d.split_csv, split="test",
                        img_size=d.img_size, severity=d.severity)
    if len(ds) == 0:
        print("[demo] test split empty for this severity; trying val split")
        ds = EnhanceDataset(d.labels_csv, d.split_csv, split="val",
                            img_size=d.img_size, severity=d.severity)
    print(f"[demo] sample set size = {len(ds)}")

    rng = np.random.default_rng(args.seed)
    idxs = rng.choice(len(ds), size=min(args.n, len(ds)), replace=False)

    n = len(idxs)
    fig, axes = plt.subplots(n, 3, figsize=(9, 3 * n))
    if n == 1:
        axes = axes[None, :]
    col_titles = ["Degraded (input)", "Enhanced (ours)", "Clean (reference)"]

    for r, idx in enumerate(idxs):
        deg, clean = ds[int(idx)]
        deg_b = deg.unsqueeze(0).to(device)
        q = visiscore(deg_b)
        enh = model(deg_b, q)[0]

        deg_np, enh_np, clean_np = to_np(deg), to_np(enh), to_np(clean)

        psnr_in = peak_signal_noise_ratio(clean_np, deg_np, data_range=255)
        psnr_out = peak_signal_noise_ratio(clean_np, enh_np, data_range=255)
        ssim_out = structural_similarity(clean_np, enh_np, channel_axis=2, data_range=255)

        for c, (im, title) in enumerate(zip([deg_np, enh_np, clean_np], col_titles)):
            ax = axes[r, c]
            ax.imshow(im)
            ax.set_xticks([]); ax.set_yticks([])
            if r == 0:
                ax.set_title(title, fontsize=11)
        axes[r, 0].set_ylabel(f"PSNR {psnr_in:.1f}", fontsize=9)
        axes[r, 1].set_ylabel(f"PSNR {psnr_out:.1f} / SSIM {ssim_out:.3f}", fontsize=9)

    plt.tight_layout()
    out = Path(args.out)
    plt.savefig(out, dpi=110, bbox_inches="tight")
    print(f"[demo] saved -> {out.resolve()}")


if __name__ == "__main__":
    main()
