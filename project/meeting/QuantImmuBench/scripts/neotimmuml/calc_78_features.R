#!/usr/bin/env Rscript
# calc_78_features.R
# QuantImmuBench / NeoTImmuML 特征计算脚本
# 用 R Peptides 2.4.6 包对肽段算 78 个物化特征
# 输出 csv 列名与 NeoTImmuML demo.csv 严格一致（Peptide + 78 特征列）
#
# 用法：
#   Rscript calc_78_features.R --input <peptides.txt/csv> --output <features.csv>
#
# 输入：
#   --input   : 单列 txt（每行一条肽段）或带 Peptide 列的 csv
# 输出：
#   --output  : csv，Peptide + 78 特征（列名与 NeoTImmuML demo.csv 严格对齐）
#
# 依赖：Peptides (>= 2.4.6)，argparse
# 安装：install.packages(c("Peptides","argparse"))
#
# R 路径（本机 Windows）：E:\R-4.3.3\bin\Rscript.exe
#
# API 说明（Peptides 2.4.6 实测，与旧版不同）：
#   - blosumIndices/fasgaiVectors/mswhimScores/crucianiProperties/kideraFactors/
#     protFP/stScales/tScales/vhseScales/zScales 全部返回 list，[[1]] 才是 numeric vector
#   - aaComp() 返回 list，[[1]] 是 9x2 matrix（行=AA类别，列=Number/Mole%）
#   - membpos() 返回 list，[[1]] 是 data.frame（列 Pep/H/uH/MembPos，重复3行）
#   - autoCorrelation/autoCovariance 签名: (sequence, lag, property, center=TRUE)
#     property = named numeric vector (20 AAs)，需用 AAdata[[grp]][[idx]]
#     demo.csv 实测确认：property = AAdata$Hydrophobicity$KyteDoolittle (10/10 peptides match)
# -------------------------------------------------------------------------

suppressPackageStartupMessages({
  if (!requireNamespace("argparse", quietly = TRUE)) install.packages("argparse", repos="https://cran.r-project.org")
  if (!requireNamespace("Peptides", quietly = TRUE)) install.packages("Peptides", repos="https://cran.r-project.org")
  library(argparse)
  library(Peptides)
})

# ---- 命令行参数 ----
parser <- ArgumentParser(description="Compute 78 physicochemical features for peptides (NeoTImmuML input)")
parser$add_argument("--input",  required=TRUE, help="Input: one-per-line txt or csv with Peptide column")
parser$add_argument("--output", required=TRUE, help="Output CSV with Peptide + 78 features")
args <- parser$parse_args()

# ---- 读取肽段 ----
cat(sprintf("[INFO] Reading peptides from: %s\n", args$input))
raw <- tryCatch(read.csv(args$input, stringsAsFactors=FALSE), error=function(e) NULL)
if (is.null(raw)) {
  raw <- read.table(args$input, header=FALSE, stringsAsFactors=FALSE, col.names="Peptide")
}
if ("Peptide" %in% colnames(raw)) {
  peptides <- unique(trimws(raw$Peptide))
} else {
  peptides <- unique(trimws(raw[[1]]))
}
peptides <- peptides[nchar(peptides) > 0]
cat(sprintf("[INFO] %d unique peptides loaded\n", length(peptides)))

# ---- 加载 AAdata（autoCorrelation/autoCovariance 用）----
data(AAdata)
# 实测 demo.csv 10 条肽全部吻合：property = KyteDoolittle
KD_PROPERTY <- AAdata$Hydrophobicity$KyteDoolittle

# ---- 78 特征列名（严格按 demo.csv 列 C-CB 顺序）----
FEAT_NAMES <- c(
  "mol_weight", "isoelectric_point", "boman_index", "charge",
  "hydrophobicity_index", "lengthpep", "instability_index", "hmoment",
  "membpos.H", "membpos.uH", "aindex",
  "autoCorrelation", "autoCovariance",
  "aaComp_1",
  paste0("blosum_", 1:10),
  "cruciani_1",
  paste0("fasgai_", 1:6),
  paste0("kidera_", 1:10),
  paste0("mswhim_", 1:3),
  paste0("protFP_", 1:8),
  paste0("stscale_", 1:8),
  paste0("tscale_", 1:5),
  paste0("vhse_", 1:8),
  paste0("zscale_", 1:5)
)
stopifnot(length(FEAT_NAMES) == 78)

# ---- NA 占位行（error 时返回，结构与正常行一致）----
NA_ROW <- as.data.frame(
  matrix(NA_real_, nrow=1, ncol=78, dimnames=list(NULL, FEAT_NAMES)),
  check.names=FALSE
)

# ---- 计算单肽 78 特征，返回 1-row data.frame ----
compute_features <- function(pep) {
  tryCatch({

    # 1. mol_weight — mw() -> scalar
    mol_weight        <- mw(pep)

    # 2. isoelectric_point — pI() -> scalar
    isoelectric_point <- pI(pep)

    # 3. boman_index — boman() -> scalar
    boman_index       <- boman(pep)

    # 4. charge — charge(pH=7) -> scalar
    charge_val        <- charge(pep, pH=7)

    # 5. hydrophobicity_index — hydrophobicity() -> scalar (Kyte-Doolittle default)
    hydrophobicity_index <- hydrophobicity(pep)

    # 6. lengthpep — nchar -> integer
    lengthpep         <- nchar(pep)

    # 7. instability_index — instaIndex() -> scalar
    instability_index <- instaIndex(pep)

    # 8. hmoment — hmoment(angle=100, window=11) -> scalar
    hmoment_val       <- hmoment(pep, angle=100, window=11)

    # 9-10. membpos.H / membpos.uH
    # membpos() -> list, [[1]] = data.frame(Pep/H/uH/MembPos), 3 identical rows
    mp         <- membpos(pep, angle=100)[[1]]
    membpos_H  <- mp$H[1]
    membpos_uH <- mp$uH[1]

    # 11. aindex — aIndex() -> scalar
    aindex_val <- aIndex(pep)

    # 12. autoCorrelation
    # autoCorrelation(sequence, lag, property, center=TRUE) -> scalar
    # property = named numeric vector (20 AAs); demo confirmed: KyteDoolittle (10/10 match)
    auto_corr <- tryCatch(
      autoCorrelation(pep, lag=1, property=KD_PROPERTY, center=TRUE),
      error=function(e) NA_real_
    )

    # 13. autoCovariance
    # autoCovariance(sequence, lag, property, center=TRUE) -> scalar
    # same property as autoCorrelation
    auto_cov <- tryCatch(
      autoCovariance(pep, lag=1, property=KD_PROPERTY, center=TRUE),
      error=function(e) NA_real_
    )

    # 14. aaComp_1
    # aaComp() -> list, [[1]] = 9x2 matrix(rows=AA categories, cols=Number/Mole%)
    # Row names: Tiny/Small/Aliphatic/Aromatic/NonPolar/Polar/Charged/Basic/Acidic
    #
    # CONCLUSION (2026-06-30, researcher + R Peptides 2.4.6 实测, 见脚本尾注):
    #   demo.csv 的 aaComp_1 列「损坏/不可复现」——铁证: STLPETAVV/STLPETTVI/STLPETCVV
    #   三条近乎相同的肽 demo aaComp_1=2/27.778/38.889 天差地别(分母 7/17/18 ≠ 肽长),
    #   而 R aaComp 任一类 Mole%/Number 对这三条几乎相同。无法对齐 demo (官方产物本身有缺陷)。
    #   => 不再追 demo 值。改用论文语义口径: 论文将 aaComp_1 描述为 "non-polar amino acid
    #      ratio" → 取 NonPolar Mole%。这是「自洽口径」(训练/推理用同一管道即可),非 demo 复刻。
    #   COUPLING: 若复用旧 models/*.joblib(用 Acidic 训练的) 必须把本行改回 "Acidic";
    #      若重训(推荐,因旧模型类不平衡 1:364 已失真)则本 NonPolar 口径训练+推理一致即可。
    #   TODO: 邮件作者(13401930670@163.com)或查 Supplementary Table 1 / TumorAgDB2.0 在线计算器确认。
    aacomp_mat <- aaComp(pep)[[1]]
    aaComp_1   <- as.numeric(aacomp_mat["NonPolar", "Mole%"])

    # 15-24. blosum_1..10
    # blosumIndices() -> list, [[1]] = named numeric vector length 10
    bl <- blosumIndices(pep)[[1]]

    # 25. cruciani_1
    # crucianiProperties() -> list, [[1]] = named numeric vector length 3 (PP1/PP2/PP3)
    # CONCLUSION (2026-06-30): demo.csv cruciani_1 列同样损坏——STLPET* 三条 demo 全 = 0.179048
    #   (该变不变), 而 R PP1 = -0.28/-0.1222/-0.2344 (各不同)。无法对齐 demo。
    #   论文将 cruciani_1 描述为 "polarity (PP1)" → 保留 cr[1] = PP1 (语义最匹配的口径)。
    #   同样是自洽口径,非 demo 复刻。TODO: 同 aaComp_1, 待作者/Supp 确认。
    cr <- crucianiProperties(pep)[[1]]

    # 26-31. fasgai_1..6
    # fasgaiVectors() -> list, [[1]] = named numeric vector length 6
    fa <- fasgaiVectors(pep)[[1]]

    # 32-41. kidera_1..10
    # kideraFactors() -> list, [[1]] = named numeric vector length 10
    ki <- kideraFactors(pep)[[1]]

    # 42-44. mswhim_1..3
    # mswhimScores() -> list, [[1]] = named numeric vector length 3
    ms <- mswhimScores(pep)[[1]]

    # 45-52. protFP_1..8
    # protFP() -> list, [[1]] = named numeric vector length 8
    pf <- protFP(pep)[[1]]

    # 53-60. stscale_1..8
    # stScales() -> list, [[1]] = named numeric vector length 8
    st <- stScales(pep)[[1]]

    # 61-65. tscale_1..5
    # tScales() -> list, [[1]] = named numeric vector length 5
    ts <- tScales(pep)[[1]]

    # 66-73. vhse_1..8
    # vhseScales() -> list, [[1]] = named numeric vector length 8
    vh <- vhseScales(pep)[[1]]

    # 74-78. zscale_1..5
    # zScales() -> list, [[1]] = named numeric vector length 5
    zs <- zScales(pep)[[1]]

    # ---- 组装成 1-row data.frame，check.names=FALSE 保留 membpos.H 点号 ----
    row <- data.frame(
      mol_weight        = mol_weight,
      isoelectric_point = isoelectric_point,
      boman_index       = boman_index,
      charge            = charge_val,
      hydrophobicity_index = hydrophobicity_index,
      lengthpep         = lengthpep,
      instability_index = instability_index,
      hmoment           = hmoment_val,
      membpos.H         = membpos_H,
      membpos.uH        = membpos_uH,
      aindex            = aindex_val,
      autoCorrelation   = auto_corr,
      autoCovariance    = auto_cov,
      aaComp_1          = aaComp_1,
      blosum_1          = bl[1],
      blosum_2          = bl[2],
      blosum_3          = bl[3],
      blosum_4          = bl[4],
      blosum_5          = bl[5],
      blosum_6          = bl[6],
      blosum_7          = bl[7],
      blosum_8          = bl[8],
      blosum_9          = bl[9],
      blosum_10         = bl[10],
      cruciani_1        = cr[1],
      fasgai_1          = fa[1],
      fasgai_2          = fa[2],
      fasgai_3          = fa[3],
      fasgai_4          = fa[4],
      fasgai_5          = fa[5],
      fasgai_6          = fa[6],
      kidera_1          = ki[1],
      kidera_2          = ki[2],
      kidera_3          = ki[3],
      kidera_4          = ki[4],
      kidera_5          = ki[5],
      kidera_6          = ki[6],
      kidera_7          = ki[7],
      kidera_8          = ki[8],
      kidera_9          = ki[9],
      kidera_10         = ki[10],
      mswhim_1          = ms[1],
      mswhim_2          = ms[2],
      mswhim_3          = ms[3],
      protFP_1          = pf[1],
      protFP_2          = pf[2],
      protFP_3          = pf[3],
      protFP_4          = pf[4],
      protFP_5          = pf[5],
      protFP_6          = pf[6],
      protFP_7          = pf[7],
      protFP_8          = pf[8],
      stscale_1         = st[1],
      stscale_2         = st[2],
      stscale_3         = st[3],
      stscale_4         = st[4],
      stscale_5         = st[5],
      stscale_6         = st[6],
      stscale_7         = st[7],
      stscale_8         = st[8],
      tscale_1          = ts[1],
      tscale_2          = ts[2],
      tscale_3          = ts[3],
      tscale_4          = ts[4],
      tscale_5          = ts[5],
      vhse_1            = vh[1],
      vhse_2            = vh[2],
      vhse_3            = vh[3],
      vhse_4            = vh[4],
      vhse_5            = vh[5],
      vhse_6            = vh[6],
      vhse_7            = vh[7],
      vhse_8            = vh[8],
      zscale_1          = zs[1],
      zscale_2          = zs[2],
      zscale_3          = zs[3],
      zscale_4          = zs[4],
      zscale_5          = zs[5],
      stringsAsFactors  = FALSE,
      check.names       = FALSE
    )
    return(row)

  }, error = function(e) {
    warning(sprintf("[WARN] Error for peptide '%s': %s", pep, e$message))
    return(NA_ROW)
  })
}

# ---- 批量计算 ----
cat("[INFO] Computing features...\n")
results <- lapply(peptides, compute_features)

# do.call(rbind) — 每个元素都是同结构 1-row data.frame，列名完全一致
feat_df <- do.call(rbind, results)
rownames(feat_df) <- NULL

# 加 Peptide 列（第一列）
feat_df <- cbind(Peptide=peptides, feat_df, stringsAsFactors=FALSE)

# ---- 验证列名顺序 ----
actual_feat_cols <- colnames(feat_df)[-1]
mismatched <- which(actual_feat_cols != FEAT_NAMES)
if (length(mismatched) > 0) {
  cat("[ERROR] Column name mismatch at positions:", mismatched, "\n")
  cat("  Expected:", FEAT_NAMES[mismatched], "\n")
  cat("  Got:     ", actual_feat_cols[mismatched], "\n")
  stop("Column name mismatch")
}
stopifnot(ncol(feat_df) == 79)

na_rows <- sum(apply(feat_df[, -1], 1, function(r) any(is.na(r))))
if (na_rows > 0) {
  cat(sprintf("[WARN] %d rows with NA features (R computation failed)\n", na_rows))
}

# ---- 写出 ----
write.csv(feat_df, file=args$output, row.names=FALSE, quote=FALSE)
cat(sprintf("[INFO] Written %d rows x %d cols to: %s\n", nrow(feat_df), ncol(feat_df), args$output))
cat("[DONE]\n")

# -------------------------------------------------------------------------
# 函数真实返回类型（Peptides 2.4.6 实测，STLPETCVV）
#
# 函数名                   返回          提取          已验
# -----------------------  ------------  ------------  -----
# mw/pI/boman/charge       scalar        直接           -
# hydrophobicity           scalar        直接           -
# instaIndex/aIndex        scalar        直接           -
# hmoment                  scalar        直接           -
# membpos                  list(1)       [[1]]$H[1]     -
# aaComp                   list(1)       [[1]][row,"Mole%"]  TODO
# autoCorrelation          scalar        (lag=1,property=KD)  demo 10/10 OK
# autoCovariance           scalar        (lag=1,property=KD)  demo 10/10 OK
# blosumIndices            list(1)       [[1]][1..10]   -
# crucianiProperties       list(1)       [[1]][1]=PP1   TODO cruciani_1=PP1?
# fasgaiVectors            list(1)       [[1]][1..6]    -
# kideraFactors            list(1)       [[1]][1..10]   -
# mswhimScores             list(1)       [[1]][1..3]    -
# protFP                   list(1)       [[1]][1..8]    -
# stScales                 list(1)       [[1]][1..8]    -
# tScales                  list(1)       [[1]][1..5]    -
# vhseScales               list(1)       [[1]][1..8]    -
# zScales                  list(1)       [[1]][1..5]    -
#
# aaComp_1 / cruciani_1 结论（2026-06-30，researcher + 本机 R Peptides 2.4.6 实测）：
#   官方 demo.csv 这两列「损坏/不可复现」，并非参数没调对：
#     - STLPETAVV / STLPETTVI / STLPETCVV（仅 7-9 位不同）demo aaComp_1 = 2 / 27.778 / 38.889
#       天差地别，分母 7/17/18 ≠ 肽长(9)，任何 R aaComp Mole%/Number 都解释不了；
#     - 同三条 demo cruciani_1 全 = 0.179048（该变不变），R PP1 = -0.28/-0.1222/-0.2344；
#     - 对照列 lengthpep/mol_weight/zscale_* 与肽完全对齐且可复现 → 仅这两列坏。
#   官方 NeoTImmuML repo 只有 ipynb+README+demo.csv，算 78 特征的 R 脚本未公开；论文仅称
#   用 "Peptides package in R (v2.4.6)"，公式在未取到的 Supplementary Table 1。
#   => 放弃对齐 demo（官方产物缺陷），改用论文语义自洽口径：
#        aaComp_1 = NonPolar Mole%（论文 "non-polar amino acid ratio"）
#        cruciani_1 = PP1（论文 "polarity"）
#   只要训练/推理用同一管道即自洽。TODO：邮件作者 13401930670@163.com 或查 TumorAgDB2.0
#   在线特征计算器 / Supplementary Table 1 确认确切定义后回改。
# -------------------------------------------------------------------------
