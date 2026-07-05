#!/bin/bash
# Check rerun_v2 pipeline status
echo "============================================"
echo " rerun_v2 Pipeline Status"
echo "============================================"
echo "Time: $(date)"
echo ""

HPC_BASE="/gpfs/work/bio/zichenli24"

check_output() {
    local desc="$1"
    local path="$2"
    local expected="$3"
    if [ -f "$path" ]; then
        local lines=$(wc -l < "$path" 2>/dev/null || echo 0)
        if [ "$lines" -gt "$expected" ]; then
            echo "  [OK]    $desc ($lines lines)"
        else
            echo "  [WARN]  $desc ($lines lines, expected >$expected)"
        fi
    elif [ -d "$path" ]; then
        local files=$(ls "$path" 2>/dev/null | wc -l)
        if [ "$files" -gt 0 ]; then
            echo "  [OK]    $desc ($files files)"
        else
            echo "  [WAIT]  $desc (empty dir)"
        fi
    else
        echo "  [WAIT]  $desc (not found)"
    fi
}

echo "--- DeepHLApan ---"
check_output "MT results" "$HPC_BASE/rerun_v2/01_DeepHLApan/outputs/dataset2_MT/DeepHLApan_dataset2_MT_predicted_result.csv" 20000
check_output "WT results" "$HPC_BASE/rerun_v2/01_DeepHLApan/outputs/dataset2_WT/DeepHLApan_dataset2_WT_predicted_result.csv" 10000

echo ""
echo "--- PRIME ---"
check_output "MT results" "$HPC_BASE/rerun_v2/02_PRIME/outputs/dataset2_MT_prime.txt" 5000
check_output "WT results" "$HPC_BASE/rerun_v2/02_PRIME/outputs/dataset2_WT_prime.txt" 3000

echo ""
echo "--- HLAthena ---"
check_output "Patient outputs" "$HPC_BASE/rerun_v2/04_HLAthena/outputs/" 0

echo ""
echo "--- ImmuneApp ---"
check_output "MT all_results" "$HPC_BASE/rerun_v2/03_ImmuneApp/outputs/all_results/ImmuneApp_Immunogenicity_predictions.tsv" 5000

echo ""
echo "--- MHLAPre ---"
check_output "Predictions" "$HPC_BASE/rerun_v2/05_MHLAPre/outputs/" 0

echo ""
echo "--- Evaluation ---"
check_output "Metrics CSV" "$HPC_BASE/rerun_v2/06_analysis/outputs/metrics_three_tier.csv" 2

echo ""
echo "--- Job Queue ---"
squeue -u "$USER" 2>/dev/null || echo "  (squeue not available)"
