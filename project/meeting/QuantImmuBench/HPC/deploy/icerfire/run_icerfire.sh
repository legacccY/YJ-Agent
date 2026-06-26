#!/bin/bash
#SBATCH --job-name=icerfire_bench
#SBATCH --account=shuihuawang
#SBATCH --partition=cpudebug
#SBATCH --qos=cpudebug
#SBATCH --cpus-per-task=4
#SBATCH --mem=16G
#SBATCH --time=01:00:00
#SBATCH --output=/gpfs/work/bio/jiayu2403/quantimmu/icerfire_run/icerfire_%j.out
#SBATCH --error=/gpfs/work/bio/jiayu2403/quantimmu/icerfire_run/icerfire_%j.err

# QuantImmuBench §Tier-2  ICERFIRE 1.0 HPC SLURM 作业脚本
# 服务项目：quantimmu-bench §Tier-2 lever=部署ICERFIRE apples-to-apples
#
# ============================================================
# 部署前必做：在 HPC 上 sed 修改 ICERFIRE.sh 顶部 3 个 config 变量
# ============================================================
# ICERFIRE.sh（位于 ${USERDIR}/bashscripts/ICERFIRE.sh）顶部有 3 个变量需替换：
#
#   USERDIR=/gpfs/work/bio/jiayu2403/quantimmu/ext_tools/ICERFIRE
#   PEPXDIR=${USERDIR}/pepx/
#   NETMHCPAN=/gpfs/work/bio/jiayu2403/quantimmu/ext_tools/netMHCpan-4.1/netMHCpan
#
# 一次性替换命令（部署时在 HPC login 节点运行，不重复执行）：
#   ICERFIRE_SH=/gpfs/work/bio/jiayu2403/quantimmu/ext_tools/ICERFIRE/bashscripts/ICERFIRE.sh
#   sed -i "s|^USERDIR=.*|USERDIR=/gpfs/work/bio/jiayu2403/quantimmu/ext_tools/ICERFIRE|" "${ICERFIRE_SH}"
#   sed -i "s|^NETMHCPAN=.*|NETMHCPAN=/gpfs/work/bio/jiayu2403/quantimmu/ext_tools/netMHCpan-4.1/netMHCpan|" "${ICERFIRE_SH}"
#   sed -i 's|^PEPXDIR=.*|PEPXDIR="${USERDIR}/pepx/"|' "${ICERFIRE_SH}"
#
# ============================================================
# cpudebug QOS 限制：cpu=4 / mem=16G / walltime=1h
# 若 34k 肽对单 job 1h 内跑不完，分块方案：
#   split -l 5000 icerfire_input.csv icerfire_chunk_
#   for chunk in icerfire_chunk_*; do
#       sbatch run_icerfire.sh "${WORK_DIR}/${chunk}"
#   done
#   （脚本接受可选 $1 覆盖 INPUT_CSV；见下方 INPUT_CSV 定义处）
# ============================================================
#
# pending_DTU_consent=True：binary 待向 health-software@dtu.dk 申请，到位前不可真跑

# ============================================================
# 路径配置
# ============================================================
USERDIR=/gpfs/work/bio/jiayu2403/quantimmu/ext_tools/ICERFIRE
WORK_DIR=/gpfs/work/bio/jiayu2403/quantimmu/icerfire_run
# 支持 $1 覆盖（分块时传入 chunk 文件路径）
INPUT_CSV=${1:-${WORK_DIR}/icerfire_input.csv}
# 输出文件名：ICERFIRE.sh 在 INPUT_CSV basename 后加 _scored_output
# 实际文件名：icerfire_input_scored_output（或含扩展名）
# TODO: 跑后 ls 核实确切文件名，更新 parse_icerfire.py --icerfire-out 参数
INPUT_BASE=$(basename "${INPUT_CSV}" .csv)
EXPECTED_OUTPUT="${WORK_DIR}/${INPUT_BASE}_scored_output"

mkdir -p "${WORK_DIR}"

echo "ICERFIRE start $(date) node=${SLURMD_NODENAME}"
echo "INPUT_CSV=${INPUT_CSV}"
echo "USERDIR=${USERDIR}"

# ============================================================
# conda 环境（py3.9 + sklearn==1.0.2 / numpy==1.21.5 / pandas==1.4.2）
# ============================================================
# TODO: 核实 HPC conda env 名称，取消下面两行注释并替换 <env_name>
# module load anaconda3
# source activate <env_name>

# ============================================================
# 运行 ICERFIRE
# CLI: ./ICERFIRE.sh -f <input_file> -a <add_expr> -u <user_exp>
# 无表达数据（DS1/DS2 均无 TPM）→ -a false -u false
# 此时 ICERFIRE 使用 ICERFIRE_ExprFalse.pkl 模型
# ============================================================
cd "${USERDIR}/bashscripts" && \
    ./ICERFIRE.sh \
        -f "${INPUT_CSV}" \
        -a false \
        -u false

EXIT_CODE=$?
echo "ICERFIRE exit=${EXIT_CODE} end $(date)"

if [ ${EXIT_CODE} -ne 0 ]; then
    echo "ICERFIRE 非零退出 → 检查 .err 日志" >&2
    exit ${EXIT_CODE}
fi

# ============================================================
# 定位输出文件（落在 bashscripts/ 还是 WORK_DIR 跑后核实）
# ============================================================
echo "查找输出文件（*_scored_output*）："
find "${USERDIR}/bashscripts" "${WORK_DIR}" -name "*_scored_output*" 2>/dev/null

# 若输出落在 bashscripts/ 则移到 WORK_DIR
SCORED_IN_BASHSCRIPTS="${USERDIR}/bashscripts/${INPUT_BASE}_scored_output"
if [ -f "${SCORED_IN_BASHSCRIPTS}" ]; then
    mv "${SCORED_IN_BASHSCRIPTS}" "${WORK_DIR}/"
    echo "输出已移至 ${WORK_DIR}/${INPUT_BASE}_scored_output"
fi

ls -lh "${WORK_DIR}/"*_scored_output* 2>/dev/null || \
    echo "⚠️ 未找到 *_scored_output* 文件，核实输出位置 TODO"
