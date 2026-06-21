#!/bin/bash
#
# gdn2_lastshot.sbatch — 最后一炮:只跑我们的 gdn2 臂(FLA GatedDeltaNet2,唯一新FLA能跑的)。
# 开 short conv(MQAR承重) + 8000 step + lr/seed sweep,给 GDN-2 最好机会过 n=4 sanity。
# 过 acc>0.9 → GDN-2 能 work,headline 有一线;不过 → 死得明白,转路 B。
#
#SBATCH --partition=gpu4090
#SBATCH --account=shuihuawang
#SBATCH --qos=4gpus
#SBATCH --gres=gpu:1
#SBATCH --cpus-per-task=4
#SBATCH --mem=32G
#SBATCH --time=03:00:00
#SBATCH --job-name=glast
#SBATCH --output=logs/%x_%j.out
#SBATCH --error=logs/%x_%j.err

mkdir -p logs
export TRITON_CACHE_DIR=/tmp/$USER/triton_glast
mkdir -p "$TRITON_CACHE_DIR"
rm -rf "$HOME/.triton/cache" 2>/dev/null || true
source /gpfs/work/bio/jiayu2403/gdn2venv/bin/activate

echo "[glast] start: $(date)  host: $(hostname)"
python -c "import torch; print(f'[glast] torch={torch.__version__} cuda={torch.cuda.is_available()}')"

cd /gpfs/work/bio/jiayu2403/gdn2vessel
python src/benchmark/mqar_capacity_probe.py \
    --arms gdn2 \
    --n_kv 4 \
    --lr 3e-4 1e-3 \
    --seeds 0 1 \
    --steps 8000 \
    --T 256 \
    --vocab 8192 \
    --out_dir /gpfs/work/bio/jiayu2403/gdn2vessel/outputs/route2_lastshot

echo "[glast] done: $(date)  exit_code=$?"
