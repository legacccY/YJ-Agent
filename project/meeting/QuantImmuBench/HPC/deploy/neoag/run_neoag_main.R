# neoag 主跑脚本（主窗填入官方 model_process+predict，2026-06-29 已在 example 验证）
# 服务 quantimmu-bench §工具部署 第30工具；复现零偏离：model_process 逐字照官方
suppressMessages({library(caret);library(Peptides);library(data.table);library(gbm)})
args <- commandArgs(trailingOnly=TRUE)
in_csv  <- if(length(args)>=1) args[1] else "neoag_input.csv"
out_csv <- if(length(args)>=2) args[2] else "neoag_raw.csv"
rds     <- "repo/Final_gbm_model.rds"
neo_tab <- fread(in_csv)
# 映射到官方列名：mut_peptide / Reference / peptide_variant_position
neo_tab$mut_peptide <- neo_tab$mt_peptide
neo_tab$Reference   <- neo_tab$wt_peptide
neo_tab$peptide_variant_position <- neo_tab$mut_pos_1based
# 官方 model_process（逐字，仅 dopar→顺序，特征值相同）
mp = function(n){ c(
  ifelse(substr(neo_tab$mut_peptide[n],1,1)=="V",1,0),
  ifelse(substr(neo_tab$mut_peptide[n],nchar(neo_tab$mut_peptide[n]),nchar(neo_tab$mut_peptide[n]))=="V",1,0),
  ifelse(aaComp(substr(neo_tab$mut_peptide[n],nchar(neo_tab$mut_peptide[n]),nchar(neo_tab$mut_peptide[n])))[[1]][2]==1,1,0),
  ifelse(aaComp(substr(neo_tab$Reference[n],neo_tab$peptide_variant_position[n],neo_tab$peptide_variant_position[n]))[[1]][8]==1,1,0),
  (aaComp(substr(neo_tab$mut_peptide[n],neo_tab$peptide_variant_position[n],neo_tab$peptide_variant_position[n]))[[1]][2]-aaComp(substr(neo_tab$Reference[n],neo_tab$peptide_variant_position[n],neo_tab$peptide_variant_position[n]))[[1]][2]),
  ifelse("K"%in%unlist(strsplit(substr(neo_tab$mut_peptide[n],1,nchar(neo_tab$mut_peptide[n])-7),"|")),1,0),
  ifelse("V"%in%unlist(strsplit(substr(neo_tab$mut_peptide[n],1,3),"|")),1,0)) }
model_mat = do.call(rbind, lapply(1:nrow(neo_tab), mp))
colnames(model_mat)=c("Absolute_position_1_V","Last_position_V","Last_position_Small","Reference_AA_at_mutated_position_Basic","Mutated_position_change_of_Small_feature","Relative_site_1_K","First_three_AA_V")
Final_model = readRDS(rds)
score = predict(Final_model, newdata=as.data.frame(model_mat))   # 回归连续分,越高越免疫原
out = data.frame(mt_peptide=neo_tab$mut_peptide, wt_peptide=neo_tab$Reference, score=score)
fwrite(out, out_csv)
cat("[neoag] 写出", nrow(out), "行 →", out_csv, "| score min/med/max:", round(min(score),3), round(median(score),3), round(max(score),3), "\n")
