# CMedFaith — 中文医学 RAG faithfulness 检测 benchmark

> 项目入口。深读档顺序：本文 → `01_STORY.md` → `02_ACCEPTANCE.md` → `DATA_INVENTORY.md` → `04_LOG.md` 最新 entry →（有则 `PLAN/`）。
> 立项：2026-07-11 用户拍板（源自 ACL 文献综述衍生的方向探索 + 两发 kill-shot pilot）。status=planning。
> **铁律**：数字一律 Bash/Grep 核 csv 不信 Read；检测器/超参查官方源查不到标 TODO；faithfulness≠factuality 是选数红线（见 STORY）；立项前 pilot 是粗筛非定论，正式实验须补 judge 第二臂 + 控制对抗构造 confound。

## 一句话

大模型在医学 RAG（先检索医学证据、再据此作答）里会生成**看似专业但不忠实于给定证据**的回答（faithfulness hallucination），高风险场景后果严重。现有 faithfulness 检测 benchmark 要么是通用域（RAGTruth/PsiloQA）、要么是英文医学（MedHallu），**中文医学 evidence-conditioned faithfulness 数据是零**。本项目建**首个中文（+英文对照）医学 RAG faithfulness 检测 benchmark + 基线套件**，并系统揭示现成通用检测器在医学域的系统性失效。

## 双核心贡献

1. **资源**：首个中文医学 evidence-conditioned RAG faithfulness 检测数据集（半自动构造 + 人工验证），填补空白。
2. **发现 + 基线**：系统评测现成检测器（NLI / LLM-judge / 专用检测器）在医学域失效的程度与失效模式，给出基线套件与评测协议。

## 为什么新（researcher 初核，待深调研精修）

- **数据空白**：Bi'an（中英双语 RAG faithfulness）中文侧只有新闻/法律/电商**无医学**；MedHallu 是**英文**医学；PsiloQA 是**通用**维基。中文医学 evidence-conditioned faithfulness **无现成可下**（researcher 2026-07-11 核实）。
- **难点在域不在语言**：见下 pilot——通用域跨语言（中↔英）检测器不掉分，但医学 vs 通用掉 29 个点。
- ⏳ **delta 精确定位待深调研**（竞品/直接撞车 researcher 在查，回来填 STORY §为什么新）。

## 立项依据（两发 kill-shot pilot ✅）

数据真源：`_scratch/killshot_psiloqa.py` + `_scratch/killshot_med_vs_general.py`；结果 csv 见 `reference/KILLSHOT_LEDGER.md`。检测器 = mDeBERTa-v3-XNLI（多语言，未在这些数据上训过，无泄漏）。

| pilot | 对照 | G | CI(95%) | 结论 |
|---|---|---|---|---|
| 通用跨语言 | PsiloQA 中文 vs 英文 macro-F1 | G_lang = **−0.004** | [−0.089, 0.086] 含0 | 语言**不是**难点 |
| 医学 vs 通用 | MedHallu(英医) 0.43 vs PsiloQA-en(英通) 0.72 | G_domain = **+0.293** | [0.184, 0.391] 排除0 | 医学域**显著更难** |

→ 现成检测器在医学 faithfulness 上系统性失效（medical macro-F1 0.43 < 随机 0.5），支持建专门 benchmark。

## 诚实天花板（立项即知）

- pilot 是**英文 MedHallu 粗筛**，中文医学数据**尚需自建**（本项目核心工作量）。
- G_domain **混着"MedHallu 对抗构造 vs PsiloQA 自然生成"的数据集差异**，不纯是"医学领域"——正式 benchmark 须控制该 confound（自然 vs 对抗幻觉分层）。
- 单承重臂（mDeBERTa），judge 第二臂待补（skeptic 要求 ≥2）。
- 书面 kill criteria 见 `02_ACCEPTANCE.md`。

## venue

走 **ARR（ACL Rolling Review）**，滚动提交不赶死线；接受后 commit → **BioNLP / ClinicalNLP / CL4Health @ *ACL** 或 **EACL/EMNLP Findings**（临床 NLP，多语言/中文加分）。venue 惯例待深调研（researcher 在查）。

## 数据 / 算力

- 复用对照：PsiloQA（14语 span，`s-nlp/PsiloQA` CC-BY-4.0）、MedHallu（英医，`UTAustin-AIHealth/MedHallu` MIT）——见 `.portfolio/datasets.json`。
- 自建：中文医学 faithfulness（证据源 + 构造范式待深调研，见 `DATA_INVENTORY.md`）。
- 算力：低——检测器是 encoder/judge 推理档，8GB 本地 + HPC 4090 足够，无大训练。

## 文件导航

| 路径 | 内容 |
|---|---|
| `01_STORY.md` | 核心 Claim + delta + faithfulness 轴红线 + 章节弧 + 防御写法（⏳待深调研填充） |
| `02_ACCEPTANCE.md` | 二元 PASS/FAIL 验收 + kill criteria + 冻结判据（⏳待深调研填充） |
| `DATA_INVENTORY.md` | 数据细目：对照集 + 自建方案（⏳待深调研填充） |
| `04_LOG.md` | 时间倒序日志真源（首条=立项决策+pilot） |
| `reference/KILLSHOT_LEDGER.md` | 两发 pilot 的冻结判据 + 结果，防 HARKing |
| `reference/RESEARCH_BRIEF_2026-07-11.md` | **全量实验设计情报底座**（5路researcher综合：实验深度靶子/检测器全谱/数据构造管线/评测协议/venue约束/**K0命门修正**）|
| `PLAN/` | planner 出的正式实验矩阵（P1-P3 全量设计） |
| `_scratch/` | pilot 脚本（gitignore） |
