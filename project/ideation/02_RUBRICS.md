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

全不命中 → 进 G3。命中任一 → 砍，pool.jsonl 记 `killed@G2 + reason`。

---

## R2 — G3 加权打分（InnoEval 五维，0-10/维）

> 来源：InnoEval（[arXiv:2602.14367](https://arxiv.org/html/2602.14367v1)）+ Si et al. 100+ 研究员权重（[arXiv:2409.04109](https://arxiv.org/pdf/2409.04109)）。
> **关键**：feasibility 单独维度，不准混进总分掩盖（历史教训：评审 feasibility 与总分 r<0.1，被忽略）。

| 维度 | 权重 | 0 分锚 | 10 分锚 |
|---|---|---|---|
| **Novelty 新颖** | 0.30 | 与已有工作完全重叠 | 提问方式本身是新的 / 攻击路径全异 |
| **Feasibility 可行** | 0.25 | 无已知攻击路径 | 清晰方法论，单人 1-2 月出首轮 |
| **Significance 重要** | 0.25 | 无人在乎的边缘小问题 | 解决会显著推进领域，公认核心 |
| **Validity 有效** | 0.10 | 方法论站不住 | 实验设计能真正证明 claim |
| **Clarity 清晰** | 0.10 | 说不清在做什么 | 一句无术语话讲清目标（Heilmeier Q1）|

加权总分 = Σ(维度分 × 权重)，满分 10。

**硬阈（先于加权执行，命中直接砍）**：
- Feasibility < 4 → 砍（Hamming：no reasonable attack = not important）
- Novelty < 5 → 砍（novelty 是 accept/reject 最决定性预测因子）

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
