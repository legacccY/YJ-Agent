#!/usr/bin/env Rscript
# run_repitope.R — QuantImmuBench §Tier-0  Repitope 免疫原性预测
# 服务项目：quantimmu-bench §工具扩张v2 lever=部署Repitope
#
# 功能：
#   1. 读 repitope_input.csv（prep_input.py 产生，列 Peptide，8-11mer）
#   2. 从 Mendeley Data 下载的 Fragment Library 计算 CPP 特征
#   3. 用 MHCI_Human_MinimumFeatureSet（包内置，32特征）训练 ERT 模型
#   4. 预测各肽的 ImmunogenicityScore（0-1，越高越免疫原）
#   5. 输出 repitope_raw.csv（列 Peptide, ImmunogenicityScore, ImmunogenicityScore.cv）
#
# 前提（必须先手动准备）：
#   A. 安装 Repitope 及依赖（见 NOTES.md §安装）
#   B. 从 Mendeley Data DOI:10.17632/sydw5xnxpt.1 下载两个文件：
#        FragmentLibrary.fst            → --frag-lib 参数
#        MHCI/FeatureDF_Weighted.10000.fst → --feature-df 参数
#   运行 prep_input.py 产生 repitope_input.csv
#
# 用法：
#   Rscript run_repitope.R \
#     --input     HPC/deploy/repitope/repitope_input.csv \
#     --frag-lib  /path/to/FragmentLibrary.fst \
#     --feature-df /path/to/MHCI/FeatureDF_Weighted.10000.fst \
#     --out       HPC/deploy/repitope/repitope_raw.csv \
#     [--smoke N] [--cores N] [--tmp-dir ./repitope_tmp]
#
# API 来源（2026-06-26 核自 github.com/masato-ogishi/Repitope master）：
#   - EpitopePrioritization.R（轻量化改写：去掉 ISM+network，仅保留免疫原性预测）
#   - Immunogenicity.R：Immunogenicity_TrainModels() / Immunogenicity_Predict()
#   - Features.R：Features()
#   - NAMESPACE：Features, Immunogenicity_TrainModels, Immunogenicity_Predict 均已 export
#
# ⚠️ 关键：options(java.parameters) 必须在 library(rJava)/library(extraTrees)
#    之前设置。此脚本在任何 library() 调用前立即设置。

# ===========================================================================
# [0] Java heap 必须最先设置（在加载任何 rJava 相关包之前）
# ===========================================================================
options(java.parameters = c(paste0("-Xmx", Sys.getenv("REPITOPE_XMX_G", "60"), "G"), "-Xms2G"))  # env 可覆盖(本机 31G 内存传 REPITOPE_XMX_G=16; 默认 60 保 HPC 行为不变)


# ===========================================================================
# [1] 参数解析（不依赖 optparse，避免额外依赖）
# ===========================================================================

parse_args <- function() {
  argv <- commandArgs(trailingOnly = TRUE)

  # 脚本目录（Rscript 下 sys.frame()$ofile 为 NULL，从 --file= 参数取）
  script_dir <- tryCatch({
    fa <- commandArgs(FALSE)
    fp <- sub("^--file=", "", fa[grepl("^--file=", fa)])
    if (length(fp) >= 1) dirname(normalizePath(fp[1])) else getwd()
  }, error = function(e) getwd())

  # 默认值
  defaults <- list(
    input      = file.path(script_dir, "repitope_input.csv"),
    frag_lib   = NULL,
    feature_df = NULL,
    out        = file.path(script_dir, "repitope_raw.csv"),
    smoke      = 0L,
    cores      = max(1L, parallel::detectCores(logical = FALSE) - 1L),
    tmp_dir    = file.path(script_dir, "repitope_tmp"),
    seed_set   = 1:5,
    frag_depth = 10000L,
    frag_len_set = 3:8
  )

  # 简单 key=value 解析（--key value）
  i <- 1
  args <- defaults
  while (i <= length(argv)) {
    flag <- argv[i]
    if (flag == "--input")      { args$input      <- argv[i + 1]; i <- i + 2 }
    else if (flag == "--frag-lib")   { args$frag_lib   <- argv[i + 1]; i <- i + 2 }
    else if (flag == "--feature-df") { args$feature_df <- argv[i + 1]; i <- i + 2 }
    else if (flag == "--out")        { args$out        <- argv[i + 1]; i <- i + 2 }
    else if (flag == "--smoke")      { args$smoke      <- as.integer(argv[i + 1]); i <- i + 2 }
    else if (flag == "--cores")      { args$cores      <- as.integer(argv[i + 1]); i <- i + 2 }
    else if (flag == "--tmp-dir")    { args$tmp_dir    <- argv[i + 1]; i <- i + 2 }
    else { cat(sprintf("[run_repitope] 忽略未知参数: %s\n", flag)); i <- i + 1 }
  }

  # 必要参数检查
  if (is.null(args$frag_lib)) {
    stop(paste0(
      "[run_repitope] ERROR: --frag-lib 未提供。\n",
      "  请从 Mendeley Data DOI:10.17632/sydw5xnxpt.1 下载 FragmentLibrary.fst 后传入。\n",
      "  示例: --frag-lib /data/Repitope/FragmentLibrary.fst"
    ))
  }
  if (is.null(args$feature_df)) {
    stop(paste0(
      "[run_repitope] ERROR: --feature-df 未提供。\n",
      "  请从 Mendeley Data DOI:10.17632/sydw5xnxpt.1 下载 MHCI/FeatureDF_Weighted.10000.fst 后传入。\n",
      "  示例: --feature-df /data/Repitope/MHCI/FeatureDF_Weighted.10000.fst"
    ))
  }
  if (!file.exists(args$input)) {
    stop(sprintf(
      "[run_repitope] ERROR: 输入文件不存在: %s\n  请先运行 prep_input.py",
      args$input
    ))
  }
  if (!file.exists(args$frag_lib)) {
    stop(sprintf("[run_repitope] ERROR: fragment library 不存在: %s", args$frag_lib))
  }
  if (!file.exists(args$feature_df)) {
    stop(sprintf("[run_repitope] ERROR: feature DF 不存在: %s", args$feature_df))
  }
  return(args)
}

args <- parse_args()

cat("[run_repitope] === Repitope 免疫原性预测 ===\n")
cat(sprintf("[run_repitope] 输入:         %s\n", args$input))
cat(sprintf("[run_repitope] 片段库:       %s\n", args$frag_lib))
cat(sprintf("[run_repitope] 训练特征DF:   %s\n", args$feature_df))
cat(sprintf("[run_repitope] 输出:         %s\n", args$out))
cat(sprintf("[run_repitope] 烟测模式:     %s\n", if (args$smoke > 0) paste0("前 ", args$smoke, " 个肽") else "关闭（全量）"))
cat(sprintf("[run_repitope] 并行核数:     %d\n", args$cores))
cat(sprintf("[run_repitope] 临时目录:     %s\n", args$tmp_dir))


# ===========================================================================
# [2] 加载包（rJava 相关必须在 options() 之后）
# ===========================================================================

cat("[run_repitope] 加载 R 包...\n")
suppressPackageStartupMessages({
  library(Repitope)      # 包含 MHCI_Human, MHCI_Human_MinimumFeatureSet
  library(data.table)
  library(fst)
})
cat("[run_repitope] 包加载完成\n")

# 内置数据（LazyData = true，library() 后直接可用）
# MHCI_Human:                  data.table, 列 Peptide + Immunogenicity (Positive/Negative)
# MHCI_Human_MinimumFeatureSet: 列表，$MinimumFeatureSet = 32 个特征名的 character vector
cat(sprintf("[run_repitope] MHCI_Human 训练集: %d 肽\n", nrow(MHCI_Human)))
cat(sprintf("[run_repitope] 最小特征集: %d 特征\n",
    length(MHCI_Human_MinimumFeatureSet)))


# ===========================================================================
# [3] 读输入肽序列
# ===========================================================================

cat("[run_repitope] 读输入肽...\n")
pep_dt <- data.table::fread(args$input, encoding = "UTF-8")

# 确认有 Peptide 列
if (!"Peptide" %in% colnames(pep_dt)) {
  stop(sprintf(
    "[run_repitope] ERROR: repitope_input.csv 缺少 Peptide 列，实际列: %s\n  请重跑 prep_input.py",
    paste(colnames(pep_dt), collapse = ", ")
  ))
}
peptideSet <- unique(pep_dt$Peptide)
cat(sprintf("[run_repitope] 输入肽数（去重后）: %d\n", length(peptideSet)))

# 肽长防御性检查（prep_input.py 已过滤，这里再次确认）
pep_lens <- nchar(peptideSet)
invalid <- peptideSet[pep_lens < 8 | pep_lens > 11]
if (length(invalid) > 0) {
  cat(sprintf(
    "[run_repitope] WARNING: %d 个肽不在 8-11mer 范围（prep_input.py 过滤应已排除），跳过: %s ...\n",
    length(invalid), paste(head(invalid, 3), collapse = ", ")
  ), file = stderr())
  peptideSet <- peptideSet[pep_lens >= 8 & pep_lens <= 11]
}

# 烟测截断
if (args$smoke > 0) {
  peptideSet <- head(peptideSet, args$smoke)
  cat(sprintf("[run_repitope] [SMOKE] 截取前 %d 个肽\n", length(peptideSet)))
}

cat(sprintf("[run_repitope] 将预测 %d 个肽\n", length(peptideSet)))


# ===========================================================================
# [4] 加载 Mendeley Data 文件
# ===========================================================================

# 4a. Fragment library（用于 Features() 计算 CPP）
cat("[run_repitope] 加载 fragment library（可能需要数分钟）...\n")
t0 <- proc.time()
fragLibDT <- fst::read_fst(args$frag_lib, as.data.table = TRUE)
cat(sprintf("[run_repitope] fragment library 加载完成: %d 行 × %d 列 (%.1fs)\n",
    nrow(fragLibDT), ncol(fragLibDT), (proc.time() - t0)["elapsed"]))

# 4b. 训练特征 DF（只读 Peptide + 最小特征集所需列，节省内存）
cat("[run_repitope] 加载训练特征 DF（只读最小特征集所需列）...\n")
min_feats <- MHCI_Human_MinimumFeatureSet   # 32 特征名（包内置为 character 向量，非 list）
t0 <- proc.time()
# 只读 Peptide + 32 最小特征列（FST 支持列选择，大幅减少 I/O）
featureDF_full <- fst::read_fst(
  args$feature_df,
  columns = c("Peptide", min_feats),
  as.data.table = TRUE
)
cat(sprintf("[run_repitope] 训练特征 DF 加载完成: %d 行 × %d 列 (%.1fs)\n",
    nrow(featureDF_full), ncol(featureDF_full), (proc.time() - t0)["elapsed"]))

# 过滤到 MHCI_Human 训练集肽
featureDF_train <- featureDF_full[Peptide %in% MHCI_Human$Peptide, ]
metadataDF_train <- MHCI_Human[, .(Peptide, Immunogenicity)]
cat(sprintf("[run_repitope] 训练特征行数: %d（共 MHCI_Human %d 肽）\n",
    nrow(featureDF_train), nrow(metadataDF_train)))
rm(featureDF_full); gc()

# 重叠警告（benchmark 肽与训练集重叠会使 Repitope 警告 "use Immunogenicity_Score instead"）
n_overlap <- length(intersect(peptideSet, MHCI_Human$Peptide))
if (n_overlap > 0) {
  cat(sprintf(
    "[run_repitope] ⚠️ OVERLAP WARNING: %d 个输入肽出现在 MHCI_Human 训练集中\n",
    n_overlap
  ), file = stderr())
  cat("[run_repitope]   Repitope 建议：训练集肽用 Immunogenicity_Score()（内部交叉验证）\n",
      "   而非 Immunogenicity_Predict()（外推）。本 benchmark 为横向对比，接受此偏差，\n",
      "   已在 NOTES.md §HLA-agnostic/caveats 处记录。\n", file = stderr())
}


# ===========================================================================
# [5] 计算新肽的特征（CPP + PeptDesc，使用最小特征集加速）
# ===========================================================================

cat("[run_repitope] 计算新肽特征（可能需要 10-60 分钟）...\n")
dir.create(args$tmp_dir, showWarnings = FALSE, recursive = TRUE)

t0 <- proc.time()
# Features() 返回长度 1 的列表（当 fragDepth 为单一值时）
featureDT_new_list <- Features(
  peptideSet   = peptideSet,
  fragLib      = fragLibDT,
  aaIndexIDSet = "all",
  fragLenSet   = args$frag_len_set,     # 3:8（与 MHCI_Human_MinimumFeatureSet 训练一致）
  fragDepth    = args$frag_depth,       # 10000
  fragLibType  = "Weighted",
  featureSet   = MHCI_Human_MinimumFeatureSet,  # 32 特征，大幅减少计算量
  seedSet      = args$seed_set,
  coreN        = args$cores,
  tmpDir       = args$tmp_dir
)
featureDT_new <- featureDT_new_list[[1]]
cat(sprintf("[run_repitope] 特征计算完成: %d 肽 × %d 特征 (%.1fs)\n",
    nrow(featureDT_new), ncol(featureDT_new), (proc.time() - t0)["elapsed"]))
rm(featureDT_new_list, fragLibDT); gc()


# ===========================================================================
# [6] 训练 ERT 模型（在 MHCI_Human 上）
# ===========================================================================

cat("[run_repitope] 训练 ERT 模型（5 seeds × 5-fold = 25 次，可能需要 5-20 分钟）...\n")
t0 <- proc.time()
ert_models <- Immunogenicity_TrainModels(
  featureDF  = featureDF_train,
  metadataDF = metadataDF_train,
  featureSet = MHCI_Human_MinimumFeatureSet,   # 32 特征
  seedSet    = args$seed_set,
  coreN      = args$cores
)
cat(sprintf("[run_repitope] ERT 模型训练完成 (%.1fs)\n",
    (proc.time() - t0)["elapsed"]))
rm(featureDF_train, metadataDF_train); gc()


# ===========================================================================
# [7] 预测新肽的免疫原性评分
# ===========================================================================

cat("[run_repitope] 预测 ImmunogenicityScore...\n")
t0 <- proc.time()
scoreDT_list <- Immunogenicity_Predict(
  externalFeatureDFList = list(featureDT_new),
  trainModelResults     = ert_models
)
# 返回列表，每个元素对应一个 dataset（此处只有 1 个）
# 列：Peptide, ImmunogenicityScore, ImmunogenicityScore.cv
scoreDT <- scoreDT_list[[1]]
cat(sprintf("[run_repitope] 预测完成: %d 行 (%.1fs)\n",
    nrow(scoreDT), (proc.time() - t0)["elapsed"]))

# 统计摘要
cat(sprintf(
  "[run_repitope] ImmunogenicityScore 摘要: min=%.4f, median=%.4f, max=%.4f\n",
  min(scoreDT$ImmunogenicityScore, na.rm = TRUE),
  median(scoreDT$ImmunogenicityScore, na.rm = TRUE),
  max(scoreDT$ImmunogenicityScore, na.rm = TRUE)
))


# ===========================================================================
# [8] 写输出
# ===========================================================================

cat(sprintf("[run_repitope] 写输出: %s\n", args$out))
out_dir <- dirname(args$out)
dir.create(out_dir, showWarnings = FALSE, recursive = TRUE)

# 只保留 Peptide + ImmunogenicityScore（cv 列保留，供参考）
out_cols <- c("Peptide", "ImmunogenicityScore", "ImmunogenicityScore.cv")
out_cols <- intersect(out_cols, colnames(scoreDT))
data.table::fwrite(scoreDT[, ..out_cols], args$out, encoding = "UTF-8")

cat(sprintf("[run_repitope] ✔ 写出 %d 行 → %s\n", nrow(scoreDT), args$out))
cat("[run_repitope] 列说明：\n")
cat("  Peptide              : 肽序列（8-11mer）\n")
cat("  ImmunogenicityScore  : 免疫原性概率 [0-1]，越高越免疫原（直接用，无需翻转）\n")
cat("  ImmunogenicityScore.cv: 跨模型变异系数（CV），越小越稳定\n")
cat("[run_repitope] 完成\n")
