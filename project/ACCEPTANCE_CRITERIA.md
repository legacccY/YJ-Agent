# 唯一论文验收标准 — C0-C3 论点判据

**论文**：D+A 系统论文 —— Safe diagnosis-preserving enhancement of degraded dermoscopy, and when to defer instead
**会场**：MICCAI 2027（~2027-02）首选 / TMLR（滚动、明文不要 SOTA、容诚实负结果）备
**最后更新**：2026-06-17（会话 41，随 STORY 重构整篇重写）
**适用范围**：每个论点 / 实验 / milestone 完成判定的唯一标准
**配套**：与 `STORY_FRAMEWORK.md`（同日重写）C0-C3 框架一一对应；最高准绳 = `project/ICLR_重构计划_拆两篇_2026-06-17.md` §2。

> ⚠️ **本文件已整篇重写**。旧版「78-80% 命中率 / 25-lever（L1-L25）」框架**已全部作废**：含 Q-VIB SOTA 的 L1、含 Q-VIB-supremacy 的 L6/L7/L8、命中率分解表、含 0.707 的 Table、M1-M4 Q-VIB milestone 全删。会场不再冲 ICLR SOTA，改 MICCAI 2027 / TMLR，验收按论文质量门槛而非命中率百分比。

> ⚠️ **不存在「基本完成」**。每条验收阈值要么 PASS 要么 FAIL。FAIL 必须在 `PROJECT_LOG.md` 写诚实记录，按需降级 framing（不藏失败）。

---

## 🎯 论点验收总览（C0-C3，对应 STORY 四论点）

| 论点 | 角色 | 不可缺性 | 实证状态 |
|---|---|---|---|
| **C0** 可靠性 × 可恢复性决策面 | 动机章（BMVC-free 刻画）| 论文动机基石 | 🚧 待出逐维 × severity AUC 网格 + 可恢复性叠层（数据已有）|
| **C1** DP-Loss + MI 下界 | 最硬主腿 | **不可缺**（论文核心贡献）| ✅ E7/E3/E10 PASS + Lemma3 toy PASS |
| **C2** query-for-retake agent | 独家钩子 | **不可缺**（文献首次采集闭环）| 🚧 4 通道实现收尾 + Thm2 降格落 tex |
| **C3** 诚实边界 | 闸门动机 + 可信度 | **不可缺**（诚实墙）| ✅ E6/E5 per-class/v6 null 全 done |

**主腿不可缺原则**（取代旧「5-theorem-closure 缺一 -2%」）：**Prop3 / Lemma3 / Thm2 是增强+决策这条主腿的理论支撑，三者缺任一则论文理论骨架塌**。Q-VIB 相关定理（Prop1/Lemma1/Thm1/Prop2）退 supp 当框架，缺失不致命。

---

## C0 — 可靠性 × 可恢复性决策面（动机章，BMVC-free，会话 41 reframe）

> **reframe 缘由**：原 C0「纯退化曲面」撞 BMVC supp 的 `table_perdeg_qcts`（逐维 **ECE** × Std VIB±QCTS，4 维无 completeness，无 severity 扫描，`itb_supp.tex` L615 确有 \input）。计划文档 §3 拍板 A：C0 改走 BMVC 没碰的角度 —— **主轴诊断 AUC（非 ECE）+ 逐维 × severity 二维网格 + completeness 第 5 维 + 可恢复性轴**。C0 仍是**动机章不当 contribution**。

### C0.1 — 可靠性轴：逐维 × severity 诊断 AUC 网格 🚧
- **内容**：模糊 / 亮度 / 完整度 / 色温 / 对比 5 维，每维 × severity 多档，画出**主轴诊断 AUC**（不用 ECE 当主轴 —— 逐维 ECE 是 BMVC `tab:perdeg` 占的角度）的二维网格。
- **severity 档位**：5 档锚 ImageNet-C severity 1-5 惯例 + 每维物理量纲连续轴（blur=σ / brightness=乘子 / contrast=α / color=偏移 / completeness=crop_ratio）；档位 = 量纲等距采样，从现有 `data/degrade.py` light/medium/heavy 三档物理外插（**禁凭印象拍档位**，确切数值 `\todo{核 degrade.py}`，§3.1 列数值表）。
- **completeness（q3）第 5 维**：定义为「视野截断比例」连续轴，severity=crop_ratio；措辞写 **"partially recoverable" 不写 "irreversible"**（与 R1 防绝对化一致）。
- **验收**：
  - (a) 5 维 × severity 诊断 AUC 网格图出齐（每维一条曲线，severity 物理量纲单调轴）。
  - (b) 可读出明确趋势「质量降 → 可靠性崩」（AUC 随 severity 单调下降，至少多数维度成立；不单调的维度如实标注）。
  - (c) 每个网格点配 bootstrap 95% CI（R6）。
- **数据**：用现有 ImageNet-C / 退化产物重算逐维 × severity。
- **若 FAIL**：动机章弱化，降级为「质量退化对可靠性有非平凡影响」的定性陈述。
- **写入位置**：§3.2 主文 + Appendix A4 完整网格表。
- **红线**：用 AUC 当主轴避撞 BMVC；引用 BMVC `tab:perdeg`（ECE+QCTS 角度）做明确区分，**不搬表**（R10）。

### C0.2 — 可恢复性轴：增强能否救回诊断 🚧（桥 C1+C3）
- **内容**：在 C0.1 的每个退化点上叠加第二轴「增强能否把诊断救回」—— 用 C3 已有数据（E5 救援净负 / E6 severe 伤诊断）标注哪些退化点可恢复、哪些不可。增强 BMVC **一字没有** → 天然 BMVC-free，且把 C0 直接桥到 C1（增强）+ C3（边界）。
- **验收**：(a) 可恢复性叠层与可靠性网格对齐成「决策面」；(b) 可读出「moderate 退化可救（C1 窗口）/ severe + melanoma 不可救（C3 闸门）」分区，与 E6（severe dAUC −0.056 排除 0）/ E5（melanoma 救 4 毁 81）一致。
- **⚠️ 会话 42 C0 实测澄清（per-dimension vs per-class 两切面，互补不矛盾，必读）**：(b) 的「不可救」分区由 **per-class** 数据（E5 melanoma 净负 / E6 severe 混合段）承载，**仍成立**。但 `c0_decision_surface.csv` 的 **per-dimension** 切面（沿单轴 × severity 的 AUC 可恢复性，n=360/cell，verifier PASS）显示 **severe 不普遍不可救** —— 全 25 cell 仅 contrast S5（α=0.19）一处 recoverability_delta −0.0355 CI[−0.0783,−0.0013] 显著 HURT；blur S5 / color_shift S5 增强仍正效益（救得回）。故 §3/§7.1 **严禁泛化「severe 退化增强普遍伤诊断」**，per-dimension 层只点名 contrast 极端档为 query-for-retake 补充触发点，**不替代、不与 E5/E6 per-class 混淆**。详见 `STORY_FRAMEWORK.md` 锁定数字「C0 决策面」块的「C3 措辞订正（强制）」条款。
- **数据**：复用 C3 的 `results/e6_severe.csv` + `results/e5_salvage_persample.csv`（per-class 分区）+ `results/c0_decision_surface.csv`（per-dimension 网格，会话 42 全量），不另跑。
- **若 FAIL**：可恢复性轴退为定性分区描述。
- **写入位置**：§3.3 主文。

### C0.3 — 多方法 UQ 不差异化（次要观察，可选）🚧
- **内容**：多个 UQ 方法（MC Dropout / Deep Ensemble / EDL / Std VIB 等）在退化下彼此**无显著差异**（BMVC 逐维只 1 方法 Std VIB，可深化）。
- **验收**：方法两两配对检验，差异 bootstrap 95% CI **含 0**（即不可区分）。
- **处置**：作动机章次要观察，**或**留给负结果兜底短文（ICBINB / ML4H Findings）。非主腿，缺失不致命。
- **红线**：BMVC 没当卖点的角度才深化；不搬 BMVC 的 LQ/HQ 表。

---

## C1 — DP-Loss + 互信息下界（最硬主腿，不可缺）

### C1.1 — E7 DP-Loss 消融（Lemma 3 实证）✅ PASS
- **内容**：有 DP-Loss 组 vs 无 DP-Loss 组，诊断保持显著更好。
- **验收**：ΔAUC_enh(S2−S1) 显著 > 0（p<0.01）+ ΔKL 显著 < 0 + McNemar p<0.001。
- **实测**：✅ **PASS** —— ΔAUC **+0.0205 CI[+0.005,+0.035]**、ΔKL **−0.148 CI[−0.173,−0.124]**、McNemar **p=2.3e-45**（run_id 1441301，`results/stage2_diag_paired_v5.csv`）。
- **写入位置**：§7.3 主文 + §4.3（Lemma 3 实证）。
- **若 FAIL**：Lemma 3 失去实证，C1 主腿塌 → 论文核心贡献失效，不可放弃，加 buffer 重做。

### C1.2 — E3 诊断保持 ✅ PASS（双 PASS）
- **验收**：|ΔAUC|(C vs A) < 1.5% + 分类一致率(C vs A) > 95% + McNemar p（enh-vs-ref）报告。
- **实测**：✅ **双 PASS** —— dAUC **−0.0120**、一致率 **0.9575**、dflip 0.135、McNemar(enh-vs-ref) p=0.573（enh≈ref）（run_id 1441301）。
- **失败处理**：若 |ΔAUC| 1.5-3% → 论文写「<3%」+ 加强 disclaimer；>3% → C1 主腿失败，重做。
- **写入位置**：§7.2 主文。

### C1.3 — Lemma 3 / Prop 3 理论 ✅（推导 + toy PASS）
- **内容**：Lemma 3 $\mathcal{L}_{\text{DP}} \leq \epsilon \implies I(Z_{\text{enh}};Y) \geq I(Z_{\text{ref}};Y) - \beta\sqrt{\epsilon}$（$\beta\approx0.74$ binary，$\sqrt{\epsilon}$ Pinsker-optimal）；Prop 3 增强降熵充分条件。
- **验收**：推导严密（显式假设 + step proof）+ toy 数值验证 PASS。
- **实测**：✅ 推导 done（`plans/Prop3_Lemma3_visienhance_theory.md`）+ `tests/test_theorems_numerical.py::test_lemma3_pinsker_* / test_proposition3_*` PASS。
- **⚠️ Prop 3 承载方式**：E4/E4Q 实证 FAIL（增强后熵不降，方向相反），**Prop3 改由 E7（Lemma 3 MI 下界实证）+ PSNR≥30 非空性条件承载**，E4 不入 paper。
- **写入位置**：§4.3 主文 + Appendix A1 完整证明。
- **写作红线**：用「we derive / under assumption」不用「we prove」（R2）。

### C1.4 — E10 vs 6 SOTA enhancement ✅ PASS（6/6）
- **内容**：vs Restormer / NAFNet / MIRNet-v2 / SwinIR / Uformer-B / Real-ESRGAN（**禁扩散红线**，无 DiffBIR）。
- **验收**：在 ΔAUC（诊断保持）上 VisiEnhance 显著优于所有 6 个（paired，CI 排除 0 / McNemar p<0.05）。
- **实测**：✅ **6/6 PASS** —— paired ΔAUC(baseline−VE)∈[−0.12,−0.07] 全 CI 排除 0、McNemar p 全 <1e-150、PSNR 32.79 vs 13-22（job 1448952，main.tex tab:e10）。
- **写入位置**：§7.5 主文。

### C1.5 — 增强质量 + 架构辅助证据
- **E1 增强质量** ✅ PASS：per-image PSNR **32.74** dB（>30）、SSIM 0.91（口径见专节）。
- **E8 FiLM 消融** ⚠️ 改判据：FiLM 对 PSNR **中性**（不卖 PSNR 增益），卖点定位**诊断保真**（dAUC −0.033 vs −0.042 / 一致率 0.90 vs 0.87 / KL 0.24 vs 0.35，均 with-FiLM 更好）。
- **E9 FiLM vs cross-attn** ✅：统计无法区分（paired bootstrap ΔAUC CI 含 0、McNemar p=0.679），FiLM 以 parsimony 胜（−1.8M 参数），保留 FiLM。
- **E12 速度** ✅ PASS：16.08 ms/img（<50）。
- **E2 分退化** ⚠️ 2/4 PASS：brightness/blur PASS，color_shift/contrast FAIL → 当 limitation 或触发重拍。

---

## C2 — query-for-retake agent（独家钩子，不可缺）

### C2.1 — 4 通道决策逻辑实现 🚧
- **内容**：direct diagnosis / cautioned diagnosis / enhance-then-diagnose / query-for-retake 四通道，质量分级阈值路由（Qwen3-4B ReAct + rule fallback）。
- **验收**：(a) 4 通道决策逻辑可运行；(b) 阈值规则明确（基于 per-input quality scalar）。
- **写入位置**：§5.1 + §5.3 主文 + Appendix A5（实现细节 + ReAct trace）。
- **写作红线**：agent **不诊断**，它决策何时诊断/增强/追问（STORY C2）；retake = 反馈重新采集，**不等同 abstain/defer**。

### C2.2 — query-for-retake 通道在低质段触发率高 ✅（实证弹药）
- **验收**：retake 通道在 severe / 低质段触发率显著高于高质段。
- **实测**：✅ P1 cluster q<0.35 **retake_rate=100%**（已 verified，会话 L19 deliverable）。
- **写入位置**：§5.1 + §7.8。

### C2.3 — Theorem 2（降格判据，🔴 skeptic 致命攻击必守）
- **内容**：agent risk bound，**降格**为局部条件界。
- **🔴 验收（三段，缺一即 FAIL）**：
  1. **局部条件界成立**：增强收益 $\Delta(\bar{q}, T_\omega) > 0$ **仅在区间 $\bar{q}\in[\tau_{\text{enh}}, \tau_{\text{high}}]$ 内**成立（moderate 退化窗口），区间外不成立。toy 验证：`tests/test_theorems_numerical.py::test_thm2_*` PASS + bootstrap CI（区间内）排除 0。
  2. **全局诚实负结果如实报**：固定阈值下全局 triage **当前不优于 Direct**，主动认负。实证 = §7.7 DCA（见 C2.4）。
  3. **threshold-learning 留 future work**。
- **🔴 严禁**：claim「$\mathcal{R}_{\text{agent}} \leq \mathcal{R}_{\text{direct}}$ 全局成立」—— r4 实证 Direct B3 sens **0.818 > agent 0.788**，与 §7.7 自相矛盾（STORY R11）。
- **写入位置**：§5.2 主文 + Appendix A2。
- **若 FAIL（写成全局界）**：直接跑偏，与诚实墙冲突，必改。

### C2.4 — DCA + triage（诚实负结果，支撑 Thm2 降格）✅
- **验收**：(a) 净收益四法 95% CI 报告；(b) triage@20% 各法 sens 报告；(c) 主动认负声明。
- **实测**：✅ ITB-LQ n=300 四法净收益 95% CI **全重叠 0.179–0.192**（不可区分）、triage@20% **Direct sens 0.818 最优**、最强变体 Q-VIB+TokFT **0.788 仍不超 Direct**（`results/dca/*` + `report/figures/fig_dca_triage.*`）。
- **写作红线**：写「we make no claim that triage raises net benefit globally」（R3）；不搬 BMVC 的 DCA 原表（R10）。
- **写入位置**：§7.7 主文。

---

## C3 — 诚实边界（闸门动机 + 可信度，不可缺）

### C3.1 — E6 severe 段增强伤诊断 ✅ PASS
- **验收**：severe 段 ΔAUC 显著 < 0（CI 排除 0）→ 坐实「severe 该 query-for-retake，非增强」。
- **实测**：✅ **PASS** —— severe 段 dAUC **−0.0559 CI[−0.085,−0.028] 排除 0**、dflip 0.46（run_id 1441321，`results/e6_severe.csv`）。
- **框法**：这是 query-for-retake 闸门的正证据，**非项目失败**（agent 设计本就不增强 severe）。
- **写入位置**：§7.8 主文。

### C3.2 — E5 per-class melanoma 救援净负（最硬证据）✅ 如实报
- **验收**：per-class 拆案如实报告，**不得**用聚合 SalvageRate 0.737 当达标指标。
- **实测**：聚合 moderate 0.737 **全由良性撑**（benign 75.6% 1809/2392）；**melanoma salvage 仅 5.2%（4/77）、damage 31% → 救 4 毁 81 净 −81**（`results/e5_salvage_persample.csv`，会话 22 拆案）。
- **🔴 红线**：**禁**把 E5 聚合 0.737 写成达标（reviewer 拆 per-class 即崩 + 伦理误导）。改写为「benign 主导 + melanoma 净负 = query-for-retake 闸门最硬证据」。
- **写入位置**：§7.4 主文 + Appendix A7。

### C3.3 — v6 mask-L1 null（诚实负结果）✅ 如实报
- **验收**：mask-weighted L1 重训对 melanoma salvage 的影响如实报。
- **实测**：melanoma salvage **5.2%→5.2% 纹丝不动**、net −81→−79（噪声）→ 重构损失加权救不了恶性救援缺口（failure mode 是 per-pixel L1 够不着诊断决策边界）（`results/e5_salvage_v6_persample.csv`）。
- **框法**：诚实负结果，强化 query-for-retake gate 是真安全机制。
- **写入位置**：§7.4 主文。

---

## 📐 PSNR 口径定义（单一真源，保留）

| 口径 | 公式 | 使用场景 | 参考值 |
|---|---|---|---|
| **per-image mean**（论文/验收）| `mean(10·log₁₀(1/MSEᵢ))` per image, then mean | 论文 Table / 验收 gate / E1 | 32.74 dB (test) / 33.10 (val) |
| **batch-aggregate**（训练监控）| `10·log₁₀(1/mean(MSE_batch))` | 训练日志 | ~28.97 dB（保守 ~4 dB 低）|

**差值来源**：log 非线性，batch 平均 MSE ≥ per-image MSE 的平均，故 log 后更小（会话 9 实测复现）。
**规则**：论文 / rebuttal / Table / 验收 gate 一律报 **per-image mean**；训练日志旁注「(aggregate MSE, conservative)」即可。

---

## 🔬 E1-E12 v5 实测阈值表（判据弹药，frozen 会话 21）

**Stage2 = feature-DP v5**（ckpt `stage2_planA_256_v5`，best_val_PSNR 30.186 守 E1）。协议除 E1/E12 外统一 degrade(moderate)@256 → enh@256 → CenterCrop224 → B3，test split n=3627 / pos=117。

| 实验 | 实测 | 判定 | run_id / 源 |
|---|---|---|---|
| **E1** | per-img PSNR 32.74(with-FiLM) / 33.06(no-FiLM)，SSIM 0.91，n=19878 | ✅ PASS（两变体 >30）| 1442290 / `results/e1_film_ablation.json` |
| **E2** | brightness 37.68 ✅ / blur 35.82 ✅；color_shift 33.77 ❌(<35)；contrast 29.11 ❌（< 降质 32.29）| ⚠️ 2/4 PASS | 1441320 / `results/e2_perdim.csv` |
| **E3** | dAUC −0.0120 ✅；一致率 0.9575 ✅；dflip 0.135；McNemar p=0.573 | ✅ 双 PASS | 1441301 / `results/stage2_diag_paired_v5.csv` |
| **E5** | 聚合 moderate 0.737 不可达标；per-class benign 75.6%、melanoma 5.2%(4/77) 救 4 毁 81 | C3 诚实负 | `results/e5_salvage_persample.csv` |
| **E5 v6** | melanoma salvage 5.2%→5.2% null、net −81→−79 | C3 诚实负 | job 1442696/1444753 / `results/e5_salvage_v6_persample.csv` |
| **E6** | severe dAUC −0.0559 CI[−0.085,−0.028] 排除 0、dflip 0.46 | ✅ C3 弹药（query-for-retake 动机）| 1441321 / `results/e6_severe.csv` |
| **E7** | ΔAUC +0.0205 CI[+0.005,+0.035]、ΔKL −0.148 CI[−0.173,−0.124]、McNemar p=2.3e-45 | ✅ PASS（C1 Lemma 3 实证）| 1441301 / 同 E3 |
| **E8** | FiLM 对 PSNR 中性；诊断保持正贡献 dAUC −0.033 vs −0.042 / 一致率 0.90 vs 0.87 / KL 0.24 vs 0.35 | ⚠️ 卖点定位诊断保真 | 1442290+1442337 / `results/filmabl_diag.json` |
| **E9** | paired ΔAUC +0.0016 CI[−0.0057,+0.0086] 含 0、ΔKL 含 0、McNemar p=0.679 → 无法区分；FiLM parsimony 胜 | ✅ 保留 FiLM | 1444849/1448254 / `results/stage2_diag_paired_e9.csv` |
| **E10** | 6/6 显著优：paired ΔAUC∈[−0.12,−0.07] 全 CI 排除 0、McNemar p<1e-150、PSNR 32.79 vs 13-22 | ✅ 6/6 PASS | 1448952 / main.tex tab:e10 |
| **E12** | 16.08 ms/img（p95 17.0）| ✅ PASS（<50）| 1441322 / `results/e12_speed.csv` |

> **E4 不入 paper**：E4/E4Q 实证 FAIL（增强后熵不降，方向与 Prop3 相反）→ Prop3 改由 E7 + PSNR≥30 非空性承载。
> **dflip 单指标陷阱**：no-DP/no-FiLM 的 dflip 反而略低（整体信号更糊巧合少翻特定 mel 子集）→ dflip 必配 KL/一致率读，不可孤立比。

---

## 🔴 红线（违反任意条 = 直接弃稿）

### 永久红线（任何项目通用）
1. **Reader Study 数据伪造** —— 不存在的 dermatologist rating 不能写入论文。
2. **联系诊所 / 线下采集** —— 所有数据必须公开数据集。
3. **数字凭印象写** —— 每个数字必须 Bash/Grep 核 csv + run_id（不信 Read）。
4. **侵犯医学安全** —— 不能用扩散模型做皮肤镜增强（伪影发明病灶）。

### 本论文项目红线
5. **从 BMVC 提交版搬表 / 搬数 / 搬图** —— 被占四维度（跨域 ρ / ImageNet-C 18 腐蚀 / 5 backbone / DCA 全表）一律只 cite（BMVC 录用公开后才能引）。
6. **主腿理论缺失** —— **Prop3 / Lemma3 / Thm2 是增强+决策主腿，缺任一论文理论骨架塌**（取代旧「5-theorem-closure 缺一 -2%」；Q-VIB 那几个退 supp 当框架，缺失不致命）。
7. **claim Q-VIB 有方法增益 / 是更强诊断器** —— r1/r2/r3 三个 FAIL csv 钉死，Q-VIB 仅作脚注。
8. **Thm2 写成全局界** —— 必须降格为局部条件界 + 诚实全局负结果（r4 Direct 0.818 > agent 0.788）。
9. **E5 聚合 SalvageRate 0.737 当达标指标** —— per-class 拆案即崩 + 伦理误导，必须诚实负结果。
10. **匿名违规** —— 投稿前 grep VisiSkin / Q-VIB / VisiScore / anonymous2025 / VisiEnhance 必须 0 命中（脱敏）。

---

## 🚨 诚实降级原则（保留）

**关键原则**：诚实记录每次降级到 `PROJECT_LOG.md`，禁止隐藏失败。

```
当前判据 FAIL → 是否致命？
├── 致命（C1 主腿 E7/E3 / C2 Thm2 写成全局界 / C3 诚实墙被违反）→ 不能放弃，加 buffer 重做 / 改回诚实
├── 严重（C0 决策面 / C2 agent 实现 / C1 理论 toy）→
│   ├── 距 deadline >3 月：重做
│   └── 距 deadline <3 月：降级 + Limitation 写清
└── 一般（C0.3 次要观察 / E2 分退化 / 复现性附加）→
    ├── 距 deadline >2 月：重做
    └── 距 deadline <2 月：放弃 + Limitation 写清
```

**会场提醒**：MICCAI 2027（8 页，5 定理压进 supp）/ TMLR（无 deadline、不要 SOTA、容诚实负结果，本科生作者无劣势）。验收按论文质量门槛判，不再用 78-80% 命中率百分比。

---

## 🪦 删掉的旧判据（不复活，与 STORY 一致）

- **L1 Q-VIB 4 定理 SOTA lever** + L6/L7/L8 含 Q-VIB-supremacy 的实验 lever。
- **25-lever（L1-L25）命中率分解 + 78-80% 目标 + 命中率扣分规则**。
- **含 0.707 的 Table 1**（幽灵数，弃用）。
- **5-theorem-closure 缺一 -2%**（改为「Prop3/Lemma3/Thm2 主腿不可缺」）。
- **M1-M4 Q-VIB milestone gate**（会场改 MICCAI/TMLR，按质量门槛验收）。
- **E5 聚合 SalvageRate>55% 当达标**（改诚实 per-class 负结果）。
