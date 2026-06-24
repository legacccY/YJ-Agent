#!/usr/bin/env bash
# ===========================================================================
# MHLAPre 部署脚本 — git clone + conda env 建立
# 服务：QuantImmuBench（袁老师免疫原性 benchmark），Wave 3 末位
#
# !! 前置阻塞（先解决再跑本脚本）：
#    1. 预训练权重缺失 → 邮件 23B903048@stu.hit.edu.cn 索取
#    2. CUDA 版本待确认 → 先 `nvidia-smi` 看驱动版本，再选下方 pip 命令
#    3. 无 LICENSE → 邮件作者确认学术用途许可
#    详见 NOTES.md
#
# 用法（HPC GPU 节点上，bash 环境）：
#   bash deploy_mhlapre.sh
#
# 产出：
#   $MHLAPRE_HOME/   — git clone 结果（MHLAPre repo）
#   conda env: mhlapre  — Python 3.9.13 + torch + rdkit + sklearn
# ===========================================================================

set -euo pipefail

# ---------- 路径配置 ----------
QUANTIMMU_ROOT="/gpfs/work/bio/jiayu2403/quantimmu"
TOOLS_REPOS="$QUANTIMMU_ROOT/tools_repos"
MHLAPRE_HOME="$TOOLS_REPOS/MHLAPre"
ENVS_DIR="$QUANTIMMU_ROOT/envs"
ENV_NAME="mhlapre"

echo "===== MHLAPre 部署开始 ====="
echo "目标目录: $MHLAPRE_HOME"
echo "Conda env: $ENVS_DIR/$ENV_NAME"

# ---------- conda 初始化 ----------
# HPC 上 conda 路径可能不同，按实际调整
# 常见：/root/miniconda3 / $HOME/miniconda3 / /opt/conda
if [ -f "$HOME/miniconda3/etc/profile.d/conda.sh" ]; then
    source "$HOME/miniconda3/etc/profile.d/conda.sh"
elif [ -f "/root/miniconda3/etc/profile.d/conda.sh" ]; then
    source "/root/miniconda3/etc/profile.d/conda.sh"
else
    echo "[ERROR] 找不到 conda.sh，请手动 source 后重跑"
    exit 1
fi

# ---------- Step 1: git clone ----------
echo ""
echo "[Step 1] git clone MHLAPre repo"
mkdir -p "$TOOLS_REPOS"

if [ -d "$MHLAPRE_HOME" ]; then
    echo "  目录已存在，git pull 更新..."
    cd "$MHLAPRE_HOME"
    git pull
else
    git clone https://github.com/ChanganMakeYi/MHLAPre.git "$MHLAPRE_HOME"
    echo "  clone 完成: $MHLAPRE_HOME"
fi

# ---------- Step 2: 检查 repo 内容 ----------
echo ""
echo "[Step 2] 检查 repo 关键文件"
echo "--- repo 根目录 ---"
ls -la "$MHLAPRE_HOME/"

echo ""
echo "--- 检查权重文件是否存在 ---"
WEIGHT_FOUND=0
# 常见权重扩展名
for ext in .pt .pth .pkl .h5 .bin; do
    COUNT=$(find "$MHLAPRE_HOME" -name "*$ext" 2>/dev/null | wc -l)
    if [ "$COUNT" -gt 0 ]; then
        echo "  [OK] 找到 $COUNT 个 $ext 文件"
        find "$MHLAPRE_HOME" -name "*$ext" 2>/dev/null
        WEIGHT_FOUND=1
    fi
done

if [ "$WEIGHT_FOUND" -eq 0 ]; then
    echo ""
    echo "  [!! 阻塞] 未找到任何权重文件（.pt/.pth/.pkl 等）"
    echo "  → README 已知：权重'太大未上传'"
    echo "  → 请邮件 23B903048@stu.hit.edu.cn 索取权重后再继续"
    echo "  → 权重到位后将文件放入: $MHLAPRE_HOME/"
    echo "  → 脚本将继续创建 conda env（无权重也可建 env，到 run 阶段才会报错）"
fi

# ---------- Step 3: 建 conda env ----------
echo ""
echo "[Step 3] 建 conda env: $ENV_NAME (Python 3.9.13)"

mkdir -p "$ENVS_DIR"

if conda env list | grep -q "^$ENV_NAME "; then
    echo "  env $ENV_NAME 已存在，跳过创建"
else
    conda create -y \
        --prefix "$ENVS_DIR/$ENV_NAME" \
        python=3.9.13 \
        -c conda-forge
    echo "  env 创建完成"
fi

_CONDA_RUN="conda run --no-capture-output --prefix $ENVS_DIR/$ENV_NAME"

# ---------- Step 4: 安装依赖 ----------
echo ""
echo "[Step 4] 安装 Python 依赖"

# !! CUDA 版本选择（重要）：
# 运行前先执行 nvidia-smi 确认驱动版本，然后选一条 pip 命令取消注释

echo ""
echo "[!! CUDA 版本 TODO] 请先运行 nvidia-smi 确认 CUDA 驱动版本："
echo "  nvidia-smi | grep 'CUDA Version'"
echo ""

# --- 备选 A: CPU 版（推荐优先试，无 GPU 兼容风险，ELISpot 数据量小可接受）---
# torch 1.12.1 CPU 版，不依赖 CUDA 驱动版本
${_CONDA_RUN} pip install \
    torch==1.12.1 \
    --extra-index-url https://download.pytorch.org/whl/cpu
# TODO: 若模型推理太慢，改用备选 B

# --- 备选 B: CUDA 11.6（HPC 常见 driver >= 520，CUDA 11.6 兼容）---
# 取消下方注释前先注释掉备选 A
# ${_CONDA_RUN} pip install \
#     torch==1.12.1+cu116 \
#     --extra-index-url https://download.pytorch.org/whl/cu116

# --- 备选 C: CUDA 11.3（旧节点 driver >= 465）---
# ${_CONDA_RUN} pip install \
#     torch==1.12.1+cu113 \
#     --extra-index-url https://download.pytorch.org/whl/cu113

# --- 备选 D: 原始 CUDA 10.2（repo 指定，HPC 一般不支持）---
# 仅当 HPC GPU 节点确认 CUDA driver = 10.2 时才用
# ${_CONDA_RUN} pip install \
#     torch==1.12.1+cu102 \
#     --extra-index-url https://download.pytorch.org/whl/cu102

echo "  torch 安装完成（备选 A: CPU 版）"

# rdkit：conda-forge 版本最稳定，与 pip 混装有时冲突
# repo 指定 rdkit~2021.03.2，conda-forge 有对应版本
${_CONDA_RUN} conda install -y \
    --prefix "$ENVS_DIR/$ENV_NAME" \
    -c conda-forge \
    "rdkit=2021.03.2" || {
    echo "  [WARN] conda 安装 rdkit 2021.03.2 失败，尝试 pip 安装 rdkit..."
    ${_CONDA_RUN} pip install rdkit-pypi
}

# 其他依赖（版本来自 repo requirements，query README 推断）
${_CONDA_RUN} pip install \
    "scikit-learn>=1.0.2" \
    "numpy==1.21.2" \
    "pandas==1.4.4"

echo ""
echo "[Step 4] 依赖安装完成"

# ---------- Step 5: 验证环境 ----------
echo ""
echo "[Step 5] 验证 import"
${_CONDA_RUN} python3 -c "
import torch, sklearn, numpy, pandas
print(f'  torch    : {torch.__version__}')
print(f'  sklearn  : {sklearn.__version__}')
print(f'  numpy    : {numpy.__version__}')
print(f'  pandas   : {pandas.__version__}')
try:
    import rdkit
    print(f'  rdkit    : {rdkit.__version__}')
except ImportError:
    print('  rdkit    : [WARN] import 失败，Pretreatment.py 会报错')
"

# ---------- Step 6: 权重占位提醒 ----------
echo ""
echo "===== 部署摘要 ====="
echo "repo 路径    : $MHLAPRE_HOME"
echo "conda env    : $ENVS_DIR/$ENV_NAME"
echo ""
if [ "$WEIGHT_FOUND" -eq 0 ]; then
    echo "[!! 阻塞] 权重文件缺失 → 无法运行推理"
    echo "  下一步："
    echo "    1. 邮件 23B903048@stu.hit.edu.cn 索取权重"
    echo "    2. 权重到位后：scp/sftp 上传至 $MHLAPRE_HOME/"
    echo "    3. 跑 inspect_mhlapre.sh 确认输入列名 + 路径硬编码"
    echo "    4. 准备输入 TSV，跑 run_mhlapre.sh（待写）"
else
    echo "[OK] 权重已存在，运行前先跑 inspect_mhlapre.sh 确认输入格式"
fi
echo ""
echo "CUDA 版本 TODO: 上机后 nvidia-smi 确认驱动，再选 deploy 脚本中的 pip 命令（备选 A-D）"
echo "License TODO: 邮件作者确认学术用途许可"
echo "IEDB overlap TODO: 权重+数据到位后核查测试集与训练集重叠"
echo ""
echo "详见 NOTES.md"
echo "===== 部署脚本执行完毕 ====="
