#!/bin/bash
# sb_B3ext.sh — 补1【生死闸门】BraTS no-clip 扩 ur 打 A2（8 ur × 5 seed = 40 run）。
# 服务 K-new-1：全 MIXED → 彻底收口；collapse_rate 单调跨 0→1 → A2 翻案。
# 复用 B1_B2_B3_sweep.py（build_grid_b3 加 --ur_list/--out_suffix 支持）。
# 输出 results/B3_ext_brats_seed.csv（不覆盖既有 B3_seed.csv）。
# 提交：sbatch --export=ALL,DICE_BG_BRATS=0.005421,SIGMA_BG_BRATS=0.002487 sb_B3ext.sh
#SBATCH --account=shuihuawang
#SBATCH --partition=gpu4090
#SBATCH --qos=4gpus
#SBATCH --gres=gpu:rtx4090:1
#SBATCH --cpus-per-task=8
#SBATCH --time=03:00:00
#SBATCH --job-name=pm_B3ext
#SBATCH --output=/gpfs/work/bio/jiayu2403/run003/phasemap/logs/%x_%j.out
#SBATCH --error=/gpfs/work/bio/jiayu2403/run003/phasemap/logs/%x_%j.err

PY=/gpfs/work/bio/jiayu2403/.conda/envs/yjcu124py310/bin/python
PM=/gpfs/work/bio/jiayu2403/run003/phasemap
export MEDNCA_ROOT=/gpfs/work/bio/jiayu2403/run003/mednca
export BRATS_ROOT=${PM}/data/brats_test
export PHASEMAP_OUT=${PM}
export DICE_BG_BRATS=${DICE_BG_BRATS:-0.005421}
export SIGMA_BG_BRATS=${SIGMA_BG_BRATS:-0.002487}
export CUDA_VISIBLE_DEVICES=0
mkdir -p ${PM}/logs ${PM}/results
cd ${PM}
echo "[B3ext] host=$(hostname) start=$(date) DICE_BG_BRATS=${DICE_BG_BRATS} SIGMA=${SIGMA_BG_BRATS}"
${PY} B1_B2_B3_sweep.py --stage B3 \
  --ur_list 0.45,0.50,0.55,0.60,0.65,0.70,0.75,0.80 \
  --out_suffix _ext_brats \
  >> ${PM}/logs/B3ext.log 2>&1
echo "[B3ext] exit=$? done=$(date)"
ls -lh ${PM}/results/B3_ext_brats_seed.csv 2>/dev/null
