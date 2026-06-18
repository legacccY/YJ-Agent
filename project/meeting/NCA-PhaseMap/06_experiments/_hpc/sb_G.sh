#!/bin/bash
# sb_G.sh — 腿② 梯度时序 G1/G2/G3（Hippo，no-clip+clip=1.0 内含，🔴-6 拆雷最高优先）。
#SBATCH --account=shuihuawang
#SBATCH --partition=gpu4090
#SBATCH --qos=4gpus
#SBATCH --gres=gpu:rtx4090:1
#SBATCH --cpus-per-task=8
#SBATCH --time=02:00:00
#SBATCH --job-name=pm_G
#SBATCH --output=/gpfs/work/bio/jiayu2403/run003/phasemap/logs/%x_%j.out
#SBATCH --error=/gpfs/work/bio/jiayu2403/run003/phasemap/logs/%x_%j.err

PY=/gpfs/work/bio/jiayu2403/.conda/envs/yjcu124py310/bin/python
PM=/gpfs/work/bio/jiayu2403/run003/phasemap
export MEDNCA_ROOT=/gpfs/work/bio/jiayu2403/run003/mednca
export PHASEMAP_OUT=${PM}
export CUDA_VISIBLE_DEVICES=0
mkdir -p ${PM}/logs ${PM}/results
cd ${PM}
echo "[G] host=$(hostname) start=$(date)"
for rid in G1 G2 G3; do
  echo "[G] --- ${rid} start=$(date) ---"
  ${PY} G_gradient_traj.py --run_id ${rid} >> ${PM}/logs/G_${rid}.log 2>&1
  echo "[G] ${rid} exit=$?"
done
echo "[G] all done=$(date)"
ls -lh ${PM}/results/G_traj_*.csv 2>/dev/null
