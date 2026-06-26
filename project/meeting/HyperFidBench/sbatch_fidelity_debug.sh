#!/bin/bash
#SBATCH --job-name=hf_fid
#SBATCH --account=shuihuawang
#SBATCH --partition=gpudebug
#SBATCH --qos=gpudebug
#SBATCH --gres=gpu:1
#SBATCH --cpus-per-task=8
#SBATCH --time=01:00:00
#SBATCH --output=/gpfs/work/bio/jiayu2403/hyperfid/logs/fid_%j.out
#SBATCH --error=/gpfs/work/bio/jiayu2403/hyperfid/logs/fid_%j.err

set -e
export PIP_DISABLE_PIP_VERSION_CHECK=1
ROOT=/gpfs/work/bio/jiayu2403/hyperfid
PY=$ROOT/hf_braingb_venv/bin/python
module load cuda/11.8.0-gcc-8.5.0-d7ndetl 2>/dev/null || true
cd $ROOT
$PY -c "import torch; print('CUDA', torch.cuda.is_available(), torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'NOGPU')"

CKPT=$ROOT/results/braingb/run-01-braingb-gcn-cc200_seed0_fold0.pt
SPLIT=$ROOT/data/external/abide1/split_indices.csv

# run-04 fidelity-on-BrainGB: 加载 seed0/fold0 ckpt (edge_node_concate/hidden256, 须匹配训练config)
# Gate1③ 判据 = PyG fidelity 非 nan 比例 > 0
echo "===== STEP 1: SMOKE (3 samples) 验 PyG2.5.3 explain API 通 ====="
$PY src/braingb_lane/eval_fidelity.py \
    --run_id run-04-fidelity-on-braingb --model_name gcn \
    --gcn_mp_type edge_node_concate --hidden_dim 256 \
    --ckpt_path $CKPT --split_csv_path $SPLIT --fold_idx 0 \
    --smoke 1

echo "===== STEP 2: FULL fold0 test 集 (gpudebug 1h 内能跑多少算多少, max 80 控时间) ====="
$PY src/braingb_lane/eval_fidelity.py \
    --run_id run-04-fidelity-on-braingb --model_name gcn \
    --gcn_mp_type edge_node_concate --hidden_dim 256 \
    --ckpt_path $CKPT --split_csv_path $SPLIT --fold_idx 0 \
    --explainer_epochs 200 --max_samples 80

echo "===== FIDELITY RUN DONE ====="
echo "--- fidelity_results.csv (head) ---"
head -5 $ROOT/results/braingb/fidelity_results.csv
echo "--- state.json ---"
cat $ROOT/results/braingb/state.json
