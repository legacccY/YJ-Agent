#!/bin/bash
#SBATCH --job-name=prime_par
#SBATCH --account=shuihuawang
#SBATCH --partition=cpudebug
#SBATCH --qos=cpudebug
#SBATCH --cpus-per-task=4
#SBATCH --mem=8G
#SBATCH --time=01:00:00
#SBATCH --output=/gpfs/work/bio/jiayu2403/quantimmu/rerun/logs/prime_par_%j.out
#SBATCH --error=/gpfs/work/bio/jiayu2403/quantimmu/rerun/logs/prime_par_%j.err
# =============================================================================
# run_prime_rerun_par.sh — PRIME rerun 并行版(cpudebug, 4 核并发)
# 串行版 41min 才 13/26 会撞 1h 墙；gpu4090 排队要 2 天(全校挤爆)。
# → 回 cpudebug + (allele,side) 粒度并行(max 4 并发, 匹配 cpus-per-task=4)。
# 26 allele × 2 侧 = 52 任务 / 4 ≈ 13 波 × ~3min ≈ ~40min? 实测串行 41min/13allele=~1.6min/(allele·side)
# → 52 任务 ×1.6min /4 并发 ≈ 21min，稳落 1h 内。
# 每 (allele,side) 写独立 out_{MT,WT}.txt，无冲突，并行安全。
# =============================================================================
set -u

QUANT_BASE=/gpfs/work/bio/jiayu2403/quantimmu
PRIME_DIR=${QUANT_BASE}/tools_repos/PRIME
INPUT_BASE=${QUANT_BASE}/rerun
OUTPUT_BASE=${QUANT_BASE}/rerun/prime_out
PRIME_ENV=${QUANT_BASE}/envs/prime
NPROC=4

module load miniconda3/22.11.1-gcc-8.5.0-l4fo6ta 2>/dev/null
if command -v conda >/dev/null 2>&1; then
    source "$(conda info --base)/etc/profile.d/conda.sh"
fi
conda activate "${PRIME_ENV}" || { echo "[FATAL] 无法 activate ${PRIME_ENV}"; exit 1; }

MIX_DIR=$(find "${QUANT_BASE}/tools_repos/MixMHCpred" "${QUANT_BASE}/ext_tools" "${QUANT_BASE}/mixmhcpred_run" \
    -maxdepth 4 -iname 'MixMHCpred' -type f 2>/dev/null | head -1)
if [ -z "${MIX_DIR}" ]; then echo "[FATAL] 未定位 MixMHCpred" >&2; exit 1; fi
echo "[INFO] PRIME_DIR=${PRIME_DIR} MIX_DIR=${MIX_DIR} NPROC=${NPROC}"
echo "[INFO] INPUT_BASE=${INPUT_BASE} OUTPUT_BASE=${OUTPUT_BASE}"

mkdir -p "${OUTPUT_BASE}"

export PRIME_DIR MIX_DIR

# 生成 (allele,side,pep,out) 任务清单 → xargs -P 并行 (内联, 不依赖函数导出)
tasks=""
for allele_dir in "${INPUT_BASE}"/prime_input_*/; do
    [ -d "${allele_dir}" ] || continue
    allele=$(basename "${allele_dir}"); allele_code=${allele#prime_input_}
    case "${allele_code}" in map*) continue;; esac
    out_dir="${OUTPUT_BASE}/${allele_code}"; mkdir -p "${out_dir}"
    tasks+="${allele_code}|MT|${allele_dir}peps_MT.txt|${out_dir}/out_MT.txt"$'\n'
    tasks+="${allele_code}|WT|${allele_dir}peps_WT.txt|${out_dir}/out_WT.txt"$'\n'
done

echo "[run] 任务数=$(printf '%s' "${tasks}" | grep -c '|') 并发=${NPROC}"
printf '%s' "${tasks}" | grep '|' | xargs -P "${NPROC}" -I {} bash -c '
    IFS="|" read -r ac side pep outf <<< "$1"
    if [ -s "$pep" ]; then
        "$PRIME_DIR/PRIME" -i "$pep" -o "$outf" -a "$ac" -mix "$MIX_DIR" \
            && echo "[OK ] $ac $side" || echo "[WARN] $ac $side PRIME 失败"
    else
        echo "[SKIP] $ac $side: 空"
    fi
' _ {}

n_mt=$(find "${OUTPUT_BASE}" -name 'out_MT.txt' -type f 2>/dev/null | wc -l)
n_wt=$(find "${OUTPUT_BASE}" -name 'out_WT.txt' -type f 2>/dev/null | wc -l)
echo "[DONE] PRIME 并行 rerun：out_MT.txt=${n_mt}/26，out_WT.txt=${n_wt}/26"
echo "PRIME_RERUN_DONE"
