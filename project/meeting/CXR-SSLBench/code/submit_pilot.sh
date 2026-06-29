#!/bin/bash
#SBATCH --job-name=cxrssl_pilot
#SBATCH --partition=gpu4090
#SBATCH --qos=4gpus
#SBATCH --account=shuihuawang
#SBATCH --gres=gpu:1
#SBATCH --cpus-per-task=8
#SBATCH --mem=48G
#SBATCH --time=04:00:00
#SBATCH --output=/gpfs/work/bio/jiayu2403/cxr-sslbench/logs/pilot_%j.out
#SBATCH --error=/gpfs/work/bio/jiayu2403/cxr-sslbench/logs/pilot_%j.err

set -e
ENV=/gpfs/work/bio/jiayu2403/.conda/envs/yjcu124py310
CODE=/gpfs/work/bio/jiayu2403/cxr-sslbench/code
cd $CODE

# compute 节点无外网 → 离线读 DTN 预下的 HF/timm 缓存
export HF_HUB_OFFLINE=1
export TRANSFORMERS_OFFLINE=1
export HF_HOME=$HOME/.cache/huggingface

echo "[$(date)] node=$(hostname) gpu=$(nvidia-smi --query-gpu=name --format=csv,noheader)"
$ENV/bin/python -c "import torch; print('cuda', torch.cuda.is_available(), torch.cuda.get_device_name(0))"

# 多范式 linear probe (pooled, 磁盘安全) 1/10/100% on NIH
# backbones 由提交时第1参数传入(默认全 4 个)；缺权重的 backbone run_pilot 自动 SKIP
BACKBONES="${1:-chexworld medical_mae rad_dino imagenet_sup_vitb}"
echo "[backbones] $BACKBONES"

$ENV/bin/python run_pilot.py \
  --backbones $BACKBONES \
  --label_fracs 1 10 100 \
  --probes linear \
  --domain nih \
  --device cuda \
  --batch_size 128 \
  --num_workers 8 \
  --out_csv /gpfs/work/bio/jiayu2403/cxr-sslbench/results/pilot_hpc.csv

echo "[$(date)] === RESULT CSV ==="
cat /gpfs/work/bio/jiayu2403/cxr-sslbench/results/pilot_hpc.csv
echo "[$(date)] DONE"
