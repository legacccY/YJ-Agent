# NCA-PhaseMap — NCA 训练功能塌缩相边界

> 项目入口。深读档顺序：本文 → `01_STORY.md` → `02_ACCEPTANCE.md` → `04_LOG.md` 最新 entry。
> 源 = ideation run-003（NCA × 医学图像）G6 唯一存活旗舰 C044，2026-06-17 用户拍板立项。

## 一句话

NCA 医学图像分割训练中，**update 稀疏度**（fire_rate / 等价 async，代码上同一旋钮）存在一条**尖锐、可前验的功能塌缩临界相边界**：越过临界（update_rate ≈ 0.375 / fire_rate ≈ 0.625）即塌缩到平凡背景解，**且与梯度幅度无关**——首次系统刻画。

## 为什么新（researcher 核实）

- 与 arXiv 2508.06389（identity 解多 organism 形态崩溃）**问题/数据/解法三重正交**，不撞车。
- 「NCA update 稀疏度 → 功能塌缩相边界」正面命题 = **真空白**（社区只把 fire_rate=50% 当固定超参直接用）。
- 组合台有 Med-NCA 复现的一手 organic 负结果当起点数据。

## 立项依据（G5 三重独立实证）

| 实验 | 结论 |
|---|---|
| 原 C044（36 cell）| 19/36 功能塌缩（dice→0.0011，diverged 0/36=塌缩非发散）；与 max_grad_norm 无关（r=0.238 p=0.16）|
| C044b（单轴 ur 细扫 12 cell）| 临界 ur 0.35→0.40 断崖（dice 0.104→0.001，−94.9%）= **SHARP** |
| C044c（4 ur × 3 seed）| **STABLE_SHARP**：ur=0.35 三 seed 全活、ur=0.40 三 seed 全塌 |

## 诚实天花板（立项即知）

当前 = **强 analysis / 中等会议**料（单数据集 Hippocampus、小模型、存活区 dice 0.10-0.37 偏低）。冲 **standout** 需立项后：① **机制升级**（把 ur 临界关联可前验量，从"测到相变"→"预言并验证临界"）；② BraTS / 第二独立实现验证普适性。书面 kill criteria K1-K4 见 STORY/ACCEPTANCE。

## 文件导航

| 路径 | 内容 |
|---|---|
| `01_STORY.md` | 战略叙事 + headline + 卖点 + 措辞红线 |
| `02_ACCEPTANCE.md` | 验收判据 + 书面 kill criteria K1-K4 |
| `04_LOG.md` | 进度留痕（倒序）|
| `00_provenance/` | 来源溯源（G6 立项卡 + G5 killshot csv 指针）|

## 来源全档

`project/ideation/runs/2026-06-17_run-003_nca-medimg/07_report/G6_proposal_card_C044.md`（立项卡）+ `06_experiments/results/c044*.csv`（G5 实证）。

## venue

top：MICCAI 2026 / NeurIPS D&B｜fallback：TMLR / MIDL / analysis track。
