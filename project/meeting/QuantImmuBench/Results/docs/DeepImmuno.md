# DeepImmuno — 工具交付说明

> 交付文档（QuantImmuBench 新抗原免疫原性 benchmark，核心工具之一）。
> 涵盖六部分：工具简介 / 输入格式 / 参数设置 / 输出含义 / 最新 benchmark 结果（DS2 ELISpot）/ 部署环境。
> 全部基准数字已对 `analysis/metrics_ds2_16tools.csv` 与 `analysis/per_patient_spearman_16tools.csv` 逐一复核。

---

## 1. 工具简介

- **定位**：基于深度学习（卷积神经网络，CNN）预测肽段对 CD8+ T 细胞的免疫原性（HLA-I 限制）。另附带一个 GAN 模块用于生成免疫原性肽段，本项目只用其预测功能。
- **方法原理**：将「肽段序列 + HLA 伪序列」编码后送入 CNN，输出一个连续的 0–1 免疫原性分数，可直接用于强弱排名。
- **特点与优势**：
  - 输入极简，只需「肽段 + HLA」，不依赖任何基因组/测序数据；
  - 不依赖任何需学术许可的外部工具（如 netMHCpan），部署最干净；
  - CPU 即可推理，无需 GPU；
  - 同时提供在线 Web 服务（deepimmuno.research.cchmc.org）。
- **主要局限**：**肽段长度死限 9-mer 与 10-mer**，其他长度的肽段不会得到有效分数（详见第 5 节覆盖率）。
- **出处**：
  - 论文：*DeepImmuno: deep learning-empowered prediction and generation of immunogenic peptides for T-cell immunity*, **Briefings in Bioinformatics**, 2021，DOI [10.1093/bib/bbab160](https://doi.org/10.1093/bib/bbab160)。
  - 代码仓库：https://github.com/frankligy/DeepImmuno
- **许可证**：依上游 repo（frankligy/DeepImmuno）许可使用，具体条款以仓库 LICENSE 为准（开源学术用途）。本工具不引入 DTU 等需再分发授权的外部依赖，benchmark 数字无第三方再分发限制。

---

## 2. 输入数据模板 / 格式

- **文件格式**：CSV。
- **批量模式输入** = **无表头 CSV，两列：`peptide, HLA`**。
- **肽段长度限制**：仅 9-mer 和 10-mer（其他长度输出归零）。
- **HLA 格式**：星号型，如 `HLA-A*0201`、`HLA-B*5801`。
- **是否需要基因组数据**：否。
- **示例**（实测跑通）：
  ```
  HPPLMNVER,HLA-A*0201
  NLVPMVATV,HLA-A*0201
  GILGFVFTL,HLA-A*0201
  ```

---

## 3. 参数设置

- **无暴露的可调超参**；CNN（打分）与 GAN（生成）是两个独立模块，打分只用 CNN。
- **两种运行模式**：
  - 单条：`--mode single --epitope <肽段> --hla <HLA>`（结果打印到 stdout）；
  - 批量：`--mode multiple --intdir <输入csv> --outdir <输出目录>`（注意 outdir 末尾不带斜杠）。
- **实测命令**（须在 repo 根目录运行，脚本用相对路径读 `./data/`、`./models/`）：
  ```
  python deepimmuno-cnn.py --mode single --epitope HPPLMNVER --hla "HLA-A*0201"
  python deepimmuno-cnn.py --mode multiple --intdir input.csv --outdir <out>
  ```

---

## 4. 输出格式及含义

- **单条模式**：stdout 直接打印分数（如 `0.5324646830558777`）。
- **批量模式**：输出文件 `deepimmuno-cnn-result.txt`，**tab 分隔，3 列**：

  | 列 | 含义 |
  |---|---|
  | peptide | 肽段序列 |
  | HLA | HLA 等位基因 |
  | immunogenicity | 免疫原性分（连续 0–1，**越高越免疫原**）|

- **方向**：分数越高，预测免疫原性越强。
- **范围**：连续 0–1（作者声明无绝对阈值，常以 0.5 作参考）。
- **示例**（实测，合理性已验证）：
  ```
  peptide    HLA          immunogenicity
  HPPLMNVER  HLA-A*0201   0.5324648
  NLVPMVATV  HLA-A*0201   0.95676666   # CMV pp65 强免疫肽 → 高分合理
  GILGFVFTL  HLA-A*0201   0.8871707    # 流感 M1 强免疫肽 → 高分合理
  ```

---

## 5. 最新 benchmark 结果（DS2 ELISpot）

> 数据集 DS2（ELISpot 验证集）；2026-06-28 IMPROVE 跑通后全量重算的 16 工具榜单。主指标为逐患者 Fisher-z，对照口径为全局 Spearman（max 聚合），AUC 取 SFC > 0。

- **覆盖率**：在 16 工具基准的肽级口径下 **n_pep = 101**（与其它工具同口径）；但**有效覆盖低**——在交付 xlsx 的子肽行口径（34247 行）下 DeepImmuno（MT_DeepImmuno 列）非空 **11358 行（33.2%）**有分，因为只支持 9/10-mer，其余长度被迫归零。这是 DeepImmuno 的结构性短板。
- **逐患者一致性（per-patient，9 名患者，Fisher-z 加权，主指标）**：fisherz_weighted = **+0.015**，95% CI **[−0.214, +0.242]**（跨 0，不显著）。
- **全局 Spearman ρ（max 聚合，对照）**：ρ = **−0.089**（p = 0.376，不显著）。
- **AUC（max，SFC > 0）**：**0.469**。
- **结论（诚实标注）**：DeepImmuno 在 DS2 上**与免疫原性强弱基本无相关甚至轻微负相关**，AUC 接近随机。主因是肽长死限 9/10-mer 导致大量肽无有效分数（覆盖只有 ~33%），benchmark 表现不应据此否定其在 9/10-mer 子集上的能力，但作为通用强弱定量工具覆盖面不足。

---

## 6. 部署环境简述

- **环境类型**：conda 虚拟环境（无需容器），CPU 推理。
- **部署位置**：WSL2 Ubuntu 24.04（Windows NTFS 因 repo 含非法 `*` 文件名 `HLA-A*0101.json` 无法 checkout，故用 WSL ext4 原生）；env 名 `deepimmuno`（python 3.8 + tensorflow 2.3.0 + numpy 1.18.5 + pandas 1.1.1 + protobuf 3.20.3）。HPC 端亦 SMOKE_PASS（env `envs/deepimmuno`，单条烟测复现本地结果 0.5324646830558777）。
- **关键坑**：TensorFlow 2.3 较老，**protobuf 必须降到 3.20.3**，否则报 `Descriptors cannot be created directly`；CUDA 库缺失会自动回退 CPU（推理够快）。
- **详细逐条命令**见同目录《环境配置命令_回顾记录.md》，此处不重复。
