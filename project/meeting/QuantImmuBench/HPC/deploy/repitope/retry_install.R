# retry_install.R — 重试失败的编译依赖 + Repitope 本体
options(repos = c(CRAN = "https://cloud.r-project.org"))
options(timeout = 1800)

failed <- c("Rcpp", "RcppArmadillo", "ade4", "seqinr", "forecast")
for (p in failed) {
  cat("=== retry install:", p, "===\n")
  tryCatch(install.packages(p, dependencies = TRUE),
           error = function(e) cat("FAIL", p, conditionMessage(e), "\n"))
  cat(p, "installed:", requireNamespace(p, quietly = TRUE), "\n")
}

cat("=== install_github Repitope ===\n")
tryCatch(remotes::install_github("masato-ogishi/Repitope", upgrade = "never"),
         error = function(e) cat("Repitope FAIL:", conditionMessage(e), "\n"))

cat("=== final load check ===\n")
tryCatch({ library(Repitope); cat("Repitope load OK; version", as.character(packageVersion("Repitope")), "\n") },
         error = function(e) cat("Repitope load FAIL:", conditionMessage(e), "\n"))
