#!/bin/bash
set -e
source /etc/profile.d/modules.sh 2>/dev/null || true
module load miniconda3/22.11.1-gcc-8.5.0-l4fo6ta
ROOT=/gpfs/work/bio/jiayu2403/quantimmu
cd $ROOT/tools_repos
[ -d DeepImmuno ] || git clone --depth 1 https://github.com/frankligy/DeepImmuno.git 2>&1 | tail -1
echo "CLONE_OK"
ENV=$ROOT/envs/deepimmuno
[ -d $ENV ] || conda create -y -p $ENV python=3.8 >/dev/null 2>&1
echo "ENV_READY"
source activate $ENV
pip install -q "tensorflow==2.3.0" "numpy==1.18.5" "pandas==1.1.1" "protobuf==3.20.3" 2>&1 | tail -1
python -c "import tensorflow as tf;print('TF_OK',tf.__version__)" 2>&1 | grep TF_OK
cd DeepImmuno
echo "SMOKE_RESULT:"
python deepimmuno-cnn.py --mode single --epitope HPPLMNVER --hla "HLA-A*0201" 2>/dev/null | tail -1
echo "ALL_DONE"
