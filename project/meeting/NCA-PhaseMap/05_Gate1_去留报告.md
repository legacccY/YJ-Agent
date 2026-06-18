# NCA-PhaseMap Gate1 去留报告

**生成时间**：2026-06-18  
**分析员**：Analyst（sonnet）  
**本分析服务**：NCA-PhaseMap Gate1，对应 ACCEPTANCE 判据 K1（临界普适性/BraTS 第二数据集）、A2（seed 稳定性/B3）、A3（梯度因果 no-clip 重测/G_traj）、A4（第二实现/B4 impl2）、M1（传播半径探针）。  
**主条件**：no-clip（clip_grad_norm=None），clip=1.0 仅对照，所有判定以 no-clip 为准。

---

## 一句话判决

**重降级，不 KILL。**  
BraTS no-clip 无干净相变（非单调散点，K1 FAIL），seed 稳定性全域混合翻转（A2 FAIL），impl2 无塌缩信号（A4 FAIL）。梯度因果方向确认无逆转（A3 PASS，K4 未触发）。现有证据支撑的诚实故事仅限：Hippo 单数据集 + clip=1.0 辅助条件下存在干净相变，BraTS no-clip 不复现。降级目标：TMLR/MIDL analysis track（单数据集诚实标注 + 反梯度直觉），撤"可前验普适临界"主叙事。

---

## 逐判据表

| 判据 | 结论 | 关键数字（来源 csv:列） | 对判据 |
|---|---|---|---|
| **K1 临界普适性** | **FAIL** | no-clip BraTS 仅 ur=0.625/0.725/0.750 塌，ur=0.650/0.675/0.700 活（夹在中间）；非单调散点；clip=1.0 有干净断崖 ur*=0.600（B2_fine.csv:collapsed/final_dice） | ACCEPTANCE K1："临界消失或漂移"→ KILL 条件；no-clip 无单调断崖，判为"临界消失"，K1 触发 |
| **A2 seed 稳定性** | **FAIL** | B3 5 ur × 5 seed 全部 MIXED（2/5, 1/5, 2/5, 3/5, 3/5 塌）；无任何 ur 达 5/5 或 0/5；Spearman rho=0.79 p=0.11（不显著）（B3_seed.csv:collapsed） | ACCEPTANCE A2："临界 ur 在 ≥3 seed 下方向一致"；BraTS no-clip 全区间 seed-random，判 FAIL |
| **A4 第二实现（impl2）** | **FAIL** | B4 MinimalNCA impl2 (Hippo) 0/15 collapsed；dice 范围 0.21-0.35，远低于官方实现活跃态 ~0.70；无相变信号（B4_impl2.csv:collapsed/final_dice） | ACCEPTANCE A4："第二独立实现上临界相变复现"；impl2 基础性能显著弱于官方，无塌缩可观测，判 FAIL |
| **A3 梯度因果（K4 检验）** | **PASS** | G1 no-clip (ur=0.45, Hippo) seed=42 collapse step=179：前 20 步 grad_norm_max 均值=3.76、最小值=0.032（活跃）；seed=43 collapse step=287：前 20 步均值=2.71、最小值=0.069；塌缩时梯度与 dice 同步归零（G_traj_g1.csv:grad_norm_max/dice_proxy） | K4："梯度是塌缩前驱"→ FAIL；实测梯度在塌缩前仍活跃（均值 2-4），与 dice 同步崩溃，不支持梯度先死；K4 未触发，A3 PASS |
| **M1 传播半径探针** | **FAIL（probe bug）** | 全 27 行 n_active_pixels=0，d_mean/d_std 全 NaN（M1_probe.csv:n_active_pixels）；日志确认每行均如此（_log_M1.log） | 非真 null 信号，是 probe 实现 bug：pulse 种子可能未激活任何像素（theta=0.1 阈值可能过高，或 active pixel 检测逻辑错）；M1 全量无效，不能作为机制证据 |

---

## 关键发现

**1. no-clip 下 BraTS 无干净相变，是本次最核心负面结果。**  
B1+B2 全量 no-clip 扫描（seed=42 单轮）在 ur=0.625 出现塌缩，但 ur=0.650/0.675/0.700 返活，ur=0.725/0.750 再塌，ur=1.0（fire_rate=0，纯确定性）也活跃。这是 ACCEPTANCE 预登记所定义的"临界消失"情形（非单调散点 ≠ 单调断崖）。clip=1.0 在 B2 里有干净断崖（ur* ≈ 0.600，过渡宽约 0.025），但 clip=1.0 是非官方条件，不能作为主判据。

**2. BraTS no-clip 临界区塌缩是概率性/种子随机，不是确定性相变。**  
B3 5 seed × 5 ur 矩阵里，没有一个 ur 点达到 5/5 全塌或 0/5 全活。单轮测试（B1/B2）的"非单调"完全可以用 seed-randomness 解释：ur=0.625 对 seed=42 恰好是 2/5 概率事件。这意味着 BraTS 在 ur 0.625-0.725 区间是一个**随机临界区**，不是尖锐确定性边界。

**3. impl2（MinimalNCA）与官方实现性能差距巨大，不构成有效对照。**  
官方实现在 Hippo 活跃态 dice ≈ 0.70-0.75；impl2 在相同数据集 0.30-0.50 ur 下 dice 仅 0.21-0.35，差距 ~0.35-0.50 Dice 单位。impl2 可能缺少官方 NCA 的关键组件（如 perception kernel、channel 数、normalization 方式），根本未达到能展现相变的性能基线，不能作为"第二实现复现"的有效证据。

---

## 异常 / 风险

**1. no-clip 非单调的深层原因有歧义。**  
ur=0.650 比 ur=0.625 更高（update 更稀疏）却不塌，可能原因：(a) BraTS 单 seed 在这个 ur 区间方差极大（B3 证实），单点采样无代表性；(b) BraTS 与 Hippo 的前景占比、patch size 不同导致临界点漂移到更高 ur（≥0.75），并且过渡区更宽。口径上 B2 只有 seed=42，无法区分 (a)(b)。

**2. M1 probe bug 需明确根因。**  
n_active_pixels 全 0 最可能的原因是：pulse seed 注入时 active pixel 初始化逻辑与 NCA 前向传播不匹配（theta=0.1 作为激活阈值可能过高，或 pulse 注入点根本未被模型认为是"active"）。log 里没有报错，脚本跑完了但全是 nan，是典型的"默默失败"类 bug。

**3. clip=1.0 实际上表现出正好符合 ACCEPTANCE 预登记的干净相变（ur* ≈ 0.60，过渡宽 0.025 ≤ 0.10），但因复现红线（官方无 clip）不能作为主结果。**  
这构成一个方法学困境：使用了非官方超参才看到干净相变，官方条件反而看不到。这不是 K4 梯度因果反转，而是一个潜在的更大问题：clip=1.0 可能通过限制梯度异常涌动帮助维持了相变的"干净性"，去掉 clip 后训练本身的随机性被放大，相变变成概率性事件。

**4. G_traj 实验数据包含 no-clip 和 clip=1.0 两组。**  
G1/G2/G3 CSV 里 clip_norm 列有 NaN（no-clip）和 1.0 两组数据行，本报告分析时已严格筛 NaN 行（no-clip）。注意 G_state.json 记录的 run_id=G3，但三个 CSV 均存在且完整，无数据丢失。

---

## 天花板（最乐观叙事）

如果放弃 BraTS 普适性要求，仅保留已有确凿结果：

**可投 TMLR / MIDL analysis track 的最小故事**（中等会议达标线）：  
"NCA 医学分割训练存在功能塌缩现象（Hippo 数据集，三重独立实证），塌缩发生时梯度与 dice 同步崩溃（非梯度驱动），clip=1.0 条件下 BraTS 出现干净相变（ur* ≈ 0.60），但 no-clip（官方条件）下 BraTS 临界呈概率性而非确定性——这本身是一个有价值的 analysis 发现：相变的确定性依赖梯度裁剪超参。"  

附加发现点：clip vs no-clip 对相变形态的影响（方法学发现，TMLR analysis 可吃）。缺点：无"普适临界常数"可 claim，无机制升级，天花板 TMLR/MIDL，审稿人会问为何 BraTS 不稳定。

---

## 建议下一步实验（3 条以内）

**1. BraTS no-clip 5-seed 全区间扫描（优先级最高）。**  
当前 B3 只覆盖 0.625-0.725。需要扩展到 ur=0.45-0.80 步长 0.05，每个 ur 5 seed，no-clip only。目的：判断是否存在更高 ur 区间（如 ur≥0.80）出现 5/5 稳定塌缩，还是整个 BraTS 在 no-clip 下全程 seed-random。成本：5×8×300step = 适中。如果 ur≥0.80 仍无稳定塌缩 → 正式触发 K1 KILL；如果出现 5/5 → 临界只是漂移到高 ur，可改写为"数据集依赖的临界位置"。

**2. impl2 诊断对齐（优先级中）。**  
在 B4 任一 ur（如 ur=0.25，应当最活跃）用 impl2 对比官方实现：打印网络架构、channel 数、perception kernel，确认是否对齐官方 Med-NCA。如果 impl2 在 ur=0.25 dice 仍只有 ~0.30 → impl2 根本架构不等价，A4 实验作废，需重新找真正独立但功能对齐的第二实现。

**3. M1 probe bug 修复（优先级低，仅机制升级需要）。**  
根因：检查 pulse 种子是否实际写入 NCA state，theta=0.1 是否合适。建议降 theta 到 0.01，或直接打印 step 0 后的 active pixel 数做 smoke test。但如果 K1 已触发 KILL，M1 就不需要再改了。

---

## 图

- `D:\YJ-Agent\project\meeting\NCA-PhaseMap\figures\K1_brats_transition.png` — BraTS no-clip 非单调散点 vs clip=1.0 干净断崖
- `D:\YJ-Agent\project\meeting\NCA-PhaseMap\figures\A2_seed_stability.png` — B3 5seed×5ur 热图，collapse 率标注
- `D:\YJ-Agent\project\meeting\NCA-PhaseMap\figures\A3_gradient_causality.png` — G1 no-clip 轨迹（dice_proxy vs grad_norm_max，seed=42/43）
- `D:\YJ-Agent\project\meeting\NCA-PhaseMap\figures\A4_impl2_comparison.png` — impl2 vs 官方预期 dice 对比

---

## Provenance：关键 Bash 命令 + 输出片段

**K1 非单调确认**（B1+B2 no-clip combined, seed=42）：
```
No-clip BraTS collapsed ur values: [0.625, 0.725, 0.75]
No-clip BraTS active ur values:    [0.0, 0.1, 0.2, 0.3, 0.4, 0.45, 0.475, 0.5,
                                    0.525, 0.55, 0.575, 0.6, 0.65, 0.675, 0.7, 1.0]
```

**A2 seed collapse rates**（B3_seed.csv, no-clip only）：
```
ur=0.625: 2/5 collapsed  (MIXED)
ur=0.650: 1/5 collapsed  (MIXED)
ur=0.675: 2/5 collapsed  (MIXED)
ur=0.700: 3/5 collapsed  (MIXED)
ur=0.725: 3/5 collapsed  (MIXED)
Spearman rho=0.7906, p=0.1114 (not significant)
```

**A4 impl2 dice range**（B4_impl2.csv）：
```
min dice: 0.2126,  max dice: 0.3469,  all collapsed=0: True
collapse_thresh: 0.01,  expected official active dice: ~0.70
```

**A3 gradient causality**（G_traj_g1.csv, no-clip rows, seed=42）：
```
collapse at step=179
grad_norm_max 20 steps before: mean=3.76, min=0.032  (still active)
grad_norm_max at collapse step: 0.0022
=> grad and dice collapse simultaneously, not grad-leading
```

**M1 全 nan**（M1_probe.csv）：
```
n_active_pixels: all 27 rows = 0
d_mean: 27 NaN,  d_std: 27 NaN
=> probe bug (pulse not seeding active pixels)
```
