#!/bin/bash
# NetTepi-only 重跑（补 PYTHON_ENV export）。stabpan/ICERFIRE 不动。
set -u
ROOT=/gpfs/work/bio/jiayu2403/quantimmu
RERUN=$ROOT/rerun
IN=$RERUN/dtu_netmhcpan_inputs
ALLELE_MAP=$IN/allele_map.tsv
module load miniconda3/22.11.1-gcc-8.5.0-l4fo6ta 2>/dev/null
source "$(conda info --base)/etc/profile.d/conda.sh" 2>/dev/null
conda activate $ROOT/envs/qib_py27
PY27=$(which python2.7)
export PATH="$ROOT/envs/qib_perl/bin:$PATH"
export PERL5LIB="$ROOT/envs/qib_perl/lib/perl5/core_perl:${PERL5LIB:-}"
export NTHOME=$ROOT/ext_tools/netTepi-1.0
export NETMHCCONS_ENV=$ROOT/ext_tools/netMHCcons-1.1/netMHCcons
export NETMHCSTAB_ENV=$ROOT/ext_tools/netMHCstabpan-1.0/netMHCstabpan
export PYTHON_ENV="$PY27"
export TMPDIR=$ROOT/nettepi_tmp; mkdir -p $TMPDIR
NETTEPI=$ROOT/ext_tools/netTepi-1.0/netTepi.py
ALLELES_LST=$ROOT/ext_tools/netTepi-1.0/alleles.lst
supported=$(tr -d ' ' < $ALLELES_LST)
: > $RERUN/logs/nettepi.err
nt=0; nsk=0
while IFS=$'\t' read -r safe nmhc; do
  [ -z "$safe" ] && continue
  if ! echo "$supported" | grep -qx "$nmhc"; then nsk=$((nsk+1)); continue; fi
  pep=$IN/$safe.pep
  [ -s "$pep" ] || continue
  if $PY27 $NETTEPI -a "$nmhc" -p "$pep" -l 9 > $RERUN/nettepi_out/${safe}_nettepi.txt 2>$RERUN/nettepi_out/${safe}_nettepi.err; then
    nt=$((nt+1)); echo "NT OK $nmhc"
  else
    echo "NT FAIL $safe $nmhc" >> $RERUN/logs/nettepi.err
  fi
done < $ALLELE_MAP
echo "NETTEPI_RERUN done: ok=$nt skip=$nsk"
