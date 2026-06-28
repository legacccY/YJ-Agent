#!/bin/bash
set -e
source ~/miniconda3/etc/profile.d/conda.sh 2>/dev/null || source ~/anaconda3/etc/profile.d/conda.sh 2>/dev/null
conda activate deepimmuno
BASE=/mnt/d/YJ-Agent/project/meeting/QuantImmuBench/scripts/out/phaseB
IN=$BASE/deepimmuno_input_101102.csv
OUT=$BASE/deepimmuno_out_101102
mkdir -p "$OUT"
cd ~/quantimmu/tools_repos/DeepImmuno
python deepimmuno-cnn.py --mode multiple --intdir "$IN" --outdir "$OUT" 2>&1 | tail -4
echo "=== OUTPUT FILES ==="
ls -la "$OUT"/
echo "=== HEAD ==="
head -4 "$OUT"/*.txt 2>/dev/null || echo "no txt output"
