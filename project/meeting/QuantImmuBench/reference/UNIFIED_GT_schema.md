# 跨数据集统一 GT schema 草案 + 泄漏标注 + train/test/held-out 划分

> 服务 quantimmu-bench 数据组（支援王子源/谢孟翰）。2026-06-24 数据组窗。所有规模/字段/重叠数 = 主线 + opus analyst/verifier 实测**已下原文件**（非页面声明），命令可复现。caveman OFF。
>
> 配套：`DATA_INVENTORY_download.md`（下载清单+状态）· `PHASE0_iedb_fillrate_MEASURED.md`（magnitude 命门实测 FAIL）· `LANDSCAPE_datasets.md`（全景）· `BENCHMARK_METHODOLOGY.md`（防泄漏学界规范）。
> 已下文件根：`project/meeting/QuantImmuBench/data/external/`

---

## 0. 一句话结论（给王子源/谢孟翰/袁老师）

1. **连续 magnitude 回归 GT 在公开源里证伪（命门 FAIL）**：IEDB 肿瘤子集 functional 连续值正例仅 6 条/3 study（判据 ≥10³），TESLA 也是 binary（37 正）。详见 `PHASE0_iedb_fillrate_MEASURED.md`。→ benchmark 监督信号现实只有 **binary + 序数三档 + 响应频率**，不是连续强弱。
2. **统一 schema 用「一肽一 HLA 一标签一来源」长表**（见 §2），多源标签语义不同（binary / 序数 / 患者应答 / TCR confidence）必须分列存，**禁混成一个 label**。
3. **泄漏极重**：几乎所有公开集都从 IEDB 衍生或与之高度重叠（实测 ITSNdb 92% 肽现于 IEDB、PRIME 60% 现于 IEDB）。肽级去重远不够，必须 (肽+4 位 HLA) key + leave-study-out + 承认 pseudo-leakage。真正干净 held-out 只剩**袁老师本地 ELISpot DS1/DS2**（需单独核是否撞 IEDB）+ TESLA（部分独立）。

---

## 1. 已下数据集实测台账（字段 = verifier 核原文件）

| 数据集 | 文件 | 肽列 | HLA列 | 标签列 + 实测分布 | 定量? | 行数 | 唯一肽 |
|---|---|---|---|---|---|---|---|
| **IEDB tcell_full_v3** | `tcell_full_v3.csv` (1.3G) | `Epitope/Name`(idx11) | MHC 段 | `Qualitative Measurement`(idx122): Neg 361572 / Pos 182923 / Pos-Low 17985 / Pos-High 5813 / Pos-Int 5116 | **是但稀疏**(`Quantitative measurement` 填充 1.01%，71% 是 binding 非 functional) | 573409 | 167673 (8-15mer 线性) |
| **ITSNdb** | `ITSNdb/data/ITSNdb.csv` | `Neoantigen` | `HLA`(31种) | `NeoType`: Positive 129 / Negative 70 | 否 | 199 | 197 |
| **ITSNdb-TNB** | `ITSNdb/data/TNB_dataset.csv` | `Neoantigen` | `HLA` | `Response`(⚠️**患者层临床应答**R/NR/DCB/NDB/LB/NB 多体系混编，**非肽级免疫原性**) | 否 | 99480 | — |
| **ITSNdb-Val** | `ITSNdb/data/Val_dataset.csv` | `Neoantigen` | `HLA` | `Origin`(⚠️**变异来源**SNV/Fusion，**非免疫标签**) | 否 | 120 | — |
| **PRIME 训练集** | `PRIME/TableS4.xlsx` | `Mutant` | `Allele` | `Immunogenicity`×`Random`: (1,0)=596 真阳 / (0,0)=6084 真阴 / (0,1)=**58905 random 负** | 否 | 65585 | 63494 |
| **PRIME benchmark** | `PRIME/TableS3.xlsx` | `Sequence` | sheet名=患者/HLA | `Ligand`(每 sheet 1列，HLA-I 配体) | 否 | 多 sheet | — |
| **VDJdb** | `vdjdb/.../vdjdb.slim.txt` (406M) | `antigen.epitope` | `mhc.a`/`mhc.b` | `vdjdb.score`(TCR confidence 0-3，**非免疫原性强弱**): 0=183663/1=7485/2=2736/3=3845 | 否 | 197729 | 2068 |
| **dbPepNeo2 补充** | `dbPepNeo2_Table1.xlsx` | `Amino acid`/`mutated Peptide` | `HLA allele` | (113 候选肽论文补充，**非全库 HC/LC**) | 否 | 116 | — |

### ⚠️ 三个口径坑（writer/实验前必锁）
1. **PRIME 负样本**：596:6084（真阴）vs 596:64989（含 58905 random decoy）差一个量级。入 tex/实验前明确取哪种负样本。学界标准做法 = 用真阴 6084 报主结果，random 仅作额外 hard-negative。
2. **ITSNdb 只有 `ITSNdb.csv`(199) 是肽级 binary GT**。TNB(99480)/Val(120) 标签语义不同（患者应答 / 变异来源），**不可当 ITSNdb 同类 binary 用**。
3. **VDJdb 是 TCR 维度**，`vdjdb.score` 是录入可信度不是肽强弱，仅 TCR-pMHC 扩展用，不进肽免疫原性 benchmark 主表。

---

## 2. 统一 GT schema（长表，一行 = 一肽×一 HLA×一来源记录）

设计原则：**多源异构标签不可压成单一 label**——binary / 序数 / 连续 / 响应频率 / 患者应答各占独立列，缺失填 null。dedup/泄漏检测用 `pep_key`。

| 字段 | 类型 | 说明 | 缺失策略 |
|---|---|---|---|
| `peptide` | str | 突变肽序列，大写 AA，无修饰，8–25mer | 必填 |
| `peptide_wt` | str | 对应 WT 肽（ITSNdb 有 `WT` 列；多数源 null） | null |
| `hla` | str | 规范化 `HLA-A*02:01`（见 §3 规则） | 必填 |
| `hla_class` | str | `I` / `II` | 推断 |
| `pep_key` | str | dedup/泄漏 key = `peptide + '|' + hla_4digit`（PredIG 规范） | 派生 |
| `label_binary` | int | 1=immunogenic / 0=non / null=未知 | null |
| `label_ordinal` | int | 0=neg,1=low,2=intermediate,3=high（IEDB Positive-High/-Int/-Low 映射） | null |
| `magnitude_value` | float | 连续响应值（SFC/%tetramer/SI）——**极稀疏，多数 null** | null |
| `magnitude_unit` | str | `SFC` / `pct_tetramer` / `SI` / `IFNg_pg_ml` | null |
| `magnitude_assay` | str | `ELISPOT`/`tetramer`/`ICS`/`ELISA` | null |
| `resp_tested` | int | 受试者数（IEDB `Number of Subjects Tested`） | null |
| `resp_positive` | int | 阳性受试者数（`Number of Subjects Positive`） | null |
| `resp_freq` | float | 响应频率 %（IEDB `Response Frequency (%)`） | null |
| `source_dataset` | str | `IEDB`/`ITSNdb`/`PRIME`/`TESLA`/`VDJdb`/`NEPdb`/`local_elispot_ds1`… | 必填 |
| `source_study_id` | str | PMID / 患者 / cohort —— **leave-study-out 切分键** | 尽量填 |
| `disease` | str | 癌种 / 病原（IEDB `Disease`） | null |
| `is_neoantigen` | bool | 肿瘤突变 neoepitope=True，病原/自身=False | 推断 |
| `iedb_leak` | bool | `pep_key` 是否撞 IEDB（派生，见 §4） | 派生 |
| `prime_train_leak` | bool | 是否撞 PRIME 训练集（派生） | 派生 |
| `note` | str | 口径备注（random negative / 患者层标签 / pseudo-leak …） | null |

> magnitude_* 三列保留是为「万一袁老师自补 ELISpot 产连续 GT」时直接落位；公开源现状几乎全 null（命门 FAIL 的直接体现）。

### 各源 → schema 映射要点
- **IEDB**：`Epitope/Name`→peptide；MHC 段→hla；`Qualitative Measurement`→label_binary(Positive*→1,Negative→0)+label_ordinal(High/Int/Low)；`Quantitative measurement`+`Units`+`Method`→magnitude_*（仅 functional assay 子集，剔 binding IC50）；`Number Tested/Positive`/`Response Frequency`→resp_*；`PMID`→source_study_id；`Disease`→disease/is_neoantigen。
- **ITSNdb**：`Neoantigen`→peptide，`WT`→peptide_wt，`HLA`→hla，`NeoType`→label_binary，`Paper`/`Author`→source_study_id，全 is_neoantigen=True。
- **PRIME TableS4**：`Mutant`→peptide，`Allele`→hla，`Immunogenicity`→label_binary，`Random`==1→note='random_negative'（默认**排除** random 行或单独标）。
- **VDJdb**：`antigen.epitope`→peptide，`mhc.a`→hla，**不产 label_binary**（仅 TCR 维度，note='tcr_pmhc_only'）。
- **dbPepNeo2/NEPdb/harmonized**（待补全下载后）：按各自肽/HLA/标签列同法映射。

---

## 3. HLA 规范化规则（跨源对齐 + dedup 前提）

各源 HLA 写法不一（`HLA-A02:01` / `HLA-A*02:01` / `A*0201` / `HLA-B27:05`）。统一到 **`HLA-{gene}*{NN}:{NN}`**：
1. 去前缀大小写差异，统一加 `HLA-`。
2. gene 后补 `*`（`A02:01`→`A*02:01`）。
3. 等位基因数字补冒号（4 位 `0201`→`02:01`）。
4. `hla_4digit` = 取前两组（field1:field2），抹掉 6/8 位后缀做 dedup key。
5. 无法解析（仅 supertype / 空）→ hla=null，标 note，不进 pep_key dedup。

> 实测注意：ITSNdb 用 `HLA-B27:05` 紧凑式、PRIME `Allele` 用 `A0201` 式、IEDB 用全称——loader 必须先全部过规范化再 join，否则 overlap 会被低估。

---

## 4. 泄漏 / overlap 实测（split plan 的硬地基）

**已实测（命令见 §6）**：

| 比对 | 重叠（肽级） | 比例 | 含义 |
|---|---|---|---|
| ITSNdb(197) ∩ IEDB(167673) | **181** | **92%** | ITSNdb 几乎全部肽现于 IEDB（文献策展同源） |
| ITSNdb(197) ∩ PRIME 真训练肽(6387) | **114** | **58%** | ITSNdb 对 PRIME 不是干净 held-out |
| PRIME 真训练肽(6387) ∩ IEDB | **3845** | **60%** | 坐实 PRIME 衍生自 IEDB（头号泄漏源） |

> ⚠️ 这是**肽-only**重叠（未配 HLA），是泄漏上界。按 (肽+HLA) key 配后会降，但 ITSNdb 92% 已说明肽层几乎全暴露——pseudo-leakage（binding 预测器见过同源序列）几乎不可避免。

**泄漏层级（学界共识，`BENCHMARK_METHODOLOGY.md` §防泄漏四层）**：
- IEDB = 头号源；PRIME/NEPdb/harmonized/NeoTImmuML 全部分或全部从 IEDB 训练。
- 工具自身训练集：DeepImmuno/PRIME/IMPROVE 等训练肽与测试集撞 → in-sample 虚高。
- 必做：(肽+4 位 HLA) 去重 + 逐工具量化 overlap% + 报剔除前后 AUC 差（已有脚本 `analysis/iedb_overlap_check.py`，现可喂真 IEDB csv 跑）。

---

## 5. 推荐 train / test / held-out 划分

**现实约束**：①连续 magnitude GT 不存在（命门 FAIL）②几乎全集撞 IEDB ③真正独立的临床功能验证集稀缺。

### 划分方案（binary + 序数，非连续）
| 角色 | 数据集 | 理由 | 防泄漏处理 |
|---|---|---|---|
| **主测试（primary held-out）** | 袁老师本地 **ELISpot DS1/DS2** | 项目自有功能验证、连续 SFC、最可能不在公开训练池 | 跑 `iedb_overlap_check.py` 核 DS1/DS2 肽 vs IEDB，剔除撞的再报 |
| **独立 held-out 补充** | **TESLA**(37 正/571 负) + **ITSNdb 干净子集** | TESLA 单 consortium 相对独立；ITSNdb 去掉撞 PRIME/IEDB 的 114+ 肽后剩干净肽 | ITSNdb 实际只剩 ~16 肽不撞 IEDB → 太薄，主要靠 TESLA + 本地 |
| **训练/参考（不可当测试）** | PRIME TableS4(596/6084) + IEDB 衍生 | 这些是工具训练源，报在测试集上=泄漏 | 仅作训练或 leave-study-out 的 in-pool |
| **TCR 扩展（独立维度）** | VDJdb | 不进肽 binary 主表 | — |

### 切分协议（套 PredIG/IMPROVE 规范）
1. **dedup**：全集按 `pep_key`(肽+4 位 HLA) 去重，重复保留信息最全的一条。
2. **leave-study-out**：按 `source_study_id`(PMID/患者) 分组切，同一 study 的肽不跨 train/test（避免同源冗余虚高）。
3. **量化 overlap**：测试集每条对每个工具训练集报 overlap%，主结果同时报「全测试集」与「剔 overlap 后」两版 AUC。
4. **阳性率还原临床**：测试集保持真实 1–6% 阳性比例（ITSNdb 是人为 1.84:1 平衡集，会高估，需还原或并报）。
5. **指标**：AUPRC + PPV@top-K(ISSR) 为主，ROC-AUC 辅助（极端不平衡下 ROC 误导）。
6. **承认 pseudo-leakage**：在 discussion 显式声明 binding 预测器见过同源序列致性能虚高（ITSNdb 92% 撞 IEDB 是直接证据）。

### 一句话给数据组
> 别指望找到「干净大独立测试集」——公开源全撞 IEDB。**可信路径 = 以袁老师本地 ELISpot 为主测试 + TESLA 补充独立性 + 全程 leave-study-out + 逐工具 overlap 报剔除前后**。这正是 PredIG/IMPROVE 的做法，方法学站得住。

---

## 6. 复现命令（关键数字）

```bash
cd project/meeting/QuantImmuBench/data/external
# IEDB 行数 + 标签分布
python -c "import csv;f=open('tcell_full_v3.csv',encoding='utf-8',errors='replace');r=csv.reader(f);next(r);next(r);from collections import Counter;c=Counter(row[122] for row in r if len(row)>122);print(c)"
# ITSNdb 计数
python -c "import csv;from collections import Counter;print(Counter(r['NeoType'] for r in csv.DictReader(open('ITSNdb/data/ITSNdb.csv',encoding='utf-8',errors='replace'))))"
# PRIME 标签×random 交叉（见 verifier）
# overlap（肽级，HLA 规范化前的上界）：见本文 §4，脚本逻辑在 analysis/load_unified.py
```

---

## 7. 下载状态 + 待补（TODO，未编造）

✅ 已下：IEDB tcell_full_v3 / ITSNdb / VDJdb / PRIME 训练集(SuppTables) / dbPepNeo2 补充。
⬜ TODO（需 Playwright/邮件/账号，本窗未拿下，标步骤防臆想）：
1. **NEPdb**：站点无批量 Download 直链，仅 Search 网页逐查 → 邮件 WHU 管理员或 Playwright 抓 Search 导出。
2. **harmonized(NeoRanking)**：README 的两个 figshare share 链实为**训练好的分类器 .sav 模型**（已 Playwright 核），非原始 `Mutation_data_org.txt`/`Neopep_data_org.txt`。真数据源待重新定位（查 repo 其他链接 / 邮件 Bassani lab）。
3. **dbPepNeo2 全库 HC(801)/LC(842k)**：站点 Axure JS 页无静态直链 → Playwright 点 Download 或邮件 luxiex2017@outlook.com。
4. **TESLA per-peptide**：Synapse syn21048999 公开（无需 MTA），但连续 tetramer 频率列在 Cell 补充 Table S4——需人工开 mmc xlsx 确认是否含连续列（两轮联网未坐实，PHASE0 标 TODO）。
5. **NeoTImmuML 训练集**：repo 仅 demo.csv(17KB)，全 5156×2 在 TumorAgDB2.0(tumoragdb.com.cn) 需重建。
6. **CEDAR**：schema 同 IEDB，单独导不省事；若要癌症聚焦子集，浏览器 More CEDAR→Database Export→CSV Metric Exports 取 tcell_full_v3.zip。
