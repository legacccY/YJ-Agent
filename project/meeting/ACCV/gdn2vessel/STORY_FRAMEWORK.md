# gdn2vessel 故事框架（反跑偏主文档）

**适用范围**：任何 Claude / Sonnet / Opus 会话写 gdn2vessel 内容（tex / 正文 / rebuttal / 实验设计 claim）前必读。
**最后更新**：2026-06-22（路B重定位 — headline 主轴从「delta-rule 机制特异」改为「可微 Frangi 门调制记忆」；用户拍板放行）

> ⚠️⚠️ **路B重定位（2026-06-22，立项锚证伪后改向，用户拍板）**：原 headline「GDN-2 delta-rule 关联记忆机制特异性做空间断点续连 / 同根 re-ID」被 MQAR 探针（job 1482972）+ 理论审计证伪——**唯一可比收敛点 n=64 lr=1e-3 上 gdn2=0.999 ≈ gla=0.992，delta 不比普通有状态记忆（GLA）强**；叠加 §4 目标函数错配（re-ID 头零梯度激励）使「记忆做 re-ID」机制特异 claim 结构性塌缩。**新 headline 主轴 = 可微 Frangi 门（input-derived vesselness）当外部门调制记忆模块做端到端血管续连**——记忆是载体，门是创新使能机制。delta-rule 不再承载机制特异 claim。完整战略与证伪链见 `PROJECT_LOG.md` Entry 31 + [`reference/THEORY_FOUNDATION.md`](reference/THEORY_FOUNDATION.md) §2.2/§4。
>
> ⚠️ **理论地基（2026-06-21~22）**：定 headline / 写 §1/§3 前先读 [`reference/THEORY_FOUNDATION.md`](reference/THEORY_FOUNDATION.md)（理论主文档）+ [`reference/NOVELTY_DERIVATION_AUDIT.md`](reference/NOVELTY_DERIVATION_AUDIT.md) §3.4（Frangi 门正交解耦轴措辞），再回本文。两者冲突以 THEORY_FOUNDATION 为准。

> 如果用户描述的任务与本文件冲突 → **停下来澄清**，不要按用户描述硬干（用户可能忘了已有约束）。铁律：计划外岔路先问，不盲跑。

---

## ⛔ 跑偏定义（命中任一条立即停手）

1. **把 headline 从「可微 Frangi 门（input-derived）调制记忆做端到端血管续连」漂走**（如改成纯「血管分割涨点」、「换了个 SSM backbone」、或退回已证伪的「delta-rule 机制特异做 re-ID」旧轴）。
2. **把 delta-rule 机制特异性重新写成 headline 卖点**（已被 MQAR delta≈GLA + 目标函数错配证伪；记忆只作**载体**，机制特异 claim 禁复活）。
3. **把 re-ID 重新升回独立机制 claim**（已降为续连质量的描述性副产指标 reid_rate，仅报告不卖机制特异）。
4. **把 scan / reorder 写成核心贡献**（撞 Serp-Mamba/SWinMamba 蛇形；只能定性「标准工程实现」）。
5. **vesselness 先验用 GT / 分割结果**（必须 input-derived 可微 Frangi，破鸡生蛋 + 防评估泄漏）。
6. **断点续连 benchmark 测试集拼入训练样本 / 记忆 key 用 GT 监督**（in-sample 伪迹，红线）。
7. **凭印象写数字**而非 Bash/Grep 核 csv。
8. **改动 §1-§7 章节弧顺序**（见下方故事弧）。
9. **写绝对化措辞**（"universal" / "always" / "we prove" / "theorem"）或 **related work 不逐条划界 vessel reconnection 成熟工作（CorSegRec / GLCP MICCAI2025 Oral）+ 合成断点 benchmark 先例（PTR MICCAI23）+ GDKVM**。
10. **novelty 过宽 claim**（禁 claim「首个 in-model 连通性」「首个断点 benchmark」；精确收窄到「in-model 端到端 + 可微 Frangi 当外部门调制记忆」，见下方 novelty 收窄段）。

---

## 🎯 核心 Claim（论文一切内容服务于此 — 2026-06-22 路B重定位后）

### Claim 1（核心机制 = headline 主轴）：可微 Frangi 门（input-derived）调制记忆，做端到端血管续连

> 我们用**可微 Frangi 层的输出（input-derived vesselness）**当**外部门信号调制记忆模块**：血管延续证据处放大写入/抑制遗忘，把断开的同一条血管在特征空间续上；整条续连在**模型内端到端**完成，门控**绝不来自 GT / 分割结果**。**门是创新使能机制，记忆是承载它的载体。**
> **为什么 Frangi 门是 novelty 主轴**（researcher 2026-06-22 核实，唯一未撞车的强 novelty）：可微 Frangi 当外部门调制别的记忆模块**无先例**——区别于 Frangi-Net（arXiv 1711.03345「学 Frangi 权重做分割」）和 VP-UNet（arXiv 2508.00235「Frangi 固定不可微」）。
> **必须写**：续连是 **end-to-end 模型内机制**（区别于拓扑损失 clDice / 后处理图算法 / learned post-processing 如 arXiv 2404.10506 / 需显式起点的 tracing 如 VGN 1806.02279 / Trexplorer MICCAI2024）。
> **绝对禁止**："universal reconnection" / "always reconnects"。续连能力随断点 severity / 序列长度衰减，必须如实呈现衰减曲线。
> **承重前提（命门，未 PASS 前 headline 不定稿）**：可微 Frangi 门（gate-on）须在拓扑轴（clDice 主判据，ε_β0/Betti 交叉印证）**显著赢**无门（gate-off）——kill-criteria 预登记见 `ACCEPTANCE_CRITERIA.md`「路B 最小验证 gate」块。FAIL → benchmark-only / workshop 诚实降级，停下报用户。

#### 🧱 记忆是载体，不是机制特异卖点（2026-06-22 路B重定位铁律，写 §1/§3 必守）

旧 headline 押在「GDN-2 的 delta-rule **机制特异性**（A2>A1' 干扰消解 / A2>GLA）」上——**此轴已证伪，不得复活**：
- **MQAR 探针实证**（job 1482972，verifier 核 csv）：唯一可比收敛点 n=64 lr=1e-3 上 **gdn2=0.999 ≈ gla=0.992**，delta 不比普通有状态记忆（GLA）强。
- **目标函数错配**（THEORY §4，独立扎实）：分割主 loss + 三道 detach 隔离 re-ID 头，没有任何 loss 优化「同根身份在 memory 状态空间可分」，故 A2≈A1' 是结构性必然。
- **铁律**：§1/§3 **不得**把 delta-rule 干扰消解 / 容量优势 / 「A2>A1'」「A2>GLA」写成动机或卖点。记忆模块只作**承载 Frangi 门调制信号的载体**；增益来源由下方「记忆类型无关」消融归因到**门**，非记忆类型。

#### 🧪 记忆类型无关消融（2026-06-22 新增 — 把 delta≈GLA 负结果转正向证据）

> Frangi 门 × {GDN-2, GLA, ConvGRU} 三种记忆载体上**都涨**（拓扑轴均较各自 gate-off 提升）→ 证**增益来自可微 Frangi 门，非某一种记忆机制**。
> **正向叙事转化**：MQAR 上「delta≈GLA」原是路A的致命负结果；在路B里它**正好支撑**「门的增益记忆类型无关」这一更强、更通用的 claim。论文如实陈述：记忆机制特异性在本任务不成立，但这不削弱门的贡献，反而说明门是模型无关的即插即用使能机制。
> **绝对禁止**：把该消融读成「delta-rule 仍有微弱优势」去复活机制特异 claim；选择性只报 GDN-2 涨的那一组。

### Claim 2（描述性副产，非独立机制 claim）：续连质量伴随同根一致性改善

> 续连质量的一个描述性侧写：报告 **reid_rate**（同根匹配率，借 MOT IDF1 逻辑：正确同根匹配 / 全部 gap），**仅作续连质量的辅助刻画指标报告，不卖「记忆做 re-ID」的机制特异性**。
> **降级理由（2026-06-22）**：§4 目标函数错配证明分割主 loss 对「memory 状态绑同根身份」零梯度激励，「记忆内生做 re-ID」的机制 claim 结构性塌缩（A2≈A1' 是数学必然）。故删除原 re-ID 头机制 headline，re-ID 从独立第二卖点**降为续连质量的副产描述指标**。
> **保留价值**：reid_rate 作为「认出≠填上」的可解释侧写仍有报告价值（与 ε_β0/SR 互补），但**不附机制归因**、**不做可归因消融的承重判据**。
> **绝对禁止**：把 reid_rate 算在含训练样本的集上；把 reid_rate 重新升回独立机制 claim；为它复活 A2>A1' 之类的机制特异性论证。

### Claim 3（机制核心贡献 = 可微 Frangi 解耦门）：正交解耦轴的门调制

> 我们设计一个**可微 Frangi 解耦门**调制记忆更新：解耦的是「**全局遗忘率 α（各向同性衰减）vs 写入强度 β（写入门）**」两条轴；门控调制信号来自**可微 Frangi 层输出（input-derived vesselness）**，绝不用分割结果/GT。**这是路B的核心机制贡献。**
> **正交解耦轴措辞（2026-06-22，按 NOVELTY §3.4 / THEORY §3 校准，删旧「双门近似」）**：我们解耦的「全局遗忘 α vs 写入强度 β」与 GDN-2 原版的「**定向擦除（b_t⊙k_t，沿 kkᵀ 选择性）vs 定向写入（w_t⊙v_t）**」是**正交的不同轴**，**不是** GDN-2 双门的劣化近似。必须**主动声明**三点：① 我们是各向同性全局衰减，非定向擦除；② β 仍同时进擦除项与写入项（原版耦合未碰）；③ **不 claim 与 NVlabs gdn2_ops 真双门等价或更细——这是对血管用例（延续处压全局遗忘保住主导身份）合理但更粗的近似**。
> **kernel 外调制（FLA 单-β 事实）**：FLA 通用 gated-delta-rule kernel 是单-β，我们的解耦门是 **kernel 外调制层**（write→β、erase→g 的加性 decay 修正），**不重写 kernel**（R4：贡献是门机制非 kernel 工程）。
> **可微 Frangi 数值坑（写实现必处理）**：可微 Hessian 在近重复特征值处梯度爆炸（arXiv 2104.03821），背景均匀区 λ₁,λ₂≈0 需 Taylor 平滑 / pseudo-inverse 防爆。
> **绝对禁止**："we prove uniqueness" / 把 kernel 外调制写成「重写了 kernel 做真双门」/ 把「正交解耦轴」回退成「双门近似」/ claim 与真双门等价。

### 🔭 Novelty 收窄（2026-06-22 — 对抗撞车，related work 必逐条划界）

vessel reconnection 已是成熟子领域，合成断点 benchmark 已有先例 —— **novelty 必精确收窄，related work 逐条点名划界，否则秒拒**：
- **vessel reconnection 成熟**：CorSegRec（自造续连指标）、**GLCP（MICCAI2025 Oral，局部断点 + 全局连通，必对比、拓扑要赢它）** 已做连通性。→ **禁 claim「首个 in-model 连通性」**。
- **合成断点 benchmark 已被占**：PTR（MICCAI2023，肺 3D）已有合成断点协议。→ **禁 claim「首个断点 benchmark」**。
- **tracing 家族**：VGN（1806.02279）/ Trexplorer（MICCAI2024）/ TopoVST（2603.14909）已在模型内做连通性，但需显式起点。
- **GDKVM**（ICCV2025）：跨帧时序门控 delta KV 记忆。
- **我们的精确差异（唯一收窄到这一句）**：**in-model 端到端 + 可微 Frangi（input-derived）当外部门调制记忆模块** 做 2D 眼底血管续连。这是 researcher 核实的唯一未撞车强 novelty。

### 🩹 诚实负结果（写进 STORY 与论文，方法学诚实点，不藏）

> 论文须主动呈现两条不利但诚实的结果（主动暴露 = 严谨，藏 = 被审稿抓）：
> ① **GDN-2 在视觉/分割任务首次应用**（NVlabs repo 仅 LM/long-context），本身是探索性贡献；
> ② **delta-rule 机制在 2D 血管不具特异性**——MQAR 探针预登记证伪（n=64 lr1e-3 gdn2≈gla），目标函数错配使「记忆内生做 re-ID」不成立。
> 这两条**不削弱** Claim 1/3（门是模型无关使能机制，由记忆类型无关消融支撑），反而是叙事的诚实承重点。**禁改判定方向去掩盖。**

### CV 方法贡献定位（纯 CV 会议必读）

> ACCV/CVPR/ICCV 是 CV 方法会议：贡献必须落在**新机制/新 benchmark**（可微 Frangi 门调制记忆做端到端续连 + 断点续连 benchmark + 续连指标），医学数据集是 **validation 场景**，不是靠临床故事撑录用。

---

## 📐 故事弧（章节顺序锁定）

```
§1 Intro
├── §1.1 问题：细长血管/管状结构在遮挡/低对比处断点，连通性是临床关键
├── §1.2 现有路径局限：拓扑损失(clDice)/后处理图算法/蛇形扫描/tracing 都不在模型内用 input-derived 门调制记忆做续连
├── §1.3 ★ Hook：可微 Frangi 门（input-derived vesselness）调制记忆做端到端血管续连（门=使能机制，记忆=载体）★
└── §1.4 贡献列点（可微 Frangi 解耦门 / 端到端续连机制 / 断点续连 benchmark / 记忆类型无关消融 / 全谱实验）

§2 Related Work（必逐条划界，见 novelty 收窄段）
├── 血管/管状分割（CNN 经典 + SSM/Mamba 家族）
├── 拓扑/连通性方法（clDice/cbDice/Skeleton Recall/Betti/DSCNet）+ ★ vessel reconnection 成熟工作硬区分：CorSegRec / GLCP MICCAI2025 Oral ★
├── tracing / 合成断点 benchmark 先例（VGN/Trexplorer 需起点；PTR MICCAI23 已占断点 benchmark）
├── 线性注意力/记忆模块（★ GDKVM 硬区分：时序 vs 空间；记忆作载体，不卖 delta 机制特异 ★）
└── 可微 vesselness（Frangi-Net / VP-UNet 固定 Frangi 区分 — Frangi 当可微外部门无先例）

§3 Method
├── §3.1 总体架构（CNN U-Net + 记忆模块插 encoder 深层 + 可微 Frangi 门调制通路）
├── §3.2 记忆模块作续连载体（模型无关，可换 GDN-2/GLA/ConvGRU）
├── §3.3 可微 Frangi 解耦门（★ 核心机制：正交解耦轴 α-decay vs β-write，input-derived ★）
├── §3.4 续连质量副产刻画（reid_rate，描述性指标，无机制归因）
└── §3.5 2D 化：标准 reorder 多向合并（定性工程，不当贡献）

§4 Disconnection-Reconnection Benchmark（杀手锏）
├── §4.1 合成断点协议（对齐 creatis plug-and-play，半径分布+gap 参数；与 PTR 划界）
├── §4.2 续连指标：ε_β0 + 自定义 SR(写公式,novel metric) + 标准 APLS/Betti-err 交叉印证 + reid_rate 副产刻画(借 MOT IDF1,先例 2107.09049)
└── §4.3 防泄漏设计（测试集 held-out，记忆/Frangi 门不碰 GT）

§5 Experiments
├── §5.1 Setup（数据集 ≥10 / baseline ≥12 / 三轴指标 / seed≥3）
├── §5.2 主实验（DRIVE/CHASE/FIVES/STARE，三轴表 + 必对比 GLCP）
├── §5.3 断点续连 benchmark 结果（★ headline 铁证：gate-on vs gate-off 拓扑轴 ★）
├── §5.4 消融（≥8 组，★ Frangi 门 on/off + 记忆类型无关(GDN-2/GLA/ConvGRU)/序列长度/多向…★）
├── §5.5 泛化/跨域/跨器官（冠脉/OCTA/跨域）
└── §5.6 可解释性（Frangi 门调制 + 续连可视化）

§6 Discussion + Limitations（续连随 severity/序列衰减；记忆机制特异性在 2D 血管不成立=诚实负结果；synthetic 断点 vs 真实病理断点）
§7 Conclusion
```

---

## 🔒 锁定数字表（实验后由 verifier 核 csv 回填，此刻一律 TODO，严禁臆造）

### 主实验三轴（DRIVE/CHASE/FIVES/STARE）

| 数据集 | 方法 | Dice | clDice | Betti β₀/β₁ err | ε_β0 | re-ID 率 |
|---|---|---|---|---|---|---|
| DRIVE | Ours | TODO | TODO | TODO | TODO | TODO |
| ... | ... | TODO | TODO | TODO | TODO | TODO |

### SOTA 天花板（researcher×4 核源 2026-06-20，作为「要赢多少」的参照，非我们的数字。全表来源/陷阱见 [`reference/SOTA_NUMBERS.md`](reference/SOTA_NUMBERS.md)）

| 数据集 | 当前最高 Dice | 方法（来源） | clDice 报告者 |
|---|---|---|---|
| DRIVE | ~0.84 | EFDG-UNet 0.8412 / HM-Mamba 0.8327（Mamba 家族最强同台） / VFGS-Net 0.8323✓ | HREFNet 0.8240 |
| CHASE_DB1 | ~0.85 | EFDG-UNet 0.8469 / HM-Mamba 0.8197✓ | HREFNet 0.8293 |
| STARE | ~0.85 | FSG-Net 0.8510✓（**上修，原 83.21 偏低**）/ MDFI-Net 0.8581(待核split) | FA-Net 0.8763 |
| HRF | ~0.86 | VFGS-Net 0.8560 / FSG-Net 0.8157 | — |
| FIVES | ~0.918 | PASC-Net 0.9183✓ | PASC-Net 0.9174 |

> 基调：**裸 Dice 已饱和**（各集 0.84–0.92），胜负压拓扑(clDice/Betti)/续连(ε_β0/SR/re-ID)轴；裸 Dice 持平不输即可，禁调参作弊凑赢。
> **战略空白**：clDice/拓扑指标报告者极少（仅 HREFNet/PASC-Net/FA-Net/TFFM），主流强作 FSG-Net/HM-Mamba/EFDG-UNet 全不报 clDice，续连/re-ID 轴更无人占——这是我们的取胜窗口。
> ⚠️ **两簇协议不可比**：DRIVE/STARE 报告值分主流簇(~0.83–0.85)+高簇(RV-GAN 0.8690/MM-UNet 0.8959/0.9177，协议差异非真实力)。**天花板只用主流簇，高簇引用必标"协议不同"**（RV-GAN 由"禁引"修正为：指标确是 Dice，但高簇协议不可比）。
> ⚠️ creatis 协议两修正（见 reference）：原文**无 boundary blur、无 SR 指标**（只 DSC/ASSD/ε_β0 三指标，无 AUC）。
> ✅ **SR 拍板（2026-06-20 用户拍「两者都上」）**：主指标 = **自定义 SR 写公式**（SR=正确续连断裂对/GT 全部断裂对，标 novel metric）+ **附标准 APLS/Betti-err 交叉印证**（防审稿质疑自定义指标自卖自夸）。re-ID 借 MOT IDF1 有先例（Deep Open Snake Tracker arXiv 2107.09049）合法锚点。

---

## 🛡️ 防御写法硬规则（违反即跑偏）

| 编号 | 严禁 | 必须 |
|---|---|---|
| R1 | "universal reconnection" / "always" | "reconnection degrades with break severity / sequence length"，附衰减曲线 |
| R2 | "we prove" / "theorem" / "uniqueness" | "we design / motivated by" |
| R3 | related work 不提或不区分 GDKVM | 固定模板："Unlike GDKVM [ICCV25] which uses gated delta KV memory across echo video frames (temporal), we operate within a single image (spatial); the memory module is a carrier for our input-derived differentiable-Frangi gate, not a claim of mechanism specificity." |
| R3b（2026-06-22 新增） | related work 不逐条划界 vessel reconnection 成熟工作 / 断点 benchmark 先例 | 必逐条点名：CorSegRec / **GLCP（MICCAI2025 Oral，必对比、拓扑要赢）** / PTR（MICCAI23 已占断点 benchmark）/ VGN/Trexplorer（需起点 tracing）。**禁 claim「首个 in-model 连通性 / 首个断点 benchmark」** |
| R4 | 把 scan/reorder / kernel 工程写成贡献 | "we adopt a standard reorder; the contribution is the differentiable-Frangi gate, not the scan or the kernel" |
| R5（分层辖域，2026-06-22 路B修订） | 把分割主干/记忆/Frangi 门写成用 GT | **声明**：分割主干 + 记忆 keys + Frangi 门 = input-derived，**never GT topology**（Claim 1 续连 GT-free）；评估用 GT 当裁判 = allowed。reid_rate 作描述性指标报告，不涉机制监督。 |
| R6（机制特异禁复活，2026-06-22 新增） | 把 delta-rule 干扰消解 / 「A2>A1'」/「A2>GLA」机制特异写成动机或卖点；把 reid_rate 升回机制 claim | 记忆=载体；增益由「记忆类型无关消融」归因到 Frangi 门。机制特异性在 2D 血管不成立=诚实负结果如实写 |
| R7（正交解耦轴，2026-06-22 新增） | §3.3 写「双门近似」/ claim 与 GDN-2 真双门等价或更细 | 写「正交解耦轴（全局遗忘 α vs 写入强度 β），非 GDN-2 定向擦除/写入」+ 三条主动声明（各向同性、β 残余耦合、更粗近似不 claim 等价） |
| R8 | bare numbers | 续连/拓扑数字附统计（bootstrap CI 或显著性），Dice/clDice 附 seed std |
| R9 | 纯临床故事撑录用 | CV 方法贡献先行，医学集是 validation |

---

## 📊 novelty 真实性（2026-06-22 路B重定位后，researcher 核实收窄）

- **★ 主轴 novelty = 可微 Frangi（input-derived）当外部门调制记忆模块 = 无先例**（区别 Frangi-Net「学权重做分割」/ VP-UNet「固定不可微」）。researcher 2026-06-22 核实为唯一未撞车的强 novelty。
- GDN-2 在视觉/分割**零应用**（NVlabs repo 仅 LM/long-context）→ 视觉首用，探索性贡献（但记忆机制特异性不卖，见诚实负结果）。
- **已撞车需划界（禁 claim 首个）**：vessel reconnection 成熟（CorSegRec / GLCP MICCAI2025 Oral）；合成断点 benchmark 已被 PTR（MICCAI23 肺 3D）占。我们的精确差异收窄到「in-model 端到端 + 可微 Frangi 当外部门调制记忆」。
- **已证伪不得复活**：单图内关联记忆「delta-rule 机制特异做 re-ID」= MQAR delta≈GLA + 目标函数错配双重证伪（THEORY §2.2/§4）。reid_rate 仅作描述性副产指标。

---

## 🚨 会话开始前 checklist

1. ✅ 读本文件一遍
2. ✅ 读 `PLAN/MASTER_PLAN.md` + 当前 `PHASE_x.md`
3. ✅ 读 `ACCEPTANCE_CRITERIA.md` 查当前任务硬阈值
4. ✅ 读 `PROJECT_LOG.md` 最新 entry
5. ✅ 写数字前先 Bash/Grep 核数据源 csv
