#!/bin/bash
#SBATCH --job-name=prime_b2706c
#SBATCH --account=shuihuawang
#SBATCH --partition=cpudebug
#SBATCH --qos=cpudebug
#SBATCH --cpus-per-task=4
#SBATCH --mem=8G
#SBATCH --time=01:00:00
#SBATCH --output=/gpfs/work/bio/jiayu2403/quantimmu/rerun/logs/prime_b2706c_%j.out
#SBATCH --error=/gpfs/work/bio/jiayu2403/quantimmu/rerun/logs/prime_b2706c_%j.err
# =============================================================================
# run_prime_b2706_chunked.sh — B2706 4路并行(切块)补跑 MT+WT
# B2706 无原生 PWM 走 pan-predictor,单肽慢(~40s)。99+99肽 2路并行=~66min撞1h墙。
# → 每侧切 4 块 = 8 块,xargs -P4 占满 4 核(2 波),总 ~33min 落进墙。
# 同等位分块输出格式一致,拼接: 块0全头 + 各块数据行(去#和Peptide表头)。
# =============================================================================
set -u
QUANT_BASE=/gpfs/work/bio/jiayu2403/quantimmu
PRIME_DIR=${QUANT_BASE}/tools_repos/PRIME
RERUN=${QUANT_BASE}/rerun
PRIME_ENV=${QUANT_BASE}/envs/prime
AC=B2706
NCHUNK=4          # 每侧切块数
NPROC=4           # 并发核数

module load miniconda3/22.11.1-gcc-8.5.0-l4fo6ta 2>/dev/null
if command -v conda >/dev/null 2>&1; then source "$(conda info --base)/etc/profile.d/conda.sh"; fi
conda activate "${PRIME_ENV}" || { echo "[FATAL] activate 失败"; exit 1; }
MIX_DIR=$(find "${QUANT_BASE}/tools_repos/MixMHCpred" -maxdepth 4 -iname 'MixMHCpred' -type f 2>/dev/null | head -1)
[ -z "${MIX_DIR}" ] && { echo "[FATAL] 无 MixMHCpred"; exit 1; }
out_dir=${RERUN}/prime_out/${AC}; mkdir -p "${out_dir}"
work=${RERUN}/prime_out/${AC}/_chunks; rm -rf "${work}"; mkdir -p "${work}"
export PRIME_DIR MIX_DIR AC
echo "[INFO] ${AC} chunked start=$(date) NCHUNK=${NCHUNK} NPROC=${NPROC} MIX=${MIX_DIR}"

# 生成切块任务清单 (side + chunk_idx)
tasks=""
for s in MT WT; do
    pep=${RERUN}/prime_input_${AC}/peps_${s}.txt
    total=$(grep -c . "${pep}")
    per=$(( (total + NCHUNK - 1) / NCHUNK ))
    split -l "${per}" -d -a 2 "${pep}" "${work}/pep_${s}_"
    for ck in "${work}/pep_${s}_"*; do
        [ -f "${ck}" ] || continue
        tasks+="${s}|${ck}|${work}/out_${s}_$(basename ${ck} | sed "s/pep_${s}_//").txt"$'\n'
    done
done
echo "[run] 块任务数=$(printf '%s' "${tasks}" | grep -c '|') 并发=${NPROC}"

printf '%s' "${tasks}" | grep '|' | xargs -P "${NPROC}" -I {} bash -c '
    IFS="|" read -r s ck outf <<< "$1"
    "$PRIME_DIR/PRIME" -i "$ck" -o "$outf" -a "$AC" -mix "$MIX_DIR" >/dev/null 2>&1 \
        && echo "[OK ] $AC $s $(basename $ck) ($(grep -cvE "^#|^Peptide" "$outf") 行)" \
        || echo "[WARN] $AC $s $(basename $ck) 失败"
' _ {}

# 拼接: 每侧 块0全头(含#和Peptide表头) + 所有块数据行
for s in MT WT; do
    final=${out_dir}/out_${s}.txt
    chunks=$(ls "${work}/out_${s}_"*.txt 2>/dev/null | sort)
    first=$(echo "${chunks}" | head -1)
    if [ -z "${first}" ]; then echo "[ERR] ${s} 无块输出"; continue; fi
    # 头 = 第一块的 # 块 + Peptide 表头行
    grep -E '^#|^Peptide' "${first}" > "${final}"
    # 数据 = 所有块的非#非表头行
    for cf in ${chunks}; do grep -vE '^#|^Peptide' "${cf}"; done >> "${final}"
    echo "[MERGE] ${AC} ${s} → ${final} ($(grep -cvE '^#|^Peptide' ${final}) 数据行, 输入 $(grep -c . ${RERUN}/prime_input_${AC}/peps_${s}.txt))"
done
echo "PRIME_B2706_CHUNKED_DONE $(date)"
