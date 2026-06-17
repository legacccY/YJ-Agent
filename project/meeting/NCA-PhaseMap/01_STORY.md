# NCA-PhaseMap — STORY FRAMEWORK

> 战略叙事唯一真源。改 headline / 卖点 = 拍板点（CLAUDE.md 拍板点 4），先报。
> 2026-06-17 立项首版（源 ideation run-003 G6 C044）。

## Headline（reframe 后正面命题）

**NCA 在医学图像分割中存在一条由 update 稀疏度刻画的尖锐、可前验的功能塌缩相边界。**

越过临界 update_rate（≈0.375 / fire_rate≈0.625）NCA 即塌缩到平凡背景解；临界尖锐（过渡宽 ≤0.05）、seed 稳定、与梯度幅度无关。社区一直只把 fire_rate=50% 当固定超参直接用，从没系统刻画过这条边界——本文首次。

## 三支柱卖点

1. **尖锐可前验临界**（非模糊经验调参）：update_rate 越过 ≈0.375 即从"能学"断崖跌到平凡解，三重独立实验坐实（原 36cell + 单轴细扫 + 3 seed STABLE_SHARP）。
2. **塌缩 ≠ 梯度爆炸**（反社区直觉）：塌缩与 max_grad_norm 统计无关（r=0.238 p=0.16），高梯度反而存活（ur=0.30 grad=396 活）。社区从没真把"梯度爆炸"当 NCA 训练失败主因——本文厘清真正的因子是 update 稀疏度。
3. **机制可升级**（立项后赌点）：把 ur 临界关联到某可前验量（如信息传播半径 × 更新稀疏度的临界比），从"我们测到相变"升到"我们预言并验证临界"——这是顶过 standout 门槛的关键。

## 关键概念厘清（措辞红线，违反即跑偏）

- **塌缩 ≠ 发散**：diverged flag 0/36，梯度正常。塌缩 = 收敛到平凡背景解（trivial solution），不是 loss→NaN 的发散。claim 全程用「功能塌缩 / 平凡解」，**禁用「发散（divergence）」**。
- **fire_rate = async = 同一旋钮**：`stochastic = rand > fire_rate`，实际更新比例 = 1−fire_rate。不是两个独立因子（原 C044 的 corr=−1.0 是数学必然非 confound）。统一用 **update_rate = 1−fire_rate** 单轴表述。
- **梯度无关写"未观察到显著关联"**，不写"证明与梯度无关"（p>0.05 = absence of evidence，功效不足）。
- **诚实天花板**：当前单数据集小模型 = 中等会议料；standout 是立项后赌注，不在叙事里预支。

## 对手 / 差异化

- arXiv 2508.06389「Identity Increases Stability in NCA」：多 organism 形态边界崩溃 + identity 架构修复。**三重正交**（问题域 morphogenesis≠训练塌缩 / 数据 gecko≠医学 / 解法 identity≠相边界刻画）。须在 related work 显式引 + 差异化。
- distill 2020 Growing NCA / Med-NCA：把 fire_rate/async 当正则化/鲁棒手段，未系统研究塌缩边界——本文补这块空白。

## 数据

Med-NCA Hippocampus（Task04，本地 + HPC ready）；立项后扩 BraTS 切片 + 第二独立实现（如 M3D-NCA prostate）验普适性。
