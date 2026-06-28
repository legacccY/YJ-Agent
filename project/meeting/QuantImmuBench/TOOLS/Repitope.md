# Repitope — 信息收集卡（PPT 素材）

> 4 类信息来源：DEPLOY_TRACKER §Tier-0 + HPC/deploy/repitope/NOTES.md（2026-06-26 核实）。实跑项以「实测」标注。

## 0. 定位 / 一句话

**唯一 HLA-agnostic 路线**：模拟整个人群 TCR 库对肽序列的 in-silico 接触势能（Contact Potential Profiling, CPP），测肽序列本身的免疫原性潜力，无需输入 HLA allele 信息。  
**输出 ImmunogenicityScore ∈ [0,1]，越高越免疫原**。支持 8–11mer（长于 11mer 填 NaN）。  
R 语言 + Extremely Randomized Trees（ERT）后端；MIT 许可；2019 Frontiers in Immunology。

## 1. 输入数据模板 / 格式

- **文件格式**：肽序列列表（R character vector；Python prep 脚本生成 CSV 再由 R 读入）
- **必填字段**：仅**肽段序列**（8–11mer 大写氨基酸），**不使用 HLA 信息**
- **肽段长度**：**严格 8–11mer**（官方 `peptideLengthSet=8:11`）；12–14mer 在 benchmark 中填 NaN
- **HLA 格式**：**不接受 HLA 输入**（HLA-agnostic）
- **是否需基因组数据**：否
- **数据依赖**：需从 Mendeley Data（DOI 10.17632/sydw5xnxpt.1）下载两个预计算文件：
  - `FragmentLibrary.fst`：TCR CDR3b 片段库（CPP 计算用）
  - `MHCI/FeatureDF_Weighted.10000.fst`：MHCI 训练集预计算特征（fragDepth=10000）
- **实测输入规模**（实测）：7437 个唯一 8–11mer 肽（从 benchmark universe 过滤出）
- **实测输入样例**（实测）：
  ```
  peptide
  SIINFEKL
  LITGRLQSL
  FIAGLIAIV
  ```

⚠️ **核心 caveat（必须在报告中标注）**：Repitope 不使用 HLA 信息，同一肽对所有 HLA_Allele 行填相同 MT_Repitope / WT_Repitope 值。

## 2. 运行参数设置

### R API（核心函数）

```r
library(Repitope)

# Step 1: 计算 CPP 特征
featureDT_list <- Features(
  peptideSet   = peptideSet,               # character vector，8-11mer
  fragLib      = fragLibDT,                # 从 FragmentLibrary.fst 加载
  aaIndexIDSet = "all",                    # 使用所有 AAIndex AACP 量表
  fragLenSet   = 3:8,                      # 滑动窗口长度（与训练一致）
  fragDepth    = 10000,
  fragLibType  = "Weighted",
  featureSet   = MHCI_Human_MinimumFeatureSet,  # 仅 32 个最小特征（大幅加速）
  seedSet      = 1:5,
  coreN        = N,                        # 并行核数
  tmpDir       = "./repitope_tmp"          # 中断可续
)
featureDT <- featureDT_list[[1]]

# Step 2: 训练 ERT 模型（每次运行重训，约 5-20min）
ert_models <- Immunogenicity_TrainModels(
  featureDF  = featureDF_MHCI[Peptide %in% MHCI_Human$Peptide, ],
  metadataDF = MHCI_Human[, .(Peptide, Immunogenicity)],
  featureSet = MHCI_Human_MinimumFeatureSet,
  seedSet    = 1:5,
  coreN      = N
)
# 返回 25 个 ERT 模型（5 seeds × 5 runs）

# Step 3: 预测新肽
scoreDT_list <- Immunogenicity_Predict(
  externalFeatureDFList = list(featureDT),
  trainModelResults     = ert_models
)
scoreDT <- scoreDT_list[[1]]
# 输出列：Peptide, ImmunogenicityScore, ImmunogenicityScore.cv
```

### 命令行（本 benchmark 调用方式）

```bash
# Windows 本地
set RSCRIPT=E:\R-4.3.3\bin\Rscript.exe
set FRAG_LIB=D:\data\Repitope\FragmentLibrary.fst
set FEAT_DF=D:\data\Repitope\MHCI\FeatureDF_Weighted.10000.fst

# 全量预测（7437 肽，6 核，约 30-120 分钟）
%RSCRIPT% HPC\deploy\repitope\run_repitope.R \
  --input repitope_input.csv \
  --frag-lib %FRAG_LIB% \
  --feature-df %FEAT_DF% \
  --out repitope_raw.csv \
  --cores 6
```

### 主要可调参数

| 参数 | 说明 |
|---|---|
| `--cores N` | 并行核数（建议 6–8，加速 Features() 计算） |
| `--smoke N` | 仅取前 N 肽烟测（快速验格式） |
| `featureSet` | 默认 `MHCI_Human_MinimumFeatureSet`（32 特征）；全量特征大幅增加时间 |

### 流水线

```bash
python HPC/deploy/repitope/prep_input.py    # 过滤 8-11mer，生成 repitope_input.csv
%RSCRIPT% run_repitope.R --cores 6         # CPP 特征 + 训练 + 预测（~30-120min）
python HPC/deploy/repitope/parse_output.py  # 回贴 universe，HLA-agnostic 同肽各 allele 填同值
```

⚠️ **安装依赖较复杂**：需 R 4.x + rJava（Java 17 + JAVA_HOME）+ `extraTrees`（CRAN 已下架，需从 Archive 安装源码版 + Rtools43 编译）+ ~40 个 CRAN/Bioconductor 包。

## 3. 输出数据格式 + 含义

### R 原始输出（`repitope_raw.csv`）

| 列 | 含义 |
|---|---|
| `Peptide` | 肽段序列（8–11mer） |
| `ImmunogenicityScore` | 25 个 ERT 模型均值，∈ [0,1]，越高越免疫原 |
| `ImmunogenicityScore.cv` | 变异系数（CV），反映 25 模型间一致性 |

### 最终产物（`Repitope_DS1DS2_scores.csv`）

| 列 | 含义 |
|---|---|
| `Dataset` | DS1 / DS2 |
| `Peptide_ID` | 原始 ID |
| `HLA_Allele` | HLA-A*xx:xx（Repitope 不使用，仅保留用于 join） |
| `MT_Subpeptide` | 突变肽序列 |
| `MT_Repitope` | MT 侧 ImmunogenicityScore（float / NaN） |
| `WT_Repitope` | WT 侧 ImmunogenicityScore（float / NaN） |

- **分数类型**：连续 [0,1] 概率
- **分数方向**：**越高越免疫原，直接用，无需翻转**
- **能否定量免疫强弱**：✅ 是（0-1 连续，可排名）← 项目核心目标
- **实测输出**（实测）：
  - 34247 行；MT/WT 各 22391 行有分（8–11mer 部分）
  - **12–14mer → NaN**（超长度限制，共约 11856 行）
  - ImmunogenicityScore 范围：**0.06–0.61**

⚠️ **HLA-agnostic 映射**：同一肽对应的所有 HLA_Allele 行填相同值；parse_output.py 以 MT_Subpeptide → peptide_lookup → MT_Repitope 方式回贴，HLA_Allele 字段忽略。

## 4. 简介（特点 / 优势）

- **方法**：Contact Potential Profiling（CPP）—— 用公开 TCR CDR3b 序列库，对每条肽序列模拟整个 TCR 库对其各位置的 in-silico 接触势能，计算 ~32 个最小特征集；Extremely Randomized Trees（ERT，25 模型 ensemble）训练于 MHCI_Human 数据集（~7000 肽，IEDB 等公开 T 细胞实验标注），输出概率均值
- **训练数据**：`MHCI_Human`（包内置，约 7000 条，IEDB 及多个公开数据库）
- **特点 / 优势**：
  - **唯一 HLA-agnostic 路线**：量化「HLA 限制信息」到底值多少；如果不差说明序列内在特征够用；如果很差，反证 HLA 限制是关键
  - MIT 许可，无许可障碍，部署零须申请
  - CPP 生物物理可解释性强
- **局限**：
  - **严格 8–11mer**，12mer+ 无法打分（NaN），覆盖率 ~65% universe 行
  - **HLA-agnostic**：同肽不同 HLA 行得分相同，无法区分 HLA 特异性差异（须在报告脚注标注）
  - R + rJava + extraTrees 安装繁琐；extraTrees 已从 CRAN 下架，需从 Archive 源码编译
  - 每次运行重训 25 个 ERT 模型（无预保存权重），约 5–20min
  - 训练集 MHCI_Human 可能与 benchmark 测试肽部分重叠（已在 run_repitope.R 中加重叠警告）

## 部署记录

- **repo**：https://github.com/masato-ogishi/Repitope（v3.1.7）
- **论文**：*Quantitative Prediction of the Landscape of T Cell Epitope Immunogenicity in Sequence Space*，2019 · Frontiers in Immunology，DOI [10.3389/fimmu.2019.00827](https://doi.org/10.3389/fimmu.2019.00827)
- **语言 / 框架**：R 4.3.3（E:\R-4.3.3\bin\Rscript.exe）；rJava（Java 17）；extraTrees（CRAN Archive 源码版 + Rtools43 编译）；fst；data.table
- **数据依赖**：Mendeley Data DOI 10.17632/sydw5xnxpt.1（FragmentLibrary.fst + MHCI/FeatureDF_Weighted.10000.fst）；实测下载 `*_RepitopeV3.fst` 仅 127MB
- **外部许可证工具**：无
- **GPU 需求**：无（CPU 多核并行）
- **许可**：MIT（完全自由，发数字 ✅）
- **部署状态**：✅ **RUN_DONE**（本地 R 4.3.3，cores=6，7437 肽 CPP 特征+ERT）
- **已知 bug 修复**：修 2 个 coder bug（ofile 变量名 + `$MinimumFeatureSet` 取列表元素方式）
- **部署文件**：`HPC/deploy/repitope/`（prep_input.py / run_repitope.R / parse_output.py / NOTES.md）
- **实测输出**：`Repitope_DS1DS2_scores.csv`，34247 行；有分 22391（8–11mer）；12–14mer NaN；ImmunogenicityScore 0.06–0.61

---

**为什么选作对比**：原 10 工具几乎全是 HLA-aware；Repitope 是唯一 HLA-agnostic 路线，量化「HLA 限制信息」到底值多少——HLA-agnostic 若不差说明序列内在特征够用；若很差反证 HLA 限制是关键。MIT 许可、部署零障碍。（来源：NEWTOOLS_LIT_MATRIX §二 §2）
