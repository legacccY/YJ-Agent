#!/bin/bash
source ~/.bashrc
conda activate immuneapp
# NOTE: must use "immuneapp" (lowercase) — "ImmuneApp" env has NO tensorflow!

cd /gpfs/work/bio/zichenli24/tools/ImmuneApp

INPUTS=/gpfs/work/bio/zichenli24/rerun_v2/03_ImmuneApp/inputs
OUTPUTS=/gpfs/work/bio/zichenli24/rerun_v2/03_ImmuneApp/outputs
mkdir -p ${OUTPUTS}/all_results

echo "Start: $(date)"

for subset in dataset2_MT dataset2_WT; do
  INDIR=${INPUTS}/${subset}
  for txt in ${INDIR}/*.txt; do
    fname=$(basename ${txt} .txt)
    hla_raw=${fname#HLA-}
    a1=${hla_raw:0:1}
    a2=${hla_raw:1:2}
    a3=${hla_raw:3:2}
    hla="HLA-${a1}*${a2}:${a3}"
    outdir=${OUTPUTS}/${subset}/${fname}
    mkdir -p ${outdir}
    echo "  ${subset}/${fname} -> ${hla}"
    timeout 300 python ImmuneApp_immunogenicity_prediction.py -f ${txt} -a ${hla} -o ${outdir}
  done
done

python /gpfs/work/bio/zichenli24/rerun_v2/03_ImmuneApp/merge_results.py
echo "Done: $(date)"
