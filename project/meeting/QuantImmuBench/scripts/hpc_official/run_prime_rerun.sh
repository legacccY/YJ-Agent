#!/bin/bash
#SBATCH --job-name=prime_rerun
#SBATCH --account=shuihuawang
#SBATCH --partition=cpudebug
#SBATCH --qos=cpudebug
#SBATCH --cpus-per-task=4
#SBATCH --mem=8G
#SBATCH --time=01:00:00
#SBATCH --output=/gpfs/work/bio/jiayu2403/quantimmu/rerun/logs/prime_rerun_%j.out
#SBATCH --error=/gpfs/work/bio/jiayu2403/quantimmu/rerun/logs/prime_rerun_%j.err
# =============================================================================
# run_prime_rerun.sh — PRIME on RERUN inputs (改动②/③ 全量重跑, CPU only)
# 克隆自 run_prime_official.sh，唯一改动 = INPUT_BASE→rerun / OUTPUT_BASE→rerun/prime_out
# MT + WT 双侧都跑（rerun 全 26 allele 均含 peps_WT.txt = 改动③ 全 WT）。
# =============================================================================
set -u

QUANT_BASE=/gpfs/work/bio/jiayu2403/quantimmu
PRIME_DIR=${QUANT_BASE}/tools_repos/PRIME
INPUT_BASE=${QUANT_BASE}/rerun
OUTPUT_BASE=${QUANT_BASE}/rerun/prime_out
PRIME_ENV=${QUANT_BASE}/envs/prime

module load miniconda3/22.11.1-gcc-8.5.0-l4fo6ta 2>/dev/null
if command -v conda >/dev/null 2>&1; then
    source "$(conda info --base)/etc/profile.d/conda.sh"
fi
conda activate "${PRIME_ENV}" || { echo "[FATAL] 无法 activate ${PRIME_ENV}"; exit 1; }

MIX_DIR=$(find "${QUANT_BASE}/tools_repos/MixMHCpred" "${QUANT_BASE}/ext_tools" "${QUANT_BASE}/mixmhcpred_run" \
    -maxdepth 4 -iname 'MixMHCpred' -type f 2>/dev/null | head -1)
if [ -z "${MIX_DIR}" ]; then
    echo "[FATAL] 未定位到 MixMHCpred 可执行文件。" >&2
    exit 1
fi
echo "[INFO] PRIME_DIR  = ${PRIME_DIR}"
echo "[INFO] MIX_DIR    = ${MIX_DIR}"
echo "[INFO] INPUT_BASE = ${INPUT_BASE}"
echo "[INFO] OUTPUT_BASE= ${OUTPUT_BASE}"
echo "[INFO] -----------------------------------------------------------------"

mkdir -p "${OUTPUT_BASE}"

n_done=0
for allele_dir in "${INPUT_BASE}"/prime_input_*/; do
    [ -d "${allele_dir}" ] || continue
    allele=$(basename "${allele_dir}")          # prime_input_A0201
    allele_code=${allele#prime_input_}          # A0201
    case "${allele_code}" in map*) continue;; esac  # 跳过 prime_input_map_*.csv 若被 glob 误匹配

    out_dir="${OUTPUT_BASE}/${allele_code}"
    mkdir -p "${out_dir}"

    pep_mt="${allele_dir}/peps_MT.txt"
    if [ -s "${pep_mt}" ]; then
        out_mt="${out_dir}/out_MT.txt"
        "${PRIME_DIR}/PRIME" -i "${pep_mt}" -o "${out_mt}" -a "${allele_code}" -mix "${MIX_DIR}" \
            && echo "[OK ] ${allele_code} MT → ${out_mt}" \
            || echo "[WARN] ${allele_code} MT PRIME 失败，跳过"
    else
        echo "[SKIP] ${allele_code} MT：peps_MT.txt 为空/缺失"
    fi

    pep_wt="${allele_dir}/peps_WT.txt"
    if [ -s "${pep_wt}" ]; then
        out_wt="${out_dir}/out_WT.txt"
        "${PRIME_DIR}/PRIME" -i "${pep_wt}" -o "${out_wt}" -a "${allele_code}" -mix "${MIX_DIR}" \
            && echo "[OK ] ${allele_code} WT → ${out_wt}" \
            || echo "[WARN] ${allele_code} WT PRIME 失败，跳过"
    fi

    n_done=$((n_done + 1))
    echo "[PROGRESS] 已处理 ${n_done} 个 allele 目录"
done

n_mt=$(find "${OUTPUT_BASE}" -name 'out_MT.txt' -type f 2>/dev/null | wc -l)
n_wt=$(find "${OUTPUT_BASE}" -name 'out_WT.txt' -type f 2>/dev/null | wc -l)
echo "[DONE] PRIME rerun：allele 目录 ${n_done} 个，out_MT.txt=${n_mt}，out_WT.txt=${n_wt}"
echo "PRIME_RERUN_DONE"
