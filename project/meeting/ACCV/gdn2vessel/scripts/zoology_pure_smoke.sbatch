#!/bin/bash
#
# zoology_pure_smoke.sbatch — 纯 Zoology harness cheap 烟测：三臂 n=4 验接口通 + sanity。
# 用 Zoology Trainer(去依赖) 跑,重点 gla/linear_attn 这次学不学。过了全扫 zoology_pure.sbatch。
#
#SBATCH --partition=gpu4090
#SBATCH --account=shuihuawang
#SBATCH --qos=4gpus
#SBATCH --gres=gpu:1
#SBATCH --cpus-per-task=4
#SBATCH --mem=32G
#SBATCH --time=01:30:00
#SBATCH --job-name=zpure_smoke
#SBATCH --output=logs/%x_%j.out
#SBATCH --error=logs/%x_%j.err

mkdir -p logs
export TRITON_CACHE_DIR=/tmp/$USER/triton_zpuresmoke
mkdir -p "$TRITON_CACHE_DIR"
rm -rf "$HOME/.triton/cache" 2>/dev/null || true
source /gpfs/work/bio/jiayu2403/gdn2venv/bin/activate

echo "[zpure_smoke] start: $(date)  host: $(hostname)"
python -c "import torch; print(f'[zpure_smoke] torch={torch.__version__} cuda={torch.cuda.is_available()}')"

cd /gpfs/work/bio/jiayu2403/gdn2vessel
python scripts/run_zoology_pure.py \
    --arms gdn2 gla linear_attn \
    --n_kv 4 \
    --seeds 0 \
    --max_epochs 8 \
    --out_dir /gpfs/work/bio/jiayu2403/gdn2vessel/outputs/route2_pure_smoke

echo "[zpure_smoke] done: $(date)  exit_code=$?"
