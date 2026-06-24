# DS1 定量 magnitude 排序分析

> 服务 quantimmu-bench / 袁 QuantImmune。analyst(opus) 本地 Bash+scipy 实算，2026-06-24。判据=工具能否给出连续 magnitude 排序。

## 数据可用性确认（Bash 实查）
| 项 | 结果 |
|---|---|
| DS1 原始 | 82 肽 9mer，有 ELISpot SFC | `data/Elispot_Dataset1.xlsx` sheet All_Peptides |
| DS1 有无工具输出 | **有，8 工具都跑过 DS1** | merged_all_tools_8tools.xlsx DS1 子集 325 行 |
| 非空率(325 行) | DeepImmuno/PredIG/IMPROVE/NeoTImmuML/pTuneos/PRIME/ImmuneApp=325/325；deepHLApan 321；NOAH 229；NetCleave 0(排除) |

DS1 结构：325 行=82 肽×每肽 2-6 HLA(中位 4)，6 病人 18 HLA。**SFC 是 per-peptide**(同肽多 HLA 行 SFC 相同)→ 相关性必须聚合到肽级(82 肽)算。
DS1 SFC：全阳(min 16，无≤0，**无阴性对照→算不了 AUC**)，range 16-677，中位 131，均值 200.6。magnitude 跨 40 倍适合测排序。

## DS1 肽级 magnitude 排序能力（best-binder, n=82 肽）
| 工具 | Spearman ρ | p | 判定 |
|---|---|---|---|
| NOAH | 0.073 | 0.512 | ≈随机 |
| ImmuneApp | 0.039 | 0.729 | ≈随机 |
| PredIG | 0.028 | 0.804 | ≈随机 |
| IMPROVE | 0.007 | 0.953 | ≈随机 |
| pTuneos | −0.022 | 0.844 | ≈随机 |
| DeepImmuno | −0.028 | 0.803 | ≈随机 |
| PRIME | −0.123 | 0.270 | 弱反向 n.s. |
| NeoTImmuML | −0.157 | 0.159 | 弱反向 n.s. |
| **deepHLApan** | **−0.503** | **0.0000** | **显著反向 ❌(待 verifier 核极性)** |

源：merged_all_tools_8tools.xlsx 各 MT_<tool> vs Elispot。落表 `analysis/ds1_magnitude_spearman_bestbinder.csv`(+_mean.csv 结论一致)。

对照 DS2(metrics_ds2.csv)：IMPROVE top3mean ρ=0.32(p=0.001)、PredIG mean ρ=0.28(p=0.005) —— DS2 头部工具能正向显著排 SFC。

## 关键发现
- **DS1 全阳子集上没有任何工具能排 SFC 强弱**：8/9 工具 |ρ|<0.16 p 全不显著(≈随机)。唯一显著的 deepHLApan ρ=−0.50 是**反向**(负贡献非能力，待 verifier 核分数极性语义)。
- **同批工具 DS2 能排、DS1 不能排** = 干净对照(`figures/ds1_vs_ds2_spearman_bar.png`)。差异源于 **DS1 是全阳窄子集**：工具判别力主要在「阳 vs 阴」门槛上，全阳后失去区分力，「阳性内部谁更强」工具基本不会。
- **正面回应袁 QuantImmune**：现有工具是**分类器不是定量回归器**——能粗分有无，预测连续 SFC magnitude 在已确认阳性肽集合里 ≈ 0。benchmark 一个可写进报告的硬结论(诚实负结果)。

## 风险/下一步
- deepHLApan ρ=−0.50 反向：真实计算(列 321/325 非空有方差非 bug)，但极反常，**交 verifier 核分数极性**再决定报告写法，不下 bug 终判。
- 样本量 n=82 小(6 病人全 9mer)，结论统计稳(p 都大不边界)但标注 n=82。
- 建议把 **DS2(有阴性+SFC 连续跨度大)定 magnitude 主验证集，DS1 作全阳极端对照**并列报告——「连阳性内部都排不出来」比「整体能排」更凸显工具局限。
- 救信号可试 DS2 上 Top-K 富集/分位回归(`analysis/metrics_topk.py`)，看头部高 SFC 肽是否更易排上去。

## 产物
- 图 `figures/ds1_magnitude_scatter_bestbinder.png`、`figures/ds1_vs_ds2_spearman_bar.png`
- csv `analysis/ds1_magnitude_spearman_bestbinder.csv`、`analysis/ds1_magnitude_spearman_mean.csv`
