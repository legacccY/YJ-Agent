#!/bin/bash
#SBATCH --job-name=hf_hg03
#SBATCH --account=shuihuawang
#SBATCH --partition=gpu3090
#SBATCH --qos=4gpus
#SBATCH --gres=gpu:1
#SBATCH --cpus-per-task=8
#SBATCH --time=12:00:00
#SBATCH --output=/gpfs/work/bio/jiayu2403/hyperfid/logs/hg03_%j.out
#SBATCH --error=/gpfs/work/bio/jiayu2403/hyperfid/logs/hg03_%j.err

set -e
export PIP_DISABLE_PIP_VERSION_CHECK=1
ROOT=/gpfs/work/bio/jiayu2403/hyperfid
PY=$ROOT/hf_hypergale_venv/bin/python
module load cuda/11.8.0-gcc-8.5.0-d7ndetl 2>/dev/null || true
cd $ROOT
$PY -c "import torch; print('CUDA', torch.cuda.is_available(), torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'NOGPU')"

FC=$ROOT/data/external/abide1_cc200/fc_large_data_cc200.npy
SPLIT=$ROOT/data/external/abide1_cc200/splits/split_cc200_5fold.csv

# run-03 HyperGALE 超图 cc200 全量: fold0 × 3 seed, ep200 (Gate1 HyperGALE acc 判据)
# 与 BrainGB 同 ABIDE-I cc200 同 split → Gate2 纯比 GNN vs 超图架构
echo "===== run-03 HyperGALE cc200 fold0 × 3seed ep200 ====="
$PY src/hypergale_lane/train_hypergale.py \
    --fc-path $FC --split-csv $SPLIT --fold 0 --seeds 1 2 --device cuda:0

echo "===== HYPERGALE run-03 DONE ====="
cat $ROOT/results/hypergale/results_hypergale.csv 2>/dev/null
echo "--- state ---"
cat $ROOT/results/hypergale/state.json 2>/dev/null | tail -15
