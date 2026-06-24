# gdn2vessel 故事框架（反跑偏主文档）

**适用范围**：任何 Claude / Sonnet / Opus 会话写 gdn2vessel 内容（tex / 正文 / rebuttal / 实验设计 claim）前必读。
**最后更新**：2026-06-24（**benchmark-only 重定位** — 两条命门全死后，headline 从「方法赢」彻底改为「benchmark 套件 + 诊断方法学 + 诚实负结果」；用户拍板 Entry 32）

> ⚠️⚠️⚠️ **benchmark-only 重定位（2026-06-24，两命门全死后改向，用户拍板 Entry 32）**
>
> 项目先后押过两条「我们的方法赢」的承重主轴，两条均已被预登记实验/审计**证伪**，时间线如下：
> 1. **路A（2026-06-20 ~ 06-22）：GDN-2 delta-rule 关联记忆机制特异性做断点续连 / 同根 re-ID。**
>    - 证伪：MQAR 探针（job 1482972 / 1481718，verifier 核 csv）在唯一可比收敛点 n=64 lr=1e-3 上 **gdn2≈0.999 ≈ gla≈0.992** —— delta 不比普通有状态记忆（GLA）特异；叠加 §4 目标函数错配（分割主 loss + 三道 detach 隔离 re-ID 头，对「memory 状态绑同根身份」零梯度激励）使「记忆内生做 re-ID」结构性塌缩。
> 2. **路B（2026-06-22 ~ 06-24）：可微 Frangi 门（input-derived vesselness）当外部门调制记忆，拓扑轴显著赢无门。**
>    - 证伪：`ACCEPTANCE_CRITERIA.md`「路B 最小验证 gate」预登记 PASS 需同时满足三条（≥1 集 clDice 3-seed 均值 gap ≥ +0.03 / 配对 p<0.05 且 bootstrap CI 下界 >0 / DRIVE+CHASE 两集方向都为正）。实测 **gate FAIL**：DRIVE 方向为正但 CHASE 方向相反（一正一负，不稳健），三条预登记 PASS 条件无一满足。FAIL 后机械红线（禁换轴/扩 seed/调 σ 凑显著）触发，停下报用户。
>
> **新 headline（承重主轴，benchmark-only）= 首个 2D 眼底血管断点续连评测套件**：① 合成断点协议（creatis-aligned，4-severity 难度网格，可复现，held-out 零泄漏）② 续连指标族（ε_β0 / SR / reid_rate + clDice / Betti 交叉印证，含**指标可被过预测刷满的诊断**）③ 12 baseline 全谱 leaderboard（DRIVE / CHASE / STARE / FIVES × 4 severity）④ 预登记诊断方法学 + 诚实负结果。
>
> **承重点 = 「benchmark 能区分方法 + 诊断现有方法/指标局限」，不是「我们的方法赢」。** GDN-2 记忆模块（ours_gdn2）与 Frangi 门**降为 leaderboard 上被评测的方法之一 + 一个被 benchmark 照出不稳健的门控变体**——它们的失败是 benchmark **有判别力的正面证据**，不是项目失败。
>
> **⚠️ 待批2 命门 hedge（关键纪律，对齐 [[feedback_falsify_crux_first]]）**：批2「方法间区分度」命门**还没跑**（GPU 排队中）。故凡涉及「benchmark 能 sharply 区分方法」的 claim **一律 hedge**，写成「we present a benchmark and report what it reveals」，**不写死**「our benchmark sharply ranks methods」。区分度 = 待批2 确认的承重前提，标清楚。诚实负结果（两命门死 + SR gameable）是**已确证**的，照实写。
>
> 完整战略与证伪链见 `PROJECT_LOG.md` Entry 31/32 + `PLAN/LEADERBOARD_MATRIX.md`（planner 矩阵 + 两口径偏移）+ `ACCEPTANCE_CRITERIA.md`（路B gate FAIL 记录）。

> 如果用户描述的任务与本文件冲突 → **停下来澄清**，不要按用户描述硬干（用户可能忘了已有约束）。铁律：计划外岔路先问，不盲跑。

---

## ⛔ 跑偏定义（benchmark-only 版；命中任一条立即停手）

1. **把 headline 从「2D 眼底断点续连评测套件 + 诊断方法学 + 诚实负结果」漂走**（如改回「我们的方法在拓扑/续连轴赢 SOTA」、「可微 Frangi 门显著涨点」、「delta-rule 机制特异做 re-ID」——这三条都是已死的旧主轴，禁复活成卖点）。
2. **把已死掉的路A（delta-rule 机制特异）/ 路B（Frangi 门拓扑轴显著赢）复活成承重卖点**。两者只能作为「被 benchmark 评测的方法之一」（ours_gdn2 / 门控变体）报告，其失败写进**诚实负结果**，禁包装成成功。
3. **把「benchmark 能 sharply 区分方法」写死成已确证结论**（批2 区分度命门未跑，必须 hedge：「we report what the benchmark reveals」，不写「sharply ranks/separates methods」）。
4. **benchmark 测试集拼入训练样本 / 记忆 key 或合成断点协议碰 GT 拓扑**（in-sample 伪迹 + held-out 泄漏，红线）。
5. **凭印象写数字**而非 Bash/Grep 核 csv（曾幻觉编造不存在的 csv，险踩红线）。
6. **related work 不逐条划界**断点 benchmark 先例（PTR）/ vessel reconnection 成熟工作（CorSegRec / GLCP MICCAI2025 Oral）/ 2D 眼底 completion 方法（MaskVSC）/ 协议参考源（creatis）——不划界 = 秒拒。
7. **novelty 过宽 claim**（禁 claim「首个断点 benchmark」——PTR MICCAI23 已占 3D 肺；精确收窄到「首个 **2D 眼底** 续连评测套件 = 协议 + 指标族 + 全谱基线 + 诊断方法学」的组合，见下方 novelty 收窄段）。
8. **藏诚实负结果**（两命门死 + SR 可被过预测刷满 = 已确证，必须主动写进正文；藏 = 被审稿抓 + 反 D&B track 收负结果的初衷）。
9. **改动 §1-§7 章节弧顺序**（见下方 benchmark-only 故事弧）。
10. **写绝对化措辞**（"universal" / "always" / "we prove" / "theorem" / "first benchmark"）或把诊断/诚实负结果读成胜利。

---

## 🎯 核心 Claim（论文一切内容服务于此 — 2026-06-24 benchmark-only 重定位后）

> **总纲**：本稿是 **dataset & benchmark（D&B）/ 评测方法学**贡献，不是「新方法赢 SOTA」贡献。NeurIPS Datasets & Benchmarks track 明文收**含诚实负结果的 benchmark**；承重点 = 套件能区分方法（hedge 至批2 确认）+ 诊断现有方法/指标的局限。下列四条贡献全部服务此总纲。

### Claim 1（headline 主轴）：首个 2D 眼底血管断点续连评测套件（benchmark + 合成断点协议）

> 我们构建一个**面向 2D 眼底血管断点续连**的评测套件：以 **creatis plug-and-play 合成断点协议**（arXiv 2404.10506，方法论文 = 我们的协议参考源，**非竞品**）为基础，给出**半径分布 + gap 参数固定可复现**的断点注入，并构成 **4-severity 难度网格**（Easy / Medium / Hard / Extreme）。测试集严格 **held-out**（DRIVE val 与 train 不重叠等），合成断点协议**绝不碰 GT 拓扑监督任何被测方法**。
> **精确收窄（related work 必点名，禁过宽）**：**禁 claim「首个断点 benchmark」**——PTR（MICCAI2023）已占 **3D 肺**的合成断点 benchmark。我们收窄到「首个 **2D 眼底**续连评测套件 = 合成断点协议 + 续连指标族 + 全谱基线 leaderboard + 预登记诊断方法学的**组合**」。
> **绝对禁止**：测试集拼训练样本；断点协议读 GT 拓扑回流任一被测方法；claim「first disconnection benchmark」。

### Claim 2（方法学贡献）：续连指标族 + 「SR 可被过预测刷满」的诊断

> 我们给出一族续连指标并**诊断其失效模式**——这是方法学贡献（指标缺陷诊断），先例 = NeurIPS25 Pixel-Wise Metrics / Touchstone（NeurIPS24）。
> **指标族**：主续连轴 = **ε_β0（拓扑连续量）**；辅以自定义 **SR（success rate，写公式，标 novel metric）** + **reid_rate（同根匹配率，借 MOT IDF1 逻辑，先例 Deep Open Snake Tracker arXiv 2107.09049）** + 标准 **clDice / Betti** 交叉印证。
> **★ 已确证诊断（代码层硬证据，照实写）**：**SR 可被过预测（over-prediction）刷满**。批0 烟测实测——一个 dice ≈ 0.16 的烂模型在 SR 上得 **1.0**。根因 = `success_rate` 调用的 `_is_gap_closed`（`src/benchmark/metrics.py:640`）**只检查 gap 中心邻域内是否有任一前景像素覆盖**（covers the centre of the erased zone），故一个把前景刷成一大片 blob 的退化模型可让每个 gap 都判 "closed"，SR=1.0。**因此主续连轴用 ε_β0（拓扑连续量，对 blob 刷满不免疫但更敏感于真连通性），SR 必须配 specificity / 过预测语境报告，不单独作排名轴。**
> **绝对禁止**：把 SR 当干净的主排名轴；藏掉 SR=1.0@dice0.16 的诊断（这是核心方法学贡献，藏 = 自废武功）；把诊断读成「我们的指标完美」。

### Claim 3（判别轴）：12 baseline 全谱 leaderboard + severity-response 衰减曲线

> 我们在 **DRIVE / CHASE / STARE / FIVES × 4 severity** 上同台评测 **≥12 baseline**（SSM/Mamba + 拓扑 + 经典 CNN + 续连专门方法 + ours_gdn2），按三轴报告：分割（dice/iou/auc/se/sp，sanity）+ 拓扑（clDice/Betti/Skeleton Recall）+ 续连（ε_β0/SR/reid_rate）。核心判别轴 = **severity-response 衰减曲线**（续连质量随断点 severity 衰减，不同方法斜率不同）。
> **⚠️ 待批2 hedge（铁律）**：批2「方法间区分度」命门未跑。**禁写**「our benchmark sharply ranks / separates methods」；**只写**「we present the leaderboard and the severity-response profiles, and report the separation the benchmark exhibits」。区分度是待批2 确认的承重前提，标清楚——挤一团撑不起判别轴 = 停下报用户（见 LEADERBOARD_MATRIX 批2 出口 gate）。
> **绝对禁止**：写死区分度结论；调参作弊凑某 baseline 赢/输；某 baseline 复现 Dice 低 >2-3 点不标差距就当胜利。

### Claim 4（方法学诚实点）：预登记诊断方法学 + 诚实负结果

> 我们把项目两条已死的承重命门作为 **falsify-the-crux 纪律的范例**写进论文（NeurIPS E&D track 明文收负结果 benchmark）：
> ① **MQAR theory-audit 三层防线**（theorist 推导 → skeptic 证伪 → verifier 核数）预登记 kill-criteria，证 **delta-rule 记忆在 2D 血管不特异**（n=64 lr1e-3 gdn2≈gla + §4 目标函数错配）。
> ② **路B 预登记 gate**（clDice gap≥+0.03 + 配对 p<0.05 + bootstrap CI 下界>0 + 两集方向一致，数字跑前写死）证 **Frangi 门拓扑增益不稳健**（DRIVE 正、CHASE 负，三条 PASS 条件无一满足）。
> **正向叙事转化**：这两条负结果**不削弱** benchmark——恰相反，它们是 benchmark **能照出方法不 work** 的正面证据（一个有判别力的套件就该照出门控变体不稳健 / 记忆机制不特异）。GDN-2 与 Frangi 门**降为 leaderboard 一行 + 一个被照出的门控变体**。
> **绝对禁止**：改判定方向去掩盖负结果；选择性只报 DRIVE 涨那一组复活 Frangi 门 claim；把 delta≈gla 读成「delta 仍有微弱优势」复活机制特异。

### 贡献列点（写 §1.4 用，benchmark-only）

1. **benchmark + 合成断点协议**：首个 **2D 眼底**续连评测套件（creatis-aligned 协议 + 4-severity 网格 + 可复现 + held-out 零泄漏）。
2. **续连指标族 + SR 可被过预测刷满的诊断**（dice0.16 烂模型 SR=1.0 实证，代码层根因 `_is_gap_closed` 只看覆盖）——方法学贡献。
3. **12 baseline 全谱 leaderboard + severity-response 衰减曲线**（判别轴，区分度待批2 hedge）。
4. **预登记诊断方法学 + 诚实负结果**（MQAR 三层防线证 delta 不特异 + 路B gate 证 Frangi 门不稳健）——falsify-the-crux 范例。

### CV 方法 / D&B 定位（投稿必读）

> 本稿走 **dataset & benchmark / 评测方法学** 投稿路线（NeurIPS D&B、ACCV/工作坊保底），贡献落在**新 benchmark + 指标诊断 + 诚实负结果**，不靠「我们的方法赢」也不靠纯临床故事撑录用。医学数据集是 benchmark 的 validation 场景。

---

## 📐 故事弧（章节顺序锁定 — benchmark-only D&B 稿）

```
§1 Intro
├── §1.1 问题：细长血管/管状结构在遮挡/低对比处断点，续连质量难评测、现有指标语义不清
├── §1.2 现状缺口：2D 眼底无标准化断点续连评测套件（断点 benchmark 先例 PTR 在 3D 肺；续连指标散落、缺失效模式诊断）
├── §1.3 ★ Hook：首个 2D 眼底断点续连评测套件 = 合成断点协议 + 续连指标族（含指标诊断）+ 12 baseline 全谱 leaderboard + 诚实负结果 ★（hedge：we present and report what it reveals）
└── §1.4 贡献列点（benchmark+协议 / 指标族+SR诊断 / 全谱 leaderboard+衰减曲线 / 预登记诊断方法学+诚实负结果）

§2 Related Work（必逐条划界，见 novelty 收窄段）
├── 血管/管状分割（CNN 经典 + SSM/Mamba 家族）= 被评测方法来源
├── 拓扑/连通性指标与方法（clDice/cbDice/Betti/Skeleton Recall）+ ★ vessel reconnection 成熟工作硬区分：CorSegRec / GLCP MICCAI2025 Oral（成熟，必对比，不 claim 首个连通）★
├── 合成断点 benchmark 先例：★ PTR MICCAI23（3D 肺，已占断点 benchmark，禁 claim 首个）★ + tracing 家族（VGN/Trexplorer，需起点）
├── 2D 眼底 completion：★ MaskVSC TMI25（方法论文非 benchmark，硬区分我们是评测套件）★
├── 协议参考源：★ creatis arXiv2404.10506（方法论文 = 我们的合成断点协议来源，非竞品）★
└── 评测方法学 / 指标诊断：NeurIPS25 Pixel-Wise Metrics / Touchstone NeurIPS24（指标缺陷诊断先例，定位我们的 SR 诊断）

§3 Benchmark：合成断点协议 + 续连指标族（杀手锏，方法学核心）
├── §3.1 合成断点协议（对齐 creatis plug-and-play，半径分布+gap 参数，4-severity 难度网格，可复现；与 PTR 划界）
├── §3.2 续连指标族（ε_β0 主续连轴 / 自定义 SR 写公式 novel metric / reid_rate 借 MOT IDF1 / clDice+Betti 交叉印证）
├── §3.3 ★ 指标失效模式诊断：SR 可被过预测刷满（dice0.16→SR=1.0，代码根因 _is_gap_closed 只看覆盖）→ 主轴用 ε_β0、SR 配 specificity 语境 ★
└── §3.4 防泄漏设计（测试集 held-out 零拼训练样本；合成断点协议不碰 GT 拓扑监督被测方法；grep 验证）

§4 Baselines & Leaderboard（判别轴）
├── §4.1 Setup（数据集 DRIVE/CHASE/STARE/FIVES / ≥12 baseline 官方超参禁改 / 三轴指标 / seed≥3 / 4 severity）
├── §4.2 全谱 leaderboard（三轴表，hedge 区分度至批2；ours_gdn2 = 普通一行，不开后门）
└── §4.3 severity-response 衰减曲线（续连随 severity 衰减，方法斜率差异 = 判别轴；hedge：报 benchmark 呈现的 separation，不写死 sharply ranks）

§5 Diagnostic Methodology & Honest Negative Results（方法学诚实点，D&B track 核心收稿点）
├── §5.1 预登记诊断方法学（falsify-the-crux 纪律：跑前写死 kill-criteria，禁 HARKing；三层防线 theorist→skeptic→verifier）
├── §5.2 负结果一：delta-rule 记忆在 2D 血管不特异（MQAR n=64 gdn2≈gla + §4 目标函数错配；ours_gdn2 leaderboard 表现）
├── §5.3 负结果二：可微 Frangi 门拓扑增益不稳健（路B 预登记 gate FAIL，DRIVE 正/CHASE 负，三条 PASS 条件无一满足）
└── §5.4 正向转化：负结果 = benchmark 有判别力的正面证据（套件照出门控变体不稳健 / 记忆不特异）

§6 Discussion + Limitations（续连随 severity 衰减；synthetic 断点 vs 真实病理断点；区分度待批2 确认的 hedge；SR 单轴不可信须配语境；指标族外推边界）
§7 Conclusion
```

---

## 🔒 锁定数字表（实验后由 verifier 核 csv 回填，此刻一律 TODO，严禁臆造）

### leaderboard 三轴（DRIVE/CHASE/STARE/FIVES × 4 severity，每 cell 列见 LEADERBOARD_MATRIX）

| 数据集 | severity | 方法 | dice | clDice | Betti β₀/β₁ err | ε_β0 | SR | reid_rate |
|---|---|---|---|---|---|---|---|---|
| DRIVE | Medium | ours_gdn2 | TODO | TODO | TODO | TODO | TODO | TODO |
| ... | ... | ... | TODO | TODO | TODO | TODO | TODO | TODO |

> 列定义、统计（3-seed mean±std + per-image bootstrap 95%CI 手算 numpy，**禁 scipy.stats** = OMP 红线）、审计列（ckpt_path/eval_input_mode/threshold/git_commit/severity）全见 `PLAN/LEADERBOARD_MATRIX.md`。
> **ε_β0/SR/reid_rate 从 pred_mask + GT 算，不需 re-ID 头 → 12 baseline 公平同台**；reid_rate_head 仅 ours_gdn2 专属附加列（不污染主列）。

### SOTA 参照（researcher×4 核源 2026-06-20，作为 baseline 复现「该到多少」的参照，非我们的卖点。全表来源/陷阱见 [`reference/SOTA_NUMBERS.md`](reference/SOTA_NUMBERS.md)）

| 数据集 | 当前最高 Dice | 方法（来源） | clDice 报告者 |
|---|---|---|---|
| DRIVE | ~0.84 | EFDG-UNet 0.8412 / HM-Mamba 0.8327 / VFGS-Net 0.8323✓ | HREFNet 0.8240 |
| CHASE_DB1 | ~0.85 | EFDG-UNet 0.8469 / HM-Mamba 0.8197✓ | HREFNet 0.8293 |
| STARE | ~0.85 | FSG-Net 0.8510✓ / MDFI-Net 0.8581(待核split) | FA-Net 0.8763 |
| FIVES | ~0.918 | PASC-Net 0.9183✓ | PASC-Net 0.9174 |

> 基调（benchmark-only）：SOTA 数字只作 **baseline 复现 sanity 参照**（某 baseline 复现 Dice 低 >2-3 点须标差距，不当胜利）；本稿**不卖「ours 赢 SOTA」**——胜负不是承重点，benchmark 的判别力 + 指标诊断 + 诚实负结果才是。
> ⚠️ creatis 协议两修正（见 reference）：原文**无 boundary blur、无 SR 指标**（只 DSC/ASSD/ε_β0 三指标）。我们的 SR 是自定义新指标（写公式，标 novel + 主动报告其过预测失效模式 = 方法学诚实）。
> ⚠️ **两簇协议不可比**：DRIVE/STARE 报告值分主流簇(~0.83–0.85)+高簇(协议差异非真实力)。参照只用主流簇，高簇引用必标"协议不同"。

---

## 🛡️ 防御写法硬规则（违反即跑偏 — benchmark-only 版）

| 编号 | 严禁 | 必须 |
|---|---|---|
| R1 | "universal" / "always" / "first disconnection benchmark" | 收窄到「first **2D fundus** reconnection evaluation suite」组合；衰减如实附曲线 |
| R2 | "we prove" / "theorem" / "uniqueness" / "sharply ranks methods"（区分度未确证） | "we design / we present / we report what the benchmark reveals"（区分度 hedge 至批2） |
| R3 | related work 不区分 GDKVM / 把记忆当机制卖点 | 模板："the memory module (ours_gdn2) is one evaluated method on the leaderboard; we make **no** claim of mechanism specificity—our pre-registered audit shows delta-rule memory is **not** specific on 2D vessels (MQAR n=64 gdn2≈gla)." |
| R3b | related work 不逐条划界断点 benchmark 先例 / vessel reconnection 成熟工作 / 协议源 | 必逐条点名：**PTR（MICCAI23，3D 肺，已占断点 benchmark，禁 claim 首个）** / CorSegRec / **GLCP（MICCAI2025 Oral）** / MaskVSC（TMI25，方法非 benchmark）/ **creatis（arXiv2404.10506，我们协议参考源非竞品）** |
| R4 | 把 ours_gdn2 / Frangi 门写成 headline 卖点或贡献 | 它们 = leaderboard 一行 + 一个被照出不稳健的门控变体；其失败 = benchmark 判别力的正面证据，写进 §5 诚实负结果 |
| R5 | 合成断点协议 / 被测方法 / 记忆 key 读 GT 拓扑；测试集拼训练样本 | **声明**：协议与所有被测方法 input-derived，**never GT topology**；评估用 GT 当裁判 = allowed；测试集 held-out 零拼训练（grep 验证）|
| R6 | 复活已死命门：delta-rule 机制特异（A2>gla）/ Frangi 门拓扑显著赢；选择性报 DRIVE 涨那组 | 两命门死 = 诚实负结果照实写；增益/胜负不是承重点，benchmark 判别力 + 指标诊断才是 |
| R7 | 把 SR 当干净主排名轴 / 藏 SR=1.0@dice0.16 诊断 | 主续连轴 = ε_β0；SR 配 specificity / 过预测语境；SR 失效诊断（代码根因 _is_gap_closed）必写进 §3.3 = 核心方法学贡献 |
| R8 | bare numbers / 凭印象写数字 | 续连/拓扑数字附 per-image bootstrap 95%CI（手算 numpy，禁 scipy.stats）；leaderboard 附 3-seed std；数字一律 Bash/Grep 核 csv 入 tex 前过 verifier |
| R9 | 把区分度写死 / 把诚实负结果读成胜利 / 纯临床故事撑录用 | 区分度 hedge 至批2；负结果如实呈现 = D&B track 严谨点；D&B/方法学贡献先行，医学集是 validation |

---

## 📊 novelty 真实性（2026-06-24 benchmark-only 重定位后，researcher 核实收窄）

- **★ 主轴 novelty = 首个 2D 眼底断点续连评测套件**（合成断点协议 + 续连指标族 + 12 baseline 全谱 leaderboard + 预登记诊断方法学的**组合**）。**禁 claim「首个断点 benchmark」**——PTR（MICCAI23）已占 3D 肺。
- **方法学 novelty = SR 可被过预测刷满的诊断**（dice0.16→SR=1.0，代码根因坐实），先例 NeurIPS25 Pixel-Wise Metrics / Touchstone NeurIPS24（指标缺陷诊断是合法贡献类型）。
- **已撞车需划界（禁 claim 首个）**：断点 benchmark = PTR；vessel reconnection 成熟 = CorSegRec / GLCP（MICCAI2025 Oral）；2D 眼底 completion = MaskVSC（TMI25，方法非 benchmark）；合成断点协议源 = creatis（参考非竞品）。
- **已证伪不得复活（写进诚实负结果，不卖）**：① delta-rule「机制特异做 re-ID」= MQAR delta≈gla + §4 目标函数错配双重证伪；② 可微 Frangi 门「拓扑轴显著赢」= 路B 预登记 gate FAIL（DRIVE 正/CHASE 负）。两者作为「被 benchmark 评测/照出的方法」报告。
- **⚠️ 待确证 hedge**：「benchmark 能区分方法」= 批2 命门未跑，凡此处 claim 一律 hedge「we report the separation the benchmark reveals」，不写死「sharply ranks」。

---

## 🚨 会话开始前 checklist

1. ✅ 读本文件一遍
2. ✅ 读 `PLAN/MASTER_PLAN.md` + `PLAN/LEADERBOARD_MATRIX.md`（benchmark-only 矩阵 + 批2 区分度命门 + 两口径偏移）
3. ✅ 读 `ACCEPTANCE_CRITERIA.md`（路B gate FAIL 记录 + benchmark-only 专属区分度门待补）
4. ✅ 读 `PROJECT_LOG.md` 最新 entry（Entry 31/32 benchmark-only 拍板）
5. ✅ 写数字前先 Bash/Grep 核数据源 csv（禁 Read 看数据，曾幻觉编造）
6. ✅ 凡涉「benchmark 区分方法」claim → hedge 至批2（不写死 sharply ranks）
