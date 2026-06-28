# Pooling 策略研究 — 子肽聚合如何决定免疫原性排序

> 服务 quantimmu-bench / H-pooling 窗。建档 2026-06-26。
> 承接朱同学 pooling 研究（QuantImmu/02 图）并整合进 9 工具 benchmark。
> 数字真源：`analysis/pooling_global_spearman.csv`（全局）· `analysis/pooling_2d_scan.csv`（二维）· `analysis/pooling_best_per_tool.csv`（最优）· `analysis/pooling_count_confound.csv`（混杂诊断）。脚本 `analysis/pooling_sweep.py`。
> 红线：DTU 工具数字 pending（当前 9 工具中无 netMHCpan 系，PRIME 学术免费不算）；HLAthena = presentation proxy 单列。

> ⚠️ **HLA-bug 修复修正（2026-06-27，详见 04_LOG Entry HLA-FIX）**：backbone 对患者 P101/P102 误读了源 `Elispot_Dataset2.xlsx` 的伪迹列 HLA-1..6（2268 行 / 6.6% 污染，仅这两名患者），PredIG/deepHLApan 等 HLA-相关工具受影响。修正后（剔除 P101/P102，真源 `analysis/metrics_ds2_fixed_exclP101P102.csv`）：**PredIG 的 pooling 增益不再带来全局显著**（max ρ 0.198→0.104 p=0.343；mean ρ 0.280→0.188 p=0.084，均不显著）；**IMPROVE 的 pooling 增益仍稳健显著**（max 0.243→0.226 p=0.037；top3mean 0.320→0.283 p=0.008）；**deepHLApan 双重不可信**（肽长混杂假象 + merge 传播 bug 2069 行 NaN 回填）。本档 PredIG/deepHLApan 的逐聚合 ρ 数字受 P101/P102 污染影响，corrected 值待 Phase B 重推理；现阶段以 corrected-excl 为准。「pooling 翻倍」的定性方向不变，但 PredIG 显著性结论失效。

---

## 0. 一句话结论

**「同一工具换 pooling，Spearman 可翻倍」这一现象在我们 9 工具全集成立（确认朱同学发现）；但其中 `sum` 类聚合的「提升」是肽长度混杂假象，必须排除——真正稳健的结论是：`max`（best-binder / 单显性表位假设）几乎从不是最优，top-k / 均值类聚合（表位库假设）普遍更好。**

---

## 1. 背景：两级聚合架构

新抗原免疫原性 benchmark 里，每条长肽（neoantigen）被切成大量「子肽 × HLA 等位」组合（DS2 每肽 **105–630** 个，中位 315），每个组合得一个工具分数。要与实验真值 ELISpot（肽级单值）相关，必须先把这一大堆子肽分数**聚合（pooling）成肽级单分**。

```
子肽×HLA 分数 (105–630 个/肽)  --[pooling]-->  肽级单分  --[Spearman]-->  vs ELISpot
                                     ↑ 本研究的对象
```

朱同学发现：**pooling 方式对最终 Spearman 影响巨大**（同一 feature netAffneg_9：max=0.196 vs topk_w=0.395，翻倍）。本研究把朱的 5 种 pooling 扩到 8 种，在我们 9 工具 × DS2（101 肽 / 9 患者）全集上系统扫描。

> 注意区分两级聚合：本研究的 **pooling = 子肽→肽级**（level-1）；另有 **跨患者聚合 = per-patient ρ→头条**（level-2，A 窗 `AGGREGATION_METHODS.md` 的 Fisher-z/median）。二维扫描（§5）把两级一起扫。

---

## 2. 8 种 pooling 算子（定义 + 来源）

降序排列子肽分数 s₁≥s₂≥…≥sₙ：

| 算子 | 公式 | 生物学含义 | 来源 |
|---|---|---|---|
| `max` | s₁ | **单显性表位**（best-binder）：最强子肽决定免疫原性 | netMHCpan/pVACseq/NeoFox 业界默认 [1][2][3] |
| `mean` | (1/n)Σsᵢ | 全表位平均提呈水平 | 标准 MIL [4] |
| `top3mean` | mean(s₁,s₂,s₃) | **表位库（窄）**：前 3 强表位均值 | top-k pooling [5] |
| `sum` | Σsᵢ | 总信号量（⚠️ 混入子肽数，见 §3） | 标准 MIL [4] |
| `geomean` | (∏sᵢ′)^(1/n)，sᵢ′=sᵢ−min+ε | 几何均值（木桶效应；负值经平移处理⚠️） | — |
| `softmax` | Σwᵢsᵢ，wᵢ=exp(sᵢ/T)/Σexp，T=1 | 软注意力加权（T→0 趋 max，T→∞ 趋 mean） | softmax 温度 [6] |
| `topk_w` | Σ_{i≤k} wᵢsᵢ/Σw，k=5，wᵢ∝1/rank | **表位库（加权）**：top-k 按秩递减加权 | top-k weighted [5] |
| `rankdecay` | Σdⁱ⁻¹sᵢ/Σdⁱ⁻¹，d=0.5 | 秩几何衰减（GWRP，max↔mean 平滑插值） | ordinal/GWRP pooling [7][8] |

**生物学映射核心**：`max` 编码「**单显性表位假设**」——一条长肽的免疫原性由其单个最强 MHC 结合子代表（业界主流，netMHCpan 取 best-rank、pVACseq `lowest`、NeoFox max）。`top-k / mean` 编码「**表位库（repertoire）假设**」——多个表位共同刺激 T 细胞库。**两个假设孰优是经验问题，pooling 的选择即在押这个生物学先验。** 朱同学 topk_w 翻倍提升、本研究 max 普遍非最优，都是 repertoire 假设的实证支持。

> **参数 TODO（朱实现未公开，待对账）**：朱 `topk_w` 的 k 与权重方案、`softmax` 温度 T、`rankdecay` 衰减率 d 均未公开。本研究取标准默认（k=5/inv_rank、T=1、d=0.5），并提供敏感性扫描（`--sensitivity`：softmax T∈{0.1,1,10}、topk k∈{3,5,10}、rankdecay d∈{0.3,0.5,0.8}）。

---

## 3. ⚠️ 关键修正：`sum` pooling 是肽长度混杂假象（必须排除）

朴素地看「哪个 pooling 全局 Spearman 最高」，`sum` 对 5/9 工具最优、甚至让 DeepImmuno 从 **−0.117 翻成 +0.113**（符号翻转）。**这是陷阱，不是发现。**

**铁证（Bash 核 csv）**：

| 量 | Spearman ρ |
|---|---|
| sum-pooled 分数 ↔ 子肽数（DeepImmuno） | **0.96** |
| 各 pooling 对子肽数的平均依赖（4 工具）| sum=**+0.75** / topk_w=+0.34 / top3mean=+0.33 / rankdecay=+0.33 / max=+0.24 / geomean=+0.08 / mean=+0.04 / softmax=+0.03 |
| 子肽数 ↔ ELISpot | 0.16 |
| 肽长度（Peptide_Length）↔ ELISpot | **0.31** |
| 子肽数 ↔ 肽长度 | 0.79 |

**机制**：`sum` 的肽级分数 96% 由「子肽数」决定，而子肽数 ≈ 肽长度（ρ=0.79），肽长度本身弱相关 ELISpot（ρ=0.31）。于是 `sum` 几乎纯粹在测「这条肽有多长」，把长度信号当成了免疫原性信号。DeepImmuno 自身分数与 ELISpot 弱负相关，被 sum 追长度（+0.31）的力量淹没、翻成正——**纯假象**。

**per-patient 也不消混杂**：二维扫描（§5.3）里 sum 在患者内仍最优，因患者内不同肽长度仍变。

### 混杂是「工具 × pooling」逐格的，不止 sum

逐格诊断（`pooling_count_confound.csv`，`|ρ(pooled, n_subpep)| > 0.5` 标 `count_confounded=True`，scipy 独立复核）揭示更细的图景：

| 现象 | 实测 |
|---|---|
| `sum` 普遍重混杂 | 0.23–0.98；**例外 pTuneos sum=0.23**（子肽数少 → 即便 sum 也未越阈） |
| **deepHLApan 的 max/top3mean/topk_w/rankdecay 全 ~0.57 混杂** | 长肽多窗口 → 连 `max`（best-binder）都因「抽更多次」而虚高 |
| HLAthena top3mean/topk_w = 0.55 混杂 | 同上 |
| `mean / softmax / geomean` 几乎全工具 count 不变 | <0.5（NeoTImmuML geomean=0.46 边际） |

即：**top-k 家族（含 max）对「窗口多的长肽」天然偏高**，对 deepHLApan/HLAthena 这种长肽富集的工具，连 best-binder 都漏了长度。被标 `count_confounded=True` 的格子出现在 `sum / max / top3mean / topk_w / rankdecay` 中（逐工具不同）。

**结论**：以 `count_confounded` 逐格剔除后再选「count-safe 最优」。这是**整个 benchmark 的通用警告**：聚合子肽时绝不用 sum；对长肽富集工具，连 max/top-k 都要查 count 混杂，否则把 HLA 分型数 / 肽长度泄漏进分数（red line ⑤ 评估别泄漏）。

> geomean 虽 count 不变（多数工具 ρ<0.1），但实现含 per-peptide min 平移处理负分，跨肽尺度被扭曲 → 解释脆弱，仅作探索；稳健推荐用 `mean / top3mean`。

---

## 4. 数字稳定性修正（顺手抓的 bug）

pTuneos 等多 tie 工具（101 肽仅 16–19 个唯一 pooled 值，83 ties）下，pooling 内部不同求和顺序产生 ~1e-16 浮点噪声，经 Spearman 秩相关的 tie-break 被放大成 **0.005 级 rho 漂移**（pTuneos top3mean：升序 0.0970 vs 降序 0.0905，**均为浮点假象**）。

**修法**：pooled 分数 `round(8)` 后再算 Spearman，真 tie 保持 tie、消除求和顺序依赖 → 确定性结果（pTuneos top3mean 稳定 **0.0945**）。真实分数差 ≫1e-8 不受影响。

**反哺建议（报 A 窗，不改其文件）**：A 窗 `merge_metrics_9tools.py` / `per_patient_spearman_multimethod.py` 的 `spearman_np` 同样无 round，`metrics_ds2_9tools.csv` 现有 pTuneos top3mean=0.0970 / mean=0.0297、deepHLApan top3mean=0.0475 都是浮点幸运值，与确定性真值差 ≤0.0025。建议 A 窗在 pooling 后 round(8)，保证全表确定性。

---

## 5. 结果

### 5.1 pooling matters（确认朱同学）

排除混杂的 sum 后，每工具「换 pooling」带来的 Spearman 跨度（spread）：

| 工具 | max | 安全 pooling 跨度 | spread |
|---|---|---|---|
| pTuneos | +0.136 | [−0.088, +0.136] | **0.225** |
| HLAthena (proxy) | +0.084 | [+0.084, +0.308] | **0.224** |
| PredIG | +0.198 | [+0.198, +0.364] | 0.166 |
| deepHLApan | +0.042 | [−0.100, +0.047] | 0.147 |
| NeoTImmuML | +0.022 | [+0.022, +0.159] | 0.137 |
| IMPROVE | +0.243 | [+0.201, +0.320] | 0.119 |
| ImmuneApp | +0.088 | [+0.042, +0.102] | 0.060 |
| PRIME | +0.116 | [+0.116, +0.168] | 0.052 |
| DeepImmuno | −0.117 | [−0.158, −0.117] | 0.041 |

**结论**：pooling 对多数工具影响显著（spread 0.05–0.22），确认朱「ranking 对 aggregation 高度敏感」。**例外 DeepImmuno**：spread 仅 0.041 且全为负——**pooling 救不了本质上与 ELISpot 不相关的工具**（诚实负发现）。

### 5.2 max 几乎从不最优 → repertoire 假设占优（H4 核心修正）

count-safe 最优 pooling（逐格剔混杂后选最高）vs max（全局 Spearman，`pooling_best_per_tool.csv`）：

| 工具 | count-safe 最优 | best ρ | max ρ | Δ(safe−max) | max 低估？ |
|---|---|---|---|---|---|
| PredIG | geomean* | 0.364 | 0.198 | +0.166 | ~~**是**~~ ⚠️修复前；max ρ 修正为 0.104（p=0.343 不显著），geomean/best ρ 含 P101/P102 污染待 Phase B 重算，见 HLA-FIX |
| HLAthena (proxy) | geomean* | 0.308 | 0.084 | +0.224 | （proxy 不计） |
| IMPROVE | top3mean | 0.320 | 0.243 | +0.077 | **是** |
| NeoTImmuML | geomean* | 0.159 | 0.022 | +0.137 | **是** |
| PRIME | top3mean | 0.168 | 0.116 | +0.052 | **是** |
| ImmuneApp | geomean* | 0.102 | 0.088 | +0.014 | 边际 |
| pTuneos | max | 0.136 | 0.136 | 0.000 | 否 |
| DeepImmuno | max（全负，最不负）| −0.117 | −0.117 | 0.000 | 否（无信号）|
| deepHLApan | softmax | −0.008 | 0.042 | −0.049 | **否**（见下）|

\* geomean 标星=有 per-peptide min-shift 实现注意，仅探索；稳健替代为 mean/top3mean（PredIG mean=0.280、NeoTImmuML mean=0.097 仍均超 max）。

**头条**：对有真实信号的工具（PredIG / NeoTImmuML / IMPROVE / PRIME），`max` 系统性低估其与免疫原性的相关 0.05–0.17——**用 best-binder（单显性表位）漏掉了表位库信息**。用 count-safe 最优重排，这些工具表现普遍优于「max 口径」此前报告。

**两个诚实负例**：
- **DeepImmuno**：全 pooling 皆负（−0.12 ~ −0.16），count-safe 最优只是「最不负的 max」——**pooling 救不了本质不相关的工具**。
- **deepHLApan**：naive 看似 top3mean/sum 有 +0.04~0.14，但其 max/top3mean/topk_w/rankdecay 全被 count 混杂（ρ≈0.57）；剔除后唯一 count-safe 算子（softmax/mean）反而 ≈0 或负——**deepHLApan 的「正相关」基本是肽长度假象，去混杂后无真信号**（此前 max=0.042 也属长度虚高）。

### 5.3 二维扫描（pooling × 跨患者聚合）

`pooling_2d_scan.csv` 给出 9 工具 × 8 pooling × 3 跨患者法（Fisher-z 加权 / median / simple mean）矩阵。Fisher-z 头条下 pooling 排序与全局一致（max 普遍偏低、top-k/mean 类回升），sum 仍最高但同样为混杂——**两级聚合各自独立影响，但 sum 的长度混杂在 level-2 也不消**。详见 csv。

### 5.4 与朱同学对账（H1）

| 项 | 朱（QuantImmu/02） | 我们（DS2 全集 101 肽） |
|---|---|---|
| 数据 | ds2 subset | DS2 全集（口径不同，数值不可直接比） |
| 核心 feature | netAffneg_9（netMHCpan 亲和，**DTU pending + 未进我们 9 工具表**）| 无对应列 → **不可复现其 max→topk_w 翻倍** |
| 共有工具 | PRIME / DeepHLApan | PRIME / deepHLApan ✅ |
| PRIME 方向 | （未给逐法数）| max=0.116 **最低**，mean/top3mean/topk_w/softmax(0.16–0.168)全高于 max → **方向吻合朱**（max 非最优）|
| deepHLApan 方向 | （未给逐法数）| max=0.042，top3mean 微高(0.047)、mean/softmax 转负 → **弱且噪声，朱的强效应在 deepHLApan 上不稳健**（诚实分歧）|

**对账结论**：朱「pooling 翻倍」的**定性方向**（max 非最优、聚合更优）在 PRIME 上复现；但**翻倍量级是 netAffneg（netMHCpan 亲和）特有**，无法在我们全集证实（该 feature 未部署 + DTU pending）。deepHLApan 上效应弱化——朱的极端提升不普适于所有工具。

> H1 TODO：朱 topk_w 的 k/权重、softmax T、rankdecay d 待朱本人对账；netAffneg_9 需 netMHCpan-BA 波次（C 窗）+ DTU 同意后才能在全集直接复现朱的数。

---

## 6. 图（figures/pooling_*）

见 `analysis/figures/`：
- `pooling_heatmap_global.*`：9 工具 × 8 pooling 全局 Spearman 热图（sum 列标混杂）。
- `pooling_count_confound.*`：各 pooling 对子肽数依赖度条形（sum 突出）。
- `pooling_max_vs_best.*`：max vs count-safe 最优，每工具回升量。
- （analyst 出，主线核 ≥2 关键值与 csv 一致后入档）

---

## 7. 给 benchmark 的可执行建议

1. **永不用 `sum`**；且**逐工具查 count 混杂**（`pooling_count_confound.csv`，>0.5 剔除）——长肽富集工具连 max/top-k 都可能泄漏长度（§3，deepHLApan max ρ=0.57）。
2. **默认 pooling 从 `max` 改为 `top3mean` 或 `mean`**——max 系统性低估有信号的工具（§5.2）；部署务实默认仍可保留 max 作「单 best-binder」对照，但**主排行榜用 count-safe 最优**。报数前先看该工具该 pooling 的 `count_confounded`，True 一律不入主报。
3. **pooled 分数 round(8)** 后算 Spearman——消除多 tie 工具浮点不稳定（§4）。
4. **报每工具的 pooling spread**——pooling 敏感度本身是工具特性（信号弱的工具 pooling 救不了，如 DeepImmuno）。
5. 报告须并列「max（生物先验=单显性表位）」与「最优安全 pooling（=表位库）」两套数，并说明 pooling 即在押生物学假设。

---

## 引用

[1] netMHCpan-4.1 best-rank 惯例, PMC5679736
[2] pVACtools `top_score_metric=lowest`(best-binder), pvactools.readthedocs.io
[3] NeoFox max 聚合, Bioinformatics 2021, 37(22):4246
[4] MIL pooling 综述, arXiv:1810.09050
[5] Top-k weighted pooling, arXiv:1810.09050 / emergentmind top-k
[6] Softmax temperature, jdhao 2022
[7] Ordinal pooling, arXiv:2109.01561
[8] GWRP/GWAP, arXiv:1809.08264
[9] 免疫原性预测综述（best-binder 局限，~6% top-pred 经 ELISpot 证实）, Front Immunol 2023;14:1094236
