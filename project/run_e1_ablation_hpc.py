"""E1 FiLM 消融 (HPC GPU): with-FiLM vs no-FiLM 同协议 per-image + aggregate PSNR/SSIM.

两 ckpt 同 recipe (stage1_planA_256), 唯一差 film_scale 0.1 vs 0.0.
关键: 按各自 config 的 film_scale 构建模型再加载 ckpt (no-FiLM 必须 scale=0 否则加载错).
测 test split, severity=mixed, img_size 256. cwd 必须 = code/.
"""
import json
import time
from pathlib import Path

import numpy as np
import torch
import torch.nn.functional as F
from omegaconf import OmegaConf
from skimage.metrics import peak_signal_noise_ratio, structural_similarity
from torch.utils.data import DataLoader

from data.enhance_dataset import EnhanceDataset
from models.visienhance import VisiEnhanceNet
from models.visiscore import VisiScoreNet

ROOT = "/gpfs/work/bio/jiayu2403/visienhance"
VISISCORE = f"{ROOT}/checkpoints/best_visiscore.pth"
PAIRS = [
    ("with-FiLM", f"{ROOT}/configs/visienhance_s1_planA_256_hpc.yaml",
     f"{ROOT}/checkpoints/visienhance/stage1_planA_256/best_visienhance.pth"),
    ("no-FiLM",   f"{ROOT}/configs/visienhance_s1_planA_256_noFiLM_hpc.yaml",
     f"{ROOT}/checkpoints/visienhance/stage1_planA_256_noFiLM/best_visienhance.pth"),
]


def load_visiscore(device):
    m = VisiScoreNet().to(device)
    ck = torch.load(VISISCORE, map_location=device, weights_only=False)
    m.load_state_dict(ck["model"] if "model" in ck else ck)
    return m.eval()


def load_enh(cfg, ckpt, device):
    m = cfg.model
    fs = float(getattr(m, "film_scale", 0.1))
    model = VisiEnhanceNet(
        base_channels=m.base_channels,
        enc_blocks=list(m.enc_blocks),
        mid_blocks=m.mid_blocks,
        dec_blocks=list(m.dec_blocks),
        film_scale=fs,
    ).to(device)
    ck = torch.load(ckpt, map_location=device, weights_only=False)
    model.load_state_dict(ck["model"])
    print(f"  film_scale={fs}  ckpt epoch={ck.get('epoch','?')} "
          f"best={ck.get('best_psnr', ck.get('best_val_psnr', ck.get('best','?')))}", flush=True)
    return model.eval()


@torch.no_grad()
def eval_one(tag, cfg_path, ckpt, visiscore, device):
    cfg = OmegaConf.load(cfg_path)
    d = cfg.data
    model = load_enh(cfg, ckpt, device)
    ds = EnhanceDataset(d.labels_csv, d.split_csv, split="test",
                        img_size=d.img_size, severity=d.severity)
    loader = DataLoader(ds, batch_size=32, shuffle=False, num_workers=4, pin_memory=True)
    psnr_in, psnr_out, ssim_out = [], [], []
    sum_mse_out, sum_mse_in, n = 0.0, 0.0, 0
    t0 = time.time()
    for x_low, x_ref in loader:
        x_low, x_ref = x_low.to(device), x_ref.to(device)
        q = visiscore(x_low)
        x_enh = model(x_low, q)
        sum_mse_out += F.mse_loss(x_enh, x_ref).item() * x_low.size(0)
        sum_mse_in += F.mse_loss(x_low, x_ref).item() * x_low.size(0)
        n += x_low.size(0)
        for i in range(x_enh.shape[0]):
            ref = (x_ref[i].cpu().permute(1, 2, 0).numpy() * 255).astype(np.uint8)
            enh = (x_enh[i].cpu().permute(1, 2, 0).numpy() * 255).clip(0, 255).astype(np.uint8)
            low = (x_low[i].cpu().permute(1, 2, 0).numpy() * 255).clip(0, 255).astype(np.uint8)
            psnr_out.append(peak_signal_noise_ratio(ref, enh, data_range=255))
            psnr_in.append(peak_signal_noise_ratio(ref, low, data_range=255))
            ssim_out.append(structural_similarity(ref, enh, channel_axis=2, data_range=255))
    agg = lambda s: 10.0 * np.log10(1.0 / max(s / n, 1e-10))
    res = {
        "tag": tag, "n": len(psnr_out),
        "psnr_perimg_input": round(float(np.mean(psnr_in)), 3),
        "psnr_perimg_enh": round(float(np.mean(psnr_out)), 3),
        "psnr_perimg_gain": round(float(np.mean(psnr_out) - np.mean(psnr_in)), 3),
        "psnr_aggmse_enh": round(float(agg(sum_mse_out)), 3),
        "ssim_enh": round(float(np.mean(ssim_out)), 4),
        "sec": round(time.time() - t0, 1),
    }
    print(json.dumps(res), flush=True)
    return res


def main():
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    vs = load_visiscore(device)
    out = []
    for tag, cfg_path, ckpt in PAIRS:
        print(f"\n=== {tag} ===", flush=True)
        out.append(eval_one(tag, cfg_path, ckpt, vs, device))
    print("\n=== E1 FiLM ablation summary (test split) ===")
    print(f"{'variant':10} {'perimg_PSNR':>12} {'aggmse_PSNR':>12} {'SSIM':>8}")
    for r in out:
        print(f"{r['tag']:10} {r['psnr_perimg_enh']:>12} {r['psnr_aggmse_enh']:>12} {r['ssim_enh']:>8}")
    Path("results").mkdir(exist_ok=True)
    Path("results/e1_film_ablation.json").write_text(json.dumps(out, indent=2))
    print("saved -> results/e1_film_ablation.json")


if __name__ == "__main__":
    main()
