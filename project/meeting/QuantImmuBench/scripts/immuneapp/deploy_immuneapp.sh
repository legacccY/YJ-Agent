#!/usr/bin/env bash
# ===========================================================================
# deploy_immuneapp.sh — ImmuneApp HPC 部署脚本
# 服务: quantimmu-bench / ImmuneApp-Neo 免疫原性预测模块
#
# 用法（HPC 登录节点或交互节点 bash 下运行）:
#   bash /gpfs/work/bio/jiayu2403/quantimmu/scripts/immuneapp/deploy_immuneapp.sh
#
# 产出：
#   /gpfs/work/bio/jiayu2403/quantimmu/tools_repos/ImmuneApp/   (repo)
#   /gpfs/work/bio/jiayu2403/quantimmu/envs/immuneapp/          (conda env)
#
# 已知坑（见 NOTES.md 详细说明）：
#   1. Python 必须严格 3.7（TF1.15 不支持 3.8+）
#   2. TF1.15 pip 包名 tensorflow==1.15（CPU only，HPC 推理不需 GPU）
#   3. h5py 必须 2.10.0：3.x API 不兼容 TF1 存的 .h5 权重（group/dataset 读法变了）
#   4. protobuf 必须 3.20：4.x 移除了 TF1 依赖的 descriptor_pool.Add() API
#   5. Keras 必须 2.3.1（tf.keras 与 standalone keras 在 TF1 下行为不同，只用 standalone）
#   6. numpy 1.20 / pandas 1.3.3 / scipy 1.7.1 是 repo README 锁定版本，不升
#   7. git clone 不带 --depth 以便能读 testdata/
# ===========================================================================

set -euo pipefail

# ---------- 路径配置（全部绝对路径，HPC /gpfs）----------
QUANTIMMU_HOME="/gpfs/work/bio/jiayu2403/quantimmu"
TOOLS_REPOS="$QUANTIMMU_HOME/tools_repos"
CONDA_ENVS="$QUANTIMMU_HOME/envs"
ENV_NAME="immuneapp"
REPO_URL="https://github.com/bsml320/ImmuneApp.git"
REPO_DIR="$TOOLS_REPOS/ImmuneApp"
LOG_DIR="$QUANTIMMU_HOME/logs"

mkdir -p "$TOOLS_REPOS" "$CONDA_ENVS" "$LOG_DIR"

echo "========================================================"
echo "  ImmuneApp HPC 部署脚本"
echo "  QUANTIMMU_HOME : $QUANTIMMU_HOME"
echo "  REPO_DIR       : $REPO_DIR"
echo "  CONDA_ENV      : $CONDA_ENVS/$ENV_NAME"
echo "========================================================"

# ---------- Step 0: 加载 miniconda3 ----------
echo ""
echo "[Step 0] 加载 miniconda3/22.11.1 ..."
module load miniconda3/22.11.1
# 非交互 shell 必须 source conda.sh 才有 conda 命令
source "$(conda info --base)/etc/profile.d/conda.sh"
echo "  conda 版本: $(conda --version)"

# ---------- Step 1: git clone ImmuneApp ----------
echo ""
echo "[Step 1] git clone ImmuneApp ..."
if [ -d "$REPO_DIR/.git" ]; then
    echo "  已存在 $REPO_DIR，执行 git pull 更新 ..."
    cd "$REPO_DIR"
    git pull
else
    cd "$TOOLS_REPOS"
    git clone "$REPO_URL" ImmuneApp
    echo "  clone 完成: $REPO_DIR"
fi

# 确认 testdata 存在（权重随 repo，无需额外下载）
if [ ! -f "$REPO_DIR/testdata/test_immunogenicity.txt" ]; then
    echo "[ERROR] testdata/test_immunogenicity.txt 不存在，repo 可能 clone 不完整" >&2
    exit 1
fi
echo "  testdata/test_immunogenicity.txt 确认存在"

# 确认权重目录存在（ImmuneApp_weights/ 随 repo）
if [ ! -d "$REPO_DIR/ImmuneApp_weights" ]; then
    echo "[WARN] ImmuneApp_weights/ 目录不存在，请检查 repo 结构" >&2
    # 不 exit，继续部署，smoke 时再核验
fi

# ---------- Step 2: 创建 conda env（Python 3.7 严格）----------
echo ""
echo "[Step 2] 创建 conda env: $ENV_NAME (Python 3.7) ..."
if conda env list | grep -qE "^${ENV_NAME}\s"; then
    echo "  env $ENV_NAME 已存在，跳过创建（如需重建请先 conda env remove -n $ENV_NAME）"
else
    conda create -y \
        -p "$CONDA_ENVS/$ENV_NAME" \
        python=3.7 \
        -c defaults
    echo "  env 创建完成: $CONDA_ENVS/$ENV_NAME"
fi

# 后续 pip 统一用 conda run 避免 activate 在非交互 shell 失效
_CONDA_RUN="conda run --no-capture-output -p $CONDA_ENVS/$ENV_NAME"

# ---------- Step 3: 安装 pip 依赖（版本全部钉死）----------
echo ""
echo "[Step 3] pip 安装依赖（版本钉死）..."

# 升级 pip 自身（Python 3.7 自带 pip 较旧）
${_CONDA_RUN} pip install --upgrade "pip<23" --quiet

# 核心依赖——安装顺序重要：
#   先装 numpy/scipy（TF1 编译时会检测），再装 TF，再装 Keras，最后装 h5py/protobuf
#
# numpy 1.20：TF1.15 依赖 np.bool / np.int 等已弃用别名，1.20 仍有；1.21+ 报警告，1.24+ 删除
${_CONDA_RUN} pip install \
    "numpy==1.20" \
    "pandas==1.3.3" \
    "scipy==1.7.1" \
    --quiet

# tensorflow 1.15（CPU only，官方 PyPI 包含 Linux wheel）
# 坑：tensorflow==1.15 在 Python 3.7 有官方 wheel，3.8+ 没有
${_CONDA_RUN} pip install \
    "tensorflow==1.15" \
    --quiet

# Keras 2.3.1（standalone，不用 tf.keras；TF1 下只有 standalone Keras 可稳定用）
${_CONDA_RUN} pip install \
    "Keras==2.3.1" \
    --quiet

# h5py 2.10.0：TF1 存的权重 .h5 格式用旧 API，3.x 改 API 导致 KeyError/AttributeError
# protobuf 3.20：TF1 的 .proto 生成文件用 descriptor_pool.Add()，protobuf 4.x 删除该接口
${_CONDA_RUN} pip install \
    "h5py==2.10.0" \
    "protobuf==3.20" \
    --quiet

echo "  pip 安装完成"

# ---------- Step 4: 验证关键包版本 ----------
echo ""
echo "[Step 4] 验证关键包版本 ..."
${_CONDA_RUN} python - <<'PYEOF'
import sys
print(f"  Python      : {sys.version}")

import numpy as np
print(f"  numpy       : {np.__version__}")

import pandas as pd
print(f"  pandas      : {pd.__version__}")

import scipy
print(f"  scipy       : {scipy.__version__}")

import tensorflow as tf
print(f"  tensorflow  : {tf.__version__}")

import keras
print(f"  Keras       : {keras.__version__}")

import h5py
print(f"  h5py        : {h5py.__version__}")

import google.protobuf
print(f"  protobuf    : {google.protobuf.__version__}")

# 验证版本约束
assert tf.__version__.startswith("1.15"), f"TF 版本错误: {tf.__version__}"
assert keras.__version__ == "2.3.1", f"Keras 版本错误: {keras.__version__}"
assert h5py.__version__ == "2.10.0", f"h5py 版本错误: {h5py.__version__}"
print("  [OK] 版本约束全部满足")
PYEOF

# ---------- Step 5: 打印环境摘要 ----------
echo ""
echo "========================================================"
echo "  部署完成！"
echo "  repo       : $REPO_DIR"
echo "  conda env  : $CONDA_ENVS/$ENV_NAME"
echo "  下一步     : bash smoke_immuneapp.sh"
echo "========================================================"
