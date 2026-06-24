# 评分量规（Rubrics）— G2/G3/G4 用

> 所有筛选的判据集中在此。G2 二元 kill、G3 加权打分 + 12 维 taste、G4 红队 + kill criteria 都引用这里。
> 设计依据见各节脚注（4 路 researcher 联网采集）。

---

## R1 — G2 二元 kill checklist（任一命中即砍，无打分）

> 越早的闸成本越低、标准越宽，只拦明显不可行的（Stage-Gate 原则）。二元判断，5 分钟/条。

- [ ] 命中宪章 B 节硬排除清单
- [ ] 与已发论文 SPECTER2 余弦 > 宪章阈（默认 0.85）且说不出差异化角度
- [ ] 估算算力 > 宪章 C 节预算上限
- [ ] 单人 1-2 月内无法出首轮实证（无 reasonable attack）
- [ ] 检索不到任何 future-work / limitation / gap 支撑该问题真空白
- [ ] 核心问题已有公认完整解
- [ ] 目标 venue DDL 内工作量明显超期
- [ ] **[anchor 闸，A 族专用]** 核心 claim 既无具体可观测现象/反常（phenomenon），也无指名机制（mechanism），`mechanism_anchor=MISSING` → 砍或回 G1 补锚。（B 族 S3/S4 天然现象驱动，跳过此条）

全不命中 → 进 G3。命中任一 → 砍，pool.jsonl 记 `killed@G2 + reason`。

---

## R2 — G3 加权打分（InnoEval 六维，0-10/维）

> 来源：InnoEval（[arXiv:2602.14367](https://arxiv.org/html/2602.14367v1)）+ Si et al. 100+ 研究员权重（[arXiv:2409.04109](https://arxiv.org/pdf/2409.04109)）。
> **关键**：feasibility 单独维度，不准混进总分掩盖（历史教训：评审 feasibility 与总分 r<0.1，被忽略）。
> **本轮改动（2026-06-18）**：原 Novelty（.30）拆成两子维——**问题新颖度**（.20）+**组合新颖度**（.10），总计仍 .30；其余四维不变，总权重 = .20+.10+.25+.25+.10+.10 = **1.00**。根因：原单一 Novelty 分系统性高估缝合型（A+B「没人拼」天然离任何单篇都远，SPECTER2 距离大），而 B 族现象型命中率显著更高——尺子与实证结果倒置，故拆开区分。

| 维度 | 权重 | 0 分锚 | 10 分锚 |
|---|---|---|---|
| **问题新颖度 Q-Novelty** | **0.20** | 问的问题本身无意义/已有公认答案 | 问题本身值得问：锚在真实现象/反常/已知悖论上，领域公认是开放问题 |
| **组合新颖度 C-Novelty** | **0.10** | 组合方式与已有工作完全重叠 | 攻击路径/方法组合全新；注：纯「A+B 没人拼」且问题新颖度低→此维高分无意义，被 Q-Novelty 拉低 |
| **Feasibility 可行** | 0.25 | 无已知攻击路径 | 清晰方法论，单人 1-2 月出首轮 |
| **Significance 重要** | 0.25 | 无人在乎的边缘小问题 | 解决会显著推进领域，公认核心 |
| **Validity 有效** | 0.10 | 方法论站不住 | 实验设计能真正证明 claim |
| **Clarity 清晰** | 0.10 | 说不清在做什么 | 一句无术语话讲清目标（Heilmeier Q1）|

加权总分 = Σ(维度分 × 权重)，满分 10。

**识别纯重组模式（扣分逻辑）**：若候选 C-Novelty ≥ 7 但 Q-Novelty ≤ 4（高组合新颖度 + 低问题新颖度），标记 `pattern=pure_recombination`，加权总分额外 −0.5 惩罚。这正是历史 A 族死法（「A+B 没人拼」但问题本身没有真空白）。

**硬阈（先于加权执行，命中直接砍）**：
- Feasibility < 4 → 砍（Hamming：no reasonable attack = not important）
- Q-Novelty < 4 → 砍（问题本身不值得问；原 Novelty<5 硬阈改为只对 Q-Novelty 判，C-Novelty 单独高不保底）

加权排序后取前 ~40%-50% 进 G4。

---

## R3 — G3 Swiss pairwise 排序（不用 LLM 单条打分）

> 来源：Si et al.——LLM 单条 scoring 准确率 ≈50%（随机），pairwise 比较 53.3% 更可靠；Swiss tournament N=5 轮 O(n log n)。

对 R2 幸存候选两两比较（"这两个哪个更值得做"），跑 5 轮 Swiss，累计胜场排序。
- 比较维度提示：novelty + feasibility + significance 综合，**不许只看新颖**。
- **人工 final rerank 保留**：Swiss 排完，主线/用户对 top 名次有否决权（human rerank 实证显著优于纯 AI rerank，top idea 重叠仅 17/49 → 65% 好 idea 是 AI 自己选不出来的）。

---

## R4 — 12 维选题 taste 量规（G3 深度评估，0-5/维）

> 综合 Hamming / Heilmeier / Uri Alon / Jason Wei / Chris Olah / Michael Nielsen / EA-ITN。
> R2 给快速加权，R4 给 top 候选做深度品味体检（耗时，只对 ~10 个跑）。满分 60。

| # | 维度 | 来源 | 操作测试（答不出→低分）|
|---|---|---|---|
| 1 | 重要性 Importance | Hamming+ITN | 问 3 位领域内人"这是重要问题吗"，茫然→0-1 |
| 2 | 可行性 Tractable | Hamming+Alon | 写出 3 步攻击计划，写不出→≤2 |
| 3 | 被忽视度 Neglected | ITN+Wei | 数近 2 年相关论文 + 顶会 poster 组数 |
| 4 | 时机成熟 Timing | Hamming+Wei | "3 月前做得了吗？3 年后是否太挤？"答"刚好现在"=5 |
| 5 | 持久/普遍 Longevity | Jason Wei | 去掉现在用的具体工具，结论还成立吗 |
| 6 | 个人匹配 Fit | Wei+Alon | "谁比我更适合做？"答案很多人→1-2 |
| 7 | 内驱 Inner-voice | Uri Alon | "孤立于社群你仍会做吗" |
| 8 | 影响范围 Who-cares | Heilmeier Q4 | "成功了有什么不同"，答不出→0-1 |
| 9 | 可测量 Measurable | Heilmeier Q8 | 写得出 mid-term exam 吗 |
| 10 | 差异化 Novelty | Heilmeier Q3+Nielsen | 一句话说清"新在哪" |
| 11 | excited-reader | Chris Olah | "别人先发了这篇，你会不会'该死我早该做'" |
| 12 | 统一潜力 Unification | Nielsen+Hamming | 这领域是不是一团乱、缺统一理论（mess=机会）|

**硬门槛**：维度 2（可行性）< 2 直接淘汰；维度 7（内驱）< 2 谨慎标记。

---

## R5 — G4 Heilmeier Catechism（红队前自检 8 问）

> DARPA 原版（[darpa.mil/about/heilmeier-catechism](https://www.darpa.mil/about/heilmeier-catechism)）。每个进 G4 的候选先逐条作答，答不出的条目即红队重点。

1. 你想做什么？**用绝对无术语的话**说清目标。
2. 现在怎么做的？现有做法的极限在哪？
3. 你的新在哪？为什么你觉得会成功？
4. 谁在乎？成功了有什么不同？
5. 风险是什么？
6. 花多少钱（算力/时间）？
7. 要多久？
8. mid-term 和 final"考试"怎么检查成功？

---

## R6 — G4 Pre-mortem + RAT（最大风险假设证伪）

> Gary Klein pre-mortem（风险识别 +30%）+ Lean RAT（先测最大风险，非先建 MVP）。

1. **Pre-mortem**：假设"这项目 1 年后已经失败了"（语法用"已经"非"可能"）→ skeptic 倒推"是什么导致了失败"，列出所有失败路径。
2. **提炼最大风险假设**：从失败路径里挑 2-3 个"如果这个假设错了，整个 claim 就塌"的 Riskiest Assumption。
3. **设计最便宜的证伪实验**：每个最大风险假设配一个 <1 GPU·h（或纯文献/小消融）就能部分验证的测试 → 喂给 G5。
4. 三选一：假设确认→推进 / 证伪→砍或 pivot / 不确定→再设一轮更便宜的测试。

---

## R7 — G6 立项书面 Kill Criteria 模板（幸存候选必填）

> 立项时把"什么条件下主动放弃"写死，签字、定期复查、禁随意松动。防止沉没成本绑架。

```
项目: ______
顶会档: ______   退路档: ______

KILL-1 (实证): 若 [首轮核心实验] 在 [N 周] 内未显示 [比 baseline 高 X% / 信号存在]，则终止冲顶会、转退路档或砍。
KILL-2 (撞车): 若 [核心 novelty gap] 被竞对 arXiv/顶会先发覆盖，则终止或重定位。
KILL-3 (理论): 若 [核心理论前提] 被证伪/已知不成立，则降格为分析工具 / 砍。
KILL-4 (资源): 若 [算力/时间] 超出预算 [X GPU·h / Y 周] 仍无 PASS 读数，则停。

复查节奏: 每 [阶段/2 周] 对照一次。
签字: 用户 ______ 日期 ______
```

立项后这份 kill criteria 进项目 `ACCEPTANCE_CRITERIA.md`，stage-gate 时一并核。

---

## R8 — 顶会天花板 Ceiling（G3 surface + G4 红队 + G6 定档共用）

> **病因**：漏斗历来只量「会不会死」（下风险全是硬闸），从不量「活了够不够顶会」（上风险无闸）。结果 5 轮幸存者全是 benchmark/分析型（selinf→TMLR/D&B、disagree、ArtiOODBench），没一个 CVPR/NeurIPS main-track 苗子；能上顶会的 method/theory 型（A 族）全死在 G5。这条量规把上风险补成显式维度。
> **反矫枉过正铁律**：天花板**不靠 novelty 自评**——Si et al.（[arXiv:2506.20803](https://arxiv.org/html/2506.20803v1)）+ HindSight（[arXiv:2603.15164](https://arxiv.org/pdf/2603.15164)）实证 **LLM 打高 novelty 的 idea 真实价值反而更低**（负相关）。故 5 个信号**全要举证据，举不出=0 分**，杜绝「听起来大胆」泡沫。

5 信号，各 0-2 分，满分 10：

| # | 信号 | 接地测试（举不出实据 = 0） | 来源 |
|---|---|---|---|
| 1 | **新领地非新点** | 能一句话说「这是第一篇做 X 类问题的」+ 文献 isolation 实测（与近 3 年最近邻 conceptual 距离大且**非缝合**距离）。只能说「比上篇高 Y%」= 0 | NeurIPS guidelines；[arXiv:2602.06607](https://arxiv.org/pdf/2602.06607)（central-claim isolation = 被引/disruption 最强前兆）|
| 2 | **10x 非 10% upside** | 写出「方法全成→领域具体怎样不同」，是量级跳还是边际。边际改进 = 0（除非 trivially simple 到人人会用）| Schulman 10%/10x 测试 |
| 3 | **enabling 开线** | 列举 ≥3 个独立 follow-up 论文方向，每个能单独成文。列不出 = 0 | Schulman（stacking toward ambitious objective）|
| 4 | **跨域桥** | 说出领域 A 机制用到领域 B 问题的**具体机制连接**（非「都用神经网络」泛泛）。单域应用 = 0 | Kirsch（generality）；[PLOS](https://journals.plos.org/plosone/article?id=10.1371%2Fjournal.pone.0312945)（interdisciplinarity 正相关被引）|
| 5 | **reviewer 7.5+ 相** | 三件套全有：清晰 challenge（为何难）+ 明确 insight（为何之前做不到）+ 可行验证路径 → 推 7+；insight 模糊 → borderline 5-6（ICLR 实证 >7.4 几乎全 Oral，5-6 是博弈区）| [arXiv:2510.13201](https://arxiv.org/html/2510.13201v2) |

**档位映射**（顶会 main-track 有「新领地 OR 强 insight」缺一不可，对齐 NeurIPS「new territory > incremental SoTA」+ CVPR 2026 反 novelty fallacy 但分 Findings track）：
- **Ceiling ≥7 且（信号 1 或 5）≥1**：`ceiling_tier=MAIN` — CVPR/NeurIPS/ICLR main-track 潜力 = **顶会苗子**
- **Ceiling 4-6**：`ceiling_tier=FINDINGS` — CVPR Findings / MICCAI / TMLR / D&B 档，能发但非顶会 main
- **Ceiling <4**：`ceiling_tier=WORKSHOP` — 除非 reframe 否则不进顶会通道

**用法（关键，防两头矫枉过正）**：
- 低 Ceiling **不在 G3 直接砍**——扎实的 B-venue 好题仍是真论文，只**诚实标档**，不让它冒充顶会 slot（CVPR 2026 Findings track 实操：solid-but-incremental 自愿进 Findings，不当 main-track 胜）。
- **G3 MAIN-tier 保底晋级 = opt-in（2026-06-24 路 B 校准，见 [[STRATEGY_MEMO_2026-06-24]]）**：**仅当本轮宪章 E 节 `risk_quota` 显式留了 A 族 side-bet 槽**，才强制晋级 ≥1 个 `MAIN` 候选进 G4（标 `lane=high_variance`，对冲 pairwise judge 风险厌恶 [Si et al.] + Swiss 偏差 [arXiv:2410.19333](https://arxiv.org/html/2410.19333v1)）。**默认路 B 轮（A 族槽=0）不强塞**——让漏斗自然导向 B 族 benchmark/empirical（约束下最高成功率，组合台死活对照实证：A 族大胆题全死、B 族全活）。ceiling_tier 评分本身仍跑（诚实标档是有用信息），只是不再用它强行保送 A 族。
- portfolio 配比由宪章 `risk_quota` 定（默认 ≈85% B / 15% A，非旧 70-20-10）；要冲 transformational 通道须开 side-bet 槽显式留痕（[innovation portfolio](https://www.acceptmission.com/blog/innovation-portfolio-management-guide/)）。

---

## R9 — G5 kill-shot 判定三分流 + 强制功效声明（防假阴性误杀）

> **病因**：<1 GPU·h 最小数据 pilot 统计功效低，floor effect / proxy 失真易把「测不出」误判成「信号不存在」，杀错真顶会苗子（run-004 终判一堆 GRAY 即此症）。ML 领域 ~93% 研究不做统计检验、95% 不报 effect size（[arXiv:2502.00902](https://arxiv.org/html/2502.00902v2)），null 无法与「欠功效」区分。
> **反矫枉过正**：这条放松的是**误杀**，不放松 kill 纪律——干净 KILL 照杀不误，只是欠功效的 null 不当死信号。

**每个 kill-shot 跑完必附功效声明**（verifier 核，缺则判 GRAY 不判 KILL）：
```
N(epochs/samples): X | metric: <continuous / binary-exactmatch> | 95% CI: [lo, hi] | MDE@80%power: Y
verdict: KILL / GRAY / KILL-proxy
```

三分流：
1. **KILL（可信否定，照砍）**：null + **CI 窄**（上界 < 最小有意义 effect）+ 用了 **continuous metric**（非 exact-match）。「没信号」是真信息 → 砍。
2. **GRAY（欠功效，不可判，不砍）**：null + **CI 宽** 或 用了 binary/exact-match 且 MDE > 合理 effect size。只说明「实验太小」→ **候选存活**，带债排队更大规模验证或换 continuous proxy。kill 权重设 **0.3**（降权非等权），绝不当死。
3. **KILL-proxy（代理否定，偏强 kill）**：目标能力小规模本就不可测（emergent，[arXiv:2412.07111](https://arxiv.org/html/2412.07111v1)）→ 设计相关 proxy task → proxy 也无信号 → 给 **0.6** 权重 kill（非 1.0，proxy 不完美）。

**反 floor-effect 操作**：pilot 评估指标**优先 continuous**（Brier/edit-distance/连续 score），别用 0/1 exact-match——后者最易触发 floor effect 把微弱信号抹平（[arXiv:2310.03262](https://arxiv.org/html/2310.03262v3) PassUntil：大采样可在小模型捞出信号）。

`null result = no evidence of effect ≠ evidence of no effect`（[arXiv:2406.03980](https://arxiv.org/abs/2406.03980)）——宽 CI 的 null 是 GRAY 不是 KILL。

---

## R10 — G5 PASS 范围纪律 + 立项 headline 不得超实证（防假阳跨集外推）

> **病因（2026-06-22 横向复盘）**：R9 只防**假阴**（宽 CI null 误判 KILL），完全不防**假阳**。组合台两篇 pipeline 自产项目同一死法——
> - **nca-phasemap**：G5 在 Hippocampus 上「临界存在」三重实证 PASS → 立项 headline 写「NCA 存在**普适**尖锐相边界」→ 真命门（普适性=BraTS 第二集）被 IOU 进 R7 书面 kill criteria（K1）→ Gate1 K1 FAIL，烧完算力才死。
> - **disagree**：75-scan AUROC 0.71 PASS → 立项 → 289-cluster 0.43 低于随机（小样本假阳=回归均值）。
>
> **根因**：大胆 claim 的承重命门 = 普适性/跨集复现/足样本，而 `<1GPU·h` 发现集小 pilot **测得出「这里有没有现象」、测不出「普适」**。G5 验了个便宜的代理命门 PASS，真命门推到立项后才死 = 「事后才严」偷爬回来，正是流水线立志消灭的病。配 [[feedback_falsify_crux_first]] + [[feedback_claim_shape_decides_birth_difficulty]]。

**R10-a — 区分 PASS-local vs PASS-general**：G5 在**一个 setting**（单数据集/单实现/单尺度/单样本量级）上信号存在 = `PASS-local`，**不等于** `PASS-general`。命门只有在 **≥2 个独立 setting**（第二数据集 / 第二实现 / 足功效大样本）都不塌才算 `PASS-general`。G5 verdict 必标 local/general。

**R10-b — 立项 headline 措辞不得超过实证覆盖（G6 钉死）**：headline 只能 claim G5 实际验过的 setting 范围。含「普适 / universal / 可前验 / 可外推 / 跨集 / 机制特异 / seed 稳定」等**外推字样**的 headline，其外推维度若只有 `PASS-local`，**必须二选一**：
  - **(i) headline 收窄到已验 setting**（如「在 Med-NCA Hippocampus 上」而非「NCA 存在」），普适降为**显式标注的立项后赌注**写进 R8 standout 线，**不烤进 headline**；或
  - **(ii) 把跨集/足功效命门提为硬前置 gate**（即便 >1GPU·h），`PASS-general` 才准用外推 headline。

  **🔒 禁**：把外推维度的真命门丢进 R7 书面 kill criteria 当 IOU 推到立项后（= nca-phasemap/disagree 死法）。R7 只兜「**已验范围内**出意外」，**不兜「从没验过的外推维度」**。
  > 正例 = BMVC QCTS：headline 只 claim「q̄ 在 dermoscopy + ImageNet-C 有效」——两个 setting 都实测了，绝不多写一个「universal」。所以 reviewer 18 issue 全应答下来，没一条能从地基掀翻。

**R10-c — G3 命门证伪成本维（flag）**：G3 给每个候选标 `crux_cost` ∈ {LOW / HIGH}——其 headline 承重命门能否在**可用 setting** 上 `<1GPU·h` 证伪。`HIGH`（真命门 = 普适/跨集/emergent，发现集小 pilot 根本测不了）→ 在 G4 红队 + G6 呈用户时**显式标「高难产风险」**，逼 R10-b 二选一（收窄 claim or 预算贵命门前置），**不准带着未验外推 claim 进 G6 乐观立项**。`crux_cost=HIGH` 不是 kill 条件，是逼诚实定档。
