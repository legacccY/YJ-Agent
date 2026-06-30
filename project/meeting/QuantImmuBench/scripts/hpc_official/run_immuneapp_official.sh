#!/usr/bin/env bash
# =============================================================================
# run_immuneapp_official.sh — ImmuneApp on NEW official inputs (HPC, CPU)
# =============================================================================
# 复制 scripts/wave3_bench/RUN_NOTES.md §4 的 per-allele 循环，
# 但输入指向 official_inputs/out_official/immuneapp_input_*，输出 immuneapp_out/。
# MT + WT 两侧都跑（26 个 MT allele 目录，仅 7 个含 peps_WT.txt）。
#
# 直跑：bash run_immuneapp_official.sh
# 纯 CPU，不需 GPU。
# =============================================================================
set -u

# ---------------------------------------------------------------------------
# 路径配置
# ---------------------------------------------------------------------------
QUANT_BASE=/gpfs/work/bio/jiayu2403/quantimmu
IMMUNEAPP_DIR=${QUANT_BASE}/tools_repos/ImmuneApp
INPUT_BASE=${QUANT_BASE}/official_inputs/out_official
OUTPUT_BASE=${QUANT_BASE}/official_inputs/immuneapp_out
IMMUNEAPP_ENV=${QUANT_BASE}/envs/immuneapp

# --- conda activate envs/immuneapp ---
module load miniconda3/22.11.1-gcc-8.5.0-l4fo6ta 2>/dev/null
if command -v conda >/dev/null 2>&1; then
    source "$(conda info --base)/etc/profile.d/conda.sh"
fi
conda activate "${IMMUNEAPP_ENV}" || { echo "[FATAL] 无法 activate ${IMMUNEAPP_ENV}"; exit 1; }

echo "[INFO] IMMUNEAPP_DIR = ${IMMUNEAPP_DIR}"
echo "[INFO] INPUT_BASE    = ${INPUT_BASE}"
echo "[INFO] OUTPUT_BASE   = ${OUTPUT_BASE}"
echo "[INFO] -----------------------------------------------------------------"

mkdir -p "${OUTPUT_BASE}"

# ImmuneApp 用相对路径读 supporting_file/*.npy，必须 cd 进 repo 根（输入/输出均绝对路径，cd 安全）
cd "${IMMUNEAPP_DIR}" || { echo "[FATAL] 无法 cd ${IMMUNEAPP_DIR}"; exit 1; }

# ---------------------------------------------------------------------------
# 按 allele 循环
# ---------------------------------------------------------------------------
n_done=0
for allele_dir in "${INPUT_BASE}"/immuneapp_input_*/; do
    [ -d "${allele_dir}" ] || continue
    dirname=$(basename "${allele_dir}")          # e.g. immuneapp_input_HLA-A_02_01
    allele_safe=${dirname#immuneapp_input_}      # e.g. HLA-A_02_01
    # 还原标准 HLA 格式（第一个 _DD → *DD，第二个 _DD → :DD）
    allele_std=$(echo "${allele_safe}" | sed 's/_\([0-9]\)/*\1/' | sed 's/_\([0-9]\)/:\1/')

    out_dir_mt="${OUTPUT_BASE}/${allele_safe}/MT"
    out_dir_wt="${OUTPUT_BASE}/${allele_safe}/WT"

    # ---- MT 侧 ----
    pep_mt="${allele_dir}/peps_MT.txt"
    if [ -s "${pep_mt}" ]; then
        mkdir -p "${out_dir_mt}"
        python "${IMMUNEAPP_DIR}/ImmuneApp_immunogenicity_prediction.py" \
            -f "${pep_mt}" \
            -a "${allele_std}" \
            -o "${out_dir_mt}" \
            && echo "[OK ] ${allele_std} MT → ${out_dir_mt}" \
            || echo "[WARN] ${allele_std} MT ImmuneApp 失败，跳过"
    else
        echo "[SKIP] ${allele_std} MT：peps_MT.txt 为空/缺失"
    fi

    # ---- WT 侧（仅 7 个 allele 有）----
    pep_wt="${allele_dir}/peps_WT.txt"
    if [ -s "${pep_wt}" ]; then
        mkdir -p "${out_dir_wt}"
        python "${IMMUNEAPP_DIR}/ImmuneApp_immunogenicity_prediction.py" \
            -f "${pep_wt}" \
            -a "${allele_std}" \
            -o "${out_dir_wt}" \
            && echo "[OK ] ${allele_std} WT → ${out_dir_wt}" \
            || echo "[WARN] ${allele_std} WT ImmuneApp 失败，跳过"
    fi

    n_done=$((n_done + 1))
    echo "[PROGRESS] 已处理 ${n_done} 个 allele 目录（${allele_safe}）"
done

# ---------------------------------------------------------------------------
# 末尾统计输出文件数
# ---------------------------------------------------------------------------
n_tsv=$(find "${OUTPUT_BASE}" -name '*.tsv' -type f 2>/dev/null | wc -l)
echo "[DONE] ImmuneApp official：allele 目录 ${n_done} 个，预测 .tsv 文件=${n_tsv}"
echo "[DONE] 输出根目录 ${OUTPUT_BASE}"
