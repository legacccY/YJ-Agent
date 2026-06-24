# FetalSSBench — LOG（时间倒序）

## Entry 1 — 2026-06-24 立项决策

**来源**：`/ideate` run-011 候选 A（胎儿超声半监督分割 benchmark），G0-G6 全跑完。

**立项要素**：
- **核心 RQ**：胎儿/产科超声半监督分割缺统一跨任务评测——建首个 3 数据集×5 标注比例×5 方法统一 benchmark，揭示效率曲线/排名稳定性/结构难度不对称三规律 + 自适应阈值小增量。
- **venue**：ACCV 2026 主会 / 退 WACV App / MICCAI workshop / ISBI
- **边界**：新项目，与组合台在跑(ArtiOOD/selinf/quantimmu/gdn2vessel/fmreg/medad)核心 claim 无重叠；与并行窗 hyperfid/wavefid(脑MRI XAI)不同模态不同任务。重叠<30%。
- **数据**：PSFHS(✅ready)+HC18(todo下)+FUGC(需申请)，全公开。
- **策略**：纯 B 族 benchmark+小增量，复现零偏离。

**G2-G6 漏斗**：~100 候选→去重40→G2砍U3(撞车)/D15(PID不可靠)→G4红队→G5数据命门核(A=GRAY偏PASS)→G5 pilot GRAY-PASS。详见 run-011 报告。

**G5 pilot 结果**（GRAY-PASS，`project/meeting/_run011_pilot/G5_VERDICT.md`）：PSFHS 上 Sup vs MeanTeacher，曲线干净单调、MT增益随标注比例单调递减、增益集中难结构PS(5%下+2.1%)。债=监督baseline已强headroom薄→设计加低比例(1/2%)+HC18/FUGC(更难)+多baseline。

**拍板点记录**：立项方向/venue/RQ 经 /ideate G0 宪章 + AskUserQuestion(方向簇+数据+风险+claim形状) + 「都推」拍板。

## Entry 2 — 2026-06-24 Phase 1 设计 + 前置研究完成

**planner 出 Phase 1 矩阵**：5方法(Sup/MeanTeacher/CPS/UAMT/FixMatch-Seg) × 5比例(1/2/5/10/20%) × 2集(PSFHS ready/HC18 下载中) × 3seed = **150 run，~12-18 GPU·h**。依赖图+判据映射+风险见 planner 回汇。自适应阈值留 Phase 3（先跑实 5 baseline 地基）。

**前置研究完成**（researcher，复现零偏离，存 `reference/SSL4MIS_hparams.md`）：
- CPS: consistency=0.1, rampup=200, 双UNet同架构 / UAMT: ema=0.99, T=8, threshold=(0.75+0.25·sigmoid)·ln2 / FixMatch: conf_thresh=0.8(SSL4MIS)
- HC18: cv2.ellipse 填实心 mask(thickness=-1) + resize 缩放椭圆参数，单前景类
- **对照协议**：方法超参取官方，训练预算统一 100ep/Adam，rampup 换算到 epoch 制

**数据**：PSFHS ✅ready；HC18 后台下载中(training_set 133MB+test 44MB+CSV)；FUGC 待邮件申请。

## Entry 3 — 2026-06-24 Phase 1 harness 建成 + HC18 mask 坑修复

**coder 建 harness**（`src/datasets.py`+`harness.py`+`run_matrix.py`+`unet.py`，py_compile OK）：统一 5 方法(supervised/mean_teacher/cps/uamt/fixmatch)，PSFHS+HC18 双 loader，results.csv+state.json 续跑。

**HC18 数据下完**（999图+999轮廓PNG+CSV）。Step0 真烟测抓到**预判的最大坑**（铁律:新脚本必真跑别信自报）：
- Bug1: `_get_hc18_pairs` 配对 779≠999——220 个多视角 `_2HC.png` glob 没匹配。判定**有意保留 779 主视角**（多视角=同患者另切面，混 train/test 会泄漏），改注释明确。
- Bug2: HC18 mask 填充错——2px 椭圆轮廓被 findContours 碎段，fillPoly 只填环不填盘（前景占比仅 5.9%，填充比 2.7×）。**修：cv2.fitEllipse 拟合轮廓点→画实心椭圆**（HC18 GT 本是椭圆）。修后前景占比中位 18.6%（合理胎头面积）。主线直接改+验，未派 coder（焦点 bug 已诊断清）。

**卡槽争用**：local 卡被并行窗 hyperfid(BrainGB Gate1) 占，烟测 QUEUED→按铁律不挤正在跑的→dequeue 撤回。HPC 1 卡空但上传数据/代码=拍板点。

**拍板点（待用户）**：Phase 1 150-run 怎么跑？①等 hyperfid 释放 local 卡本地跑(~12-18 GPU·h占机~1天) ②上传 PSFHS+HC18+harness 到 HPC 4 卡跑(~1-2h，但上传是对外传输拍板点)。

**就绪待跑**：harness 5 方法 + 双数据集 loader（mask 验过）。

## Entry 4 — 2026-06-24 HPC 上传 + smoke 提交（用户授权 HPC 1卡）

CPU 烟测超时(143)不可行、local GPU 被 hyperfid 占满 8GB → 走 HPC。
- **HPC 连通 OK**（VPN 开），work dir `/gpfs/work/bio/jiayu2403/fetalss/`
- **数据上传验证**：PSFHS_repack.zip(134MB,DEFLATED)+HC18 training_set.zip(133MB)+csv → 远程解压 PSFHS 2716 .mha + HC18 779 _HC.png ✅（download脚本删了PSFHS.zip,重打包上传）
- **env 确认**：`yjcu124py310`(torch2.6+cu124/SimpleITK2.5.5/cv2 4.13/scipy/numpy/PIL 全齐)，另 my_torch_env 缺 SimpleITK 不用
- **代码 patch**：harness.py `_DEFAULT_DATA_ROOT` 读环境变量 `FETALSS_DATA_ROOT`（HPC 设它指向 /gpfs/.../fetalss/data）
- **smoke 提交**：job **1490527**（5方法×hc18 --quick 验不崩），PD 排队(队列前有 fmreg/gdn2vessel/wavefid)。sbatch=`sbatch_smoke.sh`（gpu4090/shuihuawang/4gpus/gpu:1/30min）

**下一步**：smoke 跑完看 `logs/smoke_1490527.out`（看产出不信jobid）→ 5方法全 PASS 则写 150-run sbatch（PSFHS+HC18 × 5方法 × 5比例{1,2,5,10,20%} × 3seed）提交 → analyst 判规律。**HPC job 1490527 = 当前未决，需 poll SLURM 队列**。

**poll loop armed（2026-06-24）**：smoke job 1490527 PD（gpu4090 被其他用户占，全队列 PD）。poll 脚本 `scratchpad/poll_smoke.py`（查 squeue→完成且 SMOKE_ALL_DONE 无 SMOKE_FAIL 则传+提 `sbatch_full.sh` 150-run；失败报哪方法崩）。全量 sbatch `scratchpad/sbatch_full.sh` 已备。25min 周期 poll，smoke 过自动提 150-run，跑完 analyst 判规律。

**⚠️ SLURM ETA（2026-06-24 ~18:21 查）**：smoke 1490527 优先级预计开始 **2026-06-26 13:47（~2天后）**，gpu4090 全集群 46 running job 占满。30min 短 job，**backfill 可能插队提前**。poll 放缓 30min。job durable。

## Entry 5 — 2026-06-24 ~20:53 smoke backfill 跑了 + env bug 修复 + 重提

**backfill 抓到 1490527**（约 3h，ETA 估 2 天但 30min 短 job 被 backfill 插队提前跑）。但 **5 方法全 `python: command not found`**——非代码 bug，是 **sbatch env 激活失败**（假设的 `conda.sh` 路径不存在，conda activate 没生效）。
**修复**：核到绝对 python 路径 `/gpfs/work/bio/jiayu2403/.conda/envs/yjcu124py310/bin/python` 可用(3.10.18)；两 sbatch(smoke+full)改用 `$PYBIN` 绝对路径，不靠 activate。
**重提 smoke job 1491156**（env 修复版），PD 排队。poll_smoke.py 的 SMOKE_JID 已更到 1491156。

**进度**：代码/数据/env 全验通，纯卡 SLURM 排队。下次 backfill 跑 1491156→若 5 方法真出 Dice 不崩→自动提 150-run。

## Entry 6 — 2026-06-24 ~21:26 🎉 smoke 全过 + 150-run 自动提交

**smoke 1491156 全 5 方法在 RTX 4090 跑通**（env 修复见效，无 SMOKE_FAIL）：
- **HC18 mask 修复实证成功**：supervised hc18 10% 5ep → dice_head **0.8895**（高 Dice 证 fitEllipse 填的实心椭圆 mask 正确，非坏环）
- mean_teacher 0.831 / cps 爬到 0.87 / uamt / fixmatch 全真出 Dice，无崩
- 仅 autocast deprecation warning（无害）
**poll 脚本自动提交 150-run full job 1491207**（PASS_SUBMITTED 流程生效），PD 排队。sbatch_full（5方法×2集×5比例×3seed，state.json 续跑，24h，绝对python路径）。

**监控转 full job 1491207**：poll_full.py 查 squeue + results.csv 行数趋近150（去重）+ logs/full tail。

## Entry 7 — 2026-06-24 ~23:19 改 chunk 策略（monolith 难 backfill）

**洞察**：24h monolith(1491207) ETA 仍 6-26（~2天），**24h 长 job backfill 难插队**（需 24h 卡窗），而 30min smoke 能 backfill 是因短。→ 取消 monolith，**切 10 chunk(method×dataset，各15run~2.5h，--time=4h)**，4h 比 24h 易 backfill。
**patch harness**：加 `RESULTS_TAG` 环境变量→各 chunk 写自己 `results_<m>_<ds>.csv`+`state_<m>_<ds>.json`，防并发写竞争。
**QOS 限额**：MaxSubmitJobsPerUser=8 / MaxJobsPerUser=4 跑 / 4 GPU。已有 fmreg+gdn2vessel 占额→首批提了 5 chunk(1491509-13:supervised×2/mean_teacher×2/cps_psfhs)，剩 5 超 8-提交限。
**poll_chunks.py 接管**：每轮算各 results_<m>_<ds>.csv 满15行=done→进度/150 + 跑完释放额度自动补提剩余 chunk + RUN_FAIL 检查。全 10 chunk done(150)→analyst。**当前=10 chunk 队列，poll_chunks 管理，进度 0/150**。
