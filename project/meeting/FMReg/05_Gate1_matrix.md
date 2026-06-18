# FMReg Gate1 中训实验矩阵（正式 plan，coder 真源）

落档日 2026-06-18。planner 出 -> skeptic 红队 RED 2 致命修订 -> researcher 超参/撞车核定后定稿。
纪律：只设计不写码不跑；数字一律 Bash/Grep 核 csv；超参查官方源查不到标 TODO；复现零偏离；不自创验收阈值（全锚 02_ACCEPTANCE 的 L0-L4 + K1/K2/K3 + A0）。
服务：Claim FM-in-SVF 给出良好校准的形变后验（01_STORY 定稿 headline）/ 承重 lever = L0 校准后验；最硬命门 = 02_ACCEPTANCE A0 为何 FM 校准优于 cVAE 的机制解释（证不出 -> 降 TMLR analysis）。
不碰：iclr / medad-failmap / nca-phasemap / selinf / disagree。

## 0. 本版相对上版的修订（skeptic RED 2 致命 + researcher 核定）

skeptic 2 致命（已修，否则机制章填不上 A0 命门 -> 降 TMLR）：
1. RED-1 H1/H2 不正交：上版换 FM-loss->ELBO 在实现上同时换了采样结构（臂 C 多 psi0 rollout -> 臂 B 单 reparam），H1 损失 等价 H2 采样 是同一刀，归因脏 -> 改为 2x2 因子设计（损失 x 采样，四格全跑取干净边际效应），见第 2 节。
2. RED-2 cVAE 是稻草人：cVAE(ELBO) 反校准 rho_B=-0.39 是已知后验塌缩病（init bias -10 -> sigma 约 4.5e-5 起步即塌），FM 赢可能只赢一个躺平对手 -> 必加强概率 baseline = deep ensemble（N 个确定性臂 A 不同 seed 取预测方差算 rho，同架构同损失最干净控制），FM 须显著大于 deep ensemble 才算机制立。此条同样落到 G2-A gating 第一棒。

skeptic 非阻断（已纳入）：
- 橙-3 H3 去 time-cond 连带去掉 flow 时间积分结构 -> 加保留 t 但 rollout 单步中间臂切开 time-cond 与多步积分；解读口径改 time-conditioned flow vs time-free iterative refinement。
- 橙-4 sigma_p sweep 从辅助提为 H2 必跑前置（sigma_p 若是 rho 主因则 H2 结论作废，曲线进附录）。
- 防 HARKing 预登记：每假设数值 PASS 门 + 三结局解读口径 + 一条证伪整机制叙事的线（强 baseline 下 FM 不赢 -> 降 TMLR 不洗），见第 4 节。

researcher 核定（已更新对照系/超参/数据/校准指标）：
- prob-VoxelMorph 官方 prior_lambda=10（FMReg 占位 10 正确；03 附录写 25 是错的，本矩阵以 10 为准）+ image_sigma=0.02（FMReg 现 0.01 须改 0.02）。
- baseline 超参表见第 5 节。
- 数据 ready：IXI 预处理版（GDrive 1.44GB，atlas-to-patient，.pkl 160x192x224 带 30 标签，403/58/115，主线在下）；OASIS Learn2Reg Task03（1.3GB inter-subject，394/19/38）。
- 校准指标对齐审稿人主流命名：AUSE + ECE（Structured SIR / hetero-uncertainty / WACV2022 用）+ PULPo 的 NCC_VX / NCC_LM（OASIS 上 PULPo NCC_VX=0.533 vs DIF-VM 0.210 可直接对标）-> 替上版自拟的 SE/ECE-d/COV 命名。
- 撞车：FlowReg（mathpluscode/FlowReg，MIT，cardiac 确定性无后验）-> K3 差异化成立，可引其精度数字当确定性 FM baseline 不必自复现脑数据。新竞品 Structured SIR（arXiv:2603.17415，SIR 非 FM）非撞车但近 -> related work 正面区分。

仍需主线/用户过目：L0 当前正式只锚 Pearson rho；本矩阵升级为 rho + AUSE + ECE + NCC_VX/LM 四指标一致 -> 建议主线在 02_ACCEPTANCE L0 + A0 补口径锚点 + 预登记 PASS 门（第 4 节已起草）。属小幅口径收紧，planner 不擅自改 ACCEPTANCE。

## 1. 模型臂命名（全矩阵统一）

- A = 确定性 baseline（VoxelMorph-diff，SVF+S&S 单前向，无后验）。
- B = cVAE 概率后验（prob-VoxelMorph，ELBO + 单 amortized 后验）= 原校准腿对手，但已知塌缩 -> 不再当唯一对手。
- C = FM warp-driven 零 teacher（本文方法，SVF 空间 flow，多采样后验）。
- DE = deep ensemble（强概率 baseline，skeptic RED-2 新增）= N>=5 个臂 A 不同 seed，预测方差当后验，同架构同损失最干净控制。FM(C) 的 rho 须显著大于 DE 才算机制立。
- TM = TransMorph(-diff)（精度腿对照）；DM = DiffuseMorph（diffusion 多步，K2/K3 钉死对照）；FR = FlowReg（DDF-FM 确定性 refinement，K3 差异化锚；引论文数字不自复现）。

指标缩写：rho=后验方差与配准误差 Pearson（+bootstrap CI + p）；AUSE=area under sparsification error curve；ECE=expected calibration error（形变区间分箱）；NCC_VX/NCC_LM=PULPo 体素级/landmark 级负相关校准量（对标 OASIS leaderboard）；Dice/DSC30/HD95/neg_jac_pct/SDlogJ=Learn2Reg 标准。

## 2. 机制归因设计（A0 命门，最关键 — 2x2 因子 + deep ensemble）

### 2.1 为何改 2x2（修 RED-1）

上版三臂假设彼此正交，实则 H1 与 H2 是同一刀：把 warp-driven FM 换成 ELBO，同时把多 psi0 rollout 采样换成单 reparam 后验。无法分离校准来自损失还是采样结构。改为 2x2 因子设计：
- 因子 1 = 训练目标 loss 属于 {warp-driven FM, ELBO}
- 因子 2 = 后验采样结构 属于 {单后验 single reparam, 多采样 multi-sample rollout}

| 格 | loss | 采样 | 等价 | run_id |
|---|---|---|---|---|
| 1 | warp-driven FM | 多采样 | = 臂 C（本文方法） | G1-F11 |
| 2 | warp-driven FM | 单后验 | 新交叉格（拆采样贡献） | G1-F10 |
| 3 | ELBO | 多采样 | 新交叉格（拆损失贡献） | G1-F01 |
| 4 | ELBO | 单后验 | = 臂 B（cVAE） | G1-F00 |

干净边际效应：loss 主效应 = (格1+格2)/2 - (格3+格4)/2（控制采样）；采样主效应 = (格1+格3)/2 - (格2+格4)/2（控制损失）；交互项 = 格1 - 格2 - 格3 + 格4。
算力兜底（诚实条款）：四格 x 3 seed x 多集 若超 Gate1 预算（第 6 节），诚实砍掉一个假设只跑一行/一列，明写未能分离 X，绝不假装正交硬 claim。优先保 loss 主效应。

### 2.2 加强概率 baseline（修 RED-2）

cVAE(格4) 反校准是已知塌缩病 -> 单靠赢它不能 claim 机制。新增 deep ensemble（DE）作主对照：N>=5 臂 A 不同 seed，预测方差算 rho，同架构同损失，是不靠生成式后验也能给不确定性的最强非塌缩对照。
- 机制立硬条件：rho_C 显著大于 rho_DE（bootstrap CI 不重叠 / 配对检验 p<0.05）。
- 次选补充：MC-dropout、well-tuned cVAE（手动调 init bias 防塌，验 cVAE 反校准是否纯实现 artifact）。
- 此条同样进 G2-A gating 第一棒：gating 不只比塌掉的 cVAE，必含 DE。

### 2.3 H3 中间臂（修 橙-3）

| run_id | 臂 | 含 time-cond | 多步积分 rollout | 解读 |
|---|---|---|---|---|
| G1-M3a | C full | 有 | 多步 | 基线 |
| G1-M3b | 中间臂 | 有 | 单步（保 t 但 rollout=1） | 切 time-cond 本身 vs 多步积分 |
| G1-M3c | time-free | 无 | 单步（退化成 SVF 回归） | time-free iterative refinement |

解读口径：time-conditioned flow vs time-free iterative refinement，不写去掉时间嵌入这种含糊话。

### 2.4 sigma_p 前置（修 橙-4）

sigma_p 扫 3 档作 H2/2x2 前置必跑：若 rho 主要由 sigma_p 驱动则采样结构结论作废，曲线进附录。run_id = G1-Msig（臂 C，2 seed，3 档）。

### 机制组 run 表

| run_id | 变量（被试） | 控制（固定） | config/数据 | seed | 预期 | 判据 |
|---|---|---|---|---|---|---|
| G1-F11 | 2x2 格1（FM+多采样=臂C） | 同 backbone/数据/采样预算 | BraTS2021 3D | 3 | rho 大于 0 | A0/L0 |
| G1-F10 | 2x2 格2（FM+单后验） | 同上 | BraTS2021 3D | 3 | 拆采样边际 | A0 |
| G1-F01 | 2x2 格3（ELBO+多采样） | 同上 | BraTS2021 3D | 3 | 拆损失边际 | A0 |
| G1-F00 | 2x2 格4（ELBO+单后验=臂B） | 同上 | BraTS2021 3D | 3 | rho 小于 0 复现 | A0 |
| G1-DE | deep ensemble（N>=5 臂 A 方差） | 同架构同损失 | BraTS2021 3D | 5 | rho_DE，C 须显著大于它 | A0 硬条件 |
| G1-M3a/b/c | time-cond 三臂 | 同损失/数据 | BraTS2021 3D | 3 | time-cond 贡献 | A0 |
| G1-Msig | sigma_p 三档（前置） | 臂 C | BraTS2021 3D | 2 | rho 对 sigma_p 敏感曲线 | A0 稳健 |

## 3. 校准指标（领域标准命名，对齐审稿人）

L0 当前正式只有 Pearson rho（单指标 MICCAI 嫌弱）。升级为四指标，全 held-out 算 + 每指标配 bootstrap CI：
1. rho（保留）：后验方差与配准误差 Pearson，配 p+CI。校准好=显著大于 0。
2. AUSE（area under sparsification error curve，主流）：按不确定性从高到低逐步剔除画剔除比例 vs 剩余误差曲线，与按真实误差剔除的 oracle 曲线之差的面积。校准好=AUSE 小。
3. ECE（expected calibration error，形变区间分箱）：后验当高斯/经验分位分箱，名义置信度 vs 实际落入频率的期望误差。校准好=ECE 小。
4. NCC_VX/NCC_LM（PULPo 量，对标 OASIS leaderboard）：体素级/landmark 级不确定性-误差负相关量。对标点 OASIS PULPo NCC_VX=0.533 vs DIF-VM 0.210。

判定口径：rho + AUSE + ECE + NCC_VX/LM 四者方向一致才算 L0 校准证据稳。C 四指标全优于 DE/B、B 在 AUSE/ECE 反校准 = headline 坐实。

## 4. 预登记 PASS 判据表（防 HARKing，建议落 02_ACCEPTANCE A0）

跑前冻结不事后改门。每假设：数值 PASS 门 + 三结局解读 + 一条证伪整机制叙事的线。

| 假设 | 干净对照 | PASS 门（预登记） | 三结局解读 |
|---|---|---|---|
| 整机制（A0） | C vs DE | rho_C 显著大于 rho_DE（CI 不重叠/配对 p<0.05）且 rho_C 大于 0 跨绝对线 | a 立->MICCAI 机制章；b C约等于DE不显著->降 TMLR 不洗；c C 小于 DE->headline 塌报拍板 |
| H1 损失主因 | loss 主效应 (格1+格2)-(格3+格4) | 换 ELBO 后 rho 下降>=Delta_loss（跑前由 G2-A 标定，暂记>=0.3 待 pilot 定）且跨正负绝对线 | 单一主因/交互显著需配多采样/无变化非主因 |
| H2 采样主因 | 采样主效应 (格1+格3)-(格2+格4) | 换单后验后 rho 下降>=Delta_samp，且 sigma_p 前置已排除 sigma_p 主导 | 同上口径结合 sigma_p 曲线 |
| 交互项 | 格1-格2-格3+格4 | 交互显著（CI 排除 0）才能 claim 损失 x 采样共担 | 不显著则只 claim 主效应较大者 |
| H3 time-cond | M3a vs M3b vs M3c | M3a 显著大于 M3c，M3b 定位 time-cond 是否独立于多步积分 | 独立贡献/仅多步积分/无贡献 三档 |

证伪整机制叙事的线（硬退路）：强 baseline（DE）下 FM 不显著赢 -> A0 机制证不出 -> 降 TMLR analysis-track，诚实写实证 calibration study，不强 claim 机制创新不洗数据。报拍板。

## 5. 四组完整矩阵

### 组 1 机制归因（A0 命门）-> 见第 2 节 run 表

### 组 2 校准稳健性放大（L0 承重，多集 x 多形变幅度复现，含 DE）

| run_id | 变量 | 控制 | config/数据 | seed | 预期 | 判据 |
|---|---|---|---|---|---|---|
| G2-A | 臂 A/B/C/DE 全跑，rho+AUSE+ECE+NCC 四指标 | 3D 全分辨率 | IXI（pilot 首选） | 3（DE=5） | rho_C 大于 0 显著大于 rho_DE 且大于 rho_B；C 四指标全优 | L0+A0（第一棒 gating，含 DE） |
| G2-B | 同上 A/B/C/DE | 3D | OASIS Learn2Reg Task03 | 3（DE=5） | L0 第二脑集复现 | L0 |
| G2-C | 形变幅度分层 small/mid/large 下 rho | 臂 C | IXI+OASIS | 3 | 大形变档 rho 不塌 | L0 稳健 |
| G2-D | cVAE 反校准复现（B 多集 rho 小于 0） | 臂 B 官方超参 | IXI+OASIS+BraTS | 3 | rho_B 小于 0 在>=2 集复现 | L0 对照锚 |

### 组 3 广度 benchmark（L1/L2/L3/L4）

| run_id | 变量 | 控制 | config/数据 | seed | 预期 | 判据 |
|---|---|---|---|---|---|---|
| G3-topo | neg_jac_pct/SDlogJ（A/B/C/TM） | held-out 大形变 | OASIS+IXI | 3 | C neg_jac 与 A(diff) 相当不显著高于回归 baseline | L1/K1 |
| G3-acc | Dice/DSC30/HD95（A/B/C/TM/DM） | held-out | IXI+OASIS+BraTS | 3 | Dice_C>=TM 且不退于 A | L2 |
| G3-step | C 推理步数扫 1/2/4/8 vs DM 多步 | 同 ckpt | IXI+OASIS | 2 | 小于等于 4 步 Dice 掉点小于等于 2% vs DM | L3/K2 |
| G3-cross | 臂 A/B/C 跨模态 MR-CT + 后验校准是否保持 | 全分辨率 | AbdomenMRCT（ready） | 3 | C 不塌 + 跨模态校准 bonus | L4 |
| G3-lung | 二期可选 TRE on 肺 4DCT | 臂 C vs A | Dir-Lab（待下可砍） | 2 | TRE 不塌 | L2 广度 |

### 组 4 baseline 对照线（复现零偏离，超参 researcher 核定）

| run_id | 模型 | config（核定值） | 数据 | seed | 用途 | 判据 |
|---|---|---|---|---|---|---|
| G4-vxm | VoxelMorph-diff | enc[16,32,32,32]/dec[32,32,32,32,32,16,16], int_steps=7, lr1e-4, lambda_smooth0.01, NCC | IXI+OASIS | 3 | 臂 A+DE 基元+L2 锚 | L2 |
| G4-tm | TransMorph-diff | embed96/depths(2,2,4,2)/heads(4,4,8,8)/win(5,6,7,7)/img(160,192,224)/lr1e-4/500ep/prior_lambda10/image_sigma0.01 | IXI+OASIS | 3 | 精度腿对照 | L2 |
| G4-dm | DiffuseMorph | T2000/nsample7/loss_lambda20/lr2e-4（推理单步去噪+7插值） | IXI+OASIS | 3 | K2 少步对照系钉死 diffusion | L3/K2 |
| G4-prob | prob-VoxelMorph cVAE | prior_lambda=10/image_sigma=0.02（researcher 核定，03 附录 25 是错的） | IXI+OASIS+BraTS | 3 | 臂 B 校准腿对手 | L0 |
| G4-fr | FlowReg | mathpluscode/FlowReg（MIT, cardiac, 确定性无后验）-> 引论文精度数字当确定性 FM baseline 不自复现 | n/a | n/a | K3 差异化锚 | K3 |

## 6. 依赖顺序 + 硬前置 + 算力

硬前置（必先解决才能跑）：
- 数据：ready 免下=BraTS2021（机制组主战场）、AbdomenMRCT（L4，1.8GB 已验通）；必下=IXI（GDrive 1.44GB 免注册，G2-A gating 靠它，主线在下，最高优先）、OASIS Learn2Reg Task03（1.3GB，需 grand-challenge 账号，账号申请有前置时延）；可选/二期=Dir-Lab 4DCT（非承重可砍）。
- 拍板：IXI/OASIS 下到本地后上 HPC 跑 = CLAUDE.md 拍板点（HPC 上传新数据），主线先报。
- baseline 超参：第 5 节已核定。残留 TODO（coder 中训前手动核 repo 行不臆想）：VoxelMorph nb_unet_features dev 分支、DiffuseMorph config nsample、TransMorph IXI config 行。FlowReg 不自复现无超参前置。

依赖图：
- 阶段 0（前置可并行）：主线下 IXI 先 + 申 OASIS 账号；researcher 已交超参；coder 把 K0v2 2D 升级 3D volumetric（四格机制臂+DE 复用）+ 实现 AUSE/ECE/NCC 校准指标。
- 阶段 1（gating 串行第一棒）：G2-A（IXI 3D：A/B/C/DE 四臂校准含 deep ensemble）。门 rho_C 显著大于 rho_DE 且大于 rho_B。不只比塌掉的 cVAE。FAIL 停报（可能直接降 TMLR）。
- 阶段 2（G2-A PASS 后大批并行）：组1 机制 2x2 四格+DE+M3a/b/c+Msig(BraTS)；组2 G2-B/C/D(OASIS/分层)；组3 G3-topo/acc/cross(IXI/OASIS/AbdomenMRCT)；组4 baseline 对照线。串行依赖：G3-step 依赖 G3-acc 的 C ckpt；G4-dm 须先于 G3-step；Msig 须先于 2x2 解读。
- 阶段 3（收口）：analyst 汇 rho/AUSE/ECE/NCC + 2x2 边际/交互 + DE 对照 + 机制归因判定 -> verifier 核数 -> 判 A0 机制 PASS / 降 TMLR。

算力预估（供主线判拍板）：
- 3D 全分辨率（160x192x224 量级）单 config 真中训约 8-20 GPU·h（VoxelMorph/TransMorph 量级经验，待 coder 实测首 run 校准）。
- run 数（含本版新增 DE+2x2 第四格）：组1 约 28 run（2x2 4x3 + DE 1x5 + M3 3x3 + Msig 1x2）；组2 约 14；组3 约 12；组4 约 5（FlowReg 不跑）。合计约 55-60 中训 run（上版约 40-50）。
- 总量级约 55 run x 12 GPU·h 约 500-700 GPU·h（DE 复用臂 A ckpt 增量主要在 evaluation，实际增幅小于 run 数表观）。
- HPC 4 卡排法：每卡占 1 config（gpu_slot.py request fmreg hpc 1 x4），约 55 run/4 卡 约 14 波流水。
- 建议两段式拍板：先拍阶段 0 前置 + 阶段 1 G2-A gating（含 DE 约 5 子 run 约 60 GPU·h）；G2-A PASS（rho_C 显著大于 DE）再拍阶段 2 全量。省得 headline 在 3D/强 baseline 下不复现时白烧 500+ GPU·h。

## 7. 风险 + 交接

风险点：
- R-3D（最高）：K0v2 全 2D，3D 下 FM 校准优势是否复现完全未验 -> G2-A 设 gating 第一棒 FAIL 即停。
- R-机制不正交（已修但仍盯）：2x2 四格需 coder 确认 FM-loss x 采样结构 实现上真能独立切换（格2,3 是否技术可实现）-> coder 动手前回报可行性，不可实现则按 2.1 兜底诚实砍假设。
- R-DE 反超（健康风险）：若 deep ensemble 也校准好（rho_DE 大于 0 且约等于 rho_C），FM 不可替换塌 -> skeptic 要的真考验，FAIL 就降 TMLR 不洗。
- R-prior_lambda 已消解：researcher 核定 prob-VoxelMorph prior_lambda=10/image_sigma=0.02（FMReg 须把 0.01 改 0.02），03 附录 25 是错值以核定值为准。
- R-OASIS 账号：grand-challenge 账号申请前置时延，IXI 先行解耦不卡 G2-A。

交接：
- researcher：已交超参/撞车；投稿前再复查 2026-27 新 FM/diffusion 配准成片占缝 K3 及 Structured SIR 2603.17415 动态。
- coder（skeptic 已过设计闸）：1 K0v2 2D->3D volumetric（臂 A/B/C）；2 2x2 机制四格（确认 FM-loss x 采样可独立切换不可则回报）；3 deep ensemble 评测（N>=5 臂 A 方差算 rho）；4 M3a/b/c time-cond 三臂+sigma_p sweep；5 AUSE/ECE/NCC_VX/LM 四校准指标计算；6 baseline 对照线（第 5 节核定超参，prob-VM 用 prior_lambda10/image_sigma0.02）；7 IXI/OASIS/AbdomenMRCT 3D 加载+标签 Dice 评测。
- 主线（拍板+HPC 串行）：1 拍 Gate1 启动（建议先阶段1 G2-A gating PASS 再全量）；2 IXI/OASIS 上 HPC=拍板点先报；3 gpu_slot 申卡跑；4 考虑在 02_ACCEPTANCE L0/A0 补校准四指标口径+第 4 节预登记 PASS 门。
- analyst（跑后）：汇四校准指标+2x2 边际/交互项+DE 对照+time-cond 三臂判定 -> 对 L0/A0/L1-L4 判 PASS/降级，出 sparsification 曲线图。
- verifier：所有 rho/AUSE/ECE/Dice/neg_jac 入正文前三方对账。

上版仅在对话中（coder 无真源），本文件为正式 plan 真源。修订点全部源自 skeptic RED 2 致命 + 4 非阻断 + researcher 超参/撞车/校准指标核定。
