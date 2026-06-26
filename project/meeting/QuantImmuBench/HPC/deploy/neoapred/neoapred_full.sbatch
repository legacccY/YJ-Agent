#!/bin/bash
#SBATCH --job-name=neoa_full
#SBATCH --partition=gpu3090
#SBATCH --account=shuihuawang
#SBATCH --qos=4gpus
#SBATCH --gres=gpu:1
#SBATCH --cpus-per-task=16
#SBATCH --mem=64G
#SBATCH --time=24:00:00
#SBATCH --output=/gpfs/work/bio/jiayu2403/quantimmu/neoapred_hpc/logs/%j.out
#SBATCH --error=/gpfs/work/bio/jiayu2403/quantimmu/neoapred_hpc/logs/%j.err
# =============================================================================
# NeoaPred 全量 SLURM 作业（gpu4090 节点 48核/257GB，CPU-only OpenMM 弛豫）
# ⚠️ 占 1 GPU 卡仅为拿 gpu4090 节点的 48 CPU（NeoaPred 不用 GPU）；经 gpu_slot 调度。
# 全量 5692 严格 9mer → 11384 OpenMM 弛豫。本地 ~60h 不可行（内存带宽限并行）→ HPC。
# =============================================================================
set -o pipefail   # 不用 -u：source module init 会撞未绑定变量直接退出
WORK=/gpfs/work/bio/jiayu2403/quantimmu/neoapred_hpc
HERE=${WORK}/deploy
mkdir -p ${WORK}/logs

echo "[sbatch] node=$(hostname) start=$(date)"
# 计算节点 singularity 不在 PATH，必须 module load（登录节点 /usr/bin/singularity 不传到计算节点）
source /etc/profile.d/modules.sh 2>/dev/null || source /usr/share/Modules/init/bash 2>/dev/null || true
module load singularityce/3.11.4-gcc-8.5.0-jgr6oam 2>&1 || echo "[sbatch] WARN module load 失败"
echo "[sbatch] singularity = $(command -v singularity || echo NOT_FOUND)"

bash ${HERE}/run_neoapred_hpc_full.sh \
  ${WORK}/neoapred_input.csv \
  ${WORK}/full \
  8 2
echo "[sbatch] end=$(date)"
