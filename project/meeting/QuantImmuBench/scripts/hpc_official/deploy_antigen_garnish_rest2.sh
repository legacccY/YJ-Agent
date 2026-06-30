#!/usr/bin/env bash
# garnish rest2 — 补 7 个缺失轻依赖(conda-forge 预编译)→ install_local(deps=FALSE)
# rest 缺: mclust purrr Rdpack tidyr uuid vcfR zoo（都轻,conda-forge 有,快 solve）
set -uo pipefail
BASE="/gpfs/work/bio/jiayu2403/quantimmu"
ENV_DIR="$BASE/envs/garnish_r"
AG_SRC="$BASE/ext_tools/antigen.garnish_src"
AG_DATA_DIR="$BASE/ext_tools/antigen.garnish"
AG_TARBALL="https://s3.amazonaws.com/get.rech.io/antigen.garnish-2.3.0.tar.gz"
RBIN="$ENV_DIR/bin"
export R_LIBS_USER="$ENV_DIR/lib/R/library"

echo "[g-rest2] 补装 7 缺失轻依赖(conda-forge)"
timeout 600 conda install -p "$ENV_DIR" -c conda-forge -y \
  r-mclust r-purrr r-rdpack r-tidyr r-uuid r-vcfr r-zoo 2>&1 | tail -4
echo "[g-rest2] conda rc=${PIPESTATUS[0]}"

echo "[g-rest2] 核 7 依赖"
"$RBIN/Rscript" -e '
  d<-c("mclust","purrr","Rdpack","tidyr","uuid","vcfR","zoo")
  m<-d[!sapply(d,requireNamespace,quietly=TRUE)]
  if(length(m)){cat("[MISS]",paste(m,collapse=", "),"\n");quit(status=1)}else cat("[OK] 7 依赖齐\n")' 2>&1|tail -3
[ "${PIPESTATUS[0]}" -ne 0 ] && { echo "[FAIL] 仍缺依赖"; exit 1; }

echo "[g-rest2] install_local(deps=FALSE)"
"$RBIN/Rscript" -e "
  remotes::install_local('$AG_SRC', upgrade='never', dependencies=FALSE, force=TRUE)
  stopifnot(requireNamespace('antigen.garnish', quietly=TRUE))
  cat('[OK] antigen.garnish', as.character(packageVersion('antigen.garnish')), '\n')
" 2>&1 | tail -15
"$RBIN/Rscript" -e 'stopifnot(requireNamespace("antigen.garnish",quietly=TRUE))' || { echo "[FAIL] 未装上"; exit 1; }

echo "[g-rest2] 下 S3 数据包"
if [ ! -d "$AG_DATA_DIR" ] || [ -z "$(ls -A "$AG_DATA_DIR" 2>/dev/null)" ]; then
  mkdir -p "$AG_DATA_DIR"; cd "$(dirname "$AG_DATA_DIR")"
  curl -fsSL --retry 5 --retry-delay 10 "$AG_TARBALL" | tar -xz; chmod -R 700 "$AG_DATA_DIR" || true
else echo "  [skip] 已存在"; fi
ls -la "$AG_DATA_DIR" | head

echo "[g-rest2] 烟测 foreignness_score"
AG_DATA_DIR="$AG_DATA_DIR" "$RBIN/Rscript" -e '
  suppressMessages(library(antigen.garnish))
  v<-c("SIINFEKL","KAQPVTQATSF","EEFLNSWML")
  out<-tryCatch(foreignness_score(v,db="human"),error=function(e){cat("[SMOKE FAIL]",conditionMessage(e),"\n");quit(status=3)})
  print(out); cat("[SMOKE OK] rows=",nrow(out),"\n")' 2>&1 | tail -15
echo "[g-rest2] 完成"
