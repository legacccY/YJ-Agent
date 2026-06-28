#!/bin/bash
PD=/root/quantimmu/tools_repos/PRIME
MIX=/root/quantimmu/tools_repos/MixMHCpred
echo "=== 权限 (能否读 /root) ==="
sudo -n true 2>/dev/null && echo "有免密 sudo" || echo "无免密 sudo"
ls -ld $PD $MIX 2>&1 | head
echo "=== MixMHCpred alleles 列表文件 ==="
LIB=$(find $MIX -iname 'allele*' -o -iname '*list*' 2>/dev/null | head -5)
echo "$LIB"
echo "=== 订正 7 等位在 MixMHCpred 支持表? ==="
ALLELE_FILE=$(find $MIX/lib -iname '*allele*' 2>/dev/null | head -1)
echo "查 $ALLELE_FILE"
for a in A0201 A6601 B4001 B5701 C0602 B3503 B3801; do
  h=$(grep -iw "$a" $ALLELE_FILE 2>/dev/null | head -1)
  echo "  $a : ${h:-NOT_FOUND}"
done
echo "=== PRIME 自带 allele 列表 (PRIME 用自己的 allele 表) ==="
PRIMEALL=$(find $PD -iname '*allele*' 2>/dev/null | head -3)
echo "$PRIMEALL"
for f in $PRIMEALL; do echo "# $f"; grep -iwE 'A0201|A6601|B4001|B5701|C0602|B3503|B3801' "$f" 2>/dev/null | head; done
