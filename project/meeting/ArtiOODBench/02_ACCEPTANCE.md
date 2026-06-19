# ArtiOODBench — ACCEPTANCE / 判据

> 立项时预登记，防 HARKing。**v2 已冻结（2026-06-19，用户拍板，Gate1 设计 + skeptic 4 修后）**。阈值 + PR-F1/F2/F3 预登记项 + L3 cross-source 设定均冻结，不再随结果改。
>
> **v3 澄清（2026-06-19，用户拍板 + skeptic 0 致命放行）**：仅澄清 **PR-匹配半径** 的维度歧义（初版实现误作 43 维欧氏球，维度灾难仅配 6 对无统计功效 → 按 Austin 2011 标准含义修正为 1 维 propensity caliper，定性=实现 bug 修正非协议变更）。**阈值、PR-F1/F2/F3、命门口径（方案 C 唯一裁决）一律不动**。v2 原文保留于下不覆盖，修正说明附 PR-匹配半径条。详 04_LOG Entry 6。
>
> **v4 reframe 修订记录（2026-06-19，用户拍板 option ① + skeptic 0 致命放行；详 04_LOG Entry 7）**：A-4 命门据实跑出 FAIL（3 可评估对无一达预登记阈值 + 7 法 Spearman 结构性低功效）。**承重重排，但所有预登记痕、v2/v3 块、A-1~A-4 判据原文、PR-F1/F2/F3、K1-K4 一律保留不删不改阈值**——本块为**追加修订记录**，记录承重转移，非抹除原命门。变更摘要：
> 1. **A-4（原命门）降级为 negative result / limitation**：判据原文 + 跑前预登记痕全部保留，**追加「L3 实跑 FAIL + 低功效剖析」修订记录**（见 A-4 下方）。所有已 PASS 数字不动。
> 2. **新增承重判据 A-5（source-leakage）+ A-6（评测协议处方 = L3' actionable so-what）**，承接 headline 重心（见承重判据表）。
> 3. **K2 处理**：K2 literal（Spearman>0.9）仅 1/3 对满足 → **非干净触发**；用户拍板 reframe 而非降 ICBINB，因 L1 + source-leakage 承重独立成立（见 Kill criteria K2 修订记录）。
> 4. **不改任何已 PASS 的数字**（A-1/A-2 维持）。reframe 是 headline 重心转移，不是改阈值凑结果。
>
> **v5 扩证据预登记冻结记录（2026-06-19，用户拍板 + skeptic 实算放行；详 04_LOG）**：NeurIPS D&B 主投，扩方法集（7→13）+ 扩对（4→6–7）+ 扩模态对，跑前冻结全部新自由度防 HARKing。**不删任何 v2/v3/v4 块、A-1~A-6 判据原文、PR-F1/F2/F3、PR-匹配半径、K1-K4**——本块为追加。两处实质变更：
> 1. **A-5 升级承重口径**（表内 A-5 行已改）：门从「≥3 对接近完美」收紧为 **ViM AUROC 在 ≥(N-1)/N 对上 >0.95**（贴合现 4/4=1.0 强度，FAIL 才有意义、非松到必过）。**承重只由 ViM 单法承载**。
> 2. **删去原拟的 A-5b 组级命门**（feature-vs-logit 组级显著差异）：**skeptic 2026-06-19 实算 leave-ViM-out 后 CXR 反号**，该组级 claim 几乎全靠 ViM 单骑，去 ViM 反向，会反噬 A-5a 铁证 → 不当命门。13 法 × 多对 AUROC 谱**仅作描述性证据呈现（工件完整度），不预登记任何组级显著命门**。
> 3. **新增预登记块 PR-G1~G4**（扩方法集 / multi-label 适配 / 扩对 / 去污染一致性）+ **FAIL 三档退路**，跑前冻结（见文末「v5 预登记块」）。
> 4. **不改任何已 PASS 数字 + 不动 A-1~A-4/A-6 阈值 + 不动 PR-F1/F2/F3/匹配半径 7 规格 + 不动 K1-K4**。

## 核心 RQ
医学影像 OOD detection benchmark 的方法排名在多大程度上被采集 artifact 混淆？去污染后排名是否实质改变？

## 承重判据（reframe 后，对齐 STORY lever）

> reframe 后承重 = **A-1 + A-2（L1，PASS 维持）+ A-5（source-leakage，新承重）+ A-6（评测协议处方 = L3'）**。A-4（原命门）降级 negative/limitation，判据原文保留、追加修订记录。表内 v2 阈值列一律不改。

| ID | 判据 | 阈值（v2 冻结，不改） | 对应 lever | reframe 后地位 |
|---|---|---|---|---|
| A-1 | artifact-only 特征在 ≥3 个医学 OOD benchmark 对上 AUROC | ≥3 对中 ≥2 对 all-43dim AUROC≥0.80，且 ≥1 对 >0.90 | L1 | **承重 · PASS（verifier 核：跨机构对 0.82–0.9997）** |
| A-2 | 现象普适性：≥3 模态（CXR / 脑 MRI / dermoscopy）均见污染 | 每模态 ≥1 对 all-43dim AUROC>0.75 | L1 | **承重 · PASS（不动数字）** |
| A-3 | 去污染协议有效性：去污染后 artifact-only AUROC 显著下降 | artifact-only 掉到 <0.65 **且** 降幅 Δ>0.15 | L2 | 支撑 · L2 有效性（手工 artifact 部分） |
| A-4（原命门 → **降级**） | 去污染后主流 OOD 方法排名改变 | **方案 C（artifact-matched 配对子集）为唯一裁决**：bootstrap Spearman(原,C) **CI 上界<0.7**（或 top1 掉出 top3）**AND** 口径2 翻转机制可解释（掉幅顺序符合 MDS>KNN/ViM>MSP 敏感度假设）。方案 A/B 仅附录 robustness | L3 | **negative result / limitation（实跑 FAIL，见下修订记录；连同低功效剖析当 contribution）** |
| **A-5（新承重 · v5 升级口径）** | source-leakage 承重：ViM AUROC 在 cross-source normal-vs-normal 对（纯 covariate、零 semantic）上接近完美分离 | **ViM AUROC 在 ≥(N-1)/N 个 cross-source normal-vs-normal 对上 >0.95**（N = 实际可评估对数；现 4/4=1.0；v5 扩到 6–7 对，容忍 ≤1 对退化，退化对须附 PR-F3 类退化机制理由）。**承重只由 ViM 单法承载（无 multi-label 适配歧义）** | source-leakage | **承重（v5 升级版判据；写法见 A-5 v5 修订记录）** |
| **A-6（新承重）** | 评测协议处方（L3' actionable so-what）：给出可操作评测规范 | ①cross-source normal-vs-normal 作 sanity baseline（方法在它上高 AUROC → benchmark 被源域污染、结果作废）②报 artifact-only AUROC 作污染上界 | L3'（补 L3 退场空缺） | **承重（不依赖低功效 7 点 Spearman）** |

**防 K3 硬约束**：去污染后 artifact-only<0.65，但 7 方法在方案 C 子集上平均 AUROC **不得同时 <0.55**（否则把 semantic 也删了 → 回设计）。

### A-4 修订记录（2026-06-19，v4 reframe；判据原文 + 跑前预登记痕保留于上表，本块为追加）

> **不删 A-4 判据、不改其阈值。** A-4 于 v2 跑前冻结为唯一承重命门（HARKing 防护），实跑后据实降级——以下为时间线留痕：

- **跑前预登记**：A-4「去污染后排名翻转」为唯一命门，方案 C 唯一裁决，bootstrap CI 上界<0.7 或 top1 掉出 top3（v2 冻结，详 04_LOG Entry 6）。
- **实跑结果（4 对，1 对剔除）**：BraTS_vs_BrainTumor 因 n_matched<30 硬门剔除（PR-匹配半径第 6 条，如预登记预判，propensity 近完美可分仅配 ~6 对）。3 可评估对：
  - NIH_vs_RSNA_normal：n_matched=382，Spearman(orig,C)=1.0（7 法 rank 全同 d²=0），CI[1.0,1.0]，SMD max/mean=0.146/0.045 → **FAIL**（CI 上界 1.0≮0.7，top1 未掉）。
  - NIH_vs_VinDr：n_matched=156，Spearman(orig,C)=0.857，CI[0.40,1.0]，SMD 0.128/0.052 → **FAIL**（CI 上界 1.0≮0.7）。
  - HAM_vs_ISIC2020：n_matched=228，Spearman(orig,C)=0.286（GradNorm 7→2 / MDS 2→4 / Energy 4→7，确有重排），CI[-0.87,0.96]，SMD 0.196/0.066 → **FAIL**（CI 上界 0.96≮0.7，巨宽判不出方向）。
- **判定**：**无一对达预登记阈值 → A-4 命门 FAIL。** 据实降级 negative result / limitation，不删不硬撑。
- **低功效剖析（当 contribution）**：7 方法仅 7 个 rank 点，bootstrap Spearman CI 天然趋向 [-1,1]，CI 上界<0.7 近乎不可达（除非点估计本就很低 + n 极大）→ **该判据结构性低功效，可能与真值无关地恒 FAIL**。「为何 7 方法 Spearman 是结构性低功效判据」写入 discussion 当 contribution。
- **修正不偏向 PASS**：PR-匹配半径修正（43 维→1 维 caliper）恢复了配对功效（n 6→156/382/228），结果可 PASS 可真 FAIL；实跑为真 FAIL（CI 上界=1.0/1.0/0.96 而非无功效的全 1.0），故据实降级。

## 预登记项（防 HARKing，跑前冻结）

- **PR-F1（共线准入）**：regress-out 方案 A **仅当 R0a 同机构 normal-vs-anomaly 上 f(artifact) 对 score 的 R²<0.3 时**才作对照纳入；R²≥0.3 = 共线坐实，方案 A 作废不进 paper。命门不依赖方案 A。
- **PR-F2（唯一裁决 + CI）**：A-4 命门**只用方案 C**，A/B 仅附录 robustness（杜绝三方案取最显著的隐性 p-hacking）；翻转判据用 bootstrap CI 上界（B=1000）非点估计；第二口径=机制可解释性，与 CI 口径正交。
- **PR-F3（模态准入门）**：每模态进入 A-4 前先报去污染**前** cross-source 对上 7 方法 raw AUROC 分布；若该模态 7 法 AUROC **全<0.6**（无有效排名可翻，跨域 frozen encoder 退化）→ **不计入 A-4**，只用于 A-1/A-2。不事后挑过门模态。
- **PR-匹配半径**：方案 C 的 artifact 匹配预登记 caliper（如 0.2 SD），不事后调。
  - **【v3 澄清，2026-06-19】** 「0.2 SD caliper」按 propensity-score matching 文献标准含义（Austin 2011, Pharm Stat / PMC3144483；Wang 2014 AJE）= **1 维 logistic propensity score 的 logit 上、半径 = 0.2×SD(logit)**，非 43 维特征空间欧氏球（初版实现误读，维度灾难致 NIH/RSNA 仅配 6/500 对无统计功效，证据见 04_LOG Entry 6）。修正实现冻死 7 规格（防新自由度 HARKing）：
    1. **propensity 模型**：plain logistic regression，输入 = 与 A-1/A-2 同一套 43 维 artifact 特征（z-score 标化），**无交互项、无多项式**。
    2. **正则**：无正则；若数值不稳需正则则固定 L2 并在 paper 写明 λ 值，**不做 CV 选 λ**。
    3. **交叉拟合**：k=5 fold，用 out-of-fold propensity 防过拟合自配，k 预登记。
    4. **caliper**：0.2 × SD(logit propensity)，pooled。
    5. **配对**：1:1 greedy without replacement，随机序 seed=42。
    6. **配对数硬门**：修正后某对 n_matched **< 30 则不计入 A-4**（类比 PR-F3，替代原脚本 n<10 仅 WARN），不事后挑过门对。
    7. **平衡诊断必报**：配对后报 standardized mean difference（SMD），|SMD|<0.1 为平衡达标（证明 artifact 真配齐 + 防 K3 保险）。
  - **程序正当性**：先 LOG 留痕（Entry 6）→ 本条 v3 澄清留 v2 原文 → coder 实现 → verifier 核 n_matched/SMD → **paper methods 必主动 disclose**「预登记 0.2 SD；初版误作 43 维欧氏球仅配 6 对无功效；按 Austin 2011 修正为 1 维 propensity logit caliper」。**修正方向不偏向 PASS**：现 FAIL 是无功效（CI 上界=1.0）非排名稳，修正恢复功效后结果可 PASS 可真 FAIL。

## L3 设定（钉死）
L3 重排用 **cross-source 跨机构对**（ID=本机构如 NIH，OOD=跨机构如 VinDr，任务=检测图来自 OOD 机构），与 L1 量化同对。MedIAnomaly 同集内 near-OOD 仅作对照。理由：headline 攻跨机构 artifact 混淆排名，同集内无跨机构 artifact 可去污染（假触 K2 + 割裂 L1↔L3 承重链）。

## 锁定超参（堵臆想红线）
- backbone：TorchXRayVision DenseNet121-res224 frozen encoder（倒二层特征 N=1024，224² 输入）。
- OOD 方法集（OpenOOD 官方超参）：MSP（无参）/ ODIN（T=1000, ε=0.0014）/ Energy EBO（T=1）/ Mahalanobis MDS（无参）/ KNN（K=50）/ ViM（**dim=512**，自定依 ViM 原论文 arXiv:2203.10807 N<1500→D≈N/2 法则，paper 标注）/ GradNorm（无参）。
- artifact 特征 = 43 维（hist32 + stats + glcm Haralick + 边缘暗角比 + fft 高低频比），复用 G5 killshot 脚本，**必 resize 224² 控分辨率泄漏**。

## Kill criteria（书面，事前冻结）
- **K1**：artifact-only AUROC 在 ≥3 个 benchmark 对都 <0.7 → 现象不普适，**砍立项**。
- **K2**：去污染后 OOD 方法排名 Spearman(原,去污染) >0.9（几乎不变）→ 污染无 actionable 后果，**降 ICBINB 短文，不投 CVPR**。
  - **【K2 修订记录，2026-06-19 v4 reframe】** K2 literal（Spearman>0.9）实跑**仅 1/3 对满足**（NIH_vs_RSNA_normal=1.0>0.9 触发；NIH_vs_VinDr=0.857<0.9 未触发；HAM_vs_ISIC2020=0.286<0.9 未触发）→ **非干净 K2 触发**（K2 设计意图是「所有对都几乎不变」）。**用户拍板 reframe 而非降 ICBINB**：理由 = L1（A-1/A-2 PASS）+ source-leakage（A-5，ViM=1.0）承重**独立于排名翻转成立**，CVPR 命门改为 source-leakage + 评测处方（A-5/A-6），不再依赖 L3 排名翻转。K2 的 ICBINB 退路仍作底线保留（见 01_STORY § 会场）。
- **K3**：去污染协议把真 semantic 信号也去掉（去污染后所有方法都崩到随机）→ 协议无效，回设计。（方案 C 天然防 K3 + 防 K3 硬约束兜底）
- **K4**：撞车——某已发论文已做 L1+L2+L3 完整闭环（非仅概念/3D）→ 撞车 >0.85，**砍或大幅 reframe**。（2026-06-19 researcher×3 核查：OpenMIBOOD 0.18 / PMC10532230 仅 L1 局部限 3D / L1+L2+L3 闭环零命中 = K4 安全）

## Gate1（立项后第一闸，CVPR 就绪前置）
- 第一硬前置 = 在 ≥3 个 cross-source 对上复现 A-1（artifact-only 高 AUROC）+ 实现 A-3 去污染使其掉到随机。出不来则现象不稳，退守。
- 次优先 = A-4 重排（命门，决定 CVPR vs ICBINB）。
- 算力 ≤50 GPU·h（v2 矩阵实估 ~10 GPU·h，本地 RTX4070 8GB，无需 HPC 训练）。

## 反跑偏红线（继承组合台）
- 数字一律 Bash/Grep 核 csv，不信 Read。
- artifact 特征提取必须 resize 统一分辨率（否则分辨率直接泄漏 AUROC=1 无意义）——G5 已落实，正式实验沿用。
- OOD 方法用官方实现/官方超参，查不到标 TODO，不臆想。
- 去污染前后用同一 split、同一方法集，三方对账。

---

## v5 扩证据预登记块（2026-06-19 跑前冻结，防 HARKing；不删历史，纯追加）

> NeurIPS D&B 主投扩证据。以下 PR-G1~G4 + A-5 v5 升级口径 + FAIL 三档退路**在跑任何 v5 扩展实验前冻结**，结果出来后不得回改自由度。**官方超参查不到一律标 TODO 绝不臆想**（当前新增 6 法均经 researcher 确认无 TODO）。

### A-5 v5 修订记录（source-leakage 承重升级 + 删 A-5b 组级 claim）

> **不删 v4 的 A-5 原判据，表内 A-5 行已就地升级口径，本块留时间线痕。**

- **升级口径**：A-5（source-leakage 承重）= **ViM AUROC 在 ≥(N-1)/N 个 cross-source normal-vs-normal 对上 >0.95**（N = 实际可评估对数）。现状 4/4=1.0；v5 扩到 6–7 对后**容忍 ≤1 对退化**，退化对须附 PR-F3 类退化机制理由（如该对 frozen encoder 跨域整体崩 / 该模态 source covariate 偏弱）。门贴合现 4/4 全 1.0 的强度——**留下 FAIL 空间才有承重意义，非松到必过**。
- **承重只由 ViM 单法承载**：命门口径只看 ViM，**不让任何 multi-label 适配方法（SHE/NNGuide/DICE/Residual/fDBD）单独承载 A-5 命门**——ViM 在本 backbone 无 multi-label 适配歧义（dim=512 纯几何残差，不依赖 softmax/sigmoid 口径），故承重最稳。
- **删去原拟 A-5b 组级命门**：原计划登记「feature-based 方法组 vs logit-based 方法组在 normal-vs-normal 上 AUROC 存在组级显著差异」为辅命门。**skeptic 2026-06-19 实算证伪当命门资格**：该组级差异几乎全靠 ViM 单骑撑起，**leave-ViM-out 后 CXR 上组级差异反号**（feature 组不再系统性高于 logit 组）→ 当命门会反噬 A-5a 这条 ViM=1.0 的铁证。故**13 法 × 多对 AUROC 谱仅作描述性证据呈现（展示工件完整度 + 方法谱形），不预登记任何组级显著性命门**，discussion 据实陈述异质性、不挂「组规律」帽子。

### PR-G1：扩展方法集 7 → 13（复用 7 + 新增 6，OpenOOD 官方超参）

- **复用 7（不重跑，直接复用 `l3_method_scores_raw`）**：MSP（无参）/ ODIN（T=1000, ε=0.0014）/ Energy EBO（T=1）/ Mahalanobis MDS（无参）/ KNN（K=50）/ ViM（dim=512）/ GradNorm（无参）。
- **新增 6（OpenOOD 官方超参，researcher 已查、无 TODO）**：
  1. **Residual**（dim=512，纯几何子空间残差，不依赖 logits）
  2. **SHE**（metric = inner_product）
  3. **NNGuide**（alpha=0.01, K=100）
  4. **fDBD**（distance_as_normalizer=True）
  5. **ASH**（percentile=90；**唯一需 live forward**，其余复用已存盘 feats/logits）
  6. **DICE**（p=90）
- **明确排除（写明理由，不事后挑）**：GEN / KLM / Relation / RankFeat / SCALE —— 软依赖 single-label softmax 概率结构，或需中间 conv 层激活（本 frozen 倒二层 + classifier 取不到），**与本 backbone 不兼容**，排除非择优。
- **超参纪律**：上述 6 法官方超参当前均经 researcher 在 OpenOOD 官方实现确认，无臆想；若后续任一法官方超参查不到 → 标 TODO 不臆补，该法暂不纳入。

### PR-G2：multi-label 适配（3 处适配跑前冻结，不事后调）

> backbone = TorchXRayVision DenseNet121，18 病理 **multi-label sigmoid**（非 single-label softmax）。OpenOOD 多数后处理器默认 single-label softmax，故下列适配跑前冻死；**每处在 paper 写「官方假设 single-label softmax；本 backbone multi-label sigmoid 故 X → Y，是 multi-label 下的 canonical 推广 + 理由」+ limitation**。

1. **SHE**：global pattern = **全 ID penultimate 特征均值**（单一全局原型）+ inner_product 打分，**不按伪类分桶**（multi-label 无单一类标签，按伪类分桶会引入自由度 + 桶定义歧义）。limitation：丢失类条件结构，仅测全局原型对齐度。
2. **NNGuide**：energy = **logsumexp(18 logits)**，与现有 Energy(EBO) 同口径（一致性）；guide 的 KNN **K=100 余弦相似度**。limitation：energy 在 multi-label sigmoid 下非严格 free energy，作 confidence proxy。
3. **DICE / Residual / fDBD**：`get_fc` 取 classifier 权重 **W(18×1024) + b(18)**；DICE 的 mean activation 用 **ID-train penultimate 特征、p=90** 稀疏化。limitation：DICE 稀疏掩码按多 logit 平均贡献定，跨 18 个 sigmoid head。
- **命门保护**：A-5 承重只看 ViM（无适配歧义），**上述任何适配法不单独承载 A-5 命门**，仅进 13 法描述性谱。

### PR-G3：扩展对 4 → 6–7（全 normal-vs-normal 物理切分）

- **复用 4 对**（已 PASS / 已存盘）：NIH_vs_RSNA_normal、NIH_vs_VinDr、HAM_vs_ISIC2020、BraTS_vs_BrainTumor（后者 n<30 仍按 PR-匹配半径第 6 条剔除）。
- **新增对（仅用 `.portfolio/datasets.json` 标 ready 的，feats 已存盘）**：
  - **P2b**：VinDr vs RSNA_normal（CXR 第 3 对）
  - **P4b**：HAM_NV vs fitzpatrick17k（dermoscopy 第 2 对）
  - **P4c**：ISIC2020_benign vs PAD-UFES（dermoscopy 第 3 对，**可选**——ready 则纳入，否则不强求）
- **拍板点边界（不擅纳，标 TODO）**：LAG / Camelyon16 / VinCXR（Zenodo 待下，datasets.json todo）+ MRI 第 3 源 = **需 HPC 上传新数据 → 对外传输拍板点**，**不擅自纳入 v5**，标 TODO 待主线拍板后另行扩。
- 全部为 **normal-vs-normal 物理切分**（按采集机构/源切，零 semantic 差异），口径同 v4 的 4 对。

### PR-G4：去污染一致性（新方法在 cleanC 同跑）

- 新增 6 法 + 新增对在 **cleanC**（propensity caliper 0.2 SD，PR-匹配半径 7 规格**不变**）下同跑，与 v4 同协议。
- BraTS n<30 仍按 PR-匹配半径第 6 条剔除。
- **feature-based 方法（含 ViM/Residual）若 cleanC 去污染后仍高分离** = 深层 source leakage 超出 43 维手工 artifact 特征可匹配范围 → **主动 disclose 为 limitation**（与 v4 中 ViM cleanC 恒 =1.0 同等处理，不藏）。

### FAIL 三档退路（事前写清，跑完不得再想新退路）

1. **A-5a FAIL（新增对上 ViM 不再 >0.95，达不到 ≥(N-1)/N）** → source-leakage 是 CXR / dermoscopy 跨机构特异、不普适 → **承重退回 A-1/A-2（已独立 PASS）+ A-6 评测处方**，仍是合格的 NeurIPS D&B 贡献（benchmark 污染量化 + 处方）。
2. **13 法描述性谱显示污染不普适（部分模态/方法不见高分离）** → **诚实报模态 / 方法异质性**，不强行普适化，谱本身即工件价值。
3. **最坏情形** → source-leakage 整体降为 **supporting observation**，承重 = **A-1/A-2 + A-6**，headline 仍站得住（artifact 污染现象 + 可操作评测规范）。
