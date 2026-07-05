# 矫正法菜单 + novelty 定位（文献支撑）

> 服务 QuantImmuBench 肽长×ELISpot 混杂 § Part2/PPT。researcher 联网查证，2026-07-05，带引用。

## Novelty 定位

- **「肽长是免疫原性特征」不 novel**：多工具 SHAP 显示肽长+疏水性/分子量是 top 决定因子，早进模型（NAR Cancer 2024 PMC10823584；Front Immunol 2026）。
- **「把肽长当评测混杂、用偏相关/残差化统计扣除以防工具排名虚高」未见先例**：领域标准动作是控 **MHC binding** 混杂（"binding is a confounding variable if trying to assess immunogenicity predictor performance"，Exploration of Immunology 综述）+ **长度分布匹配**（TESLA/benchmark 保证肽长分布符合 MHC-I 天然配体预期），**没有针对 SLP 疫苗 per-patient ELISpot 幅度的长度混杂秩相关矫正**。
- 已有旁证「长肽更依赖表达/呈递来预测」（PMC5694748）暗示长度需单独处理，但停在建模启示、未做评测矫正。
- **判定**：这个角度（长度作评估混杂 + 统计矫正）可作 novelty 主张。TODO：若审稿要穷尽，再查 IEDB benchmark 官方 + Nielsen/Buckley 组近文。

## 矫正法菜单（6 族，本场景 = per-patient 秩相关 / n≈9 / 混杂与信号共线）

| 方法 | 原理 | 本场景适用性 |
|---|---|---|
| ① **偏 Spearman**（两侧去混杂，**主分析**） | X、Y 各就 Z 取残差再相关（秩残差 PSR，Liu 2018 Biometrics） | **最贴合**：秩基、对称去长度，小样本方向/效应量可信（功效低需报） |
| ② **残差化 ELISpot**（只去标签侧长度，**稳健性对照**） | 只对结局 Y 就 Z 回归取残差（FWL 思想） | **适合对照**：认定长度只污染标签时更贴合；与①一致则加固 |
| ③ 分层/分箱内比较 | 混杂同层内估计再合并 | **弱**：连续肽长分箱 + n≈9 每层过少，仅示意 |
| ④ 回归调整/协变量入模 | 肽长作协变量同入回归估偏效应 | **可补充**：能同控多混杂(子肽数/HLA数)，但小样本+共线系数不稳 |
| ⑤ IPW/matching | 倾向得分加权/匹配平衡混杂分布 | **不推荐**：为离散 treatment 设计，肽长连续、n≈9 权重不稳 |
| ⑥ 秩内归一 | 层内秩归一再合并 | **仅附注**：同受小样本分层拖累 |

**主张**：矫正有多族标准法；本场景分层/IPW/matching 因小样本+连续暴露失效，故选 **①偏 Spearman（主）+ ②残差化 ELISpot（稳健性对照）**，二者一致即加固。

## 关键引用
- Beyond MHC binding 综述 — https://www.explorationpub.com/Journals/ei/Article/100391
- TESLA / Wells et al. Cell 2020 — https://www.cell.com/cell/fulltext/S0092-8674(20)31156-9
- NAR Cancer 2024 肽特征 — https://www.ncbi.nlm.nih.gov/pmc/articles/PMC10823584/
- 长肽更依赖表达 — https://www.ncbi.nlm.nih.gov/pmc/articles/PMC5694748/
- Liu 2018 Biometrics 偏 Spearman(PSR) — https://onlinelibrary.wiley.com/doi/10.1111/biom.12812
- CLEP 控混杂综述 — https://www.dovepress.com/control-of-confounding-in-the-analysis-phase-ndash-an-overview-for-cli-peer-reviewed-fulltext-article-CLEP
- Austin 2011 倾向得分 — https://pmc.ncbi.nlm.nih.gov/articles/PMC3144483/
