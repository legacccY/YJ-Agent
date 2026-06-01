"""Confirm regenerated no-crop data has high oracle ceiling on val(medium)."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np, torch, torch.nn.functional as F
from torch.utils.data import DataLoader
from data.enhance_dataset import EnhanceDataset

IMG = 128


def psnr(p, t): return 10*np.log10(1.0/(F.mse_loss(p, t).item()+1e-8))


def affine(low, ref):
    out = torch.empty_like(low)
    for b in range(low.shape[0]):
        for c in range(3):
            x, y = low[b, c].reshape(-1), ref[b, c].reshape(-1)
            xm, ym = x.mean(), y.mean()
            a = ((x-xm)*(y-ym)).mean()/(((x-xm)**2).mean()+1e-8)
            out[b, c] = (a*low[b, c]+(ym-a*xm)).clamp(0, 1)
    return out


ds = EnhanceDataset("D:/YJ-Agent/data/quality_labels_nocrop.csv",
                    "D:/YJ-Agent/data/isic_split.csv", "val", IMG, "medium")
print("val(medium) nocrop n =", len(ds))
ld = DataLoader(ds, batch_size=16, num_workers=0)
base = orc = n = 0
for low, ref in ld:
    B = low.shape[0]; n += B
    base += psnr(low, ref)*B; orc += psnr(affine(low, ref), ref)*B
print(f"baseline (no enhance) : {base/n:6.2f} dB")
print(f"oracle affine ceiling : {orc/n:6.2f} dB")
