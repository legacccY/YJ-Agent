# deepHLApan — 信息收集卡（PPT 素材）

> 第二批 5 工具（Wave 3，原李紫晨负责，现并入余嘉测试）。事实来自官方 repo + 论文，实测项标 TODO。

## 0. 定位 / 一句话
深度学习（BiGRU + attention）预测新抗原，**双模型**：binding model（pHLA 结合/提呈概率）+ immunogenicity model（T 细胞激活免疫原性）。仅 MHC Class I。

## 1. 输入数据模板 / 格式
- 文件格式：CSV，必须有 header `Annotation,HLA,peptide`
- 必填列：Annotation（注释标识）、HLA、peptide
- 肽段长度限制：8–15 AA
- HLA 格式：`HLA-A01:01`（**无星号、连字符直连**，不是 `HLA-A*01:01`）
- 是否需基因组数据：否（只要肽+HLA）
- 也支持单肽单 HLA 命令行：`deephlapan -P <peptide> -H HLA-A02:01`
- **实测输入样例**：TODO

## 2. 运行参数设置
- 主要参数：`-F` 输入 CSV 文件 / `-P` 单肽 + `-H` 单 HLA / 输出目录
- 模型变体：binding model + immunogenicity model（双输出，无需手动切换）
- **实测命令行**：TODO

## 3. 输出数据格式 + 含义
- 输出文件格式：CSV
- 关键列 + 含义：binding score（0–1，越高越可能结合）、immunogenicity score（0–1，>0.5 = 免疫原性阳性过滤阈值）
- 高置信新抗原定义：immunogenicity >0.5 AND binding 排名 top20
- 分数类型：连续 0–1（两个分数）
- **能否定量免疫强弱**：✅ 是（immunogenicity score 连续）← 项目核心目标
- **实测输出样例**：TODO（README 未列精确输出列名，需跑 demo 确认）

## 4. 简介（特点 / 优势）
- 方法：3 层双向 GRU（BiGRU）+ attention
- 训练数据：binding 437,077 条；immunogenicity 32,785 条（IEDB，7,212 阳性）
- 特点 / 优势：双任务（结合+免疫原性）一次出、纯肽+HLA、无许可工具依赖
- 局限：仅 MHC-I（不支持 MHC-II）；**训练数据含 IEDB（含 ELISpot）→ 与 benchmark 测试集可能 overlap，需排重**；版本地狱（见下）

## 部署记录
- repo：https://github.com/jiujiezz/deephlapan （GPL-2.0，最新 release v1.1.1，2021-08-10；旧 `zjupgx/deephlapan` 已失效）
- web server：http://biopharm.zju.edu.cn/deephlapan/
- 论文：*DeepHLApan: A Deep Learning Approach for Neoantigen Prediction Considering Both HLA-Peptide Binding and Immunogenicity*, Frontiers in Immunology 2019, DOI 10.3389/fimmu.2019.02559（PMID 31736974）
- 语言 / 框架 / 依赖：Python + Perl（Linux only）；`keras==2.0.8` + `tensorflow==2.7.2` + numpy/pandas/gensim/scipy/sklearn；CUDA9 + cuDNN7
- 外部许可证工具：无
- GPU 需求：训练需 GPU（CUDA9/cuDNN7 旧版）；推理 CPU 可
- **部署难度坑**：keras2.0.8（2017）+ TF2.7.2（2021）已知不兼容（Issue #9「Error in loading the saved optimizer state」）→ **官方推荐 Docker `biopharm/deephlapan:v1.1`** 绕版本地狱
- 部署状态：调研完成，待部署（建议走官方 Docker）
- example 烟测 job_id / 路径：TODO
- 许可：GPL-2.0（衍生品须同 GPL-2.0 开源）

### TODO（researcher 标）
- 输出 CSV 精确列名（README 未列，跑 `demo/1.csv` 验证）
- Docker `biopharm/deephlapan:v1.1` 内 TF/Keras 真实版本
- HLA allele 覆盖列表
