#!/usr/bin/env bash
# =============================================================================
# run_dtu_icerfire_official.sh — ICERFIRE-1.0 on NEW official inputs (HPC).
#   Service: quantimmu-bench / node tools_dtu (W1).
# =============================================================================
# ICERFIRE.sh 全流程（NetMHCpan + KernDist + PepX + RF），config 路径已配好。
#   输入 icerfire_input.csv（mut,wt,HLA 无表头，仅 244 有 WT 的 SNV 行；
#   ICERFIRE 强制需 WT）。无表达数据 → -a false -u false（ExprFalse 模型）。
#   conda env qib_icerfire（sklearn 1.0.2 / numpy 1.21.5 / pandas 1.4.2，W1 确认）。
# 输出 <basename>_scored_output → parse_icerfire_official.py（行序对齐 index）。
#
# 直跑: bash run_dtu_icerfire_official.sh
# =============================================================================
set -u
ROOT=/gpfs/work/bio/jiayu2403/quantimmu
USERDIR=${ROOT}/ext_tools/ICERFIRE
IN=${ROOT}/ds1/icerfire_inputs
INPUT_CSV=${IN}/icerfire_input.csv

module load miniconda3/22.11.1-gcc-8.5.0-l4fo6ta 2>/dev/null
source "$(conda info --base)/etc/profile.d/conda.sh" 2>/dev/null
conda activate "${ROOT}/envs/qib_icerfire" || { echo "[FATAL] activate qib_icerfire 失败"; exit 1; }

[ -s "$INPUT_CSV" ] || { echo "[FATAL] input missing: $INPUT_CSV"; exit 1; }
echo "[INFO] input rows: $(wc -l < "$INPUT_CSV")"

cd "${USERDIR}/bashscripts" || exit 1
./ICERFIRE.sh -f "${INPUT_CSV}" -a false -u false
ec=$?
echo "[INFO] ICERFIRE exit=$ec"

echo "[INFO] 查找输出 *_scored_output*："
base=$(basename "${INPUT_CSV}" .csv)
find "${USERDIR}/bashscripts" "${IN}" -name "${base}_scored_output*" 2>/dev/null
# 若落在 bashscripts/ 移到 input 目录
if [ -f "${USERDIR}/bashscripts/${base}_scored_output" ]; then
    mv "${USERDIR}/bashscripts/${base}_scored_output" "${IN}/"
    echo "[INFO] 输出移至 ${IN}/${base}_scored_output"
fi
ls -lh "${IN}/${base}_scored_output"* 2>/dev/null || echo "[WARN] 未找到 scored_output，核实位置"
