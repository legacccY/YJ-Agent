#!/usr/bin/env bash
# ===========================================================================
# deploy_deephlapan.sh — deepHLApan 部署（官方数据补跑用）
# 服务: quantimmu-bench Phase0 官方数据工具补跑 / deepHLApan
# ===========================================================================
#
# ★ 部署路线决策（已调研，见 NOTES.md §1 + DEPLOY_TRACKER L296）★
#
#   路 0【推荐·零部署·已实证】本机 WSL2 docker biopharm/deephlapan:v1.1
#     - DEPLOY_TRACKER L296 记：本机 WSL2 docker 已跑通 binding+immuno 双分（SMOKE_PASS）。
#     - prior 全量 32179 肽即用此路跑出（scripts/out/deephlapan_out_*）。
#     - 官方数据仅 1462 MT + 244 WT 肽、全 9mer、纯 CPU → 几分钟即完。
#     - **无需任何新部署**：镜像在 → 直接 run_deephlapan_official.sh --mode docker。
#     - 若本机已无该镜像：docker pull biopharm/deephlapan:v1.1（主线执行，对外拉取=拍板点）。
#
#   路 A【弃用】HPC 原生 conda
#     - keras==2.0.8(2017) + tensorflow==2.7.2(2021) ABI 不兼容（issue #9 optimizer 报错）。
#     - NOTES.md §1 已判定大概率不通，不浪费时间调版本。**本脚本不走路 A。**
#
#   路 B【HPC 唯一可行·需 build】singularity sif（从同一 proven docker 镜像转）
#     - 镜像内版本已固化（跳过路 A 版本地狱）。仅当「必须在 HPC 跑」时用。
#     - 代价：WSL2 docker pull→save→gzip→scp→HPC singularity build（~3-5GB 传输）。
#
# ⚠️ 主线拍板点：docker pull / scp 上传 / singularity build 均为对外/重操作，
#    本脚本只给确切命令，由主线串行执行（agent 不执行 pull/上传/build）。
#
# ---------------------------------------------------------------------------
# 用法:
#   bash deploy_deephlapan.sh check    # 只探测本机镜像 + HPC sif 是否已就位（只读）
#   bash deploy_deephlapan.sh sif      # 打印路 B 三段确切命令（不自动执行重操作）
# ---------------------------------------------------------------------------
set -u

ACTION="${1:-check}"

ROOT=/gpfs/work/bio/jiayu2403/quantimmu
SIF_DIR="${ROOT}/sif"
DOCKER_IMG="biopharm/deephlapan:v1.1"

case "${ACTION}" in
  check)
    echo "===== [check] 本机 docker 镜像 ====="
    if command -v docker >/dev/null 2>&1; then
        docker images "${DOCKER_IMG}" 2>/dev/null || echo "  (docker 在但查镜像失败)"
        echo "  → 若上面列出 ${DOCKER_IMG} = 路 0 就绪，直接 run --mode docker"
        echo "  → 若没有 = 主线执行: docker pull ${DOCKER_IMG}（拍板点：对外拉取）"
    else
        echo "  本 shell 无 docker（可能需在 WSL2 内跑）"
    fi
    echo ""
    echo "===== [check] HPC sif（只读，需在 HPC 登录节点跑此段）====="
    echo "  预期路径: ${SIF_DIR}/deephlapan.sif"
    echo "  在 HPC 上: ls -lh ${SIF_DIR}/deephlapan.sif 2>/dev/null || echo '未 build'"
    ;;

  sif)
    echo "===== 路 B：从 proven docker 镜像 build singularity sif ====="
    echo ""
    echo "--- 段 1（WSL2，有 docker）---"
    echo "  docker pull ${DOCKER_IMG}                       # 拍板点：对外拉取"
    echo "  mkdir -p /mnt/d/tmp_deephlapan"
    echo "  docker save ${DOCKER_IMG} -o /mnt/d/tmp_deephlapan/deephlapan.tar"
    echo "  gzip -kf /mnt/d/tmp_deephlapan/deephlapan.tar     # 看 ls -lh 确认真实体积"
    echo ""
    echo "--- 段 2（本机 PowerShell，scp 传 HPC）---  # 拍板点：对外上传"
    echo "  scp D:\\tmp_deephlapan\\deephlapan.tar.gz jiayu2403@dtn.hpc.xjtlu.edu.cn:${SIF_DIR}/"
    echo ""
    echo "--- 段 3（HPC 登录节点）---  # 拍板点：build"
    echo "  mkdir -p ${SIF_DIR} && cd ${SIF_DIR}"
    echo "  gunzip -kf deephlapan.tar.gz"
    echo "  singularity build deephlapan.sif docker-archive://deephlapan.tar"
    echo "  ls -lh ${SIF_DIR}/deephlapan.sif"
    echo ""
    echo "build 完 → run_deephlapan_official.sh --mode sif"
    ;;

  *)
    echo "用法: bash deploy_deephlapan.sh [check|sif]"
    exit 1
    ;;
esac
