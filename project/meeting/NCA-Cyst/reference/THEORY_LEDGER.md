# NCA-Cyst — THEORY LEDGER（假设链冻结，防 HARKing）

> 冻结方法创新的地基假设 + 证据分档（定理/实测/待验/文献空白）。动创新模块前 git commit 冻结本文。
> 证据分档：🟢实测(本项目数据) ｜ 📄文献 ｜ 🟡假设待验 ｜ 🔴文献空白/未证。

---

## H1 — 「多尺度下采样抹掉散布小囊肿」是 M3D-NCA 结构性缝

**陈述**：M3D-NCA 的全局上下文只来自最粗分辨率级（下采样换感受野）；散布的小囊肿在下采样时被几何抹掉，故该级获得全局上下文时几乎看不见囊肿。

**证据**：
- 🟢 **实测（2026-07-08，`06_experiments/downsample_survival.csv`，248 含囊肿 case，官方 rescale3d 同法 INTER_NEAREST 重采样）**：
  - 粗级 (64,64,32)：**9.7% 囊肿完全抹没，中位囊肿存活 0.4% 体素**。
  - 细级 (128,128,64)：1.2% 抹没，中位存活 3.5%。
- 📄 KiTS 官方：cyst 三类最难 Dice 0.447；根因含小病灶+类不平衡（springer 978-3-031-54806-2_21）。
- 📄 小病灶+全局分布让局部感受野模型失效（arXiv 2502.08675 散布小病灶全局补偿有效）。

**两级数据流（🟢 已核实 `Agent_M3D_NCA.get_outputs` L151-229，2026-07-08）**：
- **粗级 (m=0)**：在下采样**整卷**跑 NCA → 有全局视野，但囊肿几何抹掉（实测 (64,64,32) 9.7% 抹没/中位存活 0.4%）。
- **细级 (m=1=train_model)**：在**随机 patch** 跑（L204-209 `random.randint`+立即 `break`，**agent 层不做 mask 优先采样**）。囊肿仅占 ~0.0065% 体素 → 随机 (128,128,64) patch 几乎抽不到囊肿；且 patch 间无全局通道。
- **→ 「两难」代码坐实**：无一级同时具备「全局视野 + 看得见囊肿」。粗级有全局无囊肿；细级有分辨率但(a)随机 patch 抽不到囊肿(b)无全局。这正是全局池化 broadcast(H2)要补的缝。

**推论（故事逻辑）**：
- 🟡 vanilla M3D-NCA baseline 在囊肿上大概率也失败——**不矛盾，是动机**：baseline 证「UNet + 原版 NCA 都做不了囊肿」，博士生说的「我们能跑」=NCA+全局视野(Phase2)，非 vanilla。低 baseline 分数=创新动机（写 STORY 须讲清这层，别让审稿人误读成「你自己的 NCA 也不行」）。
- 🟡 下采样几何抹掉 + 随机 patch 抽不到 ≠ 训练必然失败的完整因果（类不平衡也贡献）；Phase1b 训练结果佐证。

**档位**：🟢 机制(几何抹掉 + 随机patch漏采)代码+数据双实测成立 ｜🟡 「这导致 M3D-NCA 囊肿分割失败」= 待 Phase1b 训练结果佐证。

---

## H2 — 全局池化 broadcast 能补这条缝（核心创新假设，下阶段）

**陈述**：给 NCA 每步加「全图 hidden state 池化→小 MLP→广播回每个 cell」的全局通道，让每个 cell 在**不下采样**的前提下获得全局上下文（散布囊肿的分布先验），补 H1 的缝。

**证据**：
- 🔴 **文献空白**：多源检索未命中「显式全局池化场耦进 NCA 分割 + 针对散布小目标」直接前作（既是机会，也**不能 claim 已被证明**）。
- 📄 可借鉴 GNN virtual node 聚合+广播近似 attention 线性复杂度（PMC12920779）。
- 🟡 待验：轻量全局池化能否在保 NCA「任意分辨率+~13k 参数」下显著拉起囊肿 Dice——**本项目要用实验填的核心 claim**。

**档位**：🔴 未验（创新模块下阶段立项 + 红队 + 实验，禁越级卖）。

> **🔴 2026-07-10 双红队独立判定（Phase2 立项前，skeptic + theorist 正交，各自收敛到同一结论）**：H2 **存疑，不 greenlight，先跑 2×2 kill-shot**。
> - **命门=因果混淆（两队一致砸中同一处）**：baseline 囊肿≈0 更 Occam 的解释是**极端类不平衡（65/百万体素）**这个一阶主因，而非「缺全局视野」。**关键反证=M3D-NCA 粗级(m=0)本就在整卷跑、有全局视野，囊肿照样≈0** → H1 机制真但**不足以推出 H2**。
> - **theorist 理论刀**：6.5e-5 前景比下标准 Dice/focal loss 平凡解（全背景）吸引盆极深 → 类不平衡是**一阶** killer、全局视野至多**二阶**；H2a（全局视野瓶颈）vs H2b（不平衡瓶颈）**当前数据理论不可分**。信息论侧：囊肿解剖散布 → 全局先验对定位约束弱，I(全局;囊肿mask|局部patch) 可能可忽略（与「全局视野治囊肿」卖点直接张力）。
> - **skeptic 补两刀**：①novelty 可能撞车（Backbone-NCA / global-pooling NCA 变体或已存在，立项前须查空白真伪）；②尺度失配（全局池化 broadcast 可能**稀释**定位 65/百万小目标所需的局部信号）。
> - **kill-shot（立项前必跑，~15-20 GPU·h）**：2×2 = ±全局视野 × ±类平衡（加权 Dice/focal/前景优先采样）。关键格=**「+类平衡 / −全局视野」**：若单加类平衡就把 vanilla NCA 囊肿 Dice 拉到 ~0.1-0.3，则 H2 地基塌一半，Phase2 须转向（如改成散布小目标类不平衡分割 benchmark）。
> - **置信更新**：低 → **低（且已识别一阶混淆变量，不先控就是押错 claim 形状）**。呼应 [[feedback_falsify_crux_first]] + [[feedback_claim_shape_decides_birth_difficulty]] + [[feedback_benchmark_is_optimal_strategy]]。

---

## H3 — 「主流模型囊肿近随机」在多类小散布设定成立

**陈述**：见 `01_STORY` 措辞红线。
- 📄 多类 KiTS23 cyst Dice 0.17–0.45（近随机）｜⚠️ 二分类 ADPKD nnUNet 0.82–0.90（不随机）。
- 🟡 本项目 Phase1c 自跑 UNet3D 同口径复现（待结果）。

---

## H4 — 【方向转向·2026-07-11 用户拍板立项】3D 多尺度 NCA 不确定性 × 囊肿极端难场景

> **背景**：Phase1 baseline 全 PASS 后，方向 A（全局视野治囊肿）双红队命门存疑（囊肿≈0 一阶主因是极端类不平衡非缺全局，b 格 kill-shot 在跑验证）。学长提示「NCA 天然带不确定性可解释、没人做」。三 researcher 并行侦察后，用户拍板：**Phase2 headline 从 A（分割）转向 C（不确定性/可解释）**，在 NCA-Cyst 内做（复用数据/M3D-NCA 骨干/baseline/b 格模型），不开新项目。

**Headline（v1 定稿）**：在 KiTS23 肾囊肿这种主流模型都做不好（Dice 天花板 0.447、多类小散布近随机）的极端类不平衡场景下，利用 3D 多尺度 M3D-NCA 的迭代随机动力学，给出**校准良好、空间可解释的预测不确定性**，把「模型看不清囊肿」从失败转化为可用的临床信号（不确定性引导的漏检定位 / 质量控制 / 转诊）。

**措辞红线（承 01_STORY，写作/立项必守）**：
- 🔴 卖点是**不确定性/可解释**，**不是「分割赢过别人」**。绝不 claim「囊肿别人做不了我们能做」——KiTS23 天花板 0.447、二分类 nnUNet 0.82-0.90，笼统吹一击破，且 b 格未验（[[feedback_falsify_crux_first]] [[feedback_claim_shape_decides_birth_difficulty]]）。
- 🔴 不追 Dice SOTA（追不动），追不确定性的**校准 + 决策价值**。

**证据分档（三 researcher 2026-07-11，全带 URL）**：
- 🟢 **机制真（代码实证）**：`Model_BasicNCA3D.py:69-71` 每步 `stochastic=torch.rand()>fire_rate` 随机激活 mask（fire_rate=0.5），推理 `torch.no_grad()` 下仍开、无 dropout → 同图多 rollout 天然出多份输出，零架构改动。
- 🔴 **核心机制已被占（非蓝海，但≠不能做）**：① base model M3D-NCA 自带 NQM=N=10 随机预测 std 质量指标（arxiv 2309.02954）；② **MICCAI 2026 已接收** Sadafi et al. resilience（arxiv 2605.26726，github.com/marrlab/resilience）专做「NCA 分割不确定性、不改架构不重训」，系统对比 6 信号。**「没人做」被证伪。**
- 🟢 **delta 合法且清楚（这是可立项的支点）**：resilience/竞品全是 **2D、通用 NCA、自然/内镜/病理图**——**没碰 3D、M3D-NCA 多尺度骨干、KiTS、囊肿、极端类不平衡**。我们的贡献单元 = 首次在 3D 多尺度 NCA + 极端稀疏小目标上刻画不确定性，且可联动 H1（囊肿在粗级被下采样抹掉时，粗/细级不确定性怎么表现——竞品结构上碰不到）。
- 🟡 **技术风险（与撞车无关，纯可行性，须最先 pilot 证伪）**：vanilla fire-rate 多 rollout 的方差在囊肿区**可能太弱**（NCA 收敛到稳定 attractor，末态对 fire-rate 抖动不敏感）。佐证=竞品没用 vanilla rollout、而提出显式扰动 resilience 且打赢了「靠迭代自带随机」的信号。→ **动笔前必跑零成本 pilot**：b 格模型训完，同图 N=10 rollout 算体素方差，看囊肿区有无信号。有信号→直接用；弱→加显式扰动/多尺度聚合机制（又一方法贡献点，无论强弱都有论文）。

**评测协议（不刷 Dice 怎么证不确定性有用，researcher 查得标准）**：AURC（风险-覆盖，唯一同抓性能+置信排序）、ΔDice@90（选择性 Dice）、ECE/校准曲线、failure/OOD detection AUROC/AUPRC（AUPRC 类不平衡下最有信息）、retention/sparsification 曲线。

**venue**：MICCAI UNSURE workshop（明确吃此 framing、不要 Dice SOTA、接受率 65-71%）/ ACCV / MIDL / MELBA。博士生+导师最终定。⚠️ 审稿圈与 resilience 高度重叠，投稿须明确对标讲清 delta。

**档位**：🟡 立项已拍板（用户 2026-07-11）；核心机制被占已知并接受（走 delta 路线）；技术命门=vanilla rollout 信号强度，**pilot 最先证伪**（呼应命门最先证伪纪律）。

### 🔴 立项前提红队补丁（skeptic 2026-07-11，pilot 花大算力/动笔前 must-fix）

**更深的致命命门（比 vanilla σ 强弱更根本）**：baseline 囊肿 Dice≈0（A2=5.3e-6）是**近零召回**模型 = 把囊肿当背景处理、无囊肿表征。→ ① 评测协议退化：AURC/selective-Dice 无真阳性可排序、ECE 被 99.9935% 背景体素主导成「完美校准」假象；② **方差非囊肿特异**：无囊肿表征的模型，其 rollout 分歧反映通用纹理/边缘/强度梯度，**不是囊肿位置** → 「不确定性引导漏检定位」可能定位到边缘而非漏检囊肿。联网证：所有成熟「UQ 引导小病灶检出」（Nair MS lesion MedIA'20）+ resilience benchmark 全在**部分召回**区制，无人在零召回上跑过 UQ（既空白也雷）。

**出路 = A 的墓碑 = C 的地基（同一个 b 格实验，相反解读）**：
- **预注册绑定**：方向 C 显式挂在「b 格 CB-max 能把囊肿 Dice 拉离 0（部分召回）」上。b 格对方向 A 是**杀死信号**（CB-max 单独拉起 Dice≥0.10 → 类不平衡一阶主因 → A 死）；对方向 C 是**赋能信号**（给一个部分召回模型，让不确定性有实质可谈）。
- **🔴 stop 条件（预注册）**：若 b 格 CB-max 仍 Dice≈0（拉不动，全 seed <~0.05）→ 方向 C **无底物**（多尺度发现 + UQ 故事同时失去实质）→ **预定义 stop，不硬做**。→ 此时 A 与 C 同时失去实质，Phase2 须整体重估（停下报拍板）。

**扩充 pilot 判据（从「有方差」升到三条同时过，替换旧 RQ1 判据）**：
1. 方差图对**漏检囊肿**的 failure-detection AUPRC **显著高于强度/边缘 baseline**（证方差是囊肿特异，非通用纹理）；
2. 选定模型上 AURC/selective-Dice **非退化**（有足够真阳性可排序）；
3. 至少一个校准指标在**囊肿正体素子集**上有定义（别让背景稀释）。

**其他修（🟠 立项更稳）**：
- **delta 承重必须是「多尺度特有的不确定性发现」**（囊肿在粗级被抹掉时：粗级是否「自信地错」=低不确定 vs 细级高不确定，2D 单尺度竞品结构上产生不了），写进 headline，别只 claim「3D NCA 也有 UQ 信号」（=注水增量，好审稿人一句「2D 方法跑个 3D」打掉）。此发现同样依赖部分召回 → 命根仍在上面 stop 条件。
- **baseline 必须对照标准 UQ（MC-dropout / deep-ensemble / TTA）在同一 KiTS 囊肿上**，不只对 resilience。真优势 = 「零成本多 rollout 不改架构不重训 + 首次测极端不平衡近零召回区制」，**不是 NCA 骨干本身**（那是注水）。→ researcher 待核「KiTS/肾囊肿 MC-dropout UQ」空白真伪。deep-ensemble 用已有 3 seed 免费。
- **摆成 B 族 benchmark 形状**（claim setting + 多尺度发现 + 多尺度 UQ 聚合，**别 claim 方法 novelty**）→ 解「vanilla 弱 vs 撞 resilience 方法」两难（[[feedback_benchmark_is_optimal_strategy]]）。venue UNSURE workshop 吃 benchmark framing。
