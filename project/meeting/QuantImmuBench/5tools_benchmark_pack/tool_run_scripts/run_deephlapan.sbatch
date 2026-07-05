#!/bin/bash
#SBATCH --job-name=DHL_rerun
#SBATCH --output=/gpfs/work/bio/zichenli24/rerun_v2/01_DeepHLApan/logs/%j.out
#SBATCH --error=/gpfs/work/bio/zichenli24/rerun_v2/01_DeepHLApan/logs/%j.err
#SBATCH --time=04:00:00
#SBATCH --cpus-per-task=8
#SBATCH --mem=32G
#SBATCH --partition=short

source ~/.bashrc
conda activate deephlapan

HPC_BASE="/gpfs/work/bio/zichenli24"
INPUT_DIR="$HPC_BASE/rerun_v2/01_DeepHLApan/inputs"
OUTPUT_DIR="$HPC_BASE/rerun_v2/01_DeepHLApan/outputs"

echo "============================================"
echo " DeepHLApan — Dataset2 Complete (130 peptides)"
echo "============================================"
echo "Date: $(date)"
echo "Input:  $INPUT_DIR"
echo "Output: $OUTPUT_DIR"

# MT prediction
mkdir -p "$OUTPUT_DIR/dataset2_MT"
echo ""
echo "[1/2] Running MT prediction..."
deephlapan -F "$INPUT_DIR/DeepHLApan_dataset2_MT.csv" -O "$OUTPUT_DIR/dataset2_MT"
echo "  MT done: $(wc -l < "$OUTPUT_DIR/dataset2_MT/DeepHLApan_dataset2_MT_predicted_result.csv") lines"

# WT prediction
mkdir -p "$OUTPUT_DIR/dataset2_WT"
echo "[2/2] Running WT prediction..."
deephlapan -F "$INPUT_DIR/DeepHLApan_dataset2_WT.csv" -O "$OUTPUT_DIR/dataset2_WT"
echo "  WT done: $(wc -l < "$OUTPUT_DIR/dataset2_WT/DeepHLApan_dataset2_WT_predicted_result.csv") lines"

echo ""
echo "DeepHLApan complete: $(date)"
