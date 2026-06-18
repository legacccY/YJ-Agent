# FMReg ACCEPTANCE + Kill Criteria

> 验收判据 + 书面 kill criteria（立项即生效，触发即诚实回退，不洗数据凑 PASS）。立项日 2026-06-17。
> 数字一律 Bash/Grep 核 csv 不信 Read；超参查官方源查不到标 TODO；复现零偏离。

## A. 核心验收 lever（达标才算论文成立）

| Lever | 判据 | 数据 |
|---|---|---|
| **L0 承重·校准后验**（K0v2 收窄后新承重 lever，原「多解后验」已撤）| **校准证据 = rho + AUSE + ECE + NCC_VX/LM 四指标方向一致**（领域标准命名，对齐 PULPo / WACV2022 / Structured SIR 审稿人预期）。GREEN 须四指标**一致优**（不是单 rho）：FM(C) 四指标全优于强 baseline（deep ensemble）与 cVAE(B)、且 B 在 AUSE/ECE 反校准；非 GREEN 即按 A0 口径降级。详四指标定义 + 判定口径见 `05_Gate1_matrix.md` §3 | BraTS2021 / IXI / OASIS held-out + deep ensemble + cVAE 对照 |
| L1 拓扑合法 | 完整 FM 配准 held-out 上 `neg_jac_pct` 低（目标 < 1%，硬上界见 K1）| OASIS / Learn2Reg held-out |
| L2 精度 | Dice（或 TRE/landmark）≥ TransMorph baseline 且**不退于确定性 baseline**，目标接近/超 DiffuseMorph | BraTS2021 / OASIS / Learn2Reg |
| L3 少步卖点 | ≤4 步推理 Dice 掉点 ≤2% vs diffusion 多步（K2 闸）| 同上 |
| L4 跨模态 | CT-MRI 形变配准上不塌（相对回归 baseline 有优势）| Learn2Reg CT-MRI |

## A0. 🛑 立项闸 killshot 结局 = **YELLOW 固化 → headline 收窄**（2026-06-18 定）

**K0（FM 增益）已跑完两轮，结局 YELLOW（非 GREEN 非 RED）**：校准腿 GREEN（FM 校准显著优）+ 多峰腿未立（dip CI 含 0），按预登记 YELLOW=校准赢、多峰平 → **headline 收窄至「FM-in-SVF 给出良好校准的形变后验」，撤回「多解 / 多模态」claim，进 Gate1**。

**两轮实证（job + 已核实数字，csv `killshot_K0v2_three_arm_HPC_fixed.csv` 原值）**：
- **K0v1 = RED（job 1459750）**：FM 蒸馏 vxm teacher 路线退化，作废。
- **K0v2 修复重跑 = YELLOW（job 1460205）**：三臂 A 确定性 / B cVAE VoxelMorph-prob 概率后验 / C FM warp-driven 零 teacher；24 distinct 歧义几何 + K=48 采样（修复了首跑的 synth 5× 假重复 / cluster_sep 饱和 / K=8 太小），多峰测试 now 有效。2000 步×3 臂，sigma_p=0.0800（数据驱动）。prob-VoxelMorph 对照超参 = **prior_lambda=10**（官方 Dalca2019，researcher 核定；03 附录写 25 是错的，以 10 为准）+ **image_sigma=0.02**（FMReg 现 0.01 须改 0.02）。
  - **校准腿（GREEN，FM 硬赢，二次复现 = 承重证据）**：BraTS rho_C=+0.5161 (p<1e-4) vs rho_B=−0.3890 (p<1e-4)；synth rho_C=0.9073 vs rho_B=−0.6954。FM 后验方差与配准误差**正相关**（校准好），cVAE **反校准**。
  - **精度不退**：dice_A=0.9461 / dice_C_ensemble=0.9444 / dice_B=0.9468（top40 大形变子集 dice_A=0.9259 / dice_C=0.9255）。
  - **拓扑**：neg_jac_pct 三臂全 0.0000%。
  - **多峰腿未立（旧候选① KILLED）**：dip_C=0.1630 ≈ dip_B=0.1575（dip_diff CI=[−0.0038, 0.0156] 含 0，不显著）；bimodal_coeff_C=0.4466 < 0.555 阈、BC_B=0.4179（两臂均未达双峰）；disp_spread_C=0.0037 > B=0.0016（C 后验更宽但单峰）。

**📌 K0 判据订正（机制命门，YELLOW 后新增）**：实证 rho 校准优势已立，但**「为何 FM-in-SVF 校准优于 cVAE」的机制未解**。Gate1 须补机制解释（非纯实证 rho）——MICCAI 大概率追问。
- **证出机制** → headline 「校准后验」站稳，走 MICCAI。
- **证不出机制（只有实证）** → **降级 TMLR analysis-track**（实证 calibration study，不强行 claim 机制创新），报拍板。

> 此 killshot 替代旧 G5（旧 killshot 已诚实作废：恒等假基线 + near-identity 构造性 neg_jac=0% + 非真 FM，不构成证据，详 01_STORY 证据链 + 真实实力评估报告）。能量地形探针 GREEN_PROBE（diffeomorphic 正则不填平多峰能量地形）+ skeptic 红队均已放行三臂设计。

## A0′. 🔒 Gate1 预登记 PASS 表（防 HARKing，2026-06-18 落，照搬 `05_Gate1_matrix.md` §4 + §6）

> **跑前冻结、不事后改门**。Gate1 升级为四指标 + 强 baseline（deep ensemble）+ 2×2 因子设计后，须把数值 PASS 门 + 三结局解读口径 + 证伪整机制叙事的硬退路在看结果前正式锚定，否则升级指标无判据锚 + 防不住 HARKing。本表为 planner 出 → skeptic 复裁 0 致命 GREEN 的设计闸产物，数字全取自 05 矩阵，不自创阈值。
> 臂命名（05 §1）：A=确定性 baseline（VoxelMorph-diff，无后验）；B=cVAE 概率后验（prob-VoxelMorph，已知塌缩，不再当唯一对手）；C=FM warp-driven（本文方法）；**DE=deep ensemble（N≥5 臂 A 不同 seed 方差当后验，强非塌缩概率 baseline，skeptic RED-2 新增）**。

### A0′.1 G2-A gating 硬门（第一棒，串行，不只比塌掉的 cVAE）

- **硬门**：`rho_C 显著 > rho_DE`（deep ensemble 强 baseline，**配对检验 p < 0.05 或 bootstrap CI 不重叠**）**AND** `rho_C > rho_B`，且 dice_C 不退。
- **FAIL（强 baseline 反超 / 打平）→ 停报、降 TMLR analysis-track、不洗数据**。这是 skeptic 要的真考验：若 DE 也校准好（rho_DE > 0 且 ≈ rho_C），FM 不可替换性塌。
- 算力兜底：先拍阶段 1 G2-A gating（含 DE 约 5 子 run，约 60 GPU·h）；G2-A PASS（rho_C 显著 > DE）再拍阶段 2 全量，省得 headline 在 3D / 强 baseline 下不复现时白烧 500+ GPU·h。

### A0′.2 机制组 2×2 因子预登记（损失 × 采样，四格取干净边际效应）

> Δ 门一律「由 G2-A 标定、在看 FM 四格结果前冻结」（skeptic 🟢-C），不事后改。

| 假设 | 干净对照 | PASS 门（预登记，跑前冻结） | 三结局解读口径 |
|---|---|---|---|
| **整机制（A0）** | C vs DE | `rho_C 显著 > rho_DE`（CI 不重叠 / 配对 p<0.05）且 rho_C 跨绝对 0 线 | a 立 → MICCAI 机制章；b C≈DE 不显著 → 降 TMLR 不洗；c C<DE → headline 塌、报拍板 |
| **H1 损失主效应** | loss 主效应 (格1+格2)−(格3+格4) | 换 ELBO 后 rho 下降 ≥ Δ_loss（**由 G2-A 标定、看四格前冻结**，pilot 暂记 ≥0.3 待定）且跨正负绝对线 | 单一主因 / 交互显著才配多采样共担 / 无显著变化 → 损失非主因，不许改写联合贡献 |
| **H2 采样主效应** | 采样主效应 (格1+格3)−(格2+格4) | 换单后验后 rho 下降 ≥ Δ_samp（同上冻结口径），且 sigma_p 前置已排除 sigma_p 主导 | 同上口径结合 sigma_p 曲线；sigma_p 若是主因则 H2 结论作废、曲线进附录 |
| **交互项** | 格1−格2−格3+格4 | 交互显著（**CI 排除 0**）才能 claim 损失 × 采样**共担** | 不显著则只 claim 主效应较大者，不许硬写共担 |
| **H3 time-cond** | M3a vs M3b vs M3c | M3a 显著 > M3c，M3b 定位 time-cond 是否独立于多步积分 | 独立贡献 / 仅多步积分 / 无贡献 三档，按实测落，不许含糊改写 |

### A0′.3 证伪整机制叙事的硬退路

**强 baseline（deep ensemble）下 FM 不显著赢 → A0 机制证不出 → headline 机制章降 TMLR analysis-track，诚实写实证 calibration study，不强 claim 机制创新、不洗数据**。报拍板。这是预登记的「整叙事可证伪线」，与 A0 的 MICCAI/TMLR 二分一致。

## B. 书面 Kill Criteria（任一触发 → 诚实回退/降级，报拍板）

- **K1（拓扑·诚实措辞）**：完整 FM 配准在 OASIS / Learn2Reg **held-out 大形变** 上折叠率 `neg_jac_pct` **未显著低于回归 baseline（VoxelMorph/TransMorph 非 diff 版）** 或 **不与 VoxelMorph-diff 相当** → 拓扑卖点塌 → **降级**。**写作禁「topology-guaranteed」**，只写 continuous-limit diffeomorphic + 实测低折叠率（IJCV 2024 证 S&S 离散仍可负 Jacobian）。Dice ≤ TransMorph → **KILL**。
- **K2（卖点·快）**：少步（≤4 步）推理 Dice 掉点 **> 2% vs diffusion 配准多步（DiffuseMorph/DiffuseReg）** → 「少步逼近 diffusion」卖点塌 → **降级或 KILL**。⚠️ 对照系**钉死为 diffusion 多步**，**不得**把「少步保拓扑」写成相对回归 baseline 的优势（VoxelMorph-diff 单次前向比少步还少步）。
- **K3（撞车）**：FlowReg(2603.01073) 已直撞（探路实证，确定性 refinement 无后验）→ FMReg 据「**少步 FM 给的良好校准 SVF 后验** + 通用 benchmark + 跨模态」残余新颖立足。⚠️ 后验配准是拥挤领域（prob-VoxelMorph/DiffuseMorph/PULPo 均做后验），FMReg 护城河收窄为 **(a) 少步 FM + (b) 校准质量**（非「有后验」本身）。投稿前 researcher 再复查 2026-27 有无新成片占满残余 → 据残余新颖性**降级/KILL**。⚠️ **Structured SIR（arXiv:2603.17415，SIR 非 FM 后验配准）非直接撞车但近**，related work 须正面区分（FMReg = warp-driven flow matching 后验，非 stochastic interpolant / SIR 采样器）。

## C. 立项前已知风险（须消解，非 kill 但盯）

- **R1 理论（已复核 2026-06-17）**：researcher+skeptic 结论 = FM 积分 ODE 连续域可保 diffeomorphism（Lipschitz 速度场 Picard-Lindelöf），**但**①离散实现不自动（IJCV 2024）②diffeomorphic 功劳属 SVF+S&S 老构造**非 FM**。→ 措辞已订正（K1 禁 guaranteed）；**FM 的不可替换价值改由 K0 killshot 证**（生成式后验，非 diffeomorphic）。
- **R1' 范畴矛盾（skeptic 🔴，K0v2 部分消解）**：SVF stationary vs FM time-dependent，FM-in-SVF 可能退化成「VoxelMorph-diff 换采样器」。K0v2 校准腿 FM 校准显著优于 cVAE（rho_C 二次复现）→ FM 增益**在「校准质量」维度已存活**（不是纯换采样器）；但增益收窄到校准、非多解，且**机制未解**（命门，见 A0 订正）。
- **R2 单苗**：run-002 G5 唯一存活候选，无第二苗对冲（用户并行申 VinDr 标注复活 S4-05 作潜在第二项目，独立线）。

## D. Gate 设计（进中训前）

- **Gate0（立项闸 killshot，✅ 完成 = YELLOW）**：K0v2 三臂对照（job 1460205）→ YELLOW 固化，headline 收窄至「校准后验」，进 Gate1。详 A0。
- **Gate1（数据就绪 + baseline 对照线 + 🔑 机制解释）**：IXI/OASIS + AbdomenMRCT 下载就绪 + VoxelMorph(-diff)/TransMorph/DiffuseMorph + **prob-VoxelMorph/cVAE** 官方超参跑通对照线（超参见 03_探路计划 附录）；**新增承重项 = 给「FM 校准优于 cVAE」的机制解释**（A0 命门，证不出降级 TMLR）。过了进中训。
- **Gate2（中训 held-out）**：L1-L4 在 held-out 上读数，对照 K1/K2 闸。
