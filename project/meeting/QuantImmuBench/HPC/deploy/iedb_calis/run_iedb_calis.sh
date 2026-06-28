#!/bin/bash
#SBATCH --job-name=iedb_calis
#SBATCH --account=shuihuawang
#SBATCH --partition=cpudebug
#SBATCH --qos=cpudebug
#SBATCH --cpus-per-task=4
#SBATCH --mem=8G
#SBATCH --time=01:00:00
#SBATCH --output=/gpfs/work/bio/jiayu2403/quantimmu/iedb_calis_run/logs/iedb_calis_%j.out
#SBATCH --error=/gpfs/work/bio/jiayu2403/quantimmu/iedb_calis_run/logs/iedb_calis_%j.err

# QuantImmuBench §Tier-0 first wave  IEDB Calis 2013 HPC 批量打分脚本
# 服务项目：quantimmu-bench benchmark 扩张 v2 第一波  lever=部署IEDB_Calis
#
# 工具：IEDB Class I Immunogenicity Predictor v3.0
#       Calis et al. 2013 PLoS Comput Biol 9(10):e1003253
# 许可：NPOSL-3.0（数字可自由发布，无 DTU pending）
# 官方下载：https://downloads.iedb.org/tools/immunogenicity/LATEST/IEDB_Immunogenicity-3.0.tar.gz
#
# CLI（官方 README 确认）：
#   python predict_immunogenicity.py [--allele=HLA-A0201] input.txt
#   输入：每行一肽的文本文件；HLA 格式：无 * 无 :（如 HLA-A0201）
#   输出：stdout  →  元数据行（allele:/masking:/masked variables:）+ CSV（peptide,length,score）
#         score 越高越免疫原，方向一致，无需翻转
#
# 依赖：Python 3.6+（纯标准库，无第三方依赖）
#
# 用法（HPC）：
#   sbatch run_iedb_calis.sh
#   （无参数；自动读 ${INPUTS_DIR}/allele_manifest.csv 循环所有 allele 组）
#
# 烟测（无 sbatch，本地 SSH 节点快跑验证）：
#   bash run_iedb_calis.sh --smoke
#   只跑 manifest 第一个 allele 的前 3 条肽，验证 stdout 格式是否正常

set -euo pipefail

# ---- 路径配置 ----
WORK_DIR=/gpfs/work/bio/jiayu2403/quantimmu/iedb_calis_run
INPUTS_DIR="${WORK_DIR}/inputs"       # prep_input.py 生成并上传的输入文件目录
TOOL_DIR="${WORK_DIR}/tool"            # IEDB 工具解压目录
SCORES_DIR="${WORK_DIR}/scores"        # 每个 allele 的打分输出
LOGS_DIR="${WORK_DIR}/logs"
MANIFEST="${INPUTS_DIR}/allele_manifest.csv"
PRED_SCRIPT="${TOOL_DIR}/predict_immunogenicity.py"
TOOL_TAR_URL="https://downloads.iedb.org/tools/immunogenicity/LATEST/IEDB_Immunogenicity-3.0.tar.gz"

# ---- smoke 模式 ----
SMOKE_MODE=0
if [[ "${1:-}" == "--smoke" ]]; then
    SMOKE_MODE=1
    echo "[smoke] 烟测模式：只跑 manifest 第一行，前 3 条肽"
fi

mkdir -p "${INPUTS_DIR}" "${TOOL_DIR}" "${SCORES_DIR}" "${LOGS_DIR}"

echo "IEDB Calis start $(date) node=${SLURMD_NODENAME:-local}"

# ============================================================
# Step 1: 下载并解压 predict_immunogenicity.py（已存在则跳过）
# ============================================================
if [[ ! -f "${PRED_SCRIPT}" ]]; then
    echo "[setup] Downloading IEDB_Immunogenicity-3.0.tar.gz ..."
    wget -q "${TOOL_TAR_URL}" -O "${TOOL_DIR}/IEDB_Immunogenicity-3.0.tar.gz"
    # --strip-components=1 去掉 immunogenicity/ 前缀
    tar -zxvf "${TOOL_DIR}/IEDB_Immunogenicity-3.0.tar.gz" \
        -C "${TOOL_DIR}" \
        --strip-components=1
    echo "[setup] predict_immunogenicity.py ready: ${PRED_SCRIPT}"
else
    echo "[setup] predict_immunogenicity.py already present, skip download"
fi

# Python 版本检查
echo "[setup] Python version: $(python --version 2>&1)"

# ============================================================
# Step 2: 检查 manifest
# ============================================================
if [[ ! -f "${MANIFEST}" ]]; then
    echo "ERROR: allele_manifest.csv not found: ${MANIFEST}" >&2
    echo "  先在本地跑 prep_input.py，再将 iedb_calis_inputs/ 上传至 ${INPUTS_DIR}" >&2
    exit 1
fi

echo "[run] manifest: ${MANIFEST}"
TOTAL_ALLELES=$(tail -n +2 "${MANIFEST}" | wc -l)
echo "[run] total alleles in manifest: ${TOTAL_ALLELES}"

# ============================================================
# Step 3: 循环 allele，调用 predict_immunogenicity.py
# ============================================================
# manifest CSV 列：allele_tag,original_hla,is_supported,pep_count,pep_filename,scores_filename
DONE_COUNT=0
SKIP_COUNT=0
FAIL_COUNT=0
ROW_NUM=0

while IFS=',' read -r allele_tag original_hla is_supported pep_count pep_filename scores_filename; do
    # 跳过 header
    [[ "${allele_tag}" == "allele_tag" ]] && continue

    ROW_NUM=$((ROW_NUM + 1))

    # smoke 模式只跑第一行
    if [[ "${SMOKE_MODE}" -eq 1 && "${ROW_NUM}" -gt 1 ]]; then
        break
    fi

    PEP_FILE="${INPUTS_DIR}/${pep_filename}"
    SCORES_FILE="${SCORES_DIR}/${scores_filename}"

    # 跳过已完成（scores 文件存在且非空）
    if [[ -f "${SCORES_FILE}" && -s "${SCORES_FILE}" ]]; then
        echo "[skip] ${allele_tag}  →  ${scores_filename} (已存在)"
        SKIP_COUNT=$((SKIP_COUNT + 1))
        continue
    fi

    # 检查肽文件
    if [[ ! -f "${PEP_FILE}" ]]; then
        echo "[warn] pep file not found, skip: ${PEP_FILE}" >&2
        FAIL_COUNT=$((FAIL_COUNT + 1))
        continue
    fi

    # smoke 模式：只取前 3 条肽
    if [[ "${SMOKE_MODE}" -eq 1 ]]; then
        SMOKE_PEP_FILE="${TOOL_DIR}/smoke_test.txt"
        head -3 "${PEP_FILE}" > "${SMOKE_PEP_FILE}"
        PEP_FILE="${SMOKE_PEP_FILE}"
        pep_count=3
        echo "[smoke] pep_file truncated to 3 lines for smoke test"
    fi

    echo "[run] ${allele_tag}  (supported=${is_supported}, peps=${pep_count}) ..."

    # 打分调用
    if [[ "${is_supported}" == "True" ]]; then
        # allele-specific anchor mask
        python "${PRED_SCRIPT}" \
            --allele="${allele_tag}" \
            "${PEP_FILE}" \
            > "${SCORES_FILE}" 2>&1
    else
        # 默认 mask（P1, P2, C-term）
        python "${PRED_SCRIPT}" \
            "${PEP_FILE}" \
            > "${SCORES_FILE}" 2>&1
    fi

    ret=$?
    if [[ ${ret} -eq 0 ]]; then
        DONE_COUNT=$((DONE_COUNT + 1))
        LINES=$(wc -l < "${SCORES_FILE}")
        echo "[done] ${allele_tag}  →  ${scores_filename}  (${LINES} output lines)"
    else
        FAIL_COUNT=$((FAIL_COUNT + 1))
        echo "[fail] ${allele_tag} exit=${ret}; see ${SCORES_FILE}" >&2
        # 不 exit，继续其他 allele
    fi

done < "${MANIFEST}"

echo ""
echo "IEDB Calis end $(date)"
echo "  done=${DONE_COUNT}  skipped=${SKIP_COUNT}  failed=${FAIL_COUNT}"
echo ""
echo "[next] 取回 ${SCORES_DIR}/ 到本地，运行 parse_output.py 回贴 universe.csv"
echo "  python parse_output.py --scores-dir <本地 scores 路径> --out-csv <...>/IEDB_Calis_DS1DS2_scores.csv"
