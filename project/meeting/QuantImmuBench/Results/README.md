# QuantImmuBench 工具部署与测试交付包

> 子任务交付：在 HPC / 本地部署并测试新抗原免疫原性预测工具，收集每个工具的 4 类信息（输入模板 / 参数设置 / 输出格式含义 / 工具简介），并在 DS2 ELISpot 数据集上做横向 benchmark。
>
> **更新日期：2026-06-28**（IMPROVE 工具跑通后全量重算，14 个工具全部恢复患者 P101/P102 数据，n_pep 86→101）。

---

## 一、交付内容

| 子目录 / 文件 | 内容 |
|---|---|
| `docs/` | **16 个工具的说明文档**，每个一份 md，含 6 部分：① 工具简介（原理 / 特点 / 论文 DOI / repo / 许可）② 输入数据模板 ③ 参数设置 ④ 输出格式及含义 ⑤ 最新 DS2 ELISpot benchmark 结果 ⑥ 部署环境简述 |
| `data_tables/` | **16 个工具的数据表 xlsx**，每个一张：backbone（患者 / 肽 / 等位等 17 列）+ 该工具原生输出列 + 第二 sheet「列说明」。数据为 IMPROVE 跑通后的最新结果 |
| `环境配置命令.md` | **16 个工具的真实部署命令回顾**（clone / 建环境 / 权重下载 / 烟测 / 正式跑），逐条标来源脚本，可照着复现 |

数据真源：`../analysis/metrics_ds2_16tools.csv`（全局指标）+ `../analysis/per_patient_spearman_16tools.csv`（患者内指标）。

---

## 二、16 个工具横评总表（DS2 ELISpot，n_pep=101）

> **主指标 = 患者内 Fisher-Z 加权 Spearman**（先在每位患者内部算相关、再跨患者聚合，计入患者间差异，方法学最严谨）；**全局 Spearman** = 所有患者肽混合后算（作对照）；AUC = 有无免疫原性二分类判别力。方向统一「分数越高越免疫原」。下表按主指标（患者内 Fisher-Z）降序。

| 工具 | 患者内 Fisher-Z [95%CI]（主） | 全局 Spearman ρ (p)（对照） | AUC(SFC>0) | 许可 | 备注 |
|---|---|---|---|---|---|
| **PRIME** | **+0.279 [+0.050, +0.481]** ✅显著 | +0.158 (0.114) | 0.517 | 学术免费 | 患者内最强；配 MixMHCpred |
| **IMPROVE** | **+0.250 [+0.021, +0.455]** ✅显著 | +0.252 (0.011) ✅ | 0.616 | 见 repo | RF 集成；患者内+全局双显著 |
| PredIG | +0.229 [−0.003, +0.437] | +0.201 (0.044) ✅ | 0.663 | 见 repo | 全局显著；原生特征最全 |
| deepHLApan | +0.224 [−0.007, +0.433] | +0.002 (0.988) | 0.445 | 见 repo | HLA 格式无星号 |
| MHCflurry(亲和力) | +0.203 [−0.028, +0.413] | +0.128 (0.202) | 0.476 | Apache-2.0 | 提呈分另为 +0.124 |
| ImmuneApp | +0.157 [−0.076, +0.374] | +0.079 (0.433) | 0.591 | 见 repo | TF1.15 老环境 |
| netMHCpan-BA | +0.155 [−0.079, +0.373] | +0.090 (0.370) | 0.468 | 🔴 DTU 学术许可 | 数字未经 DTU 书面同意禁对第三方发布 |
| pTuneos | +0.121 [−0.112, +0.341] | +0.119 (0.237) | 0.718 | 见 repo | Pre&RecNeo 子模型；AUC 最高 |
| Repitope | +0.119 [−0.112, +0.338] | +0.084 (0.406) | 0.620 | MIT | HLA-agnostic（同肽各等位同分） |
| IEDB_Calis | +0.112 [−0.120, +0.334] | +0.096 (0.339) | 0.528 | NPOSL-3.0 自由 | 纯统计模型 |
| NeoTImmuML | +0.033 [−0.194, +0.256] | +0.022 (0.829) | 0.655 | 见 repo | ★自训复刻版（官方权重不可得），HLA-agnostic |
| DeepImmuno | +0.015 [−0.213, +0.242] | −0.089 (0.376) | 0.469 | 见 repo | CNN，仅 9-10mer 覆盖低 |
| TSCAPE | +0.001 [−0.226, +0.227] | −0.139 (0.167) | 0.442 | CC BY-NC-ND 4.0 | 患者内≈0、全局负但均不显著 |
| HLAthena | −0.011 [−0.249, +0.228] | +0.091 (0.390) | 0.415 | 见 repo | n=92（8 患者）；⚠️ 提呈 proxy，非免疫原性工具，近随机 |
| BigMHC | −0.014 [−0.241, +0.215] | −0.041 (0.684) | 0.499 | 学术非商用 | im 模式 7 模型 ensemble |
| CNNeo | −0.204 [−0.413, +0.026] | +0.085 (0.396) | 0.398 | MIT | |

> AUC 口径 = **SFC>0**（有无免疫反应二分类，90 阳/11 阴），与配套 PPT 一致；连续强度定量以左侧 Fisher-Z / Spearman 为准。

> ✅显著 = 95% 置信区间不含 0（患者内主指标）/ p<0.05（全局对照）。逐工具详细数字（含 top3mean 等其它聚合）见 `docs/<工具>.md`。

**总体结论**：现有工具对「免疫强度连续定量」普遍弱相关（患者内 Fisher-Z 无一 >0.30）。按最严谨的患者内口径，**PRIME（+0.279）和 IMPROVE（+0.250）是仅有的两个显著正相关工具**（95%CI 排 0）；全局对照口径下 IMPROVE（p=0.011）与 PredIG（p=0.044）显著。无任何工具达到强相关 —— 这正是 QuantImmune 立项要填补的空白。

---

## 三、数据表形式（`data_tables/`）

每张 xlsx：
- **Sheet1**：backbone 17 列（`bb_idx, Dataset, Patient_ID, Peptide_ID, Gene_Name, Mutation, MT_FullPeptide, WT_FullPeptide, Peptide_Length, Elispot, Window_Size, Position, MT_Subpeptide, WT_Subpeptide, HLA_Allele, Ref_UniProt_ID, Peptide_Position`）+ 该工具原生输出列（行对行，含 bb_idx 主键可溯源）
- **Sheet2「列说明」**：每个工具列的含义、方向、覆盖率、caveat

源 = `../scripts/out/merged_all_tools_16tools.xlsx`（IMPROVE 跑通后全量重算，已含患者 P101/P102）。生成脚本 `../scripts/build_alltools_delivery.py`。

---

## 四、重要 caveat（诚实标注）

- **HLAthena** = 提呈（presentation）预测工具，不预测免疫原性，benchmark 近随机（AUC ~0.57），仅作 presentation proxy 单列，不与免疫原性工具直接并列比较。
- **NeoTImmuML** = 官方权重不可得，用自训复刻版（RF+LGB+XGB），标 ★，不对标原论文数字；HLA-agnostic（同肽各等位同分）。
- **IMPROVE** = Simple 模型，Expression 特征降级、Stability 特征插补（与原 86 肽口径严格一致）。
- **pTuneos** = Pre&RecNeo 子模型。
- **许可红线**：`netMHCpan-BA`（DTU 学术许可）的 benchmark 数字未经 DTU 书面同意不得对第三方发布；`TSCAPE`（CC BY-NC-ND 4.0）仅限学术非商用。投稿 / 对外发布前需处理。
- 患者 P101/P102 曾因 Excel 拖拽填充产生 HLA 等位伪迹，已于 2026-06-27 查清根因并统一修复（正确等位 P101={A\*66:01,B\*40:01,B\*57:01,C\*06:02}、P102={A\*02:01,B\*35:03,B\*38:01}），当前数据已是订正后的正确版本。详见 `../04_LOG.md`。
