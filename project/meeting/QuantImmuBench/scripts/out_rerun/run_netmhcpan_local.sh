#!/bin/bash
# 本地 WSL netMHCpan-4.1 -BA -xls 批跑（rerun, out_rerun 输入）
# 一次 -xls 同出 BA + EL 列。服务 quantimmu-rerun slice_dtu。
set -u
NMP=/root/quantimmu/ext_tools/netMHCpan-4.1/netMHCpan
IN=/mnt/d/YJ-Agent/project/meeting/QuantImmuBench/scripts/out_rerun/netmhcpan_ba_inputs
LOG=$IN/run_ba.log
: > "$LOG"
ok=0; fail=0
while IFS=$'\t' read -r safe nmhc; do
    [ -z "${safe:-}" ] && continue
    pep="$IN/$safe.pep"
    out="$IN/${safe}_out.xls"
    if [ ! -f "$pep" ]; then echo "MISS $safe" >> "$LOG"; continue; fi
    if "$NMP" -p "$pep" -BA -a "$nmhc" -xls -xlsfile "$out" >/dev/null 2>>"$LOG"; then
        ok=$((ok+1)); echo "OK $safe peps=$(wc -l < "$pep")" >> "$LOG"
    else
        fail=$((fail+1)); echo "FAIL $safe" >> "$LOG"
    fi
done < "$IN/allele_map.tsv"
echo "DONE ok=$ok fail=$fail" >> "$LOG"
