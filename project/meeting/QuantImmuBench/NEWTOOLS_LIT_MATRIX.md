# 新增对比工具 — 文献矩阵 + 选用理由（PPT 素材）

> 7 个新工具，在原 10 工具横评基础上扩充，补方法学多样性。本文 = PPT「新工具文献矩阵」+「为什么选作对比基线」两节的素材真源。
> 数字/结果见 `analysis/NEWTOOLS_ANALYSIS.md`；部署 4 类信息见 `TOOLS/<tool>.md`；许可见 `PROVENANCE.md`。
> 建档 2026-06-27（researcher×2 联网核 DOI/repo/许可，researcher caveman ON 但 DOI/标题/URL 原样核对）。

---

## 一、文献矩阵

| 工具 | 论文标题 | 年/期刊 | DOI | 官方 repo/web | 许可 |
|---|---|---|---|---|---|
| **BigMHC** (-m=im) | Deep neural networks predict class I MHC epitope presentation and transfer learn neoepitope immunogenicity | 2023 · Nature Machine Intelligence | [10.1038/s42256-023-00694-6](https://doi.org/10.1038/s42256-023-00694-6) | github.com/KarchinLab/bigmhc | 学术非商用（Johns Hopkins Karchin Lab）·发数字✅ |
| **CNNeo / CNNeoPP** | CNNeoPP: a LLM-enhanced deep learning pipeline for personalized neoantigen prediction and liquid biopsy applications | 2026 · Frontiers in Immunology | [10.3389/fimmu.2026.1722117](https://doi.org/10.3389/fimmu.2026.1722117) | github.com/AaronChen007/neoantigen | MIT |
| **MHCflurry 2.0** | MHCflurry 2.0: Improved Pan-Allele Prediction of MHC-I-Presented Peptides by Incorporating Antigen Processing | 2020 · Cell Systems | [10.1016/j.cels.2020.06.010](https://doi.org/10.1016/j.cels.2020.06.010) | github.com/openvax/mhcflurry | Apache-2.0 |
| **IEDB Immunogenicity** (Calis) | Properties of MHC Class I Presented Peptides That Enhance Immunogenicity | 2013 · PLOS Comput Biol | [10.1371/journal.pcbi.1003266](https://doi.org/10.1371/journal.pcbi.1003266) | tools.iedb.org/immunogenicity | NPOSL-3.0 / 学术免费·发数字✅ |
| **Repitope** | Quantitative Prediction of the Landscape of T Cell Epitope Immunogenicity in Sequence Space | 2019 · Frontiers in Immunology | [10.3389/fimmu.2019.00827](https://doi.org/10.3389/fimmu.2019.00827) | github.com/masato-ogishi/Repitope | MIT |
| **netMHCpan-4.1** (BA mode) | NetMHCpan-4.1 and NetMHCIIpan-4.0: improved predictions of MHC antigen presentation by concurrent motif deconvolution and integration of MS MHC eluted ligand data | 2020 · Nucleic Acids Research | [10.1093/nar/gkaa379](https://doi.org/10.1093/nar/gkaa379) | services.healthtech.dtu.dk/services/NetMHCpan-4.1 | ⚠️ DTU 学术·**禁再分发**（投稿前取 DTU 书面同意）|
| **T-SCAPE** | T-SCAPE（Sci Adv 2025；标题以官网/DOI 为准）| 2025 · Science Advances | [10.1126/sciadv.adz8759](https://doi.org/10.1126/sciadv.adz8759) | github.com/seoklab/T-SCAPE | ⚠️ CC BY-NC-ND 4.0·**禁衍生发布**（须 caveat）|

> ⚠️ **许可红线**：netMHCpan-BA = DTU 学术许可禁再分发跑出的数字 → 投稿/对外报告前取书面同意；T-SCAPE = CC-BY-NC-ND 禁演绎 → 报告数字须标注，不发衍生版本。其余 5 工具（BigMHC/CNNeo/MHCflurry/IEDB_Calis/Repitope）许可允许发数字。
> ⚠️ **T-SCAPE 标题**：REFERENCES.md 原记标题与本次核查不一致，且全网未确认唯一权威全称展开 → 以 DOI 10.1126/sciadv.adz8759 为准，正式引用时从官网/原文核全称。

---

## 二、为什么选这 7 个作对比基线（方法学演化光谱）

选这 7 个不是随意扩，而是补齐原 10 工具缺的**方法学生态位**，形成「经典统计 → HLA-agnostic ML → 纯结合亲和力 → 提呈代理 → LLM 增强 → 大规模迁移 → 多域结构 DL」的完整演化光谱，让 benchmark 覆盖面和说服力上一个台阶。

### 1. IEDB Immunogenicity (Calis 2013) — 经典统计「临界线」
- **生态位**：无机器学习、无结构，纯氨基酸理化属性在 P4–P6 位的富集统计，一个线性加权分。
- **为什么选**：建立 2013 年的历史对照基准——现代深度学习工具必须显著高于这条线才算真进步。被 pVACseq、iNeo-Suite 等主流流水线默认集成，是引用频次最高的 class-I 免疫原性工具之一。**任何新工具不超过它即可判无效**。

### 2. Repitope (2019) — 唯一 HLA-agnostic 路线
- **生态位**：原 10 工具几乎全是 HLA-aware（必须输入等位基因）；Repitope 不问肽结合哪个 HLA，靠 in-silico 模拟整个人群 TCR 库对肽序列的接触势，测「肽序列本身的免疫原性潜力」。
- **为什么选**：量化「HLA 限制信息」到底值多少——HLA-agnostic 若表现不差，说明序列内在特征够用；若很差，反证 HLA 限制是关键。MIT 许可、部署零障碍。

### 3. netMHCpan-4.1 BA mode (2020) — 纯结合亲和力标尺，验证核心命题
- **生态位**：HLA-肽结合亲和力金标准（覆盖 >18,000 等位基因），新抗原流水线最广用上游工具。
- **为什么选**：直接检验本 benchmark 最重要的方法学命题——**「结合亲和力 ≠ 免疫原性」**。把纯 binding 信号作基线，量化它与真实 ELISpot 反应的 gap，为整合了 TCR / 抗原加工等更多信号的工具提供「提升幅度参照系」。⚠️ DTU 禁再分发。

### 4. MHCflurry 2.0 (2020) — 社区金标准「提呈代理」
- **生态位**：开源社区使用最广的提呈预测工具，同时输出 binding affinity + presentation 双分数；不直接预测免疫原性。
- **为什么选**：检验「提呈预测（无免疫原性微调）能否当强弱定量代理」。作为领域「公共参照系」，多数新工具论文都拿它对比，不纳入会被 reviewer 注意。双分数可分析 affinity vs presentation 哪条更预测真值。Apache-2.0、pip 一键装。

### 5. CNNeo / CNNeoPP (2026) — LLM 增强 CNN，方法前沿
- **生态位**：原 10 工具无一用蛋白质语言模型；CNNeoPP 率先把 BioBERT 序列嵌入引入新表位免疫原性，CNN+BioBERT 三子模型晚融合 ensemble。
- **为什么选**：填「LLM 增强序列表征」方法学空白，正交于 BigMHC（自训练大矩阵而非外部 LLM）。2026 最新发表、TESLA+ELISpot 验证（与本项目真值同源）、MIT 许可、轻量 backbone。展示方法前沿。

### 6. BigMHC -m=im (2023) — 大规模迁移学习深度 ensemble
- **生态位**：「先在数十万条 MHC-I 洗脱配体上预训练（EL）→ 迁移到免疫原性标签（IM）」两阶段范式，训练规模远超其他工具。
- **为什么选**：代表「大规模预训练 + 下游迁移」现代范式；Nature MI 2023 高可信、同类比较精度最优、覆盖 >500 等位基因 pan-allele。reviewer 会注意它的缺席。

### 7. T-SCAPE (2025) — 多域结构感知 SOTA「复杂度上限」
- **生态位**：2025 年最新、本 benchmark 时间戳最新工具；多任务多域对抗 DL，融合 pMHC binding + TCR-pMHC 交互 + source organism + T 细胞激活四路信号。
- **为什么选**：作「复杂度上限」基线——若最新多域 DL 在 ELISpot 真值上也只有有限增益，说明是数据瓶颈而非方法瓶颈。benchmark 有义务纳入最新 SOTA 保时效性。⚠️ CC-BY-NC-ND 须 caveat。

---

## 三、一句话总览（PPT 收尾用）

> 这 7 个工具不是同质堆叠，而是沿「**统计基线（Calis）→ HLA-agnostic（Repitope）→ 纯结合（netMHCpan-BA）→ 提呈代理（MHCflurry）→ LLM 增强（CNNeo）→ 大规模迁移（BigMHC）→ 多域结构 SOTA（T-SCAPE）**」一条方法学演化主轴各占一格，使横评从「比谁分高」升级为「检验每一类方法范式对免疫强弱定量的真实贡献」。
