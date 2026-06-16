#!/bin/bash
# Gate0 linear probe：A0 vs from-scratch，probe 10pct。sbatch hpc/run_gate0_probe.sh
#SBATCH --job-name=ncaj_gate0
#SBATCH --account=shuihuawang
#SBATCH --partition=gpu4090
#SBATCH --qos=4gpus
#SBATCH --gres=gpu:rtx4090:1
#SBATCH --cpus-per-task=8
#SBATCH --time=00:40:00
#SBATCH --output=/gpfs/work/bio/jiayu2403/nca-jepa/logs/gate0_%j.out
#SBATCH --error=/gpfs/work/bio/jiayu2403/nca-jepa/logs/gate0_%j.err

ROOT=/gpfs/work/bio/jiayu2403/nca-jepa
PY=/gpfs/work/bio/jiayu2403/.conda/envs/yjcu124py310/bin/python
cd $ROOT
echo "[gate0] start=$(date)"
echo "===== A0 (pretrained) ====="
$PY eval_linear_probe.py --ckpt logs/a0_vit_vits_nih10k/jepa-latest.pth.tar --probe-train 10pct --out results/gate0_probe.csv
echo "===== scratch (random init) ====="
$PY eval_linear_probe.py --scratch --probe-train 10pct --out results/gate0_probe.csv
echo "[gate0] done=$(date)"
cat results/gate0_probe.csv
