"""HPC launcher for eval_e2_perdim (E2 单维度降质 PSNR).

把本地路径常量覆盖为 GPFS 路径, 再调 main().
cwd 必须是 code/ (HPC job script 中已 cd).
"""
import sys
sys.path.insert(0, ".")

import eval_e2_perdim as M

ROOT = "/gpfs/work/bio/jiayu2403/visienhance"
M.LABELS    = f"{ROOT}/data/quality_labels_nocrop_hpc.csv"
M.SPLIT     = f"{ROOT}/data/isic_split.csv"
M.META      = f"{ROOT}/data/train-metadata.csv"
M.VISISCORE = f"{ROOT}/checkpoints/best_visiscore.pth"
M.B3        = f"{ROOT}/checkpoints/efficientnet_b3_isic.pth"
M.CKPT_V5   = f"{ROOT}/checkpoints/visienhance/stage2_planA_256_v5/best_visienhance.pth"

M.main()
