#!/bin/bash
#
# noconv_sanity.sbatch — 关键闸(skeptic 出路①):三臂统一无 conv + 8000 step,验 n=4 sanity。
# 决定整个判决怎么跑:三臂都过0.9→无conv干净跑甜区双gap(short conv是污染源);没过→开/关conv双跑。
# 假设:之前三臂不学是 step不够(2000)不是缺conv;8000 step 无conv三臂应都能学。
#
#SBATCH --partition=gpu4090
#SBATCH --account=shuihuawang
#SBATCH --qos=4gpus
#SBATCH --gres=gpu:1
#SBATCH --cpus-per-task=4
#SBATCH --mem=32G
#SBATCH --time=02:00:00
#SBATCH --job-name=nsanity
#SBATCH --output=logs/%x_%j.out
#SBATCH --error=logs/%x_%j.err

mkdir -p logs
export TRITON_CACHE_DIR=/tmp/$USER/triton_nsanity
mkdir -p "$TRITON_CACHE_DIR"
rm -rf "$HOME/.triton/cache" 2>/dev/null || true
source /gpfs/work/bio/jiayu2403/gdn2venv/bin/activate

echo "[nsanity] start: $(date)  host: $(hostname)"
python -c "import torch; print(f'[nsanity] torch={torch.__version__} cuda={torch.cuda.is_available()}')"

cd /gpfs/work/bio/jiayu2403/gdn2vessel
python src/benchmark/mqar_capacity_probe.py \
    --arms gdn2 gla linear_attn \
    --n_kv 4 \
    --lr 3e-4 1e-3 \
    --seeds 0 \
    --steps 8000 \
    --T 256 \
    --vocab 8192 \
    --out_dir /gpfs/work/bio/jiayu2403/gdn2vessel/outputs/route2_noconv_sanity

echo "[nsanity] done: $(date)  exit_code=$?"
