# ICLR 投稿规范与评审制度（落档，2026-06-19）

> 来源：researcher 联网核 ICLR 官方（iclr.cc / openreview）。ICLR 2027 日期未公布，以 ICLR 2026 规则为参照基线。带 TODO 的需投稿前再核官方。
> 服务：本论文（analysis/系统方向）投稿决策与稿件优化的硬约束真源。

---

## 1. 格式硬约束（违反 = desk-reject）

| 项 | 规则 | 来源 |
|---|---|---|
| **正文页数** | **9 页硬上限**（投稿时）；rebuttal 后 camera-ready 可到 10 页 | ICLR 2026 Author Guide |
| **超页后果** | 主文超 9 页 → **直接桌拒，不进审稿** | 同上 |
| 参考文献 | **不计页**，无限 | 同上 |
| 附录（bib 之后）| **无限页**，但 reviewer 无义务读 | 同上 |
| Ethics / Reproducibility statement | 可选，**不计页** | 同上 |
| 模板 | 官方 `iclr2027.sty`（投稿前从 iclr.cc 下当年模板）；当前用 iclr2026 | ICLR Master-Template |
| 字号/页边距 | TODO：需解压官方 zip 核 `.sty`（惯例 10pt，但官方原值未取到，禁臆想） | TODO |

**对本论文的硬含义**：当前正文 §1-§9 ≈ **32 页**（附录从第 33 页起）= **超标 3.5 倍**。投 ICLR 前必须砍到 ≤9 页，否则秒拒。

---

## 2. 双盲机制

- **double-blind**：作者/审稿人互盲。
- 主文或 supp **泄露作者身份 → desk-reject**。
- **arXiv 预印允许**，不破坏匿名；但引用自己的 arXiv 工作**必须第三人称**（禁 "our prior work [X]"，改 "[X] shows..."）。
- Supplementary 与主文**合并成单个 PDF**，附在参考文献后，同一 deadline。
- 重大未披露 LLM 使用 → desk-reject（润色/生成代码允许但须披露）。
- **本论文落点**：R4 脱敏（项目内部代号 + 各模型名 + 占位作者标签改通用名）= 投稿前 grep 清零的硬动作，与双盲红线绑定（具体名单见 STORY_FRAMEWORK R4）。

---

## 3. 审稿流程时间线（ICLR 2026 实际，2027 参照）

| 节点 | ICLR 2026 时间 |
|---|---|
| Abstract deadline | Sep 19 |
| Full paper deadline | Sep 24 |
| Reviews 发给作者 | Nov 11 |
| 公开讨论 / rebuttal 期 | Nov 11 – Dec 3（约 3 周，OpenReview 公开，非封闭）|
| Decision 通知 | Jan 25, 2026 |
| 会议 | Apr 2026（里约）|

- **Abstract deadline 作用**：占位注册，须与 full paper 一致；重复/占位 abstract → desk-reject。
- **2027 日期未公布**（地点确认 = 北美西海岸）。第三方预测 paper deadline ≈ Sep 16, 2026 / notification ≈ Jan 13, 2027（**非官方，待核**）。本组合台记录 deadline = 09-22 abs / 09-29 full（待官方修正）。

---

## 4. 评分制 + 评审标准

- **评分**：ICLR 2026 改 **{2,4,6,8,10} 五档**（删中间值 5，强迫表态）。子维度 Soundness / Presentation / Contribution 各 1-4，Confidence 1-5（2026 子维度官方表单待核，TODO）。2026 平均分 ≈ 5.39，接收率 ≈ 28%。
- **四大评审问题**（官方 Reviewer Guide）：
  1. 论文解决什么具体问题？
  2. 方法是否有充分 motivation、是否恰当定位文献？
  3. 是否支撑其 claim（理论/实验正确性与严谨）？
  4. 工作意义？是否贡献新知识？
- **关键利好**：官方明文「**缺 SOTA 结果本身不构成拒稿理由**」→ 对本论文（analysis/系统/诚实负结果）友好。
- **无强制 reproducibility checklist**（NeurIPS 有，ICLR 目前未找到 mandatory；建议自带）。

---

## 5. 行文准则（researcher 综合 Peyton Jones / ICLR reviewer guide / NeurIPS）

> 直接对应用户痛点「文字杂乱、数据文字穿插太多、标点堆砌、要写人话」。

- **R-行文1 漏斗结构**：intro = problem→gap→idea→evidence。Abstract 4 句（是什么/为什么难/怎么做/最好数字）。贡献别埋，审稿人读完 intro 已定判。
- **R-行文2 正文/表/附录分工**：正文句子只说 **key result + trend**，**不逐条复述表里每个数字**；数字多到「数眼睛」就甩进表；原始数据/超参/dead-end 消融/证明进附录。黄金标准：附录删掉论文仍成立。
- **R-行文3 一段一核心**：每段一个 claim，段首句直接写结论。**括号/分号/破折号 = 密度堆砌信号**——需要括号补充通常意味着该拆成两句或前半砍掉。ICLR 审稿人明确罚 ambiguous statement 和 logic jump。
- **R-行文4 例子先于一般**：先具体例子（一张图/一个失败案例）抓直觉，再给公式/定义。Fig.1 应是「具体失败案例 → agent 决策 → retake」示意，不是抽象流程框。
- **R-行文5 Related Work 后置**：放 method 之后（§2 或 §6 皆合法），读者先懂方法才好理解差异。

## 6. 图表准则

- **F1 概念图**：一张图只传一个核心 insight。必含数据流向（箭头一致）、模块名与正文逐字对应、关键决策点高亮其余灰化。禁 3D/阴影/背景色块/混用箭头样式。
- **F2 组图 multi-panel**：定一个叙事顺序（左→右 或 上→下，别混）；panel 标签左上角粗体 A/B/C，字号≥图内字号；拥挤/不同 scale → split，共享 scale 且同一论点 → merge；clarity > quantity；panel 间留白。
- **F3 砍废图判据**：「这图能被一句话替代吗」→ 能就砍。砍图信号：轴标不可读、元素重叠、图例要回查、与正文 claim 无直接映射。
- **F4 配色（硬要求）**：**Okabe-Ito 8 色**色盲友好（Black/Orange #E69F00/SkyBlue #56B4E9/Green #009E73/Yellow #F0E442/Blue #0072B2/Vermillion #D55E00/Purple #CC79A7）。**禁 jet/rainbow**；连续量用 viridis，偏差图用 RdBu。
- **F5 字体格式**：图内 sans-serif，字号≥正文（≥8pt，建议 9-10）；输出**矢量 PDF**；跨图统一线宽/marker/legend 位置；legend 贴数据不压角落。

## 7. 诚实负结果写法（本论文核心 framing）

- **Limitation = 可信度信号非认罪**。用 **Reflection 型**：「我们的评测受 X 假设所限；Y 条件下的结果仍是 open question，列为 future work」。禁 Confessional（求饶）/ Dismissal（轻描淡写）。
- 负结果转化：不写「我们失败了」，写「这个 negative finding 说明 X 机制在 Y 条件下不 work，原因可能 Z」。dead-end 配置进附录，主文一句带过 + 指附录。
- claim 主动限定 scope：写 "works **when** ..." 不写 "works"。审稿人发现的未披露 limitation 损害 > 作者自曝。先发制人。

---

## 关键引用

- ICLR 2026 Author Guide / Reviewer Guide / Call for Papers / Dates（iclr.cc/Conferences/2026/*）
- ICLR 2025 Reviewer Guide（评分子维度）
- Rougier et al. "Ten Simple Rules for Better Figures" PLOS CompBiol 2014
- Simon Peyton Jones "How to Write a Great Research Paper" (Microsoft Research)
- NeurIPS Paper Checklist（limitations 强制、不因诚实披露降分）
- Okabe-Ito palette（Wong 2011 Nature Methods）

## 待核 TODO（投稿前）
- ICLR 2027 官方日期（待 iclr.cc/Conferences/2027 上线）
- 官方 `iclr2027.sty` 字号/页边距精确值
- ICLR 2026 review form 子维度是否变化
