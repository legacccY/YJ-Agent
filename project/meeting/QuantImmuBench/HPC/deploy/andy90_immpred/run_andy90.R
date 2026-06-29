#!/usr/bin/env Rscript
# run_andy90.R — QuantImmuBench §工具部署  andy90 immunogenicity_predictor 单 HLA 驱动
# 服务项目：quantimmu-bench §工具部署 lever=免疫原补位（补到 20）
#
# 这是官方 main.R 的“参数化忠实包装”：逻辑/算法零改动，只把硬编码的
#   path_netmhcpan / HLAs / file_fasta / final_output_file 改成命令行参数，
# 然后原样 source() 三个官方 src/*.R（未改一字）。
# run_andy90.py 对每个 HLA 调一次本脚本（HLAs 传单个 allele）。
#
# 官方来源（2026-06-29 核自 github.com/andy90/immunogenicity_predictor master）：
#   main.R:
#     path_netmhcpan <- ".../netMHCpan"   # netMHCpan-4.0
#     HLAs <- "HLA-A02:01,HLA-A03:01"     # 逗号分隔，无空格，去星格式
#     file_fasta <- here("input.fasta")
#     final_output_file <- here("predicted_immunogenicity.csv")
#     source(here("src","binding_prediction.R"))
#     source(here("src","get_similarity.R"))
#     source(here("src","predict_amp.R"))
#   预测无需训练：模型=固定阈值 amp_thresh=7024 + data/ 下 self/foreign 参考肽集。
#   amplitude = self*foreign/binding，越高越免疫原（amp>7024 → immunogenic=YES）。
#
# 用法：
#   Rscript run_andy90.R \
#     --fasta     /abs/path/HLA-A03_01.fasta \
#     --hlas      HLA-A03:01 \
#     --netmhcpan /path/to/netMHCpan \
#     --repo      /path/to/immunogenicity_predictor   (clone 根目录) \
#     --out       /abs/path/andy90_out_HLA-A03_01.csv
#
# ⚠️ 必须在 clone 根目录可解析 here()：本脚本 setwd(repo) 后再 source，
#    使 src/get_similarity.R 里的 here("data","self_peps.txt") 等正确解析到 repo/data/。

# ---------------------------------------------------------------------------
# 参数解析（简单 --key value，不依赖 optparse；对齐 repitope/run_repitope.R 风格）
# ---------------------------------------------------------------------------
argv <- commandArgs(trailingOnly = TRUE)
args <- list(fasta = NULL, hlas = NULL, netmhcpan = NULL, repo = NULL, out = NULL)
i <- 1
while (i <= length(argv)) {
  flag <- argv[i]
  if (flag == "--fasta")          { args$fasta     <- argv[i + 1]; i <- i + 2 }
  else if (flag == "--hlas")      { args$hlas      <- argv[i + 1]; i <- i + 2 }
  else if (flag == "--netmhcpan") { args$netmhcpan <- argv[i + 1]; i <- i + 2 }
  else if (flag == "--repo")      { args$repo      <- argv[i + 1]; i <- i + 2 }
  else if (flag == "--out")       { args$out       <- argv[i + 1]; i <- i + 2 }
  else { cat(sprintf("[run_andy90] 忽略未知参数: %s\n", flag)); i <- i + 1 }
}

for (k in c("fasta", "hlas", "netmhcpan", "repo", "out")) {
  if (is.null(args[[k]])) stop(sprintf("[run_andy90] ERROR: 缺少参数 --%s", k))
}
if (!file.exists(args$fasta)) stop(sprintf("[run_andy90] ERROR: fasta 不存在: %s", args$fasta))
if (!dir.exists(args$repo))   stop(sprintf("[run_andy90] ERROR: repo 目录不存在: %s（先 git clone，见 NOTES.md）", args$repo))
if (!file.exists(args$netmhcpan)) {
  cat(sprintf("[run_andy90] WARNING: netMHCpan 二进制路径不存在: %s（若在 PATH 中可忽略）\n", args$netmhcpan), file = stderr())
}

# 绝对化（setwd 之后相对路径会失效）
abs_fasta <- normalizePath(args$fasta, mustWork = TRUE)
abs_out   <- normalizePath(args$out,   mustWork = FALSE)
abs_repo  <- normalizePath(args$repo,  mustWork = TRUE)

cat(sprintf("[run_andy90] HLA=%s  fasta=%s\n", args$hlas, abs_fasta))
cat(sprintf("[run_andy90] repo=%s  netmhcpan=%s\n", abs_repo, args$netmhcpan))

# ---------------------------------------------------------------------------
# 切到 clone 根目录，使官方 src/*.R 内的 here() 解析到 repo（.git 在此）
# here 在首次加载时按 getwd() 锚定 root，故必须先 setwd 再 source。
# ---------------------------------------------------------------------------
setwd(abs_repo)

# 复刻 main.R 的 4 个全局赋值（官方 src/*.R 直接引用这些全局变量）
path_netmhcpan    <- args$netmhcpan
HLAs              <- args$hlas        # 单个 allele，去星格式（如 HLA-A03:01）
file_fasta        <- abs_fasta
final_output_file <- abs_out

# 原样 source 三个官方 src 文件（算法零改动；忠实复现 main.R）
source(file.path(abs_repo, "src", "binding_prediction.R"))
source(file.path(abs_repo, "src", "get_similarity.R"))
source(file.path(abs_repo, "src", "predict_amp.R"))

cat(sprintf("[run_andy90] ✔ 完成 → %s\n", abs_out))
