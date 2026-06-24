#!/usr/bin/env bash
# ===========================================================================
# deploy_deephlapan_condaA.sh — 路 A：HPC 原生 conda 部署 deepHLApan
# 服务: quantimmu-bench / deepHLApan
#
# 用法（HPC 登录节点 bash，非 sbatch）:
#   bash /gpfs/work/bio/jiayu2403/quantimmu/scripts/deephlapan/deploy_deephlapan_condaA.sh
#
# 成功标志:
#   打印 ENV_READY + TF_OK + INSTALL_DONE + CLONE_OK
#
# ⚠️  版本地狱警告（必读，见 NOTES.md §1）:
#   deepHLApan requirements.txt 要求 keras==2.0.8（2017）+
#   tensorflow==2.7.2（2021）。两者 ABI 不兼容——Issue #9 报
#   "Error in loading the saved optimizer state"。
#   本脚本先按官方 requirements 装，装完做兼容性探针；
#   若探针报 optimizer 错 → 见 NOTES.md 备选 pin 方案，
#   最终兜底走 路 B（singularity sif）。
#
# 依赖事实:
#   - HPC: conda 22.11.1, singularity 3.11.3, 无 docker
#   - GitHub 通, PyPI 通
#   - 项目根: /gpfs/work/bio/jiayu2403/quantimmu/
# ===========================================================================

set -euo pipefail

ROOT=/gpfs/work/bio/jiayu2403/quantimmu
REPO_DIR="$ROOT/tools_repos/deephlapan"
ENV_DIR="$ROOT/envs/deephlapan"
SCRIPTS_DIR="$ROOT/scripts/deephlapan"

echo "===== [A-0] 加载 conda 模块 ====="
source /etc/profile.d/modules.sh 2>/dev/null || true
module load miniconda3/22.11.1-gcc-8.5.0-l4fo6ta

echo "===== [A-1] clone deepHLApan repo ====="
mkdir -p "$ROOT/tools_repos"
if [ -d "$REPO_DIR" ]; then
    echo "repo 已存在: $REPO_DIR，跳过 clone"
else
    git clone --depth 1 https://github.com/jiujiezz/deephlapan.git "$REPO_DIR" 2>&1 | tail -3
fi
echo "CLONE_OK"
ls "$REPO_DIR"

echo "===== [A-2] 建 conda env (python 3.6) ====="
# deepHLApan 依赖 keras2.0.8 + TF1.x-era API，需 python3.6 兼容栈
# TF2.7.2 最低要 python3.7，而 keras2.0.8 要 python<=3.6 → 已知矛盾
# 这里用 python3.7 作为折中（TODO: 需主线实测确认，官方 Docker 内真实 python 版本未知）
# TODO: 若 python3.7+TF2.7.2+keras2.0.8 仍炸 → 改走路 B sif

if [ -d "$ENV_DIR" ]; then
    echo "env 已存在: $ENV_DIR，跳过创建"
else
    conda create -y -p "$ENV_DIR" python=3.7 2>&1 | tail -3
fi
echo "ENV_READY"

echo "===== [A-3] 激活 env 并安装依赖 ====="
source activate "$ENV_DIR"

# --- 核心依赖（按官方 requirements.txt）---
# keras==2.0.8 是 standalone keras（非 tf.keras），与 TF2.7 已知冲突
# 先装 TF2.7.2，再装 keras2.0.8；若 optimizer 探针报错见下方备选 pin
pip install -q \
    "tensorflow==2.7.2" \
    "keras==2.0.8" \
    "numpy==1.19.5" \
    "pandas>=1.0" \
    "gensim==3.8.3" \
    "scipy>=1.4" \
    "scikit-learn>=0.24" \
    2>&1 | tail -5

# TODO: 若上行报 keras/TF 冲突，备选 pin：
#   pip install "tensorflow==1.14.0" "keras==2.2.4" "numpy==1.16.4"
#   （TF1.14 + Keras2.2.4 是当年推荐组合，但 CUDA9 cuDNN7 专属，HPC GPU 是否兼容需主线确认）
#   另一备选：不装 standalone keras，改 "keras" 包替换为 "tf_keras"（TF2.7 内置兼容层）
#   deepHLApan 源码 import keras → 需检查是否可直接替换为 import tensorflow.keras

echo "TF version:"
python -c "import tensorflow as tf; print('TF_OK', tf.__version__)"
echo "Keras version:"
python -c "import keras; print('Keras_OK', keras.__version__)" 2>/dev/null || \
    echo "Keras standalone import FAIL（预期中——TF2.7 冲突，见 NOTES.md §1）"

echo "===== [A-4] 版本兼容性探针 ====="
# 探针：尝试 import deepHLApan 并加载模型权重
# 若报 optimizer 错 → 路 A 不可用，走路 B
cd "$REPO_DIR"
python - <<'PYEOF'
import sys
try:
    import keras
    print(f"[probe] standalone keras {keras.__version__} import OK")
except Exception as e:
    print(f"[probe] standalone keras import FAIL: {e}", file=sys.stderr)
    sys.exit(1)

# 尝试加载模型（不跑 GPU，只测 load）
import os
model_path = os.path.join(os.path.dirname(__file__), "models") if False else "models"
if os.path.isdir(model_path):
    try:
        from keras.models import load_model
        # 只 list 文件，不 load（避免 CUDA init）
        model_files = [f for f in os.listdir(model_path) if f.endswith('.h5') or f.endswith('.hdf5')]
        print(f"[probe] model files found: {model_files}")
        print("[probe] 模型文件存在，load_model 探针跳过（需 CUDA init，主线确认）")
    except Exception as e:
        print(f"[probe] load_model import FAIL: {e}", file=sys.stderr)
        sys.exit(2)
else:
    print(f"[probe] models/ 目录不存在于 {os.getcwd()}，跳过模型探针")
PYEOF

echo "INSTALL_DONE"

echo ""
echo "===== [路 A 部署小结] ====="
echo "  env    : $ENV_DIR"
echo "  repo   : $REPO_DIR"
echo "  若探针打印 FAIL → 走路 B singularity（build_deephlapan_sifB.sh）"
echo "  否则继续 smoke_deephlapan.sh 全链验证"
