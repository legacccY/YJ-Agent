#!/bin/bash
#SBATCH --job-name=v7_eval
#SBATCH --account=shuihuawang
#SBATCH --partition=gpu4090
#SBATCH --qos=4gpus
#SBATCH --nodes=1
#SBATCH --cpus-per-task=8
#SBATCH --gres=gpu:1
#SBATCH --time=01:00:00
#SBATCH --output=/gpfs/work/bio/jiayu2403/visienhance/logs/%j.out
#SBATCH --error=/gpfs/work/bio/jiayu2403/visienhance/logs/%j.err

# E9 crossattn re-eval (job 1444849 trained, best_val_PSNR 30.184). Two steps only:
# E1 gate + E3/E7 paired diag. NO dflip/E5 (those are the mask-L1/v6 line; E9 = FiLM vs
# crossattn conditioning, judged on PSNR fidelity + diagnosis preservation). Run AFTER
# best_visienhance.pth exists in checkpoints/visienhance/stage2_planA_256_v7_crossattn/.
# Pull results/stage2_diag_paired.csv -> stage2_diag_paired_v7.csv locally.

PY="/gpfs/work/bio/jiayu2403/.conda/envs/yjcu124py310/bin/python3.10"
HPC_BASE="/gpfs/work/bio/jiayu2403/visienhance"
export OMP_NUM_THREADS=4
cd "$HPC_BASE/code"

echo "=== v7 EVAL Job $SLURM_JOB_ID Node $SLURMD_NODENAME Start $(date) ==="

echo "--- [1/2] E1 gate per-image PSNR/SSIM (v7 crossattn) ---"
$PY run_e1_hpc_v7.py
echo "  E1 exit=$?"

echo "--- [2/2] E3/E7 paired diag (v7 crossattn vs Stage1 FiLM) ---"
$PY run_eval_hpc_v7.py
echo "  E3/E7 exit=$?"

echo "=== v7 EVAL done $(date) ==="
