#!/bin/bash
PY=/root/miniconda3/bin/python
PROJ=/mnt/d/YJ-Agent/project/meeting/QuantImmuBench
MODE="${1:-smoke}"
ARGS="--prime-dir /root/quantimmu/tools_repos/PRIME --mix /root/quantimmu/tools_repos/MixMHCpred/MixMHCpred --activate true"
if [ "$MODE" = "smoke" ]; then ARGS="$ARGS --smoke 2"; fi
cd $PROJ
$PY scripts/phaseB/run_prime_101102.py $ARGS 2>&1 | tail -18
