# CNNeo / CNNeoPP — 工具交付说明

> 项目：QuantImmuBench（癌症个性化新抗原疫苗协作项目）
> 任务：HPC 部署测试现有预测工具，收集 4 类信息 + benchmark 结果。
> 版本与数字截至 2026-06-28（DS2 ELISpot 全量重算后）。详细环境配置命令见同目录《环境配置命令_回顾记录.md》。

---

## 1. 工具简介

- **原理 / 方法**：LLM 增强的 CNN 新表位免疫原性预测。旗舰子模型用 BioBERT 蛋白质语言模型嵌入 + TextCNN；另有轻量子模型用 TF-IDF + 全连接网络（FCNN）。本项目 benchmark 采用 CPU 友好的 **FCNN_TF** 子模型（TF-IDF 6-mer → FCNN 1000→64→2 → softmax）。
- **训练数据**：repo 内置 `training_data.xlsx`（TESLA / IEDB 多来源免疫原性标注肽，含 label 0/1），训练时用 SMOTE 过采样平衡类别。
- **特点 / 优势**：率先在新表位免疫原性任务引入 BioBERT 蛋白质语言模型嵌入，方法学上正交于 BigMHC（自训大矩阵而非外部 LLM）；FCNN_TF 轻量，CPU 5–15 分钟可训完；2026 最新发表，TESLA + ELISpot 验证（与本项目真值同源）；MIT 许可，完全自由发布。
- **局限**：**无官方预训练权重**，每次需从内置 xlsx 自训；CNN_BioBERT 子模型 CPU 训练需数小时（GPU 约 20–30 分钟）；12–14mer 为轻度分布外（训练主体 8–11mer）。
- **论文**：*CNNeoPP: a LLM-enhanced deep learning pipeline for personalized neoantigen prediction and liquid biopsy applications*, Frontiers in Immunology, 2026。DOI: 10.3389/fimmu.2026.1722117。
- **代码**：https://github.com/AaronChen007/neoantigen 。
- **许可证**：MIT（完全自由，发表数字允许；BioBERT 权重从 HuggingFace 自动下载）。

---

## 2. 输入数据模板 / 格式

- **文件格式**：CSV（带表头）。
- **必填列**：
  - `peptide`：肽段氨基酸序列；
  - `hla`：HLA 等位（标准 `HLA-A*02:01` 格式）。
- **肽段长度**：
  - 8–11mer：训练分布内，补 X 至 11 字符后处理；
  - 12–14mer：可处理（不截断），轻度分布外，分数供参考；
  - <8 或 >14mer：prep_input.py 过滤，不喂模型（NaN）。
- **HLA 格式**：输入用标准 `HLA-A*02:01`；模型内部自动去 `*`（`HLA-A02:01`）用于 k-mer 拼接。
- **是否需基因组 / WT 肽**：均否（本 benchmark 同时喂 MT + WT 分别打分）。
- **输入样例**（实测）：
  ```
  peptide,hla
  SIINFEKL,HLA-A*02:01
  NLVPMVATV,HLA-B*07:02
  ```
  实测输入 53582 行（MT + WT 全量，8–14mer 均有）。

---

## 3. 参数设置

> **重要**：CNNeo 无预训练权重，首次运行 `run_cnneo.py` 自动从 `repo/training_data/training_data.xlsx` 训练，权重保存至 `weights/`。

| 参数 | 说明 |
|---|---|
| `--model` | 子模型选择：默认 FCNN_TF（不加该参数）；`cnn_biobert` = CNN_BioBERT 子模型 |
| `--smoke N` | 烟测：仅对 N 对肽推理（不影响训练） |
| `--force-retrain` | 强制重新训练（覆盖已有 weights/） |

**子模型对照**：

| 子模型 | 参数 | 框架 | 说明 |
|---|---|---|---|
| FCNN_TF（默认，本项目用） | 不加 `--model` | PyTorch + TF-IDF | TF-IDF 6-mer → FCNN；CPU 友好，约 5–15min |
| CNN_BioBERT | `--model cnn_biobert` | PyTorch + BioBERT | 4-mer → BioBERT → TextCNN；HF 下载约 500MB |

**完整命令**（三步流水线）：
```bash
python prep_input.py        # 准备输入
python run_cnneo.py         # 训练（首次自动）+ 推理，默认 FCNN_TF
python parse_output.py      # 回贴 universe
```

---

## 4. 输出格式及含义

- **中间产物**（`cnneo_raw_output.csv`）：

| 列 | 类型 | 含义 |
|---|---|---|
| `peptide` | str | 原始肽序列（未补 X） |
| `hla` | str | 标准 `HLA-A*02:01` 格式 |
| `score` | float [0,1] | softmax class=1 概率，越高越免疫原 |
| `label` | int {0,1} | score>0.5 → 1（预测阳性） |

- **最终产物**（`CNNeo_DS1DS2_scores.csv`）：Dataset / Peptide_ID / HLA_Allele / MT_Subpeptide / MT_CNNeo / WT_CNNeo。
- **分数类型 / 方向 / 范围**：连续 [0, 1]（softmax 概率），**越高越免疫原，直接使用，无需翻转**。
- **能否定量免疫强弱**：✅ 是（0–1 连续，可排名）——契合项目核心目标。
- **实测输出**：34247 行，**0 NaN**，score 范围 0.13–0.96（FCNN_TF 子模型，自训验证集准确率约 75%）。

---

## 5. 最新 benchmark 结果（DS2 ELISpot）

> 数据源：`analysis/metrics_ds2_16tools.csv` + `analysis/per_patient_spearman_16tools.csv`（2026-06-28 全量重算）。FCNN_TF 子模型。

- **覆盖率**：n_pep = **101**（DS2 全部 101 个肽，肽段层 34247 行 0 NaN，覆盖完整）。
- **per-patient Fisher-z 加权 ρ（主指标）**：**−0.204**，95% CI [−0.413, +0.026]（n_patients = 9）——CI 跨 0，无显著患者内相关。
- **全局 Spearman ρ（max 聚合，对照）**：ρ = **+0.085**（p = 0.396，不显著）。
- **AUC（max，SFC > 0）**：**0.398**。

**小结**：CNNeo（FCNN_TF）在 DS2 ELISpot 上 ρ ≈ +0.09 且不显著、AUC ≈ 0.40–0.55，per-patient CI 跨 0，本数据集未显现稳定的免疫强弱定量能力。注意此为 repo 内置数据自训的 FCNN_TF 轻量子模型，BioBERT 旗舰子模型未纳入本轮 benchmark；结论受 DS2 小样本（101 肽）限制。

---

## 6. 部署环境简述

- **部署状态**：RUN_DONE（本地 Windows，FCNN_TF 自训推理，53582 对）。
- **平台**：Python 3.8.5；PyTorch 2.4.1 + transformers 4.46.3 + scikit-learn + imbalanced-learn；无强制 GPU（FCNN_TF CPU 可跑），CNN_BioBERT GPU 大幅加速。
- **关键坑**：
  1. 无官方权重，须自训（首次 run 自动训练，约 5–15min CPU）；
  2. "FCN_TF" 的 "TF" 指 TF-IDF，不是 TensorFlow，全程 PyTorch；
  3. CNN_BioBERT 首次推理自动从 HuggingFace 下载 `dmis-lab/biobert-base-cased-v1.1`（约 500MB），HPC 不联网时须提前在 DTN 节点下载并设 `TRANSFORMERS_CACHE`；
  4. 训练用 SMOTE 过采样，须 `pip install imbalanced-learn`。
- 详细命令见同目录《环境配置命令_回顾记录.md》及 `HPC/deploy/cnneo/NOTES.md`。
