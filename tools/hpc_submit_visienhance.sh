#!/bin/bash
#SBATCH --job-name=visienhance_s2
#SBATCH --account=shuihuawang
#SBATCH --partition=gpu4090
#SBATCH --qos=4gpus
#SBATCH --nodes=1
#SBATCH --cpus-per-task=8
#SBATCH --gres=gpu:1
#SBATCH --time=48:00:00
#SBATCH --output=/gpfs/work/bio/jiayu2403/visienhance/logs/%j.out
#SBATCH --error=/gpfs/work/bio/jiayu2403/visienhance/logs/%j.err

echo "=== VisiEnhance Stage 2 (DP-Loss) ==="
echo "Job ID: $SLURM_JOB_ID"
echo "Node: $SLURMD_NODENAME"
echo "Start: $(date)"
echo "======================================"

# 环境
module purge
module load anaconda3
source activate yjcu124py310

# Linux 下不需要 Windows 兼容 env var，但保留无害
export OMP_NUM_THREADS=4
export CUDA_LAUNCH_BLOCKING=0

HPC_BASE="/gpfs/work/bio/jiayu2403/visienhance"
CODE="$HPC_BASE/code"
LOGS="$HPC_BASE/logs"
STATE="$LOGS/experiment_state.json"

# 写初始 state（供监控读取）
python -c "
import json, time
state = {'status': 'starting', 'epoch': 0, 'val_psnr': 0, 'train_loss': 0,
         'job_id': '$SLURM_JOB_ID', 'node': '$SLURMD_NODENAME',
         'start_time': time.strftime('%Y-%m-%d %H:%M:%S')}
open('$STATE', 'w').write(json.dumps(state, indent=2))
"

# 启动 GPU 监控（后台写到日志）
nvidia-smi --query-gpu=utilization.gpu,memory.used,memory.total,temperature.gpu \
    --format=csv,noheader --loop=30 >> "$LOGS/${SLURM_JOB_ID}_gpu.log" &
GPU_MON_PID=$!

cd "$CODE"

# 运行训练（STATE_PATH 通过环境变量覆盖）
export STATE_PATH="$STATE"

python train_visienhance.py \
    --config "$HPC_BASE/configs/visienhance_s2_planA_hpc.yaml"

EXIT_CODE=$?

# 停 GPU 监控
kill $GPU_MON_PID 2>/dev/null

# 写最终 state
python -c "
import json, time
try:
    state = json.loads(open('$STATE').read())
except:
    state = {}
state['status'] = 'completed' if $EXIT_CODE == 0 else 'failed'
state['exit_code'] = $EXIT_CODE
state['end_time'] = time.strftime('%Y-%m-%d %H:%M:%S')
open('$STATE', 'w').write(json.dumps(state, indent=2))
"

echo "=== 结束: $(date), exit_code=$EXIT_CODE ==="
exit $EXIT_CODE
