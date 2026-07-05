# DeepHLApan 工具交付说明

> 项目：Rerun v2 — 5 工具 × 130 肽 × 三层次评估
> 数据红线：本文所有 benchmark 数字精确溯源 HPC 评估输出，未自创。

---

## 1. 工具简介

- **原理 / 方法**：基于 BiGRU + Attention 机制的深度学习模型，整合肽段序列与 HLA 等位基因信息，同时预测 pMHC-I 结合亲和力（binding）和免疫原性（immunogenicity）。使用大规模质谱（MS）免疫肽组数据训练。
- **特点**：
  - 双输出：binding score + immunogenicity score
  - 注意力机制提供一定可解释性（关键残基权重）
  - Docker 镜像分发（biopharm/deephlapan:v1.1），避版本地狱
- **论文**：*DeepHLApan: A Deep Learning Approach for Neoantigen Prediction Considering Both HLA-Peptide Binding and Immunogenicity*, Frontiers in Immunology, 2019. DOI: **10.3389/fimmu.2019.02559**
- **代码仓库**：https://github.com/jiujiezz/deephlapan
- **许可证**：GPL-2.0

---

## 2. 输入数据模板 / 格式

- **文件格式**：CSV，含表头
- **必填列**：`HLA_type` + `MT_pep`（或 `peptide`）
- **HLA 格式**：**`HLA-A02:01`**（无星号，连字符直连，**不是** `HLA-A*02:01`）
- **肽段长度**：8–14 AA
- **是否需基因组数据**：否

**输入示例**（`DeepHLApan_dataset2_MT.csv`）：
```
MT_pep,HLA_type
SLLMWITQV,HLA-A02:01
ALPPTVYEV,HLA-A02:01
...
```

---

## 3. 参数设置

| 参数 | 说明 | 本项目用值 |
|---|---|---|
| `-F` | 输入 CSV 文件 | `DeepHLApan_dataset2_MT.csv` / `..._WT.csv` |
| `-O` | 输出目录 | `outputs/dataset2_MT/` / `outputs/dataset2_WT/` |
| 模型 | 容器内固化 dual-head 模型 | 默认（binding + immunogenicity 双输出） |

**完整命令**（SIF 模式）：
```bash
deephlapan -F DeepHLApan_dataset2_MT.csv -O outputs/dataset2_MT
```

---

## 4. 输出格式及含义

- **输出文件**：`<输入文件名>_predicted_result.csv`（CSV）
- **关键列**：

| 列 | 含义 | 方向 / 范围 |
|---|---|---|
| peptide | 肽段序列 | — |
| HLA_type | HLA 等位 | — |
| binding_score | pMHC-I 结合亲和力预测分 | 越高结合越强 |
| immunogenity_score | 免疫原性预测分 | 越高越免疫原（**本评估用**） |

- **⚠️ 分数方向疑点（已调查 2026-06-30）**：评估发现 DeepHLApan 全局 ρ = **−0.129**（弱负相关），但经排查**不是方向反转**，而是 immunogenic_score 极度聚集在 0.97 附近（范围 0.75-0.998），方差极小，等同于随机。模型在 DS2（肾癌新抗原）上基本无区分力——几乎所有肽都判为"高免疫原性"。这与模型训练数据（IEDB 已知免疫原性表位）的分布差异有关。

---

## 5. 最新 benchmark 结果（DS2 ELISpot，130 肽）

> 数据集：DS2 In Vitro ELISpot，130 肽 / 9 患者。主指标为逐患者 Fisher-Z 加权 Spearman。

| 指标 | 数值 |
|---|---|
| n_pep（覆盖肽数） | 130 / 130（全覆盖） |
| per-patient Fisher-Z 加权 ρ [95% CI]（**主指标**） | **+0.009 [−0.182, +0.200]**（CI 跨 0，**不显著**） |
| Spearman ρ（max 聚合，对照） | **−0.129**（p = 0.144，不显著，反方向） |
| AUC（max，SFC > 0） | 0.404 |

**解读**：5 工具中表现最弱。Fisher-Z 接近 0，全局 ρ 为负（但均不显著）。可能与下列因素有关：① 分数方向疑点（见 §4）；② DS2 数据与训练数据分布差异大；③ 容器镜像较老（v1.1，论文发表后未更新）。

---

## 6. 部署环境与已知问题

- **跑的版本**：`biopharm/deephlapan:v1.1` Docker → Singularity SIF（路 B；路 A conda 版因 keras==2.0.8 + tf==2.7.2 ABI 不兼容放弃）
- **环境**：HPC Singularity 3.11.3。CPU 推理，轻量模型。
- **HPC Job**：1503135（4h，8 CPU，32G RAM，short partition）
- **SIF 位置**：`/gpfs/work/bio/zichenli24/tools/deephlapan.sif`
- **关键坑**：
  - **HLA 格式**：`HLA-A02:01`（无星号，连字符直连），与其他工具格式不同 → 输入构造须转换
  - **版本地狱**：conda 直装（路 A）因 `keras==2.0.8`（2017）与 `tensorflow==2.7.2` ABI 不兼容 → 走 Singularity 容器（路 B）
  - **分数方向疑点**：immunogenity_score 与 ELISpot 负相关 → 须排查；建议读源码 `/pred/immunogenecity.py` 确认输出层激活函数与标签定义
  - outdir 须先建（容器内不会自动 mkdir）
