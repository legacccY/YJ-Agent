#!/usr/bin/env bash
# =============================================================================
# run_predig_official.sh — PredIG on NEW official inputs (HPC, CPU only)
# =============================================================================
# 输入指向 official_inputs/out_official/predig_input.csv（2005 行：1761 MT + 244 WT，
# 列 epitope,HLA_allele,protein_seq,protein_name；只读，不改），输出 predig_out/。
#
# 【真入口】predig.sif 是 OCI 镜像，其 runscript(=docker ENTRYPOINT)=
#   "micromamba run -n predig_env python /Immuno/run_predig/run.py"
# 所以必须用 `singularity run`（执行 runscript）而非 `singularity exec predig.sif predig`
# （镜像内无 `predig` 命令，故那条会报 "predig: executable file not found in PATH"）。
# 入参与 docker 版完全一致：<input.csv 位置参> -o <out.csv> --modelXG neoant --type recombinant
# 证据：HPC/elispot_run/predig_elispot.sh 已用此命令成功跑过 elispot 批次。
#
# 容器 run.py 单次 input CSV 限 <5000 行；official 输入 2005 行 < 5000，单次跑即可（无需分块）。
#
# 直跑：bash run_predig_official.sh      （纯 CPU，无需 GPU；主线决定直跑 / sbatch 包一层）
# =============================================================================
set -u

# ---------------------------------------------------------------------------
# 路径配置
# ---------------------------------------------------------------------------
QUANT_BASE=/gpfs/work/bio/jiayu2403/quantimmu
SIF=${QUANT_BASE}/sif/predig.sif
INPUT_BASE=${QUANT_BASE}/official_inputs/out_official        # 只读：含 predig_input.csv
OUTPUT_BASE=${QUANT_BASE}/official_inputs/predig_out         # 输出目录
INPUT_CSV=${INPUT_BASE}/predig_input.csv
OUT_CSV=${OUTPUT_BASE}/predig_out.csv

echo "[INFO] SIF        = ${SIF}"
echo "[INFO] INPUT_CSV  = ${INPUT_CSV}"
echo "[INFO] OUTPUT_BASE= ${OUTPUT_BASE}"
echo "[INFO] -----------------------------------------------------------------"

[ -f "${SIF}" ]       || { echo "[FATAL] 缺 sif: ${SIF}"; exit 1; }
[ -f "${INPUT_CSV}" ] || { echo "[FATAL] 缺输入: ${INPUT_CSV}"; exit 1; }
mkdir -p "${OUTPUT_BASE}"

n_in=$(($(wc -l < "${INPUT_CSV}") - 1))
echo "[INFO] 输入数据行（不含表头）= ${n_in}"
if [ "${n_in}" -ge 5000 ]; then
    # TODO: 输入 ≥5000 行触发容器 run.py 单文件上限，需切块跑（参 scripts/phaseB/hpc/run_predig_hpc.sh
    #       的分块逻辑：每块 ≤4000 行逐块 singularity run，跑完按 K 序 awk 拼回 out.csv）。
    echo "[FATAL] 输入 ${n_in} 行 ≥5000，超容器单文件上限，需分块。当前脚本只支持单次跑。" >&2
    exit 1
fi

# ---------------------------------------------------------------------------
# 跑 PredIG（singularity run = 执行 runscript = python /Immuno/run_predig/run.py）
#   挂 INPUT_BASE→/in（只读）、OUTPUT_BASE→/out（写）。input.csv 位置参 + -o out.csv。
#   --modelXG neoant（新抗原模型）--type recombinant（绕 UniProt 库，与 86 肽部署口径一致）。
# ---------------------------------------------------------------------------
echo "[INFO] PredIG start $(date) node=$(hostname)"
singularity run --writable-tmpfs \
    -B "${INPUT_BASE}:/in" \
    -B "${OUTPUT_BASE}:/out" \
    "${SIF}" \
    /in/predig_input.csv -o /out/predig_out.csv --modelXG neoant --type recombinant
rc=$?
echo "[INFO] PredIG exit=${rc} end $(date)"

if [ "${rc}" -ne 0 ]; then
    echo "[FATAL] PredIG 返回非零 rc=${rc}，未产可信输出。" >&2
    exit "${rc}"
fi

if [ -s "${OUT_CSV}" ]; then
    n_out=$(($(wc -l < "${OUT_CSV}") - 1))
    echo "[DONE] PredIG official 输出 ${n_out} 数据行 → ${OUT_CSV}"
    echo "[DONE] （预期 ${n_in} 行；行数应等于输入，parse 阶段会按行序位置 join + 断言）"
else
    echo "[FATAL] 输出 ${OUT_CSV} 为空，PredIG 未产结果。" >&2
    exit 1
fi
