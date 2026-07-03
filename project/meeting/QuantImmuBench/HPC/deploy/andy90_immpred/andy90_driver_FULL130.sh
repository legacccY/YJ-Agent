#!/usr/bin/env bash
# =============================================================================
# andy90_driver_FULL130.sh — QuantImmuBench §工具部署  andy90 全量(FULL130)覆盖驱动
# 服务项目：quantimmu-bench §工具部署 lever=免疫原补位（覆盖修复战役）
#
# 【为什么有这个脚本】
#   旧 driver andy90_driver.sh 为旧 43 肽输入硬编码了 7 个 SLURM sbatch 批次 +
#   编号 HLA manifest。换成全量输入 FULL130（3283 对 (肽,HLA)）后，HLA 数不再是
#   旧编号，硬编码批次就错位/漏跑。本版**彻底去掉硬编码批次索引**：
#     1) 用 prep_input.py 按 FULL130 输入动态建全量 per-HLA fasta + manifest；
#     2) 让 run_andy90.py 按 manifest **实际行数**逐 HLA 循环（0 硬编码索引）；
#     3) 逐 HLA 输出 merge 成 andy90_raw_FULL130.csv。
#
# 【为什么串行单循环而非 SLURM 并发批】
#   官方 src/predict_amp.R 每个 HLA 跑都覆写 repo 内共享的 src/output.out
#   （见 NOTES.md 已知坑 #4）。若并发多批共用同一 repo clone → output.out 竞态、
#   数值污染。故用一次 nohup 串行循环（run_andy90.py 内部逐 HLA 串行，无竞态），
#   跑在登录节点 / cpudebug 即可。netMHCpan 是主成本，65 个 HLA 串行可接受；
#   如需并发提速须给每批各自 clone repo（本脚本不做，避免竞态）。
#
# 【只改批次调度层，不碰工具本体】
#   prep_input.py / run_andy90.py / run_andy90.R / parse_output.py 一字未改，
#   本脚本只负责：建全量输入 → 动态循环调度 → merge → 落 raw。
#
# -----------------------------------------------------------------------------
# 主线怎么跑（HPC）：
#   0) 本仓 HPC/deploy/andy90_immpred/ 传到 HPC 对应目录（含本脚本 + FULL130.csv）
#   1) 去 CRLF：  sed -i 's/\r$//' andy90_driver_FULL130.sh
#   2) 后台起：   setsid bash andy90_driver_FULL130.sh > andy90_FULL130.log 2>&1 &
#   3) 看进度：   tail -f andy90_FULL130.log
#   产物：${ROOT}/HPC/deploy/andy90_immpred/andy90_raw_FULL130.csv
#         （列 HLA,peptide,amplitude,immunogenic）
#
# 可用环境变量覆盖（不改脚本）：
#   REPO=<immunogenicity_predictor clone 路径>
#   NETMHC=<netMHCpan 二进制路径>
#   RSCRIPT=<Rscript 路径>
#   PY=<python 路径>
#   SMOKE=<N>   仅跑前 N 个 HLA 做烟测（0=全量，默认 0）
# =============================================================================
set -euo pipefail

# ---------- HPC 绝对路径（真源） ----------
ROOT="${ROOT:-/gpfs/work/bio/jiayu2403/quantimmu}"
ANDY_DIR="${ROOT}/HPC/deploy/andy90_immpred"

# 工具本体（不改）
PY="${PY:-${ROOT}/envs/andy90_r/bin/python}"
RSCRIPT="${RSCRIPT:-Rscript}"
REPO="${REPO:-${ROOT}/ext_tools/immunogenicity_predictor}"
NETMHC="${NETMHC:-${ROOT}/ext_tools/netMHCpan-4.1/netMHCpan}"

# 输入 / 输出
UNIQ_CSV="${ANDY_DIR}/andy90_input_FULL130.csv"       # 3283 对 (肽,HLA)
INPUTS_DIR="${ANDY_DIR}/andy90_inputs_full130"        # 本轮独立目录，不覆盖旧 andy90_inputs
MANIFEST="${INPUTS_DIR}/andy90_manifest.csv"
RAW_OUT="${ANDY_DIR}/andy90_raw_FULL130.csv"

SMOKE="${SMOKE:-0}"

# ---------- 前置检查 ----------
echo "[driver] ===== andy90 FULL130 驱动 ====="
echo "[driver] ROOT       = ${ROOT}"
echo "[driver] PY         = ${PY}"
echo "[driver] RSCRIPT    = ${RSCRIPT}"
echo "[driver] REPO       = ${REPO}"
echo "[driver] NETMHC     = ${NETMHC}"
echo "[driver] UNIQ_CSV   = ${UNIQ_CSV}"
echo "[driver] INPUTS_DIR = ${INPUTS_DIR}"
echo "[driver] RAW_OUT    = ${RAW_OUT}"
echo "[driver] SMOKE      = ${SMOKE}"
echo "[driver] 开始时间   = $(date '+%Y-%m-%d %H:%M:%S')"

for f in "${UNIQ_CSV}" "${ANDY_DIR}/prep_input.py" "${ANDY_DIR}/run_andy90.py" "${ANDY_DIR}/run_andy90.R"; do
  [ -e "${f}" ] || { echo "[driver] ERROR: 缺文件 ${f}" >&2; exit 1; }
done
[ -x "${PY}" ] || command -v "${PY}" >/dev/null 2>&1 || { echo "[driver] ERROR: python 不可用: ${PY}" >&2; exit 1; }
[ -e "${REPO}" ]   || { echo "[driver] ERROR: repo 不存在: ${REPO}（先 git clone immunogenicity_predictor）" >&2; exit 1; }
[ -e "${NETMHC}" ] || { echo "[driver] ERROR: netMHCpan 不存在: ${NETMHC}" >&2; exit 1; }

# ---------- Step 1: 动态建全量 manifest + per-HLA fasta ----------
echo ""
echo "[driver] --- Step 1: prep_input.py（按 FULL130 动态建 fasta+manifest）---"
"${PY}" "${ANDY_DIR}/prep_input.py" \
  --uniq-csv "${UNIQ_CSV}" \
  --inputs-dir "${INPUTS_DIR}"

[ -f "${MANIFEST}" ] || { echo "[driver] ERROR: manifest 未生成: ${MANIFEST}" >&2; exit 1; }

# 动态读 manifest 行数（不硬编码批次索引）——减表头 1 行 = HLA 数
N_HLA=$(( $(wc -l < "${MANIFEST}") - 1 ))
echo "[driver] manifest 动态 HLA 数 = ${N_HLA}（旧 driver 的硬编码 7 批已作废）"
[ "${N_HLA}" -ge 1 ] || { echo "[driver] ERROR: manifest 无 HLA 行" >&2; exit 1; }

# ---------- Step 2: 逐 HLA 串行循环跑（run_andy90.py 内部按 manifest 行数动态循环）----------
echo ""
echo "[driver] --- Step 2: run_andy90.py（逐 HLA 串行，共 ${N_HLA} 个 HLA）---"
SMOKE_ARG=()
if [ "${SMOKE}" -gt 0 ]; then
  echo "[driver] [SMOKE] 仅跑前 ${SMOKE} 个 HLA"
  SMOKE_ARG=(--smoke "${SMOKE}")
fi

"${PY}" "${ANDY_DIR}/run_andy90.py" \
  --repo "${REPO}" \
  --netmhcpan "${NETMHC}" \
  --rscript "${RSCRIPT}" \
  --inputs-dir "${INPUTS_DIR}" \
  --out "${RAW_OUT}" \
  "${SMOKE_ARG[@]}"

# ---------- 收尾 ----------
[ -f "${RAW_OUT}" ] || { echo "[driver] ERROR: raw 未生成: ${RAW_OUT}" >&2; exit 1; }
N_RAW=$(( $(wc -l < "${RAW_OUT}") - 1 ))
echo ""
echo "[driver] ===== 完成 ====="
echo "[driver] raw 行数     = ${N_RAW}"
echo "[driver] raw 输出     = ${RAW_OUT}"
echo "[driver] 结束时间     = $(date '+%Y-%m-%d %H:%M:%S')"
echo "[driver] 下一步（回贴 universe，主线跑）："
echo "         ${PY} ${ANDY_DIR}/parse_output.py --raw ${RAW_OUT}"
