# PredIG — 工具交付说明

> 交付文档（QuantImmuBench 新抗原免疫原性 benchmark，核心工具之一）。
> 涵盖六部分：工具简介 / 输入格式 / 参数设置 / 输出含义 / 最新 benchmark 结果（DS2 ELISpot）/ 部署环境。
> 全部基准数字已对 `analysis/metrics_ds2_16tools.csv` 与 `analysis/per_patient_spearman_16tools.csv` 逐一复核。

---

## 1. 工具简介

- **定位**：T 细胞表位免疫原性预测器，覆盖癌症新抗原 / 非经典抗原 / 病原体抗原三类，是一个**可解释**的预测器。
- **方法原理**：基于 **XGBoost**（R 实现），整合 12 个特征——蛋白酶体切割（NetCleave）、TAP 转运 / 提呈（NetCTLpan）、HLA-I 结合（MHCflurry / NOAH）以及肽段物理化学描述符（疏水性、分子量、电荷、稳定性、TCR 接触位等），输出连续 0–1 的 PredIG 分数，并可用 SHAP 做特征级解释。
- **特点与优势**：
  - 连续分数可定量排名，且附带 12 个可解释特征列；
  - 三类抗原各有专用模型（neoant / noncan / path）；
  - 官方提供 Docker / Singularity 容器，把全部依赖打包，HPC 部署友好。
- **主要局限**：核心依赖一组外部预测器（NetCleave / NetCTLpan / MHCflurry / NOAH），其中 NetCTLpan 含 DTU 系工具——官方容器已打包，但其跑出的结果在对外发布时受相应学术许可约束（见第 6 节与许可说明）。
- **出处**：
  - 论文：*PredIG: an interpretable predictor of T-cell epitope immunogenicity*, **Genome Medicine**, 2025，DOI [10.1186/s13073-025-01569-8](https://doi.org/10.1186/s13073-025-01569-8)。
  - 代码仓库：https://github.com/BSC-CNS-EAPM/PredIG ；容器仓库：https://github.com/BSC-CNS-EAPM/predig-containers
- **许可证**：PredIG 自身代码依上游 repo（BSC-CNS-EAPM/PredIG）许可。**注意**：容器内打包的 NetCTLpan 属 DTU 系工具，含其结果的对外 benchmark 发布需遵守 DTU 学术许可（未经书面同意不得向第三方发布在其软件上跑出的结果），投稿阶段处理。

---

## 2. 输入数据模板 / 格式

支持三种输入模式（CSV 或 FASTA）：

1. **CSV-Recombinant**（本项目实测采用，避开 UniProt 库）：列 `epitope, HLA_allele, protein_seq, protein_name`。
2. **CSV-Uniprot**：peptide / HLA-I allele / UniProt ID。
3. **FASTA**：蛋白序列文件 + CSV（HLA 用 4 位分辨率格式 `HLA-A_02:01`），默认生成 8–14 AA 表位。

- **肽段长度**：FASTA 模式默认 8–14 AA。
- **HLA 格式**：CSV 模式 `HLA_allele` 列；FASTA 模式用 `HLA-A_02:01` 样式。
- **是否需要基因组数据**：否。

---

## 3. 参数设置

- **三类抗原模型可选**（`--modelXG`）：`neoant`（新抗原）/ `noncan`（非经典）/ `path`（病原体）。
- **输入类型**（`--type`）：`recombinant` / `uniprot` / `fasta`。
- 无暴露的连续超参调节接口。
- **实测命令**（recombinant 模式）：
  ```
  docker run --rm -v <workdir>:/work bsceapm/predig:latest /work/input.csv \
    -o /work/out.csv --modelXG neoant --type recombinant
  ```
  入参：`input_file`（位置参）+ `-o 输出` + `--modelXG {neoant|noncan|path}` + `--type {uniprot|recombinant|fasta}` + `--alleles`（fasta 模式用）。

---

## 4. 输出格式及含义

- **输出**：CSV，列含 `ID, epitope, HLA_allele, PredIG, NOAH, NetCleave, Hydrophobicity_peptide, MW_peptide, Charge_peptide, Stab_peptide, TCR_contact, ...`。
- **主输出列 `PredIG`**：0–1 连续免疫原性概率，**1 = 最高免疫原性**（越高越强）。
- **方向**：PredIG 主分越高越免疫原；结合类辅助列（如 %Rank）越小越强。
- **范围**：PredIG ∈ [0, 1] 连续。
- **可解释性**：附 12 个特征列，可做 SHAP 解释。
- **示例**：实测 `SLLMWITQV` 的 PredIG = 0.0061（弱）。

---

## 5. 最新 benchmark 结果（DS2 ELISpot）

> 数据集 DS2（ELISpot 验证集）；2026-06-28 全量重算的 16 工具榜单。主指标为逐患者 Fisher-z，对照口径为全局 Spearman（max 聚合），AUC 取 SFC > 0。

- **覆盖率**：肽级口径 **n_pep = 101**（满覆盖）；子肽行口径（34247 行）下 MT_PredIG 主输出覆盖 **100%（34247/34247）**；原生子特征覆盖：**NOAH 67.9%、NetCleave 63.3%、Stability/TCR_contact 88.3%**。
- **逐患者一致性（per-patient，9 名患者，Fisher-z 加权，主指标）**：fisherz_weighted = **+0.229**，95% CI **[−0.003, +0.437]**——CI 下界**恰好擦到 0**（−0.003），逐患者层面方向一致为正但未稳健显著。
- **全局 Spearman ρ（max 聚合，对照）**：ρ = **+0.201**（p = **0.044**，显著）。
- **AUC（max，SFC > 0）**：**0.663**。
- **结论（诚实标注）**：PredIG 是 16 工具中表现较好的之一——**全局 max 聚合 p < 0.05 的两个工具之一**（另一个是 IMPROVE）。但逐患者 CI 擦 0，稳健性略逊于 IMPROVE。整体相关仍属中弱（ρ < 0.4），符合本 benchmark「现有工具普遍弱相关」的总体观察。

---

## 6. 部署环境简述

- **环境类型**：官方 Docker / Singularity 容器（容器内打包全套 predictors，无需逐一装外部工具）。
- **部署位置**：本地 SMOKE_PASS（镜像 `bsceapm/predig:latest`，14.4GB，经本地代理拉取）；HPC SMOKE_PASS（`predig.sif` 4.6GB，`singularity run --writable-tmpfs -B ...`，recombinant 烟测复现本地结果 PredIG = 0.0061380286）。
- **运行需挂载**：工作目录 → `/predig`（或 `/work`）、UniProt 库 → `/uniprot`（recombinant 模式可省 UniProt）。
- **关键坑**：Docker Hub 在 HPC 不通 → 本地拉镜像后转 Singularity；recombinant 模式可避开 UniProt 大库。
- **详细逐条命令**见同目录《环境配置命令_回顾记录.md》，此处不重复。
