#!/bin/bash
# HyperFidBench BrainGB env — 纯离线（计算节点无外网）。禁 pip 版本自检(否则走网挂起)。
set -e
export PIP_DISABLE_PIP_VERSION_CHECK=1
export PIP_NO_INPUT=1
ROOT=/gpfs/work/bio/jiayu2403/hyperfid
WH=$ROOT/wheelhouse
BASEPY=/gpfs/work/bio/jiayu2403/.conda/envs/yjcu124py310/bin/python
mkdir -p $ROOT/logs $ROOT/results

echo "=== 0. 清旧 venv ==="
rm -rf $ROOT/hf_braingb_venv
echo "=== 1. 建干净 venv py3.10 ==="
$BASEPY -m venv $ROOT/hf_braingb_venv
PY=$ROOT/hf_braingb_venv/bin/python

OFF="--no-index --find-links $WH --disable-pip-version-check"
echo "=== 2. torch 2.1.0+cu118 (离线, --no-deps 跳 triton; BrainGB 不用 torch.compile) ==="
$PY -m pip install $OFF --no-deps torch==2.1.0+cu118 2>&1 | tail -3
$PY -m pip install $OFF filelock sympy mpmath networkx jinja2 MarkupSafe fsspec typing-extensions 2>&1 | tail -3
echo "=== 3. torch_sparse/scatter (离线) ==="
$PY -m pip install $OFF torch_sparse torch_scatter 2>&1 | tail -3
echo "=== 4. PyG 2.5.3 + extras (离线) ==="
$PY -m pip install $OFF torch_geometric==2.5.3 nilearn node2vec nni "networkx<3" scikit-learn pandas 2>&1 | tail -3

echo "=== 5. 验 import ==="
$PY -c "import torch; print('torch', torch.__version__, 'cuda', torch.version.cuda)"
$PY -c "import torch_sparse, torch_scatter; print('sparse', torch_sparse.__version__)"
$PY -c "import torch_geometric as g; from torch_geometric.explain import Explainer, GNNExplainer; from torch_geometric.explain.metric import fidelity; print('pyg', g.__version__, 'explain+fidelity OK')"
$PY -c "import nilearn, node2vec, nni, networkx; print('extras OK nx', networkx.__version__)"
echo "=== BRAINGB ENV DONE ==="
