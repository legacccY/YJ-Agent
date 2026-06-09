"""HPC launcher: patch 路径常量为 GPFS, 再跑 dflip 数据落盘.

顺序: 先 import eval_stage2_compare 并改其模块属性 (LABELS/CKPTS/...),
再 import dump_dflip_figure_data (它顶层从 eval_stage2_compare as E 取常量, 此时已 patch).
镜像本地配置: S1=stage1_planA_nocrop, S2=stage2_planA_256_v5 (feature-DP). cwd 必须 = code/.
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
    "Stage1 (no DP)":   f"{ROOT}/checkpoints/visienhance/stage1_planA_nocrop/best_visienhance.pth",
    "Stage2 (DP, v5)":  f"{ROOT}/checkpoints/visienhance/stage2_planA_256_v5/best_visienhance.pth",
}

import dump_dflip_figure_data as D
D.main()
