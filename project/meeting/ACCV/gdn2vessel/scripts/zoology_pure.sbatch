#!/bin/bash
#
# zoology_pure.sbatch — 纯 Zoology harness MQAR 三臂 capacity probe
# 服务: gdn2vessel (ACCV 2026) / Route-2 Layer-2 MQAR (判决性 kill-shot)
# 脚本: scripts/run_zoology_pure.py (ZoologyPureTrainer epoch-based, no wandb/pandas/torchvision)
#
# SLURM array: 3 task 对应 3 臂 (gdn2 / gla / linear_attn), 每臂独占 1 卡并行
# 判据: reference/ROUTE2_BUDGET_PREREG.md — dual-gap LIVE (A2-A1'>0.15 AND A2-GLA>0.15)
#
# Zoology harness 说明:
#   - 用 Zoology 官方 epoch 制 (max_epochs=32) + CosineAnnealingLR (original_mqar_configs.py)
#   - 不用 wandb/pandas/torchvision (ZoologyPureTrainer 去掉这三个依赖)
#   - 数据: Zoology MQARConfig + prepare_data
#   - Mixer: gdn2=GDN2Mixer (gdn2_mixer.py), gla=GatedLinearAttention, linear_attn=FLA wrap
#
# 安装 (一次性, 在 gdn2venv):
#   pip install -e /gpfs/work/bio/jiayu2403/gdn2vessel/_scratch/zoology --no-deps
#   pip install einops pydantic tqdm rotary-embedding-torch rich
#
#SBATCH --partition=gpu4090
#SBATCH --account=shuihuawang
#SBATCH --qos=4gpus
#SBATCH --array=0-2
#SBATCH --gres=gpu:1
#SBATCH --cpus-per-task=4
#SBATCH --mem=32G
#SBATCH --time=12:00:00
#SBATCH --job-name=mqar_zpure
#SBATCH --output=logs/%x_%A_%a.out
#SBATCH --error=logs/%x_%A_%a.err

# 1. logs 目录防静默失败
mkdir -p logs

# 2. 臂映射: array 0→gdn2, 1→gla, 2→linear_attn
ARMS=(gdn2 gla linear_attn)
ARM=${ARMS[$SLURM_ARRAY_TASK_ID]}
echo "[job] array_task=$SLURM_ARRAY_TASK_ID  arm=$ARM"

# 3. 每 task 独立 Triton cache (防并发 cache 冲突)
export TRITON_CACHE_DIR=/tmp/$USER/triton_zpure_$SLURM_ARRAY_TASK_ID
mkdir -p "$TRITON_CACHE_DIR"
rm -rf "$HOME/.triton/cache" 2>/dev/null || true

# 4. 激活 venv
source /gpfs/work/bio/jiayu2403/gdn2venv/bin/activate

# 5. 环境信息
echo "[job] start: $(date)"
echo "[job] host: $(hostname)"
echo "[job] gpu: $(nvidia-smi --query-gpu=name,memory.total --format=csv,noheader 2>/dev/null || echo 'no nvidia-smi')"
python -c "import torch; print(f'[job] torch={torch.__version__} cuda={torch.cuda.is_available()}')"

# 6. fla 必须在 (三臂均用 FLA 官方 CUDA layer)
python -c "import fla; print('[job] fla OK')" || {
    echo "[job] ERROR: fla import failed — all arms require flash-linear-attention with CUDA"
    exit 1
}

# 7. zoology 必须可 import
python -c "from zoology.config import TrainConfig; print('[job] zoology OK')" || {
    echo "[job] ERROR: zoology not importable."
    echo "[job] Fix: pip install -e /gpfs/work/bio/jiayu2403/gdn2vessel/_scratch/zoology --no-deps"
    exit 1
}

# 8. 每 task 独立 out_dir (避免三臂并发写同一 csv)
OUT_DIR=/gpfs/work/bio/jiayu2403/gdn2vessel/outputs/route2_zoology_pure/arm_${ARM}

# 9. 跑单臂全扫 (Zoology 官方 epoch 制)
#    n_kv: {4,8,16,32,64}
#    max_epochs: 32 (original_mqar_configs.py)
#    lr: 1e-3 (Zoology TrainConfig default; TODO: 若判据不通, 加 --lr 3e-4)
#    seeds: 0 1 2
#    batch_size: 64 (VLA Table 3; Zoology 原版 256 会 OOM on 4090/24G)
#    d_model=128, num_heads=2, head_dim=64 → state 2×64×64=8192 (三臂等容)
#    T=256 → Zoology 自动 bump 到 max(256, 4*n_kv)
cd /gpfs/work/bio/jiayu2403/gdn2vessel
python scripts/run_zoology_pure.py \
    --arms $ARM \
    --n_kv 4 8 16 32 64 \
    --seeds 0 1 2 \
    --lr 1e-3 \
    --max_epochs 32 \
    --batch_size 64 \
    --vocab_size 8192 \
    --num_examples 20000 \
    --T 256 \
    --d_model 128 \
    --out_dir "$OUT_DIR"

EXIT_CODE=$?
echo "[job] arm=$ARM done: $(date)  exit_code=$EXIT_CODE"
exit $EXIT_CODE
