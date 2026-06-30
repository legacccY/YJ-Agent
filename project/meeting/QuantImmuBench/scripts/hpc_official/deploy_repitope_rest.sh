#!/usr/bin/env bash
# =============================================================================
# deploy_repitope_rest.sh — 续装 Repitope（[1/4] conda 已装好后跑）
# =============================================================================
# 背景：deploy_repitope.sh 的 [1/4] conda install（openjdk8/r-rjava/r-fst/
#   r-devtools/r-biocmanager）已成功；[3/4] install_github 撞 GitHub API 限流
#   403（HPC 共享 IP 60/hr 用尽）。本脚本绕 API：git clone（git 协议，不走 API
#   rate limit）+ devtools::install_local，再下 Mendeley 数据集。
# 主线串行执行：
#   module load miniconda3/... && source .../conda.sh && bash deploy_repitope_rest.sh
# =============================================================================
set -euo pipefail

BASE=/gpfs/work/bio/jiayu2403/quantimmu
ENV="$BASE/envs/andy90_r"
RBIN="$ENV/bin"
DATADIR="$BASE/tools_repos/Repitope_data"
SRC="$BASE/tools_repos/Repitope_src"
export R_LIBS_USER="$ENV/lib/R/library"

mkdir -p "$DATADIR"

echo "==================================================================="
echo "[rest] $($RBIN/R --version | head -1)"
echo "[rest] 确认 conda 装的依赖在位"
"$RBIN/Rscript" -e 'for(p in c("devtools","rJava","fst","BiocManager")) cat(p, requireNamespace(p,quietly=TRUE), "\n")'

# ---------------------------------------------------------------------------
# 3) git clone（绕 GitHub API 限流）+ install_local
# ---------------------------------------------------------------------------
echo "[3/4] git clone masato-ogishi/Repitope（git 协议，不走 API rate limit）"
if [ -d "$SRC/.git" ]; then
  echo "  [skip clone] 已存在 $SRC，git pull 更新"
  git -C "$SRC" pull --ff-only || echo "  [warn] pull 失败，用现有"
else
  git clone --depth 1 https://github.com/masato-ogishi/Repitope.git "$SRC"
fi

echo "[3/4] devtools::install_local（dependencies=TRUE 走 CRAN/Bioc，不走 GitHub API）"
"$RBIN/Rscript" -e '
  options(repos="https://cloud.r-project.org")
  Sys.setenv(R_REMOTES_UPGRADE="never")
  devtools::install_local(Sys.getenv("REPITOPE_SRC"), upgrade="never", dependencies=TRUE, force=TRUE)
  stopifnot(requireNamespace("Repitope", quietly=TRUE))
  cat("[OK] Repitope 安装成功 version:", as.character(packageVersion("Repitope")), "\n")
' REPITOPE_SRC="$SRC" 2>&1 || { echo "[FAIL] install_local 失败（看上方 R 报错；可能有 GitHub-only 依赖）"; exit 1; }

# ---------------------------------------------------------------------------
# 4) 下 Mendeley 预算数据集
# ---------------------------------------------------------------------------
echo "[4/4] 下 Mendeley 数据集 → $DATADIR"
dl_mendeley () {  # $1=dataset_id $2=version $3=filename $4=dest
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
echo "[rest] 数据集："
ls -la "$DATADIR"
echo "[rest] 自检 library(Repitope)："
"$RBIN/Rscript" -e '
  suppressMessages(library(Repitope))
  cat("Repitope OK\n")
  cat("MHCI_Human rows:", tryCatch(nrow(MHCI_Human), error=function(e) NA), "\n")
'
echo "[rest] 部署 OK → 下一步 bash run_repitope_official.sh"
echo "==================================================================="
