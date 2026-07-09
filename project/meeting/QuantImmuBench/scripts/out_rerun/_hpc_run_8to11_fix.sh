#!/bin/bash
# slice_hpc_dtu 8-11mer FIX 重跑：stab(拆长,干净pep) + NetTepi(干净allele_map) + ICERFIRE(干净csv)。
# BA/EL 已在首轮跑好(netMHCpan自动strip \r,ba xls长度正确)→ 本脚本不重跑 BA。
# 首轮 CRLF 污染(pep/allele_map/icerfire_input 带\r)已由主线 dos2unix 修复。
set -u
ROOT=/gpfs/work/bio/jiayu2403/quantimmu
RERUN=$ROOT/rerun8to11
IN=$RERUN/dtu_netmhcpan_inputs
ALLELE_MAP=$IN/allele_map.tsv
STABPAN=$ROOT/ext_tools/netMHCstabpan-1.0/netMHCstabpan
module load miniconda3/22.11.1-gcc-8.5.0-l4fo6ta 2>/dev/null
source "$(conda info --base)/etc/profile.d/conda.sh" 2>/dev/null
mkdir -p $RERUN/logs $RERUN/stab_out $RERUN/nettepi_out
export TMPDIR=$ROOT/tmp_8to11fix; mkdir -p $TMPDIR

echo "===== [1/3] netMHCstabpan (按长度8/9/10/11拆, 干净pep) ====="
export NMHOME=$ROOT/ext_tools/netMHCstabpan-1.0
: > $RERUN/logs/stab.err
# 先清首轮污染的 stab 产物(非_L的9mer stale + 错位的_L)
rm -f $RERUN/stab_out/*_stab.xls
nstab=0
while IFS=$'\t' read -r safe nmhc; do
  [ -z "$safe" ] && continue
  pep=$IN/$safe.pep
  [ -s "$pep" ] || continue
  for L in 8 9 10 11; do
    lpep=$TMPDIR/${safe}_L${L}.pep
    awk -v L=$L 'length($1)==L' "$pep" > "$lpep"
    [ -s "$lpep" ] || continue
    if $STABPAN -p "$lpep" -a "$nmhc" -l $L -xls -xlsfile "$RERUN/stab_out/${safe}_L${L}_stab.xls" >/dev/null 2>>$RERUN/logs/stab.err; then
      nstab=$((nstab+1))
    else
      echo "STAB FAIL $safe $nmhc L$L" >> $RERUN/logs/stab.err
    fi
  done
done < $ALLELE_MAP
echo "STAB done: $nstab xls (期望 26×4=104)"

echo "===== [2/3] NetTepi (13等位模型, 命中6等位, -l 8,9,10,11, 干净allele_map) ====="
conda activate $ROOT/envs/qib_py27
PY27=$(which python2.7)
export PATH="$ROOT/envs/qib_perl/bin:$PATH"
export PERL5LIB="$ROOT/envs/qib_perl/lib/perl5/core_perl:${PERL5LIB:-}"
export NTHOME=$ROOT/ext_tools/netTepi-1.0
export NETMHCCONS_ENV=$ROOT/ext_tools/netMHCcons-1.1/netMHCcons
export NETMHCSTAB_ENV=$ROOT/ext_tools/netMHCstabpan-1.0/netMHCstabpan
export PYTHON_ENV="$PY27"
export TMPDIR=$ROOT/nettepi_tmp_8to11fix; mkdir -p $TMPDIR
NETTEPI=$ROOT/ext_tools/netTepi-1.0/netTepi.py
ALLELES_LST=$ROOT/ext_tools/netTepi-1.0/alleles.lst
supported=$(tr -d ' \r' < $ALLELES_LST)
: > $RERUN/logs/nettepi.err
rm -f $RERUN/nettepi_out/*_nettepi.txt
nt=0; nsk=0
while IFS=$'\t' read -r safe nmhc; do
  [ -z "$safe" ] && continue
  nmhc=$(echo "$nmhc" | tr -d ' \r')
  if ! echo "$supported" | grep -qx "$nmhc"; then nsk=$((nsk+1)); continue; fi
  pep=$IN/$safe.pep
  [ -s "$pep" ] || continue
  if $PY27 $NETTEPI -a "$nmhc" -p "$pep" -l 8,9,10,11 > $RERUN/nettepi_out/${safe}_nettepi.txt 2>$RERUN/nettepi_out/${safe}_nettepi.err; then
    nt=$((nt+1))
  else
    echo "NT FAIL $safe $nmhc" >> $RERUN/logs/nettepi.err
  fi
done < $ALLELE_MAP
echo "NETTEPI done: ok=$nt skip=$nsk (期望 ok=6 skip=20)"
conda deactivate 2>/dev/null

echo "===== [3/3] ICERFIRE (-a false -u false, 干净csv) ====="
conda activate $ROOT/envs/qib_icerfire
export TMPDIR=$ROOT/tmp_8to11fix
cd $ROOT/ext_tools/ICERFIRE/bashscripts
./ICERFIRE.sh -f $RERUN/icerfire_inputs/icerfire_input.csv -a false -u false > $RERUN/logs/icerfire.log 2>&1
echo "ICERFIRE exit=$?"
find $ROOT/ext_tools/ICERFIRE/output $ROOT/ext_tools/ICERFIRE/bashscripts $RERUN/icerfire_inputs -name "ICERFIRE_predictions.csv" -newermt "-30 min" 2>/dev/null | while read f; do
  cp "$f" $RERUN/icerfire_inputs/ICERFIRE_predictions.csv 2>/dev/null && echo "copied $f"
done
echo "icerfire pred rows: $(wc -l < $RERUN/icerfire_inputs/ICERFIRE_predictions.csv 2>/dev/null)"
echo "ALL_DONE_8TO11_FIX"
