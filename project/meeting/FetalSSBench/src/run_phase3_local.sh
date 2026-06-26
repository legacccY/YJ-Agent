#!/bin/bash
# Phase3 本地 sweep：4 臂(freematch_sat + fixmatch τ{.7,.8,.9}) × {psfhs,hc18,fugc} × ratios × seed0-4
# 单 run ~1min(PSFHS)；state.json 自动 skip 已跑，可断点续。承重 PSFHS 先跑。
set -u
cd "$(dirname "$0")"
export KMP_DUPLICATE_LIB_OK=TRUE OMP_NUM_THREADS=4
export FUGC_DATA="D:\YJ-Agent\project\meeting\_run011_pilot\data\FUGC"
LOG=phase3_sweep.log
echo "=== Phase3 local sweep start $(date) ===" | tee $LOG

run_arm () {  # $1=method $2=extra_args(conf_thresh) $3=dataset $4=ratios
  local M=$1 EXTRA=$2 DS=$3 RATIOS=$4
  local DD=""
  [ "$DS" = "fugc" ] && DD="--data_dir $FUGC_DATA"
  for R in $RATIOS; do
    for S in 0 1 2 3 4; do
      echo "---- $M $EXTRA $DS r=$R s=$S $(date +%H:%M:%S) ----" | tee -a $LOG
      python harness.py --method $M --dataset $DS --ratio $R --seed $S $EXTRA $DD 2>&1 \
        | grep -E "\[done\]|RUN_FAIL|Error|Traceback" | tee -a $LOG
    done
  done
}

# 承重 PSFHS 先 (5 ratios × 5 seed × 4 臂 = 100 run)
for DS in psfhs hc18; do
  run_arm freematch_sat ""               $DS "0.01 0.02 0.05 0.10 0.20"
  run_arm fixmatch      "--conf_thresh 0.7" $DS "0.01 0.02 0.05 0.10 0.20"
  run_arm fixmatch      "--conf_thresh 0.8" $DS "0.01 0.02 0.05 0.10 0.20"
  run_arm fixmatch      "--conf_thresh 0.9" $DS "0.01 0.02 0.05 0.10 0.20"
done
# FUGC (官方固定 split, ratio 0.1, 4 臂 × 5 seed = 20 run)
run_arm freematch_sat ""               fugc "0.1"
run_arm fixmatch      "--conf_thresh 0.7" fugc "0.1"
run_arm fixmatch      "--conf_thresh 0.8" fugc "0.1"
run_arm fixmatch      "--conf_thresh 0.9" fugc "0.1"

echo "=== Phase3 local sweep DONE $(date) ===" | tee -a $LOG
wc -l results/results.csv | tee -a $LOG
