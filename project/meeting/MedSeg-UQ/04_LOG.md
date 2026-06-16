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

**17. reviewer-2 回汇 + E1 全面降级（重要诚实回退）**：
   - **CRITICAL**：低 prevalence「修正」**没堵洞**——「候选区铺满前景」零样本、σ-无关拿 Dice=2/3>校准最优0.505，excess O(1)。第一轮 f≡1 漏洞只是搬家。根因：Dice-excess 主项来自前景位置/普遍性（公开），非 resolve 隐藏 σ（我把 σ 放 O(ε) 维度）。
   - 附带：引理9.2′ 常数错（ε=1/√(8nβ) 给 TV≈0.707≠½，须 1/√(16nβ)）。
   - **命中红线「不把弱结果当强卖」**：撤回全部「E1 严格✅/COLT级/minimax已建立」。E1 → **OPEN**。
   - reviewer-2 正面验证 **§10 E2 最扎实**：Nc 是唯一控制参数（数值 Nc=100 偏差~0.001/Nc=1~0.16）、Jensen 偏差系统向下、O(1/Nc) 衰减，全对；小病灶标 OPEN 诚实必要。
   - reviewer-2 指 §11 三辩护均偏弱：P2 证明**没用到 Dice non-proper**（只用 Dice≤1 + E[fp]=E[f²]@cal）= Lipschitz泛函+ECE 实例化；E1 垮 → E5 无硬支柱。
   - **主线再自检**：连 reviewer 给的「ECE-约束 minimax」方向也有洞——flooding 小候选区全局 ECE₁=β（小），被背景稀释，排不掉。**正确度量须 region-conditional calibration（接 ★3/E4）。E1 比两轮以为的更深。**
   - 已据此修 §6/§9/§11/heading：E1 全面 OPEN、撤过度声称、记正确方向(conditional-cal minimax)。

**诚实总定位**：扎实可用 = A1 下 P1+P2（洞补）+ E2 大前景（reviewer 数值验证）= **workshop/期刊级**。冲 COLT 的命门 = E1 的 conditional-calibration-约束 minimax，**全新未证，比预想深**。**E1 证成前不立项、不对外称下界结果。**

**18. E1 第三次尝试（§9.1，候选未确认）**：改 **region-conditional calibration（cECE，只在候选区算）** 约束。主线自验非退化：flooding 候选区 cECE=½>δ 被排除（全局 ECE₁=β 排不掉，换度量是关键）；部分承诺/背景承诺/半 flooding 初步看也堵。候选定理：cECE≤δ 下 σ-unaware worst-case excess≤O(1/√(nβ))。**已派 reviewer-3 专攻找退化洞（按自己承诺，不提前称成）。**

**诚实状态汇总（给后续窗口）**：
- 🟢 **扎实**：A1 下 P1（校准最优=E[p²]/E[p]）+ P2（ECE₁≥(E[p]/3)(𝔇−𝔇_cal*)，洞已补）+ E2 大前景（Nc≫1，reviewer 数值验证）= workshop/期刊级，正确可用。
- 🔴 **OPEN 命门**：E1 minimax（前两次构造翻车，第三次 cECE 候选待 reviewer-3 裁）。E1 成→COLT；不成→期刊档。
- **纪律教训**：E1 连翻三次源于「自验通过就写已成」。今后理论先派 reviewer 裁再落「已证」。

**19. reviewer-3 否决第三次 + E1 最终停证（重大战略回退）**：
   - reviewer-3：第三次 cECE 构造也垮——退化预测器=候选区常数 f=½+δ、背景0，cECE=δ 满约束却拿 excess≈δ/2=Θ(δ)（hard-Dice Θ(1)）。我候选定理漏 O(δ) 项，该项免费=P2 换皮。
   - **主线深层分析（§9.2）**：三次同一病根逼出根本矛盾——「σ 统计难辨(Le Cam 需 KL 小)」⟺「两区都有前景」⟺「flooding 有效」⟺「excess 免费」。**「σ 难辨」与「flooding 无效」不可兼得。**
   - **裁定**：超出 P2 的额外 finite-sample minimax floor **大概率不存在**（唯一逃逸=稀疏多位置，但退化成 detection 样本复杂度，非新 trade-off floor）。**E1 停证，撤出论文卖点，不追 COLT。**
   - 全文重新定位：§0/§6/§9/§11 改为 **MICCAI/MedIA/TMI 应用理论档**。

**═══ 最终诚实定位（三轮 reviewer + 深层分析挤完水分）═══**
- 🟢 **真实可用（论文骨干）**：A1 下 P1（校准最优=E[p²]/E[p]=aleatoric 封顶）+ P2（ECE₁≥(E[p]/3)·Dice-excess，洞补）+ E2 大前景有限-N 修正。正确、自洽、机制清晰。
- ⛔ **COLT/NeurIPS 纯理论不可达**：E1 minimax 三次失败 + 结构矛盾 → 大概率不存在。
- 🟡 **唯一真增量 OPEN**：E2 小病灶 Nc=O(1) 随机-Dice 下界（§10.1）。
- **会场**：MICCAI/MedIA（贴导师领域、算力低），**非顶理论会**。
- **纪律教训**：理论「自验通过就写已成」连害三次；今后先 reviewer 裁再落「已证」。

**用户拍板**：换理论更高的 ★ 重推（★1 trade-off 降 MICCAI 档存档于 `02`）。

**20. ★ 选型（3 路 researcher 收敛）**：
   - **★2 最优聚合=高塌缩弃**：Guarino et al. **CVPR'26 已做经验版**且实证「无单一最优算子」；Neyman-Roughgarden'21 已奠基 proper-scoring→最优聚合；SDC 做 Dice 特例。
   - **★3 分割 multicalibration=选**（塌缩中-低）：核心硬问题零先例（含 COLT'25 全程序）——**空间 Markov/CRF 结构能否打破高维 MC 指数下界 d^Ω(1/ε²)**（Tang 2505.21460 + 2601.05245 开放方向）。竞品 Fair Risk Control(ICML'24 demographic+post-hoc)、Liu-Wu'24(NLP) 不覆盖。
   - 建 `05_理论框架_★3`：锚定 reading-(b) 结构化联合分布 MC（outcome 2^HW 指数，Markov 因子化坍缩有效维度=COLT 核心；reading-(a) 逐像素=poly 平凡避开）。
   - **严守 E1 教训**：先建 1D Markov 链 toy 验「结构红利是否存在」（未知二元，正反都可发）→ 算出再写定理 → reviewer 裁 → 上一般 CRF。

**21. ★3 形式化钉死（researcher）**：reading-(b)=部分空白。最危险塌缩=Kuleshov-Liang'15（结构化预测校准，但非 multi-group/无复杂度分析/不用因子化）。推荐形式化=**clique-marginal multicalibration**，复杂度参数(n,k,|G|,ε)，目标 poly(n^k,|G|,1/ε) vs 朴素 exp(n)。防塌缩四条精确区分(Kuleshov/Low-Degree-MC/Tang/Decision-cal)已记 §1.5。

**22. ★3 toy 初推（主线，正信号有边界）**：1D 链——clique 边际低维(4维)→ 校准 (n−1)·|G| 个低维子问题=poly(n)；链/树 joint 由 clique 边际定(junction-tree)→ 结构红利存在。**浮现核心参数=treewidth**，候选主定理 **复杂度 poly(n,|G|,1/ε)·exp(O(treewidth))**（图模型推断的 treewidth 参数化搬进 MC）。**诚实边界**：clique 校准⟹全联合 仅当 truth 是该结构；诚实 claim=局部边际校准。

**23. 派 reviewer-4 攻 toy（后台，按纪律不庆祝先找洞）**：重点攻——(a) 结构红利是否**平凡/稻草人**（clique 边际本就低维，「朴素联合 MC=exp(n)」是不是没人会做的假靶）(b) treewidth 主定理是否=**Kuleshov'15+junction-tree 教科书的平凡组合**(c) online 对抗下红利是否转移(2601.05245 的 Ω 会不会打在每个 clique)。

**24. reviewer-4 裁 ★3：当前形态大体塌缩**：
   - toy「结构红利」=稻草人（朴素联合 MC over 2^n 是自定义靶，外部无人主张；真问题=局部边际校准本就 poly，没打破任何外部下界）。
   - treewidth 主定理上界=junction-tree(教科书)+per-marginal 校准机械拼接，treewidth 进复杂度纯因推断已知事实，非 MC 新难度→塌缩。
   - 退守局部边际校准=Kuleshov'15+Hébert-Johnson 直接叠加，无本质差异。
   - **唯一窄活路**：弃 batch/打破指数叙事，只赌 online 对抗 regret（链上证严格优于逐 clique 独立基线、gap 源自 MC 对抗性）。但 2601.05245 的 Ω(T^{2/3}) 可能逐边触发吃光红利，reviewer 判也很可能塌缩。

**═══ 大局诚实判断（★1 三翻 + ★3 塌缩后）═══**
两个理论上限最高的 ★ 深推后**都塌缩成「整合已知结果」**（★1→refinement+无 minimax；★3→junction-tree+per-marginal）。强信号：**医学分割 UQ 的硬理论早被 calibration/multicalibration/conformal 社区做完，「搬到分割」普遍 incremental**。「纯顶会(CVPR/ICLR/NeurIPS/COLT)靠理论」对本配置(本科+导师 IEEE 期刊/医学影像+低算力)是逆梯度。
**这是拍板点**：①接受 MICCAI/MedIA 档(★1 的 P1+P2+E2+实证,真实可发) ②赌 ★3 online-regret 窄门(高风险,reviewer 判likely塌缩) ③换大方向(非「医学分割理论下界」这类)。需用户定。

---

## 2026-06-16 收工

**用户拍板**：战略**先停,问王水花教授再定**（会场偏好/资源/是否有理论合作者）。本窗不再往下推，等导师反馈。

**本次完成**：
1. MedSeg-UQ 从零完成立项前调研：8 路 researcher 选题矩阵+文献矩阵+理论深挖矩阵+导师画像（`00`），定向 ★1。
2. ★1 calibration-Dice trade-off 理论：P1（校准最优=aleatoric 封顶）+ P2（ECE₁≥(E[p]/3)·Dice-excess，致命洞已修）+ E2 大前景有限-N，三轮 reviewer + 主线自检挤干水分；E1 minimax 经结构矛盾判**大概率不存在** → 降 MICCAI/MedIA 档存档（`02`）。
3. 转 ★3 multicalibration（`05`）：形式化钉死，但 reviewer-4 判 toy=稻草人、treewidth 上界=junction-tree 机械拼接，大体塌缩，仅余 online-regret 窄门。
4. 大局结论：医学分割 UQ 纯理论下界这条路对本配置**逆梯度**，硬理论已被 calibration/MC/conformal 社区做完。

**待导师定**：①会场（接受 MICCAI/MedIA 真实可发 vs 硬冲 CV/ML 三大会）②若冲三大会则需转方法/实证类（吃算力）③是否有理论合作者支撑 ★3 online 窄门。

**纪律教训沉淀**：理论「自验通过就写已成」连害 ★1 三翻；今后先 reviewer 裁再落「已证」。本项目已认领 `.portfolio/locks/medseg-uq.claim`，pre-立项（未跑 /spin-off-paper，registry 未建）。

**下一步（待办）**
- [ ] E1 严格化：引理9.2 t↔sign 定量 + reduction Markov 论证 + 定常数 c₁。
- [ ] E2 hard part：小病灶 N·E[p]=O(1) 的随机 Dice 直接 high-prob 下界（论文主攻）。
- [ ] verifier 开 PDF 三方核：Błasiok ½/2 常数、RankSEG Thm1、mL1-ACE 实证量级（reviewer 提醒未独立复核）。
- [ ] P3 实证：ACDC/BraTS 画 Dice–ECE 经验 Pareto 前沿（查 `.portfolio/datasets.json`）。
- [ ] **拍板点**：Gate0（A1 下 P1/P2 ✅ + E1/E2 至少 high-prob 版 + P3）→ `/spin-off-paper` 立项 + 导师对齐会场。

**拍板状态**：方向已拍（★1+★2 留）；正式立项（registry schema）待 Gate0。已认领 `.portfolio/locks/medseg-uq.claim`。
