# CMedFaith — 战略叙事（反跑偏主文）

> 读档：`00_README` → 本文 → `02_ACCEPTANCE` → `DATA_INVENTORY` → `04_LOG`。
> 本文钉死 Claim 与 delta，防止方向再漂（本项目立项前已漂移多次，见 04_LOG 历程）。

## 核心 Claim（headline）

> **医学 RAG 系统里，大模型会生成看似专业、却不忠实于所检索医学证据的回答；现成 faithfulness 检测器在医学域系统性失效，而中文医学场景连评测这一失效的数据都没有。CMedFaith 建首个中文（+英文对照）医学 evidence-conditioned RAG faithfulness 检测 benchmark，量化并诊断这一失效。**

一句话卖点：**填补中文医学 faithfulness 空白 + 揭示现成检测器医学域失效 + 给出诊断性基线**。

## 任务定义（钉死轴，防混淆）

- **faithfulness（本项目唯一轴）**：回答的每条陈述是否被**给定的检索医学证据**显式支持。unfaithful = 增改、捏造、或来自证据之外。
- **不是 factuality**（对世界知识对错）——**红线**：过半幻觉检测失败源于混淆二者（arXiv:2508.08285），医学域尤致命（答案可能符合教科书但不忠于检索到的病历/指南）。选数只留 closed-world"答案 vs 给定证据"。

## 为什么新 / delta（researcher 竞品终检 2026-07-11）

五方竞品定位（每方标"占了什么"）：
- **MedHallu**（EMNLP2025）：医学 + evidence-conditioned，但**英文**（PubMedQA）→ 语言差。
- **Bi'an**（2502.19209）：中英双语 RAG faithfulness，但中文侧只有新闻/法律/电商**无医学** → 域差。
- **PsiloQA**：14语通用维基 → **非医学**。
- **CiteCheck**（2502.10881）：**中文** faithfulness，但**引用忠实度/通用域** → 域差。
- 🔴 **CMHE**（Chinese Medical Hallucination Evaluation, LREC-COLING2024，真正的中文医学撞车对照）：**中文+医学**幻觉评测，但**对话式 snowballing 幻觉（多轮被误导下滚雪球）+ 非 evidence-conditioned（无"给定检索证据段"字段，判幻觉不靠外部证据）** → **范式差**（我们判"答案 vs 给定证据"，它判对话滚雪球）→ 不撞 headline #1。（⚠️ **K0 原核对象张冠李戴**：之前标"MedHallu-ZH / SelfElicit `2025.findings-acl.211`"核错了论文——该 anthology ID 真身="Long-form Hallucination Detection with Self-elicitation"，是**通用域**长文本幻觉检测方法，与中文/医学/release 全无关；"MedHallu-ZH"根本不存在，MedHallu 英文独占无 zh 分支。真正该核的中文医学 benchmark = CMHE，详 ACCEPTANCE K0 修正 + RESEARCH_BRIEF §0。）

→ **独有交集 = 中文 ∧ 医学 ∧ evidence-conditioned（给定检索证据判忠实/span grounding）∧ 独立 benchmark 资源 ∧ 检测器横评**。

### CMHE（真正的中文医学撞车对照，🔴 K0 修正后重定）
**K0 重做对象 = CMHE**（2026-07-11 修正，原"MedHallu-ZH K0 PASS"因张冠李戴作废，留痕见 ACCEPTANCE K0）：CMHE 是**对话式 snowballing 幻觉**评测，**无"给定检索证据段"字段**（判幻觉不靠外部证据），**初判非 evidence-conditioned → 不撞 headline #1**。⏳ 待下载 Google Drive 复核规模/IAA/许可后正式冻结"不撞"（TODO，ACCEPTANCE K0）。
**写作策略（用户 2026-07-11，定调不变）**：CMHE 及其他中文医学幻觉相关工作 related work **一句带过即可，不刻意处处对标强调**——我们的 evidence-conditioned RAG 定位本身独立成立，靠自己亮点立文不靠踩它。**同期成果（concurrent work）按学术惯例不刻意对标**。

### Headline 策略（防御性组合，命门未核前不锁死）
1. **「首个中文医学 evidence-conditioned RAG faithfulness 检测 benchmark + 检测器横评」**——最承重，死活压在 CMHE 确非 evidence-conditioned（K0 待复核冻结）。**方法贡献增量**：以**对称化控 confound**（对照通用域也过**同一构造管线 + 同"骗过≥1检测器"筛子**，把构造/选择强度钉成常量后再比域效应）隔离"域效应 vs 构造伪迹"——**benchmark 文献无具名先例**（MedHallu 原作医学 vs 通用仅文献综述非受控对照），matched design 原理支持，既填真空白又是方法增量（见 ACCEPTANCE K2 + PLAN §0.6 方案 A）。
2. **「中文医学 RAG 检测器对抗鲁棒性评测」**（K2 FAIL 退路）——若等构造强度下医学域不更难，退守"现成检测器在此对抗构造集上弱、人造对抗集高估检测器真实能力"，不归因域，更稳（对抗鲁棒性发现在中文医学域无人做，即便 CMHE 是 evidence-conditioned 也活）。
3. **「英→中医学 faithfulness 检测器迁移崩塌诊断」**——跨语迁移分析，CMHE 未做迁移诊断（对话集单一范式）。
> 三者可组合成一篇：#1 当主 claim（K0 复核完 CMHE 定），#2 当 K2 FAIL 兜底、#3 当加分章节。

**pilot 已证的立项地基**（KILLSHOT_LEDGER）：难点在**域**不在语言——通用域跨语言检测器不掉分（G_lang≈0），医学 vs 通用掉 29 分（G_domain=0.29）。动机 = 扎实的"检测器医学域失效"，非被证伪的"跨语言崩"。此 pilot 图（MedHallu 0.43 vs PsiloQA 0.72）= "域+语言双迁移崩塌"核心 figure 雏形。

**加分角度（researcher 核实中文医学域无人做）**：
- 自然 vs 对抗构造幻觉**分层评测**（TRIVIA+/FaithBench 证实"检测器人造集好、自然集掉点"，中文医学未验）；
- 医学幻觉**类型学诊断**（MedHallu 有英文 taxonomy，中文医学无）；
- 中英对照 detector **跨语迁移**崩塌。

## 章节弧（benchmark 论文标准骨架）

Intro（医学 RAG 忠实度高风险 + 中文医学空白）→ Related（faithfulness 检测 / 医学幻觉 / 中文资源，三方定位 delta）→ 任务定义（faithfulness 轴）→ 数据构造（证据源 / 半自动管线 / 幻觉类型学 / 标注协议 / IAA）→ 数据统计（类别/分层/规模）→ 基线套件（三族检测器）→ 实验（BA/Macro-F1/span-F1，医学 vs 通用，自然 vs 对抗）→ 分析（失效模式 / 难度分层 / 错误类型）→ Limitations → Ethics。

## 防御写法 R-rules

- **R1 口径固定不混报**：response / claim / span 级分开报，主口径 response 级 BA+Macro-F1，不挑高的报。
- **R2 对抗 confound 显式**：自然/对抗幻觉分层报，未过 K2 前不 claim 难度来自"医学领域本身"，只说"现成检测器在此数据上弱"。
- **R3 factuality/faithfulness 显式声明**：明写只评 faithfulness，选数如何筛掉 factuality 样本。
- **R4 baseline 全面**：NLI + 专用 + LLM-judge 三族都要有，否则 reviewer 打"没测 SOTA"。
- **R5 LLM-judge 不当唯一裁判**：judge 有内/间方差，标注用多 LLM 共识 + 人工质检，评测报 judge 不稳定性。
- **R6 伦理/隐私**：临床数据去标识 + 来源合规 + Ethics Statement。
- **R7 复现**：数据/代码/prompt/检测器超参全公开，超参查官方源查不到标 TODO。

## 措辞红线

- 不笼统吹"解决医学幻觉"；只 claim "faithfulness 检测 benchmark + 现成检测器失效诊断"。
- **难度归因只能 claim「等构造强度下」（方案 A 重述，红线，2026-07-11）**：K2 即便 PASS，最强 claim = 「**等构造强度下**（对称对抗锚 + 同筛）医学域检测难度显著高于通用域」，**绝不 claim 无条件"医学域本身难"**——因全集皆对抗构造、零纯自然臂，**证据源风格（通用百科 vs 医学 PubMed 风格）是已声明的残余变量**，只声明不控制（reviewer 硬要真自然臂则退方案④轻量自建，暂不启）。K2 未过前只说"现成检测器在此数据上弱"。
- 不拿 pilot 的英文 MedHallu 粗筛数当中文结论——中文靠自建数据独立验（K3）。
- 数据不 overclaim"专家标注"若实际是半自动+抽检——如实写标注协议与 IAA。
- **（防 overclaim 撞车，K0 修正后重定）**：检测器横评措辞保守限定**"evidence-conditioned 设定下"**（避免与已有 reference-free 幻觉检测横评混同）；相对 CMHE，我们的**同管线对称化对抗对照 + 中英跨语迁移诊断**独有，但**首创/首个类措辞在 K0 复核 CMHE 规模/分层完成前不锁死**（据实呈证不踩人）。
