# WardAgentBench 方向菜单 · 真实交班语料 + 医生验证 → 病房 agent benchmark

> **日期**：2026-07-07
> **性质**：面谈王水花后的方向发散调研 + 候选菜单（余嘉决策存档，未拍板）
> **触发**：2026-07-07 面谈带来实质变化——医院不给大量数据，但**能做验证 + 有合作医生 + 两批稀缺资产**（① 医生盲评/纠错 ② 真实医护交互/交班语料 SBAR）。用户要「更多有亮点、别人没做过、可行」的方向。
> **调研基础**：6 个 Explore 编队并行联网（撞车复查 / venue 级别 / 架构创新空白 ×3 → 交班语料 / 医生盲评 / 跨界亮点 ×3），全带 URL，firecrawl 402 转 WebSearch。
> **前序**：`REPORT_2026-07-04_pivot_strategy.md`（pivot 决策）+ `RECON_2026-07-06_advisor_precedent_dueDiligence.md`（资源链尽调）。

---

## 一、两个资产的稀缺性（联网坐实）

- **真实护理交班语料**：全网公开的护理交班数据集**只有 NICTA 一个且是合成的**，真实去标识带标注的从未公开发布（[PMC4427705](https://pmc.ncbi.nlm.nih.gov/articles/PMC4427705/)）。→ 历史 5 次死因「只能自造交班场景」被填平（`01_STORY.md` 写明路线①复活条件 = 真实 nursing handoff/SBAR 语料）。
- **医生盲评/纠错**：现有 WHO harm 标注只用在诊断 QA（Stanford 2603.14158），没人对病房 agent 输出做后果分级。

**铁律不变**：不押架构 novelty 承重（历史被当 prompt engineering 毙 5 次），押 benchmark + 真实数据 + 真实医生验证（组合台实证：B 族全活 A 族全死）。小样本够发（标尺 Dr.CaBot [2509.12194](https://arxiv.org/abs/2509.12194) = ~5 医生 × ~29 例）。

## 二、Venue（前轮已核）

主力 **MLHC / CHIL Applications track**（★★★★ 本科一作无门槛、收 benchmark 无新方法、PMLR 归档 HYPSM 认）；冲刺 **npj Digital Medicine**（★★☆，合作医生挂通讯=障碍破，AgentClinic 等先例形状吻合）；现实 JMIR/JBHI；兜底 ML4H/AMIA。

## 三、方向菜单（12 候选筛选后，按亮点 × 可行排序）

### 第一梯队（别人没做过 + 本科半年可行）

**① WardGate — 家属 agent + 病房信息门控**（最独特）
- 把「家属」当病房正式参与角色，评测 agent 团队该不该/何时/由谁把信息（尤其坏消息）透露给家属、谁越权泄露。
- 亮点：现有病房 multi-agent 全是医生/患者/检查者，无家属角色；信息门控只在通用域成熟（SOTOPIA-TOM [2605.02307](https://arxiv.org/abs/2605.02307)），医学「坏消息门控」全空。首次搬病房+家属当 agent+医生盲评。
- 可行：30-60 病房场景 + 医生盲评披露恰当性，SPIKES 协议当锚，纯推理无训练。
- venue：MLHC/CHIL 主，隐私/门控叙事冲 npj DM。

**② HandoffLoss — 真实交班「关键信息漏传」检测**（最稳、资产最独家）
- 第一个基于真实交班语料的「上班掌握的→实际传下去的之间哪些高危信息漏传」检测 benchmark，漏传项带危害分级。
- 亮点：最接近的 MEDEC（[2412.19260](https://arxiv.org/pdf/2412.19260)）做病历「写错」非交班「漏传」，隔两层。真实交班语料+医生纠错直接当金标。
- 可行：几百条交接，纯推理评测，本科半年最稳。
- venue：AMIA/JAMIA/npj DM/ML4H。

**③ WardHarm — agent 错误的「临床后果严重度」分级**
- 医生盲评病房 agent 的告警处置/升级输出，不评对错而评「照做多严重」(无害→轻→中→重→致命)，绑定肇事角色 agent。
- 亮点：WHO harm 分级现在只用在诊断 QA，没人对病房 agent 输出做后果分级+绑角色。
- 可行：5-8 医生 × 30-50 场景，对标 Dr.CaBot，报 Cohen's κ。
- venue：MLHC/CHIL，配真实 vitals 冲 npj DM。

**④ WardAlarm — 角色感知告警解读 + 告警疲劳 benchmark**（最稳退路，数据现成）
- 同一告警护士/医生/家属得不同角色化解读；把告警疲劳（72-99% 告警无意义硬痛点 [PMC12406432](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC12406432/)）做成 benchmark——agent 能否压无用告警又不漏真报。
- 亮点：告警疲劳被硬量化但从没做成 role-aware multi-agent benchmark。
- 可行：PhysioNet/CinC 2015 公开告警（498 段带真假标签）直接起步，最不依赖私有数据。
- venue：MLHC/npj DM。

### 第二梯队（有料，但有威胁/工作量）
- **WardEscalate** 告警→护士→charge→医生→RRT 升级链 + SBAR 闭环回读：亮点足，但 arXiv 2604.27872（2026-04）在逼近同动机，须抢「真实多角色链」差异化。
- **WardDisagree** 医生-agent 分歧 taxonomy/图谱：低成本 spin-off，可当第二篇。
- **WardBlame** 多角色责任归因/audit trail：理论亮点高，但归因金标需医生逐案裁定、标注贵。
- **SBAR-Compliance** 交班 SBAR/I-PASS 结构合规自动评测：可与 ② 同语料两任务。

### 慎选（踩铁律）
- **WardDefer** 纠错驱动 deferral：方法承重、L2D 理论已拥挤（HILA/Guided Deferral），易被当增量。

## 四、融合打法（一份稀缺数据两篇产出）
- **①+② 缝一起**：真实交班语料既喂 HandoffLoss（漏传检测）又抽「披露事件」喂 WardGate（信息门控）——一份语料撑「病房信息流安全」大故事，最放大资产稀缺性。
- ②+SBAR合规 = 同一交班语料两任务。
- ③+跨开源模型安全审计 = 一个 harm 数据集两篇。

## 五、⚠️ 未决讨论（2026-07-07 用户质疑，重要）

用户质疑：「感觉都不是什么非常关键的地方，还是说这些已经足够发好的文章了」。

**诚实校准（待继续讨论）**：菜单方向本质都是 benchmark/补空白型，**不是「攻克硬问题」型关键突破**——用户直觉准。但 benchmark 型能发好 venue（AgentClinic=benchmark 发 npj DM）。**分量不来自方向本身，来自三个来源**：① 方法突破（项目死 5 次的地方，结构性够不着）② 数据稀缺性（真实交班语料=护城河）③ 一个反直觉的实证发现（benchmark 型拔高关键杠杆，如「顶级模型系统性漏传高危信息」）。

**分水岭**：只做「我评测了这个角落」= 中等 benchmark；做成「用别人没有的真实数据，揭示一个被忽视的、会伤害患者的真实 AI 风险」= 好文章。差别不在选哪个方向，在有没有一个让审稿人记住的发现。**下一步需与用户校准：要「稳的好 venue」还是「有分量让人记住」。**

## 六、立项前 Kill-shot（选定方向后必清）
- KS-A 撞车终核：逐篇精读最接近对手全文 + 中文库（万方/知网）补扫。
- KS-B 资产细节确认（用户×合作医生）：①交班语料是否含失败/次优交接样本 ②是否带可对齐 vitals/时间戳 ③医生纠错粒度是否细到「哪条信息漏了」④盲评量表/规模。
- KS-C 数据地基：复用 `src/ks3_pilot/`（告警派生，C1 共触发已 GO）+ `src/feasibility_pilot/`（四角色打分）。

## 硬资产
`src/ks3_pilot/`、`src/feasibility_pilot/`、慧脉 RAG 知识库；可复用 GitHub：AgentClinic/AI_Hospital 骨架、clinicalml deferral 代码群、PhysioNet 2015 告警数据。
