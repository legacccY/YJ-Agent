# WardAgentBench — LOG

## 2026-07-07 · 🧭 新方向探索 WardRouteGov「双轨路由守门员」→ 🚦killshot 揭「记忆点半」数据封死，建议退步重估

**触发**：用户对旧候选 B + 07-07 菜单不满，要「非常重要、后人复用、没人做过、让审稿人记住」的方向；灵感=Claude Code 高级编排 / 真实病房痛点。全景决策档 `~/.claude/plans/project-claudecode-agent-woolly-shore.md`。

**过程（3 轮研究编队 + 用户 4 次纠偏）**：
- v1 drift 被否（WardEscalate/WardHandoffDecay 把多 agent 平台压扁成单任务 eval）；v2 平台中心（R1 坐实「评临床 agent **编排层本身**=基本空地」，最近邻 MedCTA 单 agent/HAO·TAO 系统非 bench）；v3 架完整方向。
- 用户拍定交付物形状：①**agent 平台不能丢**（多 agent 编排当研究对象）②**不做 benchmark，能力/机制当主角**（applied-systems，组装已知技术，不 claim 新算法）③**公开数据主承重 + 医院验证层**④**4B+守门框架打赢最先进大模型 + MedGemma-27B，且大模型须单体强过 4B**（隔离框架贡献，制胜模板 LENS-01 形状）。
- 收敛方向 **WardRouteGov**：给慧脉双轨告警调度器镶「路由安全 governor」（acuity-aware re-routing + admission control，用 conformal/risk-coverage/NEWS2 趋势），破「固定阈值下压假必漏真」死局。

**硬证据（复现编队 3 簇真跑）**：
- **过升级/告警疲劳半=铁证**：Drew 2014 心律失常告警 88.8% 假、室速/室颤最假；agent 218 条 CinC-2015 真复现「压假必漏真」trade-off（零漏真只能压 10% 假 / 压 74% 假必静音 24% 致命真报警）。数据全开放（CinC-2015/VTaC CC BY-SA/mimic3wdb ODbL）。
- **SOTA 靶=VTaC 官方 split AUC 0.949**；「便宜/小模型赢 LLM」已被 **OpenTSLM(2510.02410)** 做过 → novelty 不能押它，须押「路由/升级决策」面。
- **工具就绪**：killshot_w 接 OpenRouter 通（Nemotron-120B/Gemma-4-31B 免费模型响应，Llama/GPT-OSS/Qwen 免费版被上游 429）；MedGemma HF token 验通、门禁已过可下。

**🚦 killshot（命门先证伪，主线亲跑）**：
- v1 静态 NEWS2 探针**测错轴**（测瞬时多参数轻度异常，非趋势；用户拦下）→ 重建**趋势+时间解耦结局+置换检验**版。
- **揭深层真障=人群错配**：安静高危/欠升级半在 mimic3wdb 上，ICU 病人全 loud（85% 窗口 loud，连安静平稳者未来危急率也 0.815）——ICU 里根本没有病房那种「安静恶化」。「安静上升」组 0 窗。
- 查证到底：**开放病房（非 ICU）恶化数据集不存在；连 MIMIC-IV（要 CITI）都无 ward 频繁体征**（官方明说 frequent vitals 仅 ICU，hosp 模块 ward 无系统体征）；结构性数据荒（病房 4-8h 人工间歇抄表）。Ward2ICU(1910.00752) 是合成。

**结论（诚实，未消费立项，STORY/ACCEPTANCE 未改）**：
- 「记忆点半」（安静病房恶化/afferent limb failure）现象文献为真（60% 恶化前 4h 有异常），但**可得数据封死、CITI 都救不了 → 发不成 paper**。
- 能做的：过升级/告警疲劳半（ICU 数据可做但中等老赛道）；beat-LLM（已被 OpenTSLM 做）。「让审稿人记住」bar 在此盘子+可得数据上够不到。
- **建议 ③：退步把慧脉跟其他项目（QuantImmu 等）重估**；或清醒收「告警疲劳守门员」中等版（JMIR/JBHI）。降采样 ICU→病房代理=创意但站不稳（人群不迁移），不敢押。
- **留底资产**：killshot_w OpenRouter 接线 + 复现的告警疲劳硬证据 + 趋势 killshot 方法论（scratchpad/news2_trend_probe.py）+ 决策全景 plan。
- **⚠️ 安全**：用户 OpenRouter/HF key 存 `src/killshot_w/.env`（gitignored），提醒用完 rotate。

**过程价值**：几小时（非几个月）证伪了方向的承重前提=「命门先证伪」纪律生效，未让用户为拿不到数据的方向砸整学期。

---

## 2026-07-06 · 🔍 面谈前尽调（导师画像 × 本科先例 × 资源链）→ `reference/RECON_2026-07-06_advisor_precedent_dueDiligence.md`

**触发**：用户明天与王水花面谈慧脉科研转化，要求联网核实「王水花有没有类似文章 + XJTLU 有没有本科先例 + AI4Health/孟佳/Moraros/附二院链成色」，做成详细分析 md。派 3 researcher 并行核实（全带 URL）。

**三大发现**：
1. **王水花 = 跨域挂名背书非对口内行**：静态医学影像 CNN 分类/分割 + 信息融合的连续高被引（h≈85-96），与慧脉四支柱（LLM-agent/生理波形告警/部署 usability/benchmark 构建）**基本零交集**。她能给通讯声望 + 通用 ML 把关 + 实验室席位 + 医院人情，**给不了核心方法内审**。
2. **本科先例仅 1 例且不背书这条路 + 重要更正**：Liu Yiheng（2025 CSBJ Q2，DOI 10.1016/j.csbj.2025.05.051）是**方法+应用**型、通讯是**黄夏 Xia Huang**、**王水花/孟佳/Moraros 均非作者**（Moraros 仅背书露面）。→ 之前 pivot 报告「Moraros 背书的先例」说法名不副实，已在新报告更正。走 benchmark/deployment 路的本科先例**零命中**。
3. **资源链平台真、对口薄**：AI4Health 实验室真实（2024、Moraros 主任），**王水花在 Theme Leaders 名单 = 最强正面支点**；但 Moraros/孟佳只提供平台+背书+行政力（不做 AI/agent）；孟佳不在实验室名单；**附二院公开 AI 需求不含病房监测、XJTLU×附二院既有合作查无实据**。

**对明天的含义**：会的本质=「用她的实验室席位+通讯声望+医院人情，把我一个人做得出的 benchmark 升级成有真实落地背书的东西」，非「让内行审方向」。必问三红：①医院能否落到具体科室具体人 ②署名锁本科一作+要不要走 SURF ③AI4Health 挂靠。措辞红线：别说已真实部署、别把两院意向说成已获资源、别把 Liu Yiheng 说成王水花/Moraros 成果。

**7 条 TODO 待人工复核**（王水花部署论文/第二本科先例/SURF 细则页 404/孟佳本科一作/XJTLU×附二院合作/附二院病房监测需求/伦理委是否受理 AI）。

---

## 2026-07-04 · 🧭 路 W' probe（制胜模板 LENS-01 适配评估 → $5 kill-shot 就绪待 key）

**触发**：用户问「慧脉守护适不适配制胜模板 LENS-01，灵活举一反三」。派 Explore 挖全档 + researcher×2（三候选角落撞车 + 终核）。评估档 `~/.claude/plans/inherited-hopping-boot.md`。

**结论（三层）**：①完整模板**不适配**——慧脉 07-04 pivot 明确「不 claim 方法新、卖真实落地」正是模板反极；缺 S4（唯一模型实验弱 Qwen-3B 对称 null 40=40）、缺 S5（无打爆 SOTA 支架）。②模板反而是慧脉 5 次难产的**最佳诊断透镜**：反复踩 S3（承重贡献总需不存在/无效金标）。③**举一反三唯一活口=路 W'**：保域+公开数据，换到「前沿 MLLM 读原始生理波形判 ICU 警报真假」——PhysioNet2015/VTaC 有专家 true/false 金标（客观、连标注都省），项目从没拿前沿 MLLM 读过波形（只跑弱 Qwen-3B）。

**researcher 三角落判定**：角落1（波形判警报真假）🟢benchmark 槽空（终核 16 组检索+5 PDF，覆盖 2026H1，无抢跑）；角落2（LLM 数值时序推理）🔴HEARTS 2026-06 已填；角落3（ECG QA+符号支架）🔴ECG-QA/PULSE/HeartLLM 饱和。**头条必改**：经典 SOTA 已 0.96 挡死「SOTA 暴涨」→改「安全攸关任务前沿 MLLM 灾难失败 + 廉价信号符号支架补差距」；**方法不 claim novelty**（VitalAgent/HeartLLM 已有支架形状，与本项目铁律一致），价值全在 benchmark/empirical 应用交集。

**用户拍板路线 A**：不推翻 07-04 pivot，先跑 $5 kill-shot 验路 W' 是活是死，再定旗舰（路 P 稳 / 路 W' 搏 / 并行）。

**本轮做（管道全就绪，实测非 mock）**：建 harness `src/killshot_w/`（config/download_data/build_inputs/run_models/score）→ 下 30 条 challenge-2015（5 类 × TRUE/FALSE 各 3，全含 ECG II+脉动波，17MB，免 CITI，`data/challenge2015_killshot/`）→ 建 30 文本+30 波形 PNG（金标零泄漏，实测 grep=0）→ dry-run 240 调用（30×2 表征×4 模型，cost 顶 300，缺失 0）。修一 bug（`dl_database` 版本号拼重 404→改直连 physionet.org/files 下载）。

**🔴 卡点**：等用户放前沿 API key 进 `.env`（OPENAI/GEMINI/ANTHROPIC，≥1 即可）。到位后：装 SDK + 核模型快照名（config TODO4）→ run_models + score → 准确率 vs naive/0.8139/0.96。判据：显著低于 naive 或 <0.65 且缝无抢跑=路 W' 活；接近经典=路 W' 死。**N=30 是筛子非 benchmark，别当定论**。

---

## 2026-07-04 · 🔀 PIVOT（用户拍板）：弃方法 novelty 路 → benchmark + 真实医院 deployment/usability 双线

**触发**：用户提出转向——不纠结「多角色分布承不承重」（已 5 次证死），改把**本科生 × 真实医院落地沟通**当独特资产，问领域相似项目怎么发文章。派 6 编队并行调研（项目资产 / AgentClinic 家族文献 / venue 形状 / 三人物 / 苏大附二院 / 孟佳+院长），出 pivot 决策，用户 ExitPlanMode 批准（plan=`~/.claude/plans/enchanted-sparking-lampson.md`）。**全景报告=`reference/REPORT_2026-07-04_pivot_strategy.md`**。

**核心转向**：换贡献类型——不卖方法新，卖「真实世界系统 + 落地证据 + 可复现 benchmark」（审稿人不要求方法新）。文献坐实 AgentClinic/AI Hospital/MedAgentBench 家族创新点全是 benchmark 本身，本科可复制；且全是 doctor/patient 组合，**护士/家属/告警联动=全空白**。

**资源链（本轮最大发现，不是散资源是一条已打通的链）**：
- **AI4Health 苏州市重点实验室**（院长 **John Moraros** 任主任）= 论文完美挂靠平台，scope 字面含病房 agent+告警。
- **苏大附二院**（王水花对接，苏州本地三甲 2600 床，ICU/心内/呼吸/神外全重点专科，2024 公开征集智能监护 AI，伦理委成熟）= 真实病房场景，B 级最现实。
- 王水花（影像 ML 高被引背书）+ 孟佳（统计/生信/系主任，已合作）= 方法+通讯背书；同校本科一作先例 Liu Yiheng。
- ⚠️ 诚实：王水花无 LLM-agent 经验/无真实医院 IRB 队列历史（agent+部署活学生扛）；孟佳企业合作证据薄弱不当数据源；两院仅意向函。

**三腿骨架**：腿1 病房多角色（护士/家属/告警）覆盖度 + 告警→角色路由 benchmark（纯公共数据保底，复用 `feasibility_pilot` 管道，claim 重定为覆盖度+路由**非**「四角色揭示新失败」，家属轴过采样专测）｜腿2 苏大附二院医护 usability（B 级，最小风险 IRB+QI）｜腿3 系统部署经验（QI 框架）。venue：CHIL App track（主）/ JMIR Human Factors / AMIA Student Paper。

**🔴 命门（headline 定稿前必清）**：切割点 B 存疑——**动笔前读 PSEBench(2606.05463)+Emergency Triage(2509.26351) 全文**确认未触及「告警→角色路由」；切割点 A 收窄（不 claim 首个护士角色，Agent Hospital 已有护士 agent 职能=分诊）。腿2 命门=导师对接须落到苏大附二院具体科室愿挂名 PI（**用户线下确认**）。

**下一步**：用户线下确认科室 PI + AI4Health 挂靠 + 署名分工；我方软活（腿1 现可开工）改 README/STORY/ACCEPTANCE pivot → planner 出 benchmark 矩阵 → coder 改 feasibility_pilot 加家属轴过采样 → writer 起草 usability 设计+IRB 模板。registry 已改 status=planning。

**同日补（命门清 + 瑞金通道盘点）**：
- ✅ **切割 B 命门 = CLEAN**：读 PSEBench(2606.05463)+2509.26351 全文，两篇都只做「判什么」（判上报义务/判恶化风险）**不做「派给谁」**——「告警→角色响应分派」评测协议无人做，**腿1 创新点成立**（首个 response dispatch/role routing 评测 + 护士/家属覆盖）。收窄措辞用「响应分派/角色路由」轴切开「事件上报分诊」「恶化预测」。（前序 researcher 误标 2509.26351 为"uncertainty-aware escalation"，读全文证伪该词不存在，不影响判定。）
- **瑞金通道裁决**：XJTLU×瑞金（瑞浦智慧医疗研究院 2025-12）由**慧湖药学院傅磊主导、方向新药/慢病/医疗技术、与王水花/理学院无关联**，瑞金 AI 合作方全是华为/商汤大厂本科课题权重低 → **腿2 先走苏大附二院**（王水花对接+重症急诊场景+可达性三齐全），瑞金仅当「XJTLU 战略级智慧医疗合作生态」背书背景提及，**不 claim 已获瑞金资源**（未落实写了失实）。
- **产出级别/工作量定档**：腿1 CHIL/ML4H 中等偏上 2–3 人月（骨架已有）｜腿2 JMIR HF 3–5 人月（卡 IRB）｜腿3 AMIA/CHIL App 1–2 人月。组合 2–3 篇中等 venue 本科一作，升学靠「benchmark 硬核+真实落地稀缺证据+跨机构执行力」组合叙事+推荐信（非单篇顶会名气）。

---

## 2026-07-02 · 🔬 reframe（多角色病房模拟 benchmark）可行性命门实证 = 方向性 NO-GO（四角色不承重）

用户认可 reframe（保留慧脉多角色思路，做 simulation benchmark，对标 AgentClinic）后，skeptic+theorist 砸命门给「有条件 GO」+ 一个 <1GPU·h 定生死实验（四角色分布 B 是否暴露医生中心 A 测不出、指南可打分的失败）。用户「先证明可行性」→ 派 coder 搭原型（`src/feasibility_pilot/`）→ 主线真跑。

**管道可行性 ✅ 证通**：真实 mimic3wdb numerics seed（开放无需 CITI）+ partial-NEWS2 指南 D*（确定函数非 LLM，锚 RCP 2017）+ A/B 场景 + 家属信号非循环锚未来指南态 + 结构化精确匹配打分 + rank-flip 护栏。这套管道是可复现硬资产。

**命门结果（真 Qwen2.5-3B-Instruct，274 场景 548 决策 parse_ok 548/548）= 方向性 NO-GO**：
- escalate 正确率 A/B = **0.507/0.507**（分布不影响升级）
- route 正确率 A/B = 0.562/0.303（B 更差 = 分布更难，非新失败类）
- A对B错 **40** vs A错B对 **40** = **对称** → 分布=加噪非承重信号（若四角色真揭示结构性失败应不对称）
- dropped_concern 仅 8 例（家属/护士轴被设计欠采样，唯一未干净测的窄缝）

**实证坐实 theorist 预测**：协同作为被打分能力塌，只剩多模态升级退化刻画 → **天花板 workshop/D&B，多角色=背景板，够不到一作扛旗一区**。这是第 5 次收敛同结论，且首次真跑数据实证。

**未死的窄缝（诚实）**：家属/护士「唯一早期信号」轴欠采样（8 例），要救需过采样该场景专测；但期望=窄 claim，大概率仍 workshop。

**待用户拍板**：①接受慧脉=workshop/SOP + 一区旗换载体（生物 FM 忠实度 benchmark 等，领域 scout 已扫出）②再救一次（过采样家属轴）③消化/问导师。用户「先收工」暂停在此。

---

## 2026-07-02 · 🏁 慧脉「一作扛旗一区」arc 终结 → 归位 workshop/SOP，主线转广域旗舰侦察

**三次独立严格验证收敛，病房告警×LLM 撑不起一区扛旗**：
1. **skeptic（候选 B）**：多告警联合承重腿撞车 + 无护城河。
2. **$0 金标存在性检查**：穷尽 8 源，公开数据**不存在多告警共触发的专家 true/false 金标**（PhysioNet2015/VTaC=单告警；Drew/Pelter/UPenn 多参数标注**全未公开**；eICU/HiRID/MIMIC 无专家告警标注）。
3. **theorist（深框架"agent 告警管理决策层"）NO-GO**：唯一有区分度的判据「用临床结局判抑制安全」**反事实无效**（早期预警悖论：救命告警被系统性判"可抑制"，方向性错），因果校正 MIMIC 不可辨识；有效判据（单告警金标=LLM 错工具被 VTaC 占 / 医生 rubric 被 RealICU/HealthBench 占，团队零医生自造 rubric 全循环）都非新。命门定理见 theorist 回汇。

**慧脉真实天花板**：workshop（ML4H Findings/JBHI application）+ 开源 ward-agent 参考实现 + 强临床合作 SOP。**非一作扛旗一区**（demo-only 无数据护城河的结构性上限）。theorist 递的唯一活的一区角度=「结局代理评告警抑制反事实无效 + Manski 部分辨识」方法批判论文，但理论重、是另一种项目。

**用户拍板（2026-07-02）**：视角放开别死磕慧脉；按博士级找一作旗舰，战场=医学影像/生信/ML/AI。→ 主线转**广域旗舰方向侦察**（3 领域并行扫），慧脉归位 SOP/workshop 备选，不再当一区主攻。

**流程教训（已记 memory [[feedback_validate_test_before_negative_verdict]]）**：命门先行对，但我一度用坏工具（错轴/循环标签/粗基线）得假阴性负结果，被用户拦下；且在单一 demo-only 资产上钻太久，视角窄——旗舰方向该先广域扫再收敛。

---

## 2026-07-02 · ⚠️ 命门 pilot C2/C3 方法学作废（自审 + 2 researcher 核实，负结果 VOID）

**背景**：主线跑 KS-3 命门 C2（复合误报超独立预期）/C3（依赖让 naive 失效）得表面负结果（C2 ratio≈1、C3 e-value 无优势），一度判「候选 B 塌」。**用户质疑「我们出错概率很大」→ 自审 + 派 2 researcher 核 → 确认 pilot 三处全错，负结果作废，不作数。**

**三处错（都指向假阴性）**：
1. **测错价值主张（C3）**：拿 e-value vs Bonferroni 比**覆盖**。但 e-value 真卖点 = **anytime-valid 序贯监测**（任意停时 Type-I 受控，Ville 不等式），非覆盖——静态多重检验轴 Bonferroni 本就够，e-value 无优势是测错轴的预期结果。对口框架 = **e-detector**（Ramdas，arXiv 2203.03532）。
2. **真/假标签错且循环（C2/C3）**：用「波形持续紊乱=真」弱代理。领域金标全是**专家波形标注**（PhysioNet2015 双专家 / VTaC 6 专家 12000+ 决策），无一用此代理；且拿波形判波形告警=循环。
3. **独立基线太粗（C2）**：∏p_k 假设时间齐次+独立（拿假设当结论）。正解=**多元点过程依赖检验（IndTestPP/Hawkes）或 log-linear/χ²**。

**修正后候选 B 真实状态（不吹不埋）**：方向**没被证伪**（我冤枉了它）。正确做法 = anytime-valid e-detector 框架 + 专家标注金标 + 点过程依赖统计。真空白 = 多告警复合**序贯**评测协议无公开权威版（可作贡献）。**但**：方法 novelty≈0（e-detector/WCTM 现成）+ 框架拥挤，尤其 **2603.13156「Anytime-Valid Calibration Monitoring」几乎正撞**。→ benchmark 贡献型、窄缝收口中、有近身撞车。

**流程教训（记 memory）**：命门先行纪律对，但**执行用错工具（错轴/错标签/错统计）→ 假阴性**；下负结论前必先核「测法本身对不对」，尤其证伪自己主推方向时。已派 skeptic 红队修正后候选 B 值不值得重建 vs pivot 候选 A。

**KS3_PILOT_REPORT 的 C1 仍有效**（共触发存在=描述性统计，不依赖真/假标签）；C2/C3 结果作废勿引用。

---

## 2026-07-02 · KS-3 数据命门预热真跑 ✅ 核心命门初步 GO

用户授权立项前完全验方向可行性（"千万别立项后做不出来"）。派 coder 建 KS-3 命门探针（`src/ks3_pilot/`），主线真跑（coder 只写不跑）。

**三大 de-risk（真跑数据，非 mock）**：
1. **完全不用 CITI**：`00_check_access.py` 实证 mimic3wdb + matched + challenge-2015 **三库全 Open Access（ODbL/ODC-BY）**。原 KS-2「MIMIC 需 CITI 2 周」假设作废，命门+benchmark 主体现在就能跑（已改 datasets.json + CITI 仅结构化 EHR 结局才需）。
2. **管道真跑通**：修 coder 一个 wfdb 路径 bug（record 含子目录时 pn_dir 未拼），15 条 matched numerics record 真派生告警真统计。
3. **🎯 核心命门 Q1 初步 GO**：15 条 × 3 阈值族，共触发 default **11/15 病人(73%)**、liberal 13/15、随阈值单调；告警**正相关**（HR|RESP phi 中位 0.41 / ABPsys|SpO2 0.39，17/33 对>0.1，最高 0.86-0.96）。→ 共触发**真实、常见、依赖** = 正是 e-value 依赖稳健承重前提；**不是「结构性不存在」坑**。Q3 单告警反证 by-design（PhysioNet2015 官方每 record 单告警）。

**裁决**：**立项-killing 的结构性风险已退，方向可做**。报告 `src/ks3_pilot/KS3_PILOT_REPORT.md`，数字 `cotrigger_stats.csv` 可 Bash 核。
**仍需补（非 blocker）**：researcher 查 Chromik 阈值替占位 → 扩 30-50 record → 定弱结局代理跑 Q2 复合 FAR → e-value 联合校准实现。诚实边界：N=15 非终值、阈值占位、phi within-record。

---

## 2026-07-02 · venue 策略定案（本科一作扛旗 × HYPSM 直博视角）

用户诉求升级：希望这篇成为**独立/主导一作扛旗作**（别处组合台可能共一/无独立一作机会），目标美国顶校(HYPSM)直博。派 3 researcher 核 npj DM / CHIL / ML4H / MLHC 对「本科一作 + 公开数据 benchmark + 无真实临床数据」profile 的真实可达性。

**核心发现**：
- HYPSM 认领域声望**不认中科院分区/JCR/IF** → 认 NeurIPS/顶刊 + 健康 ML 专业会(CHIL/MLHC/ML4H)。
- 一作机会真实存在（四 venue 政策上均无资历门槛，benchmark/eval 不要求新方法=本科单主导够得着形状；数据公开/无 IRB 不是门槛，npj DM 有纯公开数据 benchmark 先例）。**真实卡点=①组内让贤(须事前跟王水花锁 lead 身份)②本科生执行力**，非 venue 政策。
- **定案 venue（HYPSM 一作视角）**：主力双投 **CHIL 2027(~2月) + MLHC 2027(~4月)**（均 PMLR 归档、Research Track 明收无新方法公开数据 benchmark、本科一作无结构障碍、MLHC 临床门槛隔离在别 track 对无临床背景最干净、竞争池小 25-36%、CHIL 先投未中转 MLHC 错开）；冲刺 npj DM（零本科独立一作先例，需拉临床 MD 挂通讯）/ NeurIPS E&D（24.9% stretch）；保底 ML4H Findings（非归档）。
- AgentClinic 一作=JHU 博士生非本科、发 npj DM 非 NeurIPS，不能当本科先例。

已改：00_README/01_STORY R9/registry venue。**venue 仍卡 KS-3 命门**（地基不成立无论文）。

---

## 2026-07-02 · 升级候选 B 立项（大编队冲一区侦察 + 撞车复查，方向拍板）

**触发**：用户把上限从「二区/workshop」拉到 SCI 一区/顶会，要低竞争 + 可行，派大编队（5 researcher + skeptic + 撞车复查 researcher，全 opus）。用户 ExitPlanMode 批准方向升级（plan=`~/.claude/plans/bubbly-fluttering-turtle.md`）。

**venue 双靶（R1+R2）**：SCI 一区现实可达 = IEEE JBHI（性价比）/ npj DM（冲刺）；NeurIPS E&D 主 track 低概率不押（本科一作+无真实数据+合成 benchmark 难中 25%）。天花板诚实定一区期刊 + D&B-workshop。

**方向（R3 白地 + R4 方法两个独立 researcher 汇聚 + skeptic 放行）= 候选 B**：医疗「多告警器复合误报」联合校准 benchmark + e-value 依赖稳健校准配方。双贡献（benchmark + 依赖稳健配方），纯公开波形数据，后验校准不训大模型=不塌，B 族。

**skeptic 红队候选 B**：致命=1（数据命门，有出路）。novelty 押数据/经验刻画（方法=已知机器换场景）；venue 据实 JBHI 不写 NeurIPS 主 track。

**撞车复查（步骤 2）✅**：真空成立（中高置信，无直接撞全 claim 者）。STORY 必切 3 处邻接（R11）：工业 FDR-cry-wolf（单检测器 vs 联合）/ Veritas-RPM（启发式 vs 有限样本保证）/ 通用 e-value conformal selection（告警依赖使通用方法不直接可用）。

**🔴 命门（动笔前必跑 KS-3，<1GPU·h）**：多告警「共触发 + 逐告警真/假」公开数据不带标注存在（PhysioNet2015 单告警/段、VTaC 全 VT 单类、MIMIC Waveform 须自派生无专家真假标签）。三问：共触发真频繁+相关 / 复合 FAR 阈值族稳健 / PhysioNet 单告警锁死。GO→冲一区；翻→退腿 A 开源+SOP。

**已改档**：00_README/01_STORY（核心 claim→候选 B、命门三问、R8-R11）/02_ACCEPTANCE（KS-3 数据命门）/DATA_INVENTORY（主数据换 MIMIC Waveform+PhysioNet2015+VTaC）/reference/RECON_2026-07-02_venue_niche.md（全侦察落档）。

**卡点（等用户）**：KS-3 依赖 MIMIC Waveform，须先办 PhysioNet CITI（`reference/CITI_PHYSIONET_CHECKLIST.md`，2 周提前量）。CITI 前可先用**开放** PhysioNet 2015 Challenge 做单告警对照预热（不需 credentialing）。

---

## 2026-07-02 · 立项（承接决策档 + 4-agent 全方位核实）

**触发**：用户要求把创业项目「慧脉守护——病房智能体平台与服务机器人系统」转化为科研成果，读商业计划书 + PPT + repo，建 project + 设计下一步探路。承接 `GradSchool-Prep/26_慧脉守护_论文可行性全景决策档.md`（2026-07-01，8-agent 建）。

**用户拍板三定调**：① 只有 demo 原型无真实临床数据 ② venue 先探路不锁 ③ 低优先当 SOP 素材。

**本次核实（4 后台 agent，全落 reference/）**：
1. **repo（WardLung Compass v2）**：FastAPI+SQLite demo，MedGemma-1.5-4b-it + MedSigLIP-448 + LlamaIndex/FAISS，四角色肺炎场景，`ward_demo.db`+`Demo@123` 占位。
2. **商业计划书（PDF 106 页为准，txt 是旧海洋换皮稿弃用）**：技术栈清晰 —— 脉枢 HuimaiMed（MedSigLIP+MedGemma-4B/27B+Qwen3-ASR/MedASR+Qwen3）+ ReAct 6 工具 + 向量/BM25 混合 + 生命体征轻量 ML 三模块（心梗 LSTM/呼吸窘迫趋势/呼吸暂停 ODI+LSTM）+ 双轨告警 P0-P3。RAG 知识库真源（指南 500/药物 3000/ICD-10 14000）。
3. **真实性核查（三 agent 一致）**：🔴 零真实临床数据/零 IRB/零自证实验/零可复现 benchmark。UI 全 demo 假数据；两院「成果应用证明」= 意向背书函；MedQA69/EHRQA90/AUC 全是底层开源模型文献值非自测；团队真实 IP 在海洋/港口 CV 域（换皮痕迹）；导师王水花。隐私：学生证/证件照需清洗。
4. **landscape（researcher）**：⚠️ 首选失败分类学路撞 **MedAgentAudit**（2510.10185）；分流 benchmark 撞 **PSEBench**（2606.05463）+ MIETIC + MedAgentBench；救命护城河「真实部署+中国数据」= 恰缺 → 顶会 novelty 路基本堵死。

**裁决**：能转化但只能低成本走 —— 现实活路 = 小 venue 可行性/开源贡献 + 强美博 SOP 素材，非顶会。诚实定性写进 00_README。

**新洞察**：系统有两块可分离科研料 —— 路线①agent 多角色（撞车+数据饥荒）vs **路线②生命体征早预警**（公开生理数据充足、无需 IRB、不撞多 agent 坑），后者数据处境好得多，KS-1 一并权衡。

**建 scaffold**：`project/meeting/WardAgentBench/`（00_README/01_STORY/02_ACCEPTANCE/DATA_INVENTORY/04_LOG + reference/），status=`planning-scouting`，registry + CLAUDE.md 入口已补。

**下一步**：KS-1（路线选择+差异化红队，skeptic）已派 → 等结论定路 → KS-2（数据可达性，用户办 CITI）+ KS-4（venue）并行 → KS-3（命门 pilot <1GPU·h）。任一 NO-GO 诚实退纯 SOP。

---

## 2026-07-02 · KS-1 裁决（skeptic 红队，✅ 过闸）

**结论：选路线②重定位 + 组合，不选纯①，不 NO-GO 全退。** 致命伤=1（路线①作承重实证 claim），skeptic 自带解法。

- 🔴 **路线①作承重实证 = 死**（高置信）：四角色交接失败探针**公开数据结构性不支撑** —— MedDG=17864 例春雨消化科医患对话（无护士/家属/SBAR），CBLUE/Huatuo 同单轮 QA；四角色场景只能自构造 → 失败=prompt 设计产物非真实浮现，审稿人一句毙（同 [[mechanism_probe_methodology]]/[[delta_statetrack]] 结构性不存在坑）。→ **降腿 A 开源参考实现，不带实证 claim**。复活条件=找到真实 nursing handoff/SBAR/多方会诊公开语料（当前无）。
- 🟠 **路线②必须重定位**：当「更好模型」必死（benchmark 饱和 + 新竞品 **AI-TEW** npj Digital Med 2026 占分层减误报）。但 AI-TEW 按**风险**分层、慧脉按**延迟**分轨 → 轴不同。重定位「部署系统实证」即活。
- 事实更正：MedAgentAudit ~6 类同质医生 agent（非 10 类、非四角色）。已更 STORY/ACCEPTANCE/LANDSCAPE。

**锁定 claim（承重）**：边缘延迟(<5ms)+双轨告警部署约束下，公开 ICU 数据(MIMIC-IV/eICU)实证多并行轻量体征告警器的**延迟-精度前沿 + 误报复合效应** + 简单缓解 + 开源 ward-agent 参考实现。**卖点=部署系统实证非模型 novelty。** 三腿=A 开源实现(原①)/B 承重实证(重定位②)/C TRIPOD-DECIDE feasibility。

**KS-3 命门（<1GPU·h，依赖 KS-2 数据）**：MIMIC/eICU 复现 1 轻量恶化预警测 FAR → OR 合并第 2 个测级联 FAR 是否显著超独立可加基线 → CPU 测<5ms 延迟画前沿。GO=复合 non-trivial+前沿有结构；NO-GO=退腿 A+SOP。

**卡点（等用户）**：KS-3 依赖 MIMIC/eICU，须先办 PhysioNet CITI 认证（用户线下，2 周提前量，checklist=`reference/CITI_PHYSIONET_CHECKLIST.md`）。KS-4（venue 核对，0 算力）可主线自主推。
