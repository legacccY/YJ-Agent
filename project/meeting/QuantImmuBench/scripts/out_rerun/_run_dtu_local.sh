#!/bin/bash
# 本地 WSL DTU netMHCpan 家族批跑（rerun）。用法: _run_dtu_local.sh <ba|stab>
# ba   : netMHCpan-4.1 -BA -xls  → <allele>_out.xls   (BA+EL 同批)
# stab : netMHCstabpan-1.0        → <allele>_stab.xls
set -u
MODE="${1:-ba}"
IN=/mnt/d/YJ-Agent/project/meeting/QuantImmuBench/scripts/out_rerun/dtu_netmhcpan_inputs
NMP=/root/quantimmu/ext_tools/netMHCpan-4.1/netMHCpan
STAB=/root/quantimmu/ext_tools/netMHCstabpan-1.0/netMHCstabpan
LOG=$IN/run_${MODE}.log
: > "$LOG"
ok=0; fail=0
while IFS=$'\t' read -r safe nmhc; do
    [ -z "${safe:-}" ] && continue
    pep="$IN/$safe.pep"
    [ ! -f "$pep" ] && { echo "MISS $safe" >> "$LOG"; continue; }
    if [ "$MODE" = "ba" ]; then
        out="$IN/${safe}_out.xls"
        if "$NMP" -p "$pep" -BA -a "$nmhc" -xls -xlsfile "$out" >/dev/null 2>>"$LOG"; then
            ok=$((ok+1)); echo "OK $safe" >> "$LOG"
        else fail=$((fail+1)); echo "FAIL $safe" >> "$LOG"; fi
    else
        out="$IN/${safe}_stab.xls"
        if "$STAB" -p "$pep" -a "$nmhc" -xls -xlsfile "$out" >/dev/null 2>>"$LOG"; then
            ok=$((ok+1)); echo "OK $safe" >> "$LOG"
        else fail=$((fail+1)); echo "FAIL $safe" >> "$LOG"; fi
    fi
done < "$IN/allele_map.tsv"
echo "DONE mode=$MODE ok=$ok fail=$fail" >> "$LOG"
