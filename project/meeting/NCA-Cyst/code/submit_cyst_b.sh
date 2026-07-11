#!/bin/bash
#SBATCH --job-name=ncacystB
#SBATCH --partition=gpu4090
#SBATCH --qos=4gpus
#SBATCH --account=shuihuawang
#SBATCH --gres=gpu:1
#SBATCH --cpus-per-task=8
#SBATCH --time=24:00:00
#SBATCH --output=/gpfs/work/bio/jiayu2403/nca-cyst/logs/%j.out
#SBATCH --error=/gpfs/work/bio/jiayu2403/nca-cyst/logs/%j.err

# NCA-Cyst Phase2 kill-shot 关键格 b：vanilla M3D-NCA + CB-max（-GV +CB）
# label==3 cyst 二分类，CB-max 三组件（囊肿中心采样 + copy-paste frac=0.02 + DiceTversky w_fn=0.9）
# 零偏离官方模型架构（global_view off），CB 为受控自变量。SEED 由 --export=SEED=N 传入。

export KITS23_ROOT=/gpfs/work/bio/jiayu2403/kits23/dataset
export M3DNCA_OFFICIAL_ROOT=/gpfs/work/bio/jiayu2403/mednca/M3D-NCA-official

PY=/gpfs/work/bio/jiayu2403/.conda/envs/yjcu124py310/bin/python
CODE=/gpfs/work/bio/jiayu2403/nca-cyst/code
RUN=/gpfs/work/bio/jiayu2403/nca-cyst/runs/cbmax_cyst_seed${SEED}

mkdir -p "$RUN"
cd "$CODE" || exit 1

echo "[submit] host=$(hostname) gpu=$CUDA_VISIBLE_DEVICES seed=${SEED} start=$(date)"
$PY train_kits23.py --config full --label_mode cyst --class_balance on --seed ${SEED} \
    --model_path "$RUN" \
    --state_path "$RUN/state.json"
echo "[submit] end=$(date) exit=$?"
