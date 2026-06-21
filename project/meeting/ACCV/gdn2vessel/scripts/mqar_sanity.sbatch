#!/bin/bash
# mqar_sanity.sbatch — 路2 Layer2 探针 n=4 收敛 sanity（验双重残差修复，过了才全扫）
# 3臂(gdn2/linear_attn/gdn2_fla)×3lr×1seed=9 config，应全部 n=4 acc>0.9
#SBATCH --partition=gpu4090
#SBATCH --account=shuihuawang
#SBATCH --qos=4gpus
#SBATCH --gres=gpu:1
#SBATCH --cpus-per-task=4
#SBATCH --mem=32G
#SBATCH --time=01:00:00
#SBATCH --job-name=mqar_sanity
#SBATCH --output=logs/%x_%j.out
#SBATCH --error=logs/%x_%j.err

mkdir -p logs
export TRITON_CACHE_DIR=/tmp/$USER/triton_cache
mkdir -p "$TRITON_CACHE_DIR"
rm -rf "$HOME/.triton/cache" 2>/dev/null || true
source /gpfs/work/bio/jiayu2403/gdn2venv/bin/activate

echo "[job] start: $(date)  host: $(hostname)"
python -c "import torch; print(f'[job] torch={torch.__version__} cuda={torch.cuda.is_available()}')"
python -c "import fla; print('[job] fla OK')" || echo "[job] WARN no fla"

cd /gpfs/work/bio/jiayu2403/gdn2vessel
python src/benchmark/mqar_capacity_probe.py \
    --n_kv 4 \
    --d_head 64 \
    --lr 1e-3 5e-4 1e-4 \
    --seeds 0 \
    --T 256 \
    --vocab 8192 \
    --steps 1500 \
    --arms gdn2 linear_attn gdn2_fla \
    --fla_num_heads 2 --fla_head_dim 32 --fla_conv_size 4 \
    --out_dir /gpfs/work/bio/jiayu2403/gdn2vessel/outputs/route2_budget/sanity_n4

echo "[job] done: $(date)  exit=$?"
