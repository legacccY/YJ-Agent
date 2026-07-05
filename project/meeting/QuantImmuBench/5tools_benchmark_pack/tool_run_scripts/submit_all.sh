#!/bin/bash
# ===========================================================
# rerun_v2 — Master HPC Submission Script
# ===========================================================
# Usage:  bash submit_all.sh
#
# Order:  DeepHLApan + PRIME + HLAthena  (parallel)
#         ImmuneApp                         (after DeepHLApan)
#         MHLAPre                           (after DeepHLApan + PRIME)
#         eval_v5                            (after all)
# ===========================================================

HPC_BASE="/gpfs/work/bio/zichenli24"
SCRIPT_DIR="$HPC_BASE/rerun_v2/_hpc_scripts"

echo "============================================"
echo " Submitting rerun_v2 Pipeline"
echo "============================================"
echo "Time: $(date)"
echo ""

# ── Step 1: Parallel (DeepHLApan + PRIME + HLAthena) ──
echo "[Step 1] Submitting DeepHLApan..."
JOB_DHL=$(sbatch --parsable "$SCRIPT_DIR/run_deephlapan.sbatch")
echo "  -> Job ID: $JOB_DHL"

echo "[Step 1] Submitting PRIME..."
JOB_PRM=$(sbatch --parsable "$SCRIPT_DIR/run_prime.sbatch")
echo "  -> Job ID: $JOB_PRM"

echo "[Step 1] Submitting HLAthena..."
JOB_ATH=$(sbatch --parsable "$SCRIPT_DIR/run_hlathena.sbatch")
echo "  -> Job ID: $JOB_ATH"

# ── Step 2: ImmuneApp (after DeepHLApan) ──
echo "[Step 2] Submitting ImmuneApp (after DeepHLApan)..."
JOB_IMM=$(sbatch --parsable --dependency=afterok:$JOB_DHL "$SCRIPT_DIR/run_immuneapp.sbatch")
echo "  -> Job ID: $JOB_IMM"

# ── Step 3: MHLAPre (after DeepHLApan + PRIME) ──
echo "[Step 3] Submitting MHLAPre (after DeepHLApan & PRIME)..."
JOB_MHL=$(sbatch --parsable --dependency=afterok:$JOB_DHL:$JOB_PRM "$SCRIPT_DIR/run_mhlapre.sbatch")
echo "  -> Job ID: $JOB_MHL"

# ── Step 4: Evaluation (after all) ──
echo "[Step 4] Submitting Evaluation (after all tools)..."
JOB_EVAL=$(sbatch --parsable --dependency=afterok:$JOB_IMM:$JOB_MHL:$JOB_ATH "$SCRIPT_DIR/run_evaluation.sbatch")
echo "  -> Job ID: $JOB_EVAL"

echo ""
echo "============================================"
echo " All jobs submitted!"
echo "============================================"
echo ""
echo "Monitor:  squeue -u \$USER"
echo "Status:   bash $SCRIPT_DIR/check_status.sh"
echo ""
echo "Pipeline:"
echo "  DeepHLApan ($JOB_DHL) ──┬── ImmuneApp ($JOB_IMM) ──┐"
echo "  PRIME      ($JOB_PRM) ──┼── MHLAPre   ($JOB_MHL) ──┼── Eval ($JOB_EVAL)"
echo "  HLAthena   ($JOB_ATH) ──┘                            │"
echo "                                                       │"
echo "  All complete ────────────────────────────────────────┘"
