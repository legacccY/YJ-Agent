# CNNeo / CNNeoPP — 信息收集卡（PPT 素材）

> 4 类信息来源：DEPLOY_TRACKER §Tier-0 + HPC/deploy/cnneo/NOTES.md（2026-06-26 实测）。实跑项以「实测」标注。

## 0. 定位 / 一句话

**LLM 增强 CNN 新表位免疫原性预测**（BioBERT 序列嵌入 + TextCNN；另有 TF-IDF FCNN 轻量子模型）。  
**输出 score ∈ [0,1]，softmax class=1 概率，越高越免疫原**，>0.5 判为免疫原。  
repo：github.com/AaronChen007/neoantigen；MIT 许可；2026 Frontiers in Immunology。

## 1. 输入数据模板 / 格式

- **文件格式**：CSV（有表头）
- **必填列 / 字段**：
  - `peptide`：肽段氨基酸序列
  - `hla`：HLA allele（标准 `HLA-A*02:01` 格式）
- **肽段长度**：
  - **8–11mer**：训练分布内，补 X 至 11 字符后处理
  - **12–14mer**：可处理（不截断），轻度 OOD，分数供参考
  - <8 或 >14mer：prep_input.py 过滤，不喂模型（NaN）
- **HLA 格式**：输入用标准 `HLA-A*02:01`；模型内部自动去 `*`（`HLA-A02:01`），用于 k-mer 拼接
- **是否需基因组数据**：否
- **是否需野生型（WT）肽**：否（但本 benchmark 同时喂 MT+WT 分别打分）
- **实测输入样例**（实测）：
  ```
  peptide,hla
  SIINFEKL,HLA-A*02:01
  NLVPMVATV,HLA-B*07:02
  ```
- **实测行数**：53582 行（MT+WT 全量，8–14mer 均有）

## 2. 运行参数设置

> **重要**：CNNeo **无预训练权重**，首次运行自动从 `repo/training_data/training_data.xlsx` 训练，权重保存至 `weights/`。

### 子模型选择（`--model`）

| 子模型 | 参数 | 框架 | 说明 |
|---|---|---|---|
| **FCNN_TF**（默认）| 不加 `--model` | PyTorch + TF-IDF | TF-IDF 6-mer → FCNN(1000→64→2)；CPU 友好，约 5–15min |
| **CNN_BioBERT** | `--model cnn_biobert` | PyTorch + BioBERT | 4-mer → BioBERT → TextCNN；HF 下载 ~500MB |
| ~~FCNN_BioBERT~~ | 不支持 | — | 需 BA/TAP 等额外列，已排除 |

### 主要参数

| 参数 | 说明 |
|---|---|
| `--smoke N` | 烟测：仅对 N 对肽做推理（不影响训练） |
| `--force-retrain` | 强制重新训练（覆盖已有 weights/） |
| `--model` | 子模型选择（见上表） |

### 完整命令行（三步流水线）

```bash
# Step 1: 准备输入
python HPC/deploy/cnneo/prep_input.py

# Step 2: 训练（首次自动）+ 推理
python HPC/deploy/cnneo/run_cnneo.py                    # 默认 FCNN_TF
# 或
python HPC/deploy/cnneo/run_cnneo.py --model cnn_biobert

# Step 3: 回贴 universe
python HPC/deploy/cnneo/parse_output.py
```

### FCNN_TF 编码细节

1. HLA 去 `*`（`HLA-A02:01`），拼接 padded 肽（pad 至 11 chars）
2. 滑窗切 **6-mer**（全小写），空格分隔为文本串
3. **TF-IDF**（max_features=1000）→ FCNN（1000→64→2）→ softmax[:, 1]

### CNN_BioBERT 编码细节

1. HLA 去 `*`，拼接 padded 肽（11 chars）
2. 滑窗切 **4-mer**（全小写），空格分隔
3. **BioBERT**（`dmis-lab/biobert-base-cased-v1.1`）嵌入，max_length=64
4. last_hidden_state → TextCNN（filters=[3,4,5], num_filters=120）→ softmax[:, 1]

## 3. 输出数据格式 + 含义

### 中间产物（`cnneo_raw_output.csv`，run_cnneo.py 产出）

| 列 | 类型 | 含义 |
|---|---|---|
| `peptide` | str | 原始肽序列（未补 X） |
| `hla` | str | 标准 `HLA-A*02:01` 格式 |
| `score` | float [0,1] | softmax class=1 概率，越高越免疫原 |
| `label` | int {0,1} | score>0.5 → 1（预测阳性） |

### 最终产物（`CNNeo_DS1DS2_scores.csv`，parse_output.py 产出）

| 列 | 含义 |
|---|---|
| `Dataset` | DS1 / DS2 |
| `Peptide_ID` | 原始 ID |
| `HLA_Allele` | HLA-A*xx:xx |
| `MT_Subpeptide` | 突变肽序列 |
| `MT_CNNeo` | MT 侧 CNNeo score（float / NaN） |
| `WT_CNNeo` | WT 侧 CNNeo score（float / NaN） |

- **分数类型**：连续 [0,1]（softmax 概率）
- **分数方向**：**越高越免疫原，直接用，无需翻转**
- **能否定量免疫强弱**：✅ 是（0-1 连续，可排名）← 项目核心目标
- **实测输出**（实测）：
  - 34247 行，**0 NaN**，score 范围 **0.13–0.96**
  - 使用 FCNN_TF 子模型（自训 ValAcc ~75%）

## 4. 简介（特点 / 优势）

- **方法**：三子模型 notebook 设计，最终 ensemble；本 benchmark 用 FCNN_TF（TF-IDF FCNN）和/或 CNN_BioBERT（BioBERT+TextCNN）
- **训练数据**：`training_data.xlsx`（TESLA/IEDB 多来源免疫原性标注肽，含 label 0/1），SMOTE 过采样平衡类别
- **特点 / 优势**：
  - **LLM 序列嵌入**：率先在新表位免疫原性任务引入 BioBERT 蛋白质语言模型嵌入，正交于 BigMHC（自训大矩阵而非外部 LLM）
  - FCNN_TF 子模型轻量，CPU 5–15min 可训练完
  - 2026 最新发表，TESLA+ELISpot 验证（与本 benchmark 真值同源）
  - MIT 许可，完全自由发布
- **局限**：
  - **无官方预训练权重**，每次需自训（训练数据为 repo 内置 xlsx）
  - CNN_BioBERT GPU 训练约 20–30min，CPU 需数小时
  - 12–14mer 轻度 OOD（训练主体 8–11mer）

## 部署记录

- **repo**：https://github.com/AaronChen007/neoantigen
- **论文**：*CNNeoPP: a LLM-enhanced deep learning pipeline for personalized neoantigen prediction and liquid biopsy applications*，2026 · Frontiers in Immunology，DOI [10.3389/fimmu.2026.1722117](https://doi.org/10.3389/fimmu.2026.1722117)
- **语言 / 框架**：Python 3.8.5；PyTorch 2.4.1 + transformers 4.46.3 + scikit-learn + imbalanced-learn
- **外部许可证工具**：无（BioBERT 权重从 HuggingFace 自动下载）
- **GPU 需求**：无强制（FCNN_TF CPU 可跑）；CNN_BioBERT GPU 大幅加速
- **许可**：MIT（完全自由，发数字 ✅）
- **部署状态**：✅ **RUN_DONE**（本地 Windows，FCNN_TF 自训推理，53582 对）
- **部署文件**：`HPC/deploy/cnneo/`（prep_input.py / run_cnneo.py / parse_output.py / NOTES.md）
- **实测输出**：`CNNeo_DS1DS2_scores.csv`，34247 行，0 NaN，score 0.13–0.96

---

**为什么选作对比**：填「LLM 增强序列表征」方法学空白，正交于 BigMHC（自训大矩阵非外部 LLM）。2026 最新发表、TESLA+ELISpot 验证（与本项目真值同源）、MIT 许可、轻量 backbone，展示方法前沿。（来源：NEWTOOLS_LIT_MATRIX §二 §5）
