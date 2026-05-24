#!/usr/bin/env bash
# Reproduces Table 1 and Table 3. ~2h on an A100, ~8h on a 4070.
set -euo pipefail

DATA_DIR="${DATA_DIR:-./data}"
OUT_DIR="${OUT_DIR:-./outputs}"
mkdir -p "$OUT_DIR"

python scripts/download_itb.py --data_dir "$DATA_DIR"

python scripts/build_itb.py \
    --data_dir "$DATA_DIR" \
    --output_dir "$OUT_DIR/itb_partitions"

python scripts/run_evaluation.py \
    --itb_dir "$OUT_DIR/itb_partitions" \
    --output_dir "$OUT_DIR/baselines" \
    --config configs/default.yaml

python scripts/run_qcts.py \
    --itb_dir "$OUT_DIR/itb_partitions" \
    --baselines_dir "$OUT_DIR/baselines" \
    --output_dir "$OUT_DIR/qcts"

python scripts/generate_tables.py \
    --baselines_dir "$OUT_DIR/baselines" \
    --qcts_dir "$OUT_DIR/qcts" \
    --output_dir "$OUT_DIR/tables"

echo "Tables in $OUT_DIR/tables/: table1_main.tex, table3_universality.tex"
