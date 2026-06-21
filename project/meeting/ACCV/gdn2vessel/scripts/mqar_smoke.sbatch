#!/bin/bash
#
# mqar_smoke.sbatch — 重构后 FLA 三臂 cheap 烟测：验接口通 + n=4 sanity 趋势。
# 单卡，n=4 三臂 × 1 seed × 2000 step（FLA chunk kernel 快）。过了再全扫 mqar_route2.sbatch。
#
#SBATCH --partition=gpu4090
#SBATCH --account=shuihuawang
#SBATCH --qos=4gpus
#SBATCH --gres=gpu:1
#SBATCH --cpus-per-task=4
#SBATCH --mem=32G
#SBATCH --time=01:00:00
#SBATCH --job-name=mqar_smoke
#SBATCH --output=logs/%x_%j.out
#SBATCH --error=logs/%x_%j.err

mkdir -p logs
export TRITON_CACHE_DIR=/tmp/$USER/triton_smoke
mkdir -p "$TRITON_CACHE_DIR"
rm -rf "$HOME/.triton/cache" 2>/dev/null || true
source /gpfs/work/bio/jiayu2403/gdn2venv/bin/activate

echo "[smoke] start: $(date)  host: $(hostname)"
python -c "import torch; print(f'[smoke] torch={torch.__version__} cuda={torch.cuda.is_available()}')"
python -c "import fla; from fla.layers import GatedDeltaNet2, GatedLinearAttention, LinearAttention; print('[smoke] fla 3-layer import OK')" \
    || { echo '[smoke] FATAL fla layer import failed'; exit 1; }

cd /gpfs/work/bio/jiayu2403/gdn2vessel
python src/benchmark/mqar_capacity_probe.py \
    --n_kv 4 \
    --arms gdn2 gla linear_attn \
    --lr 3e-4 \
    --seeds 0 \
    --steps 2000 \
    --T 256 \
    --vocab 8192 \
    --out_dir /gpfs/work/bio/jiayu2403/gdn2vessel/outputs/route2_smoke

echo "[smoke] done: $(date)  exit_code=$?"
