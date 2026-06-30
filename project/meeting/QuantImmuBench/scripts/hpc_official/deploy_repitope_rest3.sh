#!/usr/bin/env bash
# =============================================================================
# deploy_repitope_rest3.sh — conda 预编译批装 Repitope 的 22 个 R 依赖 + msa
#                            → install_local(dependencies=FALSE)
# =============================================================================
# rest2 进展：rJava 修通、git clone 成功，但 install_local(dependencies=TRUE) 因
# 22 个 R 依赖源码构建失败("not available")。本脚本改用 conda-forge/bioconda
# 预编译包批装这些依赖（避源码编译地狱），msa 走 bioconda，再 install_local 不带 deps。
# 主线串行：module load miniconda3/... && source .../conda.sh && bash deploy_repitope_rest3.sh
# =============================================================================
set -uo pipefail

BASE=/gpfs/work/bio/jiayu2403/quantimmu
ENV="$BASE/envs/andy90_r"
RBIN="$ENV/bin"
DATADIR="$BASE/tools_repos/Repitope_data"
SRC="$BASE/tools_repos/Repitope_src"
export R_LIBS_USER="$ENV/lib/R/library"

# rJava JVM 环境（同 rest2，install/load 时要）
LIBJVM=$(find "$ENV" -name libjvm.so 2>/dev/null | head -1)
export JAVA_HOME="$ENV"
export LD_LIBRARY_PATH="$(dirname "$LIBJVM"):$ENV/lib:${LD_LIBRARY_PATH:-}"

echo "[rest3] conda 预编译批装 Repitope 22 依赖 + msa(bioconda)"
# DESCRIPTION Imports（来自 rest2 报错清单）。Peptides 也含在内（W4 NeoTImmuML 同款）。
conda install -p "$ENV" -c conda-forge -c bioconda -y \
  r-bbmisc r-car r-caret r-cvauc r-desctools r-extratrees r-ggplot2 r-ggpubr \
  r-ggsci r-igraph r-matrixstats r-mlr r-peptides r-precrec r-proc r-psych \
  r-rlecuyer r-stringdist r-survminer r-survival r-zoo bioconductor-msa 2>&1 | tail -8
rc=$?
echo "[rest3] conda install rc=$rc"

echo "[rest3] 核依赖加载性"
"$RBIN/Rscript" -e '
  deps <- c("BBmisc","car","caret","cvAUC","DescTools","extraTrees","ggplot2","ggpubr",
            "ggsci","igraph","matrixStats","mlr","msa","Peptides","precrec","pROC",
            "psych","rlecuyer","stringdist","survminer","survival","zoo")
  miss <- deps[!sapply(deps, requireNamespace, quietly=TRUE)]
  if(length(miss)) cat("[MISS]", paste(miss, collapse=", "), "\n") else cat("[OK] 22 依赖全可加载\n")
' 2>&1 | tail -5

echo "[rest3] install_local(dependencies=FALSE)（依赖已 conda 装）"
"$RBIN/Rscript" -e "
  devtools::install_local('$SRC', upgrade='never', dependencies=FALSE, force=TRUE)
  stopifnot(requireNamespace('Repitope', quietly=TRUE))
  cat('[OK] Repitope 安装成功 version:', as.character(packageVersion('Repitope')), '\n')
" 2>&1 | tail -20
"$RBIN/Rscript" -e 'stopifnot(requireNamespace("Repitope",quietly=TRUE))' || { echo "[FAIL] Repitope 仍未装上"; exit 1; }

# ---- 下 Mendeley 数据集 ----
echo "[rest3] 下 Mendeley 数据集 → $DATADIR"
mkdir -p "$DATADIR"
dl_mendeley () {
  local ds="$1" ver="$2" fn="$3" dest="$4"
  if [[ -s "$dest" ]]; then echo "  [skip] 已存在 $dest ($(du -h "$dest"|cut -f1))"; return; fi
  echo "  [get] $fn (dataset $ds v$ver)"
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
echo "[rest3] 部署 OK → 下一步 bash run_repitope_official.sh"
echo "==================================================================="
