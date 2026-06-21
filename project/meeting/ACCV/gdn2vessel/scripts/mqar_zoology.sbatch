#!/bin/bash
#
# mqar_zoology.sbatch — Route-2 Layer-2 MQAR胜负手: Zoology mixer + step制训练
# 替换自搓 harness (gla/linear_attn 两臂完全不收敛根因: FLA GLA/LinearAttention 与
# 我们原 harness 接口不兼容, 改用 Zoology 官方 gla.py wrapper + 我们step制训练loop)
#
# 三臂 SLURM array (0→gdn2, 1→gla, 2→linear_attn), 每臂独占1卡并行。
# 判据: reference/ROUTE2_BUDGET_PREREG.md dual-gap LIVE:
#   A2−A1'>0.15 AND A2−GLA>0.15 at n∈{16,32,64} + sanity n=4 all>0.9
#
# 主要变化 vs mqar_route2.sbatch:
#   - 数据生成: Zoology multiquery_ar (power_a=0.01, random_non_queries=True)
#     代替我们自搓 build_mqar_batch (Zoology constraint: T>=4*n_kv, 比我们3*n_kv+1更严)
#   - GLA mixer: zoology.mixers.gla.GatedLinearAttention (Zoology官方, 已验证在MQAR能work)
#   - GDN-2 mixer: zoology.mixers.gdn2_mixer.GDN2Mixer (本项目新写, 包FLA GatedDeltaNet2)
#   - LinearAttn: FLA LinearAttention (与probe保持一致实现)
#   - 训练配置: VLA Table 3 step制 8000步+warmup (不用Zoology epoch制Trainer)
#   - out_dir: outputs/route2_zoology/arm_<ARM>/ (独立目录,不与旧csv冲突)
#
#SBATCH --partition=gpu4090
#SBATCH --account=shuihuawang
#SBATCH --qos=4gpus
#SBATCH --array=0-2
#SBATCH --gres=gpu:1
#SBATCH --cpus-per-task=4
#SBATCH --mem=32G
#SBATCH --time=12:00:00
#SBATCH --job-name=mqar_zoology
#SBATCH --output=logs/%x_%A_%a.out
#SBATCH --error=logs/%x_%A_%a.err

# 1. logs 目录防静默失败
mkdir -p logs

# 2. 臂映射
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

# 6. fla 检查
python -c "import fla; print('[job] fla OK')" || {
    echo "[job] ERROR: fla import failed — gdn2/linear_attn arms require flash-linear-attention"
    exit 1
}

# 7. zoology 检查 (必须先 pip install -e _scratch/zoology --no-deps)
cd /gpfs/work/bio/jiayu2403/gdn2vessel
python -c "import zoology; print('[job] zoology OK')" || {
    echo "[job] ERROR: zoology not importable."
    echo "[job] Fix: cd _scratch/zoology && pip install -e . --no-deps"
    echo "[job]       pip install einops pydantic tqdm 'rotary-embedding-torch>=0.5'"
    exit 1
}

# 8. 每 task 独立 out_dir
OUT_DIR=/gpfs/work/bio/jiayu2403/gdn2vessel/outputs/route2_zoology/arm_${ARM}

# 9. 跑单臂全扫
#    n_kv: {4,8,16,32,64}
#    T=256: Zoology 约束 T>=4*n_kv; n_kv=64 -> 4*64=256 ✓ (边界恰好满足)
#    lr: 3e-4 (VLA Table 3)
#    seeds: 0 1 2
#    steps: 8000 (VLA Table 3)
#    batch_size: 64 (VLA Table 3)
#    d_model=128, num_heads=2, head_dim=64 -> state 2*64*64=8192 (三臂等容)
python scripts/run_zoology_mqar.py \
    --arms $ARM \
    --n_kv 4 8 16 32 64 \
    --T 256 \
    --V 8192 \
    --lr 3e-4 \
    --seeds 0 1 2 \
    --steps 8000 \
    --batch_size 64 \
    --d_model 128 \
    --num_heads 2 \
    --head_dim 64 \
    --n_layers 2 \
    --log_every 200 \
    --out_dir "$OUT_DIR"

EXIT_CODE=$?
echo "[job] arm=$ARM done: $(date)  exit_code=$EXIT_CODE"
exit $EXIT_CODE
