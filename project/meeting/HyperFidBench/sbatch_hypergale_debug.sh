#!/bin/bash
#SBATCH --job-name=hf_hgdbg
#SBATCH --account=shuihuawang
#SBATCH --partition=gpudebug
#SBATCH --qos=gpudebug
#SBATCH --gres=gpu:1
#SBATCH --cpus-per-task=8
#SBATCH --time=01:00:00
#SBATCH --output=/gpfs/work/bio/jiayu2403/hyperfid/logs/hgdbg_%j.out
#SBATCH --error=/gpfs/work/bio/jiayu2403/hyperfid/logs/hgdbg_%j.err

set -e
export PIP_DISABLE_PIP_VERSION_CHECK=1
ROOT=/gpfs/work/bio/jiayu2403/hyperfid
PY=$ROOT/hf_hypergale_venv/bin/python
module load cuda/11.8.0-gcc-8.5.0-d7ndetl 2>/dev/null || true
cd $ROOT
$PY -c "import torch; print('CUDA', torch.cuda.is_available(), torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'NOGPU')"

FC=$ROOT/data/external/abide1_cc200/fc_large_data_cc200.npy
SPLIT=$ROOT/data/external/abide1_cc200/splits/split_cc200_5fold.csv

# run-03 HyperGALE 超图 cc200 SMOKE: 1 epoch + seed0 + fold0, 验端到端真能跑(非mock)
echo "===== run-03 HyperGALE cc200 SMOKE (1 epoch 验端到端) ====="
$PY src/hypergale_lane/train_hypergale.py \
    --fc-path $FC --split-csv $SPLIT --fold 0 --smoke 1 --device cuda:0

echo "===== HYPERGALE SMOKE DONE ====="
cat $ROOT/results/hypergale/state.json 2>/dev/null || echo "(no state.json)"
