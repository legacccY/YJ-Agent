# MedAD-FailMap — STORY FRAMEWORK

> 项目核心叙事 + 贡献边界 + 反跑偏。任务与本文冲突 → 停下澄清，不照描述硬干。
> **2026-06-17 重铸（headline 路径 A，用户拍板 + 5-agent 文献/红队收敛）**：旧 headline「失败可外推函数 / 对任意新图像 predict」被自家 G1-a 实证（BraTS→HAM 几何不同构）字面证伪，是 claim 辖域写错（非科学做错）。新 headline 把跨模态负诊断从「事故」翻身成贡献——见 §一。
> **2026-06-17 二次收窄（reframe A'，用户拍板 + skeptic 0 致命放行）**：跨模态正臂在免费 pixel-mask 数据集**结构性枯竭**（HAM 28% 太大 / CBIS mass 1% 太小，verifier 坐实 OVL=0.26 / IDRiD 真异常微小多灶，三模态从两端都打不进 BraTS 脑组织 ~10% 的窄 niche）。**正向「可外推」claim 收窄为同模态示范（BraTS→METS），跨模态一律落「可前验失败」负臂——headline 禁 claim 任何跨模态正向外推**（写作铁律，见 §六）。同时把「病灶几何天然双峰、稀释失败 regime 落两峰间稀疏窄带」抬成**第二 headline（负发现，不依赖 METS 是否 PASS，抗风险）**，见 §一末。修订记录见文件尾。

## 一、核心 RQ（一句话）

**重建式医学异常检测的失败何时可预测、何时可外推——这个「能不能外推」能否在跑之前判定？**

失败由 conspicuity / 几何机制驱动（小病灶淹大背景 → 整图重建误差被稀释 → 漏检）。这个失败**在协变量空间里可系统刻画、可预测**；失败边界**可零调参外推——但有条件：当且仅当源集与目标集的几何 regime 同构**。关键是，**这个「能不能外推」本身在跑外推前就能从无标注数据前验**（病灶/背景面积比分布重叠诊断）。本文**正向只示范几何匹配时外推成立（同模态 BraTS→METS，脑 MRI 内）**；跨模态对（皮镜/X 线/眼底）经实证几何系统性不匹配，落「前验判据正确预言其外推失败」的负臂。**核心卖点不是「外推 work」这个结果，是「给一个新（集,模态）对，跑之前就能 predict 失败边界搬不搬得过去」这个判据的预言性**（同模态预言 work→实测 work；跨模态预言 fail→实测 fail；Gate2 held-out 盲测命中是终验，见 ACCEPTANCE）。

由此「小病灶普遍难检」这个隐含共识被精确化为**几何 regime 特异**的现象——不是普适规律，跨几何 regime 不迁移，且何时迁移 / 何时不迁移**可操作判定**。

**第二 headline（负发现，A'，独立成立不依赖 METS）**：医学异常的病灶几何**天然双峰**——弥漫病变占画面主体（如皮镜皮损中位 28%）vs 点状病变近亚像素（如 mammo mass 中位占乳腺 1%、眼底 MA <0.15%）。recon-AD 的 conspicuity 稀释失败 regime（病灶占器官 ~5-16%，BraTS 脑瘤所在）恰落在**两峰之间的稀疏窄带**，多数真实医学模态的病灶几何不落此带。**这从机制上解释了为什么跨数据集/跨模态 AD 失败迁移如此脆**——不是方法不好，是失败几何本身被一个窄 niche 锁定。证据 = 三模态（脑瘤/皮镜/X 线[+眼底]）面积比并排分布的定量论证，非轶事。

## 二、为什么这是 capability paper 而非刷 SOTA

不打「我的 AD 方法 AUROC 更高」。打三件 incumbent 给不出的事：(1) recon-AD 失败在协变量空间的**系统几何**（带交互、非单变量）；(2) **per-image 可靠性判据**（给一张新图 predict 该方法在它上靠不靠谱）；(3) **外推有效性判据**（给一个新数据集/新模态，在跑之前 predict 失败边界能不能零调参迁移过去）。贡献是 insight + 可操作判据，不是新方法——所以「标准做法配足数据也能做」反驳不到点（我们刻画的正是标准做法的边界 + 边界何时可搬）。

## 三、三大贡献（按承重排序）

| # | 贡献 | 为何 incumbent 给不出 |
|---|---|---|
| **①（真承重，全文最干净钩子）** | **conspicuity 桥 → per-image 可靠性判据**：借放射学 conspicuity 框架（lesion contrast / background complexity）派生无 mask 代理特征（全图 σ / GLCM / FFT 频谱熵 / CNR_proxy），given 一张新图、given 模型 anomaly score 后**仍能额外预测**该图 AD 成败（增量信息，非重命名「大病灶好检」）。**per-image 同图内机制，不依赖跨模态外推**。 | AE4AD 存在性定理给不出「这张图上可不可信」；conspicuity 桥从没人嫁接到 DL AD 失败建模（文献核实空白，最近邻=乳腺 GLCM reader-difficulty AUC=0.71，针对人读片非 DL AD） |
| **②（承重，novelty 翻身点）** | **外推有效性前验判据**：失败边界 fit 在 A，零调参 predict held-out B——**搬不搬得过去在跑前就能从无标注数据前验**（面积比分布重叠 → 几何 regime 同构 → 可外推；不重叠 → 不可外推）。**承重在判据的预言性，非「外推 work」这个结果**：正向命中（同模态 BraTS→METS 预言 work→实测 work）+ 负向命中（跨模态 HAM 28%/CBIS 1% 预言 fail→实测 fail，verifier 坐实 OVL=0.26）+ **Gate2 held-out 盲测对**（判据参数没碰过的对，先预言后跑、看命中）= ICLR 终验命门。**正向 claim 严格限同模态示范，不 claim 任何跨模态正向外推**（跨模态正例经实证几何枯竭，留 open）。 | unsupervised performance estimation（ATC/AutoEval/DISDE）全用 confidence / dataset 统计量预测 model accuracy，**无人用 instance 几何属性当失败函数输入 + 无人给「外推何时有效」的前验门**；Lagogiannis percentile 分层是描述性、无外推、无前验判据 |
| **③（地基，非 headline）** | **协变量化失败相图 / failure phase diagram**：受控操纵 size×contrast×纹理×位置 + 正常集多样性，画带边界线的失败相图（含交互/非单调，非聚合 AUROC）。framing 类比 Donoho-Jin 信号检测相图（easy/hard/impossible 三区）。 | MedIAnomaly 是聚合 benchmark（无协变量分层）；AE4AD 是 mismatch 存在性定理（不带协变量参数）——结构上无协变量维度。但单卖相图易被归约成 Lagogiannis+ε，故作地基不作 headline |

> **多方法对比（旧③）= 退为 Phase 1+ 补充章，不进 headline**：Phase 0 只跑 AE，VAE/MemAE/RD 未动，当前零实证。补足后作 coverage 加强，不作承重柱。
>
> **三假设（只训正常够 / 重建误差=异常 / 正常误差<病理误差）= 分析工具，不是标题、不是卖点。** Intro 第一句必须是「失败何时可预测、何时可外推」，不能是「我们证伪三假设」（= AE4AD 实证延伸 = incremental 死法）。

## 四、与 incumbent / 邻近线的精确边界（防撞车红线）

**incumbent = HKUST Cai/Chen/Cheng**（这块地的 dominant group）：
- **MedIAnomaly**（MedIA'25）：7 集 30 方法 benchmark，描述性指出三假设「does not always hold, still unresolved」，**无受控协变量分层**，Section 5 自挂 open。
- **AE4AD**（MICCAI'24）：纯理论证伪假设②（重建目标≠AD 目标 mismatch）+ constructive（latent 熵 + dim≥D/2），只打一条假设，无协变量参数。HKUST 主页 2025-2026 无后续 follow-up（抢发风险当前低）。

**邻近但未占满（文献核实，留缝完整）**：
- **Lagogiannis TMI'24 / 2512.01534**：按 size/contrast **percentile 分层报 AUROC** = 定性 observation，**非 failure-as-function、不可外推、无 phase boundary、无 per-image 判据、无外推前验**。
- **Meissen eBioMedicine'24**：**人口学** bias（sex/age/race vs 训练集比例）线性 fairness law，subgroup-level 非病灶理化协变量、非 per-image。
- **unsupervised performance estimation 家族**（须作 baseline 对照，非撞车）：ATC（ICCV'21）/ AutoEval（CVPR'21）/ DISDE（ICML'22）—— 用 confidence / dataset embedding 统计量预测 model accuracy。**正交点**：他们预测 model 软输出，我们用 instance 几何属性预测 method-level 失败 regime + 给外推有效性前验门。AutoEval 的 meta-regression 是我们外推方法最近邻，引作 methodology 参照 + baseline。
- **Bouman & Heskes 2501.13864**（ICLR'25 撤稿）：线性 AE 可完美重建 OOD 点的纯理论，非医学无协变量，邻近正交。
- **conspicuity**（AJR 1976 Kundel & Revesz 起）：放射学读片 signal-detection 框架，**从未迁移到 DL AD 失败建模**。conspicuity 文献本身即模态特异量（MRI vs CT 临床差异有据）→ **支撑我方「外推须 regime 同构」而非反对**。

**我们走正交轴**：协变量失败几何 + per-image 判据 + 外推有效性前验。**绝不**把卖点压在「证伪三假设」（AE4AD 地盘）或「刷 AUROC」。

## 五、目标会场

- **主投**：ICLR / NeurIPS（analysis / capability / rethinking track）。先例结构：MediConfusion ICLR'25（逆向 benchmark 触发失败）、What Makes a Good Diffusion Planner ICLR'25 spotlight（大规模消融→反直觉 actionable rule）、OpenMIBOOD CVPR'25（跨方法普适失败量化）。**接收要点**：actionable rule（我们=外推有效性判据）+ 反直觉发现（小病灶难检非普适=几何特异）+ 机制解释（conspicuity 稀释）+ 足够 coverage。
- **退路**：MICCAI / MedIA（贴导师领域、算力低，受控失败现象学仍可发，不白做）。负结果向（机制模态特异）作 ICBINB/ML4H 兜底，非主投。

## 六、反跑偏红线

1. 主轴永远 = 失败几何 + 可预测 + **可外推有效性判据**；三假设只作工具，跑偏到「证伪三假设」立即停。
2. **headline 辖域铁律**（防 🔴-1 复发 + reframe A' 铁律3'）：「可外推」永远带「regime 同构条件 + 可前验」限定词，**绝不裸卖「对任意新图像/任意模态可外推」**（已被 G1-a 自证伪）。**且正向「可外推」claim 严格限同模态示范（BraTS→METS），headline / 正文禁出现任何「跨模态正向外推 work」的暗示**——跨模态正例经实证几何枯竭（HAM/CBIS/IDRiD 全 iso=False），手上零跨模态 iso=True 正例，暗示跨模态能 work = 偷偷松掉「跨模态」三字 = 移动球门。跨模态一律落「前验判据正确预言其失败」负臂。
3. 数字一律 Bash/Grep 核 csv 不信 Read；超参查官方源查不到标 TODO；复现零偏离。
4. 理论命题（conspicuity 桥、外推有效性判据、regime 同构充要性）**先 reviewer/skeptic 裁再落「已证」**。
5. capability paper：非劣不是目标，**可预测/可外推有效性/可操作**是目标；别滑回刷 AUROC。
6. 抢发风险（HKUST 扩 AE4AD）→ 紧凑、早 arXiv 占坑、守正交轴。
7. **negative-result 不当主轴**：跨模态不同构是 ② 判据的**正面支撑**（吸收进正向 headline），不 pivot 成纯负结果论文（n 不足、易被打「换皮」）。

## 七、审稿人预对峙（精简）

| 攻击 | 回应 |
|---|---|
| 「你声称可外推，但唯一跨模态实验（BraTS→HAM）显示失败机制模态特异、外推前提不成立——claim 自相矛盾」 | **这正是贡献②**：我们不裸卖普适可外推，卖「可外推**当且仅当 regime 同构** + 同构性可前验」。G1-a 的 1.3% 重叠负诊断是判据**正确预言**「这对该外推失败」的证据，非反例。判据在跑前就分诊了「哪对能搬、哪对不能搬」 |
| 「AE4AD 已证伪假设②，你=实证延伸 incremental」 | 主轴是协变量失败几何 + per-image 判据 + 外推有效性前验（AE4AD 定理不带协变量参数，结构上给不出）；三假设只是工具 |
| 「benchmark 已观察到小病灶难检」 | 那是聚合 percentile 观察（Lagogiannis），不可外推、无 per-image、无前验；我们建可外推函数 + 给「何时可外推」判据 + held-out 验证命中 |
| 「per-image 判据 = 把『大病灶好检』重命名」 | PC-C 已坐实**增量信息**：given size+raw contrast 残差后 conspicuity 桥仍 Holm 显著预测成败（C2/C3 三档一致），非平凡重命名 |
| 「unsupervised perf estimation（ATC/AutoEval）已做性能预测」 | 他们用 confidence/dataset 统计量预测 model accuracy，无 instance 几何输入、无「外推何时有效」前验门；我们正交且引作 baseline 对照 |
| 「失败相图 novelty thin / 像 benchmark+ε」 | 相图是地基非 headline；承重是 per-image 判据 + 外推有效性判据，incumbent 结构上给不出。framing 有 Donoho-Jin 高分量先例 |
| 「conspicuity 是老概念」 | 概念老，但**首次**嫁接放射学 conspicuity 到 DL AD 失败建模做 per-image reliability，跨框架桥非旧概念复用 |
| 「你的正臂是同模态（BraTS→METS），同模态外推 work 是 trivial baseline 不是发现」（skeptic 🟠-2，最可能打穿点） | 承重不在「同模态 work」这个结果，在**判据预言性**：同模态 work 只是「前验门正向命中」的一个数据点；headline 是「给新（集,模态）对跑前 predict 失败边界搬不搬得过」。trivial 攻击靠 **Gate2 held-out 盲测命中**破（判据参数没碰过的对，先预言后跑）——无 held-out 命中则确会被打 trivial，故 held-out 是 ICLR 命门非可选 |
| 「跨模态外推呢？你只 claim 同模态」 | 跨模态正例经实证几何系统性枯竭（HAM 太大/CBIS 太小/IDRiD 微小多灶），这本身是**第二 headline 的负发现**（病灶几何双峰、稀释 regime 窄 niche）；我们诚实不 claim 跨模态正向外推，但给出**前验判据正确预言每个跨模态对会失败** + 机制解释「为什么跨模态迁移脆」 |
| 「窄 niche 你就试了俩跨模态集」（skeptic 🟠-3） | 不靠 n 靠定量几何论证：三模态（脑瘤 10.5%/皮镜 28%/X 线 1%[+眼底 MA]）面积比并排分布图显示 BraTS 的 5-16% 窗口被两侧从相反端夹住、医学病灶几何天然双峰中间稀疏；这是分布论证非轶事。IDRiD 实跑补第三独立模态 |
| 「正臂全押 METS 一个对，太脆」 | 诚实残差：METS 受阻则 fallback = BraTS 跨中心 train/test split（退化同模态对照，06 §3 预登记备胎）；且第二 headline 负发现不依赖 METS PASS，抗单点风险 |
| 「只 2 模态，不能 generalize」 | Coverage 加强（Phase 1+ 补 ≥3 集 + 多方法 ③）+ 外推有效性判据本身**不靠模态数撑普适**，靠「前验门正确预言每对能否外推」撑——judging 的是判据准不准，非堆模态。**注**：「判据准不准」须由 Gate2 的 held-out 盲测对兑现（判据参数没碰过的对预言命中），Gate1 的 1+1 双臂只解锁外推腿、不算判据已验 |
| 「判据是为给 BraTS→HAM 那次失败圆场而事后倒推的吗（HARKing）」 | 时间线诚实切分：HAM 是**激发判据的发现性观察**（motivating，不计判据证据，如训练集不算测试精度）；判据的**检验**在 Gate2 的 held-out 盲测对（判据参数从未碰过、先预言后跑）。「激发判据的对」与「检验判据的对」严格分离 → HARKing 攻击破 |
