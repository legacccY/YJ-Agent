"""Decompose the PSNR ceiling by degradation type.

Sample N originals, apply medium degradation in two isolated regimes:
  photometric-only : brightness + contrast + color_shift (NO blur)
  blur-only        : Gaussian blur only

For each, report:
  baseline  PSNR(degraded, ref)
  oracle    PSNR after per-image per-channel affine correction

Hypothesis: photometric oracle ceiling is very high (affine inverts it),
blur oracle ~= blur baseline (affine cannot undo blur) -> blur is the wall.
"""
import os, sys, random
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import cv2
import numpy as np
import pandas as pd
import torch
import torch.nn.functional as F

IMG = 128
N = 400
MED = {"blur_sigma": (1.2, 2.5), "brightness": (0.55, 0.84),
       "contrast": (0.55, 0.84), "color_shift": 0.10}


def psnr(pred, target):
    mse = F.mse_loss(pred, target).item()
    return 10 * np.log10(1.0 / (mse + 1e-8))


def affine_match(low, ref):
    out = torch.empty_like(low)
    for c in range(3):
        x = low[c].reshape(-1); y = ref[c].reshape(-1)
        xm, ym = x.mean(), y.mean()
        cov = ((x - xm) * (y - ym)).mean()
        var = ((x - xm) ** 2).mean() + 1e-8
        a = cov / var; b = ym - a * xm
        out[c] = (a * low[c] + b).clamp(0, 1)
    return out


def deg_photometric(img, rng):
    out = img.astype(np.float32)
    out = np.clip(out * rng.uniform(*MED["brightness"]), 0, 255)
    alpha = rng.uniform(*MED["contrast"])
    mean = out.mean(axis=(0, 1), keepdims=True)
    out = np.clip(alpha * (out - mean) + mean, 0, 255)
    shift = MED["color_shift"] * 255
    for c in range(3):
        out[:, :, c] = np.clip(out[:, :, c] + rng.uniform(-shift, shift), 0, 255)
    return out.astype(np.uint8)


def deg_blur(img, rng):
    sigma = rng.uniform(*MED["blur_sigma"])
    ksize = int(2 * np.ceil(3 * sigma) + 1)
    return cv2.GaussianBlur(img, (ksize, ksize), sigma)


def to_t(bgr):
    rgb = cv2.cvtColor(cv2.resize(bgr, (IMG, IMG), interpolation=cv2.INTER_AREA), cv2.COLOR_BGR2RGB)
    return torch.from_numpy(rgb).permute(2, 0, 1).float() / 255.0


def main():
    df = pd.read_csv("D:/YJ-Agent/data/quality_labels_all.csv")
    paths = [p for p in df["original_path"].tolist() if os.path.exists(p)]
    rng = random.Random(42)
    rng.shuffle(paths)
    paths = paths[:N]

    acc = {"photo_base": [], "photo_oracle": [], "blur_base": [], "blur_oracle": []}
    for p in paths:
        img = cv2.imread(p)
        if img is None:
            continue
        ref = to_t(img)
        ph = to_t(deg_photometric(img, rng))
        bl = to_t(deg_blur(img, rng))
        acc["photo_base"].append(psnr(ph, ref))
        acc["photo_oracle"].append(psnr(affine_match(ph, ref), ref))
        acc["blur_base"].append(psnr(bl, ref))
        acc["blur_oracle"].append(psnr(affine_match(bl, ref), ref))

    print(f"n = {len(acc['photo_base'])}\n")
    print("=== photometric-only (brightness+contrast+color, NO blur) ===")
    print(f"  baseline       : {np.mean(acc['photo_base']):6.2f} dB")
    print(f"  oracle affine  : {np.mean(acc['photo_oracle']):6.2f} dB  <- recoverable")
    print("\n=== blur-only (Gaussian sigma 1.2-2.5) ===")
    print(f"  baseline       : {np.mean(acc['blur_base']):6.2f} dB")
    print(f"  oracle affine  : {np.mean(acc['blur_oracle']):6.2f} dB  <- affine cannot help -> WALL")


if __name__ == "__main__":
    main()
