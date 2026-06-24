# MHLAPre — 信息收集卡（PPT 素材）

> 第二批 5 工具（Wave 3，原李紫晨负责，现并入余嘉测试）。事实来自官方 repo + 论文，实测项标 TODO。
> ⚠️ **部署前置阻塞**：预训练权重 + 训练数据「太大未上传」，需邮件作者（23B903048@stu.hit.edu.cn）索取；repo 无 LICENSE；IEDB 训练数据可能与 ELISpot benchmark overlap（数据泄露风险）。**部署难度最高，列 Wave 3 末位。**

## 0. 定位 / 一句话
元学习（MAML）+ Transformer Encoder + TextCNN 预测**突变 HLA-I 表位免疫原性**。双子模型：IM（免疫原性）+ TT（迁移到 pHLA-TCR，预测能否激活 CTL）。

## 1. 输入数据模板 / 格式
- 文件格式：TODO（repo 无 example 文件，README 无列名示例）
- 必填字段：肽段序列 + HLA allele（推测两列，需查 `Pretreatment.py` 源码确认）
- 肽段长度限制：8–15 AA（以 9-mer 为主）
- HLA 格式：标准 `HLA-A*02:01`（HLA-A/B/C；内部 34 位伪序列 + BLOSUM62 编码）
- 是否需基因组数据：否
- **实测输入样例**：TODO（无官方示例，需联系作者或读源码）

## 2. 运行参数设置
- 运行方式：顺序执行 3 脚本 `python Pretreatment.py` → `python TransfomerEncoder.py` → `python TextCNN.py`（无 CLI 参数说明）
- 模型变体：IM（免疫原性）/ TT（TCR 激活）
- **实测命令行**：TODO

## 3. 输出数据格式 + 含义
- 输出文件格式：TODO（README 无示例输出）
- 关键列 + 含义：连续概率分（0–1，softmax），越高免疫原性越强；精确列名 TODO
- 分数类型：连续 0–1
- **能否定量免疫强弱**：✅ 是（连续概率）← 项目核心目标
- **实测输出样例**：TODO

## 4. 简介（特点 / 优势）
- 方法：MAML 元学习 + Transformer Encoder + TextCNN，BLOSUM62（50×21）编码
- 训练数据：IEDB 实验验证 HLA-I 呈递+免疫原性肽（156,244 样本，清洗后 47,810）；TT 用 10X/VDJdb/McPAS-TCR
- 性能（论文）：免疫原性 AUROC 0.9041 / AUPRC 0.8462（论文称优于 NetMHCpan/MHCflurry/MHCnuggets/MixMHCpred2.2/HLAthena）
- 特点 / 优势：直接出免疫原性、纯开源依赖栈无许可工具
- 局限：**权重未发布需邮件作者**；无 license；torch1.12/cuda10.2 旧；IEDB overlap 风险

## 部署记录
- repo：https://github.com/ChanganMakeYi/MHLAPre
- 论文：*Meta learning for mutant HLA class I epitope immunogenicity prediction to accelerate cancer clinical immunotherapy*, Briefings in Bioinformatics 2024, Vol 26(1), DOI 10.1093/bib/bbae625（PMID 39656887）
- 语言 / 框架 / 依赖：Python 3.9.13 + torch1.12.1（CUDA 10.2）+ rdkit~2021.03.2 + sklearn≥1.0.2 + numpy1.21.2/pandas1.4.4（Linux，conda，~10min 装）
- 外部许可证工具：无
- GPU 需求：torch+CUDA10.2（HPC 一般 CUDA11/12 → 需确认兼容）
- 部署状态：调研完成，**阻塞待部署**（权重缺，需邮件作者；CUDA 版本待对齐）
- example 烟测 job_id / 路径：TODO
- 许可：**无 LICENSE 文件**（GitHub 默认版权保留；学术使用需确认作者许可）

### TODO（researcher 标，多为阻塞项）
- 输入/输出列名（查 `Pretreatment.py` 源码或联系作者）
- 预训练权重获取（README 称太大未上传 → 邮件 23B903048@stu.hit.edu.cn）
- cudatoolkit10.2 vs HPC CUDA 兼容性（高风险坑）
- 无 license → 学术 benchmark 使用需确认作者许可
- ELISpot 测试集与 IEDB 训练数据 overlap 排重核查
