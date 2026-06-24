#!/bin/bash
# dtn 上跑（外网快 105MB/s）：把两 env 全依赖闭包下到 wheelhouse，供计算节点离线装。
# 计算节点外网慢，故所有下载在 dtn 完成。
set -e
ROOT=/gpfs/work/bio/jiayu2403/hyperfid
WH=$ROOT/wheelhouse
PY=/gpfs/work/bio/jiayu2403/.conda/envs/yjcu124py310/bin/python
ALI="-i https://mirrors.aliyun.com/pypi/simple/"
mkdir -p $WH
cd $ROOT

echo "=== torch wheels (aliyun, --no-deps) ==="
$PY -m pip download --no-deps -d $WH -f https://mirrors.aliyun.com/pytorch-wheels/cu118/ \
    torch==2.1.0+cu118 torch==2.0.1+cu118 torchvision==0.15.2+cu118 2>&1 | tail -3

echo "=== torch-ext wheels (data.pyg.org, --no-deps) ==="
$PY -m pip download --no-deps -d $WH -f https://data.pyg.org/whl/torch-2.1.0+cu118.html torch_sparse torch_scatter 2>&1 | tail -2
$PY -m pip download --no-deps -d $WH -f https://data.pyg.org/whl/torch-2.0.0+cu118.html torch_scatter==2.1.1 torch_sparse==0.6.17 torch_cluster==1.6.1 2>&1 | tail -2

echo "=== braingb PyPI 闭包 (aliyun, 含 deps) ==="
$PY -m pip download -d $WH $ALI torch_geometric==2.5.3 nilearn node2vec nni "networkx<3" scikit-learn pandas 2>&1 | tail -2

echo "=== hypergale PyPI 闭包 (aliyun, 含 deps) ==="
$PY -m pip download -d $WH $ALI torch_geometric==2.3.1 pytorch-lightning==2.0.7 torchmetrics==1.1.0 \
    hydra-core==1.3.2 omegaconf==2.3.0 wandb==0.15.0 dhg==0.9.3 nilearn==0.10.1 nibabel==5.1.0 \
    scikit-learn==1.2.2 pandas==2.0.1 numpy==1.24.2 numba==0.57.1 optuna==3.2.0 ogb==1.3.6 \
    node2vec==0.4.6 gensim==4.3.1 ipdb 2>&1 | tail -2

echo "=== deepsnap (git, 下成 wheel/sdist) ==="
$PY -m pip download --no-deps -d $WH "git+https://github.com/snap-stanford/deepsnap.git@08bab608394484261b95a9e593d96e3127045222" 2>&1 | tail -2 || echo "deepsnap download 失败(git), 计算节点另处理"

echo "=== wheelhouse 统计 ==="
ls $WH | wc -l; du -sh $WH
echo "=== FETCH WHEELS DONE ==="
