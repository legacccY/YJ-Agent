# deepHLApan 工具交付说明

> 服务项目：QuantImmuBench（癌症个性化新抗原疫苗协作项目）—— 工具部署与 benchmark 交付文档
> 数据红线：本文所有 benchmark 数字逐一溯源 `analysis/metrics_ds2_16tools.csv` 与 `analysis/per_patient_spearman_16tools.csv`，未自创。

---

## 1. 工具简介

- **原理 / 方法**：深度学习模型（3 层双向 GRU / BiGRU + 注意力机制）。**双模型**结构：binding model（预测 pHLA 结合 / 提呈概率）+ immunogenicity model（预测 T 细胞激活的免疫原性）。一次推理同时给出两个分数。仅支持 MHC Class I。
- **特点**：
  - 双任务（结合 + 免疫原性）一次出结果，输入仅需肽段 + HLA，无许可工具依赖。
  - ⚠️ **训练数据含 IEDB（免疫原性 32,785 条，含 ELISpot 阳性）**——与 ELISpot benchmark 测试集存在 overlap 风险，正式评估须排重。
- **论文**：*DeepHLApan: A Deep Learning Approach for Neoantigen Prediction Considering Both HLA-Peptide Binding and Immunogenicity*, Frontiers in Immunology, 2019. DOI: **10.3389/fimmu.2019.02559**（PMID 31736974）
- **代码仓库**：https://github.com/jiujiezz/deephlapan （最新 release v1.1.1，2021-08-10；旧 `zjupgx/deephlapan` 已失效）；web server：http://biopharm.zju.edu.cn/deephlapan/
- **许可证**：**GPL-2.0**（衍生品须同样以 GPL-2.0 开源）。

---

## 2. 输入数据模板 / 格式

- **文件格式**：CSV，必须含 header `Annotation,HLA,peptide`。
- **必填列**：`Annotation`（注释标识）、`HLA`、`peptide`。
- **肽段长度**：8–15 AA。
- **HLA 格式**：⚠️ **`HLA-A01:01`（无星号、连字符直连）**，**不是** `HLA-A*01:01`。本项目转换规则：`master_backbone.HLA_Allele`（`HLA-A*02:01`）→ `str.replace('*', '')` → `HLA-A02:01`。
- **是否需基因组数据**：否（只要肽 + HLA）。
- 也支持单肽单 HLA 命令行：`deephlapan -P <peptide> -H HLA-A02:01`。

**示例（demo/1.csv）**：

```
Annotation,HLA,peptide
sample1,HLA-A02:01,MKRFVQWL
```

---

## 3. 参数设置

- `-F`：输入 CSV 文件
- `-O`：输出目录（⚠️ 必须**先存在**，工具不自建，否则报 `IOError No such file`→ 先 `mkdir -p`）
- `-P` / `-H`：单肽 / 单 HLA 命令行模式
- 模型变体：binding model + immunogenicity model 双输出，无需手动切换（一次同出两分）。

---

## 4. 输出格式及含义

- **输出文件**：`<name>_predicted_result.csv`（+ `<name>_predicted_result_rank.csv`，按 binding 降序加 rank 列）。
- **关键列**：`Annotation,HLA,Peptide,binding score,immunogenic score`。

| 列 | 含义 | 方向 / 范围 |
|---|---|---|
| binding score | pHLA 结合 / 提呈概率 | 0–1，**越高越可能结合** |
| immunogenic score | T 细胞激活免疫原性 | 0–1，**越高越强**；>0.5 = 阳性过滤阈值 |

- 高置信新抗原定义：immunogenicity > 0.5 **且** binding 排名 top 20。
- 示例：`MKRFVQWL  HLA-C07:02  binding=0.9919  immunogenic=0.972`。

---

## 5. 最新 benchmark 结果（DS2 ELISpot）

> 数据集：DS2 ELISpot，101 肽 / 9 患者；IMPROVE 跑通后 16 工具全量重算。主指标为逐患者 Fisher-z，对照口径为全局 Spearman（max 聚合），AUC 取 SFC > 0。
> 数字来源：`analysis/metrics_ds2_16tools.csv`、`analysis/per_patient_spearman_16tools.csv`。
> ⚠️ caveat：deepHLApan 曾发现一处 merge bug（见 04_LOG HLA-FIX）；本表数字以 `metrics_ds2_16tools.csv` 全患者口径为准，P101/P102 等位修正后的复核（corrected-excl）见 `analysis/metrics_ds2_fixed_exclP101P102.csv`。

| 指标 | 数值 |
|---|---|
| n_pep（覆盖肽数） | 101 / 101（全覆盖；9 患者，per-patient n_used=9，n_dropped=0） |
| per-patient Fisher-z 加权 ρ [95% CI]（**主指标**） | **+0.224 [−0.007, +0.433]**（CI 临界跨 0，未达显著） |
| Spearman ρ（max 聚合，对照） | **+0.002**，p = 0.988（不显著） |
| AUC（max，SFC > 0） | 0.445 |

**解读**：全局相关几乎为 0（max ρ +0.002）、AUC（SFC > 0）低于 0.5（0.445）。但 per-patient Fisher-z 加权相关 +0.224、95% CI 下界仅 −0.007（临界），提示其信号更多体现在患者内层面而非全局。须结合 IEDB overlap 与 merge bug caveat 谨慎解读。

---

## 6. 部署环境简述

- **跑的版本**：官方镜像权重，本机 WSL2 docker 烟测 PASS。
- **环境**：官方 Docker 镜像 `biopharm/deephlapan:v1.1`（约 2.44G，内置 Python 2.7 + TensorFlow 1.12，自动绕开 keras 2.0.8 / TF 版本地狱）。CLI 入口 `/usr/local/bin/deephlapan`。推理 CPU 可，训练需旧版 CUDA9 / cuDNN7。
- **关键坑**：① 官方 `requirements.txt` 的 `keras==2.0.8` + `tensorflow==2.7.2` 组合已知不兼容（Issue #9 optimizer 加载报错）→ **推荐走官方 Docker 镜像**绕版本地狱；② `-O` 输出目录必须先 `mkdir -p`；③ HLA 格式无星号 `HLA-A01:01`，喂数据前须转换。
- **仓库 / 部署脚本**：`scripts/deephlapan/`（`deploy_deephlapan_condaA.sh` 路 A / `build_deephlapan_sifB.sh` 路 B / `smoke_deephlapan.sh`）。
- 详细环境配置命令见同目录《环境配置命令_回顾记录.md》。
