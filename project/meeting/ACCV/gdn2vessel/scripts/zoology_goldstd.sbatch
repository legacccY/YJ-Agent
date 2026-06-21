#!/bin/bash
#
# zoology_goldstd.sbatch — 金标准对照：100% Zoology 官方 GDN-1 mixer + 官方充分 epoch。
# 验环境/harness 能不能让最该解出 MQAR 的官方 GDN-1(带 short conv) 过 sanity。
# 过 n=4 acc>0.9 → 环境OK,问题在我们 GDN-2 包装;不过 → 环境根本问题。
#
#SBATCH --partition=gpu4090
#SBATCH --account=shuihuawang
#SBATCH --qos=4gpus
#SBATCH --gres=gpu:1
#SBATCH --cpus-per-task=4
#SBATCH --mem=32G
#SBATCH --time=02:00:00
#SBATCH --job-name=zgold
#SBATCH --output=logs/%x_%j.out
#SBATCH --error=logs/%x_%j.err

mkdir -p logs
export TRITON_CACHE_DIR=/tmp/$USER/triton_zgold
mkdir -p "$TRITON_CACHE_DIR"
rm -rf "$HOME/.triton/cache" 2>/dev/null || true
source /gpfs/work/bio/jiayu2403/gdn2venv/bin/activate

echo "[zgold] start: $(date)  host: $(hostname)"
python -c "import torch; print(f'[zgold] torch={torch.__version__} cuda={torch.cuda.is_available()}')"

cd /gpfs/work/bio/jiayu2403/gdn2vessel
python scripts/run_zoology_pure.py \
    --arms gdn1 \
    --n_kv 4 \
    --seeds 0 \
    --max_epochs 32 \
    --out_dir /gpfs/work/bio/jiayu2403/gdn2vessel/outputs/route2_goldstd

echo "[zgold] done: $(date)  exit_code=$?"
