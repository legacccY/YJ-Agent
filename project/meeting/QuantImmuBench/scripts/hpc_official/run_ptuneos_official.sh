#!/usr/bin/env bash
# =============================================================================
# run_ptuneos_official.sh — pTuneos Pre&RecNeo on NEW official backbone
# 服务项目: quantimmu-bench  lever: pTuneos 官方数据补跑（免疫原 model_pro）
# =============================================================================
# ⚠️⚠️ 执行路径 = 本地 WSL docker（sudo），**不是 HPC singularity**。原因见下。
# 本脚本由主线在 WSL 内串行跑（含容器子进程），coder/agent 不跑。
# -----------------------------------------------------------------------------
# 【为什么不走 HPC singularity ptuneos.sif —— 已实测确认的硬阻塞，2026-06-30】
#   1. pTuneos 全部资产（train_model/RF/cf_hy/iedb.fasta + netMHCpan-4.0）都在
#      镜像 /root/ 下（mode 700）。HPC 上以普通用户 jiayu2403 跑
#      `singularity exec ptuneos.sif ls /root/pTuneos` → **Permission denied**。
#   2. `singularity exec --fakeroot` 不可用：
#      FATAL: could not use fakeroot: no mapping entry found in /etc/subuid。
#      → 无法在 HPC 上以 root 身份读 /root 资产，sif 路径对普通用户死路。
#   3. HPC 上 **没有 blastdb**（find 全空）；Self_sequence_similarity 的 homolog
#      项必需 Ensembl peptide blastdb（110048 序列），缺它该项退化 → 偏离 r=1.0 复现。
#   本地 WSL `sudo docker run` 以 root 跑 → /root 可读 + blastdb 在本地 → 复现 r=1.0
#   成立（与 phaseB run_ptuneos_101102.py 同口径，那次对账官方 40 肽 model_pro r=1.0）。
#   若坚持要 HPC：需 (a) 重打 sif 让 /root 资产 world-readable，且 (b) 上传 blastdb
#   到 HPC（对外传输=拍板点）。默认不走，走本地 docker。
# -----------------------------------------------------------------------------
# 【输入】scripts/out_official/ptuneos/ptuneos_input_unique.tsv
#   由 scripts/prepare_inputs_official.py::export_ptuneos 从 master_backbone_official.csv
#   生成，列 = unique_idx, MT_pep, WT_pep, HLA_type（1462 unique 三元组）。
#   ★ 实测覆盖：1462 unique 中仅 **244** 行有非空 WT_pep（其余 1517 为 frameshift/
#     INDEL/passenger，frozen backbone 无 WT 配对）。pTuneos Pre&RecNeo 的 model_pro
#     需 MT-vs-WT 差异特征（Self_similarity / WT_Binding_EL）→ **无 WT 的行不可打分**，
#     parse 阶段诚实留 NaN。预期官方覆盖 ≈ 244/1761（13.9%），非 bug，是工具适用面。
# 【输出】容器产 ptuneos_official_output.tsv（含 model_pro 列），供 parse 回贴 bb_idx。
# -----------------------------------------------------------------------------
# 用法（WSL 内 sudo 跑）:
#   sudo bash run_ptuneos_official.sh                 # 全量（1462 unique）
#   sudo bash run_ptuneos_official.sh --smoke 5       # 烟测前 5 行验通容器/blastdb
# 可用环境变量覆盖默认路径：REPO / BLASTDB_HOST / IMAGE / NPROC
# =============================================================================
set -u

# ---------------------------------------------------------------------------
# 路径配置（WSL 原生路径最稳；REPO 默认指向 /mnt/d 下仓库）
# ---------------------------------------------------------------------------
REPO="${REPO:-/mnt/d/YJ-Agent/project/meeting/QuantImmuBench}"
WRAPPER="${REPO}/scripts/ptuneos/ptuneos_pre_recneo.py"   # 容器内 Py2.7 wrapper
INPUT="${REPO}/scripts/out_official/ptuneos/ptuneos_input_unique.tsv"
WORKDIR="${REPO}/scripts/out_official/ptuneos/work_official"  # 挂为容器 /work
OUT_TSV_NAME="ptuneos_official_output.tsv"

# blastdb 父目录（含 peptide.{phr,pin,psq}），挂为容器 /blastdb（见 phaseB 复盘）
BLASTDB_HOST="${BLASTDB_HOST:-/root/quantimmu/ptuneos_run/database/Protein/peptide_database}"
IMAGE="${IMAGE:-bm2lab/ptuneos:v2.1}"
NPROC="${NPROC:-8}"

SMOKE=0
if [ "${1:-}" = "--smoke" ]; then SMOKE="${2:-5}"; fi

# ---------------------------------------------------------------------------
# 前置检查
# ---------------------------------------------------------------------------
[ -f "${WRAPPER}" ] || { echo "[FATAL] 缺 wrapper: ${WRAPPER}" >&2; exit 1; }
[ -f "${INPUT}" ]   || { echo "[FATAL] 缺输入: ${INPUT}" >&2; exit 1; }
if [ ! -e "${BLASTDB_HOST}/peptide.pin" ]; then
    # TODO: blastdb 不在默认路径。phaseB 实测路径 = /root/quantimmu/ptuneos_run/database/
    #       Protein/peptide_database（Ensembl release-97 human.pep.all, 110048 seq）。
    #       若本机 WSL 无此 blastdb → 须先重建/定位，否则 homolog 项全默认偏离 r=1.0。
    echo "[WARN] 未在 ${BLASTDB_HOST} 找到 peptide.pin —— Self_similarity homolog 项将退化。" >&2
    echo "       请确认 blastdb 路径（export BLASTDB_HOST=...）再跑。" >&2
fi

mkdir -p "${WORKDIR}"
cp -f "${WRAPPER}" "${WORKDIR}/ptuneos_pre_recneo.py"

# 输入：全量直接拷；smoke 截前 N 行（保留表头）
if [ "${SMOKE}" -gt 0 ]; then
    IN_NAME="ptuneos_input_smoke.tsv"
    OUT_TSV_NAME="ptuneos_official_output_smoke.tsv"
    head -1 "${INPUT}" > "${WORKDIR}/${IN_NAME}"
    tail -n +2 "${INPUT}" | head -n "${SMOKE}" >> "${WORKDIR}/${IN_NAME}"
    echo "[smoke] 截前 ${SMOKE} 行 → ${WORKDIR}/${IN_NAME}"
else
    IN_NAME="ptuneos_input_unique.tsv"
    cp -f "${INPUT}" "${WORKDIR}/${IN_NAME}"
fi

echo "[INFO] REPO         = ${REPO}"
echo "[INFO] INPUT        = ${WORKDIR}/${IN_NAME}"
echo "[INFO] BLASTDB_HOST = ${BLASTDB_HOST}"
echo "[INFO] IMAGE        = ${IMAGE}  | NPROC=${NPROC}"
echo "[INFO] OUTPUT       = ${WORKDIR}/${OUT_TSV_NAME}"
echo "[INFO] -----------------------------------------------------------------"

# ---------------------------------------------------------------------------
# docker 起容器跑 wrapper
#   wrapper 输入列须为 MT_pep/WT_pep/HLA_type；本输入首列是 unique_idx，wrapper 用
#   read_csv 按列名取 ['MT_pep','WT_pep','HLA_type']，多余 unique_idx 列被忽略 → OK。
# ---------------------------------------------------------------------------
INNER="export PATH=/root/software/netMHCpan-4.0:\$PATH && \
python /work/ptuneos_pre_recneo.py \
--input /work/${IN_NAME} \
--output /work/${OUT_TSV_NAME} \
--models /root/pTuneos/train_model \
--blastdb /blastdb/peptide \
--nproc ${NPROC}"

echo "[run] docker run --rm -v ${WORKDIR}:/work -v ${BLASTDB_HOST}:/blastdb:ro ${IMAGE} bash -c '<inner>'"
echo "[run] inner: ${INNER}"

docker run --rm \
    -v "${WORKDIR}:/work" \
    -v "${BLASTDB_HOST}:/blastdb:ro" \
    "${IMAGE}" \
    bash -c "${INNER}"
rc=$?

if [ "${rc}" -ne 0 ]; then
    echo "[FATAL] 容器退出码 ${rc}（核挂载/blastdb/镜像）" >&2
    exit "${rc}"
fi
if [ ! -f "${WORKDIR}/${OUT_TSV_NAME}" ]; then
    echo "[FATAL] 容器未产出 ${WORKDIR}/${OUT_TSV_NAME}" >&2
    exit 1
fi

n_out=$(($(wc -l < "${WORKDIR}/${OUT_TSV_NAME}") - 1))
echo "[DONE] 容器输出 ${n_out} 行 → ${WORKDIR}/${OUT_TSV_NAME}"
echo "[DONE] 下一步本地: python scripts/hpc_official/parse_ptuneos_official.py \\"
echo "         --ptuneos-out ${WORKDIR}/${OUT_TSV_NAME} \\"
echo "         --backbone scripts/out_official/master_backbone_official.csv \\"
echo "         --out-dir scripts/out_official"
