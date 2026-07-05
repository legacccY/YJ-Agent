#!/bin/bash
#SBATCH --job-name=PRIME_rerun
#SBATCH --output=/gpfs/work/bio/zichenli24/rerun_v2/02_PRIME/logs/%j.out
#SBATCH --error=/gpfs/work/bio/zichenli24/rerun_v2/02_PRIME/logs/%j.err
#SBATCH --time=08:00:00
#SBATCH --cpus-per-task=4
#SBATCH --mem=16G
#SBATCH --partition=short

source ~/.bashrc
conda activate prime

HPC_BASE="/gpfs/work/bio/zichenli24"
INPUT_DIR="$HPC_BASE/rerun_v2/02_PRIME/inputs"
OUTPUT_DIR="$HPC_BASE/rerun_v2/02_PRIME/outputs"
PRIME_DIR="$HPC_BASE/tools/PRIME"
MIXMHCPRED_DIR="$HPC_BASE/tools/MixMHCpred"

mkdir -p "$OUTPUT_DIR"

echo "============================================"
echo " PRIME — Dataset2 Complete (130 peptides)"
echo "============================================"
echo "Date: $(date)"

# Read HLA alleles
HLA_LIST=$(cat "$INPUT_DIR/HLA_alleles.txt" | tr '\n' ',' | sed 's/,$//')
echo "HLA alleles: $HLA_LIST"
echo ""

# MT prediction
echo "[1/2] Running MT prediction..."
"$PRIME_DIR/PRIME" \
    -i "$INPUT_DIR/PRIME_database2_MT.txt" \
    -o "$OUTPUT_DIR/dataset2_MT_prime.txt" \
    -a "$HLA_LIST" \
    -mix "$MIXMHCPRED_DIR/MixMHCpred"

MT_LINES=$(wc -l < "$OUTPUT_DIR/dataset2_MT_prime.txt")
echo "  MT done: $MT_LINES lines"

# WT prediction
echo "[2/2] Running WT prediction..."
"$PRIME_DIR/PRIME" \
    -i "$INPUT_DIR/PRIME_database2_WT.txt" \
    -o "$OUTPUT_DIR/dataset2_WT_prime.txt" \
    -a "$HLA_LIST" \
    -mix "$MIXMHCPRED_DIR/MixMHCpred"

WT_LINES=$(wc -l < "$OUTPUT_DIR/dataset2_WT_prime.txt")
echo "  WT done: $WT_LINES lines"

echo ""
echo "PRIME complete: $(date)"
