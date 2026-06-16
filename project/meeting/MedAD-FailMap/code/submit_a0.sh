#!/bin/bash
# MedAD-FailMap Phase 0 — A0: BraTS2021 AE 训练 (PC-A 地基)
# 提交: sbatch code/submit_a0.sh  (在 /gpfs/work/bio/jiayu2403/medad-failmap/ 下)
# 复现零偏离: MedIAnomaly 官方超参 (epochs=250/bs=64/lr=1e-3/latent=16/L2)
#SBATCH --job-name=medad_a0_ae
#SBATCH --account=shuihuawang
#SBATCH --partition=gpu4090
#SBATCH --qos=4gpus
#SBATCH --gres=gpu:rtx4090:1
#SBATCH --cpus-per-task=8
#SBATCH --time=02:00:00
#SBATCH --output=/gpfs/work/bio/jiayu2403/medad-failmap/logs/a0_ae_%j.out
#SBATCH --error=/gpfs/work/bio/jiayu2403/medad-failmap/logs/a0_ae_%j.err

ROOT=/gpfs/work/bio/jiayu2403/medad-failmap
PY=/gpfs/work/bio/jiayu2403/.conda/envs/yjcu124py310/bin/python
cd $ROOT
echo "[A0] start=$(date) node=$(hostname)"
nvidia-smi --query-gpu=name,memory.total --format=csv,noheader
$PY code/train_recon_ae.py -d brats -m ae --data-root data --out-dir results -g 0 --num-workers 8
echo "[A0] done=$(date)"
echo "===== anomaly score csv 头部 ====="
head -3 $ROOT/results/anomaly_scores_brats_ae.csv
