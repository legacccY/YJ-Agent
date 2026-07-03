#!/bin/bash
#SBATCH --job-name=stabpan_full130
#SBATCH --account=shuihuawang
#SBATCH --partition=cpudebug
#SBATCH --qos=cpudebug
#SBATCH --cpus-per-task=4
#SBATCH --mem=16G
#SBATCH --time=02:00:00
#SBATCH --output=/gpfs/work/bio/jiayu2403/quantimmu/logs/stabpan_full130_%j.out
#SBATCH --error=/gpfs/work/bio/jiayu2403/quantimmu/logs/stabpan_full130_%j.err

# ============================================================================
# run_netmhcstabpan_FULL130.sh
# Service: quantimmu-bench §tools_present  lever=netMHCstabpan coverage fix
#          (43/130 -> FULL130, all 35 MHC-I alleles x 3283 unique pep,HLA pairs)
#
# 直跑二进制版（NOT the apptainer/net.sif route）。主线 W1 实测：登录/计算节点
# glibc-2.28 够跑 ext_tools/netMHCstabpan-1.0/netMHCstabpan（`-h` 正常输出），
# 无需 net.sif、无需 tcsh wrapper 重写。避开容器复杂度直跑。
#
# 前置（主线做，不在本 kit）：
#   (a) prep_stabpan_FULL130.py 已本地跑，产出 inputs_FULL130/*.pep +
#       inputs_FULL130/alleles_FULL130.tsv，并上传到
#       ${ROOT}/HPC/deploy/netmhcstabpan/inputs_FULL130/
#   (b) netMHCstabpan-1.0 已装于 ${ROOT}/ext_tools/netMHCstabpan-1.0/
#       （其 tcsh wrapper 内部 NMHOME/backend 路径已配好——主线 -h 已验）
#
# 逐等位直跑：
#   netMHCstabpan -a <allele_nmhc> -p <allele_safe>.pep > <allele_safe>_stab.out
#   allele_nmhc = 去星 net 格式 HLA-A02:01；-p = 肽列表文件（每行一个肽）
# 输出 stdout 列（DTU 官方）：
#   pos  HLA  peptide  Identity  Pred  Thalf(h)  %Rank_Stab  BindLevel
#   Pred 越高 = 越稳定（= 本 benchmark 统一方向 higher=stronger）。
#
# 主线跑法：
#   sbatch ${ROOT}/HPC/deploy/netmhcstabpan/run_netmhcstabpan_FULL130.sh
# 产物：
#   ${OUT_DIR}/<allele_safe>_stab.out                （逐等位原始 stdout）
#   ${RAW_CSV} = scripts/out_official/coverage_fix/netmhcstabpan_raw_FULL130.csv
#                列: peptide,HLA_Allele,pred,thalf,rank_stab
#                （HLA_Allele=带星原始格式，与 mhcnuggets_raw_FULL130.csv 同约定）
# ============================================================================

ROOT=/gpfs/work/bio/jiayu2403/quantimmu

# netMHCstabpan 安装 + 环境变量（belt-and-suspenders：wrapper 通常自配，
# 这里再显式指一次以防 env 覆盖）
export NMHOME=${ROOT}/ext_tools/netMHCstabpan-1.0
export NETMHCstabpan=${ROOT}/ext_tools/netMHCstabpan-1.0
export TMPDIR=${ROOT}/tmp_stabpan
STABPAN=${NMHOME}/netMHCstabpan

INPUT_DIR=${ROOT}/HPC/deploy/netmhcstabpan/inputs_FULL130
ALLELE_LIST=${INPUT_DIR}/alleles_FULL130.tsv
OUT_DIR=${ROOT}/scripts/out_official/coverage_fix/stabpan_out
RAW_CSV=${ROOT}/scripts/out_official/coverage_fix/netmhcstabpan_raw_FULL130.csv

echo "=== netMHCstabpan-1.0 FULL130 (direct binary) start ==="
echo "date       : $(date)"
echo "node       : ${SLURMD_NODENAME}"
echo "STABPAN    : ${STABPAN}"
echo "INPUT_DIR  : ${INPUT_DIR}"
echo "OUT_DIR    : ${OUT_DIR}"
echo "RAW_CSV    : ${RAW_CSV}"

# Sanity checks --------------------------------------------------------------
if [ ! -x "$STABPAN" ] && [ ! -f "$STABPAN" ]; then
    echo "ERROR: netMHCstabpan binary not found: $STABPAN" >&2
    echo "       Install netMHCstabpan-1.0 under ${ROOT}/ext_tools/ first." >&2
    exit 1
fi
if [ ! -f "$ALLELE_LIST" ]; then
    echo "ERROR: allele list not found: $ALLELE_LIST" >&2
    echo "       Run prep_stabpan_FULL130.py locally and upload inputs_FULL130/." >&2
    exit 1
fi

mkdir -p "${ROOT}/logs" "${OUT_DIR}" "${TMPDIR}"

# 逐等位跑（不用 set -e：单等位失败不杀整批，只计数）--------------------------
fail_count=0
success_count=0

while IFS=$'\t' read -r allele_safe allele_nmhc allele_star; do
    [ -z "$allele_safe" ] && continue

    pep_file="${INPUT_DIR}/${allele_safe}.pep"
    out_file="${OUT_DIR}/${allele_safe}_stab.out"

    if [ ! -f "$pep_file" ]; then
        echo "WARN: .pep not found for $allele_safe ($pep_file), skip."
        continue
    fi

    n_peps=$(wc -l < "$pep_file")
    echo ""
    echo "--- allele: ${allele_nmhc} (star=${allele_star})  peptides: ${n_peps} ---"

    if "$STABPAN" -a "$allele_nmhc" -p "$pep_file" > "$out_file" 2> "${out_file}.err"; then
        echo "OK: $out_file"
        success_count=$((success_count + 1))
    else
        ec=$?
        echo "ERROR: netMHCstabpan exit=$ec for ${allele_nmhc} (see ${out_file}.err)" >&2
        fail_count=$((fail_count + 1))
    fi
done < "$ALLELE_LIST"

echo ""
echo "=== per-allele runs done  success=${success_count}  fail=${fail_count} ==="

# 拼 raw CSV（awk 抽 Pred/Thalf/%Rank_Stab）----------------------------------
# 数据行判据：第1列 pos 是整数 且 第3列 peptide 全字母。
# 列位：pos(1) HLA(2) peptide(3) Identity(4) Pred(5) Thalf(6) %Rank_Stab(7) [BindLevel(8)]
echo "peptide,HLA_Allele,pred,thalf,rank_stab" > "$RAW_CSV"
row_count=0
while IFS=$'\t' read -r allele_safe allele_nmhc allele_star; do
    [ -z "$allele_safe" ] && continue
    out_file="${OUT_DIR}/${allele_safe}_stab.out"
    [ -f "$out_file" ] || continue
    n=$(awk -v star="$allele_star" '
        $1 ~ /^[0-9]+$/ && $3 ~ /^[A-Za-z]+$/ {
            print $3 "," star "," $5 "," $6 "," $7
        }' "$out_file" | tee -a "$RAW_CSV" | wc -l)
    row_count=$((row_count + n))
done < "$ALLELE_LIST"

echo ""
echo "=== netMHCstabpan FULL130 done ==="
echo "raw CSV rows (excl header): ${row_count}  ->  ${RAW_CSV}"
echo "date: $(date)"

if [ $fail_count -gt 0 ]; then
    echo "WARN: ${fail_count} allele(s) failed (likely unsupported by netMHCpan-2.8 backend)." >&2
    echo "      Check *_stab.out.err; those pairs stay uncovered (expected for rare alleles)." >&2
fi
exit 0
