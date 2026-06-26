# ImmunoStruct — 信息收集卡（PPT 素材）

> Tier-3 扩展工具。**判定 = ❌ NO-GO（诚实放弃，三重硬 blocker，许可本身不挡）**。
> 4 类信息按「未部署」如实标注；blocker 说明见§部署记录。

## 0. 定位 / 一句话
Yale KrishnaswamyLab 多模态（序列 + AlphaFold2 结构 + 生化特征）新抗原免疫原性预测。PyTorch Geometric 图神经网络，训练于 IEDB / CEDAR 标注数据。Nat Machine Intelligence 2025（bioRxiv 2024.11.01.621580）。HF 权重 ChenLiu1996/ImmunoStruct。

**工程三重封死，无法接入本项目 benchmark，不产出分数列。**

## 1. 输入数据模板 / 格式
- **未部署，下同；原因见 §NO-GO Blockers**
- 官方 infer 脚本：`infer_IEDB_or_CEDAR.py` / `infer_clinical_only.py`
- ⚠️ 脚本**锁定预构建 PyG 图**（针对训练/测试集预生成），无通用「裸肽 + HLA」推理入口——任意新肽段输入无法直接使用
- 肽段长度限制：未部署，N/A（官方未测试任意长度）
- HLA 格式：未部署，N/A
- 是否需基因组数据：否（序列 + 结构输入）
- **实测输入样例**：未部署，N/A

## 2. 运行参数设置
- 主要参数：未部署，N/A
- 模型变体 / 模式：未部署，N/A
- **实测命令行**：未部署，N/A

## 3. 输出数据格式 + 含义
- 输出格式：未部署，N/A
- 关键列含义：未部署，N/A
- 分数类型：设计上为连续免疫原性分（多模态融合），但工程封死无法跑到此步
- **能否定量免疫强弱**：待核（设计意图是多模态打分可定量，但工程封死无实测）
- **实测输出样例**：未部署，N/A

## 4. 简介（特点 / 优势）
- 方法：多模态融合——序列特征 + AlphaFold2 / ColabFold 结构 + 生化特征，PyG 图神经网络
- 训练数据：IEDB / CEDAR 新抗原免疫原性标注数据集
- 特点 / 优势：结构感知 + 多模态，Nat MI 2025 高影响力；HF 公开权重
- 局限（即本项目 NO-GO 根因）：
  - 无裸肽+HLA 通用推理入口
  - 需全套 AF2 结构管线（成本极高）
  - 训练 HLA 覆盖仅 27 个 allele，不覆盖本项目数据集

## 部署记录
- repo：https://github.com/KrishnaswamyLab/ImmunoStruct
- 论文：*ImmunoStruct: multimodal neoantigen immunogenicity prediction integrating sequence, structure and biochemistry*, Nat Machine Intelligence 2025, DOI 10.1038/s42256-025-01163-y（bioRxiv 2024.11.01.621580）
- HF 权重：https://huggingface.co/ChenLiu1996/ImmunoStruct
- 语言 / 框架 / 依赖：Python + PyTorch Geometric + AlphaFold2 / ColabFold（6 步结构管线）
- 外部许可证工具：ColabFold / AlphaFold2
- GPU 需求：AF2 结构推断需 GPU，大批量不可承受
- 许可：Yale 学术非商用许可（**许可本身不挡**）
- **部署状态：❌ NO-GO（三重硬 blocker，诚实放弃）**
- example 烟测 job_id / 路径：N/A（未尝试）

---

### NO-GO Blockers（三重，工程封死）

**Blocker 1 — 无通用「肽+HLA」推理入口**

官方仅提供 `infer_IEDB_or_CEDAR.py` / `infer_clinical_only.py` 两个推理脚本，均要求输入**预构建 PyG 图文件**（特定于 IEDB/CEDAR 训练/测试数据集），不接受任意裸肽+HLA 字符串。将 DS1+DS2 共 34 247 行肽段输入需从头构建 PyG 图，而官方 repo 无该构建脚本、无文档说明图构建方式。

**Blocker 2 — AF2 结构不可承受**

任意新肽的结构输入需完整跑 6 步 ColabFold / AlphaFold2 管线（step1–step6 生成肽-HLA 复合物结构）；本地数据库依赖约 500 GB（uniref30 + colabfold_envdb）；DS1+DS2 去重后上千条 unique 9 mer × 数分钟/条（单 GPU）= **数百 GPU·h**，超出本项目算力预算，本地/HPC 均不可行（NeoaPred 已实证全量 ~11 384 次轻量弛豫需 48 核 HPC，ImmunoStruct 重量级 AF2 管线远超该量级）。

**Blocker 3 — HLA 覆盖不足**

ImmunoStruct 训练仅覆盖 **27 个常见 HLA-I allele**；本地 Bash 核 DS1+DS2 master_backbone 共 **65 个唯一 allele**，大量 allele（含 HLA-B/C 多数）无对应模型权重，无法跑全量 benchmark，覆盖率不满足本项目基本要求。

> 许可（Yale 学术非商用）本身不挡。stretch 工具工程封死 = 诚实 block 非失败。投稿/报告不引用 ImmunoStruct 分数。
