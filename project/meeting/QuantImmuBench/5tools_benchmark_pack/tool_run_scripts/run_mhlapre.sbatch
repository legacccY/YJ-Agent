#!/bin/bash
#SBATCH --job-name=MHL_rerun
#SBATCH --output=/gpfs/work/bio/zichenli24/rerun_v2/05_MHLAPre/logs/%j.out
#SBATCH --error=/gpfs/work/bio/zichenli24/rerun_v2/05_MHLAPre/logs/%j.err
#SBATCH --time=04:00:00
#SBATCH --cpus-per-task=4
#SBATCH --mem=16G
#SBATCH --partition=gpu4090
#SBATCH --qos=2gpu
#SBATCH --gres=gpu:1

source ~/.bashrc
conda activate mhlapre

HPC_BASE="/gpfs/work/bio/zichenli24"
MHLAPRE_DIR="$HPC_BASE/tools/MHLAPre"
OUTPUT_DIR="$HPC_BASE/rerun_v2/05_MHLAPre/outputs"
MODEL_DIR="$HPC_BASE/rerun_v2/05_MHLAPre/models"

mkdir -p "$OUTPUT_DIR" "$MODEL_DIR"

echo "============================================"
echo " MHLAPre — Dataset2 Complete (130 peptides)"
echo "============================================"
echo "Date: $(date)"
echo "GPU: $(nvidia-smi --query-gpu=name --format=csv,noheader 2>/dev/null || echo 'N/A')"
echo ""

# Check PyTorch + CUDA
python -c "
import torch
print(f'PyTorch: {torch.__version__}')
print(f'CUDA available: {torch.cuda.is_available()}')
if torch.cuda.is_available():
    print(f'CUDA devices: {torch.cuda.device_count()}')
    print(f'Current device: {torch.cuda.current_device()}')
"

cd "$MHLAPRE_DIR"

echo ""
echo "=== Training MHLAPre on DS2 data ==="
python train_predict.py \
    --mode train \
    --data_dir "$HPC_BASE/rerun_v2" \
    --output_dir "$OUTPUT_DIR" \
    --model_dir "$MODEL_DIR" \
    --epochs 30 \
    --batch_size 128

echo ""
echo "=== Predicting on DS2 data ==="
python train_predict.py \
    --mode predict \
    --data_dir "$HPC_BASE/rerun_v2" \
    --output_dir "$OUTPUT_DIR" \
    --model_dir "$MODEL_DIR"

echo ""
echo "MHLAPre complete: $(date)"
