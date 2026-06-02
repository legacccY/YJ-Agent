"""Probe: measure B3-sourced DP-Loss + pos-hinge magnitude (Stage 2 v2 calibration).

Why: v2 swaps the DP-Loss source from Q-VIB/B0 latent (no diagnosis signal) to the
B3 oracle that eval actually uses, and adds a pos-hinge so true melanomas are not
flipped to benign. The config ships with placeholder lambda_dp / lambda_hinge — this
script reports the *un-weighted* KL / hinge / L1 magnitudes on the Stage-1 @256 best
checkpoint so the weights are chosen on evidence (target: DP term ~ 5-20% of L1).

Doubles as an HPC smoke test of the never-run build_b3 / dp_loss_b3 / meta-merge code
path before we burn 12h of 4-GPU training.

Run (on HPC, single GPU, ~5 min):
    python scripts/probe_b3_dp.py --config configs/visienhance_s2_planA_256_v2_hpc.yaml --n-batches 200
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
from train_visienhance import build_b3, dp_loss_b3, _b3_logits, psnr


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    ap.add_argument("--n-batches", type=int, default=200)
    args = ap.parse_args()

    cfg = OmegaConf.load(args.config)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    # ── VisiEnhance (Stage-1 @256 best weights) ────────────────────────────────
    mcfg = cfg.model
    model = VisiEnhanceNet(
        base_channels=mcfg.base_channels, enc_blocks=list(mcfg.enc_blocks),
        mid_blocks=mcfg.mid_blocks, dec_blocks=list(mcfg.dec_blocks),
        film_hidden=mcfg.get("film_hidden", 128), film_scale=mcfg.get("film_scale", 0.1),
    ).to(device)
    ckpt_path = cfg.train.resume_from
    ckpt = torch.load(ckpt_path, map_location=device, weights_only=False)
    model.load_state_dict(ckpt["model"] if "model" in ckpt else ckpt)
    model.eval()
    print(f"[INFO] loaded Stage-1 @256 best: {ckpt_path}")

    # ── Frozen VisiScore (q_low conditioning) ──────────────────────────────────
    visiscore = VisiScoreNet(pretrained=False).to(device)
    vs = torch.load(cfg.frozen_models.visiscore_ckpt, map_location=device, weights_only=False)
    visiscore.load_state_dict(vs["model"] if "model" in vs else vs)
    visiscore.eval().requires_grad_(False)

    # ── Frozen B3 oracle (same one eval + v2 DP-Loss use) ──────────────────────
    b3 = build_b3(cfg.frozen_models.b3_ckpt, device)
    print("[INFO] EfficientNet-B3 oracle loaded (frozen)")

    # ── Val data — meta_csv + return_target so pos-hinge has melanoma labels ───
    dcfg = cfg.data
    val_ds = EnhanceDataset(
        labels_csv=dcfg.labels_csv, split_csv=dcfg.split_csv,
        split="val", img_size=dcfg.img_size,
        severity=dcfg.get("val_severity", dcfg.severity),
        meta_csv=dcfg.get("meta_csv", None),
        return_target=True,
        pos_oversample=1,
    )
    loader = DataLoader(val_ds, batch_size=dcfg.batch_size, shuffle=False, num_workers=0)
    print(f"[INFO] val={len(val_ds)}, probing up to {args.n_batches} batches")
    margin = cfg.loss.get("hinge_margin", 0.5)

    kls_enh, kls_input, l1s, psnrs = [], [], [], []
    hinge_sum, n_pos = 0.0, 0          # hinge averaged over positives only
    pmel_ref_pos, pmel_enh_pos = [], []  # melanoma prob on true positives (flip check)

    with torch.no_grad():
        for i, batch in enumerate(loader):
            if i >= args.n_batches:
                break
            x_low, x_ref, y = batch
            x_low = x_low.to(device); x_ref = x_ref.to(device); y = y.to(device)

            q_low = visiscore(x_low)
            x_enh = model(x_low, q_low)

            # enh-vs-ref KL + pos-hinge (exactly the v2 training objective).
            kl_enh, hinge = dp_loss_b3(b3, x_enh, x_ref, y, margin)
            kls_enh.append(kl_enh.item())

            # input-vs-ref KL = upper baseline (how far degraded drifts from ref).
            kl_in, _ = dp_loss_b3(b3, x_low, x_ref, y, margin)
            kls_input.append(kl_in.item())

            l1s.append(F.l1_loss(x_enh, x_ref).item())
            psnrs.append(psnr(x_enh, x_ref))

            pos = (y == 1)
            if pos.any():
                k = int(pos.sum().item())
                hinge_sum += hinge.item() * k     # un-normalise (dp_loss_b3 returns mean over pos)
                n_pos += k
                p_enh = F.softmax(_b3_logits(b3, x_enh), dim=-1)
                p_ref = F.softmax(_b3_logits(b3, x_ref), dim=-1)
                pmel_enh_pos.extend(p_enh[pos, 1].tolist())
                pmel_ref_pos.extend(p_ref[pos, 1].tolist())

    def stats(a):
        a = np.array(a)
        return a.mean(), a.std(), a.min(), a.max()

    me, se, mne, mxe = stats(kls_enh)
    mi, si, *_ = stats(kls_input)
    ml1, *_ = stats(l1s)
    mp, *_ = stats(psnrs)
    mean_hinge = hinge_sum / n_pos if n_pos > 0 else float("nan")

    print("\n========== B3 DP-Loss probe (Stage 2 v2) ==========")
    print(f"KL(enh ‖ ref)   mean={me:.4f}  std={se:.4f}  min={mne:.4f}  max={mxe:.4f}")
    print(f"KL(input ‖ ref) mean={mi:.4f}  std={si:.4f}   <- upper baseline (degraded drift)")
    print(f"pos-hinge        mean={mean_hinge:.4f}  over n_pos={n_pos} true melanomas")
    print(f"L1(enh, ref)     mean={ml1:.4f}   (for scale)")
    print(f"PSNR(enh,ref)agg mean={mp:.2f} dB")
    if n_pos > 0:
        pe, pr = np.mean(pmel_enh_pos), np.mean(pmel_ref_pos)
        print(f"\nTrue-melanoma mel-prob: ref={pr:.3f} -> enh={pe:.3f}  (drop={pr-pe:+.3f})")
        print(f"  enh mel-prob below {margin} (would flip benign): "
              f"{np.mean(np.array(pmel_enh_pos) < margin)*100:.1f}% of pos")

    print("\n---------- lambda calibration (target: DP term ~ 5-20% of L1) ----------")
    print(f"L1 term   = 1.0 * {ml1:.4f} = {ml1:.4f}")
    if me > 0:
        for frac in (0.05, 0.10, 0.20):
            lam = frac * ml1 / me
            print(f"  lambda_dp={lam:7.3f} -> DP term = {lam*me:.4f} ({frac*100:.0f}% of L1)")
    if n_pos > 0 and mean_hinge > 0:
        print(f"\nhinge term (safety, want it to bite — aim ~10-30% of L1):")
        for frac in (0.10, 0.20, 0.30):
            lam = frac * ml1 / mean_hinge
            print(f"  lambda_hinge={lam:7.3f} -> hinge term = {lam*mean_hinge:.4f} ({frac*100:.0f}% of L1)")
    print("===================================================")
    print("\nReading guide:")
    print("  - KL(enh) << KL(input): Stage 1 already preserves B3 diagnosis well.")
    print("  - Pick lambda_dp so DP term ~5-20% of L1 (bites without cratering PSNR).")
    print("  - Pick lambda_hinge so the safety term is non-trivial on positives.")
    print("  - mel-prob drop on true positives > 0 = the exact dangerous_flip risk v2 fights.")


if __name__ == "__main__":
    main()
