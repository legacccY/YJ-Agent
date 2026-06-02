#!/bin/bash
#SBATCH --job-name=probe_b3_dp
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

echo "=== B3 DP-Loss probe (Stage 2 v2 calibration + HPC smoke) ==="
echo "Job ID: $SLURM_JOB_ID  Node: $SLURMD_NODENAME  Start: $(date)"

export OMP_NUM_THREADS=4
export KMP_DUPLICATE_LIB_OK=TRUE

cd "$HPC_BASE/code"
$PYTHON scripts/probe_b3_dp.py \
  --config "$HPC_BASE/configs/visienhance_s2_planA_256_v2_hpc.yaml" \
  --n-batches 200

echo "=== done: $(date), exit_code=$? ==="
