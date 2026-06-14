#!/bin/bash
#SBATCH --job-name=e4q_prop3
#SBATCH --account=shuihuawang
#SBATCH --partition=gpu4090
#SBATCH --qos=4gpus
#SBATCH --nodes=1
#SBATCH --cpus-per-task=8
#SBATCH --gres=gpu:1
#SBATCH --time=00:30:00
#SBATCH --output=/gpfs/work/bio/jiayu2403/visienhance/logs/%j.out
#SBATCH --error=/gpfs/work/bio/jiayu2403/visienhance/logs/%j.err

# E4Q (Prop 3, Q-VIB variant): retest entropy-q̄ |rho| using Q-VIB Full's
# quality-conditioned predictive entropy instead of unrelated B3 (which
# saturated at ln2 in job1449036). v5 FiLM DP ckpt.
PY="/gpfs/work/bio/jiayu2403/.conda/envs/yjcu124py310/bin/python3.10"
BASE="/gpfs/work/bio/jiayu2403/visienhance"
export OMP_NUM_THREADS=4
cd "$BASE/code"
echo "=== E4Q job $SLURM_JOB_ID $(date) ==="
$PY eval_visienhance.py \
  --config "$BASE/configs/visienhance_s2_planA_256_v5_hpc.yaml" \
  --ckpt   "$BASE/checkpoints/visienhance/stage2_planA_256_v5/best_visienhance.pth" \
  --qad-ckpt "$BASE/checkpoints/efnet/best_qad.pth" \
  --exp E4Q
echo "=== done $(date) ==="
