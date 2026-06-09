"""HPC E6 launcher: 把 eval_e6_severe 路径常量覆盖为 GPFS 后调 main().

模式与 run_eval_hpc.py 完全一致:
  import eval_e6_severe as M -> 逐个覆盖 M.XXX -> M.main()
cwd 必须 = code/（项目代码根目录）.
"""
import sys
sys.path.insert(0, ".")

import eval_e6_severe as M

ROOT = "/gpfs/work/bio/jiayu2403/visienhance"

M.ROOT      = ROOT
M.LABELS    = f"{ROOT}/data/quality_labels_nocrop_hpc.csv"
M.SPLIT     = f"{ROOT}/data/isic_split.csv"
M.META      = f"{ROOT}/data/train-metadata.csv"
M.VISISCORE = f"{ROOT}/checkpoints/best_visiscore.pth"
M.B3        = f"{ROOT}/checkpoints/efficientnet_b3_isic.pth"
M.CKPT_V5   = f"{ROOT}/checkpoints/visienhance/stage2_planA_256_v5/best_visienhance.pth"

M.main()
