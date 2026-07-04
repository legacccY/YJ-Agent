# 文献支撑：结合/呈递工具 ≥ 免疫原性专用工具（QuantImmuBench 核心发现的先例与定位）

> 建档 2026-07-04。服务 §3.1 headline + Discussion。**用途**：写 tex 时直接调这份的引用 + 现成句子；证明「结合工具打赢免疫原工具」不是数据错、是已知现象，卖点在「系统化 + 新数据 + 方法严谨」而非新机制。researcher 多源交叉核实（Cell/BiB/NAR Cancer/Frontiers），存疑处标 TODO。

## 0. 本项目的发现（DS2，Braun 2025 ELISPOT，9 患者/130 肽）
- 单工具预测免疫原性 per-patient Spearman（控肽长/Fisher-z/effN≥8）：**前三名 MHCnuggets 0.447 / netMHCpan_BA 0.392 / MHCflurry 0.308 全是 MHC 结合预测器**，打赢所有专门免疫原性工具（PRIME 0.294/NetTepi 0.293/IMPROVE 0.285/ICERFIRE 0.250/PredIG 0.250/IEDB 0.249…）。
- **分类稳健性（2026-07-04 敏感性核）**：即使只留教科书级无争议工具、剔掉边界工具（TransHLA/MUNIS/andy90），**结合类均值 0.287 vs 免疫原专用 0.158（差 +0.129，近两倍）**；前三名无争议。→ 结论不是分类假象。⚠️ 但精确「类均值」对分类敏感，论文卖点应用「前列全是结合工具」这句硬表述，不用类均值。**工具 10-vs-20 权威分类 + MUNIS/TransHLA 边界归属 = 袁老师拍板点**（见决策档）。

## 1. 「结合/呈递 ≥ 专门免疫原性」是学界已知（→ 数据没错）
| 文献 | 关键结论 | 链接 |
|---|---|---|
| **Wells et al., Cell 2020（TESLA 联盟）** ⭐最权威 | 五佳特征=binding affinity/tumor abundance/binding stability/hydrophobic/位置；优先呈递类特征的方法更优，**显式优先 foreignness/agretopicity（免疫原专用）不管呈递的「无差别或更差」** | https://www.cell.com/cell/fulltext/S0092-8674(20)31156-9 |
| **Buckley et al., Briefings in Bioinformatics 2022 (bbac141)** ⭐**同目标期刊·最直接先例** | 9 工具全近随机(ROC-AUC 0.50–0.57；癌症 neoantigen PR-AUC 0.051–0.211)；模型「**主要捕捉抗原呈递而非 T 细胞识别**」 | https://academic.oup.com/bib/article/23/3/bbac141/6573960 · 全文 https://pmc.ncbi.nlm.nih.gov/articles/PMC9116217/ |
| **"Beyond MHC binding" review, Explor Immunol 2023** | MHCflurry processing **0.609 ≥ PRIME 0.604** > INeo-Epp 0.584；最高 AUC≈0.6；binding「necessary but not sufficient」。⚠️差距小，宜写「持平或略胜」非「大幅超」 | https://www.explorationpub.com/Journals/ei/Article/100391 |
| **Frontiers Immunol 2023「Unraveling…」(ITSNdb)** | 排名 DeepHLApan #1、**MHCflurry(纯结合) #2**；全体 AUC 0.52–0.60 | https://www.frontiersin.org/journals/immunology/articles/10.3389/fimmu.2023.1094236/full |
| **ICERFIRE / NAR Cancer 2024（Nielsen 组）** | ML 头号重要特征=**MHC binding percentile rank**（14.7–22.7%），压过序列特征 | https://academic.oup.com/narcancer/article/6/1/zcae002/7591107 |

## 2. 机制共识：呈递主导可测信号
- 免疫原性 = 呈递 × TCR 识别；呈递侧可算、TCR 识别侧基本不可预测 → 可测信号被呈递主导（Buckley 2022 实证「捕捉呈递不捕捉识别」）。综述原文「binding…necessary but not sufficient」。低结合表位偶可免疫原（非充分性反面，Nat Commun 2021 reversion）。

## 3. 性能天花板：全体弱是任务难非数据错
- ROC-AUC 普遍 0.50–0.65（Buckley 0.50–0.57 / Frontiers 0.52–0.60 / 综述≈0.6）；新工具同域可 0.72–0.81 但**跨集崩**（ICERFIRE AXEL-F NEPDB 0.769→其他 0.415–0.466）。本项目最好 ρ≈0.45、多数<0.3，落天花板内正常。「accurate immunogenicity prediction remains unsolved」。

## 4. ⚠️ 反向电流（Discussion 须诚实呈现）
工具作者自评论文（Müller Immunity 2023、neoIM、DeepNeo-v2、ImmugenX、ICERFIRE）常宣称专用工具超 binding **7–30%**，但**多在自家 curated/同域数据、跨集常崩**；**独立第三方 benchmark**（Buckley、综述、本项目）一致发现 binding 有竞争力。二者并存=专用工具优势不稳、不可跨集复现。写作时点明此张力（Müller et al., Immunity 2023 https://www.cell.com/immunity/fulltext/S1074-7613(23)00406-5）。

## 5. 新颖性定位（投稿 differentiate）
- **卖点 ≠「binding 赢」（已知）**，而是：30 工具 × **独立新疫苗 ELISPOT 数据（Braun 2025）** × 严格 per-patient Spearman（控肽长/Fisher-z/effN≥8）× 突变级定量框架 × pooling/fusion 三层 —— 比以往零散/混数据集/二分类 AUC 报道**更系统、更大、更可复现**。
- **必须 vs Buckley 2022 划清**（同期刊）：本项目多了=定量 Spearman(非 AUC)+突变级(非肽级)+30 工具(非 9)+新数据(Braun2025)+QuantImmu 框架。

## 6. 现成 Discussion 句子（写 tex 直接用，附引用）
> **句1（binding baseline）**：Consistent with prior independent benchmarks and the TESLA consortium, we find that MHC binding/presentation predictors form a strong baseline for neoantigen immunogenicity, matching or exceeding tools explicitly designed for immunogenicity — echoing the TESLA observation that submissions prioritizing binding affinity, abundance and stability outperformed those prioritizing foreignness or agretopicity (Wells et al., *Cell* 2020; Buckley et al., *Brief Bioinform* 2022).
> **句2（性能天花板）**：The uniformly modest correlations we observe (best ρ≈0.45) are in line with the recognized performance ceiling of the field, where reported AUCs cluster around 0.5–0.65 and specialized predictors have been shown to primarily capture antigen presentation rather than T-cell recognition (Buckley et al. 2022; 'Beyond MHC binding' review, *Explor Immunol* 2023) — reflecting that immunogenicity is governed by a largely unpredictable TCR-recognition component on top of a measurable presentation signal.

## 7. TODO（写 tex 前人工二次确认）
- [ ] 用 "Braun 2025 neoantigen ELISPOT benchmark" 搜 Google Scholar，**确认没人用同款设置抢发**（初判本项目具体设置是新的）。
- [ ] 补全「Beyond MHC binding」综述**作者+卷期**（PDF 乱码/HTML 403 未取到）。
- [ ] Müller 2023 Immunity「专用工具超 binding ~30%」的确切 AUC 对照数值（全文 403，仅二手），引用前核。
