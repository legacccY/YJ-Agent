#!/bin/bash
PROJ=/mnt/d/YJ-Agent/project/meeting/QuantImmuBench
TPY=/root/miniconda3/envs/tscape/bin/python
TDIR=/root/quantimmu/tools_repos/T-SCAPE
MODE="${1:-smoke}"
ARGS="--tscape-dir $TDIR --tscape-python $TPY"
if [ "$MODE" = "smoke" ]; then ARGS="$ARGS --smoke 5"; fi
cd $PROJ
$TPY scripts/phaseB/run_tscape_101102.py $ARGS 2>&1 | tail -22
