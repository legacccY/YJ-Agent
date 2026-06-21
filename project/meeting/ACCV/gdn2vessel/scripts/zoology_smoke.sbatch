#!/bin/bash
#
# zoology_smoke.sbatch — Zoology 路线 cheap 烟测：三臂 n=4 × 2000 step 验收敛。
# 重点：gla/linear_attn（上次自搓不学）这次用 Zoology/FLA mixer 学不学。过了再全扫 mqar_zoology.sbatch。
#
#SBATCH --partition=gpu4090
#SBATCH --account=shuihuawang
#SBATCH --qos=4gpus
#SBATCH --gres=gpu:1
#SBATCH --cpus-per-task=4
#SBATCH --mem=32G
#SBATCH --time=01:30:00
#SBATCH --job-name=zoo_smoke
#SBATCH --output=logs/%x_%j.out
#SBATCH --error=logs/%x_%j.err

mkdir -p logs
export TRITON_CACHE_DIR=/tmp/$USER/triton_zoosmoke
mkdir -p "$TRITON_CACHE_DIR"
rm -rf "$HOME/.triton/cache" 2>/dev/null || true
source /gpfs/work/bio/jiayu2403/gdn2venv/bin/activate

echo "[zoo_smoke] start: $(date)  host: $(hostname)"
python -c "import torch; print(f'[zoo_smoke] torch={torch.__version__} cuda={torch.cuda.is_available()}')"

cd /gpfs/work/bio/jiayu2403/gdn2vessel
python scripts/run_zoology_mqar.py \
    --arms gdn2 gla linear_attn \
    --n_kv 4 \
    --steps 2000 \
    --seeds 0 \
    --lr 3e-4 \
    --T 256 \
    --V 8192 \
    --out_dir /gpfs/work/bio/jiayu2403/gdn2vessel/outputs/route2_zoo_smoke

echo "[zoo_smoke] done: $(date)  exit_code=$?"
