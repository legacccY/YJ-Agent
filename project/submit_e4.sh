#!/bin/bash
#SBATCH --job-name=e4_prop3
#SBATCH --account=shuihuawang
#SBATCH --partition=gpu4090
#SBATCH --qos=4gpus
#SBATCH --nodes=1
#SBATCH --cpus-per-task=8
#SBATCH --gres=gpu:1
#SBATCH --time=00:30:00
#SBATCH --output=/gpfs/work/bio/jiayu2403/visienhance/logs/%j.out
#SBATCH --error=/gpfs/work/bio/jiayu2403/visienhance/logs/%j.err

# E4 (Prop 3): entropy-q̄ |rho| should increase after enhancement. v5 FiLM DP.
# 本地 laptop GPU 跑不动 VisiEnhance convT (cuDNN engine / illegal-mem) -> HPC.
PY="/gpfs/work/bio/jiayu2403/.conda/envs/yjcu124py310/bin/python3.10"
BASE="/gpfs/work/bio/jiayu2403/visienhance"
export OMP_NUM_THREADS=4
cd "$BASE/code"
echo "=== E4 job $SLURM_JOB_ID $(date) ==="
$PY eval_visienhance.py \
  --config "$BASE/configs/visienhance_s2_planA_256_v5_hpc.yaml" \
  --ckpt   "$BASE/checkpoints/visienhance/stage2_planA_256_v5/best_visienhance.pth" \
  --b3-ckpt "$BASE/checkpoints/efficientnet_b3_isic.pth" \
  --exp E4
echo "=== done $(date) ==="
