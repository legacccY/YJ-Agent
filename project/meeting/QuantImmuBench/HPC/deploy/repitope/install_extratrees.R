options(timeout=1800)
cat("=== extraTrees from CRAN archive ===\n")
tryCatch(
  install.packages("https://cran.r-project.org/src/contrib/Archive/extraTrees/extraTrees_1.0.5.tar.gz",
                   repos=NULL, type="source"),
  error=function(e) cat("extraTrees FAIL:", conditionMessage(e),"\n"))
cat("extraTrees installed:", requireNamespace("extraTrees", quietly=TRUE), "\n")
cat("=== install_github Repitope ===\n")
tryCatch(remotes::install_github("masato-ogishi/Repitope", upgrade="never"),
         error=function(e) cat("Repitope FAIL:", conditionMessage(e),"\n"))
tryCatch({library(Repitope); cat("Repitope load OK ver", as.character(packageVersion("Repitope")),"\n")},
         error=function(e) cat("Repitope load FAIL:", conditionMessage(e),"\n"))
