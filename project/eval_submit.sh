#!/bin/bash
#SBATCH --job-name=visi_eval
#SBATCH --account=shuihuawang
#SBATCH --partition=gpu4090
#SBATCH --qos=4gpus
#SBATCH --nodes=1
#SBATCH --cpus-per-task=8
#SBATCH --gres=gpu:1
#SBATCH --time=02:00:00
#SBATCH --output=/gpfs/work/bio/jiayu2403/visienhance/logs/%j.out
#SBATCH --error=/gpfs/work/bio/jiayu2403/visienhance/logs/%j.err

PY="/gpfs/work/bio/jiayu2403/.conda/envs/yjcu124py310/bin/python3.10"
HPC_BASE="/gpfs/work/bio/jiayu2403/visienhance"
export OMP_NUM_THREADS=4

echo "=== VisiEnhance EVAL (E3/E7 paired) Job $SLURM_JOB_ID Node $SLURMD_NODENAME Start $(date) ==="
cd "$HPC_BASE/code"
$PY run_eval_hpc.py
echo "=== done exit=$? $(date) ==="
