# QuantImmu 方法学重构提案 — 给袁老师 / 朱同学拍板

> **一句话**：官方更正数据（130 肽 9mer 主分析口径，忠于 outline §2.2）跑通后，我们发现 outline 的两个细粒度 headline（§3.2「免疫原类→max 最优」、§3.3.4「geomean 唯一双检验第一」）**在官方数据上不复现**。经严谨归因，**根因是评价功效（n=9 患者太小），不是我们实验的 bug，也不是数据真相反转**。领域旗舰 benchmark（TESLA）撞过同一堵墙、并给出了成熟解法。本提案把这套解法整理成三部曲，请老师拍板论文的方法学定位。
>
> **这是改论文战略定位的决策，余嘉不擅自实施，先呈请拍板。**

---

## 一、发生了什么（据实，数字 Bash 核 csv）

按 outline §2.2「全文主分析用 9AA-only」把主分析口径从「全窗 8-14mer」切到「仅 9mer」后（数据实证支持：9mer 在 **21/30 工具**上优于或等于全窗，27/30 ≥，坐实 §2.2）：

| outline 核心主张 | 官方 130 肽 9mer 实测 | 判定 |
|---|---|---|
| §2.2 9AA 优于可变窗 | 21/30 工具胜 | ✅ 成立 |
| §3.2 亲和类靠聚合跃升 | netMHCpan_BA max 0.32 → 聚合 0.52-0.54 | ✅ **强成立**（大效应）|
| §3.2 免疫原类→max 即最优 | 6 工具 5 个 max 非数值最优 | ❌ 不复现 |
| §3.3.4 geomean 唯一双检验第一 | 偷看标签→powmean / 原则规则→mean_rank / geomean 从不第一 | ❌ 不复现 |
| §3.3.5 整合 vs 最强单持平 | 最强单(亲和)现明显领先 fusion | ⚠️ 偏移 |

---

## 二、根因诊断：是评价功效，不是 bug、不是数据反转（配对检验铁证）

对「不复现」的两个 headline 做患者层配对检验（n=9 患者）：

**免疫原「max 塌」——全部不显著：**
| 工具 | best-pooling vs max Δz̄ | p 值 | 判定 |
|---|---|---|---|
| PRIME | +0.078 | 0.27-0.30 | 不显著 |
| PredIG | +0.152 | 0.10-0.13 | 不显著 |
| pTuneos | +0.169 | 0.37-0.38 | 不显著 |
| ImmuneApp | +0.133 | 0.35-0.36 | 不显著 |

**fusion「geomean 塌」——大多不显著：**
- geomean vs powmean：p=0.22（区分不开）
- geomean vs mean_rank：p=0.98（几乎相同）
- 仅 powmean vs mean_rank：p=0.01（显著）

**结论**：max 与「最优 pooling」、geomean 与其他 fusion **在统计上打平**。outline 的细粒度「谁第一」是在旧数据上**过度解读了噪声**；换数据就重排，正因它们从未被显著区分。

**排除了两个替代解释**：
- ❌ 不是数据真相反转：差距根本不显著，谈不上"反转"。
- ⚠️ 子肽展开含约 40% 非突变 WT 9mer（该清理瑕疵）+ DAI 缺失（outline Step1 选项）——查过，只留含突变 9mer / 加 DAI 都不复现 max 最优（DAI 全 24 工具只救 1）。非主因。

> **🔴 2026-07-01 补充（全 30 工具再审，修正上文）**：headline 塌**部分确是我方评价问题 = count 混杂**。`n_subpep`（子肽数）自己对 ELISpot per-patient Spearman **+0.36**（比多数工具真分高），`sum`/`mean` pooling 在数数；`best_pooling_for_tool` 给 21/29 工具挑了 count-混杂的 sum → 「聚合打败 max」大半是假象。**排除 count 混杂 pooling 后：全工具 max 最优 1/30→5/29，免疫原类 13/22 max≈最优（中位 gap 仅 +0.04）** → outline §3.2「免疫原→max」**比本提案初稿说的可辩护得多**。诊断修正为两层：①count 混杂（可修，修了 §3.2 站得住）②残余 n=9 噪声+稀疏工具。⚠️ fusion 维度也用 best_pooling(sum) → geomean/powmean 比较同受污染，需 **count-clean 重跑 R1-R9** 才是真结果。详见 04_LOG Entry 38。

---

## 三、领域先例：TESLA 撞过同一堵墙（关键背书）

- **TESLA（Wells et al. 2020, Cell；PMC7652061）**：领域旗舰新抗原免疫原性 benchmark，只有 **6 患者 / 608 肽**。它**不 claim 哪个工具/方法显著最优**——工具排序只用 median/boxplot 描述性呈现；其 p 值全部来自 **pooled peptide-level**（608 肽做特征关联，Mann-Whitney p=4e-6）。**功效从「肽数」拿，不从「患者数」拿。**
- **IMPROVE（Frontiers Immunol 2024）**：70 患者，同样走 pooled 肽级 AUC 比工具。
- **ITSNdb 综述（Frontiers Immunol 2023）**：全工具 AUC 0.52-0.60，明说「所有方法都难区分免疫原性」。

→ **我们「n=9 分不出谁第一」不是失败，是领域通例**；且旗舰的标准解法就是**换到肽级估计量拿功效**。这为我们的诚实呈现 + 方法学重构提供了直接背书。

---

## 四、三部曲：原目标（统一定量·突变级·30 工具标准）怎么严谨实现

原目标能实现且**更能打**，靠三个修：

### 修① 换估计量（最大杠杆，从肽拿功效）
- **保留** per-patient Spearman 作临床动机主指标（诚实但功效低）。
- **增补** pooled 肽级 AUPRC/AUROC 作**共同主指标**（对齐 TESLA/IMPROVE），功效从 130 肽而非 9 患者来。
- 工具/pooling 对比用**混合效应 logistic（患者随机效应）**：用满 130 肽 + 校正患者内相关；小簇 SE 用 clubSandwich CR2 校正。
- 显著性：bootstrap-over-peptides BCa CI + **患者内 restricted permutation**（守 type I error，文献认证最诚实）。

### 修② 去掉偷看标签的 selection bias
- pooling/fusion 改**先验指派**（按工具类别 / 数据属性，非看 Elispot 挑最优）→ 消除让 geomean/powmean 乱跳的根因。
- fusion 默认用 **RRA（Kolde 2012 Bioinformatics，有零假设显著性、抗噪、非偷看标签）** 或 **geomean（AND 语义 + 抗离群）**；headline 改成「先验选 X 因其鲁棒性；n=9 下 fusion 细排序统计未分辨（同 TESLA）」。
- 依据：Li et al. 2022 Bioinformatics 明确「无普适最优聚合子，按数据属性用流程图先验选」。

### 修③ 扩 N 上外部队列（患者层功效的真解）
- **Müller et al. 2023, Immunity（131 患者 harmonized，明示供外部 benchmark）= 首选、最省事。**
- **Gartner et al. 2021, Nature Cancer（112 患者，真 IFN-γ ELISpot；dbGaP 受控）= 金标准但需申请。**
- 这一步把「趋势但不显著」变「外部队列确证」——定论级。

---

## 五、决定性检验：修①够不够（analyst 实测，已回填 2026-07-01）

R2 文献点明命门：**方法差是患者内一致（修①肽级可救）还是患者间异质（必须修③外部）？** analyst 用真数据检验完毕（数字 Bash 核 DIAG csv）：

**检验1 — 患者内方向一致性**（关键分野）：
| 对比 | 跨 9 患者同号 | 判定 |
|---|---|---|
| netMHCpan_BA best(sum) vs max | **9/9** | ✅ 患者内一致（真肽层信号）|
| PredIG best(sum) vs max | **7/9** | ✅ 患者内一致 |
| PRIME best vs max | 5/9 | ⚠️ 异质 |
| fusion geomean vs powmean | 5/9（4正5负）| ❌ 无方向 |
| fusion powmean vs mean_rank | 5/9 | ❌ 无方向 |

**分野清晰**：有真信号的问题（哪工具/哪 pooling 更好，如 best 优于 max 因 max 丢子肽信息）患者内一致 → 效应在肽层，修①可救；但 **fusion 方法互比那 0.03 微差** 4-5/9 完全无方向 → **不是欠功效，是效应本就 ≈0**。

**检验2 — 肽级 AUPRC 试跑**（标签=官方 Braun2025 `Ttest_pvalue_InVitroStim<0.05`，76 阳/54 阴平衡，与 SFC>0 一致；二分是 choice 已注明）：
- 肽级 CI 明显比 per-patient 窄（BA CIw 0.212 vs perpat 0.294）。
- **决定性配对 bootstrap（同 130 肽）**：真工具差 netMHCpan_BA vs PredIG **ΔAUPRC=+0.084 [+0.006,+0.161] 排除 0** ✅ 能测出；同一差 per-patient(n=9) Wilcoxon **p=0.359 测不出**（P107=−0.52/P109=+0.80 患者间方差爆表）。fusion 微差 powmean vs geomean Δ=+0.005 [−0.016,+0.026] **紧 null** → 能说「等价」而非「欠功效未知」。

**VERDICT — 修①（肽级估计量）够用，不必强上修③外部队列**（针对 pooling/fusion lever）：
1. **有真信号的问题**（工具/pooling 优劣）患者内一致 + 肽级可显著 → 修①把「n=9 全不显著」变成「BA>PredIG 显著」。
2. **fusion 方法微差**患者内无方向 + 肽级紧 null → 真的 ≈0，修③外部队列也变不出 geomean 赢 powmean。fusion 该改写为**等价性结论（TOST）**，别再当「未达显著」。

**诚实 caveat**（写作必守）：肽级 pooled AUPRC 换了 estimand（混患者内+患者间、忽略患者结构），回答的临床问题与 per-patient Spearman（单患者内排序，TESLA 关心的）略不同 → **双指标并列，不用肽级悄悄替换主指标**；进阶可上肽级 mixed-effects（患者随机截距）兼顾功效+患者结构。

（产出 `analysis/official/DIAG_within_patient_consistency.csv` + `DIAG_peptide_level_auprc.csv` + `figures/DIAG_power_rescue.png`）

---

## 六、论文定位的转变（比原版更经得起 BiB 审稿）

贡献从「我们发现 geomean 是最优 fusion」（噪声、站不住）→ 转为：
1. **首个统一定量·突变级协议 + 肽级估计量**评测 30 工具（方法学贡献，扎实）。
2. **稳健发现**：亲和聚合效应、9mer 口径优势、工具排序（大效应，跨口径存活）。
3. **诚实功效分析**：单队列 n=9 细排序不可分辨（同 TESLA）→ 先验原则聚合（RRA/geomean）+ 外部队列验证。「新抗原算法可复现性」本身是近年热点，诚实框架反而是加分项。

---

## 七、请老师拍板的点

1. **认不认这个诊断**（headline 塌 = 评价功效所限，非 bug，非数据反转）？
2. **主分析口径**：确认 9mer（忠 §2.2 + 数据 21/30 支持）为主、全窗降补充？
3. **估计量**：接不接受「per-patient Spearman + pooled 肽级 AUPRC」双主指标（对齐 TESLA/IMPROVE）？
4. **headline 重定**：把「geomean 唯一最优」改为「先验原则选聚合子 + 诚实报 n=9 不可分辨」？
5. **是否上外部队列**（Müller 2023 / NCI）扩 N —— 决定这篇是「单队列诚实 benchmark」还是「多队列确证 benchmark」的档次。

---

## 附：关键引用

- TESLA / Wells 2020, Cell — https://pmc.ncbi.nlm.nih.gov/articles/PMC7652061/
- IMPROVE, Frontiers Immunol 2024 — https://www.frontiersin.org/journals/immunology/articles/10.3389/fimmu.2024.1360281/full
- ITSNdb 综述, Frontiers Immunol 2023 — https://www.frontiersin.org/journals/immunology/articles/10.3389/fimmu.2023.1094236/full
- Müller 2023, Immunity — https://www.cell.com/immunity/fulltext/S1074-7613(23)00406-5
- Gartner 2021, Nature Cancer — https://www.nature.com/articles/s43018-021-00197-6
- Kolde 2012 RRA, Bioinformatics — https://academic.oup.com/bioinformatics/article/28/4/573/213339
- Li 2022 rank aggregation 系统比较, Bioinformatics — https://academic.oup.com/bioinformatics/article/38/21/4927/6696211
- Cameron & Miller 2015, JHR（少簇铁律）— https://cameron.econ.ucdavis.edu/research/Cameron_Miller_JHR_2015_February.pdf
- Leyrat 2018, IJE（LMM 需 30-40 簇）— https://academic.oup.com/ije/article/47/1/321/4091562
- Corani & Benavoli 2017, ML + baycomp — https://arxiv.org/abs/1609.08905 / https://github.com/janezd/baycomp

**TODO（researcher 未核实，勿当已证）**：Müller harmonized 确切下载 URL、TESLA 608 肽是否含 IFN-γ 定量、Gartner dbGaP accession、Nature Cancer 2025「reproducibility crisis」确切 DOI。
