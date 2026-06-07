"""Probe: feature-level DP (v5) 量级标定.

v4 输出层 prob-KL+hinge 没压下 dangerous_flip (0.176): 标量监督被 L1+LPIPS 碾压.
v5 改 feature-level DP = channel-wise cosine 对齐 B3 最终特征图 (1536×7×7), 梯度密集.
config 的 lambda_dp 是 placeholder — 本脚本报 *未加权* feat / hinge / L1 量级 (Stage-1 @256
best 上), 据此选 λ (目标: feat 项 ~ 15-30% of L1, 比 v4 的 prob-KL 更狠才压得动结构磨平).

兼作 dp_feat_loss / _b3_feat 新代码路径的 HPC smoke (烧 4 卡前先验).
Run (HPC, 单 GPU, ~5min):
    python scripts/probe_feat_dp.py --config configs/visienhance_s2_planA_256_v5_hpc.yaml --n-batches 200
"""
import argparse
import os
import sys
from pathlib import Path

os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")
os.environ.setdefault("OMP_NUM_THREADS", "1")

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
import torch
import torch.nn.functional as F
from omegaconf import OmegaConf
from torch.utils.data import DataLoader

from data.enhance_dataset import EnhanceDataset
from models.visienhance import VisiEnhanceNet
from models.visiscore import VisiScoreNet
from train_visienhance import build_b3, dp_feat_loss, _b3_logits, psnr


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    ap.add_argument("--n-batches", type=int, default=200)
    args = ap.parse_args()

    cfg = OmegaConf.load(args.config)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    mcfg = cfg.model
    model = VisiEnhanceNet(
        base_channels=mcfg.base_channels, enc_blocks=list(mcfg.enc_blocks),
        mid_blocks=mcfg.mid_blocks, dec_blocks=list(mcfg.dec_blocks),
        film_hidden=mcfg.get("film_hidden", 128), film_scale=mcfg.get("film_scale", 0.1),
    ).to(device)
    ckpt = torch.load(cfg.train.resume_from, map_location=device, weights_only=False)
    model.load_state_dict(ckpt["model"] if "model" in ckpt else ckpt)
    model.eval()
    print(f"[INFO] loaded Stage-1 @256 best: {cfg.train.resume_from}")

    visiscore = VisiScoreNet(pretrained=False).to(device)
    vs = torch.load(cfg.frozen_models.visiscore_ckpt, map_location=device, weights_only=False)
    visiscore.load_state_dict(vs["model"] if "model" in vs else vs)
    visiscore.eval().requires_grad_(False)

    b3 = build_b3(cfg.frozen_models.b3_ckpt, device)
    print("[INFO] EfficientNet-B3 oracle loaded (frozen)")

    dcfg = cfg.data
    val_ds = EnhanceDataset(
        labels_csv=dcfg.labels_csv, split_csv=dcfg.split_csv,
        split="val", img_size=dcfg.img_size,
        severity=dcfg.get("val_severity", dcfg.severity),
        meta_csv=dcfg.get("meta_csv", None), return_target=True, pos_oversample=1,
    )
    loader = DataLoader(val_ds, batch_size=dcfg.batch_size, shuffle=False, num_workers=0)
    print(f"[INFO] val={len(val_ds)}, probing up to {args.n_batches} batches")
    clamp = cfg.loss.get("hinge_clamp", 3.0)

    feats_enh, feats_input, l1s, psnrs = [], [], [], []
    hinge_sum, n_pos = 0.0, 0
    pmel_ref_pos, pmel_enh_pos = [], []

    with torch.no_grad():
        for i, batch in enumerate(loader):
            if i >= args.n_batches:
                break
            x_low, x_ref, y = batch
            x_low = x_low.to(device); x_ref = x_ref.to(device); y = y.to(device)
            q_low = visiscore(x_low)
            x_enh = model(x_low, q_low)

            feat_enh, hinge = dp_feat_loss(b3, x_enh, x_ref, y, clamp)
            feats_enh.append(feat_enh.item())
            feat_in, _ = dp_feat_loss(b3, x_low, x_ref, y, clamp)   # degraded drift baseline
            feats_input.append(feat_in.item())

            l1s.append(F.l1_loss(x_enh, x_ref).item())
            psnrs.append(psnr(x_enh, x_ref))

            pos = (y == 1)
            if pos.any():
                k = int(pos.sum().item())
                hinge_sum += hinge.item() * k
                n_pos += k
                p_enh = F.softmax(_b3_logits(b3, x_enh), dim=-1)
                p_ref = F.softmax(_b3_logits(b3, x_ref), dim=-1)
                pmel_enh_pos.extend(p_enh[pos, 1].tolist())
                pmel_ref_pos.extend(p_ref[pos, 1].tolist())

    def m(a):
        a = np.array(a); return a.mean(), a.std(), a.min(), a.max()
    me, se, mne, mxe = m(feats_enh)
    mi, *_ = m(feats_input)
    ml1, *_ = m(l1s)
    mp, *_ = m(psnrs)
    mean_hinge = hinge_sum / n_pos if n_pos > 0 else float("nan")

    print("\n========== feature-DP probe (Stage 2 v5) ==========")
    print(f"feat(enh,ref)   mean={me:.4f}  std={se:.4f}  min={mne:.4f}  max={mxe:.4f}  (1-cos, B3 feat)")
    print(f"feat(input,ref) mean={mi:.4f}   <- upper baseline (degraded drift)")
    print(f"pos-hinge        mean={mean_hinge:.4f}  over n_pos={n_pos} true melanomas")
    print(f"L1(enh,ref)      mean={ml1:.4f}   (for scale)")
    print(f"PSNR(enh,ref)agg mean={mp:.2f} dB")
    if n_pos > 0:
        pe, pr = np.mean(pmel_enh_pos), np.mean(pmel_ref_pos)
        print(f"\nTrue-melanoma mel-prob: ref={pr:.3f} -> enh={pe:.3f}  (drop={pr-pe:+.3f})")
        print(f"  enh mel-prob below 0.5: {np.mean(np.array(pmel_enh_pos) < 0.5)*100:.1f}% of pos")

    print("\n---------- lambda calibration (feat 项 ~ 15-30% of L1) ----------")
    print(f"L1 term = 1.0 * {ml1:.4f} = {ml1:.4f}")
    if me > 0:
        for frac in (0.15, 0.20, 0.30):
            lam = frac * ml1 / me
            print(f"  lambda_dp={lam:8.3f} -> feat term = {lam*me:.4f} ({frac*100:.0f}% of L1)")
    if n_pos > 0 and mean_hinge > 0:
        print("hinge term (safety):")
        for frac in (0.10, 0.20, 0.30):
            lam = frac * ml1 / mean_hinge
            print(f"  lambda_hinge={lam:8.3f} -> hinge term = {lam*mean_hinge:.4f} ({frac*100:.0f}% of L1)")
    print("===================================================")


if __name__ == "__main__":
    main()
