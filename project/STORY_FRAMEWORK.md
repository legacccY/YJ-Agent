# 唯一论文故事框架（反跑偏主文档）

**论文**：D+A 系统论文 —— Safe diagnosis-preserving enhancement of degraded dermoscopy, and when to defer instead
**会场**：MICCAI 2027（~2027-02）首选 / TMLR（滚动、无 deadline、明文不要 SOTA）备
**最后更新**：2026-06-17（会话 41，立项级重构后重写）
**适用范围**：任何 Claude / Sonnet / Opus 会话写本论文内容前必读
**权威来源**：本文件以 `project/ICLR_重构计划_拆两篇_2026-06-17.md`（下称「计划文档」）为最高准绳；冲突处以计划文档 §2 为准。

> ⚠️ **本文件已整篇重写**。旧版以「Q-VIB 当 headline、三论点冲 SOTA、78-80% 命中率 25-lever」为框架，**已全部作废**。旧的中心 claim「Q-VIB 是更强的诊断方法」经三轮独立核查判死（Q-VIB ≈ Std VIB，无差异化，r1/r2/r3 三个 FAIL csv 钉死），Q-VIB 在本论文中**降级为脚注**。本框架换成建设式 headline + 四论点 C0-C3。

---

## ⛔ 跑偏定义（命中下列任何一条立即停止操作，报告主线）

1. **把 headline 写成否定式**（如「不能盲目增强」「passive enhancement is unsafe」）—— 弱、且 Blau & Michaeli (CVPR 2018) / Cohen et al. (MICCAI 2018) 早说过。必须写成建设式：「how to enhance *safely* —— a mutual-information lower bound for diagnosis preservation, plus a query-for-retake triage shell」。
2. **claim Q-VIB 有方法增益 / 比 Std VIB 强 / 是更好的诊断器**。三个 FAIL csv（`results/qvib_minverify/r1,r2,r3`）钉死，永久放弃。triage 只需现成不确定性信号（Std VIB 即可），不靠 Q-VIB。
3. **claim「agent 整体风险 ≤ Direct」/「triage 全局优于直接诊断」**。自家 r4 实证 Direct B3 sens=0.818 > agent=0.788（会与 §7.7 DCA 自相矛盾）。Thm2 必须降格为「区间局部条件界 + 全局诚实负结果」。
4. **凭印象写数字** 而非从 `results/**.csv` + bootstrap CI 核算（数字入 tex 前过 verifier）。复活 0.707 当 headline 数（幽灵数，旁支管线误抄，原始 csv 不可考，弃用）。
5. **从 BMVC 提交版搬表 / 搬图 / 搬数字进本论文**。被 BMVC 占的四维度（跨域 ρ / ImageNet-C 18 腐蚀 / 5 backbone universality / DCA-triage）一律只 cite 不搬，且 BMVC 录用公开后（notification ~2026-08）才能引。
6. **使用扩散 / 生成模型做皮肤镜增强**（DiffBIR / SD-Turbo / Stable Diffusion 等，伪影发明色素网络/血管结构 = 医学安全红线）。
7. **删除理论骨架定理**（Prop3 / Lemma3 / Thm2 主文，Prop1/Lemma1/Thm1/Prop2 退 supp 当框架）。
8. **把 query-for-retake 简化成 abstain/defer**。retake = 反馈要求重新采集（采集闭环），是独家钩子；defer-to-clinician（AT-CXR 等）人人会做，不是新意。
9. **改动 §1-§9 章节顺序**（已按新 headline 锁定，见下方故事弧）。
10. **把诚实负结果（C3 边界 / triage 实证负 / E5 melanoma 救援净负）写成正面卖点或藏起来**。它们是 query-for-retake 闸门的动机，诚实陈述才是本论文的可信度来源。

---

## 🎯 四条核心论点（按强度排，论文一切内容服务于此）

> 取代旧三论点（Q-VIB / VisiEnhance / Closed-Loop Agent）。新论点强度递增：C0 动机 → C1 最硬 → C2 独家钩子 → C3 诚实边界。

### C0 — 动机章：可靠性 × 可恢复性决策面（BMVC-free，会话 41 reframe）

> **claim**：在降质皮肤镜下，本文刻画一张 **「可靠性 × 可恢复性」决策面** —— 沿 5 维退化（模糊 / 亮度 / 完整度 / 色温 / 对比）× severity 的二维网格，**主轴领以诊断 AUC**，叠加**可恢复性第二轴**（每个退化点上「增强能否把诊断救回」）。这是「为什么需要质量感知 triage」的实证动机，并把 C0 直接桥到 C1（增强）与 C3（边界）。
>
> **为何 reframe（计划文档 §3 拍板 A）**：第一轮审计误判 BMVC supp 的 `table_perdeg_qcts`（`itb_supp.tex` L615 确有 \input）为孤儿表；二次核实推翻 —— BMVC 已占「**逐维 ECE + QCTS 视角**」（4 维 blur/color/brightness/contrast，**无 completeness**，仅 Std VIB±QCTS，无 severity 扫描）。故 C0 改走 BMVC 没碰的角度：
> - **主轴用诊断 AUC**（不用 ECE —— 逐维 ECE 是 BMVC 占的角度，用 AUC 避撞）。
> - **逐维 × severity 二维网格**（BMVC 单档 / 聚合）。
> - **completeness 第 5 维**（BMVC 的逐维表无此维）。
> - **可恢复性轴**：用 C3 已有的 E5 救援净负 / E6 severe 伤诊断数据叠上去 —— 增强 BMVC **一字没有**，天然 BMVC-free。
> - **次要观察（可选）**：多方法 UQ 不差异化（BMVC 逐维只 1 方法 Std VIB，可深化）。作动机章次要观察，或留给负结果兜底短文（ICBINB / ML4H Findings）。

**绝对禁止**：① 把 C0 单列成「我们提出退化曲面」的 **contribution**（C0 是动机章，§1.4 四 bullet 由 C1/C2/C3 扛）；② 用逐维 **ECE** 当主轴（撞 BMVC `tab:perdeg`）；③ 把 completeness 写成「不可逆 / irreversible」绝对化措辞（违 R1）。
**必须写**："we chart a reliability × recoverability decision surface (per-dimension × per-severity, AUC-led, with a recoverability axis from enhancement), which BMVC's per-dimension ECE/QCTS view (`tab:perdeg`, cited not reused) does not cover, motivating quality-aware triage." completeness 写 "partially recoverable" 而非 "irreversible"。

### C1 — 最硬：DP-Loss 让增强在 moderate 退化窗口不损诊断（BMVC-free）

> **claim**：诊断保持损失（DP-Loss，feature-level diagnosis-preserving KL）在 moderate 退化窗口内让增强**不损诊断**，有实证 + 理论双支撑。
>
> - **实证 E7（Lemma 3 的证据）**：feature-level DP（对齐 B3 1536×7×7 诊断特征）使 ΔAUC_enh(S2−S1) **+0.0205 CI[+0.005,+0.035] 显著>0**、ΔKL **−0.148 CI[−0.173,−0.124] 显著<0**、**McNemar p=2.3e-45** → DP 组诊断保持显著优于无 DP（run_id 1441301，源 `results/stage2_diag_paired_v5.csv`）。
> - **实证 E3（诊断保持双 PASS）**：dAUC **−0.0120**、分类一致率 **0.9575**、McNemar(enh-vs-ref) p=0.573（enh≈ref）（run_id 1441301）。
> - **理论 Lemma 3**：$\mathcal{L}_{\text{DP}} \leq \epsilon \implies I(Z_{\text{enh}};Y) \geq I(Z_{\text{ref}};Y) - \beta\sqrt{\epsilon}$（互信息下界保持，$\beta = M L_{q_\theta}/\sqrt{2} \approx 0.74$ binary，$\sqrt{\epsilon}$ Pinsker-optimal）。源 `plans/Prop3_Lemma3_visienhance_theory.md` §2。
> - **理论 Prop 3**：$\bar{q}(T_\omega(x,q)) > \bar{q}(x) \implies \mathbb{E}[H(\hat{p}_{T_\omega(x,q)})] \leq \mathbb{E}[H(\hat{p}_x)]$。**注意**：E4/E4Q 实证 FAIL（增强后熵不降，方向相反），Prop3 改由 **E7（Lemma 3 MI 下界实证）+ PSNR≥30 非空性条件**承载，E4 不入 paper。

**绝对禁止**：用 GAN/扩散骨干；把 enhancement 写成 super-resolution；把 FiLM 卖成 PSNR 增益（E8 实测 FiLM 对 PSNR 中性 32.74 vs no-FiLM 33.06）。
**必须写**："deterministic restoration with quality-conditional FiLM modulation"，FiLM 卖点定位在**诊断保真**（E8: dAUC −0.033 vs −0.042、一致率 0.90 vs 0.87、KL 0.24 vs 0.35，均 with-FiLM 更好），绝不写「FiLM 提升复原质量」。

### C2 — 独家钩子：query-for-retake 通道

> **claim**：当图像质量不足以安全增强时，agent **反馈要求重新采集**（query-for-retake），而非只 abstain / defer-to-clinician。
>
> - **gap**：整个 agent / selective-prediction / deferral 文献**无人做采集闭环**。AT-CXR 等只 defer-to-clinician；selective prediction（Geifman & El-Yaniv, NeurIPS 2017）只 abstain；teledermatology IQA 引导重拍（PMC10468541）有临床动机但无 risk-bounded 闭环。本文把「质量分级 → 增强 OR 追问重采 → 诊断」串成带局部条件界的闭环。
> - **实现**：query-for-retake agent（Qwen3-4B ReAct + rule fallback），4 通道决策（direct diagnosis / cautioned diagnosis / enhance-then-diagnose / query-for-retake），质量分级阈值路由。

**绝对禁止**：写 "agent generates/produces diagnosis"（agent 不诊断，它决策**何时**诊断/增强/追问）；把 retake 等同 defer。
**必须写**："the agent decides among four channels based on quality-stratified thresholds; the query-for-retake channel requests re-acquisition rather than merely abstaining."

### C3 — 诚实边界：增强不是万能 → query-for-retake 闸门的最硬动机

> **claim**：增强在 severe 退化与黑色素瘤上**伤诊断**，这是 query-for-retake 闸门存在的最硬理由，**不是项目缺陷**。
>
> - **E6 severe 段**：极低质段增强显著拉低诊断，dAUC **−0.0559 CI[−0.085,−0.028] 排除 0**、dflip 0.46（run_id 1441321，源 `results/e6_severe.csv`）→ severe 图该 query-for-retake，agent 设计本就不增强 severe。
> - **E5 melanoma 救援净负（最硬证据）**：聚合 SalvageRate 0.737「达标」**全由良性撑**（良性 salvage 75.6% 1809/2392）；**黑色素瘤 salvage 仅 5.2%（4/77）、damage 31%** → 救 4 毁 81 **净 −81**（源 `results/qvib_minverify/` 同批的 `e5_salvage_persample.csv`，会话 22 per-class 拆案）。
> - **v6 mask-L1 null（诚实负结果）**：mask-weighted L1 重训（4× 病灶区权重）melanoma salvage **5.2%→5.2% 纹丝不动** → 重构损失加权救不了恶性救援缺口，failure mode 是 per-pixel L1 够不着诊断决策边界（源 `results/e5_salvage_v6_persample.csv`）。

**绝对禁止**：把 E5 聚合 SalvageRate 0.737 当达标指标写 paper（reviewer 拆 per-class 即崩 + 伦理误导）。
**必须写**：E5 = "benign-dominated salvage with net-negative melanoma rescue → the hardest evidence for the query-for-retake gate as a genuine safety mechanism."

---

## 🦶 Q-VIB 处置（降级为脚注，不复活）

- Q-VIB（Quality-Conditioned Variational Information Bottleneck）从论文同名核心**降级为脚注 / 一句相关工作**。
- **不得** claim 任何方法增益、SOTA、比 Std VIB 强、是更好诊断器。三个 FAIL csv（`results/qvib_minverify/r1,r2,r3`）钉死。
- triage 通道所需的不确定性信号用**现成的 Std VIB / 任意 per-input uncertainty 即可**，不依赖 Q-VIB。
- 5 定理里 Q-VIB 相关的（Prop1 ELBO / Lemma1 σ² 单调 / Thm1 attention drift / Prop2 entropy 单调）退 supp 当**理论框架**，不在主文当卖点。

---

## 📐 理论骨架处置（5 定理）

| 定理 | 归属 | 处置 |
|---|---|---|
| **Prop 3**（增强降熵充分条件）| 主文 §4 | 增强+决策这条腿；E4 实证不支持降熵，改由 E7+非空性承载 |
| **Lemma 3**（DP-Loss → 互信息下界）| 主文 §4 | C1 最硬理论，E7 实证 |
| **Thm 2**（agent risk bound）| 主文 §5，**降格** | 见下方降格规则 |
| Prop 1（Q-VIB ELBO）| supp | Q-VIB 框架，不当卖点 |
| Lemma 1（σ² 单调）| supp | Q-VIB 框架 |
| Thm 1（attention drift bound）| supp | Q-VIB 框架 |
| Prop 2（entropy 单调）| supp | Q-VIB 框架 |
| Cor 1（Q-VIB+QCTS ECE bound）| supp（或删）| 原为 link BMVC，BMVC 占 → 可弃 |

### 🔴 Thm 2 降格规则（skeptic 致命攻击，必改）

**严禁**写「$\mathcal{R}_{\text{agent}}(x) \leq \mathcal{R}_{\text{direct}}(x)$ 全局成立」。自家 r4 实证 Direct B3 sens=0.818 > agent=0.788，与 §7.7 DCA 自相矛盾。

**必须改写为三段诚实表述**：
1. **局部条件界**：增强收益 $\Delta(\bar{q}, T_\omega) > 0$ **仅在区间 $\bar{q} \in [\tau_{\text{enh}}, \tau_{\text{high}}]$ 内成立**（moderate 退化窗口），区间外不成立。
2. **全局诚实负结果**：固定阈值下，全局 triage **当前不优于 Direct**（§7.7 DCA 四法净收益 95% CI 全重叠 0.179–0.192 不可区分、triage@20% Direct sens 0.818 最优、最强变体 Q-VIB+TokFT 0.788 仍不超 Direct）。主动认负「we make no claim that triage raises net benefit globally」。
3. **future work**：threshold-learning（学习路由阈值而非固定）留作未来工作。

---

## ⚔️ GradProm 对比（撞车=中，必写一段防御）

**GradProm**（arXiv 2501.01114，同 ISIC 皮损域）已先证「增强伤诊断」，但其解法是**梯度修复**（gradient projection / gradient promotion）。

**差异化焊死**（必写进 related work + discussion）：
> "Unlike GradProm, which corrects gradients during training, we provide (i) a **mutual-information lower bound guarantee** for diagnosis preservation (Lemma 3), and (ii) a **routing decision** including query-for-retake. GradProm treats the symptom by repairing gradients; we bound the information loss and decide when enhancement is unsafe."

简记：**我们给「诊断保持的互信息下界保证」+「路由决策（含 retake）」，它治标修梯度。**

---

## 🧱 防火墙（两道，写进文档）

### 防火墙 1 — BMVC 墙
- BMVC = 已投未公开（notification ~2026-08）；数字仅 cite，**录用公开后才能引**。
- 被 BMVC 占的四维度一律**只 cite 不搬表**（计划文档 §3 逐表核实）：
  - 跨域 ρ（Fitz I-VI 6 域 + transfer + HAM/PAD/CheXpert/APTOS fundus）
  - ImageNet-C **18 腐蚀** × 2 backbone × 5 严重度
  - 5 backbone universality（ResNet-50 / ViT-Tiny / ConvNeXt-Tiny / Swin-Tiny + Std VIB）
  - DCA / triage（`tab:dca`/`tab:triage`/`fig:dca`）
- **事实订正**：早期计划写的「9 方法 / 14 腐蚀」与 BMVC 提交版（**7 方法 / 18 腐蚀**）对不上，以 BMVC 提交版为准。

### 防火墙 2 — 诚实墙
- Q-VIB 无方法增益（r1/r2/r3 FAIL），不得 claim 增益。
- triage 实证负（Direct 赢），Thm2 降格为局部条件界 + 诚实负结果。
- 0.707 是幽灵数（旁支管线误抄，原始 csv 不可考），**弃用**，不当任何 headline 数。
- E5 melanoma 救援净负、E6 severe 退化、E4 实证 FAIL、v6 mask-L1 null —— 全部诚实陈述，作为 query-for-retake 动机，不藏不美化。

---

## 📐 故事弧（§1-§9 章节顺序锁定，按新 headline 重排）

```
§1 Introduction
├── §1.1 问题陈述：医学 AI 部署在 consumer devices 上，图像质量沿多维度退化；
│         passive enhancement 不保证诊断保持，盲目 defer 浪费可救图像
├── §1.2 ★ Headline hook ★：safe diagnosis-preserving enhancement
│         + query-for-retake triage（detect degradation → enhance safely OR query-for-retake → diagnose）
├── §1.3 现有方法缺陷：
│   - enhancement (Real-ESRGAN / NAFNet) → 不保证 diagnostic preservation
│   - GradProm (arXiv 2501.01114) → 修梯度治标，无 MI 保证、无路由
│   - selective prediction / deferral (Geifman 2017 / AT-CXR) → 只 abstain/defer，无采集闭环
│   - calibration (Guo) → post-hoc，不处理 quality（cite BMVC，不搬数）
├── §1.4 Contributions（4 条 bullet = C0-C3）：
│   - C0 per-dimension × per-severity 退化曲面（动机刻画）
│   - C1 DP-Loss 诊断保持增强 + Lemma 3 互信息下界（实证 E7）
│   - C2 query-for-retake agent（采集闭环，文献首次）
│   - C3 诚实边界（severe/melanoma 增强净负 → 闸门动机）+ Thm2 局部条件界

§2 Related Work（4 块）
├── §2.1 Medical Image Enhancement: Real-ESRGAN / Restormer / NAFNet / Retinex（+ GradProm 差异化段）
├── §2.2 Diagnosis-preserving / perception-distortion: Blau&Michaeli 2018 / Cohen 2018
├── §2.3 Selective Prediction / Deferral / Agentic Medical AI: Geifman 2017 / AT-CXR（query-for-retake gap）
├── §2.4 Information Bottleneck（轻量）: Tishby / Alemi VIB（Q-VIB 一句脚注，不当卖点）

§3 Reliability × Recoverability Decision Surface（C0 动机章，BMVC-free）
├── §3.1 5 维退化 taxonomy（模糊/亮度/完整度/色温/对比）+ severity 物理量纲档位表
│        （blur=σ / brightness=乘子 / contrast=α / color=偏移 / completeness=crop_ratio；
│         5 档锚 ImageNet-C severity 1-5，从 degrade.py light/medium/heavy 外插 \todo 核确切值；
│         completeness 写 "partially recoverable" 不写 "irreversible"）
├── §3.2 可靠性轴：逐维 × severity 二维网格，主轴诊断 AUC（非 ECE，避撞 BMVC tab:perdeg）
├── §3.3 可恢复性轴：每个退化点叠加「增强能否救回诊断」（用 C3 的 E5/E6 数据）→ 桥 C1+C3
├── §3.4 VisiScore 5 维质量评估（PLCC 0.924 / SRCC 0.895）
└── §3.5（可选）多方法 UQ 不差异化次要观察（BMVC 逐维只 1 方法）

§4 Diagnosis-Preserving Enhancement（C1）
├── §4.1 NAFNet + quality-conditional FiLM Architecture（确定性，非生成式）
├── §4.2 DP-Loss Definition（feature-level diagnosis-preserving KL）
├── §4.3 Lemma 3（互信息下界保持）+ Prop 3（由 E7 + 非空性承载）
└── §4.4 Three-stage Training Protocol

§5 Query-for-Retake Agent（C2）
├── §5.1 Four-channel Decision Logic（direct / cautioned / enhance / query-for-retake）
├── §5.2 ★ Theorem 2（降格）★：区间 [τ_enh,τ_high] 局部条件界 + 全局 triage 诚实负结果 + threshold-learning future work
└── §5.3 Agent Implementation（Qwen3-4B ReAct + rule fallback）

§6 Experimental Setup
├── §6.1 Datasets + degradation protocol + metrics
└── §6.2 Enhancement baselines（6 SOTA：Restormer / NAFNet / MIRNet-v2 / SwinIR / Uformer-B / Real-ESRGAN，禁扩散）

§7 Experiments
├── §7.1 可靠性 × 可恢复性决策面（C0 结果，逐维 × severity AUC 网格 + 可恢复性叠层）
├── §7.2 ★ E3 Diagnostic Preservation ★（dAUC −0.012 / 一致率 0.9575 / McNemar p=0.573）
├── §7.3 ★ E7 DP-Loss ablation ★（Lemma 3 实证，ΔAUC +0.0205 / McNemar p=2.3e-45）
├── §7.4 ★ E5 honest salvage ★（benign 主导 + melanoma 净负 −81 + v6 mask-L1 null）
├── §7.5 vs 6 SOTA enhancement（E10：6/6 显著优，paired ΔAUC CI 排除 0、McNemar p<1e-150）
├── §7.6 E8 FiLM ablation（诊断保真非 PSNR）+ E9 FiLM vs cross-attn（统计无法区分，parsimony 胜）
├── §7.7 ★ DCA + triage（诚实负结果）★：四法净收益 CI 全重叠、Direct sens 0.818 最优 → Thm2 局部界
└── §7.8 E6 severe boundary（dAUC −0.056 排除 0 → query-for-retake 动机）+ E12 速度（16ms）

§8 Discussion + Limitations
├── §8.1 GradProm 差异化（MI 下界 + 路由 vs 修梯度）
├── §8.2 Why Diffusion Fails Here（生成式伪影安全分析）
├── §8.3 当前可部署方案的收益边界（triage 全局不优于 Direct 的诚实读法）
└── §8.4 Limitations（必含：理论是 sketch 非 watertight；退化 semi-synthetic；q̄ 信号成本；
        无真实部署验证；E2 contrast/color_shift 弱；melanoma 救援缺口未解）

§9 Conclusion

Appendix（supp）
├── A1 Lemma 3 / Prop 3 完整证明（C1 理论）
├── A2 Theorem 2 完整证明（局部条件界 4-case + 诚实全局负结果讨论）
├── A3 Q-VIB 理论框架（Prop1/Lemma1/Thm1/Prop2，框架性，不当卖点）
├── A4 决策面完整逐维 × severity AUC 网格 + 可恢复性叠层表 + severity 物理档位定义
├── A5 Agent 实现细节 + ReAct trace 样例
├── A6 Per-mechanism ablation（FiLM vs cross-attn / DP-Loss λ sweep / KL schedule）
├── A7 E5 per-class salvage 完整拆案 + v6 mask-L1 null
├── A8 Pre-emptive rebuttal（5+ 已知攻击预防）
└── A9 Reproducibility checklist
```

---

## 🔒 锁定数字（不可凭印象改写，全部从 csv 核算 + run_id；入 tex 前过 verifier）

> 来源：旧框架已 Bash/Grep 核实的 E1-E12 v5 实测块（会话 21 frozen）+ VisiScore 5 维 + E5 per-class + 计划文档 §2。BMVC 占的维度（跨域 ρ 全表 / ImageNet-C / 5 backbone / DCA 全表）**不进本表**，仅 cite。

### C1 增强 + 诊断保持（VisiEnhance E1-E12 v5，frozen 会话 21）

| 实验 | 实测 | 判定 | run_id / 源 |
|---|---|---|---|
| **E1** 增强质量 | per-image PSNR **32.74**(with-FiLM) / 33.06(no-FiLM)，SSIM 0.91，n=19878 | ✅ PASS（>30）| 1442290 / `results/e1_film_ablation.json` |
| **E2** 分退化 | brightness 37.68 ✅ / blur 35.82 ✅；color_shift 33.77 ❌(<35)；contrast 29.11 ❌（且 < 降质图 32.29，帮倒忙）| ⚠️ 2/4 PASS → limitation | 1441320 / `results/e2_perdim.csv` |
| **E3** ★诊断保持 | dAUC **−0.0120** ✅；一致率 **0.9575** ✅；dflip 0.135；McNemar(enh-vs-ref) p=0.573 | ✅ 双 PASS | 1441301 / `results/stage2_diag_paired_v5.csv` |
| **E5** salvage | 聚合 moderate 0.737 **不可当达标**；per-class：benign 75.6%(1809/2392)，**melanoma 5.2%(4/77) 救 4 毁 81 净 −81** | C3 弹药（诚实负）| `results/e5_salvage_persample.csv`（会话 22 拆案）|
| **E5** v6 mask-L1 | melanoma salvage **5.2%→5.2% null**，net −81→−79（噪声）| C3 诚实负结果 | job 1442696/1444753 / `results/e5_salvage_v6_persample.csv` |
| **E6** severe 边界 | severe 段 dAUC **−0.0559 CI[−0.085,−0.028] 排除 0**、dflip 0.46 | C3 弹药（query-for-retake 动机）| 1441321 / `results/e6_severe.csv` |
| **E7** ★DP-Loss（Lemma 3）| ΔAUC_enh(S2−S1) **+0.0205 CI[+0.005,+0.035]** 显著>0；ΔKL **−0.148 CI[−0.173,−0.124]** 显著<0；McNemar **p=2.3e-45** | ✅ PASS（C1 最硬）| 1441301 / 同 E3 |
| **E8** FiLM 消融 | FiLM 对 PSNR **中性**（33.06 ≥ 32.74）；对诊断保持正贡献：dAUC −0.033 vs −0.042、一致率 0.90 vs 0.87、KL 0.24 vs 0.35 | ⚠️ 卖点定位诊断保真 | 1442290+1442337 / `results/filmabl_diag.json` |
| **E9** FiLM vs cross-attn | paired bootstrap ΔAUC +0.0016 CI[−0.0057,+0.0086] 含 0、ΔKL CI 含 0、McNemar p=0.679 → 统计无法区分；FiLM parsimony 胜（−1.8M 参数）| ✅ 保留 FiLM | job 1444849/1448254 / `results/stage2_diag_paired_e9.csv` |
| **E10** vs 6 SOTA | **6/6 显著优**：paired ΔAUC(baseline−VE)∈[−0.12,−0.07] 全 CI 排除 0、McNemar p 全 <1e-150、PSNR 32.79 vs 13-22 | ✅ 6/6 PASS | job 1448952 / main.tex tab:e10 |
| **E12** 速度 | 16.08 ms/img（p95 17.0）| ✅ PASS（<50）| 1441322 / `results/e12_speed.csv` |

> **E4 不入 paper**：E4/E4Q 实证 FAIL（增强后熵不降，方向与 Prop3 相反）。Prop3 改由 E7（Lemma 3 实证）+ PSNR≥30 非空性承载。
> **dflip 单指标陷阱**：no-DP/no-FiLM 的 dflip 反而略低（整体信号更糊巧合少翻特定 mel 子集）→ dflip 必配 KL/一致率一起读，不可孤立比。

### C0 / VisiScore 5 维质量（已 done）

| 维度 | PLCC | SRCC |
|---|---|---|
| Sharpness | 0.947 | 0.863 |
| Brightness | 0.987 | 0.986 |
| Completeness | 0.731 | 0.689 |
| Color Temp | 0.992 | 0.990 |
| Contrast | 0.961 | 0.945 |
| **平均** | **0.924** | **0.895** |

### C0 决策面（c0_decision_surface.csv，会话 42 全量 n=360/cell，verifier PASS，0 drift）

> 来源 `results/c0_decision_surface.csv`（25 行 = 5 轴 × 5 severity 档；列 axis/severity_level/severity_value/auc/auc_ci_lo/auc_ci_hi/ece/.../n/auc_enhanced/recoverability_delta/recoverability_ci_lo/recoverability_ci_hi）。每 cell n=360；S1 = identity 退化锚（brightness/contrast/completeness 三轴 S1 AUC 逐位相同 0.923756）。recoverability_delta = auc_enhanced − auc，bootstrap 95% CI。**只增不删其他锁定数字。**

**可靠性轴（AUC，S5 vs S1 跌幅，物理档 severity_value）**

| 轴 | S1 AUC | S5 AUC | S5 sev | 跌幅 | 排序 |
|---|---|---|---|---|---|
| **blur** | 0.9219 | 0.8307 | σ=3.5 | **−0.0911**（最脆）| 1 |
| completeness | 0.9238 | 0.8722 | crop=0.515 | −0.0516 | 2 |
| color_shift | 0.9239 | 0.8870 | shift=0.34 | −0.0369 | 3 |
| brightness | 0.9238 | 0.9061 | mult=0.345 | −0.0177 | 4（最鲁棒）|
| contrast | 0.9238 | 0.9085 | α=0.19 | −0.0153 | 5（表面最鲁棒）|

**可恢复性轴（recoverability_delta，CI 排除 0 才显著）**

| cell | delta | 95% CI | 判定 |
|---|---|---|---|
| **contrast S5**（α=0.19）| **−0.0355** | [−0.0783, **−0.0013**] | 🔴 **HURT\***（全 25 cell 唯一显著「增强帮倒忙」；AUC 0.9085→enh 0.8734）|
| blur S3/S4/S5 | +0.0500 / +0.0598 / +0.0634 | CI_lo 全 >0 | ✅ HELP\*（转折在 S3；S1/S2 跨零）|
| color_shift S3/S4/S5 | +0.0124 / +0.0275 / +0.0361 | CI_lo 全 >0 | ✅ HELP\*（S4/S5 enh AUC≈0.924 桥回基线；转折 S3）|
| brightness S4 | +0.0186 | 排除 0 | ✅ HELP\*（仅此档显著，最鲁棒轴）|
| completeness 全 5 档 | S5 +0.0236 | [−0.0079, +0.0572] | ⚠️ 全跨零 = **partially recoverable 趋势但统计不显著**（不写 irreversible）|

> **C3 措辞订正（强制）**：旧设想「severe 档增强普遍失效」**被 C0 部分推翻** —— 仅 contrast S5 一个 cell 显著 HURT；blur S5 / color_shift S5 增强仍**正效益**（救得回）。§3/§7.1 **严禁泛化「severe 退化增强普遍伤诊断」**，须精确写「对 contrast 极端退化（α=0.19）增强后 AUC 显著下降 −0.0355（95%CI 排除 0），构成 query-for-retake 的一个 per-dimension 触发条件」。C3 主弹药仍是 E5 melanoma 净负 + E6 severe（per-class，§7.4/§7.8）；C0 的 contrast S5 是 per-dimension 层**补充触发点，不替代、不与 E5/E6 混淆**。

### §7.7 DCA / triage（ICLR 重跑，诚实负结果 → Thm2 局部界）

- ITB-LQ n=300，四法净收益 95% CI **全重叠 0.179–0.192**（不可区分）。
- triage@20%：**Direct sens 0.818 最优**；最强变体 Q-VIB+TokFT **0.788 仍不超 Direct**。
- 源 `results/dca/*` + `report/figures/fig_dca_triage.*`。主动认负「make no claim enhancement/triage raises net benefit globally」。

> ⚠️ **BMVC 占、不进本表（仅 cite）**：跨域 ρ 全表（HAM/PAD/Fitz17k/DermNet/fundus）、ImageNet-C 18 腐蚀、5 backbone universality、BMVC 的 DCA/triage 原表。

---

## 🛡️ 防御性写作硬规则（R1-R10，违反即跑偏）

> 多数保留自旧框架（脱敏 / 不写 universal / 数字配 CI / 禁扩散）；按新框架调整：删 Q-VIB-supremacy（R1 旧版关于 TS reversal 保留为通用「不绝对化」）、加 Thm2 降格规则、加 GradProm 差异化规则。

| 编号 | 严禁写法 | 必须写法 |
|---|---|---|
| R1 | "universal across architectures" / "always reverses" 等绝对化 | "most pronounced on X (具体方法名)" / 限定到 dermatology 域内 |
| R2 | "we prove" / "theorem" 用于 Prop 3 / Lemma 3 | "we derive" / "under assumption X, the bound follows" / "we sketch why" |
| R3 | "doctors confirmed" / "triage raises net benefit" | "decision-curve analysis suggests" / "we make no claim that triage raises net benefit globally"（诚实认负）|
| R4 | "Q-VIB" / "VisiScore-Net" / "VisiEnhance-Net" / "anonymous2025*" / "VisiSkin" 在 tex | 投稿前全部脱敏为通用名（"QC-VIB" / "5-head IQA" / "QP-Enhance" 类）|
| R5 | "best ECE in literature" / "state-of-the-art" | 具体数字 + bootstrap 95% CI + 对比的具体方法名 |
| R6 | bare numbers | 每个 ρ 配 p-value，每个 ECE/AUC/ΔAUC 配 bootstrap 2000-sample 95% CI |
| R7 | 把 q̄ 绑死成 VisiScore | "any per-input quality scalar (learned via VisiScore, computed via BRISQUE/CLIP-IQA, or known a priori as corruption severity)" |
| R8 | 把扩散 / SD-Turbo / DiffBIR 当作我们的方法 | 仅在 §8.2 (Why Diffusion Fails Here) 作对照警示 + 明确否决 |
| R9 | 把 VisiEnhance 写成 super-resolution | "diagnosis-preserving restoration / quality-conditional enhancement"，强调诊断保持非视觉超分 |
| R10 | 从 BMVC 搬表 / 搬数 / 搬图进本论文 | 只 cite BMVC paper（录用公开后）；被占四维度一律不进本篇 |
| **R11（新）** | claim「agent 整体风险 ≤ Direct」/「triage 全局优于 Direct」 | Thm2 降格：区间 [τ_enh,τ_high] 局部条件界 + 全局诚实负结果 + threshold-learning future work（见上方 Thm2 降格规则）|
| **R12（新）** | 把 GradProm 当成「也修梯度的同类工作」含糊带过 | 焊死差异化：「我们给诊断保持的**互信息下界保证** + 路由决策（含 retake），它治标修梯度」|
| **R13（新）** | claim Q-VIB 有方法增益 / 是更强诊断器 | Q-VIB 仅作脚注；triage 用现成不确定性信号（Std VIB 即可）|
| **R14（新）** | headline 写成否定式「不能盲目增强」| 建设式：「how to enhance safely —— a mutual-information lower bound for diagnosis preservation + query-for-retake」|

---

## ✅ 已完成 vs 待做

### ✅ 已完成（复用，不重跑）
- VisiScore-Net 5 维质量评估（PLCC 0.924）
- VisiEnhance Stage1/2 ckpt + E1/E2/E3/E5/E6/E7/E8/E9/E10/E12 全套实测（会话 21 frozen + 会话 25/27/28 收官）
- E5 per-class melanoma 救援净负 + v6 mask-L1 null（诚实负结果）
- §7.7 DCA/triage ICLR 重跑（诚实负结果）
- 5 定理推导（`plans/Prop3_Lemma3_*.md`、`plans/Theorem2_agent_risk_bound.md` 等）

### 🚧 待做（新框架收尾）
- **framing 改造**：triage 从「我们做成了」改写为「我们形式化了质量-triage 决策问题 + 诚实报告当前 deployable 方案的收益边界」（参照 Nature Medicine 2024「fair AI 泛化极限」诚实模式）。
- **Thm2 降格落 tex**：按上方降格规则改写主文 §5.2 + supp A2。
- **GradProm 对比段**：related work + discussion 各一段，焊死差异化。
- **C0 决策面出图**：逐维 × severity 的诊断 AUC 网格（主轴，非 ECE）+ 可恢复性叠层（用 E5/E6 数据）；severity 5 档从 `data/degrade.py` light/medium/heavy 物理量纲外插（\todo 核确切值，禁凭印象拍档位）。
- **query-for-retake agent 实现收尾**：Qwen3-4B ReAct + rule fallback。
- **脱敏扫描**：投稿前 grep R4 名单全 0。

---

## 🚨 任何会话开始前必读 checklist

1. ✅ 读本文件至少一遍
2. ✅ 读 `project/ICLR_重构计划_拆两篇_2026-06-17.md`（最高准绳）
3. ✅ 读 `PROJECT_LOG.md` 最新 entry
4. ✅ 读 `ACCEPTANCE_CRITERIA.md` 确认当前任务验收阈值
5. ✅ 任何新数字写入前 → 先 Bash/Grep 核数据源 csv + 过 verifier，不信 Read
6. ✅ grep `meeting/ICLR2027/*.tex`（或本论文 tex）确认无 BMVC 数字偷溜过来

**如果用户描述的任务与本文件 / 计划文档冲突 → 停下来澄清，不要按用户描述执行。**

---

## 🪦 诚实记录：死掉的东西（不复活）

- **Q-VIB 当「更强诊断方法」的 SOTA claim** —— 三轮核查 + r1/r2/r3 钉死，永久放弃，降为脚注。
- **abstract 中心数 0.707** —— 幽灵数（旁支管线误抄），原始 csv 不可考，弃用。
- **R6 重训赌 Q-VIB 差异化** —— 两轮判死（结构性 bottleneck 欠拟合），不烧卡。
- **「agent 整体风险 ≤ Direct」的 Thm2 强 claim** —— r4 实证 Direct 赢，降格为局部条件界。
- **纯 quality-conditional IB 理论论文** —— 实证无增益致命，降级为本论文理论骨架（supp）。
- **单独的 E 可靠性图谱论文** —— BMVC 占 4/7 维度，#1 退化曲面折进本论文当动机章 C0。
- **78-80% 命中率 25-lever 框架** —— 随旧 headline 一并作废；会场改 MICCAI 2027 / TMLR，不再冲 ICLR SOTA。
- **E5 聚合 SalvageRate 0.737 当达标指标** —— per-class 拆案即崩，改写诚实负结果。
