# CMedFaith — 数据清单

> 数据集真源 = `.portfolio/datasets.json`（本地/HPC/source/状态）；本文只记细目与构造方案，路径不硬编码。
> ⏳ 部分待 researcher（竞品/delta）回来定稿。数字/许可跑前 Bash 核。

## A. 对照集（现成，已用于 pilot）

| 数据集 | 用途 | 来源 | 许可 | 规模 | 状态 |
|---|---|---|---|---|---|
| PsiloQA | 通用域对照 + 中文通用 faithfulness | `s-nlp/PsiloQA` (HF) | CC-BY-4.0 | 中文 5757 / 英文 18103（span级，wiki证据）| 已下载 scratchpad |
| MedHallu | 英文医学 faithfulness（pilot#2 医学臂 + 构造蓝本）| `UTAustin-AIHealth/MedHallu` (HF) | MIT | 10k（1k人工pqa_labeled + 9k合成）| 已下载 |

## B. 自建目标：中文医学 RAG faithfulness（本项目核心工作量）

现状：**中文医学 evidence-conditioned faithfulness 数据 = 零**（Bi'an 中文无医学、MedHallu 英文、PsiloQA 通用）。需半自动自建。

### B1. 中文医学证据源（RAG 的"给定证据"段，researcher 2026-07-11 核许可）

| 源 | 能否作 evidence | 许可 | 规模 | 判定 |
|---|---|---|---|---|
| **Huatuo-26M** | ✅ encyclopedia_qa/KG_qa 可作证据 | **Apache 2.0**（最宽松）| 2600万 QA | 🟢 首选，可随数据集分发 |
| **CMExam** | ✅ 85% 题带解释，解释当证据段 | 学术用禁商用 | 60K+ 执业医考 | 🟢 可用（学术）|
| **中文维基医学条目** | ✅ | CC BY-SA（署名+同协议）| 全站医学 | 🟢 可用，注意 share-alike |
| CMB (FreedomIntelligence) | ✅ 分层临床 QA | 待核 HF 卡 | 11,200 题 | 🟡 核许可后用 |
| MRAG-CLFQA | ⚠️ 1253 中文问诊 | 拟 CC-BY-4.0 "upon acceptance" | 1253 | 🟡 待确认是否已 release |
| 默沙东中文/中华医学会指南/UpToDate | ⚠️ 权威但**版权受限禁再分发** | 商业/版权 | — | 🔴 只可内部构造不分发，或改用其派生公开 QA |

> 选源红线：**分发的数据集只用可再分发许可的证据源**（Huatuo-26M/维基/CMExam）；版权受限源（指南/UpToDate）不进公开发布。

### B2. 构造范式（照 MedHallu 半自动四阶段，本科团队可行）

1. **候选生成**：LLM + in-context 示例 + 精确幻觉类型定义，从（证据段, 忠实答案）生成"语义相似但不忠实"的幻觉答案。
2. **质检过滤**：LLM 集成投票（ensemble）+ 双向蕴含（bidirectional entailment）过滤劣质候选。
3. **精修**：失败样本用反馈迭代改写（MedHallu 用 TextGrad）。
4. **兜底**：生成失败选语义最接近候选。
- 人工只做**小比例质检 + hard 层专家抽检**（不走 K-QA 的全专家路线：那要 400 工时/2.6万美元，本科跳不起）。

### B3. 医学幻觉类型学（覆盖清单，综合 MedHallu 4类 + 医学综述 arXiv:2503.05777 7类 + RAGTruth 4类）

至少覆盖：① 证据篡改/捏造 ② 证据无关（baseless）③ **剂量/数值错**（医学特有，numerical fabrication）④ 过度断言（overclaim）⑤ 信息不全（最难检测）⑥ 机制/通路误归因 ⑦ 捏造指南/引用。
→ **自然 vs 对抗构造分层**（回应 pilot 的对抗 confound，见 ACCEPTANCE K2）。

### B4. 标注协议

- **粒度**：主标 response 级（省，RAGTruth 一致性 91.8%）+ 原子陈述级 NLI（K-QA 式，可定位且比字符 span 易达一致）；span 级只在 hard 子集做。
- **共识**：多 LLM 集成投票 + 双向蕴含（MedHallu 已证医学域可行）；冲突条第三方裁决；hard 层专家抽检。
- **IAA**：双标 + 报 Cohen's κ / Krippendorff α，对标 RAGTruth（response 91.8% / span 78.8%）。

### B5. 规模目标
⏳ 待定（参考 MedHallu 1k 人工 + 合成扩充；中文医学至少 ~1-2k 人工验证核心 + 合成扩充）。researcher/planner 回来定。

## C. 待登记
- [ ] PsiloQA / MedHallu 写入 `.portfolio/datasets.json`
- [ ] 自建数据集建成后登记本地+HPC 路径
