#!/bin/bash
#SBATCH --job-name=v6_eval
#SBATCH --account=shuihuawang
#SBATCH --partition=gpu4090
#SBATCH --qos=4gpus
#SBATCH --nodes=1
#SBATCH --cpus-per-task=8
#SBATCH --gres=gpu:1
#SBATCH --time=01:00:00
#SBATCH --output=/gpfs/work/bio/jiayu2403/visienhance/logs/%j.out
#SBATCH --error=/gpfs/work/bio/jiayu2403/visienhance/logs/%j.err

# v6 mask-L1 re-eval: E3/E7 paired diag + dflip dump + E5 salvage, one GPU job.
# Run AFTER job 1442696 (v6 training) finishes and best_visienhance.pth exists in
# checkpoints/visienhance/stage2_planA_256_v6_maskL1/. Pull stage2_diag_paired.csv and
# dflip_persample.csv to *_v6 locally (会话 20/21 convention); e5_salvage_v6 is already
# suffixed by run_e5_hpc_v6.py.

PY="/gpfs/work/bio/jiayu2403/.conda/envs/yjcu124py310/bin/python3.10"
HPC_BASE="/gpfs/work/bio/jiayu2403/visienhance"
export OMP_NUM_THREADS=4
cd "$HPC_BASE/code"

echo "=== v6 EVAL Job $SLURM_JOB_ID Node $SLURMD_NODENAME Start $(date) ==="

echo "--- [1/4] E1 gate per-image PSNR/SSIM (v6) ---"
$PY run_e1_hpc_v6.py
echo "  E1 exit=$?"

echo "--- [2/4] E3/E7 paired diag (v6) ---"
$PY run_eval_hpc_v6.py
echo "  E3 exit=$?"

echo "--- [3/4] dflip dump (v6) ---"
$PY run_dflip_hpc_v6.py
echo "  dflip exit=$?"

echo "--- [4/4] E5 salvage (v6) ---"
$PY run_e5_hpc_v6.py
echo "  E5 exit=$?"

echo "=== v6 EVAL done $(date) ==="
