#!/usr/bin/env Rscript
# =============================================================================
# deploy_repitope_local.R — 本机 Windows R 4.3.3 Repitope 部署（幂等：已装则跳过）
# =============================================================================
# 主线串行执行（agent 只写不跑）：
#   "E:/R-4.3.3/bin/Rscript.exe" scripts/hpc_official/deploy_repitope_local.R
#
# ★★ 重要事实（agent 2026-06-30 核实）★★
# 本机 Repitope 部署【已于 2026-06-26 完成且跑通】，证据：
#   - HPC/deploy/repitope/mendeley_data/ 已有两数据集（FragmentLibrary 122MB +
#     FeatureDF_MHCI_Weighted.10000_RepitopeV3.fst 5.1MB + ScoreDF 895KB）
#   - HPC/deploy/repitope/repitope_raw.csv = 7437 肽已成功打分（列 Peptide,
#     ImmunogenicityScore, ImmunogenicityScore.cv）→ R 包 + rJava + Repitope 全就位
#   - HPC/deploy/repitope/install_deps.R 当时已跑成功（install_deps.log）
# 故本脚本默认只【验证】，库在则直接跳过安装。HPC conda 路堵死与本机无关——
# 本机走 install.packages 拿 CRAN Windows 预编译二进制，绕开 conda solve+源码编译双墙。
#
# 仅当 library(Repitope) 失败（如换机/库被清）才真装。装的是 2026-06-26 验证过的同一套依赖。
# =============================================================================

options(repos = c(CRAN = "https://cloud.r-project.org"))
options(timeout = 1800)
# Java heap 设小（本机内存有限，551 肽够用；-Xmx 是上限非预留）。注：run 阶段的
# HPC/deploy/repitope/run_repitope.R 行 39 自带 -Xmx60G（2026-06-26 在本机跑通过，
# 是上限不是占用，无 OOM 风险）；此处仅 deploy 验证用小堆。
options(java.parameters = c("-Xmx8G", "-Xms1G"))

cat("=== [deploy_local] Repitope 本机部署/验证 ===\n")
cat("R:", R.version.string, "\n")

# ---------------------------------------------------------------------------
# 0) 幂等检查：Repitope 已装则只验证 rJava + 数据集，跳过安装
# ---------------------------------------------------------------------------
already <- requireNamespace("Repitope", quietly = TRUE)
if (already) {
  suppressPackageStartupMessages(library(Repitope))
  cat(sprintf("[deploy_local] ✔ Repitope 已装 v%s —— 跳过安装\n",
              as.character(packageVersion("Repitope"))))
} else {
  cat("[deploy_local] Repitope 未装 → 开始安装（2026-06-26 验证过的依赖集）\n")

  # 1) Bioconductor：Biostrings + msa + S4Vectors（Windows 二进制）
  cat("[deploy_local] Step1 BiocManager + Bioc 包\n")
  if (!requireNamespace("BiocManager", quietly = TRUE)) install.packages("BiocManager")
  BiocManager::install(c("Biostrings", "msa", "S4Vectors"), update = FALSE, ask = FALSE)

  # 2) CRAN 依赖（Windows 预编译二进制，快）。与 install_deps.R 一致 + 列出的 22 必需包。
  cat("[deploy_local] Step2 CRAN 依赖\n")
  cran <- c(
    "devtools", "data.table", "fst", "readr",
    "rJava", "extraTrees",
    "mlr", "caret", "BBmisc", "pbapply",
    "foreach", "doParallel", "doSNOW",
    "purrr", "magrittr", "stringr", "stringi", "stringdist",
    "igraph", "Peptides", "seqinr",
    "ggplot2", "ggpubr", "ggsci", "gridExtra", "RColorBrewer", "scales",
    "matrixStats", "psych", "zoo", "rlecuyer",
    "car", "DescTools", "cvAUC", "pROC", "precrec",
    "survminer", "survival", "tidyr", "VennDiagram"
  )
  for (p in cran) {
    if (!requireNamespace(p, quietly = TRUE)) {
      cat("  install:", p, "\n")
      tryCatch(install.packages(p),
               error = function(e) cat("  FAIL", p, conditionMessage(e), "\n"))
    } else cat("  ok:", p, "\n")
  }

  # 3) rJava 验证（Java 17 Temurin 须在 PATH；extraTrees 后端需要）
  cat("[deploy_local] Step3 rJava .jinit 验证\n")
  tryCatch({ library(rJava); .jinit(); cat("  rJava OK\n") },
           error = function(e) cat("  rJava FAIL:", conditionMessage(e),
                                   "\n  → 确认 JAVA_HOME 指向 JDK17, PATH 含 %JAVA_HOME%\\bin\n"))

  # 4) Repitope 本体：优先本地源（HPC/deploy/repitope 若已 clone），否则 install_github
  cat("[deploy_local] Step4 安装 Repitope\n")
  Sys.setenv(R_REMOTES_UPGRADE = "never")
  local_src <- "D:/YJ-Agent/project/meeting/QuantImmuBench/tools_repos/Repitope_src_local"
  if (dir.exists(file.path(local_src, "DESCRIPTION")) || file.exists(file.path(local_src, "DESCRIPTION"))) {
    cat("  install_local:", local_src, "\n")
    devtools::install_local(local_src, dependencies = FALSE, upgrade = "never")
  } else {
    cat("  install_github('masato-ogishi/Repitope')\n")
    devtools::install_github("masato-ogishi/Repitope", upgrade = "never")
  }
  stopifnot(requireNamespace("Repitope", quietly = TRUE))
  suppressPackageStartupMessages(library(Repitope))
  cat(sprintf("[deploy_local] ✔ Repitope 安装成功 v%s\n",
              as.character(packageVersion("Repitope"))))
}

# ---------------------------------------------------------------------------
# 验证：rJava .jinit + 内置数据集 + Mendeley 数据集就位
# ---------------------------------------------------------------------------
cat("[deploy_local] 验证 rJava ...\n")
tryCatch({ library(rJava); .jinit(); cat("  rJava .jinit OK\n") },
         error = function(e) cat("  ⚠️ rJava FAIL:", conditionMessage(e), "\n"))

cat("[deploy_local] 验证内置数据集 ...\n")
cat("  MHCI_Human 行:", tryCatch(nrow(MHCI_Human), error = function(e) NA), "\n")
cat("  MHCI_Human_MinimumFeatureSet 长度:",
    tryCatch(length(MHCI_Human_MinimumFeatureSet), error = function(e) NA), "\n")

DATA <- "D:/YJ-Agent/project/meeting/QuantImmuBench/HPC/deploy/repitope/mendeley_data"
frag <- file.path(DATA, "FragmentLibrary_TCRSet_Public_RepitopeV3.fst")
feat <- file.path(DATA, "FeatureDF_MHCI_Weighted.10000_RepitopeV3.fst")
cat("[deploy_local] 验证 Mendeley 数据集 ...\n")
for (f in c(frag, feat)) {
  if (file.exists(f)) cat(sprintf("  ✔ %s (%.1f MB)\n", basename(f), file.info(f)$size / 1e6))
  else cat(sprintf("  ✗ 缺失: %s（从 Mendeley DOI:10.17632/sydw5xnxpt.1 下载）\n", f))
}

cat("[deploy_local] 完成。下一步: bash scripts/hpc_official/run_repitope_local.sh\n")
