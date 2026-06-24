#!/bin/bash
# dtn 补 HyperGALE wheel（分组下避 pip 回溯；多数 deps 已在 wheelhouse/braingb 闭包）
export PIP_DISABLE_PIP_VERSION_CHECK=1
ROOT=/gpfs/work/bio/jiayu2403/hyperfid
WH=$ROOT/wheelhouse
PY=/gpfs/work/bio/jiayu2403/.conda/envs/yjcu124py310/bin/python
ALI="-i https://mirrors.aliyun.com/pypi/simple/"
cd $ROOT

echo "=== torch2.0.1 + torchvision (--no-deps, aliyun pytorch) ==="
$PY -m pip download --no-deps -d $WH -f https://mirrors.aliyun.com/pytorch-wheels/cu118/ torch==2.0.1+cu118 2>&1 | tail -1
$PY -m pip download --no-deps -d $WH -f https://mirrors.aliyun.com/pytorch-wheels/cu118/ torchvision==0.15.2+cu118 2>&1 | tail -1

echo "=== pyg2.3.1 (--no-deps) ==="
$PY -m pip download --no-deps -d $WH $ALI torch_geometric==2.3.1 2>&1 | tail -1

echo "=== lightning + torchmetrics (含deps) ==="
$PY -m pip download -d $WH $ALI pytorch-lightning==2.0.7 torchmetrics==1.1.0 2>&1 | tail -1

echo "=== hydra/omegaconf/wandb (含deps) ==="
$PY -m pip download -d $WH $ALI hydra-core==1.3.2 omegaconf==2.3.0 wandb==0.15.0 2>&1 | tail -1

echo "=== dhg + nilearn0.10.1 + nibabel (含deps) ==="
$PY -m pip download -d $WH $ALI dhg==0.9.3 nilearn==0.10.1 nibabel==5.1.0 2>&1 | tail -1

echo "=== deepsnap (git --no-deps) ==="
$PY -m pip download --no-deps -d $WH "git+https://github.com/snap-stanford/deepsnap.git@08bab608394484261b95a9e593d96e3127045222" 2>&1 | tail -1 || echo deepsnap_fail

echo "=== torchvision deps (pillow) + 杂项 ==="
$PY -m pip download -d $WH $ALI pillow 2>&1 | tail -1

echo "=== 统计 ==="; ls $WH | wc -l
echo "=== FETCH HG WHEELS DONE ==="
