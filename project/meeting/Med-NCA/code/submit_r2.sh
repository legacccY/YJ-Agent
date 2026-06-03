#!/bin/bash
#SBATCH --job-name=mednca_r2_isic
#SBATCH --partition=gpu4090
#SBATCH --account=shuihuawang
#SBATCH --qos=4gpus
#SBATCH --gres=gpu:1
#SBATCH --cpus-per-task=8
#SBATCH --mem=32G
#SBATCH --time=24:00:00
#SBATCH --output=/gpfs/work/bio/jiayu2403/mednca/logs/r2_%j.out
#SBATCH --error=/gpfs/work/bio/jiayu2403/mednca/logs/r2_%j.err

# ---- 环境变量 -------------------------------------------------------
export MEDNCA_ROOT=/gpfs/work/bio/jiayu2403/mednca
export R2_EPOCHS=300
export KMP_DUPLICATE_LIB_OK=TRUE
export CUDA_VISIBLE_DEVICES=0

# ---- 绝对路径 Python（血泪：SLURM 里 source activate 不生效）--------
PYTHON=/gpfs/work/bio/jiayu2403/.conda/envs/yjcu124py310/bin/python

# ---- 确保 logs 目录存在 ---------------------------------------------
mkdir -p ${MEDNCA_ROOT}/logs

echo "[submit_r2] job=${SLURM_JOB_ID}  node=${SLURMD_NODENAME}"
echo "[submit_r2] MEDNCA_ROOT=${MEDNCA_ROOT}"
echo "[submit_r2] R2_EPOCHS=${R2_EPOCHS}"
echo "[submit_r2] python=$(${PYTHON} --version)"
nvidia-smi --query-gpu=name,memory.total --format=csv,noheader

${PYTHON} ${MEDNCA_ROOT}/code/run_r2_isic.py
