#!/bin/bash
#SBATCH --job-name=wf_bin
#SBATCH --partition=gpu4090
#SBATCH --qos=4gpus
#SBATCH --account=shuihuawang
#SBATCH --gres=gpu:1
#SBATCH --cpus-per-task=8
#SBATCH --time=08:00:00
#SBATCH --output=/gpfs/work/bio/jiayu2403/wavefid/logs/%j.out
#SBATCH --error=/gpfs/work/bio/jiayu2403/wavefid/logs/%j.err

set -e
PY=/gpfs/work/bio/jiayu2403/.conda/envs/yjcu124py310/bin/python
ROOT=/gpfs/work/bio/jiayu2403/wavefid
CODE=$ROOT/code
CFG=$CODE/configs/gate1_oasis_binary.yaml
DATA="$ROOT/data/oasis_kaggle/Data"
SPLIT=log/splits_oasis_binary
CKPT=$CODE/log/hpc_oasis_binary/checkpoints/resnet50_seed42_best.pt

cd $CODE
echo "=== [1/4] data_split (patient, binary remap) ==="
$PY src/data_split.py --config $CFG --data_root "$DATA"

echo "=== [2/4] train_classifier resnet50 seed42 (50ep, GPU) ==="
$PY src/train_classifier.py --config $CFG --data_root "$DATA" --split_csv_dir $SPLIT --seed 42

echo "=== [3/4] subband_zero (L1 初验) ==="
$PY src/subband_zero.py --config $CFG --data_root "$DATA" --split_csv_dir $SPLIT --checkpoint "$CKPT" --seed 42

echo "=== [4/4] faithfulness (GradCAM+IG+GradientShap x Quantus, n=200) ==="
$PY src/faithfulness.py --config $CFG --split_csv_dir $SPLIT --checkpoint "$CKPT" --n_samples 200 --seed 42

echo "=== ALL DONE ==="
