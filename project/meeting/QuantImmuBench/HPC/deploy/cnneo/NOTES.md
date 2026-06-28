# CNNeo / CNNeoPP 部署说明

> 服务项目：quantimmu-bench §扩张v2 Tier-0，lever=部署 CNNeo apples-to-apples 免疫原性工具。
> 建档：2026-06-26。来源：git clone AaronChen007/neoantigen + 逐 cell 读三个 ipynb 实测。

---

## 1. Repo 结构（实测，非猜测）

```
repo/
├── README.md
├── CHANGELOG.md
├── LICENSE.md              # MIT 许可
├── environment.yml         # conda env "cnneopp"（Python 3.8.5 + PyTorch 2.4.1 + transformers 4.46.3）
├── CNNeoPP workflow.docx   # 工作流文档（Word）
├── models/
│   ├── CNNeo_CNN_BioBERT.ipynb   # 子模型①：BioBERT 嵌入 + TextCNN（旗舰）
│   ├── CNNeo_FCNN_BioBERT.ipynb  # 子模型②：BioBERT + FCNN（需额外特征，不适用当前输入）
│   └── CNNeo_FCN_TF.ipynb        # 子模型③：TF-IDF 6-mer + FCNN（CPU 友好，脚本默认）
├── training_data/
│   ├── training_data.xlsx        # 训练数据（必须，含 "Mutated Peptide", "HLA type", "label"）
│   └── MHC_pseudo.dat            # HLA 伪序列（仅 FCNN_BioBERT 需要，当前脚本不用）
├── data/example/
│   ├── input_features.csv        # 示例输入（实为 xlsx 格式，被误命名）
│   └── example_output.csv        # 示例输出（6 列）
└── independent dataset/
    └── independent dataset.xlsx
```

---

## 2. 框架与依赖

| 子模型 | 框架 | 额外依赖 | 适用当前输入？ |
|---|---|---|---|
| FCNN_TF | PyTorch + scikit-learn TF-IDF | imbalanced-learn（SMOTE） | ✅ **默认** |
| CNN_BioBERT | PyTorch + transformers（BioBERT）| HF 下载 ~500MB | ✅ --model cnn_biobert |
| FCNN_BioBERT | PyTorch + transformers + 额外特征 | BA/TAP/NetCTLpan 等列 | ❌ 当前输入无这些列，已排除 |

注意："FCN_TF" 中 "TF" = **TF-IDF**（不是 TensorFlow），模型全程 PyTorch。

---

## 3. 权重文件状态

**repo 不含任何预训练权重（.pth / .h5 / .pkl）。**

三个 ipynb 均为**训练 + 评估** notebook，保存格式：
- `CNN_BioBERT.pth` — TextCNN 权重（需自行训练）
- `FCNN_BioBERT.pth` — FCNN+BioBERT 权重（需自行训练，已排除）
- `FCNN_TF.pth` — FCNN 权重（需自行训练）

首次运行 `run_cnneo.py` 时自动从 `repo/training_data/training_data.xlsx` 训练，权重保存至 `weights/`。

---

## 4. HLA 格式

| 阶段 | 格式 | 示例 |
|---|---|---|
| 输入 CSV（cnneo_input.csv）| 标准 WHO 格式 | `HLA-A*02:01` |
| 模型内部处理 | 去 * 去空格 | `HLA-A02:01` |
| 用于 k-mer 拼接 | 上述去 * 格式 | `HLA-A02:01` |
| universe.csv 回贴 join key | 标准 WHO 格式 | `HLA-A*02:01` |

转换由 `run_cnneo.py::hla_strip_star()` 完成（镜像 notebook cell-1 三行 str.replace）：
```python
hla.replace("*", "").replace(" ", "").replace("\xa0", "")
```

---

## 5. 肽长支持范围

| 肽长 | 处理方式 | 状态 |
|---|---|---|
| 8-11 mer | 补 X 至 11 chars（trans_Mutated）| ✅ 训练分布内 |
| 12-14 mer | 原样传入（不截断，不补 X）| ⚠️ 轻度 OOD（训练主体 8-11mer），仍处理，分数参考 |
| <8 mer 或 >14 mer | prep_input.py 默认 min=8 / max=14 过滤，不喂模型 | ❌ 过滤 / NaN |

当前 `uniq_pep_hla.csv` 实测分布：8-14mer 均有（8-9mer 最多，8601/9011 行；14mer 6173 行）。

---

## 6. 编码方式

### FCNN_TF（默认）
1. HLA 去 *，拼接 padded 肽（11 chars）
2. 滑窗切 **6-mer**（全小写），空格分隔为文本
3. **TF-IDF**（max_features=1000, smooth_idf=True, use_idf=True）
4. 输入到 FCNN（1000→64→2）
5. softmax[:, 1] = 免疫原性分数

### CNN_BioBERT
1. HLA 去 *，拼接 padded 肽（11 chars）
2. 滑窗切 **4-mer**（全小写），空格分隔为文本
3. **BioBERT** (`dmis-lab/biobert-base-cased-v1.1`) 嵌入，max_length=64
4. last_hidden_state → [N, 64, 768] → **TextCNN**（filters=[3,4,5], num_filters=120）
5. softmax[:, 1] = 免疫原性分数

---

## 7. 安装环境命令

### 推荐：完整 conda 环境（镜像 repo 规范）

```bash
# 首次安装（cnneopp 环境）
conda env create -f repo/environment.yml -n cnneopp
conda activate cnneopp

# CPU-only PyTorch（若 CUDA 安装失败）
pip uninstall -y torch torchvision torchaudio
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cpu
```

### 精简安装（仅 FCNN_TF 子模型，无 BioBERT）

```bash
pip install torch scikit-learn imbalanced-learn pandas openpyxl numpy
```

### CNN_BioBERT 追加依赖

```bash
pip install transformers huggingface-hub tokenizers safetensors
# 首次推理自动下载 dmis-lab/biobert-base-cased-v1.1（~500MB）
# 若 HPC 不联网，需提前在 DTN 节点下载并指定 --cache-dir
```

---

## 8. 运行命令

```bash
# ① 准备输入（全量）
python HPC/deploy/cnneo/prep_input.py

# ② 训练 + 推理（首次自动训练 FCNN_TF，约 5-15 分钟 CPU）
python HPC/deploy/cnneo/run_cnneo.py

# ③ 回贴 universe → 最终结果
python HPC/deploy/cnneo/parse_output.py

# 烟测（5 对快速验格式，--smoke 不影响训练，只截断推理）
python HPC/deploy/cnneo/prep_input.py --smoke 5
python HPC/deploy/cnneo/run_cnneo.py --smoke 5
python HPC/deploy/cnneo/parse_output.py  # 全量 join，NaN 多属正常（烟测只跑了 5 对）

# CNN_BioBERT 子模型（需 transformers 和 BioBERT 下载）
python HPC/deploy/cnneo/run_cnneo.py --model cnn_biobert

# 强制重新训练
python HPC/deploy/cnneo/run_cnneo.py --force-retrain
```

---

## 9. 输出格式

### cnneo_raw_output.csv（run_cnneo.py 产出）

| 列 | 类型 | 说明 |
|---|---|---|
| peptide | str | 原始氨基酸序列（未补 X）|
| hla | str | 标准 HLA-A*02:01 格式 |
| score | float [0,1] | softmax class=1 概率，越高越免疫原 |
| label | int {0,1} | score>0.5 → 1（免疫原）|

### CNNeo_DS1DS2_scores.csv（parse_output.py 产出）

| 列 | 类型 | 说明 |
|---|---|---|
| Dataset | str | DS1 / DS2 |
| Peptide_ID | str | 原始 ID |
| HLA_Allele | str | HLA-A*xx:xx |
| MT_Subpeptide | str | 突变肽序列 |
| MT_CNNeo | float / NaN | MT 侧 CNNeo score |
| WT_CNNeo | float / NaN | WT 侧 CNNeo score（WT 肽不在输入中时为 NaN）|

---

## 10. 分数方向

**越高越免疫原（直接用，无需翻转）。**

- 方向：softmax(class=1) = P(immunogenic)
- 参考：score > 0.5 → 预测免疫原性阳性
- benchmark Spearman：与 ELISpot SFC 直接计算（正相关）

---

## 11. Windows / NTFS 特殊坑

**无 `*` 文件名问题**：repo（AaronChen007/neoantigen）所有文件名均合法，NTFS 可正常 checkout，无需 WSL2 绕行。

其他 Windows 注意：
- 脚本已按 Windows 规范写：`num_workers=0`，`pin_memory=False`，路径用 `pathlib.Path`。
- BioBERT 缓存目录默认 `~/.cache/huggingface/`（Windows = `%USERPROFILE%\.cache\...`），HPC 则在 `$HOME/.cache/...`。
- 若 HPC 不联网：提前在 DTN 节点下载 BioBERT，设 `TRANSFORMERS_CACHE=/path/to/cache`。

---

## 12. 已知坑 / TODO

1. **训练数据列名依赖**：脚本假设 training_data.xlsx 有 `"Mutated Peptide"`, `"HLA type"`, `"label"` 列（与 notebook 一致）。若列名不同脚本会清晰报错。
2. **FCNN_TF TF-IDF vocab 固定**：推理时对 training 外的 k-mer 给 0 权重（正常行为）；12-14mer 肽的 k-mer 若不在词表中预测分数偏保守。
3. **CNN_BioBERT 训练 CPU 慢**：BioBERT 嵌入全训练集需较长时间（CPU ~数小时，GPU ~20-30 分钟）；推荐在 HPC GPU 节点训练一次，然后 HPC 或本地 CPU 推理。
4. **FCNN_BioBERT 已排除**：需 BA/TAP/NetCTLpan/Stability 等列，当前 uniq_pep_hla.csv 无这些特征，不纳入。
5. **SMOTE 过采样**：训练时 imbalanced-learn SMOTE 过采样，需确保 pip install imbalanced-learn。
6. **BioBERT 版本**：CNN_BioBERT 用 `dmis-lab/biobert-base-cased-v1.1`（HuggingFace），FCNN_BioBERT 用 `monologg/biobert_v1.1_pubmed`（两者不同，当前脚本只实现前者）。
7. **TODO（研究员确认）**：训练数据具体肽长分布（是否真为 8-11mer 为主）——打开 training_data.xlsx 核实后更新 NOTES 第 5 节。
