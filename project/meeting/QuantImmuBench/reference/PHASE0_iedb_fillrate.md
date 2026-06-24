# QuantImmune Phase0 命门：IEDB/CEDAR 定量字段填充率核查

> 服务 quantimmu-bench / 袁 QuantImmune 立项 Phase0（帮徐伊琳/袁老师证伪方向地基）。researcher(opus) 联网，2026-06-24。0 GPU 命门证伪。
> 承重前提：连续 ground-truth（SFC/%tetramer/SI）跨 ≥2 study ≥10³。

## ⭐ 核心结论（命门倾向 FAIL）
**连续 magnitude 在公开源里不是可直接回归的连续列系统存在**，而是被 IEDB/CEDAR 折叠成「响应频率二分 + 序数三档(positive-high/-intermediate/-low)」。所有实际用过 IEDB T cell 数据的免疫原性模型(DeepImmuno/NetTepi/Repitope)**无一用连续 magnitude 回归，全部二分** = 「连续列稀疏/不可直接用」的最强间接铁证。
- 连续 magnitude 跨 ≥2 study ≥10³ 的**直接证据未找到**(标 TODO 给实测步骤)。
- 量大跨多 study 的是**序数分级**(够 10³+，但是序数非连续 = 退守路线)。
- 肿瘤/新抗原子集带 magnitude 的**正例极少**(TESLA 仅 37 immunogenic/608)。

## 证据
- **CEDAR**(34,889 T cell assays，16,100 neoepitopes)：官方「quantitative numerical values available *for assay types with quantitative measurements*；positive-high/-intermediate/-low *if authors provide*」→ **连续值条件性非系统填充**(best-effort)。仅 XML/MySQL dump 无现成连续值 csv。[PMC9825495]
- **IEDB curation**：必填=Qualitative(pos/neg)；Quantitative=「whenever available must be captured」条件性，T cell functional assay 数值捕获弱(系统化主要针对 MHC binding IC50)。[IEDB 文档，TLS 失败待本地直验]
- **决定性间接铁证**：DeepImmuno 从 IEDB 拿 9,056 instances，label = number tested/responded + 序数三档经 beta-binomial 折二分，**非连续 SFC/tetramer**[PMC7781330]；NetTepi/Repitope 同样 binary。整个社区面对 IEDB/CEDAR 默认拿到的监督信号 = 二分+响应频率+序数三档，非连续 magnitude。
- **TESLA**(Cell 2020)：608 肽 tetramer 测，仅 **37(6%) immunogenic**。确有 per-peptide 连续 tetramer 频率(补充表，mmc 表号 TODO)，但正例仅 ~37、单 consortium study，远 <10³。

## 填充率估计（区间，确切数 TODO）
| 监督信号 | 肿瘤/neoepitope 子集跨 study 量 | ≥10³? |
|---|---|---|
| 连续 magnitude(数值 SFC/%tetramer/SI) | 估 10¹-10² 正例，高度集中(TESLA 占大头)，填充率 <10-20% 且分散 | **否(FAIL)** |
| 响应频率(responded/tested) | 10³ 量级(病毒+癌混合，纯癌子集更小) | 混合可，纯癌 TODO |
| 序数三档(high/int/low) | ≥10³(混合)，纯 neoepitope 子集 TODO | 混合 PASS/纯癌 TODO |
> caveat：DeepImmuno 9,056 是病毒+癌+SARS 混合；**纯肿瘤 neoepitope 连续 magnitude 正例几乎肯定 <10³**。

## PASS/FAIL 判断
- **claim=连续 magnitude 回归 → 命门 FAIL(高置信)**：无已发表工作从 IEDB/CEDAR 提连续 magnitude 回归(全退二分)+官方「if available」非系统填充+肿瘤正例量级 10¹-10²(TESLA 37)不满足 ≥10³ 跨 ≥2 study。
- **claim 松到序数分级回归(ordinal) → CONDITIONAL PASS**(待纯癌子集实测确认 ≥10³)。
- **退路**：序数分级回归，或**自补 ELISpot 实测**(Wave3 已有 ELISpot 正式测试管道正好补)。
- **建议(命中率回退方向=拍板点)**：把 claim 形状从「连续回归」改「序数分级+响应频率」，或明确 QuantImmune 用自补实验产连续 GT 而非依赖公开源。**需袁老师/徐伊琳拍板。**

## 主线实测步骤（替代 TODO，0 GPU）
1. 拉 IEDB T cell 全表 `http://www.iedb.org/downloader.php?file_name=doc/tcell_full_v3.zip` 解压 tcell_full_v3.csv。
2. pandas 核连续填充率：定位 `Assay - Quantitative measurement`/`Method`/`Number of Subjects Tested/Responded`；query A=ELISPOT|tetramer|ICS 方法子集 `Quantitative measurement` 非空率按 method 分组；query B=肿瘤子集(Disease 含 cancer/neoplasm + Antigen 为 neoepitope/mutant)数非空连续值正例条数 + PMID 去重数 study。
3. CEDAR 全库(More CEDAR→Database Export XML/MySQL)解析 T cell assay 数值非空 + 单位 SFC/%tetramer 记录数。
4. TESLA mmc 补充表(ScienceDirect S0092867420311569 或 Caltech authors.library.caltech.edu/records/5haf9-91503)找 per-peptide tetramer frequency 列确认 ~37 正例。
5. 判定：肿瘤子集连续 magnitude 正例数 + 跨 study 数 → 套判据(≥10³ 且 ≥2 study=PASS)。预判 <10³(FAIL)，必须实测不臆想。

## 引用
- CEDAR NAR 2023 — PMC9825495（「quantitative if available + 序数三档 if authors provide」）
- DeepImmuno PMC7781330（社区不用连续 magnitude 铁证）
- TESLA Cell 2020 — S0092-8674(20)31156-9（肿瘤正例仅 37 单 study）
- IEDB T cell 全表 — http://www.iedb.org/downloader.php?file_name=doc/tcell_full_v3.zip

## ✅ 2026-06-24 实测回填（主线下 IEDB tcell_full_v3 实跑，授权后）

下 IEDB `tcell_full_v3.zip`（43M→解压 csv **1.33 GB**，确认暴涨）跑 `analysis/phase0_fillrate_check.py`，实测落 `analysis/phase0_fillrate_actual.csv`。**IEDB 573,409 行，肿瘤子集（Disease 含 cancer/neoplasm/tumor/carcinoma/melanoma/…）50,384 行**。三路线命门实测：

| 路线 | 肿瘤子集实测 | 全库对照 | 判据 ≥10³ 跨 ≥2 study | 判定 |
|---|---|---|---|---|
| **连续 SFC**（Quantitative measurement 非空） | **455**（0.9%） | 5773（1.0%） | 455 < 10³ | 🔴 **FAIL 实证坐实**（原预判确认，连续回归 headline 死） |
| **A 序数三档**（Qualitative Measure） | Positive-High 472(117 PMID) + Positive-Intermediate **160**(35 PMID) + Positive-Low 1545(316 PMID) = **2177 跨多 study** | high 5813/int 5116/low 17985 | 三档合计 >10³ 且跨多 study，但**中间档仅 160** | 🟡 **CONDITIONAL PASS**：用全三档够、跨 study 足；但 high+int（真区分强弱）仅 632、中间档 160 薄 → 实质可能退化成 high-vs-low 二档（skeptic「中间档<100=退化二分」判据：160 刚过线但判别力弱） |
| **B 响应频率**（Number of Subjects Positive / Tested，≥4 tested） | **3813**，中间值(0.2-0.8)占 **32.4%**(>20% 阈值)；直方=0 值 1394/极低 716/中段 1281/高 144/满 278 | ≥4-tested 全库 237048 | 3813 > 10³ 且中间值占比 32.4% > 20% | 🟢 **PASS（量最足、不退化二分）** |

> ⚠️ **B 的实测反转预判**：此前 skeptic/researcher 担心 B 纯肿瘤稀疏（neoepitope 患者私有突变→≥4 受试者罕见），**实测 B 反而最足（3813）**。但两条 caveat 仍在：①**撞 DeepImmuno**（DeepImmuno 正是用 Number of Subjects Positive/Tested 做 beta-binomial，PMC7781330）②**theorist B4 红旗**（$\hat\pi$ 与 SFC magnitude 实证可解耦，B 代理 magnitude 风险最高）。
> ⚠️ **scope caveat**：肿瘤子集按 Disease 关键词圈，含**共享肿瘤抗原**（NY-ESO-1/MAGE/病毒相关 HPV·EBV 等）非纯**私有 neoepitope**——B 的 3813 多受试者配对大概率多来自共享抗原（私有突变难有 ≥4 独立受试者测同一肽）。若 QuantImmune 限定真私有 neoantigen，可用量会大幅缩水（需再按 Antigen=mutant/neoepitope 二次过滤，TODO）。
> ⚠️ **IEDB v3 字段名**：responded 等价列 = `Assay - Number of Subjects Positive`（非 "Responded"）；连续列 = `Assay - Quantitative measurement`；序数 = `Assay - Qualitative Measurement`(Positive-High/-Intermediate/-Low)。

**实测判定小结**：数据可得性 **B(3813) > A(2177，中间档薄) > 连续(455 FAIL)**。但「数据足」≠「claim 好」——B 撞 DeepImmuno+理论红旗、A novelty 稍好但中间档判别力弱。**skeptic 的 D（benchmark 主路）不依赖任一路线数据够（证据在手），仍最稳。** claim 形状 = 命中率回退方向 = 拍板点呈袁/徐定。

## TODO（勿臆想填充率）
- ~~IEDB Quantitative 在肿瘤子集非空正例数~~ → ✅ 已实测 455（FAIL），见上回填。
- ✅ **Antigen 二次过滤已实测**（决定性）：三层缩水——①肿瘤(disease=cancer) A序数2177(中间档160)/B频率3813，跨976 PMID；②+人源(排病毒HPV/EBV) A序数1191(hi250/**int49**/lo892)/B频率3069，跨738 PMID（**中间档骤降49<100=退化二分坐实**）；③+有修饰(候选私有neoepitope) **A序数仅2/B频率仅25，跨18 PMID** = **真私有 neoepitope 定量 GT 公开源≈0**。
  → **开发针对私有 neoantigen 的定量工具，公开源无足够 GT**。三条开发路线：(a)自补 ELISpot 产私有 neoepitope 定量数据；(b)用共享肿瘤抗原(NY-ESO/MAGE，人源序数1191/频率3069)训练再迁移到私有；(c)放宽 scope 到全肿瘤 T 细胞表位(含病毒，2177/3813，但偏离 neoantigen 本意)。caveat：IEDB Modifications 列填充不全可能低估真私有数，但"能稳健识别的私有 neoepitope 定量 GT≈0"成立。
- CEDAR 全库（癌症专库）序数/计数净增量（本次只跑 IEDB tcell_full，CEDAR 未单独跑）。
- IEDB tcell_full_v3 `Quantitative measurement` 在 ELISPOT/tetramer×肿瘤子集确切非空正例数+跨 PMID 数（步骤 2/3 跑）。
- TESLA 补充表确切 mmc 表号+连续频率列名（步骤 4）。
- CEDAR 纯 neoepitope 序数三档可用正例 ≥10³?（决定退守路线可行性）。
