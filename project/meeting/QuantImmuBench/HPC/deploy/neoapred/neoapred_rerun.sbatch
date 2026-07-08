#!/bin/bash
#SBATCH --job-name=neoa_rerun
#SBATCH --partition=gpu4090
#SBATCH --account=shuihuawang
#SBATCH --qos=4gpus
#SBATCH --gres=gpu:1
#SBATCH --cpus-per-task=16
#SBATCH --mem=64G
#SBATCH --time=24:00:00
#SBATCH --output=/gpfs/work/bio/jiayu2403/quantimmu/neoapred_hpc/logs/rerun_%j.out
#SBATCH --error=/gpfs/work/bio/jiayu2403/quantimmu/neoapred_hpc/logs/rerun_%j.err
# =============================================================================
# neoapred_rerun.sbatch — NeoaPred 改动②/③ 全量重跑（gpu4090 节点, CPU-only OpenMM 弛豫）
# 克隆自 neoapred_full.sbatch：partition gpu3090→gpu4090（用户拍板只用 gpu4090）；
# 输入指向 rerun/neoapred_rerun/neoapred_input.csv（3684 unique 9mer, 改动②窗数恒定=9）。
# ⚠️ 占 1 GPU 卡仅为拿节点 CPU（NeoaPred 不用 GPU）；经 gpu_slot 调度，绝不挤正在跑的。
# =============================================================================
set -o pipefail
WORK=/gpfs/work/bio/jiayu2403/quantimmu/neoapred_hpc
HERE=${WORK}/deploy
RERUN=/gpfs/work/bio/jiayu2403/quantimmu/rerun/neoapred_rerun
mkdir -p ${WORK}/logs ${RERUN}

echo "[sbatch] node=$(hostname) start=$(date)"
source /etc/profile.d/modules.sh 2>/dev/null || source /usr/share/Modules/init/bash 2>/dev/null || true
module load singularityce/3.11.4-gcc-8.5.0-jgr6oam 2>&1 || echo "[sbatch] WARN module load 失败"
echo "[sbatch] singularity = $(command -v singularity || echo NOT_FOUND)"

bash ${HERE}/run_neoapred_hpc_full.sh \
  ${RERUN}/neoapred_input.csv \
  ${RERUN}/full \
  8 2
echo "[sbatch] end=$(date)"
