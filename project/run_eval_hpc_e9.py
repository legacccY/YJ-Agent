"""E9 核心对比 (HPC GPU): FiLM (v5 DP Stage2) vs CrossAttn (v7 DP Stage2).

这才是 E9 的真正消融——两者都是 DP-Loss Stage2、唯一变量 = quality-conditioning
机制 (FiLM vs cross-attention)。run_eval_hpc_v7.py 比的是 crossattn vs Stage1(no-DP)，
那等于 E7 复制；E9 要的是 crossattn vs FiLM 同口径 paired 显著性。

names[0]=FiLM, names[1]=CrossAttn -> paired ΔAUC/ΔKL = crossattn − film。若 CI 含 0 =>
两机制无显著差异 (FiLM 以 parsimony 胜，少 1.8M 参数)。per-model 行给 1:1 同口径
dAUC/一致率/KL/dflip (红线 4: 不用约值)。CFG_MAP 让每 ckpt 用自己的 conditioning 构建。
Produces results/stage2_diag_paired.csv -> pull to *_e9.csv. cwd=code/.
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

FILM_NAME = "FiLM (v5 DP)"
CA_NAME = "CrossAttn (v7 DP)"
E.CKPTS = {
    FILM_NAME: f"{ROOT}/checkpoints/visienhance/stage2_planA_256_v5/best_visienhance.pth",
    CA_NAME:   f"{ROOT}/checkpoints/visienhance/stage2_planA_256_v7_crossattn/best_visienhance.pth",
}

CFG_FILM = OmegaConf.load(f"{ROOT}/configs/visienhance_s2_planA_256_v5_hpc.yaml")
CFG_CA = OmegaConf.load(f"{ROOT}/configs/visienhance_s2_planA_256_v7_crossattn_hpc.yaml")

import eval_diag_paired as P
P.CFG_MAP = {FILM_NAME: CFG_FILM, CA_NAME: CFG_CA}
P.main()
