#!/usr/bin/env bash
# Reproduce Table 1 + Table 3 of the paper.
# Runtime: ~2h on a single A100.
set -euo pipefail

DATA_DIR="${DATA_DIR:-./data}"
OUT_DIR="${OUT_DIR:-./outputs}"
mkdir -p "$OUT_DIR"

echo "=== ITB + QCTS Reproduction Script ==="

# ── Step 1: Download ITB v1.0 ────────────────────────────────────────────────
echo "[1/5] Downloading ITB v1.0..."
python scripts/download_itb.py --data_dir "$DATA_DIR"

# ── Step 2: Build ITB partitions ─────────────────────────────────────────────
echo "[2/5] Building ITB quality-stratified partitions..."
python scripts/build_itb.py \
    --data_dir "$DATA_DIR" \
    --output_dir "$OUT_DIR/itb_partitions"

# ── Step 3: Run baselines (EfficientNet / Std VIB / TS / MC Dropout / DE / EDL) ─
echo "[3/5] Running baseline evaluations..."
python scripts/run_evaluation.py \
    --itb_dir "$OUT_DIR/itb_partitions" \
    --output_dir "$OUT_DIR/baselines" \
    --config configs/default.yaml

# ── Step 4: Fit and evaluate QCTS ────────────────────────────────────────────
echo "[4/5] Fitting QCTS and evaluating..."
python scripts/run_qcts.py \
    --itb_dir "$OUT_DIR/itb_partitions" \
    --baselines_dir "$OUT_DIR/baselines" \
    --output_dir "$OUT_DIR/qcts"

# ── Step 5: Generate Tables 1 & 3 ────────────────────────────────────────────
echo "[5/5] Generating paper tables..."
python scripts/generate_tables.py \
    --baselines_dir "$OUT_DIR/baselines" \
    --qcts_dir "$OUT_DIR/qcts" \
    --output_dir "$OUT_DIR/tables"

echo ""
echo "Done. Tables written to $OUT_DIR/tables/"
echo "  table1_main.tex   — Table 1 (main results)"
echo "  table3_universality.tex — Table 3 (backbone universality)"
