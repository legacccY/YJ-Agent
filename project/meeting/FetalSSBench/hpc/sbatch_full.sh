#!/bin/bash
#SBATCH --job-name=fetalss_full
#SBATCH --partition=gpu4090
#SBATCH --account=shuihuawang
#SBATCH --qos=4gpus
#SBATCH --gres=gpu:1
#SBATCH --cpus-per-task=4
#SBATCH --time=24:00:00
#SBATCH --output=/gpfs/work/bio/jiayu2403/fetalss/logs/full_%j.out
#SBATCH --error=/gpfs/work/bio/jiayu2403/fetalss/logs/full_%j.err

PYBIN=/gpfs/work/bio/jiayu2403/.conda/envs/yjcu124py310/bin/python
export FETALSS_DATA_ROOT=/gpfs/work/bio/jiayu2403/fetalss/data
export OMP_NUM_THREADS=4
cd /gpfs/work/bio/jiayu2403/fetalss/code

echo "=== full matrix start $(date) ==="
$PYBIN -c "import torch; print('cuda', torch.cuda.is_available())"

# 5 method x 2 dataset x 5 ratio x 3 seed = 150 run; harness state.json 自动跳过已跑
for M in supervised mean_teacher cps uamt fixmatch; do
  for DS in psfhs hc18; do
    for R in 0.01 0.02 0.05 0.10 0.20; do
      for S in 0 1 2; do
        echo "---- $M $DS r=$R s=$S $(date +%H:%M:%S) ----"
        $PYBIN harness.py --method $M --dataset $DS --ratio $R --seed $S 2>&1 || echo "RUN_FAIL_${M}_${DS}_${R}_${S}"
      done
    done
  done
done
echo "=== full matrix done $(date) ==="
wc -l /gpfs/work/bio/jiayu2403/fetalss/code/results/results.csv
