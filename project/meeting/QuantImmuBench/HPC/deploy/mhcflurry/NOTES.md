# MHCflurry 2.0 — 部署说明（QuantImmuBench §Tier-0）

> 建档：2026-06-26。服务 quantimmu-bench 工具扩张 v2 第一波。  
> 许可：Apache-2.0，自由发布数字。

---

## 安装

### 方法 A：pip（推荐，HPC 或本地均可）

```bash
pip install mhcflurry
mhcflurry-downloads fetch models_class1_presentation
```

`models_class1_presentation` 约 70MB，下载到 `~/.mhcflurry/`（或 `MHCFLURRY_DOWNLOADS_PATH` 指向处）。  
HPC 无公网时可用手动下载（见"HPC 离线安装"节）。

### 方法 B：conda 环境（推荐隔离）

```bash
conda create -n mhcflurry_env python=3.10 -y
conda activate mhcflurry_env
pip install mhcflurry pandas
mhcflurry-downloads fetch models_class1_presentation
```

> 注：mhcflurry 2.x 依赖 TensorFlow 2.x / Keras，pip 会自动拉取合适版本。  
> 若 HPC 有 CUDA，TF 会自动识别 GPU，无需额外配置。

### HPC 离线安装（XJTLU gpu4090 无公网）

1. 本地 `mhcflurry-downloads url models_class1_presentation` 获取下载链接
2. 本地下载 tar.bz2 文件，`sftp` 传到 HPC
3. HPC 上：`mhcflurry-downloads fetch models_class1_presentation --already-downloaded-dir <dir>`

---

## 运行流水线

```bash
# Step 1: 准备输入（需模型已下载，用 --skip-predictor 可跳过 allele 检查）
python HPC/deploy/mhcflurry/prep_input.py

# Step 2: 跑烟测（5 肽验算子/列结构）
python HPC/deploy/mhcflurry/run_mhcflurry.py --smoke 5

# Step 3: 全量预测（53K 对，CPU ~30-60min，GPU ~5min）
python HPC/deploy/mhcflurry/run_mhcflurry.py

# Step 4: 回贴 universe（34247 行输出）
python HPC/deploy/mhcflurry/parse_output.py
```

最终输出：`scripts/out/newtools/MHCflurry_DS1DS2_scores.csv`

---

## 官方 API 出处（2026-06-26 核自 GitHub master）

**来源**：`github.com/openvax/mhcflurry/blob/master/mhcflurry/class1_presentation_predictor.py`

```python
from mhcflurry import Class1PresentationPredictor

predictor = Class1PresentationPredictor.load()

# 支持的 allele（格式 HLA-A*02:01，直接与 universe HLA_Allele 匹配）
supported = set(predictor.supported_alleles)

# 预测（单 allele 当单样本）
result_df = predictor.predict(
    peptides=["SIINFEKL", "NLVPMVATV"],
    alleles=["HLA-A*02:01"],   # 列表 = 单样本
    verbose=0,
)
# 返回 DataFrame 列：
#   peptide, peptide_num, sample_name,
#   affinity (nM, 越低越强),
#   best_allele, processing_score,
#   presentation_score (0-1, 越高越强),
#   presentation_percentile
```

列名核实来源：`predict_columns()` 方法 + `predict()` docstring 示例输出（同文件）。  
`supported_alleles` property 核实来源：`class1_presentation_predictor.py` + `class1_affinity_predictor.py`。

---

## 已知坑

1. **模型下载慢 / HPC 无公网**：用 `--already-downloaded-dir` 离线安装（见上）。
2. **TF 版本冲突**：若环境已有 TF 1.x 会失败 → 建新 conda env 隔离。
3. **Windows OMP Error #15**：MHCflurry 用 TF/Keras，不调 scipy.stats，无 OMP 冲突。但若在 Windows 本地跑注意 TF 版本（TF 2.10 是最后一个原生 Windows GPU 支持版）；CPU 推理 Windows 无问题。
4. **allele 格式**：supported_alleles 返回 `HLA-A*02:01` 格式；universe 也是此格式，直接比较即可，无需转换。
5. **predict() 返回行顺序**：与输入 peptides 列表顺序一致（无 shuffle），可安全按输入顺序对应。
6. **处理速度**：65 个 allele，平均每组 ~800 肽，CPU 下每组约 5-30s，总计约 30-60min。HPC GPU 快 10 倍以上。

---

## 分数方向归一说明（越高越免疫原）

| 原始列 | 原始方向 | 输出列 | 变换 |
|--------|----------|--------|------|
| `presentation_score` | 越高越强（0-1） | `MT/WT_MHCflurry_presentation` | 直接用 |
| `affinity` (nM) | 越低越强 | `MT/WT_MHCflurry_affinity_neg` | 取负 (`-affinity`) |

计算 Spearman(ρ, ELISpot) 时两列均直接使用（正相关越高越好）。

---

## 4 类信息（工具横评标准格式）

| 项 | 值 |
|----|----|
| 工具版本 | MHCflurry 2.x（pip install mhcflurry 最新稳定版 2.2.x；2.3.0rc3 候选中，API 兼容） |
| 许可 | Apache-2.0，数字可自由发布 |
| 输入格式 | peptide(str) + allele(HLA-A*02:01 格式)，8-15mer |
| 输出分数 | presentation_score(0-1) + affinity(nM) |
| 运行平台 | CPU 或 GPU（TensorFlow 自动检测），无需结构/测序数据 |
| 分类 | proxy baseline（BA + presentation），非 T 细胞免疫原性直接预测 |
