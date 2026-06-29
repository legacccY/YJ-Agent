#!/usr/bin/env Rscript
# run_neoag.R — QuantImmuBench §工具部署  neoag 预测忠实包装（第 30 工具）
# 服务项目：quantimmu-bench §工具部署 lever=补满 30 工具最后 1 个免疫原槽（neoag）
#
# neoag = R/caret GBM 模型（权重自带 repo 内 Final_gbm_model.rds），吃
#   mutant 肽 + WT/reference 肽 + 突变位号（**不吃 HLA**），输出连续 immunogenicity score。
# repo: github.com/vincentlaboratories/neoag
# 论文: Cancer Immunol Res 2019, DOI 10.1158/2326-6066.CIR-19-0155
# 许可: non-commercial research license（数字可发表）
#
# 设计哲学（同 andy90/run_andy90.R）：**官方算法零改动**。本脚本只：
#   (1) setwd(repo) 使官方 R 内的相对/here() 路径解析正确；
#   (2) 原样 source 官方 feature/predict R；
#   (3) load Final_gbm_model.rds；
#   (4) 对本部署 canonical 输入(neoag_input.csv) 调官方 feature 函数 → predict。
# 特征计算 / 模型 predict 一字不改，仅参数化输入/输出路径。
#
# ⚠️⚠️⚠️ OFFICIAL API ADAPTER（本机无外网 curl HTTP 000，官方 API 未核，必须主窗 clone 后填）：
#   下方 4 个常量 + compute_neoag_scores() 是唯一需主窗按官方 repo 核对/填写处。
#   未填妥时脚本会 **stop() 硬停**（绝不臆造一个假预测），并打印需填什么。
#   填写来源：clone 后读 repo README + R/ 下脚本 + Final_gbm_model.rds 训练特征名。
#
# 用法（主窗跑，本脚本不自跑）：
#   Rscript run_neoag.R \
#     --input /abs/neoag_input.csv \
#     --repo  /path/to/neoag        (git clone 根目录) \
#     --model /path/to/neoag/Final_gbm_model.rds   (默认 <repo>/Final_gbm_model.rds) \
#     --out   /abs/neoag_raw.csv

# ---------------------------------------------------------------------------
# 参数解析（简单 --key value，对齐 run_andy90.R 风格）
# ---------------------------------------------------------------------------
argv <- commandArgs(trailingOnly = TRUE)
args <- list(input = NULL, repo = NULL, model = NULL, out = NULL)
i <- 1
while (i <= length(argv)) {
  flag <- argv[i]
  if (flag == "--input")      { args$input <- argv[i + 1]; i <- i + 2 }
  else if (flag == "--repo")  { args$repo  <- argv[i + 1]; i <- i + 2 }
  else if (flag == "--model") { args$model <- argv[i + 1]; i <- i + 2 }
  else if (flag == "--out")   { args$out   <- argv[i + 1]; i <- i + 2 }
  else { cat(sprintf("[run_neoag] 忽略未知参数: %s\n", flag)); i <- i + 1 }
}
for (k in c("input", "repo", "out")) {
  if (is.null(args[[k]])) stop(sprintf("[run_neoag] ERROR: 缺少参数 --%s", k))
}
if (is.null(args$model)) {
  args$model <- file.path(args$repo, "Final_gbm_model.rds")   # ⚠️TODO 确认 rds 在 repo 根；否则传 --model
}
if (!file.exists(args$input)) stop(sprintf("[run_neoag] ERROR: input 不存在: %s（先跑 prep_input.py）", args$input))
if (!dir.exists(args$repo))   stop(sprintf("[run_neoag] ERROR: repo 不存在: %s（先 git clone，见 NOTES.md）", args$repo))
if (!file.exists(args$model)) stop(sprintf("[run_neoag] ERROR: 模型 rds 不存在: %s（确认 Final_gbm_model.rds 路径，--model 指定）", args$model))

abs_input <- normalizePath(args$input, mustWork = TRUE)
abs_repo  <- normalizePath(args$repo,  mustWork = TRUE)
abs_model <- normalizePath(args$model, mustWork = TRUE)
abs_out   <- normalizePath(args$out,   mustWork = FALSE)

cat(sprintf("[run_neoag] input=%s\n", abs_input))
cat(sprintf("[run_neoag] repo =%s\n", abs_repo))
cat(sprintf("[run_neoag] model=%s\n", abs_model))

# 切到 clone 根目录（使官方 R 内相对/here() 路径解析到 repo；同 andy90 处理）
setwd(abs_repo)

# 载模型（caret GBM；readRDS 不改算法）
gbm_model <- readRDS(abs_model)
cat("[run_neoag] ✔ 载入 Final_gbm_model.rds\n")

# ===========================================================================
# OFFICIAL API ADAPTER —— ⚠️ 主窗 clone 后必填（未核区，绝不臆造）
# ===========================================================================
# (1) 官方特征/predict R 脚本（source 进来，算法零改）。clone 后看 repo R/ 目录补实际文件。
#     例（占位，需主窗核实际文件名）：c("R/features.R", "R/predict.R")
OFFICIAL_R_SOURCES <- c()      # ⚠️TODO 填官方 R 脚本相对路径（相对 repo 根）

# (2) 官方「给一组 (mt,wt,pos) 算特征 data.frame」的函数名（source 后应可见）。
FEATURE_FN_NAME    <- ""       # ⚠️TODO 填官方特征函数名，如 "build_features" / "neoag_features"

# (3) 官方输入列名（feature 函数期望的列名）。本部署 canonical = mt_peptide/wt_peptide/mut_pos_1based。
#     若官方 feature 函数吃别的列名，在 build_official_input() 里改映射。
# (4) predict 取分方式：caret GBM 多为 predict(model, newdata, type="prob")[, <正类列>]。
PREDICT_TYPE       <- "prob"   # ⚠️TODO 确认 "prob" 还是 "raw"
PREDICT_POS_CLASS  <- ""       # ⚠️TODO 若 type="prob"，填正类(免疫原)列名，如 "immunogenic" / "Positive" / "1"

# source 官方 R（算法零改动）
for (src in OFFICIAL_R_SOURCES) {
  sp <- file.path(abs_repo, src)
  if (!file.exists(sp)) stop(sprintf("[run_neoag] ERROR: 官方 R 缺失: %s（核 OFFICIAL_R_SOURCES）", sp))
  source(sp)
}

# 适配：本部署 canonical 输入 → 官方 feature 函数所需 data.frame
build_official_input <- function(df) {
  # df 列: pair_id, mt_peptide, wt_peptide, mut_pos_1based, pep_len
  # ⚠️TODO 若官方 feature 函数要别的列名/位号 base，在此改映射（默认透传 mt/wt/pos）。
  data.frame(
    mt_peptide = as.character(df$mt_peptide),
    wt_peptide = as.character(df$wt_peptide),
    mut_pos    = as.integer(df$mut_pos_1based),
    stringsAsFactors = FALSE
  )
}

# 主预测：调官方特征函数 + GBM predict（未填妥则硬停，绝不返回假分）
compute_neoag_scores <- function(df_in) {
  if (length(OFFICIAL_R_SOURCES) == 0 || nchar(FEATURE_FN_NAME) == 0) {
    stop(paste0(
      "[run_neoag] ⛔ OFFICIAL API ADAPTER 未填（本机无外网未核官方 API）。\n",
      "  主窗 clone github.com/vincentlaboratories/neoag 后，按 NOTES.md §官方API 填：\n",
      "    - OFFICIAL_R_SOURCES（官方特征/predict R 脚本相对路径）\n",
      "    - FEATURE_FN_NAME（官方特征函数名）\n",
      "    - PREDICT_TYPE / PREDICT_POS_CLASS（caret predict 取分方式）\n",
      "  绝不在未核实下输出臆造分数。"))
  }
  if (!exists(FEATURE_FN_NAME, mode = "function")) {
    stop(sprintf("[run_neoag] ⛔ 官方特征函数 '%s' 未在 source 后可见，核 FEATURE_FN_NAME / OFFICIAL_R_SOURCES",
                 FEATURE_FN_NAME))
  }
  feat_fn <- get(FEATURE_FN_NAME, mode = "function")
  off_in  <- build_official_input(df_in)
  feats   <- feat_fn(off_in)        # 官方算法，零改

  if (identical(PREDICT_TYPE, "prob")) {
    if (nchar(PREDICT_POS_CLASS) == 0)
      stop("[run_neoag] ⛔ PREDICT_TYPE='prob' 需填 PREDICT_POS_CLASS（正类列名）")
    probs <- predict(gbm_model, newdata = feats, type = "prob")
    if (!(PREDICT_POS_CLASS %in% colnames(probs)))
      stop(sprintf("[run_neoag] ⛔ predict prob 无列 '%s'，实际列: %s",
                   PREDICT_POS_CLASS, paste(colnames(probs), collapse = ",")))
    scores <- probs[[PREDICT_POS_CLASS]]
  } else {
    scores <- as.numeric(predict(gbm_model, newdata = feats, type = PREDICT_TYPE))
  }
  scores
}

# ===========================================================================
# 跑预测 + 写 raw
# ===========================================================================
df_in <- read.csv(abs_input, stringsAsFactors = FALSE, colClasses = "character")
need_cols <- c("pair_id", "mt_peptide", "wt_peptide", "mut_pos_1based")
miss <- setdiff(need_cols, colnames(df_in))
if (length(miss) > 0) stop(sprintf("[run_neoag] ERROR: input 缺列: %s", paste(miss, collapse = ",")))
cat(sprintf("[run_neoag] 读入 %d 个 (mt,wt) 对\n", nrow(df_in)))

scores <- compute_neoag_scores(df_in)
if (length(scores) != nrow(df_in))
  stop(sprintf("[run_neoag] ERROR: 预测数 %d ≠ 输入对数 %d", length(scores), nrow(df_in)))

raw <- data.frame(
  mt_peptide = df_in$mt_peptide,
  wt_peptide = df_in$wt_peptide,
  score      = as.numeric(scores),
  stringsAsFactors = FALSE
)
dir.create(dirname(abs_out), showWarnings = FALSE, recursive = TRUE)
write.csv(raw, abs_out, row.names = FALSE, quote = FALSE)
cat(sprintf("[run_neoag] ✔ 写出 %d 行 → %s\n", nrow(raw), abs_out))
cat("[run_neoag] raw 列: mt_peptide, wt_peptide, score（score 方向见 NOTES §分数方向，⚠️TODO 核）\n")
