# ICLR 2027 故事框架（反跑偏主文档）

**目标命中率**：78-80%（25 lever stack + 5-theorem closure）
**最后更新**：2026-05-24
**适用范围**：任何 Claude / Sonnet / Opus 会话写 ICLR 2027 内容前必读

---

## ⛔ 跑偏定义（命中下列任何一条立即停止操作）

1. **改动 Abstract 第一句**离开 closed-loop quality-triage hook
2. **写「we prove TS reversal universal」/「universal across architectures」**等绝对化措辞
3. **凭印象写数字**而非从 `results/**.csv` + bootstrap CI 核算
4. **删除 Proposition 1-3 / Lemma 1-3 / Theorem 1-2 / Corollary 1 中任何一个**（5-theorem closure 是 ICLR 命脉）
5. **重新加入 anonymous2025\* / VisiSkin / Q-VIB / VisiScore 字样**（投稿前需脱敏）
6. **改动 §3-§7 章节顺序**（已锁定，详见下方故事弧）
7. **把 closed-loop agent 单一化为 calibration story**（必须保留 quality-triage 完整 framing：detect → enhance OR query → diagnose）
8. **使用扩散生成模型做皮肤镜增强**（DiffBIR / SD-Turbo / 等，伪影风险红线）
9. **混淆 BMVC QCTS 与 ICLR 系统**（QCTS = frozen model post-hoc；ICLR = end-to-end trainable + active intervention）
10. **从 BMVC 直接复用 fig / tex / 数字到 ICLR 论文**（必须重跑 / 重画 / 重表达，引用方式 = cite BMVC paper after acceptance）

---

## 🎯 三条核心论点（论文一切内容服务于此）

### Claim 1：Q-VIB —— Quality-Conditioned Variational Information Bottleneck

> 把 Information Bottleneck 的 marginal prior $r(z)$ 由固定 $\mathcal{N}(0,I_d)$ 推广为 quality-conditional $r_\psi(z|q) = \mathcal{N}(0, \sigma^2(\bar{q})I_d)$。
> - **Proposition 1**：Q-VIB ELBO（标准变分推断的 quality-conditional 推广）
> - **Lemma 1**：$\sigma^2(\bar{q})$ 严格单调递减（sigmoid 参数化）
> - **Theorem 1**：Attention drift bound $\|a'-a\|_1 \leq 10 L_{\tilde{u}}L_{\tilde{v}}\varepsilon^2$（Lipschitz + softmax 扰动）
> - **Proposition 2**：预测熵关于 $\bar{q}$ 单调递增（quality-calibrated uncertainty 数学保证）

**绝对禁止**：写 "Q-VIB is a Bayesian extension" — 它是 information-theoretic variational generalization，不是 Bayesian。
**必须写**："Q-VIB strictly generalises VIB (Alemi et al., 2017) by conditioning the marginal prior on perceptual quality."

### Claim 2：VisiEnhance —— Diagnosis-Preserving Enhancement

> NAFNet (Chen et al., ECCV 2022) + FiLM (Perez et al., AAAI 2018) 条件调制，损失含 L1 + LPIPS + **DP-Loss**（diagnosis-preserving KL）+ quality hinge。
> - **Proposition 3**：若 $\bar{q}(T_\omega(x,q)) > \bar{q}(x)$，则 $\mathbb{E}[H(\hat{p}_{T_\omega(x,q)})] \leq \mathbb{E}[H(\hat{p}_x)]$（增强降低诊断熵）
> - **Lemma 3**：$\mathcal{L}_{\text{DP}} \leq \epsilon \implies I(Z_{\text{enh}};Y) \geq I(Z_{\text{ref}};Y) - \beta\epsilon$（互信息下界保持）

**绝对禁止**：用 GAN / 扩散模型做骨干（医学伪影红线）/ 把 enhancement 写成 super-resolution
**必须写**："deterministic restoration with quality-conditional FiLM modulation，never generative diffusion，因为生成式模型在皮肤镜域有发明色素网络/血管结构的伪影风险"

### Claim 3：Closed-Loop Quality-Triage Agent

> VisiScore → VisiEnhance OR 追问 → Q-VIB 诊断的双通道决策，4 通道精细分级（A1 高质 / A2 准高 / B 增强 / C 极低）。
> - **Theorem 2**：双通道决策的 expected risk bound — 给定 quality scalar $\bar{q}$、增强映射 $T_\omega$、退化阈值 $\tau$，agent 的 expected risk $\mathcal{R}_{\text{agent}}(x)$ 上界为 $\mathcal{R}_{\text{direct}}(x) - \Delta(\bar{q}, T_\omega)$，$\Delta > 0$ 当且仅当 $\bar{q} \in [\tau_{\text{enh}}, \tau_{\text{high}}]$
> - **Corollary 1**：Q-VIB + QCTS 复合的 ECE upper bound（连 BMVC 故事 + 给出 deployment-time guarantee）

**绝对禁止**：写 "agent generates diagnosis" — agent 不诊断，它**决策何时诊断/增强/追问**
**必须写**："The closed-loop agent decides among four channels — direct diagnosis, cautioned diagnosis, enhance-then-diagnose, or query-for-retake — based on quality-stratified thresholds with theoretical risk bounds."

---

## 📐 故事弧（§1-§9 章节顺序锁定）

```
§1 Introduction
├── §1.1 问题陈述：medical AI 在 consumer devices 上 quality varies，passive calibration 不够
├── §1.2 现有方法缺陷：
│   - calibration (Guo) → post-hoc，不处理 quality
│   - Bayesian (MC Dropout / Deep Ensemble) → quality-oblivious uncertainty
│   - enhancement (Real-ESRGAN) → 不保证 diagnostic preservation
├── §1.3 ★ Closed-loop quality-triage hook ★
│   - VisiScore 评估 + VisiEnhance 修复 OR Agent 追问 + Q-VIB 诊断
│   - 5-theorem end-to-end closure
├── §1.4 Contributions（4 条 bullet）：
│   - C1 Q-VIB（first quality-conditional IB）
│   - C2 VisiEnhance + DP-Loss（first diagnosis-preserving enhancement with mutual info guarantee）
│   - C3 Closed-loop agent + risk bound (Thm 2)
│   - C4 ITB benchmark + 25 lever evaluation

§2 Related Work（4 块）
├── §2.1 Calibration: Guo / Platt / isotonic / EDL / MC Dropout / Deep Ensemble
├── §2.2 Information Bottleneck: Tishby / Alemi (VIB) / β-VAE / IB Theorems
├── §2.3 Medical Image Enhancement: Real-ESRGAN / DiffBIR / Restormer / NAFNet / Retinex
├── §2.4 IQA + Medical AI Benchmarks: BRISQUE / CLIP-IQA / APTOS / ISIC challenges

§3 Quality Assessment + Q-VIB
├── §3.1 VisiScore-Net（5维 quality vector, PLCC 0.924 / SRCC 0.895）
├── §3.2 Q-VIB ELBO（Proposition 1 + 完整证明）
├── §3.3 Quality-Adaptive Prior（Lemma 1 + sigmoid 参数化 + asymptotic）
├── §3.4 Quality Tokenizer + Attention Drift Bound（Theorem 1）
└── §3.5 Quality-Calibrated Entropy Guarantee（Proposition 2）

§4 Diagnosis-Preserving Enhancement
├── §4.1 Degradation taxonomy（5 维 q 的可修复性分析，q₃ 完整度不可逆）
├── §4.2 NAFNet + FiLM Architecture
├── §4.3 DP-Loss Definition
├── §4.4 Proposition 3（增强降低熵）+ Lemma 3（互信息下界保持）
└── §4.5 Three-stage Training Protocol

§5 Closed-Loop Agent
├── §5.1 Dual-channel Decision Logic（4 通道阈值规则）
├── §5.2 Theorem 2（expected risk bound）+ 完整证明
├── §5.3 Corollary 1（Q-VIB + QCTS ECE bound — link to BMVC）
└── §5.4 Agent Implementation（ReAct + Qwen3-4B + rule fallback）

§6 ITB Benchmark
├── §6.1 4 subsets construction（LQ / HQ / Edge / Diverse）
├── §6.2 Quality-stratified evaluation protocol
└── §6.3 9 baselines（含 BMVC QCTS as one ablation）

§7 Experiments
├── §7.1 Setup（training / metrics / cross-validation）
├── §7.2 Main Results（Table 1 — 9 baselines × ITB-LQ/HQ × {AUC,ECE,QCDI,ρ}）
├── §7.3 ★ E3 Diagnostic Preservation ★（核心：|ΔAUC|<1.5%, McNemar p<0.001）
├── §7.4 ★ E5 Salvage Rate ★（临床价值：moderate-degraded > 55%）
├── §7.5 Universality（Table 2 — 5 backbone × {raw / +QCTS / +Q-VIB}）
├── §7.6 Cross-Domain Generalisation（Table 3 — 8 datasets）
├── §7.7 Cost-Benefit + DCA（Net Benefit + Triage simulation）
└── §7.8 Fairness（Fitz I-VI + sex + age stratified）

§8 Discussion + Limitations
├── §8.1 Connection to BMVC QCTS（post-hoc vs end-to-end）
├── §8.2 Why Diffusion Fails Here（safety analysis）
├── §8.3 Failure Mode Taxonomy（3-mode breakdown + per-mode mitigation）
└── §8.4 Limitations（必须含：theory 是 sketch 不是 watertight 证明；ITB synthetic；q̄ learning cost；no real-world deployment validation）

§9 Conclusion

Appendix（50-80 页 supp）
├── A1 Proposition 1 / Lemma 1 / Theorem 1 / Proposition 2 完整证明（V-QIB 数学推导）
├── A2 Proposition 3 / Lemma 3 / Theorem 2 完整证明
├── A3 Corollary 1 完整证明（Q-VIB + QCTS ECE bound）
├── A4 ITB Construction 详细协议
├── A5 25 Lever 完整 ablation 表
├── A6-A15 Per-mechanism ablation（FiLM vs Cross-attn / DP-loss λ / KL schedule / etc）
├── A16 8 dataset cross-domain 全表
├── A17 Fitz I-VI + sex + age 完整 fairness breakdown
├── A18 Failure mode clustering（KMeans k=3 + per-mode mitigation）
├── A19 LLM-as-clinical-judge 协议 + 200 case study ratings
├── A20 Cost-benefit deployment analysis
├── A21 Pre-emptive rebuttal section（5+ 已知攻击预防）
├── A22 ImageNet-C generalisation（complement BMVC）
├── A23 Reader Study Disclaimer（why no real readers + LLM-judge methodology）
├── A24 Hyperparameter sensitivity（λ_DP / λ_LPIPS / β-schedule / etc）
├── A25-A30 Per-dataset breakdown + reproducibility checklist + Docker spec
```

---

## 🔒 锁定数字（不可凭印象改写，全部从 csv 核算）

### Table 1 (ICLR Main Results, ITB-LQ n=300 / ITB-HQ n=360 — 与 BMVC 不共享，待重跑确认)

| Method | AUC-LQ | ECE-LQ | AUC-HQ | ECE-HQ | QCDI | ρ |
|---|---|---|---|---|---|---|
| EfficientNet-B3 (Direct) | 0.751 | 0.345 | 0.938 | 0.068 | +0.277 | −0.123 |
| MC Dropout (30×) | 0.693 | 0.615 | 0.808 | 0.473 | +0.142 | −0.114 |
| Deep Ensemble (5×) | 0.711 | 0.440 | 0.868 | 0.339 | +0.101 | −0.123 |
| EDL | 0.586 | 0.316 | 0.895 | 0.270 | +0.046 | +0.039 |
| Focal+LS | 0.708 | 0.533 | 0.884 | 0.492 | +0.041 | −0.059 |
| Std VIB | 0.553 | 0.146 | 0.587 | 0.129 | +0.016 | −0.153 |
| Std VIB + TS (Guo) | 0.582 | 0.175 | 0.732 | 0.160 | +0.015 | **+0.241** |
| Std VIB + QCTS (BMVC) | 0.563 | 0.079 | 0.580 | 0.075 | +0.004 | −0.249 |
| **Q-VIB Full (Ours)** | **0.707** | **0.098** | **0.760** | **0.075** | **+0.012** | **−0.165** |
| + VisiEnhance Stage 3 (TBD M2) | TBD ≥0.71 | TBD ≤0.10 | TBD ≥0.76 | TBD ≤0.08 | TBD | TBD |

数据源：`results/eval_report_all.csv` + 待跑 Plan A 重训后 `results/visienhance_qvib_combined.csv`

### Q-VIB 核心数字（test set, n=19878 — 已 done）

| Method | AUC | ECE | Entropy | ρ(H, q̄) |
|---|---|---|---|---|
| Std VIB (D) | 0.693 | 0.097 | 0.240 | −0.024 |
| Adaptive Prior (E) | 0.688 | 0.100 | 0.228 | −0.169 |
| **Q-VIB Full (F)** | **0.707** | **0.098** | 0.225 | **−0.165** (p < 10⁻²⁴) |

### VisiScore-Net 5 维质量（已 done）

| 维度 | PLCC | SRCC |
|---|---|---|
| Sharpness | 0.947 | 0.863 |
| Brightness | 0.987 | 0.986 |
| Completeness | 0.731 | 0.689 |
| Color Temp | 0.992 | 0.990 |
| Contrast | 0.961 | 0.945 |
| **平均** | **0.924** | **0.895** |

### VisiEnhance Plan A 目标（M1-M2 待跑）

| 实验 | 指标 | 目标 | 当前 (Stage 1 v0) |
|---|---|---|---|
| E1 复原质量 | PSNR (moderate) | ≥ 30 dB | 25.55 dB ❌ |
| E1 复原质量 | SSIM (moderate) | ≥ 0.92 | 0.9535 ✅ |
| E3 诊断保持 | \|ΔAUC\| | < 1.5% | TBD |
| E3 诊断保持 | 分类一致率 (C vs A) | > 95% | TBD |
| E5 双通道效率 | SalvageRate (moderate q̄∈[0.35,0.5]) | > 55% | TBD |
| E5 双通道效率 | SalvageRate (severe q̄<0.25) | < 25% | TBD（安全边界）|

### 跨域 zero-shot（已 done）

| Dataset | n | Q-VIB Full ρ | p |
|---|---|---|---|
| HAM10000 | 10,015 | −0.108 ⚠️待核 | < 10⁻²⁶ |
| PAD-UFES | 2,298 | −0.150 ⚠️待核 | < 10⁻¹² |
| CheXpert (cross-modality) | TBD | TBD | TBD（M1-M2 待跑）|
| Fundus APTOS (cross-modality) | TBD | TBD | TBD（M1-M2 待跑）|
| Kvasir endoscopy (cross-modality) | TBD | TBD | TBD（M2 待跑）|
| ISIC 2024 SLICE-3D LQ (real smartphone-style) | TBD | TBD | TBD（M2 D22-D28）|

### 5 backbone universality（BMVC 已 done，ICLR 加 Q-VIB 行）

| Backbone | Method | ECE-LQ | ECE-HQ | QCDI | ρ |
|---|---|---|---|---|---|
| Std VIB | Raw | 0.146 | 0.129 | +0.016 | −0.153 |
| Std VIB | +TS | 0.175 | 0.160 | +0.015 | **+0.241** ⚠️ |
| Std VIB | +QCTS (BMVC) | 0.079 | 0.075 | +0.004 | −0.249 |
| Std VIB | **+Q-VIB (ICLR)** | **0.098** | 0.075 | +0.012 | **−0.165** |
| ResNet-50 | Raw / +TS / +QCTS | 0.050 / 0.029 / 0.046 | 0.036 / 0.025 / 0.031 | +0.014 / +0.004 / +0.014 | −0.368 / −0.368 / −0.380 |
| ViT-Tiny | Raw / +TS / +QCTS | 0.058 / 0.043 / 0.058 | 0.036 / 0.072 / 0.075 | +0.023 / −0.029 ⚠️ / −0.017 | −0.160 / −0.160 / −0.266 |
| ConvNeXt-Tiny | Raw / +TS / +QCTS | 0.171 / 0.097 / 0.096 | 0.035 / 0.119 / 0.116 | +0.136 / −0.022 ⚠️ / −0.020 | −0.241 / −0.241 / −0.270 |
| Swin-Tiny | Raw / +TS / +QCTS | 0.056 / 0.044 / 0.051 | 0.037 / 0.066 / 0.035 | +0.020 / −0.021 ⚠️ / +0.016 | −0.237 / −0.237 / −0.259 |

数据源：`results/backbones/section54_summary.csv`

---

## 🛡️ 防御性写作硬规则（R1-R10，违反即跑偏）

| 编号 | 严禁写法 | 必须写法 |
|---|---|---|
| R1 | "TS always reverses" / "universal reversal" | "most pronounced on weakly quality-aware backbones (e.g., Std VIB, ViT-Tiny, ConvNeXt-Tiny, Swin-Tiny)" |
| R2 | "we prove" / "theorem" 用于 Prop 3 / Lemma 3 | "we derive" / "we sketch why" / "under assumption X, the bound follows" |
| R3 | "doctors confirmed" / "clinicians validated" | "decision-curve analysis suggests" / "triage simulation indicates" / "LLM-judge protocol (Appendix A19) suggests" |
| R4 | "Q-VIB" / "VisiScore-Net" / "VisiEnhance-Net" / "anonymous2025\*" 在论文 tex 里 | 投稿前全部脱敏为 "QC-VIB" / "5-head IQA" / "QP-Enhance" 类通用名 |
| R5 | "best ECE in literature" / "state-of-the-art" | 用具体数字 + bootstrap 95% CI + 对比的具体方法名 |
| R6 | bare numbers | 每个 ρ 数字附 p-value，每个 ECE/QCDI/AUC 附 bootstrap 2000-sample 95% CI |
| R7 | 把 q̄ 绑死成 VisiScore-Net | "any per-input quality scalar (learned via VisiScore, computed via BRISQUE/CLIP-IQA, or known a priori as corruption severity)" |
| R8 | 提 "diffusion enhancement" / "Stable Diffusion" / "SD-Turbo" / "DiffBIR" 当作我们的方法 | 仅在 §8.2 (Why Diffusion Fails Here) 出现，作为对照警示 + 明确否决 |
| R9 | 把 VisiEnhance 写成 super-resolution | "diagnosis-preserving restoration / quality-conditional enhancement" — 强调诊断保持，非视觉超分 |
| R10 | 把 BMVC QCTS 数字直接搬进 ICLR Table 1 | 标注 "(BMVC)" + 必须有对应 ICLR 重跑的 Q-VIB 行 + 在 §1.3 + §8.1 明确区分 |

---

## 📊 已实验完成 vs 待跑（按 M1-M4 日程）

### ✅ 已完成（BMVC 复用 + 大项目前期）
- VisiScore-Net（5 维质量评估，PLCC 0.924）
- Q-VIB Full (F)（AUC 0.707, ECE 0.098, ρ=-0.165）
- Std VIB / Adaptive Prior / MC Dropout / Deep Ensemble / EDL baseline
- ResNet-50 / ViT-Tiny / ConvNeXt-Tiny / Swin-Tiny 4 backbone universality
- ITB 4 子集构建 + 9 baseline 评测
- HAM10000 / PAD-UFES zero-shot
- ImageNet-C 14 corruption × 5 severity
- VisiEnhance Stage 1 v0（PSNR 25.55 dB，待 Plan A 重训）
- BMVC QCTS（已封印）

### 🚧 M1 (2026-05-24 ~ 06-22) 必做
- VisiEnhance Plan A Stage 1 重训（NAFNet base_channels=64, mid_blocks=8, ~15M 参数, ~30-40h）
- VisiEnhance Stage 2 DP-Loss 微调（~36h）
- VisiEnhance Stage 3 quality hinge（~24h）
- Theorem 2 (agent risk bound) 数学推导 + 完整证明
- Corollary 1 (Q-VIB + QCTS ECE bound) 推导
- CheXpert + Fundus APTOS cross-domain inference（BMVC 已存脚本）

### 🚧 M2 (2026-06-23 ~ 07-22) 必做
- E1-E12 全跑（VisiEnhance 12 实验）
- 6 SOTA enhancement compare（Real-ESRGAN / DiffBIR / Restormer / NAFNet-base / SwinIR / DRSformer）
- Per-mechanism ablation（FiLM vs Cross-attn / DP-loss λ sweep / KL schedule）
- Fitz I-VI + sex + age fairness 完整 breakdown
- Kvasir endoscopy + ISIC 2024 SLICE-3D LQ 子集 inference
- Q-VIB + QCTS 复合 ECE bound 实证验证

### 🚧 M3 (2026-07-23 ~ 08-22) 必做
- 论文 9 页正文 draft v1
- Supp 50 页骨架 + per-mechanism A6-A15 写入
- LLM-as-clinical-judge 200 case study（Qwen3-72B + GPT-4 + Claude）
- 5+ dermatologist baseline 文献整理（cite-and-compare table）
- Cost-benefit deployment analysis（DALY / QALY / missed melanoma cost）
- Anonymous GitHub repo + 8 周持续 commit history
- Docker + reproduce.sh

### 🚧 M4 (2026-08-23 ~ 09-22) 必做
- 10 轮 LLM adversarial review（Calibration ML / Medical AI / Theory / ICLR senior PC / etc personas）
- Pre-emptive rebuttal section（A21）
- 5 轮 polish（同行 / non-domain / copy-edit / calibration expert / typography）
- ITB v1.0 公开 + Zenodo DOI 申请
- HF checkpoint mirror 上传
- OpenReview pre-rebuttal draft（A25 + L25 lever）
- 投稿前最后 grep R1-R10 防御扫描

### ⏳ Buffer (2026-09-23 ~ deadline)
- 编译 × 3
- 数字一致性 17/17（参考 BMVC 协议扩展到 ICLR 30+ 数字）
- OpenReview 上传 + ethics declaration

---

## 🚨 任何会话开始前必读 checklist

1. ✅ 读本文件至少一遍
2. ✅ 读 `PROJECT_LOG.md` 最新 entry
3. ✅ 读 `ACCEPTANCE_CRITERIA.md` 确认当前任务的验收阈值
4. ✅ 读 `DATA_INVENTORY.md` 确认要用的数据是否就位
5. ✅ grep `meeting/ICLR2027/*.tex` 确认无 BMVC 数字偷溜过来（必须重跑）
6. ✅ 任何新数字写入前 → 先 grep 数据源 csv

**如果用户描述的任务与本文件冲突 → 停下来澄清，不要按用户描述执行**（用户可能忘了已有约束）。
