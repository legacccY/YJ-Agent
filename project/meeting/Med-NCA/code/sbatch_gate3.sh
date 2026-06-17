#!/bin/bash
# Gate3 Nodule 轨迹探针（训练，~30min）。提交：sbatch sbatch_gate3.sh
#SBATCH --account=shuihuawang
#SBATCH --partition=gpu4090
#SBATCH --qos=4gpus
#SBATCH --gres=gpu:rtx4090:1
#SBATCH --cpus-per-task=8
#SBATCH --time=01:30:00
#SBATCH --job-name=mednca_gate3
#SBATCH --output=/gpfs/work/bio/jiayu2403/nca-jepa/logs/%x_%j.out
#SBATCH --error=/gpfs/work/bio/jiayu2403/nca-jepa/logs/%x_%j.err

ROOT=/gpfs/work/bio/jiayu2403/nca-jepa/med_nca_probe
PY=/gpfs/work/bio/jiayu2403/.conda/envs/yjcu124py310/bin/python
cd $ROOT
echo "[gate3] host=$(hostname) start=$(date)"
$PY probe_persistence.py --config probe_trajectory_hpc.yaml
echo "[gate3] done=$(date) exit=$?"
