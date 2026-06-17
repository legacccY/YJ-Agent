# FMReg ACCEPTANCE + Kill Criteria

> 验收判据 + 书面 kill criteria（立项即生效，触发即诚实回退，不洗数据凑 PASS）。立项日 2026-06-17。
> 数字一律 Bash/Grep 核 csv 不信 Read；超参查官方源查不到标 TODO；复现零偏离。

## A. 核心验收 lever（达标才算论文成立）

| Lever | 判据 | 数据 |
|---|---|---|
| L1 拓扑合法 | 完整 FM 配准 held-out 上 `neg_jac_pct` 低（目标 < 1%，硬上界见 K1）| OASIS / Learn2Reg held-out |
| L2 精度 | Dice（或 TRE/landmark）≥ TransMorph baseline，目标接近/超 DiffuseMorph | BraTS2021 / OASIS / Learn2Reg |
| L3 少步卖点 | ≤4 步推理 Dice 掉点 ≤2% vs diffusion 多步（K2 闸）| 同上 |
| L4 跨模态 | CT-MRI 形变配准上不塌（相对回归 baseline 有优势）| Learn2Reg CT-MRI |

## B. 书面 Kill Criteria（任一触发 → 诚实回退/降级，报拍板）

- **K1（拓扑）**：完整 FM 配准在 OASIS / Learn2Reg **held-out** 上 `neg_jac_pct > 5%` **或** Dice ≤ TransMorph baseline → **KILL**。
- **K2（卖点·快）**：少步（≤4 步）推理 Dice 掉点 **> 2%** vs diffusion 配准多步 → 「FM 又快又准」卖点塌 → **降级或 KILL**。
- **K3（撞车）**：投稿前 researcher 复查 2026-27 有 **FM-registration 成片**直接占核心方法 → 据残余新颖性**降级/KILL**。

## C. 立项前已知风险（须中训消解，非 kill 但盯）

- **R1 FM-proxy caveat**：G5 killshot 用简化 FM target 代理；几何雅可比已干净，但完整 velocity→diffeomorphism 理论保证（LDDMM/测地线层面）未证。**立项后第一硬前置 = 派 researcher + skeptic 复核该理论是否成立**，不成立则 headline 从「保证 diffeomorphism」降为「经验无折叠」。
- **R2 单苗**：本项目是 run-002 G5 唯一存活候选，无第二苗对冲（用户已并行申 VinDr 标注复活 S4-05 作潜在第二项目，独立线）。

## D. Gate 设计（进中训前）

- **Gate1（理论 + 数据就绪）**：R1 理论复核出结论 + OASIS/Learn2Reg 下载就绪 + baseline（VoxelMorph/TransMorph/DiffuseMorph）跑通对照线。过了才进完整中训。
- **Gate2（中训 held-out）**：L1-L4 在 held-out 上读数，对照 K1/K2 闸。
