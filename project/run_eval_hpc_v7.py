"""HPC eval launcher (E3/E7) for v7 crossattn (E9). Mirrors run_eval_hpc_v6.py BUT
Stage1=FiLM, Stage2=crossattn -> two different architectures in ONE paired job.
Sets eval_diag_paired.CFG_MAP so each ckpt is built with its own conditioning
(FiLM for Stage1, crossattn for Stage2). Without it, the single shared CFG would
build a FiLM net for the crossattn ckpt -> all CrossAttnConditioning keys missing.

Produces results/stage2_diag_paired.csv (generic) — pull to *_v7.csv (会话 20 convention).
Order matters: set E.* BEFORE importing eval_diag_paired (it binds names at import). cwd=code/.
"""
import sys
sys.path.insert(0, ".")

from omegaconf import OmegaConf

import eval_stage2_compare as E

ROOT = "/gpfs/work/bio/jiayu2403/visienhance"
E.LABELS = f"{ROOT}/data/quality_labels_nocrop_hpc.csv"
E.SPLIT = f"{ROOT}/data/isic_split.csv"
E.META = f"{ROOT}/data/train-metadata.csv"
E.VISISCORE = f"{ROOT}/checkpoints/best_visiscore.pth"
E.B3 = f"{ROOT}/checkpoints/efficientnet_b3_isic.pth"

S1_NAME = "Stage1 (no DP)"
S2_NAME = "Stage2 (v7 crossattn)"
E.CKPTS = {
    S1_NAME: f"{ROOT}/checkpoints/visienhance/stage1_planA_256/best_visienhance.pth",
    S2_NAME: f"{ROOT}/checkpoints/visienhance/stage2_planA_256_v7_crossattn/best_visienhance.pth",
}

# per-ckpt config: Stage1 = FiLM, Stage2 = crossattn (the single variable for E9)
CFG_S1 = OmegaConf.load(f"{ROOT}/configs/visienhance_s1_planA_256_hpc.yaml")
CFG_S2 = OmegaConf.load(f"{ROOT}/configs/visienhance_s2_planA_256_v7_crossattn_hpc.yaml")

import eval_diag_paired as P
P.CFG_MAP = {S1_NAME: CFG_S1, S2_NAME: CFG_S2}
P.main()
