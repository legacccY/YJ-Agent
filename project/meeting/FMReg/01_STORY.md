# FMReg STORY

> 故事框架。任务/数字与本文冲突 → 停下澄清，不硬干。立项日 2026-06-17。

## Headline（✅ 定稿 — K0v2 立项闸 YELLOW 固化后收窄，2026-06-18）

> **Headline 定稿（单一确定主轴）：FM-in-SVF 给出良好校准的形变后验（well-calibrated deformation posterior）。**
> FM warp-driven（零 teacher）的后验不确定性与配准误差**正相关**（校准好），明确区别于确定性 baseline 与 cVAE 概率 baseline 的**反校准**；少步采样 + diffeomorphic 拓扑保持（neg_jac=0%）+ 精度不退（Dice 与确定性 baseline 持平）。

**收窄依据（K0v2 两轮 HPC 实证，详证据链 + 04_LOG）**：
- K0v1（FM 蒸馏 vxm teacher）RED——蒸馏路线退化，作废。
- 重设计三臂 K0v2（A 确定性 / B cVAE VoxelMorph-prob 概率后验 / C FM warp-driven 零 teacher），skeptic 红队 + 能量地形探针 GREEN_PROBE（diffeomorphic 正则不填平多峰能量地形）放行。
- K0v2 修复重跑（job 1460205，24 distinct 歧义几何 + K=48 采样，多峰测试已有效）= **YELLOW 固化**：校准腿 GREEN（FM 硬赢，二次复现），多峰腿未立（dip CI 含 0），按预登记 YELLOW=校准赢、多峰平 → headline 收窄至「校准后验」。

**杀掉的旧候选**：
- **旧候选①「生成式 SVF *多解* 后验（多模态 / 多个合理形变）」→ KILLED。** K0v2 公平测试（24 distinct 歧义对 + K48）多峰未立：dip_C=0.1630 ≈ dip_B=0.1575（dip_diff CI=[−0.0038, 0.0156] 含 0，不显著）；bimodal_coeff_C=0.4466 < 0.555 阈、BC_B=0.4179，两臂均未达双峰。disp_spread_C=0.0037 > B=0.0016（C 后验**更宽但仍单峰**）。**不 claim 多解 / 多模态**，诚实写「后验更宽但单峰」。
- 候选②（diffeomorphic-centric）保持退路地位不变（见下卖点 + 02_ACCEPTANCE K1）。

**痛点**：可变形配准被 diffusion 配准的「慢」（多步采样）与回归式配准的「单点估计、过度平滑、不给可信不确定性」夹在中间。FM 生成式 + 少步采样破局点 = **给出可信赖（well-calibrated）的形变后验不确定性**，而非更多模态的解。

## 三段式故事

1. **痛点**：DiffuseMorph 类 diffusion 配准精度好但推理需多步、慢；VoxelMorph/TransMorph 一步快但是**单点估计**（过度平滑、不给不确定性），非 diff 版还可能折叠；prob-VoxelMorph（cVAE）虽出概率后验，但其不确定性**未必校准**（本实验实测反校准）。跨模态（CT-MRI）形变配准尤其难。
2. **洞察（K0v2 已实证）**：FM warp-driven 生成式建模（零 teacher，直接在 SVF 空间 flow）给出的形变后验**不确定性与配准误差正相关 = 良好校准**，而确定性 baseline 与 cVAE 概率 baseline 反校准。少步采样逼近，diffeomorphic 由 SVF+S&S 构造保证（不是 FM 的功劳）。**已证假说 = FM 在 SVF 生成上相对 cVAE 概率后验有不可替换的「校准质量」增益；未立假说 = FM 给多模态/多解（K0v2 多峰未立，已撤）。**
3. **证据链（K0v2 两轮实证）**：
   - ⚠️ 旧 G5 killshot 作废（恒等假基线 + near-identity 构造性 neg_jac=0% + 非真 FM，不构成证据，详 02_ACCEPTANCE A0 注）。
   - K0v1（job 1459750）RED：FM 蒸馏 vxm teacher 退化，蒸馏路线作废。
   - **K0v2 修复重跑（job 1460205，三臂 A/B/C，24 distinct 歧义几何 + K=48 采样，2000 步×3 臂，sigma_p=0.0800 数据驱动，prior_lambda=10 占位 TODO）= YELLOW 承重证据**：
     - **校准腿（FM 硬赢，二次复现 = 承重证据）**：BraTS rho_C=+0.5161 (p<1e-4) vs rho_B=−0.3890 (p<1e-4)；synth rho_C=0.9073 vs rho_B=−0.6954。FM 后验方差与配准误差正相关（校准），cVAE 反校准。
     - **精度不退**：dice_A=0.9461 / dice_C_ensemble=0.9444 / dice_B=0.9468（top40 大形变子集 dice_A=0.9259 / dice_C=0.9255）。
     - **拓扑**：neg_jac_pct 三臂全 0.0000%。
     - **多峰腿未立（旧候选①据此 KILLED）**：dip_C=0.1630 ≈ dip_B=0.1575（dip_diff CI=[−0.0038, 0.0156] 含 0）；BC_C=0.4466 < 0.555、BC_B=0.4179；disp_spread_C=0.0037 > B=0.0016（更宽但单峰）。
   - 真增益证据收窄为「校准质量」单点已立，多解证据撤回。完整 held-out L1-L4 + 机制解释待中训（Gate1/Gate2）。

## 卖点（差异化钩子，K0v2 后定稿，已收窄）

- **FM 不可替换增益（headline 核心，K0v2 已证）**：少步 FM 给的**良好校准形变后验**——后验不确定性与配准误差正相关（BraTS rho_C=+0.5161, p<1e-4），vs 确定性 baseline 与 cVAE 概率 baseline 的**反校准**（rho_B=−0.3890）。**这是 FMReg 唯一回归 / cVAE 替换不了的卖点。** ⚠️ **不再 claim「多解 / 多模态后验」**（K0v2 多峰未立，撤回）；卖点是「不确定性**质量**」不是「解的**数量**」。
- **少步**：≤4 步逼近 **diffusion 多步**（DiffuseMorph）精度（K2 验）。注：对照系是 diffusion，**不是**相对回归 baseline 的优势（VoxelMorph-diff 单次前向比少步还少步）。
- **拓扑安全（诚实措辞）**：SVF + scaling-squaring 在**连续域**构造性保证 diffeomorphism；离散实现实测折叠率低（K0v2 三臂 neg_jac=0%；IJCV 2024 证 S&S 离散仍可负 Jacobian，故**不写 guaranteed**，写 continuous-limit diffeomorphic + empirically near-zero folding）。
- **通用 benchmark / 跨模态**：脑(OASIS/IXI)/肺(Dir-Lab)/跨模态(AbdomenMRCT)——定位为**广度/泛化证据**（vs 对手全员只 cardiac），非核心创新。

## 与组合台其他项目边界（防重叠）

- **iclr (VisiSkin)**：皮肤质量诊断/增强，无配准。零重叠。
- **medad-failmap**：失败可预测性图谱（anomaly/外推判据），无配准/无 FM。零重叠。
- **nca-jepa / Med-NCA**：已封存，NCA 方向。零重叠。
- **bmvc**：封印。零重叠。

FMReg 是组合台唯一碰「配准 + flow matching」的项目，零内部撞车。

## 对手 baseline（必对照）

**头号对照（收窄后 = 校准质量对照）**：
- **prob-VoxelMorph / cVAE（概率后验 baseline）= 校准腿头号对照**（K0v2 中即臂 B，FM 校准要硬赢它才立得住——已二次复现赢，rho_C=+0.5161 vs rho_B=−0.3890）。
- **VoxelMorph-diff（SVF+S&S，单次前向，确定性）= 精度 + 拓扑对照**（FM 精度不能退、折叠率要相当——K0v2 即臂 A，dice 持平、neg_jac 均 0%）。
- 其余：VoxelMorph/TransMorph（回归一步）、DiffuseMorph/DiffuseReg（diffusion 多步，少步对照）、仿射、恒等。可选 LapIRN、TransMorph-diff、uniGradICON、PULPo（分层概率后验）、Learn2Reg leaderboard。官方超参见 03_探路计划 附录。

## 外部撞车风险（K3，2026-06-17 探路实证更新）

⚠️ **已发现直撞**：**FlowReg**（arXiv:2603.01073，2026-03，UCL/Imperial）已用 flow matching 做 2 步心脏配准。差异（FMReg 据此立足）：FlowReg 在 **displacement field 空间**做（FMReg 走 SVF 空间）、**无 diffeomorphic 保证**、**只 cardiac 2D**、是 **test-time refinement**（确定性 refinement，**不给后验**）、单步还输 CorrMLP baseline。残余新颖空间（K0v2 收窄后）=① **少步 FM 给的良好校准 SVF 后验**（核心，非多解）② 通用脑/肺 benchmark ③ 跨模态 MR-CT。投稿前 researcher 须再复查 2026-27 新成片。

⚠️ **后验配准是拥挤领域（撞车防护）**：prob-VoxelMorph（cVAE）、DiffuseMorph、PULPo（分层概率后验）等均已做「形变后验」。FMReg 差异化**不靠「有后验」本身**（已被占满），而靠 **(a) 少步 FM 采样 + (b) 后验的校准质量**——K0v2 实证 FM 后验校准（rho 正相关）显著优于 cVAE 反校准。这是收窄后唯一守得住的护城河。

## 诚实风险（MICCAI/投稿命门，2026-06-18 K0v2 后定）

- **机制未解 = Gate1 命门**：当前只有**实证** rho 优势（FM 校准好、cVAE 反校准），**为何 FM-in-SVF 校准优于 cVAE 的机制未给解释**。MICCAI 审稿大概率追问机制；Gate1 须补机制解释（如 FM 的连续 flow / 似然几何 vs cVAE 的 amortized 后验塌缩），**证不出 → 降级 TMLR analysis-track**（见 02_ACCEPTANCE K0 订正）。
- **多解卖点已撤**：勿在后续写作回流「多模态 / 多个合理形变」措辞——K0v2 多峰未立，只写「后验更宽但单峰 + 校准良好」。
- **校准证据样本**：rho 校准结论目前基于 BraTS + synth 两套，held-out 泛化 + 更大样本 + bootstrap CI 待中训补（写正文每个 rho 配 p、每个校准指标配 CI）。
- **单苗**：FMReg 仍是 run-002 唯一存活候选，无第二苗对冲。
