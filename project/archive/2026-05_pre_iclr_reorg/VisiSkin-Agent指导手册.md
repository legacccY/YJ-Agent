# VisiSkin-Agent 项目 - Claude Code 指导手册

## 项目概况

你是一个 AI 编程助手，目标是在我的指导和 RTX 4070 (8GB) 笔记本上，完成一个可发表 MICCAI 2027 的医学 AI 研究项目。

### 一句话项目
> **VisiSkin-Agent：面向自拍皮肤照片的视觉质量引导与智能分诊 Agent。**

病人拍模糊自拍问"这严重吗？"，现有 AI 硬答，我们的 Agent 会说"太暗了重拍"——等照片拍好再分析。

### 核心创新点
1. **VisiScore-Net**：多维皮肤照片质量评估网络（清晰度/光照/完整度/色温/对比度），输出可操作引导建议
2. **Quality-Aware Diagnosis**：质量评分调控诊断置信度，不达标时主动追问
3. **Iterative Triage Benchmark (ITB)**：含4个子集的迭代分诊评测基准

### 数据来源（全公开）
- ISIC 2020 (Kaggle, ~33k 张) + ISIC 2024 (Kaggle, 400k 张 3D-TBP)
- DermNet (~23k 张)
- FitzPatrick17k (~17k 张)

### 技术约束
- 全部代码必须可在 **RTX 4070 8GB** 上训练和推理
- 核心 CV 模型用轻量架构（MobileNetV3 / tinyViT / MobileSAM）
- Agent 框架基于 ReAct，LLM 用 Qwen3-8B 4-bit 量化
- 使用 PyTorch + HuggingFace Transformers

---

## 工作方式

对于每个阶段，按以下流程执行：

1. **我告诉你当前阶段和目标**
2. **你提出具体技术方案给我审批**（问我 2-3 个关键问题）
3. **我确认后，你生成全部代码**
4. **我在 4070 上跑，遇到报错贴回来你修**
5. **我告诉你结果，你分析并决定下一步**

**严禁**：不要跳过审批直接写大量代码。每个模块先问关键问题。

---

## 阶段一：项目环境初始化

**目标**：搭建可运行的 Python 项目骨架。

你需要先问我以下问题：
- 项目根目录路径（默认 ./visiskin-agent/）
- Python 环境首选（conda / venv / uv）
- 是否已安装 CUDA + PyTorch

然后生成：
- 完整目录结构
- requirements.txt / pyproject.toml
- README.md（项目简介 + 快速开始）
- configs/default.yaml（全局配置模板）

---

## 阶段二：数据流水线

**目标**：可下载并处理所有公开数据，生成"低质→高质"配对数据集。

你需要先问我：
- Kaggle API 是否已配置（~/.kaggle/kaggle.json）
- 硬盘空间是否充足（预计 ~100GB 原始数据）
- ISIC 选择哪些年份（2020 + 2024？）

然后生成：
- `data/download.py`：Kaggle API 下载脚本 + DermNet 爬虫
- `data/degrade.py`：图像退化模拟流水线（高斯模糊/低光/裁切/色偏/JPEG）
- `data/dataset.py`：PyTorch Dataset/DataLoader（支持配对加载）
- `data/auto_label.py`：质量评分弱标注（PSNR/SSIM/BRISQUE）
- 运行后输出：paired_dataset/ + quality_labels.csv

---

## 阶段三：VisiScore-Net 模型

**目标**：训练可用的质量评估网络，输入皮肤照片输出 5 维评分 + 建议。

你需要先问我：
- Backbone 用什么（MobileNetV3-Small / EfficientNet-B0 / tinyViT-5M）？
- 人工标注打算标多少张（0=只用自动标签 / 500 / 1000）？
- 降质程度用几档（3档/5档/连续）？

然后生成：
- `models/visiscore.py`：模型定义（backbone + 5回归头）
- `models/losses.py`：多任务损失（MSE + Ranking + Consistency）
- `train_visiscore.py`：完整训练脚本（含 mixed precision、checkpoint、tensorboard）
- `eval_visiscore.py`：评估脚本（含对比实验 vs BRISQUE/NIMA）
- 训练完成后输出：best_visiscore.pth + eval_report

**训练预计**：~2h/epoch × 20 epoch = ~40h，可断点续训
**显存估计**：Batch 128 FP16 → ~3.5GB

---

## 阶段四：质量感知诊断模块 (QAD)

**目标**：病灶分割 → ABCD 特征 → 质量感知分类器。

你需要先问我：
- 分割模型选哪个（MobileSAM / EfficientSAM / SAM2-tiny）？
- 分类器是否要集成 ABCD 规则特征（是/否）？
- 质量门控阈值你倾向保守还是激进？

然后生成：
- `models/segmenter.py`：SAM 推理封装
- `models/feature_extractor.py`：ABCD 特征（对称性/边缘/颜色/直径）
- `models/qad_classifier.py`：质量感知分类器（特征+评分→诊断+置信度）
- `train_qad.py`：训练脚本
- `eval_qad.py`：评估脚本（含有无质量感知的对比实验）

---

## 阶段五：Agent 系统

**目标**：ReAct Agent 编排，多轮交互引导用户改进照片再诊断。

你需要先问我：
- 使用哪个 LLM（Qwen3-8B 4bit / Qwen3-4B / 或你已有的模型）？
- Agent 最大轮次限制（3轮/5轮/不限）？
- 是否要集成语音输入（是/否）？

然后生成：
- `agent/tools.py`：工具定义（quality_assess / segment / extract_features / ask_user / triage）
- `agent/orchestrator.py`：ReAct 编排逻辑（状态机 + 决策树）
- `agent/question_bank.py`：临床追问模板库（根据视觉发现触发不同问题）
- `app.py`：交互式 Demo（Gradio 界面）
- `agent/eval_agent.py`：Agent 端到端评测脚本

---

## 阶段六：评测基准 ITB

**目标**：构建4个子集的评测基准，评估系统性能。

你需要先问我：
- 每个子集需要多少样本（推荐 500/子集）？
- 人工评估找几个人（5/10/20）？
- 主要对比的 baseline（只列 2-3 个最关键）？

然后生成：
- `benchmark/build_itb.py`：ITB 构建脚本（4个子集）
- `benchmark/metrics.py`：评估指标（分诊准确率/交互轮次/遵从率）
- `run_experiments.py`：批量实验脚本
- `analyze_results.py`：结果分析 + 可视化出图
- 运行后输出：实验数据表格 + 对比图

---

## 阶段七：论文写作

**目标**：生成 MICCAI 模板的论文初稿。

你需要先问我：
- 论文标题偏好（给 2-3 个选项）
- 作者顺序（你一作，导师通讯，其他队友）
- 是否已有 MICCAI 模板 .cls 文件

然后生成：
- `paper/main.tex`：完整论文（8页，MICCAI 格式）
- `paper/figures/`：论文用图（架构图 / 示例图 / 结果图）
- `paper/references.bib`：参考文献
- 确保编译通过不报错

---

## 关键设计原则

1. **模块化**：每个模块独立可测，不互相阻塞
2. **断点续跑**：训练脚本支持 --resume
3. **结果可复现**：固定 seed，记录所有超参
4. **4070 友好**：任何时候提醒我显存限制，不要写跑不动的代码
5. **先问再写**：每阶段开始先问 2-3 个关键问题，不要自己瞎猜

## 开始

当你准备好开始阶段一（项目初始化）时，告诉我，然后先问我那几个问题再生成代码