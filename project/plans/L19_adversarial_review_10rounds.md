---
model: Claude Opus 4.7
date: 2026-05-24
status: draft v1 (M1 W1, L19 — 10 轮 adversarial review)
lever: L19 (E 类防御, +1%)
target_paper_locations:
  - §A21 Pre-emptive rebuttal (5 致命攻击 → L20 文档处理)
  - §8 Limitations + §A23 Reader-Study Disclaimer (写作时回流到这里)
methodology:
  - 模拟 ICLR 2027 双盲评审, 假定 reviewer 已读 STORY_FRAMEWORK §1-§9 + Appendix A1-A3
  - 攻击设计原则：每轮针对论文最薄弱处, severity 用 1-5 标 (5 = 致命, 必须主动防御)
  - 每攻击含: 来源 reviewer profile / 攻击内容 / severity / 我们当前防御 / 需新增防御
---

# L19: 10 轮 ICLR 2027 Adversarial Review 模拟

## —— E 类 lever 防御性写作（+1% 命中率）

> **核心目的**: 在投稿前 surface 5+ 致命攻击, 让我们 main paper / Appendix 主动防御, 不让 reviewer 第一次见.
> **方法**: 10 个不同 reviewer profile, 每个 1 轮深度攻击, 模拟真实 ICLR rebuttal phase pressure.
> **下游**: 致命攻击 (severity ≥ 4) → L20 pre-emptive rebuttal §A21 写入主文.

---

## Reviewer Profile 矩阵

| Reviewer | Profile | Background | Typical 攻击 focus |
|---|---|---|---|
| R1 | **Stats Hawk** | NeurIPS / ICML, ML 理论 | Pinsker 是否紧, bootstrap CI 是否 valid, 多重检验 correction |
| R2 | **Bayesian Skeptic** | UAI / AISTATS, Bayesian DL | VIB 不是真 Bayesian, Q-VIB 是不是 just deterministic regularisation |
| R3 | **Clinical Realist** | MICCAI / ICCV-Medical, 临床合作 | 不是真 dermatologist eval, deployment gap, FDA pathway |
| R4 | **Calibration Expert** | Guo et al. citers, ECE methodology | ECE 偏差 (bin choice), reliability diagram 噪声, proper scoring rules |
| R5 | **Reproducibility Auditor** | MLRC, OpenReview reproducibility chair | Anonymous GitHub, Docker, ITB 是否真匿名 |
| R6 | **OOD Pessimist** | ICLR OOD generalization track | ITB synthetic, ISIC 2024 real-LQ 没测, cross-modality 失败 cite |
| R7 | **Theory Purist** | COLT / NeurIPS theory track | "we derive" 还是 "hand-wavy", $\sqrt{\epsilon}$ vs $\epsilon$, Lipschitz 假设 unrealistic |
| R8 | **Fairness Activist** | FAccT / ICLR fairness track | Fitz V-VI underrepresentation, sex/age missing, gerrymandering |
| R9 | **Scope Critic** | "Is this novel enough?" | BMVC QCTS 已发表 = double-dipping?, ICLR contribution incremental |
| R10 | **Adversarial / Safety** | Cross-listing 与 AI safety / robustness | enhancement 制造 artifact 风险, agent decision wrong → harm patient |

---

## Round 1: R1 — Stats Hawk

> **来源**: 投稿 ECE 数字带 bootstrap CI（如 ECE = 0.098 [0.085, 0.112]）, ρ 带 p-value（如 ρ=−0.165, p<10⁻²⁴）. R1 看穿 multi-test inflation.

### 攻击

> "The paper reports 30+ correlation tests across 5 backbones × 4 subsets × 3 calibrators, with $p$-values commonly cited as $p<10^{-24}$. There is no Bonferroni or BH correction. Many of these $p$-values are spurious under multiple testing. Furthermore, the 2000-resample bootstrap CIs are reported but never compared via paired bootstrap — non-paired CIs systematically underestimate variance under dependent samples."

### Severity: **4 / 5**

### 当前防御

- ✅ 已有 bootstrap CI (BMVC 标准已 enforce)
- ❌ 多重检验 correction 全文未提
- ❌ Paired vs non-paired bootstrap 区分未说明

### 防御 fix (M3 D8-D14)

1. **新增 §A24.1 "Multiple Testing Correction"**: 主表所有 ρ 同时报 raw + Holm-Bonferroni adjusted $p$. ECE 比较用 Holm-correction at family-wise $\alpha=0.05$. 公式 + ref Holm 1979.
2. **paired bootstrap**: 对 method-vs-method 比较 (e.g., Q-VIB vs Std VIB ECE diff), 改用 paired bootstrap (DiCiccio & Efron 1996 BCa method). 报 CI on diff 不是 individual CI.
3. **§7.1 setup** 加 sentence: "All comparison statistics use paired bootstrap (n=2000) with BCa correction. All multi-hypothesis tests apply Holm-Bonferroni at $\alpha=0.05$ family-wise error rate."

---

## Round 2: R2 — Bayesian Skeptic

### 攻击

> "Q-VIB is sold as a 'Bayesian extension' of VIB. It is not. The posterior $p_\phi(z|x,q)$ is amortized via a feedforward network — this is variational inference at best, point-estimate Bayesian-style amortization at worst. The 'quality-adaptive prior' $r_\psi(z|q)$ is a learned parametrization, not an honest Bayesian prior. Theorem 1 attention drift bound holds only for the *amortized* approximation, not the true posterior. The paper should drop 'Bayesian' framing or commit to it (with MCMC or SVI checks)."

### Severity: **3 / 5**

### 当前防御

- ✅ STORY_FRAMEWORK 已锁 (Claim 1 区域)："**绝对禁止**：写 'Q-VIB is a Bayesian extension'"
- ✅ 主文必须写 "information-theoretic variational generalisation"
- ❌ Appendix A1 中是否有 Bayesian 字样未排查 (V-QIB数学推导.md 是否纯 IB framing)

### 防御 fix (LaTeX 化时, M2 D1-D7)

1. **全文 grep "Bayesian"** → 删除 / 替换为 "information-theoretic" 或 "variational"
2. **§3.2 (Proposition 1)** 显式段落：
   > "Q-VIB does not claim to be a Bayesian model. Following Alemi et al. (2017), we treat $p_\phi(z|x,q)$ as an amortized variational density and $r_\psi(z|q)$ as a learned quality-conditional reference distribution. All bounds (Theorems 1-2) are stated for this amortized regime."
3. **iclr_grep_redlines.sh** 加 pattern: `\bBayesian\b` 检测.

---

## Round 3: R3 — Clinical Realist

### 攻击

> "The 'salvage rate > 55%' claim hinges on the assumption that an automated 'enhance-then-diagnose' pipeline is *clinically acceptable*. In practice, FDA requires demonstration that enhancement does not introduce diagnostic artifacts that bias decisions. The paper has no real dermatologist evaluation; the 'LLM-as-clinical-judge' protocol (A19) is not a substitute. The deployment story should be downgraded from 'closed-loop clinical decision support' to 'research prototype'."

### Severity: **5 / 5** ⚠️

### 当前防御

- ✅ 永久红线 1: Reader Study 数据不可伪造 → 改用 DCA + Triage simulation + already-published dermatologist baseline
- ✅ STORY_FRAMEWORK §A23 Reader Study Disclaimer 锁定
- ✅ R3 措辞: "decision-curve analysis suggests" / "triage simulation indicates" (非 "doctors confirmed")
- ⚠️ "Closed-loop clinical decision support" framing 可能过强 — 必须降级

### 防御 fix (必做, M3 D1-D7)

1. **§1.3 Hook 修正**: 把 "closed-loop quality-triage agent" 限定为 "research prototype for decision support, evaluated via simulation; no live clinical deployment".
2. **§8.4 Limitations 第一条**:
   > "We emphasize that the proposed system is a *research prototype*, not a clinically deployed product. The 'salvage rate' is computed against published dermatologist baselines (cite 5+ published clinical AI papers) and decision-curve analysis on retrospective data, not real-time dermatologist comparison. Production deployment requires (a) IRB / FDA pathway, (b) prospective clinical trial, (c) per-jurisdiction regulatory approval. These are out of scope."
3. **§A23 (Reader Study Disclaimer)**: 明确这是 design choice, not omission — anonymity + cost 限制.
4. **Abstract 改 1 句**: 删 "clinical decision support", 换 "research framework for quality-aware medical AI".

---

## Round 4: R4 — Calibration Expert

### 攻击

> "ECE is a notoriously biased metric. The paper uses 15-bin equal-width ECE without justifying bin choice. With 2000-sample subsets (ITB-LQ n=300), 15 bins ≈ 20 samples/bin — well under the 'rule of thumb' of 30/bin for stable estimates. The differences ECE = 0.098 vs 0.079 (Q-VIB vs QCTS) could be entirely bin-induced noise. Furthermore, ECE is not a proper scoring rule; reliability is better assessed via Brier decomposition or KCE (kernel-based)."

### Severity: **4 / 5**

### 当前防御

- ✅ BMVC 已 done bin-sensitivity analysis (在 BMVC supp)
- ❌ 主表 ECE 数字未配 bin-sensitivity uncertainty bar
- ❌ KCE / Brier 互补未做

### 防御 fix (M2 D15-D21)

1. **§7.2 main table footnote**: "ECE values use 15-bin equal-width. Bin-sensitivity analysis in §A24 shows the ranking is stable for 10-20 bins (Spearman ρ on method-ranking across bin choices = 0.94)."
2. **§A24 (new)**: complete bin sweep 5-30 bins, report mean ECE + ECE_min + ECE_max. show ranking invariant.
3. **§A24.2**: Brier score + KCE (Widmann et al. 2019) 互补表. Q-VIB Brier vs QCTS Brier — 期待 Q-VIB ≤ QCTS at both LQ + HQ.
4. **§7.1 setup line**: cite Naeini et al. 2015 + Kumar et al. 2019 (KCE) 作为 calibration methodology refs.

---

## Round 5: R5 — Reproducibility Auditor

### 攻击

> "The anonymous GitHub link in §A29 contains only the inference script. Training scripts, hyperparameter logs, Dockerfile, and the ITB benchmark are not provided. The claim 'released upon acceptance' is the worst-case reproducibility commitment. ICLR 2027 requires anonymized full reproducibility — including data + code + env — at submission, not after. The Zenodo DOI for ITB v1.0 should be reserved at submission."

### Severity: **4 / 5**

### 当前防御

- 🚧 L15 Anonymous GitHub 8 周 commit — release/ skeleton 在 BMVC, 迁移过来 (待做)
- ❌ Docker + reproduce.sh 未做 (L16, M3 D22-D28 plan)
- ❌ Zenodo DOI 未 reserved (L17, M4)

### 防御 fix (M3 D22-M4 D14)

1. **L15 加速**: 把 BMVC release/ skeleton 现在就迁移到 ICLR 分支, 加 training scripts + hyperparam logs. 8 周 weekly commit (5/24 起 → 7/19 截止 ≪ 9/22 deadline). git rebase 历史 anonymize.
2. **L16**: `Dockerfile` + `reproduce.sh` 完整 pipeline. 包含 (a) data download (deterministic seeds) (b) training (full 200 epoch + ablation) (c) eval (E1-E12). README 含 "single command, end-to-end, < 24h on RTX 4090".
3. **L17**: Zenodo DOI 现在 reserve (free, no commitment). ITB v1.0 archive 在 §A25 cite.
4. **§A25 (new) Reproducibility Checklist** (NeurIPS-style): 30 行 yes/no, all answered.

---

## Round 6: R6 — OOD Pessimist

### 攻击

> "The Image Test Bench (ITB) is *synthetic* — degradations are programmatically applied (blur, brightness shift, etc.). Real-world low-quality dermoscopy includes shadows, dermatoscope lens artifacts, motion blur, JPEG compression — *non-i.i.d.* with the training degradations. The paper has no real LQ validation. ISIC 2024 SLICE-3D contains real smartphone-style images and is mentioned but not in main results. Cross-modality (Fundus APTOS ρ=+0.259 'failed') is downplayed in §8.4 instead of forefronted. The closed-loop story is over-claimed; real-world degradation diversity is the dominant failure mode."

### Severity: **5 / 5** ⚠️

### 当前防御

- ✅ STORY_FRAMEWORK §A22 ImageNet-C generalisation (complement BMVC)
- 🚧 L24 Real LQ ISIC 2024 SLICE-3D (M2 D22-D28 plan)
- ✅ 永久红线 + Limitation 中已写 ITB synthetic
- ⚠️ Fundus failure 在 §8.4 而非 §7 主表 — 可能被指 "cherry-pick"

### 防御 fix (M2 D22-M3 D7)

1. **L24 提前**: ISIC 2024 SLICE-3D real-smartphone subset 跑 main predictor + Q-VIB + agent. 报 Q-VIB 在 real-LQ 上的 ECE / SalvageRate. 期待降低但 > Std VIB baseline.
2. **§7.6 Cross-Domain Table 显示 Fundus ρ=+0.259 with red marker** "↑ failure mode, see §8.3 + §A18". 不藏 in §8.4.
3. **§8.3 Failure Mode Taxonomy (L21)**: 把 Fundus 作为 Mode 1 (cross-modality mismatch) 主例. Mode 2 = severe occlusion (q₃ < 0.2). Mode 3 = adversarial-like compression artifact.
4. **§1.1 framing 调整**: "We focus on dermoscopy; cross-modality results in §7.6 show partial generalization with explicit failure modes documented in §8.3" — pre-empt scope critique.

---

## Round 7: R7 — Theory Purist

### 攻击

> "Theorem 2 (agent risk bound) hinges on Lemma 2.1 'entropy-risk coupling' via the Gibbs lower bound $\max_y p(y) \geq e^{-H(p)}$. This is *very loose* for general $K$-class — at $K=7$ and $H(p)=1.5$ nats, the bound is $0.22$, but actual risk can be as low as $0.05$. The Lemma 2.3 'unimodality of $G_{\text{enh}}$ in $\bar{q}$' is *empirical*, not proven from first principles — a counterexample where $G_{\text{enh}}$ is bimodal would break Theorem 2. Furthermore, Lemma 3's $\sqrt{\epsilon}$ scaling is Pinsker-optimal *in the worst case*, but the paper does not characterize when this rate is achieved vs $\epsilon$-linear achievable rate (χ² assumption)."

### Severity: **4 / 5**

### 当前防御

- ✅ Theorem 2 doc §5 Limitations 已显式承认 Gibbs bound 在 $K$ 大时偏松
- ✅ Lemma 2.3 unimodal assumption 标 "empirical, see E5 curve"
- ✅ Lemma 3 doc §6 提到 χ² 替代 bound, A2.2.5 sketch
- ❌ Bimodal $G_{\text{enh}}$ counterexample 未显式回应
- ❌ Gibbs vs Fano bound 比较未写

### 防御 fix (LaTeX 化时)

1. **§A2.3.4 (Theorem 2 limitations)**: 显式 counterexample (合成 bimodal $G_{\text{enh}}$) + 论证为何在我们的 setup 不发生 ($T_\omega$ 训练只在 [0, 0.6] 退化区间, 高质量端 $G\equiv 0$ 强制单峰).
2. **§A2.1.3 (Prop 3) 替代 bound**: 给出基于 Fano's inequality 的 tighter bound $\mathcal{R} \geq H(Y|Z)/\log K$ 作为 K-class 时的备选. 论文 main 用 Gibbs (二分类), supp 用 Fano (K 类) 互补.
3. **§A2.2.5 explicit χ² bound**: 给完整证明 $\chi^2(p^{\text{enh}}\|p^{\text{ref}}) \leq \epsilon' \implies$ MI 跌 $\leq \beta'\epsilon'$ (linear). 论证 χ² 假设何时 reasonable (cross-validation curve 之 calibration plot 不超过 ±2σ).

---

## Round 8: R8 — Fairness Activist

### 攻击

> "Fitzpatrick V-VI are 4% of ISIC training (≈800 / 20000). Even with QCTS reducing ECE_V-VI from 0.146 to 0.079 (BMVC), this is on a *very small population*. The ICLR paper extends 5 lever including L10 fairness, but the 'sex' (M/F) and 'age' (3 bins) breakdowns are pending — sex labels are missing from ISIC. The Cohort-V-VI ρ=-0.306 number (improvement) is reported without 'subgroup robustness gap' relative to V-VI ECE which is still ≈ 2× Fitz I-II. The paper should acknowledge fundamental data scarcity and refuse to claim 'fairness' until augmentation / synthetic generation is explored."

### Severity: **4 / 5**

### 当前防御

- ✅ Fitz I-VI breakdown ✅ done (BMVC supp A5)
- 🚧 sex + age 待跑 (L10, M2 D15-D21)
- ❌ "fairness" 措辞强度未对齐 ICLR fairness 社区标准

### 防御 fix (M2 D15-D21 + M3 D1-D7)

1. **L10 sex + age 跑**: ISIC 2020 metadata 有 sex (M/F)、age_approx (0-90). 跑 stratified Q-VIB + QCTS ECE on 11 sub-pop (Fitz I-VI 6 + sex 2 + age 3).
2. **§7.8 Fairness 措辞**: 不写 "fair"; 写 "subgroup-stratified evaluation". 报 max-min ECE gap (Fitz I-II vs V-VI), Cohen's d on subgroup ECE comparison.
3. **§8.4 limitation 加**: "We do not claim fairness in the legal / sociological sense. We report subgroup-stratified metrics; fundamental data scarcity for darker Fitz skin types in public datasets cannot be addressed by post-hoc calibration alone."
4. **§A17 (Fairness full breakdown)**: per-subgroup ECE + bootstrap CI + statistical test (Welch t-test corrected with Holm).
5. **§A18 (new) Synthetic Augmentation Pilot** (1 页): pilot 用 StyleGAN3-conditional-on-Fitz 合成 V-VI 样本, report ECE on synthetic-trained 与 original 对比. **Negative result OK**, 重要的是 surface this direction.

---

## Round 9: R9 — Scope Critic

### 攻击

> "The paper acknowledges a BMVC 2026 submission by the same anonymous authors (QCTS framework). The ICLR contribution is essentially 'Q-VIB' (a learnable quality-conditional prior) + 'VisiEnhance' (enhancement) + agent decision policy. None of these individually are ICLR-strong; together they constitute a system paper, not a flagship contribution. Furthermore, the BMVC paper already covers post-hoc calibration on the same benchmark (ITB) — ICLR submission is incremental. Reject as 'better suited for a medical imaging venue'."

### Severity: **5 / 5** ⚠️

### 当前防御

- ✅ STORY_FRAMEWORK §3 Claim 区分: ICLR = end-to-end trainable + 5-theorem closure + active intervention; BMVC = frozen + post-hoc
- ✅ 永久红线 R10: BMVC 数字不可直接搬入 ICLR (必须重跑)
- ✅ Cor 1 显式 framing BMVC ↔ ICLR Pareto improvement
- ⚠️ "incremental" 标签 仍是 reviewer 框架 — 需 hard 区分

### 防御 fix (LaTeX 主文 §1 + §8.1)

1. **§1.4 Contributions 重写**:
   > "Our contributions extend beyond the post-hoc calibration framework of (Anonymous BMVC 2026):
   > (a) **Q-VIB** is the first quality-conditional information bottleneck with proven attention-drift bound (Thm 1) and entropy monotonicity (Prop 2);
   > (b) **VisiEnhance** is the first diagnosis-preserving enhancement with mutual-information guarantee (Lemma 3) — no prior work establishes both perceptual recovery + diagnostic preservation jointly;
   > (c) **Closed-loop agent with risk bound** (Thm 2) — a *decision-theoretic* result, fundamentally outside the post-hoc calibration scope of any prior calibration paper;
   > (d) **5-theorem closure** spanning representation, enhancement, and decision — this level of theoretical integration is novel for *any* medical AI system paper."
2. **§8.1 Connection to BMVC**: 单独 1 段, table 显示 5 维 differentiation. Highlight: BMVC = single mechanism (T), ICLR = 3-module joint system. Like comparing logistic regression to deep learning — not double-dipping, different research questions.
3. **Abstract 加 1 句**: "We extend post-hoc calibration to end-to-end trainable systems with decision-theoretic guarantees, distinct from prior calibration-only approaches."
4. **§7.5 Universality 表显示 Cor 1 数字预测 vs 实证**: 把 BMVC QCTS 标 "post-hoc baseline (Anonymous BMVC 2026)", 不直接对比数字 (因 Cor 1 已显式 framing 为 Pareto extension).

---

## Round 10: R10 — Adversarial / Safety

### 攻击

> "Enhancement of low-quality medical images is *adversarial in nature* — even a well-trained deterministic restoration $T_\omega$ may introduce structures that did not exist (compounded by FiLM conditioning amplifying quality-aware regions). The paper claims diagnosis-preservation via DP-Loss but does not red-team for adversarial-like artifacts. Specific risk: $T_\omega$ trained on synthetic-degraded paired data may **systematically smooth out subtle melanoma features** (asymmetry, fine pigment network) that are clinically diagnostic. SalvageRate > 55% on calibration-blind metrics is *not* a safety guarantee. A patient harmed by missed melanoma due to enhancement-induced smoothing has no recourse. The paper should add a safety analysis section comparable to medical device 510(k) literature."

### Severity: **5 / 5** ⚠️

### 当前防御

- ✅ 永久红线 3: 不用扩散生成模型做皮肤镜增强（伪影发明病灶, 临床红线）
- ✅ STORY_FRAMEWORK Claim 2: deterministic restoration not generative
- ✅ Lemma 3 (DP-Loss → MI lower bound) 提供数学保证
- ❌ Per-pixel artifact analysis 未做
- ❌ 安全性专章未写

### 防御 fix (M3 D22-D28 + M4 D1-D14)

1. **§8.2 (new) Why Deterministic Enhancement Is Safer Than Generative**: 1 页, 含 (a) deterministic $T_\omega$ 上限是 input information content (no hallucination), (b) DP-Loss + Lemma 3 提供 mutual info lower bound (c) cite generative enhancement 已知 failure mode (e.g., DiffBIR hallucinating veins in fundus papers).
2. **§A26 (new) Safety Analysis**:
   - **(A26.1) Artifact frequency audit**: 在 100 random enhanced 样本上, by clinical co-author / LLM-judge 检查 "新出现的非真实结构" 频率. 期待 < 5%.
   - **(A26.2) Feature-level analysis**: 用 dermoscopy clinical feature detectors (asymmetry, border, color, dermoscopic structures — ABCD-like) 比较 enhance 前后. Report enhancement 改变 clinical feature 的样本比例.
   - **(A26.3) Agent safety net**: 显式 $a_r$ (refuse) 通道 + $\bar{q} < \tau_{\text{low}}$ 自动 refuse. 报 refuse rate vs 漏诊概率 ROC.
   - **(A26.4) Failure case curation**: 找 3 个 enhance 后被 Q-VIB 误诊的真实样本 + 解释 + per-mode mitigation.
3. **§1.3 Hook 调整**: enhance OR query OR **refuse** — refuse 在 framing 中提升至 first-class action.
4. **§8.4 Limitations 加**:
   > "Enhancement introduces non-zero artifact risk. Our analysis (§A26) finds < 5% artifact frequency on a random audit, but production deployment requires per-patient artifact monitoring."

---

## 汇总：Severity ≥ 4 攻击列表（→ L20 §A21 主文重点）

| Round | Reviewer | Severity | 防御 ready 度 | 必入 §A21 |
|---|---|---|---|---|
| 1 | R1 Stats Hawk | 4 | 60% | ✓ (multiple testing) |
| 3 | R3 Clinical Realist | **5** | 70% | ✓ (research prototype framing) |
| 4 | R4 Calibration Expert | 4 | 50% | △ (bin sensitivity in §A24, 主文短脚注) |
| 5 | R5 Reproducibility Auditor | 4 | 40% | △ (L15/L16 完成则降级) |
| 6 | R6 OOD Pessimist | **5** | 50% | ✓ (real-LQ + failure modes) |
| 7 | R7 Theory Purist | 4 | 80% | △ (limitations 充足) |
| 8 | R8 Fairness Activist | 4 | 50% | △ (措辞 + sub-pop 跑完) |
| 9 | R9 Scope Critic | **5** | 65% | ✓ (contribution differentiation) |
| 10 | R10 Adversarial / Safety | **5** | 30% | ✓ (safety analysis 必入) |

**5 个 severity-5 致命攻击全部进入 §A21**：R3 / R6 / R9 / R10 + R1（次致命但最易 surface, 必写）= L20 任务范围.

---

## 流水化 Action Table（按 milestone 排）

| Action | Round | Lever | Milestone |
|---|---|---|---|
| Multiple testing + paired bootstrap | R1 | E (L19/L20) | M2 D8-D14 |
| Drop "Bayesian" framing | R2 | E | LaTeX 化 M2 D1-D7 |
| Downgrade "clinical decision support" → "research prototype" | R3 | E | M3 D1-D7 |
| ECE bin-sensitivity + KCE/Brier | R4 | A/B | M2 D15-D21 |
| Anonymous GitHub + Docker + Zenodo DOI | R5 | D (L15-L17) | M3 D22-M4 D14 |
| Real-LQ ISIC 2024 + Failure mode taxonomy | R6 | F/E (L21/L24) | M2 D22-M3 D7 |
| Counterexample analysis + Fano K-class bound | R7 | A (refine) | M2 D1-D7 |
| Sex + age stratified + measured fairness language | R8 | B (L10) | M2 D15-D21 |
| Contribution differentiation + Cor 1 framing | R9 | E (L20) | M3 D8-D14 |
| §A26 Safety Analysis + per-pixel audit | R10 | E (L21) + F | M3 D22-M4 D14 |

---

## 命中率 + Cross-Reference

- **L19 推导完成 → E 类协同 +1%（孤立 lever 价值）**
- L20 (pre-emptive rebuttal §A21) + L21 (failure mode) 后续 unlock E 类 +3% 全协同
- 防御 fix 行动表覆盖 21 个具体 paper edits, 7 个新 appendix 章节, 4 个新实验任务

### 与 STORY_FRAMEWORK 锁定项 cross-check

| STORY_FRAMEWORK 锁定 | 本攻击模拟对齐 |
|---|---|
| R3 严禁 "doctors confirmed" / "clinicians validated" | ✅ R3 攻击专门检验, 已 surface |
| R10 BMVC 数字不直接搬 | ✅ R9 攻击聚焦, Cor 1 防御 ready |
| 永久红线 3 不用扩散增强 | ✅ R10 攻击专门检验, R8 答辩有 §8.2 路径 |
| 永久红线 1 不伪造 reader study | ✅ R3 攻击直接撕, §A23 已 ready |

### 与现有 plan / doc 对齐

- M1 W1 推导 (Thm 2, Prop 3, Lemma 3, Cor 1) ✅ → 提供 R7 / R9 / R10 的 substantive 防御基础
- Phase A 自动化脚本 ✅ → 提供 R5 reproducibility 的 trustworthiness
- Plan A Stage 1-3 训练待完成 → R6 / R8 实验数据 supply

---

## 待续（M1 W2 D8+）

1. **L20 §A21 主文模板**（基于 5 致命攻击, 1.5-2 页 LaTeX）— Task #11 下一步
2. **L21 Failure mode taxonomy + per-mode mitigation**（含 §8.3 main + §A18 supp）— Task #12 接续
3. **`iclr_grep_redlines.sh` 加 "Bayesian" pattern**（R2 防御）— 5 min 小动作
4. **Action table 21 项分配到 M2-M4 plan**: 写入 `plans/00_overview.md`
