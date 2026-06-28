# ImmuneApp 工具交付说明

> 服务项目：QuantImmuBench（癌症个性化新抗原疫苗协作项目）—— 工具部署与 benchmark 交付文档
> 数据红线：本文所有 benchmark 数字逐一溯源 `analysis/metrics_ds2_16tools.csv` 与 `analysis/per_patient_spearman_16tools.csv`，未自创。

---

## 1. 工具简介

- **原理 / 方法**：基于注意力机制的 CNN-LSTM 混合框架，用于 HLA-I 表位预测与免疫肽组分析。框架含多个模块，本项目使用其中的 **ImmuneApp-Neo 免疫原性预测模块**（迁移学习）。注意力层可识别关键结合残基（具一定可解释性）。仅支持 HLA Class I。
- **特点**：
  - HLA-I 提呈预测达 SOTA 水平（论文报告 PPV 0.3720 vs NetMHCpan-4.1 的 0.3313）；Neo 模块称 PPV 较现有方法提升约 2.1 倍。
  - 预训练权重随仓库发布，**MIT 许可无障碍**，**无 netMHCpan / DTU 依赖**，支持 10000+ MHC 等位。
- **论文**：*ImmuneApp for HLA-I epitope prediction and immunopeptidome analysis*, Nature Communications, 2024. DOI: **10.1038/s41467-024-53296-0**
- **代码仓库**：https://github.com/bsml320/ImmuneApp ；web server：https://bioinfo.uth.edu/iapp/
- **许可证**：**MIT**（自由使用 / 修改 / 分发）。

---

## 2. 输入数据模板 / 格式

- **文件格式（ImmuneApp-Neo）**：纯肽段文本（每行一条，无 header）+ 命令行 `-a` 指定 HLA。
- **必填字段**：肽段序列 + HLA 等位。
- **肽段长度**：8–15 AA（脚本 `read_peplist()` 硬性校验，仅接受 20 种标准氨基酸）。
- **HLA 格式**：标准命名 `HLA-A*01:01`（`-a` 后接多个，空格分隔）。
- **是否需基因组数据**：否。

**命令示例**：
```
python ImmuneApp_immunogenicity_prediction.py \
  -f testdata/test_immunogenicity.txt \
  -a 'HLA-A*01:01' 'HLA-A*02:01' 'HLA-B*07:02' \
  -o results
```

---

## 3. 参数设置

- `-f`：肽段文件
- `-a`：HLA 等位列表（空格分隔，标准 `HLA-A*01:01` 格式）
- `-o`：输出目录
- 模型变体：ImmuneApp-BA（结合亲和力）/ -EL（洗脱配体）/ -AP（提呈）/ -MA（复合）/ **-Neo（免疫原性，本项目用）**

---

## 4. 输出格式及含义

- **输出文件**：`ImmuneApp_Immunogenicity_predictions.tsv`（文件名固定；`-o` 指定的是目录）。
- **关键列**：`Allele` / `Peptide` / `Sample` / `Immunogenicity_score`。
- **方向 / 范围**：`Immunogenicity_score` 连续，0–1（sigmoid 约束）；**越高越免疫原**。无内置阈值过滤，所有肽均出分。
- **粒度**：每肽 × 每 allele 各一行（多 allele 时逐 allele 展开，为 per-allele 格式）。
- 示例：`HLA-A*01:01  CILGKLFTKK  0.99997`、`HLA-A*01:01  ALPPTVYEV  0.00068`。

---

## 5. 最新 benchmark 结果（DS2 ELISpot）

> 数据集：DS2 ELISpot，101 肽 / 9 患者；IMPROVE 跑通后 16 工具全量重算。主指标为逐患者 Fisher-z，对照口径为全局 Spearman（max 聚合），AUC 取 SFC > 0。
> 数字来源：`analysis/metrics_ds2_16tools.csv`、`analysis/per_patient_spearman_16tools.csv`。

| 指标 | 数值 |
|---|---|
| n_pep（覆盖肽数） | 101 / 101（全覆盖；9 患者，per-patient n_used=9，n_dropped=0） |
| per-patient Fisher-z 加权 ρ [95% CI]（**主指标**） | **+0.157 [−0.076, +0.374]**（CI 跨 0，不显著） |
| Spearman ρ（max 聚合，对照） | **+0.079**，p = 0.433（不显著） |
| AUC（max，SFC > 0） | 0.591 |

**解读**：全局相关为弱正、统计不显著（max ρ +0.079）；per-patient Fisher-z 加权相关 +0.157 但 95% CI 跨 0，未达显著。AUC（SFC > 0）= 0.591 优于近随机。整体方向正确但强度有限。

---

## 6. 部署环境简述

- **跑的版本**：官方权重（随仓库 `models/immunogenicity/model_immunogenicity.{json,h5}`），HPC 烟测 PASS。
- **环境**：HPC conda env `envs/immuneapp`，**严格 Python 3.7**（TF 1.15 仅有 3.6/3.7 官方 wheel）+ TensorFlow 1.15.0 + Keras 2.3.1（standalone）+ numpy 1.18.5 + h5py 2.10.0 + protobuf 3.20。CPU 推理可用，无需 GPU。
- **关键坑**：① TF1.15 依赖栈一次性 `pip install` 会触发依赖回溯死循环——须**先单装 `tensorflow==1.15` 再装其余**；② h5py 必须 2.10.0、protobuf 必须 3.20（高版本 API 不兼容，加载权重报错）；③ 运行前须 `cd` 到 repo 根目录（权重用相对路径加载）。
- **仓库位置**：`~/quantimmu/tools_repos/ImmuneApp`（经 GitHub tarball 下载，约 1.2G）。
- 详细环境配置命令见同目录《环境配置命令_回顾记录.md》。
