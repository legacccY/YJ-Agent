#!/bin/bash
#SBATCH --job-name=ATH_rerun
#SBATCH --output=/gpfs/work/bio/zichenli24/rerun_v2/04_HLAthena/logs/%j.out
#SBATCH --error=/gpfs/work/bio/zichenli24/rerun_v2/04_HLAthena/logs/%j.err
#SBATCH --time=06:00:00
#SBATCH --cpus-per-task=8
#SBATCH --mem=32G
#SBATCH --partition=short

source ~/.bashrc

HPC_BASE="/gpfs/work/bio/zichenli24"
INPUT_DIR="$HPC_BASE/rerun_v2/04_HLAthena/inputs"
OUTPUT_DIR="$HPC_BASE/rerun_v2/04_HLAthena/outputs"
HLATHENA_SIF="$HPC_BASE/tools/hlathena.sif"

mkdir -p "$OUTPUT_DIR"

echo "============================================"
echo " HLAthena — Dataset2 Complete (130 peptides)"
echo "============================================"
echo "Date: $(date)"

# HLAthena allele list per patient (from reference MOESM4)
# Patient : Alleles
declare -A ALLELES
ALLELES[101]="HLA-B*57:01,HLA-B*40:01,HLA-C*06:02,HLA-A*66:01"
ALLELES[102]="HLA-B*35:03,HLA-A*02:01,HLA-B*38:01"
ALLELES[104]="HLA-A*01:01,HLA-C*07:01,HLA-B*08:01,HLA-C*06:02,HLA-B*13:02,HLA-A*30:01"
ALLELES[105]="HLA-C*07:01,HLA-B*08:01,HLA-A*01:01"
ALLELES[106]="HLA-C*03:03,HLA-A*03:01,HLA-B*40:01,HLA-B*55:01,HLA-A*31:01"
ALLELES[107]="HLA-A*32:01,HLA-A*02:01,HLA-B*44:02,HLA-C*05:01"
ALLELES[108]="HLA-A*02:01,HLA-B*27:05,HLA-B*27:06"
ALLELES[109]="HLA-B*44:02,HLA-A*02:01,HLA-C*05:01,HLA-B*08:01,HLA-B*44:02,HLA-C*07:01"
ALLELES[110]="HLA-A*03:01,HLA-B*18:01,HLA-B*07:02,HLA-C*07:02,HLA-C*12:03,HLA-A*25:01"

for PID in 101 102 104 105 106 107 108 109 110; do
    INPUT_FILE="$INPUT_DIR/d2_patient${PID}.txt"
    if [ ! -f "$INPUT_FILE" ]; then
        echo "  [SKIP] Patient $PID: input not found: $INPUT_FILE"
        continue
    fi

    echo ""
    echo "  Patient $PID: ${ALLELES[$PID]}"

    singularity exec "$HLATHENA_SIF" predict \
        --runID "d2_p${PID}" \
        --rundir "$OUTPUT_DIR" \
        --peptides "$INPUT_FILE" \
        --alleles "${ALLELES[$PID]}" \
        --run_ctex true \
        --expr_col_name TPM \
        --logtransform_expr true \
        --peptide_col_name pep

    echo "  Patient $PID: done"
done

echo ""
echo "HLAthena complete: $(date)"
