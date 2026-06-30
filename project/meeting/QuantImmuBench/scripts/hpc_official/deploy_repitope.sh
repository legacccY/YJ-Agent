#!/usr/bin/env bash
# =============================================================================
# ⛔ HPC 路线已 DEFER（2026-06-30）— 不再用此脚本，保留备查
# -----------------------------------------------------------------------------
# 原因：HPC conda 装 Repitope 依赖彻底堵死——无 libmamba/mamba，classic solver 啃不动
#   caret+mlr+msa+19 依赖（5 次迭代全失败：既有 env 27min 不收敛 / 小批 caret 600s 超时 /
#   干净 env 25min rc124）。用户拍板改本机 Windows R 跑。
# 本脚本 + deploy_repitope_rest{,.2,.3,.4,.5}.sh = 当时 HPC conda 各次尝试，均失败，仅留参考。
# ✅ 现行路线 = 本机 Windows R：deploy_repitope_local.R → run_repitope_local.sh → parse_repitope_official.py
#    （且本机部署 2026-06-26 已跑通，见 HPC/deploy/repitope/NOTES.md + repitope_raw.csv）
# =============================================================================
# deploy_repitope.sh — 官方 Repitope (masato-ogishi/Repitope) HPC 部署【DEFER】
# =============================================================================
# 主线串行执行（agent 只写不跑）。在 XJTLU HPC 登录节点 (DTN) 跑：
#   bash deploy_repitope.sh
#
# Repitope = HLA-agnostic MHC-I 免疫原性打分（in silico TCR-peptide contact
# potential profiling，Ogishi & Yotsuyanagi 2019, Front Immunol）。R 包 + rJava +
# 两个 Mendeley 预算数据集（fragment library + 训练 feature DF）。
#
# ── 可行性核查结论（agent 已只读核 HPC，2026-06-30）──────────────────────────
#   磁盘    : /gpfs 余 127T，quantimmu 用 90G → 1.5GB 下载毫无压力 ✅
#   R 环境  : envs/andy90_r = R 4.1.3（已有 data.table / Biostrings / tidyverse）✅
#   缺包    : devtools / fst / rJava / BiocManager / Repitope ❌ → 本脚本装
#   Java    : 系统 /usr/bin/java = openjdk 1.8.0_332（rJava 需要，下面用 conda 自带 JDK 规避编译）
#   联网    : DTN 可达 Mendeley + GitHub (HTTP 200) ✅ → install_github + 下数据集都行
#   算力    : 登录节点 48 核 / 125G RAM ✅（Features 步是重 CPU+Java，非 GPU）
#   现状    : HPC 完全无 Repitope / 无 fragment library → 全新部署
#
# ⚠️ rJava 是最大风险点：源码编译 rJava 需 JDK 头文件 (jni.h)，系统 java 可能仅 JRE。
#    本脚本优先用 conda 装预编译的 r-rjava + openjdk（自带 JDK，零编译），最稳。
#    若该环境无 conda → 走 install.packages + R CMD javareconf 回退（高风险，见末尾注）。
#
# ⚠️ 数据集下载 = 对外大流量传输（1.5GB）。按组合台铁律属「HPC 上传/下载」拍板点，
#    主线执行前确认一次即可（DTN 下载，不占 GPU 计费）。
# =============================================================================
set -euo pipefail

BASE=/gpfs/work/bio/jiayu2403/quantimmu
ENV="$BASE/envs/andy90_r"
RBIN="$ENV/bin"
DATADIR="$BASE/tools_repos/Repitope_data"      # 存 fragment library + feature DF
REPO_TMP="$BASE/tools_repos/Repitope_src"      # install_github 临时（可选）
export R_LIBS_USER="$ENV/lib/R/library"

echo "==================================================================="
echo "[deploy_repitope] BASE=$BASE  ENV=$ENV"
echo "[deploy_repitope] $($RBIN/R --version | head -1)"
echo "==================================================================="

mkdir -p "$DATADIR"

# ---------------------------------------------------------------------------
# 1) 装 R 依赖。优先 conda（预编译 r-rjava/openjdk 零编译，最稳）；无 conda 回退 CRAN。
# ---------------------------------------------------------------------------
if command -v conda >/dev/null 2>&1; then
  echo "[1/4] conda 可用 → 装预编译 openjdk + r-rjava + r-fst + r-devtools + r-biocmanager"
  conda install -p "$ENV" -c conda-forge -y \
      openjdk=8 r-rjava r-fst r-devtools r-biocmanager
else
  echo "[1/4][回退] 无 conda → CRAN 装 fst/devtools/BiocManager + javareconf rJava（高风险）"
  echo "           系统 JDK 头文件不全时 rJava 会编译失败 → 那时改用 conda 或让主线拍板换路。"
  # JAVA_HOME 自动探测（系统 openjdk）
  export JAVA_HOME="$(dirname "$(dirname "$(readlink -f "$(command -v java)")")")"
  echo "           JAVA_HOME=$JAVA_HOME"
  "$RBIN/R" CMD javareconf || echo "[WARN] javareconf 失败，rJava 大概率装不上"
  "$RBIN/Rscript" -e 'install.packages(c("fst","devtools","BiocManager","rJava"), repos="https://cloud.r-project.org")'
fi

# ---------------------------------------------------------------------------
# 2) 装 Bioconductor 依赖（Biostrings 已有；保险再确认 + 补 Repitope 可能依赖的 Bioc 包）
# ---------------------------------------------------------------------------
echo "[2/4] 确认 Bioconductor 依赖 (Biostrings 已存在)"
"$RBIN/Rscript" -e 'if(!requireNamespace("Biostrings",quietly=TRUE)) BiocManager::install("Biostrings", update=FALSE, ask=FALSE)'

# ---------------------------------------------------------------------------
# 3) install_github 装 Repitope 本体
# ---------------------------------------------------------------------------
echo "[3/4] devtools::install_github('masato-ogishi/Repitope')"
"$RBIN/Rscript" -e '
  options(repos="https://cloud.r-project.org")
  Sys.setenv(R_REMOTES_UPGRADE="never")
  devtools::install_github("masato-ogishi/Repitope", upgrade="never", dependencies=TRUE)
  stopifnot(requireNamespace("Repitope", quietly=TRUE))
  cat("[OK] Repitope 安装成功，version:", as.character(packageVersion("Repitope")), "\n")
'

# ---------------------------------------------------------------------------
# 4) 下 Mendeley 预算数据集（README 工作流 #3/#4 必需）
#    - FragmentLibrary_TCRSet_Public_RepitopeV3.fst  (122MB) ← fragLib，算新肽特征用
#    - FeatureDF_MHCI_Weighted.10000.fst             (1.4GB) ← 训练 feature DF（README 用全量版，列完整最保险）
#    MHCI_Human + MHCI_Human_MinimumFeatureSet 随包内置，无需下。
#    （lean 回退：用 RepitopeV3 的 5.1MB FeatureDF_MHCI_Weighted.10000_RepitopeV3.fst，
#      但列可能不全，若 Immunogenicity_Score 报列缺失再换全量——故默认直接下全量。）
# ---------------------------------------------------------------------------
echo "[4/4] 下 Mendeley 数据集 → $DATADIR"

dl_mendeley () {  # $1=dataset_id  $2=version  $3=filename  $4=dest
  local ds="$1" ver="$2" fn="$3" dest="$4"
  if [[ -s "$dest" ]]; then echo "  [skip] 已存在 $dest"; return; fi
  echo "  [get] $fn  (dataset $ds v$ver)"
  local url
  url=$(curl -s "https://data.mendeley.com/public-api/datasets/${ds}/files?folder_id=root&version=${ver}" \
        | python3 -c "import sys,json
for f in json.load(sys.stdin):
    if f['filename']=='${fn}':
        print(f['content_details']['download_url']); break")
  if [[ -z "$url" ]]; then echo "  [FAIL] 拿不到 $fn 下载链接"; return 1; fi
  curl -L --fail -o "$dest" "$url"
  ls -la "$dest"
}

dl_mendeley sydw5xnxpt 1 FragmentLibrary_TCRSet_Public_RepitopeV3.fst "$DATADIR/FragmentLibrary.fst"
dl_mendeley 2hp96k6m2c 2 FeatureDF_MHCI_Weighted.10000.fst            "$DATADIR/FeatureDF_MHCI_Weighted.10000.fst"

echo "==================================================================="
echo "[deploy_repitope] 完成。数据集："
ls -la "$DATADIR"
echo "[deploy_repitope] 自检 library(Repitope) + 内置数据集："
"$RBIN/Rscript" -e '
  suppressMessages(library(Repitope))
  cat("Repitope OK\n")
  cat("MHCI_Human rows:", tryCatch(nrow(MHCI_Human), error=function(e) NA), "\n")
  cat("MHCI_Human_MinimumFeatureSet len:", tryCatch(length(MHCI_Human_MinimumFeatureSet), error=function(e) NA), "\n")
'
echo "[deploy_repitope] 部署 OK → 下一步 bash run_repitope_official.sh"
echo "==================================================================="
