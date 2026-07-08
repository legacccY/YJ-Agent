#!/bin/bash
#SBATCH --job-name=ia_rerun
#SBATCH --account=shuihuawang
#SBATCH --partition=cpudebug
#SBATCH --qos=cpudebug
#SBATCH --cpus-per-task=4
#SBATCH --mem=8G
#SBATCH --time=01:00:00
#SBATCH --output=/gpfs/work/bio/jiayu2403/quantimmu/rerun/logs/ia_rerun_%j.out
#SBATCH --error=/gpfs/work/bio/jiayu2403/quantimmu/rerun/logs/ia_rerun_%j.err
# =============================================================================
# run_immuneapp_rerun.sh — ImmuneApp on RERUN inputs (改动②/③ 全量重跑, CPU)
# 克隆自 run_immuneapp_official.sh，唯一改动 = INPUT_BASE→rerun / OUTPUT_BASE→rerun/immuneapp_out
# MT + WT 双侧都跑（rerun 全 26 allele 均含 peps_WT.txt = 改动③ 全 WT）。
# =============================================================================
set -u

QUANT_BASE=/gpfs/work/bio/jiayu2403/quantimmu
IMMUNEAPP_DIR=${QUANT_BASE}/tools_repos/ImmuneApp
INPUT_BASE=${QUANT_BASE}/rerun
OUTPUT_BASE=${QUANT_BASE}/rerun/immuneapp_out
IMMUNEAPP_ENV=${QUANT_BASE}/envs/immuneapp

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

n_done=0
for allele_dir in "${INPUT_BASE}"/immuneapp_input_*/; do
    [ -d "${allele_dir}" ] || continue
    dirname=$(basename "${allele_dir}")          # immuneapp_input_HLA-A_02_01
    allele_safe=${dirname#immuneapp_input_}      # HLA-A_02_01
    allele_std=$(echo "${allele_safe}" | sed 's/_\([0-9]\)/*\1/' | sed 's/_\([0-9]\)/:\1/')

    out_dir_mt="${OUTPUT_BASE}/${allele_safe}/MT"
    out_dir_wt="${OUTPUT_BASE}/${allele_safe}/WT"

    pep_mt="${allele_dir}/peps_MT.txt"
    if [ -s "${pep_mt}" ]; then
        mkdir -p "${out_dir_mt}"
        python "${IMMUNEAPP_DIR}/ImmuneApp_immunogenicity_prediction.py" \
            -f "${pep_mt}" -a "${allele_std}" -o "${out_dir_mt}" \
            && echo "[OK ] ${allele_std} MT → ${out_dir_mt}" \
            || echo "[WARN] ${allele_std} MT ImmuneApp 失败，跳过"
    else
        echo "[SKIP] ${allele_std} MT：peps_MT.txt 为空/缺失"
    fi

    pep_wt="${allele_dir}/peps_WT.txt"
    if [ -s "${pep_wt}" ]; then
        mkdir -p "${out_dir_wt}"
        python "${IMMUNEAPP_DIR}/ImmuneApp_immunogenicity_prediction.py" \
            -f "${pep_wt}" -a "${allele_std}" -o "${out_dir_wt}" \
            && echo "[OK ] ${allele_std} WT → ${out_dir_wt}" \
            || echo "[WARN] ${allele_std} WT ImmuneApp 失败，跳过"
    fi

    n_done=$((n_done + 1))
    echo "[PROGRESS] 已处理 ${n_done} 个 allele 目录（${allele_safe}）"
done

n_tsv=$(find "${OUTPUT_BASE}" -name '*.tsv' -type f 2>/dev/null | wc -l)
echo "[DONE] ImmuneApp rerun：allele 目录 ${n_done} 个，预测 .tsv 文件=${n_tsv}"
echo "IMMUNEAPP_RERUN_DONE"
