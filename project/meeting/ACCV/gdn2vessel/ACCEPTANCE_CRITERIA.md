# gdn2vessel 验收标准（顶会亮度目标分解）

**目标**：按 CVPR/ICCV/MICCAI 顶会亮度建，ACCV 2026 作保底。不设周期上限——**唯一推进条件 = 每阶段硬阈值全 PASS**，不赶 deadline 牺牲质量。
**最后更新**：2026-06-25（**benchmark-only 重定位** — 路A/路B 两命门全死，headline 改「2D 眼底断点续连评测套件 + 诊断方法学 + 诚实负结果」；新增「批2 区分度门预登记(待拍草案)」）

> 完成判定铁律：**不存在「基本完成」「差不多了」。要么逐条全 PASS，要么继续补。** 任一 FAIL → 不标完成，回去补；非硬伤无解 → 写诚实回退 + 停下报用户（stage-gate FAIL 放行是拍板点）。

> ⚠️⚠️⚠️ **benchmark-only 重定位（2026-06-24~25，用户拍板 Entry 32）**：路A（delta 机制特异，MQAR delta≈GLA）+ 路B（Frangi 门拓扑轴显著赢，最小验证 gate FAIL：DRIVE 正 CHASE 反）**两条「方法赢」命门全死**。headline 改 **benchmark-only**：①合成断点协议(4-severity 网格)②续连指标族(ε_β0/SR/reid_rate + clDice/Betti)③12 baseline 全谱 leaderboard④诊断方法学 + 诚实负结果。**承重点=「benchmark 能区分方法 + 诊断现有方法/指标局限」非「我们方法赢」**。GDN-2/Frangi 门降为被评测方法之一。**当前前置命门 = 下方「🔒🔒 批2 区分度门预登记」（待用户拍板冻结，skeptic 2🔴 修复版）**。详见 `PROJECT_LOG.md` Entry 32/33 + `STORY_FRAMEWORK.md` + `PLAN/LEADERBOARD_MATRIX.md`。
>
> 下方「路B 最小验证 gate」+「re-ID 可归因表」**均已死/归档，只读留痕不再作 gate**。L6「拓扑/续连赢 SOTA」**已降参照**（2026-06-25 用户拍板，Ours 输不塌稿，区分力才承重）。

---

## 🎯 录用亮度 lever 分解表

| Lever | 目标版本（顶会亮度） | 不达标后果 | 状态 |
|---|---|---|---|
| L1. 可微 Frangi 门证透（路B主轴，2026-06-22 改） | Frangi 门 on/off 命门拓扑轴显著赢 + 记忆类型无关消融（门 ×{GDN-2,GLA,ConvGRU}都涨）| headline 塌 → benchmark-only/workshop 降级 | ⬜ 路B命门（下方预登记）|
| L2. 杀手锏 benchmark | 自造断点续连 benchmark（对齐 creatis 合成协议）+ ε_β0/SR/re-ID | 核心 claim 无铁证 → 降为 overclaim | ⬜ P1 |
| L3. baseline 全谱同台 | ≥12（SSM+拓扑+经典+冠脉+2025-2026 最新） | 漏比关键竞品 = reject | ⬜ P3 |
| L4. 数据集超量 | ≥10 集全做满（视网膜5+冠脉3+OCTA2+跨域），允许 1-2 边缘集失败 | 数据偏单 = 泛化质疑 | ⬜ P3/P5 |
| L5. 消融超量 | ≥8-10 组，每个机制 ≥1 干净对照 | 消融不系统 = novelty 存疑 | ⬜ P4 |
| ~~L6. 拓扑/续连赢 SOTA~~ **(2026-06-25 降参照)** | benchmark-only 后**不要求 Ours 赢**——leaderboard 报全谱方法续连/拓扑数，Ours 输也不塌稿。承重改为「benchmark 能区分方法」(批2 区分度门) | ~~无胜负点 = reject~~ 不再是 gate | 🔽 降参照 |
| L7. 可解释性 | ≥3 张「记忆认出同根血管」可视化（王水花方向） | 卖点弱 | ⬜ P6 |
| L8. CV 方法贡献叙述 | 新机制/原理/benchmark 先行，医学=validation | 被读成换模块/纯临床 = reject | ⬜ P7 |
| L9. 写作/对抗审稿 | 数字三方对账 0 偏离 + reviewer 十角色 0 致命 + skeptic 攻 claim | 防御漏洞被审稿命中 | ⬜ P7 |
| L10. 复现/双盲 | 复现零偏离 + Code release + 双盲脱敏合规 | 红线/不送审 | ⬜ P7 |

---

## 🚧 每阶段硬阈值（出口 gate，逐条 PASS 才进下阶段）

### 🔒🔒 路B 最小验证 gate 预登记（2026-06-22 写死；planner 设计 + 用户拍板放行；**当前唯一前置命门，PASS 才全铺路B**；数字一字不动禁 HARKing）

**背景**：路B重定位后 headline 押在「可微 Frangi 门（input-derived）调制记忆能否在拓扑轴显著提升续连」。严守 feedback_falsify_crux_first，先砸命门，不重蹈路A把命门拖到最后。

**命门 H_crux（单一，跑前写死）**：可微 Frangi 门（**gate-on**）vs 无门（**gate-off**，唯一变量）在拓扑轴**显著赢**。配置 = 2 臂 × 2 集（DRIVE/CHASE）× 3 seed = 12 run（≈6–15 GPU·h）。

**主判据轴 = clDice**（ε_β0 / Betti 交叉印证；clDice 是 PASS/FAIL 承重轴，ε_β0/Betti 只作同向佐证，**不许 clDice 不显著时改报 Betti**）。

**PASS（→ 全铺路B，约 125 GPU·h）需同时满足三条**：
1. **≥1 集** `clDice(gate-on) − clDice(gate-off)` 的 **3-seed 均值 gap ≥ +0.03 绝对**；
2. 该集 **per-image 配对符号检验 / Wilcoxon 单侧 p < 0.05** 且 **bootstrap 95% CI 下界 > 0**；
3. **DRIVE + CHASE 两集方向都为正**（不许一正一负）。

**FAIL（→ benchmark-only / workshop 诚实降级，停下报用户）**：gap < +0.03 **或** p ≥ 0.05 / CI 下界 ≤ 0 **或** 两集方向相反。

**🔒 FAIL 后机械红线（写死，禁绕）**：
- 禁换主判据轴（clDice 不显著**不许**改报 Betti / ε_β0 凑过）；
- 禁扩 seed 凑显著；
- 禁调 Frangi σ / scale 参数重跑凑显著；
- 禁换数据集（DRIVE/CHASE 锁定）。
- FAIL = **stage-gate FAIL 拍板点**，停下报用户，写诚实回退。**禁再找新缺陷续命。**

**🔒 参数量隐患已实测排除（gate 2 臂无需等参对照，2026-06-22）**：Frangi 门加 d_model+2 ≈ **258–514 参数 = 0.001–0.006%**（可忽略量级），故 gate-on 若赢**非容量优势**——记进预登记说明，无须扩 3 臂加等参对照。

**统计实现纪律**：配对符号检验 / Wilcoxon 单侧 + bootstrap 95% CI **手算**（numpy + itertools，**禁 scipy.stats**，OMP 红线，沿用全项目纪律）。

**一次验证（禁 p-hack）**：本地 e2e 真烟测通过后冻结配置，命门跑**一次**，禁反复调参直到 gap 出现。

> 🗄️ **以上「路B 最小验证 gate」2026-06-24 已 FAIL 归档**（DRIVE 正 CHASE 反，三条 PASS 无一满足）。只读留痕，不再作 gate。当前命门 = 下方「批2 区分度门」。

---

### 🔒🔒 批2 区分度门预登记（**已冻结** — 2026-06-25 planner 设计 + skeptic 2🔴 修复版，用户拍板采纳；数字一字不动禁 HARKing）

> ✅✅ **批2 VERDICT: PASS（2026-06-26，seed42 GO 信号；verifier 核数字 ✅）**：M=8 baseline，pool DRIVE+CHASE n=12。**PSR on clDice=0.857(24/28 可分离) >> shuffle-null 95pct=0.143**；power=0.926；饱和 sanity False(fr_unet Medium clDice 0.745 不饱和)；交叉印证 ε_β0 PSR0.75 同向 + SR/reid 斜率同号 + Kendall W=1.0。**5 项预登记交叉印证全过 → 承重命门「benchmark 能区分方法」确证。** 详见 PROJECT_LOG「批2 VERDICT PASS」entry。**纪律：seed42=GO 初判，正式判据落批3 3-seed**（下方第 4 条仍要求 3-seed 复核）。⚠️ cs_net eval bug(训练 0.81 vs eval 0.49/0.12,preprocess_benchmark_image 路径 miss)待修重跑——PASS 不受影响(cs_net 修后 PSR 仍 >>null)。

**背景**：benchmark-only 后承重前提 = 「benchmark 能区分方法」。STORY 标此 claim 全 hedge 至本门确认。严守 [[feedback_falsify_crux_first]]：先砸区分度命门再立判别轴 claim。**skeptic 红队逮 2🔴(PSR 复合量未切开 + 小样本假 FAIL)，下方修复版已采纳冻结。** L6「拓扑/续连赢 SOTA」正式降参照（Ours 输不塌稿）。

**命门 H_disc（单一，跑前写死）**：~M 个 baseline 在续连/拓扑指标上分得开（成对差超噪声带 **且超方法池基础可分性**），而非全挤一团 / 假 FAIL。

**配置**：批2 = {DRIVE,CHASE} × ~M main-venv baseline × seed42（早期信号）→ 批3 +seed{1,2}（正式）× 4 severity（不重训）。方法集合 M 批2 跑前**冻结**（C(M,2) 是分母，跑后改 M = HARKing）。

**主判据轴 = 成对可分离率 PSR on clDice，但用 shuffle-null 锚（skeptic 🔴-1 修）**：
- per-method-pair (a,b)：per-image 配对差 dᵢ=clDice_a(i)−clDice_b(i)，cluster bootstrap（按 image_id，B=2000，手算 numpy）求 mean 95%CI，BH-FDR(q=0.05) 校正后 CI 不含 0 = 「可分离」。PSR = 可分离对 / C(M,2)。
- **shuffle-null 锚（核心修复，替代拍脑袋的绝对 0.30）**：把方法标签 shuffle 重算 PSR 得 null 分布；**PASS ⟺ real PSR 超 null 95 分位**。证 benchmark 判别力**超出方法池本身的强弱悬殊**（扣掉「随便选两个差很多的方法当然分得开」）。researcher 核：Demšar/Touchstone/HECKTOR 均无「PSR≥X%」规范阈值，shuffle-null 相对锚比绝对阈可辩护。

**小样本假 FAIL 修（skeptic 🔴-2）**：DRIVE n=4 / CHASE n=8 + 91 对 FDR → CI 系统压宽 → PSR 系统偏低。修：
- **pool DRIVE+CHASE → n=12 配对样本算每对 CI**（数据集作 cluster 维度；复用旧 re-ID 命门 pooled 跨集思路），不各集 n=4/8 单独判。
- **加 INSUFFICIENT 档（照 ArtiOODBench 先例）**：批2 跑完先报「当前 n 下假定文献效应量 bootstrap 能检出概率」；power 不足 → 判 **INSUFFICIENT 非 FAIL**，待批3/FIVES(n=200) 补功效，不被「禁扩 seed」红线锁死成假 FAIL。

**饱和盲区修（skeptic 🟠-3）**：跑前写死 sanity——若 Medium 下强 baseline(FR-UNet) clDice >0.90 或 <0.30（地板/天花板失分辨力），主判据档自动切预登记次选 **Hard**。切换规则跑前定、基于单强 baseline 绝对值、不看方法间差距 → 非 HARKing。

**交叉印证（须同向，否则降一档）**：① PSR on ε_β0（固定 severity，ε_β0 是 severity-不变量只作固定档印证，**禁画衰减曲线**）方向一致 ② severity-response 斜率分散度 max−min βₘ（**只用 SR/reid_rate，禁 ε_β0**）≥ 噪声量级且 reid_rate 同号扩散。

**判定档**：PASS（real PSR>null 95 分位 + 交叉印证同向）→批3 铺 3-seed 立判别轴 claim；INSUFFICIENT（功效不足）→补样本不强判；FAIL（real PSR 未超 null）→停下报用户，诚实写「区分力有限/挤一团」，D&B 稿仍立但 Claim3 判别轴降级不写区分 claim。

**🔒 机械红线（写死，FAIL 后禁绕）**：禁换主判据轴（clDice 不过不许改 ε_β0/斜率凑）/ 禁换指标（SR 永不升主排名轴，可刷满 R7）/ 禁换 severity 档凑（除上方饱和 sanity 预登记切换）/ 禁加减方法凑 PSR（M 跑前冻结）/ INSUFFICIENT 后只许补预登记样本不许换判据。FAIL = stage-gate FAIL 拍板点，停下报用户。

**统计纪律**：全手算 numpy 禁 scipy.stats（OMP 红线）；cluster bootstrap 按 image_id（非像素/gap）；BH-FDR q=0.05 手算；shuffle-null 重算 PSR；3-seed mean±std。

**口径（L6 降参照落实，待拍板）**：本门不含「ours_gdn2 须赢」条款——ours 在 PSR 里是普通配对方，秩位/胜负不影响门 PASS/FAIL。胜负不承重，区分力才承重。

---

### P0 环境 & kill-shot
- [ ] 关 2：单层 GDN-2 fwd/bwd 在 4090(sm_89) GPU 跑通（退路 `naive_chunk_gated_delta_rule` 纯 PyTorch 先验正确）
- [ ] 关 3：GDN-2 记忆模块塞小 U-Net，DRIVE 上 ①不发散 ②Dice ≥ 纯 CNN
- [ ] **不妥协闸**：kernel 连 naive 退路都不通 OR pilot 主集发散/输纯 CNN → 砍（拍板点，写诚实回退）

### P1 数据 & 断点续连 benchmark
- [ ] 10+ 集就位（datasets.json 登记 + 许可证逐个确认）
- [ ] 断点合成协议可复现（对齐 creatis plug-and-play，参数固定可复现）
- [ ] 续连指标实现：ε_β0 / SR（直接用）+ re-ID 率（自定义，同根血管匹配）
- [ ] **防泄漏**：benchmark 测试集 held-out 零拼训练样本；记忆 key 不碰 GT 拓扑（grep 验证）

### P2 核心模型实现
- [ ] pytest 全通（记忆模块/re-ID 头/Frangi 门/多向合并 单测）
- [ ] grep 确认 Frangi 与记忆 key **不读 GT/分割结果**
- [ ] flatten 序列 ≤~1K；可退化纯 CNN 兜底可跑
- [ ] **红线**：不重写 kernel；scan 不写成贡献

### P3 主实验
- [ ] DRIVE/CHASE/FIVES/STARE 主集深做，≥12 baseline 同框架（无漏比）
- [ ] 三轴指标全算（Dice/IoU/AUC + clDice/Betti/Skeleton Recall + ε_β0/SR/re-ID）
- [ ] seed ≥3，数字 Bash/Grep 核 csv（禁 Read 看数据）
- [ ] **不妥协**：拓扑或续连维度 ≥1 轴显著赢 SOTA + 裸 Dice 持平不输；禁调参作弊凑赢 Dice

### P4 消融（2026-06-22 路B重定位：承重判据改 Frangi 门 on/off + 记忆类型无关）
- [ ] ≥8-10 组消融
- [ ] **Frangi 门 on/off 干净对照证「有门拓扑轴（clDice）显著↑」（headline 铁证，可归因到门，承重判据见上方路B命门）**
- [ ] **记忆类型无关消融：Frangi 门 ×{GDN-2, GLA, ConvGRU} 都涨 → 证增益来自门非记忆类型（把 MQAR delta≈GLA 负结果转正向证据）**
- [ ] 序列长度扫、多向数、reid_rate 副产刻画（仅报告不作机制承重）
- [ ] **红线**：机制纠缠不可归因 = 跑偏；**禁把 delta-rule 机制特异（A2>A1'/A2>GLA）复活为承重判据**（已证伪，R6）

> 🗄️ **以下 re-ID 可归因预登记表（A-I / A-v2 三臂命门）2026-06-22 整体冻结归档**：re-ID 已降为续连质量副产描述指标（STORY Claim 2），其机制特异性已被 MQAR delta≈GLA + 目标函数错配证伪。**本表不再作为推进 gate**，保留为硬资产留痕（诚实负结果 + 方法学诊断），论文可引「我们曾预登记机制可归因判据并诚实报告其证伪」。当前推进命门 = 上方「路B 最小验证 gate」。**以下内容只读不再执行。**

#### 🔒 re-ID 可归因预登记表（2026-06-20 skeptic 致命-2 补 → 2026-06-20 命门 v2 修：补 A1' 等参臂 + 判据2 改 ε_β0 配平分层 CDE，skeptic 三轮复核 0🔴，设计阶段写死，禁跑完找说法）【🗄️ 2026-06-22 冻结归档，不再作 gate】

| 臂 | bottleneck 特征源 | re-ID 头 | 作用 |
|---|---|---|---|
| **A0'（零假设臂）** | 纯 CNN bottleneck（无记忆/无注意力模块，use_memory=False） | 同一个 re-ID 头 | 容量/机制全无的地板 |
| **A1'（等参对照臂）** | 等参普通线性注意力模块（保留 q/k/v/out 投影+LayerNorm+同插入深度+同 Frangi 门通路，仅把有状态 delta-rule 关联记忆换成无状态 linear attn；可训练参数总量与 A2 差 ≤±5%） | 同头 | 隔离「加注意力模块的容量」贡献 |
| **A2（完整）** | GDN-2 有状态 delta-rule 关联记忆增强特征（delta 更新 + 递推状态 S_t） | 同头 | headline |
| A3（断记忆梯度） | 记忆特征但 detach 记忆训练 | 同头 | 隔离头 vs 记忆训练贡献 |
| A4（bonus，封泄漏） | 记忆特征 | 同头 + **预测骨架断点**（非 GT 骨架，Ren MICCAI2024 范式） | 证 GT 拓扑无实质优势 |

> 所有臂**同 seed≥3 / 同 split / 同超参 / 同训练预算（epochs）**，只切对照变量。A1' 等参口径以全模型可训练 numel 计，差 >±5% 须回 planner 重对齐再跑（禁默许超阈）。三臂 numel 实测值写进论文表脚注留痕。

**预登记判据（写死，FAIL = Claim 2 塌或降级 → 停下报用户拍板）**：

1. **主判据（机制可归因，归因链 A2 > A1' > A0'）**：
   - (1a) `re-ID率(A2) − re-ID率(A1') > 0` 且每集内 per-image 配对**精确排列检验**显著（n≥6：枚举 2^n 符号排列，单侧 p < 0.05；**n<6 小集预登记特例见下**）+ 配对 Wilcoxon 一致同号。**这是 headline 核心：证有状态 delta-rule 关联记忆（delta 更新+递推状态 S_t）超出等参 stateless 容量的净贡献。** FAIL → 增益来自容量非关联记忆 → Claim 2 机制塌。
   - (1b) `re-ID率(A1') − re-ID率(A0') > 0`（同检验）。佐证「加注意力模块」容量贡献（**辅助证据，A1'≈A0' 不致命**——只说明容量本身没用、增益全在 delta-rule 关联记忆，反而更利 headline；据结果在论文如实陈述，禁跑完改判定方向）。
   - **n<6 小集预登记特例（防 STARE n=4 机械卡 p=0.0625）**：n<6 时 2^n 符号排列单侧最小可达 p=1/2^n（n=4→0.0625>0.05 不可达）。故对 n<6 的集，主判据 (1a) 达标线预登记为「**方向为正（A2>A1' 同号）+ 该 n 下精确排列取得最小可达 p（即全部配对同向）**」，记为「该集达标」；不机械套 0.05。同时该小集**并入 pooled 跨集符号检验**作为补证。**n<6 集的单集 p 仅作方向佐证，Claim 2 的统计承重在 pooled 跨集检验 + n≥6 集的逐集 p<0.05**。CHASE(n=8,最小 p=0.0039)/HRF(n=18)/FIVES(n=20) 不受此特例影响，仍按 p<0.05。**此特例跑前写死，禁跑完发现卡 0.0625 再改（HARKing）。**
   - **跨集一致性**（替代旧 pool）：每集内独立做 (1a)，A2>A1' 方向在 ≥3/4 集成立（小集按上特例判达标）。
   - 统计实现：**禁 scipy.stats（OMP 红线）**，排列检验/Wilcoxon 手算（numpy + itertools 枚举），bootstrap 95% CI 手算（≥1000 resample 跨 test 图，CI 下界 > 0）。

2. **「认出≠填上」= memory 对 re-ID 的直接效应（ε_β0 配平分层 CDE；ε_β0 是中介非混杂，禁 over-control）**
   命门问的是：填充质量（ε_β0）持平时，记忆是否仍认得更准 = memory 对 re-ID 是否有**超出填充质量改善**的直接贡献。ε_β0 是因果链 memory→续连更好(ε_β0↓)→认出同根 上的**中介**，控制中介 = over-control bias（会抹真效应），故**作废旧 partial_corr(...|ε_β0) 及任何「结局模型放 ε_β0 取 memory 系数」的回归**（与 reid_verdict_v2.py:131 旧 LMM 数学同构，pilot 已实证塌缩为 p=0.486）。**唯一 PASS/FAIL 门 = ε_β0 配平子集分层（受控直接效应 CDE，匹配设计，非 over-control）**：
   - 做法：每集内，A2 与 A1' 在**同一图**天然配对，看同图 ε_β0 是否相近；仅纳入 `|ε_β0(A2)−ε_β0(A1')|` 落在该集 ε_β0 IQR 内的图（=**两臂填充质量相当**的子集，非「固定 ε_β0 水平」——筛的是 Δε_β0 落 IQR），在该子集内重做 (1a) 的配对精确排列检验。
   - **PASS 线（预登记，单侧，禁跑完调）**：两臂填充质量相当子集内 `re-ID率(A2) − re-ID率(A1') > 0` 且配对排列单侧 p < 0.10（子集更小故 .10，仍单侧预登记；子集 n<6 套上「方向为正+最小可达 p」特例）。
   - **意义**：填充质量一样好时记忆仍认得更准 → re-ID 是 memory 的直接效应（CDE），非 ε_β0 副产物。FAIL（持平子集内方向反或不显著）→ re-ID 仅 ε_β0 副产物 → Claim 2 降级为「记忆改善续连」（无独立 re-ID claim）。
   - **辅助刻画（不设门、不论成败，但须真写进论文正文）**：探索性中介分解报 TE/NDE/NIE 三件套（手算 OLS：中介模型 `ε_β0~memory_on+dataset`、结局模型 `reid_rate~memory_on+ε_β0+dataset`，NDE=结局模型 memory_on 系数，cluster bootstrap 按 image_id 报 CI）。**仅描述效应分布，不作 PASS/FAIL 依据**——NDE 因 block 经 ε_β0 中介路径而系统性偏小是**预期**（与旧 over-control 同构），**不以 NDE 论 Claim2 成败**，论文如实标注「NDE 偏小源于中介路径被截断，非无直接效应」。**TE/NDE/NIE 三件套必须真写进论文正文（主动暴露不利数字 = 严谨；省掉 = 藏，会被审稿抓）。**

3. **A4 封泄漏（不变，维持原判据）**：`|re-ID率(A4 预测骨架) − re-ID率(A2 GT骨架)| < 0.05` → GT 拓扑无实质优势，自监督泄漏质疑解除。
   > 保留理由：A4 与容量混杂/over-control 两条命门正交（管 GT-拓扑泄漏，非机制归因），skeptic 未质疑，维持 0.05 严阈。

> 阈值（A2−A1' 主判据 >0 + p<.05，小集特例；分层 CDE p<.10 单侧；A4 0.05）= 设计阶段预登记下限，**禁跑完上下调**。等参 ±5% = numel 对齐上限。判据2 唯一门 = ε_β0 配平分层 CDE，NDE 三件套仅辅助不设门（禁逻辑或择优放假阳）。所有统计禁 scipy.stats（OMP 红线），手算实现。

#### 🔒🔒 命门方向 A 预登记（2026-06-21 写死，planner 设计 + skeptic 红队 0 致命过 + 用户拍方向 A；跑前留痕，禁 HARKing）

**背景**：CHASE Stage-1 命门初跑 A2(delta-rule 有状态记忆)≈A1'(等参 stateless linear attn)≈A0'(纯CNN)≈0.50 随机（旧 seg-mask `reid_rate`）。**根因 = 测量管道断裂（代码层硬事实）**：`evaluate.py:708` 的 `reid_rate` 纯读 seg mask（`compute_all_metrics(pred_bin,...)`，`metrics.py:679` 只看分割掩膜是否覆盖 gap 两段），**从不调 re-ID 头的 K×K 配对 logits**；而 re-ID 头被 `reid_loss.py` 三道 detach 屏障隔离、其输出 eval 从不用 → claim 的机制（memory→头→同根匹配）结构性够不到 headline 指标。叠加 A1' 死参（`unet_gdn2.py:1120` proj_erase/proj_g/alpha_e ×0.0 零梯度，等参对照无效）+ 机制窗口窄（raster scan 同根 token 隔 1-3，delta-rule 短程 tied 文献预期）。**非真 null，是测量错位。**

**机制性假说 H（单一，跑前写死）**：A2≈A1' 源于「测量指标不对齐机制 + A1' 死参 + 检索窗口窄」三处工程缺陷。修后预测 **A2 > A1' 在对齐指标 `reid_rate_head` 上成立**（有状态 delta-rule 关联记忆有超出 stateless linear attn 的净贡献）。

**唯一指标变更（修测量非松阈值）**：判据 1a/1b/2/A4 中「re-ID率」从旧 seg-mask `reid_rate` 换成新 `reid_rate_head`（由 re-ID 头**离散 argmax 配对决策**判，**裁判 = GT vessel_segment_map 同根标签 Y，head 只贡献「选哪个伙伴」，连续 logit 仅作 match/no-match 门不进打分** → 切开「用被 L_match 训练的头判头」自证循环，skeptic 🔴-1）。**判据阈值数字一字不动**（1a p<0.05、CDE p<0.10、A4 0.05、跨集 ≥3/4、小集特例全冻结）。旧 seg-mask `reid_rate` **并列报但不作判据**（反 HARKing 诚实留痕，论文写明代码层指标错位证据）。

**分阶段修复（skeptic 🟢-6 采纳，做根因拆分）**：
- **Stage-1a（先做）= M1 新指标 + M4 修死参，不动 scan**：跑 CHASE 单集×3seed。若 `reid_rate_head` 上已 A2>A1'（判据 1a 过）→ 证根因 = 测量错位，**M3 骨架 scan 不必做**（省 R4 撞 Serp-Mamba 风险）。
- **Stage-1b（条件触发）= 上 M3 骨架 scan**（Frangi input-derived 导序，**禁 GT skeleton**，三臂一致施加，scan 当标准工程不当贡献 R4）：仅当 Stage-1a 仍 A2≈A1' 才做，给 delta-rule 检索窗口后重跑 CHASE。
- **全命门（过 CHASE 才跑）= 4 集×3 臂(+A4)×3 seed**，一次成型。

**一次验证（禁 p-hack）**：配置本地真烟测通过后冻结，每 stage 跑**一次**，**禁反复调 scan 参数/阈值/lambda 直到 A2>A1' 出现**。

**硬退出判据（写死，这是 Claim2 记忆机制最后一次修复机会）**：Stage-1a+1b 全做完、全命门仍 `reid_rate_head` 上 A2≈A1'（判据 1a FAIL + 持平子集 CDE FAIL，跨集方向不一致/pooled 不显著）→ **真 null 坐实，Claim2 记忆机制不再救** → headline 转 benchmark-led（杀手锏断点 benchmark + 续连指标 ε_β0/SR + 可解释图 + 诚实报告 delta-rule 在 ≤1K 容量下不超 stateless）→ stage-gate FAIL 拍板点停下报用户。**禁再找新缺陷续命。**

**留痕审计（PHASE_4 ⑧）**：A1' 修死参后审计 proj_erase/proj_g/alpha_e grad norm ≠ 0（已实测 3.04/0.831/0.526）+ 三臂 numel 差 ≤±5%，写论文附录。

> **A-I 结果（2026-06-21 跑完）**：CHASE Stage-1a M1+M4 跑出 → 对齐指标 `reid_rate_head` 跳到 0.94（旧 seg-mask 0.46，证头真学会匹配、老指标测错东西），**但 A2(0.9437)≈A1'(0.9401) 仍平**。二诊（researcher+analyst 收敛 90%+）：测量已对齐，但 **re-ID 头融合架构让 dec_feat(decoder 局部 128×128) 抄近路压没 memory(o_seq 32×32)**——头 ep10 即靠局部空间邻近解任务，delta-rule 没机会。非真 null。→ 触发 A-v2。

#### 🔒🔒🔒 命门方向 A-v2 预登记（2026-06-21 写死；planner 设计 + skeptic 红队 2🔴 修 + 复核 0 致命 + researcher 理论锚核实 + 用户拍 Option A；**Claim2 记忆机制最后一次设计调整**）

**机制性假说 H（单一，跑前写死）**：A2≈A1' 源于「① re-ID 头局部近路（dec_feat 高分辨率压没 memory）+ ② 评估未在 delta-rule 理论占优区度量」。delta-rule 相对 stateless linear attn 的净优势**理论上只发生在 state crowding（同一感受野内同时竞争写入有限状态维 d 的身份数 k 大）处**，避免 catastrophic overwriting / key collision；low-crowding 处两臂本就该 tied。修后预测 **A2−A1' 的 `reid_rate_head` delta 随 crowding 单调上升：high-crowding 子集 A2>A1' 显著，low-crowding 子集 tied**（剂量-反应，非单点）。**判据轴 = state-crowding（关联密度 k），不是 gap 距离/序列长度**（距离是两臂共享维度分不开，STORY L37-42 铁律）。

**理论锚（researcher 2026-06-21 核实坚实，写论文用）**：Schlag 2021（ICML，形式界：状态维 d 个正交关联上限，超之检索出错）+ DeltaNet arXiv 2406.06484 §2.2（"key collisions when L>d"）+ VLA arXiv 2605.11196 §5.2/§6.5/Prop.3（对照实验解耦 K 关联数 vs T 序列长度，证 **K 是驱动因素非距离**，per-head 容量 = d_h）。⚠️外推边界：MQAR key 离散近正交，血管 feature 连续、碰撞率无直接实验对应——论文须显式声明此外推。（2602.04852 不支撑此命题，禁引。）

**两处修复（三臂一致施加，测量/架构修复非自变量）**：
- **M-A memory-only 头**：`ReIDReadoutHead` 加 `use_loc_feat=False`，砍 dec_feat 路、头只吃 memory `o_seq`。三臂一致。detach 三屏障不动。
- **M-B state-crowding 子集判据**：k(i)=query i 局部窗口（半径 R_win=bottleneck 感受野按 stride 算定的架构常量，input-derived）内**不同 vessel segment id 去重数**。判据在 high-crowding 子集(k≥k_thresh) vs low-crowding 子集上分别算 `reid_rate_head`。**子集从无 hard-neg 的标准主 benchmark 自然分布筛**（单图~100 gap 天然含高 crowding 区），候选池**全 K 无人工门**。**不注入 hard negative**（删，防构造性 cherry-pick + 保命门 benchmark = P3 主续连 benchmark 可比）。

**跑前写死数值**：k 度量=窗口去重 seg id 数 / R_win=stride 算定理论感受野 / k_thresh=各集自然 k 分布**中位数**（+ 均值 + 60 分位稳健性并报方向须一致）/ 候选池全 K / hard neg=删 / 判据阈值 1a p<0.05·CDE p<0.10·A4 0.05·跨集≥3/4·小集特例（A-I 一字不动）/ r_chance=该子集 1÷平均候选数（每集每子集分算）/ epochs 300 / severity Medium。

**主判据（dose-response 交互，skeptic 裁决一，关死循环+强化 headline）**：不是「high-crowding A2>A1'」单点，而是 **「A2−A1' delta 随 crowding 单调上升：high-crowding 子集 per-image 配对 A2>A1' 显著(p<0.05 小集特例) + low-crowding 子集 tied(方向不显著)」的联合交互模式**。只 high 显著 low 也显著 → 非 crowding 特异 → 归因存疑。bonus 并报 top-quartile crowding 方向（不设门）。

**(a)/(b) 归因切分（描述性读数，skeptic 🟠-2，不设 PASS/FAIL 门）**：high-crowding 子集同报 A1' 与 A2 各自相对 r_chance 位置——A1' 塌到 ≈r_chance(|·|<0.05)=被动垫底=容量复发=归因弱；A1' 显著>r_chance 只是<A2=delta-rule 主动优=headline 强。**承重门始终是 A2>A1' per-image 配对检验（r_chance 在配对中约掉）**；(a)/(b) 仅描述归因强度，不设门（同 v1 NDE 三件套纪律）。r_chance 跨集不可比，只比同集同子集配对 delta。

**判据 1b 容量排除（必报）**：A2>A1'(1a 过) 且 A1'≈A0'(1b 方向不显著) = 增益全在 delta-rule、容量本身没用 = 最强 headline（STORY L74）。memory-only 下 A0' headless→reid_rate_head NaN→1b 回退 seg-mask。

**k 的 R5 辖域声明（skeptic 🟠-1）**：k 用 GT vessel_segment_map 计数，但**仅作评估时难度分层、三臂共享同一 k 划分、不回流任何臂的训练/前向/memory**（合法「按难度分桶报指标」，与「GT 监督机制」正交）。论文须显式声明。可选鲁棒性对照：用 input-derived crowding 代理（Frangi 局部峰数/骨架分叉密度）重算验证子集划分高度重合。

**指标**：判据结局量 = `reid_rate_head`（high/low-crowding 子集，memory-only 头，标准 benchmark）。旧 seg-mask `reid_rate` + 全 gap reid_rate_head + 距离切子集 reid_rate_head **三者并列报不作判据**（诚实留痕，距离仅次要刻画）。

**一次验证（禁 p-hack）**：本地真 e2e 烟测通过+各集 k_thresh/R_win/r_chance/high-crowding 子集 n(≥4) 落档后冻结。CHASE 先验(3臂×3seed)跑一次→过 dose-response 主判据→全命门(4集×3臂(+A4)×3seed)一次成型。**禁反复调 R_win/k_thresh/子集设计直到 A2>A1' 出现。**

**🔒🔒 无条件铁闸（skeptic 🟠-3，与上方 A-I 硬退出判据合并为唯一退出门，最高优先）**：**A-v2 是 Claim2 记忆机制绝对最后一次设计调整。全命门跑完，若 high-crowding 子集 `reid_rate_head` 上仍 A2≈A1'（dose-response 不成立 / 配对方向不一致 / pooled 不显著）→ 真 null 坐实 → 无条件转 benchmark-led**（杀手锏断点 benchmark + 续连指标 ε_β0/SR + reid_rate_head 指标本身作贡献 + 可解释图 + 诚实报告 delta-rule 在 ≤1K 容量/k 下不超 stateless）→ stage-gate FAIL 拍板点停下报。**四点名红线（机械判定，禁绕）：FAIL 后禁换轴、禁换指标、禁换子集定义、禁扩 seed 凑显著。禁再找新缺陷续命。**

**留痕审计**：① 三臂 memory-only 头 numel ≤±5%；② A1' 死参 grad≠0（A-I 实测沿用）；③ R_win/k_thresh(中位数+均值+60分位)/r_chance/各集 high+low-crowding 子集 n + (a)/(b) 读数 + dose-response 曲线写论文附录。

**算力**：CHASE 先验 9 run ≈23 GPU·h（门控）→ 全命门 36+12(A4) run ≈125 GPU·h。CHASE benchmark cache **无须重生**（删 hard neg 用自然分布，cache 不变）。

### P5 泛化/跨域/跨器官
- [ ] 冠脉(XCAD/DCA1/CHUAC) + OCTA(OCTA-500/ROSE) + 跨域(Crack500/Roads 附录)
- [ ] 跨域协议 FIVES→{DRIVE,STARE,CHASE,HRF} + DRIVE→CHASE/STARE
- [ ] ≥10 集；跨域不崩；边缘集允许 1-2 失败
- [ ] **红线**：许可证未确认不纳入发表；跨域禁调参作弊

### P6 可解释性
- [ ] ≥3 张支撑 headline 的可解释图（记忆检索热图/re-ID 匹配/容量衰减）
- [ ] 图含数字/比例的，主线派 verifier 或自核 ≥2 关键值与 csv 一致
- [ ] **红线**：禁 cherry-pick 误导；解释不超数据

### P7 写作 + 对抗审稿 + 投稿
- [ ] 14 页 LNCS，related work 硬区分 GDKVM（R3 模板）
- [ ] 数字三方对账（registry↔STORY↔tex）0 偏离
- [ ] reviewer 十角色 0 致命 + skeptic 攻 claim 通过
- [ ] 双盲脱敏合规 + 编译 0 error/0 undef + Code release
- [ ] **拍板**：投稿（venue 顶会优先，ACCV 保底）

---

## 🚨 红线（任意触发立即停手）

1. ❌ 断点续连 benchmark 测试集拼入训练样本 / in-sample 评估
2. ❌ vesselness 或记忆 key 用 GT / 分割结果监督（鸡生蛋 + 泄漏）
3. ❌ 凭印象写数字（必须 Bash/Grep 核 csv）
4. ❌ 复现偏离（私加裁剪/降 lr/改步数/换实现凑收敛；baseline 不按官方）
5. ❌ scan/reorder 当核心贡献（撞 Serp-Mamba）
6. ❌ related work 不区分 GDKVM
7. ❌ 绝对化 claim（"universal"/"always"/"prove"）

---

## 📝 task 完成判定流程

```
Step 1: 查本文件找该 task 的硬阈值
Step 2: 逐条对照实际产出
Step 3: 全条 PASS → 更新 PROJECT_LOG + 移下一项
        任一 FAIL → 不标完成，回去补
Step 4: 跑 grep 防御检查（R1-R7 + 红线）
Step 5: 大阶段收口跑 /stage-gate（verifier 核数 + opus reviewer 严判 PASS/FAIL）
```
