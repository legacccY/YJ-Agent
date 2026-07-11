# CMedFaith 全量实验矩阵设计 P1–P3

> Planner 交付，2026-07-11（主线落盘）。服务 STORY 双贡献（L1 中文医学 faithfulness 资源 + L2 检测器医学域失效发现），对齐 ACCEPTANCE 的 L1/L2 判据 + K1/K2/K3 kill criteria。只设计不写码不跑；实现交 coder，跑交主线（`/loop /run-experiment`），分析交 analyst。
> 数据源/超参一律引 RESEARCH_BRIEF（`reference/RESEARCH_BRIEF_2026-07-11.md`）来源；查不到标 TODO。判据不自创，用 ACCEPTANCE 既定值。
> 🛑 **skeptic 红队 2026-07-11 出 3 条 🔴 致命（已联网核实承重事实）——见下 §0.5。三条同根：对照锚 PsiloQA-zh 未与我们"骗过≥1检测器"筛过的 zh-med 集匹配（构造管线/选择筛子/模型身份三处不匹配）。仅阻断 K 判决 run（R-P3.4/3.5/3.6）+ 判据预注册；P1/P2/主横评/R-P1.0 不阻断可推进。K 判决设计待修 + 🔴-3 待用户拍板后定稿。**

## 0.5 skeptic 红队结论（2026-07-11，3🔴 阻断 K 判决）

| # | severity | 攻击点 | 修法 | 状态 |
|---|---|---|---|---|
| 🔴-1 | 致命 | 对照锚 PsiloQA-zh 未过"骗过≥1检测器"筛子，zh-med 过了 → `G_domain=F1(gen)−F1(med)≥0.05` 是**选择伪迹**非域效应，K1/K3 假闸 | 给一般域锚施加**同管线+同筛子**（中文维基一般条目自建 general 锚），或 PsiloQA-zh 补过同筛后再跑 | 待修 |
| 🔴-2 | 致命 | 构造投票器含 Qwen2.5-7B = K1 承重 judge D10 同体 → 循环（专挑它答错的考它），judge 臂失效近构造保证 | K1 承重 judge 改用**非投票器** D11(GLM-4)/D12(InternLM2.5)，D10 单列标"构造参与不进 K1 承重"，生成器↔最终评测器解耦 | 待修 |
| 🔴-3 | 致命 | **Evident/Subtle ≠ natural/adversarial**（核实：RAGTruth 全自然、Evident/Subtle 只是自然内部难度梯度；我们全集皆对抗构造、零自然样本）→ K2 无真自然医学臂可剥，对抗-confound 控制无效，红线3难度归因作废 | **建真自然医学臂**（RAGTruth 式采集 LLM 自发医学幻觉，额外成本）→ 干净 K2；或**诚实降级 headline #2 对抗鲁棒性**并红线3处收紧"不 claim 医学域本身难" | 🛑**待用户拍板** |

**🟠 值得改（不阻断）**：① 族D D15 train→test 同管线泄漏 → 加跨管线泛化测 + provenance-shortcut 探针（只用长度/困惑度/生成器特征训分类器，若也高分=全集有来源捷径）；② 证据长度/风格 confound（PsiloQA 维基片段 vs 我们 Huatuo/CMExam ~192tok）→ K1/K3 匹配证据长度分布或回归掉长度；③ Finding-1 的域×语言 2×2 被三管线混杂 → 至少 zh-med/en-med 同管线自建平行，措辞降"可比条件下"；④ Evident/Subtle 标注规程未定义（spec gap）→ taxonomy 定稿处显式定义，与投票难度轴分开。

**🟢 可接受残差**：中文 claim 分句/span char 边界（已选 char-level soft-F1 缓解，指定确定性分句器即可）；K1/K2/K3 的 FAIL 退路机制本身站得住（#1收缩/#2/#3 均诚实退守，修完 🔴 后可直接沿用）。

**放行裁决**：可立即 GO（不受🔴阻断）= R-P1.0 英文对照复现 / P1 中文构造 pilot / P2 数据集成+IAA / R-P3.1 主横评（建 L1 资源+出主表）。**修完 🔴-1/🔴-2 + 🔴-3 拍板后**再预注册并跑 R-P3.4/3.5/3.6。承重事实来源：RAGTruth Evident/Subtle=自然幻觉显隐性 https://arxiv.org/pdf/2502.17125 ；MedHallu hard/med/easy=骗过检测器过滤+faithful=GT https://aclanthology.org/2025.emnlp-main.143.pdf

### 🔴-3 解法研究结论（2026-07-11，researcher）— 待用户拍板

**推荐方案（researcher 排序）：对称化主力 ★★★★★ + MedFact 三角互证 ★★★ + 协变量回归 robustness 附录 ★★**。

| 解法 | 做法 | 成本 | 消 confound | 
|---|---|---|---|
| **①对称化（主力）** | 通用锚也过同 MedHallu 管线+同"骗过≥1"筛子（中文百科一般条目造对抗集）→ 双侧同为对抗构造，构造钉成常量 | **低**（管线已建，换证据源跑 compute） | **是·最干净**（一石二鸟消 🔴-1+🔴-3）|
| **②MedFact 自然臂** | 中文自然医学 fact-checking 集（`arXiv:2509.17436`，1321Q/7409claims，Apache-2.0，Yi-Large 自发作答）当真自然臂三角互证 | 极低采集/中适配（偏 factuality 需重构成"给定证据"格式） | 部分（真自然但跨集异质性新 confound）|
| **③协变量回归** | 用现有 hard/med/easy 难度层当对抗强度代理回归掉，看域主效应 | 极低（纯分析） | 部分（robustness 附加，单独不够）|
| **④轻量自建自然臂** | 同批证据让 LLM 自然作答采集自发幻觉+人工标注（几百条够 K2 power）| 中-高（人工标注主成本） | 是（reviewer 硬要真自然时上）|

**关键权衡**：①对称化**重述 K2**——从「剥掉对抗后医学域**本身**难」→「**等构造强度下**医学域仍比通用难」（更正确的因果对比，把构造钉成常量，但换了问题）。**残余 confound**：证据源异质性（通用百科 vs 医学 PubMed 风格）→ 通用锚须选**同粒度同风格**中文百科/教科书条目，文中显式声明证据源为残余变量。**无具名 benchmark 先例**（matched design 原理支持）= 既是坑（无照抄）也是**方法贡献点**。
**上游背书**：MedHallu 原作也无同管线通用对照（医学vs通用仅文献综述非受控）→ 对称化填真空白。来源: https://arxiv.org/html/2502.14302v1 ; 构造confound实证 https://arxiv.org/html/2410.12278v1 (去HPG F1 0.908→0.973) ; MedFact https://arxiv.org/html/2509.17436v1
**✅ 用户 2026-07-11 拍板方案 A**（对称化主力 + MedFact 自然臂三角互证 + 协变量回归 robustness）。K 判决据此定稿 → 见下 §0.6。

---

## 0.6 K 判决修订版（方案 A 定稿，2026-07-11 planner）

**三 🔴 定稿修法**：

| # | 状态 | 定稿修法 |
|---|---|---|
| 🔴-1 选择伪迹 | ✅已解 | 通用锚改用**对称通用对抗锚 CMedFaith-zh-gen-adv**（同 MedHallu 管线+同"骗过≥1检测器"筛，中文百科同粒度同风格条目）→ 双侧同筛，选择效应钉常量。构造 run=R-P2.7 |
| 🔴-2 循环 | ✅已解 | K1 承重 judge 改**非投票器 D11(GLM-4-9B)/D12(InternLM2.5)**；D10(Qwen2.5-7B)是构造 ensemble 成员→单列标「构造参与不进 K1 承重」。生成器↔最终评测器解耦 |
| 🔴-3 无自然臂 | ✅已解(方案A) | ①对称化主力(R-P2.7,重述K2) + ②MedFact 真自然医学臂三角互证(R-P3.12) + ③协变量回归 robustness(R-P3.5-appx)。K2 重述为「**等构造强度下医学域仍比通用域难**」 |

**新增数据资产（§A.1 补）**：
- **CMedFaith-zh-gen-adv 对称通用对抗锚**（zh/general，R-P2.7 建）：同管线同筛，作 K1/K2 域对照主锚（替代 PsiloQA-zh）。PsiloQA-zh 降为「未匹配旧锚」参照（展示不对称化会得到的膨胀 G_domain 作对照）。
- **MedFact 真自然医学臂**（zh/medical，R-P3.12 引）：`arXiv:2509.17436`，1321Q/7409claims，Apache-2.0，Yi-Large 自发作答；⚠️偏 factuality 需重构成 evidence-conditioned。

**新增 Run**：
- **R-P2.7 对称锚构造**（K1/K2 前置，消🔴-1/🔴-3）：同 R-P2.1 管线换中文百科一般条目证据，同筛检测器集必须与 zh-med 严格一致（冻结进 spec+KILLSHOT）。4090+API。依赖 R-P2.1。
- **R-P3.12 MedFact 自然臂**（K2 三角互证）：D1(mnli-xnli)/D5/D11/D12 在 MedFact-重构 vs zh-med-adv，真自然医学也弱→域效应外部闭合。T11。⚠️前置=MedFact 重构成给定证据格式(TODO 派 coder+researcher)，重构不干净则只作外部效度参考不进主判据(守 R3)。
- **R-P3.5-appx 协变量回归**（K2 robustness 附录）：logistic `correct ~ domain + difficulty`，用 hard/med/easy 当对抗强度代理，回归掉难度看 β_domain 是否残留。T12/F8 森林图。CPU。

**修订版 K 判决判据（替换 §C）**：
- **K1**（对称化+解循环）：`G_domain=MacroF1(zh-gen-adv)−MacroF1(zh-med-adv)≥0.05` 且 bootstrap95%CI下界>0，承重族=NLI(D1 mnli-xnli)+**非投票judge(D11/D12)**+专用(D5)，**D10不进承重**。双侧均对称对抗锚（同管线同筛，消🔴-1）。PASS=≥2族(含≥1非投票judge)医学显著弱→#1保；FAIL=非投票judge不弱→收缩「NLI族失效」。
- **K2**（等构造强度下域效应，重述）：主判据 `ΔF1=MacroF1(zh-gen-adv)−MacroF1(zh-med-adv)≥0.05` 且CI下界>0（对称锚）；**三角互证≥1同向**（MedFact自然臂也弱/协变量回归β_domain残留）。PASS=主判据CI排0**且≥1三角同向**→claim「等构造强度下医学域更难」（**非无条件"本身难"**，证据源风格属已声明残余变量）；FAIL=退#2对抗鲁棒性，红线3收紧不归因域。
- **K3**（中文迁移，承接）：对照改用 zh-gen-adv 对称锚（非旧PsiloQA-zh），D1对齐mnli-xnli。PASS/FAIL 同原（中文医学显著弱→#1；不难→#3迁移诊断）。

**§D 互调表更新（K2 重述后关键分支）**：R-P3.5对称锚「等构造强度下仍难」→#1措辞精确化 / 「不难」→#2；R-P3.12 MedFact「真自然也弱」→#1强化(三角闭合)/「不弱」→只claim对抗设定难,自然域效应写Limitations；R-P3.5-appx β_domain残留→robustness支撑/不显著→收紧。**Finding-2 重述**=「等构造强度下(对称对抗+同筛)医学域检测难度显著高于通用域,经MedFact真自然臂+协变量回归三角互证;证据源风格为已声明残余变量」。

**体量更新**：8 数据资产 / P2×7+P3×13 runs / **T1-T12(12表)** / **F1-F8(8图)** / 8 分析块 / 2 findings — 仍全 ≥ 靶子。

**新增 TODO（§F.3 补）**：①对称通用锚证据源选型(中文百科/教科书同粒度~192tok,派researcher选源核许可,声明证据源风格为残余变量)；②MedFact 重构 evidence-conditioned(派coder+researcher,不干净则只作外部参考守R3)；③同筛检测器集冻结(zh-med与zh-gen-adv必须同一组"骗过≥1"检测器,写进R-P2.7 spec+KILLSHOT)。

**⚠️ planner 建议 skeptic 复核残留点**：①K1(多族一致)与K2(构造钉常量后域残留+三角)是否重复判据；②证据源风格残余confound能否只"声明"不"控制"(reviewer硬要则退方案④轻量自建自然臂,暂不启)。

---


## 0. 本设计服务契约（drift 声明）

- **服务**：Claim headline #1（首个中文+英文对照医学 evidence-conditioned RAG faithfulness benchmark + 检测器横评）为主，#2（自然/对抗分层）、#3（英→中迁移崩塌）为兜底加分章节。
- **轴红线**：只评 faithfulness（答案 vs 给定证据），构造与评测全程剔 factuality 样本（R3）；response/claim/span 三级独立报绝不混（R1/L2-b）；**K2 未过前不 claim 难度来自"医学领域本身"**（R2/红线3）。
- **口径承接 pilot**：主指标 = Balanced Accuracy + Macro-F1（应对不平衡）；命门数据点 = pilot 冻结的 G_domain=+0.2927（英文粗筛，正式实验须补 judge 臂 K1 + 自然/对抗分层 K2 + 中文自建 K3）。

---

## A. 实验矩阵总表

### A.0 检测器编制（4 族 × 15 个 = D1–D15）

| ID | 检测器 | 族 | 中文原生 | 主/对照臂 | 算力档 | 来源（HF/repo） |
|---|---|---|---|---|---|---|
| D1 | mDeBERTa-v3-XNLI | A NLI | ✅真多语 | **中文主 NLI 臂**（承接 pilot） | 本地8GB | ⚠️复现锚=**`MoritzLaurer/mDeBERTa-v3-base-mnli-xnli`**（pilot 0.43/0.72 冻结用此，零偏离必须用它）；`...xnli-multilingual-nli-2mil7`(更强多语版)仅作可选加强臂，用它须重跑基线不能直接引 pilot 值 (MIT) |
| D2 | AlignScore-large | A NLI | ❌英文 | 英文迁移对照臂 | 本地8GB | `yzha/AlignScore` (许可 TODO核) |
| D3 | SummaC(ZS+Conv) | A NLI | 底层NLI决定 | 句×句矩阵臂 | 本地8GB | `github.com/tingofurro/summac` (Apache TODO核) |
| D4 | HHEM-2.1-Open | A NLI | ❌英文 | 英文迁移对照臂 | 本地8GB | `vectara/hallucination_evaluation_model` (Apache-2.0) |
| D5 | **LettuceDetect-多语(mmBERT)** | B 专用 | ✅7-14语含中文 | **唯一原生中文专用 + span 主臂** | 本地8GB | `KRLabsOrg/lettucedect-v2-mmbert-base` (MIT) |
| D6 | LettuceDetect-EN(ModernBERT) | B 专用 | ❌英文 | 英→中迁移对照臂 | 本地8GB | `KRLabsOrg/lettucedect-base-modernbert-en-v1` (MIT) |
| D7 | MiniCheck | B 专用 | ❌英文 | 事实核查 SOTA<1B 对照 | 本地8GB(Flan-T5-L 0.77B)/4090(7B) | `lytang/MiniCheck-Flan-T5-Large` (MIT) |
| D8 | Patronus Lynx-8B | B 专用 | ❌英文 | 含 PubmedQA 医学素材臂 | HPC4090 | `PatronusAI/Llama-3-Patronus-Lynx-8B-Instruct` (**CC-BY-NC 非商用**) |
| D9 | RefChecker | B 专用 | extractor决定 | **消融臂（非主 baseline，pipeline 重）** | HPC4090 | `github.com/amazon-science/RefChecker` (Apache TODO核) |
| D10 | **Qwen2.5-7B-Instruct** | C judge | ✅ | **中文 judge 主力臂（K1 承重）** | HPC4090 | `Qwen/Qwen2.5-7B-Instruct` (Apache-2.0) |
| D11 | GLM-4-9B-chat | C judge | ✅ | 中文 judge 对照臂（inter-judge κ） | HPC4090 | `THUDM/glm-4-9b-chat` (许可 TODO核) |
| D12 | InternLM2.5-7B-chat | C judge | ✅ | 中文 judge 对照臂 | HPC4090 | `internlm/internlm2_5-7b-chat` (Apache TODO核) |
| D13 | Qwen2.5-72B-Instruct | C judge | ✅强 | 强 judge 上界臂 | HPC多卡/量化 | `Qwen/Qwen2.5-72B-Instruct` (Qwen License) |
| D14 | GPT-4o / DeepSeek-V3 | C judge | ✅ | **API 参考臂（不作主结论，不可复现）** | API/CPU | 商用/MIT |
| D15 | CMedFaith-finetune | D 自训 | ✅ | **族D 自训中文小模型（RAGTruth 钩子）** | HPC4090训 | 在 CMedFaith-train finetune mDeBERTa/中文BERT |

> 主横评核心 = 全族A + D5/D6/D7/D8（族B）+ D10/D11/D12/D13（族C）+ D15（族D）；D9/D14 作消融/参考臂不进主结论表。**族齐 → 满足 L2-a**。

### A.1 数据资产切片（分层维 ≥5）

| 资产 | 语言 | 域 | 状态 | 用途 | 来源/许可 |
|---|---|---|---|---|---|
| **CMedFaith-zh-med**（自建）| zh | medical | P2 建 | 核心评测集 ≥8-10k | Huatuo-26M(Apache)/维基(CC-BY-SA)/CMExam(内部构造不分发) |
| CMedFaith-en-med（自建/复用）| en | medical | P2 建 | 中英平行对照（K3）| MedHallu 复用 + 自建平行 |
| MedHallu | en | medical | 已下载 | 英文医学对照（K1/K3 + pipeline 蓝本）| `UTAustin-AIHealth/MedHallu` (MIT) |
| PsiloQA-zh | zh | general | 已下载 | 中文通用对照（K1 域轴）| `s-nlp/PsiloQA` (CC-BY-4.0) |
| PsiloQA-en | en | general | 已下载 | 英文通用对照（pilot 基线）| 同上 |
| CMHE | zh | medical | ⏳下载核 | 撞车核查 + related work（非 evidence-conditioned 不作主评测）| Google Drive TODO |

**5 分层维**：① 语言 zh/en ② 域 medical/general ③ 幻觉内容型 7-9 类 ④ 难度轴 natural/adversarial(=RAGTruth Evident/Subtle) ⑤ 证据 given/withheld；（第 6 维加分：医学子域 内科/外科/药理/诊断，若证据源可标）。

### A.2 Run 总表 — P1 pilot（数据构造 + K3 初验）

| run | 服务判据 | 自变量 | 控制（固定） | 检测器 | 数据切片 | 主指标 | 预期 | 论文表图 | 依赖 | 算力 |
|---|---|---|---|---|---|---|---|---|---|---|
| **R-P1.0** | L2-a 基线管线 | 检测器 | 数据固定（已下载）| 全 D1–D14 | MedHallu + PsiloQA-en/zh | BA/Macro-F1 | 复现 pilot：MedHallu-med≈0.43，PsiloQA-en≈0.72 | 复现校验（内部）| **无依赖，最先跑** | 本地+4090 |
| **R-P1.1** | P1 闸 / K3 | 幻觉类型 | temp 0.3–0.7 / top-p 0.95 / max512 / 幻觉长=真值±10% | 生成用 Qwen2.5-7B | Huatuo-26M 抽 ~100-200 QA | 构造成功率 | 中文四阶段管线通，产 100-200 条 | 附录 pipeline 图 | R-P1.0 | 4090 |
| **R-P1.2** | P1 闸 / L1-a | — | — | 3-LLM 投票(GPT-4o-mini+Gemma2-9B+Qwen2.5-7B) + 中文NLI双向蕴含τ=0.75 | pilot 100-200 条 | 人工抽检合格率 + 投票难度分布 | hard/med/easy≈33/33/34；抽检幻觉质量合格 | T-pilot 质量表 | R-P1.1 | 4090+API |
| **R-P1.3** | **K3 初验** | 域×语言 | NLI 设置恒定 | D1(mDeBERTa) + D10(Qwen judge) | pilot-zh-med vs PsiloQA-zh vs MedHallu-en | Macro-F1 + G_domain(zh) | 中文医学显著弱于中文通用（G_domain,zh 与英文 0.29 同号）| F1 雏形（中英×域）| R-P1.2 | 本地+4090 |

### A.3 Run 总表 — P2 数据集成（构造/标注/合规，多数非 GPU-跑）

| run | 服务判据 | 自变量 | 控制（固定） | 方法 | 数据切片 | 主指标 | 预期 | 论文表图 | 依赖 | 算力 |
|---|---|---|---|---|---|---|---|---|---|---|
| **R-P2.1** | L1-c 规模 | 幻觉类型×难度轴 | 四阶段超参同 pilot | MedHallu 四阶段中文复刻 | Huatuo-26M/维基→ zh-med ≥8-10k | 产出条数 + 类平衡 | ≥8-10k，faithful/unfaithful 均衡 | T1 数据统计 | R-P1.2 | 4090+API |
| **R-P2.2** | R3 剔 factuality | — | 双向蕴含 ℰ=min(NLI(H→GT),NLI(GT→H))，τ=0.75 | 中文 NLI(mDeBERTa)过滤 | zh-med 全量 | 过滤率 | 滤除"其实同义正确"候选，防混 factuality | 附录管线 | R-P2.1 | 本地8GB |
| **R-P2.3** | L1-c 分层 | — | 3-LLM 投票保留规则=骗过≥1 | 难度投票分层 | zh-med 全量 | hard/med/easy 分布 | ≈33/33/34，正交双轴（内容型×Evident/Subtle）解耦 | T1/F2 | R-P2.2 | 4090+API |
| **R-P2.4** | **L1-a IAA** | 标注者 | 省力路线（brief §3）| response 级双标 Cohen κ（主）+ hard 子集原子级 Krippendorff α（辅）| zh-med 双标子集 | **κ / α** | **κ≥0.7 PASS（L1-a）**；α≥0.6 | T2 IAA 表 | R-P2.3 | CPU |
| **R-P2.5** | L1-c 类型学 | — | taxonomy 定稿：内容型 7-9 类（补过时指南+诊断决策误导，剔 reasoning/temporal/memory/multimodal）| 类型标注 + 平衡校验 | zh-med 全量 | 类覆盖数 | ≥5 类（实为 7-9）+ 自然/对抗分层 | T1/F3 | R-P2.4 | CPU |
| **R-P2.6** | **L1-b 许可** | — | Huatuo-26M(Apache)可分发；CMExam 只内部构造不进发布集；维基 CC-BY-SA 传染标注 | 合规审计 | 发布集 | 二元 | 无版权受限源进发布 = PASS | Ethics/附录 | R-P2.5 | CPU |

### A.4 Run 总表 — P3 基线评测（横评 + K1/K2/K3，论文主体）

| run | 服务判据 | 自变量 | 控制（固定） | 检测器 | 数据切片 | 主指标 | 预期 | 论文表图 | 依赖 | 算力 |
|---|---|---|---|---|---|---|---|---|---|---|
| **R-P3.1** | L2-a/b 主横评 | 检测器(15) | prompt/阈值/输入格式恒定；response 级 | D1–D15 | **CMedFaith-zh-med test（类平衡）** | **BA + Macro-F1 + AUPRC/AUROC + bootstrap CI** | NLI 族<随机(~0.4-0.5)；judge 族较高但仍<通用；span 专用居中 | **T3 主表**/F1 | R-P2.6, R-P3.0(train) | 本地+4090 |
| **R-P3.2** | L2-b claim 级 | 检测器 | claim=原子陈述；独立表 | D1,D5,D7,D10,D13,D15（可原子级）| zh-med hard 子集原子陈述 | BA+Macro-F1+MCC+CI | 与 response 级同趋势，独立报不混 | **T4 claim 表** | R-P3.1 | 本地+4090 |
| **R-P3.3** | L2-b span 级 | 检测器 | span=char-level overlap；独立表 | D5,D6（LettuceDetect token-span）+ NLI 派生 span | zh-med 有 span 标注子集 | **char-level P/R/F1 + soft-F1** | 原生中文 D5 领先，英文 D6 迁移掉 | **T5 span 表**/F5 | R-P3.1 | 本地8GB |
| **R-P3.4** | **K1 判决**（域对照多臂）| 域(med/gen)×检测器族 | 语言固定 zh；NLI设置跨集恒定 | **≥2 承重族**：NLI(D1) + judge(D10/D13) + 专用(D5) | zh-med vs PsiloQA-zh（平衡下采样对齐 n）| **G_domain = F1(gen)−F1(med) + bootstrap 95%CI** | judge 臂 med 仍显著<gen（CI 排除 0）→ K1 PASS | **T6 域对照**/F1 | R-P3.1 | 本地+4090 |
| **R-P3.5** | **K2 判决**（自然vs对抗）| 难度轴(natural/adv)×域 | 检测器固定主臂 | D1,D5,D10 | zh-med natural 子集 vs zh-med adv 子集 vs PsiloQA-zh(natural) | **医学 natural 子集 F1 + CI** | 自然幻觉子集上医学仍显著难于通用自然子集 → K2 PASS | **T7 分层表**/F2 | R-P3.3, R-P2.3 | 本地+4090 |
| **R-P3.6** | **K3 判决**（中英迁移）| 语言(zh/en) | 域固定 medical；平行样本 | 全 D1–D13 | CMedFaith-zh-med vs CMedFaith-en-med（平行）| **ΔF1(en→zh) per detector + CI** | 英文原生检测器(D2/D4/D6/D7/D8) zh 显著掉；D1/D5 多语较稳 | **T8 迁移表**/F5 | R-P3.1 | 本地+4090 |
| **R-P3.7** | 差异化(校准) | 检测器 | 15-bin ECE | D1,D5,D7,D10,D13,D15 | zh-med test | **ECE + Brier + reliability + 温度缩放** | 医学域检测器普遍 miscalibrated（净增量，对标集无人报）| **T9 校准**/F4 | R-P3.1 | CPU |
| **R-P3.8** | R5 judge 稳定性 | judge×序×verbosity | 三级独立报 | D10,D11,D12,D13,D14 | zh-med 采样子集 | **自一致(n≥5方差)+inter-judge κ/Fleiss+judge-vs-人工κ+position/verbosity bias** | judge 有内/间方差，position 翻转 10-15pt，verbosity 偏长 15-30pt | **T10 稳定性**/F6 | R-P3.1 | 4090+API |
| **R-P3.9** | 族D 钩子(加分) | 训练数据量 | finetune 恒定超参(TODO查) | **D15 自训** vs D10/D13 judge | CMedFaith-train→test | BA+Macro-F1 | 自训中文小模型能否打平/接近 judge（RAGTruth/Bi'an 钩子）| T3 内 + 分析块 | R-P3.0(train), R-P3.1 | 4090训 |
| **R-P3.10** | 分析块(类型诊断) | 幻觉类型(7-9) | 检测器固定 | D1,D5,D10 | zh-med 按类型切 | 逐类型 F1 | 信息不全/机制误归因 最难检；证据篡改最易 | F7 类型×检测器热图 | R-P3.1 | CPU |
| **R-P3.11** | 分析块(分歧挑战集) | — | FaithBench 钩子 | D1–D13 全 | zh-med 检测器高分歧子集 | 检测器间一致率 + 人工重标 | 中文医学分歧集大 → Finding「尤其主观/难」| 分析块 + F6 | R-P3.1 | CPU |

> **训练前置 R-P3.0**：D15 finetune（在 CMedFaith-train 上），依赖 P2 数据 train split 建好；HPC4090 单卡；经 `gpu_slot.py request cmedfaith hpc 1` 起（主线做，非 planner）。

**体量核对（对齐 brief §1 靶子）**：检测器 15/4 族 ✅｜三级评测 R-P3.1/3.2/3.3 ✅｜分层维 5-6 ✅｜主表 T1–T10 = 10 张 ✅(≥8)｜图 F1–F7 = 7 张 ✅(≥6)｜分析块 R-P3.4/3.5/3.6/3.7/3.8/3.10/3.11 = 7 块 ✅(≥6)｜独立 findings ≥2（见 D 节）✅。

---

## B. 三阶段拆解（对齐 ACCEPTANCE 阶段闸）

### P1 数据构造 pilot（~100-200 条中文医学 faithfulness）

- **runs**：R-P1.0（英文对照 pipeline，**无依赖立即跑**）→ R-P1.1（中文四阶段构造）→ R-P1.2（质检投票+双向蕴含）→ R-P1.3（K3 初验）。
- **照抄级超参（brief §3）**：候选生成 temperature 0.3–0.7 变动 / top-p 0.95 固定 / max 512 tokens / 幻觉答案长度=真值±10%；质检 3-LLM 投票（GPT-4o-mini + Gemma2-9B + Qwen2.5-7B），保留规则=骗过≥1 个即留，难度=hard(全骗)/med(部分)/easy(仅1)；双向蕴含 ℰ=min(NLI(H→GT),NLI(GT→H))，中文换 mDeBERTa，**阈值 τ=0.75** 保留 ℰ<τ；TextGrad 精修最多 5 次，兜底取余弦相似度最大候选。
- **TODO**：MedHallu Appendix K 逐字 prompt + embedding 型号需 clone `github.com/MedHallu/MedHallu`（MIT）核 → 派 researcher。
- **P1 闸 PASS 条件（ACCEPTANCE）**：中文构造管线通 + 人工抽检幻觉质量合格 + K3 初验（R-P1.3 中文医学显著弱）。
- **产出**：pilot 100-200 条 zh-med + 难度分布表 + 抽检合格率 + K3 初验 F1 图雏形。

### P2 数据集成（全量 ≥8-10k）

- **runs**：R-P2.1（全量构造）→ R-P2.2（双向蕴含滤 factuality）→ R-P2.3（难度分层）→ R-P2.4（标注+IAA）→ R-P2.5（类型学定稿）→ R-P2.6（许可合规）。
- **类型学定稿（brief §3，正交双轴）**：内容型 7-9 类（证据篡改/无关/剂量数值错/过度断言/信息不全/机制误归因/捏造指南 + **补** 过时指南、诊断治疗决策误导）× 难度轴 natural/adversarial（=RAGTruth Evident/Subtle，充当"自然 vs 对抗"可操作化）；**剔** temporal/causal reasoning/memory/multimodal（属 factuality/推理，纳入会 confound，taxonomy 处显式写剔除理由，呼应 R3）。剂量数值错标"本工作细化派生，非直接引自源"。
- **标注省力路线**：主粒度 response 级 Cohen κ；自动共识（多 LLM 投票+中文 NLI）先筛，人工只裁冲突+hard 层；原子级 NLI 只在 hard 子集做；hard 层专家抽检。
- **P2 闸 PASS（ACCEPTANCE）**：全量数据 + **IAA κ≥0.7（L1-a）** + 许可合规（L1-b）+ 类型/分层覆盖（L1-c）。
- **⚠️ IAA 对标修正（brief §3）**：ACCEPTANCE 现引"RAGTruth response 91.8%"可能是 finetuned Llama-2-13B 的模型 F1 而非人际一致率 → **TODO 人工核 arXiv 2401.00396 annotation 小节**；若为模型性能，改用 **FaithBench Krippendorff α=0.748** 作 IAA 对标。（此为口径澄清，非改阈值 κ≥0.7 本身，属拍板前提示。）

### P3 基线评测（全量横评）

- **runs**：R-P3.0（D15 训）→ R-P3.1（主横评）→ R-P3.2/3.3（claim/span）→ R-P3.4/3.5/3.6（K1/K2/K3 判决）→ R-P3.7–3.11（校准/稳定性/finetune/类型/分歧）。
- **P3 闸 PASS（ACCEPTANCE）**：三族基线全跑（L2-a）+ 口径固定 response 主、claim/span 不混（L2-b）+ **K1/K2 通过（L2-c）**。
- **矩阵结构**：4 族检测器 × 三级 × 5-6 分层维；主口径 response 级 BA+Macro-F1，全部带 bootstrap 95%CI。

---

## C. 三条命门（K1/K2/K3）判决实验

> 判据跑前冻结（防 HARKing，写进 THEORY_LEDGER/KILLSHOT_LEDGER）。任一 FAIL → 停下报拍板 + 按 headline 退路切换。

### K1 — 补第二承重臂（judge 臂上医学是否仍失效）

| 项 | 内容 |
|---|---|
| **判决 run** | R-P3.4 |
| **预注册判据** | 在 **≥2 承重检测器族**（NLI-D1 + LLM-judge-D10/D13，可加专用-D5）上，`G_domain = Macro-F1(PsiloQA-zh) − Macro-F1(CMedFaith-zh-med) ≥ 0.05` 且 **bootstrap 95%CI 下界 > 0** |
| **对照** | 域二值（medical vs general），语言固定 zh，样本量平衡对齐（PsiloQA-zh 下采样至 med 集 n），NLI/judge 设置跨集恒定 |
| **PASS** | ≥2 族上医学显著弱（CI 排除 0）→ 核心发现成立，headline #1 保 |
| **FAIL** | judge 臂医学不弱 → 失效是 mDeBERTa 单模型伪迹 → **停下报**；claim 收缩到「NLI 族失效」（见 D 节互调） |

### K2 — 控对抗构造 confound（自然子集医学是否仍难）

| 项 | 内容 |
|---|---|
| **判决 run** | R-P3.5 |
| **预注册判据** | **医学 natural 子集** Macro-F1 显著低于**通用 natural 子集**（PsiloQA-zh 天然自然），`ΔF1 ≥ 0.05` 且 bootstrap 95%CI 下界 > 0 |
| **对照** | 难度轴分层：zh-med-natural vs zh-med-adversarial vs PsiloQA-zh(natural)；检测器固定主臂 D1/D5/D10 |
| **PASS** | 自然幻觉子集上医学仍显著难 → 可 claim「医学领域难」 |
| **FAIL** | 难度纯来自对抗构造 → **停下报**；口径从「医学域难」切「对抗鲁棒性」，走 headline #2（见 D 节） |

### K3 — 中文迁移（英文 pilot 结论迁移到中文自建）

| 项 | 内容 |
|---|---|
| **判决 run** | R-P1.3（初验）→ R-P3.6（全量定稿）|
| **预注册判据** | CMedFaith-zh-med 上现成检测器 Macro-F1 显著弱（<通用），且 en→zh 平行迁移每检测器 ΔF1 带 CI |
| **对照** | 语言二值（zh/en），域固定 medical，平行样本；全 D1–D13 |
| **PASS** | 中文医学上现成检测器显著弱 → benchmark 价值成立 |
| **FAIL** | 中文医学不难 → **停下报**；benchmark 价值存疑，转 headline #3（英→中迁移诊断本身当贡献）|

---

## D. 🎯 实验↔叙事互调点（映射表）

> 主线跑完对应 run 后，按此表决定看哪条 claim、以什么强度写。**这是实验反哺叙事的开关。**

| 触发 run / 结果 | 若结果 | 叙事分支 / claim 强度 | 落到 headline |
|---|---|---|---|
| **R-P3.4 (K1)** judge 臂 | 医学仍显著弱 | 保「现成检测器医学域系统性失效」全强度 | **#1 主** |
| **R-P3.4 (K1)** judge 臂 | judge 臂医学**不弱** | claim 收缩为「**NLI 族**在中文医学失效，judge 族可挽回」——从"检测器失效"降到"encoder-NLI 失效" | #1 收缩版 |
| **R-P3.5 (K2)** 自然子集 | 医学自然子集仍难 | 可 claim「难度来自医学领域本身」 | **#1 强化** |
| **R-P3.5 (K2)** 自然子集 | 医学自然**不难** | 口径切「**对抗鲁棒性**：人造对抗集高估检测器」 | **#2**（自然/对抗分层）|
| **R-P3.6 (K3)** 中英迁移 | 中文医学显著弱 | 保 #1 | #1 |
| **R-P3.6 (K3)** 迁移 | 中文医学不难 | 转「**英→中迁移崩塌诊断**」当独立贡献 | **#3** |
| **R-P3.9 (族D)** finetune | D15 打平/接近 judge | **多一条贡献**：「轻量中文 faithfulness 检测器」（RAGTruth 钩子）| #1 + 加分章 |
| **R-P3.9 (族D)** finetune | D15 远不及 judge | 写「中文医学 faithfulness 难到小模型学不动」当难度证据 | #1 分析块 |
| **R-P3.11 (分歧集)** | 中文医学分歧特别大 | **多一条 finding**：「中文医学 faithfulness 尤其主观/难」（FaithBench 钩子）| Finding-2 |
| **R-P3.11 (分歧集)** | 分歧不大 | 说明标注可靠，强化 L1-a 质量论证 | L1-a 支撑 |
| **R-P2.4 (IAA)** | κ<0.7 但 hard 层低 | finding：「hard 层本质主观」，非标注差 | L1-a + Limitations |

**两条独立可迁移 findings（≥2 靶子）**：
- **Finding-1**：evidence-conditioned 设定下，NLI-encoder 族在中文医学系统性失效（Macro-F1 可 <随机 0.5），LLM-judge 族部分挽回但仍显著低于通用域——**失效是"域"效应，非"语言"效应**（承接 pilot G_lang≈0 / G_domain=0.29）。
- **Finding-2**：检测器在自然幻觉 vs 对抗构造幻觉上表现分化（K2 决定方向），人造对抗集系统性高估/低估检测器真实能力（可迁移到通用 faithfulness benchmark 构造方法论）。

---

## E. 评测协议精密规范（brief §4，落到每个对比）

| 维度 | Response 级（主口径）| Claim 级（原子陈述）| Span 级 |
|---|---|---|---|
| 主指标 | **Balanced Accuracy + Macro-F1** | BA + Macro-F1 | char-level **P/R/F1**（中文更稳）|
| 辅助单值 | MCC | MCC | soft(partial-overlap) F1 |
| 阈值无关 | **AUPRC(主) + AUROC** | AUPRC + AUROC | — |
| 校准 | **ECE(15-bin) + reliability + Brier + 温度缩放** | 同 | 可选 |
| 点估计 CI | **bootstrap 95%CI，10000 resamples** | 同 | 同 |
| 配对检验 | **McNemar（仅 accuracy）+ paired bootstrap（BA/F1）** | paired bootstrap/permutation | paired bootstrap on span-F1 |
| 多检测器校正 | **Holm-Bonferroni（FWER）**，多则 BH(FDR) | 同 | 同 |
| effect size | ΔMacro-F1 + bootstrap CI（G_domain 带 CI）| 同 | Δspan-F1 + CI |

**🔴 三个必守（不可违反）**：① F1/BA **禁用 McNemar**（仅 accuracy 可），必须 paired bootstrap/permutation [arXiv:1609.09471]；② 横评多检测器必 **Holm-Bonferroni**；③ span/claim/response **三级各建独立表各带 CI，绝不混报**（L2-b 铁律 / R1）。

**LLM-judge 稳定性（R-P3.8，三级独立报，R5）**：自一致性（n≥5 采样方差 / 多数票稳定率）+ inter-judge κ/Fleiss（≥2 家族 D10/D11/D12）+ judge-vs-人工 κ + **position bias 控制（交换顺序保双序一致，报翻转率）+ verbosity bias 控制（rubric 长度中立）**；框架 G-Eval。

**IAA 报告（R-P2.4，L1-a）**：response 级 Cohen κ（主，PASS 线 ≥0.7）+ hard 子集原子级 Krippendorff α（辅，≥0.6）；对标 FaithBench α=0.748（RAGTruth 数口径待核，见 P2 TODO）。

**校准 = 差异化贡献**：对标集（MedHallu/FaithBench）均未系统报 calibration，我们报 ECE+Brier+温度缩放 = 净增量（高风险医学场景刚需）。

---

## F. 风险 · 依赖 · 算力预算

### F.1 依赖与并行

```
立即可跑（无依赖，数据已下载，先起）:
  R-P1.0  英文对照 pipeline（全检测器 × MedHallu/PsiloQA）→ 顺带复现 pilot 冻结值 0.43/0.72
  ├─ 可并行族A(本地8GB) + 族B英文(本地/4090) + 族C judge(4090) + API参考臂

数据链（串行，P2 数据是 P3 前置）:
  R-P1.1 → R-P1.2 → R-P1.3(K3初验) ─┐
  R-P2.1 → R-P2.2 → R-P2.3 → R-P2.4(IAA) → R-P2.5 → R-P2.6(合规)
                                              └─→ P3 全部解锁

P3 内并行（数据建好后，各检测器无文件冲突可多 opus/多卡扇出）:
  可并行: {R-P3.1 主横评各族} {R-P3.7 校准} {R-P3.10 类型}（都读同一 test，只跑不同检测器）
  串行依赖: R-P3.0(D15训) → R-P3.9(族D评)；R-P3.3(span) → R-P3.5(K2)
  K 判决: R-P3.4/3.5/3.6 依赖 R-P3.1 出全表后
```

### F.2 算力总估（供主线判拍板）

| 档 | run | 硬件 | 粗估 |
|---|---|---|---|
| **本地 8GB**（<5min 烟测 + encoder 全跑）| 族A(D1-D4)/D5/D6/D7-Flan-T5/校准/统计 | RTX4070 8GB | 各检测器推理 ~0.5-2 GPU·h/万条 |
| **HPC 4090 单卡**（默认，多窗各占 1）| D8 Lynx-8B / D10-D12 judge / D15 finetune | gpu4090 | judge 推理 ~2-4 GPU·h/万条/model；D15 训 ~3-6 GPU·h |
| **HPC 多卡/量化** | D13 Qwen72B | gpu4090 ×2 或 4bit 量化单卡 | ~4-8 GPU·h |
| **纯 CPU / API**（gpu_slot 填 0）| D14 GPT-4o/DeepSeek API、bootstrap 10000、ECE、IAA、类型/分歧分析 | CPU | 数据构造 API 调用（temp 采样）为主成本 |

- **总量级**：P3 主横评 15 检测器 × ~10k × 三级 ≈ 中等；judge 族(D10-D13)是大头（4090 队列）；构造/标注的 API 调用（3-LLM 投票 + TextGrad）是**真金花费点**（GPT-4o-mini 大量调用）→ 大笔 API 花费属拍板点，主线先估预算。
- **卡槽纪律**：所有 GPU run 经 `python tools/gpu_slot.py request cmedfaith hpc 1`（judge/训练）或 `hpc 0`（CPU/API 批跑）登记；planner 不启，主线串行做。

### F.3 风险点 / 前置 TODO

| 风险/TODO | 影响 | 处置 |
|---|---|---|
| **MedHallu Appendix K 逐字 prompt + embedding 型号** 未拿到 | R-P1.1 构造管线细节缺 | **TODO 派 researcher** clone `github.com/MedHallu/MedHallu`（MIT）抓原文 |
| **judge prompt 逐字**（RAGTruth 0-100 式 / MedHallu 二分类式）未定 | D10-D14 judge 臂 | **TODO 派 researcher** clone RAGTruth/MedHallu repo |
| **D15 finetune 官方超参**（lr/epoch/batch）未查 | R-P3.0 训 | **TODO 派 researcher 查官方**（RAGTruth/Bi'an finetune 设置），查不到标 TODO 不臆想（红线6）|
| AlignScore/SummaC/RefChecker/GLM-4/Lynx **许可** 待核 | L1-b 合规 + 商用 | TODO 逐个核 HF/repo LICENSE；**Lynx-8B 是 CC-BY-NC 非商用**，写清用途限制 |
| **RAGTruth 91.8% IAA 口径存疑**（可能是模型 F1 非人际一致）| L1-a 对标错配 | TODO 人工核 arXiv 2401.00396 annotation 小节；错则改 FaithBench α=0.748 对标 |
| **CMExam 数据许可与 repo Apache 冲突** | L1-b | 保守：CMExam 只内部构造不进发布集，或只发我们生成的幻觉答案+指针 |
| **CMHE 未下载核** | related work + 撞车终检 | TODO 下载 Google Drive 核规模/许可/分层（初判非 evidence-conditioned 不撞 headline #1）|
| 中文 3-LLM 投票器 Gemma2-9B/GPT-4o-mini 中文医学能力 | 构造质量 | pilot R-P1.2 抽检验证；若中文弱可换 DeepSeek/Qwen 组合（记 LOG）|
| **维基 CC-BY-SA share-alike 传染** | 发布集协议 | 用维基作证据源则该子集须同协议标注，合规审计 R-P2.6 处理 |

---

## G. 交接

- **→ researcher**（先派，解 F.3 的 TODO）：MedHallu Appendix K prompt + embedding 型号；judge 逐字 prompt；D15 finetune 官方超参；AlignScore/SummaC/GLM-4/Lynx 许可；RAGTruth IAA 口径；下载 CMHE 核撞车。
- **→ skeptic**（本设计动手前红队）：攻 K1/K2/K3 判据是否真能证伪、正交双轴（内容型×Evident/Subtle）是否真解耦难度、族D自训是否泄漏 train→test。
- **→ coder**（数据链）：R-P1.1 中文四阶段构造脚本（照 brief §3 超参）；R-P2.2 中文 NLI 双向蕴含过滤；R-P2.3 难度投票分层；R-P3.* 各检测器统一评测 harness（三级 + bootstrap CI + Holm-Bonferroni）。**无文件冲突可多 opus 扇出**。
- **→ 主线**：R-P1.0 英文对照 pipeline **无依赖立即可跑**（数据已下载），先起把 pilot 冻结值 0.43/0.72 复现校验；GPU run 经 `gpu_slot.py` 登记；大笔 API 花费（构造的 3-LLM 投票+TextGrad）先估预算拍板。
- **→ analyst**：R-P3.1 出主表后算 G_domain 趋势 + K1/K2/K3 CI 判决 + 出 F1-F7；对齐 L2-c / K 判据。
- **→ verifier**：所有入表数字 Bash/Grep 核 csv（红线5），三级不混（L2-b）。

> **建议主线/Opus 复核的两个拍板前提示**：① IAA 对标口径（RAGTruth 91.8% 可能错配）是否需先改 ACCEPTANCE 措辞——属拍板点（改判据方向），planner 未擅改仅标出；② 正交双轴把 RAGTruth Evident/Subtle 当"自然 vs 对抗"是 brief §3 的可操作化建议，K2 判据强依赖此映射成立，建议 skeptic 先攻。
