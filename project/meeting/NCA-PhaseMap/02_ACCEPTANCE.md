# NCA-PhaseMap — ACCEPTANCE CRITERIA

> 验收判据 + 书面 kill criteria 唯一真源。改阈值 = 拍板点。2026-06-17 立项首版。

---

## 🔄 第三次重启降级 — 当前生效判据（2026-06-22，用户拍板；详 04_LOG Entry 6）

> ⚠️ **下方「核心验收判据 A1–A4 + 雄心档位 + K1–K4」是立项首版，其中「普适尖锐临界」主 claim 已被 Gate1 K1/A2 证伪封存。本块为当前生效版**，与首版冲突以本块为准。首版 A1–A4 / K1 预登记规则**保留**（A2/A4 仍是要正面处理的硬伤，K1 预登记规则继续约束补实验②防 HARKing）。

**当前 headline（降级，弃普适）**：「NCA 医学分割训练中 update 稀疏度功能塌缩的**条件性**刻画——Hippo+clip=1.0 有确定断崖，BraTS/no-clip/跨 seed 不稳；正面贡献 = 刻画相变**成立/不成立的条件** + 谱半径/信息传播机制解释（PRIMER §6.4/6.7）+ NCA 训练**安全 fire_rate 区间实践指南**」。
> **R10-b 范围纪律**：headline 已收窄到「条件性 + 实践指南」，**不得**回写「普适/可前验普适常数」等外推字样（K1 已证伪）。措辞超范围 = 跑偏。

**🔒 写正文前必跑的前置 gate（feedback_falsify_crux_first，命门最先砸不拖到最后）**：Entry 6 的 **4 项补实验是写任何正文/定 headline 的前置条件**，未出读数不准写 §Method/§Results。承重命门 = **A2 跨 seed 随机性**（BraTS 5ur×5seed 全 MIXED 2/5,1/5,2/5,3/5,3/5 = 相变可能是随机塌缩概率事件非确定边界）。
- ① 修 M1 probe bug（全 nan 静默失败）→ 跑信息传播半径机制探针；
- ② BraTS no-clip 扩 ur（0.45–0.80，步长 0.05，5 seed）→ 判临界**漂移 vs 消失**（判定复用下方已冻结 K1 预登记规则，禁事后调宽）；
- ③ Hippo vs BraTS 差异机制假设（前景占比/patch）+ 单变量控制；
- ④ 找对齐第二实现替 MinimalNCA（当前 dice 0.3 vs 官方 0.7 = 无效对照）。

**重启版 kill criteria（比首版硬，防第四次重启）**：
- **K-new-1（核心，硬收口）**：4 补实验后跨 seed 相变**仍随机**（A2 翻不了案）→ 承认无确定相变，**彻底收口不再重启**。
- **K-new-2**：BraTS 全程任何条件**无断崖** → 降纯 Hippo 单集 analysis（弱）或收口。
- **K-new-3**：机制段（谱半径/传播半径 ↔ ur 临界）**拿不出实证关联** → 诚实 TMLR/workshop 不冲 ACCV。

---

## 核心验收判据（立项首版，普适主 claim 已证伪，见上方降级块）

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
