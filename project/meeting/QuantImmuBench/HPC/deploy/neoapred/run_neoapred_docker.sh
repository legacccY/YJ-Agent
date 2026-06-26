#!/usr/bin/env bash
# =============================================================================
# run_neoapred_docker.sh — NeoaPred Docker 运行封装（本地 WSL2 / Linux 主路）
# =============================================================================
# 说明：
#   本脚本适用于本地 WSL2 或 Linux 环境，直接从 Docker Hub 拉取并运行
#   panda1103/neoapred:1.0.0（3.35 GB, linux/amd64）。
#
#   HPC 环境（XJTLU gpu4090）不通外网，Docker Hub 无法拉取，
#   请改用 build_singularity_hpc.sh（本地 docker save → sftp 传 → Singularity）。
#
# 使用方法：
#   bash run_neoapred_docker.sh <input_csv> <output_dir>
#
#   <input_csv>   : neoapred_input.csv 路径 (列: ID,Allele,WT,Mut)
#   <output_dir>  : 宿主机上的输出目录（会自动创建）
#
# 环境变量（可覆盖默认值）：
#   GPUS          : docker --gpus 参数值（默认空=不传，CPU 模式）
#                   GPU 非强制：NeoaPred PepFore 主要用 OpenMM CPU 弛豫 + MSMS/APBS
#                   若需 GPU 加速，设 GPUS=all 后调用脚本
#   IMAGE         : Docker 镜像名（默认 panda1103/neoapred:1.0.0）
#   CONTAINER_IN  : 容器内输入文件路径（默认 /input.csv）
#   CONTAINER_OUT : 容器内输出目录路径（默认 /test_out）
#
# 烟测（5 行）：
#   bash run_neoapred_docker.sh scripts/out/newtools/neoapred_input_smoke.csv smoke_out/
#
# 全量：
#   bash run_neoapred_docker.sh scripts/out/newtools/neoapred_input.csv neoapred_out/
#
# 关键输出：
#   <output_dir>/Foreignness/MhcPep_foreignness.csv
#   列: ID, Allele, WT, Mut, Foreignness_Score, ...
#   Foreignness_Score > 0.5 为候选免疫原性肽（越高越强）
#
# 已知耗时提示（TODO: 精确耗时待实跑确认）：
#   OpenMM 结构弛豫为 CPU 密集型，单条肽约数分钟量级，全量 5692 条需数日。
#   建议先烟测 5-10 条确认流程，再决定是否全量提交（HPC sbatch 或本地后台）。
#
# 依赖：
#   - Docker（WSL2 已启用 Docker Desktop 或 Linux 原生 Docker）
#   - 镜像 panda1103/neoapred:1.0.0（首次运行会自动 pull，约 3.35 GB）
# =============================================================================

set -euo pipefail

# ---------------------------------------------------------------------------
# 参数解析
# ---------------------------------------------------------------------------
if [[ $# -lt 2 ]]; then
    echo "用法: bash $0 <input_csv> <output_dir>" >&2
    echo "例:   bash $0 scripts/out/newtools/neoapred_input.csv neoapred_out/" >&2
    exit 1
fi

INPUT_CSV="$1"
OUTPUT_DIR="$2"

# ---------------------------------------------------------------------------
# 配置（可通过环境变量覆盖）
# ---------------------------------------------------------------------------
IMAGE="${IMAGE:-panda1103/neoapred:1.0.0}"
CONTAINER_IN="${CONTAINER_IN:-/input.csv}"
CONTAINER_OUT="${CONTAINER_OUT:-/test_out}"

# GPU 配置（默认不传 --gpus，CPU 模式足够 PepFore 流水线）
GPUS="${GPUS:-}"

# ---------------------------------------------------------------------------
# 验证输入文件
# ---------------------------------------------------------------------------
if [[ ! -f "$INPUT_CSV" ]]; then
    echo "[ERROR] 输入文件不存在: $INPUT_CSV" >&2
    exit 1
fi

# 创建输出目录
mkdir -p "$OUTPUT_DIR"
OUTPUT_DIR="$(realpath "$OUTPUT_DIR")"
INPUT_CSV="$(realpath "$INPUT_CSV")"

echo "[INFO] 镜像       = $IMAGE"
echo "[INFO] 输入 CSV   = $INPUT_CSV"
echo "[INFO] 输出目录   = $OUTPUT_DIR"
if [[ -n "$GPUS" ]]; then
    echo "[INFO] GPU 模式   = --gpus $GPUS"
else
    echo "[INFO] GPU 模式   = CPU (GPUS 未设置)"
fi

# ---------------------------------------------------------------------------
# 1. 以 detached 模式启动容器
# ---------------------------------------------------------------------------
echo "[STEP 1] 启动容器..."

GPUS_ARGS=""
if [[ -n "$GPUS" ]]; then
    GPUS_ARGS="--gpus $GPUS"
fi

CMD=$(docker run -it -d $GPUS_ARGS "$IMAGE" /bin/bash)
echo "[INFO] 容器 ID = $CMD"

# 捕获退出信号，确保容器被清理
cleanup() {
    echo "[CLEANUP] 停止并删除容器 $CMD ..."
    docker stop "$CMD" 2>/dev/null || true
    docker rm   "$CMD" 2>/dev/null || true
    echo "[CLEANUP] 完成"
}
trap cleanup EXIT INT TERM

# ---------------------------------------------------------------------------
# 2. 拷贝输入文件到容器
# ---------------------------------------------------------------------------
echo "[STEP 2] 拷贝输入 CSV 到容器..."
docker cp "$INPUT_CSV" "$CMD:$CONTAINER_IN"
echo "[INFO] 已拷贝 $INPUT_CSV → $CMD:$CONTAINER_IN"

# ---------------------------------------------------------------------------
# 3. 在容器内激活 conda 环境并运行 NeoaPred PepFore
# ---------------------------------------------------------------------------
echo "[STEP 3] 运行 NeoaPred PepFore（此步骤耗时较长，OpenMM CPU 弛豫）..."
docker exec -it "$CMD" bash -c \
    "source ~/.bash_profile && \
     source ~/.bashrc && \
     conda activate neoa && \
     python /var/software/NeoaPred/run_NeoaPred.py \
         --input_file $CONTAINER_IN \
         --output_dir $CONTAINER_OUT \
         --mode PepFore"

echo "[INFO] NeoaPred 运行完成"

# ---------------------------------------------------------------------------
# 4. 拷贝结果回宿主机
# ---------------------------------------------------------------------------
echo "[STEP 4] 拷贝结果到宿主机..."
docker cp "$CMD:$CONTAINER_OUT" "$OUTPUT_DIR/"
echo "[INFO] 已拷贝 $CMD:$CONTAINER_OUT → $OUTPUT_DIR/"

# 显示关键输出文件
FOREIGNNESS_CSV="$OUTPUT_DIR/$(basename $CONTAINER_OUT)/Foreignness/MhcPep_foreignness.csv"
if [[ -f "$FOREIGNNESS_CSV" ]]; then
    echo "[SUCCESS] 关键输出: $FOREIGNNESS_CSV"
    echo "[INFO] 行数: $(wc -l < "$FOREIGNNESS_CSV") (含表头)"
    echo "[INFO] 列名(前5列): $(head -1 "$FOREIGNNESS_CSV" | cut -d',' -f1-5)"
else
    # 输出目录结构可能略有不同，列出实际文件
    echo "[WARN] 未在预期路径找到 MhcPep_foreignness.csv，实际产出:" >&2
    find "$OUTPUT_DIR" -name "*.csv" 2>/dev/null | head -20
fi

# cleanup 由 trap 执行（容器停止+删除）
echo "[DONE] run_neoapred_docker.sh 完成"
