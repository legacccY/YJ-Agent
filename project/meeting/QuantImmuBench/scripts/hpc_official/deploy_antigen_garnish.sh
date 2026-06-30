#!/usr/bin/env bash
# ===========================================================================
# deploy_antigen_garnish.sh — 在 HPC 部署 antigen.garnish (供 IMPROVE Foreigness 真算)
# 服务: quantimmu-bench Phase0 IMPROVE 档II (lever=IMPROVE)。主线串行在 HPC 跑。
#
# ⚠️⚠️ 时序提醒: 此刻 envs/andy90_r 正被 Repitope 部署占用做 conda install。
#   本脚本默认建【独立 env envs/garnish_r】, 不碰 andy90_r, 避免 conda solve 撞车。
#   但若你要复用 andy90_r, 务必等 Repitope 的 conda install 完全结束再跑 (错开 solve)。
#
# 官方安装 (antigen.garnish 2, github.com/andrewrech/antigen.garnish):
#   R pkg : remotes::install_github("andrewrech/antigen.garnish")
#   数据包: curl S3 tarball -> $AG_DATA_DIR (含 IEDB fasta + blast 参考)
#   外部  : R>=3.5, Biostrings, GNU parallel, ncbi-blast+ (blastp, foreignness 必需)
#           [mhcflurry/netMHC 是 full predict 用, foreignness_score 大概率不需 -> 见 TODO]
#
# foreignness 出处: IMPROVE_paper/.../01_Foreginess_score_*.R: foreignness_score(pep, db="human")
# 复现零偏离: 装官方版本, 不改算法。
# ===========================================================================
set -euo pipefail

BASE="/gpfs/work/bio/jiayu2403/quantimmu"
ENV_DIR="$BASE/envs/garnish_r"          # 独立 env, 不撞 andy90_r
AG_DATA_DIR="$BASE/ext_tools/antigen.garnish"   # 数据包落点
AG_TARBALL="https://s3.amazonaws.com/get.rech.io/antigen.garnish-2.3.0.tar.gz"

echo "================ deploy antigen.garnish ================"
echo "ENV=$ENV_DIR  AG_DATA_DIR=$AG_DATA_DIR"

module load miniconda3/22.11.1-gcc-8.5.0-l4fo6ta
source "$(conda info --base)/etc/profile.d/conda.sh"

# ---------- 1. 建独立 R env (预编译, 避源码编译) ----------
if [ ! -d "$ENV_DIR" ]; then
  echo "[1] conda create garnish_r (conda-forge + bioconda 预编译包)"
  conda create -y -p "$ENV_DIR" -c conda-forge -c bioconda \
    "r-base>=4.1" r-remotes r-magrittr r-data.table r-stringr r-testthat \
    r-biocmanager bioconductor-biostrings blast parallel
else
  echo "[1] env 已存在, 跳过 create"
fi
conda activate "$ENV_DIR"
echo "  R: $(which R)  blastp: $(which blastp 2>/dev/null || echo 'MISSING-TODO')"

# ---------- 2. 装 antigen.garnish R 包 ----------
echo "[2] install_github antigen.garnish"
Rscript -e 'if(!requireNamespace("antigen.garnish",quietly=TRUE)) remotes::install_github("andrewrech/antigen.garnish", upgrade="never"); cat("antigen.garnish:", as.character(packageVersion("antigen.garnish")), "\n")'

# ---------- 3. 下数据包 ----------
if [ ! -d "$AG_DATA_DIR" ] || [ -z "$(ls -A "$AG_DATA_DIR" 2>/dev/null)" ]; then
  echo "[3] 下载数据包 -> $AG_DATA_DIR"
  mkdir -p "$AG_DATA_DIR"
  cd "$(dirname "$AG_DATA_DIR")"
  # tarball 解出目录名 antigen.garnish/; 直接落到 ext_tools/
  curl -fsSL "$AG_TARBALL" | tar -xvz
  chmod -R 700 "$AG_DATA_DIR" || true
else
  echo "[3] 数据包已存在, 跳过"
fi
export AG_DATA_DIR

# ---------- 4. 烟测 foreignness_score ----------
echo "[4] 烟测 foreignness_score (3 条肽)"
AG_DATA_DIR="$AG_DATA_DIR" Rscript -e '
suppressMessages(library(antigen.garnish))
v <- c("SIINFEKL","KAQPVTQATSF","EEFLNSWML")
out <- tryCatch(foreignness_score(v, db="human"),
  error=function(e){cat("[SMOKE FAIL]", conditionMessage(e), "\n"); quit(status=3)})
print(out)
cat("[SMOKE OK] rows=", nrow(out), "\n")
'

echo ""
echo "===== antigen.garnish 部署完成 ====="
echo "env=$ENV_DIR ; AG_DATA_DIR=$AG_DATA_DIR"
echo "下一步: GARNISH_ENV=$ENV_DIR AG_DATA_DIR=$AG_DATA_DIR bash run_improve_official.sh"
echo ""
echo "TODO/盲区 (查不到则主线跑时暴露):"
echo " - foreignness_score 是否强依赖 mhcflurry/netMHC: 官方 README 列为 full-predict 依赖,"
echo "   foreignness 路径大概率只需 blastp+IEDB(数据包内)。若 [4] 烟测报缺 mhcflurry/netMHC:"
echo "   pip install mhcflurry (env 内) + 把 $BASE/ext_tools/netMHCpan-4.1 加 PATH 再试。"
echo " - 若 conda solve 与 Repitope 的 andy90_r 撞 -> 等 Repitope 完再跑本脚本。"
