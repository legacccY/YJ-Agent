# Phase 3 — 自适应置信阈值小增量

> **服务对象**：FetalSSBench 核心 claim 之三「给一个自适应置信阈值小增量稳定提升低标注区」（01_STORY.md 第 4、19 行）+ ACCEPTANCE Phase 3（02_ACCEPTANCE.md 第 21-24 行）。
> **lever**：本阶段直接撬 **L3（自适应阈值显著增益）**，并联动加固 **L12（叙事闭环）** 与 Phase 2 规律3 裂缝（见 STORY_REFINEMENT.md）。
> **caveman OFF**：本文件为决策文件，完整规范书写。
> **本阶段所有新增数值阈值（增益幅度、显著性口径、seed 数）均标「草案待用户冻结」，不自创 ACCEPTANCE 阈值（守 drift 契约）。**

---

## ① 目标 & 服务 lever

**一句话目标**：在 Phase 2 已坐实的「SSL 增益强结构依赖（易结构 FH 可靠受损 p=7.07e-08、跨结构差异稳健 p=0.0012）」之上，用一个**已被文献验证的自适应置信阈值**（FreeMatch SAT-only，非自创机制，守 R5）替换 FixMatch-Seg 的固定阈值，**测试**它在难结构/极端小目标类（PS）区能否带来实用小增量、易结构高标注区是否无害，**正负结果均报**——不预设「修复负增益」（防循环论证）。

**机制依据（精化为「极端类不平衡致固定阈值失效」，analyst 实算占比，假设待实测）**：
- **关键实算**：PS 前景占比 median **仅 2.5%**（vs FH 22% / HC18-head 31%）——PS 是**极端小目标类不平衡**结构。
- 一个**可能**成因：固定高阈值 0.8 下，模型对极端少数类（2.5% 前景）的置信度普遍偏低 → **几乎所有 PS 伪标签被滤掉** → unlabeled 信号无法注入。这是「固定阈值在极端类不平衡下失效」的**具体机制**（不是泛泛「难结构」）——**假设，非已证**，正是 Phase 3 要测的。
- 自适应阈值（FreeMatch SAT 的类别局部阈值 τ_t(c)）**自动给少数类更低阈值** → 放进本被固定 0.8 滤掉的 PS 伪标签。机制**正打 PS 的极端类不平衡痛点**，比泛泛「难结构」更精准可证。
- **双因诚实声明（必写）**：PS「难」= 低基线难结构 **+** 极端小前景占比（2.5%）双因叠加，无法拆分主因——文中并列写，不单归任一因。
- Phase 3 定位 = **诊断（极端类不平衡致固定阈值失效）→ 处方（SAT 给少数类低阈值）→ 实测（正负均报）**，不预设疗效。若实测无增量，诚实写「固定阈值已够」（GRAY 出口）。

**服务 lever**：L3（自适应阈值增益）为主，L12（叙事闭环）为辅，间接加固 Phase 2 lever②（规律3 承重）。

---

## ② 前置依赖（含 TODO）

- **[依赖] Phase 1/2 已完成**：`results/master_wide.csv`(150 run) + `results/master_long.csv`(225 行) 已就位，规律3 已 PASS（LOG Entry 10）。Phase 3 复用同 split / 同 backbone / 同训练预算，只换阈值这一个变量。
- **[依赖] FixMatch-Seg 基线已在 benchmark 内**：Phase 1 的 `fixmatch` 方法即固定阈值 `conf_thresh=0.8`（reference/SSL4MIS_hparams.md 第 17 行），直接作为 A/B 对照的 A 臂，无需重跑。
- **[TODO — researcher 动手前必核]** 自适应阈值的官方公式与分割逐前景类适配：
  - 核 **FreeMatch**（ICLR 2023, arXiv:2205.07246）。**⚠️ 关键（红队致命级单变量）**：FreeMatch = **SAT（self-adaptive threshold，自适应阈值）+ SAF（self-adaptive fairness，class-fairness 正则）两件套**。为保证「只换阈值一个变量」的干净 A/B，**只移植 SAT、关掉 SAF**（SAF 是额外的公平正则损失项，带进来=换两个变量，污染归因）。核 SAT 的全局阈值 τ_t EMA 更新公式 + 类别局部阈值 τ_t(c) 定义（原文分类任务，需确认逐**前景类**在分割下的适配——按像素类别置信度直方图还是按类平均最大概率）；**SAF 单独留作 G5 扩展臂消融**（见 ③），不进主对照。
  - 核 **FlexMatch**（NeurIPS 2021, arXiv:2110.08263）的 curriculum pseudo-labeling：类别学习难度估计 → 阈值缩放因子的公式（作消融对照）。
  - 核 **nnFilterMatch**（2025, arXiv:2509.19746）关于「像素类不平衡致阈值极低」在医学分割尚未解决的论述，作为 motivation 引用与设计空间界定。
  - 落 `reference/ADAPTIVE_THRESHOLD_hparams.md`，**逐条带官方行号/公式引用；查不到的细节显式标 TODO，绝不臆造**（守 R3）。
  - 边界：**只复用上述已验证机制，不自创新阈值公式**（守 R5）。本阶段贡献定位 = 在「跨结构难度 benchmark」上**测量**已验证的自适应阈值（SAT-only）在难结构区的实用增量（正负均报），而非提出新方法、也非预设它必然带来增益。

---

## ③ 任务分解（实验矩阵）

固定不变量：同 PSFHS/HC18 split、同 UNet base32 backbone、同 100ep/Adam lr=1e-3 训练预算、同 FixMatch-Seg 主体（弱/强增广、consistency 损失结构都不动），**唯一变量 = 置信阈值（最优固定 τ → SAT-only 自适应）**。这是最干净的单变量 A/B。

**公平 baseline（红队，防「自适应优势只是 0.8 选差」）**：固定阈值臂**不固定取 0.8，而是跑 τ ∈ {0.7, 0.8, 0.9} 取每 setting 最优**作 baseline。理由 = FreeMatch 原论文消融正是与「最优固定 τ」比，SAT 的卖点是「省去调 τ 的人力」而非「超越最优 τ」；若只比 0.8 会被批「你的自适应优势只是 0.8 选差了」。报告时注明最优 τ 由哪个值取得（透明）。

**自适应臂 = SAT-only**（关 SAF，见 ②），保证单变量。

| 组 | 目的 | 配置 | 数据/比例 | seed | 预期（中性，正负均报） |
|---|---|---|---|---|---|
| **G1** | 主对照（难结构低标注） | `fixmatch_best_τ`(τ∈{.7,.8,.9}取优) vs `sat_only`(自适应) | PSFHS-PS @ {1, 2, 5%} | ≥5 | 测自适应在难结构低标注能否带实用小增量，**正负均报** |
| **G2** | 易结构高标注无害验证 | 同上两臂 | PSFHS-FH @ {10, 20%} | ≥5 | Δ ≈ 0、CI 含 0，不退步 |
| **G3** | 第二集泛化 | 同上两臂 | HC18 @ {1, 2, 5%} | ≥5 | 高基线天花板下 Δ 小但不退步 |
| **G4** | 第三集（待数据） | 同上两臂 | FUGC @ {1, 2, 5%} | ≥5 | **待 FUGC 到位才跑**；宫颈结构作第三难度点 |
| **G5** | 机制消融（可选，扩） | `fixed_best_τ` vs `sat_only` vs `sat+saf`(整 FreeMatch) vs `flexmatch` | PSFHS @ {2, 5%} | ≥5 | 分离 SAT 单独贡献 vs 加 SAF 公平正则增益 vs 其它自适应（FlexMatch） |

- G4 依赖 FUGC 数据集（R6：拿不到则诚实写「双数据集」，**不假装有**）。
- G5 扩展：除 FlexMatch 对照外，**新增 `sat+saf`（完整 FreeMatch）臂**，把 SAF（被主对照关掉的公平正则）作为可选增益单独测量——这样既保住主对照单变量，又不丢 SAF 可能的贡献。若 G1-G3 已足够支撑 L3，G5 可降附录。

---

## ④ 每任务 DoD（验收口径，**草案待用户冻结**）

**统计方法（对齐 Phase 2 口径 + 升级）**：
- 配对检验：同 split / 同 seed / 同 backbone，只换阈值 → 用**配对 Wilcoxon signed-rank**（比 Phase 2 的 Mann-Whitney 更合适，因为是配对设计）。
- 每格 Dice 差报 **bootstrap 95% CI**。
- **分层报告**：难低区（PS @ 低标注）vs 易高区（FH/HC18 @ 高标注）分开报，不混池。
- **多重校正**：跨多个 setting 的显著性用 **Holm** 校正（与规律3 加固口径一致）。
- **seed ≥ 5**（草案；Phase 1/2 为 3 seed，Phase 3 升 5 收窄 CI）。

**DoD（逐组，正负均报，不预设疗效）**：
- **G1 PASS（草案）**：PSFHS-PS @ {1,2,5%} 自适应 vs 最优固定 τ 的 Δdice 中位为正且 Holm 后至少一比例显著（p<0.05）→ L3 兑现；**若 Δ ≈ 0 或为负 → 不是 FAIL 而是「自适应在难结构低标注无实用增量」的诚实结果**，照实报（GRAY 出口）。预注册预期效应量见 ④bis。
- **G2 PASS（草案）**：易高区 Δdice 95% CI 包含 0（无害，不退步）；不要求正增益。
- **G3 PASS（草案）**：HC18 不出现系统性退步（Δ 中位 ≥ −0.005）。
- **G4**：FUGC 到位后同 G1 判据；未到位则本组缺失照实写，不影响 L3 主结论（基于 G1-G3）。
- **G5**：描述性对比 sat_only vs sat+saf vs flexmatch，分离 SAT/SAF/curriculum 各自贡献，不强行分高下。

**Phase 3 整体（对齐 ACCEPTANCE 第 23 行，草案细化，正负均报）**：自适应在难结构/低标注区多数 setting 正增益且 Holm 后显著 → PASS（L3 兑现）；增益 ≈ 0 → GRAY 诚实写「固定阈值已够」（非 FAIL，benchmark 仍成立）。**claim 不写「修复了规律3 负增益」**（循环论证），写「测一个已验证自适应阈值的实用小增量，正负均报」。

---

## ④bis 预注册（防 HARKing，冻结进 THEORY_LEDGER）

> **红队（防 HARKing）**：跑 Phase 3 **之前**，把预期方向 + 效应量 + 判据冻结进 `reference/THEORY_LEDGER.md`（或本阶段 ledger 段），**跑完正负都报、不事后改预期**。这样无论结果如何都不构成「挑结果讲故事」。

**预注册条目（草案，待用户冻结后写入 ledger）**：
- **假设 H3'**：SAT-only 自适应阈值相对最优固定 τ，在极端小目标类难结构（PS，前景占比 2.5%）低标注（{1,2,5%}）区带来**非负**的 Dice 增量；在易结构高标注区**无害**（Δ 含 0）。机制 = SAT 给极端少数类更低阈值，放进固定 0.8 滤掉的伪标签。
- **预期方向**：难结构低标注 Δ 中位 ≥ 0（点估计期望 +0.005 ~ +0.02，**但允许 ≈0/负**，这是 GRAY 出口不是预期外）。
- **判据冻结**：PASS = Δ 中位正 + Holm 后 ≥1 比例显著；GRAY = Δ ≈ 0 诚实写「固定阈值已够」；**两种结局事先都写好措辞，跑完照填，不改预期**。
- **效应量门槛**：实用意义阈 = Δdice ≥ 0.01（低于此即便显著也写「统计显著但临床增量微小」，不夸大）。
- **正负均报承诺**：所有 G1-G5 格的 Δ（含负）全部入 `results/phase3_adaptive.csv`，不挑格报。

---

## ⑤ 风险 & 回退

| 风险 | 触发条件 | 回退（诚实，守 R4/ACCEPTANCE GRAY 条款） |
|---|---|---|
| 自适应增益 ≈ 0 | 难结构低标注 Δ 中位 ≈ 0 或 CI 全含 0 | **守 ACCEPTANCE Phase 3 FAIL（GRAY，不砍）**：诚实写「最优固定阈值在本 benchmark 已足够，自适应未带来稳定增量」。benchmark（核心贡献之一二）仍成立，自适应降为「贡献之三·可选附录」。**绝不为达标夸大成「显著优势」**（红线）。这是 ④bis 预注册的事先写好出口，不构成 HARKing。 |
| 自适应在易高区反而退步 | G2 Δ 显著为负 | 报为「自适应阈值有适用边界——仅在难低区有益，易高区应保留固定阈值」，这本身是 benchmark 的有用结论（指导临床何时用哪种）。 |
| 阈值适配引入新超参未对齐官方 | researcher 核不到分割版逐类公式 | 标 TODO，公式缺口处用最接近的官方分类版直接迁移并在文中显式声明该适配为本文工程选择，不假装是官方原版。 |
| FUGC 始终拿不到 | 邮件申请无果 | R6：诚实双数据集，G4 缺失照实写，不影响 G1-G3 主结论。 |

---

## ⑥ 对齐 ACCEPTANCE

| ACCEPTANCE 条目（02_ACCEPTANCE.md） | 本阶段如何满足 |
|---|---|
| Phase 3「自适应阈值 vs 固定阈值，跨集跨比例」(第 22 行) | G1-G4 覆盖 PSFHS/HC18(/FUGC) × 低/高比例 |
| Phase 3 PASS「低标注/难结构稳定提升(≥多数 setting 正)且统计显著」(第 23 行) | G1 DoD 草案 = 难低区多数 setting 正 + Holm 显著 |
| Phase 3 FAIL GRAY「增量≈0 → 诚实写固定阈值已够」(第 24 行) | ⑤ 回退第 1 行严格照此 |
| 红线「spread 薄就夸大」(第 34 行) | ④ 全程报绝对 Δ + CI + 绝对微负照实，不夸大 |
| 红线「私改超参凑收敛」(第 33 行) | ② 阈值机制取官方公式，只换阈值不动其余 |

---

## ⑦ 佐证（联网已核，附出处）

- **FlexMatch**（NeurIPS 2021, arXiv:2110.08263）：curriculum pseudo-labeling，按类别学习难度动态缩放阈值——自适应阈值在 SSL 分类已被验证有效。
- **FreeMatch**（ICLR 2023, arXiv:2205.07246）：self-adaptive threshold（全局 τ_t EMA + 类别局部 τ_t(c)），无需手调阈值——本阶段主力机制来源。
- **nnFilterMatch**（2025, arXiv:2509.19746）：指出「像素类不平衡导致阈值极低」在医学分割**尚未解决** → 即本阶段的设计空间与 motivation。
- **ERSR**（JBHI 2025）：用 dual-scoring adaptive filtering 做胎儿超声 SSL（HC18+PSFH）——同领域同方向先例，佐证自适应过滤在胎儿超声 SSL 可行；需在 Related Work 显式切割（本文是跨结构难度统一 benchmark + 阈值机制对照，非单集方法）。

> 上述每条引用在写 tex 前需 researcher 复核 arXiv 编号与年份，并补 FreeMatch/FlexMatch 官方阈值公式（见 ② TODO）。

---

## ⑧ 产出（artifacts）

- `results/phase3_adaptive.csv` — 每 run 一行（method ∈ {fixed_best_τ, sat_only, sat+saf, flexmatch} × dataset × ratio × structure × seed × dice/hd95；固定臂记录所用最优 τ）。**所有格的 Δ 含负值全部入表，不挑格报**（④bis 承诺）。
- `results/phase3_paired_stats.csv` — 配对 Wilcoxon p、bootstrap 95% CI、Holm 校正后 p，按难结构低标注/易结构高标注分层。
- `figures/fig_adaptive_gain.pdf` — 自适应 vs 最优固定 τ 的分层增益条形/森林图（难结构低标注 vs 易结构高标注，含 CI，正负均显示）。
- `figures/fig_closed_loop.pdf` — 因果链示意图：规律3 诊断（难结构改善概率高）→ 自适应阈值处方 → **实测结果（正负均报）**（一图讲清诊断-处方-实测链，服务 L12；**不画成预设疗效**）。
- `reference/ADAPTIVE_THRESHOLD_hparams.md` — researcher 落官方公式 + 适配说明（② 产出）。

> 含数字的图（fig_adaptive_gain）coder 交付后，主线必派 verifier（或自己 Bash）核 ≥2 个关键增益值与 `phase3_paired_stats.csv` 一致再接稿（防分母不一致/双标）。图路径与 ICLR 规范一致：`figures/` 下，main.tex 同目录引用 `figures/<name>`。

---

## ⑨ 完成判定（5 步）

1. **查阈值**：回本文件 ④ 找该组 DoD（草案需先经用户冻结）。
2. **逐条对照**：G1-G3（G4 视 FUGC）实际 csv 产出对 ④ 判据，分层报 Δ + CI + Holm p。
3. **全条 PASS → 更新 04_LOG（新 Entry）+ registry phase**；任一 FAIL → 不标完成，回 ⑤ 走对应回退（GRAY 诚实写，不硬撑）。
4. **跑防御检查**：每个 Δ 数字附近有 p 或 CI；绝对微负照实报；无「显著优势/SOTA」夸大字样；阈值机制注明官方来源（R3/R4/R5）。
5. **图验证 + 数字三方对账**：fig_adaptive_gain 过 `/validate-figures`，phase3 csv ↔ tex ↔ registry 三方对账过 verifier（对齐 Phase 4 L7）。

> 不存在「基本完成」。要么全条 PASS，要么走 GRAY 诚实回退。
