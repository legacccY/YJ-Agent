#!/bin/bash
#SBATCH --job-name=fss_fugc
#SBATCH --partition=gpu3090
#SBATCH --account=shuihuawang
#SBATCH --qos=4gpus
#SBATCH --gres=gpu:1
#SBATCH --cpus-per-task=4
#SBATCH --time=03:00:00
#SBATCH --output=/gpfs/work/bio/jiayu2403/fetalss/logs/fugc_%x_%j.out
#SBATCH --error=/gpfs/work/bio/jiayu2403/fetalss/logs/fugc_%x_%j.err

PYBIN=/gpfs/work/bio/jiayu2403/.conda/envs/yjcu124py310/bin/python
FUGC_DIR="/gpfs/work/bio/jiayu2403/fetalss/data/FUGC"
export FETALSS_DATA_ROOT=/gpfs/work/bio/jiayu2403/fetalss/data
export OMP_NUM_THREADS=4
export KMP_DUPLICATE_LIB_OK=TRUE
cd /gpfs/work/bio/jiayu2403/fetalss/code

echo "=== fss_fugc start $(date)  SMOKE=${SMOKE:-0} ==="
$PYBIN -c "import torch; print('cuda', torch.cuda.is_available())"

# run_one arm_label method conf_thresh_or_empty seed
run_one() {
  local arm=$1 method=$2 conf=$3 seed=$4
  echo "---- ${arm} r=0.1 s=${seed} $(date +%H:%M:%S) ----"
  local extra=""
  [ -n "$conf" ] && extra="--conf_thresh $conf"
  $PYBIN harness.py --method $method $extra \
    --dataset fugc --ratio 0.1 --seed $seed \
    --data_dir "$FUGC_DIR" 2>&1 \
    | grep --line-buffered -E "\[done\]|RUN_FAIL|Error|Traceback"
  local py_exit=${PIPESTATUS[0]}
  [ $py_exit -ne 0 ] && echo "RUN_FAIL_fugc_${arm}_${seed}"
}

# ---- smoke test mode: only 1 run (freematch_sat seed 0) ----
if [ "${SMOKE:-}" = "1" ]; then
  echo "=== SMOKE MODE: 1 run only ==="
  run_one freematch_sat freematch_sat "" 0
  echo "=== smoke done $(date) ==="
  exit 0
fi

# ---- full matrix: 4 arms x seed 0-4 = 20 runs ----

# arm1: freematch_sat (no conf_thresh)
for S in 0 1 2 3 4; do
  run_one freematch_sat freematch_sat "" $S
done

# arm2: fixmatch conf=0.7
for S in 0 1 2 3 4; do
  run_one fixmatch_t07 fixmatch 0.7 $S
done

# arm3: fixmatch conf=0.8
for S in 0 1 2 3 4; do
  run_one fixmatch_t08 fixmatch 0.8 $S
done

# arm4: fixmatch conf=0.9
for S in 0 1 2 3 4; do
  run_one fixmatch_t09 fixmatch 0.9 $S
done

echo "=== fss_fugc done $(date) ==="
wc -l results/results.csv
