# WardAgentBench 战略转向项目报告

> **日期**：2026-07-04
> **性质**：立项方向 pivot 决策报告（用户拍板批准，plan = `~/.claude/plans/enchanted-sparking-lampson.md`）
> **一句话**：慧脉守护科研转化放弃「方法 novelty」路（5 次验证收敛 workshop 天花板），转 **benchmark + 真实医院 deployment/usability 双线**——核心推动力是本轮调研坐实用户手里握着一条**院长挂帅的 AI 医疗平台 + 苏州本地三甲医院通道 + 方法/统计/通讯背书 + 同校本科一作先例**的完整资源链。
> **调研基础**：6 个 Explore/researcher 编队并行（项目资产盘点 / AgentClinic 家族文献 / venue 形状 / 三人物背景 / 苏大附二院 / 孟佳+院长）。
> **面向读者**：余嘉本人决策存档 + 可用于与导师（王水花/孟佳）、院长（Moraros）沟通的材料底稿。

---

## 一、执行摘要（一页看懂）

**从哪来**：慧脉守护是一套基于开源医疗大模型拼装的病房多角色 LLM-agent 系统（demo + 系统设计，零真实临床数据/零 IRB/零自研模型）。此前想做「方法 novelty」科研——四角色交接失败分类学 → 多告警复合误报 e-value 校准 benchmark，**5 次独立验证全部收敛到 workshop 天花板**。最后一次真跑数据实证坐实：四角色分布作为「被打分能力」不承重（274 场景，A对B错 40 = A错B对 40，完全对称 = 分布是加噪不是承重信号）。

**卡在哪**：所有「方法新」的路都被杀，因为底层是单一开源模型被 prompt 扮多角色，「角色特有失败」与 prompt 工程完全混杂；而项目**最大的独特资产（本科生 × 真实医院落地沟通）一直没用上**。

**转去哪**：换**贡献类型**——不卖方法新，卖「真实世界系统 + 落地证据 + 可复现 benchmark」。这条路审稿人不要求方法新，而领域文献坐实 AgentClinic 这类顶会 benchmark 的创新点**全是 benchmark/环境本身**，本科生够得到；且现有家族全是 doctor/patient 组合，**护士端 + 家属端 + 告警联动是全空白**——这正是慧脉系统的形状。

**为什么现在能成**：调研发现用户的资源不是散的，是一条**已经打通的链**——理学院院长 John Moraros 本人是 AI4Health 苏州市重点实验室主任（论文完美挂靠平台）、王水花已对接苏大附二院（苏州本地三甲，ICU/心内/呼吸/神外全是重点专科，2024 公开征集智能监护 AI 方案）、王水花×孟佳已合作、同校已有本科一作医疗 AI 论文先例（Liu Yiheng）。

**目标**：本科生一作，服务 HYPSM 直博申请。定位关键——**推荐信 > 论文名气**；医疗 AI 圈「benchmark 高分 ≠ 临床能用」的落地鸿沟是公认痛点（Stanford HAI 专门在推 real-world benchmark），所以对 clinical AI / medical informatics / human-centered AI 方向的导师，「真实落地 + 中等 venue」的说服力可能高于「纯 benchmark + 好 venue」。论文只需证明「能把事做成体系」，落地经验当 SOP 主线 + 推荐信素材。

---

## 二、项目现状诊断：为什么必须转向

### 2.1 方法 novelty 路的死亡记录（5 次收敛）

| 时间 | 关口 | 结论 |
|---|---|---|
| 2026-07-02 立项 | 4-agent 核实 | demo 原型零真实数据/IRB；首选失败分类学撞 MedAgentAudit，顶会 novelty 路基本堵死 |
| 2026-07-02 KS-1 | skeptic 选路红队 | 路线①（四角色交接失败实证）判**致命**——公开数据结构性不支撑（MedDG 是医患对话无护士/家属/SBAR），失败=prompt 设计产物 |
| 2026-07-02 升级 | 大编队冲一区 | 转候选 B（多告警复合误报 e-value 校准 benchmark） |
| 2026-07-02 pilot 自审 | 2 researcher 核 | 候选 B pilot 方法学三处全错（测错轴/循环标签/粗基线），负结论作废——方向没被证伪但也没被证实 |
| 2026-07-02 arc 终结 | 3 次独立验证 | benchmark 贡献真但 novelty≈0（e-detector/WCTM 现成）+ 框架拥挤 + 2603.13156 近身撞车 → workshop 天花板 |
| 2026-07-02 reframe 真跑 | 274 场景真 Qwen-3B | **方向性 NO-GO**：A/B escalate 0.507=0.507、A对B错40=A错B对40 对称 → 四角色分布不承重 |

**根因（记 memory [[claim_shape_decides_birth_difficulty]] / [[benchmark_is_optimal_strategy]]）**：A 族「大胆 novelty 押命门」项目全死，B 族「benchmark/empirical」全活。慧脉一直在 A 族硬撑，且始终没动用真实落地资产。

### 2.2 但留下了硬资产（不白跑）

- **两条 pilot 管道**（都主线真跑跑通，可复现）：`src/feasibility_pilot/`（四角色 A/B + NEWS2 指南真值 + 精确匹配打分 + rank-flip 护栏）、`src/ks3_pilot/`（Chromik 式波形→阈值告警派生 + 共触发 + phi 相关）。
- **关键数据发现**：PhysioNet 三库（mimic3wdb / matched / challenge-2015）**全 Open Access 无需 CITI**（原 2 周办证假设作废）。
- **慧脉 RAG 知识库**：指南~500 / 药物~3000 / ICD-10~14000（公开源整理，可作指南真值）。
- **完整纪律链**：命门先行、负结果先核测法、防循环/防 artifact 护栏。

---

## 三、领域定位（文献确认，2026-07-04）

### 3.1 AgentClinic 家族——创新点全是 benchmark 本身，本科可复制

| 项目 | 机构/一作层级 | Venue | 创新形状 | 角色组合 |
|---|---|---|---|---|
| AgentClinic | JHU 博士生 | npj DM 2026 | benchmark | doctor/patient/examiner |
| AI Hospital | 阿里 | COLING 2025 | benchmark + 协作方法 | doctor/patient/examiner/chief |
| MedAgentBench | Stanford | NEJM AI | benchmark（部署味重） | EHR agent |
| MedAgentsBench | Yale | 2025.03 | benchmark | 多步推理 |
| MedAgentSim | — | MICCAI 2025 oral | 方法（自进化） | doctor/patient/measurement |
| DischargeSim | — | 2025.09 | benchmark | doctor/patient |

**空白确认**：现有家族全是 doctor/patient(/examiner)。**护士端、家属端、生命体征告警联动 = 全空白**。这是可立的**覆盖度 novelty**（不是方法 novelty）。

### 3.2 主要竞品（需 related-work 主动切割）

- **MedAgentAudit**（2510.10185）：~6 类协同失败分类，同质医生 agent，**非四角色** → 切「无真实部署/无护士家属角色」
- **AI-TEW**（npj DM 2026）：两阶段分层减误报，按**风险**分层 → 切「我们按角色路由，做告警→响应角色，非降假阳」
- **PSEBench**（2606.05463）：文本患者安全事件分流 → 与生理体征告警不撞
- **MedAgentBrief**（Stanford 真实住院部署）：做出院小结非多角色分流

### 3.3 novelty 切割核实结论（researcher 2026-07-04）

- **切割点 A（角色覆盖度）= 成立但须收窄措辞**：现有家族确无「护士+家属+告警」三者组合。**但**「护士 agent」本身已被做——Agent Hospital（2405.02957）含护士 agent（职能=分诊导科**非**告警响应，且无家属/告警联动）；AgentClinic/MedAgentBench 把护士明确列 future work。→ headline **不能** claim「首个护士角色」，novelty 落在「**护士+家属+告警驱动角色路由的组合评测**」，related-work 须显式区分 Agent Hospital 护士职能。
- **✅ 切割点 B（告警→角色路由评测）= CLEAN（2026-07-04 读两篇全文核实）**：两个近邻 benchmark 都**只做「判什么」不做「派给谁」**，与 headline 正交：
  - **PSEBench**（2606.05463）：文本安全事件→**要不要上报**（合规分诊），无生理告警、无角色路由。其「role」是评测机制的 LLM/oracle 非临床岗位；「escalation」=灰区标 Uncertain 非升级给角色。
  - **2509.26351**：生命体征→**会不会恶化**（ICU转入/院内死亡二分类预测），LLM 仅用于建数据集非被测 agent，无 escalation 无角色路由。（注：前序 researcher 误标此篇为"uncertainty-aware escalation"，读全文证实该词不出现——描述有误但增强 CLEAN。若 STORY 要对标真带该词的急诊分诊论文需回传正确 arXiv ID。）
  两篇都停在**分类判定层**，没有下一跳「派给护士/主治/RRT」——这正是 headline novelty 承重点。**角色分级路由概念本身临床成熟（AAMI/GE/Philips nurse→charge→physician→RRT 升级链），故 novelty 落「可复现评测协议」不落「概念首创」。** 收窄措辞：用「响应分派/角色路由 response dispatch/role routing」轴，与「事件上报分诊」「恶化风险预测」划清界限。

---

## 四、资源链盘点（本轮最重要的发现）

**结论：不是散资源，是一条已打通的链。**

### 4.1 六个节点

| # | 节点 | 能给什么 | 成色（诚实分档） |
|---|---|---|---|
| 1 | **AI4Health 苏州市重点实验室**（院长 John Moraros 任主任，2024 成立） | 论文挂靠平台 + 院长背书；scope 明确含「医疗交付优化/预测分析」，字面覆盖病房 agent+告警 | ✅ 有明确证据 |
| 2 | **苏大附二院**（王水花对接，苏州本地三甲，2600 床） | ICU/心内/呼吸/神外全是重点专科（病房告警场景齐全）；2024 公开征集智能监护 AI 方案；伦理委成熟（18 委员，涵盖涉人研究） | ✅ 场景真实，B 级最现实 |
| 3 | 太和医院（Moraros+孟佳 2025.1 已访、筹建合作基地） | 第二条临床通道 | ⚠️ 湖北十堰、偏肿瘤组学，次要 |
| 3b | 瑞金医院（XJTLU 2025.12 瑞浦智慧医疗研究院，全国第4 顶级三甲）| 顶级背书 + ICU 国家重点专科 | ⚠️ **慧湖药学院主导、方向新药/慢病、与王水花/理学院无关联**；AI 合作方全华为/商汤大厂本科权重低 → **仅当背书生态背景，不 claim 已获资源**（未落实写了失实）|
| 4 | **王水花**（生科系副教授，连续 5 年高被引，Info Fusion 副主编） | 医学影像 ML 方法学顾问 + 高通讯背书 + 苏大附二院人情通道 | ✅ 背书稳；⚠️ 无 LLM-agent 经验、无真实医院 IRB 队列历史（agent+部署活学生扛） |
| 5 | **孟佳**（生科系教授兼系主任，MIT/Broad 背景，ORCID 0000-0003-3455-205X） | 统计/生信/临床 AI 建模方法论（专利全是唐氏筛查 Swin-Transformer 这类"医疗数据→模型→benchmark→专利"）+ 系主任调动力 + 高通讯背书 | ✅ 方法+背书；⚠️ 企业合作（川昕生物/苏州精准医疗）证据薄弱，别当数据/算力来源写死 |
| 6 | **同校本科一作先例**：Liu Yiheng（RS-CNN 乳腺癌分类，发 *Comput Struct Biotechnol J*，SURF，Moraros 背书） | 证明「本科一作医疗 AI 论文」同校同院长可达 | ✅ 有明确先例 |

**链的拓扑**：AI4Health 实验室的 Theme Leaders 名单里，王水花 + 魏振（孟佳合作者）都在；2025.1 Moraros + 孟佳一起访太和医院。→ 院长 + 系主任 + 王水花 + 一条医院通道**已经被同一个平台串在一起**。用户要促成的「资源联合」是往一个**已存在的平台**里放项目，不是从零撮合。

### 4.2 自有硬资产

慧脉系统设计 + 可跑 demo（`wardlungcompass.top` / repo `ZXZ12310304/wardlung-composs-v2`）+ 两条 pilot 管道 + RAG 知识库。**注意隐私清洗**（商业计划书目录含学生证/证件照，转公开物前必清）。

### 4.3 苏大附二院三档可达性（决定天花板）

| 档 | 能拿到 | 现实性 | 前置 |
|---|---|---|---|
| **A** 真实监护数据/EHR 队列（deployment 研究） | ICU/心内/呼吸 waveform + EHR 回顾队列 | ⚠️ 偏低，本科周期高风险 | 院内 PI 立项 → IRB（涉人研究 1–3 月，回顾去标识可申豁免知情同意）→ 数据协议（常要求院内网分析）→ 总 3–6 月起 |
| **B** 真实场景 + 医护 usability/访谈 | 真科室 agent 原型可用性测试 + 告警需求访谈 + workflow 观察 | 🎯 **最现实、性价比最高**，1–2 月启动 | 最小风险 IRB（访谈/问卷/可用性，常快审或豁免）+ 5–15 名医护 + 知情同意；**无需病人数据导出** |
| **C** 临床顾问/背书/需求访谈 | 科室主任做顾问 + 确认需求 + 共同署名 | ✅ 几乎必达 | 需求访谈 + 顾问关系，无需 IRB |

**真正的卡点不是医院资源，是：导师对接有没有落到苏大附二院某个具体科室的一位愿挂名 PI**（本科生不能独立申报 IRB）。这决定 B/A 能否启动。

---

## 五、最终方向：三腿骨架

**Headline**：一个开源可复现的**病房多角色（医生/护士/家属/患者）协同 + 生命体征告警→角色路由**评测 benchmark，配一个在**真实三甲医院（苏大附二院）**做的医护 usability/需求验证，挂靠 **AI4Health 苏州市重点实验室**。

### 腿 1 · Benchmark（保底承重，纯公共数据，不依赖任何人）
填两个空白：①角色覆盖度（护士/家属没人做）②**「告警降假阳之后→路由给谁响应」评测协议**（告警融合工作只做降假阳，不做角色响应）。数据用公共 MedQA + PhysioNet/CinC 2015 + 慧脉 RAG 当指南真值。复用 `feasibility_pilot` 管道骨架。
> ⚠️ **claim 重定**：不得 claim「四角色分布揭示新失败」（pilot 已证伪）；重定为「**覆盖度 benchmark + 告警-角色路由评测协议**」，家属/护士轴须**过采样专测**（现仅 8 例欠采样）。

### 腿 2 · 真实医院 Usability（升级，B 级，最大化落地叙事）
苏大附二院真实科室（ICU/心内/呼吸/神外）做 agent 原型医护可用性测试 + 告警需求访谈 + workflow 观察。5–15 名医护，公共/合成数据驱动 agent，真实性来自「真医院真医护验证」。走最小风险 IRB，无需病人数据导出。

### 腿 3 · 系统/部署经验（差异化护城河，QI 框架无需 IRB）
慧脉系统架构 + 落地协调经验 + lessons learned，框成 QI（质量改进）/deployment context。

**组合打法**：腿1 保证一定有 paper（不依赖任何人）→ 腿2 把纯 benchmark 升级成「benchmark + 真实场景 human factors」→ 腿3 差异化 + SOP 叙事。

---

## 六、venue 形状与目标

**本科 + 真实落地故事最对口的形状（门槛低、最大化独特资产）**：

| 形状 | 投哪 | 要什么 | 本科可达 |
|---|---|---|---|
| Systems/Deployment（架构+经验教训） | **CHIL "Applications & Practice" track**（字面 "bridging the deployment gap"）/ AMIA | 系统架构+部署经验，无需病人数据 | ★★★☆ |
| Usability/Human-Factors | **JMIR Human Factors** | 真实医护用户反馈（去标识、多 IRB 豁免） | ★★★★ |
| AMIA Systems Demo + Student Paper | AMIA（Student Paper 本科专属竞赛） | 能跑 demo + 短文 | ★★★★ |
| Benchmark descriptor | CHIL / MICCAI / NeurIPS D&B / ML4H | 公开数据集/基准 | ★★★☆ |
| 兜底 | JMIR Formative Research（feasibility）/ JMIR Viewpoint | 低门槛 | ★★★★ |

**够不到（本科一作无先例，别当主贡献）**：Nature Med / npj DM / Lancet DH 级真实部署 RCT——需资深临床 PI + IRB + 大样本。可作 case study 的「未来工作」提一句。

**目标 venue 确切信息（researcher 2026-07-04）**：

| Venue | 截止 | 页数 | APC | 归档 | 收我们形状 |
|---|---|---|---|---|---|
| **CHIL 2027**（主力·腿1+3） | 2027 未发，参照 2026=2月初 `TODO临近再查` | 8–10 页 | 免费（PMLR OA） | ✅ PMLR | Applications & Practice track 明收 datasets/benchmarks/evaluations，「引入新方法非必需」 |
| **JMIR Human Factors**（腿2·usability） | 滚动无截止 | 无硬限 | **$1985** | ✅ DOAJ/PMC | 收 usability + 原型评测；审稿平均 ~12 周，fast-track 20 工作日出决定 |
| **AMIA 2027**（兜底·demo+student） | 2027 约 3 月 `TODO` | 论文≤8–10 / **Demo 1 页** | 免费投稿 | ✅ PubMed | Systems Demo 要写「部署程度」；**Student Paper 本科符合**（degree-granting program），须个人独立完成 |
| **JMIR Formative**（保底·feasibility） | 滚动无截止 | 无硬限 | **$2500** | ✅ DOAJ/PMC | feasibility/pilot/开发期评测 |

遗留 TODO：CHIL/AMIA 2027 确切截止（CFP 未发）；JMIR 各刊接受率（官方未公开）。

**合规红线（QI vs Research 分界，依 HHS OHRP 45 CFR 46）**：
- ✅ 可写无需 IRB：系统架构、部署协调过程、lessons learned（无病人数据）；框成本地 QI 的运行数据；医护 usability 反馈（最小风险，多豁免/快审）。
- ❌ 必须先 IRB：真实病人可识别数据/结局数据做可泛化科学声称；任何 PHI；用真实病人交互记录做模型评测并声称泛化。

---

## 七、命门 / 风险 / 前置

1. **命门·腿2 能否启动**（真正卡点）：导师对接须落到苏大附二院某具体科室一位愿挂名 PI。若只是院方泛泛认识 → 先落到具体科室。
2. **命门·腿1 novelty**（🔴 headline 定稿前必清）：切割点 A 成立但须收窄（不 claim「首个护士角色」，落「护士+家属+告警组合路由」）；**切割点 B 存疑**——**动笔前必读 PSEBench（2606.05463）+ Emergency Triage Benchmark（2509.26351）全文**确认其评测轴未触及「告警→角色路由」，否则 headline 撞车。角色路由概念本身临床成熟不 novel，novelty 只能落「可复现评测协议」。skeptic 红队 0 致命即过。
3. **诚实约束**（沿用 R-rules）：开源模型文献值明标「引用非自测」；不夸大两院意向函 / 不声称「已真实部署」；隐私清洗；孟佳企业合作不当数据来源写死；held-out 不泄漏。
4. **周期风险**：A 级 IRB+数据协议 3–6 月，可能拖过本科毕业时间线 → 不押 A 级作成败关键，作机会性加分。

---

## 八、行动路线图

### 用户线下（决定腿2天花板，最优先）
- [ ] 确认苏大附二院对接的**具体科室 + 哪位医生 + 是否愿做合作 PI**
- [ ] 确认能否挂靠 AI4Health 实验室（Moraros）+ 王水花/孟佳署名分工

### 我方软活（腿1现在就能开工，不等医院）
- [ ] 改档案 pivot：00_README / 01_STORY / 02_ACCEPTANCE / registry（status→planning，venue→CHIL App/JMIR HF/AMIA）+ 04_LOG entry
- [ ] planner 出腿1 benchmark 实验矩阵（覆盖度维度 + 告警-角色路由评测协议 + 家属轴过采样，对齐 ACCEPTANCE）
- [ ] coder 改 `feasibility_pilot`：重定 claim 为覆盖度+路由，加家属/护士轴过采样专测子集
- [ ] writer 起草腿2 usability 研究设计 + 医护访谈提纲 + 最小风险 IRB 材料模板（供用户带给科室 PI）
- [ ] researcher 补 venue 确切截止 + related-work 切割核实（进行中）

---

## 附录 · 关键 URL

- AI4Health 实验室：https://www.xjtlu.edu.cn/en/study/departments/school-of-science/labs-and-spaces/
- John Moraros 领导页：https://www.xjtlu.edu.cn/en/about/people/leadership/professor-john-moraros
- 王水花 scholar：https://scholar.xjtlu.edu.cn/en/persons/ShuihuaWang ｜ 孟佳：https://scholar.xjtlu.edu.cn/en/persons/JiaMeng/
- 苏大附二院伦理委员会：https://www.sdfey.com/gfb/llwyh.html
- 苏大附二院 AI+医疗供需对接会（2024-05）：https://kxjst.jiangsu.gov.cn/art/2024/5/23/art_82538_11252026.html
- 理学院访太和医院（Moraros+孟佳）：https://www.xjtlu.edu.cn/en/news/2025/01/xjtlu-school-of-science-visits-taihe-hospital
- 本科一作先例（RS-CNN）：https://www.xjtlu.edu.cn/en/news/2025/06/xjtlu-undergraduate-developed-innovative-ai-diagnostic-tool
- AgentClinic：https://arxiv.org/abs/2405.07960 ｜ AI Hospital：https://aclanthology.org/2025.coling-main.680/
- CHIL CFP：https://chil.ahli.cc/submit/call-for-papers/ ｜ JMIR Human Factors：https://humanfactors.jmir.org/
- 前序侦察：`reference/RECON_2026-07-02_venue_niche.md` + `reference/LANDSCAPE_2026-07-02.md`

---

*本报告综合 6 编队调研，是 WardAgentBench pivot 的决策依据存档。数字类结论以各 pilot csv（Bash 可核）+ 官方源为准；标「待核/TODO」处为未一手确认，勿越级引用。*
