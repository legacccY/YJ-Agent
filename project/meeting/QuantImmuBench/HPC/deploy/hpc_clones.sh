#!/bin/bash
ROOT=/gpfs/work/bio/jiayu2403/quantimmu
cd $ROOT/tools_repos
for r in 01SYan19/NeoTImmuML GfellerLab/PRIME GfellerLab/MixMHCpred SRHgroup/self_similarity SRHgroup/IMPROVE_tool; do
  d=$(basename $r)
  if [ ! -d "$d" ]; then echo "cloning $d"; git clone --depth 1 https://github.com/$r.git 2>&1 | tail -1; else echo "$d exists"; fi
done
echo "=== git-lfs pull IMPROVE models ==="
cd $ROOT/tools_repos/IMPROVE_tool && git lfs install >/dev/null 2>&1 && git lfs pull 2>&1 | tail -1
ls -la models.zip 2>/dev/null
echo "DONE_CLONES"; ls $ROOT/tools_repos
