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

## A0. 🛑 立项闸 killshot（headline 定稿前必跑，<1 GPU·h，skeptic 2026-06-17 红队前置）

**K0（FM 增益）= 决定 headline 走候选①还是降级**：同数据同 backbone，最小对照 **VoxelMorph-diff（单次前向出 SVF + S&S）vs FM-in-SVF（多步采样 SVF + 同一 S&S）**。
- 看 FM 版在 ① Dice / ② 折叠率 `neg_jac_pct` / ③ **不确定性校准 / 多解后验质量**（FM 主场）上对 VoxelMorph-diff 的增益。
- **GREEN（FM 有不可替换增益，尤其 posterior/校准/难配准对）** → headline 走候选①「生成式 SVF 后验」，进中训。
- **RED（FM 版对 VoxelMorph-diff 无可测增益）** → FM-in-SVF 退化坐实 = 「换个采样器」增量 → **headline 不立、报拍板降级/转向**，省 80 GPU·h。

> 此 killshot 替代旧 G5（旧 killshot 已诚实作废：恒等假基线 + near-identity 构造性 neg_jac=0% + 非真 FM，不构成证据，详 01_STORY 证据链 + 真实实力评估报告）。

## B. 书面 Kill Criteria（任一触发 → 诚实回退/降级，报拍板）

- **K1（拓扑·诚实措辞）**：完整 FM 配准在 OASIS / Learn2Reg **held-out 大形变** 上折叠率 `neg_jac_pct` **未显著低于回归 baseline（VoxelMorph/TransMorph 非 diff 版）** 或 **不与 VoxelMorph-diff 相当** → 拓扑卖点塌 → **降级**。**写作禁「topology-guaranteed」**，只写 continuous-limit diffeomorphic + 实测低折叠率（IJCV 2024 证 S&S 离散仍可负 Jacobian）。Dice ≤ TransMorph → **KILL**。
- **K2（卖点·快）**：少步（≤4 步）推理 Dice 掉点 **> 2% vs diffusion 配准多步（DiffuseMorph/DiffuseReg）** → 「少步逼近 diffusion」卖点塌 → **降级或 KILL**。⚠️ 对照系**钉死为 diffusion 多步**，**不得**把「少步保拓扑」写成相对回归 baseline 的优势（VoxelMorph-diff 单次前向比少步还少步）。
- **K3（撞车）**：FlowReg(2603.01073) 已直撞（探路实证）→ FMReg 据「生成式 SVF 后验 + 通用 benchmark + 跨模态」三点残余新颖立足；投稿前 researcher 再复查 2026-27 有无新成片占满残余 → 据残余新颖性**降级/KILL**。

## C. 立项前已知风险（须消解，非 kill 但盯）

- **R1 理论（已复核 2026-06-17）**：researcher+skeptic 结论 = FM 积分 ODE 连续域可保 diffeomorphism（Lipschitz 速度场 Picard-Lindelöf），**但**①离散实现不自动（IJCV 2024）②diffeomorphic 功劳属 SVF+S&S 老构造**非 FM**。→ 措辞已订正（K1 禁 guaranteed）；**FM 的不可替换价值改由 K0 killshot 证**（生成式后验，非 diffeomorphic）。
- **R1' 范畴矛盾（skeptic 🔴，待 K0 消解）**：SVF stationary vs FM time-dependent，FM-in-SVF 可能退化成「VoxelMorph-diff 换采样器」。K0 killshot 证 FM 增益→存活；无增益→降级。
- **R2 单苗**：run-002 G5 唯一存活候选，无第二苗对冲（用户并行申 VinDr 标注复活 S4-05 作潜在第二项目，独立线）。

## D. Gate 设计（进中训前）

- **Gate0（立项闸 killshot，进行中）**：K0（VoxelMorph-diff vs FM-in-SVF 增益对照，<1 GPU·h）→ GREEN 定 headline 候选① + 进 Gate1；RED 报拍板降级。
- **Gate1（数据就绪 + baseline 对照线）**：IXI/OASIS + AbdomenMRCT 下载就绪 + VoxelMorph(-diff)/TransMorph/DiffuseMorph 官方超参跑通对照线（超参见 03_探路计划 附录）。过了进中训。
- **Gate2（中训 held-out）**：L1-L4 在 held-out 上读数，对照 K1/K2 闸。
