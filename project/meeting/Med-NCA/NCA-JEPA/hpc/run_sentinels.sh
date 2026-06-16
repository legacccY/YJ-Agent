#!/bin/bash
# NCA-JEPA §7 哨兵门：跑 s1-s8（训练前强制全过）。提交：sbatch hpc/run_sentinels.sh
#SBATCH --job-name=ncaj_sentinel
#SBATCH --account=shuihuawang
#SBATCH --partition=gpu4090
#SBATCH --qos=4gpus
#SBATCH --gres=gpu:rtx4090:1
#SBATCH --cpus-per-task=8
#SBATCH --time=00:30:00
#SBATCH --output=/gpfs/work/bio/jiayu2403/nca-jepa/logs/sentinel_%j.out
#SBATCH --error=/gpfs/work/bio/jiayu2403/nca-jepa/logs/sentinel_%j.err

ROOT=/gpfs/work/bio/jiayu2403/nca-jepa
PY=/gpfs/work/bio/jiayu2403/.conda/envs/yjcu124py310/bin/python
cd $ROOT
echo "[sentinels] host=$(hostname) start=$(date)"
for s in s1_norm_assert s2_ema_sanity s3_collapse_canary s4_overfit_one_batch \
         s5_zshuffle_control s6_determinism_log s7_silent_divergence s8_pure_predict_overfit; do
  echo "===== $s ====="
  $PY sentinels/$s.py 2>&1 | tail -8
done
echo "[sentinels] done=$(date)"
