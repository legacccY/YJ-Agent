#!/bin/bash
#SBATCH --job-name=prime_gpu
#SBATCH --partition=gpu4090
#SBATCH --account=shuihuawang
#SBATCH --qos=4gpus
#SBATCH --gres=gpu:1
#SBATCH --cpus-per-task=8
#SBATCH --mem=16G
#SBATCH --time=06:00:00
#SBATCH --output=/gpfs/work/bio/jiayu2403/quantimmu/rerun/logs/prime_gpu_%j.out
#SBATCH --error=/gpfs/work/bio/jiayu2403/quantimmu/rerun/logs/prime_gpu_%j.err
# =============================================================================
# run_prime_rerun_gpu.sbatch — PRIME rerun 改投 gpu4090 节点(CPU-only)
# 因 cpudebug 1h walltime 撞墙(41min 仅 13/26 allele)。gpu4090 4gpus qos 有 24h walltime。
# ⚠️ 占 1 GPU 卡仅为拿长 walltime + 节点 CPU(PRIME 不用 GPU)；经 gpu_slot(slot b09affcb)。
# 复用已上传的 run_prime_rerun.sh loop 体(内层 #SBATCH cpudebug 行在 bash 调用下=注释,忽略)。
# =============================================================================
echo "[sbatch] node=$(hostname) start=$(date)"
bash /gpfs/work/bio/jiayu2403/quantimmu/rerun/scripts/run_prime_rerun.sh
echo "[sbatch] end=$(date)"
