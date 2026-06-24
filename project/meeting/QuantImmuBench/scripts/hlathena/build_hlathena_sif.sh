#!/usr/bin/env bash
# ===========================================================================
# build_hlathena_sif.sh
# 服务: quantimmu-bench  lever: HLAthena presentation proxy baseline
#
# ⚠️  HLAthena 预测 MHC-I 提呈（presentation）不是免疫原性。
#     进 benchmark 只作 presentation baseline proxy，不与免疫原性工具并列。
#
# 流程概述（两段，主机+HPC 分开跑）:
#   [本机 WSL2]  拉 Docker 镜像 → docker save → SCP 传 HPC
#   [HPC]        singularity build docker-archive -> hlathena.sif
#
# 前提:
#   本机 WSL2: docker daemon 运行中（Docker Desktop + 代理已通 Docker Hub）
#   HPC: Singularity 3.11.3；登录节点联网；/gpfs 有足量空间（~3GB）
#   SSH 凭证: jiayu2403@dtn.hpc.xjtlu.edu.cn（端口 22）
#
# 用法:
#   bash build_hlathena_sif.sh [--dry-run]
#   --dry-run: 只打印命令不执行（用于审阅）
#
# 产物:
#   本机 WSL2:  ~/quantimmu/docker_archives/hlathena-external.tar  (~909MB)
#   HPC:        /gpfs/work/bio/jiayu2403/quantimmu/sif/hlathena.sif  (~600-900MB，Singularity压缩后)
# ===========================================================================

set -euo pipefail

# ---------- 参数 ----------
DRY_RUN=0
if [[ "${1:-}" == "--dry-run" ]]; then
    DRY_RUN=1
    echo "[DRY-RUN] 只打印命令，不执行"
fi

run() {
    echo ">> $*"
    if [[ $DRY_RUN -eq 0 ]]; then
        "$@"
    fi
}

# ---------- 路径配置 ----------
# 本机 WSL2 侧
DOCKER_ARCHIVE_DIR="$HOME/quantimmu/docker_archives"
ARCHIVE_FILE="$DOCKER_ARCHIVE_DIR/hlathena-external.tar"
DOCKER_IMAGE="ssarkizova/hlathena-external:dev"

# HPC 侧
HPC_USER="jiayu2403"
HPC_HOST="dtn.hpc.xjtlu.edu.cn"
HPC_SIF_DIR="/gpfs/work/bio/jiayu2403/quantimmu/sif"
HPC_ARCHIVE_REMOTE="/gpfs/work/bio/jiayu2403/quantimmu/sif/hlathena-external.tar"
HPC_SIF_PATH="/gpfs/work/bio/jiayu2403/quantimmu/sif/hlathena.sif"

echo "================================================================"
echo " HLAthena Docker -> Singularity 转换脚本"
echo " 镜像: $DOCKER_IMAGE"
echo " 目标 SIF: $HPC_SIF_PATH"
echo "================================================================"
echo ""

# ===========================================================================
# 阶段 A: 本机 WSL2 — 拉镜像 + 存档
# ===========================================================================
echo "===== [A] 本机 WSL2: docker pull + save ====="

# A-1: 建存档目录
run mkdir -p "$DOCKER_ARCHIVE_DIR"

# A-2: 拉镜像（需 Docker Hub 可访问；本机走代理时确认代理已开）
#   镜像约 909MB，拉取时间视带宽约 5-15 分钟
echo "[A-2] docker pull $DOCKER_IMAGE"
run docker pull "$DOCKER_IMAGE"

# A-3: 检查镜像是否拉到
echo "[A-3] 确认镜像存在..."
if [[ $DRY_RUN -eq 0 ]]; then
    docker image inspect "$DOCKER_IMAGE" > /dev/null 2>&1 || {
        echo "[ERROR] 镜像 $DOCKER_IMAGE 不存在，pull 可能失败，请手动检查"
        exit 1
    }
    echo "[A-3] OK: 镜像已在本地"
fi

# A-4: 导出为 tar（时间视 I/O 约 2-5 分钟）
echo "[A-4] docker save -> $ARCHIVE_FILE"
run docker save -o "$ARCHIVE_FILE" "$DOCKER_IMAGE"

# A-5: 显示文件大小
if [[ $DRY_RUN -eq 0 ]]; then
    TAR_SIZE=$(du -sh "$ARCHIVE_FILE" | cut -f1)
    echo "[A-5] 存档大小: $TAR_SIZE  路径: $ARCHIVE_FILE"
else
    echo "[dry-run] 跳过 du"
fi

# ===========================================================================
# 阶段 B: 传输到 HPC（SCP）
# ===========================================================================
echo ""
echo "===== [B] SCP 传 HPC: $ARCHIVE_FILE -> $HPC_ARCHIVE_REMOTE ====="
echo "  ⚠️  本步骤上传新文件到 HPC，按约定主线拍板确认后执行"
echo "  若使用 --dry-run，此命令只打印不跑"
echo ""

# B-1: 建 HPC 目录（如已存在 ssh 会报 File exists，忽略即可）
echo "[B-1] 在 HPC 建 sif 目录: $HPC_SIF_DIR"
run ssh "${HPC_USER}@${HPC_HOST}" "mkdir -p $HPC_SIF_DIR"

# B-2: SCP 传 tar（~909MB，视带宽约 5-20 分钟，HPC 内网较快）
echo "[B-2] scp 传输中... (大文件，耐心等)"
run scp "$ARCHIVE_FILE" "${HPC_USER}@${HPC_HOST}:${HPC_ARCHIVE_REMOTE}"

echo "[B-2] SCP 完成"

# ===========================================================================
# 阶段 C: HPC 侧 — singularity build（登录 HPC 后手动跑，或 ssh 一行）
# ===========================================================================
echo ""
echo "===== [C] HPC: singularity build ====="
echo "  以下命令在 HPC 登录节点执行（ssh 后粘贴，或用下面的 run 方式）"
echo ""

HPC_BUILD_CMD="singularity build $HPC_SIF_PATH docker-archive://$HPC_ARCHIVE_REMOTE"

echo "  手动执行方式（推荐，方便看进度）:"
echo "    ssh ${HPC_USER}@${HPC_HOST}"
echo "    $HPC_BUILD_CMD"
echo ""

# C-1: 通过 ssh -t 在远端跑 singularity build（需终端 TTY，交互式 ssh 更稳）
#   如需无交互跑，去掉 -t 改 ssh ... "singularity build ..."
#   时间约 5-15 分钟（900MB 解包+重打）
echo "[C-1] 通过 ssh -t 远端 singularity build"
run ssh -t "${HPC_USER}@${HPC_HOST}" "$HPC_BUILD_CMD"

# ===========================================================================
# 阶段 D: 验证 SIF
# ===========================================================================
echo ""
echo "===== [D] 验证 SIF ====="

HPC_VERIFY_CMD="singularity inspect $HPC_SIF_PATH && echo '[D] SIF inspect OK'"
echo "[D-1] 远端 singularity inspect"
run ssh "${HPC_USER}@${HPC_HOST}" "$HPC_VERIFY_CMD"

# ===========================================================================
# 完成
# ===========================================================================
echo ""
echo "================================================================"
echo " BUILD 完成 (dry-run=$DRY_RUN)"
echo " SIF 路径 (HPC): $HPC_SIF_PATH"
echo " 下一步: 运行 smoke_hlathena.sh 做最小烟测"
echo ""
echo " ⚠️  镜像再分发提醒:"
echo "   ssarkizova/hlathena-external 为 research purposes only。"
echo "   转存 HPC 供研究内部测试，不向第三方发布。"
echo "   若论文引用数字，需核实 Broad Institute 再分发政策（见 NOTES.md）。"
echo "================================================================"
