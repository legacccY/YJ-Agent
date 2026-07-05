# 肽长×ELISpot 混杂 — 机制文献三角验证（MECHANISM_NOTES）

> 服务 QuantImmuBench「肽长×ELISpot 混杂」深度研究 § Part3。researcher 联网多源查证，2026-07-05。
> 结论一句话：**配肽等质量 + ELISpot 技术偏倚偏向短肽，两条都反向，足以排除「剂量/质量混杂」解释；ρ̄≈0.38 正相关更像真实 SLP 生物学，但因 assay 带长肽刺激+体外扩增，须保留「CD4-help/加工放大」的口径，别纯卖成 in vivo 保护性。**

## 1. Braun 2025 配肽协议（敲定：等质量，非等摩尔）

- **数据来源 = NeoVax SLP pipeline**：Braun et al., *A neoantigen vaccine generates antitumour immunity in renal cell carcinoma*, **Nature 2025**（DOI 10.1038/s41586-024-08507-5）；试验 NCT02950766「NeoVax Plus Ipilimumab in RCC」。疫苗肽 = **合成长肽（SLP）15–33 aa**，每池 ≤5 肽、共 4 池/患者。
- **IFN-γ ELISpot 用「长肽本身」刺激，非 8–11mer 短表位**，且有体外预扩增：week0/week16 PBMC 先 `10 µg ml⁻¹ vaccine peptide pools` + IL-7 20 ng/mL（d3 起 IL-2 20 U/mL）扩增 10–14 天再上 ELISpot；ex vivo 孔 `10 µg peptide pool`/2×10⁵ PBMC；flow 验证 `2 µg ml⁻¹ per individual peptide`。
- **配肽按质量（µg/mL）固定，不是摩尔（µM）**。同 pipeline 的 Ott 2017 NeoVax 独立佐证：ELISpot `2 µg/ml` 每肽、疫苗 `0.3 mg` 每肽——均按质量。
- **⚠️ 对用户原始前提的修正**：用户设想「ELISpot 配摩尔浓度、长肽用更多重量→剂量拉高」。文献是**反的**——等质量下**长肽分子量更大→摩尔数更少→表位拷贝更少**，若有剂量效应该**压低**长肽 SFC。故「长肽用更多量所以更高」不成立；技术方向反而利空长肽。

## 2. ELISpot 技术偏倚方向（也偏向短肽，逆着观测）

- 短 8–10mer 可被任意细胞直接负载 MHC-I、无需加工；长肽须 APC 内化+蛋白酶加工才呈递 → 短肽常给更高 spot 数。观测到**长肽 SFC 更高 = 逆着技术偏倚**（Mabtech ELISpot 论坛）。
- TODO：未找到「长肽 ELISpot 读数系统性偏高」的直接技术文献（现有反而报短肽偏高）。若需正面引「长肽偏高技术混杂」，暂无官方源 → 标 TODO 勿编。

## 3. SLP 长度↔免疫原性（公认生物学，支撑「真效应」）

- 长肽须经 DC 内化+加工才交叉呈递 MHC-I（短肽直载 MHC-I 会绕过 DC 成熟共信号→CD8 无能/耐受）；长肽天然含 MHC-II 表位招 CD4 帮助 → 更强更持久 CTL。经典对照：精确短表位（IFA 中）诱导 CTL「消失」，长肽诱导「持续」CTL。
- 关键文献：Melief & van der Burg, *Nat Rev Cancer* 2008（SLP 优于短肽机制经典综述）；SLP-for-DC-presentation（PMC6422379）；Theranostics 2020 SLP 综述。

## 4. 甲/乙/丙 判断

| 解释 | 内容 | 判断 |
|---|---|---|
| **乙 剂量/质量混杂**（人为拉高长肽） | 等质量→长肽用更多量 | ❌ **排除**。等质量下长肽摩尔更少+ELISpot 偏向短肽，两条都反向，无法解释正相关 |
| **甲 真实 SLP 生物学**（长肽内部越长越免疫原） | 更多/更强 CD4 辅助表位 + 更充分加工-交叉呈递 | ✅ **得支撑**，但口径精修：不是「长肽跨过短肽阈值」，而是「15↔33mer 长肽**内部**更长更强」 |
| **丙 assay-CD4 放大**（介于甲乙） | 长肽刺激+10–14 天体外扩增，长肽 MHC-II 表位在扩增期获 CD4 帮助→CD8 扩增更充分 | ⚠️ **须保留**。是真免疫原性一部分，但被 assay 系统性放大，≠纯 in vivo 保护效应。**别把 ρ̄0.38 过度卖成纯 in vivo 生物学** |

## 5. 对「矫正」论证的含义（关键）

长肽效应**是真生物学、不是技术伪迹** → 矫正的正确论证 **不是**「去掉长度这个 fake artifact」，**而是估计量（estimand）之争**：
- QuantImmuBench 的估计量 = **突变（mutation）本身的免疫原性**；
- 疫苗肽长度是**实验构造（construct）的选择**（他们把 SLP 合成成多长），**不是突变的属性**；
- 一个 mutation-level 预测器若靠追踪 construct-level 的长度拿分，就是**把构造级信号记到突变级账上** → 该矫正。
- 所以矫正 = **从真实但构造级的长度效应里，剥离出突变的贡献**，而非「抹掉一个假信号」。这个措辞更稳、也更有意思，且正面回应「肽长到底是 nuisance 还是真 driver」的红队攻击。

## 6. 仍存疑 / 待项目侧确认

- MOESM4 里 SFC 数据肽长是否即落在 15–33mer IMP 范围（本项目 peplen 15–33 已核 = 是）；若混入非 IMP 短肽刺激孔需调口径。
- Braun 原文精确浓度经小模型 WebFetch 提取（带引号非逐字截图）；`10 µg`/`10 µg ml⁻¹` 建议人工再核 Methods/Supplementary 原句（per-pool 总量 vs per-peptide）。Ott 侧 `2 µg/ml each` + `0.3 mg each` 已独立佐证等质量，方向可靠。

## 关键引用
- Braun et al., Nature 2025, DOI 10.1038/s41586-024-08507-5 — https://www.nature.com/articles/s41586-024-08507-5
- NCT02950766 — https://clinicaltrials.gov/study/NCT02950766
- Ott et al., Nature 2017 — https://www.nature.com/articles/nature22991 ; https://pmc.ncbi.nlm.nih.gov/articles/PMC5577644/
- Melief & van der Burg, Nat Rev Cancer 2008 — https://www.nature.com/articles/nrc2373
- SLP-for-DC-presentation — https://pmc.ncbi.nlm.nih.gov/articles/PMC6422379/
- Theranostics 2020 SLP 综述 — https://www.thno.org/v10p6011.htm
- Mabtech ELISpot 肽长论坛 — https://www.mabtech.com/forum/topic/900-peptide-length-for-elispot
