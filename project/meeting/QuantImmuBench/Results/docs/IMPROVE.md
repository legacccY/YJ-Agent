# IMPROVE — 工具交付说明

> 交付文档（QuantImmuBench 新抗原免疫原性 benchmark，核心工具之一）。
> 涵盖六部分：工具简介 / 输入格式 / 参数设置 / 输出含义 / 最新 benchmark 结果（DS2 ELISpot）/ 部署环境。
> 全部基准数字已对 `analysis/metrics_ds2_16tools.csv` 与 `analysis/per_patient_spearman_16tools.csv` 逐一复核。
> 本工具 2026-06-28 才在 Phase B 跑通 P101/P102 全量（n_pep 86 → 101），是 benchmark 收尾的最后一块。

---

## 1. 工具简介

- **定位**：预测新表位（neoepitope）免疫原性的随机森林模型，**专为新表位排名优先级设计**。
- **方法原理**：基于 **RandomForest**，整合 22 个特征——MHC 结合亲和力（netMHCpan）、PRIME 的 TCR 识别分、肽段疏水性、自身相似性、稳定性（netMHCstabpan）以及肿瘤微环境特征等。提供三个变体：**Simple**（只要肽段 + HLA）/ **TME_excluded**（+ 细胞普遍率等）/ **TME_included**（+ RNA-seq 微环境）。输出连续 0–1 概率。
- **特点与优势**：连续分专为排名设计；整合 TCR 识别（PRIME）这一其它工具少见的信息维度；三变体适配有无 TME 数据的不同场景。
- **主要局限**：外部工具链多且部分需学术许可（netMHCpan / netMHCstabpan），是部署主要卡点；肽长受 netMHC 系工具限制（8–12 AA）。
- **出处**：
  - 论文：*IMPROVE: a feature model to predict neoepitope immunogenicity through broad-scale validation of T-cell recognition*, **Frontiers in Immunology**, 2024，DOI [10.3389/fimmu.2024.1360281](https://doi.org/10.3389/fimmu.2024.1360281)。
  - 代码仓库：https://github.com/SRHgroup/IMPROVE_tool ；论文 repo：https://github.com/SRHgroup/IMPROVE_paper
- **许可证**：IMPROVE 自身代码依上游 repo（SRHgroup/IMPROVE_tool）许可；PRIME / MixMHCpred / self_similarity 为学术免费。**注意**：依赖的 netMHCpan-4.1 / netMHCstabpan 属 DTU 系工具，含其结果的对外 benchmark 发布受 DTU 学术许可约束（投稿阶段需取书面同意）。

---

## 2. 输入数据模板 / 格式

- **文件格式**：TSV（tab 分隔）。
- **必填列**：mutant peptide（突变肽）+ wild-type peptide（野生型肽）+ HLA allele（4 位分辨率）。
- **可选列**：表达量 / 细胞普遍率 / 肿瘤微环境参数（决定用哪个变体）。
- **肽段长度**：8–12 AA。
- **是否需要基因组数据**：TME 变体需 RNA-seq（Kallisto）；Simple 变体只要肽段 + HLA。
- **HLA 格式示例**：`HLA-B40:02`、`HLA-A26:01`（4 位分辨率）。

---

## 3. 参数设置

**两步流程**（关键结构）：

- **步骤 1 — `bin/feature_calculations.py`**：算 22 个特征，需全套外部工具。
  - `--file <输入tsv>` `--dataset <名>` `--ProgramDir <外部工具根目录>` `--outfile <算好特征tsv>` `--TmpDir <临时目录>`；
  - 外部工具（netMHCpan / netMHCstabpan / PRIME / MixMHCpred / self_similarity）放同一 `--ProgramDir`。
- **步骤 2 — `bin/Predict_immunogenicity.py`**：在算好的特征上跑 RF 集成（**零外部工具**）。
  - `--file <算好特征tsv>` `--model {Simple|TME_excluded|TME_included}` `--outfile <输出tsv>`；
  - 每变体加载 5 个 RF（rf0–rf4 集成）。
- repo 自带 `data/calculated_features_test.tsv`（已算好特征）→ 步骤 2 可独立先跑通验证。

---

## 4. 输出格式及含义

- **输出**：TSV（输入全列 + 追加预测列）。
- **主输出列 `mean_prediction_rf`**：5-fold × RF 集成平均的免疫原性概率（连续 0–1，**越高越免疫原**）。
- **方向**：分数越高，预测免疫原性越强（设计上就用于排名优先级）。
- **范围**：连续 0–1（本项目 P101/P102 重跑值域实测 0.3083–0.7499）。
- **示例**（Simple 变体）：
  ```
  Mut_peptide    HLA_allele   mean_prediction_rf
  EEFLNSWML      HLA-B40:02   0.5146
  KAQPVTQATSF    HLA-B07:02   0.2459
  SVQTAKGMALF    HLA-A26:01   0.3193
  ```

---

## 5. 最新 benchmark 结果（DS2 ELISpot）

> 数据集 DS2（ELISpot 验证集）；2026-06-28 IMPROVE 跑通 P101/P102 后全量重算的 16 工具榜单。主指标为逐患者 Fisher-z，对照口径为全局 Spearman（max 聚合）。

- **覆盖率**：肽级口径 **n_pep = 101**（由 86 恢复至满覆盖）；子肽行口径下 **78.2%（26790/34247）** 有分（受 netMHC 系工具 8–12-mer 肽长限制，超长子肽跳过为 NaN）。本项目跑的是 **Simple 变体**，口径 = netMHCpan-4.1 + PRIME / MixMHCpred + SelfSim，跳过 stabpan（Stability 特征插补），Expression 特征为降级值。
- **核心三件套（统一口径）**：
  - 逐患者一致性（per-patient，9 名患者，Fisher-z 加权，**主指标**）：fisherz_weighted = **+0.250**，95% CI **[+0.021, +0.455]**——**CI 排除 0，逐患者层面稳健显著**。其中 P101 ρ = +0.085（n = 9）、P102 ρ = +0.486（n = 6）已正确填回。
  - 全局 Spearman ρ（max 聚合，**对照**）= **+0.252**（p = **0.011**，显著）；
  - AUC（SFC > 0）= **0.616**。
- **结论（诚实标注）**：IMPROVE 是 **16 工具中表现最好的工具**——是唯一同时在**全局（max ρ = 0.252, p = 0.011）与逐患者（Fisher-z = +0.250, CI [+0.021, +0.455] 排 0）双重显著**的工具。但相关系数绝对值仍属中等（ρ < 0.4），印证本 benchmark 的总体观察：现有工具对免疫反应强弱的定量能力普遍有限，为后续自研 QuantImmune 留出空间。
- **caveat**：Expression 特征为降级值、Stability 特征经插补（未用 netMHCstabpan），结论按 Simple 变体口径理解。

---

## 6. 部署环境简述

- **环境类型**：conda 虚拟环境 + 一组外部命令行工具，CPU 推理（RF）。预训练 `models.zip`（1.9GB，经 git-lfs）。
- **环境坑（重要）**：`models.zip` 是用 **numpy 2.x retrained 的 pkl**，必须用现代环境加载——建 env `improve_new`（python 3.11 + numpy 2.4 + scikit-learn 1.9 + pandas），并用 `Predict_immunogenicity_CLEAN_retrain.py`（老 py3.7 脚本会报 `No module named numpy._core`）。
- **🔑 IMPROVE 跑通的真根因（2026-06-28 定位）**：feature_calc 阶段 PRIME.x 长期 99% CPU 死循环、几十分钟 0 字节输出，曾被误判为「DTN 登录节点限流」「工具固有慢」。**真根因 = 调用脚本未 `conda activate`，导致 MixMHCpred 内部 `python3` 解析到系统 python（无 numpy）→ MixMHCpred 崩溃产空临时文件 → PRIME.x 的 `while(!file.eof())` 读空文件时 eofbit 永不置位 → 无限忙等**（GfellerLab/PRIME 源码层的经典 C++ eof 反模式 bug）。
- **修法（1 行，不偏离复现，仅修环境）**：在 feature_calc 子进程的环境注入 `PATH=<improve_bin>:$PATH`，使 MixMHCpred 的 `python3` 解析到带 numpy 的 improve env python。修后 7 个等位的 PRIME 评估由「死循环 1 字节」恢复为「秒级、21–27KB 正常输出」。
- **部署状态**：本地 WSL2 已跑通全量（步骤 2 早 SMOKE_PASS，步骤 1 feature_calc 此次彻底跑通）。HPC 版脚本同病（也用绝对 env python 不 activate），日后上 HPC 须同样注入 PATH。
- **详细逐条命令**见同目录《环境配置命令_回顾记录.md》，此处不重复。
