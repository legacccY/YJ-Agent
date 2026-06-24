# 已发表 neoantigen benchmark 方法学对标

> 服务项目 quantimmu-bench。researcher(opus) 联网，2026-06-24。用途：给我们 benchmark 对标学界标准、查漏补缺。所有数字带来源，未核实标 (未核实)/TODO。

## ⭐ 一句话结论

学界 neoantigen 免疫原性 benchmark 方法学三条核心规范：
1. **指标用 AUPRC + top-K 命中率(ISSR/PPV@K) 而非只看 ROC-AUC** —— 极端类不平衡下 ROC-AUC 误导。
2. **防泄漏要在 peptide-HLA 身份层去重 + 按患者/motif 分组切分，并显式量化与各工具训练集的 overlap**。
3. **阳性率要还原真实临床比例(~1–6% 阳性，1:20–1:50)**，不能用人为平衡集报喜。

真实性能天花板低（独立集 ROC-AUC 仅 0.52–0.65）= 行业共识，不是我们 benchmark 做错。

## 论文对照表

| 论文 | 比了哪些工具 | Ground truth | 评估指标 | 防泄漏 | 关键结论 |
|---|---|---|---|---|---|
| **TESLA** (Wells 2020 Cell) | 28 团队 pipeline | 9 患者 608 肽/37 真阳(~6.1%) | 验证候选排名/recall 75% | 未显式讨论泄漏 | 特征模型预测 75% 有效靶点、滤 98% 无效 |
| **Müller 2023 Immunity** | ML vs 常规特征 | 120+11 患者，178/1.78M 肽免疫原性(~0.01%) | (AUC 值正文 403 未核) | harmonized 统一重处理 | HLA presentation hotspot 位置等为新特征 |
| **IMPROVE** (Borch 2024 Front Immunol, 10.3389/fimmu.2024.1360281) | IMPROVE(RF) vs NetMHCpan/MixMHCpred/MHCflurry/PRIME 等 | 70 患者 17,520 候选/467 免疫原性(2.7%) | **AUPRC + ISSR top-X + AUC01(pAUC)** | **5 折 CV 按 neoepitope/motif/患者三重分组**；测试肽现于训练则剔除 | AUC 0.63；top-20 命中>2/3 患者 |
| **PredIG** (2025, 10.1186/s13073-025-01569-8) | vs NOAH/MHCflurry/NetMHCpan/PRIME/TLImm | 13,073 训练 pHLA；3 held-out | **AUPRC 为主 + ISSR + MCC/pAUC** | **held-out 不含训练 pHLA**；"epitope+4 位 HLA"去重；**显式承认 binding 预测器 pseudo-leakage 致 neoantigen ISSR 虚高** | ROC-AUC 不适合优先级排序，ISSR 更优 |
| **Comprehensive analysis** (2023, 10.3389/fimmu.2023.1094236) | NetMHCpan/MHCflurry/MixMHCpred/PRIME/DeepImmuno/DeepHLApan/CIImm | ITSNdb 199 肽(129 阳/70 阴,1.84:1)+模拟 7 阳/113 阴 | AUC(**0.52–0.60**)+DOP/F1/PPV/NPV | **未显式处理**(作者自提 DeepHLApan/DeepImmuno 可能 DB-bias) | DeepHLApan 综合最优；所有工具 AUC 仅 0.52–0.60；预测重叠极小 |
| **Beyond MHC binding** (2023, 10.37349/ei.2023.00091) | 30+ 工具四类 | in-house 94 肽(26 阳/68 阴)+CEDAR/NEPdb/IEDB；IFNγ ELISPOT | AUC(最高 **0.609**)+Pearson/Spearman(ELISPOT 值 vs 预测) | **显式量化 overlap**：与 DeepImmuno/DeepHLA 重叠 1%、NetCleave 4%；剔除后无实质变化 | 最高 AUC 0.6；binding 强度与响应幅度相关但不能预测有无 |
| **Schaap-Johansen 综述** (2021, 10.3389/fimmu.2021.712488) | 18 个 pipeline | 综述 | 指出工具混用 ACC/AUC 标准不一 | **强调 homology reduction 必要性** | 强 binding 是否=免疫原性存争议 |
| **Calis 2013** (IEDB Immunogenicity 内核) | 建 class-I 免疫原性预测器 | 2,509 肽 | 氨基酸位置富集 | (未核实) | NetTepi 沿用的 class-I 标准模型 |

## 标准方法学规范（学界共识提炼）

### 指标怎么选
- **AUPRC（PR-AUC）优先于 ROC-AUC**：极端不平衡(阳性 1–5%)下 ROC-AUC 严重高估；PredIG 明确以 AUCPR 为主优化指标。
- **top-K 命中率/筛选成功率最临床相关**：PredIG 的 **ISSR(Immunogenicity Screening Success Rate, ISSR10/25/…/1000) = 免疫原性肽排进 top-X 的比例**；IMPROVE 报 top-20 命中>2/3 患者。等价 PPV@top-K。
- **partial AUC(pAUC)/AUC at low FPR**：IMPROVE 报 AUC01(10% specificity 处)。
- **定量强弱**：少数论文做。Beyond MHC binding 用 **Pearson/Spearman 关联 ELISPOT 实测值与预测分**，是衡量定量响应幅度的标准做法。多数 benchmark 仍二分类。
- 辅助：MCC、F1、Sens/Spec/PPV/NPV、FPR/FNR。

### 防泄漏（最易被审稿人攻）四层
1. **peptide-HLA 身份层去重**：以 "epitope + 标准化 4 位 HLA" 拼接 key 去重(PredIG)。
2. **测试肽现于训练集则剔除**(IMPROVE)。
3. **按患者/motif 分组切分** + homology reduction(Schaap-Johansen，否则同源冗余致过拟合、性能虚高)。
4. **显式量化与各工具训练集 overlap 并报剔除前后差异**(Beyond MHC binding 逐工具报 1%/4%)。
5. **承认 pseudo-leakage**：即使比对集不在训练集，binding 预测器见过同源序列也使性能虚高(PredIG)。
> 反例：ITSNdb 未显式处理泄漏 = 方法学弱点，别照搬。

### 阳性/阴性比例
- 独立验证集**还原真实临床比例**(极不平衡)：IMPROVE 2.7%、TESLA 6.1%、PredIG ~4%、Müller ~0.01%。
- 训练集可平衡/欠采样但要在 CV fold 内做。
- **平衡 vs 不平衡集结论会翻转**(Comprehensive analysis 实证) → 只在平衡集报数会误导。

### Ground truth 标准
功能性 T 细胞实验(IFNγ ELISpot、barcoded multimer/tetramer、41BB/TNFα 染色)，非仅 binding。

### 行业共识（必引对标）
- 真实性能天花板低：独立 neoantigen 集 ROC-AUC 普遍 0.52–0.65。"AI 报 0.85–0.90"几乎都是 binding 任务非免疫原性。
- 存在 reproducibility crisis（训练偏差+缺标准化）。
- 工具间预测重叠极小，binding 强度与免疫原性无强共识。

## 对我们 benchmark 的改进建议
1. **主指标加 AUPRC + PPV@top-K（采 PredIG 的 ISSR 思路）**，ROC-AUC 只辅助。
2. **定量强弱**：有 ELISpot 数值就加 Spearman(预测分, ELISpot 实测)，对标 Beyond MHC binding —— 正是 QuantImmu 差异化卖点。
3. **防泄漏**（最易被攻）：peptide+4 位 HLA 去重；逐工具量化与各工具训练集 overlap%、报剔除前后性能差；声明 pseudo-leakage；有患者维度按患者分组。
4. **阳性率还原真实临床比例(1–6%)，同时报平衡集对照**。
5. ground truth 明确是功能 T 细胞验证、标注来源、是否 held-out。
6. related work/discussion 引 TESLA+IMPROVE+PredIG+Comprehensive+Beyond MHC binding 证明方法学对齐。

## TODO / 盲区
- Müller 2023 Immunity 正文 403，确切 AUC/切分细则未核（已确认核心：LOOCV on NCI-train→test NCI-test/TESLA/HiTIDE，top-20 命中 54.5/54.3/46.4%，统一重处理 harmonization）。
- ~~"neoantigen reproducibility crisis" 2025 Nature Cancer~~ → **见下回填：疑搜索模型幻觉，须替换**。
- ~~IMPROVE DOI 歧义~~ → **已确认（见下回填）**。
- 部分 AUC(BigMHC 0.70/NeoaPred 0.81)来自摘要聚合未核原表。

## ✅ 2026-06-24 文献深挖窗回填（researcher opus）
- **IMPROVE DOI 确认**：两个候选指**同一篇**，不矛盾。`10.3389/fimmu.2024.1360281`=正式 DOI；`PMC11021644`=同文 PMC ID。完整：Borch A, Hadrup SR 等,「IMPROVE: a feature model to predict neoepitope immunogenicity through broad-scale validation of T-cell recognition」, **Front Immunol 15, 2024-04-03, PMID 38633261**。GitHub github.com/SRHgroup/IMPROVE_tool。
- **🔴 "Nature Cancer 2025 reproducibility crisis" 疑似搜索模型幻觉**：3 次独立搜索反复出现相同概括句但**无可点击具体文章**，`site:nature.com` 搜不出。**引用前必须人工确认；建议从 related work 删除或替换**为真实可引证据：① TESLA 25 队普遍失败 + 6% 验证率 [10.1016/j.cell.2020.09.015]；② Buckley 2022「无工具显著超纯 MHC-presentation baseline」[10.1093/bib/bbac141]；③ Zhao 综述 2025「<half immunogenic peptides in top-20」[10.1093/bib/bbaf302]。这三条比那个幻觉更扎实。
- **复现性规范来源确认**：Zhao 2025 (10.1093/bib/bbaf302) 明确规范 = workflow manager(Snakemake/NextFlow) + 包管理器(bioconda/容器) + data provenance/portability/scalability/reentrancy。
- **评估协议九条 + 句子库**：见 `RELATED_WORK_draft.md` §4（cohort-level TTIF+FR+AUPRC、患者级 split+去重、LOCO、harmonization、还原真实阳性率 2-6%、AUPRC>AUROC 依据 Saito 2015 10.1371/journal.pone.0118432，含 2024 反方 arXiv 2401.06091 平衡陈述）。
- 本地 PDF：IMPROVE/Buckley/comprehensive/Saito2015 已下 `litlib/`。

## 关键引用

## 关键引用
- TESLA — cell.com/cell/fulltext/S0092-8674(20)31156-9
- IMPROVE — PMC11021644 / 10.3389/fimmu.2024.1360281
- PredIG — PMC12613480 / 10.1186/s13073-025-01569-8（ISSR + pseudo-leakage）
- Comprehensive analysis — 10.3389/fimmu.2023.1094236（AUC 0.52–0.60 天花板）
- Beyond MHC binding — 10.37349/ei.2023.00091（overlap 量化 + ELISpot 相关）
- Schaap-Johansen — PMC8479193（homology reduction）
