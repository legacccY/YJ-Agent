#!/bin/bash
#SBATCH --job-name=netmhcstabpan
#SBATCH --account=shuihuawang
#SBATCH --partition=cpudebug
#SBATCH --qos=cpudebug
#SBATCH --cpus-per-task=4
#SBATCH --mem=16G
#SBATCH --time=01:00:00
#SBATCH --output=/gpfs/work/bio/jiayu2403/quantimmu/logs/netmhcstabpan_%j.out
#SBATCH --error=/gpfs/work/bio/jiayu2403/quantimmu/logs/netmhcstabpan_%j.err

# ============================================================================
# run_netmhcstabpan.sh
# Service: quantimmu-bench §tools_present  lever=netMHCstabpan-1.0 (DTU stability)
#
# Runs netMHCstabpan-1.0 INSIDE an apptainer container (net.sif) to dodge the
# GLIBC_2.29 vs el8-glibc-2.28 mismatch. See net.def header for the why.
#
# INPUT REUSE (important):
#   We reuse the EXACT same per-allele .pep files + allele_map.tsv that the
#   netMHCpan-4.1 -BA job uses (same peptides × alleles). Do NOT regenerate.
#     INPUT_DIR = .../scripts/out/newtools/netmhcpan_ba_inputs
#   Stability outputs are written to a SEPARATE dir so they don't clobber the
#   *_out.xls files of the -BA job:
#     OUT_DIR   = .../scripts/out/newtools/netmhcstabpan_inputs   (<allele>_stab.xls)
#
# After this job, run parse_netmhcstabpan.py to produce
#   scripts/out/newtools/netmhcstabpan_DS1DS2_scores.csv
#
# ⚠️⚠️ PREREQUISITES — all of these are MAIN-THREAD decision points, NOT done
#      by this kit (DTU academic license + outbound HPC transfer):
#   (a) netMHCstabpan-1.0 binary installed at:
#         ${ROOT}/ext_tools/netMHCstabpan-1.0/   (apply for it from DTU)
#   (b) netMHCpan-2.8 backend already present (DONE):
#         ${ROOT}/ext_tools/netMHCpan-2.8
#   (c) net.sif built and present next to this script (see net.def two routes).
#
# ⚠️⚠️ tcsh WRAPPER REWRITE CHECKLIST (do this ONCE before first run) ⚠️⚠️
#   The netMHCstabpan-1.0 launcher is a tcsh script. Near its top it sets
#   environment vars with HOST paths that will NOT exist inside the container.
#   You MUST edit them to the CONTAINER-VISIBLE (post-bind) paths:
#     setenv NMHOME   /ext_tools/netMHCstabpan-1.0      # was a /gpfs/... path
#     setenv TMPDIR   /tmp                              # must be writable in container
#   AND the wrapper points at its netMHCpan-2.8 backend — repoint that too, e.g.
#     setenv NETMHCpan /netMHCpan-2.8/netMHCpan         # backend bind target
#     (exact var name differs by install — grep the wrapper for 'netMHCpan' /
#      'NetMHCpan' / 'NMHOME' and fix every host path to its bind target.)
#   Likewise check netMHCpan-2.8's own wrapper for an NMHOME pointing at /gpfs.
#   If these are wrong you get "cannot find data directory" or backend-not-found
#   errors rather than a glibc error.
#
# ⚠️ FLAG TODO — the netMHCstabpan-1.0 backend is OLD (netMHCpan-2.8 era).
#    The flags below FOLLOW the net* family convention but are NOT verified for
#    this exact version. Before the real run, inside the container do:
#        apptainer exec net.sif /ext_tools/netMHCstabpan-1.0/netMHCstabpan -h
#    and confirm: peptide-file flag (-p), allele flag (-a, comma-joined no
#    spaces), and whether -xls/-xlsfile exist (older builds may only print to
#    stdout → then redirect stdout to <allele>_stab.xls instead of -xlsfile).
# ============================================================================

set -e

ROOT=/gpfs/work/bio/jiayu2403/quantimmu
SIF="$(dirname "$0")/net.sif"
STABPAN_IN_CONTAINER=/ext_tools/netMHCstabpan-1.0/netMHCstabpan

# Reuse the -BA job inputs (same peptides × alleles).
INPUT_DIR=${ROOT}/scripts/out/newtools/netmhcpan_ba_inputs
ALLELE_MAP=${INPUT_DIR}/allele_map.tsv
# Separate output dir so we don't overwrite the -BA *_out.xls files.
OUT_DIR=${ROOT}/scripts/out/newtools/netmhcstabpan_inputs

echo "=== netMHCstabpan-1.0 batch start ==="
echo "date        : $(date)"
echo "node        : ${SLURMD_NODENAME}"
echo "SIF         : ${SIF}"
echo "INPUT_DIR   : ${INPUT_DIR}"
echo "OUT_DIR     : ${OUT_DIR}"

# Sanity checks ---------------------------------------------------------------
if [ ! -f "$SIF" ]; then
    echo "ERROR: container not found: $SIF" >&2
    echo "       Build net.sif first (see net.def header), it must sit beside this script." >&2
    exit 1
fi

if [ ! -d "${ROOT}/ext_tools/netMHCstabpan-1.0" ]; then
    echo "ERROR: netMHCstabpan-1.0 not installed at ${ROOT}/ext_tools/netMHCstabpan-1.0" >&2
    echo "       Apply for the DTU academic binary and install it there first." >&2
    exit 1
fi

if [ ! -d "${ROOT}/ext_tools/netMHCpan-2.8" ]; then
    echo "ERROR: netMHCpan-2.8 backend not found at ${ROOT}/ext_tools/netMHCpan-2.8" >&2
    exit 1
fi

if [ ! -f "$ALLELE_MAP" ]; then
    echo "ERROR: allele_map.tsv not found at $ALLELE_MAP" >&2
    echo "       The netMHCpan_ba inputs must already be on HPC (we reuse them)." >&2
    exit 1
fi

mkdir -p "${ROOT}/logs"
mkdir -p "${OUT_DIR}"

# Container bind layout:
#   host ${ROOT}/ext_tools                     -> /ext_tools
#   host ${ROOT}/ext_tools/netMHCpan-2.8       -> /netMHCpan-2.8   (backend, see wrapper rewrite)
#   host ${INPUT_DIR} and ${OUT_DIR} live under ${ROOT} which is bound too, but
#   we bind them explicitly so paths are stable regardless of ROOT layout.
BINDS="--bind ${ROOT}/ext_tools:/ext_tools \
       --bind ${ROOT}/ext_tools/netMHCpan-2.8:/netMHCpan-2.8 \
       --bind ${INPUT_DIR}:/pep_in \
       --bind ${OUT_DIR}:/pep_out"

fail_count=0
success_count=0

# allele_map.tsv: two-column TSV (no header)
#   col1 = allele_safe     (e.g. HLA-A02-01)
#   col2 = allele_netmhcpan (e.g. HLA-A02:01)
while IFS=$'\t' read -r allele_safe allele_nmhc; do
    [ -z "$allele_safe" ] && continue

    pep_file_host="${INPUT_DIR}/${allele_safe}.pep"
    pep_file_cont="/pep_in/${allele_safe}.pep"
    out_xls_host="${OUT_DIR}/${allele_safe}_stab.xls"
    out_xls_cont="/pep_out/${allele_safe}_stab.xls"

    if [ ! -f "$pep_file_host" ]; then
        echo "WARN: .pep not found for allele=$allele_safe (expected $pep_file_host), skipping."
        continue
    fi

    n_peps=$(wc -l < "$pep_file_host")
    echo ""
    echo "--- allele: $allele_nmhc  peptides: $n_peps  out: $(basename $out_xls_host) ---"

    # ⚠️ FLAG TODO (see header): -a / -p / -xls / -xlsfile assumed by net*
    #    convention; verify with `netMHCstabpan -h` in the container first.
    #    If this build has no -xls, drop -xls/-xlsfile and redirect stdout:
    #        ... netMHCstabpan -a "$allele_nmhc" -p "$pep_file_cont" > "$out_xls_host"
    if apptainer exec ${BINDS} "$SIF" \
        "$STABPAN_IN_CONTAINER" \
        -a "$allele_nmhc" \
        -p "$pep_file_cont" \
        -xls \
        -xlsfile "$out_xls_cont"; then
        exit_code=0
    else
        exit_code=$?
    fi

    if [ $exit_code -ne 0 ]; then
        echo "ERROR: netMHCstabpan exit=$exit_code for $allele_safe" >&2
        fail_count=$((fail_count + 1))
    else
        echo "OK: $out_xls_host"
        success_count=$((success_count + 1))
    fi

done < "$ALLELE_MAP"

echo ""
echo "=== netMHCstabpan-1.0 batch done ==="
echo "success: $success_count   fail: $fail_count   $(date)"

if [ $fail_count -gt 0 ]; then
    echo "Some alleles failed. Check stderr above." >&2
    exit 1
fi

echo "Next: run parse_netmhcstabpan.py to produce netmhcstabpan_DS1DS2_scores.csv"
exit 0
