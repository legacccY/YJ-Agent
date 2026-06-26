#!/bin/bash
#SBATCH --job-name=netmhcpan_ba
#SBATCH --account=shuihuawang
#SBATCH --partition=cpudebug
#SBATCH --qos=cpudebug
#SBATCH --cpus-per-task=4
#SBATCH --mem=16G
#SBATCH --time=01:00:00
#SBATCH --output=/gpfs/work/bio/jiayu2403/quantimmu/logs/netmhcpan_ba_%j.out
#SBATCH --error=/gpfs/work/bio/jiayu2403/quantimmu/logs/netmhcpan_ba_%j.err

# ============================================================
# run_netmhcpan_ba.sh
# Service: quantimmu-bench §Tier-2  lever=NetMHCpan 4.1 -BA proxy baseline
#
# Prerequisite: run prep_netmhcpan_ba.py locally first, then upload
#   scripts/out/newtools/netmhcpan_ba_inputs/ to HPC (same relative path).
#
# What this script does:
#   Loops over every <allele_safe>.pep in INPUT_DIR (listed in allele_map.tsv),
#   calls netMHCpan-4.1 -BA -xls for each allele, saves output XLS to INPUT_DIR.
#
# HLA format note (see prep_netmhcpan_ba.py):
#   .pep filename:  HLA-A02-01.pep   (safe, no * or :)
#   CLI -a arg:     HLA-A02:01       (remove * keep :, read from allele_map.tsv)
#
# After this job finishes, run parse_netmhcpan_ba.py to produce
#   scripts/out/newtools/netmhcpan_ba_DS1DS2_scores.csv
#
# TODO: if cpudebug walltime is insufficient for large allele sets,
#       switch to --partition=cpu --qos=cpu (check available partitions with
#       `sinfo -s` on the HPC login node).
# ============================================================

set -e

ROOT=/gpfs/work/bio/jiayu2403/quantimmu
NETMHCPAN=${ROOT}/ext_tools/netMHCpan-4.1/netMHCpan
INPUT_DIR=${ROOT}/scripts/out/newtools/netmhcpan_ba_inputs
ALLELE_MAP=${INPUT_DIR}/allele_map.tsv

echo "=== NetMHCpan-4.1 -BA batch start ==="
echo "date        : $(date)"
echo "node        : ${SLURMD_NODENAME}"
echo "NETMHCPAN   : ${NETMHCPAN}"
echo "INPUT_DIR   : ${INPUT_DIR}"

# Sanity checks
if [ ! -x "$NETMHCPAN" ]; then
    echo "ERROR: netMHCpan binary not found or not executable: $NETMHCPAN" >&2
    exit 1
fi

if [ ! -f "$ALLELE_MAP" ]; then
    echo "ERROR: allele_map.tsv not found at $ALLELE_MAP" >&2
    echo "       Run prep_netmhcpan_ba.py first and upload the inputs/ dir to HPC." >&2
    exit 1
fi

mkdir -p "${ROOT}/logs"

fail_count=0
success_count=0

# allele_map.tsv: two-column TSV (no header)
#   col1 = allele_safe  (e.g. HLA-A02-01)
#   col2 = allele_nmhc  (e.g. HLA-A02:01)
while IFS=$'\t' read -r allele_safe allele_nmhc; do
    # Skip blank lines
    [ -z "$allele_safe" ] && continue

    pep_file="${INPUT_DIR}/${allele_safe}.pep"
    out_xls="${INPUT_DIR}/${allele_safe}_out.xls"

    if [ ! -f "$pep_file" ]; then
        echo "WARN: .pep not found for allele=$allele_safe (expected $pep_file), skipping."
        continue
    fi

    n_peps=$(wc -l < "$pep_file")
    echo ""
    echo "--- allele: $allele_nmhc  peptides: $n_peps  out: $(basename $out_xls) ---"

    # 用 if 包裹：set -e 对 if 条件里的命令不触发退出，单 allele 失败不中断整批
    if "$NETMHCPAN" \
        -p "$pep_file" \
        -BA \
        -a "$allele_nmhc" \
        -xls \
        -xlsfile "$out_xls"; then
        exit_code=0
    else
        exit_code=$?
    fi

    if [ $exit_code -ne 0 ]; then
        echo "ERROR: netMHCpan exit=$exit_code for $allele_safe" >&2
        fail_count=$((fail_count + 1))
    else
        echo "OK: $out_xls"
        success_count=$((success_count + 1))
    fi

done < "$ALLELE_MAP"

echo ""
echo "=== NetMHCpan-4.1 -BA batch done ==="
echo "success: $success_count   fail: $fail_count   $(date)"

if [ $fail_count -gt 0 ]; then
    echo "Some alleles failed. Check stderr above." >&2
    exit 1
fi

echo "Next: run parse_netmhcpan_ba.py to produce netmhcpan_ba_DS1DS2_scores.csv"
exit 0
