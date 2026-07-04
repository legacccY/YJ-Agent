# 干净标准结果总表（writer 单一数据来源）

> 从零重建后的最终锁定数字，按 outline § 组织。**writer 只用本表 + 对应 csv，不用重建前的旧数（旧表已标 legacy）。** 口径：官方 130 肽 / 9 患者（P101-110 缺 P103）/ 9mer 主分析 / 含突变窗过滤 / 4 outline pooling / 零选择 max 维 / 跨病人等权 Fisher-z / 数字均 Bash 核 csv + verifier PASS。
>
> **两处待袁老师定后才终稿**（见 `给袁老师_两个方法学问题.md`）：① 肽长控不控为主指标 ② geomean 措辞强弱。本表数字不变，仅措辞随拍板调整。

---

## §3.1 单工具基线（表5/图1）— 真源 `analysis/official/recompute_effN/R1_recomputed_effN8.csv`（2026-07-03 **覆盖修复 remerge 后重算**，Entry 49）
> 🔴 **覆盖修复（Entry 48-49）**：8 工具（MHCnuggets/MHCseqNet/netMHCstabpan/andy90/MUNIS/ImmuGenX/DeepNetBim/Seq2Neo）全量重跑补满 130/130 覆盖 → patch 进 merged 副本 → p0e2 重池化 → effN8 重算。**后果：原缺 P102 的工具（MHCnuggets/MUNIS/MHCseqNet 等）从 8/9 升 9/9，主榜 15→22 个**。数字均 Bash 核 csv + verifier PASS（含填值符号逐格对、pre-covfix 0.4602 精确重现）。
> 🔴 **口径（Entry 47 沿用）**：图1 = **effN≥8 门槛 + 9mer**。effN≥8 保全 9 患者且去 2-3 点撞 ±1 伪迹（effN≥5≡≥8 数值全同）；effN≥10 会结构性剔掉 P102（整患者仅 8 肽、最难）。

per-patient Spearman(工具 max-pool 分, ELISpot)，跨患者 Fisher-z 等权聚合，effN≥8，**主榜 = 23 个 9/9 全覆盖工具**（含 deepHLApan indel 补跑后新入榜，见下）：

| 工具 | rho(effN8) | 95% CI | 覆盖 | 注 |
|---|---|---|---|---|
| MHCnuggets | **+0.447** | [+0.32,+0.55] | 9/9 | 覆盖修复后升 9/9（含最难 P102），数值居首；呈递/结合类 |
| netMHCpan_BA | +0.392 | [+0.14,+0.59] | 9/9 | 亲和 baseline 锚点（DTU 受限）；CI 宽，P102 上 rho=−0.36 |
| MHCflurry | +0.308 | [+0.17,+0.46] | 9/9 | 稳 |
| PRIME | +0.294 | [+0.12,+0.47] | 9/9 | 稳 |
| IMPROVE | +0.285 | [+0.09,+0.48] | 9/9 | 稳 |
| PredIG | +0.250 | — | 9/9 | 稳 |
| IEDB_Calis | +0.249 | — | 9/9 | 稳 |
| MHCseqNet | +0.246 | — | 9/9 | 覆盖修复后升 9/9（原 8/9 参考区）|
| netMHCstabpan | +0.234 | — | 9/9 | 覆盖修复后满 130（原 43 肽）|
| MUNIS | +0.207 | — | 9/9 | 覆盖修复后升 9/9（P102 补入 rho=−0.60 拉低，原 8/9=0.304）|
| …（余 12 个 9/9 见 csv）| | | | BigMHC_IM 0.179 / netMHCpan_EL 0.179 / ImmuneApp 0.179 / …/ Seq2Neo 0.072 / andy90 0.033 |

- **headline（top-cluster,不排单一王座）**：顶部工具 **0.39–0.45 无单一压倒者**（MHCnuggets 0.447 / netMHCpan_BA 0.392 / MHCflurry 0.308），CI 大幅重叠（MHCnuggets[0.32,0.55] vs netMHCpan_BA[0.14,0.59]）。全 ≤0.45 天花板、合文献 0.15–0.35。⚠️ **headline 措辞待袁老师定**：MHCnuggets 覆盖修复后客观数值第一但与 netMHCpan_BA 差 0.055 且 CI 重叠、P102 仅 8 点 rho=0.119——「单一最强」脆，故本表采 top-cluster 表述；netMHCpan_BA 仍作亲和 baseline / fusion 对照锚点。
- **🔴 主榜工具数 15→22→23**（覆盖修复的直接后果）：15→22 = MHCnuggets/MUNIS/MHCseqNet/netMHCstabpan/Seq2Neo/andy90/ImmuGenX 补满 P102 等缺口后升 9/9；**22→23 = deepHLApan indel 补跑**（Entry 51-DEEPHLA-INDEL）——它本是 context-free 单肽打分被 MT-WT 配对输入误滤了 28 indel + 1 SNV，补跑 context-free MT-only 打分后 101→130，n_full 8→9 入榜（rho 0.101→**0.052**，排 22/23 弱预测，与文献 deepHLApan AUC≈0.40 一致）。
- **⚠️ deepHLApan 补跑后 rho 降**（0.101→0.052）：8/9 时靠缺最难患者的易子集偏高，补满 9/9 后回落真值——与「防覆盖子集不同致虚高」同理，不是变差是变真。
- **⚠️ DeepNetBim 掉榜（coverage_fail, rho=nan）**：补满覆盖后 max-pool 饱和到全 130 肽 =1.0（工具本身 29% 对输出 1.0 天花板，每肽≥1 子肽命中→max 常数列）。**仅 max-pool 退化**，换 topk(k≥2)/softmax/rankdecay 任一算子方差恢复可算 rho（见 §3.2）→ 作 pooling 算子决定成败的正面案例，不入 §3.1 max-pool 主榜。
- **8/9 覆盖工具（5 个,非满覆盖不入主榜同患者集可比）**：NetTepi 0.293(13 等位上限)/ICERFIRE 0.250/HLAthena 0.207/pTuneos 0.117/NeoaG −0.045——均**真差分/异己性**(pTuneos/ICERFIRE/NeoaG 需 MT-vs-WT，脚本证据坐实)或**等位硬限**(NetTepi 13 等位/HLAthena 缺 P101 部署可补)，论文标诚实覆盖上限。NeoaPred coverage_fail(n_full=1, 14/130 结构 9mer)。**deepHLApan 已移出此组**（补跑入主榜）。
- ⚠️ **控肽长偏相关（袁老师问题一）本轮未在 effN8 重算**（拍板级：肽长控不控进排名未定），主图只报裸 rho。
- 敏感性 5/8/10 三档：`R1_effN_sensitivity_5_8_10.csv`。总账 = **24/30 工具到 130 覆盖**（deepHLApan indel 补跑后 23→24；覆盖矩阵图 `Results/effN_coverage_matrix.png`）。

## §3.2 pooling 规律（表3/图2「洗牌」）— 真源 `R2_pooling_sweep_official.csv` + `R2_best_per_tool.csv`
- 亲和类靠聚合（控肽长后仍成立）：netMHCpan_BA max 0.43 → topk_k5 **0.52**、topk_k20(netAffneg) 0.46。
- ⚠️ 免疫原类「max 即最优」软化：控肽长后免疫原类 best-vs-max 中位 gain 仅 +0.05（噪声内），且大 k topk 会把肽长混杂捡回（须用控肽长版选 best）。

## §3.3.1 12 fusion 点估计（表6）— 真源 `R3_fusion_12methods_official.csv`
- dim7 max 维：geomean/mean_rank/median/min/weighted 紧簇 0.33–0.39，**统计打平无点冠军**。

## §3.3.3 nested-LOPO（表8）+ §3.3.5 显著性 — 真源 `R5_*` / `R7_*`
> §3.3.3/§3.3.5 数字 2026-07-04 同步至 covfix 后 canonical（Entry 54）；§3.3.3 已补 1000 次置换 null（经验 p=0.013，信号显著非泄漏）。
- nested-LOPO（表8）：LOPO ρ=**0.275**（控肽长 0.257）vs oracle ρ=**0.297**，gap **0.018** → 内层选超参近零过拟合。
- shuffle-null（1000 次置换，`R5_permutation_null.py`）：null 分布居中于 0（mean=−0.00，std 0.14，[q2.5,q97.5]=[−0.28,+0.24]），真 LOPO ρ=0.275 落 **98.8 分位**（1000 次里仅 12 次 ≥ real），**经验 p=0.013 < 0.05 → nested-LOPO 信号显著、非泄漏**（单次置换旧值 0.279 系高方差伪影，已被 1000 次分布证伪）。
- §3.3.5 整合 vs 最强单：整合(SURV6 geomean, max 维) = **0.366** vs 最强单 MHCnuggets = **0.447**（covfix 补满 9/9 覆盖、零选择池 15→24 工具后 MHCnuggets 居首）。
- 配对置换 **p=0.46（裸）/ 0.22（控肽长）→ 整合与最强单统计上持平**（p>0.05）；但点估上整合略逊于 covfix 后的最强单 MHCnuggets（Δ=**−0.081**，gap 较 covfix 前 −0.030 扩大，bootstrap CI 上界从 +0.210 收窄到 **+0.079** 贴近 0）。价值=不知最优工具时给稳健近最优输出（按鲁棒性部署）。

## §3.3.4 删突变鲁棒性（表9/图3）— 真源 `R6_robustness_official_summary.csv`（2026-07-04 同步 covfix canonical）
win_top1（drop10%，30 seed）：

| fusion | win_top1 | rank |
|---|---|---|
| **geomean** | **0.567** | **1** |
| min | 0.300 | 2 |
| weighted_mean_rank | 0.100 | 5 |
| mean_rank | 0.000 | 4 |
| median | 0.000 | 7 |
| max | 0.000 | 14 |
- geomean 删 10% win_top1=**0.567**、删 20%=**0.600**，两档均 rank1（鲁棒众数第一）；但 min 紧咬（0.30/0.13）、跨维一致判据 weighted_mean_rank 略胜（诚实局限）。
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
