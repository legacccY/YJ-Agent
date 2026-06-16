#!/bin/bash
# NCA-JEPA pilot 单臂训练。提交（A0 baseline）：
#   sbatch --export=ALL,ARM=a0,SEED=42 --job-name=ncaj_a0_s42 hpc/sbatch_pilot.sh
# A1/A2 多 seed：ARM=a1|a2，SEED=42|123|2024（每 seed 一个 job，qos 上限 4 卡可并行）
#SBATCH --account=shuihuawang
#SBATCH --partition=gpu4090
#SBATCH --qos=4gpus
#SBATCH --gres=gpu:rtx4090:1
#SBATCH --cpus-per-task=8
#SBATCH --time=08:00:00
#SBATCH --output=/gpfs/work/bio/jiayu2403/nca-jepa/logs/%x_%j.out
#SBATCH --error=/gpfs/work/bio/jiayu2403/nca-jepa/logs/%x_%j.err

ROOT=/gpfs/work/bio/jiayu2403/nca-jepa
PY=/gpfs/work/bio/jiayu2403/.conda/envs/yjcu124py310/bin/python
export EXP_LOG_ROOT=$ROOT/logs
ARM=${ARM:-a0}
SEED=${SEED:-42}

# ARM -> config 文件名映射
case "$ARM" in
  a0) CFG=configs/a0_vit_vits_nih10k.yaml ;;
  a1) CFG=configs/a1_vanilla_nca_vits_nih10k.yaml ;;
  a2) CFG=configs/a2_scp_nca_vits_nih10k.yaml ;;
  *)  echo "未知 ARM=$ARM"; exit 1 ;;
esac

cd $ROOT
echo "[pilot] host=$(hostname) ARM=$ARM SEED=$SEED CFG=$CFG start=$(date)"
$PY ijepa/main.py --fname $CFG --devices cuda:0 --seed $SEED
echo "[pilot] done=$(date)"
