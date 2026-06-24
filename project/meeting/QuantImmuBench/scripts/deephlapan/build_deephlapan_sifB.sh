#!/usr/bin/env bash
# ===========================================================================
# build_deephlapan_sifB.sh — 路 B：WSL2→docker save→传 HPC→singularity build
# 服务: quantimmu-bench / deepHLApan
#
# 分三段执行（三台机器，不连续自动跑）:
#   段 1：WSL2 本地（有 docker，Docker Hub 可经代理拉）
#   段 2：本机 PowerShell（scp 传 HPC）
#   段 3：HPC 登录节点（singularity build）
#
# 使用方式:
#   手动逐段执行，每段末尾打印 DONE_<段> 再进下一段。
#   不要在 HPC 上跑段 1/2，不要在 WSL2 跑段 3。
#
# 镜像: biopharm/deephlapan:v1.1（GPL-2.0，约 3-5 GB，需主线确认真实体积）
# TODO: 镜像真实体积未知，传输前在 WSL2 先 docker images 看 SIZE
# ===========================================================================

set -euo pipefail

# ===========================================================================
# 段 1 — WSL2 本地（ubuntu，有 docker）
# 在 WSL2 bash 中运行此段
# ===========================================================================
echo "===== [B-1] WSL2: docker pull + save ====="

# 路径说明: /mnt/d/... = Windows D: 盘在 WSL2 内的挂载点
WSL_SAVE_PATH="/mnt/d/tmp_deephlapan/deephlapan.tar"
mkdir -p /mnt/d/tmp_deephlapan

# 确认 docker daemon 在跑
docker info > /dev/null 2>&1 || {
    echo "[ERROR] docker daemon 未启动，启动 Docker Desktop 后重试"
    exit 1
}

echo "[B-1-a] 拉取镜像（需代理，Docker Hub 被墙）..."
# 若 Docker Desktop 已配代理（HTTP_PROXY/HTTPS_PROXY），下行直接跑
# 若未配代理，先在 Docker Desktop Settings > Resources > Proxies 填代理地址
docker pull biopharm/deephlapan:v1.1
echo "PULL_DONE"
docker images biopharm/deephlapan:v1.1

echo "[B-1-b] 保存为 tar..."
docker save biopharm/deephlapan:v1.1 -o "$WSL_SAVE_PATH"
echo "SAVE_DONE: $(ls -lh $WSL_SAVE_PATH)"

echo "[B-1-c] gzip 压缩（减少传输体积）..."
gzip -k "$WSL_SAVE_PATH"
echo "GZIP_DONE: $(ls -lh ${WSL_SAVE_PATH}.gz)"

# 段 1 完成后记下压缩包路径，供段 2 用
echo "DONE_B1"
echo "  本地压缩包: D:\\tmp_deephlapan\\deephlapan.tar.gz"
echo "  下一步: 在 PowerShell 运行段 2（scp 传 HPC）"

# 提前退出（段 2/3 不在 WSL2 跑）
exit 0

# ===========================================================================
# 段 2 — 本机 PowerShell（scp 传 HPC）
# 下面是 PowerShell 命令，手动复制到 PowerShell 窗口执行
# ===========================================================================
# --- 粘贴到 PowerShell 执行（不在 bash 里跑）---
#
# $HPC_USER = "jiayu2403"
# $HPC_HOST = "dtn.hpc.xjtlu.edu.cn"
# $LOCAL_FILE = "D:\tmp_deephlapan\deephlapan.tar.gz"
# $REMOTE_DIR = "/gpfs/work/bio/jiayu2403/quantimmu/sif"
#
# Write-Host "[B-2] scp 传输（镜像较大，预计几分钟）..."
# scp "$LOCAL_FILE" "${HPC_USER}@${HPC_HOST}:${REMOTE_DIR}/"
# Write-Host "DONE_B2"
# Write-Host "  HPC 目标: ${REMOTE_DIR}/deephlapan.tar.gz"
# Write-Host "  下一步: SSH 登录 HPC，运行段 3"
#
# ===========================================================================

# ===========================================================================
# 段 3 — HPC 登录节点（singularity build）
# SSH 登录后在 bash 中运行此段
# ===========================================================================
echo "===== [B-3] HPC: gunzip + singularity build ====="

ROOT=/gpfs/work/bio/jiayu2403/quantimmu
SIF_DIR="$ROOT/sif"
mkdir -p "$SIF_DIR"
cd "$SIF_DIR"

# 解压（-k 保留原 gz，-f 覆盖已有 tar）
if [ -f deephlapan.tar.gz ]; then
    echo "[B-3-a] 解压 deephlapan.tar.gz..."
    gunzip -kf deephlapan.tar.gz
    echo "GUNZIP_DONE: $(ls -lh deephlapan.tar)"
else
    echo "[ERROR] deephlapan.tar.gz 不存在，请先运行段 2 传文件"
    exit 1
fi

# singularity build（无需 root，用 --fakeroot 或普通用户均可）
echo "[B-3-b] singularity build deephlapan.sif..."
singularity build deephlapan.sif docker-archive://deephlapan.tar
echo "SINGULARITY_BUILD_DONE"
ls -lh deephlapan.sif

# 可选：删除中间 tar 节省空间（gz 留着备用）
# rm -f deephlapan.tar

echo ""
echo "===== [路 B 部署小结] ====="
echo "  sif 位置: $SIF_DIR/deephlapan.sif"
echo "  下一步: 运行 smoke_deephlapan.sh --sif 做全链验证"
echo "DONE_B3"
