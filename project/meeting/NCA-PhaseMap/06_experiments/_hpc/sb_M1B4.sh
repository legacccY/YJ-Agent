#!/bin/bash
# sb_M1B4.sh — 腿③ M1 传播半径探针（纯前向）+ 腿①-b B4 第二独立实现（Hippo）。
#SBATCH --account=shuihuawang
#SBATCH --partition=gpu4090
#SBATCH --qos=4gpus
#SBATCH --gres=gpu:rtx4090:1
#SBATCH --cpus-per-task=8
#SBATCH --time=01:30:00
#SBATCH --job-name=pm_M1B4
#SBATCH --output=/gpfs/work/bio/jiayu2403/run003/phasemap/logs/%x_%j.out
#SBATCH --error=/gpfs/work/bio/jiayu2403/run003/phasemap/logs/%x_%j.err

PY=/gpfs/work/bio/jiayu2403/.conda/envs/yjcu124py310/bin/python
PM=/gpfs/work/bio/jiayu2403/run003/phasemap
export MEDNCA_ROOT=/gpfs/work/bio/jiayu2403/run003/mednca
export PHASEMAP_OUT=${PM}
export CUDA_VISIBLE_DEVICES=0
mkdir -p ${PM}/logs ${PM}/results
cd ${PM}
echo "[M1B4] host=$(hostname) start=$(date)"
echo "[M1] start"
${PY} M1_probe.py >> ${PM}/logs/M1.log 2>&1
echo "[M1] exit=$?"
echo "[B4] start (Hippo dice_bg≈0 默认阈 0.01)"
${PY} B4_impl2.py >> ${PM}/logs/B4.log 2>&1
echo "[B4] exit=$?"
echo "[M1B4] done=$(date)"
ls -lh ${PM}/results/M1_probe.csv ${PM}/results/B4_impl2.csv 2>/dev/null
