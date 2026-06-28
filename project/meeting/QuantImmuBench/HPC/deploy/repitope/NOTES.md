# Repitope — 部署说明（QuantImmuBench §工具扩张v2 第一波）

> 建档：2026-06-26。服务 quantimmu-bench 工具扩张 v2 第一波。
> 许可：MIT，数字可自由发布。
> R 来源：github.com/masato-ogishi/Repitope（作者 Masato Ogishi，Frontiers in Immunology 2019）

---

## 工具简介

Repitope 通过模拟 TCR-肽接触势能（Contact Potential Profiling, CPP）预测肽的免疫原性。
底层模型：Extremely Randomized Trees（ERT），训练于 MHCI_Human（~7000 肽，含 T 细胞实验标注）。
输出：ImmunogenicityScore（0-1 概率，越高越免疫原）。

**MHC-I 支持肽长：8-11mer**（`peptideLengthSet=8:11`，官方默认值）。
12-14mer 肽在 benchmark 中填 NaN（parse_output.py 阶段处理）。

---

## ⚠️ HLA-agnostic — 核心 caveat

**Repitope 不使用 HLA 信息，只依赖肽序列本身。**

- 预测输入：仅肽序列（8-11mer）
- 无 HLA binding 步骤：不区分 HLA-A/B/C allele
- 映射方式：同一肽对所有 HLA_Allele 行填相同 MT_Repitope / WT_Repitope 值
- benchmark 报告须标注：「Repitope is HLA-agnostic; scores reflect peptide-intrinsic immunogenicity without HLA constraint」

---

## 安装

### 步骤 1：R 依赖环境

```r
# 在 R 4.3.3 中运行（E:\R-4.3.3\bin\Rscript.exe）

# 1. Bioconductor 包（必须先装，devtools 安装 Repitope 时 Bioc 包不自动装）
if (!requireNamespace("BiocManager", quietly = TRUE)) install.packages("BiocManager")
BiocManager::install(c("Biostrings", "msa", "S4Vectors"))

# 2. CRAN 依赖（devtools 会自动处理，但 mlr/survival 较重，建议提前装）
install.packages(c(
  "devtools", "data.table", "fst", "readr",
  "extraTrees",   # 依赖 rJava！必须先配好 Java
  "mlr", "caret", "BBmisc", "pbapply",
  "foreach", "doParallel", "doSNOW",
  "purrr", "magrittr", "stringr", "stringi", "stringdist",
  "igraph", "Peptides", "seqinr",
  "ggplot2", "ggpubr", "ggsci", "gridExtra", "RColorBrewer", "scales",
  "matrixStats", "psych", "zoo", "rlecuyer",
  "car", "DescTools", "cvAUC", "pROC", "precrec",
  "survminer", "survival", "tidyr", "VennDiagram"
))

# 3. 安装 Repitope 本体
devtools::install_github("masato-ogishi/Repitope")
```

#### install_github 路径（确认来源）
```
masato-ogishi/Repitope
```
GitHub 地址：https://github.com/masato-ogishi/Repitope
版本：3.1.7（DESCRIPTION 核实，2026-06-26）
另有 Python 版：masato-ogishi/Repitope-Python（本 benchmark 不使用）

### 步骤 2：rJava / Java 17 配置

```
本机 Java：openjdk 17.0.16（已安装）

Windows 环境变量须设置：
  JAVA_HOME = C:\Program Files\Java\jdk-17（实际路径，依安装位置）
  PATH 含 %JAVA_HOME%\bin

验证：
  java -version   →  openjdk version "17.x.x"
  R -e "library(rJava); .jinit()"  →  无报错
```

> ⚠️ 版本风险：Repitope v3.1.7 依赖 R >= 3.6.0（本机 4.3.3 应兼容）。
> extraTrees（rJava 后端）在 Java 9+ 上运行需要 `--add-opens` JVM 参数，
> 已通过 `options(java.parameters = "-Xmx60G")` 在 run_repitope.R 中预设大堆；
> 若仍报 JVM 错误，尝试追加 `"-Djava.awt.headless=true"` 或 `"--add-opens=java.base/java.io=ALL-UNNAMED"`。

---

## Mendeley Data 数据下载（必须手动操作）

**DOI**：10.17632/sydw5xnxpt.1
**URL**：https://data.mendeley.com/datasets/sydw5xnxpt/1

需下载两个文件：

| 文件路径（Mendeley 上） | 本地路径建议 | 说明 |
|---|---|---|
| `FragmentLibrary.fst` | `/data/Repitope/FragmentLibrary.fst` | TCR CDR3b 片段库，用于 CPP 计算 |
| `MHCI/FeatureDF_Weighted.10000.fst` | `/data/Repitope/MHCI/FeatureDF_Weighted.10000.fst` | MHCI 训练集预计算特征（fragDepth=10000） |

> TODO：确切文件大小未从 Mendeley API 获取（网页 JS-rendered，curl 无法解析）。
> 建议打开 https://data.mendeley.com/datasets/sydw5xnxpt/1 确认文件名和大小后再下载。
> 估计：FragmentLibrary.fst 可能 1-5GB；FeatureDF_Weighted.10000.fst 可能 500MB-2GB。

---

## 运行流水线

```bash
# 本机 Rscript 路径
set RSCRIPT=E:\R-4.3.3\bin\Rscript.exe

# 本地 Mendeley 文件路径（下载后填入）
set FRAG_LIB=D:\data\Repitope\FragmentLibrary.fst
set FEAT_DF=D:\data\Repitope\MHCI\FeatureDF_Weighted.10000.fst

# 工作目录根
set REPO=D:\YJ-Agent\project\meeting\QuantImmuBench

# Step 1: 准备输入（过滤 8-11mer，~5 秒）
python %REPO%\HPC\deploy\repitope\prep_input.py

# Step 2: 烟测（5 个肽验算子/列结构，约 5-30 分钟）
%RSCRIPT% %REPO%\HPC\deploy\repitope\run_repitope.R ^
  --input  %REPO%\HPC\deploy\repitope\repitope_input.csv ^
  --frag-lib  %FRAG_LIB% ^
  --feature-df %FEAT_DF% ^
  --out    %REPO%\HPC\deploy\repitope\repitope_raw.csv ^
  --smoke  5

# Step 3: 全量预测（7437 个 8-11mer 肽，估计 30-120 分钟，多核加速）
%RSCRIPT% %REPO%\HPC\deploy\repitope\run_repitope.R ^
  --input  %REPO%\HPC\deploy\repitope\repitope_input.csv ^
  --frag-lib  %FRAG_LIB% ^
  --feature-df %FEAT_DF% ^
  --out    %REPO%\HPC\deploy\repitope\repitope_raw.csv ^
  --cores  8

# Step 4: 回贴 universe（~1 分钟）
python %REPO%\HPC\deploy\repitope\parse_output.py

# 最终输出：scripts/out/newtools/Repitope_DS1DS2_scores.csv（34247 行）
```

---

## 官方 R API 出处（2026-06-26 核自 GitHub master）

来源：github.com/masato-ogishi/Repitope/blob/master/R/

### Features()（特征计算）
```r
featureDT_list <- Features(
  peptideSet   = peptideSet,          # character vector，肽序列（8-11mer）
  fragLib      = fragLibDT,           # FST 加载的 fragment library
  aaIndexIDSet = "all",               # 使用所有 AAIndex AACP 量表
  fragLenSet   = 3:8,                 # 滑动窗口长度（与训练一致）
  fragDepth    = 10000,               # 片段库深度
  fragLibType  = "Weighted",
  featureSet   = MHCI_Human_MinimumFeatureSet,  # 只算 32 最小特征（大幅加速）
  seedSet      = 1:5,
  coreN        = N,
  tmpDir       = "./repitope_tmp"     # 中断可续
)
featureDT <- featureDT_list[[1]]      # 返回列表，取第一个元素
# 输出列：Peptide + 特征列（CPP + PeptDesc 合并）
```

### Immunogenicity_TrainModels()（训练 ERT）
```r
ert_models <- Immunogenicity_TrainModels(
  featureDF  = featureDF_MHCI[Peptide %in% MHCI_Human$Peptide, ],
  metadataDF = MHCI_Human[, .(Peptide, Immunogenicity)],
  featureSet = MHCI_Human_MinimumFeatureSet,   # 传列表，内部取 $MinimumFeatureSet
  seedSet    = 1:5,
  coreN      = N
)
# 返回：list(TrainModelResults, FeatureSet, SeedSet)，共 25 个 ERT 模型（5×5）
```

### Immunogenicity_Predict()（预测新肽）
```r
scoreDT_list <- Immunogenicity_Predict(
  externalFeatureDFList = list(featureDT),    # 新肽的特征 DF 列表
  trainModelResults     = ert_models
)
scoreDT <- scoreDT_list[[1]]
# 输出列：Peptide, ImmunogenicityScore, ImmunogenicityScore.cv
#   ImmunogenicityScore: 25 模型 ImmunogenicityScore 均值 [0-1]
#   ImmunogenicityScore.cv: CV（变异系数）
```

### 包内置数据（library(Repitope) 后直接可用）
```r
MHCI_Human                  # data.table：训练集肽+标注
MHCI_Human_MinimumFeatureSet # list：$MinimumFeatureSet = 32 特征名（character vector）
TCRSet_Public                # CDR3b 集合（生成 fragment library 用，Mendeley 版本已预生成）
```

---

## 分数方向归一说明（越高越免疫原）

| 原始输出 | 方向 | 输出列 | 变换 |
|---|---|---|---|
| `ImmunogenicityScore` | 越高越免疫原（0-1 概率） | `MT_Repitope` / `WT_Repitope` | **直接用** |

Spearman(ρ, ELISpot) 时直接使用 MT_Repitope（正相关方向正确）。

---

## 版本风险与已知问题

### 1. R 版本兼容性风险
- Repitope v3.1.7 依赖 R >= 3.6.0，本机 R 4.3.3 **理论兼容**。
- 依赖包共 ~40 个（含 Bioconductor），可能有版本冲突。
- 关键风险点：`mlr 2.14.0`（已停止维护，CRAN 目前 2.19.x）；`caret 6.0-84`（现 6.0-94+）。
- TODO：如安装失败，尝试指定老版本：`devtools::install_version("mlr", version="2.14.0")`。

### 2. rJava / extraTrees Java 兼容性
- `extraTrees` 依赖 rJava + Java backend（.jar 文件）。
- Java 17 与旧 Java API（pre-Java 9）有 module 封装问题，可能报 `InaccessibleObjectException`。
- 解决方案（在 run_repitope.R 已预置）：`options(java.parameters = c("-Xmx60G", "-Xms4G"))`
- 若仍报错：追加 `"--add-opens=java.base/java.io=ALL-UNNAMED"` 到 java.parameters。

### 3. 训练集肽重叠
- MHCI_Human 数据集（约 7000 肽）来自 IEDB 及多个公开数据库。
- benchmark 的 MT/WT 肽可能部分来自相同数据库 → 存在重叠风险。
- `run_repitope.R` 中已添加重叠计数警告（stderr 输出）。
- 对于出现在训练集中的肽，Repitope 推荐用 `Immunogenicity_Score()`（交叉验证）
  而非 `Immunogenicity_Predict()`（外推）。本 benchmark 统一用外推（apples-to-apples），
  在最终报告中标注此 caveat。

### 4. 计算时间估计（粗估，待实测更新）
| 步骤 | 肽数 | 估计时间 |
|---|---|---|
| Features()（特征计算） | 7437 | 30-120 分钟（8核） |
| Immunogenicity_TrainModels() | 训练集 ~7000 | 5-20 分钟 |
| Immunogenicity_Predict() | 7437 | 2-5 分钟 |
| **总计** | | **40-150 分钟** |

> NOTE：使用 `featureSet=MHCI_Human_MinimumFeatureSet` 只计算 32 个特征，
> 相比全量特征（数百个）大幅减少计算量。若仍太慢，可通过 `--cores` 增大并行数。

### 5. Mendeley 文件路径名（TODO 待确认）
- README 示例路径：`FragmentLibrary.fst` + `MHCI/FeatureDF_Weighted.10000.fst`。
- 实际 Mendeley 文件名以下载页为准，若不同请相应修改 `--frag-lib` / `--feature-df` 参数。

---

## HLA-agnostic 映射方案（parse_output.py 实现）

```
universe.csv (34247 行，4-key 唯一)
  ↓  MT_Subpeptide → peptide_lookup → MT_Repitope
  ↓  WT_Subpeptide → peptide_lookup → WT_Repitope
  HLA_Allele 字段：忽略（HLA-agnostic）
  同肽不同 allele 行：填相同值
  12-14mer / 未打分肽：填 NaN
```

benchmark 报告时在工具描述脚注中标注：
> "Repitope scores are HLA-agnostic (peptide sequence-only);
>  the same ImmunogenicityScore is assigned to all HLA alleles sharing the same peptide."

---

## 4 类信息（工具横评标准格式）

| 项 | 值 |
|----|----|
| 工具版本 | Repitope v3.1.7（GitHub masato-ogishi/Repitope） |
| 许可 | MIT |
| 输入格式 | 肽序列（8-11mer）；不使用 HLA 信息 |
| 输出分数 | ImmunogenicityScore（0-1 概率，越高越免疫原） |
| 运行平台 | CPU（多核并行，R + rJava extraTrees） |
| 分类 | TCR-peptide 接触势能模拟，HLA-agnostic，群体水平免疫原性预测 |
