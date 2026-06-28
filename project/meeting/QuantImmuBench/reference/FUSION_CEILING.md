# 融合上限与天花板研究（QuantImmune 立项关键决策证据）

> 服务 quantimmu-bench，I-fusion 窗，2026-06-26。承接朱同学多工具融合实验，往下挖「融合到底能不能显著超最优单分，还是撞理论天花板」。
> 方法学产出，**不是余嘉的 HPC 部署任务**（部署交付已完成）。caveman OFF。
> 与 F 窗（quantimmune_pilot，建可部署原型）分工：**I 回答「融合能不能显著超单工具」（方法学 + 天花板），F 回答「原型怎么建」**。本档结论是 QuantImmune 是否值得立项的关键证据。
> 全部数字 Bash/Grep 核 csv/json，已过 verifier 三方对账。数据真源见各表脚注。

---

## 一句话结论

**在真实新抗原免疫原性数据（DS2，101 肽 / 9 患者）上，多工具融合相对最优单工具的增益落在噪声内（三种检验 p>0.8），且学权重融合（ridge/GBDT）因样本饥饿反伤；融合点估（ρ≈0.33）距理论天花板下沿（0.4）仅 0.07、CI 上界已触及天花板带 [0.4,0.6]——融合既未显著超单工具、也未触顶，方向不死但增益不可学出。复现并加固朱同学「融合提升不显著（p≈0.70）」的结论。**

→ **对 QuantImmune：融合现有工具分数不是杀手锏。** 要破天花板必须喂**新信号**（供体 TCR-seq / HLA 分型 / precursor 代理，THEORY C2）或扩**多中心连续 SFC 数据**做 powered study，而非堆更多现有工具或更复杂的融合架构。**这是高价值负结论，不是失败。**

---

## 一、复现朱同学的融合实验（I1）

朱同学的图（外部 QuantImmu/02）：
- 最优单一分数（netAffneg_9）≈ **0.3946**；6 维融合模型 ≈ **0.4328**；提升 **p≈0.70 不显著**。
- 部署建议：务实默认 = 单 affinity pooling；按需备选 = 7 维自由 pooling + geomean。

⚠️ **口径差异（透明声明）**：朱的 0.3946/0.4328 来自不同的打分方案（netAffneg_9、global pooling，非 per-patient），我们手里没有朱的原始输入/脚本，无法逐位复现其绝对值。但**结构性结论完全可复现**：在我们 9 工具 × 101 肽 的 LOPO + per-patient Fisher-z 口径下，**最优融合相对最优单工具的提升同样不显著**。下文用我们的口径独立验证朱的核心发现。

朱用「6 维融合」——我们的 surv6 特征集（6 存活工具：PredIG / IMPROVE / pTuneos / PRIME / ImmuneApp / deepHLApan）正好对应 6 维，是朱设定的自然类比。

---

## 二、融合 vs 最优单工具：地板线与方法对比（I2/I3）

**铁律 LOPO CV**：leave-one-patient-out 15 折（留 1 患者训其余），防泄漏（标准化/缺失填补全用训练折统计），评估 = per-patient Spearman ρ_i → Fisher-z 固定效应加权聚合（公式照抄 F 窗 `lopo_eval.py`，保证可比）。主分析仅 DS2 9 患者；DS1 6 患者仅敏感性。

### 2.1 单工具地板（无训练，工具分即预测）

| 工具 | DS2 Fisher-z ρ̄ | 95% CI |
|---|---|---|
| **deepHLApan（最强）** | **0.2519** | [0.019, 0.459] |
| PRIME | 0.2481 | [0.017, 0.454] |
| IMPROVE | 0.2499 | [0.021, 0.454] |
| PredIG | 0.2300 | [-0.002, 0.438] |
| ImmuneApp | 0.1732 | [-0.060, 0.389] |
| pTuneos | 0.1696 | [-0.063, 0.385] |
| NeoTImmuML / DeepImmuno / HLAthena | ≤0.03 | 含 0（死工具） |

> 源：`analysis/fusion_single_floor.csv`。`analysis/per_patient_spearman_9tools.csv`（独立脚本）给 deepHLApan=0.2605，两法均判 deepHLApan 为最强单工具（差异来自聚合细节，均≈0.25-0.26）。
> ⚠️ **关键校准（skeptic 红队修正）**：最优单工具 = **deepHLApan（0.25-0.26）**，**不是 IMPROVE**。前几列工具（deepHLApan/PRIME/IMPROVE）地板几乎并列，「融合 +0.08」若拿 IMPROVE 当 baseline 会高估优势——下文配对一律对**最强单工具 deepHLApan** 报。

### 2.2 融合方法（surv6 特征集，LOPO，target = raw SFC）

| 融合法 | DS2 Fisher-z ρ̄ | 95% CI | DS1 敏感性 |
|---|---|---|---|
| **rankmean_surv6**（rank 等权平均，尺度无关）| **0.3336** | [0.108, 0.527] | -0.157 |
| **fixavg_surv6**（z-score 等权平均，零参数）| **0.3281** | [0.101, 0.523] | -0.160 |
| ridge_surv6（学权重，eff_DOF≈2.5）| **-0.3008** | [-0.499, -0.072] | +0.107 |
| gbdt_surv6（GBDT，max_depth=2）| -0.0421 | [-0.268, 0.188] | -0.118 |
| **shuffle 对照**（打乱 SFC）| -0.0507 | [-0.275, 0.179] | — |

> 源：`analysis/fusion_methods.csv`。
> - **简单融合（rankmean/fixavg）赢学权重融合（ridge/GBDT）**：等权 ρ≈0.33，ridge raw_sfc 塌到 **负值**（-0.30），GBDT≈0。F 窗 ridge 用 patient_centered target 较温和（0.241，见 `quantimmune/results/lopo_ridge_surv6_patient_centered.summary.json`），但**仍 < fixavg**。两条独立证据都指向：**K=9 患者根本学不动权重，学权重 = 过拟合反伤**。
> - **shuffle 对照 ρ≈0 且 CI 含 0** → 管道干净无泄漏，0.33 的信号是真的（高于 null）。

---

## 三、★显著性：融合提升是否真显著（I5，headline）

朱 p=0.70 = 不显著。我们用**患者级配对检验**（K=9 极小，bootstrap 不可信，故同时报对 K=9 更可信的精确符号检验 + 全枚举置换检验，skeptic 红队要求）。配对量 Δz_i = Fisher-z(融合 ρ_i) − Fisher-z(deepHLApan ρ_i)。

| 融合法 vs deepHLApan | Δρ 点估 | bootstrap p | 符号检验 p | 置换检验 p | 患者方向 | 判决 |
|---|---|---|---|---|---|---|
| fixavg_surv6 | +0.033（Δz=0.004）| 0.974 | **1.000** | 0.984 | 5 正 / 4 负 | **不显著（抛硬币）** |
| rankmean_surv6 | ~+0.04（Δz=0.040）| 0.833 | **1.000** | 0.852 | 5 正 / 4 负 | **不显著** |
| ridge_surv6 | （Δz=-0.58）| 0.016 | 0.180 | 0.047 | 2 正 / 7 负 | **显著更差（过拟合）** |
| gbdt_surv6 | （Δz=-0.30）| 0.312 | 1.000 | 0.356 | 4 正 / 5 负 | 更差，不显著 |

> 源：`analysis/fusion_vs_single_paired.csv`（B=10000 bootstrap + 精确符号 + 全枚举 2⁹=512 置换）。
> **三种独立检验全部收敛**：简单融合 vs 最强单工具 = **不显著**（5 正 4 负，字面抛硬币）；学权重融合显著更差。

**独立交叉验证（F 窗）**：F 窗用不同脚本（`paired_bootstrap.py`）跑的 vs_floor 配对完全一致——
- fixavg vs deepHLApan：Δρ=0.033，P(Δ>0)=0.514，5 正 / 4 负（`quantimmune/results/bootstrap_fixavg_surv6_raw_sfc_vs_floor_deepHLApan.json`）。
- vs 较弱单工具：vs IMPROVE +0.046（P=0.864）、vs PRIME +0.099（P=0.874）、vs PredIG +0.054（P=0.714）——**点估正向但全部 CI 含 0**，与朱 p≈0.70 量级一致。

**判决**：「融合**显著超**最优单工具」当前证据下**不成立**。「融合方向死/无用」也**不成立**（shuffle 干净，信号真但小）。综合 = **当前数据不足以判定「显著超」，最佳证据指向「不显著超最强单工具」**。

---

## 四、对照理论天花板（I4）

理论天花板（`reference/THEORY_quant.md`，theorist 推导，**低置信**）：纯肽+HLA 的 magnitude 可解释方差上界被 naïve precursor frequency 的供体特异性结构锁住，ρ_max 量级估 **0.4–0.6**。

| 方法 | ρ̄ | CI 上界 | 距天花板下沿 0.4 | CI 触及 [0.4,0.6]? |
|---|---|---|---|---|
| 最强单工具 deepHLApan | 0.252 | 0.459 | 0.148 | **YES** |
| fixavg_surv6 | 0.328 | 0.523 | 0.072 | **YES** |
| rankmean_surv6 | 0.334 | 0.527 | 0.066 | **YES** |

> 源：`analysis/fusion_ceiling_distance.csv`。
> - 最优融合点估（0.33）距天花板下沿 0.4 仅 **0.07**，CI 上界（0.52-0.53）**已伸进天花板带 [0.4,0.6]**。
> - 但单工具地板（0.25）CI 上界（0.46）同样触及天花板带。**融合相对单工具没有把点估更靠近天花板（提升不显著），二者都在天花板下沿的噪声范围内。**

**⚠️ 双重不确定（skeptic 红队）**：拿 CI 很宽（±0.2）的 ρ̄=0.33 和「低置信」天花板 0.4-0.6 比，「撞顶 / 未撞顶」都说不死。诚实表述 = **「逼近天花板下沿但未确证触顶，且未显著超单工具」**，不能宣称「融合已撞天花板所以到头了」（那是拿两个噪声量比）。

---

## 五、对 QuantImmune 立项的建议（I6）

### 5.1 核心决策证据

1. **融合现有工具分数不是杀手锏**。简单融合（rankmean/fixavg）点估 0.33 略高于最强单工具 0.25，但三种检验一致判**不显著**（p>0.8，5 正 4 负）。学权重融合（ridge/GBDT）在 K=9 下过拟合反伤。这复现并加固朱的 p≈0.70。
2. **方向不死，是数据不够 + 信号本身被生物学封顶**。shuffle 对照干净（信号真）；fixavg 赢 ridge = 样本饥饿（THEORY §六 ②+③，非 ① 方向死）；点估逼近天花板下沿。
3. **天花板逼近但未确证触顶**。0.33 距 0.4 仅 0.07，但 CI 太宽，需 powered study 才能确权 ρ 与天花板的真实距离。

### 5.2 给 QuantImmune 的路线建议

- **不要**把「融合多工具」当 headline 杀手锏——证据不支持显著增益。
- **要破天花板，唯一理论路径 = 喂新信号**（THEORY C2）：供体 TCR-seq / HLA 分型（袁数据已有 HLA）/ precursor frequency 代理。这是结构性缺失的头号驱动，融合现有「肽+HLA」工具填不上。
- **或扩数据做 powered study**：当前 K=9 功效严重不足（单 ρ_i CI ±0.6-0.7）。多中心连续 SFC 配对（THEORY 估 O(10³-10⁴)）才能把 ρ=0.33 的 CI 收窄、确证是否真触顶。
- **headline 押 C3（连续模型 top-K 排序优于二分，临床价值）**，不押「融合破天花板」。C1（坐实天花板）当诚实刻画，C2（供体数据破顶）当探索性 stretch。

### 5.3 负结论的价值（明说）

用一套干净的 LOPO + 配对协议 + 三检验，**定量钉死了领域里大家含糊带过的点**：「在真实 neoantigen 免疫原性数据上，多工具融合相对最强单工具的增益落在噪声内，学权重因样本饥饿反伤」。这本身是可发表的方法学发现 + powered study 的功效估算依据，比硬塞一个站不住的杀手锏强。

---

## 六、残留 caveat / TODO

1. **多重比较未校正**（skeptic 🟡）：试了 4 融合法 × 多特征集 × 多 target，报最高那个有 cherry-picking 风险。投稿前需列全 grid + 标注「报告值为 max」或预登记单一配置。
2. **DS1 跨数据集符号翻负**（fixavg DS1=-0.16）：融合在第二数据集无正迁移，泛化未验，须标「未验泛化」不当支持证据。
3. **DTU 工具分数**（NetMHCpan-BA / NetTepi / ICERFIRE）若纳入融合输入，整列 `pending_DTU_consent`，未经 DTU 书面同意禁发（PROVENANCE 红线）。新工具落地后融合输入扩到 ~19 维，本结论需重跑确认。
4. **朱原始口径未逐位复现**：netAffneg_9 / global pooling 的绝对值（0.3946/0.4328）依赖朱的输入，本档只复现结构性结论。若需对齐绝对值，需朱提供原始打分表。
5. 天花板 0.4-0.6 = 低置信理论估计，需真实大样本 magnitude benchmark 校准（THEORY TODO-2/3）。

---

## 数据真源

- 单工具地板：`analysis/fusion_single_floor.csv` + `analysis/per_patient_spearman_9tools.csv`
- 融合方法：`analysis/fusion_methods.csv`
- 配对显著性：`analysis/fusion_vs_single_paired.csv`（本窗）+ `quantimmune/results/bootstrap_*_vs_floor_*.json`（F 窗交叉验证）
- 天花板距离：`analysis/fusion_ceiling_distance.csv`
- 脚本：`analysis/fusion_study.py`（本窗，复用 `quantimmune/lopo_eval.py` 口径）
- 理论：`reference/THEORY_quant.md`；聚合方法学：`reference/AGGREGATION_METHODS.md`；实验矩阵：`reference/EXPERIMENT_MATRIX_quantimmune.md`
