# PRIME — 信息收集卡（PPT 素材）

> 第二批 5 工具（Wave 3，原李紫晨负责，现并入余嘉测试）。事实来自官方 repo + 论文，实测项标 TODO。
> **注**：PRIME 已在 HPC `tools_repos/PRIME`（之前作 IMPROVE 依赖 clone 过）→ 半部署，部署链最短。

## 0. 定位 / 一句话
预测 neo-epitope **免疫原性**的轻量模型（PRedictor of IMmunogenic Epitopes）——整合 MixMHCpred 的 HLA-I 提呈分 + 肽段 TCR 接触位点氨基酸频率 + 肽长，输出连续免疫原性排名分。非深度学习（线性/logistic 类）。

## 1. 输入数据模板 / 格式
- 文件格式：纯文本（每行一条肽段）或 FASTA（`>` 开头行跳过）
- 必填字段：肽段序列 + HLA allele（命令行 `-a` 指定，多个逗号分隔）
- 肽段长度限制：8–14 AA
- HLA 格式：简写 `A0101` 或标准 `A01:01` / `HLA-A01:01` / `HLA-A*01:01` 均可
- 是否需基因组数据：**否**（只要 mutant peptide + HLA，不要 WT 肽/表达量）
- **实测输入样例**：TODO

## 2. 运行参数设置
- 主要参数：`-i` 输入肽段文件、`-o` 输出、`-a` HLA allele 列表、`-mix` 指定 MixMHCpred 路径
- 模型变体：v2.1（最新，依赖 MixMHCpred v3.0+）
- **实测命令行**：TODO

## 3. 输出数据格式 + 含义
- 输出文件格式：文本（空格/tab 分隔，5 列）
- 关键列 + 含义：
  - Col1 = Peptide 序列
  - Col2 = 跨所有 allele 最低 **PRIME %Rank**（越低越好，0 最优）
  - Col3 = 对应最优 allele 的 **PRIME Score**（连续，量化免疫原性强弱）
  - Col4 = MixMHCpred binding %Rank（纯结合分对照）
  - Col5 = Best allele
- 分数类型：连续 %Rank（0–100）+ Score
- **能否定量免疫强弱**：✅ 是（PRIME Score / %Rank 连续）← 项目核心目标
- **实测输出样例**：TODO

## 4. 简介（特点 / 优势）
- 方法：MixMHCpred 提呈分 + TCR 接触位点氨基酸频率特征 + 肽长 → 轻量打分模型
- 训练数据：实验验证的 neo-epitope 免疫原性数据（Gfeller lab）
- 特点 / 优势：直接出免疫原性连续分、依赖链最短（仅 MixMHCpred，无 netMHCpan/DTU 许可）、5 工具中部署最易、输入只要肽+HLA
- 局限：肽长 8–14；依赖 MixMHCpred 版本对齐（v3.0+）

## 部署记录
- repo：https://github.com/GfellerLab/PRIME （v2.1，2025-09-24；master 分支）
- 论文：
  - PRIME 1.0 — *Prediction of neo-epitope immunogenicity reveals TCR recognition determinants...*, Cell Reports Medicine 2021, DOI 10.1016/j.celrep.2021.100194
  - PRIME 2.0 — *Improved predictions of antigen presentation and TCR recognition with MixMHCpred2.2 and PRIME2.0...*, Cell Systems 2023, DOI 10.1016/j.cels.2022.12.002（PMID 36603583）
- 语言 / 框架 / 依赖：C++（lib 需 `g++ -O3` 编译）+ Perl + Shell；**唯一外部依赖 MixMHCpred v3.0+**
- 外部许可证工具：无（MixMHCpred 同 Gfeller lab，学术免费，无 DTU 许可）
- GPU 需求：无（CPU）
- 部署状态：调研完成，HPC 已半 clone `tools_repos/PRIME` → 待编译 + 确认 MixMHCpred 版本（见 DEPLOY_TRACKER Wave 3）
- example 烟测 job_id / 路径：TODO
- 许可：学术非商用免费；商用需向 Ludwig Institute (nbulgin@lcr.org) 申请

### TODO（researcher 标）
- 确认 HPC `tools_repos/PRIME` 版本（master v2.1 还是旧版，git tag 核）
- 确认 HPC MixMHCpred 版本 ≥ v3.0
- PRIME 实测烟测（尚无 HPC 实跑记录）
