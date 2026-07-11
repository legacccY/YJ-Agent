# CMedFaith — 数据清单

> 数据集真源 = `.portfolio/datasets.json`（本地/HPC/source/状态）；本文只记细目与构造方案，路径不硬编码。
> ⏳ 部分待 researcher（竞品/delta）回来定稿。数字/许可跑前 Bash 核。

## A. 对照集（现成 + 自建锚，含 K2 三角互证臂）

| 数据集 | 用途 | 来源 | 许可 | 规模 | 状态 |
|---|---|---|---|---|---|
| PsiloQA | 通用域对照 + 中文通用 faithfulness | `s-nlp/PsiloQA` (HF) | CC-BY-4.0 | 中文 5757 / 英文 18103（span级，wiki证据）| 已下载 scratchpad；**方案 A 后降为「未匹配旧锚」**（未过我们"骗过≥1检测器"筛子，仅作对照展示不对称化会得到的膨胀 G_domain，见 PLAN §0.6）|
| MedHallu | 英文医学 faithfulness（pilot#2 医学臂 + 构造蓝本）| `UTAustin-AIHealth/MedHallu` (HF) | MIT | 10k（1k人工pqa_labeled + 9k合成）| 已下载 |
| **MedFact** | **K2 真自然医学臂（三角互证，R-P3.12）**：中文自然医学 fact-checking，Yi-Large 自发作答，检验"真自然医学也弱"外部闭合 | `arXiv:2509.17436`（zh 自然医学 fact-checking） | **Apache-2.0** | 1321 Q / 7409 claims | ⏳ 待下载适配；⚠️ **偏 factuality（"答案 vs 世界知识"），须重构成 evidence-conditioned（"答案 vs 给定证据"）**，重构不干净则只作外部效度参考不进主判据（守 R3，faithfulness≠factuality）|
| **CMHE** | **撞车对照 + related work**（非 evidence-conditioned，不撞 headline #1）：中文医学**对话式 snowballing** 幻觉（多轮被误导），做检测/诊断/解释三任务，ICD-10+MeSH 构造 | `LREC-COLING2024`（Chengfeng Dou 等，`2024.lrec-main.428`）| 规模/许可 **TODO**（Google Drive `1DrdovKwZIh6AX_JjL8BVpUmI9djiIwn_` 下载核）| **TODO**（初判 ~对话集，非"答案 vs 给定证据段"）| ⏳ 下载核规模/IAA/许可后冻结"不撞"；**非 evidence-conditioned → 不作主评测集**，只进撞车终检 + related work |
| **CMedFaith-zh-gen-adv 对称通用对抗锚** | **K1/K2 域对照主锚（方案 A 主力，R-P2.7 建）**：通用域也过**同 MedHallu 管线 + 同"骗过≥1检测器"筛子**，把构造/选择异质性钉成常量，替代 PsiloQA-zh 作域对照 | 自建（中文百科同粒度同风格~192tok条目为证据）| 随管线产物（证据源可再分发许可）| ≥8-10k（与 zh-med 对齐 n）| P2 建（R-P2.7）；同筛检测器集须与 zh-med 严格一致（冻结进 spec+KILLSHOT）|

## B. 自建目标：中文医学 RAG faithfulness（本项目核心工作量）

现状：**中文医学 evidence-conditioned faithfulness 数据 = 零**（Bi'an 中文无医学、MedHallu 英文、PsiloQA 通用）。需半自动自建。

### B1. 中文医学证据源（RAG 的"给定证据"段，researcher 2026-07-11 核许可）

| 源 | 能否作 evidence | 许可 | 规模 | 判定 |
|---|---|---|---|---|
| **Huatuo-26M** | ❌ **实测退化**（researcher 2026-07-11 核字段）：encyclopedia_qa/KG_qa 均只有 questions/answers **无独立证据段**（答案即证据，做不了 evidence-conditioned）| Apache 2.0 | 2600万 QA | 🔴 **不能作 evidence-conditioned 证据源**（可分发但无独立证据）|
| **CMExam** | ✅✅ **唯一可行 evidence-conditioned 源**（researcher 2026-07-11 实测）：`Explanation` 临床解析段(4-3k字，可空)→独立证据，`Question`+正确选项文本→忠实答案 | ⚠️ 国家医师考题许可受限（数据卡"学术禁商用"vs repo `williamliujl/CMExam` Apache-2.0 冲突，正式发布前核 LICENSE）| 68,119 MCQ（train54497/val6811/test6811）| 🟡 **zh-med 主证据源（内部构造）**；发布只发生成幻觉答案+CMExam题目ID指针，不重分发 Explanation 原文 |
| **中文维基医学条目** | ✅ | CC BY-SA（署名+同协议）| 全站医学 | 🟢 可用，注意 share-alike |
| CMB (FreedomIntelligence) | ✅ 分层临床 QA | 待核 HF 卡 | 11,200 题 | 🟡 核许可后用 |
| MRAG-CLFQA | ⚠️ 1253 中文问诊 | 拟 CC-BY-4.0 "upon acceptance" | 1253 | 🟡 待确认是否已 release |
| 默沙东中文/中华医学会指南/UpToDate | ⚠️ 权威但**版权受限禁再分发** | 商业/版权 | — | 🔴 只可内部构造不分发，或改用其派生公开 QA |

> 选源红线 + **🔴 承重张力（researcher 2026-07-11）**：可分发的 Huatuo-26M **实测无独立证据段、做不了 evidence-conditioned**（核心护城河）；唯一有独立证据段的 CMExam **许可受限**。**解法**=CMExam 内部构造作 **zh-med 主证据源**，发布只发生成的幻觉答案+题目ID指针（不重分发 Explanation 原文），核 CMExam LICENSE 确认（MedHallu 外常见合规做法）。⚠️ CMExam 是选择题解析当证据，与典型 RAG 检索文档段性质略异，数据构造说明须写清。版权受限源（指南/UpToDate）不进发布。

### B2. 构造范式（照 MedHallu 半自动四阶段，本科团队可行）

逐字实现指针引 `reference/RESEARCH_BRIEF_2026-07-11.md` §7（clone `github.com/MedHallu/MedHallu` MIT 源码核）：

1. **Phase1 候选生成**：LLM + in-context 示例 + 精确幻觉类型定义，从（证据段, 忠实答案）生成"语义相似但不忠实"的幻觉答案。超参逐字：**temperature 0.3–0.7 变动 / top-p 0.95 固定 / max 512 tokens**；**幻觉答案长度 = 真值 ±10%**（原文 `Hallucinated Answer can only have about 5 more words than Ground truth answer`）；Justification 不超过真值 2 倍长 + 带 citations。prompt/示例源=`Dataset Generation/Prompts/system_prompt_medical.txt`（行 24-62）。
2. **Phase2 质检投票（定难度）**：ensemble = **GPT-4o-mini + Gemma2-9B + Qwen2.5-7B** 多数投票；保留规则 = **骗过 ≥1 个即留**；**难度分层来自投票**：hard=全被骗 / medium=部分被骗 / easy=仅 1 个被骗（≈33/33/34）。⚠️ Qwen2.5-7B 是构造投票器成员（D10），据 PLAN §0.6 单列标"构造参与不进 K1 承重 judge"（解 skeptic 🔴-2 循环）。
3. **Phase3 双向蕴含过滤（滤 factuality）**：模型 = **`roberta-large-mnli`**（`Detection/bidirectional_checking.py:12`，**非之前以为的 deberta-large-mnli**）；分数 ℰ=min(NLI(H→GT), NLI(GT→H))，**阈值 τ=0.75** 保留 ℰ<τ（防幻觉其实是同义正确答案，守 R3）。**中文复刻换 mDeBERTa / 中文 NLI**。
4. **Phase4 精修 + 兜底**：TextGrad 反馈迭代改写（backend GPT-4o-mini，最多 5 次）；**兜底 embedding = `all-MiniLM-L6-v2`**（sentence-transformers，`generation.py:266`，`util.pytorch_cos_sim` 选与 GT 余弦相似度最大候选）。
- 人工只做**小比例质检 + hard 层专家抽检**（不走 K-QA 的全专家路线：那要 400 工时/2.6万美元，本科跳不起）。

### B3. 医学幻觉类型学（定稿：正交双轴，综合 MedHallu 4类 + 医学综述 arXiv:2503.05777 7类 + RAGTruth 2×2轴）

**正交双轴设计**（内容型 × 难度轴解耦，对齐 ACCEPTANCE K2 对抗 confound 控制）：

**轴一 · 内容型（7 类 + 补 2 类 = 9 类）**：① 证据篡改/捏造 ② 证据无关（baseless）③ **剂量/数值错**（本工作细化派生，**非直接引自 MedHallu/RAGTruth**——三源均无独立命名类，散在 Evident Conflict/Evidence Fabrication，作中文医学特有类保留）④ 过度断言（overclaim）⑤ 信息不全（最难检测）⑥ 机制/通路误归因 ⑦ 捏造指南/引用 + **补** ⑧ **过时/被推翻的指南**（真实但过时，≠捏造）⑨ **诊断/治疗决策误导**（医学高危，可从证据判忠实）。
- **剔除**：temporal / causal reasoning / memory / multimodal——属 **factuality/推理错**（"答案 vs 世界知识"），非"答案 vs 给定证据"，纳入会 **confound faithfulness**，故显式剔除以呼应 STORY faithfulness≠factuality 红线 + R3。

**轴二 · 难度轴（natural / adversarial）**：natural = 现成检测器天然易判 / adversarial = 同管线 + 同"骗过≥1检测器"筛子造的难例。**方案 A 后由对称化操作化**：医学域与通用域**双侧均过同管线造对抗集**，把构造强度钉成常量后比域效应（见 ACCEPTANCE K2 重述 + PLAN §0.6）。

**⚠️ 订正（防误用）**：**RAGTruth 的 4 类实为 2×2 正交轴**（Conflict/Baseless × **Evident/Subtle**），非并列 4 类 [来源: arXiv:2401.00396]。**Evident/Subtle 是"幻觉显隐性"（自然幻觉内部的难度梯度）≠"自然 vs 对抗构造来源"**——RAGTruth 全集皆自然幻觉，Evident/Subtle 只是其显隐分层；我们全集皆对抗构造、零自然样本。**故不再把 Evident/Subtle 当 natural/adversarial 轴用**（这是 skeptic 🔴-3 命门），对称化设计已改用**同管线造对抗集**解决域对比的构造 confound。

### B4. 标注协议

- **粒度**：主标 response 级（省，RAGTruth 一致性 91.8%）+ 原子陈述级 NLI（K-QA 式，可定位且比字符 span 易达一致）；span 级只在 hard 子集做。
- **共识**：多 LLM 集成投票 + 双向蕴含（MedHallu 已证医学域可行）；冲突条第三方裁决；hard 层专家抽检。
- **IAA**：双标 + 报 Cohen's κ / Krippendorff α，对标 RAGTruth（response 91.8% / span 78.8%）。

### B5. 规模目标（定稿，2026-07-11）
**≥8-10k 中文医学 evidence-conditioned 样本**（`CMedFaith-zh-med`），**test 集类平衡明确**（faithful/unfaithful 均衡，不搞 PsiloQA 39:261 极不平衡）。医学域可小而精，但 test 类平衡是硬约束。对称通用对抗锚 `CMedFaith-zh-gen-adv` 规模与 zh-med 对齐 n（同筛后下采样匹配）。对标：MedHallu 英文医学 10k。[来源: RESEARCH_BRIEF §1 靶子表 + §6.4]

## C. 待登记
- [ ] PsiloQA / MedHallu 写入 `.portfolio/datasets.json`
- [ ] 自建数据集建成后登记本地+HPC 路径
