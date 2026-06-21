#!/bin/bash
#
# mqar_route2.sbatch — 路 2 Layer 2 GDN-2 MQAR 容量探针（判决性 kill-shot）
# 单 GPU 一次进程内跑完全扫（n_kv×lr×seed×arm）。判据见 reference/ROUTE2_BUDGET_PREREG.md
#
#SBATCH --partition=gpu4090
#SBATCH --account=shuihuawang
#SBATCH --qos=4gpus
#SBATCH --gres=gpu:1
#SBATCH --cpus-per-task=4
#SBATCH --mem=32G
#SBATCH --time=08:00:00
#SBATCH --job-name=mqar_route2
#SBATCH --output=logs/%x_%j.out
#SBATCH --error=logs/%x_%j.err

# 1. 防 logs 缺失静默失败
mkdir -p logs

# 2. Triton/FLA NFS 死锁修复（Entry3 命脉，所有 GDN-2 job 必带）
export TRITON_CACHE_DIR=/tmp/$USER/triton_cache
mkdir -p "$TRITON_CACHE_DIR"
rm -rf "$HOME/.triton/cache" 2>/dev/null || true

# 3. 激活 venv（Entry22 验通路径）
source /gpfs/work/bio/jiayu2403/gdn2venv/bin/activate

# 4. 环境信息
echo "[job] start: $(date)"
echo "[job] host: $(hostname)"
echo "[job] gpu: $(nvidia-smi --query-gpu=name,memory.total --format=csv,noheader 2>/dev/null || echo 'no nvidia-smi')"
python -c "import torch; print(f'[job] torch={torch.__version__} cuda={torch.cuda.is_available()}')"
python -c "import fla; print('[job] fla OK (real kernel, not stub)')" || echo "[job] WARN fla import failed — GDN2 arm would use stub, INVALID"

# 5. 跑全扫（默认参数即 PREREG 配置）
cd /gpfs/work/bio/jiayu2403/gdn2vessel
python src/benchmark/mqar_capacity_probe.py \
    --n_kv 4 8 16 32 64 96 \
    --d_head 64 \
    --lr 1e-3 5e-4 1e-4 \
    --seeds 0 1 \
    --T 256 \
    --vocab 8192 \
    --steps 2000 \
    --out_dir /gpfs/work/bio/jiayu2403/gdn2vessel/outputs/route2_budget

EXIT_CODE=$?
echo "[job] done: $(date)  exit_code=$EXIT_CODE"
exit $EXIT_CODE
