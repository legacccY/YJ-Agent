#!/bin/bash
# run_nettepi.sh — NetTepi 1.0 SLURM 批跑脚本
# 服务：quantimmu-bench §Tier-2, lever=NetTepi baseline
#
# ================================================================
# ⚠️  BLOCKED 风险（必读，跑前先核）
# ================================================================
# NetTepi 1.0 内部依赖 netMHCstabpan（稳定性预测子组件）。
# netMHCstabpan 需要 GLIBC_2.29，但 HPC el8 节点仅 GLIBC_2.28。
# → NetTepi 可能因 stabpan glibc 版本不足而无法在当前 HPC 环境运行。
# 先用最小测试用例 `netTepi -p test.pep -a HLA-A02:01` 确认是否报
#   "version `GLIBC_2.29' not found" → 若报则此路 BLOCKED，需替代方案。
# ================================================================
# ⚠️  pending_DTU_consent=True
#   NetTepi binary 须向 DTU 申请学术授权（health-software@dtu.dk）。
#   在获得授权并下载 binary 前，不得运行本脚本。
# ================================================================
# TODO: 下载 NetTepi binary 后确认实际 CLI 参数名及 allele 格式
#       当前占位: netTepi -p <pep_file> -a <HLA-Axx:xx> [-l <len>]
# ================================================================
#
# 用法（手动）：
#   sbatch run_nettepi.sh <ALLELE_TAG> <PEP_FILE>
#   例: sbatch run_nettepi.sh A0201 /path/to/A0201.pep
#
# 批量调用（脚本循环）：
#   for pep in $INPUTS/*.pep; do
#       tag=$(basename $pep .pep)
#       sbatch run_nettepi.sh $tag $pep
#   done

#SBATCH --job-name=nettepi
#SBATCH --account=shuihuawang
#SBATCH --partition=cpudebug
#SBATCH --qos=cpudebug
#SBATCH --cpus-per-task=4
#SBATCH --mem=16G
#SBATCH --time=02:00:00
#SBATCH --output=/gpfs/work/bio/jiayu2403/quantimmu/nettepi_run/nettepi_%j.out
#SBATCH --error=/gpfs/work/bio/jiayu2403/quantimmu/nettepi_run/nettepi_%j.err

set -euo pipefail

# ---- 参数 ----
ALLELE_TAG="${1:-A0201}"       # e.g. A0201（文件名 tag，无 HLA- 前缀无冒号）
PEP_FILE="${2:-}"              # 对应 .pep 文件路径

if [[ -z "$PEP_FILE" ]]; then
    echo "ERROR: PEP_FILE 未指定"
    echo "用法: sbatch run_nettepi.sh <ALLELE_TAG> <PEP_FILE>"
    exit 1
fi

# ---- 路径 ----
WORKDIR="/gpfs/work/bio/jiayu2403/quantimmu"
NETTEPI_BIN="${WORKDIR}/tools/nettepi/netTepi"  # TODO: 下载后核实 binary 路径
OUTDIR="${WORKDIR}/nettepi_run/out"
mkdir -p "${OUTDIR}"

# HLA allele 格式：ALLELE_TAG=A0201 → HLA-A02:01
# TODO: 跑通后核实 NetTepi 实际接受的格式（去星/保冒号/HLA- 前缀）
HLA_FMT="HLA-${ALLELE_TAG:0:1}${ALLELE_TAG:1:2}:${ALLELE_TAG:3:2}"
# 例: A0201 → HLA-A02:01  （TODO 核实）

echo "NetTepi start $(date) node=${SLURMD_NODENAME:-local}"
echo "  allele_tag=${ALLELE_TAG}  hla_fmt=${HLA_FMT}  pep=${PEP_FILE}"

# ---- glibc 预检 ----
echo "[glibc check] ldd --version:"
ldd --version | head -1
echo "[glibc check] netMHCstabpan ldd test (BLOCKED if GLIBC_2.29 missing):"
# TODO: 替换为真实 stabpan binary 路径后取消注释
# ldd "${WORKDIR}/tools/netMHCstabpan-1.0/netMHCstabpan" 2>&1 | grep "GLIBC" || true

# ---- 运行 NetTepi ----
# TODO: 下载 binary 后核实实际 CLI 选项
#       当前为占位命令，跑前必须替换
"${NETTEPI_BIN}" \
    -p "${PEP_FILE}" \
    -a "${HLA_FMT}" \
    > "${OUTDIR}/${ALLELE_TAG}_nettepi_raw.txt" 2>&1
# TODO: 确认 -l（肽长）参数是否必须显式传；NetTepi 是否自动识别长度

echo "NetTepi exit=$? end $(date)"
echo "Output: ${OUTDIR}/${ALLELE_TAG}_nettepi_raw.txt"
