"""HPC eval launcher: patch eval_stage2_compare 路径常量为 GPFS, 再跑 paired diag (E3/E7).

顺序关键: 先 import eval_stage2_compare 并改其模块属性, 再 import eval_diag_paired
(它顶层 from-import 此时读到的是 patch 后的值). cwd 必须 = code/.
"""
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
    "Stage2 (DP)":    f"{ROOT}/checkpoints/visienhance/stage2_planA_256/best_visienhance.pth",
}

import eval_diag_paired as P
P.main()
