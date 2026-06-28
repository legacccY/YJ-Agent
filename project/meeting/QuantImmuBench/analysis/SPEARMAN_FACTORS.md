# SPEARMAN_FACTORS — 工具预测分 vs ELISpot 真值的相关性「因素分析」

> 服务 quantimmu-bench benchmark 扩张 v2，**E-analysis 窗（factors 节点）**。建档 2026-06-26。
> **本档 = E1 预备版**：在现有 **9 工具**（DeepImmuno · PredIG · NeoTImmuML · IMPROVE · pTuneos · PRIME · ImmuneApp · deepHLApan · HLAthena[proxy]）上搭好因素分析框架并出全套预备图。
> **E2 待办**：metrics 节点解锁（A 窗灌入全 ~19 工具数据）后，同一框架重跑，刷新本档每条结论与图。
>
> **数据真源**：`scripts/out/merged_all_tools_9tools.xlsx`（34247 行炸开表，per-subpeptide × HLA）。
> **计算脚本**：`analysis/_explore_factors_framework.py`（一次跑出 7 个 `SPEARMAN_FACTORS_*.csv`）。
> **口径对账**：本框架 max 聚合 Spearman 与 A 窗 `metrics_ds2_9tools.csv` **逐工具 diff=0**（完全复现，无口径漂移）。
>
> **统一 caveat（每条结论都适用）**：
> - **HLAthena = presentation proxy**（预测 MHC-I 提呈，非免疫原性），ELISpot 上预期近随机，所有图/表单列标注，不与免疫原性工具 apples-to-apples。
> - **样本量小**：DS2 n≈100 肽、per-patient n_i=5-16。任何 ρ 的 95%CI 都很宽（肽级 ±0.20，患者级 ±0.5-0.7），数字不可过度解读。
> - netMHCpan/DTU 工具数字本框架不涉及（IMPROVE 用主路 `mean_prediction_rf`），无 pending 标记需求。
>
> ⚠️ **HLA-bug 修复修正（2026-06-27，详见 04_LOG Entry HLA-FIX）**：backbone 对患者 P101/P102 误读了源 `Elispot_Dataset2.xlsx` 的伪迹列 HLA-1..6（2268 行 / 6.6% 污染，仅这两名患者），PredIG/deepHLApan 等 HLA-相关工具受影响。修正后（剔除 P101/P102，真源 `analysis/metrics_ds2_fixed_exclP101P102.csv`）：**PredIG 全局 Spearman 显著性不存活**（max ρ 0.198→0.104 p=0.343；mean ρ 0.280→0.188 p=0.084，均不显著）；**IMPROVE 仍稳健显著**（max 0.243→0.226 p=0.037；top3mean 0.320→0.283 p=0.008）；**TSCAPE 由不显著翻为显著负**（−0.135 ns→−0.230 p=0.033）；**deepHLApan 双重不可信**（肽长混杂假象 + merge 传播 bug 2069 行 NaN 回填）；**NeoTImmuML/Repitope HLA-agnostic 不变**。本档凡引用 PredIG 全局/聚合 ρ 与 deepHLApan 的结论均受影响，corrected 值待 Phase B 重推理；现阶段以 corrected-excl 为准。**E2 重跑时本档 PredIG/deepHLApan 结论需同步刷新。**

---

## 数据底盘（先看清两个数据集的「天生差异」）

| | DS1 | DS2 |
|---|---|---|
| 肽数 | 82 | 101 |
| 整肽长 | **全部 9mer**（短肽，等于子肽） | **15-29mer 长肽**（被滑窗切成 8-14 子肽，再 best-binder 聚合） |
| 阳性比 | — | >0 阈值下 90 阳 / 11 阴（极不平衡） |

这个差异本身就是一个因素：DS1 测「短肽直接打分」，DS2 测「长肽切窗 + 聚合」，两者不是同一任务。

---

## 因素 1 — 聚合方式（max / mean / top3mean）

**图**：`figures/factors_aggregation.png`（9 工具 × 3 聚合的 ρ 分组柱）
**csv**：`SPEARMAN_FACTORS_aggregation.csv`

**结论**：**max（best-binder 主口径）不是普遍最优**。三种聚合各赢 3/2/3 个工具，非代理工具均值几乎持平（max 0.091 / mean 0.079 / top3mean 0.098，差 <0.02）。
- 两个唯一统计显著工具的最优聚合**都不是 max**：**IMPROVE top3mean ρ=0.320**（>max 0.243）、**PredIG mean ρ=0.280**（>max 0.198）→ 说明这俩工具内部不是纯「取最强子肽」逻辑。
  - **(2026-06-27 HLA bug 修复后修正，详见 04_LOG Entry HLA-FIX)**：剔 P101/P102 后**仅 IMPROVE 仍统计显著**（top3mean 0.320→0.283 p=0.008；max 0.243→0.226 p=0.037）；**PredIG 全聚合显著性不存活**（mean 0.280→0.188 p=0.084；max 0.198→0.104 p=0.343）。「两个显著工具」应修正为「仅 IMPROVE 显著」。
- 反例 **pTuneos**：max 0.136 >> mean 0.029，是少数真符合 best-binder 语义的工具。
- **DeepImmuno** 三种聚合全为负，换聚合救不回来。

**对横评的含义**：聚合方式是次要因子，工具本身是主因子。报「best-binder 最优」需加注——它在最强的两个工具上反而非最优。主口径仍用 max（与文献 pVACseq/IEDB Aggregator=Maximum 对齐），但 IMPROVE/PredIG 应并报敏感性。

---

## 因素 2 — per-patient vs 全局 ρ（最重要 ⭐）

**图**：`figures/factors_perpatient.png`（每工具 ρ_i 患者内分布 box+strip，叠全局 ρ 红叉 + Fisher-z 均值）
**csv**：`SPEARMAN_FACTORS_perpatient_global.csv` / `_within.csv`（已对账 A 窗 `per_patient_spearman_9tools.csv`，定性一致）

**这是支撑 STORY「现有工具是分类器非定量回归器」的核心因素。**

**结论 1 — 全局 ρ 排名 ≠ per-patient 排名（Simpson 混淆真实存在）**：
- **deepHLApan**：全局 ρ=+0.04（第 7）但 Fisher-z within=+0.26（第 1），rank Δ=−6 → 患者间 ELISpot 量级差异把它的患者内信号**压平**（全局严重低估）。
- **HLAthena[proxy]**：全局 ρ=+0.08 但 within 中位数 ρ_i≈+0.009（≈0）→ 那点全局正值**完全由患者间量级撑起**（典型 Simpson 虚高）。印证它在 ELISpot 任务上 within-patient 无效。

**结论 2 — 9/9 工具患者内 ρ_i 都出现符号翻转**：每个工具都有些患者 ρ_i>0、另一些 ρ_i<0。连排名第一的 IMPROVE 也在 3/9 患者内为负。top 工具（IMPROVE/PredIG）Fisher-z CI 下限贴零（0.02 / −0.00）。
→ **没有任何工具能在单个患者内可靠地按 ELISpot 量级排序肽段** = all classifiers, not regressors。这是本 benchmark 最硬的结论。

**警告**：n_i=5-16 → 单患者 ρ_i 的 95%CI ≈±0.5-0.7，图中每个点不可单独解读，只有跨 9 患者汇总才有弱信号。deepHLApan「Fisher-z 第一」也脆弱（std 最高 0.43），见因素 5 bootstrap。

---

## 因素 3 — 肽长分层（DS1 短肽 vs DS2 长肽 + DS2 内分桶）

**图**：`figures/factors_length.png`（DS1 vs DS2_all 对比）+ `figures/factors_length_ds2strata.png`（DS2 三长度桶）
**csv**：`SPEARMAN_FACTORS_length.csv`

**结论 1 — DS1（短9mer）信号普遍弱于 DS2（长肽）**：6/8 非代理工具从 DS1→DS2 出现正向 Δ（中位 +0.17）。提示这类工具对长肽更匹配（长肽涉及更多加工/提呈步骤，工具内置特征能抓）。但 DS2 上仍只 2 个工具 p<0.05。

**结论 2 — DS2 内无单调「长肽→best-binder max 虚高」趋势**（修正分桶后，15-18 n=22 / 19-22 n=49 / 23+ n=30 才有意义）：IMPROVE/PRIME 在最长桶(23+)略升（0.28/0.25），但 n=30 不显著；多数工具桶间无系统规律。**「长肽切更多子肽→max 系统虚高」假说在现有数据不成立**。

**异常 — deepHLApan DS1 ρ=−0.503（p<0.001）强负相关**：DS2 恢复到≈0。最可能解释：deepHLApan 在 9mer 输出的是 presentation/binding score，高结合≠高 ELISpot 免疫原性（提呈与 T 细胞激活解耦，甚至负相关）。**是工具设计边界，非 bug**（已核分数分布；建议 E2 补 scatter 复核再定是否单列）。同样 DeepImmuno 在 DS2 短/长桶都强负（-0.49/-0.48）中桶正(+0.19)，待 E2 深挖。

---

## 因素 4 — 阈值（>0 / >10 / >median）对分类可分性

**图**：`figures/factors_threshold.png`（9 工具 × 3 阈值的 AUC 柱）
**csv**：`SPEARMAN_FACTORS_threshold.csv`
（注：阈值只改二元标签 → 影响 AUC，不影响 Spearman 输入）

**结论 — AUC 随阈值收紧单调下降，>0 的高 AUC 部分是结构伪迹**：
- 非代理均值 AUC：>0 0.588 → >10 0.563 → >median 0.541。
- **>0 极不平衡（90 阳/11 阴）**，仅 11 个负例时稍好排序即拉高 AUC。典型：**pTuneos >0 AUC=0.753 但 >median 跌到 0.530** → 「高分」依赖松阈值下极少数负例排序，非真鉴别力。
- **最平衡、最保守 = >median（50/51）**，工具间差距也最小（越严越趋随机）。

**对横评含义**：主图建议 **>0 + >median 双报**（看效应漂移），别只报单阈值；任何「某工具 AUC 高」必标注阈值。

---

## 因素 5 — 小样本 ρ 稳定性 bootstrap（B=2000, seed=42）

**图**：`figures/factors_bootstrap.png`（9 工具 caterpillar/forest，ρ_point + 95%CI，绿=不跨0 / 红=跨0）
**csv**：`SPEARMAN_FACTORS_bootstrap.csv`

**结论 — 9 工具里只有 IMPROVE 的 ρ 统计上不可排除真信号**：
- **IMPROVE**：ρ=0.243，95%CI **[0.046, 0.423] 全正不跨 0** ← 唯一稳健。
- **PredIG**：CI [−0.001, 0.380] 刚好擦 0 → 边缘信号，不宜与 IMPROVE 并列「有信号」。**(2026-06-27 HLA-FIX 进一步坐实)**：剔 P101/P102 后 PredIG max ρ=0.198→0.104（p=0.343 不显著），边缘信号确实由污染患者撑起，全局显著性不存活。
- **其余 7 个（含 HLAthena proxy）CI 明确跨 0** → 与「零相关」统计不可区分。
- 全工具 rho_std_boot≈0.10（CI 宽≈±0.20）= n≈100 的系统性基线噪声，**不是工具缺陷**。只有 IMPROVE 在这噪声下仍显著。

**这是 benchmark 的稳健性底线结论**：n≈100 下，能站住的「定量相关」屈指可数，benchmark 报告必须如实呈现宽 CI，不能拿点估值卖。

---

## 因素 6 — 工具间一致性（9×9 Spearman ρ 热图）

**图**：`figures/factors_toolconsistency.png`（9×9 热图，coolwarm 中心0，HLAthena 标 proxy）
**csv**：`SPEARMAN_FACTORS_toolconsistency.csv`

**结论 1 — 整体一致性极低（mean 两两 ρ=0.130，中位 0.088）**：36 对里绝大多数 ρ<0.3。同一批肽送进不同工具，排名几乎无法互换 → 直接支撑 STORY「现有工具缺共识标准、各说各话」。

**结论 2 — 唯一高相关对 IMPROVE↔PRIME ρ=0.689**，且两者都与 **HLAthena（提呈 proxy）中等相关**（PRIME 0.52 / IMPROVE 0.46）。
→ **假说（待 E2 验证，不当定论）**：IMPROVE/PRIME 输出里可能「提呈信号占主导」而非独立免疫原性建模。E2 建议：把这俩在 ELISpot 上的性能拆成「提呈阳性肽 vs 阴性肽」子集看 AUC 是否分层。

**结论 3 — NeoTImmuML 是孤立异类**：与几乎所有工具不相关甚至轻度负相关（与 HLAthena −0.23）。底层特征/模型与其余 8 个完全不同，要么捕获正交真信号、要么系统偏差反转，待 ELISpot GT 进一步判。

---

## E1 总账（一句话）

> 在 9 工具现有数据上，**聚合方式是次要因子、工具本身是主因子**；**全局 ρ 被患者间量级混淆**（per-patient 内全工具符号翻转 = 分类器非回归器）；**阈值越严越保守、>0 的高 AUC 含结构伪迹**；**bootstrap 下仅 IMPROVE 一个工具 ρ 不跨 0**；**工具间一致性极低（mean ρ=0.13）= 各说各话**。HLAthena 全程 proxy 单列。
>
> **框架已就绪**，metrics 节点一解锁即把全 ~19 工具灌入同一脚本重出（E2）。

## 待 E2 / 交接清单
- [ ] metrics 解锁 → `_explore_factors_framework.py` 跑全工具，刷新本档 6 因素。
- [ ] deepHLApan / DeepImmuno DS1/DS2 强负相关：补 scatter 复核机制，定是否单列。
- [ ] IMPROVE/PRIME「提呈污染」假说：拆提呈阳/阴子集验 AUC 分层。
- [ ] per-patient 聚合：接 A 窗 `per_patient_spearman_9tools.csv` 的 Fisher-z/median 正式聚合做主报（本档用原始 ρ_i）。
