#!/bin/bash
#SBATCH --job-name=IMM_rerun
#SBATCH --output=/gpfs/work/bio/zichenli24/rerun_v2/03_ImmuneApp/logs/%j.out
#SBATCH --error=/gpfs/work/bio/zichenli24/rerun_v2/03_ImmuneApp/logs/%j.err
#SBATCH --time=06:00:00
#SBATCH --cpus-per-task=4
#SBATCH --mem=16G
#SBATCH --partition=short

source ~/.bashrc
conda activate immuneapp

HPC_BASE="/gpfs/work/bio/zichenli24"
IMMUNEAPP_DIR="$HPC_BASE/tools/ImmuneApp"
INPUT_DIR="$HPC_BASE/rerun_v2/03_ImmuneApp/inputs"
OUTPUT_DIR="$HPC_BASE/rerun_v2/03_ImmuneApp/outputs"

mkdir -p "$OUTPUT_DIR"

echo "============================================"
echo " ImmuneApp — Dataset2 Complete (130 peptides)"
echo "============================================"
echo "Date: $(date)"

# Process MT peptides
echo ""
echo "=== Processing MT ==="
for txt in "$INPUT_DIR/dataset2_MT"/*.txt; do
    fname=$(basename "$txt" .txt)
    # Convert filename back to HLA format: HLA-A0101 -> HLA-A*01:01
    hla=$(echo "$fname" | sed 's/HLA-//' | sed 's/\([ABC]\)\([0-9][0-9]\)\([0-9][0-9]\)/\1*\2:\3/')
    out_subdir="$OUTPUT_DIR/dataset2_MT/$fname"
    mkdir -p "$out_subdir"

    echo "  $fname -> $hla"
    cd "$IMMUNEAPP_DIR"
    python ImmuneApp_immunogenicity_prediction.py \
        -f "$txt" \
        -a "$hla" \
        -o "$out_subdir"
done

# Process WT peptides
echo ""
echo "=== Processing WT ==="
for txt in "$INPUT_DIR/dataset2_WT"/*.txt; do
    fname=$(basename "$txt" .txt)
    hla=$(echo "$fname" | sed 's/HLA-//' | sed 's/\([ABC]\)\([0-9][0-9]\)\([0-9][0-9]\)/\1*\2:\3/')
    out_subdir="$OUTPUT_DIR/dataset2_WT/$fname"
    mkdir -p "$out_subdir"

    echo "  $fname -> $hla"
    cd "$IMMUNEAPP_DIR"
    python ImmuneApp_immunogenicity_prediction.py \
        -f "$txt" \
        -a "$hla" \
        -o "$out_subdir"
done

# Merge all results
echo ""
echo "=== Merging all results ==="
python -c "
import glob, pandas as pd, os
dfs = []
for tsv in glob.glob('$OUTPUT_DIR/**/ImmuneApp_Immunogenicity_predictions.tsv', recursive=True):
    dfs.append(pd.read_csv(tsv, sep='\t'))
if dfs:
    df = pd.concat(dfs, ignore_index=True)
    os.makedirs('$OUTPUT_DIR/all_results', exist_ok=True)
    df.to_csv('$OUTPUT_DIR/all_results/ImmuneApp_Immunogenicity_predictions.tsv', sep='\t', index=False)
    print(f'Merged {len(dfs)} files -> {len(df)} rows')
else:
    print('No results found!')
"

echo ""
echo "ImmuneApp complete: $(date)"
