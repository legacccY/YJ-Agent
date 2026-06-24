# 新抗原免疫原性数据集下载清单（数据组支援）

> 服务 quantimmu-bench（支援数据收集组=王子源/谢孟翰：文献搜索+数据收集）。researcher(opus) 联网核 2026-06-24。
> 用途：照着就能下的获取清单。铁律：查不到确切 URL 标 TODO，不编造链接，URL 原样。

## 🟢 实下状态（2026-06-24 数据组窗实测，已下根 `data/external/`）

| 数据集 | 状态 | 实下文件 + 体积 | 实测字段（verifier 核原文件） |
|---|---|---|---|
| **IEDB tcell_full_v3** | ✅ 已下 | `tcell_full_v3.csv` 1.3G，573409 行 | `Epitope/Name`(肽)+MHC段+`Qualitative Measurement`(Neg361572/Pos182923/序数三档28914)；`Quantitative measurement` 填充仅 1.01% 且 71% binding → **magnitude 命门 FAIL**（详 `PHASE0_iedb_fillrate_MEASURED.md`） |
| **ITSNdb** | ✅ 已下 | `ITSNdb/` 15M (git clone) | `ITSNdb.csv` 199 肽 `Neoantigen`+`HLA`+`NeoType`(129阳/70阴)；TNB/Val 另两文件标签非肽级免疫原性（患者应答/变异来源，⚠️别误用） |
| **PRIME 训练集** | ✅ 已下 | `PRIME/TableS4.xlsx`(训练596/6084+58905random) + `TableS3.xlsx`(benchmark) | `Mutant`+`Allele`+`Immunogenicity`；CC BY 4.0。⚠️596:6084 vs 596:64989(含random)差一量级 |
| **VDJdb** | ✅ 已下 | `vdjdb/` 406M，197729 行 | `antigen.epitope`+`mhc.a/b`+`vdjdb.score`(0-3 confidence 非强弱)；2068 唯一肽；TCR 维度，AGPL-3.0 |
| **dbPepNeo2** | 🟡 仅补充 | `dbPepNeo2_Table1.xlsx` 20K (113 候选肽 figshare) | 全库 HC(801)/LC(842k) 未下（站点 JS 无直链）→ TODO 邮件/Playwright |
| **NEPdb** | ⬜ TODO | — | 站点无批量 Download 直链，仅 Search 网页逐查 → 邮件 WHU 或 Playwright 抓导出 |
| **harmonized(NeoRanking)** | ⬜ TODO | — | README 两 figshare share 实为**分类器 .sav 模型**非原始数据（Playwright 已核）；真数据源待重定位 |
| **TESLA** | ⬜ TODO | — | Synapse syn21048999 公开无需 MTA；连续 tetramer 列在 Cell mmc S4 待人工开文件确认（PHASE0 TODO）。binary 源（37正），非 magnitude 源 |
| **NeoTImmuML** | ⬜ TODO | — | repo 仅 demo.csv(17K)，全 5156×2 在 TumorAgDB2.0 需重建 |
| CEDAR | ⏸ 不必单独 | — | schema 同 IEDB，单独导不省事；要癌症聚焦才走 More CEDAR→Database Export |

**统一 GT schema + 泄漏实测 + train/test/held-out 划分** → `UNIFIED_GT_schema.md`。
**加载脚本** → `scripts/load_unified.py`（把异构集统一成 schema 长表 + 复现 overlap，已烟测对上 verifier）。
**泄漏铁证（肽级实测）**：ITSNdb 197 肽 → 181(92%)现于 IEDB、114(58%)现于 PRIME；PRIME-real 6387 → 3845(60%)现于 IEDB。→ 公开源几乎全撞 IEDB，真 held-out 靠本地 ELISpot + TESLA + leave-study-out。

## 推荐下载顺序（①带定量 GT ②可直接下 ③规模够）
**第一梯队（带定量 magnitude，回归 GT 命门，优先）**
1. **IEDB tcell_full_v3** — 唯一系统带 quantitative magnitude 大库，直接下无门槛。**先下。**
2. **CEDAR tcell_full_v3**（IEDB 癌症子库）— 同 schema，癌症 epitope 更聚焦，直接下。
3. **TESLA**（Synapse syn21048999）— 逐肽 tetramer 频率(真定量金标准)，需 Synapse 账号，定量列需挖补充表。

**第二梯队（binary/序数，分类+泄漏对照，可直接下规模够）**
4. NEPdb(nep.whu.edu.cn) 17,549 neo-epitope CSV · 5. harmonized(Immunity2023 Figshare) 1.78M 肽/178 免疫原性已去泄漏 · 6. NeoTImmuML/TumorAgDB2.0(tumoragdb.com.cn) · 7. ITSNdb(github elmerfer/ITSNdb) 129 阳/70 阴专为评估预测器。

**第三梯队（binary 补充/对照）**
8. PRIME 训练集(Mendeley，IEDB 衍生=头号泄漏源当对照不当测试集) · 9. dbPepNeo2.0(Frontiers figshare) · 10. TANTIGEN2.0(4 级序数做不了回归) · 11. VDJdb(TCR 维度扩展才下)。

## 下载清单表
| # | 数据集 | 下载入口 | 方式 | 体积 | 格式 | 定量? | 肽+HLA | 许可 |
|---|---|---|---|---|---|---|---|---|
| 1 | IEDB tcell_full_v3 | `http://www.iedb.org/downloader.php?file_name=doc/tcell_full_v3.zip` (入口 database_export_v3.php) | 直接无注册 | zip 数百 MB→解压 >1GB(>2.2M 记录注意暴涨) | zip→csv | **是**(SFC/%tetramer/SI/IFN-γ) | 是 | 免费需引用 |
| 2 | CEDAR | `https://cedar.iedb.org/` → More CEDAR → Database Export → CSV | 直接无注册 | 比 IEDB 小 | zip→csv(+XML/MySQL) | **是**(同 schema) | 是 | 免费同 IEDB |
| 3 | TESLA | `https://www.synapse.org/Synapse:syn21048999`；定量见 Cell 2020 补充 | **需 Synapse 账号**，定量挖 mmc | 肽表小/测序大 | csv/xlsx | **原文有**(tetramer 频率) | 是(黑色素瘤+NSCLC HLA-I) | Synapse 条款 |
| 4 | NEPdb | `http://nep.whu.edu.cn/` → Download | 直接免费 | MB 级 csv | csv | 否(二分) | 是(I+II) | 免费学术 |
| 5 | harmonized | `github.com/bassanilab/NeoRanking` → Figshare(Mutation_data_org.txt/Neopep_data_org.txt) | Figshare 直接 | MB~百 MB | tab txt | 否(binary) | 是(含 HLA 表) | LICR/Figshare 友好 |
| 6 | NeoTImmuML/TumorAgDB2.0 | `https://tumoragdb.com.cn` → Download；NeoTImmuML repo | 直接 | TumorAgDB 百 MB/训练集小 | csv/xlsx | 否 | 是 | 库公开 |
| 7 | ITSNdb | `https://github.com/elmerfer/ITSNdb` | clone/ZIP 无门槛 | KB~MB | csv/tsv | 否(binary) | 是(I) | repo LICENSE |
| 8 | PRIME 训练集 | `https://data.mendeley.com/datasets/2kmmjp4tmm/1`(Table S4，596 正/6084 负) | Mendeley 直接 | KB~MB xlsx | xlsx | 否 | 是 | **软件学术非商用**；**IEDB 衍生=头号泄漏源** |
| 9 | dbPepNeo2.0 | `http://www.biostatistics.online/dbPepNeo2` → Download；figshare collection 5944861 | 直接 | 百 MB(842k LC) | csv | 否 | 是(含 630 TCRβ) | 开放 |
| 10 | TANTIGEN2.0 | `https://projects.met-hilab.org/tadb/` | 站点导出(TODO 整库一键?) | MB | fasta/csv | 否(4 级序数) | 是(15 HLA) | 免费学术 |
| 11 | VDJdb | `https://github.com/antigenomics/vdjdb-db/releases`；Zenodo 11642183 | release 直接 | 数十 MB tsv | tsv | 否(TCR) | 部分 | CC 开放 |

## 门槛分流
- **无门槛直接下**：IEDB/CEDAR/NEPdb/harmonized/ITSNdb/PRIME 训练集/dbPepNeo2/VDJdb。
- **需账号**：TESLA→Synapse(免费注册，测序层受控肽表走补充可绕)。
- **可能需逐表导出**：TANTIGEN2.0、CEDAR/IEDB Export Results(整库走 CSV Metric Exports 一键)。
- **商用注意**：PRIME 软件学术非商用(数据可学术用)。其余学术免费，发布前逐库核条款+引用原文。

## 给数据组执行建议（命门）
- 定量回归 GT 现实只两条：①IEDB+CEDAR 导 quantitative(量大但脏，需 assay 分层+研究内归一化)②TESLA 逐肽 tetramer(干净但量小需 Synapse+挖补充表)。**先下 IEDB/CEDAR tcell_full_v3 实测 quantitative 列填充率**(见 `PHASE0_iedb_fillrate.md`)，这决定 magnitude 回归有没有 GT。
- 泄漏防线：PRIME/NeoTImmuML/harmonized 几乎都从 IEDB 训练；测试集也来自 IEDB → in-sample 泄漏。下完必做 sequence-level 去重 + leave-study-out。ITSNdb/TESLA 相对独立适合 held-out。

## TODO（未编造）
1. 各库确切体积(下载时看属性，IEDB 解压暴涨留盘)。
2. TESLA per-peptide 连续 tetramer 列在哪个 mmc 表(正文 403 未核)。
3. IEDB/CEDAR quantitative 列实际填充率(下完实测，见 PHASE0)。
4. TANTIGEN2.0 整库一键 Download?。
5. NeoTImmuML 训练集确切 GitHub raw 路径。
