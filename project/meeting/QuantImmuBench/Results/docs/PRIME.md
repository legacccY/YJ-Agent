# PRIME 工具交付说明

> 服务项目：QuantImmuBench（癌症个性化新抗原疫苗协作项目）—— 工具部署与 benchmark 交付文档
> 数据红线：本文所有 benchmark 数字逐一溯源 `analysis/metrics_ds2_16tools.csv` 与 `analysis/per_patient_spearman_16tools.csv`，未自创。

---

## 1. 工具简介

- **原理 / 方法**：PRIME（PRedictor of IMmunogenic Epitopes）是预测 neo-epitope **免疫原性**的轻量打分模型。它整合三类信息：MixMHCpred 给出的 HLA-I 提呈分 + 肽段 TCR 接触位点的氨基酸频率特征 + 肽长，输出连续的免疫原性排名分。非深度学习（线性 / logistic 类轻量模型）。
- **特点**：
  - 直接输出免疫原性连续分数（可量化强弱），契合本项目「强弱定量」目标。
  - **依赖链最短**：唯一外部依赖是同实验室的 MixMHCpred，**无 netMHCpan / DTU 学术许可负担**，是 Wave3 五工具中部署最易的。
  - 输入只需突变肽段 + HLA 等位，不要 WT 肽 / 表达量 / 基因组数据。
- **论文**：
  - PRIME 1.0 — *Prediction of neo-epitope immunogenicity reveals TCR recognition determinants...*, Cell Reports Medicine, 2021. DOI: **10.1016/j.celrep.2021.100194**
  - PRIME 2.0 — *Improved predictions of antigen presentation and TCR recognition with MixMHCpred2.2 and PRIME2.0...*, Cell Systems, 2023. DOI: **10.1016/j.cels.2022.12.002**（PMID 36603583）
- **代码仓库**：https://github.com/GfellerLab/PRIME （v2.1，master 分支）；依赖 https://github.com/GfellerLab/MixMHCpred （v3.0+）。
- **许可证**：学术非商用免费；商用需向 Ludwig Institute 申请（nbulgin@lcr.org）。MixMHCpred 同属 Gfeller lab，学术免费，无 DTU 许可。

---

## 2. 输入数据模板 / 格式

- **文件格式**：纯文本（每行一条肽段）或 FASTA（`>` 开头行跳过）。
- **必填字段**：肽段序列 + HLA 等位（HLA 由命令行 `-a` 指定，多个用逗号分隔）。
- **肽段长度**：8–14 AA。
- **HLA 格式**：简写 `A0101` 或标准 `A01:01` / `HLA-A01:01` / `HLA-A*01:01` 均可。
- **是否需基因组数据**：否（只要突变肽 + HLA）。

**示例**（仓库 `test/test.txt` = 147 行肽段，每行一条）：

```
VMLQAPLFT
GILGFVFTL
...
```

命令行给 allele：`-a A0101,A2501,B0801,B1801`

---

## 3. 参数设置

- `-i`：输入肽段文件
- `-o`：输出文件
- `-a`：HLA 等位列表（逗号分隔）
- `-mix`：MixMHCpred 路径（不传则查 PATH）
- 模型变体：v2.1（最新，依赖 MixMHCpred v3.0+）

**完整命令示例**：
```
./PRIME -i test/test.txt -o test/out.txt -a A0101,A2501,B0801,B1801 -mix <MixMHCpred 路径>
```

---

## 4. 输出格式及含义

- **输出文件**：文本（空格 / tab 分隔）。基础 5 列，多 allele 时展开为 17 列（每 allele 各出 %Rank + Score + %RankBinding）。
- **关键列**：

| 列 | 含义 | 方向 / 范围 |
|---|---|---|
| Peptide | 肽段序列 | — |
| %Rank（best allele） | 跨所有 allele 最低 PRIME %Rank | **越低越强**，0 最优（0–100） |
| Score（best allele） | 对应最优 allele 的 PRIME Score | **越高越强免疫原性**（连续） |
| %RankBinding（best allele） | MixMHCpred 纯结合 %Rank（对照） | 越低结合越强 |
| BestAllele | 最优 allele | — |

- **能否定量免疫强弱**：是（PRIME Score / %Rank 连续）。
- 示例：`VMLQAPLFT  %Rank=3.901  Score=0.010242  BestAllele=B0801`。

---

## 5. 最新 benchmark 结果（DS2 ELISpot）

> 数据集：DS2 ELISpot，101 肽 / 9 患者；IMPROVE 跑通后 16 工具全量重算。主指标为逐患者 Fisher-z，对照口径为全局 Spearman（max 聚合），AUC 取 SFC > 0。
> 数字来源：`analysis/metrics_ds2_16tools.csv`、`analysis/per_patient_spearman_16tools.csv`。

| 指标 | 数值 |
|---|---|
| n_pep（覆盖肽数） | 101 / 101（全覆盖；9 患者，per-patient n_used=9，n_dropped=0） |
| per-patient Fisher-z 加权 ρ [95% CI]（**主指标**） | **+0.279 [+0.050, +0.481]**（CI 不含 0，**患者内显著**） |
| Spearman ρ（max 聚合，对照） | **+0.158**，p = 0.114（不显著） |
| AUC（max，SFC > 0） | 0.517 |

**解读**：PRIME 是 Wave3 四个免疫原性工具中 benchmark 表现最强的——其 **per-patient Fisher-z 加权相关的 95% CI 整体大于 0**（+0.279 [+0.050, +0.481]），是该批工具中唯一在患者内层面达到统计显著正相关的工具；全局 max 聚合 ρ = +0.158 方向一致但未达显著（p = 0.114）。

---

## 6. 部署环境简述

- **跑的版本**：官方权重（PRIME v2.1 + MixMHCpred v3.0），**已验证 r=1.0**——147 行烟测输出与官方 `test/out_compare.txt` 完全一致（diff=0）。
- **环境**：HPC conda env `envs/prime`（Python 3.11 + numpy / pandas / scipy / logomaker / matplotlib）。PRIME 主体为 C++（`g++ -O3` 编译）+ Perl + Shell；MixMHCpred 3.0 为 Python 实现（无需编译，可选 MAFFT）。CPU 推理，无 GPU 需求。
- **仓库位置**：`~/quantimmu/tools_repos/PRIME` 与 `~/quantimmu/tools_repos/MixMHCpred`。
- 详细环境配置命令见同目录《环境配置命令_回顾记录.md》。
