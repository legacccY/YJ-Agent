# IEDB Class I Immunogenicity（Calis 2013）— 交付说明文档

> 服务项目：QuantImmuBench（癌症个性化新抗原疫苗协作项目）。本文为对外交付说明，数字均经 CSV 复核。
> 数据真源：`analysis/metrics_ds2_16tools.csv`（全局指标）、`analysis/per_patient_spearman_16tools.csv`（患者分层）。
> 详细部署命令见同目录《环境配置命令_回顾记录.md》。

---

## 1. 工具简介

**IEDB Class I Immunogenicity Predictor v3.0（Calis 等，2013）** 是一个经典的统计型免疫原性打分工具，**不含任何机器学习训练、无权重文件**。

- **原理 / 方法**：依据 HLA I 类呈递肽段在各个位置上氨基酸的 immunogenicity propensity（免疫原性倾向）分值，对各非锚位做线性加权求和；并通过 allele-specific anchor mask 屏蔽 HLA 锚位（如 P1、P2、C 端）的贡献，避免这些位置上的 HLA 结合信号干扰免疫原性估计。propensity 量表来自 IEDB 实验数据的统计汇总，因此整个打分过程完全可解释、每个分数都可逐位追溯到具体氨基酸贡献。
- **特点 / 优势**：
  - 零依赖、纯 Python、CPU 秒级运行（约 65 个 allele 秒级跑完）；
  - 完全可解释，无梯度、无训练；
  - 被 pVACseq、iNeo-Suite 等主流新抗原流水线默认集成，是 class-I 免疫原性领域引用频次最高的经典基准——任何新工具若不能显著超过它，即可判为无实质进步。
- **局限**：不考虑 TCR 识别概率、蛋白酶处理与 TAP 转运效率，仅基于氨基酸理化性质；对不在支持列表内的 allele 回退到默认 mask，会丢失锚位特异性；输出无硬边界（非 0-1 概率），跨工具比较时需注意单位不一致。
- **论文 DOI**：10.1371/journal.pcbi.1003266（*Properties of MHC Class I Presented Peptides That Enhance Immunogenicity*，2013，PLOS Computational Biology）。
- **下载 / repo**：https://downloads.iedb.org/tools/immunogenicity/LATEST/IEDB_Immunogenicity-3.0.tar.gz
- **许可证**：**NPOSL-3.0（开源，学术 / 商业均可，跑出的 benchmark 数字可自由发布，不触发任何第三方再分发限制）**。

---

## 2. 输入数据模板 / 格式

- **文件格式**：纯文本 `.txt`，每行一条肽序列（大写标准 20 种氨基酸），**无表头、无 HLA 列**。
- **调用粒度**：工具每次调用只处理一个 HLA allele；本 benchmark 按 `HLA_Allele` 分组，每组生成一个 txt 文件（`prep_input.py` 自动生成约 65 个）。
- **HLA 格式**：通过命令行 `--allele` 参数传入，格式为「去 `*` 去 `:`」，例如 `HLA-A*02:01 → HLA-A0201`。
- **肽段长度**：无硬限制，9-mer 最优（position weight 向量长 9）；8-mer 及 10-mer 以上均有 C 端调整规则，本 benchmark 8–15mer 全部可打分，不因肽长产生 NaN。
- **是否需基因组数据 / 野生型肽**：均不需要（MT、WT 用同一 allele 分别打分即可）。
- **输入样例**：
  ```
  FIAGLIAIV
  LITGRLQSL
  NLVPMVATV
  ```
  （文件名如 `HLA-A0201.txt`，对应 `--allele=HLA-A0201`）

**支持 allele**：42 个使用 allele-specific anchor mask（含 6 个小鼠 H-2 与 36 个 HLA-A/B 亚型）；其余 allele（含全部 HLA-C 及部分 A/B 亚型）回退到默认 mask（P1、P2、C 端），不反映该 allele 锚位特异性，须在报告中标注此 caveat。

---

## 3. 参数设置

| 参数 | 说明 |
|---|---|
| `--allele=HLA-A0201` | 指定 allele（去 `*` 去 `:`），使用 allele-specific mask |
| `--custom_mask=2,3,9` | 自定义 mask 位置（本 benchmark 不使用） |
| `--allele_list` | 打印全部 42 个支持 allele |
| 不加 `--allele` | 回退默认 mask（P1、P2、C 端） |

典型命令行：

```bash
# 有 allele 支持：使用 allele-specific mask
python predict_immunogenicity.py --allele=HLA-A0201 HLA-A0201.txt
# 不在支持列表：回退默认 mask
python predict_immunogenicity.py HLA-B4601.txt
```

---

## 4. 输出格式及含义

stdout 为 CSV 片段，按 score 降序排列：

```
allele: HLA-A0201
masking: custom
masked variables: [1, 2, 9]

peptide,length,score
FIAGLIAIV,9,0.45678
LITGRLQSL,9,0.23456
```

最终汇总产物 `IEDB_Calis_DS1DS2_scores.csv` 关键列：

| 列 | 含义 |
|---|---|
| `Dataset` | DS1 / DS2 |
| `Peptide_ID` | 原始 ID |
| `HLA_Allele` | HLA-A\*xx:xx |
| `MT_Subpeptide` | 突变肽序列 |
| `MT_IEDB_Calis` | MT 侧免疫原性分数 |
| `WT_IEDB_Calis` | WT 侧免疫原性分数 |

- **分数类型**：连续、无硬边界的线性分（通常落在约 −1.5 ~ +1.5）。
- **分数方向**：**越高越免疫原，直接使用，无需翻转**，方向与 benchmark 内其他工具一致。
- **能否定量免疫强弱**：可以（连续分，可排名），契合项目「强弱定量」核心目标。
- **覆盖率**：实测产物 34247 行、**0 NaN**（工具对所有肽长均有输出，不支持 allele 用默认 mask 仍给分）。

---

## 5. 最新 benchmark 结果（DS2 ELISpot）

> 以下为 IMPROVE 跑通后全量重算结果（P101 / P102 已用修正后 HLA 等位恢复，n_pep=101）。Spearman 用纯 numpy 实现、p-value 经 betainc 计算；患者分层用 Fisher-z 加权聚合并给 95% 区间。netMHCpan 限制不适用本工具，所有数字可自由发布。

| 指标 | 数值 |
|---|---|
| n_pep（DS2 唯一肽） | 101 |
| 患者分层 Fisher-z（加权，**主指标**） | **+0.112**，95% CI [−0.121, +0.334]（9 名患者） |
| Spearman ρ（max 聚合，对照） | **+0.096**（p = 0.339，n.s.） |
| AUC（max，SFC > 0） | **0.528** |
| 覆盖率 | 100%（34247 行 0 NaN） |

**解读**：IEDB_Calis 作为 2013 年的历史统计基准，全局与患者内方向均为正、但量级很小且统计不显著，AUC（SFC > 0）接近随机线（0.528）。这条线正是衡量现代深度学习工具是否真有进步的「及格线」。

---

## 6. 部署环境简述

- 工具：IEDB_Immunogenicity-3.0（纯 Python 3，约 4KB 脚本，无 ML 框架依赖）。
- 运行平台：本地 Windows 即可，纯统计、CPU 秒级、约 65 个 allele 全量打分。
- GPU 需求：无。外部许可证工具：无。
- 部署状态：✅ RUN_DONE（全量跑通）。
- 部署文件：`HPC/deploy/iedb_calis/`（`prep_input.py` / `run_iedb_calis.sh` / `parse_output.py` / `NOTES.md`）。
- 详细安装与运行命令见同目录《环境配置命令_回顾记录.md》。
