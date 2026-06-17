# FMReg Gate1 探路计划

> 立项后第一棒。源动机 = `真实实力评估_FMReg_S4-05.md`（run-002 07_report）查出 FMReg 黄牌：killshot GREEN 站不住 + FlowReg 已直撞。探路目标 = 在进中训前，把两条命门摸到底，决定 headline 怎么改、值不值得硬碰 FlowReg。
> 探路日 2026-06-17。纪律：查不到标 TODO 绝不臆想；超参查官方源；数字带引用。探路只调研不写码不跑训练。

## 两条命门（探路要回答的核心问题）

- **命门 A（理论）**：FM 学的速度场积分成形变 φ，能不能**保证** diffeomorphism（拓扑合法、可逆、无折叠）？还是只能经验上「通常不折叠」？这决定 headline 写「topology-safe / diffeomorphic guarantee」还是降级为「empirically fold-free」。
- **命门 B（差异化）**：FlowReg（arXiv:2603.01073）已用 FM 做 2 步心脏配准。FMReg 还剩多少独家空间？速度场 FM vs FlowReg 的位移场 FM 到底差在哪、是不是真优势？通用 benchmark（脑/肺/跨模态）是不是真空地？

## 探路矩阵（4 researcher 并行扇出 → reviewer 收口）

| # | researcher 任务 | 服务命门 | 必答 | 交付 |
|---|---|---|---|---|
| R1 | **diffeomorphism 理论**：FM/rectified flow 的速度场积分 vs SVF（stationary velocity field）/LDDMM 的微分同胚保证。ODE flow 在什么条件下保证 diffeomorphism（Lipschitz 速度场？积分步数？）。配准里「保证拓扑」目前靠什么（雅可比正则 vs 架构约束 vs 积分构造）。 | A | FM 能否构造性保证 diffeomorphism 的明确结论 + 条件 + 关键文献 | 结论 + 引用 |
| R2 | **FlowReg 读透 + FM/diffusion 配准全景**：FlowReg(2603.01073) 具体怎么做（位移场空间？warmup-reflow？test-time refinement 定位？评测集？指标？少步几步？）。DiffuseReg/FSDiffReg/Diff-Def/LDM-Morph 各自机制与短板。少步采样 diffusion 配准最新进展。 | B | FlowReg 的精确机制 + 它没做什么（FMReg 的缝）+ FM/diffusion 配准对手清单 | 机制拆解 + 缝清单 |
| R3 | **baseline 官方设置**：VoxelMorph / TransMorph / DiffuseMorph 官方 repo 的架构/损失/lr/训练步数/评测协议。Learn2Reg 标准评测协议（TRE/Dice/折叠率 neg_jac/HD95 怎么算）。复现零偏离用。 | B | 三个 baseline 的官方超参 + Learn2Reg 评测指标定义 | 超参表 + 指标定义（查不到标 TODO） |
| R4 | **数据就绪度**：OASIS（脑 MRI 配准，killshot 已用 2D）、Learn2Reg 各任务（LUMIR 脑/NLST 肺 CT/腹部 CT-MRI 跨模态）、Dir-Lab（肺 CT）、IXI/LPBA40。各数据集下载路径/凭证要求/预处理协议/是否有 landmark 或分割标签（评测要）。登 datasets.json 用。 | A+B | 候选数据集就绪度表（下载难度/标签/凭证/跨模态有无） | 数据就绪表 |

**收口**：4 路回汇 → 主线综合 → 判定 (1) headline 改写方向（diffeomorphic guarantee vs empirical）(2) 硬碰 FlowReg 的差异化卖点能不能立住 (3) Gate1 数据/baseline 清单。必要时 reviewer 找漏洞、skeptic 红队「差异化是否真成立」。

## 探路后的决策分叉

- **若命门 A = FM 可构造性保证 diffeomorphism + 命门 B = 速度场/通用 benchmark 是真缝** → headline 强化「diffeomorphic few-step FM registration」，进 `/design-experiment` 出中训矩阵 + 重做诚实 killshot。
- **若命门 A = 只能经验无折叠** → headline 降级「empirically fold-free」，仍可投但卖点弱一档。
- **若命门 B = FlowReg 把缝基本占满、速度场无实质优势** → 报拍板：FMReg 降级/转向，run-002 收档诚实负结果。

## 落档去向
- 探路结论 → 本文件追加「探路结果」节 + FMReg `04_LOG`。
- 数据 → `.portfolio/datasets.json`。
- baseline 超参 → 本文件附录（中训复现用）。

---

# 探路结果（2026-06-17，4 researcher 并行回汇）

## 命门 A（理论）— FM 能否保证 diffeomorphism

**连续域：能。离散域：不自动。**
- ODE flow 在速度场 **Lipschitz 连续**时，流映射是 diffeomorphism（Picard-Lindelöf 定理）。FM 学的是 time-dependent 速度场，SVF（stationary velocity field，VoxelMorph-diff/DARTEL 用的）是其特例。
- **但数值积分（Euler/RK + 插值）会破坏保证**：IJCV 2024（PMC11870676）证明即便 SVF + scaling-and-squaring 在离散网格上仍可产生负 Jacobian（插值与有限差分不自洽 + checkerboard 盲区）。
- 现状「保拓扑」分两类：**构造性保证**（LDDMM 的 Sobolev 正则 / SVF+S&S 的 Lie 群指数映射，连续域成立）vs **经验软约束**（Jacobian 正则项 `λ·(det J−1)²`，只减不消、靠调 λ）。
- **结论**：FMReg 要写「diffeomorphic guarantee」必须三件套——① 速度场网络 Lipschitz 约束（谱归一化等）② 充分积分步数（RK4 ≥7）③ Sobolev/平滑正则。三者缺一只能写「empirically fold-free」。

**⚠️ 内在张力（命门 A × 命门 B 的核心矛盾）**：少步（卖点）= 积分步数少 = 离散误差大 = diffeomorphic 保证更易破裂。「又快又保拓扑」表面冲突。**解法（也是差异化钩子）**：在 **SVF 空间**做 FM——FM 少步**采样出一个 stationary velocity field**（少步指生成采样），再用 **scaling-and-squaring 积分**该 SVF 得形变（S&S 的 squaring 是确定性指数映射，构造性保证 diffeomorphism，与 FM 采样步数解耦）。少步采样 SVF + S&S = 少步 + 拓扑保证两不误。

## 命门 B（差异化）— vs FlowReg + 缝

**FlowReg（arXiv:2603.01073）精确机制**：
- (a) 在 **displacement field（DDF）空间**做 FM，**不是速度场、不是 SVF、无 diffeomorphic 构造**。
- (b) warmup-reflow 两阶段（teacher EMA 生成参考 DDF 让学生精修；标准 L² velocity loss 不稳定，改 NCC+梯度损失）。
- (c) **test-time refinement 路线**（精修已有配准），非端到端生成式。
- (d) 单步 Dice 82.94% **弱于** CorrMLP baseline 83.88%；2 步才超（84.27%）；10 步 84.68%，但**折叠率随步数升**（10 步 0.44%）。
- (e) **只 cardiac 2D cine MR**（ACDC/M&Ms），指标 Dice/%|J|≤0/LVEF MAE。
- (f) 没做：diffeomorphic 保证（future work 自承「可加」未实现）/ 脑·肺·腹 / 跨模态 / 3D volumetric / 标准脑肺 benchmark。

**真空地缝（researcher 判定）**：
1. **SVF 空间 FM + diffeomorphic 保证** — 真空地（FlowReg 在 DDF 无保证，无人做 SVF+FM）。
2. **通用脑/肺 benchmark 的 FM 少步配准** — 真空地（所有 FM/diffusion 配准只测 cardiac）。
3. **跨模态（MR-CT）生成式配准** — 真空地。
4. 扩散配准的少步蒸馏 — 配准侧真空地。
半占：端到端生成式超 baseline / 3D volumetric。

**对手都是 cardiac、都无 diffeomorphic 保证**：DiffuseReg（DDPM denoise 形变场，only ACDC，自承要减步）、FSDiffReg（diffusion 做 guide 非主干）、Diff-Def（atlas 生成非配准赛道）、LDM-Morph（LDM 当 feature 非生成式）。注：DiffuseMorph 推理实为**单步去噪 + 7 步插值**（非 T=2000 迭代），少步对照系要写准。

## 🎯 两命门合流 → headline 收敛

命门 A「必须加 diffeomorphic 构造（SVF+S&S）」**恰好等于**命门 B「区别于 FlowReg（DDF 无保证）」的核心卖点。建议 headline 从泛泛「FM 做配准」**强化**为：

> **Diffeomorphic Flow Matching：在 stationary velocity field 空间做 flow matching，少步采样 + scaling-and-squaring 积分，拿到 few-step × topology-guaranteed 的可变形配准，并首次在通用脑/肺/跨模态 benchmark 上验证。**

三个差异化支柱：① **SVF 空间**（vs FlowReg 的 DDF）→ 构造性 diffeomorphic 保证；② **通用 benchmark**（OASIS/Dir-Lab/AbdomenMRCT，vs 全员只 cardiac）；③ **少步 × 拓扑保证两不误**（用 S&S 解耦采样步数与积分保证）。

## Gate1 数据 + baseline 清单（就绪）

- **脑首选**：IXI 预处理版（junyuchen GDrive 1.44GB，免注册）做快速 pilot；OASIS Learn2Reg 版（416 例/35 标签，需 grand-challenge 账号）做正式 benchmark。
- **跨模态首选**：Learn2Reg **AbdomenMRCT**（MRI→CT，L4 lever 最直接）。
- **肺 TRE**：Dir-Lab 4DCT（300 landmark/对，需确认官网可达）。
- **baseline 官方超参已全查**（VoxelMorph lr 1e-4/λ 0.01-1/int_steps=7、TransMorph Swin embed 96/depths{2,2,4,2}/lr 1e-4、DiffuseMorph T=2000/lr 2e-4/推理单步+7插值）+ **Learn2Reg 指标定义**（TRE/Dice/DSC30/HD95/%|J|≤0/SDlogJ）→ 见附录。少数 config 行标 TODO（中训前手动核 repo）。

## 决策分叉 → 命中「进 design-experiment」

- 命门 A = **FM 可构造性保证 diffeomorphism**（条件：SVF+S&S+Lipschitz+Sobolev）✅
- 命门 B = **SVF 空间 FM + 通用 benchmark + 跨模态 = 真空地** ✅
→ 落在最优分叉：**headline 强化为 Diffeomorphic FM（SVF 空间）+ 进 `/design-experiment` 出中训矩阵 + 重做诚实 killshot**。

**🛑 拍板点（headline/STORY 改写）**：把 STORY headline 从「FM-as-deformation-field」改成「Diffeomorphic FM in SVF space」是 STORY 战略根基的强化（CLAUDE.md 拍板点 4：偏离/改 STORY）。探路支持这么改，但等用户拍板后再动 STORY/ACCEPTANCE。

**残余风险（待 skeptic 红队 + 中训验）**：
- SVF 空间做 FM 是否真新/真 work（无人发表既是缝也是未证）；
- 「少步采样 SVF + S&S」的少步到底能压到几步还保 Dice（K2 闸）；
- diffeomorphic「保证」在离散实现上仍可能漏（IJCV 2024 警告）→ 写作措辞需诚实（continuous-limit guarantee + 实测低折叠率）。

---

# 附录：baseline 官方超参（复现零偏离，中训对照用）

> researcher 查官方 repo/论文。标 TODO 的项中训前手动核对应 repo 行，绝不臆想填默认。

**VoxelMorph**（github voxelmorph + TMI2019 1809.05231）：Adam **lr=1e-4**；NCC window n=9（λ≈1）或 MSE（λ≈0.01）+ 空间梯度 L2；论文 150,000 iter（脚本默认 epochs=100000×steps100×batch4）；diffeomorphic 变体 SVF+S&S **int_steps=7**；概率版 image_sigma=0.01/prior_lambda=25。`TODO: nb_unet_features 脚本[16×5] vs 论文[16,32,32,32,32]/[32,32,32,8,8] 不一致，手动核 dev 分支 scripts/train.py`。

**TransMorph**（github junyuchen245 + MedIA2022 PMC9999483）：Swin embed_dim=**96**，depths={2,2,4,2}，heads={4,4,8,8}，window={5,6,7}脑，46.77M params；Adam amsgrad lr=**1e-4** polynomial decay^0.9，max_epoch=500 batch=1；脑 inter-patient MSE+diffusion weights=[1,1]；变体 -diff（SVF+S&S σ=0.01 λ=20）/-bspl（控制点 δ=2）。`TODO: 手动核 IXI/TransMorph/configs/TransMorph.py`。

**DiffuseMorph**（github DiffuseMorph + ECCV2022）：n_timestep T=**2000**（β 线性 1e-6→1e-2）；**推理=单步去噪(t=0)+nsample=7 插值，非 T 步迭代逆扩散**（少步对照系写准）；score UNet inner_channel=8 mult[1,2,4,4]，deform net enc[16,32,32,32,32]/dec[32,32,32,8,8,3]，3D 128×128×32；Adam betas(0.5,0.999) lr=**2e-4**，n_epoch=800，loss L2+sim+smooth λ=20。`TODO: 核 config/diffuseMorph_test_3D.json nsample`。

**Learn2Reg 评测指标**：TRE=配准后 landmark 欧氏距离均值(mm)；Dice=分割标签 overlap；DSC30=最低 30 百分位 Dice（惩罚离群失败）；HD95=95 百分位 Hausdorff(mm)；**neg_jac_pct=%|J|≤0**（折叠率，越低越好理想 0）；SDlogJ=std(log det J)（形变规则性）。Task2 肺仅 TRE+SDlogJ；脑/腹 Dice+HD95+折叠率。总排名=各指标归一化 per-case rank 的几何均值。
