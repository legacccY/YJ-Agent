# FMReg STORY

> 故事框架。任务/数字与本文冲突 → 停下澄清，不硬干。立项日 2026-06-17。

## Headline

**Flow matching turns deformable registration into a few-step, topology-safe transport problem.**
可变形配准长期被 diffusion 配准的「慢」（多步采样）与回归式配准的「拓扑不保证」（VoxelMorph/TransMorph 可能折叠）夹在中间。FM 的直线 OT 传输天生「少步 + 连续流」，把形变场当 flow target 学，有望同时拿到「快」与「diffeomorphism」。

## 三段式故事

1. **痛点**：DiffuseMorph 类 diffusion 配准精度好但推理需多步、慢；VoxelMorph/TransMorph 一步快但不保证拓扑合法（负雅可比 = 解剖折叠 = 临床不可用）。跨模态（CT-MRI）形变配准尤其难。
2. **洞察**：FM 学的是从源到目标的**直线速度场**，积分即得连续形变；少步 Euler 积分就能逼近，且流的连续性利于约束 diffeomorphism。FM 在图像合成证明了「直线 = 少步高质量」，配准范畴尚空白。
3. **证据链**：G5 雅可比闸（OASIS 2D 单步）已证 `neg_jac=0%` + 胜仿射 → skeptic「FM≠形变场范畴塌」的 🔴 快测不成立。中训补完整 velocity→diffeomorphism + 少步 vs diffusion 多步的精度/速度 trade-off。

## 卖点（差异化钩子）

- **少步**：≤4 步逼近 diffusion 多步精度（K2 验）。
- **拓扑安全**：FM 连续流 + 雅可比正则 → 无折叠（K1 验）。
- **范畴新**：FM-as-deformation-field，区别于 FM 图像合成、区别于 diffusion 配准、区别于回归配准。

## 与组合台其他项目边界（防重叠）

- **iclr (VisiSkin)**：皮肤质量诊断/增强，无配准。零重叠。
- **medad-failmap**：失败可预测性图谱（anomaly/外推判据），无配准/无 FM。零重叠。
- **nca-jepa / Med-NCA**：已封存，NCA 方向。零重叠。
- **bmvc**：封印。零重叠。

FMReg 是组合台唯一碰「配准 + flow matching」的项目，零内部撞车。

## 对手 baseline（必对照）

VoxelMorph、TransMorph（回归式，一步）、DiffuseMorph（diffusion，多步）、仿射基线。可选 LapIRN、Learn2Reg leaderboard 方法。

## 外部撞车风险（K3）

FM 方向热，投稿前必须 researcher 复查 2026-27 有无「flow-matching registration」成片。G3 撞车核验当前未发现直接撞，但须复核（FM-for-registration 是显然的 next step，可能有并行工作）。
