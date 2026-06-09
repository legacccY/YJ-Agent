"""HPC qnorm 对照 launcher: 覆盖 eval_qnorm_compare 路径常量为 GPFS 后调 main(). cwd=code/."""
import sys
sys.path.insert(0, ".")

import eval_qnorm_compare as M

ROOT = "/gpfs/work/bio/jiayu2403/visienhance"
M.ROOT      = ROOT
M.LABELS    = f"{ROOT}/data/quality_labels_nocrop_hpc.csv"
M.SPLIT     = f"{ROOT}/data/isic_split.csv"
M.META      = f"{ROOT}/data/train-metadata.csv"
M.VISISCORE = f"{ROOT}/checkpoints/best_visiscore.pth"
M.B3        = f"{ROOT}/checkpoints/efficientnet_b3_isic.pth"
M.CKPT_V5   = f"{ROOT}/checkpoints/visienhance/stage2_planA_256_v5/best_visienhance.pth"

M.main()
