#!/bin/bash
#SBATCH --job-name=selinf_a3
#SBATCH --partition=gpu4090
#SBATCH --qos=4gpus
#SBATCH --gres=gpu:1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=32G
#SBATCH --time=04:00:00
#SBATCH --account=shuihuawang
#SBATCH --output=/gpfs/work/bio/jiayu2403/selinf/logs/a3_%j.out
#SBATCH --error=/gpfs/work/bio/jiayu2403/selinf/logs/a3_%j.out

# ── SelInfBench A3 HPC 提交脚本 ──────────────────────────────────────────────
# workdir: /gpfs/work/bio/jiayu2403/selinf/
# conda:   yjcu124py310 (torch 2.6.0+cu124, sklearn 1.7.1)
# 主线上传清单（上传到 HPC 前必传）：
#   selinf_a3_truthproxy.py  → /gpfs/work/bio/jiayu2403/selinf/
#   ISIC_2020_Training_GroundTruth_v2.csv → /gpfs/work/bio/jiayu2403/selinf/data/
#   isic_split.csv           → /gpfs/work/bio/jiayu2403/selinf/data/
# ─────────────────────────────────────────────────────────────────────────────

PYTHON=/gpfs/work/bio/jiayu2403/.conda/envs/yjcu124py310/bin/python
WORKDIR=/gpfs/work/bio/jiayu2403/selinf
DATA_DIR=${WORKDIR}/data

# 确保 logs/ 和 results/ 目录存在
mkdir -p ${WORKDIR}/logs
mkdir -p ${WORKDIR}/results

cd ${WORKDIR}

echo "=== SLURM job ${SLURM_JOB_ID} started at $(date) ==="
echo "    Node: ${SLURMD_NODENAME}  GPU: ${CUDA_VISIBLE_DEVICES}"

${PYTHON} -u ${WORKDIR}/selinf_a3_truthproxy.py \
    --benchmarks ISIC2020,BraTS2021,HAM10000 \
    --m_values 18 \
    --isic_img_dir /gpfs/work/bio/jiayu2403/visienhance/data/isic2020 \
    --isic_gt_csv  ${DATA_DIR}/ISIC_2020_Training_GroundTruth_v2.csv \
    --isic_split_csv ${DATA_DIR}/isic_split.csv \
    --ham_root     /gpfs/work/bio/jiayu2403/ideation_run002/data/ham10000 \
    --brats_test_dir /gpfs/work/bio/jiayu2403/medad-failmap/data/BraTS2021/test \
    --out_dir      ${WORKDIR}/results

echo "=== job ${SLURM_JOB_ID} finished at $(date) ==="
