#!/usr/bin/env bash
# reproduce.sh — One-command reproduction of VisiSkin-Agent main results
# Expected runtime: ~30 min on RTX 4070 (with pretrained weights from Zenodo)
# Full training from scratch: ~3 hours

set -e

CKPT_DIR="${CKPT_DIR:-../checkpoints}"
DATA_DIR="${DATA_DIR:-../data}"
SEED="${SEED:-42}"

echo "=== VisiSkin-Agent Reproduction Script ==="
echo "Checkpoints: $CKPT_DIR | Data: $DATA_DIR | Seed: $SEED"
echo ""

# ── Step 0: Environment check ─────────────────────────────────────────────────
echo "[0/5] Checking environment..."
python -c "
import torch, numpy, pandas, cv2, omegaconf, timm
print(f'  torch {torch.__version__} | CUDA: {torch.cuda.is_available()}')
print(f'  numpy {numpy.__version__} | pandas {pandas.__version__}')
"

# ── Step 1: Verify data ───────────────────────────────────────────────────────
echo ""
echo "[1/5] Verifying data assets..."
python -c "
import os, sys
required = [
    '$DATA_DIR/efficientnet_features.npy',
    '$DATA_DIR/isic_split.csv',
    '$DATA_DIR/quality_labels_all.csv',
    '$DATA_DIR/abcd_cache.csv',
]
missing = [f for f in required if not os.path.exists(f)]
if missing:
    print('Missing files:')
    for f in missing: print(f'  {f}')
    print()
    print('Download pretrained features from Zenodo (DOI: TBD) and place in data/')
    print('Or run: python precompute_efficientnet.py && python create_split.py')
    sys.exit(1)
print('  All data assets found.')
"

# ── Step 2: Run test suite ────────────────────────────────────────────────────
echo ""
echo "[2/5] Running test suite..."
python -m pytest tests/ -q --timeout=60
echo "  All tests passed."

# ── Step 3: Build ITB benchmark ───────────────────────────────────────────────
echo ""
echo "[3/5] Building ITB benchmark subsets..."
python benchmark/build_itb.py
echo "  ITB subsets built -> results/itb_subsets.csv"

# ── Step 4: Run inference ─────────────────────────────────────────────────────
echo ""
echo "[4/5] Running ITB inference for all baselines..."
echo "  (Using pretrained checkpoints from $CKPT_DIR)"

for BASELINE in A D E F G TS H I J; do
    echo "  Baseline $BASELINE..."
    python run_experiments.py --baseline $BASELINE
done

echo "  Inference complete -> results/itb_results.csv"

# ── Step 5: Generate figures ──────────────────────────────────────────────────
echo ""
echo "[5/5] Generating paper figures..."
python analyze_results.py
echo "  Figures saved to results/figures/ (DPI 300)"

echo ""
echo "=== Reproduction complete ==="
echo "Main results: results/itb_results.csv"
echo "Figures:      results/figures/"
echo ""
echo "Key metrics (ITB-LQ):"
python -c "
import pandas as pd
df = pd.read_csv('results/itb_results.csv')
lq = df[df['subset']=='ITB-LQ'][['baseline_name','auc','ece']].sort_values('ece')
print(lq.to_string(index=False))
"
