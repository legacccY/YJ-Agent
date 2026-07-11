# CMedFaith — 全量实验设计情报底座（5 路 researcher 综合，2026-07-11）

> 本文 = 派 planner 出全量实验矩阵前的情报综合。5 路并行深调研（对标协议 / 检测器全谱 / 数据构造 / venue 标准 / 统计方法学）成果压缩。
> 每条带来源；查不到标 TODO。数字入正文前仍 Bash/verifier 核。
> 服务 STORY 双贡献（L1 资源 + L2 检测器医学域失效发现）；只做 faithfulness（答案 vs 给定证据），不做 factuality。

---

## 0. 🔴 命门修正：K0 撞车核查对象错了（最高优先）

- **之前 K0「PASS」核的 `2025.findings-acl.211` 是张冠李戴**：其真身 = "Long-form Hallucination Detection with Self-elicitation"（Zihang Liu 等），**通用域长文本幻觉检测方法（SelfElicit 框架 + 图结构），跨 5 数据集，与中文/医学/数据集 release 全无关**。[来源: https://aclanthology.org/2025.findings-acl.211/]
- **"MedHallu-ZH" 不存在**：MedHallu 本体英文独占，HF `UTAustin-AIHealth/MedHallu` 只有 pqa_labeled(1000)+pqa_artificial(9000) 两 config，无 zh/multilingual 分支；官方 repo 亦无。[来源: https://huggingface.co/datasets/UTAustin-AIHealth/MedHallu ; https://github.com/MedHallu/MedHallu]
- **真正该核查的中文医学幻觉 benchmark = CMHE**（Chinese Medical Hallucination Evaluation, LREC-COLING 2024, Chengfeng Dou 等）：人工+模型混合构造，ICD-10+MeSH 术语表，焦点 = **snowballing hallucination（多轮误导下滚雪球）**，做检测/诊断/解释三任务。**非 evidence-conditioned（不是"答案 vs 给定证据段"）→ 不撞我们 headline #1**，但须写进相关工作 + KILLSHOT_LEDGER 补正式撞车条。[来源: https://aclanthology.org/2024.lrec-main.428/]
- **动作**：① 撤销 04_LOG/ACCEPTANCE 里 "MedHallu-ZH K0 PASS" 的错误表述，改为"MedHallu-ZH 系误指，实为 SelfElicit 通用域"；② 对 CMHE 补撞车核查（初判非 evidence-conditioned = 不撞，但需下载 Google Drive 核规模/许可/分层 → TODO）；③ headline #1 结论**不变**（中文医学 evidence-conditioned faithfulness 仍空白）。
- TODO: 下载 CMHE 数据核规模/幻觉分类/IAA/许可（Google Drive: `https://drive.google.com/drive/folders/1DrdovKwZIh6AX_JjL8BVpUmI9djiIwn_`）。

---

## 1. 实验深度靶子（对标 EACL/ACL 强 benchmark 中位数 → 我们"远超"目标）

对标 6 篇（RAGTruth ACL24 / MedHallu EMNLP25 / FaithBench NAACL25 / Bi'an / RAGBench / LettuceDetect）实测：

| 维度 | 对标中位数 | **CMedFaith 目标（远超）** |
|---|---|---|
| 主结果表 | ~5-6 | **≥8 主表**（+ 附录补齐）|
| 图 | ~4 | **≥6 图**（难度分层/错误类型饼图/校准曲线/中英迁移/judge 一致性）|
| 检测器基线 | ~11（MedHallu 17 最多）| **≥12-15，4 族**（NLI-encoder / 专用幻觉检测 / LLM-judge / finetune 小模型）|
| 分层维度 | ~3-4 | **≥5**（语言 zh/en × 幻觉类型 × 难度自然/对抗 × 医学子域 × 证据给/不给）|
| 评测级数 | 中位 2 级 | **3 级全做**（response / claim(原子陈述) / span）|
| 统计严谨度 | **多数无 IAA/CI/校准/单语** | **κ/α + bootstrap CI + AUROC/AUPRC + ECE 校准 + 中英对照**（直接系统性超越全部对标）|
| 数据规模 | ~1.5-2 万（医学域 MedHallu 10k）| **≥8-10k 中文医学 evidence-conditioned 样本**（医学可小而精，但 test 集类平衡明确）|
| 分析块 | MedHallu 6 块 = 事实标准 | **≥6 分析块 + ≥2 独立可迁移 findings** |

**"远超"配方（4 钩子叠加）**：RAGTruth 的 span 级标注 + MedHallu 的 6 分析块 + Bi'an 的中英迁移 + FaithBench 的"检测器分歧挑战集" → baseline ≥15、分析块 ≥6、独立 findings ≥2、全人工 IAA(κ/α) 报告。
**对标普遍软肋（我们的净增量）**：无 IAA κ/α（仅 FaithBench 报 Krippendorff α=0.748/0.679/0.58）、无 bootstrap CI、**无一篇报 ECE/校准**、多为单语。

---

## 2. 检测器横评清单（4 族，标中文支持 + 许可 + 算力）

> 关键洞察：**原生支持中文的专用检测器极稀缺**——只有 LettuceDetect 多语版（EuroBERT/mmBERT）。AlignScore/HHEM/MiniCheck/Lynx 全仅英文 → 这正是"英→中迁移崩塌"章节的天然素材（在中文上预期退化）。

### 族A NLI/蕴含（encoder，本地 8GB 全可跑）
| 检测器 | HF ID | 许可 | 中文 | evidence-cond 输入 |
|---|---|---|---|---|
| mDeBERTa-v3-XNLI（pilot 已用）| `MoritzLaurer/mDeBERTa-v3-base-xnli-multilingual-nli-2mil7` | MIT | ✅ 真多语15语 | premise=证据/hyp=答案 NLI 三分类 |
| AlignScore | `yzha/AlignScore`(base125M/large355M) | TODO核 | ❌仅英文 | context+claim chunk NLI |
| SummaC | `github.com/tingofurro/summac` | Apache(TODO核) | 底层NLI决定 | 句×句 NLI 矩阵 |
| HHEM-2.1-Open | `vectara/hallucination_evaluation_model` | Apache-2.0 | ❌仅英文(open版) | premise-hyp pair→0-1 |

### 族B 专用检测器
| 检测器 | HF ID | 许可 | 中文 | 备注 |
|---|---|---|---|---|
| **LettuceDetect 多语** | `KRLabsOrg/lettucedect-210m-eurobert-*` / `lettucedect-v2-mmbert-base` | MIT | ✅ 7-14语含中文 | **唯一原生中文专用**，token-level span，context-question-answer |
| LettuceDetect EN | `KRLabsOrg/lettucedect-base-modernbert-en-v1` | MIT | ❌英文 | 英文对照臂 |
| MiniCheck | `lytang/MiniCheck-Flan-T5-Large`(0.77B)/`bespokelabs/Bespoke-MiniCheck-7B` | MIT(7B待核) | ❌仅英文 | (doc,claim)→0/1，事实核查SOTA<1B |
| Patronus Lynx | `PatronusAI/Llama-3-Patronus-Lynx-8B-Instruct` | **CC-BY-NC**(非商用!) | ❌英文 | 含PubmedQA训练=医学素材，4090可 |
| RefChecker | `github.com/amazon-science/RefChecker` | Apache(TODO) | LLM extractor决定 | claim-triplet级，pipeline重→作消融不作主baseline |

### 族C LLM-judge
| judge | HF ID | 许可 | 中文医学 | 算力 |
|---|---|---|---|---|
| **Qwen2.5-7B-Instruct** | `Qwen/Qwen2.5-7B-Instruct` | Apache-2.0 | ✅ 主力 | 4090单卡 |
| Qwen2.5-72B | `Qwen/Qwen2.5-72B-Instruct` | Qwen License | ✅ 强 | 多卡/HPC |
| GLM-4-9B | `THUDM/glm-4-9b-chat` | TODO核 | ✅ C-Eval87.2 | 4090 |
| InternLM2.5-7B | `internlm/internlm2_5-7b-chat` | Apache(TODO) | ✅ | 4090 |
| DeepSeek-V3/R1 | API/超大MoE | MIT | ✅中国医考96% | 仅API |
| GPT-4o/Claude/Gemini | API | 商用 | ✅ | 参考臂（不可复现→不做主结论）|

### 族D finetune 小模型（我们自训基线，对标 RAGTruth「小模型 finetune 打平 GPT-4」钩子）
- 在我们中文医学训练集上 finetune 一个中文 encoder（mDeBERTa/中文 BERT）做检测，看能否打平 judge——RAGTruth/Bi'an 都用此钩子（Bi'an 14B judge 打平 Qwen2.5-72B）。

**推荐主横评**：族A全 + 族B(LettuceDetect多语+EN对照+MiniCheck英文+Lynx英文) + 族C(Qwen7B主+GLM/InternLM对照+GPT-4o参考) + 族D自训 = **约12-15个，4族齐**。
**judge prompt 范式**：RAGTruth式(request+context+answer→0-100分) / MedHallu式(question+GT+answer→二分类+"not sure"类可提F1达38%)。TODO: 逐字 prompt 需 clone RAGTruth/MedHallu repo 抓原文。

---

## 3. 数据构造：MedHallu 四阶段管线（照抄级细节，可复刻到中文）

**幻觉类型（MedHallu Table 1，4类，注意与我们B3命名不同）**：①误解问题(占~76%最大)②信息不全③机制/通路误归因④方法与证据捏造(占~0.5%最小)。

- **Phase1 候选生成**：prompt = 每类精确定义 + in-context 示例 + Qᵢ + 真值答案GTᵢ + 真值证据Cᵢ → 生成"语义相似但错误"答案。超参：**temperature 0.3-0.7 变动，top-p 0.95 固定，max 512 tokens，幻觉答案长度=真值±10%**。完整prompt在Appendix K。
- **Phase2 质检投票**：**3判别模型 GPT-4o mini + Gemma2-9B + Qwen2.5-7B**；保留规则=**骗过≥1个即保留**；**难度分层来自投票**：hard=全被骗/medium=部分被骗/easy=仅1个被骗（分布≈33/33/34）。
- **Phase3 双向蕴含过滤**：模型 `microsoft/deberta-large-mnli`；分数 ℰ=min(NLI(H→GT),NLI(GT→H))；**阈值τ=0.75**，保留 ℰ<τ（防幻觉其实是同义正确答案）。中文需换中文 NLI（mDeBERTa）。
- **Phase4 TextGrad 精修+兜底**：后端 GPT-4o mini，最多5次尝试；兜底=选与GT余弦相似度最大的候选。
- [来源: https://arxiv.org/html/2502.14302v1 §3/Table1/Algorithm1] TODO: Appendix K prompt 全文 + embedding 型号需 clone repo 核（`github.com/MedHallu/MedHallu` Dataset Generation/ 目录，MIT）。

**中文证据源（全核许可）**：
| 源 | HF | 许可 | 规模 | 证据字段 |
|---|---|---|---|---|
| Huatuo-26M | `FreedomIntelligence/Huatuo-26M`(encyclopedia_qa/KG_qa 子集) | **Apache-2.0** | 2600万 | Q/A，🟢首选可分发 |
| CMExam | `williamliujl/CMExam` | ⚠️**代码Apache/数据学术禁商用（冲突！）** | 68,119 MCQ | Explanation(均192tok)当证据；🟡保守只内部构造不分发 |
| CMB | `FreedomIntelligence/CMB` | Apache(LICENSE待核) | 11,200+ | CMB-test带解释 |
| 中文维基医学 | HF wikipedia zh | **CC-BY-SA(share-alike传染!)** | 全站 | 🟢可用注意同协议 |
- 选源红线：分发只用可再分发许可（Huatuo-26M首选/维基）；**CMExam 数据许可与repo Apache冲突 → 保守只内部构造不进发布集，或只发我们生成的幻觉答案+指针**。

**中文医学幻觉类型学定稿建议（我们B3的7类核实后）**：
- ✅ 已覆盖映射清晰：证据篡改=RAGTruth Conflict / 无关=Baseless / 过度断言=spurious / 信息不全=MedHallu Incomplete / 机制误归因=MedHallu Mechanism / 捏造指南=fabricated sources。
- ⚠️ **剂量/数值错**：三源都无独立命名类（散在 Evident Conflict/Evidence Fabrication）→ 作中文医学特有类保留合理**且是我们贡献点**，但须标"本工作细化派生非直接引自源"。
- 🔺 建议补2类：**过时/被推翻的指南**（真实但过时，≠捏造）+ **诊断/治疗决策误导**（医学高危，可从证据判忠实）。
- 🔻 建议剔除：temporal/causal reasoning/memory/multimodal（属factuality/推理错非"答案vs证据"，纳入会confound → 呼应STORY faithfulness≠factuality红线，taxonomy定稿处显式写剔除理由）。
- **正交双轴设计（对齐K2对抗confound）**：用 **RAGTruth Evident/Subtle 轴**充当"自然vs对抗"分层可操作化（Subtle=对抗/难，Evident=自然/易），内容型7-9类作另一轴，类型与难度解耦。
- [来源: RAGTruth 2401.00396 是 Conflict/Baseless×Evident/Subtle 2×2轴非并列4类；医学综述 2503.05777 §2.3]

**标注协议省力路线（本科团队，K-QA全专家=400工时/2.6万美元跳不起）**：
1. 主粒度=**response级二分类**报 Cohen κ（对标 RAGTruth response 91.8%易达高一致）。
2. 自动共识=MedHallu那套（多LLM投票+中文NLI双向蕴含）先筛，人工只裁决冲突+hard层。
3. 原子陈述级NLI（K-QA式）只在hard子集做（可定位、比span易一致）。
4. hard层专家抽检（非全量）+报 Krippendorff α。
5. IAA报告：response级Cohen κ(主)+hard子集原子级Krippendorff α(辅)。
- ⚠️ **RAGTruth 91.8%/78.8% 出处存疑**：可能是finetuned Llama-2-13B的**模型检测F1**而非IAA一致率 → **TODO人工核 arXiv 2401.00396 annotation小节**；若为模型性能，ACCEPTANCE 引它当IAA对标是错配，改用 **FaithBench Krippendorff α=0.748** 作对标。

---

## 4. 评测协议推荐表（指标×粒度×统计检验，专业精密）

| 维度 | Response级 | Claim级(原子陈述) | Span级 |
|---|---|---|---|
| 主指标 | **Balanced Accuracy + Macro-F1** | BA+Macro-F1 | overlap **P/R/F1（char-level，中文更稳）** |
| 辅助单值 | MCC | MCC | soft(partial-overlap)F1 |
| 阈值无关 | **AUPRC(主)+AUROC** | AUPRC+AUROC | — |
| 校准 | **ECE(15-bin)+reliability diagram+Brier** | 同 | 可选 |
| 点估计CI | **bootstrap 95%CI（≥1000，荐10000 resamples）** | 同 | 同 |
| 配对检验 | **McNemar(仅accuracy)+paired bootstrap(BA/F1)** | paired bootstrap/permutation | paired bootstrap on span-F1 |
| 多检测器校正 | **Holm-Bonferroni(FWER)**，多则BH(FDR) | 同 | 同 |
| effect size | ΔMacro-F1 + bootstrap CI（G带CI） | 同 | ΔspanF1+CI |

**🔴 三个必守校正**：
1. **F1/BA 不能用 McNemar**（仅accuracy可）→ 必须 paired bootstrap/permutation。[来源: arXiv 1609.09471]
2. 横评多检测器 → **Holm-Bonferroni**（优于Bonferroni，同FWER更powerful）。
3. span/claim/response **三级各建独立表各带CI，绝不混报**（L2-b铁律）。

**LLM-judge稳定性（贯穿三级独立报，R5）**：自一致性(n≥5采样方差/多数票稳定率)+inter-judge κ/Fleiss(≥2家族)+judge-vs-人工κ+**position bias控制(交换顺序保双序一致，翻转率10-15pt)+verbosity bias控制(rubric长度中立，15-30pt偏长)**。框架G-Eval。
**校准是差异化贡献**：MedHallu/FaithBench均未系统报calibration，我们报ECE+Brier+温度缩放=净增量（高风险医学场景刚需）。
**IAA目标κ/α≥0.7合理**：Landis-Koch substantial高端，高于FaithBench含灰区0.679接近干净binary0.748；主报Krippendorff α + Cohen κ双标子集对照。

---

## 5. venue 硬约束（ARR/EACL）

- **页数**：long 8页正文(接收+1)，short 4页(+1)；references/Limitations/Ethics/appendices **不计页数**。
- **Limitations 强制独立章节**：缺=**desk reject 不评审**；该节不得引入新方法/结果。
- **Responsible NLP Checklist 强制**：填错/误导可desk reject；**EMNLP2025起随文作附录公开**。
- **Ethics**：医学数据须声明去标识化+证据源许可+不作临床建议。
- **数据/复现**：匿名repo必需，**禁Dropbox/Google Drive明链**；AI写作/编码须在checklist+Acknowledgements声明。
- **venue路线**：首选 ARR→EMNLP/EACL main（Findings兜底）拿含金量；领域退路 BioNLP/ClinicalNLP workshop（reviewer更懂医学evidence，隐私伦理审更重）。中文多语点在EACL吃香，临床伦理点在ClinicalNLP更被理解。
- **双贡献叙事范式（Bi'an/MedHallu）**：主claim=资源本身（数据+标注管线+评测协议）；兜底findings=资源上跑出的可迁移发现。benchmark"更难"的claim **必须实验支撑**（=SOTA检测器在我们集上掉分）。

---

## 6. 对 STORY/ACCEPTANCE 的更新建议（planner/主线执行）

1. **K0 改写**：MedHallu-ZH 系误指（实为SelfElicit通用域）；新增 CMHE 撞车核查条（初判非evidence-conditioned不撞，待下载核）。
2. **DATA_INVENTORY 更新**：撤MedHallu-ZH；CMExam许可降级为"内部构造不分发";B3补2类(过时指南+诊断决策误导)并剔reasoning类;明确RAGTruth是2×2轴非并列4类;正交双轴(内容型×Evident/Subtle)。
3. **ACCEPTANCE 修**：IAA对标从"RAGTruth 91.8%"改/补 FaithBench Krippendorff α=0.748（待核RAGTruth数口径）；主指标BA+Macro-F1✅已对齐FaithBench无需改；span报P/R/F1✅已对；补统计检验规范（paired bootstrap非McNemar + Holm-Bonferroni + ECE校准）。
4. **规模阈定稿**：≥8-10k 中文医学 evidence-conditioned 样本，test集类平衡明确。

---

## 引用总表（关键）
- RAGTruth ACL24 https://arxiv.org/abs/2401.00396 ｜ MedHallu EMNLP25 https://arxiv.org/abs/2502.14302 ｜ FaithBench NAACL25 https://aclanthology.org/2025.naacl-short.38/ ｜ Bi'an https://arxiv.org/abs/2502.19209 ｜ RAGBench https://arxiv.org/abs/2407.11005 ｜ LettuceDetect https://arxiv.org/abs/2502.17125
- CMHE LREC-COLING24 https://aclanthology.org/2024.lrec-main.428/ ｜ SelfElicit(误指真身) https://aclanthology.org/2025.findings-acl.211/ ｜ 医学幻觉综述 https://arxiv.org/html/2503.05777v2 ｜ K-QA https://arxiv.org/html/2401.14493
- 证据源: Huatuo-26M https://github.com/FreedomIntelligence/Huatuo-26M ｜ CMExam https://github.com/williamliujl/CMExam ｜ CMB https://github.com/FreedomIntelligence/CMB
- 统计: paired bootstrap https://arxiv.org/pdf/1609.09471 ｜ Holm-Bonferroni https://personal.utdallas.edu/~herve/abdi-Holm2010-pretty.pdf ｜ ARR CFP http://aclrollingreview.org/cfp

---

## 7. 前置 TODO 解决（2026-07-11 续，实现级增量，源码逐字核）

**MedHallu 四阶段逐字实现（clone `github.com/MedHallu/MedHallu` MIT，session 临时目录，建议主线 clone 到 `vendor/`）**：
- 四型幻觉 prompt + in-context 示例：`Dataset Generation/Prompts/system_prompt_medical.txt`（行 24-62）。生成约束逐字：`Hallucinated Answer can only have about 5 more words than Ground truth answer`；`Justification 不超过 2 倍长 + 带 citations`。
- Phase4 兜底 embedding = **`all-MiniLM-L6-v2`**（sentence-transformers，`generation.py:266`，`util.pytorch_cos_sim` 选候选）。
- Phase3 双向蕴含模型 = **`roberta-large-mnli`**（`Detection/bidirectional_checking.py:12`，**非之前以为的 deberta-large-mnli**）。中文复刻换 mDeBERTa/中文 NLI。
- Phase2 ensemble 投票 = GPT-4o-mini + Gemma2-9B + Qwen2.5-7B 多数投票；Phase4 TextGrad backend = GPT-4o-mini 最多 5 次；默认生成器 = Qwen2.5-14B-Instruct（可配）。

**judge 逐字 prompt**：
- MedHallu（`Detection/detection_vllm_notsurecase.py:30-70`）：`Answer '0' if factual, '1' if hallucinated, '2' if unsure（choose 2 instead of guessing）`；带证据版多 `World Knowledge: {knowledge}` 行。
- RAGTruth（`baseline/dataset.py:19-50`）：**span 抽取式 JSON**（`{"hallucination list":[...]}`）非 0-100 打分；按 QA/Summary/Data2txt 三套模板。

**finetune 官方超参**：
- RAGTruth（arXiv:2401.00396 §5.1）：full-ft，lr **2e-5**，**1 epoch**，4×A100，基座 Llama-2-13B。⚠️ **batch/max_length/optimizer/warmup 论文未披露→TODO 不臆想**（repo baseline 是另一套 LoRA-7B 口径 `lora_r=8/alpha=32`，复现前拍板对齐哪套）。
- Bi'an（arXiv:2502.19209 Table15）：基座 Qwen2.5-7B/14B，LoRA r=8/alpha=16，SFT lr 5e-5 + DPO lr 5e-6，batch4，ep3，warmup0.1，cosine，序贯 SFT→DPO。（HTML 读，入 D15 前 Read PDF 表15 逐字核）

**许可定论（可再分发/商用）**：AlignScore=MIT｜SummaC=Apache2.0｜RefChecker=Apache2.0（三者自由并入）｜GLM-4-9B=glm-4 license 学术免费/商用须注册｜InternLM2.5=学术免费/商用填表｜**MiniCheck-Bespoke-7B=CC-BY-NC 禁商用**｜**Lynx-8B=CC-BY-NC 禁商用**（后两者仅非商用研究评测，写清用途）。

**RAGTruth 91.8%/78.8% 口径定论**：= **人际一致率 IAA**（§3.3 `consistency rate of two annotators`），**非模型 F1** → 可引当 IAA 对标；但是**未偶然校正的原始 agreement rate**，与 FaithBench Krippendorff α=0.748 不同类，引用须注明"未校正一致率"避免直接混比。**结论：ACCEPTANCE 的 κ≥0.7 阈值不改，只需在措辞处标清对标口径**。

**CMHE 撞车**：LREC-COLING2024，对话式 snowballing 幻觉（多轮被误导），评检测/诊断/解释，ICD-10+MeSH 构造。**非 evidence-conditioned（无给定检索证据字段）→ 不撞 headline #1**。TODO: 精确规模/IAA 需主线下 Google Drive + 读全 PDF §3-4 复核后冻结"不撞"。
