#!/usr/bin/env Rscript
# ===========================================================================
# run_foreignness.R — IMPROVE Foreigness 特征官方算法 (Łuksza 2017, antigen.garnish)
# 服务: quantimmu-bench Phase0 IMPROVE 档II 真算 Foreigness (lever=IMPROVE)
#
# 官方出处: IMPROVE_paper/bin/R_script/01_data/01_Foreginess_score_*.R
#   fs <- foreignness_score(pep, db = "human")   (README: v %>% foreignness_score(db="human"))
#   = Łuksza et al. 2017 Nature (nature24473) foreignness: 肽 vs IEDB 阳性表位
#     BLOSUM62 gapless 比对 → logistic (a=26, k=4.87)。**唯一输入 = 肽序列, 不需 RNA。**
#
# 用法 (HPC, 需先跑 deploy_antigen_garnish.sh 装好 garnish_r + 数据包):
#   conda activate $BASE/envs/garnish_r
#   AG_DATA_DIR=$BASE/ext_tools/antigen.garnish \
#     Rscript run_foreignness.R <input.tsv (含 Mut_peptide 列)> <out.csv>
# 输出: csv 两列 Mut_peptide,Foreigness  (供 complete_features 按肽 merge 回特征表)
#
# 复现零偏离: 完全调官方 antigen.garnish::foreignness_score, db="human", 不改参数。
# ===========================================================================

suppressMessages({
  library(data.table)
  ok <- requireNamespace("antigen.garnish", quietly = TRUE)
})
if (!ok) {
  stop("antigen.garnish 未安装。先跑 deploy_antigen_garnish.sh (建 garnish_r + install_github + 数据包)。")
}
# antigen.garnish 靠 AG_DATA_DIR 找 IEDB fasta + blast 参考; 未设则它自查标准目录
if (Sys.getenv("AG_DATA_DIR") == "") {
  message("[warn] AG_DATA_DIR 未设, antigen.garnish 将自查默认目录; 建议显式 export AG_DATA_DIR")
}

# --- 兼容补丁 (2026-07-07 rerun): Biostrings>=2.77.1 把 pairwiseAlignment 迁到 pwalign
#     并使旧 shim (.call_fun_in_pwalign) 形式化 defunct → 直接报错不自动委托。
#     antigen.garnish 内部 make_sw_alignment 仍经该 shim, 已装 pwalign 但不自动接管
#     → 运行时把 Biostrings 内部 .call_fun_in_pwalign 改为直接调 pwalign 导出函数,
#       语义完全等价 (同一 pairwiseAlignment 实现), 不改任何算法参数/逻辑 = 复现零偏离。
if (requireNamespace("pwalign", quietly = TRUE)) {
  patched <- FALSE
  try({
    assignInNamespace(
      ".call_fun_in_pwalign",
      function(FUN, ...) do.call(getExportedValue("pwalign", FUN), list(...)),
      ns = "Biostrings"
    )
    patched <- TRUE
  }, silent = TRUE)
  message(sprintf("[patch] Biostrings::.call_fun_in_pwalign -> pwalign 委托: %s",
                  if (patched) "OK" else "未打上(可能 Biostrings 版本无此内部函数)"))
}

args <- commandArgs(trailingOnly = TRUE)
if (length(args) < 2) stop("用法: Rscript run_foreignness.R <input.tsv> <out.csv>")
infile <- args[1]; outfile <- args[2]

df <- fread(infile, sep = "\t")
if (!"Mut_peptide" %in% colnames(df)) stop("输入缺 Mut_peptide 列")

peps <- unique(df$Mut_peptide)
peps <- peps[!is.na(peps) & nchar(peps) > 0]
cat(sprintf("[foreignness] 唯一肽=%d\n", length(peps)))

# 官方调用: foreignness_score(v, db="human") → data.table(nmer, foreignness_score)
fs <- antigen.garnish::foreignness_score(peps, db = "human")
setDT(fs)

# antigen.garnish 返回列名: nmer + foreignness_score (容错两种命名)
pep_col <- if ("nmer" %in% names(fs)) "nmer" else names(fs)[1]
sc_col  <- if ("foreignness_score" %in% names(fs)) "foreignness_score" else
           grep("foreign", names(fs), ignore.case = TRUE, value = TRUE)[1]
if (is.na(sc_col)) stop(paste("找不到 foreignness 分列, 实际列:", paste(names(fs), collapse=",")))

out <- fs[, .(Mut_peptide = get(pep_col), Foreigness = get(sc_col))]
# 未返回的肽 (db 无匹配) → 官方语义 foreignness=0 (无外源相似)
miss <- setdiff(peps, out$Mut_peptide)
if (length(miss) > 0) {
  cat(sprintf("[foreignness] %d 肽 db 无匹配 -> Foreigness=0 (官方语义)\n", length(miss)))
  out <- rbind(out, data.table(Mut_peptide = miss, Foreigness = 0))
}

fwrite(out, outfile)
cat(sprintf("[foreignness] 写 %d 行 -> %s (列: Mut_peptide,Foreigness)\n", nrow(out), outfile))
