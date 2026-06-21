#!/bin/bash
#
# mqar_route2.sbatch — 路 2 Layer 2 GDN-2 MQAR 容量探针（判决性 kill-shot）
# SLURM array 版：4 task 对应 4 臂，每臂独占 1 卡并行，~4× 加速
# 判据见 reference/ROUTE2_BUDGET_PREREG.md
#
#SBATCH --partition=gpu4090
#SBATCH --account=shuihuawang
#SBATCH --qos=4gpus
#SBATCH --array=0-3
#SBATCH --gres=gpu:1
#SBATCH --cpus-per-task=4
#SBATCH --mem=32G
#SBATCH --time=08:00:00
#SBATCH --job-name=mqar_route2
#SBATCH --output=logs/%x_%A_%a.out
#SBATCH --error=logs/%x_%A_%a.err

# 1. 防 logs 缺失静默失败
mkdir -p logs

# 2. 臂映射：array task 0-3 → arm 名称
ARMS=(gdn2 gla linear_attn gdn2_fla)
ARM=${ARMS[$SLURM_ARRAY_TASK_ID]}
echo "[job] array_task=$SLURM_ARRAY_TASK_ID  arm=$ARM"

# 3. 每 task 独立 Triton cache，防 array task 间 NFS cache 冲突
#    （原单任务 triton_cache 已改为 triton_$SLURM_ARRAY_TASK_ID）
export TRITON_CACHE_DIR=/tmp/$USER/triton_$SLURM_ARRAY_TASK_ID
mkdir -p "$TRITON_CACHE_DIR"
rm -rf "$HOME/.triton/cache" 2>/dev/null || true

# 4. 激活 venv（Entry22 验通路径）
source /gpfs/work/bio/jiayu2403/gdn2venv/bin/activate

# 5. 环境信息
echo "[job] start: $(date)"
echo "[job] host: $(hostname)"
echo "[job] gpu: $(nvidia-smi --query-gpu=name,memory.total --format=csv,noheader 2>/dev/null || echo 'no nvidia-smi')"
python -c "import torch; print(f'[job] torch={torch.__version__} cuda={torch.cuda.is_available()}')"

# 6. fla 检查
#    gdn2_fla 臂必须 fla 真在，否则 cross-val 无效
#    gdn2/gla/linear_attn 三臂用纯 PyTorch stub，无需 fla
python -c "import fla; print('[job] fla OK (real kernel, not stub)')" || {
    if [ "$ARM" = "gdn2_fla" ]; then
        echo "[job] ERROR: arm=gdn2_fla requires fla but import failed — aborting this task"
        exit 1
    else
        echo "[job] WARN: fla import failed — arm=$ARM uses pure-PyTorch stub (OK for this arm)"
    fi
}

# 7. 每 task 独立 out_dir（避免 4 job 并发写同一 csv 冲突）
OUT_DIR=/gpfs/work/bio/jiayu2403/gdn2vessel/outputs/route2_budget/arm_${ARM}

# 8. 跑单臂全扫（n_kv×lr×seed 全量不变，臂内 sanity n=4 完整）
cd /gpfs/work/bio/jiayu2403/gdn2vessel
python src/benchmark/mqar_capacity_probe.py \
    --n_kv 4 8 16 32 64 96 \
    --d_head 64 \
    --lr 1e-3 5e-4 3e-4 1e-4 \
    --seeds 0 1 \
    --T 256 \
    --vocab 8192 \
    --steps 2000 \
    --arms $ARM \
    --fla_num_heads 2 --fla_head_dim 32 --fla_conv_size 4 \
    --out_dir "$OUT_DIR"

EXIT_CODE=$?
echo "[job] arm=$ARM done: $(date)  exit_code=$EXIT_CODE"
exit $EXIT_CODE
