#!/bin/bash
#SBATCH --job-name=tscape_bench
#SBATCH --account=shuihuawang
#SBATCH --partition=gpu4090
#SBATCH --qos=4gpus
#SBATCH --gres=gpu:1
#SBATCH --cpus-per-task=4
#SBATCH --mem=32G
#SBATCH --time=04:00:00
#SBATCH --output=/gpfs/work/bio/jiayu2403/quantimmu/t_scape/logs/tscape_%j.out
#SBATCH --error=/gpfs/work/bio/jiayu2403/quantimmu/t_scape/logs/tscape_%j.err

# =============================================================================
# submit_tscape.sbatch  —  QuantImmuBench §Tier-3  T-SCAPE SLURM 提交脚本
# 服务项目：quantimmu-bench §工具扩张v2 lever=部署T-SCAPE
#
# 许可：CC BY-NC-ND 4.0，仅限学术非商用
# ⚠️  ND 条款：禁止对 T-SCAPE 输出做再发布/衍生；仅用于 QuantImmuBench 内部学术评测
#
# 提交：
#   sbatch submit_tscape.sbatch
#
# 资源申请（默认单卡）：
#   1 GPU（RTX 4090，24GB VRAM）—— 本窗口默认单卡，推理 34K 肽估计 <2h
#   4 CPU，32GB RAM
#   walltime 4h（留足余量；T-SCAPE 推理较快但 34K 行含 pseudo matching 步骤）
#   TODO: 核实实际耗时（首次跑后按实际缩短 walltime）
#
# 路径约定：
#   TSCAPE_DIR  = /gpfs/work/bio/jiayu2403/quantimmu/t_scape （clone + 权重）
#   INPUT_CSV   = T-SCAPE 推理用输入（prep_tscape_input.py 产生，需提前上传或 HPC 上跑 prep）
#   OUTPUT_CSV  = T-SCAPE 推理输出（保留 Allele,Peptide + 追加 score）
# =============================================================================

# ---------------------------------------------------------------------------
# 路径配置（按实际修改）
# ---------------------------------------------------------------------------
TSCAPE_DIR=/gpfs/work/bio/jiayu2403/quantimmu/t_scape
CONDA_BASE=/gpfs/work/bio/jiayu2403/.conda        # TODO: 核实 conda 路径
PYTHON_BIN=${CONDA_BASE}/envs/tscape/bin/python   # 绝对路径（source activate 在 sbatch 不可靠）

# 输入：prep_tscape_input.py 产生的 tscape_input.csv
INPUT_CSV=${TSCAPE_DIR}/inputs/tscape_input.csv

# 输出：T-SCAPE 推理结果
OUTPUT_CSV=${TSCAPE_DIR}/outputs/tscape_output.csv

# 脚本路径（run_tscape.sh 与本 sbatch 同目录，上传到 HPC 时一并放此处）
RUN_SCRIPT=${TSCAPE_DIR}/run_tscape.sh

LOG_DIR=${TSCAPE_DIR}/logs

# ---------------------------------------------------------------------------
# 前置检查
# ---------------------------------------------------------------------------
echo "=== [T-SCAPE sbatch] 开始 $(date) ==="
echo "Node: ${SLURMD_NODENAME}"
echo "JobID: ${SLURM_JOB_ID}"
echo ""

# 必须在 GPU 节点
if [ -z "${SLURMD_NODENAME}" ]; then
    echo "[WARN] SLURMD_NODENAME 未设置，可能在登录节点运行" >&2
fi

# 创建必要目录
mkdir -p "${LOG_DIR}"
mkdir -p "$(dirname "${OUTPUT_CSV}")"
mkdir -p "$(dirname "${INPUT_CSV}")"

# GPU 可见性
nvidia-smi --query-gpu=name,memory.total --format=csv,noheader 2>/dev/null \
    && echo "[OK] GPU 可见" \
    || echo "[WARN] nvidia-smi 不可用" >&2

# Python 可执行
if [ ! -f "${PYTHON_BIN}" ]; then
    echo "[ERROR] python binary 不存在: ${PYTHON_BIN}" >&2
    echo "  请先在 DTN 上跑 setup_tscape_hpc.sh 创建 conda env" >&2
    exit 1
fi
echo "[OK] python: $(${PYTHON_BIN} --version)"

# 输入文件
if [ ! -f "${INPUT_CSV}" ]; then
    echo "[ERROR] 输入文件不存在: ${INPUT_CSV}" >&2
    echo "  请先上传 prep_tscape_input.py 产生的 tscape_input.csv 到 ${INPUT_CSV}" >&2
    echo "  或在 HPC 登录节点跑：${PYTHON_BIN} prep_tscape_input.py --out-dir ${TSCAPE_DIR}/inputs/" >&2
    exit 1
fi

# run_tscape.sh
if [ ! -f "${RUN_SCRIPT}" ]; then
    echo "[ERROR] 推理脚本不存在: ${RUN_SCRIPT}" >&2
    echo "  请将 run_tscape.sh 上传到 ${TSCAPE_DIR}/" >&2
    exit 1
fi

# ---------------------------------------------------------------------------
# 执行推理
# ---------------------------------------------------------------------------
echo ""
echo "=== [T-SCAPE sbatch] 执行推理 ==="
echo "  input  : ${INPUT_CSV}"
echo "  output : ${OUTPUT_CSV}"
echo ""

bash "${RUN_SCRIPT}" "${INPUT_CSV}" "${OUTPUT_CSV}"
EXIT_CODE=$?

# ---------------------------------------------------------------------------
# 结果检查
# ---------------------------------------------------------------------------
echo ""
echo "=== [T-SCAPE sbatch] 完成检查 ==="
if [ ${EXIT_CODE} -ne 0 ]; then
    echo "[FAIL] run_tscape.sh 返回 exit code ${EXIT_CODE}" >&2
    exit ${EXIT_CODE}
fi

if [ ! -f "${OUTPUT_CSV}" ]; then
    echo "[FAIL] 输出文件未产生: ${OUTPUT_CSV}" >&2
    exit 1
fi

N_OUTPUT=$(wc -l < "${OUTPUT_CSV}")
echo "[OK] 输出文件: ${OUTPUT_CSV}（${N_OUTPUT} 行含表头）"
echo "[OK] T-SCAPE 推理成功完成"
echo "完成时间: $(date)"
echo ""
echo "下一步（本地）："
echo "  python merge_tscape.py \\"
echo "      --tscape-out <上传路径>/tscape_output.csv \\"
echo "      --map scripts/out/newtools/tscape_input_map.csv \\"
echo "      --out-csv scripts/out/newtools/tscape_scores.csv"
