# MedAD-FailMap — STORY FRAMEWORK

> 项目核心叙事 + 贡献边界 + 反跑偏。任务与本文冲突 → 停下澄清，不照描述硬干。
>
> **重铸轨迹（保留以备审计，最新在最上）**：
> - **2026-06-18 第四次重铸（双柱翻盘版，venue 退守 MICCAI/MedIA 后用户拍板）**：ICLR「可外推 PASS」命门正臂在开放 pixel-mask 数据集结构性填不出（METS 卡 Synapse 核验、LGG 精确 skull-strip 后 iso=False、BraTS 跨中心 split 被「不算真外推」一击穿，见 04_LOG 终局决断）。诚实回退 MICCAI/MedIA。本次把承重柱整体翻盘：**柱1 = per-image 可靠性判据，以 C4 risk-coverage 作 actionable rule 领证**（不再押小 partial_r）；**柱2 = 病灶几何决定失败可迁移性的 a priori transferability diagnostic（iso 门写成诊断框架/proposal，非已验证判据）**；**失败相图退为支撑性地基，不当 headline**。**铁律加固：正臂落空写成 benchmark 生态负发现，只 claim 负向命中（前验门预言「不可搬」→ 实测真塌），绝不暗示正向也验过。headline/正文绝不带「外推 / transfer / generalize」当主张。** 旧的「可外推函数 / 条件外推 PASS」叙事整体作废。
> - 2026-06-17 二次收窄（reframe A'）：跨模态正臂免费数据集结构性枯竭，正向 claim 曾收窄为同模态示范（BraTS→METS）。**该同模态正臂亦已落空，本次第四重铸一并弃用。**
> - 2026-06-17 headline 路径 A：把跨模态负诊断从「事故」翻成贡献。

## 一、核心 RQ（一句话）

**重建式医学异常检测何时会失败——能否在信任某次预测之前、仅凭单张图像就判断出来？**
*(When does reconstruction-based medical anomaly detection fail — and can we tell from a single image before trusting it?)*

重建式（无监督）异常检测把「整图重建误差」当异常信号，但它**何时失效从未被刻画到可操作的粒度**。本文把这个失败问题拆成两个**跑前/单图就能问的**子问题，并各给一根承重柱：

1. **柱1（per-image 可靠性，承重）**：给定一张新图像、给定模型已输出的 anomaly score，**还能不能仅凭图像本身的影像学属性，额外判断该图上这次检测靠不靠谱？** 答案是能——我们借放射学 **conspicuity（病灶可见性）** 框架派生无 mask 代理特征，并把它兑现成一条 **actionable selective-prediction rule**：按可靠性排序、只保留最可信的一部分图像，检测性能总体趋势升高（top-10% coverage 下 AD-AUROC 从全集 0.8228 升到 0.9119，见 §三①）。

2. **柱2（a priori transferability diagnostic，第二承重 / 诊断框架）**：给定一个新的（数据集，模态）对，**在跑任何迁移实验之前**，能不能仅凭无标注数据的病灶几何分布，预判「在源集上刻画出的失败模式能不能搬到目标集」？我们提出一个**病灶几何同构（geometric isomorphism）前验诊断框架**（iso 门：area-ratio 双侧守门 + n_components 单侧上界），并用三个跨模态目标集**实证其负向预言**：判据预言这三个目标集都落在源集的失败 regime 之外、迁移会失败——这与实测一致。**柱2 写成诊断框架 / proposal：手上有的是负向命中（预言不可搬 → 实测真塌），没有正向锚（无任何目标集被预言「可搬」且实测搬成），故不 claim 该框架已被正向验证。**

由此，「小病灶普遍难检」这条隐含共识被精确化为**几何 regime 特异**的现象，而非普适规律；并落地成「给一张图判可信度 / 给一对集判可迁移性」两条可操作判据。

**核心定位转向（venue 退守后的关键 framing）**：本文**不 claim「失败模式可外推 / 可迁移 / 可泛化」**——那是 ICLR 命门，正臂在开放数据上填不出（见 §五）。本文 claim 的是更诚实、也更难被一击穿的一件事：**「跨四个开放 pixel-mask 异常检测目标集（涵盖脑 MRI / 皮镜 / 乳腺 X 线 / 眼底三模态），现有开放数据系统性地覆盖不到重建式 AD 的 conspicuity-dilution 失败 regime」**——这是一个 **benchmark 生态层面的发现**，并从机制上解释了**为什么文献里跨数据集 / 跨模态的 AD 失败迁移如此脆**：不是方法不好，是失败几何本身被一个窄 niche 锁定，多数真实模态的病灶几何根本不落进这个 niche。

## 二、为什么这是 capability / analysis paper 而非刷 SOTA

不打「我的 AD 方法 AUROC 更高」。打三件 incumbent 给不出的事：
1. recon-AD 失败在协变量空间的**系统几何**（带交互、非单变量）；
2. **per-image 可靠性判据**（给一张新图判该次检测可信度，兑现为 selective-prediction actionable rule）；
3. **a priori transferability 诊断框架**（给一对集，跑前从无标注几何分布预判失败模式能否迁移）+ 由此得到的 **benchmark 生态负发现**（开放数据覆盖不到 dilution regime）。

贡献是 insight + 可操作判据 + 生态发现，不是新方法——所以「标准做法配足数据也能做」反驳不到点（我们刻画的正是标准做法的失败边界 + 这条边界为什么这么难搬）。

## 三、三大贡献（按承重排序）

| # | 贡献 | 为何 incumbent / 邻近线给不出 |
|---|---|---|
| **①（真承重，全文最干净 actionable 钩子）** | **conspicuity 桥 → per-image 可靠性判据，兑现为 risk-coverage selective-prediction rule**：借放射学 conspicuity 框架派生无 mask 代理特征（全图 σ / GLCM / FFT 频谱熵 / CNR_proxy），given 一张新图、given 模型 anomaly score 后**仍能额外预测**该图 AD 成败（增量信息，非重命名「大病灶好检」）。**领证用 C4 risk-coverage 当 actionable rule**：按 conspicuity 代理（glcm_cluster_prom）排序、丢弃最不可信图像，保留集的 AD-AUROC 总体趋势升高（端点单调、中段有局部振荡，措辞用「overall increasing」勿写严格 monotonic）——**全集（coverage=1.0, n=2776）AD-AUROC=0.8228 → top-10%（coverage=0.10, retained_n=278）AD-AUROC=0.9119**（源 `results/incremental_C4_risk_coverage_glcm_cluster_prom.csv`，verifier 核 csv 原值）。这是一条临床可直接执行的规则：把可靠性最低的图像分流给人工复核，自动化部分的检测精度即抬升。**per-image 同图内机制，不依赖任何跨集 / 跨模态迁移。** | MedIAnomaly（incumbent）是 dataset-level 聚合 percentile-AUROC，结构上给不出「这张图上可不可信」的 instance 级 actionable rule；conspicuity 桥从未被嫁接到 DL AD 失败建模（最近邻 = 乳腺 GLCM reader-difficulty AUC=0.71，针对人读片非 DL AD） |
| **②（第二承重，novelty 点，写成诊断框架 / proposal）** | **病灶几何 a priori transferability diagnostic（iso 门）**：给一对（集，模态），跑前仅凭无标注病灶几何分布预判失败模式能否迁移。判据 = area-ratio 双侧守门（病灶占器官比例落 BraTS 自身 [P33,P67] 带内）+ n_components 单侧上界（多灶性 ≤ BraTS 自身 P75=3）。**只 claim 负向命中**：三个跨模态目标集（HAM 皮镜 / CBIS 乳腺 X 线 / IDRiD 眼底）被判据预言「几何不同构 → 失败模式不可搬」，实测一致。**铁律：本框架手上零正向锚（无任何对被预言可搬且实测搬成），故全文写成「诊断框架 / proposal」，绝不写成「已验证判据」、绝不暗示正向迁移已被验过。** | unsupervised performance estimation 家族（ATC / AutoEval / DISDE）用 confidence / dataset 统计量预测 model accuracy，无人用 **instance 病灶几何属性**当迁移可行性的前验输入；MedIAnomaly / Lagogiannis percentile 分层是描述性、无前验迁移诊断 |
| **③（地基，非 headline，退为支撑）** | **协变量化失败相图 / failure phase diagram**：用 BraTS 像素 mask 分层刻画 size × contrast × 多灶性 × 位置驱动的失败几何（含交互 / 非单调，非聚合 AUROC），framing 类比 Donoho-Jin 信号检测相图。**三档阈值敏感性（P85/P90/P95）坐实方向一致**（PC-A：T1 size / T2 contrast / T3 交互三档全 Holm 显著）。这是柱1 与柱2 的共同地基，但单卖易被归约成「Lagogiannis + ε」，故**退为支撑性地基，不当 headline**。 | MedIAnomaly 是聚合 benchmark（无协变量分层）；AE4AD 是 mismatch 存在性定理（不带协变量参数）——结构上无协变量维度 |

> **多方法 coverage（Phase 2）= 支撑章，不进 headline**：稀释 → 漏检失败几何跨 AE / VAE / MemAE 三方法全复现（PC-A 三档全显著、检出率单调同向），证明这是**重建式 AD 范式的共性而非 AE 特例**——这强化柱1 / 柱2 的普适性论证，但不另起一根承重柱。
>
> **三假设（只训正常够 / 重建误差=异常 / 正常误差<病理误差）= 分析工具，不是标题、不是卖点。** Intro 第一句必须是核心 RQ「何时失败、能否单图前判」，不能是「我们证伪三假设」（= AE4AD 实证延伸 = incremental 死法）。

## 四、与 incumbent / 邻近线的精确边界（防撞车红线）

**incumbent = MedIAnomaly（Cai 等，HKUST，MedIA 2025）**：30 方法 × 7 集的大规模 benchmark，**dataset-level 聚合 percentile-AUROC**，描述性指出三假设「does not always hold, still unresolved」，**无受控协变量分层、无 per-image actionable rule、无几何迁移诊断**，Section 5 自挂 open。
- **differentiation（一句话钉死）**：他们做 dataset-level 聚合可见性排序；**我们做 per-image actionable selective-prediction rule（risk-coverage）+ 病灶几何 a priori transferability 诊断——这是他们的聚合粒度结构上做不到的 instance 粒度。**

**incumbent 理论侧 = AE4AD（HKUST，MICCAI 2024）**：纯理论证伪假设②（重建目标 ≠ AD 目标 mismatch）+ constructive（latent 熵 + dim ≥ D/2），只打一条假设，无协变量参数、无 per-image、无迁移诊断。

**可 cite 的近邻 failure-mode 工作（positioning 用）**：
- **What Do AEs Learn About Anomalies?（MICCAI 2023）**：AE 在 AD 上学到什么 / 漏什么的分析，近邻 failure-mode 分析，引作 motivation。
- **Rethinking AEs for Medical AD（MICCAI 2024）**：理论 failure-mode 分析，引作邻近理论参照（与 AE4AD 同族）。
- **Comparative Benchmarking of Failure Detection（MedIA 2024）**：per-image failure detection benchmark，用 ensemble Dice 当 failure predictor。**正交点**：他们用模型自身的 ensemble 一致性 / Dice 当 predictor；**我们用图像本征 conspicuity 几何属性当 predictor，且额外给跨集迁移的前验诊断**——引作 per-image failure benchmark 的方法论参照 + baseline 对照。

**其余邻近但未占满（文献核实，留缝完整）**：
- **Lagogiannis TMI'24**：按 size / contrast percentile 分层报 AUROC = 定性 observation，无 per-image actionable rule、无迁移诊断、无 phase boundary。
- **Meissen eBioMedicine'24**：人口学 bias（sex/age/race）线性 fairness law，subgroup-level 非病灶理化协变量、非 per-image。
- **unsupervised performance estimation 家族**（须作 baseline 对照，非撞车）：ATC（ICCV'21）/ AutoEval（CVPR'21）/ DISDE（ICML'22）—— 用 confidence / dataset embedding 统计量预测 model accuracy。**正交点**：他们预测 model 软输出，我们用 instance 几何属性预测 per-image 失败 + 给跨集迁移前验诊断。
- **conspicuity**（AJR 1976 Kundel & Revesz 起）：放射学读片 signal-detection 框架，**从未迁移到 DL AD 失败建模**。conspicuity 文献本身即模态特异量 → **支撑我方柱2「迁移须几何同构」而非反对**。

**我们走正交轴**：per-image conspicuity actionable rule + 病灶几何迁移诊断 + dilution regime 的 benchmark 生态发现。**绝不**把卖点压在「证伪三假设」（AE4AD 地盘）、「刷 AUROC」、或「失败模式可外推 / 可迁移」（ICLR 命门，正臂填不出）。

## 五、目标会场 + 正臂落空的诚实处理

- **主投**：MICCAI / MedIA（capability / analysis，贴导师领域、算力低）。MICCAI 起步，若 held-out 正向锚日后补上可升级重投 ICLR/NeurIPS（见末）。
- **为何不冲 ICLR「可外推」headline**：ICLR analysis track 的命门是「失败模式**可外推 / 可迁移**」并有**正向锚 + held-out 盲测命中**。该正臂在开放 pixel-mask 数据上**结构性填不出**（04_LOG 终局决断核实）：
  - METS（BraTS-METS，同模态正臂主锚）卡在 Synapse BraTS 2026 Data Access Team 人工核验，无限期拿不到；
  - LGG（开放同模态候选）精确 skull-strip + anatomy 分母重算后 **iso=False**（落 band 下方，按已冻反事实自缚纪律不改门救）；
  - BraTS 跨中心 split 太 trivial（「只跨中心不算真外推」一击穿）。
- **正臂落空 → 写成贡献，不写成失败**：用本文铁律 framing——「开放数据系统性覆盖不到 dilution regime」本身是 **benchmark 生态发现**，并提供**前验诊断框架 + 三模态负向命中**作为「为什么跨集 AD 迁移这么脆」的**机制性解释**。**铁律：只 claim 负向命中（预言不可搬 → 实测真塌，HAM/CBIS/IDRiD 三模态满足），绝不暗示正向也验过。**

## 六、反跑偏红线（继承 + 退守后加固）

1. 主轴 = per-image actionable 判据（柱1）+ 病灶几何迁移诊断框架（柱2）+ dilution regime 生态发现；三假设只作工具，跑偏到「证伪三假设」立即停。
2. **headline / claim 绝不带「外推 / transfer / generalize」当主张**（退守后铁律，最高优先）：ICLR「可外推 PASS」命门正臂已实证填不出。全文 claim 限「per-image 可信度可判 + 跨集迁移可前验诊断（仅负向命中）+ 开放数据覆盖不到 dilution regime」。任何句子若暗示「我们的失败刻画能搬到新集 / 新模态并成功」= 跑偏，立即改。
3. **柱2「只 claim 负向命中」铁律（退守后新增，与铁律2 同级）**：iso 门写成「诊断框架 / proposal」，**绝不写成「已验证判据」**。手上零正向锚（无任何对被预言可搬且实测搬成）。**绝不暗示正向迁移已验过**——负臂三模态命中（预言失败 → 实测失败）是判据**有判别力的证据**，但不等于「判据已被双向验证」。措辞须显式区分「预言失败已兑现」与「预言成功未兑现（open）」。
4. **柱1 领证纪律**：per-image 承重**以 C4 risk-coverage 当 actionable rule 领证**（全集 0.8228 → top-10% 0.9119，csv 原值），**不以小 partial_r 领证**（n=1948 下 r≈0.1 量级会被攻「统计显著但实践存疑」）。引 per-image 相关处若用 partial_r，用 corrected 值（`results/c3_corrected/`，glcm_cluster_prom=0.3054 控 size+contrast，verifier 核）；主目录旧值 0.5044 是无条件相关 bug、frozen 保留供审计、禁用。
5. **数字纪律**（继承 + 退守特纠口径）：
   - 凡「1.3% 重叠」一律写全：「**HAM 落 BraTS P25 稀释 regime 的样本占比仅 1.3%（43/3310）**」。这与 **OVL=0.469（全分布中等重叠，退为连续趋势描述性证据，非二分门）** 严格区分——**绝不裸写「重叠 1.3%」**（与 OVL=0.469 并存会被当造假）。低尾占比门 + n_components 不相交（IDRiD n_comp OVL=0.001）领证 iso=False，**不以全分布 OVL 领证**。
   - 数字一律 Bash/Grep 核 csv，不信 Read；只用已核值或自核 csv 原值；拿不准标 `\todo{核 verifier}`。
   - **Holm 校正写 α=0.05/3**（family=3，非 /4）。
6. 理论命题（conspicuity 桥、iso 同构诊断）**先 reviewer/skeptic 裁再落「已证 / 已验证」**；柱2 在零正向锚下永远是「框架 / proposal」。
7. capability paper：非劣不是目标，**per-image 可操作 + 迁移可前验诊断**是目标；别滑回刷 AUROC。

## 七、审稿人预对峙（精简，退守版）

| 攻击 | 回应 |
|---|---|
| 「per-image 判据 = 把『大病灶好检』重命名」 | **C4 risk-coverage 兑现增量 actionable 价值**：given size+raw contrast 残差后 conspicuity 桥仍预测成败（三档一致），且按可靠性排序丢 bottom-k% 后 AD-AUROC 总体趋势升高（全集 0.8228 → top-10% 0.9119）。这是一条临床可执行的分流规则，非平凡重命名。（corrected C3 partial_r：glcm_cluster_prom=0.3054 控 size+contrast，verifier 核；领证仍不押 partial_r） |
| 「risk-coverage 抬升只是因为丢掉了大病灶（easy case）」 | 增量信息检验已控制 size + raw contrast 残差；conspicuity 桥在残差上仍有预测力（嵌套 LR / 偏相关三档一致），排序信号非 size 的同义改写。`[残差检验数值待 verifier 复核]` |
| 「你声称失败模式可迁移 / 可外推吗？」 | **明确不 claim。** 本文 claim 的是「跨集迁移可**前验诊断**」+「开放数据覆盖不到 dilution regime」。我们诚实报告：开放 pixel-mask 数据上无任何对被前验诊断为「可搬」且实测搬成（正向锚缺失，open）；有的是**负向命中**——三模态目标集（HAM 太大 / CBIS 太小 / IDRiD 太碎）被诊断框架预言不可搬、实测一致。这正是「为什么跨集 AD 迁移这么脆」的机制解释。 |
| 「你的 iso 诊断框架只有负例，没正例验证，凭什么叫判据」 | 我们**不叫它已验证判据，叫诊断框架 / proposal**（§六铁律3）。负向命中（预言失败 → 实测失败，三模态一致）证明它**有判别力**；正向锚需 held-out 几何同构对兑现，开放数据上结构性缺失（METS 卡核验 / LGG iso=False）。我们透明标 open，不冒充双向验证。这本身是诚实的 benchmark 生态发现，非判据缺陷。 |
| 「窄 niche 你就试了三个跨模态集 / n 太小」 | 不靠 n 靠**定量几何论证**：三模态病灶几何从三个不同维度（HAM 皮镜中位占画面 28%=太大 / CBIS 乳腺 X 线中位占器官 1%=太小 / IDRiD 眼底中位 136 微灶=太碎）都打不进 BraTS 的「少灶 + 中等占比」niche；HAM 落 BraTS P25 稀释 regime 的样本占比仅 1.3%（43/3310），IDRiD n_components 与 BraTS 几乎不相交（OVL=0.001）。这是分布论证非轶事。 |
| 「全分布 OVL=0.469 看着挺重叠，你凭什么说不同构」 | **全分布 OVL ≠ dilution regime 重叠**。OVL=0.469 是连续趋势的描述性证据（退为支撑、非二分门）；iso 判据领证用**低尾占比门**（HAM 仅 1.3% 落 BraTS≤P25 稀释 regime）+ n_components 不相交（IDRiD OVL=0.001）。我们严格区分「全分布中等重叠」与「稀释 regime 几乎不重叠」，并显式同时报两个数防止 cherry-pick 质疑。 |
| 「AE4AD 已证伪假设②，你 = 实证延伸 incremental」 | 主轴是 per-image actionable rule + 病灶几何迁移诊断 + dilution 生态发现（AE4AD 定理不带协变量参数、无 per-image、无迁移诊断，结构上给不出）；三假设只是工具。 |
| 「MedIAnomaly 已 benchmark 30 方法」 | 那是 dataset-level 聚合 percentile-AUROC；我们做 **instance 级 actionable selective-prediction rule + 跨集迁移前验诊断**，是他们聚合粒度结构上做不到的层次，且我们用三方法（AE/VAE/MemAE）证 dilution 几何是范式共性。 |
| 「失败相图 novelty thin / 像 benchmark+ε」 | 相图是**地基非 headline**；承重是 per-image actionable rule（柱1）+ 迁移诊断框架（柱2）。相图三档敏感性（P85/P90/P95）坐实、含交互 / 非单调，framing 有 Donoho-Jin 先例。 |
| 「conspicuity 是老概念」 | 概念老，但**首次**把放射学 conspicuity 嫁接到 DL AD 失败建模做 per-image reliability + selective prediction，跨框架桥非旧概念复用。 |
| 「这是不是为某次失败事后倒推（HARKing）」 | 时间线诚实切分：三模态负臂的 iso 门**结构上无参守门承重**（band 宽度 ±33% 对四集 verdict 零影响，skeptic 实算坐实），HARKing「band 事后收窄救 verdict」残口被架空；柱2 全程只 claim 负向命中、透明标正向锚 open，不存在「事后改判为成功」。reframe 产生于实测之后但清白靠**结构（无参守门 + band 不承重 + 零候选依赖）非时序**，已留痕。 |
