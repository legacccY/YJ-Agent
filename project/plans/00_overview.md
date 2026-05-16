# VisiSkin-Agent 项目总览

## 项目定义

面向自拍皮肤照片的视觉质量引导与智能分诊 Agent。
核心创新：AI 不直接给诊断，而是先评估照片质量，质量不达标时引导用户重拍，再进行分析。

**投稿目标**：ICLR 2027（CCF-A 级别）

---

## 8 阶段路线图

| 阶段 | 名称 | 核心目标 | 主要交付物 | 状态 |
|------|------|---------|-----------|------|
| 1 | 环境初始化 | 搭建可运行项目骨架 | 目录结构 + 依赖 + 配置模板 | ✅ 完成 |
| 2 | 数据流水线 | 下载数据，生成配对数据集 | paired_dataset/ + quality_labels.csv | ✅ 完成 |
| 3 | VisiScore-Net | 训练图像质量评估网络 | best_visiscore.pth + 评估报告 | ✅ 完成 |
| 4 | Q-VIB 模块 | 质量条件化变分推断 + 分类 | Q-VIB 编码器 + 质量自适应先验 + 质量分词器 + 消融实验 | ✅ 完成 |
| 5 | Agent 系统 | ReAct 多轮交互 + Gradio Demo | app.py + 端到端评测 | ✅ 完成 |
| 6 | ITB 评测基准 | 构建 4 子集基准 + 9 条 baseline | 数据表 + 可视化图 | ✅ 完成 |
| **7** | **VisiEnhance-Net** | **诊断保持型质量增强 + 双通道集成** | **增强模块 + 双通道决策 + 12 项实验** | ⏳ 待开始 |
| **8** | **论文写作** | **ICLR 2027 初稿（CCF-A 标准）** | **main.tex（9 页）+ 附录 + 图表** | ⏳ 待开始 |

---

## 五大核心创新点

| 模块 | 说明 | 理论保证 |
|------|------|---------|
| **VisiScore-Net** | 5 维细粒度质量评估（清晰度/光照/完整度/色温/对比度），输出可操作的引导建议；PLCC=0.924，3.1 ms/张 | — |
| **Q-VIB（Quality-Conditioned VIB）** | 将标准 VIB 推广到质量条件化：KL 约束强度由 $\mathbf{q}$ 动态调控——低质量图先验宽，自然产生高熵预测；质量分词器注入注意力层 | Lemma 1（先验单调性）+ Proposition 2（熵-质量单调性）+ Theorem 1（注意力漂移界） |
| **VisiEnhance-Net** | 诊断保持型质量增强：NAFNet backbone + FiLM 质量条件调制，L1 + LPIPS + DP-Loss + 质量约束损失；在 Q-VIB 隐空间中约束增强前后诊断分布一致性 | Proposition 3（增强降低预测熵）+ Lemma 3（DP-Loss 保持诊断互信息） |
| **双通道 Agent** | 增强路径（VisiEnhance 修复可修复退化）+ 追问路径（不可修复时引导重拍），双通道协同决策；4 通道精细分级（高质/准高质/可增强/极低） | 退化可修复性分析：$q_3$（完整度）不可逆，其余 4 维条件可逆 |
| **ITB Benchmark** | 4 质量子集评测基准（LQ/HQ/Edge/Diverse），9 条 baseline 覆盖判别、校准后处理、贝叶斯近似、集成方法；填补领域内低质量 AI 分诊专项 benchmark 空白 | — |

---

## 数据集

| 数据集 | 数量 | 来源 |
|--------|------|------|
| ISIC 2020 | ~33k 张 | Kaggle |
| ISIC 2024 | ~400k 张（3D-TBP） | Kaggle |
| DermNet | ~23k 张 | 公开网站 |
| FitzPatrick17k | ~17k 张 | 公开 |
| **合计** | **~473k 张** | 全部公开 |

---

## 全局工具总览

### 核心模型与框架

| 层级 | 选型 | 说明 |
|------|------|------|
| 深度学习框架 | PyTorch 2.x + torchvision | 主框架 |
| Backbone 库 | timm（PyTorch Image Models） | 提供 MobileNetV3 / EfficientNet / tinyViT 等所有候选 Backbone |
| 语言模型 | HuggingFace Transformers + bitsandbytes | Qwen3-8B 4-bit 量化加载 |
| 模型加速 | accelerate | 优化模型加载与推理，管理设备映射 |
| 分割模型 | MobileSAM / EfficientSAM / SAM2-tiny | 选一，推理阶段加载预训练权重 |
| Agent 框架 | ReAct pattern（自实现） | 不引入额外框架，控制依赖复杂度 |
| Demo 框架 | Gradio | 交互式 Web Demo |

### 实验追踪

**选型：Weights & Biases（wandb）**

- 免费个人版，无需自己部署服务器
- 自动记录每次 run 的超参、loss 曲线、评估指标、GPU 占用
- 支持对比多次实验（Backbone 选型对比、消融实验），论文写作时直接引用图表
- 命令行 `wandb login` 一次性配置，之后代码里加两行即可接入
- 备选：TensorBoard（本地离线，无需账号，但功能弱于 wandb）

### 代码风格

**选型：ruff**

- 一个工具同时做 lint（检查代码问题）+ format（自动格式化），替代 flake8 + isort + black
- 速度极快（比 black 快 10-100x），配置简单
- 在 `pyproject.toml` 中统一配置，所有人执行 `ruff check .` 和 `ruff format .` 结果一致
- 规则：行宽 120，忽略 E501（长行），强制 import 排序

### 测试策略

**选型：pytest，聚焦数据和指标层**

研究代码不追求高覆盖率，测试集中在最容易出错、最难调试的两层：

| 测试类型 | 覆盖范围 | 示例 |
|---------|---------|------|
| 单元测试 | 数据处理函数 | 退化模拟输出形状、标签归一化范围 |
| 单元测试 | 指标计算 | PLCC/SRCC 计算结果与 scipy 手算对齐 |
| 单元测试 | Q-VIB 组件 | KL 解析式与数值积分对齐、$\sigma^2(\bar{q})$ 单调性验证、质量分词器零边界条件 |
| 冒烟测试 | 模型推理 | 模型前向传播不报错，输出值域 [0,1] |
| 集成测试 | DataLoader | 批次形状、标签与图片对应关系 |

测试文件放在 `tests/`，命名 `test_xxx.py`，运行 `pytest tests/ -v`。

### 版本控制与 Git 工作流

**Claude Code 可以处理全部 git 操作**，包括 add / commit / push。

**提交规范（Conventional Commits）**：

| 前缀 | 用途 | 示例 |
|------|------|------|
| `feat:` | 新功能/新模块 | `feat: add Q-VIB encoder with quality-adaptive prior` |
| `data:` | 数据相关变更 | `data: add degradation pipeline` |
| `train:` | 训练脚本变更 | `train: add Q-VIB ELBO loss and KL annealing` |
| `eval:` | 评估相关 | `eval: add Q-VIB ablation study (fixed vs adaptive prior)` |
| `fix:` | bug 修复 | `fix: fix memory leak in DataLoader` |
| `docs:` | 文档更新 | `docs: integrate Q-VIB theory into phase 4 plan` |

**分支策略**：`main`（稳定可运行）+ 按阶段或功能开 feature branch，合并前确认可运行。

**使用方式**：告诉我「提交一下」或「push 到 GitHub」，我会 stage → commit → push（push 前会告诉你命令让你确认）。前提是本地已执行 `git init` 和 `git remote add origin <your-repo-url>`。

### 配置管理

| 工具 | 用途 |
|------|------|
| OmegaConf | 加载 YAML 配置，支持命令行覆盖（`train.py lr=0.001`） |
| `configs/default.yaml` | 全局配置：数据路径、超参、设备 |

### 依赖清单（按阶段）

| 阶段 | 主要新增依赖 |
|------|------------|
| 1 环境 | torch、torchvision、timm、wandb、ruff、pytest、omegaconf、tqdm、loguru |
| 2 数据 | kaggle、Pillow、opencv-python、albumentations、scikit-image、piq、pandas |
| 3 训练 | torch.cuda.amp（内置）、scipy |
| 4 QAD | mobile-sam 或 sam2、scikit-learn（注：Q-VIB 编码器/先验/分词器/ELBO 全用 PyTorch 原生实现，无额外概率编程库依赖） |
| 5 Agent | bitsandbytes、accelerate、gradio |
| 6 评测 | matplotlib、seaborn、scipy（已有） |
| 7 论文 | LaTeX（本地安装）、BibTeX |

---

## 硬件约束

- **目标硬件**：RTX 4070 8GB 笔记本
- **显存预算**：Batch 128 FP16 ≈ 3.5GB，留有余量
- **磁盘需求**：原始数据 ~100GB
- **训练时间**：VisiScore-Net ~40h + Q-VIB ~30h（均支持断点续训）

---

## 5 大设计原则

1. **模块化**：每个模块独立可测，不互相阻塞
2. **断点续跑**：所有训练脚本支持 `--resume` 参数
3. **结果可复现**：固定 random seed，记录所有超参
4. **4070 友好**：任何操作提前估算显存，不写跑不动的代码
5. **先问再写**：每阶段开始先确认关键决策点，不盲目写代码

---

## 计划文档索引

进入某阶段时，读取对应文档获取详细工作计划：

| 阶段 | 计划文件 | 状态 |
|------|---------|------|
| 阶段一 | `phase_01_setup.md` | ✅ 完成 |
| 阶段二 | `phase_02_data.md` | ✅ 完成 |
| 阶段三 | `phase_03_visiscore.md` | ✅ 完成 |
| 阶段四 | `phase_04_Q-VIB.md` | ✅ 完成 |
| 阶段五 | `phase_05_agent.md` | ✅ 完成 |
| 阶段六 | `phase_06_benchmark.md` | ✅ 完成 |
| **阶段七** | **`phase_07_visienhance.md`** | ⏳ 待开始 |
| **阶段八** | **`phase_08_paper.md`** | ⏳ 待开始 |

> 技术设计参考：`V2.0plan.md`（VisiEnhance-Net 详细技术报告，含架构图、伪代码、参考文献）
