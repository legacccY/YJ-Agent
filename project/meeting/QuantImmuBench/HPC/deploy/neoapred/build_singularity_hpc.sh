#!/usr/bin/env bash
# =============================================================================
# build_singularity_hpc.sh — NeoaPred HPC Singularity 镜像构建模板
# =============================================================================
# 用途：
#   XJTLU gpu4090 HPC 集群不通 Docker Hub，需在本地将 Docker 镜像导出为 tar，
#   sftp 传到 HPC，再用 Singularity 转换为 .sif 文件后运行。
#
# 流程三步（命令模板，按需手动执行）：
#   本地 Step 1: docker save 导出镜像
#   本地 Step 2: sftp 上传到 HPC
#   HPC  Step 3: singularity build 转换
#
# ⚠️  已知风险 / TODO：
#   1. pTuneos 同坑警告：
#      pTuneos Docker 镜像中程序位于 /root/ 目录；HPC Singularity 以非 root
#      用户运行时，/root/ 访问受限，导致程序找不到。NeoaPred 程序位于
#      /var/software/NeoaPred/，理论上无此问题，但 conda activate 路径需验。
#      参考 04_LOG pTuneos/HLAthena 部署经验，实跑前先 singularity shell 进容器
#      确认路径可访问。
#
#   2. 文件大小：
#      镜像 3.35 GB，tar.gz 约 3 GB，上传 + build 耗时较长（HPC build 约 15-30 min）。
#
#   3. Singularity conda activate 行为：
#      Singularity 中 conda activate 需显式 source conda init 脚本，
#      TODO: 需测试 `source ~/.bash_profile && conda activate neoa` 在 Singularity
#      exec 中是否有效；若不行，改用 `conda run -n neoa python ...` 替代。
#
#   4. MSMS/APBS/PDB2PQR 路径：
#      这些工具均镜像内置（/var/software/ 下），Singularity 应可访问，
#      TODO: 实跑验证 MSMS binary 的执行权限（需 +x）。
#
# 本脚本不直接执行（set -n 干运行），只展示命令模板。
# 去掉 set -n 后按步骤手动执行各段命令。
# =============================================================================

# set -n   # 取消注释 = 干运行（只解析不执行），注释掉则真执行

# ===========================================================================
# 配置（按实际修改）
# ===========================================================================
IMAGE_NAME="panda1103/neoapred:1.0.0"
TARBALL_LOCAL="neoapred.tar.gz"            # 本地保存路径
HPC_USER="jiayu2403"                       # HPC 用户名
HPC_HOST="gpu4090.xjtlu.edu.cn"            # HPC 登录节点
HPC_WORK="/gpfs/work/bio/jiayu2403/quantimmu/sif"   # HPC 目标目录
SIF_NAME="neoapred.sif"                    # 转换后 sif 文件名

# ===========================================================================
# 本地 Step 1：导出 Docker 镜像为 tar.gz
# ===========================================================================
echo "=== [本地 Step 1] docker save + gzip ==="
echo "# 预计生成约 3 GB 文件，根据网速需 5-15 分钟"
echo ""
echo "命令："
echo "  docker save ${IMAGE_NAME} | gzip > ${TARBALL_LOCAL}"
echo ""
# 实际执行时取消下面注释：
# docker save "${IMAGE_NAME}" | gzip > "${TARBALL_LOCAL}"
# echo "导出完成: $(ls -lh ${TARBALL_LOCAL})"

# ===========================================================================
# 本地 Step 2：sftp 上传到 HPC
# ===========================================================================
echo "=== [本地 Step 2] sftp 上传 ==="
echo "# 约 3 GB，校园网约 10-30 分钟"
echo ""
echo "方法 A (sftp 交互)："
echo "  sftp ${HPC_USER}@${HPC_HOST}"
echo "  sftp> mkdir -p ${HPC_WORK}"
echo "  sftp> put ${TARBALL_LOCAL} ${HPC_WORK}/${TARBALL_LOCAL}"
echo ""
echo "方法 B (scp 一行)："
echo "  scp ${TARBALL_LOCAL} ${HPC_USER}@${HPC_HOST}:${HPC_WORK}/"
echo ""
echo "方法 C (rsync，断点续传)："
echo "  rsync -avz --progress ${TARBALL_LOCAL} ${HPC_USER}@${HPC_HOST}:${HPC_WORK}/"
echo ""

# ===========================================================================
# HPC Step 3：Singularity build（登录 HPC 后执行）
# ===========================================================================
echo "=== [HPC Step 3] singularity build（在 HPC 登录节点或 sbatch 中执行）==="
echo ""
echo "# 先 ssh 进 HPC："
echo "  ssh ${HPC_USER}@${HPC_HOST}"
echo ""
echo "# 在 HPC 上解压并 build："
cat <<'HPC_CMDS'
# -- 以下在 HPC 上执行 --

HPC_WORK=/gpfs/work/bio/jiayu2403/quantimmu/sif
cd ${HPC_WORK}

# 解压（singularity build 支持直接读 .tar.gz，但 .tar 更稳定）
gunzip -kf neoapred.tar.gz
# → 产出 neoapred.tar

# Singularity build（需要 singularity 模块，约 15-30 min）
module load singularity 2>/dev/null || true
singularity build neoapred.sif docker-archive://neoapred.tar
echo "BUILD_DONE: $(ls -lh neoapred.sif)"

# -- build 完成后验证（进容器检查路径）--
singularity shell neoapred.sif
# 在容器内运行：
#   ls /var/software/NeoaPred/
#   ls /root/anaconda3/envs/neoa/  # 或 /opt/conda/envs/neoa/
#   conda activate neoa && python --version
# 按 Ctrl+D 退出

HPC_CMDS

# ===========================================================================
# HPC Step 4：Singularity exec 运行 NeoaPred
# ===========================================================================
echo ""
echo "=== [HPC Step 4] Singularity exec 运行（验证后使用）==="
cat <<'RUN_CMDS'
# -- 以下在 HPC 上执行（确认路径可访问后）--

HPC_WORK=/gpfs/work/bio/jiayu2403/quantimmu
SIF=${HPC_WORK}/sif/neoapred.sif
INPUT=${HPC_WORK}/inputs/neoapred_input.csv    # 先上传 prep_neoapred_input.py 产出的 CSV
OUTPUT=${HPC_WORK}/outputs/neoapred_out

mkdir -p ${OUTPUT}

# TODO: 若 conda activate 在 Singularity 中不可用，改用 conda run：
#   singularity exec ${SIF} bash -c \
#       "conda run -n neoa python /var/software/NeoaPred/run_NeoaPred.py \
#        --input_file /input.csv --output_dir /test_out --mode PepFore"

singularity exec \
    --bind ${INPUT}:/input.csv \
    --bind ${OUTPUT}:/test_out \
    ${SIF} bash -c \
    "source ~/.bash_profile && \
     source ~/.bashrc && \
     conda activate neoa && \
     python /var/software/NeoaPred/run_NeoaPred.py \
         --input_file /input.csv \
         --output_dir /test_out \
         --mode PepFore"

echo "输出: ${OUTPUT}/Foreignness/MhcPep_foreignness.csv"
RUN_CMDS

echo ""
echo "[NOTE] 以上全部为命令模板，实跑前请确认 SIF 路径、conda env 名称、HPC 模块名。"
echo "       参考 04_LOG Entry pTuneos/HLAthena 章节了解 /root 访问受限解决方案。"
