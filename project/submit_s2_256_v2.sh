#!/bin/bash
#SBATCH --job-name=visienhance_s2_256_v2
#SBATCH --account=shuihuawang
#SBATCH --partition=gpu4090
#SBATCH --qos=4gpus
#SBATCH --nodes=1
#SBATCH --cpus-per-task=16
#SBATCH --gres=gpu:4
#SBATCH --time=48:00:00
#SBATCH --output=/gpfs/work/bio/jiayu2403/visienhance/logs/%j.out
#SBATCH --error=/gpfs/work/bio/jiayu2403/visienhance/logs/%j.err

PYTHON="/gpfs/work/bio/jiayu2403/.conda/envs/yjcu124py310/bin/python3.10"
TORCHRUN="/gpfs/work/bio/jiayu2403/.conda/envs/yjcu124py310/bin/torchrun"

echo "=== VisiEnhance Stage 2 @256 v2 (B3 DP-Loss + pos-hinge, 4xGPU DDP) ==="
echo "Job ID: $SLURM_JOB_ID  Node: $SLURMD_NODENAME  Start: $(date)"

export OMP_NUM_THREADS=4
export WANDB_MODE=offline
export WANDB_DISABLE_SERVICE=1
export STATE_PATH="/gpfs/work/bio/jiayu2403/visienhance/logs/experiment_state.json"
HPC_BASE="/gpfs/work/bio/jiayu2403/visienhance"

$PYTHON -c "
import json, time
state = {'status': 'starting', 'epoch': 0, 'job_id': '$SLURM_JOB_ID', 'node': '$SLURMD_NODENAME', 'gpus': 4, 'start_time': time.strftime('%Y-%m-%d %H:%M:%S')}
open('$STATE_PATH', 'w').write(json.dumps(state, indent=2))
"

nvidia-smi --query-gpu=index,utilization.gpu,memory.used,temperature.gpu --format=csv,noheader --loop=30 >> "$HPC_BASE/logs/${SLURM_JOB_ID}_gpu.log" &
GPU_MON_PID=$!

cd "$HPC_BASE/code"
$TORCHRUN --nproc_per_node=4 train_visienhance.py --config "$HPC_BASE/configs/visienhance_s2_planA_256_v2_hpc.yaml"

EXIT_CODE=$?
kill $GPU_MON_PID 2>/dev/null
$PYTHON -c "
import json, time
try: state = json.loads(open('$STATE_PATH').read())
except: state = {}
state.update({'status': 'completed' if $EXIT_CODE == 0 else 'failed', 'exit_code': $EXIT_CODE, 'end_time': time.strftime('%Y-%m-%d %H:%M:%S')})
open('$STATE_PATH', 'w').write(json.dumps(state, indent=2))
"
echo "=== done: $(date), exit_code=$EXIT_CODE ==="
exit $EXIT_CODE
