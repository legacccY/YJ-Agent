#!/usr/bin/env bash
# =============================================================================
# deploy_repitope_rest2.sh — 修 rJava 加载 + install_local 路径 + 下数据集
# =============================================================================
# rest 跑出两坑：① rJava FALSE（conda 装了 r-rjava 但 R 找不到 libjvm）
# ② install_local("") 因 REPITOPE_SRC 没作为 env 传进去（Rscript -e 后接的是位置参）。
# git clone 已成（Repitope_src 在）。本脚本：配 JAVA_HOME/LD_LIBRARY_PATH + javareconf
# 让 rJava 可加载 → install_local(显式路径) → 下 Mendeley 数据集。
# 主线串行：module load miniconda3/... && source .../conda.sh && bash deploy_repitope_rest2.sh
# =============================================================================
set -uo pipefail

BASE=/gpfs/work/bio/jiayu2403/quantimmu
ENV="$BASE/envs/andy90_r"
RBIN="$ENV/bin"
DATADIR="$BASE/tools_repos/Repitope_data"
SRC="$BASE/tools_repos/Repitope_src"
export R_LIBS_USER="$ENV/lib/R/library"

# ---------------------------------------------------------------------------
# rJava：定位 conda openjdk 的 libjvm.so，配 JAVA_HOME/LD_LIBRARY_PATH + javareconf
# ---------------------------------------------------------------------------
LIBJVM=$(find "$ENV" -name libjvm.so 2>/dev/null | head -1)
echo "[java] libjvm.so = ${LIBJVM:-(未找到)}"
[ -z "$LIBJVM" ] && { echo "[FAIL] conda env 内无 libjvm.so，openjdk 没装好"; exit 1; }
export JAVA_HOME="$ENV"
export LD_LIBRARY_PATH="$(dirname "$LIBJVM"):$ENV/lib:${LD_LIBRARY_PATH:-}"
echo "[java] JAVA_HOME=$JAVA_HOME"
echo "[java] R CMD javareconf ..."
"$RBIN/R" CMD javareconf JAVA_HOME="$JAVA_HOME" \
  JAVA="$ENV/bin/java" JAVAC="$ENV/bin/javac" JAR="$ENV/bin/jar" JAVAH="$ENV/bin/javah" 2>&1 | tail -4 || echo "[warn] javareconf 非零（继续试）"

echo "[java] 测 rJava 加载 + .jinit"
"$RBIN/Rscript" -e 'library(rJava); .jinit(); cat("[OK] rJava 加载+JVM 起成功\n")' || {
  echo "[FAIL] rJava 仍加载不了。可能要重装 r-rjava 让其链当前 JVM。"
  echo "       试: conda install -p $ENV -c conda-forge -y --force-reinstall r-rjava"
  exit 1
}

# ---------------------------------------------------------------------------
# install_local（显式路径，非 env）
# ---------------------------------------------------------------------------
echo "[3/4] devtools::install_local('$SRC')"
[ -d "$SRC" ] || { echo "[FAIL] 缺 $SRC（git clone 没成）"; exit 1; }
"$RBIN/Rscript" -e "
  options(repos='https://cloud.r-project.org')
  Sys.setenv(R_REMOTES_UPGRADE='never')
  devtools::install_local('$SRC', upgrade='never', dependencies=TRUE, force=TRUE)
  stopifnot(requireNamespace('Repitope', quietly=TRUE))
  cat('[OK] Repitope 安装成功 version:', as.character(packageVersion('Repitope')), '\n')
" 2>&1 | tail -25
"$RBIN/Rscript" -e 'stopifnot(requireNamespace("Repitope",quietly=TRUE))' || { echo "[FAIL] Repitope 未装上（看上方 R 报错）"; exit 1; }

# ---------------------------------------------------------------------------
# 下 Mendeley 数据集
# ---------------------------------------------------------------------------
echo "[4/4] 下 Mendeley 数据集 → $DATADIR"
mkdir -p "$DATADIR"
dl_mendeley () {  # ds ver fn dest
  local ds="$1" ver="$2" fn="$3" dest="$4"
  if [[ -s "$dest" ]]; then echo "  [skip] 已存在 $dest ($(du -h "$dest"|cut -f1))"; return; fi
  echo "  [get] $fn (dataset $ds v$ver)"
  local url
  url=$(curl -s "https://data.mendeley.com/public-api/datasets/${ds}/files?folder_id=root&version=${ver}" \
        | python3 -c "import sys,json
for f in json.load(sys.stdin):
    if f['filename']=='${fn}':
        print(f['content_details']['download_url']); break")
  [[ -z "$url" ]] && { echo "  [FAIL] 拿不到 $fn 下载链接"; return 1; }
  curl -L --fail --retry 5 --retry-delay 10 -o "$dest" "$url"
  ls -la "$dest"
}
dl_mendeley sydw5xnxpt 1 FragmentLibrary_TCRSet_Public_RepitopeV3.fst "$DATADIR/FragmentLibrary.fst"
dl_mendeley 2hp96k6m2c 2 FeatureDF_MHCI_Weighted.10000.fst            "$DATADIR/FeatureDF_MHCI_Weighted.10000.fst"

echo "==================================================================="
ls -la "$DATADIR"
"$RBIN/Rscript" -e 'suppressMessages(library(Repitope)); cat("Repitope OK; MHCI_Human rows:", tryCatch(nrow(MHCI_Human),error=function(e)NA), "\n")'
echo "[rest2] 部署 OK → 下一步 bash run_repitope_official.sh"
echo "==================================================================="
