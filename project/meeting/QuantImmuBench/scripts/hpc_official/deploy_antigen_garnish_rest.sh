#!/usr/bin/env bash
# =============================================================================
# deploy_antigen_garnish_rest.sh — garnish_r env 已建好后续装(绕 GitHub API)
# =============================================================================
# 原 deploy_antigen_garnish.sh：[1] conda create garnish_r 成功(R+blastp 在),
# [2] install_github 撞 GitHub API(api.github.com 打不开/限流)。本脚本 git clone
# (git 协议绕 API)+ install_local + 下 S3 数据包 + 烟测 foreignness_score。
# 主线串行：module load miniconda3/... && source .../conda.sh && bash deploy_antigen_garnish_rest.sh
# =============================================================================
set -uo pipefail

BASE="/gpfs/work/bio/jiayu2403/quantimmu"
ENV_DIR="$BASE/envs/garnish_r"
AG_SRC="$BASE/ext_tools/antigen.garnish_src"
AG_DATA_DIR="$BASE/ext_tools/antigen.garnish"
AG_TARBALL="https://s3.amazonaws.com/get.rech.io/antigen.garnish-2.3.0.tar.gz"
RBIN="$ENV_DIR/bin"
export R_LIBS_USER="$ENV_DIR/lib/R/library"

echo "[g-rest] R=$($RBIN/R --version|head -1)  blastp=$($RBIN/../bin/blastp -version 2>/dev/null|head -1 || echo MISSING)"

echo "[1] git clone antigen.garnish(git 协议绕 API)"
if [ -d "$AG_SRC/.git" ]; then git -C "$AG_SRC" pull --ff-only || true; else
  git clone --depth 1 https://github.com/andrewrech/antigen.garnish.git "$AG_SRC"; fi

echo "[2] install_local(dependencies=TRUE 走 CRAN/Bioc,不走 GitHub API)"
"$RBIN/Rscript" -e "
  options(repos='https://cloud.r-project.org')
  Sys.setenv(R_REMOTES_UPGRADE='never')
  devtools_ok <- requireNamespace('remotes', quietly=TRUE)
  remotes::install_local('$AG_SRC', upgrade='never', dependencies=TRUE, force=TRUE)
  stopifnot(requireNamespace('antigen.garnish', quietly=TRUE))
  cat('[OK] antigen.garnish', as.character(packageVersion('antigen.garnish')), '\n')
" 2>&1 | tail -20
"$RBIN/Rscript" -e 'stopifnot(requireNamespace("antigen.garnish",quietly=TRUE))' || { echo "[FAIL] antigen.garnish 未装上"; exit 1; }

echo "[3] 下 S3 数据包 → $AG_DATA_DIR"
if [ ! -d "$AG_DATA_DIR" ] || [ -z "$(ls -A "$AG_DATA_DIR" 2>/dev/null)" ]; then
  mkdir -p "$AG_DATA_DIR"; cd "$(dirname "$AG_DATA_DIR")"
  curl -fsSL --retry 5 --retry-delay 10 "$AG_TARBALL" | tar -xz
  chmod -R 700 "$AG_DATA_DIR" || true
else echo "  [skip] 已存在"; fi
ls -la "$AG_DATA_DIR" | head

echo "[4] 烟测 foreignness_score(3 肽)"
AG_DATA_DIR="$AG_DATA_DIR" "$RBIN/Rscript" -e '
  suppressMessages(library(antigen.garnish))
  v <- c("SIINFEKL","KAQPVTQATSF","EEFLNSWML")
  out <- tryCatch(foreignness_score(v, db="human"),
    error=function(e){cat("[SMOKE FAIL]", conditionMessage(e), "\n"); quit(status=3)})
  print(out); cat("[SMOKE OK] rows=", nrow(out), "\n")
' 2>&1 | tail -15
echo "[g-rest] 完成。下一步: GARNISH_ENV=$ENV_DIR AG_DATA_DIR=$AG_DATA_DIR FOREIGN=1 bash run_improve_official.sh"
