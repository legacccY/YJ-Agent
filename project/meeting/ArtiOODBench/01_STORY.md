# ArtiOODBench — STORY

> **⚠️ Headline reframe v6（2026-06-19，用户拍板「held-out 重算 + 把 in-sample 灌水升为新 benchmark-critique 主贡献」；详 04_LOG Entry 10/11，verifier 零 drift）**：v4 的 source-leakage 承重数字「ViM 在跨机构 normal-vs-normal 对上 AUROC=1.0」**被证为 in-sample 评估伪迹**（l3 用 `feats_test=concat(feats_id,feats_ood)` 致投影类残差打分把 in-sample ID 当满分信号、与 source 无关地完美分离）。held-out 协议重算真值：ViM 0.406–0.997（mean 0.777，>0.95 仅 2/7）→ **A-5 v5 strict 门 FAIL**，触预登记 FAIL 三档退路 #1。**承重据实迁移到三贡献框架**：①现象（L1，artifact-only 白盒定位，A-1/A-2 PASS）②机制（in-sample 评估灌水陷阱，A-7 新机制贡献）③处方（held-out 协议 + sanity baseline + artifact 上界，A-6）。source 信号仍真实可检但**中等、由 source 距离驱动、含诚实负例**（NIH/RSNA held-out ViM 0.406≈chance）。**本节为 v6 修订版；v4 reframe 块与原 headline 全留痕于下，不删（HARKing 免疫）。**

> **⚠️ v4 Headline reframe（2026-06-19，用户拍板 option ① + skeptic 0 致命放行；留痕，已被 v6 校正）**：原承重命门 L3「去污染后方法排名翻转（actionable so-what）」据实跑出 FAIL（4 对中 3 对可评估，Spearman(orig,C) = 1.0 / 0.857 / 0.286，无一对达预登记 CI 上界<0.7 或 top1 掉出 top3；7 方法 Spearman 经剖析为结构性低功效判据）。v4 重心从「排名翻转」转移到 L1（artifact-only 高 AUROC）+ source-leakage（ViM 在跨机构 normal-vs-normal 对上 AUROC=1.0）。L3 FAIL 不删，连同低功效剖析降级为 negative result / limitation 并当 contribution。**⚠️ v4 的 ViM=1.0 source-leakage 承重数字已被 v6 证为 in-sample 伪迹、held-out 重算后 strict FAIL，见上 v6 块 + `02_ACCEPTANCE.md` A-5 v6 修订记录。**

## Headline（reframe v6 后 + skeptic 收窄定稿，承重版）

> **⚠️ skeptic v6 收窄定稿（2026-06-19，04_LOG Entry 11 红队，1🔴+3🟠 全落实；本块为定稿，原三并列 bullet 版留痕于下「原 v6 headline」不删）**：A-7 framing 据 skeptic 致命-1 收窄——held-out 评估是 ViM 原论文（arXiv:2203.10807，principal space P 与 α 由 training set 事前确定）+ OpenOOD 既有强制标准协议，**不能 claim「我们发现投影类需 held-out 评估」**（那是常识，会被反咬）。headline 改为**单一叙事弧**（污染物 → 如何精确伪装 → 去伪处方）。source 距离相关补到 **n=7**（ρ=0.821 / r=0.955），「单因子」改「一个主要驱动因子」。

**叙事弧（single narrative arc）：医学影像 OOD detection 基准被采集 artifact 这一可白盒定位的污染物渗透——不读任何病理内容的 artifact-only 手工特征即可高 AUROC 预测 source 身份（跨 3 模态 AUROC 0.64–0.9997）；这一污染物如何精确伪装成「OOD 信号」，甚至让投影类检测器（ViM/Residual）在一种已知的 in-sample estimation leakage 误用下产生伪完美分离（AUROC=1.00，足以骗过投稿前自审），而 held-out 校正后真 source 信号回落到中等量级（mean 0.777）、由 source 距离驱动、含同模态诚实负例；我们由此给出一套去伪处方——held-out 协议 + cross-source normal-vs-normal sanity baseline + artifact-only 污染上界。**

这条弧的三个环节据实展开（污染物 / 伪装 / 去伪处方）：

1. **污染物：白盒可定位的 artifact（现象，L1）**：不读任何病理内容的 artifact-only 43 维手工特征即可高 AUROC 区分 source 身份（跨机构命门对 AUROC 0.82–0.9997、含两美国源最弱对 0.64，覆盖 CXR / 脑 MRI / dermoscopy 三模态，A-1/A-2 PASS，verifier 已核）。benchmark 的「OOD 信号」大半是 scanner/机构采集指纹。**此环独立于下文被推翻的几何打分链**：artifact-only 是手工特征 AUROC，不经任何 ViM 子空间拟合，不受 in-sample 灌水影响。
2. **伪装：污染物如何精确伪装成 OOD 信号（机制，A-7 收窄贡献）**：投影类 OOD 检测器（ViM/Residual，基于 principal-subspace 残差打分）在一种**已知的 estimation/in-sample leakage 误用**下报近完美 AUROC（1.00）。本文不 claim 发现「held-out 才对」（那是 ViM/OpenOOD 既有标准协议）；本文量化的是：**这一已知 leakage 在 N_id<D 的 underdetermined 投影子空间 + 跨源 medical benchmark 场景下被放大到 Δ=+0.223，且精确伪装成完美 source-leakage 结论（ViM=1.0，足以骗过投稿前自审）。** 这个 N_id<D 放大效应 + 它如何 masquerade 成可信 benchmark-critique，文献未专门打包过，是 cautionary 方法学贡献。灌水高度局部化（仅投影类 ViM/Residual 各 +0.223，其余 11 法 |Δ|<0.012）。
3. **去伪：诚实量级的 source leakage + 处方（held-out 真值）**：held-out 协议下 source 信号真实可检（ViM 7 对 0.406–0.997 全 >> 同源 held-out chance ≈0.5 的中位）但**中等、source 距离是一个主要驱动因子**（artifact 可分性 vs held-out ViM 的 Spearman ρ=0.821 / Pearson r=0.955, n=7）。含同模态内**诚实负例**：NIH/RSNA 两美国源 artifact=0.64 → held-out ViM=0.406≈chance（证非「普遍/完美 source leakage」，是 source 距离驱动）。

当 ID 与 OOD 来自不同机构/设备时（绝大多数医学 OOD benchmark 如此），且当评估协议为 in-sample 时，「更强的 OOD 检测器」可能只是「读 in-sample 几何伪迹 + 源域指纹的检测器」。我们给出可操作的评测处方（held-out 协议 + cross-source normal-vs-normal sanity baseline + artifact-only 污染上界，见 § Lever L3'），而非依赖低功效的 7 点 Spearman 排名翻转或被 in-sample 灌水的近完美 AUROC。

### 原 v6 headline（skeptic 收窄前的三并列 bullet 版，留痕勿删）

> 以下为 skeptic v6 红队收窄前的 headline，三并列 bullet 结构（现象/机制/处方）。**A-7 机制 bullet 原写「这是可推广任意 projection-based OOD 法的评测协议陷阱」隐含「发现 held-out 才对」，据 skeptic 致命-1 收窄为上文版；source 相关原 n=4（ρ=1.0/r=0.9995）补到 n=7。保留以诚实呈现收窄过程。**
>
> **医学影像 OOD detection 基准受采集 artifact（扫描仪、机构、源域指纹）污染——不读任何病理内容的 artifact-only 手工特征即可高 AUROC 预测 source 身份（跨 3 模态 AUROC 0.64–1.00）；且投影类 OOD 检测器（ViM/Residual）因在 in-sample principal subspace 上拟合产生系统性评估虚高（in-sample 近完美 1.00 → held-out 0.78），held-out 校正后真 source 信号中等且由 source 距离驱动。** 三路独立证据承重（现象 / 机制 / 处方）：
>
> 1. **白盒 artifact 可定位（现象，L1）**：不读任何病理内容的 artifact-only 43 维手工特征即可高 AUROC 区分 source 身份（跨机构命门对 AUROC 0.82–0.9997、含两美国源最弱对 0.64，覆盖 CXR / 脑 MRI / dermoscopy 三模态，A-1/A-2 PASS，verifier 已核）。benchmark 的「OOD 信号」大半是 scanner/机构采集指纹。
> 2. **in-sample 评估灌水陷阱（机制，A-7 新贡献）**：投影类 OOD 检测器（ViM/Residual，基于 principal-subspace 残差打分）在常见 in-sample 评估协议下报近完美 AUROC（1.00），但这是 null-space 残差伪迹（N_id<D 致 in-sample ID 残差≈0、完美分离任何 held-out，**与 source 无关**），非真 source 信号。held-out 校正后 ViM 真值 mean 0.777（仅投影类受影响：ViM/Residual 各 −0.223，其余 11 法 |Δ|<0.012）。这是可推广任意 projection-based OOD 法的评测协议陷阱。
> 3. **诚实量级的 source leakage（held-out 真值）**：held-out 协议下 source 信号真实可检（ViM 7 对 0.406–0.997 全 >> 同源 held-out chance ≈0.5 的中位）但**中等、由 source 距离单因子驱动**（artifact 可分性 vs held-out ViM 的 Spearman ρ=1.0 / Pearson r=0.9995, p=0.0005, n=4）。含同模态内**诚实负例**：NIH/RSNA 两美国源 artifact=0.64 → held-out ViM=0.406≈chance（证非「普遍/完美 source leakage」，是 source 距离驱动）。

## 原 headline（reframe 前，留痕勿删）

> 以下为 reframe 前以 L3 排名翻转为命门的原 headline，保留以诚实呈现重心转移、防 HARKing。**此 claim 因 L3 实跑 FAIL 已不再作为承重 headline。**
>
> **医学影像 OOD 检测基准在测量采集 artifact，而非病理异常。** 不看任何病理内容的 artifact-only 手工特征即可高 AUROC 区分 ID/OOD（NIH vs VinDr，resize 控分辨率后 AUROC=0.92），说明现有 benchmark 的「OOD 信号」大半是 scanner/采集指纹。当 ID 与 OOD 来自不同机构/设备时（绝大多数医学 OOD benchmark 如此），方法排名被 artifact 混淆——「更强的 OOD 检测器」可能只是「更会读 scanner 指纹的检测器」。

## 为什么是 CV 社区在意的通用失效（非纯医学 niche）

这是 **spurious correlation / shortcut learning 在 OOD detection 评测层的实例**：评测协议本身被一个与任务无关但与域标签强相关的混杂变量（采集 artifact）污染。CV 社区对「benchmark 在测捷径不测能力」高度敏感（ImageNet-C、backgrounds challenge、shortcut learning 系列）。医学影像是这个失效的**最佳放大镜**——不同机构的 scanner/采集协议差异巨大且系统化，artifact 信号比自然图像强得多。

## Lever（承重链，reframe v6 后）

> **reframe v6 承重链 = L1（白盒 artifact 量化 source 身份，PASS）+ 新机制贡献（in-sample 评估灌水陷阱，A-7）+ L3'（评测协议处方：held-out + sanity baseline + artifact 上界，A-6）。** v4 的「source-leakage 深层泄漏 ViM=1.0」承重数字被证为 in-sample 伪迹、held-out 重算后 strict FAIL、降为 held-out 真值描述性证据（source 信号真实但中等、source 距离驱动、含诚实负例），承重让位给 A-7 机制贡献。原 L3「排名翻转」维持降级。**以下编号项 1/2/3/4 为 v4 原文留痕（含已失效的 ViM=1.0 承重表述），v6 校正口径见上 § Headline + 下 § L3 退场与新承重 v6 时间线 + `02_ACCEPTANCE.md` A-5 v6 / A-7。**

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

### v6 时间线追加（HARKing 免疫：ViM=1.0 被证 in-sample 伪迹 → held-out 校正 → 承重据实再迁移；discussion/methods 必明写，不写成「一直就是这 claim」）

> v4 把承重押在「ViM=1.0 完美 source leakage」。**v6 据实校正这条数字本身——必须明写完整时间线，不得抹平：**

5. **v5 报满分（in-sample）**：v5 扩证据后 A-5 ViM raw AUROC = 1.0 全 7/7 对，写入 ACCEPTANCE 为「pre-specified consistent observation」（Entry 9，in-sample 协议）。
6. **reviewer 攻**：对抗审 05_DRAFT_core.md 列头号 reject 风险 =「ViM=1.0 可能是 trivial 评估伪迹而非真 source covariate」（Entry 10）。
7. **负对照证伪**：主线写 `scripts/sanity_samesource_vim.py`，C1 同一来源对半切 + in-sample 也给 ViM=1.0（1.0 来自 in-sample 不对称、非 source）、C2 同源 held-out ≈0.5（无信号）、C3 跨源 held-out 真信号但非完美 → **坐实 1.0 是 in-sample 评估协议混杂**（根因：投影类 null-space 残差，N_id<D 致 in-sample ID 残差≈0）。
8. **held-out 校正 + 承重据实再迁移**：用户拍板 held-out 重算（Entry 11）。held-out ViM 0.406–0.997（mean 0.777，>0.95 仅 2/7）→ A-5 v5 strict 门 **FAIL**，触预登记 FAIL 三档退路 #1。**承重再迁移到三贡献框架**：现象（L1，A-1/A-2 PASS，不变）+ 机制（A-7，**收窄 framing 见下**）+ 处方（held-out 协议 + sanity baseline + artifact 上界，A-6）。**in-sample 灌水写成 finding + 方法学贡献，不写成 bug 致歉。** source 信号据实写诚实量级（中等、source 距离驱动、含 NIH/RSNA 0.406 诚实负例），不再写「完美/普遍 source leakage」。**paper 必呈这条「v5 满分→reviewer 攻→负对照证伪→held-out 校正→承重据实迁移」时间线，证非 HARKing。**
   - **【skeptic v6 致命-1 收窄，A-7 framing 定稿】**：held-out 评估**是 ViM 原论文（arXiv:2203.10807，principal space P 与 α 由 training set 事前确定）+ OpenOOD 既有强制标准协议**，不是本文发现的处方。v5 的 in-sample 跑法（`feats_test` 含 ID 半）= 违反既有标准 = **已知的 estimation/in-sample leakage 误用**。故 A-7 **绝不能 claim「我们发现投影类 OOD 需 held-out 评估」**（常识，会被审稿人反咬「自己跑错又改对」）。**A-7 收窄口径**：量化这一**已知的** estimation/in-sample leakage 在 **N_id<D 的 underdetermined 投影子空间 + 跨源 medical benchmark** 场景下被放大到 **Δ=+0.223** 且**精确伪装成完美 source-leakage 结论（ViM=1.0，足以骗过投稿前自审）**——这个 N_id<D 放大效应 + 它如何 masquerade 成可信 benchmark-critique，文献未专门打包过，是 cautionary 方法学贡献。Related Work 必正面引 ViM 原文 train-fit 设定 + leakage taxonomy（arXiv:2604.04199，已知 estimation leakage 在 N>>D 低维下 ΔAUC<0.005），差异化 = 本文证同类 leakage 在 N_id<D 投影子空间下放大到 +0.223 且产生确定性 perfect separation。

## 诚实边界（防跑偏，v6 校正）

- **artifact 量化边界**：跨机构命门对 AUROC 范围 0.82–0.9997（含两美国源最弱对 0.64），headline 不夸大成「完全是 artifact」；claim 是「benchmark 受 artifact 污染、方法表现主要由 source 可分性驱动」，由 normal-vs-normal 纯 covariate 切分支撑。
- **source leakage 写诚实量级，不写「完美/普遍」（v6 红线）**：held-out 校正后 ViM 真值 0.406–0.997（mean 0.777，>0.95 仅 2/7），**不再写「ViM=1.0 完美 source leakage」**。写：source 信号真实可检（全 >> 同源 held-out chance ≈0.5 的中位）但**中等、source 距离单因子驱动（Spearman ρ=1.0 / Pearson r=0.9995, p=0.0005, n=4）、含诚实负例（NIH/RSNA held-out ViM 0.406≈chance）**。
- **in-sample 灌水写成 finding/机制贡献，不写成 bug 致歉（v6 红线）**：投影类 OOD 检测器 in-sample 评估虚高（ViM/Residual 1.00→0.78，其余 11 法 |Δ|<0.012）是 null-space 残差的内在数学特性（N_id<D），可机理解释可复现、可推广任意 projection-based 法 → 写成评测协议陷阱 finding（A-7），是比原 claim 更契合 D&B 的 benchmark-critique 贡献。
- **不 claim「所有 OOD benchmark 都废」**；claim「当 ID/OOD 跨机构时方法表现被 source 可分性混淆，且投影类检测器 in-sample 评估会报虚高，需 held-out 协议 + cross-source normal-vs-normal sanity baseline + artifact-only 污染上界」。
- **ViM cleanC held-out 0.628 主动 disclose（不藏）**：L2 propensity 去污染（cleanC）削的是 43 维手工 artifact 可解释的那部分 covariate（A-3 artifact-only 掉 <0.65），但 **ViM 在 cleanC held-out 子集上仍 AUROC=0.628**（raw held-out 0.777，Δ−0.149）> chance。物理含义 = ViM virtual-logit residual 捕获的 backbone 深层 source 表示**超出 43 维手工特征的匹配范围** → 写成 finding + limitation：「深层 source leakage 比手工特征能量化的更顽固，propensity 配对仅削去一部分」。（注：v4 此处写「cleanC 仍 1.0」系 in-sample 伪迹，v6 校正为 held-out 0.628。）
- **L3 FAIL 不删、不硬撑排名翻转**：原 L3 命门据实 FAIL（in-sample 与 held-out 协议下均 FAIL），连同低功效剖析降级 negative result / limitation（见上 § L3 退场与新承重 + `02_ACCEPTANCE.md` A-4 修订记录）。

## 会场（reframe 后更新 → 2026-06-19 v5：D&B 主投，用户拍板「为 70 中稿」）

- **主投：NeurIPS Datasets & Benchmarks track**（用户 2026-06-19 拍板，为最大化中稿率）。此工件（系统 artifact 量化 + 去污染配对协议 + 评测处方 + 多模态 + 预登记 + 扩展方法池）**正是 D&B track 收的类型**——benchmark critique + 可操作评测规范天然契合，realistic odds 高于主会 critique。命中靠工件完整度 + ImageNet-OOD 差异化辩护，扩证据后「artifact 主导 OOD」跨方法/模态无可辩驳。
- **退路：CVPR 2027**（analysis / benchmark-critique track）：prestige 高但 critique 无 killer result + ImageNet-OOD 祖 → odds 低，作退路非主投。
- **再退：MICCAI**（医学影像受众，artifact 量化 + 评测处方）。
- **底线：ICBINB**（negative-result 友好；source-leakage + L3 低功效剖析仍是合格短文）。

> **70 中稿策略（用户拍板）**：D&B 主投 + **扩证据**——OOD 方法 7→12-15（OpenOOD REACT/DICE/SHE/ASH 等官方实现）+ 加 benchmark 对/模态，使「artifact 主导 OOD」跨方法/模态稳固（顺带缓解 L3 7 点 Spearman 低功效=方法多了 CI 收窄）。扩展方法集 + 新对须**跑前预登记**（写入 ACCEPTANCE，防「加方法到故事 work」HARKing），skeptic 轻量过闸。
