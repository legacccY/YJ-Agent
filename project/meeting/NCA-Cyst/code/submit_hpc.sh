#!/bin/bash
#SBATCH --job-name=ncacyst1a
#SBATCH --partition=gpu4090
#SBATCH --qos=4gpus
#SBATCH --account=shuihuawang
#SBATCH --gres=gpu:1
#SBATCH --cpus-per-task=8
#SBATCH --time=24:00:00
#SBATCH --output=/gpfs/work/bio/jiayu2403/nca-cyst/logs/%j.out
#SBATCH --error=/gpfs/work/bio/jiayu2403/nca-cyst/logs/%j.err

# NCA-Cyst Phase 1a：官方二分类 full baseline，KiTS23 全 489 例，探发散。
# 轻配置（config full 默认 [10,10]/1000ep）。零偏离官方，无梯度裁剪。

export KITS23_ROOT=/gpfs/work/bio/jiayu2403/kits23/dataset
export M3DNCA_OFFICIAL_ROOT=/gpfs/work/bio/jiayu2403/mednca/M3D-NCA-official

PY=/gpfs/work/bio/jiayu2403/.conda/envs/yjcu124py310/bin/python
CODE=/gpfs/work/bio/jiayu2403/nca-cyst/code
RUN=/gpfs/work/bio/jiayu2403/nca-cyst/runs/full_binaryall_seed0

mkdir -p "$RUN"
cd "$CODE" || exit 1

echo "[submit] host=$(hostname) gpu=$CUDA_VISIBLE_DEVICES start=$(date)"
$PY train_kits23.py --config full --label_mode binary_all --seed 0 \
    --model_path "$RUN" \
    --state_path "$RUN/state.json"
echo "[submit] end=$(date) exit=$?"
