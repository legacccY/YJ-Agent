#!/bin/bash
#SBATCH --job-name=EVAL_rerun
#SBATCH --output=/gpfs/work/bio/zichenli24/rerun_v2/06_analysis/logs/%j.out
#SBATCH --error=/gpfs/work/bio/zichenli24/rerun_v2/06_analysis/logs/%j.err
#SBATCH --time=00:30:00
#SBATCH --cpus-per-task=2
#SBATCH --mem=8G
#SBATCH --partition=short

source ~/.bashrc
conda activate base

HPC_BASE="/gpfs/work/bio/zichenli24"

echo "============================================"
echo " Three-Tier Evaluation — rerun_v2 (130 peptides)"
echo "============================================"
echo "Date: $(date)"

# Install deps if needed
python -c "import pandas, numpy, scipy, sklearn; print('Dependencies OK')"

# Run evaluation
cd "$HPC_BASE"
python tools/analysis/eval_v5_three_tier.py \
    --data-root "$HPC_BASE/rerun_v2" \
    --tools PRIME DeepHLApan ImmuneApp HLAthena MHLAPre \
    --output "$HPC_BASE/rerun_v2/06_analysis/outputs"

echo ""
echo "============================================"
echo " Evaluation Results:"
echo "============================================"
cat "$HPC_BASE/rerun_v2/06_analysis/outputs/metrics_three_tier.csv"

echo ""
echo "Evaluation complete: $(date)"
