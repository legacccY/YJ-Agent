#!/bin/bash
#
# mqar_route2.sbatch — Route-2 Layer 2 GDN-2 MQAR 容量探针（判决性 kill-shot）
# SLURM array: 3 task 对应 3 臂，每臂独占 1 卡并行（gdn2 / gla / linear_attn）
# 判据: reference/ROUTE2_BUDGET_PREREG.md — dual-gap LIVE (A2-A1'>0.15 AND A2-GLA>0.15)
#
# 重构说明 (2026-06-21):
#   - 弃自搓 stub (T=256 GPU 卡死 26min 0 step)
#   - 三臂全换 FLA 官方 CUDA layer (GatedDeltaNet2 / GatedLinearAttention / LinearAttention)
#   - n_kv=96 删 (T=256 不够; 甜区 n<=d=64 已足)
#   - steps 2000→8000, batch 32→64, lr 单值 3e-4+cosine+warmup, wd 1e-4→1e-2
#   - array 4→3 (gdn2_fla 臂删: A2 本身就是 FLA canonical GDN-2)
#
#SBATCH --partition=gpu4090
#SBATCH --account=shuihuawang
#SBATCH --qos=4gpus
#SBATCH --array=0-2
#SBATCH --gres=gpu:1
#SBATCH --cpus-per-task=4
#SBATCH --mem=32G
#SBATCH --time=12:00:00
#SBATCH --job-name=mqar_route2
#SBATCH --output=logs/%x_%A_%a.out
#SBATCH --error=logs/%x_%A_%a.err

# 1. logs 目录防静默失败
mkdir -p logs

# 2. 臂映射: array 0→gdn2, 1→gla, 2→linear_attn
ARMS=(gdn2 gla linear_attn)
ARM=${ARMS[$SLURM_ARRAY_TASK_ID]}
echo "[job] array_task=$SLURM_ARRAY_TASK_ID  arm=$ARM"

# 3. 每 task 独立 Triton cache
export TRITON_CACHE_DIR=/tmp/$USER/triton_$SLURM_ARRAY_TASK_ID
mkdir -p "$TRITON_CACHE_DIR"
rm -rf "$HOME/.triton/cache" 2>/dev/null || true

# 4. 激活 venv
source /gpfs/work/bio/jiayu2403/gdn2venv/bin/activate

# 5. 环境信息
echo "[job] start: $(date)"
echo "[job] host: $(hostname)"
echo "[job] gpu: $(nvidia-smi --query-gpu=name,memory.total --format=csv,noheader 2>/dev/null || echo 'no nvidia-smi')"
python -c "import torch; print(f'[job] torch={torch.__version__} cuda={torch.cuda.is_available()}')"

# 6. fla 必须在 (所有臂均用 FLA 官方 CUDA layer)
python -c "import fla; print('[job] fla OK')" || {
    echo "[job] ERROR: fla import failed — all arms require flash-linear-attention with CUDA"
    exit 1
}

# 7. 每 task 独立 out_dir (避免并发写同一 csv)
OUT_DIR=/gpfs/work/bio/jiayu2403/gdn2vessel/outputs/route2_budget/arm_${ARM}

# 8. 跑单臂全扫
#    n_kv: {4,8,16,32,64} (T=256 全覆盖; 3*64+1=193 ≤ 256 ✓)
#    lr: 3e-4 单值 (VLA Table 3)
#    seeds: 0 1 2 (3 seeds for std)
#    steps: 8000 (VLA Table 3 对齐)
#    batch_size: 64 (VLA Table 3)
#    d_model=128, num_heads=2, d_head=64 → state 2×64×64=8192 (三臂等容)
cd /gpfs/work/bio/jiayu2403/gdn2vessel
python src/benchmark/mqar_capacity_probe.py \
    --n_kv 4 8 16 32 64 \
    --d_head 64 \
    --lr 3e-4 \
    --seeds 0 1 2 \
    --T 256 \
    --vocab 8192 \
    --steps 8000 \
    --batch_size 64 \
    --d_model 128 \
    --num_heads 2 \
    --arms $ARM \
    --log_every 200 \
    --out_dir "$OUT_DIR"

EXIT_CODE=$?
echo "[job] arm=$ARM done: $(date)  exit_code=$EXIT_CODE"
exit $EXIT_CODE
