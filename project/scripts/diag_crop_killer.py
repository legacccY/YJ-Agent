"""Test whether random_crop is the PSNR ceiling killer.

Replicate degrade.py medium pipeline, toggle crop on/off.
Report baseline + oracle affine ceiling for each.

If no-crop oracle >> with-crop oracle, the crop (spatial misalignment)
is the binding constraint -> remove crop, regenerate, PSNR>=30 becomes reachable.
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
SIZE = 256
CFG = {"blur_ksize": (5, 5), "blur_sigma": 1.5, "brightness_range": (0.65, 0.85),
       "jpeg_quality": (50, 74), "crop_ratio": (0.75, 0.89), "color_shift": 0.12}
PROBS = {"blur": 0.7, "brightness": 0.6, "jpeg": 0.8, "crop": 0.5, "color_shift": 0.5}


def psnr(pred, target):
    return 10 * np.log10(1.0 / (F.mse_loss(pred, target).item() + 1e-8))


def affine_match(low, ref):
    out = torch.empty_like(low)
    for c in range(3):
        x = low[c].reshape(-1); y = ref[c].reshape(-1)
        xm, ym = x.mean(), y.mean()
        a = ((x - xm) * (y - ym)).mean() / (((x - xm) ** 2).mean() + 1e-8)
        out[c] = (a * low[c] + (ym - a * xm)).clamp(0, 1)
    return out


def degrade(img, rng, use_crop):
    r = img.copy()
    if rng.random() < PROBS["blur"]:
        r = cv2.GaussianBlur(r, CFG["blur_ksize"], CFG["blur_sigma"])
    if rng.random() < PROBS["brightness"]:
        r = np.clip(r.astype(np.float32) * rng.uniform(*CFG["brightness_range"]), 0, 255).astype(np.uint8)
    if rng.random() < PROBS["color_shift"]:
        f = r.astype(np.float32)
        for c in range(3):
            f[:, :, c] = np.clip(f[:, :, c] + rng.uniform(-CFG["color_shift"]*255, CFG["color_shift"]*255), 0, 255)
        r = f.astype(np.uint8)
    if use_crop and rng.random() < PROBS["crop"]:
        h, w = r.shape[:2]
        ratio = rng.uniform(*CFG["crop_ratio"])
        ch, cw = int(h*ratio), int(w*ratio)
        y, x = rng.randint(0, h-ch), rng.randint(0, w-cw)
        r = cv2.resize(r[y:y+ch, x:x+cw], (SIZE, SIZE), interpolation=cv2.INTER_LINEAR)
    else:
        r = cv2.resize(r, (SIZE, SIZE), interpolation=cv2.INTER_LINEAR)
    if rng.random() < PROBS["jpeg"]:
        q = rng.randint(*CFG["jpeg_quality"])
        _, buf = cv2.imencode(".jpg", r, [int(cv2.IMWRITE_JPEG_QUALITY), q])
        r = cv2.imdecode(buf, cv2.IMREAD_COLOR)
    return r


def to_t(bgr):
    rgb = cv2.cvtColor(cv2.resize(bgr, (IMG, IMG), interpolation=cv2.INTER_AREA), cv2.COLOR_BGR2RGB)
    return torch.from_numpy(rgb).permute(2, 0, 1).float() / 255.0


def main():
    df = pd.read_csv("D:/YJ-Agent/data/quality_labels_all.csv")
    paths = [p for p in df["original_path"].tolist() if os.path.exists(p)]
    rng = random.Random(42); rng.shuffle(paths); paths = paths[:N]

    res = {"crop_base": [], "crop_oracle": [], "nocrop_base": [], "nocrop_oracle": []}
    for p in paths:
        img = cv2.imread(p)
        if img is None:
            continue
        ref = to_t(cv2.resize(img, (SIZE, SIZE), interpolation=cv2.INTER_LINEAR))
        c = to_t(degrade(img, random.Random(hash(p) & 0xffff), True))
        nc = to_t(degrade(img, random.Random(hash(p) & 0xffff), False))
        res["crop_base"].append(psnr(c, ref)); res["crop_oracle"].append(psnr(affine_match(c, ref), ref))
        res["nocrop_base"].append(psnr(nc, ref)); res["nocrop_oracle"].append(psnr(affine_match(nc, ref), ref))

    n = len(res["crop_base"])
    print(f"n = {n}\n")
    print("=== WITH random crop (current saved pipeline) ===")
    print(f"  baseline      : {np.mean(res['crop_base']):6.2f} dB")
    print(f"  oracle affine : {np.mean(res['crop_oracle']):6.2f} dB")
    print("\n=== WITHOUT random crop (proposed fix) ===")
    print(f"  baseline      : {np.mean(res['nocrop_base']):6.2f} dB")
    print(f"  oracle affine : {np.mean(res['nocrop_oracle']):6.2f} dB")


if __name__ == "__main__":
    main()
