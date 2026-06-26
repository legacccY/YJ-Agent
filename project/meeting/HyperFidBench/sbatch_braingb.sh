#!/bin/bash
#SBATCH --job-name=hf_bgb
#SBATCH --account=shuihuawang
#SBATCH --partition=gpu3090
#SBATCH --qos=4gpus
#SBATCH --gres=gpu:1
#SBATCH --cpus-per-task=8
#SBATCH --time=12:00:00
#SBATCH --output=/gpfs/work/bio/jiayu2403/hyperfid/logs/bgb_%j.out
#SBATCH --error=/gpfs/work/bio/jiayu2403/hyperfid/logs/bgb_%j.err

set -e
export PIP_DISABLE_PIP_VERSION_CHECK=1
export TMPDIR=/tmp/hf_bgb_$SLURM_JOB_ID   # 节点本地盘, 加速 pip 解包(避 gpfs 慢IO)
mkdir -p $TMPDIR
ROOT=/gpfs/work/bio/jiayu2403/hyperfid
WH=$ROOT/wheelhouse
PY=$ROOT/hf_braingb_venv/bin/python
module load cuda/12.6.0-gcc-13.1.0-65s2yve 2>/dev/null || true
cd $ROOT

# ---- 建 env(若 torch 不可用) ----
if ! $PY -c "import torch, torch_geometric" 2>/dev/null; then
  echo "===== 建 braingb env (TMPDIR=本地盘) ====="
  bash hpc_setup_braingb.sh
fi
$PY -c "import torch; print('CUDA avail', torch.cuda.is_available(), torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'NOGPU')"

# run-01 GCN 3seed 已完成(mean 64.98%, csv 已有)，跳过省时；重跑见 git 历史
# echo "===== run-01 BrainGB GCN edge_node_concate (headline, 对齐文献65%) ====="
# $PY src/braingb_lane/train_braingb.py --run_id run-01-braingb-gcn-cc200 --model_name gcn \
#     --seeds 0 1 2 --gcn_mp_type edge_node_concate --hidden_dim 256

echo "===== run-02 BrainGB GAT (PyG版本shim修复后正式跑) ====="
$PY src/braingb_lane/train_braingb.py --run_id run-02-braingb-gat-cc200 --model_name gat --seeds 0 1 2

echo "===== run-04 fidelity on BrainGB GCN ====="
$PY src/braingb_lane/eval_fidelity.py --run_id run-04-fidelity-on-braingb \
    --ckpt_path $ROOT/results/braingb/run-01-braingb-gcn-cc200_seed0_fold0.pt --fold_idx 0 \
    --gcn_mp_type edge_node_concate --hidden_dim 256

rm -rf $TMPDIR
echo "===== BRAINGB JOB DONE ====="
