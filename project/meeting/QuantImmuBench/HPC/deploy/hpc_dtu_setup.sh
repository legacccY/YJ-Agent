#!/bin/bash
set -e
ROOT=/gpfs/work/bio/jiayu2403/quantimmu
cd $ROOT/ext_tools
tar -xzf dtu_tools.tar.gz && echo EXTRACT_OK
HPCEXT=$ROOT/ext_tools
# 重配 NMHOME (WSL /root/... -> HPC /gpfs/...)
for d in netMHCpan-4.1 netMHCpan-2.8; do
  sed -i "s|/root/quantimmu/ext_tools/$d|$HPCEXT/$d|g" $d/netMHCpan
  mkdir -p $d/tmp
done
sed -i "s|/root/quantimmu/ext_tools/netMHCstabpan-1.0|$HPCEXT/netMHCstabpan-1.0|g; s|/root/quantimmu/ext_tools/netMHCpan-2.8|$HPCEXT/netMHCpan-2.8|g" netMHCstabpan-1.0/netMHCstabpan
mkdir -p netMHCstabpan-1.0/tmp
echo "=== test netMHCpan-4.1 (HPC 真Linux老二进制) ==="
cd netMHCpan-4.1/test && ../netMHCpan -p test.pep 2>/dev/null | grep -c PEPLIST | sed 's/^/PEPLIST_rows: /'
cd $HPCEXT
echo "=== test netMHCpan-2.8 ==="
cd netMHCpan-2.8/test && ../netMHCpan -p test.pep 2>/dev/null | grep -c PEPLIST | sed 's/^/PEP28_rows: /'
cd $HPCEXT
echo "=== test netMHCstabpan ==="
cd netMHCstabpan-1.0/test && ../netMHCstabpan -p test.pep 2>/dev/null | grep -c PEPLIST | sed 's/^/STAB_rows: /'
echo DTU_DONE
