#!/bin/bash
set -e
source /etc/profile.d/modules.sh 2>/dev/null || true
module load miniconda3/22.11.1-gcc-8.5.0-l4fo6ta
ROOT=/gpfs/work/bio/jiayu2403/quantimmu
cd $ROOT/tools_repos/IMPROVE_tool
echo "=== unzip models ==="
unzip -o -q models.zip && echo UNZIP_OK
for v in Simple TME_excluded TME_included; do echo "$v: $(ls models/$v/ 2>/dev/null | grep -c rf) rf"; done
ENV=$ROOT/envs/improve
[ -d $ENV ] || conda create -y -p $ENV python=3.11 >/dev/null 2>&1
echo "ENV_READY"
source activate $ENV
pip install -q "numpy>=2.0" pandas scikit-learn seaborn 2>&1 | tail -1
python -c "import numpy,sklearn,pandas;print('LIBS_OK np',numpy.__version__,'sk',sklearn.__version__)" 2>&1 | grep LIBS_OK
# 改 base_dir 为 HPC repo 路径
sed "s|^base_dir = .*|base_dir = \"$ROOT/tools_repos/IMPROVE_tool\"|" Predict_immunogenicity_CLEAN_retrain.py > predict_local.py
mkdir -p $ROOT/smoke/improve
echo "=== Predict Simple 烟测 ==="
python predict_local.py --file data/calculated_features_test.tsv --model Simple --outfile $ROOT/smoke/improve/out_simple.tsv 2>/dev/null | tail -1
echo "=== 输出关键列 ==="
python -c "
import csv
r=list(csv.DictReader(open('$ROOT/smoke/improve/out_simple.tsv'),delimiter='\t'))
print('rows',len(r))
for row in r[:3]: print(row['Mut_peptide'],row['HLA_allele'],'pred='+row['mean_prediction_rf'])
"
echo "IMPROVE_ALL_DONE"
