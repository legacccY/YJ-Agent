#!/bin/bash
# sb_B0.sh — 腿① 闸：B0 全背景基线，出 BraTS+Hippo dice_bg/σ_bg（不训练，短）。
#SBATCH --account=shuihuawang
#SBATCH --partition=gpu4090
#SBATCH --qos=4gpus
#SBATCH --gres=gpu:rtx4090:1
#SBATCH --cpus-per-task=8
#SBATCH --time=00:20:00
#SBATCH --job-name=pm_B0
#SBATCH --output=/gpfs/work/bio/jiayu2403/run003/phasemap/logs/%x_%j.out
#SBATCH --error=/gpfs/work/bio/jiayu2403/run003/phasemap/logs/%x_%j.err

PY=/gpfs/work/bio/jiayu2403/.conda/envs/yjcu124py310/bin/python
PM=/gpfs/work/bio/jiayu2403/run003/phasemap
export MEDNCA_ROOT=/gpfs/work/bio/jiayu2403/run003/mednca
export BRATS_ROOT=${PM}/data/brats_test
export PHASEMAP_OUT=${PM}
export CUDA_VISIBLE_DEVICES=0
mkdir -p ${PM}/logs ${PM}/results
cd ${PM}
echo "[B0] host=$(hostname) start=$(date)"
${PY} B0_baseline.py >> ${PM}/logs/B0.log 2>&1
echo "[B0] exit=$? done=$(date)"
echo "===== B0_baseline.csv ====="
cat ${PM}/results/B0_baseline.csv 2>/dev/null
