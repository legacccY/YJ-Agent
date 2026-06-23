# G0–G6 逐闸细则（Gates）

> 每闸：目的 / 负责执行 / 输入 / 动作 / kill 条件 / 输出 / 通过率 / 杀哪个历史死法。
> 量规细节见 [`02_RUBRICS.md`](02_RUBRICS.md)（R1-R7）。候选池 schema 见 [`04_POOL.schema.md`](04_POOL.schema.md)。

---

## G0 — 宪章 Charter

- **目的**：定搜索空间硬约束 + 默认 kill 线。**不筛候选，定规则。**
- **负责**：用户 + Opus 主线（人主导，这是战略）。
- **输入**：用户的方向种子 / 兴趣 / 当前组合台缺口。
- **动作**：复制 [`01_CHARTER.template.md`](01_CHARTER.template.md)，主线据种子草拟 → 用户过目改 → 签字锁定，存 `runs/<date>_charter.md`。
- **输出**：锁定的 charter.md（领域/硬排除/算力预算/双 venue/风险配比/默认 kill criteria）。
- **通过率**：N/A（这是配置闸）。
- **杀死法 ④（顶会执念）**：D 节强制双 venue 分档。

---

## G1 — 批量产出 Generate

- **目的**：广撒网，产 50-100 候选，覆盖多策略多方向。
- **负责**：`ideator`(sonnet)×N 扇出（每个领一种生成策略），主线收口去重聚类。
- **输入**：锁定的 charter.md。
- **动作**：
  1. 起 **8 个 ideator**，按**B 族倾斜配额**分配（实证：B 族现象/矛盾型命中率显著高于 A 族缝合/迁移型）：
     - **S3 矛盾/复现失败 ×2**：文献里互相打架的结论 / 复现不出来的声称 = 选题金矿（B族，已出 selinf）
     - **S4 dataset-first ×2**：被低估/新出的数据集能问什么新问题（B族，已出 disagree、nca-phasemap）
     - **S1 gap 挖掘 ×1**：从近 2 年顶会论文 future-work/limitation 段批量挖未解问题（A族，须填机制栏）
     - **S2 跨域迁移 ×1**：方法 X（领域 A 成熟）→ 问题 Y（领域 B 没人用过）（A族，须填机制栏）
     - **S5 死项目残值 ×1**：组合台已死项目（NCA-JEPA 负结果 / MedSeg-UQ）的可救残值
     - **S6 SOTA-limitation ×1**：当前 SOTA 方法的已知失效边界 = capability 型选题（A族，须填机制栏）

     > **配额倾斜理由**：5 轮实证 B 族（S3/S4）产的候选全部存活（selinf/disagree/nca-phasemap）；A 族（S1/S2/S6）产的候选全军覆没（C015 S1-gap、C105 S6 缝合）。根因：A 族易产「A+B 没人拼过」型缝合，G5 杀手锏一捅「绑两块的机制是空的」即塌；B 族从真实可测的反常现象出发，机制实存。**S3/S4 各 ×2 扩容，A 族（S1/S2/S6）各保 ×1 维持多样**。

  2. **A 族（S1/S2/S6）强制机制栏**：S1/S2/S6 ideator 产出的每条候选，schema 里**必须填** `mechanism_anchor`（现象驱动 `phenomenon` / 有具体机制 `mechanism` / 缺失 `MISSING`）+ `anchor_note`（一句话说明机制/现象）。填不出的标 `mechanism_anchor=MISSING`——这类候选在 G2 anchor 闸会受重罚。
  3. 每个 ideator 产 ~15-20 条，每条按 `pool.jsonl` schema 输出（含 one-liner / 问题 / 初步方法 / why-new / 候选 venue / 数据 / 算力估 / mechanism_anchor / anchor_note）。**新增天花板预填**：每条填 `ceiling_upside`（10x / 10% 一句话说全成后领域怎样不同）+ `ceiling_followups`（能列几个独立 follow-up）+ `ceiling_bridge`（跨哪两域的具体机制，单域填 none）——给 G3 的 R8 打分备料，举不出就如实留空（G3 判 0，不臆造）。
  4. 主线汇总 → **SPECTER2 余弦 0.8 去重**（95% 可能重复）→ **多样性聚类**（k-means，确保进 G2 的来自不同簇）。
- **kill 条件**：去重命中（与池内已有 >0.8）→ 合并。
- **输出**：`pool.jsonl` ~50 条唯一候选。
- **通过率**：~50%（100 raw → ~50 唯一）。
- **杀死法 ③（蓝海一碰就塌）**：多策略广撒 + B 族倾斜，不只押缝合型。

---

## G2 — 机器硬筛 Screen

- **目的**：用规则 + 工具便宜地砍掉明显不行的，尤其**工具验证撞车**（不信任何人自报 novel）。
- **负责**：自动（`tools/ideation_*.py`）+ 主线判二元 checklist。
- **输入**：G1 的 ~50 候选。
- **动作**：
  1. **撞车检测**（`tools/ideation_collision.py`，见 [`05_TOOLING.md`](05_TOOLING.md)）：每条候选 → Semantic Scholar / OpenAlex 检索 + 本地 SPECTER2 余弦比对 top-K 已发论文，记录最大相似度 + 最近邻论文。
  2. **gap 验证**：检索是否有 future-work/limitation 支撑这是真空白。
  3. **R1 二元 kill checklist**逐条过（硬排除/撞车阈/算力/可行/gap/已解/DDL）。
- **kill 条件**（R1，任一命中即砍）：撞车 >0.85 无差异化 / 超算力预算 / 命中硬排除 / 无 gap 支撑 / 已有完整解 / DDL 超期 / **anchor 闸：核心 claim 既无可观测现象/反常锚点（phenomenon）也无指名机制（mechanism），且 `mechanism_anchor=MISSING`** → 砍或打回 G1 补锚（此闸只对 A 族候选严格执行；B 族 S3/S4 天然以现象为锚，不重复判）。
- **输出**：~20 候选存活，被砍的记 `killed@G2 + reason + 最近邻论文`。
- **通过率**：~40%（50 → ~20）。
- **杀死法 ③（撞车自欺）**：工具显式比对，杜绝"以为新其实撞车/塌"。

---

## G3 — 评分排序 Rank

- **目的**：给幸存候选补情报 + 量化打分排序，砍掉中下游。
- **负责**：`researcher`(sonnet) 补情报 → 主线跑 R2/R3，top 10 跑 R4。
- **输入**：G2 的 ~20 候选。
- **动作**：
  1. **researcher 补情报**（每条或成簇）：最新 SOTA / 竞品密度 / 官方可行性 / venue 定位，带引用，查不到标 TODO。
  2. **R2 InnoEval 加权**（见 R2 现版六维 + 硬阈 Feasibility<4 / Q-Novelty<4 直接砍）。
  3. **R3 Swiss pairwise** 5 轮排序（不用 LLM 单条打分）→ 主线/用户 final rerank 否决权。
  4. **R8 顶会天花板打分（每条都打）**：5 接地信号 → `ceiling_tier` ∈ {MAIN/FINDINGS/WORKSHOP}，落进 pool.jsonl。低 tier **不砍**（诚实标 venue 档），但用于下面保底 + G6 定档。
  5. **天花板保底 re-rank（关键，治「顶会苗子被埋」）**：Swiss 排完后，**强制 ≥1-2 个 `ceiling_tier=MAIN` 候选晋级 G4**，即使其 Swiss 名次低于 cutoff（标 `lane=high_variance`）。否则保守 benchmark 题在 pairwise 天然占优，会把高天花板苗子全埋（[Si et al.] 风险厌恶 + Swiss 系统偏差）。
  6. **top 8-10 跑 R4 12 维 taste 深度体检**（含 excited-reader 测试）。
  7. **R10-c 命门证伪成本标注**：每条标 `crux_cost` ∈ {LOW/HIGH}——headline 承重命门能否在可用 setting 上 <1GPU·h 证伪。真命门=普适/跨集/emergent（发现集小 pilot 测不了）→ `HIGH`，标「高难产风险」带进 G4/G6（不砍，逼 G6 按 R10-b 二选一）。
- **kill 条件**：R2 硬阈命中 / 加权排序后 ~60%（**但 high_variance lane 名额受保护不被 cutoff 砍**）/ R4 可行性维<2。
- **输出**：8-10 候选带完整分数表 + `ceiling_tier`，按综合名次排（含至少 1-2 个 MAIN-tier 苗子）。
- **通过率**：~45%（20 → 8-10）。
- **杀死法 ③（可行性被忽略）**：可行性单独硬闸；**新增治「全是安全 benchmark」**：天花板维度 + MAIN-tier 保底配额，防漏斗塌成只活 B-venue。

---

## G4 — 红队预演 Pre-mortem

- **目的**：执行前对手攻致命伤 + pre-mortem 挖失败路径 → 提炼立项前要证伪的最大风险假设。
- **负责**：`skeptic`(opus)。
- **输入**：G3 的 top 8-10。
- **动作**：
  1. 每个候选先填 **R5 Heilmeier 8 问**，答不出的即红队重点。
  2. `skeptic` 攻三死法（立项前提：可行性/撞车/理论会不会塌 ←→ severity-gated，0 致命即放行）。
  3. **缝合测试（强制，对所有候选）**：skeptic 问——「赌它死在 killshot，空的前提是 ___；这前提在文献里被直接测过（phenomenon-grounded），还是只是假设（assumption）？」逐词检查 A+B 绑定的机制是否实存，是假设 → 标为最大风险假设之一，喂 G5 优先证伪。此步专堵「绑两块的机制是空的」型塌缩（历史根因：C015/C105/run-004 世界模型×医学，G5 才暴雷）。
  4. **R6 Pre-mortem**：假设"1 年后已失败"倒推失败路径 → 提炼 2-3 个最大风险假设 → 配 <1 GPU·h 证伪实验设计（喂 G5）。
  5. **上风险红队（新增，对称攻天花板）**：skeptic 除攻「会不会死」，再问每个候选——「**就算全成了，天花板到哪？是 CVPR main-track 还是只够 Findings/workshop？**」。R8 信号有没有水分（举不出实据的信号判 0）。`ceiling_tier=MAIN` 的候选若 skeptic 戳穿其新领地/insight 是空的 → 降级 tier（**不一定砍**，降到诚实档）。这步防两头：既防低天花板冒充顶会，也防高天花板信号注水自欺。
- **kill 条件**：skeptic 给 ≥1 个**无出路**的 🔴 致命 → 砍 / 回 G1 重挖。（天花板低**不是** kill 条件，只降 tier）
- **输出**：~5 候选，每个带：红队裁决 + 最大风险假设 + 校准后 `ceiling_tier` + G5 杀手锏实验设计草案。**保证 ≥1 个 MAIN-tier 进 G5**。
- **通过率**：~55%（8-10 → ~5）。
- **杀死法 ①（立项乐观无对手）**：把 skeptic 从立项后前移到批量候选筛选中 + **上下风险对称红队**。

---

## G4.5 — 理论闸 Theory（调研后·跑实验前）

- **目的**：花 GPU·h 前先用**纯推导**杀掉理论上就站不住的候选——下界/界不存在、关键量是参数恒等式、拼接式不成立、回报预测说该规模不可能 work。组合台历史最贵的塌缩（MedSeg-UQ minimax 不存在 + 拼接不成立、SelInf deflation=√(2M)−1 喂任何数据固定值、NCA-JEPA「100×」无等参对照）全是**手推就能发现、却拖到跑完才暴**的。这道闸把它们前移到 0 算力的推导侧。
- **负责**：`theorist`(opus)，经 `/theory-audit <候选> kickoff`。
- **输入**：G4 幸存 ~5 候选 + 各自最大风险假设（G4 红队提炼）。
- **动作**：
  1. theorist 对每个候选半形式化推导**四栏假设链**（核心假设→机理→可证伪预测→若假设错现象），逐步标 `[假设]→[步骤]→[结论][置信][来源]`，结论分档（定理/toy验/待跑），数字标 csv/URL 查不到标 TODO 不臆造。
  2. **回报预测**：用 scaling law / 样本复杂度 / 泛化界估「要多少数据·算力才该 work」。文献无现成 law 标 TODO 派 researcher。
  3. **三层防线**：theorist 推导 → G4 skeptic 已红队（命门 claim 可补一轮独立证伪，CoVe 式生成验证问题 + self-consistency 多路重推）→ verifier 核引用数。
- **kill 条件**：理论侧确定性证伪——下界/界**不存在**、关键量**纯参数恒等式**（σ/分母约掉喂任何数据固定值）、A+B **拼接式不成立**、回报预测说**该规模下不可能 work**。证伪须是 `定理` 档（有证明/可证伪条件），`待跑` 档**不算证伪通过也不算砍**（带进 G5 实证）。
- **输出**：~4 候选，幸存者各产**冻结假设链** `<home>/reference/THEORY_LEDGER.md`（出实证前写死防 HARKing），其可证伪预测**直接成为 G5 杀手锏要验的靶**。
- **通过率**：~80%（~5 → ~4）。**纯推导 0 算力**。
- **杀死法 ②（理论先行实证滞后）**：与 G5 互补——G4.5 推导侧先廉价证伪，G5 实证侧强制再验。**理论过 ≠ 实证过，不放松 G5 纪律。**

---

## G5 — 杀手锏预实验 Kill-shot 🛑

- **目的**：**立项前**用最便宜的实验先证伪核心 claim——这是组合台历史上最缺的一步。
- **负责**：`planner` 设计 → 🛑 主线跑（拍板点，训练经 `gpu_slot.py`）→ `verifier` 核读数。
- **输入**：G4.5 的 ~4 候选 + 各自**冻结假设链** `THEORY_LEDGER.md`（G5 跑的就是验这条链的可证伪预测）。
- **动作**：
  1. `planner` 把 G4.5 假设链的可证伪预测落成可跑的 <1 GPU·h run（最小数据/最短训练，目标=**快速证伪不是证明**）。**planner 必须预声明功效**：这实验能可靠检出的最小 effect size（MDE）+ 用 continuous metric（非 0/1 exact-match，防 floor effect）。欠功效设计退回重设。
  2. 🛑 主线 `gpu_slot.py request` 申请卡槽 → 有空卡即起（自主区，一行回报）→ 跑。
  3. `verifier` 核结果 csv（Bash/Grep，不信 Read）+ **按 R9 判三分流**：附功效声明（N/metric/95%CI/MDE）→ 判 KILL / GRAY / KILL-proxy。
- **G5 pilot 实现三铁律（优先官方·宽容·轻量）**：
  - **① 优先官方代码，非必要不手搓**：杀手锏实现优先复用候选方法/baseline 的**官方 repo**（researcher 先查 official source）；接外部库**先核版本矩阵**（装的 vs requirements pin）+ 跑官方 example 裸基准坐实地基，再改最小量验 claim。手搓只在无官方实现时，且标 TODO 说明（[[feedback_version_matrix_first]] [[feedback_no_hallucinate_settings]]）。
  - **② 测试宽容（快速证伪不是证明）**：pilot 判据从宽——只需能区分「**信号真不存在** vs **实验太小说不清**」。**不**因 pilot 没达 SOTA / 没精确复现 / 绝对性能低就判 claim 死（那是 floor effect → 走 R9 GRAY 带债，不是 KILL）。只有 `定理`级理论证伪 或 CI 窄+continuous 的干净 null 才 KILL。
  - **③ 尽量轻量**：最小数据子集 / 最短训练 / 单 seed / 优先小 proxy task 或合成数据 / 能 CPU 烟测先 CPU。硬上限 <1 GPU·h，超了退回 planner 砍规模。
  - **scope 警告**：以上宽容**只限 G5 快速证伪 pilot**；立项（G6）后正式实验仍**复现零偏离 + 数字 Bash/Grep 核 csv**（[[feedback_repro_zero_deviation]]），不把 pilot 宽松带进正式跑。
- **kill 条件**（R9，**改三分流，防假阴性误杀顶会苗子**）：
  - **KILL（照砍）**：null + CI 窄 + continuous metric → 信号真不存在，砍。
  - **GRAY（不砍，带债）**：null + CI 宽 或 binary metric/MDE 过大 → 实验太小说明不了，**候选存活**排队更大验证（kill 权重仅 0.3）。run-004 一堆 GRAY 即此症——当时若直接砍就误杀。
  - **KILL-proxy**：目标 emergent 小规模本不可测 → 换 proxy task，proxy 也无信号才 kill（权重 0.6）。
- **输出**：2-3 候选，核心 claim 经廉价实证**没当场死**（GRAY 的带「需大验证」债存活）。**verdict 必按 R10-a 标 `PASS-local`（单 setting 信号存在）vs `PASS-general`（≥2 独立 setting 不塌）**——单数据集/单实现的 PASS 只算 local，外推维度未验。
- **通过率**：~50%（5 → 2-3）。
- **杀死法 ②（理论先行实证滞后）**：强制立项前实证去风险；**反矫枉过正：欠功效 null 不当死信号，只杀干净 KILL**。
- **🆕 杀死法（假阳跨集外推，R10）**：G5 单 setting PASS = `PASS-local`，**不准当普适证据**。真命门是普适/跨集的候选（`crux_cost=HIGH`），其外推维度此处只可能拿到 local PASS——交 G6 按 R10-b 处理，**禁把外推命门 IOU 进 R7 推到立项后**（= nca-phasemap/disagree 死法）。

---

## G6 — 立项拍板 Go 🛑

- **目的**：幸存候选成立项材料，用户拍板。
- **负责**：主线整材料 → **用户拍板**（立项是用户的决策，雷打不动）。
- **输入**：G5 的 2-3 个证伪幸存候选。
- **动作**：
  1. 每个候选出完整立项卡：双 venue 分档（**顶档由 `ceiling_tier` 钉死，不准乐观虚标**——MAIN→CVPR/NeurIPS main 冲，FINDINGS→Findings/MICCAI/TMLR 务实，不让 Findings 题写成「冲 CVPR main」自欺）+ 全分数轨迹（G2-G5，含 Ceiling + kill-shot verdict）+ 红队残差 + 杀手锏读数 + **R7 书面 kill criteria**。
  2. 主线一句话推荐 + AskUserQuestion 呈给用户。**若幸存里有 `ceiling_tier=MAIN` 苗子，推荐时显式点出「这是本轮顶会苗子」**，与 Findings-tier 稳票分开呈，让用户按 portfolio（顶会赌注 vs 稳产）配。
  3. **🔒 R10-b headline 不得超实证（钉死，立项卡必过）**：立项 headline 措辞只能 claim G5 实际验过的 setting。含外推字样（普适/universal/可前验/可外推/跨集/机制特异/seed 稳定）但外推维度只有 `PASS-local`（或 `crux_cost=HIGH` 未验）→ **必须二选一**：(i) headline 收窄到已验 setting，普适降为显式标注的立项后赌注（写 R8 standout 线，不进 headline）；(ii) 把跨集/足功效命门提为硬前置 gate（PASS-general 才准用外推 headline）。**禁把外推命门丢进 R7 kill criteria 当 IOU**——R7 只兜已验范围内出意外，不兜从没验过的外推维度。
- **kill 条件**：用户不拍 → 回池 / 砍；**headline 外推字样超出 G5 实证覆盖且未按 R10-b 二选一 → 打回收窄，不准乐观立项**。
- **输出**：用户拍板的 1（少数 2）个 → `/spin-off-paper` 建 schema + 登 registry + 关联 datasets + claim + 首条 LOG（含完整选题轨迹）。
- **通过率**：~40%（2-3 → 1）。
- **杀死法 ①④**：立项基于完整证据轨迹 + 双 venue，不基于单点乐观。

---

## 漏斗数字汇总

| 闸 | 入 | 出 | 通过率 | 主要方法 |
|---|---|---|---|---|
| G1 | 100 raw | ~50 唯一 | 50% | 多策略产出 + 去重聚类 |
| G2 | ~50 | ~20 | 40% | 二元 kill + 工具撞车检测 |
| G3 | ~20 | 8-10 | 45% | InnoEval 加权 + Swiss + 12维taste |
| G4 | 8-10 | ~5 | 55% | skeptic 红队 + pre-mortem |
| G4.5 | ~5 | ~4 | 80% | theorist 半形式化推导(理论证伪/回报预测)·0算力 |
| G5 | ~4 | 2-3 | 60% | <1GPU·h 杀手锏证伪 |
| G6 | 2-3 | 1 | 40% | 双venue+kill criteria+用户拍 |

总 ~1%，与 VC deal funnel 同量级（leads→investment 0.5-1.5%）。

---

## 引用（设计依据）

- Stage-Gate（go/kill/hold/recycle + gatekeeper）：[stage-gate.com](https://www.stage-gate.com/blog/the-stage-gate-model-an-overview/)
- RICE/ICE：[ProductPlan RICE](https://www.productplan.com/glossary/rice-scoring-model/) ／ [ICE](https://www.productplan.com/glossary/ice-scoring-model/)
- Pre-mortem（+30% 风险识别）：[Gary Klein HBR 2007](https://hbr.org/2007/09/performing-a-project-premortem)
- Kill criteria：[Rajesh Dutta 2025](https://medium.com/@rajeshdutta/kill-criteria-the-uncomfortable-pill-to-swallow-for-product-managers-5f130b3a28a5)
- RAT 先测最大风险：[ModelThinkers](https://modelthinkers.com/mental-model/riskiest-assumption-test)
- VC deal funnel 转化率：[GoingVC](https://www.goingvc.com/post/the-ultimate-guide-to-navigating-the-vc-investment-funnel)
- 95% 重复 / pairwise 53.3% / human rerank：[Si et al. arXiv:2409.04109](https://arxiv.org/abs/2409.04109)
- LLM 误判 novelty：[arXiv:2502.14297](https://arxiv.org/html/2502.14297v2)
- 多样性聚类 3.4×：[Nova arXiv:2410.14255](https://arxiv.org/abs/2410.14255) ／ [co-scientist arXiv:2502.18864](https://arxiv.org/abs/2502.18864)
- InnoEval 五维：[arXiv:2602.14367](https://arxiv.org/html/2602.14367v1)
- 选题量规：Hamming [cs.virginia.edu](https://www.cs.virginia.edu/~robins/YouAndYourResearch.html) ／ Heilmeier [darpa.mil](https://www.darpa.mil/about/heilmeier-catechism) ／ Alon [PubMed 19782018](https://pubmed.ncbi.nlm.nih.gov/19782018/) ／ Jason Wei [jasonwei.net](https://www.jasonwei.net/blog/practicing-ai-research) ／ Olah [colah.github.io/notes/taste](https://colah.github.io/notes/taste/)
