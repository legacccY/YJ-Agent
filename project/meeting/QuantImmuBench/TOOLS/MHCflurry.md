# MHCflurry 2.0 — 信息收集卡（PPT 素材）

> 4 类信息来源：DEPLOY_TRACKER §Tier-0 + HPC/deploy/mhcflurry/NOTES.md（2026-06-26 核实）。实跑项以「实测」标注。

## 0. 定位 / 一句话

**开源社区最广用的 MHC-I 提呈代理预测工具**，同时输出 binding affinity（nM）和 presentation score（0-1）；**本身不直接预测 T 细胞免疫原性**，在本 benchmark 中作「提呈代理 baseline」，检验「提呈预测无免疫原性微调能否代理强弱定量」。  
Apache-2.0，pip 一键装；2020 Cell Systems。

## 1. 输入数据模板 / 格式

- **文件格式**：Python API（DataFrame）或 CLI（CSV）
- **必填字段**（Python API）：
  - `peptides`：肽段列表（str list）
  - `alleles`：HLA allele 列表（`HLA-A*02:01` 格式）
- **肽段长度**：**8–15mer**（官方建议；短于 8 或长于 15 预测质量下降）
- **HLA 格式**：标准 `HLA-A*02:01`，**与 benchmark universe 格式一致，无需转换**
- **是否需基因组数据**：否
- **是否需野生型（WT）肽**：否（本 benchmark 同时喂 MT+WT 分别打分）
- **支持 allele 数量**：65 个（本 benchmark universe 全覆盖，0 NaN）
- **实测输入样例**（实测）：
  ```python
  from mhcflurry import Class1PresentationPredictor
  predictor = Class1PresentationPredictor.load()
  result = predictor.predict(
      peptides=["SIINFEKL", "NLVPMVATV"],
      alleles=["HLA-A*02:01"],
      verbose=0,
  )
  ```
- **实测行数**：53582 行（MT+WT 全量）

## 2. 运行参数设置

### Python API（本 benchmark 使用方式）

```python
from mhcflurry import Class1PresentationPredictor

predictor = Class1PresentationPredictor.load()

# 按 allele 分组循环（65 个 allele，每组约 800 肽）
result_df = predictor.predict(
    peptides=peptide_list,    # str list
    alleles=[allele],         # 当前 allele（单值列表）
    verbose=0,
)
```

### 主要可调参数

| 参数 | 说明 |
|---|---|
| `alleles` | 支持单个或多个 allele（多 allele 时每肽取最佳 allele）；本 benchmark 按 allele 分组单独预测 |
| `verbose` | 0 = 静默，1 = 进度 |

### 模型下载（安装时一次性执行）

```bash
pip install mhcflurry
mhcflurry-downloads fetch models_class1_presentation    # ~70MB，下载至 ~/.mhcflurry/
```

### HPC 离线安装

```bash
# 本地获取下载链接
mhcflurry-downloads url models_class1_presentation
# sftp 传 tar.bz2 → HPC
mhcflurry-downloads fetch models_class1_presentation --already-downloaded-dir <dir>
```

### 完整流水线命令

```bash
python HPC/deploy/mhcflurry/prep_input.py         # 生成分组输入
python HPC/deploy/mhcflurry/run_mhcflurry.py      # 全量预测（CPU ~30-60min，GPU ~5min）
python HPC/deploy/mhcflurry/parse_output.py        # 回贴 universe，34247 行
```

⚠️ **坑**：若环境已有 TF 1.x，需新建隔离 conda env（MHCflurry 依赖 TF 2.x/Keras）。Windows 本地 CPU 推理无 OMP 冲突（不用 scipy.stats）。

## 3. 输出数据格式 + 含义

### predictor.predict() 返回 DataFrame（原始输出）

| 列 | 含义 |
|---|---|
| `peptide` | 肽段序列 |
| `peptide_num` | 输入序号 |
| `sample_name` | allele 名 |
| `affinity` | **binding affinity（nM），越低越强结合**（需取负才与免疫强弱正相关） |
| `best_allele` | 最佳匹配 allele |
| `processing_score` | 抗原加工分数 [0,1] |
| `presentation_score` | **提呈综合分 [0,1]，越高越强提呈**（直接用） |
| `presentation_percentile` | 百分位 |

### 分数方向归一（本 benchmark 输出列）

| 原始列 | 原始方向 | 输出列名 | 变换 |
|---|---|---|---|
| `presentation_score` | 越高越强（0-1）| `MT/WT_MHCflurry_presentation` | **直接用** |
| `affinity`（nM）| 越低越强 | `MT/WT_MHCflurry_affinity_neg` | **取负**（`-affinity`） |

### 最终产物（`MHCflurry_DS1DS2_scores.csv`）

| 列 | 含义 |
|---|---|
| `Dataset` | DS1 / DS2 |
| `Peptide_ID` | 原始 ID |
| `HLA_Allele` | HLA-A*xx:xx |
| `MT_Subpeptide` | 突变肽序列 |
| `MT_MHCflurry_presentation` | MT 提呈分 [0,1] |
| `WT_MHCflurry_presentation` | WT 提呈分 [0,1] |
| `MT_MHCflurry_affinity_neg` | MT 亲和力取负（越高越强结合） |
| `WT_MHCflurry_affinity_neg` | WT 亲和力取负 |

- **分数类型**：presentation_score 连续 [0,1]；affinity 连续 [0,∞) nM
- **能否定量免疫强弱**：⚠️ **间接代理**（提呈/结合亲和力 ≠ T 细胞免疫原性），作 baseline 使用
- **实测输出**（实测）：34247 行，**0 NaN**（65 allele 全支持）；烟测已知强免疫原肽 sanity 通过

## 4. 简介（特点 / 优势）

- **方法**：神经网络 pan-allele 模型（Class1PresentationPredictor），联合建模 HLA 结合亲和力 + 抗原加工（proteasome + TAP），输出提呈综合分；不直接建模 TCR 识别
- **训练数据**：大规模 MHC-I 结合亲和力 + MS 洗脱配体数据（多机构多 allele），无 T 细胞免疫原性标注
- **特点 / 优势**：
  - 社区使用最广（open-source 生态第一），多数新工具论文以其作对比
  - 双分数（affinity + presentation），可分析哪条信号更预测真值
  - `pip install mhcflurry` 一键安装，无许可证障碍
  - Apache-2.0，完全自由发布（数字、结果无限制）
  - CPU/GPU 均可，65 allele 全量 CPU ~30–60min，GPU ~5min
- **局限**：
  - **不直接预测 T 细胞免疫原性**，无免疫原性微调；作 presentation proxy baseline
  - 提呈 ≠ 免疫原性（HLAthena 同样性质，benchmark AUC 近随机）
  - TF 版本依赖（TF 2.x），需隔离 conda env

## 部署记录

- **repo**：https://github.com/openvax/mhcflurry
- **论文**：*MHCflurry 2.0: Improved Pan-Allele Prediction of MHC-I-Presented Peptides by Incorporating Antigen Processing*，2020 · Cell Systems，DOI [10.1016/j.cels.2020.06.010](https://doi.org/10.1016/j.cels.2020.06.010)
- **语言 / 框架**：Python 3.10；TensorFlow 2.x / Keras；`pip install mhcflurry` 自动拉依赖
- **模型下载**：`mhcflurry-downloads fetch models_class1_presentation`（~70MB）
- **外部许可证工具**：无
- **GPU 需求**：无强制（TF 自动检测 GPU）
- **许可**：Apache-2.0（完全自由，发数字 ✅）
- **部署状态**：✅ **RUN_DONE**（本地 conda env qib_mhcflurry，65 allele 全支持，53582 对）
- **已知坑**：PYTHONUTF8=1（Windows yaml GBK 坑，conda env 内须设置）
- **部署文件**：`HPC/deploy/mhcflurry/`（prep_input.py / run_mhcflurry.py / parse_output.py / NOTES.md）
- **实测输出**：`MHCflurry_DS1DS2_scores.csv`，34247 行，0 NaN

---

**为什么选作对比**：检验「提呈预测（无免疫原性微调）能否当强弱定量代理」。作为领域「公共参照系」，多数新工具论文都拿它对比，不纳入会被 reviewer 注意。双分数可分析 affinity vs presentation 哪条更预测真值。（来源：NEWTOOLS_LIT_MATRIX §二 §4）
