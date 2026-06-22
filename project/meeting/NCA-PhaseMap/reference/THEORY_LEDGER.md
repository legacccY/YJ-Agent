# NCA-PhaseMap — THEORY LEDGER（理论支撑账本）

> 三层防线（theorist 推导 → skeptic 独立证伪 → verifier 核数）冻结假设链，防 HARKing。
> 首版 2026-06-22（/theory-audit diagnose）。**证伪条件一旦写死，事后不得调宽 / 加特例。**

---

## §1 现象 + mode

**mode = diagnose**。诊断核心威胁 **A2**：NCA update 稀疏度功能塌缩相变，在 **Hippo+clip=1.0** 下干净尖锐断崖，但换 **BraTS+no-clip（官方条件）** 后退化成**跨 seed 全 MIXED**（B3 5ur×5seed 塌缩率 2/5,1/5,2/5,3/5,3/5，无 5/5 无 0/5，Spearman rho=0.79 **p=0.11 不显著**）。问：MIXED 归因三分流哪一类？理论预言补1 结果？

---

## §2 推导链（Layer 1 theorist，半形式化）

```
A1 塌缩=吸收态：全背景 state→alive 门控关→更新恒零→自维持，单次 rollout 不可逆
   [置信 高｜来源 A3实证 dice锁死+grad/dice同步归零(verifier已核✅)｜⚠️skeptic: 仅就单rollout成立，训练层逃逸另论=跳步]
A2 随机更新=probabilistic CA：每cell每step Bernoulli(p=fire_rate)，Var=p(1−p)‖δ‖²
   [置信 高｜来源 PRIMER §6.3]
A3 有限系统→概率临界带：吸收态相变(APT)有限尺度涨落展宽临界区成概率带
   [置信 中｜来源 Hinrichsen cond-mat/0001070｜🔴skeptic证伪: 见§5命门2，方向用反]
A4 clip 解释 Hippo 干净断崖：no-clip BPTT梯度涌动e^{λT}放大涨落，clip截断压方差缩窄概率带
   [置信 中｜来源 §6.5+🔴-6实证｜🟠skeptic: 纯定性，无定量链]
A5 谱半径ρ(J)是稳定性标准量(非传播半径)，但"落入吸收域"是全局逃逸+随机问题非ρ单点<1
   [置信 中｜来源 PRIMER §6.4｜skeptic: 此自我修正诚实正确，但反证DP框架不适用→§5命门3]
```

**投票（命门多路，第 2 个 theorist 独立重推「(A) 确定相变 vs (B) 概率临界区」）**：独立推到 **(B) 概率临界区，置信 8 成**，补1 预测全 MIXED + 中段非单调。与 Layer1 **方向一致（2/2）**。新增物理细节：有效系统尺度 = 活动前景 cell 数 n_active（前景稀疏 1–10% → n~40–400，相对涨落 ∝1/√n_active ~10%，远大于 1/√4096），pseudo-critical 点跨 seed 有宽度分布 Δ=Θ(1/√n_active)。

---

## §3 三分流归因（含 skeptic 独立证伪后的修正）

| 类 | theorist 原置信 | **skeptic 证伪后** | 判别实验 |
|---|---|---|---|
| ① 假设错（NCA 本征无确定相变，相变=clip+Hippo artifact） | 高 65%（主归因） | **🔴 降级为「未坐实候选假设」**——经 4 致命伤独立证伪，不成立为「已坐实诊断」 | =补1 本身（无偏裁决） |
| ② 实现/数据集错（临界漂出采样窗 / clip缺失放大方差 / 前景占比/归一化未对齐） | 中 25% | **🟠 被系统性低估，应与①平权**（A4 impl2 dice0.3、BraTS前景5%、归一化TODO 未核） | 补3 E3b 归一化核 + 补4 实现对齐，**不应等补1 PASS 才做** |
| ③ 数据不够（n=5 seed 太少，p=0.11 不显著） | 低-中 10% | **🟠 被读成了①**（n=5 在 P=0.5 下 5/5或0/5 各~3% 假阳） | 补1 扩 8ur×5seed；theorist2 建议 ≥10 seed 把假阳压到<0.1% |

**skeptic 核心证伪（4 致命伤）**：
1. **命门2 🔴 方向用反**：finite-size scaling 整套方法的目的就是从有限数据**外推确证**无限系统尖锐 p_c；「观测到 MIXED 展宽」是临界点**存在**的标准信号，不是「无确定相变」证据。真能把尖锐变 crossover 的是 persistent driving/background noise（需额外论证 NCA 有此机制，未给）。[来源 arXiv:0807.2300, PRE 72.016119]
2. **命门3 🔴 DP 框架不适用**：DP/APT 是纯局部随机动力学（p 固定外参、无目标函数）；NCA 是 BPTT 梯度训练驱动，"是否进吸收态"是优化轨迹/吸引域几何问题，非单参数 p 的稳态 DP。套 DP 临界指数最多是比喻，撑不起 65% 主归因。
3. **命门4 🔴 不可证伪**：当前表述对「尖锐」（→clip/Hippo特例解释）和「随机」（→预言命中）两种相反观测都能自圆 = 没有判别力。
4. **命门6 🔴 确认偏误**：主线语境倾向 KILL（防第四次重启），理论"预测 KILL"贴合该倾向，系统性低估②③。
5. **🔑 Hippo 反例（贯穿）**：同等有限网格 64²×300step + 同等随机更新下，Hippo STABLE_SHARP（3/3 全塌、0/3 全活）。若"有限+随机⟹必概率带"成立，Hippo 不该尖锐。Hippo 尖锐 ⟹ 该机制下确定相变**可达** ⟹ BraTS MIXED 必来自 BraTS 特异因素（②/③）。

---

## §4 补1 理论预测 + 证伪条件（🔒 冻结，防 HARKing）

**预测（两 theorist 一致，档=待跑，禁当定理）**：补1（BraTS no-clip ur∈{0.45..0.80}步0.05×5seed）~70–80% 概率全程 MIXED + 中段非单调，无干净 5/5↔0/5 二分。

**🔒 证伪条件（写死，事后不得加特例）**：
- **A2 翻案（①作废，转②/③）⟺ 补1 在 BraTS no-clip 中段（ur≈0.55–0.72）出现 collapse_rate 从某档 0/5 单调跨到某档 5/5、过渡≤0.10ur 的确定断崖。** 此时"NCA 本征无确定相变"被直接证伪，临界只是漂移。
- **概率带坐实（①第一次拿到实证支撑）⟺ 补1 全 0.45–0.80 仍无任何 5/5 或 0/5 档。** 注意：此时支撑①的是**数据**，不是 §2 推导（推导方向被 skeptic 证伪）。
- **⚠️ 端点平凡饱和不算翻案**：若 5/5 只在 ur≥0.80 极稀疏端（步长太小学不动→全塌）= 平凡饱和，**不翻 A2**。
- **⚠️ 5 seed 假阳护栏**：单档 5/5 不能判翻案（P=0.5 时 5/5 假阳 ~3%），必须**整段单调干净二分**才算。

---

## §5 命门定理（A2 能否翻案的理论判据）

**命题**：NCA 前向 rollout = 有限尺度（有效活动 cell 数 n_active）随机过程，全背景=吸收态，每 step 含 O(1) Bernoulli 方差 ⟹ 存在临界窗 W=[ur_c−Δ, ur_c+Δ]，Δ=Θ(1/√n_active)，ur∈W 时单 seed 有限时间(300step)生存概率∈(0,1) 非退化 → 跨 seed 必 MIXED；n_active→∞ 或方差→0（clip 压方差）时 Δ→0 退化为尖锐二分。

**档 = 待跑**（FSS 渐近标度论断，非干净有限命题，**不建议 Lean 形式化**，半形式化性价比最高）。**禁当定理卖**（NCA-JEPA 100× 越级栽过）。

**skeptic 对命题的裁决**：命题在**无限/自平均极限**对，但**有限数据观测 MIXED 不蕴含命题成立**（命门2 方向问题）——命题正确用法是被补1 实证检验，不是预判 KILL。

---

## §6 净结论（lead 综合三层）

1. **理论审计净产出 ≠「证明该 KILL」**，而是：(a) 给降级版 headline 一个机制骨架——「**条件性概率相变**：clip 压方差 + 前景占比/n_active 是 (B)概率带→(A)尖锐 的旋钮」（两 theorist + skeptic 均认可此为正确叙事立点，胜过原"普适尖锐"）；(b) 揭示**关键悬而未决 = Hippo no-clip 到底尖不尖锐**，决定 Hippo 反例有效性 → 决定①能否复活。
2. **K-new-1 的 KILL 必须由补1 实证触发，绝不能由 §2 理论先验预判**（三方共识，正中 [[feedback_falsify_crux_first]]：理论自洽≠地基正确，命门要实证不要先验）。
3. self-consistency 投票 2/2 同向（B），但 skeptic 证明**两路犯同一方向错**——投票一致 ≠ 正确，记此为方法论教训。

---

## §7 残留 TODO + 待决策（不臆造，标盲区）

- **✅ 已解（2026-06-22 补3）：Hippo no-clip 也是宽概率带（w=0.20、中段 MIXED），不尖锐。** 原 STABLE_SHARP 是 clip=1.0 测的。→ **skeptic 的 Hippo 反例消解**（它假设 Hippo no-clip 尖锐，实测为假）；**theorist「no-clip→概率带」预测在双数据集坐实**（toy验，非定理）。2×2 凑齐：clip=1.0 两集尖锐 / no-clip 两集宽。机制定性 = **clip 控宽窄（toy验 partial，BraTS clip 侧仅单 seed 待补）、数据集控临界位置（no-clip ur* Hippo0.34 vs BraTS0.66，扎实）**。注：①「假设错=NCA 本征无确定相变」仍未坐实——no-clip 下两集都有确定端点（0/5+5/5），是**宽概率带非纯随机**，故归因落「条件性相变」非「无相变」。
- **🔴 数据标注矛盾（verifier 揪）**：G_traj ur=0.45 seed=42 step179 塌（dice→0.001、grad归零），但 B2 同 ur 标 collapsed=0。要么 G/B2 脚本 pool/seed 差异（→不同 run 一塌一活=seed级随机直接证据，支持B），要么 collapse flag 判定时间点 bug。**影响补1 collapse 判定可信度，须查清**（B2/B3 collapse 用 final_dice=1−mean(loss[-10:])，G_traj 用逐步轨迹）。
- **n_active 真值**：BraTS/Hippo 实际前景 cell 占比（决定 Δ 量级、决定 MIXED 带宽 step0.05 是否分辨得出）→ Grep mask csv。
- **clip 压方差定量链未闭合**（命门5）：固定权重 seed 量 no-clip vs clip=1.0 临界区 per-step state 更新方差。补2/3 可加最小探针。
- **传播半径 metric 出处 arXiv 2310.14809 待 researcher 核**（补2 机制探针物理量选型盲区）。
- **collapse_thresh 末位 drift**：B0_baseline.csv 存 0.012883，公式/B1/B2/B3 用 0.012882（无害，判定用 0.012882 对）。

**待用户拍板（不阻塞补1，但影响补1 设计/解读）**：
1. 补1 5 seed → 10 seed？（theorist2 建议；5 seed 单档假阳 3%，但判据是整段单调故 5 seed 可能够；10 seed 算力翻倍 ~0.6 GPU·h）
2. 补3（Hippo/BraTS 差异核）+ 补4（实现对齐）是否提到与①平权、不等补1 PASS（skeptic 建议——否则"BraTS 无相变"和"BraTS 归一化没对齐"分不开，KILL 理由会被审稿人一句打穿）。
