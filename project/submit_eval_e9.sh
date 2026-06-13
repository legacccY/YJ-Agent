#!/bin/bash
#SBATCH --job-name=e9_eval
#SBATCH --account=shuihuawang
#SBATCH --partition=gpu4090
#SBATCH --qos=4gpus
#SBATCH --nodes=1
#SBATCH --cpus-per-task=8
#SBATCH --gres=gpu:1
#SBATCH --time=01:00:00
#SBATCH --output=/gpfs/work/bio/jiayu2403/visienhance/logs/%j.out
#SBATCH --error=/gpfs/work/bio/jiayu2403/visienhance/logs/%j.err

# E9 core ablation: FiLM (v5 DP) vs CrossAttn (v7 DP), one paired GPU job.
# The single variable is the conditioning mechanism (both are DP-Loss Stage2).
# per-model rows give same-protocol 1:1 dAUC/consist/KL/dflip; paired bootstrap gives
# crossattn-vs-FiLM ΔAUC/ΔKL significance. Pull results/stage2_diag_paired.csv -> *_e9.csv.

PY="/gpfs/work/bio/jiayu2403/.conda/envs/yjcu124py310/bin/python3.10"
HPC_BASE="/gpfs/work/bio/jiayu2403/visienhance"
export OMP_NUM_THREADS=4
cd "$HPC_BASE/code"

echo "=== E9 EVAL (FiLM v5 vs CrossAttn v7) Job $SLURM_JOB_ID Node $SLURMD_NODENAME Start $(date) ==="
$PY run_eval_hpc_e9.py
echo "  E9 exit=$?"
echo "=== E9 EVAL done $(date) ==="
