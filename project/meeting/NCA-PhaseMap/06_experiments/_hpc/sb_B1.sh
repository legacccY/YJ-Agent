#!/bin/bash
# sb_B1.sh — 腿① BraTS 粗扫 B1（9 ur × {no-clip,1.0} = 18 run）。需 B0 出的 DICE_BG_BRATS/SIGMA_BG_BRATS。
# 提交：sbatch --export=ALL,DICE_BG_BRATS=<v>,SIGMA_BG_BRATS=<v> sb_B1.sh
#SBATCH --account=shuihuawang
#SBATCH --partition=gpu4090
#SBATCH --qos=4gpus
#SBATCH --gres=gpu:rtx4090:1
#SBATCH --cpus-per-task=8
#SBATCH --time=02:00:00
#SBATCH --job-name=pm_B1
#SBATCH --output=/gpfs/work/bio/jiayu2403/run003/phasemap/logs/%x_%j.out
#SBATCH --error=/gpfs/work/bio/jiayu2403/run003/phasemap/logs/%x_%j.err

PY=/gpfs/work/bio/jiayu2403/.conda/envs/yjcu124py310/bin/python
PM=/gpfs/work/bio/jiayu2403/run003/phasemap
export MEDNCA_ROOT=/gpfs/work/bio/jiayu2403/run003/mednca
export BRATS_ROOT=${PM}/data/brats_test
export PHASEMAP_OUT=${PM}
export DICE_BG_BRATS=${DICE_BG_BRATS:-0.0}
export SIGMA_BG_BRATS=${SIGMA_BG_BRATS:-0.0}
export CUDA_VISIBLE_DEVICES=0
mkdir -p ${PM}/logs ${PM}/results
cd ${PM}
echo "[B1] host=$(hostname) start=$(date) DICE_BG_BRATS=${DICE_BG_BRATS} SIGMA=${SIGMA_BG_BRATS}"
${PY} B1_B2_B3_sweep.py --stage B1 >> ${PM}/logs/B1.log 2>&1
echo "[B1] exit=$? done=$(date)"
ls -lh ${PM}/results/B1_coarse.csv 2>/dev/null
