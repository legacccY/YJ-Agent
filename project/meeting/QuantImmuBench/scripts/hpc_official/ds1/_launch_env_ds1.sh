#!/bin/bash
# _launch_env_ds1.sh — DS1 slice_hpc_env 7 HPC 工具并行 launcher（DTN 登录节点后台）。
# 各工具独立 subshell 激活自己 env 并行跑，写各自 log + DONE 标记。DS2 precedent 同法。
# NeoTImmuML 走本机 R，不在此脚本。
BASE=/gpfs/work/bio/jiayu2403/quantimmu
D=$BASE/ds1
LOG=$D/logs
mkdir -p "$LOG"
module load miniconda3/22.11.1-gcc-8.5.0-l4fo6ta 2>/dev/null
CONDA_SH="$(conda info --base)/etc/profile.d/conda.sh"
echo "[LAUNCH_START $(date)] node=$(hostname)"

# 1 ImmuneApp（脚本自激活 immuneapp env）
( bash "$D/hpc_official/run_immuneapp_ds1.sh" > "$LOG/immuneapp.log" 2>&1 && touch "$LOG/IMMUNEAPP.done" ) &
# 2 PRIME（脚本自激活 prime env）
( bash "$D/hpc_official/run_prime_ds1.sh" > "$LOG/prime.log" 2>&1 && touch "$LOG/PRIME.done" ) &
# 3 PredIG（singularity 单块）
( bash "$D/hpc_official/run_predig_ds1.sh" > "$LOG/predig.log" 2>&1 && touch "$LOG/PREDIG.done" ) &
# 4 HLAthena（singularity）
( bash "$D/hpc_official/run_hlathena_ds1.sh" > "$LOG/hlathena.log" 2>&1 && touch "$LOG/HLATHENA.done" ) &
# 5 IMPROVE（env 覆盖复用 DS2 脚本，档 II STAB=1 FOREIGN=1）
( INPUT="$D/improve_input.tsv" OUTDIR="$D/improve_official_run" STAB=1 FOREIGN=1 \
    bash "$BASE/rerun8to11/hpc_official/run_improve_official.sh" > "$LOG/improve.log" 2>&1 \
    && touch "$LOG/IMPROVE.done" ) &
# 6 MHCflurry
( source "$CONDA_SH"; conda activate "$BASE/envs/mhcflurry"; \
    python "$BASE/rerun8to11/hpc_official/run_mhcflurry.py" \
      --input "$D/mhcflurry_input_official.csv" --raw-out "$D/mhcflurry_raw.csv" \
      > "$LOG/mhcflurry.log" 2>&1 && touch "$LOG/MHCFLURRY.done" ) &
# 7 MHCseqNet（借 immuneapp env）
( source "$CONDA_SH"; conda activate "$BASE/envs/immuneapp"; \
    python "$BASE/rerun8to11/hpc_official/run_mhcseqnet_official.py" \
      --input "$D/mhcseqnet_input_official.csv" --repo "$BASE/tools_repos/MHCSeqNet" \
      --out "$D/mhcseqnet_raw.csv" > "$LOG/mhcseqnet.log" 2>&1 && touch "$LOG/MHCSEQNET.done" ) &

wait
echo "[LAUNCH_ALL_DONE $(date)]"
touch "$LOG/ALL_ENV_DONE"
