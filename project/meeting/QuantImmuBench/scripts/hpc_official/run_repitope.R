#!/usr/bin/env Rscript
# =============================================================================
# run_repitope.R — 官方 Repitope 在 551 唯一肽上算 MHC-I 免疫原性分
# =============================================================================
# 由 run_repitope_official.sh 调用（主线串行执行；agent 只写不跑）。
#
# 完全按官方 README 工作流（复现零偏离）：
#   2. Features()           — 用 fragment library 给「新肽」算 TCR-contact 特征（重 CPU+Java 步）
#   3. Immunogenicity_Score()— 在 MHCI_Human 训练集上建 ERT 模型，对全部 featureDF 打分
#                              输出列已确认：Peptide, ImmunogenicityScore, ImmunogenicityScore.cv
#                              （ScoreDF_MHCI_RepitopeV3.csv 表头核实）
#
# 用 Features+Immunogenicity_Score 两步（两者 I/O 均文档化、列名已确认），不用
# EpitopePrioritization 包装器——后者 Value 段官方未文档化，输出文件名/结构不确定，
# 风险更高。两步路径与 EpitopePrioritization 内部逻辑等价（官方 README 同时给了两种）。
#
# 方向：ImmunogenicityScore 越高越免疫原（probability estimate，约 0-1），无翻转。
#
# 用法：
#   Rscript run_repitope.R <peptide_csv> <fraglib_fst> <featureDF_fst> <out_dir> [coreN]
#     peptide_csv : 含 peptide 列（uniq_pep.csv，551 行）
#     fraglib_fst : FragmentLibrary.fst (122MB)
#     featureDF_fst: FeatureDF_MHCI_Weighted.10000.fst (训练特征, 1.4GB)
#     out_dir     : 输出目录（写 Repitope_scores.csv + 中间文件）
#     coreN       : 并行核数，默认 8（勿过大——issue#7 报过 "cannot create GC thread"）
# =============================================================================

args <- commandArgs(trailingOnly = TRUE)
if (length(args) < 4) stop("用法: Rscript run_repitope.R <peptide_csv> <fraglib_fst> <featureDF_fst> <out_dir> [coreN]")
pep_csv     <- args[1]
fraglib_fst <- args[2]
feature_fst <- args[3]
out_dir     <- args[4]
coreN       <- if (length(args) >= 5) as.integer(args[5]) else 8L

dir.create(out_dir, showWarnings = FALSE, recursive = TRUE)
tmp_dir <- file.path(out_dir, "tmp"); dir.create(tmp_dir, showWarnings = FALSE)

suppressMessages({
  library(Repitope)
  library(data.table)
  library(fst)
})

cat("[run_repitope] Repitope", as.character(packageVersion("Repitope")),
    "| coreN =", coreN, "\n")

# --- 读 551 唯一肽 -----------------------------------------------------------
pepDT  <- fread(pep_csv)
stopifnot("peptide" %in% names(pepDT))
ourPeps <- unique(toupper(trimws(pepDT$peptide)))
ourPeps <- ourPeps[nchar(ourPeps) >= 8 & nchar(ourPeps) <= 11]   # MHC-I 8-11mer
cat("[run_repitope] 输入唯一肽 =", length(ourPeps), "(8-11mer)\n")

# 训练集重叠提示（README 警告：不建议对建模用肽打分；这里不静默丢，只记数，下游自决）
ovl <- sum(ourPeps %in% MHCI_Human$Peptide)
cat("[run_repitope][NOTE] 其中", ovl, "肽与 MHCI_Human 训练集重叠（README 警告点，保留不丢，记入日志供下游判断）\n")

# --- 步骤2：Features() 给新肽算特征（重步，用 fragment library）-------------
cat("[run_repitope] 步骤2 Features() — 算新肽 TCR-contact 特征（耗时）...\n")
featList <- Features(
  peptideSet   = ourPeps,
  fragLib      = fraglib_fst,          # .fst 路径，函数内部读
  aaIndexIDSet = "all",
  fragLenSet   = 3:8,
  fragDepth    = 10000,
  fragLibType  = "Weighted",
  seedSet      = 1:5,                   # 须与 fragment library 同 seed（官方 RepitopeV3 用 1:5）
  coreN        = coreN,
  tmpDir       = tmp_dir                # 支持断点续算
)
# 用官方 saveFeatureDFList 落盘 → 读回 Weighted.10000 那张（文件名规律：prefix+fragLibType.fragDepth.fst）
save_prefix <- file.path(out_dir, "FeatureDF_new_")
saveFeatureDFList(featList, save_prefix)
featNew <- fst::read_fst(paste0(save_prefix, "Weighted.10000.fst"), as.data.table = TRUE)
cat("[run_repitope] 新肽特征 DF:", nrow(featNew), "行 x", ncol(featNew), "列\n")

# --- 步骤3：Immunogenicity_Score() 建模+打分 --------------------------------
cat("[run_repitope] 步骤3 读训练 feature DF ...\n")
featTrain <- fst::read_fst(feature_fst, as.data.table = TRUE)
featTrain <- featTrain[Peptide %in% MHCI_Human$Peptide, ]
cat("[run_repitope] 训练特征 DF:", nrow(featTrain), "行 x", ncol(featTrain), "列\n")

featAll <- data.table::rbindlist(
  list(featTrain, featNew[Peptide %in% ourPeps, ]),
  use.names = TRUE, fill = TRUE
)
cat("[run_repitope] 合并特征 DF:", nrow(featAll), "行 (训练+新肽)\n")

cat("[run_repitope] Immunogenicity_Score() 建 ERT 模型并打分 ...\n")
scoreDF <- Immunogenicity_Score(
  featureDF  = featAll,
  metadataDF = MHCI_Human[, .(Peptide, Immunogenicity)],
  featureSet = MHCI_Human_MinimumFeatureSet,
  seedSet    = 1:5
)
scoreDF <- as.data.table(scoreDF)
cat("[run_repitope] 打分输出列:", paste(names(scoreDF), collapse = ", "), "\n")

# --- 只留我们 551 肽的分，写出 ----------------------------------------------
out <- scoreDF[Peptide %in% ourPeps, ]
out_path <- file.path(out_dir, "Repitope_scores.csv")
fwrite(out, out_path)
cat("[run_repitope] 写出", nrow(out), "肽分 →", out_path, "\n")
cat("[run_repitope] 覆盖:", nrow(out), "/", length(ourPeps),
    "唯一肽拿到分 (差额=Features 算不出/被 Repitope 内部过滤的肽, 回贴 NaN)\n")
if (nrow(out) > 0) {
  cat("[run_repitope] ImmunogenicityScore 范围 [",
      round(min(out$ImmunogenicityScore, na.rm = TRUE), 4), ",",
      round(max(out$ImmunogenicityScore, na.rm = TRUE), 4), "]\n")
}
cat("[run_repitope][DONE]\n")
