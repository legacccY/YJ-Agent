#!/bin/bash
# HyperFidBench HyperGALE env — 离线装（从 dtn 预下 wheelhouse；torch2.0.1+cu118 + PyG2.3.1 官方 pin）
set -e
export PIP_DISABLE_PIP_VERSION_CHECK=1
export PIP_NO_INPUT=1
ROOT=/gpfs/work/bio/jiayu2403/hyperfid
WH=$ROOT/wheelhouse
BASEPY=/gpfs/work/bio/jiayu2403/.conda/envs/yjcu124py310/bin/python
mkdir -p $ROOT/logs

echo "=== 0. 清旧 ==="
rm -rf $ROOT/hf_hypergale_venv
echo "=== 1. 建干净 venv py3.10 ==="
$BASEPY -m venv $ROOT/hf_hypergale_venv
PY=$ROOT/hf_hypergale_venv/bin/python

OFF="--no-index --find-links $WH --disable-pip-version-check"
echo "=== 2. torch 2.0.1+cu118 + torchvision (离线, --no-deps 跳 triton) ==="
$PY -m pip install $OFF --no-deps torch==2.0.1+cu118 torchvision==0.15.2+cu118 2>&1 | tail -3
$PY -m pip install $OFF filelock sympy mpmath networkx jinja2 MarkupSafe fsspec typing-extensions numpy pillow requests 2>&1 | tail -3
echo "=== 3. PyG 生态 (离线, 官方 pin) ==="
$PY -m pip install $OFF torch_geometric==2.3.1 2>&1 | tail -3
$PY -m pip install $OFF torch_scatter==2.1.1 torch_sparse==0.6.17 torch_cluster==1.6.1 2>&1 | tail -3
echo "=== 4. HyperGALE 框架依赖 (离线, 官方 pin) ==="
$PY -m pip install $OFF pytorch-lightning==2.0.7 torchmetrics==1.1.0 hydra-core==1.3.2 omegaconf==2.3.0 \
    wandb==0.15.0 dhg==0.9.3 nilearn==0.10.1 nibabel==5.1.0 scikit-learn==1.2.2 pandas==2.0.1 \
    numpy==1.24.2 numba==0.57.1 optuna==3.2.0 ogb==1.3.6 node2vec==0.4.6 gensim==4.3.1 ipdb 2>&1 | tail -3
echo "=== 5. deepsnap (离线, 从 wheelhouse) ==="
$PY -m pip install $OFF --no-deps deepsnap 2>&1 | tail -2 || echo "deepsnap 离线装失败,后处理"

echo "=== 6. 验 import ==="
$PY -c "import torch; print('torch', torch.__version__, 'cuda', torch.version.cuda)"
$PY -c "import torch_sparse, torch_scatter, torch_cluster; print('pyg-ext', torch_sparse.__version__)"
$PY -c "import torch_geometric as g; print('pyg', g.__version__)"
$PY -c "import pytorch_lightning as pl, hydra, omegaconf, dhg, wandb; print('framework OK pl', pl.__version__, 'dhg', dhg.__version__)"
echo "=== HYPERGALE ENV DONE ==="
