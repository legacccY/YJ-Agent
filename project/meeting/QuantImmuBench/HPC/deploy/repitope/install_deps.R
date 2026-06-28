# install_deps.R — Repitope R 依赖一键装（R 4.3.3）
# 服务 quantimmu-bench 扩张v2 第一波 Repitope。后台跑，日志看 install_deps.log。
options(repos = c(CRAN = "https://cloud.r-project.org"))
options(timeout = 1200)

cat("=== Step 1: BiocManager + Bioconductor 包 ===\n")
if (!requireNamespace("BiocManager", quietly = TRUE)) install.packages("BiocManager")
BiocManager::install(c("Biostrings", "msa", "S4Vectors"), update = FALSE, ask = FALSE)

cat("=== Step 2: CRAN 依赖 ===\n")
cran <- c(
  "devtools", "data.table", "fst", "readr",
  "rJava", "extraTrees",
  "mlr", "caret", "BBmisc", "pbapply",
  "foreach", "doParallel", "doSNOW",
  "purrr", "magrittr", "stringr", "stringi", "stringdist",
  "igraph", "Peptides", "seqinr",
  "matrixStats", "psych", "zoo", "rlecuyer",
  "car", "DescTools", "cvAUC", "pROC", "precrec"
)
for (p in cran) {
  if (!requireNamespace(p, quietly = TRUE)) {
    cat("install:", p, "\n")
    tryCatch(install.packages(p), error = function(e) cat("FAIL", p, conditionMessage(e), "\n"))
  } else cat("ok:", p, "\n")
}

cat("=== Step 3: rJava .jinit 验证 ===\n")
tryCatch({ library(rJava); .jinit(); cat("rJava OK\n") },
         error = function(e) cat("rJava FAIL:", conditionMessage(e), "\n"))

cat("=== Step 4: install_github Repitope ===\n")
tryCatch(devtools::install_github("masato-ogishi/Repitope", upgrade = "never"),
         error = function(e) cat("Repitope install FAIL:", conditionMessage(e), "\n"))

cat("=== DONE ===\n")
tryCatch({ library(Repitope); cat("Repitope load OK\n") },
         error = function(e) cat("Repitope load FAIL:", conditionMessage(e), "\n"))
