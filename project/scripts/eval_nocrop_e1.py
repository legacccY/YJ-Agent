"""Full test-split E1 evaluation for the no-crop Stage-1 checkpoint.

Computes mean PSNR / SSIM (enhanced vs clean reference) over the entire
nocrop test split, plus the input baseline (degraded vs clean) so the net
gain is explicit. This is the frozen E1 number for the report.

Usage:
    python scripts/eval_nocrop_e1.py \
        --config configs/visienhance_s1_planA_nocrop.yaml \
        --ckpt D:/YJ-Agent/checkpoints/visienhance/stage1_planA_nocrop/best_visienhance.pth
"""

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
import torch
import torch.nn.functional as F
from omegaconf import OmegaConf
from skimage.metrics import peak_signal_noise_ratio, structural_similarity
from torch.utils.data import DataLoader
from tqdm import tqdm

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
    print(f"[eval] loaded ckpt epoch={ckpt.get('epoch','?')} "
          f"best_psnr={ckpt.get('best_psnr', ckpt.get('best','?'))}")
    return model.eval()


def load_visiscore(ckpt_path, device):
    model = VisiScoreNet().to(device)
    ckpt = torch.load(ckpt_path, map_location=device, weights_only=False)
    model.load_state_dict(ckpt["model"] if "model" in ckpt else ckpt)
    return model.eval()


@torch.no_grad()
def main():
    p = argparse.ArgumentParser()
    p.add_argument("--config", required=True)
    p.add_argument("--ckpt", required=True)
    p.add_argument("--split", default="test")
    p.add_argument("--out", default="D:/YJ-Agent/project/results/visienhance_nocrop_e1.json")
    args = p.parse_args()

    cfg = OmegaConf.load(args.config)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    model = load_visienhance(cfg, args.ckpt, device)
    visiscore = load_visiscore(cfg.frozen_models.visiscore_ckpt, device)

    d = cfg.data
    ds = EnhanceDataset(d.labels_csv, d.split_csv, split=args.split,
                        img_size=d.img_size, severity=d.severity)
    print(f"[eval] {args.split} set size = {len(ds)}")
    loader = DataLoader(ds, batch_size=32, shuffle=False, num_workers=0, pin_memory=True)

    # Two PSNR conventions:
    #  (A) per-image mean  -> standard in restoration papers
    #  (B) aggregate-MSE   -> what train_visienhance.validate() logs
    psnr_in, psnr_out, ssim_out = [], [], []
    sum_mse_out, sum_mse_in, n_imgs = 0.0, 0.0, 0
    t0 = time.time()
    for x_low, x_ref in tqdm(loader, desc="E1", ncols=80):
        x_low, x_ref = x_low.to(device), x_ref.to(device)
        q = visiscore(x_low)
        x_enh = model(x_low, q)
        # (B) aggregate MSE in float [0,1] space, exactly like training validate
        mse_out = F.mse_loss(x_enh, x_ref).item()
        mse_in = F.mse_loss(x_low, x_ref).item()
        sum_mse_out += mse_out * x_low.size(0)
        sum_mse_in += mse_in * x_low.size(0)
        n_imgs += x_low.size(0)
        for i in range(x_enh.shape[0]):
            ref = (x_ref[i].cpu().permute(1, 2, 0).numpy() * 255).astype(np.uint8)
            enh = (x_enh[i].cpu().permute(1, 2, 0).numpy() * 255).clip(0, 255).astype(np.uint8)
            low = (x_low[i].cpu().permute(1, 2, 0).numpy() * 255).clip(0, 255).astype(np.uint8)
            psnr_out.append(peak_signal_noise_ratio(ref, enh, data_range=255))
            psnr_in.append(peak_signal_noise_ratio(ref, low, data_range=255))
            ssim_out.append(structural_similarity(ref, enh, channel_axis=2, data_range=255))

    def agg_psnr(sum_mse):
        return 10.0 * np.log10(1.0 / max(sum_mse / n_imgs, 1e-10))

    res = {
        "split": args.split,
        "n": len(psnr_out),
        # (A) per-image-mean PSNR — paper convention
        "psnr_perimg_input": round(float(np.mean(psnr_in)), 3),
        "psnr_perimg_enhanced": round(float(np.mean(psnr_out)), 3),
        "psnr_perimg_gain": round(float(np.mean(psnr_out) - np.mean(psnr_in)), 3),
        "psnr_perimg_std": round(float(np.std(psnr_out)), 3),
        # (B) aggregate-MSE PSNR — training-log convention (should match val log)
        "psnr_aggmse_input": round(float(agg_psnr(sum_mse_in)), 3),
        "psnr_aggmse_enhanced": round(float(agg_psnr(sum_mse_out)), 3),
        "ssim_enhanced_mean": round(float(np.mean(ssim_out)), 4),
        "E1_target_psnr": 30.0,
        "E1_pass_perimg": bool(np.mean(psnr_out) >= 30.0),
        "E1_pass_aggmse": bool(agg_psnr(sum_mse_out) >= 30.0),
        "ssim_target": 0.92,
        "ssim_pass": bool(np.mean(ssim_out) >= 0.92),
        "eval_seconds": round(time.time() - t0, 1),
    }
    print(json.dumps(res, indent=2))
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(res, indent=2), encoding="utf-8")
    print(f"[eval] saved -> {out}")


if __name__ == "__main__":
    main()
