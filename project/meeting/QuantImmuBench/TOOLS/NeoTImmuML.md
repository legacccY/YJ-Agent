# NeoTImmuML — 信息收集卡（PPT 素材）

> Wave 1。源码已找到（Playwright 进 tumoragdb.com.cn 点 card 抓出）。事实来自 repo 实测。

## 0. 定位 / 一句话
加权集成机器学习（LightGBM + XGBoost + RandomForest，VotingClassifier）预测肿瘤新抗原免疫原性，基于肽段 **78 个物化特征**；**不依赖 HLA 结合预测外部工具**；2025 发表，训练数据 TumorAgDB2.0（187,223 条）。

## 1. 输入数据模板 / 格式
- 文件格式：CSV（repo 自带 `demo.csv` 实为 **xlsx**，10 行 × 80 列）
- 列结构（实测）：第 1 列 `Peptide`（肽段序列）+ 第 2 列 `immunogenicity`（标签 0/1）+ 第 3-80 列 = **78 个预计算物化特征**
  - 特征例：mol_weight / isoelectric_point / boman_index / charge / hydrophobicity_index / lengthpep / instability_index / hmoment / aindex / autoCorrelation / blosum_1..10 / cruciani_* / fasgai_* / aaComp_* …（= R `Peptides` 包描述符）
- 肽段长度：8-13 AA（MHC I 类）
- HLA：**不需要**（纯肽段物化特征，无 HLA 列）
- 是否需基因组数据：否
- **⚠️ 关键**：notebook 里 `X = data.iloc[:, 2:]`（特征从第 3 列起）、`y = data['immunogenicity']` → **78 特征须先用 R Peptides 包外部算好**，repo 不含特征计算代码

## 2. 运行参数设置
- **不是 CLI 工具，是 Jupyter notebook**（`NeoTImmuML.ipynb`，21 个 code cell）
- 内含 8 种 ML 算法对比 + 加权集成（LGBM/XGB/RF）+ 5-fold CV + 雷达图评估
- 无命令行参数；改 notebook 里 `file_path = "Input.csv"` 指自己数据
- **实测命令行**：N/A（notebook 执行）

## 3. 输出数据格式 + 含义
- notebook 输出：分类指标（accuracy/precision/recall/F1/AUROC）+ 混淆矩阵 + 雷达图 + `predict_proba` 概率
- 分数类型：**二分类 + 连续概率**（`predict_proba` 出 0-1，notebook 用 15 处）
- **能否定量免疫强弱**：✅ 是（predict_proba 暴露连续概率，可排名）—— 此前「待核」已解，**能定量**
- **实测输出样例**：notebook 训练评估产出（指标表 + 图），非单条预测 csv

## 4. 简介（特点 / 优势）
- 方法：加权集成 ML（VotingClassifier: LGBM+XGB+RF）
- 特点：训练数据新（TumorAgDB2.0 2024-2025）；纯肽段特征不要 HLA / 不要 netMHCpan 等许可工具
- 优势：无许可证外部工具（部署最轻）；有连续概率
- **局限（部署关键）**：
  1. 是**研究 notebook**，非现成预测 CLI——无独立 predict 脚本
  2. **不含 78 特征计算代码** → 跑新肽段须先用 R `Peptides` 包算特征
  3. **不含预训练权重**（repo 无 .pkl）→ 须按 notebook 用 TumorAgDB2.0 数据重训（notebook 用 joblib 存/读模型，但权重不随 repo 发）
  4. demo 是 xlsx 但 notebook `read_csv` → 用户须导成真 CSV

## 部署记录
- repo：**https://github.com/01SYan19/NeoTImmuML**（2026-06-22 Playwright 进 tumoragdb.com.cn `#/neotimmuml` 点 card 经 window.open 抓出；repo = NeoTImmuML.ipynb + demo.csv(xlsx) + README）
- 论文：*NeoTImmuML: a machine learning-based prediction model for human tumor neoantigen immunogenicity*, Frontiers in Immunology 2025, DOI 10.3389/fimmu.2025.1681396
- 语言 / 框架：Python 3.10.4；scikit-learn + lightgbm + xgboost + matplotlib + seaborn；特征算用 R `Peptides` 包（外部）
- 外部许可证工具：无
- GPU 需求：不需要
- 部署状态：repo 已 clone `~/quantimmu/tools_repos/NeoTImmuML`；可跑（需补 R Peptides 特征管线 + 训练数据）。完整跑通需：①R 装 Peptides 算 78 特征 ②按 notebook 重训
- 跑通 TODO：装 R+Peptides 复刻特征计算 + 用 TumorAgDB/袁老师数据训练
