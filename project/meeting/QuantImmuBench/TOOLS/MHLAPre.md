# MHLAPre — 信息收集卡（PPT 素材）

> 第二批 5 工具（Wave 3，原李紫晨负责，现并入余嘉测试）。事实来自官方 repo + 论文，实测项标 TODO。
> ⚠️ **部署前置阻塞**：预训练权重 + 训练数据「太大未上传」，需邮件作者（23B903048@stu.hit.edu.cn）索取；repo 无 LICENSE；IEDB 训练数据可能与 ELISpot benchmark overlap（数据泄露风险）。**部署难度最高，列 Wave 3 末位。**

## 0. 定位 / 一句话
元学习（MAML）+ Transformer Encoder + TextCNN 预测**突变 HLA-I 表位免疫原性**。双子模型：IM（免疫原性）+ TT（迁移到 pHLA-TCR，预测能否激活 CTL）。

## 1. 输入数据模板 / 格式
- 文件格式：CSV（**实测**：repo 内 `data/data_MHLAPre.csv` = `Epitope, MHC Restriction, Assay`，例 `APSFGSFHLI, B*07:02, 1`；TCR 任务用 `data/TCR-HLA-epotite4.csv` = `Epitope, Assay, CDR3, Label`）
- ⚠️ **列名不一致坑（实测）**：`Pretreatment.py` 代码读的是 `dataset['Antigen']` 列 + TCR，**与出厂 CSV 的 `Epitope` 列对不上** → 跑前需把 `Epitope`→`Antigen` 改名/预处理
- 必填字段：Epitope(肽段) + MHC Restriction(HLA) + Assay(标签 1/0)
- 肽段长度限制：8–15 AA（以 9-mer 为主）
- HLA 格式：**实测 `B*07:02`**（无 HLA- 前缀；HLA-A/B/C）
- 是否需基因组数据：否
- **实测输入样例**：`Epitope,MHC Restriction,Assay` → `APSFGSFHLI,B*07:02,1`

## 2. 运行参数设置
- 运行方式：顺序执行 3 脚本 `python Pretreatment.py` → `python TransfomerEncoder.py` → `python TextCNN.py`（无 CLI 参数说明）
- 模型变体：IM（免疫原性）/ TT（TCR 激活）
- **实测命令行**：TODO

## 3. 输出数据格式 + 含义
- 输出文件格式：**无（实测）**——`TextCNN.py` 最后 `return F.softmax(x)`，研究代码只算 ROC-AUC/PR 等指标（`sklearn.metrics`），**不存预测文件**（同 NeoTImmuML 性质）；要出分需自己加 to_csv
- 关键列 + 含义：softmax 概率（两类），免疫原性阳性概率越高越强
- 分数类型：连续 0–1（softmax）
- **能否定量免疫强弱**：✅ 是（连续概率）← 项目核心目标
- **实测输出样例**：N/A（需改代码导出 predict_proba）

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
- 部署状态：**阻塞坐实（2026-06-24 HPC clone+inspect）**。repo clone OK（15M，`tools_repos/MHLAPre`），代码 5 脚本齐 + 部分数据（`data_MHLAPre.csv` 等）；但 **(a) 无权重文件（无 .pt）(b) `ProcessData/Transfer_data/*.npy` 程序中间数据缺**（`TransfomerEncoder.py` line 69 `np.load('ProcessData/Transfer_data/hla_epit_cdr3.npy')` 会 FileNotFound）→ README 明示「raw + procedural data too large to upload，需邮件 23B903048@stu.hit.edu.cn」。**跑不通，待权重/数据。**
- 运行顺序（README 实测）：`python Pretreatment.py` → `TransfomerEncoder.py` → `TextCNN.py`
- **自训路也不通（2026-06-24 源码数据流分析）**：① `Pretreatment.py` 只有编码 helper 函数（peptide_encode_HLA/antigenMap/aamapping_TCR），**无 `__main__`，跑它不产出任何 npy**。② `TransfomerEncoder.py:69` 把缺失的 `ProcessData/Transfer_data/hla_epit_cdr3.npy` 当**输入** load；生成它的「HLA+epitope+CDR3→npy」拼装代码**没随 repo 发（line 55-58 全注释掉）**。→ 即「原始 CSV → 中间 npy」这步代码缺失，自训需逆向作者无文档的预处理胶水。**区别 NeoTImmuML（有完整 notebook 只需重训）；MHLAPre 是预处理管线本身不完整。**
- 全网搜权重（GitHub 原 repo+3 fork+releases+作者所有 repo / Kaggle / Zenodo / figshare / HuggingFace）**全空**（2026-06-24 researcher 核）。
- **结论**：唯一可行路 = 邮件作者要权重+ProcessData。叠加无 license + IEDB overlap → ROI 低，建议标阻塞末位、可选邮件作者当 bonus。
- example 烟测 job_id / 路径：N/A（阻塞，不可复现）
- 许可：**无 LICENSE 文件**（GitHub 默认版权保留；学术使用需确认作者许可）

### TODO（researcher 标，多为阻塞项）
- 输入/输出列名（查 `Pretreatment.py` 源码或联系作者）
- 预训练权重获取（README 称太大未上传 → 邮件 23B903048@stu.hit.edu.cn）
- cudatoolkit10.2 vs HPC CUDA 兼容性（高风险坑）
- 无 license → 学术 benchmark 使用需确认作者许可
- ELISpot 测试集与 IEDB 训练数据 overlap 排重核查
