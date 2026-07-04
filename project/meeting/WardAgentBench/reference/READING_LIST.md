# WardAgentBench 领域入门阅读清单

> 用途：本科生进入「病房多角色 LLM-agent + 告警路由」领域的分层阅读路径 + 竞品对比表。为跟王水花会谈 + 立项建立领域认知。
> 日期：2026-07-04 ｜ 配套全景 = [`REPORT_2026-07-04_pivot_strategy.md`](./REPORT_2026-07-04_pivot_strategy.md)
> 诚实标注：arXiv/期刊链接均经调研核过；NEWS2 官网路径未逐一验证（RCP 偶改版面，失效就搜关键词）。

---

## Tier 0 · 先读建框架（必读，读完懂「这类论文长什么样」）

- [AgentClinic](https://arxiv.org/abs/2405.07960) — 领域标杆，把静态问答改造成多 agent 序贯环境 ｜[期刊版 npj DM](https://www.nature.com/articles/s41746-026-02674-7) ｜[站点](https://agentclinic.github.io/)
- [AI Hospital](https://aclanthology.org/2025.coling-main.680/) — 中文多角色病历交互，看评测指标怎么设 ｜[arXiv](https://arxiv.org/abs/2402.09742) ｜[代码](https://github.com/LibertFan/AI_Hospital)
- [MedAgentBench](https://arxiv.org/abs/2501.14654) — 最「部署味」，虚拟 EHR 环境 + 真实临床任务 ｜[NEJM AI](https://ai.nejm.org/doi/full/10.1056/AIdbp2500144)

> 读这三篇带一个问题：**它们评「诊断/任务对不对」，我要评「告警响了该派给谁」——差在哪？** 这就是切入点。

## Tier 1 · 直接竞品 / 切割对象（会谈要能一句话说清差异）

- [Agent Hospital](https://arxiv.org/abs/2405.02957) — ⚠️ 唯一已有「护士 agent」，但护士=**分诊导科**非**告警响应**，要能说清区别
- [PSEBench](https://arxiv.org/html/2606.05463) — 近邻：文本安全事件「要不要上报」，已核实不做角色路由
- [Emergency Triage Benchmark](https://arxiv.org/abs/2509.26351) — 近邻：生命体征「会不会恶化」预测，也不做角色路由
- [MedAgentAudit](https://arxiv.org/abs/2510.10185) — 多 agent 协同失败分类学
- [MedAgentSim](https://arxiv.org/abs/2503.22678)（MICCAI 2025）— 自进化多 agent ｜[代码](https://github.com/MAXNORM8650/MedAgentSim)
- [DischargeSim](https://arxiv.org/pdf/2509.07188) — 家属/患者端相邻场景
- [MedAgentsBench](https://arxiv.org/html/2503.07459v1) — 难推理题 benchmark

> 读完要能说：**现有工作全停在「判什么」，没人做「派给谁」。** 这是你的护城河。

## Tier 2 · 临床 + 告警地基（你 benchmark 的「标准答案」从哪来）

- [NEWS2 早预警评分（RCP 2017）](https://www.rcp.ac.uk/improving-care/resources/national-early-warning-score-news-2/) — 你 benchmark 的 ground truth 就是它的评分函数，必读懂（失效搜 "RCP NEWS2 2017"）
- [AAMI 临床告警管理](https://array.aami.org/doi/full/10.2345/0899-8205-51.2.109) — 护士→主治→快速反应团队 RRT 升级链，你「角色路由」的临床依据
- [GE 告警管理白皮书](https://clinicalview.gehealthcare.com/white-paper/alarm-management-white-paper) — 产业侧告警管理实践
- [AI-TEW](https://www.nature.com/articles/s41746-026-02522-8)（npj DM 2026）— 分层减误报，看告警领域现在做到哪

## Tier 3 · venue / 写法范式（投稿时细读）

- [CHIL CFP](https://chil.ahli.cc/submit/call-for-papers/) — 主力 venue，看 Applications & Practice track 收什么
- [JMIR Human Factors](https://humanfactors.jmir.org/) — 腿2 usability 论文范式 + checklist
- [AMIA Student Paper Competition](https://amia.org/about-amia/amia-awards/research-awards/amia-student-paper-competitions) — 本科兜底

## Tier 4 · 元视角（建立「为什么这方向有意义」的大局观）

- [Stanford HAI real-world benchmark](https://hai.stanford.edu/news/stanford-develops-real-world-benchmarks-for-healthcare-ai-agents) — 医疗 AI「落地鸿沟」痛点，整个 pivot 的立论根基
- [LLMs in Real-World Clinical Workflows 综述](https://www.medrxiv.org/content/10.1101/2025.06.10.25329323v1) — 真实部署有多稀缺（=你的稀缺性优势）｜[PMC](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC12519456/)

---

## 🎯 竞品对比表（一眼看清 novelty，会谈可直接用）

| 工作 | 角色组合 | 输入 | 评测什么 | 告警→角色路由 |
|---|---|---|---|---|
| AgentClinic | 医生/患者/检查/主持 | 问诊对话 | 诊断准确率 | ❌ |
| AI Hospital | 医生/患者/检查/主任 | 中文病历交互 | 症状采集/检查/诊断 | ❌ |
| MedAgentBench | EHR agent | 虚拟 FHIR/EHR | 300 临床任务完成度 | ❌ |
| Agent Hospital | 医生/患者/**护士** | 全流程模拟 | 诊断能力自进化 | ❌（护士=分诊非告警）|
| MedAgentSim | 医生/患者/测量 | 多轮问诊 | 自进化诊断 | ❌ |
| DischargeSim | 医生/患者 | 出院教育对话 | 出院沟通质量 | ❌ |
| PSEBench | 无临床角色 | 文本安全事件 | 要不要上报（合规分诊）| ❌ |
| Emergency Triage(2509) | 无角色 | 生命体征结构化 | 会不会恶化（预测）| ❌ |
| MedAgentAudit | 同质医生 agent | 6 仿真集辩论 | 协同失败分类 | ❌ |
| AI-TEW | 无 agent 角色 | ED 数据 | 分层减误报 PPV | ❌ |
| **★ WardAgentBench（我们）** | **医生/护士/家属/患者** | **生命体征告警 + 多角色信息** | **告警响后该派给谁响应** | **✅ 唯一** |

> 命门已核实（2026-07-04 读两篇近邻全文）：最后一列「告警→角色路由」这把尺子无人造过 → 腿1 创新点成立。收窄措辞用「响应分派 / role routing」轴，与「事件上报分诊」「恶化预测」划清界限。

---

## 读法建议（本科刚进领域最有效）

1. **先扫不精读**：Tier 0 三篇先看 abstract + 图 + 评测指标表，建「多角色 benchmark 长什么样」的直觉。
2. **带切割问题读 Tier 1**：每篇问「它做了什么、没做什么、我补哪块」——直接变成 related work 和会谈说辞。
3. **Tier 2 当工具书**：NEWS2、告警升级链查着用，不用一次读完。
4. **对比表随手更新**：读到新论文就往上表加一行——填满这张表，你对领域的掌握就够跟导师对话了。
