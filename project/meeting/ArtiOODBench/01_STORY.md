# ArtiOODBench — STORY

> **⚠️ Headline reframe（2026-06-19，用户拍板 option ① + skeptic 0 致命放行）**：原承重命门 L3「去污染后方法排名翻转（actionable so-what）」据实跑出 FAIL（4 对中 3 对可评估，Spearman(orig,C) = 1.0 / 0.857 / 0.286，无一对达预登记 CI 上界<0.7 或 top1 掉出 top3；7 方法 Spearman 经剖析为结构性低功效判据）。**重心从「排名翻转」转移到同批预登记实验中稳健成立的 L1（artifact-only 高 AUROC）+ source-leakage（ViM 在跨机构 normal-vs-normal 对上 AUROC=1.0）**。L3 FAIL 不删，连同低功效剖析降级为 negative result / limitation 并当 contribution（见 § Lever、§ L3 退场与新承重、`02_ACCEPTANCE.md` A-4 修订记录、`04_LOG.md` Entry 7）。**本节为重心转移后的修订版；原 headline 留痕于下方 § 原 headline（reframe 前，留痕勿删）。**

## Headline（reframe 后，承重版）

**医学影像 OOD detection 基准上的方法表现主要由采集 artifact（扫描仪、机构、源域特征泄漏）驱动，而非真病理异常的检测能力。** 两路独立预登记证据承重：

1. **白盒 artifact 可定位（L1）**：不读任何病理内容的 artifact-only 43 维手工特征，即可在跨机构对上高 AUROC 区分 ID/OOD（跨机构对 AUROC 范围 0.82–0.9997，A-1/A-2 PASS，verifier 已核）。benchmark 的「OOD 信号」大半是 scanner/机构采集指纹。
2. **深层 source leakage（source-leakage 承重）**：主流 OOD 方法 ViM 在**跨机构 normal-vs-normal 对**（两端都是正常图、无任何病理差异，唯一系统差异 = 采集来源）上 AUROC=1.0（4/4 对在 raw 与 cleanC 去污染子集上恒为 1.0；vim_score 内点上界 ~2–7 vs 外点下界 ~3 万–15 万，零重叠）。其「OOD 检测」在物理上等价于「数据集来源检测」——ViM 的 virtual-logit residual 捕获的是源域表示，不是异常。

当 ID 与 OOD 来自不同机构/设备时（绝大多数医学 OOD benchmark 如此），「更强的 OOD 检测器」可能只是「更会读源域指纹的检测器」。我们给出可操作的评测处方（见 § Lever L3'），而非依赖低功效的 7 点 Spearman 排名翻转。

## 原 headline（reframe 前，留痕勿删）

> 以下为 reframe 前以 L3 排名翻转为命门的原 headline，保留以诚实呈现重心转移、防 HARKing。**此 claim 因 L3 实跑 FAIL 已不再作为承重 headline。**
>
> **医学影像 OOD 检测基准在测量采集 artifact，而非病理异常。** 不看任何病理内容的 artifact-only 手工特征即可高 AUROC 区分 ID/OOD（NIH vs VinDr，resize 控分辨率后 AUROC=0.92），说明现有 benchmark 的「OOD 信号」大半是 scanner/采集指纹。当 ID 与 OOD 来自不同机构/设备时（绝大多数医学 OOD benchmark 如此），方法排名被 artifact 混淆——「更强的 OOD 检测器」可能只是「更会读 scanner 指纹的检测器」。

## 为什么是 CV 社区在意的通用失效（非纯医学 niche）

这是 **spurious correlation / shortcut learning 在 OOD detection 评测层的实例**：评测协议本身被一个与任务无关但与域标签强相关的混杂变量（采集 artifact）污染。CV 社区对「benchmark 在测捷径不测能力」高度敏感（ImageNet-C、backgrounds challenge、shortcut learning 系列）。医学影像是这个失效的**最佳放大镜**——不同机构的 scanner/采集协议差异巨大且系统化，artifact 信号比自然图像强得多。

## Lever（承重链，reframe 后）

> reframe 后承重链 = **L1（白盒 artifact 量化，PASS）+ source-leakage（深层源域泄漏，新承重）+ L3'（评测协议处方，补 L3 退场的 actionable so-what 空缺）**。原 L3「排名翻转」降级，原文保留于 § L3 退场与新承重。

1. **L1 现象量化**（G5 + Gate1 已确证 PASS）：artifact-only 43 维手工特征在跨机构对上高 AUROC（范围 0.82–0.9997），覆盖 ≥3 模态。证明污染普遍非个例（A-1/A-2 PASS，verifier 核实）。
2. **L2 去污染协议**：propensity-matched artifact-matched ID-OOD 配对（1 维 logit caliper），削去手工 artifact 可解释的 covariate 部分（A-3 artifact-only 掉到 <0.65）。**边界**：propensity 削的是 43 维手工特征能匹配的那部分，对 backbone 深层 source 表示无能为力（见下 source-leakage）。
3. **source-leakage（新承重，替代原 L3 命门地位）**：主流 OOD 方法在**跨机构 normal-vs-normal 物理切分**（两端皆正常图，唯一系统差异 = 采集来源）上仍完美分离——ViM AUROC=1.0（4/4 对 raw 与 cleanC 恒 1.0）。这是「方法在测来源而非异常」的直接物理证据，且**不依赖低功效的 7 点排名翻转**。**主动 disclose**：cleanC 去污染后 ViM 仍 1.0 = 深层 source leakage 比 43 维手工特征能量化的更顽固（见 § 诚实边界 + A-4 修订记录）。
4. **L3'（评测协议处方，补 actionable so-what）**：原 L3 排名翻转 FAIL 后，actionable so-what 改为给社区可操作的评测规范：①**cross-source normal-vs-normal 必须作 sanity baseline**——方法若在它上 AUROC 高，说明 benchmark 被源域污染，该 benchmark 的 OOD 结果作废；②**报 artifact-only AUROC 作污染上界**，量化任一 benchmark 对的 source 可分性。这是给社区的评测处方，不依赖 7 点 Spearman。

## 与先驱的差异化（Related Work 硬对齐，reframe 后必正面摆 ImageNet-OOD）

> reframe 后承重移至 source-leakage，**最近邻先驱变为 ImageNet-OOD**（已证 OOD detector 对 covariate>semantic 敏感 + ViM latch spurious feature）。Related Work 必须正面、显著地摆它并讲清递进，不得回避——这是 CVPR 命中靠差异化辩护的核心（非 killer result）。

**最近邻先驱（必正面对齐）**：
- **ImageNet-OOD**（ICLR 2024, arXiv:2310.01755）：已证明 OOD detector 的表现对 covariate shift 比对 semantic shift 更敏感，并指出 ViM 等方法会 latch 到 spurious feature。**但限自然图像、黑盒性能归因（不定位 spurious 信号的物理载体）、无去污染配对协议。**
- **OpenMIBOOD**（CVPR 2025, arXiv:2503.16247）：已区分 covariate-shift vs semantic-shift 概念，且附带发现 covariate 影响，但**未闭环量化、无 artifact-only 白盒定位、无去污染配对**。
- **PMC10532230**（3D MRI）：已报 IHF AUROC=0.97 + 「benchmark 可能含 trivial feature」，但**限 3D 分割、无白盒定位、无配对协议**。

**递进定位（一句话）**：从 ImageNet-OOD 的「自然图像上黑盒性能归因」→ 本工作的「医学影像上白盒 artifact 定位」——医学影像里 covariate shift 拥有**可量化的物理载体（采集 artifact：扫描仪/机构指纹）**，使「方法在测来源而非异常」从黑盒观察升级为可定位、可切分、可去污染的物理证据。

**3 条差异化（写成 contribution bullet）**：
1. **白盒 artifact 定位**：43 维手工 artifact-only 特征跨机构高 AUROC（0.82–0.9997），把 spurious 信号定位到具体物理载体（直方图/纹理/暗角/频谱），而非 ImageNet-OOD 的黑盒归因。
2. **cross-institution normal-vs-normal 物理切分 covariate vs semantic**：两端皆正常图、唯一系统差异 = 采集来源，构造出干净的「纯 covariate、零 semantic」对，直接量度方法对来源的敏感度（ViM AUROC=1.0）；自然图像数据集少有这种带物理标签的纯 covariate 切分。
3. **propensity 去污染配对协议**：1 维 logistic propensity logit caliper 的 artifact-matched 配对协议，可移植到任意跨机构医学 OOD benchmark，作为去污染 + sanity baseline。

## L3 退场与新承重（HARKing 免疫，discussion/methods 必明写时间线）

> reframe 的诚实核心：**承重重心移转必须据实呈现为时间线，不得写成「我们一直就是这个 claim」。** discussion / methods 必须按以下顺序明写：

1. **预登记**：L3「去污染后方法排名翻转」于 `02_ACCEPTANCE.md` v2 跑前冻结为唯一承重命门（2026-06-19，跑前，A-4 + PR-F1/F2/F3）。
2. **实跑结果**：4 对中 BraTS 对因 n_matched<30 硬门剔除（如预登记预判），3 对可评估——Spearman(orig,C) = 1.0（NIH_vs_RSNA_normal, n=382, CI[1.0,1.0]）/ 0.857（NIH_vs_VinDr, n=156, CI[0.40,1.0]）/ 0.286（HAM_vs_ISIC2020, n=228, CI[-0.87,0.96]）。**无一对达预登记 CI 上界<0.7 或 top1 掉出 top3** → A-4 命门 FAIL。
3. **低功效剖析**：7 方法仅 7 个 rank 点，bootstrap Spearman CI 天然趋向 [-1,1]，CI 上界<0.7 近乎不可达——**该判据结构性低功效，可能与真值无关地恒 FAIL**。此剖析「为何 7 方法 Spearman 是结构性低功效判据」对社区有用，**当 contribution 写入，不删 L3 FAIL**。
4. **据实降级 + 重心转移**：headline 移至同批预登记实验中稳健成立的 **L1（artifact 0.82–0.9997 PASS）+ source-leakage（ViM=1.0）**。source-leakage 的 ViM=1.0 在 paper 中写为「pre-specified L3 matrix 的 consistent observation across all 4 pairs」，**不写「we found」**（它出自预登记矩阵的一致观测，非事后挖掘）。

## 诚实边界（防跑偏）

- **artifact 量化边界**：跨机构对 AUROC 范围 0.82–0.9997，headline 不夸大成「完全是 artifact」；claim 是「方法表现主要由 artifact 驱动」，由 normal-vs-normal 纯 covariate 切分支撑。
- **不 claim「所有 OOD benchmark 都废」**；claim「当 ID/OOD 跨机构时方法表现被源域混淆，需 cross-source normal-vs-normal sanity baseline + artifact-only 污染上界」。
- **ViM cleanC=1.0 主动 disclose（不藏）**：L2 propensity 去污染（cleanC）削的是 43 维手工 artifact 可解释的那部分 covariate（A-3 artifact-only 掉 <0.65），但 **ViM 在 cleanC 子集上仍 AUROC=1.0**（4/4 对 raw+cleanC 恒 1.0）。物理含义 = ViM virtual-logit residual 捕获的 backbone 深层 source 表示**超出 43 维手工特征的匹配范围** → 写成 finding + limitation：「深层 source leakage 比手工特征能量化的更顽固，propensity 配对无法削除」。这既加强 source-leakage 承重，也是协议的诚实 limitation。
- **L3 FAIL 不删、不硬撑排名翻转**：原 L3 命门据实 FAIL，连同低功效剖析降级 negative result / limitation（见上 § L3 退场与新承重 + `02_ACCEPTANCE.md` A-4 修订记录）。

## 会场（reframe 后更新 → 2026-06-19 v5：D&B 主投，用户拍板「为 70 中稿」）

- **主投：NeurIPS Datasets & Benchmarks track**（用户 2026-06-19 拍板，为最大化中稿率）。此工件（系统 artifact 量化 + 去污染配对协议 + 评测处方 + 多模态 + 预登记 + 扩展方法池）**正是 D&B track 收的类型**——benchmark critique + 可操作评测规范天然契合，realistic odds 高于主会 critique。命中靠工件完整度 + ImageNet-OOD 差异化辩护，扩证据后「artifact 主导 OOD」跨方法/模态无可辩驳。
- **退路：CVPR 2027**（analysis / benchmark-critique track）：prestige 高但 critique 无 killer result + ImageNet-OOD 祖 → odds 低，作退路非主投。
- **再退：MICCAI**（医学影像受众，artifact 量化 + 评测处方）。
- **底线：ICBINB**（negative-result 友好；source-leakage + L3 低功效剖析仍是合格短文）。

> **70 中稿策略（用户拍板）**：D&B 主投 + **扩证据**——OOD 方法 7→12-15（OpenOOD REACT/DICE/SHE/ASH 等官方实现）+ 加 benchmark 对/模态，使「artifact 主导 OOD」跨方法/模态稳固（顺带缓解 L3 7 点 Spearman 低功效=方法多了 CI 收窄）。扩展方法集 + 新对须**跑前预登记**（写入 ACCEPTANCE，防「加方法到故事 work」HARKing），skeptic 轻量过闸。
