#!/bin/bash
#SBATCH --job-name=ncacystU1c
#SBATCH --partition=gpu4090
#SBATCH --qos=4gpus
#SBATCH --account=shuihuawang
#SBATCH --gres=gpu:1
#SBATCH --cpus-per-task=8
#SBATCH --time=24:00:00
#SBATCH --output=/gpfs/work/bio/jiayu2403/nca-cyst/logs/%j.out
#SBATCH --error=/gpfs/work/bio/jiayu2403/nca-cyst/logs/%j.err

# NCA-Cyst Phase 1c：官方 UNet3D 同口径对照 full baseline，KiTS23 全 489 例。
# 与 M3D-NCA 完全同口径（同 Dataset_KiTS23_3D / 同 data_split[0.7,0,0.3] / 同 label_mode / 同 Dice 评估），
# 仅把模型换成官方 UNet3D。零偏离官方超参（lr=1e-4/betas(0.9,0.99)/DiceBCELoss/1000ep），无梯度裁剪。
#
# ⚠️ 依赖：本脚本 import `unet` pip 包（from unet import UNet3D），须先在 HPC DTN 上装：
#         pip install unet   （主线部署时先装，见 code/README.md Phase 1c 段）

export KITS23_ROOT=/gpfs/work/bio/jiayu2403/kits23/dataset
export M3DNCA_OFFICIAL_ROOT=/gpfs/work/bio/jiayu2403/mednca/M3D-NCA-official

PY=/gpfs/work/bio/jiayu2403/.conda/envs/yjcu124py310/bin/python
CODE=/gpfs/work/bio/jiayu2403/nca-cyst/code
RUN=/gpfs/work/bio/jiayu2403/nca-cyst/runs/unet_full_binaryall_seed0

mkdir -p "$RUN"
cd "$CODE" || exit 1

echo "[submit] host=$(hostname) gpu=$CUDA_VISIBLE_DEVICES start=$(date)"
$PY train_unet_kits23.py --config full --label_mode binary_all --seed 0 \
    --model_path "$RUN" \
    --state_path "$RUN/state.json"
echo "[submit] end=$(date) exit=$?"
