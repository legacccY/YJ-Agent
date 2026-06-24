# 新抗原免疫原性预测工具全景普查 + 定量 SOTA 撞车扫描

> 服务项目 quantimmu-bench（袁老师癌症新抗原疫苗 benchmark）。检索日期 2026-06-24。
> 来源：researcher×2（opus）联网普查，内置 WebSearch + WebFetch 官方 repo/paper 交叉验证（Firecrawl 额度爆 402）。
> 核心用途：①扩展可进 benchmark 的工具池（超出已部署 10 个）②回答 QuantImmune 做「定量强弱(response magnitude)预测」是否撞车。

---

## ⭐ 一句话核心结论（最关键）

**多源独立证据：当前主流/SOTA 新抗原免疫原性工具几乎全部是二分类（immunogenic vs non），没有一个被明确设计为预测 T 细胞 response magnitude（连续强弱回归 / 对 ELISpot SFC 量级做回归）。** 一篇 2024 专题综述直接下结论：
> "No tool in this review was explicitly developed to predict T cell response magnitude. All tools perform binary classification. Magnitude prediction remains an unaddressed gap."
> — explorationpub, Exploration of Immunology 2024, Article 100391（DOI 10.37349/ei.2023.00091）

→ **QuantImmune 的定量 magnitude 方向不撞车，是公认空白（蓝海）。** 撞车风险与必须设的对照 baseline 见末节。

---

## 一、工具对照表（超出已部署 10 个）

| 工具 | repo / paper (DOI) | 年份 | 预测什么 | 定量强弱? | 输入(肽长/HLA/测序) | 输出 | 许可 | 进 ELISpot benchmark? | 部署难度 |
|---|---|---|---|---|---|---|---|---|---|
| **BigMHC** (EL+IM) | github.com/KarchinLab/bigmhc · Nat Mach Intell 2023, 10.1038/s42256-023-00694-6 | 2023 | EL=presentation；IM=immunogenicity（迁移学习） | ❌ 二分（连续分仅排序） | 肽 8mer+；HLA 模糊匹配；不需测序 | CSV 连续 score(0-1) | 学术[TODO 核] | ✅ apples-to-apples | 中（PyTorch，下权重） |
| **MHCflurry 2.0** | github.com/openvax/mhcflurry · Cell Systems 2020, 10.1016/j.cels.2020.06.010 | 2020 | binding affinity + presentation | ❌ BA 是结合强度(nM)非 response | 肽 8-15mer；14,993 alleles；不需测序 | BA(nM)、PS、%Rank | Apache 2.0 | ⚠️ proxy（只到 presentation） | 低（pip 成熟） |
| **PRIME 2.1** | github.com/GfellerLab/PRIME · Cell Systems 2023, 10.1016/j.cels.2023.01.001 | 2023/25 | immunogenic epitope（binding+TCR） | ❌ README 明确「非 quantitative response magnitude，是 ranking metric」 | 肽 8-14mer；HLA 多格式；不需测序 | %Rank + Score | 学术免费/商用需授权 | ✅（已部署在 8tools 表） | 低 |
| **ICERFIRE** | DTU web ICERFIRE-1.0 · NAR Cancer 2024, 10.1093/narcancer/zcae002 | 2024 | neo-epitope immunogenicity | ❌ 90 RF 二分；**主动把量级标签塌缩成二分** | 肽 8-12mer；全分辨率 HLA；需 mut+WT，表达可选 | 二分+百分位 rank | CC-BY 4.0 | ✅（需 WT 配对） | 中（DTU，NetMHCpan 依赖） |
| **Repitope** | github.com/masato-ogishi/Repitope · Front Immunol 2019, 10.3389/fimmu.2019.00827 | 2019 | immunogenicity（TCR-peptide CPP） | ⚠️ 自称 quantitative 但实为概率非 magnitude 回归 | MHC-I&II 肽；R 包；不需测序 | 免疫原性概率分 | 开源[TODO 核] | ⚠️ proxy | 高（R 包，重） |
| **NeoaPred** | github.com/Dulab2020/NeoaPred · Bioinformatics 2024, 10.1093/bioinformatics/btae547 | 2024 | immunogenic（pHLA 结构 foreignness） | ❌ 二分(AUROC 0.81) | mut+WT 肽；需建 pHLA 结构 | foreignness score+二分 | Apache 2.0 | ⚠️ 重（需结构） | 高（GPU+结构管线） |
| **DeepNeo/v2** | deepneo.net · NAR 2023, 10.1093/nar/gkad275 | 2023 | binding+immunogenicity | ❌ 二分 | 肽+MHC(I/II)；web | 预测 score | web[TODO] | ⚠️ proxy（web only 难批量） | 中-高 |
| **Seq2Neo** | github.com/XSLiuLab/Seq2Neo · IJMS 2022, 10.3390/ijms231911624 | 2022 | 全管线 CNN immunogenicity | ❌ CNN 二分 | 原始测序/肽；**需测序**（全管线） | 候选肽+免疫原性分 | AFL v3.0 | ⚠️ CNN 可抽出 apples | 高（重管线） |
| **ImmunoStruct** | github.com/KrishnaswamyLab/ImmunoStruct · Nat Mach Intell 2025, 10.1038/s42256-025-01163-y | 2025 | 多模态(序列+结构+生化) class-I | ❌ 二分（强分离） | 肽+MHC；限 27 HLA；需结构 | 免疫原性 score | 开源[TODO] | ⚠️ 限 27 HLA+需结构 | 高（多模态 GPU） |
| **diffRBM (TLImm)** | eLife 2023, 10.7554/eLife.85126 | 2023 | immunogenicity+TCR specificity | ❌ 二分判别 | 肽序列；TCR | 判别分 | [TODO] | ⚠️ proxy | 高（RBM 研究码） |
| **IEDB Immunogenicity (Calis)** | tools.iedb.org/immunogenicity · PLoS CB 2013, 10.1371/journal.pcbi.1003266 | 2013 | T 细胞 immunogenicity propensity | ❌ 单分数(符号判向)非量级 | 肽 9-11mer 优；HLA 可选 | 单一分数 | IEDB 免费 | ✅ 最轻量 baseline | 低 |
| **NetTepi** | DTU NetTepi-1.0 · Immunogenetics 2014, 10.1007/s00251-014-0779-0 | 2014 | T 细胞 epitope(BA+stab+Calis 加权) | ❌ 加权和排序 | 肽+HLA | 综合分 | DTU 学术 | ✅ 经典 baseline | 低 |
| **NetMHCpan 4.1** | DTU · NAR 2020, 10.1093/nar/gkaa379 | 2020 | binding affinity + EL presentation | ⚠️ BA 连续(nM)但是结合强度非免疫原性 magnitude | 肽 8-14mer；任意 HLA-I | BA/EL SCO+RNK | DTU 学术 | ⚠️ proxy/baseline | 低（成熟） |
| **neoIM** | Immunity 2023, 10.1016/j.immuni.2023.09.002 | 2023 | CD8 T 细胞 immunogenicity | ❌ RF classifier（ELISpot 仅作验证标签） | MHC-presented 肽(n=61,829 训练) | 二分 | [TODO repo] | ✅ 专为 ELISpot 类设计，最相关 baseline | 中 |
| **T-SCAPE** | github.com/seoklab/T-SCAPE · Science Adv 2025, sciadv.adz8759 | 2025 | T cell activation(多域 binding+TCR+activation) | ❌ 概率分阈值 0.5 二分 | 肽-MHC | 免疫原性概率 | 开源 | ✅（2025 最接近功能反应的 SOTA） | 中-高 |

---

## 二、定量工具专节（撞车判断核心）

### 真做 response magnitude 连续回归的工具 = **0 个（查无明确证据）**

逐一核验每个声称「quantitative」的工具，都不是对 T 细胞反应强弱(magnitude)做回归：

1. **explorationpub 2024 综述（最强直接证据）**：明确比对 NetMHCpan/MHCflurry/IEDB Immunogenicity/PRIME/DeepImmuno/DeepHLApan/INeo-Epp 等，结论 "magnitude prediction remains an unaddressed gap"，并呼吁 "it could be of value to work on quantitative data, allowing to rank peptides within different degrees of immunogenicity"。
2. **ICERFIRE（看似最该做量级却没做）**：原作者主动 "all the labels for a given Peptide-HLA pair were collapsed into a single class label"。
3. **neoIM（专为 ELISpot 设计但仍分类）**：RF classifier，IFN-γ ELISpot 只作 ground-truth 验证。
4. **PRIME 2.1（官方 README 自我否认）**："The score is not a calibrated probability or quantitative response magnitude—it's a ranking metric"。
5. **Repitope（措辞陷阱）**：自称 "quantitative" 指免疫原性概率连续值，非实测 response magnitude 回归。
6. **T-SCAPE 2025（最接近但仍二分）**：整合 binding+TCR+activation 多域，但输出仍是 activation 概率阈值 0.5 二分。

### 容易被误认「定量」但实为别量纲

- **NetMHCpan BA / MHCflurry BA**：连续 nM 是**结合亲和力强度**，不是**免疫原性反应强弱**，量纲不同。综述实测 binding 与 ELISPOT 量级仅弱正相关（NetMHCpan 4.0 Pearson r=−0.399、MHCflurry r=0.38，全集无显著关联），仅作 proxy baseline。
- **pMTnet（TCR-pMHC）**：输出连续结合强度 percentile，但靶的是 TCR-pMHC 结合强度，非群体 T 细胞反应 SFC/频率，概念不同。

---

## 三、撞车结论（给主线拍板）

- **QuantImmune 若做「对 ELISpot/IFN-γ T 细胞反应强弱做连续回归」→ 查无直接撞车工具，是公认未填补空白**（综述明说 "unaddressed gap"）。🟢 不撞车 / 蓝海为主。
- **需警惕的「近邻」**：
  - (a) neoIM/ICERFIRE 拥有量级标签数据却选择做分类 → 说明数据存在但没人做回归，QuantImmune 可正面切入。
  - (b) **binding 类工具(NetMHCpan/MHCflurry BA)的连续输出会被审稿人当「已有定量 baseline」质疑** → QuantImmune 必须证明对 ELISpot 量级的回归**显著优于 binding affinity proxy**。这是最可能的撞车攻击点，**建议设为对照 baseline**。
  - (c) **差异化必须落在「真连续 magnitude 标签 + 报告 r/ρ/MAE」**，否则退化成又一个二分类，失去与 T-SCAPE/NeoTImmuML 的区隔。

**操作建议**：把标 ✅ apples-to-apples 的 7 个工具（BigMHC、PRIME、ICERFIRE、IEDB Immunogenicity、NetTepi、neoIM、NetMHCpan）优先纳入扩展 benchmark；NetMHCpan/MHCflurry BA 连续输出必设为 magnitude 回归的对照基线。

---

## ⚠️ 盲区 / TODO（不臆想）

- 2025-2026 极新预印本可能有遗漏的 magnitude 工具（Firecrawl 额度爆未深扫全文）；已命中 ImmunoNX(arXiv 2512.08226)、Genes&Immunity 2025 综述（登录墙挡）待人工复核。
- ~~neoIM / diffRBM(TLImm) / DeepNeo 确切 GitHub URL+许可未命中~~ → 见下「2026-06-24 回填」。
- ~~BigMHC/Repitope/ImmunoStruct 确切 LICENSE 条款未逐一核到~~ → 见下「2026-06-24 回填」。

## ✅ 2026-06-24 文献深挖窗回填（researcher opus 逐一核 LICENSE 原文 + GitHub API）

**重大纠正**：旧表把 neoIM 挂 Immunity DOI `10.1016/j.immuni.2023.09.002` 是**两篇混淆**。
- 该 Immunity DOI = **Müller et al.「ML methods & harmonized datasets improve immunogenic neoantigen prediction」**（Swiss Inst Bioinformatics/Ludwig，CC BY-NC 4.0），**不是** neoIM。
- **neoIM** = **myNEO Therapeutics bioRxiv 预印本**（10.1101/2022.06.03.494687，**专利 EP4229640，专有，无公开 repo → 不可纳入 benchmark**）。

| 工具 | 确切 repo | 许可（核 LICENSE 原文） | 可下? | 进 benchmark? |
|---|---|---|---|---|
| Repitope | github.com/masato-ogishi/Repitope | **MIT** | ✅ R 包 | ✅ 完全开放，可再分发 |
| NeoaPred | github.com/Dulab2020/NeoaPred | **Apache-2.0** | ✅ 代码+权重+Docker | ✅ 完全开放 |
| BigMHC | github.com/KarchinLab/bigmhc | 学术非商用（自定义，§1 显式禁商用，SPDX=NOASSERTION） | ✅ 权重 | ✅ 学术可，商用需联系 Karchin Lab |
| ImmunoStruct | github.com/KrishnaswamyLab/ImmunoStruct | Yale 非商用（商用需 Yale Ventures；衍生须回传） | ✅ HF 权重 | ✅ 学术可，**需结构输入(AF2 PDB→图，重)**；27-HLA 限制 README 未证实=TODO |
| diffRBM/TLImm | github.com/cossio/diffRBM ＋ github.com/bravib/diffRBM_immunogenicity_TCRspecificity | cossio=自定义「非商用」；bravib 应用库=**无 LICENSE 文件** | ✅ 代码+模型（重训需 IEDB tcell_full_v3） | ✅ 学术非商用 OK |
| T-SCAPE | github.com/seoklab/T-SCAPE | **冲突**：repo LICENSE 文件=CC0-1.0 但 README 写 CC BY-NC-ND 4.0 → 按更严 ND 走 | ✅ 代码+HF 权重 | ⚠️ ND 禁衍生可能限改装，建议 issue 问作者 |
| DeepNeo/v2 | github.com/kaistomics/DeepNeo（含可本地批量代码，非仅 web）+ deepneo.net | **无 LICENSE 文件**（默认 all-rights-reserved） | ✅ 代码 | ⚠️ 再分发输出法律不明，需联系作者 |
| neoIM | 无公开 repo | 专利 EP4229640，专有 | ❌ | ❌ 不可纳入 |

许可分级（影响能否在论文再分发其输出）：**完全自由**=Repitope(MIT)/NeoaPred(Apache)；**学术 OK 商用需授权**=BigMHC/ImmunoStruct/diffRBM(cossio)；**不明/冲突需问作者**=DeepNeo/T-SCAPE；**不可纳入**=neoIM。

残留 TODO（未核到，不臆想）：Müller Immunity 2023 确切 code/data repo URL（STAR Methods 403）；neoIM code-availability 原句（bioRxiv 全文 403）；ImmunoStruct 27-HLA 限制确切数字；T-SCAPE 双许可冲突权威解释；NeoaPred Bioinformatics 2024 确切 DOI（疑 10.1093/bioinformatics/btae547 或 btae741，未逐字核）。

## 关键引用
见上表 DOI 列；撞车判断核心证据 = explorationpub 2024 (10.37349/ei.2023.00091) "magnitude prediction remains an unaddressed gap"。

## 关键引用
见上表 DOI 列；撞车判断核心证据 = explorationpub 2024 (10.37349/ei.2023.00091) "magnitude prediction remains an unaddressed gap"。
