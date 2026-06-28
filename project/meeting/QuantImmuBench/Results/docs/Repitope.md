# Repitope — 交付说明文档

> 服务项目：QuantImmuBench（癌症个性化新抗原疫苗协作项目）。本文为对外交付说明，数字均经 CSV 复核。
> 数据真源：`analysis/metrics_ds2_16tools.csv`（全局指标）、`analysis/per_patient_spearman_16tools.csv`（患者分层）。
> 详细部署命令见同目录《环境配置命令_回顾记录.md》。

---

## 1. 工具简介

**Repitope（Ogishi & Yotsuyanagi，2019）** 是本 benchmark 中**唯一的 HLA-agnostic（不使用 HLA 信息）路线**。

- **原理 / 方法**：采用 Contact Potential Profiling（CPP，接触势能剖面）——以公开 TCR CDR3β 序列库模拟整个人群 TCR 库对一条肽序列各位置的 in-silico 接触势能，计算约 32 个最小特征；后端用 Extremely Randomized Trees（ERT，25 个模型 ensemble，5 seeds × 5 runs）训练于内置 MHCI_Human 数据集（约 7000 条 IEDB 及公开 T 细胞实验标注），输出概率均值。整个过程只看肽序列本身，不需要输入 HLA allele。
- **特点 / 优势**：
  - 唯一 HLA-agnostic 路线，可用来量化「HLA 限制信息到底值多少」——若它表现不差，说明序列内在特征已足够；若明显更差，则反证 HLA 限制是关键信息；
  - MIT 许可，部署零须申请，跑出的数字可自由发布；
  - CPP 具有较强的生物物理可解释性。
- **局限**：
  - 严格仅支持 8–11mer，12mer 及以上无法打分（填 NaN）；
  - HLA-agnostic 导致同一肽对不同 HLA 行得分相同，无法区分 HLA 特异性差异（须在报告脚注标注）；
  - R + rJava + extraTrees 安装繁琐（extraTrees 已从 CRAN 下架，需从 Archive 源码编译）；
  - 无预保存权重，每次运行需重训 25 个 ERT 模型（约 5–20 分钟）；
  - 训练集 MHCI_Human 可能与 benchmark 测试肽部分重叠，本 benchmark 统一用外推（apples-to-apples）并在报告标注此 caveat。
- **论文 DOI**：10.3389/fimmu.2019.00827（*Quantitative Prediction of the Landscape of T Cell Epitope Immunogenicity in Sequence Space*，2019，Frontiers in Immunology）。
- **repo**：https://github.com/masato-ogishi/Repitope（v3.1.7）。数据依赖：Mendeley Data DOI 10.17632/sydw5xnxpt.1（`FragmentLibrary.fst` + `MHCI/FeatureDF_Weighted.10000.fst`）。
- **许可证**：**MIT（完全自由，跑出的 benchmark 数字可自由发布）**。

---

## 2. 输入数据模板 / 格式

- **文件格式**：肽序列列表（R character vector；Python 预处理脚本生成 CSV 后由 R 读入）。
- **必填字段**：仅肽段序列（8–11mer 大写氨基酸），**不使用任何 HLA 信息**。
- **肽段长度**：严格 8–11mer（官方 `peptideLengthSet=8:11`）；12–14mer 在 benchmark 中填 NaN。
- **是否需基因组数据 / 野生型肽**：均不需要。
- **数据依赖**：需预先从 Mendeley Data 下载两个预计算文件（`FragmentLibrary.fst` 片段库、`MHCI/FeatureDF_Weighted.10000.fst` 训练集特征）。
- **输入样例**：
  ```
  peptide
  SIINFEKL
  LITGRLQSL
  FIAGLIAIV
  ```

> ⚠️ **核心 caveat（必须在报告标注）**：Repitope 不使用 HLA 信息，同一肽对所有 `HLA_Allele` 行填相同 `MT_Repitope` / `WT_Repitope` 值。

---

## 3. 参数设置

主要可调参数（命令行包装 `run_repitope.R`）：

| 参数 | 说明 |
|---|---|
| `--input` | 输入肽 CSV（`prep_input.py` 过滤 8–11mer 生成） |
| `--frag-lib` | `FragmentLibrary.fst` 路径 |
| `--feature-df` | `MHCI/FeatureDF_Weighted.10000.fst` 路径 |
| `--cores N` | 并行核数（建议 6–8，加速 `Features()` 计算） |
| `--smoke N` | 仅取前 N 肽烟测（快速验格式） |
| `featureSet` | 默认 `MHCI_Human_MinimumFeatureSet`（32 特征）；全量特征显著增加耗时 |

典型命令行：

```bash
%RSCRIPT% run_repitope.R --input repitope_input.csv \
  --frag-lib %FRAG_LIB% --feature-df %FEAT_DF% \
  --out repitope_raw.csv --cores 6
```

---

## 4. 输出格式及含义

R 原始输出 `repitope_raw.csv`：`Peptide`、`ImmunogenicityScore`（25 个 ERT 模型均值，∈ [0,1]）、`ImmunogenicityScore.cv`（变异系数，反映 25 模型一致性）。

最终汇总产物 `Repitope_DS1DS2_scores.csv` 关键列：

| 列 | 含义 |
|---|---|
| `Dataset` | DS1 / DS2 |
| `Peptide_ID` | 原始 ID |
| `HLA_Allele` | HLA-A\*xx:xx（仅保留用于 join，Repitope 不使用） |
| `MT_Subpeptide` | 突变肽序列 |
| `MT_Repitope` | MT 侧 ImmunogenicityScore（float / NaN） |
| `WT_Repitope` | WT 侧 ImmunogenicityScore（float / NaN） |

- **分数类型**：连续 [0,1] 概率。
- **分数方向**：**越高越免疫原，直接使用，无需翻转**。
- **能否定量免疫强弱**：可以（0–1 连续，可排名）。
- **覆盖率**：实测 34247 行中 MT/WT 各 22391 行有分（8–11mer 部分，约 65%）；12–14mer 共约 11856 行填 NaN。实测 ImmunogenicityScore 范围 0.06–0.61。

---

## 5. 最新 benchmark 结果（DS2 ELISpot）

> 以下为 IMPROVE 跑通后全量重算结果（P101 / P102 已用修正后 HLA 等位恢复，n_pep=101）。注意 Repitope HLA-agnostic，全局 max 聚合（对照口径）的 Spearman 已为 HLA 无关下的等价值。MIT 许可，数字可自由发布。

| 指标 | 数值 |
|---|---|
| n_pep（DS2 唯一肽） | 101 |
| 患者分层 Fisher-z（加权，**主指标**） | **+0.119**，95% CI [−0.112, +0.338]（9 名患者） |
| Spearman ρ（max 聚合，对照） | **+0.084**（p = 0.406，n.s.） |
| AUC（max，SFC > 0） | **0.620** |
| 覆盖率 | 约 65%（8–11mer；12–14mer 填 NaN） |

**解读**：作为唯一 HLA-agnostic 工具，Repitope 全局相关性弱（ρ≈+0.08，不显著），但 AUC（SFC > 0）达到 0.620，在 16 工具中属中上，说明纯序列内在特征仍携带一定免疫原性信号。其方向与患者内一致为正。

---

## 6. 部署环境简述

- 运行平台：本地 R 4.3.3（`E:\R-4.3.3\bin\Rscript.exe`），CPU 多核并行。
- 依赖：rJava（Java 17 + `JAVA_HOME`）+ extraTrees（CRAN Archive 源码版 + Rtools43 编译）+ 约 40 个 CRAN / Bioconductor 包。
- GPU 需求：无。外部许可证工具：无。
- 部署状态：✅ RUN_DONE（cores=6，7437 个 8–11mer 肽完成 CPP 特征 + ERT 训练 + 预测）。
- 部署文件：`HPC/deploy/repitope/`（`prep_input.py` / `run_repitope.R` / `parse_output.py` / `NOTES.md`）。
- 详细安装（含 Java / extraTrees 编译、Mendeley 数据下载）与运行命令见同目录《环境配置命令_回顾记录.md》。
