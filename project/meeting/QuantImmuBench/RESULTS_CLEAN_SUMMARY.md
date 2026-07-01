# 干净标准结果总表（writer 单一数据来源）

> 从零重建后的最终锁定数字，按 outline § 组织。**writer 只用本表 + 对应 csv，不用重建前的旧数（旧表已标 legacy）。** 口径：官方 130 肽 / 9 患者（P101-110 缺 P103）/ 9mer 主分析 / 含突变窗过滤 / 4 outline pooling / 零选择 max 维 / 跨病人等权 Fisher-z / 数字均 Bash 核 csv + verifier PASS。
>
> **两处待袁老师定后才终稿**（见 `给袁老师_两个方法学问题.md`）：① 肽长控不控为主指标 ② geomean 措辞强弱。本表数字不变，仅措辞随拍板调整。

---

## §3.1 单工具基线（表5/图1）— 真源 `R1_single_maxpool_official.csv`
per-patient Spearman，**裸 / 控肽长** 两列并报：

| 工具 | 裸 | 控肽长 | 注 |
|---|---|---|---|
| HLAthena | +0.627 | **+0.250** | 呈递代理，榜首大半是肽长搭便车（控后塌）|
| andy90 | +0.585 | **+0.189** | 同上，肽长伪迹 |
| netMHCpan_BA | +0.392 | **+0.432** | 亲和，控肽长稳→真最强单工具 |
| MHCflurry | +0.308 | +0.302 | 稳 |
| PRIME | +0.294 | +0.282 | 稳 |
| IMPROVE | +0.285 | +0.231 | 稳 |
- ⚠️ Seq2Neo 控肽长 0.874 = 稀疏工具（仅 43 肽）虚高，**排除出主榜**（coverage sparse）。
- 联合控 peplen+n_subpep+is_indel：netMHCpan_BA 0.42[稳]、HLAthena 0.20[塌]、andy90 0.09[塌]。

## §3.2 pooling 规律（表3/图2「洗牌」）— 真源 `R2_pooling_sweep_official.csv` + `R2_best_per_tool.csv`
- 亲和类靠聚合（控肽长后仍成立）：netMHCpan_BA max 0.43 → topk_k5 **0.52**、topk_k20(netAffneg) 0.46。
- ⚠️ 免疫原类「max 即最优」软化：控肽长后免疫原类 best-vs-max 中位 gain 仅 +0.05（噪声内），且大 k topk 会把肽长混杂捡回（须用控肽长版选 best）。

## §3.3.1 12 fusion 点估计（表6）— 真源 `R3_fusion_12methods_official.csv`
- dim7 max 维：geomean/mean_rank/median/min/weighted 紧簇 0.33–0.39，**统计打平无点冠军**。

## §3.3.3 nested-LOPO（表8）+ §3.3.5 显著性 — 真源 `R5_*` / `R7_*`
- 整合(SURV6 geomean, max 维) = **0.362** vs 最强单 netMHCpan_BA = **0.392**。
- 配对置换 **p=0.79（裸）/ 0.24（控肽长）→ 统计持平**（非"输"）。价值=不知最优工具时给稳健近最优输出（按鲁棒性部署）。

## §3.3.4 删突变鲁棒性（表9/图3）— 真源 `R6_robustness_official_summary.csv`
win_top1（drop10%）：

| fusion | win_top1 | rank |
|---|---|---|
| **geomean** | **0.400** | **1** |
| min | 0.333 | 2 |
| weighted_mean_rank | 0.133 | 5 |
| mean_rank | 0.000 | 4 |
| median | 0.000 | 8 |
| max | 0.000 | 14 |
- geomean 是删突变鲁棒性众数第一，但 min 紧咬；跨维一致判据 weighted_mean_rank 略胜（诚实局限）。
- ⚠️ **数学近亲**：geomean/mean_rank/median 排序相关 0.90-0.97（秩指标下本应如此，见给袁老师档），"唯一"难 claim。

### §3.3.4b geomean 数学近亲的正式检验（回答袁老师问题二，2026-07-01 补，verifier PASS）
> 口径=SURV6 六工具最强窗口维（**不是 dim7**，口述曾误记；数值与 R3 ndim=6 逐位一致）。真源 `Q2_fusion_kinship_paired.csv` / `Q2_peptide_auprc_kinship.csv` / `Q2_rank_corr_matrix.csv` / `analysis/theory/Q2_taylor_verification.csv`。

| 检验 | geomean vs mean_rank | geomean vs median | 判定 |
|---|---|---|---|
| patient 配对 n=9 裸 | p=0.79 | p=0.023 | mean_rank 真近亲；median 略偏 |
| patient 配对 控肽长 | p=0.73 | p=0.46 | 控肽长后全不显著 |
| 肽级 AUPRC 130 肽（primary） | Δ=0.015 p=0.15 | Δ=0.028 p=0.19 | 更高功效下仍全不显著 |
| 病人内排序相关 | 0.952（pooled 0.972） | 0.912（pooled 0.949） | 坐实备忘 0.97/0.90 |
| 泰勒二阶验证 | 残差中位 0.041 / 相对误差中位 12.5% | — | G≈A−分歧度修正 成立 |

- 三融合法点估：geomean 0.362 / mean_rank 0.352 / median 0.267（per-patient Fisher-z ρ̄，紧簇打平）。
- **结论（措辞已定，待袁老师最终确认）**：geomean 与 mean_rank 秩融合在统计上不可分辨，属数学近亲（配对 p + 排序相关 0.95 + 泰勒机理三重佐证）；与 median 的差异在裸口径边界显著但控肽长/肽级功效下消失。geomean 有理论依据（乘性/AND 语义、抗离群），可作**有依据的稳健默认**，但**不宜称「唯一最优」**。

## §3.4 部署（表10/图4）— 真源 `R8_*`
- 方案A（务实默认）= 单亲和聚合 netMHCpan_BA topk(k=20,α=0) = **0.461**（1 工具，零学习最稳）。
- 方案B（按需）= 多维 geomean（dim7 = 0.378，不知最优工具时的稳健选择）。
- HLAthena/andy90 因稀疏覆盖 + 肽长伪迹**不入部署候选**。

## 副指标：肽级 AUPRC（补充，TESLA/IMPROVE 口径拿功效）— 真源 `S1_peptide_auprc*.csv`
平衡标签（Ttest_pvalue<0.05，76阳/54阴）配对 ΔAUPRC：
- geomean vs 最弱 fusion(maxrank)：Δ+0.069 **p=0.016 显著**（geomean 是最优 fusion）。
- geomean vs 最强单 netMHCpan_BA：Δ+0.030 **p=0.46 持平**（肽级也证实整合≈最强单）。
- ⚠️ 估计量换了（混病人内外、忽略患者结构），**与 per-patient Spearman 并列不替换**。

## 每修正净效应分账（方法学诚实点）— 真源 `S2_regime_compare.csv`
- 弃 sum（count 混杂）：平均 Δ **−0.103**（netMHCpan_BA −0.219 最大）。
- 控肽长：平均 Δ **−0.079**（HLAthena −0.377）。
- 含突变过滤：+0.013（netMHCpan_BA +0.127）。
- 等权（vs 逆方差）：+0.008。
- → 两大修正=弃 sum + 控肽长，精准砸中虚高工具。

---

## Discussion 必写的诚实局限（skeptic 认证）
1. n=9 患者功效有限，细粒度方法差异统计分不开（**不接外部队列，用户已定**）；per-patient rho 跨病人 −0.06~+0.72 极异质，SE≈0.12。
2. 整合 vs 最强单不显著（持平），设计层 selection bias（维度集/pooling 菜单看数据定）未进 CV。
3. 肽长/indel 混杂：主排名控肽长（待袁老师定）；is_indel 是比肽长更深的混杂。
4. geomean 与 mean-rank/median 秩指标下数学近亲，不 claim「唯一」。
5. bootstrap CI 基于 9 簇，标注为近似；DTU 工具数字（用户已定不考虑 consent 层面）。
6. HLA-II 仅 future work；所有增量结论待外部独立队列验证。

## 数据/代码可用性
- 主分析冻结表 `data/frozen/pooled_clean_9mer.csv`（sha256 已入 PROVENANCE.json）。
- 脚本 `analysis/phase0/p0e2_pool_clean.py`（数据处理）+ `analysis/official/R{1..9}_official.py` + `S1/S2`。
- ⚠️ tool_versions 仍 TODO（PROVENANCE.json），投稿前补 30 工具版本/commit。
