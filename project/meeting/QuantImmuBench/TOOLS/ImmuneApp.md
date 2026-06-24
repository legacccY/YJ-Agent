# ImmuneApp — 信息收集卡（PPT 素材）

> 第二批 5 工具（Wave 3，原李紫晨负责，现并入余嘉测试）。事实来自官方 repo + 论文，实测项标 TODO。

## 0. 定位 / 一句话
attention-based CNN-LSTM 框架，HLA-I 表位预测 + 免疫肽组分析。多模块，其中 **ImmuneApp-Neo = 免疫原性预测模块**（迁移学习，PPV 比现有方法提升 2.1 倍）。仅 HLA Class I。

## 1. 输入数据模板 / 格式
- 文件格式（ImmuneApp-Neo）：纯肽段文本（每行一条，无 header）+ 命令行 `-a` 指定 HLA
- 必填字段：肽段序列 + HLA allele
- 肽段长度限制：8–15 AA（脚本 `read_peplist()` 硬验证，仅 20 标准氨基酸）
- HLA 格式：`HLA-A*01:01`（标准命名，`-a` 接多个空格分隔）
- 是否需基因组数据：否
- 命令示例：`python ImmuneApp_immunogenicity_prediction.py -f testdata/test_immunogenicity.txt -a 'HLA-A*01:01' 'HLA-A*02:01' -o results`
- **实测输入样例**：TODO

## 2. 运行参数设置
- 主要参数：`-f` 肽段文件、`-a` HLA allele 列表、`-o` 输出目录
- 模型变体：ImmuneApp-BA（结合亲和力）/ -EL（洗脱配体）/ -AP（提呈）/ -MA（复合）/ **-Neo（免疫原性，本项目用）**
- **实测命令行**：TODO

## 3. 输出数据格式 + 含义
- 输出文件：`ImmuneApp_Immunogenicity_predictions.tsv`
- 关键列 + 含义：`Allele` / `Peptide` / `Sample` / `Immunogenicity_score`
- 分数类型：连续（`.4%` 格式化，底层 0–1 sigmoid 概率）；无内置阈值过滤，全肽出分
- **能否定量免疫强弱**：✅ 是（Immunogenicity_score 连续）← 项目核心目标
- **实测输出样例**：TODO

## 4. 简介（特点 / 优势）
- 方法：attention-based hybrid CNN-LSTM（可解释，attention 识别关键结合残基）
- 训练数据：349,650 HLA-I ligands；Neo 模块迁移学习于 curated immunogenicity dataset
- 特点 / 优势：HLA-I 提呈 SOTA（PPV 0.3720 vs NetMHCpan-4.1 0.3313）、预训练权重随 repo、MIT 许可无障碍、无 netMHCpan 依赖、支持 10000+ MHC
- 局限：仅 HLA-I；TF1.15 老生态环境易踩坑；论文 benchmark 用 TESLA（含 ELISpot）→ 注意 overlap

## 部署记录
- repo：https://github.com/bsml320/ImmuneApp （MIT；无明确 release tag）
- web server：https://bioinfo.uth.edu/iapp/
- 论文：*ImmuneApp for HLA-I epitope prediction and immunopeptidome analysis*, Nature Communications 2024, DOI 10.1038/s41467-024-53296-0
- 语言 / 框架 / 依赖：Python 3.7 + TensorFlow 1.15 + Keras 2.3.1 + numpy1.20/pandas1.3.3/scipy1.7.1/h5py2.10.0/protobuf3.20；GibbsCluster-2.0（仅 immunopeptidomics 模块需，随 repo）
- 外部许可证工具：无（无 netMHCpan）
- GPU 需求：CPU 可（TF1 推理）
- **部署难度坑**：Linux only（CentOS 7.8）；TF1.15+Keras2.3.1 须严格 Python 3.7 conda 环境；h5py/protobuf 版本固定严；无官方 Docker
- 部署状态：调研完成，待部署（权重已随 repo，免下载）
- example 烟测 job_id / 路径：TODO
- 许可：MIT（自由使用/修改/分发）

### TODO（researcher 标）
- ImmuneApp-Neo 免疫原性训练数据集具体来源（读原文 Methods）
- Immunogenicity_score 精确值域（实跑核验 sigmoid 约束）
- 多 HLA allele 时分数是 per-allele 还是 aggregate（输出有 Allele 列，需确认每肽每 allele 一行）
