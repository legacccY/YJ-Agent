"""HPC eval launcher (E3/E7) for v6 mask-L1. Mirrors run_eval_hpc.py, Stage2 -> v6.
Produces results/stage2_diag_paired.csv (generic) — pull to *_v6.csv (see run_dflip_hpc.py
pattern, 会话 20 convention). Stage2 is positional [1] so key string is cosmetic. cwd=code/."""
import sys
sys.path.insert(0, ".")

import eval_stage2_compare as E

ROOT = "/gpfs/work/bio/jiayu2403/visienhance"
E.LABELS = f"{ROOT}/data/quality_labels_nocrop_hpc.csv"
E.SPLIT = f"{ROOT}/data/isic_split.csv"
E.META = f"{ROOT}/data/train-metadata.csv"
E.VISISCORE = f"{ROOT}/checkpoints/best_visiscore.pth"
E.B3 = f"{ROOT}/checkpoints/efficientnet_b3_isic.pth"
E.CKPTS = {
    "Stage1 (no DP)": f"{ROOT}/checkpoints/visienhance/stage1_planA_256/best_visienhance.pth",
    "Stage2 (v6 maskL1)": f"{ROOT}/checkpoints/visienhance/stage2_planA_256_v6_maskL1/best_visienhance.pth",
}

import eval_diag_paired as P
P.main()
