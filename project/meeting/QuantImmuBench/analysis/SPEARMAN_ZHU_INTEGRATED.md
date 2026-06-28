# Spearman 评判框架 — 结合朱同学 pooling 研究（17 工具）

> 服务 quantimmu-bench。建档 2026-06-27；**2026-06-28 IMPROVE 跑通后全量重算更新**（pooling_*_17tools.csv 同步重跑，多工具 count-safe ρ 有变动）。把 spearman 评判从「单一聚合取最高」升级为「结合朱同学 pooling 发现的多维评判」，覆盖全 17 工具（含 7 新工具）。
> 数字真源：`analysis/pooling_global_spearman_17tools.csv`（17×8）· `pooling_best_per_tool_17tools.csv`（每工具 max vs count-safe）· `pooling_count_confound_17tools.csv`（混杂诊断）。脚本 `analysis/pooling_sweep_17tools.py`。
> 红线：netmhcpan_ba/TSCAPE pending_DTU_consent；HLAthena=presentation proxy 单列；geomean 类有 min-shift 实现注意仅探索。

---

## 0. 为什么评判要变（朱同学的核心贡献）

朱同学发现：**同一工具，换 pooling（子肽×HLA → 肽级聚合）方式，Spearman 可翻倍**——netMHCpan 亲和 max=0.196 vs topk_w=0.395。这意味着**「报一个工具的 spearman」本身是不完整的**——你报的是「这个工具 + 你选的那个 pooling」的联合结果。之前新工具 PPT / 横评 PPT 都只取「best-agg 或 max」单值，掩盖了 pooling 维度。

本框架把评判升级为三条原则：
1. **不报单一聚合**：每工具并列 `max`（生物先验=单显性表位/best-binder）与 `count-safe 最优`（生物先验=表位库 repertoire）两套数。
2. **剔 count 混杂**：`sum` 几乎纯测肽长度（假象），长肽富集工具连 max 都可能泄漏长度 → 逐格用 `|ρ(pooled, 子肽数)|>0.5` 剔除后再选最优。
3. **对天花板定位**：把每工具最优 ρ 放进四方夹逼的 0.33–0.43 天花板区间看，而非孤立比大小。

---

## 1. 17 工具 max vs count-safe 最优排行（pooling_best_per_tool_17tools.csv）

| 工具 | 类别 | max ρ | count-safe 最优 pooling | count-safe ρ | Δ(safe−max) | pooling spread | caveat |
|---|---|---|---|---|---|---|---|
| **netmhcpan_ba** | 新·结合 | 0.090 | geomean* | **0.396** | **+0.306** | 0.306 | ⚠️ DTU pending · geomean* |
| PredIG | 旧 | 0.201 | geomean* | **0.365** | +0.165 | 0.166 | geomean*（稳健 mean=0.279,已显著）|
| HLAthena | 旧·proxy | 0.091 | geomean* | 0.330 | +0.239 | 0.239 | proxy 不计·geomean* |
| IMPROVE | 旧 | 0.252 | top3mean | **0.323** | +0.071 | 0.145 | ✅重推理完成·稳健·非混杂·**全榜最强稳健 count-safe** |
| MHCflurry_affinity_neg | 新·结合 | 0.128 | top3mean | 0.235 | +0.107 | **0.503** | ⚠️ 聚合方向翻转·部分混杂 |
| PRIME | 旧 | 0.158 | top3mean | 0.214 | +0.056 | 0.095 | 稳健·非混杂 |
| MHCflurry_presentation | 新·提呈 | 0.098 | top3mean | 0.171 | +0.073 | 0.089 | — |
| NeoTImmuML | 旧 | 0.022 | geomean* | 0.159 | +0.137 | 0.142 | geomean* |
| ImmuneApp | 旧 | 0.079 | geomean* | 0.135 | +0.056 | 0.073 | geomean* |
| IEDB_Calis | 新·统计 | 0.096 | geomean* | 0.122 | +0.025 | 0.154 | geomean* |
| pTuneos | 旧 | 0.119 | max | 0.119 | 0.000 | 0.207 | max 即最优 |
| Repitope | 新·HLA-agnostic | 0.084 | softmax | 0.088 | +0.004 | 0.072 | pooling 救不了 |
| CNNeo | 新·LLM | 0.085 | max | 0.085 | 0.000 | 0.279 | pooling 救不了 |
| BigMHC | 新·迁移 | -0.041 | sum | 0.078 | +0.119 | 0.177 | 无信号·sum 疑 count 混杂 |
| DeepImmuno | 旧 | -0.089 | geomean* | -0.081 | +0.008 | 0.225 | 无信号·pooling 救不了 |
| deepHLApan | 旧 | 0.002 | softmax | -0.054 | -0.055 | 0.250 | ⚠️ max/top-k 全 count 混杂(去混杂后无信号)|
| TSCAPE | 新·多域 | -0.139 | max | -0.139 | 0.000 | 0.242 | ⚠️ 全聚合负·重算后已不显著·方向待核·DTU |

\* geomean 标星 = per-peptide min-shift 实现，跨肽尺度扭曲，**仅探索**；稳健替代用 mean/top3mean。

---

## 2. 三条结合朱的关键洞察

### 2.1 结合亲和力工具 pooling 增益最大 —— 直接呼应朱
朱的翻倍效应在 **netAffneg_9（netMHCpan 亲和）** 上最强。我们 17 工具全集印证：**Δ(safe−max) 最大的就是结合类工具** netmhcpan_ba（+0.306，重算后）。机制一致——结合亲和力分数在子肽间差异大，max（只取最强结合）丢掉了「次强结合子肽群」携带的信息，count-safe 聚合（geomean/top-k）救回。**这是朱发现的全集复现**（量级因数据口径不同不逐位对齐，但结构性方向一致）。

### 2.2 max 系统性低估有信号工具 0.05–0.34
对有真实信号的工具（netmhcpan_ba/PredIG/HLAthena/IMPROVE/PRIME/MHCflurry_affinity_neg），`max`（业界默认 best-binder）系统低估其相关 0.06–0.31。**主排行榜应改用 count-safe 最优**，max 保留作「单显性表位假设」对照。

### 2.3 pooling 救不了无信号工具（诚实负例）
Repitope(spread 0.072)/CNNeo(max 即最优)/BigMHC/DeepImmuno/TSCAPE 换任何 pooling 都不正/不显著——**pooling 敏感度本身是工具特性，信号弱的工具换 pooling 也救不了**。TSCAPE 全聚合负相关、方向待核（不擅自取反）。

---

## 3. 天花板夹逼（四方独立证据收敛 0.33–0.43）

| 来源 | 上限 ρ | 口径 |
|---|---|---|
| 理论估计（THEORY_quant，低置信）| 0.4–0.6 | 信息论上界 |
| 朱同学融合 | 0.43（p=0.70 不显著）| ds2 subset |
| I-fusion 点估 | 0.328 | per-patient LOPO |
| F-pilot 集成 | 0.328 | per-patient LOPO |
| **17 工具 count-safe 单工具上限（探索口径）** | netmhcpan_ba geomean 0.396* / PredIG geomean 0.365* | 全局 Spearman |
| **17 工具稳健单工具上限（非 geomean*/非 DTU）** | **IMPROVE top3mean 0.323** | 全局 Spearman |

→ **四方夹逼出「现有肽+HLA 信号的定量上限 ≈ 0.33–0.43」**（2026-06-28 重算后探索上沿略降至 netmhcpan_ba geomean 0.396*，Zhu fusion 0.43 仍锚定顶端）。netmhcpan_ba 的 0.396 落在上沿，但 geomean* + DTU pending + 全局口径（非 per-patient）三重 caveat，不能当 headline 卖；**可作 headline 的稳健单工具上限 = IMPROVE top3mean 0.323**（非 geomean*、非 DTU、global+per-patient 双显著）。**核心评判结论不变：现有工具及任意组合的定量能力撞 0.33–0.43 天花板，要飞跃须喂新信号（供体 TCR/HLA/precursor）或扩数据。** 这正是 QuantImmune 立项的统一依据。

---

## 4. 给 PPT 的图清单（5 工具版式下用）

| 图 | 文件 | 评判用途 |
|---|---|---|
| 17 工具×8 pooling 热图 | `figures/pooling_heatmap_global_17tools.png` | 展示 pooling matters + count 混杂格打叉 |
| max vs count-safe 条形 | `figures/pooling_max_vs_countsafe_17tools.png` | 每工具回升量 Δ（结合亲和力最大）|
| pooling spread 条形 | `figures/pooling_spread_17tools.png` | pooling 敏感度=工具特性 |
| **天花板夹逼图** | `figures/spearman_ceiling_squeeze_17tools.png` | 头条：四方收敛 0.33–0.43 + 17 工具落点 |
| 17 工具 corrected spearman/AUC | `figures/fig_{spearman,auc}_17tools_corrected.png` | 单聚合横评（标"见 pooling 分析"）|

**PPT 评判叙事**：单聚合横评（现状）→ 但 pooling 决定排序（朱）→ max vs count-safe 双口径 → count 混杂必剔 → 天花板夹逼 → 定量飞跃须新信号。

---

## 5. caveat / 待核

- **netmhcpan_ba 0.396**（重算后，原 0.430）：geomean min-shift 仅探索 + DTU pending + 全局非 per-patient，三重 caveat，不作 headline。
- **MHCflurry_affinity_neg**：spread 0.503 最大但聚合方向翻转（max+ / mean− / top3+）+ 部分 count 混杂 + per-patient CI 重算后含 0（掉出显著），报告须说明聚合依赖性。
- **deepHLApan**：max/top3mean/topk_w/rankdecay 全 count 混杂（ρ≈0.63），去混杂后无真信号——「正相关」是肽长假象。
- geomean* 全部标星：稳健口径用 mean/top3mean。
- reinference_pending：Phase B 重推理已陆续完成（IMPROVE 06-28 跑通 n86→101，P101/P102 已全量重算）；NeoTImmuML/Repitope 本就 False。pooling csv 内 reinference_pending 旗标可能滞后，以最新 metrics csv 为准。
- 朱 topk_w 的 k/权重、softmax T、rankdecay d 实现细节待朱本人对账（本研究用标准默认 + 敏感性扫描）。
