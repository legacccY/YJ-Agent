# andy90 immunogenicity_predictor — 部署说明（QuantImmuBench §工具部署 免疫原补位）

> 建档：2026-06-29。服务 quantimmu-bench §工具部署 lever=免疫原侧补到 20（补位工具）。
> 许可：**MIT**，数字可自由发布。
> R 来源：github.com/andy90/immunogenicity_predictor（作者 Ang Gao @ MIT，anggao@mit.edu）
> 引用：Gao, A. et al. (2020) "Predicting the Immunogenicity of T cell epitopes: From HIV to SARS-CoV-2." bioRxiv 2020.05.14.095885.

---

## 工具简介

预测 **HLA Class-I matched** 肽（表位）的免疫原性。训练于 HIV 急性/慢性患者 T 细胞应答数据。
三步流水（官方 main.R → 三个 src/*.R）：
1. **binding**（src/binding_prediction.R）：调 **netMHCpan** 算肽-HLA 结合 %Rank。
2. **similarity**（src/get_similarity.R）：Smith-Waterman(BLOSUM62) 比对肽与 `data/self_peps.txt`（自身肽）、`data/foreign_peps_noHIV.txt`（外源肽），算 self / foreign 相似计数。
3. **amplitude**（src/predict_amp.R）：`amp = self*foreign/binding`；`amp > 7024 → immunogenic=YES`。

**无需训练**：predictor 用固定阈值 7024 + repo 内 `data/` 参考肽集。`model_train_test/` 仅是作者训练/验证留档，本部署不用。

---

## 4 类信息（工具横评标准格式）

| 项 | 值 |
|----|----|
| 工具版本 | immunogenicity_predictor（GitHub andy90，master，无 tag） |
| 许可 | MIT（数字可发布） |
| 输入格式 | 肽 FASTA（8-11mer）+ HLAs 逗号串（去星，`HLA-A02:01`）；**HLA-matched** |
| 输出分数 | `amplitude`（连续值，越高越免疫原；amp>7024→YES） |
| 运行平台 | CPU；**依赖 netMHCpan 二进制（Linux/Darwin）→ 实际在 HPC 跑** |
| 分类 | netMHCpan binding × self/foreign 序列相似度，HLA-matched，单肽免疫原性 |

---

## 官方 API 出处（2026-06-29 核自 GitHub master）

### main.R（4 个硬编码全局变量 → 本部署参数化为 run_andy90.R）
```r
path_netmhcpan <- ".../netMHCpan-4.0/netMHCpan"   # netMHCpan-4.0
HLAs <- "HLA-A02:01,HLA-A03:01"                   # 逗号分隔，无空格，去星格式
file_fasta <- here("input.fasta")                # 肽 FASTA
final_output_file <- here("predicted_immunogenicity.csv")
source(here("src","binding_prediction.R"))
source(here("src","get_similarity.R"))
source(here("src","predict_amp.R"))
```

### src/binding_prediction.R（netMHCpan 调用 + 列解析）
```r
system(paste(path_netmhcpan, file_fasta, "-a", HLAs, ">", file_out))
# 解析：对每个 pep，取 V3==pep 的行的 col2(HLA) 和 col13(binding=%Rank)
df_pep_binding <- a_binding_table[a_binding_table$V3 == pep, c(2,13)]
colnames(...) <- c("HLA","binding")
```
> ⚠️ **`c(2,13)` 是按 netMHCpan-4.0 默认输出列位硬编码**：col2=MHC allele，col13=%Rank。
> 见 §netMHCpan 版本风险。

### src/predict_amp.R（输出列 + 方向）
```r
amp_thresh <- 7024
... mutate(amp = self*foreign/binding)
   mutate(immunogenic = if_else(amp > amp_thresh, "YES", "NO"))
data_final <- ... select(HLA,pep,amp,immunogenic) %>%
   set_names(c("HLA","peptide","amplitude","immunogenic")) %>% arrange(desc(amplitude))
write.csv(data_final, final_output_file, quote=FALSE, row.names=FALSE)
```
**输出 `predicted_immunogenicity.csv` 列：`HLA, peptide, amplitude, immunogenic`。**

---

## 分数方向（越高越免疫原）

| 原始输出 | 方向 | 输出列 | 变换 |
|---|---|---|---|
| `amplitude` (= self*foreign/binding) | 越高越免疫原（amp>7024→YES） | `MT_Andy90` / `WT_Andy90` | **直接用，不翻转** |

Spearman(ρ, ELISpot) 直接用 MT_Andy90（正相关方向正确）。

---

## HLA 格式

- andy90/netMHCpan 格式 = **去星**：`HLA-A02:01`（无 `*`）。
- 转换：`hla_to_andy90(h) = h.replace('*','')`，与项目 netmhcpan_ba 一致。
- prep_input.py 已做；parse_output.py 两侧去星归一匹配（规避 netMHCpan 输出 allele 是否带星的不确定性）。
- 我方 universe 全 HLA Class-I（HLA-A/B/C），无 Class-II，符合工具要求。

---

## 肽长 8-11mer

README："all the 8-11mers of SARS-CoV-2"；netMHCpan Class-I 默认支持 8-11mer。
- prep_input.py 过滤 8-11mer；12-14mer → andy90_skipped.csv → parse 阶段填 NaN。
- 本数据：7437 个唯一 8-11mer 肽，65 个 HLA，53583 个 (肽,HLA) 对（含 12-14mer）。

---

## 部署四件套（本目录）

| 文件 | 作用 |
|---|---|
| `prep_input.py` | uniq_pep_hla.csv → 过滤 8-11mer + 去星 + **按 HLA 分组写 fasta** + manifest |
| `run_andy90.R` | 官方 main.R 的参数化忠实包装（算法零改，原样 source 三个官方 src/*.R） |
| `run_andy90.py` | 读 manifest，逐 HLA 调 run_andy90.R，汇总 andy90_raw.csv |
| `parse_output.py` | andy90_raw.csv join universe（(肽,HLA) 双 key MT/WT）→ Andy90ImmPred_DS1DS2_scores.csv |
| `NOTES.md` | 本文件 |

### 逐 HLA 跑而非笛卡尔（效率 + 忠实）
官方 main.R 把所有 HLA 一次塞进逗号串、跑 7437×65 笛卡尔，且 similarity 在 HLA×肽 展开向量上重复算 —— 在 benchmark 规模下过慢。
本部署按 HLA 分组，只跑 uniq_pep_hla 里**实际出现**的 (肽,HLA) 对：
- `amplitude = self*foreign/binding`，self/foreign 只依赖肽、binding 只依赖 (HLA,肽)；
- 逐 HLA 跑得到的 amplitude 与一次跑全 HLA **数值完全一致**（零偏离，非提速近似）。

---

## 依赖安装

### 1. clone repo（主线跑，本 agent 不 clone）
```bash
git clone https://github.com/andy90/immunogenicity_predictor
# 假设 clone 到 <REPO>，下文 --repo 指向它
```

### 2. R 依赖
```r
# 本机 Windows R：E:\R-4.3.3\bin\Rscript.exe；HPC 用集群 R module
install.packages(c("tidyverse", "seqinr", "here", "doParallel"))
# Biostrings 走 Bioconductor（src/get_similarity.R 用 pairwiseAlignment + BLOSUM62）
if (!requireNamespace("BiocManager", quietly=TRUE)) install.packages("BiocManager")
BiocManager::install("Biostrings")
```

### 3. netMHCpan 二进制
- andy90 原版 = **netMHCpan-4.0**（DTU 学术许可）。
- 项目 HPC 现有 **4.1**：`/gpfs/work/bio/jiayu2403/quantimmu/ext_tools/netMHCpan-4.1/netMHCpan`（见 deploy/netmhcpan_ba/README）。
- **netMHCpan 是 Linux/Darwin 二进制 → 本工具实际在 HPC(Linux) 跑**（Windows 本机无法跑 netMHCpan）。

---

## ⚠️ netMHCpan 版本风险（最高 TODO，主线/researcher 拍板）

src/binding_prediction.R 用 `c(2,13)` 按 **netMHCpan-4.0 默认输出列位**硬编码取 col13=%Rank，
且 `amp_thresh=7024` 是作者在 **4.0** 上标定的。

- **4.1 列位**：默认 EL 输出 col2=MHC、col13=%Rank_EL 与 4.0 同位，`V3==pep` 过滤也一致 → 解析**大概率不崩**；
  但 4.1 的 %Rank_EL 标度与 4.0 %Rank 不同 → **amplitude 绝对值与 7024 阈值标定会漂移**。
- 影响：YES/NO 二分类标定失真；但 benchmark 用 **Spearman 排序**（连续 amplitude），排序受标度漂移影响较小。
- 处置选项（**TODO，需 researcher/主线确认，勿臆造**）：
  - (A) 装 **netMHCpan-4.0** 跑（完全忠实，推荐）；
  - (B) 用 HPC 现有 **4.1**，烟测核对输出 col13 确为 %Rank 后用，报告标注「netMHCpan-4.1 代 4.0，amplitude 阈值未重标，仅作排序用」caveat。
- **务必先跑 `--smoke` 核对 netMHCpan 实际输出列**，确认 col13 是 %Rank 再全量。

---

## 运行流水线（主线跑，本 agent 不跑任何代码）

```bash
# 变量
REPO=D:/YJ-Agent/project/meeting/QuantImmuBench          # 本仓
ANDY=$REPO/HPC/deploy/andy90_immpred
CLONE=/path/to/immunogenicity_predictor                 # git clone 目标
NETMHC=/gpfs/work/bio/jiayu2403/quantimmu/ext_tools/netMHCpan-4.1/netMHCpan  # 或 4.0
RSCRIPT=Rscript                                         # HPC R module；本机=E:/R-4.3.3/bin/Rscript.exe

# Step 1: 准备输入（过滤 8-11mer + 分组 fasta + manifest，~秒级）
python $ANDY/prep_input.py

# Step 2: 烟测（前 1 个 HLA，验 netMHCpan 调用 + 列解析 + raw 结构）
#   ⚠️ 先核对 netMHCpan 输出 col13=%Rank（见 §版本风险）
python $ANDY/run_andy90.py --repo $CLONE --netmhcpan $NETMHC --rscript $RSCRIPT --smoke 1

# Step 3: 全量（65 HLA；HPC 上跑，netMHCpan 是主成本）
python $ANDY/run_andy90.py --repo $CLONE --netmhcpan $NETMHC --rscript $RSCRIPT

# Step 4: 回贴 universe（~秒级）
python $ANDY/parse_output.py

# 最终输出：scripts/out/newtools/Andy90ImmPred_DS1DS2_scores.csv（34247 行）
```

---

## 已知坑

1. **netMHCpan 版本**：见 §版本风险（最高优先）。
2. **netMHCpan 不支持的 allele**：65 个 HLA 里少数罕见 allele（如 HLA-A*66:04/05/06…）可能不在 netMHCpan allele 列表 → 该 HLA 无输出行 → parse 自动填 NaN（run_andy90.py 对失败 HLA 跳过并续跑）。需在覆盖统计里看实际命中率。
3. **here() 锚定**：run_andy90.R 先 `setwd(repo)` 再 source，使 src 内 `here("data",...)` 解析到 clone 根（repo 含 .git，here 据此定 root）。勿改顺序。
4. **predict_amp.R 末行 `system("rm output.out")`**：Windows 无 `rm` 会无害报错（输出已写完）；HPC(Linux) 正常。每个 HLA 跑都覆盖 src/output.out，逐 HLA 串行无冲突。
5. **训练集重叠 caveat**：andy90 训练于 HIV/SARS-CoV-2 数据；与 benchmark 肽可能部分重叠，report 标注。
6. **doParallel(cores=2)**：src/get_similarity.R 硬编码 2 核（官方值，不改）。

---

## 残留 TODO（勿臆造，需确认）

- [ ] **netMHCpan 版本决策**（4.0 装 vs 4.1 代）—— researcher/主线拍板，见 §版本风险。
- [ ] netMHCpan 输出列位实测确认（烟测核 col13=%Rank）。
- [ ] netMHCpan 不支持的 allele 清单 + 实际命中率（全量跑后看 parse 覆盖统计）。
- [ ] clone 后确认 `data/self_peps.txt` / `data/foreign_peps_noHIV.txt` 存在（src/get_similarity.R 依赖）。
