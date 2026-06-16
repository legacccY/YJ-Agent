# MedSeg-UQ 项目 LOG

> 索引见 `00_选题调研_2026-06-16.md`。理论框架见 `02_理论框架.md`。

---

## 2026-06-16 — 立项前调研 + ★1 理论骨架启动

**做了什么**
1. **8 路 researcher 并行调研**（应用 4 + 理论 4），产出选题矩阵（T1-T6）+ 文献矩阵（5 族带引用）+ 理论深挖矩阵（★1-★6 排行）+ 导师王水花画像 → 全在 `00_选题调研`。
2. **定向**：用户拍方向 = ★1（Calibration–Dice trade-off 下界）为主、★2（最优聚合算子）保留；会场 = 纯顶会（CVPR/ICLR/NeurIPS）。
3. **★1 防撞车检查**（researcher 穷举 2020-26）：判定**真空白**。最接近=mL1-ACE 实证称 "inherent tension" 无定理；RankSEG 定义 Dice-calibration 但未证 calibration 下界；信息论不可能定理仅分类非分割。
4. **★1 理论框架 `02_理论框架`**：形式化设定（逐像素 p(x)、歧义质量 m_δ、smCE、Dice）+ 三步证明骨架（Lemma1 Dice偏好硬决策 / Lemma2 sharp⟹miscalibrated / 主定理 Dice≥α⟹smCE≥Φ(α;m_δ)）。
5. **P0 玩具命题亲推走通**：p=1/2 歧义区 + sharpening s，证 **smCE(f) ≥ m·s**（构造 1-Lipschitz g*=−1@v₀），两端退化（s=0 / m=0 → 0）都过。验证 g* 构造法 work。
6. **Opus 核原文**（主源验证，红线，**两篇全核到**）：
   - RankSEG [2206.13086]：Thm1 Dice-Bayes=ranking top-τ* 规则、Remark2 固定阈值次优、Def8/Lemma9 CE/focal 非 Dice-calibrated → 精化 Lemma1。
   - Błasiok [2211.16886]（ar5iv 主源）：§7 smCE=sup_{w∈1-Lipschitz[0,1]→[−1,1]} E[w(v)(y−v)]，与 P0 逐字一致；一致性 **½·d̲CE ≤ smCE ≤ 2·d̲CE**（Def5.1）→ **P0 下界传到真·ℓ1 校准距离 d̲CE ≥ ½·m·s，结论变强，不依赖度量选择**。
   - （firecrawl 额度爆，改用 WebFetch ar5iv + themoonlight 二手交叉，均确认。）

**结论**：★1 真空白可推进；证明主线（aleatoric 歧义驱动 trade-off）自洽且 P0 内核已证；解释 mL1-ACE 实证方向（歧义大的 BraTS 损 Dice 最多、KiTS 几乎不损）。

**7. P1 + P2 主定理亲推（核心推理，已完成骨架）** — 见 `02_理论框架` §3.6/§3.7：
   - **P1（已证）**：large-image 极限 population soft-Dice 下，校准预测器的 soft-Dice 上确界 = **𝔇_cal\*=E[p²]/E[p]**（Cauchy–Schwarz，等号 f=p）；与上限 1 的头空间 = **E[p(1−p)]/E[p] = 归一化 aleatoric 不确定性**。
   - **P2（骨架已推）**：两条无条件 smCE 下界（w=v / w=1）+ soft-Dice Lipschitz（引理2.1，4Δ/c）+ d̲CE≤2smCE 找附近校准 g（引理2.2）⟹ **smCE(f) ≥ (E[p]/8)(𝔇(f)−E[p²]/E[p])**，即 **Φ(α)=(1/8)(α·E[p]−E[p²])**，d̲CE 同阶。
   - 性质：Φ>0 ⟺ α>𝔇_cal\*；确定数据 Φ=0（无 trade-off）；常数 8 宽松可改。
   - **意义**：首个把「Dice 超出校准最优量」下界到校准误差的形式化定理，头空间 = aleatoric，机制清晰。对上 mL1-ACE 实证（BraTS 损最多/KiTS 不损）。

**结论更新**：理论侧 Gate0 可证部分（P0/P1/P2 骨架）**已过**。

**8. reviewer(opus) 对抗审稿 + 据此修复（关键质量门）**
- 审稿结论：**1 致命 + 6 major**。致命=旧引理 2.2（Błasiok d̲CE coupling 找校准 g 代入 Dice 泛函）—— coupling 的 g 在扩展空间无原始 p(x)，E[g·p] 无意义，hand-wave 走不通；A1（large-image 极限）把 U-statistic 难点假设掉、小前景 regime 最不成立；P1 在 A1 下是 Bröcker/DeGroot-Fienberg refinement 分解换皮；引理1.2 等号归因错；引理2.1 常数应 3 非 4；smCE↔ECE 仅多项式等价（overclaim）；P0 只证半边。
- **已修**（02 全面改）：① 致命洞 → 原空间条件均值重标定 **g=E[p|f]**（天然校准、原空间、E|f−g|=ECE₁），主定理改为 **ECE₁(f) ≥ (E[p]/3)(𝔇−E[p²]/E[p])**，顺带把度量落到实用 ECE（修 overclaim）② 引理1.2 逻辑链重写（calibration 钉 λ=1，非 C-S）③ 引理2.1 常数修 3、写全差分 ④ §1 撞车表补 Bröcker/DeGroot-Fienberg「换皮威胁」+ RankSEG 辨析 ⑤ §6 P0 状态降级（半证）⑥ 新增 **§8 拔高路线**：E1 minimax 信息论下界(Le Cam/Fano 两点法)=决定档次、E2 去A1啃有限-N U-statistic、E4 扩 ECE+conditional、E5 主动证非平凡。
- **诚实定位**（reviewer 判）：A1 下主定理已自洽且洞补，但因 A1 + P1 refinement 推论性质，**当前仅 workshop 档**；冲 NeurIPS/COLT 必须走 §8（minimax + 去A1）。

**9. E1 + E2 执行（拔高，已推骨架）** — 见 `02_理论框架` §9/§10：
   - **E1 minimax 下界（§9）**：Le Cam 两点法。构造 P₊/P₋（p=½±εg(x)），引理9.1 KL≤8nε²→TV≤2ε√n，取 ε=1/(4√n) 不可区分；引理9.2 承诺方向定 Dice/ECE；**定理 E1：任何学习器 max_P E[(𝔇_cal\*−𝔇)₊ + ECE₁] ≥ Ω(1/√n)**。信息论、方法无关 → 脱离「refinement 换皮」批评；finite-sample rate 是新物。reduction 定量化 + c₁ 待严格化。
   - **E2 去 A1（§10）**：ratio 集中。引理10.1 |D−𝔇|≤O(1/(S√N))；定理 E2：期望前景 N·E[p]≫1 时 A1 自动成立、主定理对真 Dice 仅 O(1/(S√N)) 修正。**小病灶 regime（N·E[p]=O(1)）population 崩**（Jensen 偏差 + 集中失效）→ 需直接随机 Dice high-prob 下界 = 论文核心 open hard part，与 E1 的 1/√n floor 呼应。

**理论现状**：A1 下主定理（P1+P2）洞补完整；拔高侧 E1(minimax 1/√n)+E2(去A1)骨架已推，剩严格化 + 小病灶 hard part。

**10. E1 严格化 + 自检修正（关键）**：
   - 先推干净版 minimax（Dice-excess≤ε·TV≤O(1/√n)），**但自检 general-B 时揪出致命退化**：prevalence=½ 时 f≡1 不用样本白拿 Dice=2/3>校准最优 → minimax 叙事被击穿（reviewer 的 general-B flag 命中）。
   - **修正**：改**低 prevalence（小病灶）构造**——背景 p=0 + 候选区 2β 占比、p=½+εgσ。f≡1 因海量 FP 而废，获 Dice 必须定位+知 σ。
   - **修正定理 E1**：floor=**Θ(1/√(nβ))**，β=病灶规模，β→0 floor 最强。引理9.2′（resolve σ 需候选样本 m=2nβ）+ Le Cam。核心稳，excess 系数 + 一般 B 收尾中。
   - **大收获**：E1（统计 floor）与 E2（去 A1）**由「有信息样本/前景数 nβ ~ Nc」统一**，叙事打通。

**11. E2 锐化（§10）**：控制参数从 N 锐化为 **Nc=期望前景像素数**，相对误差 O(1/√(Nc))；Nc≫1 A1 自动成立；Nc=O(1) 小病灶 OPEN（攻法：条件化前景数 K、self-normalized 集中）。

**12. E5 非平凡性辩护（§11，回应 reviewer 最危批评）**：诚实让出「P1 在 A1 下=refinement 分解换皮」；把贡献钉死在三件分解给不出的：①跨非-proper-度量的桥（Dice 非 proper，分解理论沉默）②P2 是跨度量**不等式**非恒等式 ③E1 的 1/√(nβ) 是 finite-sample 信息论 floor（分解永远给不出 n/β-依赖）。正文 Intro 把 P1 降 warm-up，主定理挂 P2+E1。

**13. P3 数据**：查 `.portfolio/datasets.json` —— ACDC/BraTS/Synapse **不在表**（现有全是皮肤/CXR，属 ICLR+NCA-JEPA）。P3 需新下载，属立项后，不卡当前理论。

**14. researcher 三方核常数回汇 + 并入**：
   - ✅ Błasiok smCE 定义 + Thm1.4（½≤d̲CE/smCE≤2）+ Thm6.2（intCE≤4√d̲CE）核实；注意 d̄CE/intCE 别混。
   - ✅ RankSEG Thm1（Dice-Bayes ranking）+ Lemma9（CE/focal 非 Dice-cal）核实；固定阈值 Remark 号待手核。
   - ✅ mL1-ACE Table1 精确绝对值到手：soft ACDC .136→.073/DSC−0.7pp、BraTS .146→.102/DSC**−1.7pp**（原写−1.9% 略偏，方向仍对）、KiTS+0.1pp。%入正文前 verifier Bash 核。
   - **❌→修正 Bröcker**：RES=Var[E[Y|p]]、UNC=q̄(1−q̄)；**E[p(1−p)]≠RES**，而是 irreducible aleatoric Brier(=UNC−maxRES)。已修 §1/§11/积木表——**reviewer 的「P1=resolution 换皮」措辞不准**，P1 与已知 aleatoric Brier 同源但 ratio 归一化(÷prevalence)非标准分解项，非平凡性比担心的强。
   - 积木表全部升 **【三方核 ✅】**。

**本轮净结果**：理论自洽性 + 数字溯源大幅加固；E1 自检修正(低 prevalence)+E1/E2 统一(nβ)+E5 非平凡辩护(精化)。

**15. E2 小病灶精确归约（§10.1）**：不硬造定理，把 OPEN 收成 well-posed 条件化问题——条件于前景数 K~Poisson(λ=Nc)，D=2|Ŝ∩S|/(m+K)，目标命题 E[D]≥𝔇_cal*+t ⟹ ECE₁≥κ(λ)t（κ→0 当 λ→∞ 接回 P2）。两攻法（条件求和 / self-normalized 集中）+ 难点。**统一猜想：floor ~ 1/√(min(nβ,Nc))**（学习样本稀缺 vs 图内前景稀缺取小者主导）。

**16. 第二轮 reviewer 已派（后台）**：审修订版 §9-§11（E1 低 prevalence 修正是否堵漏、E2 锐化、E5 辩护够不够），回来并入。

**下一步**：等 reviewer-2 → 据其修；E1 系数+一般B收尾；E2 小病灶按 §10.1 攻；（立项后）P3 实证 + verifier Bash 核 mL1-ACE 绝对值精度。

**下一步（待办）**
- [ ] E1 严格化：引理9.2 t↔sign 定量 + reduction Markov 论证 + 定常数 c₁。
- [ ] E2 hard part：小病灶 N·E[p]=O(1) 的随机 Dice 直接 high-prob 下界（论文主攻）。
- [ ] verifier 开 PDF 三方核：Błasiok ½/2 常数、RankSEG Thm1、mL1-ACE 实证量级（reviewer 提醒未独立复核）。
- [ ] P3 实证：ACDC/BraTS 画 Dice–ECE 经验 Pareto 前沿（查 `.portfolio/datasets.json`）。
- [ ] **拍板点**：Gate0（A1 下 P1/P2 ✅ + E1/E2 至少 high-prob 版 + P3）→ `/spin-off-paper` 立项 + 导师对齐会场。

**拍板状态**：方向已拍（★1+★2 留）；正式立项（registry schema）待 Gate0。已认领 `.portfolio/locks/medseg-uq.claim`。
