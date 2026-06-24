# 新抗原免疫原性 benchmark 数据集全景

> 服务项目 quantimmu-bench。检索 2026-06-24，researcher(opus) 联网普查。
> 核心用途：回答 QuantImmune 能否落地 **magnitude（强弱）回归** ——哪些公开数据集带定量 response 值可做回归 ground truth。
> 现状：本地仅 ELISpot Dataset1/Dataset2（DS2 仅 101 肽、11 阴性），样本量与连续标签都太薄，需外部源补强。

## ⭐ TL;DR（最关键）

- **绝大多数公开新抗原数据集 = 二元标签（immunogenic / non），不带连续 magnitude。** PRIME/NEPdb/dbPepNeo2/TANTIGEN/NeoTImmuML/harmonized 全 binary，只能做分类。
- **唯一系统性带「定量 magnitude」字段的公开源 = IEDB 及其癌症子库 CEDAR。** schema 明确同时记录 qualitative(pos/neg) 与 **quantitative(magnitude)**（ELISPOT SFC、% tetramer+、SI 等），可导出 → 做 magnitude 回归 GT 的**主力候选**。[CEDAR PMC9825495]
- **TESLA 原文有定量值**（per-peptide tetramer 频率/T cell fraction），但**不在简易表格公开下载**（测序在 Synapse、tetramer 需 MTA，二手库多降为 binary）。`TODO: TESLA per-peptide 连续值是否在可下载 mmc 表需核（Cell 正文 403）`。
- **IEDB overlap = benchmark 泄漏头号风险**：PRIME/NeoTImmuML/harmonized 几乎都从 IEDB 训练，测试集若也来自 IEDB → in-sample 泄漏，需 sequence-level 去重 + leave-study-out。

## 数据集对照表

| 数据集 | 来源 URL/DOI | 规模 | 标签类型 | 定量 magnitude? | 可及性 | HLA | IEDB overlap 风险 |
|---|---|---|---|---|---|---|---|
| **IEDB** | iedb.org / PMC6970984 | >2.2M epitopes | T/B cell assay，qual+quant | **是**(ELISPOT SFC/%tetramer/IFN-γ) | 公开免费(tcell_full_v3.csv) | 极广 | 自身即泄漏源 |
| **CEDAR**(IEDB 癌症库) | cedar.iedb.org / 10.1093/nar/gkac902 | 全部癌症 epitope | qual+quant | **是**(ELISPOT/ELISA/FACS) | 公开免费 | 广 | 与 IEDB 同源，高 |
| **TESLA** | Cell 2020 10.1016/j.cell.2020.09.015；Synapse | 608 肽/37 免疫原性(首批) | immunogenic/非 | **原文有**(tetramer 频率)；二手库降 binary | Synapse+MTA；定量需挖 mmc | 黑色素瘤+NSCLC | 中 |
| **NEPdb** | nep.whu.edu.cn / 10.3389/fimmu.2021.644637 | 17,549 验证 neo-epitope | T-cell activation 分类 | **否** | 公开免费 | I+II | 中 |
| **dbPepNeo2.0** | biostatistics.online/dbPepNeo2 / 10.3389/fimmu.2022.855976 | 801 HC+842k LC+630 TCRβ | MS/immunoassay binary | **否** | 公开免费 | I+II | 中 |
| **TANTIGEN 2.0** | projects.met-hilab.org/tadb / 10.1186/s12859-021-03962-7 | 4,296 变体/>1500 表位 | 4 级序数 | **否**(序数非连续) | 公开免费 | 15 常见 | 中 |
| **PRIME 训练集** | github.com/GfellerLab/PRIME / 10.1016/j.xcrm.2021.100194 | 596 正+6,084 负 | binary | **否** | repo 公开 | 偏高频 HLA-I | **高**(直接取 IEDB tcell_full_v3) |
| **harmonized (Immunity 2023)** | 10.1016/j.immuni.2023.09.002 | 120+11 患者；1.78M 肽，178 免疫原性 | binary | **否** | resource 公开 | 广 | 中高 |
| **NeoTImmuML/TumorAgDB2.0** | 10.3389/fimmu.2025.1681396 | 5156 正/5156 负；TumorAgDB 187,223 | binary | **否** | 库公开 | 广 | 高（其用序列去重防泄漏，可参照） |
| **VDJdb** | github.com/antigenomics/vdjdb-db / 10.1093/nar/gkx760 | TCR-pMHC 十万级 | TCR 特异性 | **否**(非肽强弱) | 公开免费 | 部分 | 中 |
| **McPAS-TCR** | friedmanlab / Bioinformatics 2017 | 病原/疾病 TCR | TCR 特异性 | **否** | 公开免费 | 有 MHC 注释 | 中 |
| **ITSNdb** | Front Immunol 2023 10.3389/fimmu.2023.1094236 | 199 肽(129 阳/70 阴) | binary | **否** | 公开 | I | 文献策展 |
| **NeoPepDB** | `TODO 唯一官方 URL/DOI 未定(与 NEPdb/Neodb 同名混淆)` | TODO | TODO | TODO | TODO | TODO | TODO |

## 定量 ground truth 专节（袁 QuantImmune 落地命门）

### ✅ 带定量 magnitude，可作回归 GT 的候选
1. **IEDB（含 CEDAR）— 当前唯一系统性公开源**。schema 明确 qualitative+quantitative；T cell assay 含 ELISPOT(SFC)/ELISA/FACS。可导出连续量做回归。
   - ⚠️ 坑：assay 异质（不同实验室 SFC 不可比、未归一化）、阈值/稀释不统一、缺背景扣减 → raw SFC 跨研究回归噪声极大，需按 assay 类型分层 + 研究内归一化（工程难点，非拿来即用）。
   - ⚠️ 是多数工具训练源 → benchmark 必须 leave-study-out / 序列去重防泄漏。
2. **TESLA — 原文有定量，获取门槛高**。barcoded tetramer 逐肽频率/T cell fraction（真按强弱排序的金标准设计）。`TODO: fetch Cell mmc 补充 Excel 确认 per-peptide 定量列；正文 403 未直接核`。

### ❌ 仅 binary/序数，做不了 magnitude 回归
PRIME 训练集、NEPdb、dbPepNeo2、harmonized、NeoTImmuML/TumorAgDB（全 binary）；TANTIGEN（4 级序数）；VDJdb/McPAS（TCR 配对非肽强弱）。

### 结论对袁项目意义
- 能落地 magnitude 回归 GT 的现实路径只两条：①IEDB/CEDAR 导出 quantitative T cell assay（量大但脏，需重建归一化 pipeline）；②TESLA 逐肽 tetramer（干净但量小、需 Synapse/MTA+补充表核实）。
- 本地 DS1/DS2 的 SFC 是稀缺定量资产，但 DS2 仅 101 肽不够训/评回归。
- **建议优先核实 IEDB/CEDAR quantitative 导出可行性 + TESLA 补充表**，再判 magnitude 回归是否有足够 GT。若 IEDB quantitative 字段实际填充稀疏/TESLA 表不含连续值 → 退守「序数强弱分级」或自补 ELISpot。

## ⚠️ 未解 TODO
1. TESLA 补充 Excel（mmc7.xlsx 等）是否含 per-peptide 连续 tetramer 频率列 — Cell 正文 403 未核 → **仍未核（见下回填，Cell 全 403）**。
2. IEDB/CEDAR tcell_full 的 quantitative magnitude 列**实际填充率**（很多记录可能只 pos/neg）— 决定能否真做回归 → **无现成统计，须自测（见下回填）**。
3. ~~NeoPepDB 唯一官方 URL/DOI 未定~~ → **已消歧：NeoPepDB 不存在，=NEPdb 笔误（见下回填）**。

## ✅ 2026-06-24 文献深挖窗回填（researcher opus）
- **NeoPepDB 消歧**：精确搜 `"NeoPepDB"` 全跳 NEPdb → 几乎确定是 **NEPdb** 笔误。NEPdb = Xia et al. **Front Immunol 2021, DOI 10.3389/fimmu.2021.644637, PMID 33927717, PMCID PMC8078594**，官方 http://nep.whu.edu.cn/（武大），17,549 条（173 免疫原+17,376 无效）+ pan-cancer 预测，**标签=二元(P/N)，无连续定量分**。同名易混：NEPdb ≠ Neodb ≠ dbPepNeo/dbPepNeo2.0(10.3389/fimmu.2022.855976) ≠ TSNAdb ≠ TumorAgDB。主流库基本全二元，连续定量标签是公认稀缺点。
- **TESLA 连续值（仍未核到下载位）**：确认 Wells et al. Cell 2020 (10.1016/j.cell.2020.09.015) 报了 per-peptide tetramer 频率（连续值），数据 Synapse syn21048999；正文引 Table S1/S2/S3/S5。但 **Cell/ScienceDirect/Synapse 全程 403/JS 墙，未能核实哪个补充表含连续列、列名、是否需 MTA**。下游所有引 TESLA 的工具（Buckley/NeoFox/NeoTImmuML）**都只用二元标签** → 这本身是「连续标签事实上不可得/未被使用」的可写证据点。**数据集表勿写具体 mmc 文件名/列名（=臆造）。**
- **CEDAR/IEDB 定量填充率**：无公开统计可引。若写须自测（下 tcell_full_v3.csv 统计 "Quantitative measurement" 列非空比例）。
- 本地 PDF：NEPdb / Buckley / comprehensive(realistic-imbalance) 已下 `litlib/`。

## 关键引用

## 关键引用
- CEDAR — PMC9825495 / 10.1093/nar/gkac902 — "qualitative (positive/negative) and quantitative (magnitude) terms"
- IEDB program — PMC6970984 — ELISPOT 量化频率
- TESLA — 10.1016/j.cell.2020.09.015 — barcoded tetramer 逐肽频率，数据 Synapse+MTA
- PRIME 训练集 — github.com/GfellerLab/PRIME / 10.1016/j.xcrm.2021.100194 — 596/6084 binary + IEDB 衍生（泄漏铁证）
- NeoTImmuML/TumorAgDB2.0 — 10.3389/fimmu.2025.1681396 — 序列去重防泄漏可参照
