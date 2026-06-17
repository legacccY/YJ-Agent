# NCA-PhaseMap PROJECT LOG

> 进度留痕。倒序（最新在上）。

---

## Entry 1 — 立项（2026-06-17，用户拍板）

**立项决策**：源 = ideation run-003（NCA × 医学图像）G6 唯一存活旗舰 **C044**。用户拍板「立项 C044」。

**RQ / headline**：NCA 医学分割训练中 update 稀疏度（fire_rate/async 同一旋钮）存在尖锐可前验的功能塌缩临界相边界（update_rate≈0.375 / fire_rate≈0.625），越过即塌缩到平凡背景解，与梯度幅度无关——首次系统刻画。

**与边界**：纯新项目（非主论文拆分），与 ICLR/MedAD-FailMap/FMReg 零重叠。属 NCA 家族但**不在 nca-jepa/Med-NCA-AB 封存范围**（registry nca-jepa 条目已加 2026-06-17 scope 校正：封存仅限那两支实证死路 + NCA×世界模型交叉；NCA×医学影像单轴 run-003 不在内）。

**立项依据（G5 三重独立实证，主线核 csv 原值）**：
- 原 C044（36 cell）：19/36 功能塌缩（dice→0.0011，diverged 0/36=塌缩非发散），与 max_grad_norm 无关（r=0.238 p=0.16）。
- C044b（单轴 update_rate 细扫 12 cell）：临界 ur 0.35→0.40 断崖 dice 0.104→0.001（−94.9%）= SHARP。
- C044c（4 ur × 3 seed = 12 run）：STABLE_SHARP——ur=0.35 三 seed 全活、ur=0.40 三 seed 全塌。
- killshot 历程：C062 one-shot KILL（真塌）/ C001 anytime KILL（UNet 碾压）/ C044 PASS。researcher 核实不撞车（2508.06389 三重正交）+ 真空白。skeptic 红队 3🔴全可补救（语义错位→reframe / 共线→单旋钮非 confound / 撞车稻草人→不撞+reframe 更强）。
- csv：`ideation/runs/2026-06-17_run-003_nca-medimg/06_experiments/results/c044*.csv`；立项卡 `.../07_report/G6_proposal_card_C044.md`。

**诚实天花板**：当前中等会议料（单数据集 Hippocampus、小模型、存活区 dice 0.10-0.37）。standout 需立项后机制升级（ur 临界↔可前验量）+ BraTS/第二实现普适性。书面 kill criteria K1-K4 见 02_ACCEPTANCE。

**带债 / 立项后第一前置**：
- R1（机制）：ur 临界能否关联到可前验量（信息传播半径 × 更新稀疏度临界比）——决定 standout vs 中等会议。
- R2（普适性）：临界相变在 BraTS/第二独立实现是否复现（K1）。
- R3（因果）：梯度时序分析定"塌缩非梯度驱动"是相关还是因果（A3/K4）。

**下一步 Gate1**：`/design-experiment nca-phasemap` 出中训矩阵（第二数据集临界复现 + 梯度时序 + 机制量探索）。数据 Med-NCA Hippocampus 本地+HPC ready；BraTS 切片本地有（MedAD-FailMap/data/BraTS2021）。
