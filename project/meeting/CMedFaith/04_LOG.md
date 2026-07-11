# CMedFaith — 项目日志（时间倒序，单一真源）

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
