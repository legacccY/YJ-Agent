#!/usr/bin/env bash
# =============================================================================
# deploy_repitope_rest4.sh — 小批 conda 装 Repitope 依赖（classic solver 友好）
# =============================================================================
# rest3 教训：conda classic solver（无 libmamba/mamba）啃 22 包+bioconda 跨频道
# → solve 27min 不收敛卡死。本脚本拆小批（每批 4-6 包，conda-forge 单频道，
# classic 可秒级~分钟级收敛）+ bioconda-msa 单独一批 + 每批 timeout 防挂死。
# 装完 install_local(deps=FALSE) + 下数据集。
# 主线串行：module load miniconda3/... && source .../conda.sh && bash deploy_repitope_rest4.sh
# =============================================================================
set -uo pipefail

BASE=/gpfs/work/bio/jiayu2403/quantimmu
ENV="$BASE/envs/andy90_r"
RBIN="$ENV/bin"
DATADIR="$BASE/tools_repos/Repitope_data"
SRC="$BASE/tools_repos/Repitope_src"
export R_LIBS_USER="$ENV/lib/R/library"

LIBJVM=$(find "$ENV" -name libjvm.so 2>/dev/null | head -1)
export JAVA_HOME="$ENV"
export LD_LIBRARY_PATH="$(dirname "$LIBJVM"):$ENV/lib:${LD_LIBRARY_PATH:-}"

ci () {  # conda install 单批,带 timeout(600s)防挂死
  echo "[batch] conda install: $*"
  timeout 600 conda install -p "$ENV" -c conda-forge -y "$@" 2>&1 | tail -3
  echo "[batch rc=${PIPESTATUS[0]}] $*"
}

echo "[rest4] 小批装 conda-forge 依赖"
ci r-ggplot2 r-igraph r-zoo r-survival r-matrixstats
ci r-caret r-car r-proc r-psych r-stringdist
ci r-mlr r-bbmisc r-cvauc r-precrec r-extratrees
ci r-ggpubr r-ggsci r-survminer r-desctools r-rlecuyer r-peptides

echo "[rest4] bioconda-msa 单独一批(避跨频道大爆炸)"
echo "[batch] conda install -c bioconda -c conda-forge bioconductor-msa"
timeout 600 conda install -p "$ENV" -c bioconda -c conda-forge -y bioconductor-msa 2>&1 | tail -3
echo "[batch rc=${PIPESTATUS[0]}] msa"

echo "[rest4] 核 22 依赖加载性"
"$RBIN/Rscript" -e '
  deps <- c("BBmisc","car","caret","cvAUC","DescTools","extraTrees","ggplot2","ggpubr",
            "ggsci","igraph","matrixStats","mlr","msa","Peptides","precrec","pROC",
            "psych","rlecuyer","stringdist","survminer","survival","zoo")
  miss <- deps[!sapply(deps, requireNamespace, quietly=TRUE)]
  if(length(miss)){ cat("[MISS]", paste(miss, collapse=", "), "\n"); quit(status=1) } else cat("[OK] 22 依赖全可加载\n")
' 2>&1 | tail -3
[ "${PIPESTATUS[0]}" -ne 0 ] && { echo "[FAIL] 仍有依赖缺失(见上 [MISS]),需对缺的再装"; exit 1; }

echo "[rest4] install_local(dependencies=FALSE)"
"$RBIN/Rscript" -e "
  devtools::install_local('$SRC', upgrade='never', dependencies=FALSE, force=TRUE)
  stopifnot(requireNamespace('Repitope', quietly=TRUE))
  cat('[OK] Repitope version:', as.character(packageVersion('Repitope')), '\n')
" 2>&1 | tail -15
"$RBIN/Rscript" -e 'stopifnot(requireNamespace("Repitope",quietly=TRUE))' || { echo "[FAIL] Repitope 未装上"; exit 1; }

echo "[rest4] 下 Mendeley 数据集 → $DATADIR"
mkdir -p "$DATADIR"
dl_mendeley () {
  local ds="$1" ver="$2" fn="$3" dest="$4"
  if [[ -s "$dest" ]]; then echo "  [skip] $dest ($(du -h "$dest"|cut -f1))"; return; fi
  echo "  [get] $fn"
  local url
  url=$(curl -s "https://data.mendeley.com/public-api/datasets/${ds}/files?folder_id=root&version=${ver}" \
        | python3 -c "import sys,json
for f in json.load(sys.stdin):
    if f['filename']=='${fn}':
        print(f['content_details']['download_url']); break")
  [[ -z "$url" ]] && { echo "  [FAIL] 拿不到 $fn 链接"; return 1; }
  curl -L --fail --retry 5 --retry-delay 10 -o "$dest" "$url"; ls -la "$dest"
}
dl_mendeley sydw5xnxpt 1 FragmentLibrary_TCRSet_Public_RepitopeV3.fst "$DATADIR/FragmentLibrary.fst"
dl_mendeley 2hp96k6m2c 2 FeatureDF_MHCI_Weighted.10000.fst            "$DATADIR/FeatureDF_MHCI_Weighted.10000.fst"

echo "==================================================================="
ls -la "$DATADIR"
"$RBIN/Rscript" -e 'suppressMessages(library(Repitope)); cat("Repitope OK; MHCI_Human rows:", tryCatch(nrow(MHCI_Human),error=function(e)NA), "\n")'
echo "[rest4] 部署 OK → 下一步 bash run_repitope_official.sh"
echo "==================================================================="
