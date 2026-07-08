#!/bin/bash
#SBATCH --job-name=prime_b2706
#SBATCH --account=shuihuawang
#SBATCH --partition=cpudebug
#SBATCH --qos=cpudebug
#SBATCH --cpus-per-task=4
#SBATCH --mem=8G
#SBATCH --time=01:00:00
#SBATCH --output=/gpfs/work/bio/jiayu2403/quantimmu/rerun/logs/prime_b2706_%j.out
#SBATCH --error=/gpfs/work/bio/jiayu2403/quantimmu/rerun/logs/prime_b2706_%j.err
# =============================================================================
# run_prime_b2706.sh — 单独补跑 B2706(HLA-B*27:06) MT+WT
# 并行版里 B2706 pan-predictor 被 4 路并发挤,30min 没跑完撞墙(out空)。
# 旧 official 证 B2706 可跑(53/53有分)。独占节点单跑 MT+WT 两侧(99+99肽),无竞争。
# MT/WT 并行(2任务/4核)。
# =============================================================================
set -u
QUANT_BASE=/gpfs/work/bio/jiayu2403/quantimmu
PRIME_DIR=${QUANT_BASE}/tools_repos/PRIME
RERUN=${QUANT_BASE}/rerun
PRIME_ENV=${QUANT_BASE}/envs/prime
AC=B2706

module load miniconda3/22.11.1-gcc-8.5.0-l4fo6ta 2>/dev/null
if command -v conda >/dev/null 2>&1; then source "$(conda info --base)/etc/profile.d/conda.sh"; fi
conda activate "${PRIME_ENV}" || { echo "[FATAL] activate 失败"; exit 1; }
MIX_DIR=$(find "${QUANT_BASE}/tools_repos/MixMHCpred" -maxdepth 4 -iname 'MixMHCpred' -type f 2>/dev/null | head -1)
[ -z "${MIX_DIR}" ] && { echo "[FATAL] 无 MixMHCpred"; exit 1; }
echo "[INFO] AC=${AC} MIX_DIR=${MIX_DIR} start=$(date)"
out_dir=${RERUN}/prime_out/${AC}; mkdir -p "${out_dir}"

do_side() {
  local s=$1; local pep=${RERUN}/prime_input_${AC}/peps_${s}.txt; local outf=${out_dir}/out_${s}.txt
  echo "[run] ${AC} ${s} ($(grep -c . ${pep}) 肽) start=$(date +%H:%M:%S)"
  "${PRIME_DIR}/PRIME" -i "${pep}" -o "${outf}" -a "${AC}" -mix "${MIX_DIR}" \
     && echo "[OK ] ${AC} ${s} end=$(date +%H:%M:%S) ($(grep -cvE '^#|^Peptide' ${outf}) 行)" \
     || echo "[WARN] ${AC} ${s} 失败"
}
do_side MT &
do_side WT &
wait
echo "PRIME_B2706_DONE $(date)"
