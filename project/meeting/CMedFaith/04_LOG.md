# CMedFaith — 项目日志（时间倒序，单一真源）

---

## 2026-07-11 · 全量实验设计情报底座（5路researcher）+ 🔴K0命门修正

**本 session（推进实验设计）**：
1. 派 5 路 researcher 并行深调研 → 综合成情报底座 `reference/RESEARCH_BRIEF_2026-07-11.md`（每条带来源）：对标benchmark完整实验协议 / 检测器全谱4族 / 数据构造MedHallu四阶段照抄级细节 / venue(ARR/EACL)标准 / 评测统计方法学。
2. **实验深度靶子量化**：对标EACL/ACL强benchmark中位≈5-6主表/4图/11检测器/3-4分层维/2级评测，普遍软肋=无IAA κ/α·无CI·无校准·单语。CMedFaith"远超"配方=**≥12-15检测器4族+三级评测(response/claim/span)+≥5分层维+≥8主表+≥6图+κ/α+bootstrap CI+AUROC/AUPRC+ECE校准+中英对照**。
3. 派 planner 出正式全量实验矩阵 P1-P3（在跑，落 PLAN/）。

**🔴 K0 命门修正（张冠李戴，必须改）**：
- 之前 K0「PASS」核的 `2025.findings-acl.211` **是误指**——真身="Long-form Hallucination Detection with Self-elicitation"（**通用域**长文本幻觉检测方法，与中文/医学/release全无关）。**"MedHallu-ZH"根本不存在**（MedHallu英文独占，HF/repo无zh分支）。
- **真正该核的中文医学幻觉benchmark = CMHE**（Chinese Medical Hallucination Evaluation, LREC-COLING2024, Chengfeng Dou）：snowballing多轮误导场景，**非evidence-conditioned → 不撞headline #1**，但须补相关工作+正式撞车核查。
- **结论方向不变**：中文医学evidence-conditioned faithfulness仍空白，headline #1成立。但K0核查对象错→待改写ACCEPTANCE/KILLSHOT_LEDGER（保留原文痕迹+加correction，防HARKing），CMHE补撞车条（TODO下载Google Drive核规模/许可/分层）。

**其余待改（brief §6，planner回来一起落）**：DATA_INVENTORY撤MedHallu-ZH条·CMExam许可降级"内部构造不分发"(数据学术禁商用与repo Apache冲突)·B3补2类(过时指南+诊断决策误导)剔reasoning类·RAGTruth是2×2轴(Conflict/Baseless×Evident/Subtle)非并列4类；ACCEPTANCE的IAA对标"RAGTruth 91.8%"存疑(可能是模型F1非IAA→TODO人工核，改用FaithBench Krippendorff α=0.748)+补统计规范(paired bootstrap非McNemar+Holm-Bonferroni+ECE)。

**检测器关键情报**：原生中文专用检测器仅 LettuceDetect多语版(EuroBERT/mmBERT,MIT)；AlignScore/HHEM/MiniCheck/Lynx全仅英文=天然"英→中迁移崩塌"素材；judge中文主力Qwen2.5-7B(Apache,4090可)+GLM-4-9B/InternLM2.5对照。

**下一步**：planner实验矩阵回来 → skeptic红队设计（0致命即过）→ 落PLAN/ + 修STORY/ACCEPTANCE/DATA_INVENTORY/KILLSHOT_LEDGER四处 → P1数据构造pilot（验K3+MedHallu管线中文可跑性）。

**更新（同session续，planner+skeptic回）**：
- ✅ planner 出全量实验矩阵 `PLAN/EXPERIMENT_MATRIX_P1-P3.md`：15检测器/4族 × 三级评测 × 5-6分层维 = 10表7图7分析块（远超EACL中位），三命门判决实验+预注册判据+退路，实验↔叙事互调映射表。
- 🛑 **skeptic 红队 3🔴 致命（已联网核实，PLAN §0.5）**：同根=对照锚 PsiloQA-zh 未与我们"骗过≥1检测器"筛过的 zh-med 匹配。🔴-1 选择伪迹冒充域效应(K1/K3假闸)；🔴-2 构造投票器Qwen2.5-7B=K1承重judge D10循环；🔴-3 **Evident/Subtle≠natural/adversarial**(RAGTruth全自然/我们全对抗构造零自然样本)→K2对抗confound控制无效。**仅阻断K判决run(R-P3.4/3.5/3.6)+判据预注册，P1/P2/主横评不阻断可推进**。
- 🔴-1/🔴-2 修法明确(换非投票judge+对照锚同筛)。**🔴-3=拍板点**：建自然医学臂(额外采集标注成本)换干净K2「医学域本身难」 vs 降级headline #2「对抗鲁棒性」→抛用户拍板。
- **下一步**：用户拍 🔴-3 → 回 planner 统一修 K 判决对比设计 + 派 researcher 解TODO → P1 起(R-P1.0英文复现无依赖)。

**里程碑（方案A定稿 + R-P1.0 管线验证 PASS）**：
- ✅ **用户拍板方案A**（对称化主力+MedFact自然臂三角互证+协变量回归）→ planner 出 K 判决定稿（PLAN §0.6）：🔴-1 对称通用对抗锚 zh-gen-adv(同管线同筛)/🔴-2 K1承重judge换非投票D11/D12·D10降构造臂/🔴-3 K2重述「等构造强度下医学域仍难」+MedFact三角。新增 R-P2.7/R-P3.12/R-P3.5-appx，体量升 8资产/12表/8图/8分析块。
- ✅ **前置TODO全解**（researcher）：MedHallu逐字管线(embedding all-MiniLM-L6-v2/蕴含roberta-large-mnli τ=0.75/judge 0-1-2 prompt)+finetune超参(RAGTruth lr2e-5/1ep,batch未披露TODO)+许可全核(MiniCheck-Bespoke/Lynx=CC-BY-NC禁商用)+**RAGTruth 91.8%/78.8%确是IAA但未校正**+CMHE不撞。落 brief §7。
- ✅ **R-P1.0 全量复现精确命中冻结锚**：MedHallu 0.4277/PsiloQA-en 0.7204/G_domain 0.2927 CI[0.184,0.391] 三值全中(Bash核 code/results/)。统一评测 harness(三级+BA/F1/MCC/AUROC/AUPRC+bootstrap10000+paired bootstrap+Holm)建成验证。**L2基线地基牢**。
- ✅ **四处文档更新**：PLAN §0.6定稿 / ACCEPTANCE(K0修正留痕+K2重述+IAA口径+L2-b统计规范) / KILLSHOT(三🔴红队+方案A预注册冻结防HARKing+对称锚同筛清单) / DATA_INVENTORY+STORY(writer在改)。
- **命门修正**：K0张冠李戴(MedHallu-ZH不存在,实为SelfElicit通用域)→真对照CMHE(非evidence-conditioned不撞)已改档。
- **下一步（真拍板点）**：P1 中文数据构造 pilot(跑 MedHallu 管线中文复刻,3-LLM投票+TextGrad **花 API 钱=拍板**)；或先派 researcher 选对称锚证据源(中文百科同粒度)+skeptic复核修订版两残留点(K1/K2是否重复判据·证据源残余confound能否只声明)。D2-D15检测器接入 harness 可并行。

---

## 2026-07-11 · 收工（本 session：从文献综述到立项建档全链完成）

**本 session 完成**：
1. ACL 6 篇文献综述（`../ACL/文献综述_ACL2026_幻觉检测与忠实度验证.md`）→ 领域评估 → 三候选红队 → 选 A → 转医学域 → CMedFaith 立项。
2. 两发 kill-shot pilot（通用跨语言 G_lang≈0 证伪旧动机 / 医学 vs 通用 G_domain=0.293 命门 PASS）。
3. 标准 schema 建档全套 + registry/CLAUDE/claim/datasets 登记 + 指针自检零漂移。
4. 4 路深度调研（竞品delta/数据构造/评测venue/K0）+ K0 撞车终检 PASS。

**concurrent work 定调（用户）**：MedHallu-ZH 系同期成果，related work 一句带过不刻意对标，靠自己亮点立文。

**下一步（下次开工）**：派 planner 设计正式实验矩阵 P1-P3 → **P1 = 小规模中文医学 faithfulness 数据构造 pilot**（验 K3 中文迁移 + MedHallu 半自动构造范式跑不跑得通）。动笔前补两 TODO（MedHallu-ZH 是否真可下 / zh 有无 severity 分层）。

---

## 2026-07-11 · K0 撞车终检 PASS + 措辞红线收紧

researcher 逐段核 MedHallu-ZH 原文（SelfElicit, Findings ACL2025, 2025.findings-acl.211 §C.2）：
- **K0 PASS**：MedHallu-ZH = (query, response) 两元组**无外部证据字段**，判幻觉靠专家/世界知识（self-elicitation, reference-free），**确非 evidence-conditioned** → headline #1「首个中文医学 evidence-conditioned faithfulness benchmark」成立，不撞。
- 事实：zh 规模 2704 response / 18031 句；自然幻觉（非对抗）；已有 zh+en 平行集但未做迁移诊断；无公开 release 链接。
- **净剩亮点**：① evidence-conditioned+span grounding ✅核心 / ③ 对抗支 ✅独有 / ⑤ 独立公开资源 ✅；② 横评限"证据条件设定下" / ④ 改"跨语迁移诊断"。
- **收紧措辞红线 3 条**（写进 STORY）：横评限定 evidence-conditioned 设定、不 claim 首创难度分层、不 claim 首个中英平行集。
- **两 TODO**：MedHallu-ZH 是否真公开可下；zh 是否也有 severity 分层。
- 全文缓存 `<session>/tool-results/selfelicit.txt`。

---

## 2026-07-11 · 立项决策 + 两发 kill-shot pilot

**立项**：用户拍板，从 ACL 文献综述（6 篇全是 LLM 幻觉/RAG faithfulness 检测）衍生的方向探索收敛而来。

**方向收敛历程**（防跑偏留痕）：
1. 起点=整理 `project/meeting/ACL/papers/` 6 篇综述（MARCH/CiteGuard/SIRG/FAMA/FRANQ/ContextCheck，全是 faithfulness/幻觉检测）。
2. 领域评估：低算力、benchmark 友好、有空白。
3. 三候选红队：A 跨语言（原 headline "检测器跨语言崩" 被 EACL 论文 arXiv:2601.16766 + pilot#1 双证伪）/ B 元评测（撞车重）/ C 打 FaithBench（50% 上界过时）。
4. 用户约束："往临床/健康 NLP 靠"（升学）+ "自建两个 benchmark，做扎实" + "走 ARR 不赶死线"。
5. **一次跑偏自查纠正**：pilot#1 跑的是"检测器跨语言掉分"（旧动机），方向早转医学域；及时改对靶子跑 pilot#2。
6. 收敛 = **中文（+英文对照）医学 RAG faithfulness 检测 benchmark**。

**核心 RQ**：现成 faithfulness 检测器在中文医学 RAG 上系统性失效吗？→ 建首个中文医学 evidence-conditioned RAG faithfulness benchmark + 基线，揭示并量化医学域失效。

**双贡献**：① 资源（首个中文医学 faithfulness 数据）② 发现+基线（现成检测器医学域失效）。

**venue**：ARR → BioNLP/ClinicalNLP/CL4Health/EACL-EMNLP Findings（临床 NLP）。

**pilot 结果**（数字 Bash 核 csv，详见 `reference/KILLSHOT_LEDGER.md`）：
- #1 通用跨语言：G_lang=−0.004 CI[−0.089,0.086]→ 语言不是难点（旧动机证伪）。
- #2 医学 vs 通用：G_domain=+0.293 CI[0.184,0.391]→ **医学域显著更难，命门 PASS**。medical macro-F1 0.43<随机。

**诚实天花板**：pilot 是英文 MedHallu 粗筛；中文数据待自建；G_domain 混对抗构造 confound；单臂待补 judge。三条结转 02_ACCEPTANCE 的 K1-K3。

**建档动作**：建 00_README/01_STORY/02_ACCEPTANCE/DATA_INVENTORY/04_LOG + KILLSHOT_LEDGER；pilot 脚本在 `_scratch/`（killshot_psiloqa.py + killshot_med_vs_general.py）；登 registry + CLAUDE.md 入口 + claim + datasets.json。

**在跑**：3 路深度调研（竞品/delta 定位、数据构造范式+中文证据源、评测协议+venue 惯例），回来精修 STORY/ACCEPTANCE/DATA_INVENTORY。

**环境记账**：为跑 pilot 装了 `datasets 5.0.0`（副作用：pandas 升 3.0.3，与 idc-index/streamlit 有版本冲突警告，不影响 pilot；需要时可回退）。

**下一步**：待 3 路调研回 → 填 STORY（delta 精确定位）+ ACCEPTANCE（判据/kill criteria）+ DATA_INVENTORY（自建方案）→ 设计正式实验矩阵（补 judge 臂 + 对抗/自然分层 + 中文数据构造 pilot）。
