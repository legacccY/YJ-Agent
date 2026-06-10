"""E1 守门 (HPC GPU) for v6 mask-L1: per-image + aggregate PSNR/SSIM on test split.
Red line: PSNR >= 30 must hold. mask-weighted L1 could shift fidelity, so re-check E1.
Reuses run_e1_ablation_hpc.eval_one. v6 config carries film_scale=0.1. cwd=code/."""
import json
from pathlib import Path

import torch

import run_e1_ablation_hpc as M

ROOT = "/gpfs/work/bio/jiayu2403/visienhance"
PAIR = ("v6-maskL1",
        f"{ROOT}/configs/visienhance_s2_planA_256_v6_maskL1_hpc.yaml",
        f"{ROOT}/checkpoints/visienhance/stage2_planA_256_v6_maskL1/best_visienhance.pth")


def main():
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    vs = M.load_visiscore(device)
    res = M.eval_one(*PAIR, vs, device)
    Path("results").mkdir(exist_ok=True)
    Path("results/e1_v6.json").write_text(json.dumps(res, indent=2))
    gate = "PASS" if res["psnr_perimg_enh"] >= 30 else "FAIL (red line!)"
    print(f"\n=== E1 v6 gate: per-image PSNR {res['psnr_perimg_enh']} -> {gate}  SSIM {res['ssim_enh']} ===")
    print("saved -> results/e1_v6.json")


if __name__ == "__main__":
    main()
