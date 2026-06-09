"""HPC E12 launcher: 覆盖 eval_e12_speed 路径常量为 GPFS 后调 main(). cwd=code/."""
import sys
sys.path.insert(0, ".")

import eval_e12_speed as M

ROOT = "/gpfs/work/bio/jiayu2403/visienhance"
M.VISISCORE = f"{ROOT}/checkpoints/best_visiscore.pth"
M.CKPT_V5   = f"{ROOT}/checkpoints/visienhance/stage2_planA_256_v5/best_visienhance.pth"

M.main()
