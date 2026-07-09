#!/bin/bash
# slice_hpc_dtu 8-11mer 全量重跑：netMHCpan_BA(→BA+EL) + netMHCstabpan(按长度拆) + NetTepi(6等位)
#   + ICERFIRE(混长). 服务 quantimmu-rerun8to11 slice_hpc_dtu. 复现零偏离(9mer版设置)。
# 混长实测结论(_scratch_hpc_smoke*):
#   netMHCpan-4.1 -p 不传-l → 8/9/10/11 全处理(smoke证);
#   netMHCstabpan -p 只吃等长 → 必须按长度拆, 每(等位×L)单跑 -l L(smoke证混长报错"lenght must be equal");
#   NetTepi -l 8,9,10,11 → 内部自拆, 全4长度出(smoke证);
#   ICERFIRE 混长 → exit0 正常跑(smoke证)。
set -u
ROOT=/gpfs/work/bio/jiayu2403/quantimmu
RERUN=$ROOT/rerun8to11
IN=$RERUN/dtu_netmhcpan_inputs
ALLELE_MAP=$IN/allele_map.tsv
NETMHCPAN=$ROOT/ext_tools/netMHCpan-4.1/netMHCpan
STABPAN=$ROOT/ext_tools/netMHCstabpan-1.0/netMHCstabpan
module load miniconda3/22.11.1-gcc-8.5.0-l4fo6ta 2>/dev/null
source "$(conda info --base)/etc/profile.d/conda.sh" 2>/dev/null
mkdir -p $RERUN/logs $RERUN/ba_out $RERUN/stab_out $RERUN/nettepi_out
export TMPDIR=$ROOT/tmp_8to11; mkdir -p $TMPDIR

echo "===== [1/4] netMHCpan-4.1 -BA -xls (→BA+EL, 不传-l, 混长自处理) 26等位 ====="
: > $RERUN/logs/ba.err
nba=0
while IFS=$'\t' read -r safe nmhc; do
  [ -z "$safe" ] && continue
  pep=$IN/$safe.pep
  [ -s "$pep" ] || { echo "BA SKIP $safe no pep" >> $RERUN/logs/ba.err; continue; }
  if $NETMHCPAN -p "$pep" -BA -a "$nmhc" -xls -xlsfile "$RERUN/ba_out/${safe}_ba.xls" >/dev/null 2>>$RERUN/logs/ba.err; then
    nba=$((nba+1))
  else
    echo "BA FAIL $safe $nmhc" >> $RERUN/logs/ba.err
  fi
done < $ALLELE_MAP
echo "BA done: $nba xls"

echo "===== [2/4] netMHCstabpan-1.0 (按长度8/9/10/11拆, 每等位×L单跑 -l L) ====="
export NMHOME=$ROOT/ext_tools/netMHCstabpan-1.0
: > $RERUN/logs/stab.err
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
echo "STAB done: $nstab xls (26等位×最多4长度)"

echo "===== [3/4] NetTepi (13等位模型, 命中我们6等位, -l 8,9,10,11) ====="
conda activate $ROOT/envs/qib_py27
PY27=$(which python2.7)
export PATH="$ROOT/envs/qib_perl/bin:$PATH"
export PERL5LIB="$ROOT/envs/qib_perl/lib/perl5/core_perl:${PERL5LIB:-}"
export NTHOME=$ROOT/ext_tools/netTepi-1.0
export NETMHCCONS_ENV=$ROOT/ext_tools/netMHCcons-1.1/netMHCcons
export NETMHCSTAB_ENV=$ROOT/ext_tools/netMHCstabpan-1.0/netMHCstabpan
export PYTHON_ENV="$PY27"
export TMPDIR=$ROOT/nettepi_tmp_8to11; mkdir -p $TMPDIR
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
  if $PY27 $NETTEPI -a "$nmhc" -p "$pep" -l 8,9,10,11 > $RERUN/nettepi_out/${safe}_nettepi.txt 2>$RERUN/nettepi_out/${safe}_nettepi.err; then
    nt=$((nt+1))
  else
    echo "NT FAIL $safe $nmhc" >> $RERUN/logs/nettepi.err
  fi
done < $ALLELE_MAP
echo "NETTEPI done: ok=$nt skip=$nsk"
conda deactivate 2>/dev/null

echo "===== [4/4] ICERFIRE (-a false -u false, 混长) ====="
conda activate $ROOT/envs/qib_icerfire
export TMPDIR=$ROOT/tmp_8to11
cd $ROOT/ext_tools/ICERFIRE/bashscripts
./ICERFIRE.sh -f $RERUN/icerfire_inputs/icerfire_input.csv -a false -u false > $RERUN/logs/icerfire.log 2>&1
echo "ICERFIRE exit=$?"
# ICERFIRE 写到 ext_tools/ICERFIRE/output/ICERFIRE_predictions.csv (9mer实证); 也扫 bashscripts/inputs
find $ROOT/ext_tools/ICERFIRE/output $ROOT/ext_tools/ICERFIRE/bashscripts $RERUN/icerfire_inputs -name "ICERFIRE_predictions.csv" -o -name "icerfire_input_scored_output*" 2>/dev/null | while read f; do
  cp "$f" $RERUN/icerfire_inputs/ 2>/dev/null && echo "copied $f"
done
ls -lh $RERUN/icerfire_inputs/ICERFIRE_predictions.csv $RERUN/icerfire_inputs/*scored_output* 2>/dev/null || echo "ICERFIRE output 未找到,核 logs/icerfire.log"
echo "ALL_DONE_8TO11"
