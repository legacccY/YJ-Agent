# NCA-PhaseMap — STORY FRAMEWORK

> 战略叙事唯一真源。改 headline / 卖点 = 拍板点（CLAUDE.md 拍板点 4），先报。
> 2026-06-17 立项首版（源 ideation run-003 G6 C044）。

## Headline（2026-06-22 灰区收窄·条件性相变）

**NCA 医学图像分割训练中，update 稀疏度（fire_rate）刻画一条功能塌缩相边界，但其形态条件依赖：Hippo+梯度裁剪下呈尖锐断崖、BraTS+官方无裁剪下退化为宽概率过渡带（过渡宽 w≈0.30、临界漂至高 ur*≈0.66）——首次系统刻画相变的成立/退化条件，并指认梯度裁剪 / 数据集为控制临界宽窄的旋钮。**

越过临界 update_rate NCA 塌缩到平凡背景解（diverged≠collapse），且塌缩与梯度幅度无关（梯度与 dice 同步归零，非梯度先死）。社区一直只把 fire_rate=50% 当固定超参直接用，从没系统刻画过这条边界**及其条件性**——本文首次。正面贡献 = 刻画相变**成立/不成立的条件** + 安全 fire_rate 区间实践指南。

> **2026-06-22 灰区收窄（用户拍板，补1 生死闸门后）**：原「尖锐、可前验、seed 稳定的**普适**临界」已被 Gate1 K1/A2 + 补1 证伪——弃。补1（BraTS no-clip 扩 ur 8档×5seed）实测 collapse_rate=[0,0,.2,.2,.4,.8,.8,1.0] 单调（rho=0.982 p<0.001）但过渡宽 w=0.30 >> 0.10、ur*≈0.66（漂离 Hippo 0.375）= **灰区：有确定相变但宽概率过渡带、非尖锐普适**。headline 收窄到「条件性相变」。详 `04_LOG` Entry 9 + `reference/THEORY_LEDGER.md`。
> **真命门待验**：Hippo no-clip 到底尖不尖锐（现有尖锐 STABLE_SHARP 可能是 clip=1.0 测的）→ 决定「clip 是旋钮」机制成不成立（补3 复核）。

## 三支柱卖点（2026-06-22 条件性收窄）

1. **相变形态条件依赖**（非普适尖锐常数）：update_rate 越过临界 NCA 塌缩，但形态随条件变——Hippo+clip 尖锐断崖（w≤0.05）、BraTS+no-clip 宽概率过渡带（w≈0.30、ur*≈0.66、collapse_rate 单调 rho=0.982 p<0.001）。首次刻画相变的**成立/退化条件**。⚠️ 弃原「尖锐普适 ur*≈0.375」（Gate1 K1/A2 + 补1 证伪）。
2. **塌缩 ≠ 梯度爆炸**（反社区直觉，no-clip 坐实）：补1 BraTS no-clip 全程 diverged=0（塌缩非发散），G_traj 实测塌缩时梯度与 dice **同步归零**（非梯度先死，A3 PASS/K4 未触发）。社区从没真把"梯度爆炸"当 NCA 训练失败主因——本文厘清真正因子是 update 稀疏度。⚠️ 措辞用「未观察到梯度先于塌缩」，不卖「证明与梯度无关」。
3. **clip / 数据集 = 临界宽窄旋钮**（机制段，待补3 闭环）：宽窄差异指向 clip 压随机涨落 + 数据集前景占比（有效系统尺度）调控过渡带宽。**真命门 = Hippo no-clip 尖锐性**（补3 复核）：若 Hippo no-clip 也宽→clip 旋钮成立、机制闭环；若仍尖锐→尖锐源于数据集差异非 clip。理论骨架见 `reference/THEORY_LEDGER.md`（吸收态相变 + finite-size 概率带），档=待跑禁当定理。

## 关键概念厘清（措辞红线，违反即跑偏）

- **塌缩 ≠ 发散**：diverged flag 0/36，梯度正常。塌缩 = 收敛到平凡背景解（trivial solution），不是 loss→NaN 的发散。claim 全程用「功能塌缩 / 平凡解」，**禁用「发散（divergence）」**。
- **fire_rate = async = 同一旋钮**：`stochastic = rand > fire_rate`，实际更新比例 = 1−fire_rate。不是两个独立因子（原 C044 的 corr=−1.0 是数学必然非 confound）。统一用 **update_rate = 1−fire_rate** 单轴表述。
- **梯度无关写"未观察到显著关联"**，不写"证明与梯度无关"（p>0.05 = absence of evidence，功效不足）。
- **clip 复现红线（2026-06-18 researcher 核）**：官方 Med-NCA `Agent.py` L102-103 + 全 `src/` 零 `clip_grad_norm_`。G5 三重实证全带 `CLIP_NORM=1.0`=非官方自加。Gate1 起 **no-clip 为主条件**（对齐官方），clip=1.0 仅作对照解释 G5。所有临界点/支柱2 claim 以 no-clip 复测为准；no-clip 下若真发散（loss→NaN）严格区分 diverged≠塌缩，单列不计。
- **诚实天花板**：当前单数据集小模型 = 中等会议料；standout 是立项后赌注，不在叙事里预支。

## 对手 / 差异化

- arXiv 2508.06389「Identity Increases Stability in NCA」：多 organism 形态边界崩溃 + identity 架构修复。**三重正交**（问题域 morphogenesis≠训练塌缩 / 数据 gecko≠医学 / 解法 identity≠相边界刻画）。须在 related work 显式引 + 差异化。
- distill 2020 Growing NCA / Med-NCA：把 fire_rate/async 当正则化/鲁棒手段，未系统研究塌缩边界——本文补这块空白。

## 数据

Med-NCA Hippocampus（Task04，本地 + HPC ready）；立项后扩 BraTS 切片 + 第二独立实现（如 M3D-NCA prostate）验普适性。
