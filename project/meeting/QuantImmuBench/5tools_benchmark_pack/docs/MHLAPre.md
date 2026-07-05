# MHLAPre 工具交付说明

> 项目：Rerun v2 — 5 工具 × 130 肽 × 三层次评估
> 数据红线：本文所有 benchmark 数字精确溯源 HPC 评估输出，未自创。

> ⚠️ **重要标注（先读）**：MHLAPre 本次评估使用 DS2 数据同时训练和预测（无 GroupKFold 患者级交叉验证），导致 AUC = 0.997 是**数据泄露产物**，Fisher-Z 也相应的被高估。本文所有数字 **标 ⚠️ 仅供内部参考**，不可对外发布。真实性能需 GroupKFold（按 Patient 分组）重新校验。

---

## 1. 工具简介

- **原理 / 方法**：基于 TextCNN 的深度学习框架，预测新抗原 pMHC-I 结合与免疫原性。整合 HLA 序列编码 + 肽段氨基酸特征 + 位置权重矩阵（PWM）。模型约 300K 参数，是 5 工具中最小型、训练最快的。
- **特点**：
  - 轻量 TextCNN 架构（~300K params），CPU 可训（51K 训练样本需 1-3h）
  - 支持 HLA-I/II + 多种肽长
  - 源码公开，PyTorch 实现，无 DTU 依赖
- **论文**：Xu et al., *MHLAPre: A multi-task deep learning framework for predicting peptide-MHC binding and neoantigen immunogenicity*, Briefings in Bioinformatics, 2023
- **代码仓库**：https://github.com/.../MHLAPre
- **许可证**：开源

---

## 2. 输入数据模板 / 格式

- **文件格式**：CSV，带表头。
- **训练输入列**：`peptide`（肽段序列）、`HLA`（HLA 等位基因）、`label`（0/1 二分类标签）、`patient`（患者 ID）
- **预测输入列**：`peptide`、`allele`、`patient`
- **HLA 格式**：**`HLA-A02:01`**（无星号，冒号连字符）
- **肽段长度**：8/9/10/11-mer（滑动窗口展开自长肽）

**输入示例**（`dataset2_MT.csv`，训练）：
```
peptide,HLA,label,patient
SLLMWITQV,HLA-A02:01,1,P101
ALPPTVYEV,HLA-A02:01,0,P101
...
```
**输入示例**（`dataset2_MT_predict.csv`，预测）：
```
peptide,allele,patient
SLLMWITQV,HLA-A02:01,P101
...
```

---

## 3. 参数设置

| 参数 | 说明 | 本项目用值 |
|---|---|---|
| `--mode` | 运行模式（train/predict） | 先 train 后 predict（两阶段） |
| `--data_dir` | 数据根目录 | `/gpfs/work/bio/zichenli24/rerun_v2` |
| `--output_dir` | 输出目录 | `outputs/` |
| `--model_dir` | 模型保存/加载目录 | `models/` |
| `--epochs` | 训练轮数 | 30 |
| `--batch_size` | 批次大小 | 128 |
| `--device` | 计算设备 | **cpu**（GPU 因 CUDA 版本不兼容不可用） |

**完整命令**：
```bash
conda activate mhlapre
cd /gpfs/work/bio/zichenli24/tools/MHLAPre/

# 训练
python train_predict.py --mode train --data_dir /gpfs/work/bio/zichenli24/rerun_v2 \
    --output_dir outputs/ --model_dir models/ --epochs 30 --batch_size 128 --device cpu

# 预测
python train_predict.py --mode predict --data_dir /gpfs/work/bio/zichenli24/rerun_v2 \
    --output_dir outputs/ --model_dir models/ --device cpu
```

---

## 4. 输出格式及含义

- **输出文件**：4 个预测 CSV（MT/WT × DS1/DS2）
- **关键列**：

| 列 | 含义 | 方向 / 范围 |
|---|---|---|
| peptide | 肽段序列 | — |
| allele | HLA 等位 | — |
| patient | 患者 ID | — |
| prediction_score | TextCNN 免疫原性预测分 | **越高越免疫原**，0–1 |

- **聚合方式**：取 max 跨 allele × 子肽 → 每 Peptide_ID 一条
- **输出量**：
  - DS2 MT：25,470 行（mean score = 0.69）
  - DS2 WT：20,496 行（mean score = 0.25）
  - DS1 MT：321 行
  - DS1 WT：321 行

---

## 5. 最新 benchmark 结果（DS2 ELISpot，130 肽）⚠️

> ⚠️ **数据泄露 warning**：MHLAPre 在 DS2 数据上训练然后预测同一批数据。AUC = 0.997 是 **train-on-test 泄露**的典型信号。以下所有数字高估，不可对外使用。真实性能须 GroupKFold CV 校正。

| 指标 | 数值 |
|---|---|
| n_pep（覆盖肽数） | 130 / 130（全覆盖） |
| per-patient Fisher-Z 加权 ρ [95% CI]（**主指标**）⚠️ | **+0.224 [+0.034, +0.397]**（CI 不含 0，**显著**，但高估） |
| Spearman ρ（max 聚合，对照）⚠️ | **+0.264**（p = 0.002，**显著**，但高估） |
| AUC（max，SFC > 0）⚠️ | **0.997**（异常高 → 数据泄露确认） |

**解读（已更新 2026-06-30 GroupKFold CV 后）**：上表 ⚠️ 值为 train-on-test 泄露产物。

---

### GroupKFold CV 真实表现（Leave-One-Patient-Out, 9 folds）

| 指标 | 泄露值（旧） | **CV 真实值（新）** |
|------|-------------|---------------------|
| AUC (SFC>0) | 0.997 ⚠️ | **0.530 ± 0.057** |
| Global Spearman ρ | +0.264 (p=0.002) | **+0.052** (p≈0, 但 51K 样本下虚低) |
| Fisher-Z weighted ρ | +0.224 [0.034, 0.397] | **+0.039 [0.030, 0.048]** |
| Average Precision | — | **0.538** |

**结论**：TextCNN (BLOSUM50) 架构在 DS2 上经过严格的 GroupKFold 评估后，AUC 仅 0.53（接近随机 0.5），Spearman ρ ≈ 0.04（几乎无相关）。原始 0.997/0.264 完全是数据泄露产物。MHLAPre 的 TextCNN 模型对该任务**基本无预测力**。

---

## 6. 部署环境与已知问题

- **跑的版本**：自训版（DS2 数据训练 30 epochs），非官方预训练权重
- **环境**：HPC conda env `mhlapre`（Python + PyTorch 1.12.1+cu102）
- **HPC Job**：1503158（4h，4 CPU，16G RAM，**gpu4090 partition** — 但实际 `--device cpu` 跑）
- **仓库位置**：`/gpfs/work/bio/zichenli24/tools/MHLAPre`
- **关键坑**：
  - **CUDA 不兼容（致命）**：mhlapre env 的 PyTorch 1.12.1+cu102 只支持到 sm_75（RTX 2080 Ti / TITAN RTX），RTX 4090 是 sm_89 → `CUDA error: no kernel image is available for execution on the device`。**Fix**：`--device cpu`（模型仅 300K 参数，CPU 1-3h 可完成）
  - **PyTorch 升级不可行**：HPC GPU 节点无外网，`pip install torch==2.x` 必须下载 CUDA 12.x 依赖，且可能破坏 env 内其他包的依赖
  - **数据泄露问题**：train_predict.py 默认随机切分，不按患者分组 → 同一患者的不同子肽可能落入 train 和 test → 信息泄露。修复方案：实现 GroupKFold by Patient ID
