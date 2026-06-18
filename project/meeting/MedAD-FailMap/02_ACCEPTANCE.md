# MedAD-FailMap — ACCEPTANCE CRITERIA

> Capability / analysis paper 判据：验「失败何时可预测 / 何时可迁移」，**不验「AUROC 更高」**。Gate 不达标按预案走，不临时找理由续命、不调松门槛回填。

> **⚠️ 重铸说明（2026-06-18 venue 退守 MICCAI/MedIA，draft，阈值待主线复核冻结）**
>
> 本文档随 `04_LOG.md` 2026-06-17「终局决断」拍板（ICLR「失败可外推」命门正臂三条全堵——METS 拿不到 / LGG iso=False / BraTS 跨中心 split trivial）整体重铸：**删去原「② 正臂跨模态外推 PASS」当硬验收条件**（开放数据几何分布天然覆盖不到 BraTS 稀释 niche，正臂在开放数据下永远 FAIL，留作硬条件等于自锁死局）。
>
> 重铸后围绕**双柱**组织验收，不再以「正向外推 PASS」为生死线：
> - **柱 1（承重）= per-image 可靠性判据**：以 C4 risk-coverage 在 held-out split 上的单调性当 actionable rule 验收，**不以小 partial_r 当验收阈**。
> - **柱 2 = 几何 niche 诊断框架**：以 A' 三模态负发现 + iso 诊断框架的**负向预言力**验收，**不写「正向 PASS」**。
>
> 正臂落空 = 诚实边界，写进验收说明（开放数据覆盖不到该 regime），**非 FAIL 条件**。
>
> 判据按 **MICCAI 档（必达硬条件）/ MedIA 升级档（选达加分项）** 两档列。**MICCAI 起步、达升级档可向 MedIA 升级**。
>
> 新 Gate 阈值数值由主线复核后定稿冻结（改 ACCEPTANCE 阈值 = 拍板点）；本稿为草案。

---

## 一、双柱验收（论文成立的硬条件）

> 旧表四 Pillar（①边界存在 ②外推有效性 ③per-image ④多方法）保留为**支撑维度的内部编号**，但论文成立的承重结构重组为下述**双柱**。原 ② 的「正臂跨模态外推 PASS」**不再是验收硬条件**（降为 MedIA 升级档的 weak positive control，见 §三）。

### 柱 1（承重）— per-image 可靠性判据可操作

> 对应旧 Pillar ③。STORY §三承重排序的第一柱（conspicuity 桥派生 per-image score）。**这是双柱里真正承重的一柱**——给一张图能在跑前判「这张图上重建式 AD 靠不靠谱」。

| 项 | 验收判据（草案，阈值待冻） |
|---|---|
| **C1-1 防循环论证（继承，不松）** | conspicuity 桥的预测力须过「防循环论证三件套」：① 增量信息检验（given 模型 anomaly score 后，conspicuity 经嵌套逻辑回归似然比 / 偏相关仍显著额外预测成败）② 控制显然变量残差（回归掉 size + raw contrast 后 conspicuity 在残差上仍有预测力）③ 三档敏感性 {top-5%/10%/15%} 方向一致。**仅 ≥1 特征在 C2 或 C3 过 family Holm + 三档一致 = 增量信息成立**（已在 Phase 0 三档敏感性坐实，见 §五 Gate 0 状态）。 |
| **C1-2 actionable 校准（柱 1 头条验收）** | **报 risk-coverage / selective AUROC**：按 per-image reliability（conspicuity 桥）排序，**丢 bottom-k% 低可靠图后，剩余图上的 AD AUROC 单调升**。验收形态 = `results/incremental_C4_risk_coverage_*.csv`（列：`conspicuity_col, coverage, retained_n, ad_auroc`），低 coverage 端 AUROC 显著高于全集（coverage=1.0）端。**不以小 partial_r 当验收阈**（partial_r 只支撑 C1-1 增量信息检验，不当 actionable claim 的强度门）。 |
| **C1-3 held-out 独立检验（MICCAI 硬条件，防「判据被图示非被验证」）** | C4 risk-coverage 的单调性须在**一个独立 held-out split 上仍成立**——验收床 = **LGG 独立例（15 例，BraTS2021_MappingToTCIA 去重坐实 95 重叠 / 15 独立，`results/phase1/lgg_dedup.csv`）**，AD 全集 AUROC → top-k coverage 单调升的 actionable rule 在该 held-out 上重现（方向一致）。**LGG 在柱 2 是 iso=False 的负臂边界例，但其作为 per-image 判据的独立测试床与 iso 标签正交**——此处只问「丢低可靠图后 AUROC 是否仍单调升」，不问「能否外推」。 |

> **柱 1 红线（继承）**：C1-1 防循环论证未过关前，**不得落「conspicuity 桥成立」**——否则 = 把已知「大病灶好检」重命名，踩 STORY 红线「别把弱结果当强卖」。
>
> **conspicuity 可计算性（核实）**：gCNR/CNR/Weber 需 GT mask、不可用于无标注新图；per-image 判据用无 mask 代理（全图 σ / GLCM Cluster-Prominence,Contrast / FFT 频谱熵 / Otsu 伪前景 CNR_proxy，scikit-image 可算）。先例 = Mammogram-difficulty GLCM 无 mask AUC=0.71（Siviengphanom 2023，CC+MLO，95% CI 0.64–0.78）。

### 柱 2 — 几何 niche 诊断框架（病灶几何决定失败可迁移性）

> 对应旧 Pillar ① + 原 ② 的诊断框架部分（iso 几何同构前验门）。**柱 2 的验收写成「诊断框架的负向预言力」，不写「正向 PASS」**——手上零跨模态 iso=True 正例锚。

| 项 | 验收判据（草案，阈值待冻） |
|---|---|
| **C2-1 失败边界存在且系统（继承 ①，不松）** | 受控操纵协变量（size / contrast），重建式 AD 性能随之系统变化：≥2 协变量轴失败呈系统规律（非噪声），**且至少一个轴上是非单调 / 交互效应（size×contrast 交互）**。Phase 0 已坐实（T1/T2/T3 三档 Holm 全显著，见 §五）。 |
| **C2-2 A' 三模态几何负发现（柱 2 头条验收）** | 病灶几何天然多峰、稀释失败 regime 是**窄 niche**：HAM（病灶相对太大）/ CBIS（太小）/ IDRiD（太碎、多微灶）三模态从三向 **disjoint** 于 BraTS 稀释 regime。验收 = 三模态 area-ratio + n_components 分布与 BraTS 实质不重叠（固化值 `results/distribution_overlap_*.csv`，n_components / OVL 已固化，verifier 0 drift）。**这是负发现，是论文核心 capability 贡献之一，不是 FAIL。** |
| **C2-3 iso 诊断框架的负向预言力（柱 2 验收，写负向不写正向）** | 几何同构前验门（area 双侧守门 + n_components 单侧上界，skeptic + reviewer 双闸 vetted）的验收 = **「预言不可搬的对，实测确实塌 / iso=False」方向一致**：前验门对几何不同构的跨模态对（HAM / CBIS / IDRiD）预言「不可外推」→ 实测 disjoint / 外推塌，**前验门预言与实测方向一致 = 判据有判别力的证据**。LGG 独立例（精确 skull-strip 后 iso=False，落 band 下方 44.7% > inband 39.9%）= 判据在开放同模态数据上的**边界例**，连续趋势（重叠率↑→外推保留率↑）作连续支撑证据。**iso 门的设计结构（PR-7b/PR-7c 及其 area 双侧守门重设计）见 `05_preregistration.md §F`，此处只引用、不改。** |

> **柱 2 红线（防 HARKing，继承 iso 门留痕纪律）**：iso 门的 band 后设留痕须齐全——重设计产生于 HAM/IDRiD 实测之后，清白靠**结构**（无参守门是主判据 + band 不承重 + 零候选依赖）**而非时序**，诚实写「重设计产生于实测之后」、禁写「冻在实测之前」。反事实自缚已兑现并入文：LGG 落 band 下方判 iso=False，**未为 4.8 点差放松守门救 LGG**（教科书级不续命，见 §四）。

### 支撑维度（非头条承重，进补充章 / 不进 headline）

| 维度 | 状态 | 去向 |
|---|---|---|
| **多方法对比（旧 Pillar ④）** | Phase 2 F1 三方法（AE/VAE/MemAE）已复现：稀释→漏检跨三方法一致 = 重建 AD 范式共性、非 AE 特例（MemAE 官方移植零偏离） | MICCAI 档可入正文当「范式共性」证据；**不进 headline 当独立贡献柱** |

---

## 二、必纠口径（verifier 坐实，全文统一）

> 写作 / 验收引用以下数字时一律用统一口径，旧文档残留旧口径须改齐。

1. **「1.3% 重叠」→ 写全**：HAM 落 BraTS 稀释 regime（P25）占比 = **1.3%（43/3310）**。这与 **OVL = 0.469**（连续分布重叠系数，趋势描述用、**非二分门**）是两个不同口径的量，引用时须区分，**不得混为一谈**。
2. **Holm 校正写 α = 0.05/3**（family 内三检 Bonferroni 分母 = 3），**非 /4**。旧文档凡写 /4 的须改。
3. **C3 主目录 partial_r bug 已修**：旧值 **0.5044 是 bug（无条件相关，controlled_for 空）已重跑**——corrected 进 `results/c3_corrected/`（glcm_cluster_prom=**0.3054** 控 size+contrast，verifier 核；sigma 0.1395 / glcm_contrast 0.1702 / fft −0.1411 / cnr −0.0489 五特征 Holm 后全显著），主目录 frozen 保留供审计；引用一律用 corrected 值，不照写旧值。三档敏感性目录（`sens_p*/`）的 C3 方向一致结论可用。

---

## 三、MICCAI 硬条件 vs MedIA 升级项（分两档）

### MICCAI 档（必达，论文成立的硬条件）

| # | 硬条件 | 状态 |
|---|---|---|
| **M-1** | **口径纠错全文统一**（§二 三项）：1.3% 写全、Holm α=0.05/3、C3 主目录 partial_r 标 pending | 待写作落实 |
| **M-2** | **Phase 2 ≥3 seed**：协变量失败边界 + per-image 判据在 ≥3 seed 上方差带稳定、结论方向不翻（现有 s42 单 seed，seed-fill 待补） | `[pending seed-fill]` |
| **M-3** | **柱 1 per-image held-out（LGG）**：C4 risk-coverage actionable rule 在 LGG 独立 15 例 held-out 上单调性重现（C1-3） | `[pending LGG C4 held-out 重跑]` |
| **M-4** | **MedIAnomaly differentiation 表**：明确本文与 incumbent（MedIAnomaly benchmark 聚合无协变量 / AE4AD mismatch 存在性定理无协变量参数）的判别表——本文贡献正交于二者（协变量失败相图 + per-image 前验判据 + 几何同构诊断框架），不与之竞争 AUROC（见 §四 differentiation 表） | 待写作落实 |
| **M-5** | **柱 1 防循环论证三件套过关**（C1-1）+ **柱 2 失败边界系统 + 交互**（C2-1）+ **A' 三模态负发现**（C2-2） | Phase 0 三档已坐实（§五） |

### MedIA 升级档（选达，加分项，不达不影响 MICCAI 成立）

| # | 升级项 | 状态 |
|---|---|---|
| **U-1** | **iso 正向锚（weak positive control）**：BraTS 跨中心 split 当 weak positive control——明确标注为 weak positive control（同病种同集、不算真跨模态外推），仅作 iso 门「同构对能外推」方向的弱正向佐证，**绝不当 headline「可外推 PASS」卖** | `[pending，可选]` |
| **U-2** | **PC-A 相图跨 ≥3 数据集**：协变量失败相图在 ≥3 数据集上复现（现 BraTS 主集 + 三模态几何分布） | `[pending，可选]` |

> **升级档纪律**：U-1 即便做出，只能写「weak positive control，同病种跨中心、非真跨模态外推」，**禁止用它复活 ICLR「失败可外推」headline**（守 STORY headline 铁律：手上零跨模态 iso=True 正例，暗示跨模态 work = 移动球门 / HARKing）。

---

## 四、Gate 重定（capability / analysis 判据，非刷分）

> Gate 改判「capability 资产是否扎实 + 诚实边界是否守住」，**不判「分数是否更高」**。阈值数值待主线复核冻结。

- **Gate 0（可行性预检，Phase 0 末）**：最小 pipeline 搭通 + 协变量分层 sanity 能跑出非平凡失败变化 → 进 Phase 1。**已 PASS**（A/C 双绿三档坐实，见 §五）。
- **Gate 1（双柱地基存在，Phase 1 末）**：柱 2 的 C2-1（失败边界系统 + 交互）+ C2-2（A' 三模态负发现）成立 → 进 Phase 2。**已实质达成**（A' 三模态 disjoint + iso 框架双闸 vetted）。
- **Gate 2（MICCAI 投稿就绪，capability 收口）**：
  - **PASS（MICCAI 就绪）** = M-1..M-5 全达：口径纠齐 + ≥3 seed + 柱 1 LGG held-out 单调重现 + differentiation 表 + 防循环论证/边界/负发现三件全过。**正臂落空诚实入文、非 FAIL 条件。**
  - **MedIA 升级** = 在 PASS 基础上 U-1 / U-2 达成（weak positive control + 相图跨 ≥3 集）。
  - **FAIL（不投）** = 柱 1 防循环论证翻车（C1-1 不过 / held-out 单调不重现）**或** A' 三模态负发现被证伪（实测重叠、niche 不窄）**或** 口径纠错没做（数字不可信）。
- **正臂落空 ≠ FAIL**：开放数据几何分布天然覆盖不到 BraTS 稀释 niche → 跨模态正向外推在开放数据下无正例锚，**这本身是负发现的一部分、是诚实边界，写进 limitations，不进 Gate FAIL 条件。**

### MedIAnomaly differentiation 表（M-4 验收骨架，写作已填充）

> M-4 验收核心钉死（一句话）：**incumbent 与近邻 failure-mode 线全部停在 dataset-level 聚合或存在性定理粒度；本文落在 instance 级 per-image actionable rule + 病灶几何前验诊断粒度——结构上是不同的分析层级，因此与之正交、不竞争 AUROC 排行。** 下表按「对照对象」逐行展开此判别。

| 对照对象 | 他们做什么（粒度） | 他们给不出什么 | 本文正交贡献 | 竞争 AUROC？ |
|---|---|---|---|---|
| **MedIAnomaly**（Cai et al., HKUST, MedIA 2025; arXiv 2404.04518；**incumbent**） | 30 方法 × 7 数据集 × 5 模态 comparative study；**dataset-level 聚合 percentile-AUROC**；描述性指出重建误差假设「does not always hold」（关键 finding：local vs global anomaly 二分） | 无受控协变量分层；无 per-image actionable rule；无几何迁移诊断（其聚合粒度结构上给不出「这一张图上靠不靠谱」） | per-image 可靠性判据兑现为 risk-coverage selective-prediction rule（instance 粒度）+ 协变量失败相图（带交互/非单调）+ 几何同构前验诊断框架 | **否**——不同粒度，本文不进 dataset-level AUROC 排行 |
| **AE4AD / Rethinking AEs for Medical AD**（Cai/HKUST 同族，MICCAI 2024; arXiv 2403.09303；理论侧 incumbent） | 理论证 identical-shortcut + latent over-generalization 两 failure 机制（**存在性定理** + constructive 构造） | 定理不带协变量参数；无 per-image score；无跨集迁移诊断（证「会失败」，不刻画「何种几何下失败、能否前判」） | 把「会失败」精确化到协变量几何 regime（size×contrast 交互、非单调），并落地为单图前验判据 | **否**——理论存在性 vs 经验可操作判据，无 AUROC 比对维度 |
| **What Do AEs Learn About Anomalies?**（MICCAI 2023） | 实验分析：正常/异常分布重叠时 AE 全失败（近邻 failure-mode observation，引作 motivation） | 无协变量参数化的失败相图；无 per-image actionable rule；无几何迁移前验 | 把「分布重叠 → 失败」这一定性观察参数化为协变量相图，并派生单图可操作判据 | **否**——定性 motivation vs 定量可操作判据 |
| **Comparative Benchmarking of Failure Detection**（MedIA 2024; arXiv 2406.03323） | per-image failure detection benchmark，**用模型自身 ensemble 一致性 / Dice 当 failure predictor**；针对 segmentation，非 recon-AD | predictor 依赖模型软输出（ensemble/Dice），非图像本征属性；不给跨集迁移的前验诊断；任务为 segmentation 非重建式 AD | per-image predictor 用**图像本征 conspicuity 几何属性**（无 mask 代理），且额外给几何前验迁移诊断；引作 per-image failure benchmark 的方法论参照 + baseline 对照 | **否**——同为 per-image failure detection 但 predictor 与任务不同；作 baseline 对照而非 AUROC 竞争 |

> **判别结论**：四行对照对象覆盖 incumbent（聚合 benchmark）、理论侧 incumbent（存在性定理）、近邻 motivation（定性失败观察）、近邻方法论参照（per-image FD benchmark）。本文三条正交轴——① 协变量失败相图（带交互/非单调，非聚合 AUROC）② per-image actionable selective-prediction rule（risk-coverage，instance 粒度）③ 病灶几何 a priori transferability 诊断框架——均落在他们结构上达不到的粒度，因此**不与任一对照对象竞争 dataset-level AUROC 排行**（守 STORY §四「capability/analysis paper、不刷 AUROC」红线）。
>
> differentiation 表的数字若引入（AD-AUROC 对比、OVL 等）一律入表前过 verifier；旧 C3 主目录 partial_r 绝对值标 `[pending verifier rerun]`，不照写。本表当前不含任何未核 AUROC 值——MedIAnomaly 的 local vs global finding 为其论文定性结论，本文仅作定位引用、不复算。

---

## 五、Gate 0 既有成果状态（坐实部分，可直接引用）

> 以下为 Phase 0 已坐实、三档敏感性 {P95/P90/P85} 复核过的确证结论，作为双柱的现有地基（来源已核，见 `04_LOG.md` 三档敏感性 entry）。

- **柱 2 / C2-1 失败边界系统 + 交互 = 坐实**：T1 size（chi2 P95/P90/P85 = 120.8 / 190.9 / 237.7）、T2 contrast（140.0 / 245.2 / 302.5）、T3 size×contrast 交互（8.77 / 16.1 / 28.6）三档 Holm 全显著、方向一致。
- **柱 1 / C1-1 增量信息 = 坐实**：C3（控制 size+contrast 后偏相关）4 特征三档方向一致显著（`sens_p*/incremental_FC_family_holm.csv`：sigma_global / glcm_cluster_prom / glcm_contrast / fft_spectral_entropy）。规则「C2 或 C3 ≥1 特征过 Holm + 三档一致」远超达成。**注意：C3 主目录单档 partial_r 旧值含 bug → 已重跑 corrected（`results/c3_corrected/`，glcm_cluster_prom=0.3054 控 size+contrast，verifier 核），引用用 corrected 值；三档敏感性目录的方向一致性结论可用。**
- **柱 2 / C2-2 A' 三模态负发现 = 坐实**：HAM / CBIS / IDRiD 三向 disjoint，n_components / OVL 固化（`results/distribution_overlap_*.csv`），verifier 0 drift。

> **待补（M-2/M-3）**：Phase 2 ≥3 seed 方差带；柱 1 C4 risk-coverage 在 LGG held-out 上的单调性重现。

---

## 六、反跑偏（验收侧）

- **滑回刷 AUROC = 跑偏**：本文不与 AD 方法竞争分数，只刻画其失败几何。T8 类 in-domain 绝对 AUROC（如 GBM 0.964）= 探索性，只引相对 Δ，不当 headline。
- **不顺手加新方法 / 新模态 / 堆指标**——只验双柱 + 支撑维度。
- **多重比较校正**：所有显著性检验预登记 + Holm/FDR（family 内 Holm α=0.05/family-size，**三检 family 用 /3**），防 p 值满天飞。
- **HARKing 防护（iso 门）**：iso 门 band 为后设设计须留痕齐全——清白靠结构（无参守门主判据 + band 不承重 + 零候选依赖），诚实写「产生于实测之后」，**禁写「冻在实测之前」**；反事实自缚已兑现（LGG iso=False 不改门救）。
- **口径统一防自欺**：1.3%(43/3310) vs OVL 0.469 区分、Holm α=0.05/3、C3 主目录 partial_r 标 pending（§二）。
- **Gate FAIL 按预案走**，不临时找理由续命、不调松门槛回填。门槛改动 = 改 ACCEPTANCE 方向 = 拍板点。
- **正臂落空诚实入文**：开放数据覆盖不到 BraTS 稀释 niche，写 limitations，**不假装 PASS、不糊成全绿**（守 LOG 收口诚实表述纪律）。
- 所有 run 记 seed + 协变量配置 + 数据集 + job ID，可追溯。

---

## 附：编号映射（旧四 Pillar → 新双柱，防引用混乱）

| 旧编号 | 旧内容 | 新归属 |
|---|---|---|
| Pillar ① | 失败边界存在且系统 | 柱 2 / C2-1 |
| Pillar ② | 外推有效性判据（正臂 PASS） | **删去正臂硬条件**；诊断框架部分 → 柱 2 / C2-3（负向预言力）；正向锚 → MedIA 升级档 U-1（weak positive control） |
| Pillar ③ | per-image 可靠性判据 | 柱 1（承重）/ C1-1..C1-3 |
| Pillar ④ | 多方法对比 | 支撑维度（补充章，不进 headline） |
