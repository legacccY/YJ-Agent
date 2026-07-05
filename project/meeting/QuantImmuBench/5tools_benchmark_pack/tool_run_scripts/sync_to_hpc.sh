#!/bin/bash
# ===========================================================
# Sync rerun_v2 from local Windows to HPC
# Run this from Git Bash on Windows, or adapt for WSL
# ===========================================================
HPC_USER="zichenli24"
HPC_HOST="hpc.login.node"        # CHANGE THIS to your HPC hostname
HPC_BASE="/gpfs/work/bio/zichenli24"

echo "Syncing rerun_v2 to HPC..."
echo "Local:  $(pwd)"
echo "Remote: ${HPC_USER}@${HPC_HOST}:${HPC_BASE}/rerun_v2/"
echo ""

# Sync the entire rerun_v2 directory (excluding _hpc_scripts)
rsync -avz --progress \
    --exclude '_hpc_scripts' \
    --exclude '__pycache__' \
    --exclude '*.pyc' \
    ./ \
    "${HPC_USER}@${HPC_HOST}:${HPC_BASE}/rerun_v2/"

# Also sync the evaluation script to HPC tools dir
echo ""
echo "Syncing eval script..."
ssh "${HPC_USER}@${HPC_HOST}" "mkdir -p ${HPC_BASE}/tools/analysis"
rsync -avz \
    ../analysis/eval_v5_three_tier.py \
    "${HPC_USER}@${HPC_HOST}:${HPC_BASE}/tools/analysis/"

echo ""
echo "Done! Now SSH to HPC and run:"
echo "  cd ${HPC_BASE}/rerun_v2/_hpc_scripts"
echo "  bash submit_all.sh"
