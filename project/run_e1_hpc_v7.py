"""E1 守门 (HPC GPU) for v7 crossattn (E9): per-image + aggregate PSNR/SSIM on test split.
Red line: PSNR >= 30 must hold. Reuses run_e1_ablation_hpc.eval_one, which OmegaConf.loads
the v7 config (conditioning=crossattn) and builds the matching net. cwd=code/."""
import json
from pathlib import Path

import torch

import run_e1_ablation_hpc as M

ROOT = "/gpfs/work/bio/jiayu2403/visienhance"
PAIR = ("v7-crossattn",
        f"{ROOT}/configs/visienhance_s2_planA_256_v7_crossattn_hpc.yaml",
        f"{ROOT}/checkpoints/visienhance/stage2_planA_256_v7_crossattn/best_visienhance.pth")


def main():
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    vs = M.load_visiscore(device)
    res = M.eval_one(*PAIR, vs, device)
    Path("results").mkdir(exist_ok=True)
    Path("results/e1_v7.json").write_text(json.dumps(res, indent=2))
    gate = "PASS" if res["psnr_perimg_enh"] >= 30 else "FAIL (red line!)"
    print(f"\n=== E1 v7 gate: per-image PSNR {res['psnr_perimg_enh']} -> {gate}  SSIM {res['ssim_enh']} ===")
    print("saved -> results/e1_v7.json")


if __name__ == "__main__":
    main()
