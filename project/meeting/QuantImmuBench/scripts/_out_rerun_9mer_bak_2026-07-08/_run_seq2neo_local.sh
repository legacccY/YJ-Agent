#!/bin/bash
# 本地 WSL Seq2Neo immuno --mode multiple（rerun）。用法: _run_seq2neo_local.sh <input_csv> <outdir>
set -u
IN="${1}"
OUT="${2}"
export PATH="/root/quantimmu/ext_tools/netMHCpan-4.1:/root/quantimmu/tools_repos/pTuneos/software/netchop/netctlpan_1_1_executable:$PATH"
mkdir -p "$OUT"
echo "netMHCpan: $(which netMHCpan)"
echo "netCTLpan: $(which netCTLpan)"
/root/miniconda3/envs/seq2neo/bin/seq2neo immuno --mode multiple --inputfile "$IN" --outdir "$OUT"
echo "EXIT=$?"
ls -la "$OUT"
