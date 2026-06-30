#!/usr/bin/env bash
# =============================================================================
# deploy_repitope_rest5.sh — 全新干净 env(避既有 env 约束致 solve 爆炸)
# =============================================================================
# rest1-4 教训：往已有复杂 env(andy90_r)塞 caret/mlr/msa,classic solver(无
# libmamba)被既有 pin 约束撑爆,27min 不收敛 / 小批 caret 也 600s 超时。
# 本脚本建【全新 env repitope_r】——无既有约束,conda create solve 快得多。
# conda-forge 单频道建主体 → bioconda 单独补 msa/biostrings → install_local + 数据集。
# 主线串行：module load miniconda3/... && source .../conda.sh && bash deploy_repitope_rest5.sh
# =============================================================================
set -uo pipefail

BASE=/gpfs/work/bio/jiayu2403/quantimmu
ENV="$BASE/envs/repitope_r"          # 全新 env
DATADIR="$BASE/tools_repos/Repitope_data"
SRC="$BASE/tools_repos/Repitope_src"

echo "[rest5] conda create 全新 env $ENV (conda-forge 单频道, 主体一次建)"
timeout 1500 conda create -p "$ENV" -c conda-forge -y \
  r-base=4.1 r-rjava r-devtools r-fst r-biocmanager \
  r-bbmisc r-car r-caret r-cvauc r-desctools r-extratrees r-ggplot2 r-ggpubr \
  r-ggsci r-igraph r-matrixstats r-mlr r-peptides r-precrec r-proc r-psych \
  r-rlecuyer r-stringdist r-survminer r-survival r-zoo openjdk=8 2>&1 | tail -5
rc=${PIPESTATUS[0]}
echo "[rest5] create rc=$rc"
[ "$rc" -ne 0 ] && { echo "[FAIL] 干净 env create 仍失败/超时(rc=$rc)。classic solver 撑不住 caret/mlr → 建议 Repitope defer"; exit 1; }

RBIN="$ENV/bin"
export R_LIBS_USER="$ENV/lib/R/library"
LIBJVM=$(find "$ENV" -name libjvm.so 2>/dev/null | head -1)
export JAVA_HOME="$ENV"
export LD_LIBRARY_PATH="$(dirname "${LIBJVM:-$ENV}"):$ENV/lib:${LD_LIBRARY_PATH:-}"

echo "[rest5] bioconda 补 msa + biostrings(单独, 避跨频道大爆炸)"
timeout 900 conda install -p "$ENV" -c bioconda -c conda-forge -y bioconductor-msa bioconductor-biostrings 2>&1 | tail -4
echo "[rest5] msa rc=${PIPESTATUS[0]}"

echo "[rest5] 核 22 依赖 + rJava"
"$RBIN/Rscript" -e '
  library(rJava); .jinit(); cat("[OK] rJava\n")
  deps <- c("BBmisc","car","caret","cvAUC","DescTools","extraTrees","ggplot2","ggpubr",
            "ggsci","igraph","matrixStats","mlr","msa","Peptides","precrec","pROC",
            "psych","rlecuyer","stringdist","survminer","survival","zoo")
  miss <- deps[!sapply(deps, requireNamespace, quietly=TRUE)]
  if(length(miss)){ cat("[MISS]", paste(miss, collapse=", "), "\n"); quit(status=1) } else cat("[OK] 22 依赖全可加载\n")
' 2>&1 | tail -4
[ "${PIPESTATUS[0]}" -ne 0 ] && { echo "[FAIL] 依赖/rJava 缺(见 [MISS])"; exit 1; }

echo "[rest5] install_local(dependencies=FALSE)"
"$RBIN/Rscript" -e "
  devtools::install_local('$SRC', upgrade='never', dependencies=FALSE, force=TRUE)
  stopifnot(requireNamespace('Repitope', quietly=TRUE))
  cat('[OK] Repitope version:', as.character(packageVersion('Repitope')), '\n')
" 2>&1 | tail -15
"$RBIN/Rscript" -e 'stopifnot(requireNamespace("Repitope",quietly=TRUE))' || { echo "[FAIL] Repitope 未装上"; exit 1; }

echo "[rest5] 下 Mendeley 数据集 → $DATADIR"
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
echo "[rest5] 部署 OK(env=repitope_r) → run_repitope_official.sh 改用此 env"
echo "==================================================================="
