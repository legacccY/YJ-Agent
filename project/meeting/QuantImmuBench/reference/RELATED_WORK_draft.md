# Related Work 草稿（可投稿级储备）— 新抗原免疫原性预测 × response magnitude

> 服务项目 quantimmu-bench（袁老师癌症新抗原疫苗 benchmark / 未来 QuantImmune 论文）。
> 编纂日期 2026-06-24。来源 = 5 路 opus researcher 多角度并行深挖（撞车监控 / 工具 repo+许可 / 数据集+引用歧义 / 方法学对标 / 领域 taxonomy+引用图谱）+ opus reviewer 收口。
> 红线遵守：每条带 DOI 出处；查不到标 TODO 不臆想；撞车结论有出处；多源交叉。
> **本文是储备草稿**，不是定稿；正文落 tex 前数字仍须过 verifier，标 TODO 处须人工核实。

---

## ⭐ 0. 一句话核心结论（撞车监控，2026-06-24 更新）

**拆成两个口径（reviewer 收口要求，勿合并）**：
- **方向无撞车：高置信**（多源印证）。2024–2026 普查 12+ 新方法/工具 + 6 篇 2023–2026 综述，**没有任何一个工具对 T 细胞反应强弱（response magnitude / ELISpot SFC / tetramer 频率）做连续回归并报 Pearson/Spearman/MAE**。全部仍是二分类（immunogenic vs non，BCE loss + AUROC/AUPRC）或 binding 强度（nM）。2024 explorationpub 综述「magnitude prediction remains an unaddressed gap」未被推翻反被印证。
- **增量回报：中等，且有生物学上界**（低置信，勿夸大）。`THEORY_quant.md` 命门定理：纯肽+HLA 下 magnitude 可解释方差被供体特异 precursor frequency 结构性封顶，ρ_max 粗估 0.4–0.6。→ **claim 必须收窄**：卖点不是「精准回归 magnitude」，而是「连续排序对临床 top-K 选择的增量」（对齐 THEORY_quant.md §五押 C3）。别把 novelty 押在回归精度上。

**最强反向佐证（立项理由）**：PredIG 训练数据本含 `positive-low / intermediate / high` 分级标签却主动 binarize 丢弃；CNNeoPP 的 ELISpot 数据能分 weak(8–81 spots)/strong(≥81) 却仍只吐二分类 → **数据里有 magnitude 信号，被选择性丢弃**。
> ⚠️ 但须对冲对立假设（reviewer 🟠1）：「没人做」既可能是机会（解释 B：标签形状问题），也可能是「没人做得动」（解释 A：纯序列信号弱、ROI 低）。related work 叙事要主动承认上界，否则审稿人判「填了一个别人知道 ROI 低而故意不填的坑」。

---

## 1. 能力阶梯 Taxonomy（related work 叙事主轴：binding → presentation → immunogenicity → magnitude）

| 层 | 预测目标 | 输出量纲 | 代表工具 | 一句话方法 |
|---|---|---|---|---|
| **L1** MHC binding affinity | 肽–MHC 结合强度 | IC50 (nM) / %Rank | NetMHCpan, MHCflurry | pan-allele 神经网回归结合亲和力（binding 必要非充分） |
| **L2** Antigen presentation / EL | 肽被真实呈递概率（含蛋白酶切/TAP/质谱洗脱） | presentation %Rank / EL (0-1) | MHCflurry-presentation, PRIME, BigMHC-EL, NetMHCpan-EL | 在 binding 上加质谱 EL 配体数据，建模呈递 |
| **L3** TCR recognition / immunogenicity（**二分类**） | 该肽是否被 T 细胞识别（yes/no） | 二分类概率 (0-1) | DeepImmuno, DeepHLApan, IEDB-Immunogenicity, INeo-Epp, NetTepi, Repitope, neoIM, ICERFIRE, NeoaPred, ImmunoStruct, PredIG, IMPROVE, pTuneos, NeoTImmuML, Seq2Neo, DeepNeo, T-SCAPE | presentation 之上加 TCR-facing 残基/foreignness/agretopicity，分类免疫原 vs 非 |
| **L4** Response magnitude（**连续回归，空白**） | T 细胞应答强度/大小 | 连续标量（应答幅度） | **QuantImmune（本工作）** | 回归 magnitude 而非二分；综述反复点为 gap |

**分层叙事有综述支撑**（非自造）：
- bbaf302（Brief Bioinform 2025, DOI 10.1093/bib/bbaf302）：HLA typing → variant calling → **pMHC presentation** → **pMHC recognition**，且明指「缺 regression-based 量化 response magnitude 预测」「<half immunogenic peptides in top-20」。
- Biomarker Research 2025（DOI 10.1186/s40364-025-00808-9）：HLA typing → HLA-peptide binding → pHLA-TCR → integrated。
- ⚠️ L1/L2/L3 边界**软**（现代工具常跨层：NetMHCpan 同出 binding+EL；ICERFIRE 把 presentation %Rank 当输入特征）。写作时须说明「能力阶梯是任务目标分层，非互斥工具桶」。
- ⚠️⚠️ **L4 是正交轴，不是更高一级台阶**（reviewer 🟠4）：L1→L3 是「同一个二分判断越来越准」的递进；magnitude 是**正交的回归维度**（可在 presentation 层就问 magnitude，不必等到识别层）。写作须明确 "L4 is a regression axis orthogonal to the binary L1–L3 ladder, not a strictly higher rung"，否则 taxonomy 审稿人攻 novelty 框架本身。叙事宜改成「三级二分阶梯 + 一个正交 magnitude 维度」。

---

## 2. 方法范式分类

| 范式 | 代表作 | 核心 | 趋势 |
|---|---|---|---|
| 传统 ML (RF/XGBoost/LR) | IMPROVE(RF), PredIG(XGBoost), neoIM, ICERFIRE(ensemble RF), INeo-Epp(RF), PRIME | 手工特征(理化/cleavage/TAP/binding/agretopicity) + 树模型，SHAP 可解释 | 仍主流于 L3，强在小数据+可解释 |
| 深度序列 (CNN/Transformer) | DeepImmuno(CNN), BigMHC(DNN ensemble), Seq2Neo(CNN), ImmuScope(弱监督), MUNIS | 端到端序列编码 + 迁移学习(EL→immunogenicity) | 数据规模驱动，>650k pHLA 训练超传统 |
| 结构感知 | NeoaPred, ImmunoStruct | 引入 pHLA 表面/结构(AlphaFold)，补序列丢失的 TCR-facing 空间信息 | 解决「binding 当 surrogate 丢空间」 |
| 多模态 / 跨域 | T-SCAPE (= TITANiAN 同一 bioRxiv) | 对抗域适应整合 presentation+binding+TCR-pMHC+T 细胞活化 | 最前沿，跨任务迁移 |

⚠️ **T-SCAPE = TITANiAN 同一工作**（bioRxiv 2025.05.11.653308 v1=TITANiAN, v2=T-SCAPE；Sci Adv 正刊名 T-SCAPE, sciadv.adz8759）。引用合并，勿当两工具。

---

## 3. Related Work 散文草稿（英文，paper-ready；4 段跟能力阶梯走）

> 数字/DOI 已尽力核实；标 ⟨TODO⟩ 处投前须人工核。

**§RW.1 — The neoantigen prediction ladder.**
Computational prediction of tumor neoantigens has historically progressed along a capability ladder: from (i) peptide–MHC binding affinity, to (ii) antigen presentation, to (iii) binary T-cell immunogenicity, and—only nominally—to (iv) the *magnitude* of the elicited T-cell response. Recent surveys frame the discovery pipeline as HLA typing → variant calling → pMHC presentation → pMHC recognition [Brief Bioinform 2025, 10.1093/bib/bbaf302; Biomarker Research 2025, 10.1186/s40364-025-00808-9]. A recurring lesson across this literature is that MHC binding is necessary but not sufficient for immunogenicity: in the TESLA consortium benchmark, only ~6% of strongly-presented candidate peptides were experimentally immunogenic [Wells et al., Cell 2020, 10.1016/j.cell.2020.09.015].

**§RW.2 — From binding to presentation (L1–L2).**
Binding predictors such as NetMHCpan-4.1 [Reynisson et al., NAR 2020, 10.1093/nar/gkaa379] and MHCflurry 2.0 [O'Donnell et al., Cell Systems 2020, 10.1016/j.cels.2020.06.010] estimate peptide–MHC affinity (nM) or eluted-ligand presentation across thousands of alleles. Presentation-aware models—PRIME [Gfeller et al., Cell Systems 2023, 10.1016/j.cels.2023.01.001], BigMHC-EL [Albert et al., Nat Mach Intell 2023, 10.1038/s42256-023-00694-6]—integrate mass-spectrometry eluted-ligand data. Crucially, these continuous outputs quantify *binding strength*, not *response magnitude*: the affinity scale (nM) is a different dimension from T-cell response intensity, and benchmark studies report only weak correlation between binding and ELISpot magnitude [explorationpub 2024, 10.37349/ei.2023.00091].

> ⚠️ **必设防的「连续但非 magnitude」近邻（reviewer 🟠2，最可能被攻 novelty 的缺口）**：三类工具会输出连续值、被对抗审稿人当「已有定量 baseline」反驳我们「全是二分类」的陈述——(a) binding affinity (nM, NetMHCpan/MHCflurry)；(b) **stability/半衰期** (NetMHCstabpan)；(c) **TCR-pMHC ranking percentile** (pMTnet, Lu et al. Nat Mach Intell 2021)。防御（弹药已在 LANDSCAPE_tools.md §三）：这些靶的是结合/稳定性/TCR-pMHC 强度，**量纲不同于群体 T 细胞 SFC/频率**，且与 ELISpot magnitude 仅弱相关（NetMHCpan-4.0 Pearson r=−0.399、MHCflurry r=0.38）。正文须显式列这三个近邻 + 一句话挡掉，否则 novelty 裸奔。这三者应设为 magnitude 回归的**对照 baseline**。

**§RW.3 — Immunogenicity classification (L3).**
The bulk of neoantigen immunogenicity tools target a *binary* outcome—is this peptide T-cell immunogenic? Methodologically they cluster into: (a) classical ML on hand-crafted features—IMPROVE (random forest, 27 features) [Borch et al., Front Immunol 2024, 10.3389/fimmu.2024.1360281], PredIG (XGBoost) [PredIG, Genome Medicine 2025, 10.1186/s13073-025-01569-8 ⟨DOI TODO-confirm⟩], ICERFIRE (ensemble RF) [Tadros et al., NAR Cancer 2024, 10.1093/narcancer/zcae002]; (b) deep sequence models—DeepImmuno (CNN) [Li et al., Brief Bioinform 2021], BigMHC (DNN ensemble with EL→immunogenicity transfer) [10.1038/s42256-023-00694-6]; (c) structure-aware models—NeoaPred [Wang et al., Bioinformatics 2024, 10.1093/bioinformatics/btae547], ImmunoStruct [Liu et al., Nat Mach Intell 2025, 10.1038/s42256-025-01163-y]; and (d) multi-modal/cross-domain models—T-SCAPE [Sci Adv 2025, sciadv.adz8759]. Despite architectural diversity, every one of these produces a classification or ranking score; even tools trained on graded labels collapse them to binary—ICERFIRE explicitly states "all the labels for a given Peptide-HLA pair were collapsed into a single class label" [10.1093/narcancer/zcae002], and PRIME's authors note the %Rank is "a ranking metric, not a calibrated probability or quantitative response magnitude" ⟨原句 TODO-confirm；见 §6 盲区⟩.

**§RW.4 — The magnitude gap (L4) and this work.**
No published tool is explicitly designed to regress the *continuous magnitude* of the T-cell response. A 2024 review of immunogenicity predictors concludes bluntly: "No tool in this review was explicitly developed to predict T cell response magnitude. All tools perform binary classification. Magnitude prediction remains an unaddressed gap" [explorationpub, Exploration of Immunology 2024, 10.37349/ei.2023.00091]; the 2025 Brief Bioinform survey likewise does not list regression-based magnitude prediction among solved tasks and notes that fewer than half of immunogenic peptides appear in the top-20 ranked candidates [10.1093/bib/bbaf302]. The gap persists despite available signal: PredIG's training data carry positive-low/intermediate/high labels that are binarized away [Genome Medicine 2025], and CNNeoPP's validation ELISpot data distinguish weak (8–81 spots) from strong (≥81 spots) responses yet the model still outputs only a binary call [CNNeoPP, Front Immunol 2026, 10.3389/fimmu.2026.1722117 / PMC12913462]. Since CD8 response magnitude (and breadth) correlate with clinical benefit independently of tumor mutational burden ⟨临床关联 TODO-pin 确切出处⟩, **QuantImmune** addresses this L4 gap by regressing response magnitude rather than classifying immunogenicity. We note that sequence-level magnitude prediction is biologically upper-bounded—donor-specific precursor frequency caps the explainable variance—so our contribution is framed not as high-precision magnitude regression but as exploiting the ranking-relevant continuous signal that current binary tools discard, for clinical top-K prioritization. QuantImmune is benchmarked against the strongest binary tools (neoIM, ICERFIRE, IMPROVE, PredIG) repurposed as magnitude baselines, and against the continuous proxies reviewers will inevitably raise (NetMHCpan/MHCflurry affinity, NetMHCstabpan stability, pMTnet TCR-pMHC percentile), plus a permutation-label control.

---

## 4. 方法学对标 / Evaluation protocol（堵审稿人，写 Methods/Discussion 用）

### 方法学对标表

| 论文 | 数据规模 / 阳性率 | 主指标 | 泄漏处理 | 不平衡处理 | takeaway |
|---|---|---|---|---|---|
| TESLA / Wells, Cell 2020 [10.1016/j.cell.2020.09.015] | 608 肽 / 37 (6%) 免疫原 | **TTIF**(top-20 免疫原占比) / **Fraction Ranked**(top-100 命中) / AUPRC | 共识盲预测+集中实验验证 | rank-based 非 accuracy；PPV 均 ~7%，组合可升 ~50% | 确立 per-patient rank-based 范式 |
| IMPROVE / Borch, Front Immunol 2024 [10.3389/fimmu.2024.1360281] | 17,520 肽 / 467 (**2.7%**) | AUC + **AUC01**(高特异区偏 AUC) + PR curve + MCC | **患者级聚类 split** + **测试肽若现于训练集则剔除** | subsample 500 负样本×50 ensemble | 患者级 split + 去重防泄漏硬规范 |
| Müller, Immunity 2023 [10.1016/j.immuni.2023.09.002] | 三数据集 120+11 患者 | **Top-20/Top-100 命中率**(54.5/89.7% 等) | **统一重处理(harmonization)** + 跨数据集 held-out | ranking 命中率非分类准确率 | 跨 HLA/瘤种/实验室/assay 泛化是金标准 |
| Buckley, Brief Bioinform 2022 [10.1093/bib/bbac141] | 多工具系统评测 | AUC + rank-based + PPV | **SARS-CoV-2 新病毒做 OOD 集** | — | 无工具显著超纯 MHC-presentation baseline |
| Zhao 综述, Brief Bioinform 2025 [10.1093/bib/bbaf302] | 综述 | TTIF/FR/AUPRC/AUROC，**cohort-level TTIF 最常用** | 综述层未展开 | — | 复现性规范：Snakemake/NextFlow + bioconda + provenance/portability |
| comprehensive, Front Immunol 2023 [10.3389/fimmu.2023.1094236, PMC10411733] | validation 刻意 7/120 = **5.8%** 阳性 | DOP/F1/AUC/Se/Sp/PPV rank-averaged | TESLA 来源排除主评估外 | **刻意构造极不平衡 validation "emulate real patient scenario"** | 真实临床比例独立集是堵审稿人关键 |

> 不平衡指标理论依据（ML 经典，可引）：Saito & Rehmsmeier, PLOS ONE 2015, 10.1371/journal.pone.0118432 — PR plot 在不平衡上比 ROC 更 informative。
> ⚠️ 平衡陈述：AUPRC>AUROC 有 2024 反方（arXiv 2401.06091）；discussion 宜两面陈述。

### 我们 benchmark 该采纳的评估协议（带出处）
1. 主指标 = rank-based 三件套 **cohort-level TTIF + Fraction Ranked + AUPRC**，per-patient 算后 cohort 平均 [TESLA; bbaf302]。
2. 辅 Top-K 命中率（top-20/top-100）[Müller 2023]。
3. AUROC 仅参考、并列 AUPRC [Saito 2015]。
4. 独立验证集**还原真实临床阳性率 ~2–6%**，禁平衡集报性能 [IMPROVE 2.7%; TESLA 6%; Front Immunol 2023 5.8%]。
5. **患者级 split + peptide/motif 去重**防泄漏 [IMPROVE]。
6. **跨数据集 / leave-one-cohort-out** 验证 [Müller 2023; Buckley OOD]。
7. **统一重处理(harmonization)** 消批次 [Müller 2023]。
8. 排序分明确标 ranking score 非校准概率；做回归须报 **Pearson/Spearman/MAE/concordance index** [PRIME README]。
9. 复现性按 Zhao 2025 规范（工作流+包管理器+provenance）[bbaf302]。
10. **（reviewer 🟡7 补）magnitude 回归须设两个零成本对照** + 报 bootstrap CI：(a) **permutation-label control**（打乱标签防泄漏假信号）；(b) **single-feature binding-affinity null model**（证明回归显著优于 NetMHCpan BA proxy——LANDSCAPE_tools.md §三点名的最可能撞车攻击点）。注：DS2 阴性仅 11、ρ=0.32 可能不显著，bootstrap CI 是已知软肋必报。
11. **（reviewer 🟡8 补）补一篇连续生物标志物回归评估方法学锚**（calibration / Bland-Altman / concordance index），否则方法学审稿人挑「凭什么证明回归是好的」。⟨TODO 找具体论文⟩

---

## 5. 引用图谱（文字版，供后续画图）

**数据集引用簇（中心节点）**：
- **TESLA**（Cell 2020, 10.1016/j.cell.2020.09.015）= 几乎所有 L3 工具的外部 benchmark 锚（ICERFIRE/IMPROVE/neoIM/Müller 均对账）。
- **IEDB / CEDAR**（cancer 子库）= L3 训练标签主源（ICERFIRE 用 CEDAR；PredIG/INeo-Epp 用 IEDB）。
- **NEPdb / dbPepNeo / Neodb / TSNAdb** = neoantigen 标签库（NeoTImmuML/Seq2Neo 管道引）。
- **HLA Ligand Atlas / 质谱 EL** = L2 工具(BigMHC/MHCflurry/ImmuScope)训练源。
- **VDJdb/McPAS-TCR/TCR3d** = L3 多模态(T-SCAPE)的 TCR-pMHC 源。

**baseline 对比关系**：
- NeoTImmuML baseline = VaxiJen + IEDB-Immunogenicity + DeepImmuno [10.3389/fimmu.2025.1681396]。
- ICERFIRE baseline = 既有 immunogenicity + EL 预测器 [10.1093/narcancer/zcae002]。
- PredIG baseline = immunogenicity + HLA-I binding + pHLA stability [Genome Medicine 2025]。
- BigMHC = EL 预训练→transfer immunogenicity，自身横跨 L2→L3 [10.1038/s42256-023-00694-6]。
- **引用簇核心链**：NetMHCpan/MHCflurry(L1-L2，人人引为特征/baseline) → TESLA(benchmark 锚) → DeepImmuno/IEDB-Immunogenicity(L3 老 baseline) → ICERFIRE/neoIM/IMPROVE/PredIG(2024-25 SOTA 簇，互引) → T-SCAPE/ImmunoStruct(多模态/结构前沿)。
- **QuantImmune 入图位置**：挂 L3 SOTA 簇之后，作 L4 唯一节点；baseline = neoIM/ICERFIRE/IMPROVE/PredIG（二分分数当 magnitude 回归 baseline 对比）+ NetMHCpan/MHCflurry BA（binding proxy 对照）。
- **建议做引用图谱**：✅ 值得（领域叙事是「能力阶梯」，引用图能直观展示 L1→L4 断层 + QuantImmune 填空位）。后续派 coder 用 graphviz/networkx 出图，节点按 L1-L4 着色，边=baseline/引用关系。

---

## 6. ⚠️ 重大纠正 + 盲区 TODO（红线：未核实绝不写进 tex）

### 重大纠正（派单前提里的错，必须改）
1. **neoIM ≠ Immunity 2023 DOI**。旧档把 `10.1016/j.immuni.2023.09.002`（CD8 immunogenicity, n=61829）挂给 neoIM 是**两篇混淆**：
   - 该 Immunity DOI = **Müller et al.「Machine learning methods and harmonized datasets improve immunogenic neoantigen prediction」**（Swiss Inst Bioinformatics/Ludwig, CC BY-NC 4.0）。
   - **neoIM** = **myNEO Therapeutics bioRxiv 预印本**（10.1101/2022.06.03.494687，**专利 EP4229640，专有，无公开 repo，不可纳入 benchmark**）。
   - → 引用时分开；neoIM 不能挂 Immunity DOI；neoIM 因专有**不能进我们 benchmark**。
2. **"Nature Cancer 2025 neoantigen reproducibility crisis" 疑似搜索模型幻觉**。3 次独立搜索反复出现相同概括句但无可点击文章，`site:nature.com` 搜不出。**引用前必须人工确认；建议从 related work 删除或替换**为真实证据：TESLA 6% 验证率 + 25 队普遍失败 [10.1016/j.cell.2020.09.015]、Buckley「无工具超 MHC-presentation baseline」[10.1093/bib/bbac141]、Zhao「<half in top-20」[10.1093/bib/bbaf302]。
3. **NeoPepDB 不存在**，几乎确定是 **NEPdb** 笔误（精确搜全跳 NEPdb）。NEPdb = Xia et al. Front Immunol 2021, 10.3389/fimmu.2021.644637, PMID 33927717, http://nep.whu.edu.cn/，17,549 条**二元**标签（无连续定量分）。

### 已确认（可放心用）
- **IMPROVE 引用确认**：Borch et al., Front Immunol 15, 2024, **DOI 10.3389/fimmu.2024.1360281, PMID 38633261, PMCID PMC11021644**（两个候选指同一篇，不矛盾）。
- **工具 repo + 许可表**（已逐一核 LICENSE 原文）：

| 工具 | repo URL | 许可 | 可下? | 可进 benchmark? |
|---|---|---|---|---|
| Repitope | github.com/masato-ogishi/Repitope | **MIT** | ✅ R 包 | ✅ 完全开放 |
| NeoaPred | github.com/Dulab2020/NeoaPred | **Apache-2.0** | ✅ 代码+权重+Docker | ✅ 完全开放 |
| BigMHC | github.com/KarchinLab/bigmhc | 学术非商用(自定义) | ✅ 权重 | ✅ 学术可，商用需授权 |
| ImmunoStruct | github.com/KrishnaswamyLab/ImmunoStruct | Yale 非商用 | ✅ HF 权重 | ✅ 学术可，**需结构输入(重)** |
| diffRBM/TLImm | github.com/cossio/diffRBM + github.com/bravib/diffRBM_immunogenicity_TCRspecificity | cossio=非商用；bravib=**无 LICENSE** | ✅ 代码+模型 | ✅ 学术可 |
| T-SCAPE | github.com/seoklab/T-SCAPE | **冲突**(LICENSE 文件 CC0 vs README CC BY-NC-ND)，按 ND 走 | ✅ 代码+HF 权重 | ⚠️ ND 可能限改装，建议问作者 |
| DeepNeo | github.com/kaistomics/DeepNeo | **无 LICENSE**(默认保留版权) | ✅ 代码 | ⚠️ 再分发输出法律不明，需联系作者 |
| neoIM | 无公开 repo | 专利 EP4229640 专有 | ❌ | ❌ 不可纳入 |

### 未解 TODO（投稿前须人工核 / 不臆想）
- **TESLA 连续 tetramer 频率下载位置 + 补充表文件名 + 列名**：Cell 全程 403，**未能核实**哪个补充表(S1/S2/S3/Data S)含 per-peptide 连续值。Synapse syn21048999 是否需 MTA 才下连续值也未证实。**数据集表里勿写具体 mmc 文件名/列名**。下游所有引 TESLA 的工具都只用二元标签——这本身是「连续标签事实上不可得/未被使用」的可写证据点。
- **CEDAR/IEDB quantitative 字段（ELISpot SFC 连续值）填充率**：无现成可引统计。若写须自测（下 tcell_full_v3.csv 统计 "Quantitative measurement" 列非空比例）。
- **PRIME "not a calibrated probability" 原句**：README 只说 %Rank 用于排序，未见字面原句；逐字引前须人工定位，否则转述。
- **CD8 magnitude 关联临床获益（PFS/OS，独立 TMB）** 的确切出处未 pin。
- **PredIG DOI** 标 Genome Medicine 2025 (10.1186/s13073-025-01569-8) 待逐字核；DeepImmuno/DeepHLApan/NetTepi/Seq2Neo 各自原始 DOI 未逐一拉，引用前补。
- **3 篇综述「是否提 magnitude gap」未抓正文核**：npj Vaccines 2025 (10.1038/s41541-025-01258-y)、Trends Cancer 2026 (PII S2405-8033(26)00034-8, DOI 尾号未定)、Front Immunol 2024 (10.3389/fimmu.2024.1394003)。
- **Genes & Immunity 2025 综述**（10.1038/s41435-025-00365-z）全文被 Nature 登录墙挡，magnitude 段落未直读。

### 新工具撞车候选（2024–2026，全部确认 ❌ 不做 magnitude 回归）
ImmunoNX(arXiv 2512.08226, 纯 workflow)、NeoPrecis(bioRxiv 10.1101/2025.07.23.666355, BCE 二分)、NeoTImmuML(10.3389/fimmu.2025.1681396, 二分)、CNNeoPP/CNNeo(PMC12913462, 二分+post-hoc 强弱)、ImmuScope(10.1038/s42256-025-01073-z, BCE)、Mouse Immunogenicity Framework(bioRxiv 10.64898/2026.02.10.704454, post-hoc 相关非预测器)。

---

## 7. 参考文献表（带 DOI，related work 引用骨架）

| key | 引用 | DOI / ID | 角色 |
|---|---|---|---|
| explorationpub2024 | Exploration of Immunology 2024 综述 | 10.37349/ei.2023.00091 | **magnitude gap 最强直接证据** |
| TESLA2020 | Wells et al., Cell 2020 | 10.1016/j.cell.2020.09.015 | benchmark 锚 + 评估范式 |
| IMPROVE2024 | Borch et al., Front Immunol 2024 | 10.3389/fimmu.2024.1360281 (PMID 38633261) | 传统 ML + 泄漏规范 |
| Muller2023 | Müller et al., Immunity 2023 | 10.1016/j.immuni.2023.09.002 | harmonization + 跨数据集泛化 |
| Buckley2022 | Buckley et al., Brief Bioinform 2022 | 10.1093/bib/bbac141 | OOD 评测 |
| Zhao2025 | Zhao et al., Brief Bioinform 2025 | 10.1093/bib/bbaf302 | taxonomy + 复现性 + magnitude gap |
| BiomarkerRes2025 | Wang et al., Biomarker Research 2025 | 10.1186/s40364-025-00808-9 | 流水线 taxonomy |
| BigMHC2023 | Albert et al., Nat Mach Intell 2023 | 10.1038/s42256-023-00694-6 | 深度范式 + EL transfer |
| ICERFIRE2024 | Tadros et al., NAR Cancer 2024 | 10.1093/narcancer/zcae002 | 标签塌缩二分铁证 |
| ImmunoStruct2025 | Liu et al., Nat Mach Intell 2025 | 10.1038/s42256-025-01163-y | 结构范式 |
| NeoaPred2024 | Wang et al., Bioinformatics 2024 | 10.1093/bioinformatics/btae547 | 结构范式 |
| TSCAPE2025 | T-SCAPE, Sci Adv 2025 (=TITANiAN) | sciadv.adz8759 | 多模态前沿 |
| NetMHCpan2020 | Reynisson et al., NAR 2020 | 10.1093/nar/gkaa379 | L1 binding |
| MHCflurry2020 | O'Donnell et al., Cell Systems 2020 | 10.1016/j.cels.2020.06.010 | L1-L2 |
| PRIME2023 | Gfeller et al., Cell Systems 2023 | 10.1016/j.cels.2023.01.001 | L2 presentation |
| NEPdb2021 | Xia et al., Front Immunol 2021 | 10.3389/fimmu.2021.644637 (PMID 33927717) | 数据库(二元) |
| Saito2015 | Saito & Rehmsmeier, PLOS ONE 2015 | 10.1371/journal.pone.0118432 | 不平衡指标依据 |
| Comprehensive2023 | Front Immunol 2023 | 10.3389/fimmu.2023.1094236 (PMC10411733) | realistic-imbalance 范例 |
| NatRevImmunol2023 | Challenges in personalized neoantigen vaccines | 10.1038/s41577-023-00937-y | 临床侧 predicted≠immunogenic |
| PredIG2025 | PredIG, Genome Medicine 2025 | 10.1186/s13073-025-01569-8 ⟨待核⟩ | 传统 ML + magnitude 标签被丢弃 |
| CNNeoPP2026 | CNNeoPP, Front Immunol 2026 | 10.3389/fimmu.2026.1722117 (PMC12913462) | magnitude 数据被丢弃佐证 |
| neoIM_myNEO | neoIM, myNEO bioRxiv | 10.1101/2022.06.03.494687 (专利 EP4229640) | 专有，不可纳入 |
| pMTnet2021 | Lu et al., Nat Mach Intell 2021 | 10.1038/s42256-021-00383-2 ⟨DOI 待核⟩ | 连续 TCR-pMHC percentile，须设防的「连续近邻」对照 |
| NetMHCstabpan2016 | Rasmussen et al. | 10.4049/jimmunol.1600582 ⟨待核⟩ | 连续半衰期 proxy 对照 |

> ⚠️ 删除/勿用：「Nature Cancer 2025 reproducibility crisis」（疑幻觉）、「NeoPepDB」（=NEPdb 笔误）。

---

## 8.5 Reviewer 收口审稿（opus reviewer，2026-06-24）

**总判：0 致命，可作可投稿 related work 起点**（本文是「储备」非「成稿」，定位诚实）。落 tex 前**必补**（已据此打补丁进本文 §0/§1/§RW.2/§RW.4/§4）：
- 🟠1 蓝海叙事 vs 自家天花板张力 → §0 已拆「方向无撞车=高 / 增量回报=中等有上界」，§RW.4 已收窄 claim 到 top-K 排序增量 + 承认生物学上界。
- 🟠2 pMTnet/连续近邻防御缺失（最可能被攻 novelty 缺口）→ §RW.2 已搬入三类连续近邻 + 量纲反驳。
- 🟡4 L4 正交轴非台阶 → §1 已加 orthogonal axis 说明。
- 🟡5 带引号 ⟨TODO⟩ 引用（PRIME 原句）落 tex 须去引号转述，防捏造直接引语。
- 🟡7 评估协议补 permutation control + BA-null baseline + bootstrap CI → §4 已补第 10 条。
- 🟡6 Müller Immunity DOI 期刊归属 + ρ=0.32 CI + PredIG/pMTnet DOL/TESLA 连续值 → 交 verifier 三方核源后再入 tex。

## 8. 给主线/袁老师的三条提醒
1. 蓝海仍开放（高置信，8 工具+6 综述全空）；连 PredIG/CNNeoPP 手握 magnitude 数据都主动二值化 = QuantImmune 最强立项理由。
2. neoIM 身份纠正 + 专有不可纳入；reproducibility crisis 那篇疑幻觉须替换；NeoPepDB=NEPdb。三处旧档已据此改。
3. TESLA 连续值下载位 + 补充表列名未核（Cell 403），数据集表勿臆造文件名/列名；CEDAR 定量填充率须自测。
