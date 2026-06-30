#!/usr/bin/env bash
# =============================================================================
# run_deephlapan_official.sh — deepHLApan on NEW official inputs (MT + WT)
# =============================================================================
# 服务: quantimmu-bench Phase0 官方数据工具补跑 / deepHLApan
#
# deepHLApan = context-free：每行输出自带 HLA 列，分数只取决于 (peptide,HLA)。
# 故**整份输入一次跑**，不需 PRIME/ImmuneApp 那样 per-allele 拆分。
# 官方 batch 入口（已核 README）：  deephlapan -F <input.csv> -O <outdir>
#   输入 header: Annotation,HLA,peptide（HLA 无星号 HLA-A66:01；本数据全 9mer）
#   输出文件   : <input_basename>_predicted_result.csv  (+ _rank.csv)
#   输出列     : Annotation,HLA,Peptide,binding score,immunogenic score
#   ⚠️坑       : 输出目录须**先建好**（DEPLOY_TRACKER 记 outdir 须先建）
#
# 两种执行后端（用 --mode 选）：
#   --mode docker  本机/WSL2 docker  biopharm/deephlapan:v1.1  ← 默认，已实证跑通（最稳）
#   --mode sif     HPC singularity   $ROOT/sif/deephlapan.sif  ← 需先 build（见 deploy_deephlapan.sh）
#
# 用法:
#   # 本机 WSL2（proven，CPU，~1700 肽几分钟）:
#   bash run_deephlapan_official.sh --mode docker
#   # HPC（sif 已 build 后，主线在登录节点跑）:
#   bash run_deephlapan_official.sh --mode sif
#
# 纯 CPU，不需 GPU。
# =============================================================================
set -u

MODE="docker"
[ "${1:-}" = "--mode" ] && { MODE="${2:-docker}"; }

# ---------------------------------------------------------------------------
# 路径（docker 与 sif 各自的根；输入/输出/map 按后端不同挂载）
# ---------------------------------------------------------------------------
if [ "$MODE" = "sif" ]; then
    # --- HPC singularity ---
    ROOT=/gpfs/work/bio/jiayu2403/quantimmu
    INPUT_BASE="${ROOT}/official_inputs/out_official"
    OUTPUT_BASE="${ROOT}/official_inputs/deephlapan_out"
    SIF="${ROOT}/sif/deephlapan.sif"
else
    # --- 本机 WSL2 docker（路径为 WSL2 内的挂载点；按实际改）---
    # 约定: 把 scripts/out_official 同步到 WSL2 工作目录后跑。
    WORK="${DEEPHLAPAN_WORK:-/mnt/d/YJ-Agent/project/meeting/QuantImmuBench/scripts/out_official}"
    INPUT_BASE="${WORK}"
    OUTPUT_BASE="${WORK}"
    DOCKER_IMG="biopharm/deephlapan:v1.1"
fi

MT_IN="${INPUT_BASE}/deephlapan_input_MT.csv"
WT_IN="${INPUT_BASE}/deephlapan_input_WT.csv"
MT_OUT="${OUTPUT_BASE}/deephlapan_out_MT"
WT_OUT="${OUTPUT_BASE}/deephlapan_out_WT"

echo "[INFO] MODE       = ${MODE}"
echo "[INFO] MT_IN      = ${MT_IN}"
echo "[INFO] WT_IN      = ${WT_IN}"
echo "[INFO] MT_OUT     = ${MT_OUT}"
echo "[INFO] WT_OUT     = ${WT_OUT}"
echo "[INFO] -----------------------------------------------------------------"

# ⚠️ 输出目录须先建（官方坑）
mkdir -p "${MT_OUT}" "${WT_OUT}"

run_one() {
    local in_csv="$1" out_dir="$2" tag="$3"
    if [ ! -s "${in_csv}" ]; then
        echo "[SKIP] ${tag}: 输入缺失/为空 ${in_csv}"
        return 0
    fi
    echo "[RUN ] ${tag}: deephlapan -F ${in_csv} -O ${out_dir}"
    if [ "${MODE}" = "sif" ]; then
        # singularity：--no-home 防读到 HPC home 里的杂 python；输入/输出绝对路径已 bind（gpfs 默认可见）
        singularity exec "${SIF}" deephlapan -F "${in_csv}" -O "${out_dir}/" \
            && echo "[OK ] ${tag} → ${out_dir}" \
            || echo "[WARN] ${tag} deepHLApan 失败"
    else
        # docker：把输入/输出所在目录挂进容器；容器内路径与宿主一致以简化
        docker run --rm \
            -v "${INPUT_BASE}:${INPUT_BASE}" \
            -v "${OUTPUT_BASE}:${OUTPUT_BASE}" \
            "${DOCKER_IMG}" deephlapan -F "${in_csv}" -O "${out_dir}/" \
            && echo "[OK ] ${tag} → ${out_dir}" \
            || echo "[WARN] ${tag} deepHLApan 失败"
    fi
}

run_one "${MT_IN}" "${MT_OUT}" "MT"
run_one "${WT_IN}" "${WT_OUT}" "WT"

# ---------------------------------------------------------------------------
# 末尾统计
# ---------------------------------------------------------------------------
n_csv=$(find "${MT_OUT}" "${WT_OUT}" -name '*_predicted_result.csv' -type f 2>/dev/null | wc -l)
echo "[DONE] deepHLApan official：predicted_result.csv 文件=${n_csv}"
echo "[DONE] MT → ${MT_OUT}/deephlapan_input_MT_predicted_result.csv"
echo "[DONE] WT → ${WT_OUT}/deephlapan_input_WT_predicted_result.csv"
echo "[NEXT] 拉回本地后跑 parse_deephlapan_official.py → deepHLApan_official.csv"
