#!/bin/bash
set -e
source /etc/profile.d/modules.sh 2>/dev/null || true
module load miniconda3/22.11.1-gcc-8.5.0-l4fo6ta
ROOT=/gpfs/work/bio/jiayu2403/quantimmu
ENV=$ROOT/envs/neotimmuml
[ -d $ENV ] || conda create -y -p $ENV python=3.10 >/dev/null 2>&1
echo "ENV_READY"
source activate $ENV
pip install -q pandas numpy scikit-learn lightgbm xgboost matplotlib seaborn openpyxl 2>&1 | tail -1
python -c "import pandas,numpy,sklearn,lightgbm,xgboost;print('LIBS_OK lgbm',lightgbm.__version__,'xgb',xgboost.__version__)" 2>&1 | grep LIBS_OK
cd $ROOT/tools_repos/NeoTImmuML
python -c "
import pandas as pd
df=pd.read_excel('demo.csv')
print('DEMO_OK shape',df.shape,'cols0-2',list(df.columns)[:2])
"
echo "NEOTIMMUML_ENV_DONE"
