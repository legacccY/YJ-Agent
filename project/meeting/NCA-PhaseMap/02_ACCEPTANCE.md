# NCA-PhaseMap — ACCEPTANCE CRITERIA

> 验收判据 + 书面 kill criteria 唯一真源。改阈值 = 拍板点。2026-06-17 立项首版。

## 核心验收判据（投稿前必须全过）

- **A1 临界存在且尖锐**：≥2 个数据集上 update_rate 存在功能塌缩相变，过渡宽 ≤0.10，临界两侧 dice 断崖（非渐变）。✅ Hippocampus 已坐实（三重实证），待第二数据集。
- **A2 seed 稳定**：临界 update_rate 在 ≥3 seed 下方向一致（survive/collapse 多数判定不翻盘）。✅ C044c STABLE_SHARP（ur=0.35 3/3 活、ur=0.40 3/3 塌）。
- **A3 塌缩非梯度驱动**：塌缩与 max_grad_norm 无显著关联（措辞"未观察到显著关联"），且高梯度 cell 可存活。✅ 初证（r=0.238 p=0.16），投稿前补**梯度时序分析**（梯度先死 vs 网络先垮）定因果。
- **A4 普适性**（standout 前置，非中等会议必须）：BraTS/肺等第二数据集 + 第二独立 NCA 实现上临界相变复现 → 证非玩具/单实现 artifact。

## 雄心档位（诚实分级）

- **中等会议达标线**（A1-A3 + 单数据集诚实标注）：相边界刻画 + 反梯度直觉，投 TMLR/MIDL/analysis track 站得住。
- **standout 升级线**（再 + A4 + 机制命题）：把 ur 临界关联可前验量（信息传播半径 × 更新稀疏度临界比），从"测到"升到"预言并验证"。冲 MICCAI/NeurIPS D&B。

## 书面 kill criteria（立项即生效，触发即诚实回退）

- **K1（临界普适性）**：BraTS / 第二数据集上 update_rate 临界相变**消失或漂移到完全不同区间** → "可前验临界"塌 → 降级或 KILL。
- **K2（机制升级失败）**：投顶会前拿不出 ur 临界 ↔ 可前验量的机制命题 → **不硬冲 standout，诚实降级投 TMLR/MIDL/analysis**（不退稿，放弃 spotlight 叙事）。
- **K3（撞车复查）**：投稿前 researcher 复查 NCA 稳定性/相变是否出现成片（当前 2508.06389 正交、空白真实，方向有人动须复核）。
- **K4（梯度因果反转）**：若梯度时序分析显示梯度其实是塌缩前驱（先死）→ 改写 A3 claim，不强行"与梯度无关"。

## K1 预登记判定规则（2026-06-18 冻结，跑 BraTS 前生效，防 HARKing）

> Gate1 设计经 skeptic 红队（🟡-5）：原 [0.25,0.50] 区间过宽（实测 Hippo 过渡区仅 0.30→0.40），让 K1 几乎不可能 KILL=失去筛选力。改挂钩实测 ur*_hippo±0.10。**动 coder 前冻结 + git commit 留痕，事后不得调宽区间。**

```
ur*_hippo = Hippo **no-clip** 实测临界点（B2 在 Hippo no-clip 同管线复测；G5 的 0.35 带非官方 clip 仅历史参考，以 no-clip 复测为准记 git，复测值与 0.35 差异即 🔴-6 归因证据）
ur*_brats = 腿① B2/B3 BraTS 实测临界点
过渡宽 w  = dice 从高台跌破 collapse 阈跨越的 ur 区间宽度

PASS（A4 第二数据集复现）：ur*_brats ∈ [ur*_hippo−0.10, +0.10] = [0.25, 0.45] 且 w≤0.10 且高 ur 档 dice 显著 > dice_bg
KILL（K1 触发）：临界消失（无断崖 / w>0.10）或 ur*_brats 漂出 [0.25, 0.45]
假 KILL（不判 K1，回查数据）：全程 dice ≈ dice_bg（判据失效）→ 查前景占比/归一化/mask 配对
灰区（拍板点 4 停报）：ur*_brats ∈ [0.45, 0.625]（合理 NCA 区间但偏离）→ 不 KILL，headline 数值从「≈0.375 普适常数」改「区间一致、点位数据依赖」
```

collapse 判据（跨集自适应，B0 标定后冻结）：`collapse := final_dice < max(0.01, dice_bg + 3·σ_bg)`。Hippo dice_bg≈0 退回 ≈0.01（不破既往三重实证）；BraTS 自适应抬阈防低前景假 collapse（实测 BraTS 前景 median 5%/min 0.36%）。B0 的 dice_bg/σ_bg 跑前写 config 冻结。

## 复现红线（全程）

- 零偏离官方：NCA 架构/超参照 Med-NCA 官方（LR=16e-4 / betas=(0.5,0.5) / 300 step / channel=16），禁私改凑收敛。
- ⚠️ **CLIP_NORM 复核结论（2026-06-18 researcher 核官方 repo）**：官方 Med-NCA `train_Med_NCA.ipynb` + `Agent.py` L76-105 **从不用 `clip_grad_norm_`**（distill 2020 用 per-variable L2 norm 是另一回事）。G5 沿用的 CLIP_NORM=1.0 = **非官方自加**，且可能污染 A3「塌缩与梯度无关」（名义 grad 被裁到 1.0）。Gate1 主结果改**官方无 clip**，clip=1.0 作对照解释 G5；腿② A3 因果必在无 clip 下重测。**触复现红线，已报用户。**
- 数字一律 Bash/Grep 核 csv，入文前过 verifier。
