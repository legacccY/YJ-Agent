#!/bin/bash
# HPC slice_dtu: stabpan + NetTepi + ICERFIRE on rerun inputs (全 9mer). 服务 quantimmu-rerun slice_dtu.
set -u
ROOT=/gpfs/work/bio/jiayu2403/quantimmu
RERUN=$ROOT/rerun
IN=$RERUN/dtu_netmhcpan_inputs
ALLELE_MAP=$IN/allele_map.tsv
module load miniconda3/22.11.1-gcc-8.5.0-l4fo6ta 2>/dev/null
source "$(conda info --base)/etc/profile.d/conda.sh" 2>/dev/null
mkdir -p $RERUN/logs $RERUN/stab_out $RERUN/nettepi_out

echo "===== [1/3] netMHCstabpan (26 allele, 9mer, -xls) ====="
STABPAN=$ROOT/ext_tools/netMHCstabpan-1.0/netMHCstabpan
export NMHOME=$ROOT/ext_tools/netMHCstabpan-1.0
export TMPDIR=$ROOT/tmp_stabpan_rerun; mkdir -p $TMPDIR
: > $RERUN/logs/stab.err
ns=0
while IFS=$'\t' read -r safe nmhc; do
  [ -z "$safe" ] && continue
  pep=$IN/$safe.pep
  [ -s "$pep" ] || continue
  if $STABPAN -a "$nmhc" -l 9 -p "$pep" -xls -xlsfile "$RERUN/stab_out/${safe}_stab.xls" >/dev/null 2>>$RERUN/logs/stab.err; then
    ns=$((ns+1))
  else
    echo "STAB FAIL $safe $nmhc" >> $RERUN/logs/stab.err
  fi
done < $ALLELE_MAP
echo "STAB done: $ns xls"

echo "===== [2/3] NetTepi (13-allele subset, -l 9) ====="
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
nt=0; nsk=0
while IFS=$'\t' read -r safe nmhc; do
  [ -z "$safe" ] && continue
  if ! echo "$supported" | grep -qx "$nmhc"; then nsk=$((nsk+1)); continue; fi
  pep=$IN/$safe.pep
  [ -s "$pep" ] || continue
  if $PY27 $NETTEPI -a "$nmhc" -p "$pep" -l 9 > $RERUN/nettepi_out/${safe}_nettepi.txt 2>$RERUN/nettepi_out/${safe}_nettepi.err; then
    nt=$((nt+1))
  else
    echo "NT FAIL $safe $nmhc" >> $RERUN/logs/nettepi.err
  fi
done < $ALLELE_MAP
echo "NETTEPI done: ok=$nt skip=$nsk"
conda deactivate 2>/dev/null

echo "===== [3/3] ICERFIRE (-a false -u false) ====="
conda activate $ROOT/envs/qib_icerfire
cd $ROOT/ext_tools/ICERFIRE/bashscripts
./ICERFIRE.sh -f $RERUN/icerfire_inputs/icerfire_input.csv -a false -u false > $RERUN/logs/icerfire.log 2>&1
echo "ICERFIRE exit=$?"
base=icerfire_input
find $ROOT/ext_tools/ICERFIRE/bashscripts $RERUN/icerfire_inputs -name "${base}_scored_output*" 2>/dev/null | while read f; do
  cp "$f" $RERUN/icerfire_inputs/ 2>/dev/null
done
ls -lh $RERUN/icerfire_inputs/${base}_scored_output* 2>/dev/null || echo "ICERFIRE output 未找到,核 logs/icerfire.log"
echo "ALL_DONE"
