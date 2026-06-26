#!/bin/bash
# =============================================================================
# run_tscape.sh  —  QuantImmuBench §Tier-3  T-SCAPE GPU 节点推理脚本
# 服务项目：quantimmu-bench §工具扩张v2 lever=部署T-SCAPE
#
# 用法（通常由 submit_tscape.sbatch 调用，也可手动在 GPU 节点直跑）：
#   bash run_tscape.sh <input_csv> <output_csv>
#
# 参数：
#   $1  input_csv    — prep_tscape_input.py 产生的 tscape_input.csv
#                      （列：Allele,Peptide；HLA 格式 HLA-A*02:01）
#   $2  output_csv   — T-SCAPE 推理输出路径（T-SCAPE 保留原列 + 加 score 列）
#
# 推理两步（T-SCAPE 官方流程）：
#   Step A: mhc_pseudo_matching.py  I  <input>  <input_modified>
#           过滤到 MHC_classI_pseudo.csv 支持的 allele
#   Step B: inference_csv.py --csv_path <input_modified> --inf_type pmhc_im_neo
#                            --output <output>
#           pmhc_im_neo = cancer neoantigen 任务（必须此值，其他 inf_type 分数异常）
#
# 输出说明：
#   output_csv 保留输入列（Allele,Peptide） + 追加 score 列（0-1，>0.5=免疫原，越高越强）
#   方向无需翻转（T-SCAPE score 越高越强，与 benchmark 方向一致）
# =============================================================================

set -euo pipefail

# ---------------------------------------------------------------------------
# 参数检查
# ---------------------------------------------------------------------------
if [ $# -lt 2 ]; then
    echo "Usage: bash run_tscape.sh <input_csv> <output_csv>" >&2
    echo "  input_csv  : tscape_input.csv（列 Allele,Peptide）" >&2
    echo "  output_csv : 推理输出路径" >&2
    exit 1
fi

INPUT_CSV="$1"
OUTPUT_CSV="$2"

if [ ! -f "${INPUT_CSV}" ]; then
    echo "[ERROR] input_csv 不存在: ${INPUT_CSV}" >&2
    exit 1
fi

# ---------------------------------------------------------------------------
# 配置（路径与 setup_tscape_hpc.sh 保持一致）
# ---------------------------------------------------------------------------
HPC_WORK=/gpfs/work/bio/jiayu2403/quantimmu
TSCAPE_DIR=${HPC_WORK}/t_scape
CONDA_BASE=/gpfs/work/bio/jiayu2403/.conda   # TODO: 核实路径
PYTHON_BIN=${CONDA_BASE}/envs/tscape/bin/python

# 中间文件：mhc_pseudo_matching 过滤后的输入
INPUT_MODIFIED="${INPUT_CSV%.csv}_modified.csv"

# ---------------------------------------------------------------------------
# 环境检查
# ---------------------------------------------------------------------------
echo "=== [T-SCAPE run] 环境检查 ==="
echo "[INFO] python  : ${PYTHON_BIN}"
echo "[INFO] tscape  : ${TSCAPE_DIR}"
echo "[INFO] input   : ${INPUT_CSV}"
echo "[INFO] output  : ${OUTPUT_CSV}"

if [ ! -f "${PYTHON_BIN}" ]; then
    echo "[ERROR] python binary 不存在: ${PYTHON_BIN}" >&2
    echo "  请先跑 setup_tscape_hpc.sh 创建 tscape conda env" >&2
    exit 1
fi

if [ ! -d "${TSCAPE_DIR}" ]; then
    echo "[ERROR] T-SCAPE repo 不存在: ${TSCAPE_DIR}" >&2
    echo "  请先跑 setup_tscape_hpc.sh" >&2
    exit 1
fi

# 检查 pmhc_im_neo 权重
WEIGHT_DIR="${TSCAPE_DIR}/best_param/pmhc_im_neo"
if [ ! -d "${WEIGHT_DIR}" ]; then
    echo "[ERROR] 权重目录不存在: ${WEIGHT_DIR}" >&2
    echo "  请先完成 setup_tscape_hpc.sh Step 4（下载 HF 权重）" >&2
    exit 1
fi

# 检查 dropout patch（验证 model_fused.py:326 是否已 patch）
MODEL_FILE="${TSCAPE_DIR}/src/model_fused.py"
if ! grep -q 'training=self\.training' "${MODEL_FILE}"; then
    echo "[ERROR] dropout patch 未施打！${MODEL_FILE}:326 需含 training=self.training" >&2
    echo "  请先跑 setup_tscape_hpc.sh（Step 2 自动 patch）" >&2
    exit 1
fi
echo "[OK] dropout patch 已验证（model_fused.py 含 training=self.training）"

echo ""
echo "=== [T-SCAPE run] GPU 信息 ==="
nvidia-smi --query-gpu=name,memory.total,memory.free --format=csv,noheader 2>/dev/null || echo "[WARN] nvidia-smi 不可用"

# ---------------------------------------------------------------------------
# Step A: mhc_pseudo_matching.py — 过滤到支持的 allele
# ---------------------------------------------------------------------------
echo ""
echo "=== [T-SCAPE run] Step A: mhc_pseudo_matching.py ==="
echo "[INFO] 过滤 allele（仅保留 MHC_classI_pseudo.csv 中的 allele）..."
echo "[INFO] 输入   : ${INPUT_CSV}"
echo "[INFO] 中间输出: ${INPUT_MODIFIED}"

cd "${TSCAPE_DIR}"
${PYTHON_BIN} mhc_pseudo_matching.py I "${INPUT_CSV}" "${INPUT_MODIFIED}"

if [ ! -f "${INPUT_MODIFIED}" ]; then
    echo "[ERROR] mhc_pseudo_matching.py 未产生输出: ${INPUT_MODIFIED}" >&2
    exit 1
fi

N_INPUT=$(wc -l < "${INPUT_CSV}")
N_MODIFIED=$(wc -l < "${INPUT_MODIFIED}")
echo "[OK] Step A 完成"
echo "     输入行数（含表头）: ${N_INPUT}"
echo "     过滤后行数（含表头）: ${N_MODIFIED}"
echo "     注：不在 pseudo csv 中的 allele 会被过滤掉（在 merge_tscape.py 中对应行填 NaN）"

# ---------------------------------------------------------------------------
# Step B: inference_csv.py — 推理
# ---------------------------------------------------------------------------
echo ""
echo "=== [T-SCAPE run] Step B: inference_csv.py (inf_type=pmhc_im_neo) ==="
echo "[INFO] 输入   : ${INPUT_MODIFIED}"
echo "[INFO] 输出   : ${OUTPUT_CSV}"
echo ""
echo "⚠️  inf_type 必须为 pmhc_im_neo（cancer neoantigen）"
echo "   其他 inf_type（如 pmhc_im_vir）会产生分数但含义不同，见 Issue#1"

mkdir -p "$(dirname "${OUTPUT_CSV}")"

${PYTHON_BIN} inference_csv.py \
    --csv_path "${INPUT_MODIFIED}" \
    --inf_type pmhc_im_neo \
    --output "${OUTPUT_CSV}"

if [ ! -f "${OUTPUT_CSV}" ]; then
    echo "[ERROR] inference_csv.py 未产生输出: ${OUTPUT_CSV}" >&2
    exit 1
fi

N_OUTPUT=$(wc -l < "${OUTPUT_CSV}")
echo ""
echo "[OK] Step B 完成"
echo "     输出行数（含表头）: ${N_OUTPUT}"
echo "     输出文件: ${OUTPUT_CSV}"

# ---------------------------------------------------------------------------
# 完成
# ---------------------------------------------------------------------------
echo ""
echo "=== [T-SCAPE run] 推理完成 ==="
echo "  输入   : ${INPUT_CSV}"
echo "  中间   : ${INPUT_MODIFIED}"
echo "  输出   : ${OUTPUT_CSV}"
echo "  完成时间: $(date)"
echo ""
echo "下一步："
echo "  python merge_tscape.py --tscape-out ${OUTPUT_CSV} \\"
echo "      --map scripts/out/newtools/tscape_input_map.csv \\"
echo "      --out-csv scripts/out/newtools/tscape_scores.csv"
