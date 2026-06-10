"""HPC E5 launcher for v6 mask-L1. Same as run_e5_hpc.py but points CKPT at the v6
checkpoint and writes results/e5_salvage_v6{,_persample}.csv (keeps v5 baseline intact).
v6 == v5 model architecture (only the training loss differs: mask-weighted L1), so the
same CFG/load path is correct. cwd=code/."""
import sys
sys.path.insert(0, ".")

import eval_e5_salvage as M

ROOT = "/gpfs/work/bio/jiayu2403/visienhance"
M.ROOT      = ROOT
M.LABELS    = f"{ROOT}/data/quality_labels_nocrop_hpc.csv"
M.SPLIT     = f"{ROOT}/data/isic_split.csv"
M.META      = f"{ROOT}/data/train-metadata.csv"
M.VISISCORE = f"{ROOT}/checkpoints/best_visiscore.pth"
M.B3        = f"{ROOT}/checkpoints/efficientnet_b3_isic.pth"
M.CKPT_V5   = f"{ROOT}/checkpoints/visienhance/stage2_planA_256_v6_maskL1/best_visienhance.pth"
M.OUT_SUFFIX = "_v6"

M.main()
