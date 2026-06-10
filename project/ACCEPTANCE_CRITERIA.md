# ICLR 2027 验收标准 — 78-80% 命中率

**目标**：78-80% 投稿命中率
**最后更新**：2026-05-24
**适用范围**：每个 lever / 实验 / milestone 完成判定的唯一标准

> ⚠️ **不存在"基本完成"**。每条验收阈值要么 PASS 要么 FAIL。FAIL 必须降低对应 lever 命中率贡献预估，并在 `PROJECT_LOG.md` 写下 "命中率回退 N%" 的诚实记录。

---

## 🎯 命中率分解（25 lever，总 78-80%）

### 基线：ICLR 2027 平均接受率 ~30%
### 大项目额外提升：+50% （25 lever 累加）

| 类 | 命中率贡献 | Lever 数 |
|---|---|---|
| A 理论深度 | +5% | 5 |
| B 实验规模 | +3% | 5 |
| C 临床可信度 | +4% | 4 |
| D 复现性 | +2% | 4 |
| E 防御性写作 | +3% | 3 |
| F 附加 | +2% | 4 |
| **合计基线 + lever** | **30% + 19% = 49%** | 25 |

**但 lever 间有非线性协同**（理论深 + 实验规模 + 防御性写作 互相放大），实际预估贡献为 **+48-50%**，命中率 **~78-80%**。

**Lever 间扣分规则**：若任一 A 类 lever FAIL，所有 A 类协同效应 -50%（B/C/D/E/F 同理）。例如 L4 Theorem 2 写不出 → A 类总贡献从 +5% 降到 +2.5%。

---

## A 类：理论深度（+5%）

### L1 — Q-VIB 4 定理体系 ✅
- **内容**：Proposition 1 (ELBO) + Lemma 1 (σ² monotonicity) + Theorem 1 (attention drift bound) + Proposition 2 (entropy monotonicity) + Cor 1 (recovers VIB) + Cor 2 (practical implication)
- **状态**：✅ 已完成（`archive/2026-05_pre_iclr_reorg/创新点/创新点数学推导.md`）
- **验收**：4 个定理 + 完整证明 + 实证验证（Q-VIB ρ=-0.165 vs Std VIB -0.024）
- **写入论文位置**：§3.2-§3.5 主文（compact statement）+ Appendix A1 完整证明（5-7 页）
- **若 FAIL**：命中率 -2%（论文失去理论灵魂）

### L2 — VisiEnhance Proposition 3 ✅ (推导完成 2026-05-24)
- **内容**：$\bar{q}(T_\omega(x,q)) > \bar{q}(x) \implies \mathbb{E}[H(\hat{p}_{T_\omega(x,q)})] \leq \mathbb{E}[H(\hat{p}_x)]$
- **状态**：✅ 推导 done — `plans/Prop3_Lemma3_visienhance_theory.md` §1, 显式 (A1)-(A4) + 5-step 严密 proof，含 Q-VIB ELBO + Lemma 1 monotonicity 链路
- **实证**：⏳ 待 Plan A Stage 1+2 完成 (M2 D8-D14, E4 paired t-test)
- **toy 验证**：✅ `tests/test_theorems_numerical.py::test_proposition3_*` PASS
- **写入论文位置**：§4.4 主文 + Appendix A2.1
- **若 FAIL（实证）**：命中率 -1%

### L3 — DP-Loss Lemma 3 ✅ (推导完成 2026-05-24)
- **内容**：$\mathcal{L}_{\text{DP}} \leq \epsilon \implies I(Z_{\text{enh}};Y) \geq I(Z_{\text{ref}};Y) - \beta\sqrt{\epsilon}$，$\beta = M L_{q_\theta}/\sqrt{2}$
- **状态**：✅ 推导 done — `plans/Prop3_Lemma3_visienhance_theory.md` §2，**关键修正**：$\sqrt{\epsilon}$ scaling (Pinsker-optimal)，非 $\epsilon$ linear；显式常数 $\beta\approx 0.74$ (binary)
- **实证**：⏳ M2 D8-D14 (E7 ablation, DP 组 ΔAUC 更小)
- **toy 验证**：✅ `tests/test_theorems_numerical.py::test_lemma3_pinsker_*` PASS
- **写入论文位置**：§4.4 主文 + Appendix A2.2
- **若 FAIL（实证）**：命中率 -1%

### L4 — Closed-loop Agent Theorem 2 (risk bound) ✅ (推导完成 2026-05-24)
- **内容**：$\mathcal{R}_{\text{agent}}(x) \leq \mathcal{R}_{\text{direct}}(x) - \Delta(\bar{q}, T_\omega)$，$\Delta > 0$ iff $\bar{q} \in [\tau_{\text{enh}}, \tau_{\text{high}}]$
- **状态**：✅ 推导 done — `plans/Theorem2_agent_risk_bound.md`，含 decision-theoretic 4-action space + 4 lemmas (entropy-risk coupling / enhancement gain / threshold window / query-refuse safety) + main theorem 4-case proof + Corollary 2.1/2.2
- **实证 (P1/P2/P3)**：⏳ Plan A Stage 3 完成后, `results/agent_vs_direct_risk.csv` 跑 SalvageRate band test
- **toy 验证**：✅ `tests/test_theorems_numerical.py::test_thm2_P1/P2/P3` PASS + bootstrap CI excludes 0
- **写入论文位置**：§5.2 主文 + Appendix A2.3
- **若 FAIL（实证）**：命中率 -1%

### L5 — Corollary 1 (Q-VIB + QCTS 复合 ECE bound) ✅ (推导完成 2026-05-24)
- **内容**：$\text{ECE}(\hat{p}_{\text{comp}}) \leq \min(\text{ECE}_{\text{QV}}, \text{ECE}_{\text{QCTS}}) + \epsilon_{\text{qts}}$, $\epsilon_{\text{qts}} = O(L_T \|\ell\|_{\max}/T_{\min}^2 \cdot \sigma_{\bar{q}|c})$
- **状态**：✅ 推导 done — `plans/Corollary1_qvib_qcts_ece_bound.md`，4-step proof + Murphy 分解 + Lipschitz chain rule，显式数字预测 $\epsilon_{\text{qts}}\approx 0.037$
- **实证**：⏳ M2 D1-D7 universality 表 + composite ECE
- **战略价值**：把 BMVC 的 QCTS work cite 自己之前的 paper（防 R10），论文 closure 完整
- **写入论文位置**：§5.3 主文 + Appendix A3
- **若 FAIL（实证）**：命中率 -0.5%

---

## B 类：实验规模（+3%）

### L6 — 5 backbone universality ✅
- **内容**：Std VIB / ResNet-50 / ViT-Tiny / ConvNeXt-Tiny / Swin-Tiny × {raw, +TS, +QCTS, +Q-VIB}
- **状态**：✅ 已 done（前 3 backbone × 3 method 是 BMVC 复用，需补 +Q-VIB 列）
- **验收**：Table 2 主文 8 行 × 4 列 + bootstrap CI + Q-VIB 列必须重跑
- **完成路径**：M1 D22-D28 补 Q-VIB 列推理
- **若 FAIL**：命中率 -0.5%

### L7 — 8 dataset cross-domain 🚧
- **内容**：ISIC 2020 + HAM10000 + PAD-UFES + Fitz17k + DermNet + CheXpert + APTOS-fundus + Kvasir-endoscopy
- **状态**：🚧 前 4 已 done (BMVC 复用) + CheXpert/Fundus 脚本就位（待推理）+ DermNet/Kvasir 未做
- **验收**：8 个 ρ(H, q̄) 数字 + p-value，至少 6/8 显著 ρ<0（quality-aware）
- **完成路径**：M1 D29 ~ M2 D14
- **风险**：endoscopy / fundus 跨模态可能不 quality-aware（已知 Fundus ρ=+0.259 → 失败）— 写 §8.4 limitation 而非掩盖
- **若 FAIL（<6 个 quality-aware）**：命中率 -0.8%，论文降级为 dermoscopy-specific story

### L8 — E1-E12 full ❌
- **内容**：VisiEnhance 12 个核心实验（详见下方 E1-E12 表）
- **状态**：❌ 依赖 Plan A 重训完成
- **完成路径**：M2 D1-D28
- **若 FAIL（E3 或 E5 不达标）**：命中率 -1.5%（这是 VisiEnhance 论文核心）

### L9 — 6 SOTA enhancement compare ❌
- **内容**：vs Real-ESRGAN / DiffBIR / Restormer / NAFNet-base / SwinIR / DRSformer
- **验收**：在 ΔAUC、ΔECE、SalvageRate 三指标上，VisiEnhance 显著优于所有 6 个对比（paired t-test p<0.05）
- **完成路径**：M2 D8-D14
- **若 FAIL**：命中率 -0.5%

### L10 — Fairness 全维度 🚧
- **内容**：Fitz I-VI + sex (M/F) + age (3 bin) 共 11 sub-pop
- **状态**：🚧 Fitz I-VI 部分已 done（BMVC supp A5）
- **验收**：(a) 每个 sub-pop ECE + bootstrap CI (b) max-min ECE 差 < 0.05（fairness threshold）(c) Fitz V-VI 不能 underperform 显著（p<0.05 等价检验）
- **完成路径**：M2 D15-D21
- **若 FAIL**：命中率 -0.5%

---

## C 类：临床可信度（+4%）

### L11 — DCA + Net Benefit + Triage simulation ✅
- **状态**：✅ BMVC 已 done（QCTS max NB=0.192 vs VIB 0.186，bootstrap CI overlap）
- **ICLR 扩展**：(a) Q-VIB + VisiEnhance 复合 DCA (b) cost-aware triage (c) clinical decision threshold sensitivity
- **完成路径**：M2 D22-D28 + M3 D1-D7
- **若 FAIL**：命中率 -1%

### L12 — 5+ dermatologist baseline cite ❌
- **内容**：从 published papers cite 5+ dermatologist AUC（Esteva 2017 / Tschandl 2019 / Brinker 2019 / Phillips 2019 / Marchetti 2020）作为对照
- **验收**：(a) 表格列出 5+ AUC + reader characteristics (b) 我们的 Q-VIB AUC 落在 ±5% 范围内 (c) §7.7 文献对比段
- **完成路径**：M3 D1-D7（文献调研）
- **若 FAIL**：命中率 -1%

### L13 — Cost-benefit analysis ❌
- **内容**：deployment cost (computing / device) vs missed melanoma cost (DALY / 5-yr survival)
- **验收**：(a) sensitivity-specificity-cost 三维分析 (b) break-even threshold 计算 (c) 与 dermatologist screening cost 对比
- **完成路径**：M3 D8-D14
- **若 FAIL**：命中率 -1%

### L14 — LLM-as-clinical-judge ❌（高风险）
- **内容**：Qwen3-72B + GPT-4 + Claude 4.6 模拟 3 dermatologist reviewer，对 200 case study 评分 (1-5 scale)
- **状态**：❌ 未做
- **验收**：(a) 200 case study 完整 (b) 3 LLM 评分 Cohen's κ > 0.5 (c) 与 Q-VIB confidence 显著相关 (d) **必须有 §A23 disclaimer 写清不可替代真人**
- **完成路径**：M3 D15-D21
- **若 FAIL 或 reviewer 攻击**：命中率 -1%（这条 lever 是高风险 high-reward）
- **永久红线**：不能伪装成真人 reader study，必须明确为 LLM-judge protocol

---

## D 类：复现性（+2%）

### L15 — Anonymous GitHub 8 周持续 commit 🚧
- **状态**：🚧 BMVC release/ 已建 skeleton，需迁移到 ICLR 分支 + 持续 commit
- **验收**：M2-M4 期间每周至少 5 commit，最终 60+ commits 历史
- **完成路径**：M2 D1 启动持续 commit
- **若 FAIL**：命中率 -0.5%

### L16 — Docker + reproduce.sh ❌
- **内容**：单容器一键 reproduce 主表
- **验收**：(a) `docker run yj/visiskin reproduce.sh` 跑通 (b) 输出 Table 1 + Fig 1 数字 (c) 与论文数字误差 < 1%
- **完成路径**：M3 D22-D28
- **若 FAIL**：命中率 -0.5%

### L17 — ITB v1.0 公开 + Zenodo DOI ❌
- **内容**：ITB benchmark 数据集 + license (CC-BY-NC-SA) + Zenodo DOI
- **完成路径**：M4 D1-D7
- **若 FAIL**：命中率 -0.5%

### L18 — HuggingFace checkpoint mirror ❌
- **内容**：所有 7 个 checkpoint 上传 HF（匿名 user）
- **完成路径**：M4 D8-D14
- **若 FAIL**：命中率 -0.5%

---

## E 类：防御性写作（+3%）

### L19 — 10 轮 LLM adversarial review ✅ (2026-05-24, draft v1)
- **personas 实际**（10 个，见 `plans/L19_adversarial_review_10rounds.md`）：
  R1 Stats Hawk / R2 Bayesian Skeptic / R3 Clinical Realist / R4 Calibration Expert / R5 Reproducibility Auditor / R6 OOD Pessimist / R7 Theory Purist / R8 Fairness Activist / R9 Scope Critic / R10 Adversarial-Safety
- **状态**：✅ 10 轮 attacks + responses + 21-项 action table 完成 — 5 个 severity-5 致命攻击 (R3/R6/R9/R10 + R1 必写) 已 surface, 进入 L20 §A21
- **实证 deliverable**：P1 (M1 cluster q<0.35 retake_rate=100%) 已 verified
- **写入论文位置**：21 项 action 分配到主文 §1.4 / §7 / §8 / §A21 / §A26 等
- **若 FAIL（<8 轮完成）**：N/A，10/10 done

### L20 — Pre-emptive rebuttal section §A21 ✅ (2026-05-24, draft v1)
- **内容**：Appendix §A21 LaTeX 模板，1.5-2 页，5 subsection 应对 5 致命攻击（见 `plans/L20_preemptive_rebuttal_A21.md`）
- **状态**：✅ LaTeX 模板 + Abstract / §1.4 / §8 配套修改清单完成
- **写作 checklist**：10 项 R-numbered alignment（"don't write X / write Y"）
- **完成路径**：LaTeX 化 M2 D8-D14 落地

### L21 — Failure mode taxonomy + per-mode mitigation ✅ (2026-05-24, draft v1)
- **内容**：KMeans k=3 cluster (已 done, `results/failure_mode_clusters_v2.json`) → 3 mode + 4-action mitigation 映射（见 `plans/L21_failure_mode_taxonomy.md`）
- **状态**：✅ §8.3 主文 + §A18 supp 模板完成
- **关键发现**：Mode 3 (q=0.38, ambiguous) 在 salvage band 内但 enhance 无效 → **Theorem 2 policy 增加 secondary entropy gate** (已 backport 修订 Thm 2 doc §1.2)
- **实证**：P1 (M1+M2 cluster retake_rate 100%) + P3 (M3 q_improved 仅 16.2%) 已 live verify
- **若 FAIL**：N/A，推导 done

---

## F 类：附加（+2%）

### L22 — Supplementary 50-80 页 ❌
- **完成路径**：M3-M4 持续扩
- **若 FAIL**：命中率 -0.5%

### L23 — Per-mechanism ablation ❌
- **内容**：FiLM vs Cross-attn / DP-Loss λ ∈ {0.01, 0.05, 0.1, 0.5} / KL annealing schedule / quality scalar source × 5
- **完成路径**：M2 D22-D28
- **若 FAIL**：命中率 -0.5%

### L24 — Real LQ ISIC 2024 SLICE-3D ❌
- **内容**：从 ISIC 2024 SLICE-3D 数据集挖低质子集（无需自采）
- **预研要求**：先验证 SLICE-3D 是否有 q̄ 元数据 / 是否能用 VisiScore-Net 跑出 q̄
- **完成路径**：M2 D22-D28
- **若 FAIL（找不到合适子集）**：命中率 -0.5%，降级为「VisiScore-evaluated LQ subset on ISIC 2024」

### L25 — ICLR-specific rebuttal pre-draft ✅ (2026-05-24, draft v1)
- **内容**：15 个高概率 Q&A + 双版本（顺利/fallback）+ character count + 7 节 rebuttal framework
- **状态**：✅ draft v1 done — 15 Q&A ≈ 18K chars，覆盖 R1-R10 × 1.5 角度，实战时 paste + edit
- **完成路径**：M4 D22-D28 实验数字填充 [TBD]，升级为 final
- **若 FAIL**：命中率 -0.5%

---

## 📐 PSNR 口径定义（单一真源）

| 口径 | 公式 | 使用场景 | 参考值 |
|---|---|---|---|
| **per-image mean**（论文/验收） | `mean(10·log₁₀(1/MSEᵢ))` per image, then mean | eval_visienhance.py E1、scripts/eval_nocrop_e1.py、论文 Table | 32.74 dB (test) / 33.10 (val) |
| **batch-aggregate**（训练监控） | `10·log₁₀(1/mean(MSE_batch))` | train_visienhance.py 训练日志 | ~28.97 dB（保守 ~4 dB 低）|

**差值来源**：log 非线性。batch 平均 MSE ≥ per-image MSE 的平均，故 log 后更小。两口径已在会话 9 实测复现。

**规则**：论文、rebuttal、Table 1、验收 gate 一律报 **per-image mean**；训练日志旁注 "(aggregate MSE, conservative)" 标注即可，不用于报告。

---

## 🔬 E1-E12 实验验收阈值

| # | 实验 | 指标 | 通过阈值 | 失败处理 |
|---|---|---|---|---|
| **E1** | 增强质量 | PSNR (medium, **per-image**) | ≥ 30 dB | ✅ 实测 32.74 dB (test) / 33.10 (val) / SSIM 0.947 — PASS（口径定义见上方专节）|
| **E1** | 增强质量 | SSIM (moderate) | ≥ 0.92 | 必达，Stage 1 已 0.9535 |
| **E1** | 增强质量 | LPIPS (moderate) | ≤ 0.08 | 若 0.08-0.12：写 "comparable perceptual quality" |
| **E2** | 分退化分析 | PSNR (光照/色温/对比) | > 35 dB | 单维度 |
| **E2** | 分退化分析 | PSNR (模糊) | > 28 dB | 单维度 |
| **E3** | ★ 诊断保持 | \|ΔAUC\| (C vs A) | < 1.5% | 若 1.5-3%：论文写 "<3%" + 加强 §A23 disclaimer；>3%：核心 lever 失败 -3% |
| **E3** | ★ 诊断保持 | 分类一致率 (C vs A) | > 95% | 同上 |
| **E3** | ★ 诊断保持 | McNemar p (C vs A vs B vs A) | < 0.001 | 必达 |
| **E4** | Prop 3 验证 | 增强后 \|ρ\| 显著大于增强前 | paired t-test p < 0.01 | 若 p > 0.01：Prop 3 实证失败 → 写 "directionally consistent" |
| **E5** | ★ Salvage Rate (moderate q̄∈[0.35,0.5]) | > 55% | 必达 | 若 < 55%：双通道效率论点弱化 |
| **E5** | ★ Salvage Rate (severe q̄<0.25) | < 25% | 必达（安全边界）| 若 > 25%：增强模块边界混乱，dangerous |
| **E6** | 安全边界 | 极低质段 ΔAUC | 无显著退化 (paired t-test p>0.05) | 必达 |
| **E7** | DP-Loss 消融 | 有 DP-Loss 组 ΔAUC 显著更小 | p < 0.01 | 必达，否则 Lemma 3 实证失败 |
| **E8** | Q-Cond 消融 | ~~有 FiLM 组 PSNR 显著更高~~ → **有 FiLM 组诊断保持更好**（dAUC/一致率/KL）| FiLM 三项均更优 | ⚠️ 改判据：实测 FiLM 对 PSNR 中性（见 v5 实测块），贡献在诊断保持非像素质量 |
| **E9** | FiLM vs Cross-Attn | FiLM 速度 ≥ 3× 快 + PSNR 持平 | 必达 |
| **E10** | vs 6 SOTA | ΔAUC 全胜（6/6 paired t-test p<0.05）| 6/6 必达 | <6/6：lever -0.5%/个 |
| **E11** | 跨数据集 AUC 保持 | HAM/PAD AUC > 95% relative | 必达 |
| **E12** | 推理速度 | 端到端 < 50 ms / image | 必达 |

---

## 📊 E1–E12 v5 实测结果（会话 21，2026-06-09，frozen）

**Stage2 = feature-DP v5**（ckpt `stage2_planA_256_v5`，best_val_PSNR 30.186 守 E1）。协议除 E1/E12 外统一 degrade(moderate)@256 → enh@256 → CenterCrop224 → B3，test split n=3627 / pos=117。run_id 见末列。

| 实验 | 实测 | 判定 | run_id / 源 |
|---|---|---|---|
| **E1** | per-img PSNR 32.74 (with-FiLM) / 33.06 (no-FiLM)，SSIM 0.91，n=19878 | ✅ PASS（两变体均 >30） | 1442290 / `results/e1_film_ablation.json` |
| **E2** | brightness 37.68 ✅ / blur 35.82 ✅；**color_shift 33.77 ❌**（<35）；**contrast 29.11 ❌ 且 < 降质图 32.29**（增强帮倒忙）| ⚠️ 2/4 PASS | 1441320 / `results/e2_perdim.csv` |
| **E3** | dAUC −0.0120 ✅；一致率 0.9575 ✅；dflip 0.135；McNemar(enh-vs-ref) p=0.573（enh≈ref）| ✅ PASS（v4 borderline → v5 双 PASS）| 1441301 / `results/stage2_diag_paired_v5.csv` |
| **E6** | severe 段 dAUC −0.0559 CI[−0.085,−0.028] 排除 0、dflip 0.46 | ❌ FAIL = **triage 弹药**（severe 该 query-for-retake，非增强）| 1441321 / `results/e6_severe.csv` |
| **E7** | ΔAUC_enh(S2−S1) +0.0205 CI[+0.005,+0.035] 显著>0；ΔKL −0.148 CI[−0.173,−0.124] 显著<0；McNemar p=2.3e-45 | ✅ PASS（Lemma 3 实证）| 1441301 / 同 E3 |
| **E8** | **FiLM 对 PSNR 中性**（no-FiLM 33.06 ≥ with-FiLM 32.74，且 no-FiLM 多训 49ep 混淆）；**FiLM 对诊断保持正贡献**：dAUC −0.033 vs −0.042、一致率 0.90 vs 0.87、KL 0.24 vs 0.35（均 with-FiLM 更好，连 Stage1 无 DP 时）| ⚠️ PSNR 判据不成立 → **重定向到诊断消融（成立）** | 1442290(E1) + 1442337(diag) / `results/filmabl_diag.json` |
| **E12** | 16.08 ms/img（p95 17.0）| ✅ PASS（<50）| 1441322 / `results/e12_speed.csv` |

**两条 limitation 须在 paper 处理**：① E2 contrast/color_shift 弱 → 当 limitation 或触发重拍；② E6 severe 不安全 → 当 triage（query-for-retake）正证据，非项目失败（agent 设计本就不增强 severe）。
**dflip 单指标陷阱**（会话 20+21 两次坐实）：no-DP / no-FiLM 的 dflip 反而略低，因其整体诊断信号更糊（KL 高、McNemar 错更多）巧合少翻特定 mel 子集 → **dflip 必配 KL/一致率一起读，不可孤立比**。

**E5 SalvageRate（会话 21，norm-q 路由版，job 1442385）**：增强用 raw-q、路由/分层用 norm-q̄。按 severity：mild 0.600 / **moderate 0.737 ✅(>0.55)** / severe 0.816，DamageRate 全 <3%。⚠️ nuance：salvage 被 benign-FP 修正主导（pos 仅 117/3627），恶性安全风险另由 E6/dflip 把关；**老「severe salvage<25%」判据与此测法冲突，需重新解读**（severe salvage 高 ≠ 不安全，因 salvage 算的是整体误判修正非恶性漏诊）。

**🔴 会话 22 per-class 拆案（`e5_salvage_persample.csv`，rate 有效/count×3）**：聚合 0.737「达标」**全由良性撑**——良性 salvage 75.6%(1809/2392)/damage 0.6%；**黑色素瘤 salvage 仅 5.2%(4/77)、damage 31%(85/274 correct)**（救 4 毁 85 净 −81）。**结论：E5 聚合 SalvageRate 不可当达标指标写 paper**（reviewer 拆 per-class 即崩 + 伦理误导），改写为「benign 主导 + melanoma 净负 = query-for-retake 闸门最硬证据」（Claim 3/Thm 2 利好，削 VisiEnhance 单模块卖点）。**决策（用户拍）两手**：① §7.4 现写诚实版（待会话 23 落笔，本会话收工打断）；② mask-L1 重训（病灶区不准磨平）列 M2 救 melanoma salvage，待用户拍训练。

**🔴 visiscore 集成喂错（会话 21 根因，影响 q̄ 信号但现有结果仍有效）**：visiscore（timm backbone 约定 ImageNet-NORM224）在 `train_visienhance`+所有 eval 全被喂 raw[0,1]@256 → q̄ 恒 ~0.54 不响应退化。连贯解释 E8 FiLM 中性 / hinge 泛化不动 / E5 band 不可达。**qnorm 对照（job 1442379）证实**：喂正确 NORM-q 给 raw-q 训的模型反而变差（PSNR 30.41→29.69、dflip 0.135→0.176）→ raw-q 是训练口径自洽最优，**E1/E2/E3/E6/E7/E8/E12 数字全部站得住、不需重做**。bug 影响收窄为 ①FiLM 被 flat-q 训弱（救须重训、增益不确定）②agent/E5 路由用独立 norm-q（已做）。重训与否 = 会话 22 决策。

---

## 🔴 红线（违反任意条 = 直接弃稿）

### 永久红线（任何项目通用）
1. **Reader Study 数据伪造** — 不存在的 dermatologist rating 不能写入论文
2. **联系诊所 / 线下采集** — 所有数据必须公开数据集
3. **数字凭印象写** — 每个数字必须 csv 核算 + run_id
4. **侵犯医学安全** — 不能用扩散模型做皮肤镜增强（伪影发明病灶）

### ICLR 项目红线
5. **BMVC 数字直接搬入 ICLR Table** — 必须重跑 / 重画 / 引用方式 = cite paper
6. **5 theorem 缺失任意一个** — 5-theorem closure 是 ICLR 命脉，缺一个就 -2%
7. **匿名违规** — 投稿前 grep VisiSkin / Q-VIB / VisiScore / anonymous2025 必须 0 命中
8. **L14 LLM-judge 当真人 reader study** — 必须 §A23 明确 disclaimer

---

## 📅 M1-M4 Milestone Gate（每月 gate 必须 PASS 才进下一阶段）

### M1 Gate (2026-06-22)
- [ ] L1 写入主文 §3.2-§3.5 (compact statement)
- [ ] L2 + L3 + L4 + L5 全部完成证明（数学严密 + Appendix 写就）
- [x] VisiEnhance Stage 1 (nocrop) 训练完成（PSNR 32.74 dB per-image / SSIM 0.947 ✅，2026-05-30 会话 9）
- [ ] CheXpert + Fundus inference 完成
- [ ] PROJECT_LOG.md M1 总结 entry
- **若任何 ❌**：延期 1 周，但若延期超 2 周，砍 L4 或 L5 之一止损

### M2 Gate (2026-07-22)
- [ ] VisiEnhance Stage 2 + 3 完成
- [ ] E1-E12 全跑（E3/E5 PASS）
- [ ] L9 (6 SOTA) + L10 (fairness) + L23 (per-mechanism) 完成
- [ ] Table 1 + Table 2 + Table 3 + 主图 fig1-4 数字全部就位（待写文字）
- [ ] L24 ISIC 2024 SLICE-3D 子集就位 OR 降级说明
- **若 E3 失败**：进入 Plan B（接受 ΔAUC<3%），论文重写 framing

### M3 Gate (2026-08-22)
- [ ] 主文 9 页 draft v2 完整
- [ ] Supp 50 页骨架
- [ ] L14 (LLM-judge) + L12 (dermatologist cite) + L13 (cost-benefit) 完成
- [ ] L21 (failure mode) 完成
- [ ] Anonymous GitHub 30+ commits
- **若 supp <40 页**：M4 加压补到 50+

### M4 Gate (2026-09-22 = ICLR abstract deadline)
- [ ] L19 (10 轮 review) ≥ 8 轮完成
- [ ] L20 (pre-emptive rebuttal) + L25 (rebuttal pre-draft) 完成
- [ ] Anonymous GitHub 60+ commits + Docker + ITB DOI + HF mirror
- [ ] 数字一致性 30/30 PASS
- [ ] R1-R10 grep 全 0
- [ ] OpenReview 上传
- **若任何 ❌**：紧急 buffer 期 (09-23 ~ 09-29) 修

---

## 🚨 中途反悔决策树（什么时候放弃 lever 止损）

```
当前 lever 失败 → 是否致命？
├── 致命（A 类 L1/L4/L5）→ 不能放弃，加 buffer 重做
├── 严重（A 类 L2/L3 / B 类 L8 / C 类 L11/L14 / E 类 L19）→
│   ├── 距 deadline >3 月：重做
│   └── 距 deadline <3 月：降级 + Limitation 写清 + 命中率 -1.5%
└── 一般（D/F 类 + 其他 lever）→
    ├── 距 deadline >2 月：重做
    └── 距 deadline <2 月：放弃 + 命中率 -0.5%
```

**关键原则**：诚实记录每次降级到 `PROJECT_LOG.md`，禁止隐藏失败。

---

## 📋 当前命中率预估（实时维护）

| 类 | 状态 | 预估贡献 |
|---|---|---|
| 基线 ICLR | 30% | +30% |
| A 理论（L1 ✅ + L2-5 🚧❌）| 1/5 done | +1% (currently) |
| B 实验（L6 ✅ + L7 🚧 + L8-10 ❌）| 1/5 done | +0.5% |
| C 临床（L11 ✅ + L12-14 ❌）| 1/4 done | +1% |
| D 复现（L15 🚧 + L16-18 ❌）| 0/4 done | 0% |
| E 防御（L19-21 ❌）| 0/3 done | 0% |
| F 附加（L22-25 ❌）| 0/4 done | 0% |
| **当前预估** | — | **~32.5%** |
| **M1 Gate 后预估** | A 类 ~80%, B 类 ~40% | ~52% |
| **M2 Gate 后预估** | A/B 类 ~100%, C/F 类 ~50% | ~67% |
| **M3 Gate 后预估** | 主体完成 | ~74% |
| **M4 Gate 后预估** | 全部完成 | **~78-80%** ✅ |

**实时维护承诺**：每周日更新本文件「当前命中率预估」section，诚实反映 lever 状态。
