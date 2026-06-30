#!/usr/bin/env bash
# =============================================================================
# run_prime_official.sh — PRIME on NEW official inputs (HPC, CPU only)
# =============================================================================
# 复制 scripts/wave3_bench/RUN_NOTES.md §3 的 per-allele 循环，
# 但输入指向 official_inputs/out_official/prime_input_*，输出 prime_out/。
# MT + WT 两侧都跑（注意：26 个 MT allele 目录，仅 7 个含 peps_WT.txt）。
#
# 直跑：bash run_prime_official.sh
# 纯 CPU，不需 GPU；登录节点能跑就直跑（主线决定直跑 / sbatch 提交）。
# =============================================================================
set -u   # 故意不 set -e：单 allele 失败要跳过继续，不整批退出

# ---------------------------------------------------------------------------
# 路径配置
# ---------------------------------------------------------------------------
QUANT_BASE=/gpfs/work/bio/jiayu2403/quantimmu
PRIME_DIR=${QUANT_BASE}/tools_repos/PRIME
INPUT_BASE=${QUANT_BASE}/official_inputs/out_official
OUTPUT_BASE=${QUANT_BASE}/official_inputs/prime_out
PRIME_ENV=${QUANT_BASE}/envs/prime

# --- conda activate envs/prime ---
module load miniconda3/22.11.1-gcc-8.5.0-l4fo6ta 2>/dev/null
if command -v conda >/dev/null 2>&1; then
    source "$(conda info --base)/etc/profile.d/conda.sh"
fi
conda activate "${PRIME_ENV}" || { echo "[FATAL] 无法 activate ${PRIME_ENV}"; exit 1; }

# --- 定位 MixMHCpred 可执行文件（PRIME -mix 依赖）---
# RUN_NOTES：PRIME 依赖 MixMHCpred，路径在 ext_tools/ 或 mixmhcpred_run/，先 find 定位。
MIX_DIR=$(find "${QUANT_BASE}/tools_repos/MixMHCpred" "${QUANT_BASE}/ext_tools" "${QUANT_BASE}/mixmhcpred_run" \
    -maxdepth 4 -iname 'MixMHCpred' -type f 2>/dev/null | head -1)
if [ -z "${MIX_DIR}" ]; then
    # TODO: 未在 ext_tools/ 或 mixmhcpred_run/ 找到 MixMHCpred 可执行文件，
    #       需 researcher/主线在 HPC 上手动 `find ${QUANT_BASE} -iname MixMHCpred -type f` 确认后填此处。
    echo "[FATAL] 未定位到 MixMHCpred 可执行文件，请手动确认路径后填 MIX_DIR。" >&2
    echo "        尝试：find ${QUANT_BASE} -iname 'MixMHCpred' -type f" >&2
    exit 1
fi
echo "[INFO] PRIME_DIR  = ${PRIME_DIR}"
echo "[INFO] MIX_DIR    = ${MIX_DIR}"
echo "[INFO] INPUT_BASE = ${INPUT_BASE}"
echo "[INFO] OUTPUT_BASE= ${OUTPUT_BASE}"
echo "[INFO] -----------------------------------------------------------------"

mkdir -p "${OUTPUT_BASE}"

# ---------------------------------------------------------------------------
# 按 allele 循环
# ---------------------------------------------------------------------------
n_done=0
for allele_dir in "${INPUT_BASE}"/prime_input_*/; do
    [ -d "${allele_dir}" ] || continue
    allele=$(basename "${allele_dir}")          # e.g. prime_input_A0201
    allele_code=${allele#prime_input_}          # e.g. A0201

    out_dir="${OUTPUT_BASE}/${allele_code}"
    mkdir -p "${out_dir}"

    # ---- MT 侧 ----
    pep_mt="${allele_dir}/peps_MT.txt"
    if [ -s "${pep_mt}" ]; then
        out_mt="${out_dir}/out_MT.txt"
        "${PRIME_DIR}/PRIME" \
            -i "${pep_mt}" \
            -o "${out_mt}" \
            -a "${allele_code}" \
            -mix "${MIX_DIR}" \
            && echo "[OK ] ${allele_code} MT → ${out_mt}" \
            || echo "[WARN] ${allele_code} MT PRIME 失败，跳过"
    else
        echo "[SKIP] ${allele_code} MT：peps_MT.txt 为空/缺失"
    fi

    # ---- WT 侧（仅 7 个 allele 有）----
    pep_wt="${allele_dir}/peps_WT.txt"
    if [ -s "${pep_wt}" ]; then
        out_wt="${out_dir}/out_WT.txt"
        "${PRIME_DIR}/PRIME" \
            -i "${pep_wt}" \
            -o "${out_wt}" \
            -a "${allele_code}" \
            -mix "${MIX_DIR}" \
            && echo "[OK ] ${allele_code} WT → ${out_wt}" \
            || echo "[WARN] ${allele_code} WT PRIME 失败，跳过"
    fi

    n_done=$((n_done + 1))
    echo "[PROGRESS] 已处理 ${n_done} 个 allele 目录"
done

# ---------------------------------------------------------------------------
# 末尾统计输出文件数
# ---------------------------------------------------------------------------
n_mt=$(find "${OUTPUT_BASE}" -name 'out_MT.txt' -type f 2>/dev/null | wc -l)
n_wt=$(find "${OUTPUT_BASE}" -name 'out_WT.txt' -type f 2>/dev/null | wc -l)
echo "[DONE] PRIME official：allele 目录 ${n_done} 个，out_MT.txt=${n_mt}，out_WT.txt=${n_wt}"
echo "[DONE] 输出根目录 ${OUTPUT_BASE}"
