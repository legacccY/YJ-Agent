# FMReg STORY

> 故事框架。任务/数字与本文冲突 → 停下澄清，不硬干。立项日 2026-06-17。

## Headline（🛑 待定 — killshot 后定主轴，2026-06-17 skeptic 红队改）

> **当前不锁 headline 主轴。** skeptic 红队（03_探路计划 + 04_LOG Entry 3）查出：原拟「Diffeomorphic FM in SVF space」把「diffeomorphic / 少步」的功劳归错给 FM——这俩实为 **SVF + scaling-squaring** 老构造（2007 DARTEL / 2019 VoxelMorph-diff）送的，不是 FM 给的；且 SVF 是 stationary、FM 本命是 time-dependent velocity，强塞 SVF 空间可能退化成「VoxelMorph-diff 换个采样器」。**FM 的不可替换增益必须先用 killshot 证出来，才能定 headline。**

**两个候选主轴（killshot 结果二选一）**：
- **候选①（skeptic 推荐，FM 不可替换）**：*Few-step generative flow matching for deformable registration* —— FM 多步采样**建模形变后验**（同一对图像多个合理形变 / 不确定性校准），回归式（VoxelMorph-diff）只出过度平滑的单点均值。diffeomorphic 拓扑安全降为 SVF+S&S 免费搭车属性 + 诚实措辞，不当主卖点。
- **候选②（带债，弱）**：维持 diffeomorphic-centric，但需 killshot 证 FM-in-SVF 相对 VoxelMorph-diff 有实质增益，否则坐实增量。

**痛点（两候选共用）**：可变形配准被 diffusion 配准的「慢」（多步采样）与回归式配准的「单点估计、过度平滑、拓扑不保证」夹在中间。FM 生成式 + 少步采样有望破局——但**「破哪个局」由 killshot 定**。

## 三段式故事

1. **痛点**：DiffuseMorph 类 diffusion 配准精度好但推理需多步、慢；VoxelMorph/TransMorph 一步快但是**单点估计**（过度平滑、不给不确定性），非 diff 版还可能折叠。跨模态（CT-MRI）形变配准尤其难。
2. **洞察（待 killshot 证）**：FM 生成式建模有望给出形变**后验**（多解 + 不确定性），而非回归单点；少步采样逼近，diffeomorphic 由 SVF+S&S 构造保证（不是 FM 的功劳）。**关键未证假说 = FM 在 SVF 生成上相对单次回归（VoxelMorph-diff）有不可替换增益。**
3. **证据链（诚实订正）**：⚠️ G5 killshot（BraTS2021 flair 2D，**非 OASIS**）的 `neg_jac=0%` 是 **near-identity 微位移构造上的必然**（out_conv std=1e-4 + 200 步 + 微量级 target），`dice_affine` 实为**恒等基线**（非真仿射），用的也非真 FM（手搭强度梯度代理）——**该 killshot 不构成「FM 能配准」的证据，skeptic 的 🔴 范畴矛盾未被反驳。** 真证据待立项闸 killshot（VoxelMorph-diff vs FM-in-SVF FM 增益对照）+ 中训。

## 卖点（差异化钩子，待 killshot 验后定稿）

- **FM 不可替换增益（候选①核心，待证）**：生成式形变后验（多解 / 不确定性校准），vs VoxelMorph-diff 单点回归。**这是 FM 唯一回归替换不了的卖点，killshot 主攻此点。**
- **少步**：≤4 步逼近 **diffusion 多步**（DiffuseMorph）精度（K2 验）。注：对照系是 diffusion，**不是**相对回归 baseline 的优势（VoxelMorph-diff 单次前向比少步还少步）。
- **拓扑安全（诚实措辞）**：SVF + scaling-squaring 在**连续域**构造性保证 diffeomorphism；离散实现实测折叠率低（IJCV 2024 证 S&S 离散仍可负 Jacobian，故**不写 guaranteed**，写 continuous-limit diffeomorphic + empirically near-zero folding）。
- **通用 benchmark / 跨模态**：脑(OASIS/IXI)/肺(Dir-Lab)/跨模态(AbdomenMRCT)——定位为**广度/泛化证据**（vs 对手全员只 cardiac），非核心创新。

## 与组合台其他项目边界（防重叠）

- **iclr (VisiSkin)**：皮肤质量诊断/增强，无配准。零重叠。
- **medad-failmap**：失败可预测性图谱（anomaly/外推判据），无配准/无 FM。零重叠。
- **nca-jepa / Med-NCA**：已封存，NCA 方向。零重叠。
- **bmvc**：封印。零重叠。

FMReg 是组合台唯一碰「配准 + flow matching」的项目，零内部撞车。

## 对手 baseline（必对照）

**VoxelMorph-diff（SVF+S&S，单次前向，diffeomorphic）= killshot + 中训头号对照**（FM 增益要超它才立得住）。其余：VoxelMorph/TransMorph（回归一步）、DiffuseMorph/DiffuseReg（diffusion 多步）、仿射、恒等。可选 LapIRN、TransMorph-diff、uniGradICON、Learn2Reg leaderboard。官方超参见 03_探路计划 附录。

## 外部撞车风险（K3，2026-06-17 探路实证更新）

⚠️ **已发现直撞**：**FlowReg**（arXiv:2603.01073，2026-03，UCL/Imperial）已用 flow matching 做 2 步心脏配准。差异（FMReg 据此立足）：FlowReg 在 **displacement field 空间**做（FMReg 走 SVF 空间）、**无 diffeomorphic 保证**、**只 cardiac 2D**、是 **test-time refinement**（非生成式后验）、单步还输 CorrMLP baseline。残余新颖空间「中等偏窄」=① 生成式 SVF 后验 ② 通用脑/肺 benchmark ③ 跨模态 MR-CT。投稿前 researcher 须再复查 2026-27 新成片。
