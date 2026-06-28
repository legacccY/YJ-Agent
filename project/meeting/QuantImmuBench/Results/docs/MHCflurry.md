# MHCflurry 2.0 — 工具交付说明

> 项目：QuantImmuBench（癌症个性化新抗原疫苗协作项目）
> 任务：HPC 部署测试现有预测工具，收集 4 类信息 + benchmark 结果。
> 版本与数字截至 2026-06-28（DS2 ELISpot 全量重算后）。详细环境配置命令见同目录《环境配置命令_回顾记录.md》。

> ⚠️ **定位与双输出提示（先读）**：MHCflurry **本身不直接预测 T 细胞免疫原性**，它输出 MHC-I 提呈分（presentation）与结合亲和力（affinity）。在 QuantImmuBench 中作「**提呈代理基线**」，用于检验「无免疫原性微调的提呈预测能否代理免疫强弱定量」。本项目从其原始输出派生**两条分数列**：`presentation`（提呈分，越高越强）与 `affinity_neg`（亲和力取负，越高越强结合），二者方向、表现不同，须分别看待。

---

## 1. 工具简介

- **原理 / 方法**：pan-allele 神经网络模型（Class1PresentationPredictor），联合建模 HLA 结合亲和力 + 抗原加工（proteasome + TAP），输出提呈综合分；不直接建模 TCR 识别。
- **训练数据**：大规模 MHC-I 结合亲和力 + MS 洗脱配体数据（多机构、多 allele），无 T 细胞免疫原性标注。
- **特点 / 优势**：开源社区使用最广的 MHC-I 提呈代理工具，多数新工具论文以其为对比参照系；双分数输出（affinity + presentation），可分析哪条信号更预测真值；`pip install mhcflurry` 一键安装，无许可障碍；CPU / GPU 均可，65 个 allele 全量 CPU 约 30–60min、GPU 约 5min。
- **局限**：不直接预测 T 细胞免疫原性，无免疫原性微调（提呈 ≠ 免疫原性，benchmark 接近随机）；依赖 TensorFlow 2.x，需隔离 conda 环境。
- **论文**：*MHCflurry 2.0: Improved Pan-Allele Prediction of MHC-I-Presented Peptides by Incorporating Antigen Processing*, Cell Systems, 2020。DOI: 10.1016/j.cels.2020.06.010。
- **代码**：https://github.com/openvax/mhcflurry 。
- **许可证**：Apache-2.0（完全自由，发表数字、结果无限制）。

---

## 2. 输入数据模板 / 格式

- **文件格式**：Python API（DataFrame）或 CLI（CSV）。本项目用 Python API。
- **必填字段**（Python API）：
  - `peptides`：肽段列表（str list）；
  - `alleles`：HLA 等位列表（`HLA-A*02:01` 格式）。
- **肽段长度**：8–15mer（官方建议；短于 8 或长于 15 预测质量下降）。
- **HLA 格式**：标准 `HLA-A*02:01`，与 benchmark universe 一致，无需转换；本项目 65 个 allele 全覆盖（0 NaN）。
- **是否需基因组 / WT 肽**：均否（本 benchmark 同时喂 MT + WT 分别打分）。
- **输入样例**（实测）：
  ```python
  from mhcflurry import Class1PresentationPredictor
  predictor = Class1PresentationPredictor.load()
  result = predictor.predict(
      peptides=["SIINFEKL", "NLVPMVATV"],
      alleles=["HLA-A*02:01"],
      verbose=0,
  )
  ```
  实测输入 53582 行（MT + WT 全量）。

---

## 3. 参数设置

| 参数 | 说明 |
|---|---|
| `peptides` | 肽段列表（str list） |
| `alleles` | 单个或多个 allele；多 allele 时每肽取最佳 allele。本项目按 allele 分组（65 组，每组约 800 肽）单独预测 |
| `verbose` | 0 = 静默，1 = 进度 |

**模型下载**（安装时一次性）：
```bash
pip install mhcflurry
mhcflurry-downloads fetch models_class1_presentation   # 约 70MB，下载至 ~/.mhcflurry/
```

**完整流水线命令**：
```bash
python prep_input.py        # 生成分组输入
python run_mhcflurry.py     # 全量预测（CPU ~30-60min，GPU ~5min）
python parse_output.py      # 回贴 universe，34247 行
```

---

## 4. 输出格式及含义

- **predictor.predict() 原始输出列**：

| 列 | 含义 |
|---|---|
| `peptide` | 肽段序列 |
| `peptide_num` | 输入序号 |
| `sample_name` | allele 名 |
| `affinity` | **结合亲和力（nM），越低越强结合**（须取负才与免疫强弱正相关） |
| `best_allele` | 最佳匹配 allele |
| `processing_score` | 抗原加工分数 [0,1] |
| `presentation_score` | **提呈综合分 [0,1]，越高越强提呈**（直接用） |
| `presentation_percentile` | 百分位 |

- **本项目分数方向归一**（最终产物 `MHCflurry_DS1DS2_scores.csv` 两条派生列）：

| 原始列 | 原始方向 | 输出列 | 变换 |
|---|---|---|---|
| `presentation_score` | 越高越强（0–1） | `MT/WT_MHCflurry_presentation` | 直接用 |
| `affinity`（nM） | 越低越强 | `MT/WT_MHCflurry_affinity_neg` | 取负（−affinity） |

- **分数类型 / 范围**：presentation 连续 [0, 1]；affinity 连续 [0, ∞) nM（取负后越高越强结合）。
- **能否定量免疫强弱**：⚠️ **间接代理**（提呈 / 结合亲和力 ≠ T 细胞免疫原性），作 baseline 使用。
- **实测输出**：34247 行，**0 NaN**（65 allele 全支持）；已知强免疫原肽 sanity 烟测通过。

---

## 5. 最新 benchmark 结果（DS2 ELISpot）

> 数据源：`analysis/metrics_ds2_16tools.csv` + `analysis/per_patient_spearman_16tools.csv`（2026-06-28 全量重算）。
> 两条派生列分别评估。

- **覆盖率**：n_pep = **101**（DS2 全部 101 个肽，肽段层 34247 行 0 NaN，覆盖完整）。

### 5.1 presentation（提呈分）

- per-patient Fisher-z 加权 ρ（**主指标**）= **+0.124**，95% CI [−0.108, +0.342]（n=9）——CI 跨 0。
- 全局 Spearman ρ（max 聚合，对照）= **+0.098**（p = 0.329，不显著）。
- AUC（max，SFC > 0）= **0.513**。

### 5.2 affinity_neg（亲和力取负）

- per-patient Fisher-z 加权 ρ（**主指标**）= **+0.203**，95% CI [−0.028, +0.413]（n=9）——CI 跨 0（接近排除 0）。
- 全局 Spearman ρ（max 聚合，对照）= **+0.128**（p = 0.202，不显著）。
- AUC（max，SFC > 0）= **0.476**。

**小结**：两条信号中，**affinity_neg 在主指标上略优于 presentation**——其 per-patient Fisher-z 加权 ρ = +0.203（CI 接近排除 0）高于 presentation 的 +0.124，全局 max ρ 也更高（+0.128 vs +0.098），但两者全局相关均未达显著、per-patient CI 均跨 0。整体表现弱（无 ρ>0.4），符合「提呈 / 亲和力代理无法稳定定量免疫强弱」的预期；结合亲和力信号比综合提呈分更接近真值，是值得注意的发现。结论受 DS2 小样本（101 肽）限制。

---

## 6. 部署环境简述

- **部署状态**：RUN_DONE（本地 conda 环境 qib_mhcflurry，65 allele 全支持，53582 对）。
- **平台**：Python 3.10；TensorFlow 2.x / Keras（`pip install mhcflurry` 自动拉依赖）；无强制 GPU，TF 自动检测。
- **关键坑**：
  1. 若环境已有 TF 1.x 会冲突，须新建隔离 conda env（依赖 TF 2.x）；
  2. HPC 无公网时用 `mhcflurry-downloads fetch ... --already-downloaded-dir <dir>` 离线安装（本地先 `mhcflurry-downloads url` 取链接 + sftp 传）；
  3. Windows 本地须设 `PYTHONUTF8=1`（避免 yaml GBK 编码坑）。
- 详细命令见同目录《环境配置命令_回顾记录.md》及 `HPC/deploy/mhcflurry/NOTES.md`。
