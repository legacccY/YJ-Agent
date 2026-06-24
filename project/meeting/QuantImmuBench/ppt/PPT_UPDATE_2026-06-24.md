# PPT 增量内容大纲（2026-06-24 更新版）

> 给袁老师的 PPT 增量 / 修订内容。整合本轮 13 路编队全部发现（工具普查、数据集普查、benchmark 方法学、红队、理论可行性、本地深析、bootstrap CI）。
> 作者：余嘉（legacccy）。所有数字均经本地 csv 核对（verifier 0 drift）；文献结论带来源；不确定项显式标注。
> 措辞红线（必守）：benchmark 对外结论一律用保守版——「现有工具判别力普遍弱、统计不可区分、无稳健最优工具」；禁用「pTuneos 0.78 最优 / 最强 / 无可替代」。依据 reference/REDTEAM_benchmark.md 🔴-1。

---

## 修订总览

| 动作 | slide | 取代 / 关系 |
|---|---|---|
| 修订 | S1 benchmark 结论页（保守版） | 取代旧「pTuneos 最优」结论页 + 旧 fig6 柱状图 |
| 新增 | S2 DS1 全阳证伪定量能力 | 新页 |
| 新增 | S3 QuantImmune 立项支撑（蓝海 + 命门 + 天花板） | 新页 |
| 新增 | S4 诚实 caveat 页 | 新页（防审稿/防过度承诺） |

---

## S1（修订）现有工具 benchmark 的诚实结论（保守版）

**标题**：现有 8 工具在 ELISpot（DS2）上判别力普遍弱、统计不可区分、无稳健最优；新工具无增量

**要点**：
- 测试集 = 本地 ELISpot Dataset2（DS2，101 肽，90 阳 / 11 阴，标签按 ELISpot SFC>0 切）。
- **判别力普遍弱**：AUC 最优点估 pTuneos 0.7525，但 2000 次 bootstrap 95% CI = [0.598, 0.888]，宽达约 ±0.15；除 pTuneos 外的工具 CI 下界均跌破 0.5（随机线）。
- **统计不可区分**：配对 bootstrap 显示 pTuneos vs PredIG ΔAUC=0.091，95% CI=[−0.145, +0.310] 跨 0；pTuneos vs NeoTImmuML ΔAUC=0.098，CI=[−0.140, +0.327] 跨 0 → 头部工具之间分不出统计显著高下。根因 = 阴性样本仅 11 个，少数类主导不确定性。
- **「最优」是脆弱角落**：pTuneos 0.78 是「单聚合 × 单阈值 × 11 阴性」三重最优点；同一工具换 >median 阈值 AUC 掉到约 0.46（低于随机）→ 非稳健能力。
- **新工具无增量**（稳健结论）：第二批新纳入工具在全部聚合 × 阈值组合下，没有一个超过第一批最优点估；该结论不依赖排名精度，且 IEDB 泄漏方向只会让分数虚高、对此结论顺风。

**配图**：全 8 工具 AUC caterpillar（点估 + bootstrap 95% CI 误差棒，画 0.5 随机线）→ **取代旧 fig6 柱状图**。
**引用数**：analysis/bootstrap_ci_ds2.csv（各工具 AUC + CI）+ analysis/bootstrap_paired_ds2.csv（配对 ΔAUC + CI 跨 0）。

---

## S2（新增）DS1 全阳数据集证伪「现有工具能定量」

**标题**：现有工具是分类器，不是回归器——全阳数据集上无工具能排出反应强弱

**要点**：
- DS1 = 82 肽 9mer，全阳性（ELISpot SFC 范围 16–677，中位 131，**无阴性对照**，算不了 AUC），SFC magnitude 跨约 40 倍，适合测「阳性内部谁更强」的排序。
- **8/9 工具对 DS1 SFC 的 Spearman |ρ| < 0.16，p 全不显著（≈随机）**：PredIG ρ=0.028、IMPROVE ρ=0.007、pTuneos ρ=−0.022、ImmuneApp ρ=0.039 等。唯一显著的 deepHLApan ρ=−0.503 是**反向**（负贡献，非能力）。
- **干净对照**：同一批工具在 DS2 上头部能正向显著排 SFC（IMPROVE top3mean ρ=0.32 p=0.001、PredIG mean ρ=0.28 p=0.005），到 DS1 全阳子集就全部塌成随机。
- **机制**：工具的判别力主要落在「阳 vs 阴」门槛上；一旦全阳，门槛信息用尽，「阳性内部强弱」基本预测不出。
- **对袁课题的正面意义**：这是一个诚实的负结果硬结论——**现有工具能粗分有无，不能预测连续 magnitude**，正好坐实 QuantImmune 做连续回归的空白。

**配图**：DS1 vs DS2 各工具 Spearman ρ 对比柱（figures/ds1_vs_ds2_spearman_bar.png）。
**引用数**：analysis/DS1_magnitude.md + analysis/ds1_magnitude_spearman_bestbinder.csv。
**caveat**：deepHLApan ρ=−0.50 反向需 verifier 核分数极性语义；DS1 n=82 偏小（结论 p 非边界，统计稳）。

---

## S3（新增）QuantImmune 立项支撑：蓝海 + 命门 + 天花板 + headline

**标题**：QuantImmune 的机会与边界——做对反应强弱的连续回归，但先验证命门

**要点（四块）**：

1. **蓝海（方向不撞车）**：预测 T 细胞反应"强弱"（response magnitude，对 ELISpot SFC 做连续回归）是学界公认空白。2024 专题综述（Exploration of Immunology, DOI 10.37349/ei.2023.00091）原文："Magnitude prediction remains an unaddressed gap."；逐一核验所有自称"定量"工具（PRIME README 自认是 ranking 非 magnitude、ICERFIRE 主动把量级标签塌缩成二分、neoIM/T-SCAPE 仍做分类）→ **真正做连续 magnitude 回归的工具 = 0 个**。

2. **命门（立项前零成本必做项）**：想做回归却可能没有足够连续标签作 ground truth。绝大多数公开数据集是二元标签（PRIME / NEPdb / dbPepNeo2 全 binary）；**唯一系统性带 magnitude 字段的公开源 = IEDB 及其癌症子库 CEDAR**（schema 含 ELISPOT SFC / % tetramer）。🔴 **动手前必须先核实 IEDB / CEDAR 的 magnitude 字段实际填充率**——若 quantitative 列填充稀疏且 TESLA 补充表无连续列，则"想做回归但无连续标签"直接塌缩立项。零算力，数日可做。

3. **理论天花板（避免过度承诺）**：纯"肽 + HLA"输入对 magnitude 的可解释方差被生物学结构性封顶——头号因子 naïve precursor frequency（初始 T 细胞克隆数，近线性决定幅度，Jenkins & Moon 2012）由宿主 TCR 库决定，**无法从肽 + HLA 序列推出**；叠加 ELISpot 测量噪声（inter-lab CV 可达 40%）→ ρ 天花板粗估 **0.4–0.6（低置信，待真实 benchmark 校准）**。文献实测 IMPROVE ρ≈0.32 已达约 2/3，接近但未触顶，**请勿承诺 ρ→0.8 颠覆性增益**。

4. **headline 押 C3（临床 top-K 排序增量）**：连续模型在 held-out 病人上的 top-K 推荐质量优于二分类——临床只能合成 top-K 肽，排序质量直接等于临床价值。这条不赌破天花板，最现实、最可证伪、最有临床说服力。C1（坐实纯序列天花板）当诚实能力刻画，C2（喂供体 TCR-seq 破天花板）标探索性 stretch goal，不当主承重。

**引用数 / 来源**：PROJECT_LANDSCAPE.md（综述）+ reference/LANDSCAPE_tools.md（撞车扫描，DOI 10.37349/ei.2023.00091）+ reference/THEORY_quant.md（precursor frequency 锁 ρ~0.4–0.6，Jenkins&Moon 2012 PMC3334329）。

---

## S4（新增）诚实 caveat 与已知限制

**标题**：本轮 benchmark 的已知限制与红线（先说清，免被审稿打回）

**要点**：
- **样本量极小**：DS2 仅 11 个阴性样本，所有 AUC / ρ 的 bootstrap 95% CI 都很宽，工具间排名差异（<0.05 AUC）在统计上不显著——这是「无稳健最优」结论的直接来源。
- **患者层聚集**：DS2 的 101 肽来自 9 个病人，前 2 个病人贡献了约 45% 的阴性肽 → 同患者肽若 ELISpot 系统偏移，有效自由度 < 101（伪重复），AUC 可能部分在测「区分患者」而非「区分免疫原性」。报告需按 Patient_ID 分层复核。
- **IEDB overlap 待测**：第二批新工具（PRIME / ImmuneApp / deepHLApan）多用 IEDB 数据训练，与本 ELISpot 集可能有数据重叠；当前**尚无排重 / overlap 检测代码**，"实际独立性待查"（泄漏方向是让分数虚高，对"新工具无增量"主结论顺风，但污染单工具绝对数字）。下一步：ELISpot unique 肽 vs IEDB 全库精确 + 9mer 子串 match，报 overlap%。
- **许可红线**：netMHCpan / netMHCstabpan 为 DTU 学术许可，禁再分发（含其跑出的数字）；正式对外 / 投稿前需取 DTU 书面同意（见 PROVENANCE.md）。
- **工具完整度分级**（接 REPORT.md 诚实分级）：DeepImmuno / PredIG 完整端到端；pTuneos 用 Pre&RecNeo 子模型（r=1.0 只证复刻逻辑正确，非整管线 ELISpot 能力背书）；IMPROVE 特征链降级；NeoTImmuML 为自训版（非官方权重，不对标原论文精度）。

**引用数 / 来源**：reference/REDTEAM_benchmark.md（🔴-1 / 🟠-2 / 🟠-4）+ analysis/patient_strat_check.csv（患者聚集）+ analysis/bootstrap_ci_ds2.csv（CI 宽度）+ PROVENANCE.md（许可）。

---

## 附：本次更新一句话

八工具 benchmark 的诚实保守结论（现有工具判别力普遍弱、统计不可区分、新工具无增量、定量能力弱）不仅站得住，反而**强化了 QuantImmune 做连续 magnitude 回归的立项动机**；但立项前请务必先做掉 S3 命门项（核 IEDB/CEDAR 的 magnitude 填充率），它是整个方向的开关。
