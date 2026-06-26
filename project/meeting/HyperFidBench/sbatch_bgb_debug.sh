#!/bin/bash
#SBATCH --job-name=hf_bgbdbg
#SBATCH --account=shuihuawang
#SBATCH --partition=gpudebug
#SBATCH --qos=gpudebug
#SBATCH --gres=gpu:1
#SBATCH --cpus-per-task=8
#SBATCH --time=01:00:00
#SBATCH --output=/gpfs/work/bio/jiayu2403/hyperfid/logs/bgbdbg_%j.out
#SBATCH --error=/gpfs/work/bio/jiayu2403/hyperfid/logs/bgbdbg_%j.err

set -e
export PIP_DISABLE_PIP_VERSION_CHECK=1
ROOT=/gpfs/work/bio/jiayu2403/hyperfid
PY=$ROOT/hf_braingb_venv/bin/python
module load cuda/11.8.0-gcc-8.5.0-d7ndetl 2>/dev/null || true
cd $ROOT
$PY -c "import torch; print('CUDA', torch.cuda.is_available(), torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'NOGPU')"

# gpudebug 限 1h: run-01 headline edge_node_concate 仅 seed 0(5 fold), 拿 Gate1② acc 信号
echo "===== run-01 BrainGB GCN edge_node_concate seed0 (Gate1② 早期信号) ====="
$PY src/braingb_lane/train_braingb.py --run_id run-01-braingb-gcn-cc200 --model_name gcn \
    --seeds 0 --gcn_mp_type edge_node_concate --hidden_dim 256

# run-02 GAT smoke test: 验证 PyG 版本兼容性修复（MPGATConv.forward 覆盖后不再报 size mismatch）
echo "===== run-02 BrainGB GAT smoke (1 fold 1 epoch, 验 PyG compat fix) ====="
$PY src/braingb_lane/train_braingb.py --run_id run-02-braingb-gat-cc200-smoke --model_name gat \
    --seeds 0 --smoke 1
echo "===== DEBUG RUN DONE ====="
