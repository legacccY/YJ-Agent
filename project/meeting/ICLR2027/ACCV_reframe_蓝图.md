# ACCV / WACV Reframe 蓝图（设计文档，先设计不改 tex 主体）

**论文**：Closed-Loop Quality-Triage for Reliable Skin-Lesion Diagnosis
**转投决策**：ICLR → ACCV 2026（用户拍板，PROJECT_LOG 会话 46）/ WACV 2027（主线判客观更优，对冲 method-novelty 弱轴 + Applications track 有 AC overrule 应用稿保护）。venue 最终可等补强结果 + WACV 2027 ddl 公布再定。
**作者**：Writer（opus，caveman OFF）
**日期**：2026-06-19
**适用**：本蓝图 = emphasis 重定位的设计准绳，主线审过后才动 `drafts_short/` 现有 tex。

---

## 0. Drift 契约（开工声明）

本蓝图服务 **ICLR→ACCV/WACV 转投**（会话 46 决策）。动作 = 把 emphasis 从「ICLR 诚实-analysis（负结果当 headline）」重定位成「CV 会议 method/system paper（positive contribution 当 headline）」。

**只改 emphasis，绝不改 truth value。** 严守 skeptic 红队定的诚实安全线（会话 46 钉死）：

| 维度 | ✅ 允许 | 🛑 禁止 |
|---|---|---|
| headline | 换谁当核心卖点（C1 上、C3 降 analysis）| 把负结果写成正结果 |
| weight | 改各 claim 分量（headline / 支撑 / limitation）| 用聚合数掩盖 per-class（melanoma） |
| 放置 | 改哪节正文哪节 analysis/limitation | 把「打平」暗示成「赢」 |
| 数字 | 一字不改，只搬位置 | 删 CI / 删 p-value / 改阈值方向 |

**三条铁律负结果（必须如实留正文，带数字带 CI，只从 headline 降到 analysis/limitation）**：
1. melanoma 救援净负 −81（v6 mask-L1 null，5.2%→5.2%）。
2. 固定阈值全局 triage 不超 Direct（confidence-gated sens 0.818 Direct vs 0.788 最强变体 @20% referral）。
3. Thm 2 仅区间 [τ_enh, τ_high] 局部条件界，非全局界。

**红线继承（不可碰）**：R1-R14（STORY）+ R10 不搬 BMVC 表/数/图 + 数字只用已核实锁定值（不自创）+ Q-VIB 仅脚注（r1/r2/r3 FAIL 钉死）+ 不用扩散增强。

---

## 1. 新 headline / positive 定位

### 1.1 诊断：现有 framing 已经 80% reframe-ready

会话 44/45 的现有 abstract（`main_iclr9.tex` L27-49）+ §1 intro（`drafts_short/s1_intro.tex`）其实**已经是 positive 开头**：
- 第一句 = "We present a **closed-loop quality-triage system**"（系统贡献），
- 第一 contribution = "a recipe for enhancing **safely**: DP-Loss + Pinsker-optimal MI lower bound"（C1），
- 负结果放在 abstract **末尾**、§1 末条 bullet，措辞 "we report rather than hide an honest negative"。

这是 ICLR analysis 轨的诚实写法，**已不把负结果当 hook**。转 CV 会议要做的不是推倒重来，而是**把 positive 推得更前、更实、更"method/system paper"腔**，并把支撑性"analysis/动机"语气（决策面 C0、诚实边界 C3）的相对分量进一步压低。

### 1.2 新 headline（主推单点 = C1，机制 novelty = C2 焊死在第二位）

> **一句话 headline（abstract 首句候选）**：
> "We present **DP-Enhance**, a diagnosis-preserving image-enhancement method for degraded dermoscopy that provably bounds the loss of diagnostic information, wrapped in a **closed-loop quality-triage** pipeline whose **query-for-retake** channel requests re-acquisition when an image is beyond safe enhancement."

> **两句版（method + 为什么 CV reviewer 买）**：
> "Existing restoration improves perceptual quality with no guarantee that diagnostic content survives. We introduce a feature-level **diagnosis-preserving objective (DP-Loss)** whose information loss we bound by a Pinsker-optimal mutual-information lower bound, and embed it in a quality-triage system that decides, per input, whether to diagnose, enhance, or **query for a retake** — the first re-acquisition channel in this setting."

**为什么 CV reviewer 会买（method/system paper 视角）**：
1. **C1 是真硬 positive，CV reviewer 吃这套**：DP-Loss ablation E7 ΔAUC_enh **+0.0205 CI[+0.005,+0.035] 显著>0**、ΔKL **−0.148 CI[−0.173,−0.124]**、McNemar **p=2.3e-45**（run_id 1441301）——这是"我加了这个 loss，诊断保真显著变好"的标准 method-contribution 句式。配 Lemma 3 理论 = 方法 + 保证，CV/应用轨喜欢。
2. **C1 vs 6 SOTA 有对照赢面**：E10 6/6 显著优（paired ΔAUC(baseline−VE)∈[−0.116,−0.066] 全 CI 排除 0、McNemar p<1e-150、PSNR 32.79 vs 13-22，job 1448952）。CV reviewer 要看"比 baseline 好"，这条直接给。**⚠️ 公平性陷阱（skeptic）**：现 E10 是 zero-shot baseline，DP-Loss 见过诊断监督而 baseline 没见过 → R1（baseline fine-tune）+ R3（DP-Loss graft 到 baseline 证可移植）出结果后才能把这条说满（见 §5）。
3. **C2 是机制 novelty，对冲"incremental method"批评**：query-for-retake = 文献首次采集闭环（AT-CXR/Geifman 只 defer/abstain）。CV 应用轨（尤其 WACV Applications）认"系统里一个别人没有的机制环节"。
4. **closed-loop system framing 让散贡献收成一条线**：把 C0/C1/C2/C3 从"四个并列贡献"收成"一个系统 + 一个核心方法 + 一个新机制 + 诚实边界"，治 skeptic 指出的"贡献散"结构病。

### 1.3 候选取舍（C1 主 vs C2 主）

| 候选 | 当 headline 的强度 | 风险 | 结论 |
|---|---|---|---|
| **C1（DP-Loss + Lemma3）** | 最硬 positive：E7 p=2.3e-45 + E10 6/6 + 理论界 | 公平性需 R1/R3 补强；否则 reviewer 攻"用了诊断 label 不公平" | **主推核心**（method paper 骨干）|
| **C2（query-for-retake）** | 机制 novelty 强、独家、抗"incremental" | 单独当 headline 撑不住——全局 triage 实证负（0.818 vs 0.788），不能 claim 性能赢 | **焊死第二位**（system novelty，定位"新机制"非"性能赢"）|

**最终定位**：C1 + C2 双核 headline，**C1 扛"方法有效 + 有理论"，C2 扛"系统有别人没有的新环节"**。C0（决策面）降为动机/支撑章，C3（诚实边界）降为 analysis + limitation（带数字如实留）。

---

## 2. 贡献重排（4 合 1 → 主贡献 + 支撑）

### 2.1 现状（ICLR 四论点 C0-C3 并列）

STORY §1.4 现有 4 bullet = C0 决策面（动机）+ C1 增强（最硬）+ C2 agent（独家）+ C3 边界（诚实）。问题：CV reviewer 看 4 个并列 contribution 会判"each incremental"（skeptic 🔴①）。

### 2.2 重排（system paper 三层结构）

```
【主贡献 L1 — 核心方法】
  C1  DP-Loss diagnosis-preserving enhancement + Lemma 3 MI 下界
      └ 证据：E7（p=2.3e-45）+ E3（dAUC −0.012 / agree 0.9575）+ E10（6/6 vs SOTA）
      └ 补强后更满：R1（baseline ft 公平比）+ R3（DP-Loss graft 可移植）

【主贡献 L2 — 系统机制 novelty】
  C2  query-for-retake closed-loop triage（四通道 + 采集闭环，文献首次）
      └ 证据：retake 触发率梯度 high 0.055 / moderate 0.651 / severe 0.889
      └ 定位：新机制，非性能赢（Thm2 局部界，全局 triage 诚实负）

【支撑层 — 动机 + 理论 + 诚实边界】
  C0  reliability × recoverability 决策面 → 动机章（为什么需要 quality-aware triage）
      └ 不当独立 contribution，降为 §3 motivation + analysis
  理论 Lemma3 / Prop3 / Thm2 → C1/C2 的理论支撑（we derive，非 we prove，R2）
  C3  诚实边界（melanoma 净负 / severe / contrast S5）→ analysis + limitation
      └ 如实留正文带数字，定位"query-for-retake gate 的最硬动机"，从 headline 降到 §7 analysis
```

### 2.3 §1.4 contribution bullet 改写（4 → 3，C0 并入动机句）

现有 4 bullet（C0 独立 + C1/C2/C3）→ 改为 **3 条 contribution bullet**，C0 从 bullet 降为引导句：

- **引导句（C0 动机，非 bullet）**："To map *when* enhancement is licensed, we chart a reliability × recoverability decision surface that quantifies where degradation breaks diagnosis and where enhancement recovers it; this motivates the three contributions below."
- **Bullet 1 = C1**（DP-Loss + MI 下界，method 核心）
- **Bullet 2 = C2**（query-for-retake agent，机制 novelty）
- **Bullet 3 = C3 边界 + Thm2 局部界**（诚实边界，如实但定位为"动机/系统设计依据"，不当卖点）

> 注：现有 §1 已是这个结构（C0 引导句 + C1/C2/C3 三 bullet），**改动量小** —— 只需把 C1 bullet 措辞推得更"method paper"（强调 method name + 比 SOTA），把 C3 bullet 的 limitation 语气保住（不上升、不藏）。

---

## 3. 「claim → 证据 → 放正文哪节 → weight」对照表

> weight 三档：**HEADLINE**（abstract + §1 核心卖点）/ **支撑**（正文支撑性结果）/ **LIMITATION/ANALYSIS**（如实负结果，带数字带 CI，不当卖点不藏）。
> 数字全部 = STORY/ACCEPTANCE 锁定值（已核实），本表不自创。

| # | Claim | 证据（数字 + 源） | 正文位置 | weight |
|---|---|---|---|---|
| 1 | DP-Loss 使增强不损诊断（method 核心）| E7 ΔAUC_enh **+0.0205 CI[+0.005,+0.035]**、ΔKL **−0.148 CI[−0.173,−0.124]**、McNemar **p=2.3e-45**（1441301 / `stage2_diag_paired_v5.csv`）| §4.2-4.3 + §7.3 | **HEADLINE** |
| 2 | 增强后诊断基本不变 | E3 dAUC **−0.0120**、agree **0.9575**、McNemar(enh-vs-ref) **p=0.573**（1441301）| §7.2 | **HEADLINE**（支撑 C1）|
| 3 | Lemma 3 互信息下界保证 | $I(Z_{enh};Y)\geq I(Z_{ref};Y)-\beta\sqrt\epsilon$，β≈0.74，Pinsker-optimal（`plans/Prop3_Lemma3_*.md`）；toy PASS | §4.3 + App A1 | **HEADLINE**（理论腿，"we derive" R2）|
| 4 | vs 6 SOTA 增强诊断保真显著优 | E10 6/6：paired ΔAUC(baseline−VE)∈**[−0.116,−0.066]** 全 CI 排除 0、McNemar **p<1e-150**、PSNR **32.79 vs 13-22**（1448952）| §7.5 | **HEADLINE**（⚠️ zero-shot，R1/R3 补强后说满，见 §5）|
| 5 | query-for-retake 采集闭环（机制 novelty）| 四通道；retake 触发率 high **0.055** / moderate **0.651** / severe **0.889**（`agent_vs_direct_risk.csv`）| §5.1 + §7.8 | **HEADLINE**（系统 novelty）|
| 6 | FiLM 卖诊断保真非 PSNR | E8 FiLM 对 PSNR 中性（33.06≥32.74）；诊断保持正：dAUC −0.033 vs −0.042、agree 0.90 vs 0.87、KL 0.24 vs 0.35 | §7.6 | 支撑（C1 架构，**禁卖 PSNR 增益**）|
| 7 | FiLM vs cross-attn 统计无法区分 → parsimony 保留 FiLM | E9 paired ΔAUC +0.0016 CI[−0.0057,+0.0086] 含 0、McNemar p=0.679（−1.8M 参数）| §7.6 | 支撑 |
| 8 | 增强质量达标 | E1 PSNR **32.74**（with-FiLM）/ 33.06（no-FiLM）、SSIM 0.91、n=19878 | §7（或 §6 setup）| 支撑 |
| 9 | 速度可部署 | E12 **16.08 ms/img**（p95 17.0）| §7.8 | 支撑 |
| 10 | reliability × recoverability 决策面（动机）| C0 网格 n=360/cell：blur S5 跌 **−0.0911**（最脆）；可恢复性 blur/color_shift S3+ 转正（CI_lo>0）| §3.2-3.3 + §7.1 + App A4 | 支撑（**动机章，非 contribution**）|
| 11 | contrast 极端档增强显著伤诊断（per-dimension 触发点）| C0 contrast S5（α=0.19）recoverability_delta **−0.0355 CI[−0.0783,−0.0013]** 排除 0（全 25 cell 唯一 HURT）| §3.3 + §7.1 | **ANALYSIS**（per-dimension 触发点，**严禁泛化"severe 普遍伤诊断"**）|
| 12 | severe 段增强伤诊断（per-class 混合段）| E6 dAUC **−0.0559 CI[−0.085,−0.028]** 排除 0、dflip 0.46（1441321 / `e6_severe.csv`）| §7.8 | **ANALYSIS**（query-for-retake 动机，非项目失败）|
| 13 | melanoma 救援净负（最硬负结果）| E5 per-class：benign salvage **75.6%(1809/2392)**；**melanoma 5.2%(4/77)、damage 31% → 救 4 毁 81 净 −81**（`e5_salvage_persample.csv`）| §7.4 + App A7 | **LIMITATION**（🛑 禁聚合 0.737 当达标；如实带 per-class）|
| 14 | v6 mask-L1 重训救不了 melanoma（诚实 null）| salvage **5.2%→5.2%** 纹丝不动、net −81→−79（`e5_salvage_v6_persample.csv`）| §7.4 | **LIMITATION**（诚实 null）|
| 15 | 固定阈值全局 triage 不超 Direct（铁律负）| §7.7 DCA 四法净收益 95% CI **全重叠 0.179–0.192**；triage@20% **Direct sens 0.818 最优**、最强变体 0.788 仍不超 | §7.7 + §5.2 | **LIMITATION/ANALYSIS**（🛑 主动认负 "no claim triage raises net benefit globally" R3）|
| 16 | Thm 2 局部条件界（非全局）| 增强收益 Δ>0 仅在 [τ_enh,τ_high] 内成立；全局诚实负；threshold-learning future work | §5.2 + App A2 | **支撑 + ANALYSIS**（🛑 R11 禁写全局界）|
| 17 | E2 分退化 2/4 PASS | brightness 37.68 ✅ / blur 35.82 ✅；color_shift 33.77 ❌ / contrast 29.11 ❌（< 降质 32.29）| §7.6 + limitation | **LIMITATION** |

**对照表概要（weight 分布）**：HEADLINE = #1-5（DP-Loss + Lemma3 + E10 + retake 机制）；支撑 = #6-10；ANALYSIS = #11-12；LIMITATION = #13-17（三铁律负 #13/#15/#16 全在，如实带数字带 CI）。

**诚实自查锚点**：负结果 #13/#14/#15/#16 全部仍在正文，带 per-class、带 CI、带"make no claim"措辞——只从"曾被设想当 headline"降到 LIMITATION/ANALYSIS，truth value 零改动。

---

## 4. abstract + §1 intro reframe 草案（positive 开头，负结果如实不当 hook）

> 现有 abstract/§1 已 positive 开头，下面草案 = **在此基础上把 method/system 腔推满**（method name 显形、C1 更前、负结果保留在末尾如实段）。数字全部锁定值，未改一字。**投稿前 method name 需脱敏定稿（R4）**——下用占位名 **DP-Enhance**（增强）/ **5-head IQA**（质量评估），最终统一脱敏。

### 4.1 Abstract 草案（method/system paper 腔）

> Skin-lesion diagnostic models trained on curated dermoscopy degrade sharply on real consumer-device
> photographs — blurred, poorly lit, incompletely framed, colour-cast, low-contrast — on which a model
> can be confidently wrong. Generic restoration improves perceptual quality but offers **no guarantee that
> diagnostic content survives**, and blindly deferring every imperfect image wastes recoverable cases.
> We present **DP-Enhance**, a **diagnosis-preserving enhancement** method wrapped in a **closed-loop
> quality-triage** system. Our core contribution is a feature-level diagnosis-preserving objective
> (DP-Loss) whose information loss we bound by a **Pinsker-optimal mutual-information lower bound**
> ($I(Z_{enh};Y)\geq I(Z_{ref};Y)-\beta\sqrt{\epsilon}$, Lemma~3). Within a moderate-degradation window
> enhancement leaves diagnosis essentially unchanged ($\Delta\mathrm{AUC}=-0.012$, $95.8\%$
> enhanced-versus-reference agreement, McNemar $p=0.57$), and a DP-Loss ablation confirms the effect is
> attributable to the objective ($\Delta\mathrm{AUC}_{\text{enh}}$ $+0.0205$, $95\%$ CI $[+0.005,+0.035]$;
> McNemar $p=2.3\times10^{-45}$); against six restoration baselines DP-Enhance preserves diagnosis better
> on every one. A per-input quality estimate (our instantiation uses a five-head assessor, PLCC $0.924$;
> any no-reference scalar suffices) routes each image to one of four channels — diagnose, cautioned
> diagnose, enhance-then-diagnose, or **query for a retake** — the last, to our knowledge, the **first
> re-acquisition channel** in this setting, backed by a local per-band conditional risk guarantee
> (Theorem~2). We also **report, rather than hide, two honest boundaries** that justify the retake gate:
> enhancement turns net-negative on severely degraded melanoma (salvage $5.2\%$ against a $31\%$ damage
> rate, unchanged under a mask-reweighted retrain), and under a fixed-threshold policy global triage does
> not yet beat direct diagnosis (confidence-gated sensitivity $0.818$ vs $0.788$ at a $20\%$ referral
> budget) — motivating learned routing thresholds. Code and benchmark will be released.

**与现有 abstract 的差异（emphasis-only）**：
- 首句换成 method+system 双名（DP-Enhance + closed-loop quality-triage），"Our core contribution is..." 直接点 DP-Loss + Lemma 3。
- 加一句 vs 6 baseline（"preserves diagnosis better on every one"）——CV reviewer 要的对照赢面。
- 负结果**两句压在末尾**，措辞 "report, rather than hide"，带 per-class（5.2% / 31%）、带 0.818 vs 0.788、带 "does not yet beat" + "motivating learned thresholds"。**truth value 零改**。
- ⚠️ vs-baseline 那句目前是 zero-shot E10；R1/R3 补强落地后，把 "against six restoration baselines... better on every one" 升级为 "even after fine-tuning each baseline on degraded dermoscopy"（见 §5）。

### 4.2 §1 Intro reframe（段落级，改动点）

现有 §1 四段（Problem / Why existing tools fall short / Closed-loop quality-triage / Contributions）结构保留，改 emphasis：

**§1.1 Problem（保留，微调收尾句）**：保留"is this image good enough to diagnose, and if not, what should the system do?"——这是 system framing 的好钩子，不动。

**§1.2 Why existing tools fall short（保留三 family，加一句 method gap）**：现有列了 calibration / uncertainty / generic enhancement 三家。**加一句焊 method gap**："Crucially, none of these *preserves the diagnostic signal under a guarantee* — generic enhancement optimises perception, not diagnosis." 把"缺一个 diagnosis-preserving 方法"显成 gap，为 C1 当 headline 铺路。GradProm 差异化段（R12）从 related work 引一句到此（"gradient-level repair treats the symptom; we bound the information loss"）。

**§1.3 Closed-loop quality-triage（保留，加 method name 锚）**：现有段已好，把方法名 DP-Enhance 锚进去（"the agent... enhance-then-diagnose (via DP-Enhance)..."）。

**§1.4 Contributions（4 bullet → 3 bullet + C0 引导句，见 §2.3）**：
- C0 从独立 bullet 降为引导句（动机）。
- Bullet 1 = C1（method 核心，措辞推满 method paper 腔 + 提 vs 6 SOTA）。
- Bullet 2 = C2（机制 novelty）。
- Bullet 3 = C3 边界 + Thm2 局部界（**保留现有诚实措辞** "we show, and do not hide" + "global triage does not yet beat direct diagnosis (0.818 vs 0.788)... motivation for learned routing thresholds rather than a result to suppress"——这段现有写法已完美守诚实安全线，**一字不改**）。

> **关键**：§1.4 现有 bullet 3（s1_intro.tex L53-59）已经是教科书级诚实负结果写法。reframe **不碰它**，只把 C1 bullet（L39-46）的 method 腔推满。

---

## 5. 补强实验（R1 + R3）出结果后怎么接进新叙事（占位，数字待实验）

> R1 = 6 SOTA baseline 在降质皮肤镜上 fine-tune 后再比诊断保持（把 E10 从 zero-shot 升级到公平比）。R3 = DP-Loss graft 到最强 baseline backbone，证 DP-Loss 可移植、差异归因 loss 非容量。脚本 `project/run_r1r3_finetune_eval.py` 已就绪（会话 46，smoke 过）。**数字待 HPC 跑出（🛑 传新代码拍板点未过）。**

### 5.1 R1（baseline fine-tune 公平比）接入点

- **解决的问题**：skeptic 🔴 公平性陷阱——现 E10 baseline 是 zero-shot，没见过降质皮肤镜，DP-Enhance 见过诊断监督。reviewer 会攻"不公平比较"。
- **预期结果形态**（数字待跑，先占位）：fine-tune 后 baseline 诊断保持 ΔAUC \todo{R1 核}，与 DP-Enhance 配对比较 ΔAUC \todo{R1 核} + CI \todo + McNemar \todo。
- **接叙事方式**：
  - **若 DP-Enhance 仍显著优**（预期）→ §7.5 E10 表加 "fine-tuned" 列，abstract/§1 那句升级为 "even after fine-tuning each baseline on degraded dermoscopy, DP-Enhance preserves diagnosis significantly better"。这是最强的 method-contribution 句式，CV reviewer 直接买。
  - **若打平**（诚实预案）→ 如实写 "after fine-tuning, the gap narrows to \todo; the advantage is attributable to the diagnosis-preserving objective rather than restoration capacity"（差异归因 loss，转而强调 R3 可移植）。**绝不暗示赢**。
- **正文位置**：§7.5（E10 表加列）+ §6.2（fine-tune 协议）+ App（ft 超参 + 收敛曲线）。

### 5.2 R3（DP-Loss graft 可移植）接入点

- **解决的问题**：证 DP-Loss 是"可插拔的诊断保持 loss"，差异归因 loss 设计而非 backbone 容量——把 C1 从"我们的网络好"升级为"这个 loss 谁用谁受益"，method 贡献更普适、更抗"incremental"。
- **预期结果形态**（待跑）：最强 baseline backbone + DP-Loss vs 同 backbone 无 DP-Loss，ΔAUC \todo{R3 核} + CI \todo + melanoma per-class 拆分 \todo。
- **接叙事方式**：
  - **若 graft 后诊断保持显著改善**（预期）→ 新增 §7（如 §7.5b "DP-Loss is transferable"）：一句 headline "grafting DP-Loss onto a strong baseline restoration backbone reproduces the diagnosis-preserving effect (ΔAUC \todo, CI \todo)", 把 C1 从"我们的方法"提升为"一个通用 loss"。
  - **per-class 诚实**：R3 评测脚本已含 melanoma per-class 拆分——若 graft 后 melanoma 仍净负，**如实写**（与 E5/v6 一致，归 §7.4/limitation），**不因补强而藏**。
- **正文位置**：§7.5b 新小节 + App（graft 实现 + per-class 表）。

### 5.3 接入红线（补强不越线）

- R1/R3 数字一律 \todo 占位，HPC 跑出 + verifier 核 csv 后才填，**禁凭脚本自报或印象填**。
- 补强**只建立 C1/C2 正向贡献**，绝不触碰任何诚实负结果：melanoma 净负、全局 triage 负、Thm2 局部界三铁律即便补强后仍如实留正文。
- 若 R1/R3 出现新负结果（如 graft 后 melanoma 仍 0）→ 如实进 §7.4/limitation，不藏（诚实墙优先于 headline）。

---

## 6. 诚实自查清单（abstract 每个正面措辞 → 正文数字支撑 + 防矛盾）

> 防 headline 三重矛盾复发（会话 44 揪出 fairness ECE vs triage "well-calibrated" 张力 / benign 74.5% vs 75.6% 分母不一致）。每个 abstract 正面措辞逐条核：① 正文哪个数字支撑 ② 有无与 §7.4（melanoma）/§7.7（triage 负）矛盾。

| abstract 正面措辞 | 正文数字支撑（位置 + 值）| 防矛盾核查 |
|---|---|---|
| "diagnosis-preserving enhancement" | E3 dAUC −0.012 / agree 0.9575（§7.2）| ✅ 与 §7.4 不矛盾：§7.2 是 moderate 窗口聚合保持，§7.4 是 severe+melanoma per-class 净负——**不同 regime**，须在 §7.4 明写"这是 moderate-window 保持之外的 severe/malignant 边界"，避免读者把 −0.012 当全域承诺。**abstract 必带 "within a moderate-degradation window" 限定词**（现有已带，保留）。|
| "Pinsker-optimal MI lower bound" | Lemma 3 β≈0.74、$\sqrt\epsilon$（§4.3 / App A1）| ✅ 措辞 "we derive"（R2），非 "we prove"。理论是 sketch 须在 limitation 写明（§8.4）。|
| "ablation confirms... +0.0205 ... p=2.3e-45" | E7（§7.3，1441301）| ✅ 锁定值，verifier 会话44 核过。|
| "against six restoration baselines... better on every one" | E10 6/6 ∈[−0.116,−0.066]（§7.5）| ⚠️ **zero-shot 限定**：现阶段须保 "在相同协议下" 口径；R1 补强前**不得**暗示"fine-tuned 后仍赢"。R1 落地后才升级措辞（§5.1）。|
| "first re-acquisition channel" | retake 梯度 0.055/0.651/0.889（§5.1/§7.8）| ✅ novelty claim 配 related work gap（AT-CXR/Geifman 只 defer/abstain）。是机制 novelty，**非性能赢**——abstract 不得让"first channel"读成"triage 赢"。|
| "local per-band conditional risk guarantee (Theorem 2)" | Thm2 [τ_enh,τ_high] 局部界（§5.2/App A2）| 🛑 **最高危**：abstract **必须**带 "local / per-band"，**绝不**让 Theorem 2 读成全局风险界。与 §7.7（0.818 vs 0.788 全局负）直接呼应，否则三重矛盾复发。现有 abstract 已带 "local, per-band"——保留。|
| "report, rather than hide... net-negative on melanoma (5.2% / 31%)" | E5 per-class + v6 null（§7.4）| ✅ 必带 per-class（5.2%）+ damage（31%），**禁**写聚合 0.737。"unchanged under mask-reweighted retrain" 对应 v6 null。|
| "global triage does not yet beat direct diagnosis (0.818 vs 0.788)" | §7.7 DCA + triage@20% | ✅ 必带 "does not yet beat" + "fixed-threshold" + "motivating learned thresholds"。**禁**任何"接近/可比/有潜力赢"的暗示性措辞（R3）。|

**自查结论（三重矛盾防线）**：
1. **"diagnosis-preserving" vs melanoma 净负** → 靠 "within a moderate-degradation window" 限定词隔开两 regime（abstract + §7.2 + §7.4 三处口径一致）。
2. **"Theorem 2 guarantee" vs 全局 triage 负** → 靠 "local / per-band" 限定 + §5.2 Thm2 降格三段 + §7.7 主动认负，三处呼应不打架。
3. **"first re-acquisition channel" vs 不能 claim 性能赢** → 定位"机制 novelty 非性能赢"，related work gap 撑 novelty，§7.7 认负撑诚实。
4. **分母一致性**（会话 45 揪过 benign 74.5% vs 75.6%）→ §7.4 melanoma 5.2% headline 两版（v5/v6 图）一致；benign 分母引用须对齐 v6 句口径（图 cref 已挪），**reframe 不重新引入分母错位**。

---

## 7. 落地优先级（主线审过后的动手顺序，本蓝图不动 tex）

1. **零算力 emphasis 改写**（可先做，不依赖补强）：abstract 首句 method/system 腔（§4.1）+ §1.2 加 method gap 句 + §1.4 C1 bullet 推满（§4.2）。C3 bullet / 负结果段**一字不改**。
2. **method name 脱敏定稿**（R4）：DP-Enhance / 5-head IQA / closed-loop quality-triage 统一占位名，grep 清 Q-VIB/VisiSkin/VisiScore/VisiEnhance。
3. **C0 降权**：§3 决策面从"contribution"措辞改"motivation"措辞（引导句而非 bullet）。
4. **R1/R3 补强落地后**（🛑 HPC 传码拍板 + verifier 核数后）：按 §5 升级 vs-baseline 措辞 + 加 §7.5b transferable 小节，per-class 诚实保留。
5. **LNCS 14 页重排**（ACCV）或等 venue 定（WACV 8 页双栏）——版式工作，与 reframe 正交。

---

## 8. 蓝图自检：诚实安全线守住确认

- ✅ 只改 emphasis（headline = C1+C2，C0 降动机，C3 降 analysis/limitation），**未改任何 truth value**。
- ✅ 三铁律负结果（melanoma 净负 −81 / 全局 triage 0.818 vs 0.788 / Thm2 局部界）全部如实留正文，带数字带 CI，对照表 #13/#15/#16 明标 LIMITATION/ANALYSIS。
- ✅ 数字零自创——全部 = STORY/ACCEPTANCE 锁定值（E7/E3/E10/E5/E6/C0/triage），R1/R3 待跑值一律 \todo 占位。
- ✅ R10 守住——不搬 BMVC 表/数/图（决策面用 ICLR 干净 c0_decision_surface.csv，非 BMVC tab:perdeg）。
- ✅ R2/R11/R3 守住——"we derive" 非 "we prove"；Thm2 局部界非全局；triage "make no claim globally"。
- ✅ 防三重矛盾——abstract 每个正面措辞配限定词（moderate-window / local-per-band / first-channel-非性能赢），§6 逐条核与 §7.4/§7.7 不打架。
```
