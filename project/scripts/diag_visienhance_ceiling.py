"""Diagnose VisiEnhance PSNR ceiling on val(medium) set.

Three numbers:
  baseline   PSNR(x_low, x_ref)                      -- degradation severity
  oracle     PSNR after per-image per-channel affine -- removes brightness/contrast ambiguity
  model      PSNR(model(x_low,q), x_ref)             -- current best ckpt

If oracle >> model and oracle >> baseline, the ceiling is aleatoric
(random global photometric degradation), not model capacity.
"""
import os, sys
os.environ.setdefault("WANDB_DISABLE_SERVICE", "true")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import torch
import torch.nn.functional as F
from torch.utils.data import DataLoader

from data.enhance_dataset import EnhanceDataset

DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
IMG = 128


def psnr(pred, target):
    mse = F.mse_loss(pred, target).item()
    return 10 * np.log10(1.0 / (mse + 1e-8))


def affine_match(low, ref):
    """Per-image per-channel least-squares: a*low + b ~= ref. Returns corrected low."""
    out = torch.empty_like(low)
    for b in range(low.shape[0]):
        for c in range(3):
            x = low[b, c].reshape(-1)
            y = ref[b, c].reshape(-1)
            xm, ym = x.mean(), y.mean()
            cov = ((x - xm) * (y - ym)).mean()
            var = ((x - xm) ** 2).mean() + 1e-8
            a = cov / var
            bb = ym - a * xm
            out[b, c] = (a * low[b, c] + bb).clamp(0, 1)
    return out


def main():
    ds = EnhanceDataset(
        labels_csv="D:/YJ-Agent/data/quality_labels_all.csv",
        split_csv="D:/YJ-Agent/data/isic_split.csv",
        split="val", img_size=IMG, severity="medium",
    )
    print(f"val(medium) n = {len(ds)}")
    loader = DataLoader(ds, batch_size=16, num_workers=0)

    # try load model + visiscore
    model = None
    try:
        from models.visienhance import VisiEnhanceNet
        from models.visiscore import VisiScoreNet
        import yaml
        cfg = yaml.safe_load(open("D:/YJ-Agent/project/configs/visienhance_s1_planA.yaml", encoding="utf-8"))
        m = cfg["model"]
        model = VisiEnhanceNet(
            base_channels=m["base_channels"], enc_blocks=m["enc_blocks"],
            mid_blocks=m["mid_blocks"], dec_blocks=m["dec_blocks"],
            film_hidden=m["film_hidden"], film_scale=m["film_scale"],
        ).to(DEVICE).eval()
        ck = torch.load("D:/YJ-Agent/checkpoints/visienhance/stage1_planA/best_visienhance.pth", map_location=DEVICE, weights_only=False)
        model.load_state_dict(ck["model"] if "model" in ck else ck)
        vs = VisiScoreNet().to(DEVICE).eval()
        vck = torch.load("D:/YJ-Agent/checkpoints/best_visiscore.pth", map_location=DEVICE, weights_only=False)
        vs.load_state_dict(vck["model"] if "model" in vck else vck)
        print(f"model loaded, best_val_psnr in ckpt = {ck.get('best_psnr', 'NA')}")
    except Exception as e:
        print(f"[WARN] model load failed ({e}); skipping model PSNR")
        vs = None

    tot = {"base": 0.0, "oracle": 0.0, "model": 0.0}
    n = 0
    with torch.no_grad():
        for low, ref in loader:
            low, ref = low.to(DEVICE), ref.to(DEVICE)
            B = low.shape[0]; n += B
            tot["base"] += psnr(low, ref) * B
            tot["oracle"] += psnr(affine_match(low, ref), ref) * B
            if model is not None and vs is not None:
                q = vs(low)
                enh = model(low, q)
                tot["model"] += psnr(enh, ref) * B

    print("\n=== PSNR (val medium) ===")
    print(f"baseline (no enhance) : {tot['base']/n:6.2f} dB")
    print(f"oracle affine ceiling : {tot['oracle']/n:6.2f} dB")
    if model is not None:
        print(f"model (best ckpt)     : {tot['model']/n:6.2f} dB")


if __name__ == "__main__":
    main()
