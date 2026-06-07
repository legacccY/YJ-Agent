#!/bin/bash
#SBATCH --job-name=probe_feat
#SBATCH --account=shuihuawang
#SBATCH --partition=gpu4090
#SBATCH --qos=4gpus
#SBATCH --nodes=1
#SBATCH --cpus-per-task=4
#SBATCH --gres=gpu:1
#SBATCH --time=00:20:00
#SBATCH --output=/gpfs/work/bio/jiayu2403/visienhance/logs/%j.out
#SBATCH --error=/gpfs/work/bio/jiayu2403/visienhance/logs/%j.err

PYTHON="/gpfs/work/bio/jiayu2403/.conda/envs/yjcu124py310/bin/python3.10"
HPC_BASE="/gpfs/work/bio/jiayu2403/visienhance"
export OMP_NUM_THREADS=4
export KMP_DUPLICATE_LIB_OK=TRUE

echo "=== feature-DP probe (v5 calibration + HPC smoke) Job $SLURM_JOB_ID Node $SLURMD_NODENAME $(date) ==="
cd "$HPC_BASE/code"
$PYTHON scripts/probe_feat_dp.py \
  --config "$HPC_BASE/configs/visienhance_s2_planA_256_v5_hpc.yaml" \
  --n-batches 200
echo "=== done exit=$? $(date) ==="
