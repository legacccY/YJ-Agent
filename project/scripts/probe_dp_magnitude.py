"""Probe: measure raw DP-Loss magnitude of the Stage-1 best checkpoint on val.

Purpose: Stage 2 adds `lambda_dp * dp_loss` to L1+LPIPS. If the Stage-1 output
is already diagnosis-preserving (KL ~ 0), then lambda_dp=0.05 is a no-op and
"PSNR not rising" is expected. This script reports the un-weighted DP-Loss
(plus L1/LPIPS for scale reference) so we can pick lambda_dp on evidence.

Run:
    python project/scripts/probe_dp_magnitude.py --config project/configs/visienhance_s2_planA.yaml --n-batches 60
"""

import argparse
import os
import sys
from pathlib import Path

os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")
os.environ.setdefault("OMP_NUM_THREADS", "1")

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # project/ on path

import numpy as np
import torch
import torch.nn.functional as F
from omegaconf import OmegaConf
from torch.utils.data import DataLoader

from data.enhance_dataset import EnhanceDataset
from models.visienhance import VisiEnhanceNet
from models.visiscore import VisiScoreNet
from train_visienhance import build_qvib_encoder, build_efnet_extractor, dp_loss, psnr


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    ap.add_argument("--n-batches", type=int, default=60)
    args = ap.parse_args()

    cfg = OmegaConf.load(args.config)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    mcfg = cfg.model
    model = VisiEnhanceNet(
        base_channels=mcfg.base_channels, enc_blocks=list(mcfg.enc_blocks),
        mid_blocks=mcfg.mid_blocks, dec_blocks=list(mcfg.dec_blocks),
        film_hidden=mcfg.get("film_hidden", 128), film_scale=mcfg.get("film_scale", 0.1),
    ).to(device)
    ckpt_path = cfg.train.resume_from
    ckpt = torch.load(ckpt_path, map_location=device, weights_only=False)
    model.load_state_dict(ckpt["model"])
    model.eval()
    print(f"[INFO] loaded Stage-1 best: {ckpt_path}")

    visiscore = VisiScoreNet(pretrained=False).to(device)
    vs = torch.load(cfg.frozen_models.visiscore_ckpt, map_location=device, weights_only=False)
    visiscore.load_state_dict(vs["model"] if "model" in vs else vs)
    visiscore.eval().requires_grad_(False)

    qvib_enc = build_qvib_encoder(cfg, device)
    efnet = build_efnet_extractor(device)
    print("[INFO] Q-VIB + EfficientNet loaded (frozen)")

    dcfg = cfg.data
    val_ds = EnhanceDataset(
        labels_csv=dcfg.labels_csv, split_csv=dcfg.split_csv,
        split="val", img_size=dcfg.img_size,
        severity=dcfg.get("val_severity", dcfg.severity),
    )
    # Mirror training val loop exactly: no shuffle, autocast on (amp). Sampling
    # bias / precision must not explain any PSNR gap vs the training log.
    loader = DataLoader(val_ds, batch_size=dcfg.batch_size, shuffle=False, num_workers=0)
    print(f"[INFO] val={len(val_ds)}, probing {args.n_batches} batches")
    from torch.cuda.amp import autocast

    # Identity baseline: DP-Loss of degraded input vs ref (upper reference) and
    # of enhanced vs ref. If enh-DP << input-DP, Stage 1 already preserved
    # diagnosis; if enh-DP already ~0, Stage 2 has little to optimise.
    dps_enh, dps_input, l1s, psnrs = [], [], [], []
    with torch.no_grad():
        for i, (x_low, x_ref) in enumerate(loader):
            if i >= args.n_batches:
                break
            x_low = x_low.to(device); x_ref = x_ref.to(device)
            q_low = visiscore(x_low)
            with autocast(enabled=True):
                x_enh = model(x_low, q_low)
            dps_enh.append(dp_loss(qvib_enc, efnet, visiscore, x_enh, x_ref).item())
            dps_input.append(dp_loss(qvib_enc, efnet, visiscore, x_low, x_ref).item())
            l1s.append(F.l1_loss(x_enh, x_ref).item())
            psnrs.append(psnr(x_enh, x_ref))

    def stats(a):
        a = np.array(a); return a.mean(), a.std(), a.min(), a.max()

    me, se, mne, mxe = stats(dps_enh)
    mi, si, *_ = stats(dps_input)
    ml1, *_ = stats(l1s)
    mp, *_ = stats(psnrs)

    print("\n========== DP-Loss probe ==========")
    print(f"DP(enhanced‖ref)  mean={me:.4f}  std={se:.4f}  min={mne:.4f}  max={mxe:.4f}")
    print(f"DP(input‖ref)     mean={mi:.4f}  std={si:.4f}   <- upper baseline")
    print(f"L1(enhanced,ref)  mean={ml1:.4f}   (for scale)")
    print(f"PSNR(enh,ref)agg  mean={mp:.2f} dB")
    print(f"\nWeighted contributions in total loss:")
    print(f"  L1 term      = lambda_l1(1.0)  * {ml1:.4f} = {ml1:.4f}")
    print(f"  DP term @0.05 = 0.05 * {me:.4f} = {0.05*me:.5f}  ({0.05*me/ml1*100:.1f}% of L1)")
    print(f"  DP term @0.5  = 0.5  * {me:.4f} = {0.5*me:.5f}")
    print(f"  DP term @5.0  = 5.0  * {me:.4f} = {5.0*me:.5f}")
    print("===================================")
    print("\nReading guide:")
    print("  - If DP(enh) << DP(input): Stage 1 already preserves diagnosis.")
    print("  - If DP term @0.05 is <1% of L1: lambda_dp=0.05 is a no-op; raise it.")
    print("  - Target: DP term comparable to ~5-20% of L1 so it actually bites,")
    print("    but watch PSNR doesn't crater (decision gate).")


if __name__ == "__main__":
    main()
