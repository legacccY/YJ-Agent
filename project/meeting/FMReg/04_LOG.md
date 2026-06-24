# FMReg PROJECT LOG

> 进度留痕。倒序（最新在上）。

---

## 🔖 续跑指南（下一窗口开门必读，2026-06-24 重投后更新）

**当前态**：G2-A gating **已重投 = job 1489821**（2026-06-24，100ep + time 72h + `-u` + per-epoch state.json）。slot `9a1c6844`（hpc 1 卡）持有中。提交时 PD（排队等调度）。**监控盲已解**：脚本现每 logged epoch 写 `gate1_results/g2a_state.json`（arm/seed/epoch/loss/ts）+ print flush=True + submit `python3.10 -u`。

**下窗第一步——监控 job 1489821**（凭证见 `project/HPC_WORKFLOW.md`）：
1. paramiko 看 `squeue -u jiayu2403`（PD→R？）+ `cat gate1_results/g2a_state.json`（看到 epoch 推进=真跑）+ `tail logs/1489821.out`。
2. 跑完拉 `gate1_results/gate1_g2a_fourarm.csv` + verdict.txt + png → 本地 `gate1/results/` → 派 **analyst** 判（禁 Read 核数，Bash/Grep）。
3. `gpu_slot.py release 9a1c6844` 清账。

**预登记 gating 门**（不事后改）：`rho_C 显著>rho_DE(强baseline,CI不重叠 or p<0.05) AND rho_C>rho_B AND AUSE_C<AUSE_DE AND ECE_C<ECE_DE AND dice_C≥dice_A−0.02` → PASS 报用户拍阶段2全量(~500 GPU·h)；FAIL(强baseline反超)→诚实降 TMLR analysis 不洗（ACCEPTANCE §A0′）。

**历史**：旧 job 1461174（200ep）已 scancel（太慢+监控盲）；qos `4gpus` MaxWall=7天（旧 submit 写死 24h 是假瓶颈，已改 72h）。

**结局分支**（重投跑完后）：
1. **csv 出 verdict**：拉 `gate1_results/gate1_g2a_fourarm.csv`+verdict.txt+png 回 `gate1/results/` → 派 **analyst** 判（禁 Read 核数，Bash/Grep）。预登记门：`rho_C 显著>rho_DE(强baseline) AND >rho_B AND AUSE/ECE方向一致 AND dice_C≥dice_A−0.02`。PASS → 报用户拍阶段2全量(~500 GPU·h，见 `05_Gate1_matrix.md`)；FAIL(强baseline反超) → 诚实降 TMLR analysis 不洗（ACCEPTANCE §A0′ 预登记）。
2. **walltime 杀**：ckpt 已存的臂（arm_A/B/C.pt）`--phase eval` 复用；缺的补训。
3. **报错挂**：看 `logs/<jobid>.err` 按错误类型修。
4. **任一结局**：`gpu_slot.py release <id>` 清账。

**关键文件**：脚本 HPC `code/gate1_g2a_fourarm.py` / 本地 `gate1/gate1_g2a_fourarm.py`（含 `--epochs/--arm/--phase`，ckpt 只在单臂全 epoch 完后落盘 line 816-819）；submit `HPC:fmreg/submit_g2a.sh`；设计真源 `05_Gate1_matrix.md`；判据 `02_ACCEPTANCE.md` §A0′；K0 史见 Entry 5。HPC 数据 `/gpfs/work/bio/jiayu2403/fmreg/data/IXI/IXI_data/`（已传，免传）。

**别动**：BMVC 封印。

---

## Entry 8 — G2-A gating 重投 job 1489821（2026-06-24）

按 Entry7 续跑指南执行重投。

**监控盲修复**（解 Entry7 根因：stdout 全缓冲看不到 epoch）：`gate1_g2a_fourarm.py` 加
- `import json` + 全局 `_STATE_PATH` + `_log_state()` helper（每 logged epoch 写 `gate1_results/g2a_state.json`：arm/seed/epoch/n_epochs/loss/ts）
- 三个 train_arm_A/B/C 循环 print 加 `flush=True` + 调 `_log_state()`
- run() 设 `_STATE_PATH = out_dir/g2a_state.json`
- 共 +22 行，py_compile + CPU smoke 端到端通过，state.json 正确写入（last=arm C ep3）。

**submit_g2a.sh 改**：`--time 24h→72h`、`--epochs 200→100`、`python3.10 → python3.10 -u`。

**执行**：`gpu_slot request fmreg hpc 1` → GO `9a1c6844`（剩3卡）。paramiko 上传脚本（1589行）+ 重写 submit + `sbatch` → **job 1489821 PD**（gpu4090，排队等调度）。HPC 上传新代码=拍板点，用户「授权跑」放行。

**下一步**：监控 job（squeue PD→R + g2a_state.json 看 epoch）→ 跑完拉 csv → analyst 判预登记门 → release slot。

**🏁 收工态（2026-06-25）**：job 1489821 **RUNNING 中**（arm A_s0 ep60/100，loss≈−0.31 收敛正常）。slot `9a1c6844` 持有不释放（job 在跑）。下窗第一步=按上方续跑指南监控（paramiko squeue + cat g2a_results/g2a_state.json + tail logs/1489821.out）。完成拉 csv→analyst→release。Monitor 随本窗 session 结束停，下窗重挂或手动 poll。

---

## Entry 7 — G2-A job 200ep 太慢 → 杀 + 重投参数定（2026-06-18 收工）

**监控 job 1461174（200ep 探针）**：启于 11:41。盯到 6h13m，arm_A.pt **始终没落盘**（ckpt 只在单臂全 epoch 完后落，line 816-819）。GPU 全程 96-100%/17GB = 真训练非死循环（死循环会 CPU 满 GPU 闲）。stdout 67 字节只 start echo = Python **全缓冲**，中途完全看不到 epoch（脚本无 per-epoch state.json/flush=监控盲）。py-spy 没装栈拿不到。

**判定 walltime 风险**：训练量 = A+B+C+**DE(5×A 架构)** ≈ 8 单元。arm_A 单臂 6h+ 投影总量远超 24h walltime → 大概率 A/B/C 落盘、DE（最重那棒）被杀，而预登记门要 rho_DE（强 baseline），缺 DE 判不了门。报用户拍 → **用户拍 B（杀+减 epoch 重投）**。

**关键发现**：核 `sacctmgr` qos `4gpus` MaxWall=**7 天**，旧 submit 写死 `--time=24:00:00` 是假瓶颈。

**执行**：scancel 1461174（首次被 auto 分类器拦——只看到「进度」无杀 job 授权；用户明确「杀掉」后放行）→ 确认 squeue 空死透 → `gpu_slot.py release a54df04b` 清账。**未重投**（用户「直接收工」）。

**重投参数已定**（写进续跑指南）：epochs 200→100 + time 24h→72h + 建议加 flush/state.json 解监控盲。下窗 `request fmreg hpc 1` → 改 submit_g2a.sh → sbatch。

---

## Entry 6 — G2-A gating 脚本就绪（2026-06-18）

**coder 交付**：`gate1/gate1_g2a_fourarm.py` — Gate1 阶段1 G2-A 四臂 3D 真中训脚本。
- 四臂：A(det VoxelMorph-diff) / B(cVAE prob-VoxelMorph) / C(FM warp-driven 零teacher) / DE(N=5 deep ensemble)
- 数据：IXI 3D .pkl 160×192×224，atlas-to-patient，38 FreeSurfer subcortical 结构 Dice
- 指标：rho+bootstrap CI / AUSE / ECE / NCC_VX / neg_jac_pct / SDlogJ / Dice
- Gating verdict 预登记写死（§6 真源）：rho_C 显著>rho_DE(CI不重叠 or p<0.05) AND rho_C>rho_B AND AUSE/ECE 方向一致 AND dice_C>=dice_A-0.02 → PASS；否则 FAIL→降 TMLR
- 输出：`gate1/results/gate1_g2a_fourarm.csv` + `gate1_g2a_sparsification.png` + `gate1_g2a_verdict.txt`
- smoke 通过（CPU <3min，2 subjects/3 epochs/64³ crop/K=2/DE N=2）
- 残留 TODO：N_EPOCHS_DEFAULT(500占位需researcher核) / ECE精确WACV2022口径 / NCC_LM landmark centroid实现

**▶ G2-A gating 上 HPC 跑（2026-06-18，用户拍「上传+跑减epoch探针」）**：
- 前置全过：阶段0 researcher 核 baseline 超参（prob-VoxelMorph **prior_lambda=10**[官方Dalca2019,03附录25错] **image_sigma=0.02** / VoxelMorph enc[16,32,32,32] int_steps7 lr1e-4 λ0.01 / TransMorph embed96 / DiffuseMorph T2000 nsample7）+ 撞车（FlowReg repo在但cardiac确定性无后验K3差异化成立 / 新竞品Structured SIR 2603.17415 SIR非FM须related work区分）+ 校准指标领域标准=AUSE+ECE+NCC_VX/LM。
- skeptic 复裁 05 矩阵 **GREEN 0致命**（2×2因子修🔴-1不正交 + deep ensemble强baseline修🔴-2稻草人,DE进G2-A gating第一棒）。
- ACCEPTANCE 落 §A0′ Gate1 预登记PASS表(防HARKing)+L0四指标口径(writer)。
- IXI 下载解压(403/58/115 atlas-to-patient)登 datasets.json,真IXI smoke 验通(rho=0是良性小n守门line418非bug)。
- 加 `--epochs` 参数(<15行)。**上传 IXI 1.5GB+脚本→HPC fmreg/{code,data/IXI,gate1_results}→sbatch job=1461174 RUNNING@gpu4090n7**(减epoch200探针,A/B/C/DE四臂串行,walltime24h)。
- 估12-36GPU·h可能逼近walltime。监控=ckpt(arm_A/B/C.pt各臂跑完落)+最终csv `gate1_results/gate1_g2a_fourarm.csv`。
- **预登记gating门**：rho_C显著>rho_DE(强baseline) AND >rho_B AND AUSE/ECE方向一致 AND dice_C≥A-0.02 → PASS拍阶段2全量;FAIL(强baseline反超)→降TMLR不洗。
- 下一步:监控job→analyst判verdict→PASS则/design全量,FAIL则诚实降TMLR。slot a54df04b 跑完release。

---

## Entry 5 — K0 立项闸两轮 HPC 实证 → YELLOW 固化 → headline 收窄（2026-06-18）

用户拍「大集群」→ K0 killshot 全程上 XJTLU HPC（gpu4090，env yjcu124py310，BraTS2021 4211 PNG 已传 `/gpfs/work/bio/jiayu2403/fmreg/`）。

**K0v1（job 1459750）= RED**：二臂 VoxelMorph-diff vs FM-in-SVF（FM 蒸馏 vxm teacher SVF）。dice_vxm 0.9528 > dice_fm 0.9424，后验 ρ=−0.2273（反校准）。FM 退化成「换采样器」，正中 skeptic 预登记 R1' 范畴矛盾。**不降级**（用户拍「转向新 K0 设计」）。

**逃逸前提红队**（skeptic+researcher）：RED 根因 = 两退化源叠加（① 蒸馏陷阱 FM 回归 teacher / ② 后验坍缩 ψ_0 微小先验拉单峰）。有条件 GREEN——E1 去 teacher + warp-loss 从头训消①，但 `ρ>0` 不充分（异方差回归平凡满足），须加**确定性 cVAE 对照臂 B** + **多模态分叉判据**。

**能量地形探针（GREEN_PROBE）**：skeptic 命根——多解后验押在「warp-loss 能量地形多峰」假设。纯前向探针（受控歧义对 单 blob→双对称 blob）证：λ=1.0 实际 diffeomorphic 正则下 5/5 双谷（正则不填平多峰）→ 放行写三臂。

**K0v2 三臂（A 确定性 / B cVAE VoxelMorph-prob / C FM warp-driven 零 teacher）**：
- 首跑（job 1460073）多峰测试 3 bug（synth 5×假重复 / cluster_sep 饱和 / K=8 太小）→ analyst 逮到 → coder 修（24 distinct 几何 + K=48 + 弃 cluster_sep 用 BC + 修 verdict YELLOW 分支）。
- **修复重跑（job 1460205）= YELLOW 固化**（csv `killshot_K0v2_three_arm_HPC_fixed.csv`）：
  - **校准腿 FM 硬赢（二次复现）**：rho_C(BraTS)=+0.5161 p<1e-4 vs rho_B=−0.3890 p<1e-4；synth rho_C=0.9073 vs rho_B=−0.6954。cVAE 基线反校准。
  - **精度不退**：dice_A 0.9461 / dice_C_ens 0.9444 / dice_B 0.9468；neg_jac 三臂全 0%。
  - **多峰腿（公平测试 FM 没赢）**：dip_C 0.1630≈dip_B 0.1575，CI[−0.0038,0.0156] 含 0；BC_C 0.4466<0.555（两臂都没到双峰）；disp_spread_C 0.0037>B 0.0016（更宽但单峰）。

**结局拍板**：用户「接 YELLOW 收窄 headline」（+ 先「修复重跑」确认非测试假象，已确认）。**headline 收窄定稿**（writer 改 01_STORY + 02_ACCEPTANCE）：
- **立**：「FM-in-SVF 给出良好校准的形变后验」（少步采样 + diffeomorphic 保拓扑 + 精度不退，区别 cVAE/确定性 baseline 反校准）。
- **杀**：旧候选①「生成式多解后验」——多峰未立，不 claim 多解。
- **Gate1 命门**：MICCAI 需对「为何 FM 校准优于 cVAE」给机制解释（当前纯实证 rho 优势），证不出 → 降 TMLR analysis。撞车防护：后验配准拥挤领域（prob-VoxelMorph/DiffuseMorph/PULPo），差异化靠 FM 少步 + 校准质量。

**下一步（Gate1）**：`/design-experiment fmreg` 出中训矩阵（机制解释 FM 校准优势 + cVAE 对照 + 通用 benchmark 广度）。残留 TODO：prior_lambda=10 占位（verifier 核 Dalca 2019）；σ_p 数据驱动已实现。

---

## Entry 3 — 真实实力复核 + Gate1 探路启动（2026-06-17）

**真实实力评估**（`ideation/runs/2026-06-17_run-002_medimg-method/07_report/真实实力评估_FMReg_S4-05.md`）：逐行读 killshot 代码 + 联网核撞车 → **FMReg 黄牌，G6 GREEN 被高估**：
- killshot 三处水分：① `dice_affine` 实为恒等基线（代码 313 行注释自承 `identity (no warp)`），「胜仿射」失真；② `neg_jac=0%` 因 out_conv std=1e-4 + 200 步 + 微量级 target → φ≈恒等，小位移构造上不可能折叠，真实大形变折叠率没测；③ Dice 是脑前景轮廓重叠非解剖对应；④ 用的不是真 FM（手搭强度梯度代理）→ skeptic 的 🔴 FM≠形变场范畴塌**被绕过非被反驳**。
- **数据源订正**：killshot 实际用 **BraTS2021 flair**（`MedAD-FailMap/data/BraTS2021/train`），非 Entry 1/G6 卡所写「OASIS」——又一处留痕失真，待订正 STORY/Entry1。
- **K3 撞车实质已触发**：FlowReg（arXiv:2603.01073，2026-03，UCL/Imperial）已用 FM 做 2 步心脏配准超 SOTA。残余新颖「中等偏窄」=速度场 FM + diffeomorphic + 通用 benchmark。

**Gate1 探路计划**：见 `03_探路计划_Gate1.md`。两命门——A 理论（velocity→diffeomorphism 能否构造性保证）/ B 差异化（vs FlowReg + baseline + 数据就绪）。4 researcher 并行扇出（R1 diffeomorphism 理论 / R2 FlowReg 读透+对手全景 / R3 baseline 官方超参+Learn2Reg 指标 / R4 数据就绪度）→ 主线综合判 headline 改写 + 决策分叉。

**探路完成（同日回汇，4 researcher 并行）** — 结论全文见 `03_探路计划_Gate1.md` 末「探路结果」节 + 附录 baseline 超参。要点：
- **命门 A（理论）**：FM 连续域可保 diffeomorphism（Lipschitz 速度场 Picard-Lindelöf），但数值离散不自动（IJCV 2024 证 SVF+S&S 仍可负 Jacobian）。写「保证」需三件套=Lipschitz 网络约束+充分积分步数(RK4≥7)+Sobolev 正则；否则只能「empirically fold-free」。**内在张力**：少步↔保拓扑表面冲突，**解法=SVF 空间做 FM（少步采样 SVF）+ scaling-squaring 积分（确定性指数映射保 diffeomorphism，与采样步数解耦）**。
- **命门 B（差异化）**：FlowReg(2603.01073) 在 **DDF 空间**做 FM、**无 diffeomorphic 保证**、**只 cardiac 2D**、单步弱于 CorrMLP baseline 需多步才超且折叠率升。真空地缝=① SVF 空间 FM+diffeomorphic 保证 ② 通用脑/肺 benchmark ③ 跨模态 MR-CT。对手全员 cardiac+无保证。
- **🎯 两命门合流**：命门 A「必须加 SVF+S&S 构造」恰好 = 命门 B「区别 FlowReg」的卖点。**建议 headline 强化为「Diffeomorphic Flow Matching in SVF space + 通用 benchmark」**（三支柱：SVF vs DDF / 通用 vs 只 cardiac / 少步×保拓扑两不误）。
- **数据 Gate1 就绪**：脑 IXI 预处理版(GDrive 1.44GB 免注册 pilot)+OASIS(L2R 416/35标签正式)；跨模态 AbdomenMRCT(L4 首选)；肺 Dir-Lab(300 landmark)。baseline 官方超参全查（见附录，少数 config 行 TODO）。datasets.json 已补 ixi/abdomenmrct 指针。
- **决策分叉命中「进 design-experiment」**：命门 A✅(条件可保证)+命门 B✅(真空地)。
- **🛑 拍板点**：headline 从「FM-as-deformation-field」强化为「Diffeomorphic FM in SVF space」= STORY 战略根基改写（CLAUDE.md 拍板点 4），探路支持，**待用户拍板后再动 STORY/ACCEPTANCE**，然后 `/design-experiment fmreg` + 重做诚实 killshot。
- **残余风险（待 skeptic 红队）**：SVF 空间做 FM 是否真新真 work（无人发表=缝也=未证）；少步压到几步还保 Dice（K2）；diffeomorphic 离散仍可能漏，写作措辞诚实（continuous-limit guarantee + 实测低折叠率）。

---

## Entry 4 — skeptic 红队 headline + 诚实措辞订正 + K0 killshot 启动（2026-06-17）

**skeptic 红队**（headline 定稿前闸口）出 **1 致命（攻击点 1）**：原拟 headline「Diffeomorphic FM in SVF space」把 diffeomorphic/少步功劳归错给 FM——实为 SVF+S&S 老构造（DARTEL 2007/VoxelMorph-diff 2019）送的；SVF stationary vs FM time-dependent，FM-in-SVF 可能退化成「VoxelMorph-diff 换采样器」（JMIV 2026 坐实 SVF≠time-dependent velocity 积分）。非死刑，配可证伪 killshot。🟠：topology-guaranteed 是站不住强 claim（IJCV 2024 证 S&S 离散仍折叠），重蹈原 headline 覆辙。

**用户拍板**：先改诚实措辞，killshot 后再定 headline（最保守）。

**已改（诚实措辞订正）**：
- `01_STORY`：headline 暂不锁主轴，列两候选（①生成式 SVF 后验[skeptic 推荐，FM 不可替换] / ②diffeomorphic-centric 带债）；证据链诚实订正旧 killshot 作废（恒等假基线+near-identity 构造性 neg_jac=0%+非真 FM+用 BraTS 非 OASIS）；卖点改诚实（少步对照系=diffusion 非回归 / 禁 guaranteed / 通用 benchmark 定位广度证据）；K3 撞车订正 FlowReg 直撞。
- `02_ACCEPTANCE`：加 §A0 **K0 立项闸 killshot**（VoxelMorph-diff vs FM-in-SVF 增益对照，GREEN 走候选①/RED 降级省 80 GPU·h）；K1 禁 guaranteed 改 continuous-limit+实测低折叠率；K2 对照系钉死 diffusion；§C R1 标已复核+加 R1' 范畴矛盾；§D 加 Gate0=K0。

**下一步**：派 coder 写 K0 killshot 脚本（VoxelMorph-diff 单次出 SVF+S&S vs FM-in-SVF 多步采样 SVF+同 S&S，同数据[BraTS2021 本地 ready]同 backbone，比 Dice/neg_jac/后验不确定性）→ 主线跑（gpu_slot 申请）→ 结果定 headline。

**K0 脚本已就绪**：`project/meeting/FMReg/killshots/killshot_K0_fm_vs_vxmdiff.py`（smoke --cpu 跑通，全流程无报错）。输出 csv → `killshots/results/killshot_K0_fm_vs_vxmdiff.csv`。主线 `/loop /run-experiment` 触发正式跑（2000 steps）。

**▶ K0 上 HPC 跑（2026-06-18，用户拍板「大集群」）**：本地槽被 medad seed-fill 占满 → 改道 HPC（dequeue local 360c8b43 → gpu_slot GO `2873287f` hpc 1 卡）。上传 K0 脚本 + BraTS2021/train（4211 PNG/40M tar）→ `HPC:/gpfs/work/bio/jiayu2403/fmreg/{code,data,results,logs}`；脚本加 `--data-dir/--out-dir` argparse override（不 fork，<15 行）。SLURM `submit_k0.sh`（gpu4090/4gpus/1卡/16G/1h，env=yjcu124py310 py3.10）→ **sbatch job=1459750 RUNNING @gpu4090n2**。full run 2000 步 ×2 模型。下一步：轮询 `logs/1459750.out` → 跑完拉 `results/killshot_K0_fm_vs_vxmdiff.csv` → analyst 判 GREEN(走候选①生成式后验 headline)/RED(降级报拍板)/YELLOW → HPC release 清账。

**K0v2 能量地形前置探针（2026-06-18）**：skeptic 红队命根——多解后验全押在「warp-loss 能量地形多峰」假设，在平滑正则下可能单峰坍缩。写 5 分钟纯前向证伪脚本（零训练）：
- 脚本：`project/meeting/FMReg/killshots/killshot_K0v2_energy_probe.py`
- 输出 csv：`killshots/results/killshot_K0v2_energy_probe.csv`
- 输出图：`killshots/results/energy_probe_lambda{0.0,0.1,1.0}.png`
- 逻辑：合成受控歧义对（中心 blob → 双对称 blob，已知双解），沿 psi_left↔psi_right 插值密采 E(α)，扫 λ∈{0.0,0.1,1.0} 机械判峰（纯 numpy），λ=1.0 多数双谷=GREEN_PROBE 放行，多数单谷=RED_PROBE 证伪。
- 就绪可跑（smoke --cpu <30s 自测通过）→ 主线 `/loop /run-experiment killshot_K0v2_energy_probe.py --smoke` 先 smoke 验证。
- **▶ 跑完（2026-06-18 CPU full 5 对 41 点）= GREEN_PROBE**：λ=1.0 实际 diffeomorphic 正则下 **5/5 双谷**（barrier 0.023-0.204），λ=0/0.1 也全双谷。即 diffeomorphic 正则**不填平**多峰能量地形，warp-loss 在有歧义时保留多谷。命根假设站住 → 放行写整轮三臂 K0v2。诚实标注：探针用**受控歧义对**（人造单 blob→双对称 blob，构造上已知双解），证的是「**当**有 2 个合法 warp 时正则不毁多模态」=skeptic 第三条路核心（eval 用受控歧义对不赌 BraTS 自然歧义）。csv/png 落 `killshots/results/`。
- **臂 B 官方实现（researcher 回汇）**：VoxelMorph-prob = **ELBO/cVAE 式**（输出 velocity mean+log_sigma，KL 用 degree-matrix Laplacian 先验 `0.5·ndims·(λ·D·exp(logσ)−logσ + λ·prec(mean))`），**非** Kendall-Gal 异方差 NLL → 臂 B claim 写「cVAE-style velocity 后验」别写「heteroscedastic aleatoric」。PyTorch `use_probs` 官方未实现（抛 NotImplementedError）需从 TF 移植。init：mean flow `Normal(0,1e-5)`，log_sigma `Normal(0,1e-10)` bias −10。`prior_lambda` 官方无固定默认值=TODO。
- **K0v2 三臂 killshot 脚本（2026-06-18，coder 交付）**：
  - 脚本：`project/meeting/FMReg/killshots/killshot_K0v2_three_arm.py`
  - 三臂：A(det TinyUNetDet) / B(cVAE TinyUNetCVAE, VoxelMorph-prob 式) / C(FM warp-driven 零 teacher TinyUNetFM)
  - 关键函数：`train_arm_A/B/C` / `estimate_sigma_p`（σ_p 数据驱动）/ `eval_arm_A/B/C` / `eval_forking_on_synth` / `compute_forking_metrics`（dip/BC/cluster_sep 纯 numpy）/ `compute_verdict`（预登记判据）/ `bootstrap_dip_diff_ci`
  - 输出：`killshots/results/killshot_K0v2_three_arm.csv` + `killshots/results/k0v2_posterior_BvsC.png`
  - smoke `--smoke` <60s CPU 验三臂全跑通；full = 2000 步×3 臂，`--data-dir/--out-dir` HPC override
  - 残留 TODO：`prior_lambda=10`（占位，researcher 查 Dalca 2019 附录）；`sigma_p` 由 `estimate_sigma_p()` 数据驱动（在 run() 内臂 A 跑完后统计 SVF std），不臆想

**🏁 收工状态（2026-06-17 晚）**：K0 卡槽 **QUEUED 360c8b43**（local 满，ideation-run002-g5 占着，排在 medad-failmap 后），**未 release**，留着卡空自动取出跑。脚本超参 3 处 TODO（VoxelMorph 官方 lr/λ/NCC win，中训复现 baseline 时查实，killshot 内部对照可用占位）。**下次开窗第一件事**：查 `gpu_slot.py status`，360c8b43 轮到→主线跑 K0→analyst 判 GREEN(走候选①生成式后验 headline)/RED(降级报拍板)。headline 在 K0 出结果前不锁主轴、不写正文。

---

## Entry 2 — 立项证据归档 + 收工（2026-06-17）

立项材料完整归到本项目文件夹（自包含，不依赖 ideation run-002 目录）：`00_provenance/` 存
- `killshot_s2_03_jacobian.py`（G5 雅可比闸脚本）
- `killshot_s2_03_jacobian.csv`（GREEN 读数原值）
- `G6_proposal_card.md`（立项卡）
- `run-002_funnel.md`（漏斗台账 7→1）

组合台登记已全落：registry.json `fmreg` 条目 / datasets.json OASIS+Learn2Reg+BraTS2021复用 / locks/fmreg.claim。

下一步仍是 Entry 1 的 Gate1 三前置（R1 理论复核 / 下数据+baseline / `/design-experiment fmreg`），未启动。

---

## Entry 1 — 立项决策（2026-06-17）

**决策**：用户拍板立项。来源 = 选题流水线 run-002 医学影像方法创新型 G6 立项卡（唯一存活候选 S2-03，G5 雅可比闸 GREEN）。

**核心 RQ**：flow-matching（OT-Flow）直线流形变场做可变形医学配准，少步（≤4）逼近 diffusion 配准精度 + 保拓扑合法。

**venue**：MICCAI 2027 / CVPR 2027（top），MedIA / TMLR（fallback）。注：立项时纠偏——MICCAI 2026/CVPR 2026 截稿已过。

**边界**：组合台唯一碰「配准 + flow matching」的项目，与 iclr/medad-failmap/nca-jepa/bmvc 零重叠。

**立项证据**：`ideation/runs/2026-06-17_run-002_medimg-method/06_experiments/results/killshot_s2_03_jacobian.csv` → `neg_jac_pct=0.0000`, `dice_fm=0.9279 > dice_affine=0.8384`（OASIS 20 对 2D 单步 Euler，verifier 核 csv 自洽 0 drift）。

**G5 漏斗背景**：7 候选 → 杀手锏 6 证伪/blocked → 1 存活（S2-03）。死亡：S5-10(泄漏)/S6-18(撞车)/S2-17(输方差基线)/S2-12(masking无增益)/S1-08(无过适应峰)。S4-05 BLOCKED(VinDr 缺逐医生 bbox，用户已并行申标注作潜在第二项目)。

**已知风险（带债推进，见 02_ACCEPTANCE §C）**：
- R1 FM-proxy：killshot 用简化 FM target，velocity→diffeomorphism 理论待证。
- R2 单苗：无第二苗对冲。

**下一步（Gate1 前置）**：
1. 🔜 派 researcher + skeptic 复核 R1（FM velocity→diffeomorphism 几何配准理论，LDDMM/测地线先例），定 headline 是「保证」还是「经验」diffeomorphism。
2. 🔜 下载 OASIS + Learn2Reg，登 datasets.json，跑通 VoxelMorph/TransMorph/DiffuseMorph baseline 对照线。
3. 🔜 `/design-experiment fmreg` 出完整中训实验矩阵（对齐 L1-L4 + K1/K2 闸）。

**留痕清洁 TODO（继承自 run-002）**：run-002 pool.jsonl 的 S2-03 行有 ID 撞车污染（raw 双文件 hyphen/underscore 同 id），不影响本项目（survivor 身份 = FM 配准无歧义），下轮 /ideate 修。
