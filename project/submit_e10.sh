#!/bin/bash
#SBATCH --job-name=e10_base
#SBATCH --account=shuihuawang
#SBATCH --partition=gpu4090
#SBATCH --qos=4gpus
#SBATCH --nodes=1
#SBATCH --cpus-per-task=8
#SBATCH --gres=gpu:1
#SBATCH --time=06:00:00
#SBATCH --output=/gpfs/work/bio/jiayu2403/visienhance/logs/%j.out
#SBATCH --error=/gpfs/work/bio/jiayu2403/visienhance/logs/%j.err

# E10: 6 非扩散 SOTA baseline zero-shot vs VisiEnhance v5, 一个 GPU job 串行跑 6 方法.
# 每方法: VisiEnhance v5(FiLM DP) vs baseline 严格 paired, per-image PSNR/SSIM + dAUC/
# dflip/KL + paired bootstrap(baseline-VE). 产出 results/e10_<method>.csv.
# 叙事: baseline PSNR 或有竞争力但无 DP 约束 -> dAUC/dflip 明显劣 -> 坐实卖点.

PY="/gpfs/work/bio/jiayu2403/.conda/envs/yjcu124py310/bin/python3.10"
HPC_BASE="/gpfs/work/bio/jiayu2403/visienhance"
export OMP_NUM_THREADS=4
cd "$HPC_BASE/code"

echo "=== E10 BASELINES Job $SLURM_JOB_ID Node $SLURMD_NODENAME Start $(date) ==="
for m in restormer nafnet mirnetv2 swinir uformer realesrgan; do
    echo ""
    echo "########## E10 method=$m $(date) ##########"
    $PY run_e10_baseline_hpc.py --method "$m"
    echo "  $m exit=$?"
done
echo "=== E10 BASELINES done $(date) ==="
