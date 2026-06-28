# NeoTImmuML 工具交付说明

> 服务项目：QuantImmuBench（癌症个性化新抗原疫苗协作项目）—— 工具部署与 benchmark 交付文档
> 数据红线：本文所有 benchmark 数字逐一溯源 `analysis/metrics_ds2_16tools.csv` 与 `analysis/per_patient_spearman_16tools.csv`，未自创。
> ⚠️ 版本提示：本项目跑的是**自训复刻版（★）**，非官方权重——官方仓库不发布预训练模型，详见下文「部署环境简述」。

---

## 1. 工具简介

- **原理 / 方法**：加权集成机器学习。以肽段的 **78 个物理化学描述符**（由 R `Peptides` 包计算，如分子量、等电点、Boman 指数、电荷、疏水性、不稳定性指数、BLOSUM/Cruciani/FASGAI 等系列描述符）为输入特征，用 LightGBM + XGBoost + RandomForest 三个基学习器组成 `VotingClassifier`（软投票）预测肿瘤新抗原免疫原性，输出连续概率（`predict_proba`）可用于强弱排名。
- **特点**：
  - **不依赖 HLA 结合预测外部工具**（如 netMHCpan）——纯肽段物化特征建模，无 DTU 学术许可负担，部署链最轻。
  - 训练数据较新：TumorAgDB2.0（187,223 条）。
  - ⚠️ **HLA-agnostic（与 HLA 无关）**：模型不读 HLA 等位，**同一肽段在不同 HLA 上得到完全相同的分数**——这是它在本 benchmark 中需特别标注的固有特性。
- **论文**：*NeoTImmuML: a machine learning-based prediction model for human tumor neoantigen immunogenicity*, Frontiers in Immunology, 2025. DOI: **10.3389/fimmu.2025.1681396**
- **代码仓库**：https://github.com/01SYan19/NeoTImmuML （内容 = `NeoTImmuML.ipynb` + `demo.csv`（实为 xlsx）+ README）
- **许可证**：仓库未附明确 LICENSE 文件——再分发前需向作者确认授权范围。

---

## 2. 输入数据模板 / 格式

- **文件格式**：CSV（仓库自带 `demo.csv` 实际为 xlsx，10 行 × 80 列；使用前需另存为真 CSV）。
- **列结构**：
  - 第 1 列 `Peptide`（肽段序列）
  - 第 2 列 `immunogenicity`（标签 0/1，训练 / 评估用）
  - 第 3–80 列 = **78 个预计算物化特征**（须先用 R `Peptides` 包外部算好；仓库不含特征计算代码）
- **肽段长度**：8–13 AA（MHC I 类）。
- **HLA 格式**：**不需要 HLA 列**（纯肽段特征建模）。
- **是否需基因组数据**：否。
- ⚠️ notebook 中 `X = data.iloc[:, 2:]`（特征从第 3 列起）、`y = data['immunogenicity']`——若喂新肽段，须先在外部用 R `Peptides` 包补齐 78 个描述符列。

**示例（概念）**：

| Peptide | immunogenicity | mol_weight | isoelectric_point | boman_index | … (共 78 列) |
|---|---|---|---|---|---|
| KLFGTPLEV | 1 | … | … | … | … |

---

## 3. 参数设置

- **运行形态**：不是命令行 CLI 工具，而是 **Jupyter notebook**（`NeoTImmuML.ipynb`，21 个 code cell）。
- notebook 内含 8 种 ML 算法横向对比 + 加权集成（LGBM/XGB/RF）+ 5 折交叉验证 + 雷达图评估。
- **无命令行参数**；改数据靠编辑 notebook 内 `file_path = "Input.csv"` 指向自己的数据。
- 可调项：基学习器超参（LGBM/XGB/RF 各自参数）、投票权重、CV 折数——均在 notebook code cell 内手工调整。

---

## 4. 输出格式及含义

- **输出类型**：二分类标签 + 连续概率（`predict_proba`，0–1）。
- **方向**：分数越高 = 越倾向免疫原性阳性（可用于强弱排名）。
- **范围**：0–1。
- notebook 原生输出为评估产物（accuracy / precision / recall / F1 / AUROC 指标表 + 混淆矩阵 + 雷达图），单条肽段预测通过 `predict_proba` 取概率列获得。
- 本项目交付包 `5tools_delivery/NeoTImmuML.xlsx` 中主输出列：`MT_NeoTImmuML` / `WT_NeoTImmuML`（+ `rf` / `lgb` / `xgb` 各基学习器概率）。

---

## 5. 最新 benchmark 结果（DS2 ELISpot）

> 数据集：DS2 ELISpot，101 肽 / 9 患者；IMPROVE 跑通后 16 工具全量重算。主指标为逐患者 Fisher-z，对照口径为全局 Spearman（max 聚合），AUC 取 SFC > 0。
> 数字来源：`analysis/metrics_ds2_16tools.csv`、`analysis/per_patient_spearman_16tools.csv`。

| 指标 | 数值 |
|---|---|
| n_pep（覆盖肽数） | 101 / 101（全覆盖；9 患者，per-patient n_used=9，n_dropped=0） |
| per-patient Fisher-z 加权 ρ [95% CI]（**主指标**） | **+0.033 [−0.194, +0.256]**（CI 跨 0，不显著） |
| Spearman ρ（max 聚合，对照） | **+0.022**，p = 0.829（不显著） |
| AUC（max，SFC > 0） | 0.655 |

**解读**：全局与患者内相关均接近 0、统计不显著；AUC（SFC > 0）= 0.655 主要受类别极不平衡（90 阳 / 11 阴）影响，并非真实区分力。HLA-agnostic 设计使其无法区分同肽在不同 HLA 上的免疫原性差异，是本任务下的主要局限。

---

## 6. 部署环境简述

- **跑的版本**：⚠️ **自训复刻版（★，非官方）**。官方仓库**不发布预训练权重**（无 .pkl），且**不含 78 特征计算代码**——故按 notebook 逻辑用 R `Peptides` 包复刻特征管线 + 复刻官方 RF+LGB+XGB 集成自行训练。结论不对标原论文报告值。
- **环境**：HPC conda env `envs/neotimmuml`（Python 3.10 + lightgbm 4.6 + xgboost 3.2 + scikit-learn）；特征计算用 R + `Peptides` 包；CPU 推理，无 GPU 需求。
- **仓库位置**：`~/quantimmu/tools_repos/NeoTImmuML`；HPC 部署脚本 `HPC/deploy/hpc_neotimmuml.sh`。
- 详细环境配置命令见同目录《环境配置命令_回顾记录.md》。
