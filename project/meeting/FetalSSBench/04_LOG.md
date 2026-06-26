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

## Entry 8 — 2026-06-25 ~01:58 收工

**HPC 状态（在跑别停，durable）**：5 chunk 已提排队（1491509-13=supervised×2/mean_teacher×2/cps_psfhs，PD 等 backfill），剩 5 combo(cps_hc18/uamt×2/fixmatch×2)待额度释放自动补提。集群+我自己其他项目(fmreg/gdn2vessel/wavefid)挤满 QOS 4-跑额度，4h chunk 等 backfill 插队。
**脚本已固化**（防 session 关丢）：`project/meeting/FetalSSBench/hpc/`（poll_chunks.py / sbatch_chunk.sh / sbatch_full.sh / hpc_chunk_submit.py）。

**下次开窗恢复**：说「推进 fetalss」→ 读本 LOG → 跑 `hpc/poll_chunks.py`（注意脚本里 SC 路径指向旧 scratch，恢复时改成 `project/meeting/FetalSSBench/hpc/` 或重设）查 10 chunk 进度→满 150 拉回合并→analyst 判规律。HPC 凭证见 project/HPC_WORKFLOW.md，env=yjcu124py310，绝对 python 路径。

**本 session 总结**：选题 G0-G6(~100候选→3立项卡)→G5 pilot GRAY-PASS→FetalSSBench 立项→Phase1(150-run矩阵+SSL4MIS官方超参)→harness 建成→HC18 mask坑修(fitEllipse)→HPC上线→smoke 5方法验通(dice 0.89)→150-run 切10 chunk 在 HPC 排队。主力 A 落地到 GPU 上跑，纯卡集群排队。

## Entry 9 — 2026-06-25 ~18:10 恢复：poll 列号 bug 修复 + 真实进度 79/150

**开窗跑 poll_chunks.py 报 0/150 → 假象**。诊断（feedback_debug_silent_failure：别信自报，看产出）：
- chunk 日志显示上次 chunk **真跑完有产出**（cps_psfhs.out: dice_mean=0.9253 满100ep）。`results_*.csv` 里 5 combo 各 15 行已落（sup_psfhs/sup_hc18/mt_psfhs/mt_hc18/cps_psfhs = **75 run done**）。
- **根因 = poll 计数列号 bug**：done 检测写 `awk '$13==100'`，但 epochs 不在第 13 列。PSFHS csv 15 列(双前景 dice_PS/FH，epochs=14)，HC18 csv 13 列(单前景 dice_head，epochs=12)——**两数据集列布局不同**。修为 robust `$(NF-1)==100`（epochs 恒倒数第二列）通吃两种。
- bug 致 poll 误判 0/150 → 误触发全量补提 7 chunk。但**重复 job 无害**：harness `run_already_done` 从 state.json `runs_done` 跳过 → dup 任务 `[skip]...已完成` 秒退不写新行（核 csv 仍各 15 行未污染）。scancel 被 classifier 拦（非本 session 创建的 job），无需 cancel。

**真实进度 = 79/150**：5 combo done(75) + cps_hc18(3/15)+uamt_psfhs(1/15) 在出行。剩 5 combo(cps_hc18/uamt×2/fixmatch×2)全在飞，todo=0、njobs=8 满 QOS 额。env 修复版绝对 python 路径，fmreg 占 1 卡、fss 用余下 ~3 卡并行。预计 ~4-5h 跑满 150。

**下次开窗恢复**：跑 `hpc/poll_chunks.py`（列号已修）→ ALLDONE 150/150 则跑 `hpc/merge_results.py`（新建，拉回 10 chunk csv 合并→ `results/master_wide.csv`[每run] + `results/master_long.csv`[per-structure，供 PS/FH 不对称]，已处理 PSFHS 15列/HC18 13列 schema 差异+去重）→ analyst 判规律(效率曲线/Kendall-τ/PS-FH 不对称)对齐 Phase 2 ACCEPTANCE。

## Entry 10 — 2026-06-25 ~20:05 ✅ Phase 1 跑满 150/150 + Phase 2 PASS（结构难度不对称显著）

**Phase 1 完成**：10 chunk 全 done，`merge_results.py` 拉回合并 → `results/master_wide.csv`(150 run) + `results/master_long.csv`(225 行，PSFHS 双结构+HC18 单结构)。每 combo 15 行齐，无 NaN/崩。Phase 1 ACCEPTANCE = **PASS**（完整矩阵 5方法×2集×5比例×3seed，held-out 不泄漏）。

**Phase 2 实证规律（analyst 判 + 主线 Bash 自核 ≥4 关键值全吻合，R1 纪律）**：
- **规律3 结构难度不对称 PS vs FH = ✅ PASS（承重）**：supervised PS=0.7462(难) vs FH=0.9033(易)；SSL 正增益率 PS 56.7% vs FH 15.0%；Wilcoxon p=0.0468 / Mann-Whitney p=0.0028。SSL 增益系统性集中难结构(耻骨联合 PS)，易结构(胎头 FH)几乎无效。HC18 head 增益≈0 旁证（高基线天花板）。可解释=高基线无增益空间、难结构低基线 unlabeled 有信息增量。**诚实点**：PS 均增益 -0.0117（绝对微负），PASS 承重在「PS 增益显著>FH」相对不对称，非 SSL 绝对超 supervised（守 R4 不夸大）。
- **规律1 收益递减 = ⚠️GRAY**：信号弱。准确表述=「高比例 SSL 趋同收敛到 supervised(增益压缩到零)」而非「低比例 SSL 显著更好」。PSFHS gain 1%/2%>10%/20%（MW p=0.03-0.05）、HC18 Spearman ρ=-0.27(p=0.036)。HC18 天花板强(1% sup 已 0.835)收益递减不可见。
- **规律2 排名稳定 = 重定义为「无普适最优方法」（对齐 STORY「排名变化」预期）**：Kendall-τ 跨比例 PSFHS=0.12/HC18=0.08、跨集 τ=0.2(p>0.8) 全近随机。1% 下 PSFHS 最优=supervised、HC18 最优=CPS（两集不同），随 ratio 剧烈洗牌。这是 benchmark 核心正向发现（揭示无单一最优→统一评测必要性），非「稳定性 FAIL」。

**Phase 2 整体 = PASS**（lever② ≥1 规律显著可解释满足，规律3 坐实）。统一图景：**SSL 增益集中「难结构+低标注」交叉区，高基线/易结构/高标注无优势**——有价值 benchmark 结论。

**3 图出**（`figures/`）：fig_efficiency_curves.pdf / fig_ssl_gain.pdf / fig_struct_asymmetry.pdf。

**风险/盲区**：n=3 seed 部分格 CI 宽功效有限、p 值解释保守；PSFHS @1% UAMT 高方差(seed Dice 0.26/0.49/0.81)=6 图训练固有随机非 bug。

**下一步（拍板点）**：Phase 2 PASS → 可推 **Phase 3 自适应置信阈值小增量**（规律3 指明 SSL 增益集中难结构低标注，自适应阈值正为该区设计，叙事闭环）。或先补 FUGC 扩 benchmark 深度 / 直接进写作。Phase 3 涉及实现新方法（adaptive threshold）= 工程量，建议下窗 `/design-experiment` 派 planner 设计后再动手。

---

## Entry 11 — 2026-06-25 ~21:15 建 PLAN/ 阶段计划体系 + 红队 2 致命重塑承重 claim + 80% 信心 lever 框架

**触发**：用户要建专门阶段计划文件夹（仿 BMVC 元素）+ 联网佐证 + 拉 ACCV 中稿信心到 80% + 故事完善。大编队全力扇出（writerA/writerB/researchAdaptive/researchFUGC/skeptic/analyst 6 agent）。

**🚨 硬约束核实（联网）**：ACCV 2026 paper 截止 **2026-07-05**（CORE-B，2024 接收率 32.2%，双年会错过下次 2028），不是项目此前估的 Aug-Sep。用户拍板：**时间/算力无限，按最强论文设计，80%=内部信心目标非 venue 真实率；成稿再挑 venue（ACCV 赶得上就投否则 WACV 2027）**。

**建 PLAN/ 文件夹（8 文件 + 1 reference）**：`MASTER_PLAN`/`PHASE_1~4`/`LEVER_MATRIX`(12 lever 80% 信心总账)/`STORY_REFINEMENT`/`DATA_FUGC_ACQUISITION` + `reference/ADAPTIVE_THRESHOLD_hparams.md`。00_README 补 PLAN/ 入口指针。PLAN 答「怎么做」，验收引用 02_ACCEPTANCE 不复制。

**🔴 红队 2 致命 + analyst 实算 → 承重 claim 大幅收窄（数据直读 master_long.csv，全可复现）**：
- **致命1**：原「难结构×低标注交叉区」方向反转——PS @1% 增益 **−0.0728**（全场最负）、非单调。→ 去掉「×低标注」维。
- **致命2 + 实算**：PS 自身正增益 median +0.00205 但 **Wilcoxon p=0.38~0.54 不显著**；FH 受损 **p=7.07e-08 铁实**（剔 6 个 1% 崩塌 outlier 不变）；PS vs FH 差异 **p=0.0028→剔后 0.0012**（更强）。**→ 承重从「难结构受益大」收窄为「SSL 增益强结构依赖：高基线易结构(FH/head)可靠不受益/受损，跨结构不对称稳健显著」，不再 claim「PS 受益」**（更诚实、更抗攻击）。**此条修正 Entry 10 的「PS 增益显著>FH」「难结构+低标注交叉区」旧框架。**
- **双因混淆（必写 limitation）**：PS 前景占比 median **2.5%** vs FH **22%**（小 8.7 倍）→ PS「难」= 难结构 + 极端小目标类不平衡双因叠加，拆不开。但精化机制+强化 Phase3 闭环（极端少数类→固定阈 0.8 滤光 PS 伪标签→FreeMatch SAT 给少数类低阈值正打痛点）。

**Phase 3 设计定稿（红队回炉）**：自适应主力 = FreeMatch **SAT-only（关 SAF 保单变量）**，SAF 作 G5 消融臂；固定臂跑 **τ∈{0.7,0.8,0.9} 取最优**作公平 baseline（防「优势只是 0.8 选差」）；预注册预期方向+效应量进 ledger 防 HARKing，正负均报，GRAY 出口。超参公式落 `reference/ADAPTIVE_THRESHOLD_hparams.md`（FreeMatch EMA/SAF + FlexMatch CPL + SSL4MIS conf_thresh=0.8 官方核实，3 个 TODO 标好）。

**FUGC 重大利好**：Zenodo **16893174 Open 可直接 wget**（161.8MB，CC-BY-4.0，免邮件申请），免去 1-3 天申请等待。修正：FUGC 是 **2 类**（anterior+posterior cervical lip），给跨结构难度谱多 2 点。测试集 GT 不公开→回退自建 held-out（90 val 切）。详见 `PLAN/DATA_FUGC_ACQUISITION.md`。

**撞车核查**：FUGC/HDC/DSTCT/ERSR 四篇胎儿超声 SSL **全未用概率自适应阈值**（ERSR 是几何 dual-scoring 不同范式）→ 撞车低，Related 显式区分即可。

**4 个待拍板**（停下报用户）：①规律3 收窄 claim 回写 01_STORY=改 STORY 方向 ②FUGC 下载后上传 HPC=对外传输 ③ACCEPTANCE 新增 Phase3 细化阈值冻结 ④Phase3 自适应主力 FreeMatch SAT（已基本定，待最终确认）。

**下一步**：用户拍板后 → Wave 3（coder 加 SAT-only 分支 + FUGC loader + seed 3→5 → gpu_slot 申请 HPC 跑 Phase3 A-B → analyst 解读 → verifier 核数）。建议 `/conductor fetalss-bench` 建 DAG 驱动。

---

## Entry 12 — 2026-06-25 ~21:35 Wave 3 工程件全落地+本地烟测 PASS（FUGC 到手 test GT 公开）

**用户拍板**：Q1 保持原 claim 不收窄（⚠️ 我顶了一句：原 claim 与 csv 打架 PS 自身 p=0.38~0.54 不显著/1% 反向，触 R4——处理=不回写 01_STORY，STORY_REFINEMENT 留诚实记录，争议留 Phase4 写作期 verifier 关解决，实现不依赖措辞照推）；Q2 全推；Q3 FreeMatch SAT-only。

**coder 工程（py_compile + 本地真烟测全 PASS，非 pytest-绿）**：
- `harness.py` 加 `train_freematch_sat`（SAT-only，关 SAF，SAF 留 G5）：time_p 全局 EMA + p_model 类别局部阈值，**batch-level 更新对齐 USB 官方**（初版 epoch-level，按复现零偏离改 batch；二阶细节 p_model 用 one-hot 计数非 softmax 均值=分割适配设计选择，写 tex 声明）。
- `--conf_thresh` 参数化（默认 0.8 向后兼容，τ≠0.8 run_id 带 `_t07/_t09`，Phase1/2 结果免重跑）→ Phase3 固定臂跑 τ∈{0.7,0.8,0.9} 取最优作公平 baseline。
- seed 0-4 支持确认。
- `datasets.py` 加 FUGC loader（PNG 336×544，官方固定 split 不参与 ratio 扫，num_classes=3 双前景结构 anterior/posterior，mask nearest resize）。
- **烟测**：fixmatch τ=0.7 → dice 0.88 ✅；freematch_sat → dice 0.877 time_p EMA 生效 ✅；FUGC supervised 25ep → dice 0.586(ant 0.666/post 0.505) 收敛 ✅（早先 5ep dice=0 经核=小结构欠训非 bug，resize nearest 已验整数标签保留）。

**FUGC 到手（重大）**：Zenodo 16893174 Open curl 直下 155MB 解压验通 → `_run011_pilot/data/FUGC/FUGC (Dataset)/dataset/{train/{labeled_data 50,unlabeled_data 450},val 90,test 300}`。**⭐test/labels 300 GT 全公开**（修正旧情报「测试集 GT 不公开」，无需 Codabench/自建 held-out）。2 前景类占比 ~16%/13% 落 PS 2.5%~FH 22% 之间=难度谱补两点。datasets.json 真源已更新。

**🛑 停在 HPC 上传拍板点**（对外传输）：代码+FUGC 数据本地就绪，下一步 = 传 HPC + gpu_slot 申请跑 Phase3 A-B + 扩 FUGC/5seed benchmark，等用户放行上传。

---

## Entry 13 — 2026-06-26 ~00:00 用户放行"跑" → 上传 HPC + Phase3 PSFHS A/B 进 SLURM 队列

**上传验通**：harness.py+datasets.py(CRLF去)+sbatch_phase3.sh → `/gpfs/work/bio/jiayu2403/fetalss/code|/`；FUGC zip 161.8MB 传+HPC 解压验通(train 50+450/val 90/test 300+300labels)；HPC 端 py_compile PASS。datasets.json 真源已更新。

**卡账对账（用户批准核 squeue 清 stale）**：squeue -u jiayu2403 实况=fmreg_g2a(4090 RUNNING 1d4h)+train_CHASE(3090 RUNNING gdn2vessel)+hf_hg03/hf_bgb(PENDING)。gpu_slot ledger 的 **ideation-run010 在 squeue 彻底没了=确认 stale → release 2c8d434c 清账** → fetalss 自动晋升 starting。hyperfid/gdn2vessel 是别窗 job 不擅动。

**真瓶颈=全校集群挤爆非我窗口**：gpu4090/gpu3090 分区一长串别人 PENDING(QOSMax/Priority/Resources)。SLURM 提交=进队列 backfill 永不抢占=HPC 正常用法（用户拍板"提交进 SLURM 队列"）。

**Phase3 提交**：12 chunk(freematch_sat + fixmatch τ∈{.7,.8,.9} × {psfhs,hc18,fugc})。**QOSMaxSubmitJobPerUserLimit 触顶(账号已 8 job)→前 4 PSFHS chunk 进队列(1494268-71 PENDING Priority)，承重数据集 A/B 核心(freematch_sat vs fixmatch τ扫,5比例×5seed=100run)**；hc18/fugc 8 chunk 被 qos 挡，待额度空补提。

**Phase3 设计回顾**：单变量 A/B=固定臂 τ∈{.7,.8,.9}取最优 vs SAT-only(关 SAF)；本地烟测全 PASS(USB batch-level 对齐)；预注册正负均报防 HARKing，GRAY 出口已备。

**下一步**：①轮询：PSFHS chunk 跑完/qos 额度空 → 补提 hc18/fugc 8 chunk ②chunk 完 → merge results_{tag}.csv + analyst 配对 Wilcoxon/Holm 解读 + verifier 核数 ③Phase3 结果回 STORY_REFINEMENT 招3 闭环。全程集群 backfill，时间不定。

---

## Entry 14 — 2026-06-26 ~08:40 Phase3 转本地飞跑 + 承重 A/B 实测落定 GRAY

**HPC→本地**：全校集群挤爆（gpu4090/3090 一长串别人 PENDING），HPC Phase3 排队慢。实测本地 4070 单 run 仅 57s（PSFHS 全 100ep）→ **取消 HPC 4 个 Phase3 job（腾 qos，hyperfid 俩 PENDING 立刻转 RUNNING）→ Phase3 转本地 sweep**（`src/run_phase3_local.sh`，4 臂 freematch_sat+fixmatch τ∈{.7,.8,.9} × {psfhs,hc18,fugc} × ratios × 5seed ≈ 220run，state.json 可续）。gpu_slot local GO f190ef99。

**csv schema 注记（待 coder 修 header）**：results.csv header 旧 13 列 stale，**实际 PSFHS 数据行 16 列**：`method,dataset,label_ratio,seed,conf_thresh,dice_PS,dice_FH,dice_mean,hd95×3,n_labeled,n_unlabeled,n_test,epochs,train_time`。臂由 (method, conf_thresh第5列) 定：freematch_sat=adaptive / fixmatch=0.70/0.80/0.90。分析按位置解析不信 header。

**🎯 承重 A/B 实测落定 = GRAY（analyst 配对实算，PSFHS 承重 G1，全 Bash/pandas 核 csv）**：
- 公平 baseline=每 ratio 从 τ∈{.7,.8,.9} 选跨 seed 平均 dice_PS 最高者。SAT vs fixed-best 配对（同 ratio/seed）。
- **难结构 PS 低标注区 {1,2,5%}**：低 ratio 合并 n=15，**ΔdicePS 中位 −0.0008**，bootstrap 95%CI **[−0.0089,+0.0071]**（跨零），配对 **Wilcoxon p=0.42**；全 10 检验 Holm 后 **p 均 1.0 无一显著**。逐 ratio：r0.01 +0.0071(p=1.0)/r0.02 −0.0028/r0.05 −0.0008。
- **结论=GRAY**（预注册出口兑现）：**SAT 相对最优固定 τ 在极端少数类难低区无正且显著增量**，整体绕零震荡。诚实写「最优固定阈值已够，自适应无稳定增量」。**正负均报，不凑显著**（守 R4 + ④bis 防 HARKing）。

**影响（已落档 STORY_REFINEMENT 招3 + LEVER L3/L12 + Top3 风险）**：
- 招3 从「核心贡献之二」**降为「诚实负结果/可选附录」**；L3/L12 = GRAY −6。
- **承重 claim 完全不受影响**：靠招1+2（FH 受损 p=7e-8 + 跨结构差异 p=0.0012）独立成立，不依赖自适应闭环。
- 论文定位收敛为**单主轴「benchmark + 结构难度不对称」**，自适应阈值作「调好固定阈值已够」的诚实负结果附录（本身有信息量：自适应阈值在此场景不优于调好的固定阈值）。
- 图出：figures/psfhs_AB_sat_vs_fixed_dicePS.png + psfhs_AB_delta_dicePS_bar.png。

**下一步**：sweep 续跑 t09 高 ratio + HC18(G3)/FUGC(G4) 补全（GRAY 判定不依赖，但补全 benchmark 覆盖）→ verifier 核数 → sweep 真完 gpu_slot release f190ef99 → 待拍板：①规律3 收窄 claim 回写 01_STORY ②Phase3 GRAY 定位收敛是否需用户确认（原定双核→现 benchmark 单核+诚实负附录）。

---

## Entry 15 — 2026-06-26 ~09:00 论文定位锁定：benchmark 单核 + 诚实负附录（用户拍板）

**拍板**：Phase3 自适应阈值承重区实测 GRAY（null 增量）后，用户重选定位 = **「benchmark 单核 + 诚实负附录（稳）」**。原 Q3「双核（benchmark+方法）」作废。

**定位收敛**：
- **唯一主轴承重 = 统一 benchmark + 结构难度不对称**（招1+2，FH 受损 p=7.07e-08 + 跨结构差异 p=0.0012，铁实独立成立）。
- **自适应阈值 = 诚实负结果附录**：调好的固定阈值（τ∈{.7,.8,.9}取最优）已够，FreeMatch SAT 不额外加分（PSFHS 承重区 ΔdicePS 中位 −0.0008/p=0.42/Holm 全不显著）。**不当并列贡献**（守 R4，不拿 null 当核心）。本身有信息量（自适应阈值机制在产科超声分割不优于调好固定阈值）。
- 依据：WACV/ACCV 明文 benchmark 不需新方法超 SOTA，「new way of benchmarking」即 novelty。

**已落档**：00_README（一句话+定位声明+核心贡献节改单核+诚实负）、STORY_REFINEMENT 招3（降可选附录）、LEVER_MATRIX L3/L12（GRAY −6）+ Top3 风险（自适应≈0 风险已实现消化）。

**待 Phase4 写作期同步**：①01_STORY 的「双核心贡献」框架 → 单核+附录（**注**：01_STORY 的规律3 claim 措辞用户 Q1 选保持原状不收窄，与 STORY_REFINEMENT 诚实方案的冲突留写作期 verifier 核数关解决——这俩是分开的两件事）②ACCEPTANCE Phase3 判据按 GRAY 出口确认。

**sweep 进度**：95/220，PSFHS 96/100（承重已 GRAY），续跑 PSFHS 高 ratio→HC18(G3)→FUGC(G4) 补全 benchmark 覆盖。轮询挂着自动补全+派 analyst 补 G3/G4。

---

## Entry 16 — 2026-06-26 ~12:31 收工（用户指定 12:30 停训续训下次接）

**本窗大成果（一窗推完 fetalss 一大段）**：
1. **建 PLAN/ 阶段计划体系 8 文件**（仿 BMVC 元素）+ reference/ADAPTIVE_THRESHOLD_hparams.md，LEVER_MATRIX 12 lever 80% 信心总账。
2. **故事加固（救命非完善）**：红队 2 致命 + analyst 实算把承重 claim 从「难结构×低标注增益大」（PS 自身 p=0.38~0.54 不显著、1% 反向，会被一审打塌）救成「**SSL 增益强结构依赖：高基线易结构可靠无益/受损 p=7e-8 + 跨结构差异稳健 p=0.0012**」最诚实可辩形态。挖出双因混淆（PS 前景 2.5% 难结构+极端类不平衡叠加）。
3. **Phase3 工程+实测**：SAT-only 分支（USB batch-level 对齐）+ τ 扫 + FUGC loader，本地烟测全 PASS。**承重 A/B 实测=GRAY**（SAT vs 最优固定 τ 难低区 ΔdicePS 中位 −0.0008/Wilcoxon p=0.42/Holm 全不显著，verifier 独立重算吻合无 bug）。诚实负：调好固定阈值已够，SAT 阈值偏宽松（mask_rate≈1.0）连放开都没赢。
4. **定位锁定**：原双核→**benchmark 单核 + 诚实负附录**（用户拍板），承重靠招1+2 独立成立，自适应阈值降附录。
5. **FUGC 数据到手**：Zenodo 16893174 Open 直下解压验通，test 300 GT 公开，已上传 HPC + datasets.json 真源更新。

**训练状态（续训基线，state.json 可续）**：本地 Phase3 sweep 跑到 **159/220 停**。`src/results/results.csv`：**PSFHS 100 全完**（承重 A/B 已出）、**HC18 62 partial**、**FUGC 0 未跑**（fugc=2 是烟测残留）。续训=`cd src && bash run_phase3_local.sh`（state.json 自动 skip 已跑续 HC18 剩余+FUGC）。HPC 因账号 4 并发满（gdn2vessel+fmreg 占）转本地跑，本地单 run 57s-12min（高 ratio 慢）。

**续训后待办**：①补完 HC18(G3)/FUGC(G4)→派 analyst 出 3 集全 SAT vs 固定 A/B（同 G1 法正负均报）补 STORY_REFINEMENT 招3+00_README ②补抓 1 个 SAT config 的 mask_rate/time_p 轨迹坐实「阈值宽松」③派 coder 修 results.csv stale header（13 列 vs 数据 16 列含 conf_thresh+dice_PS/FH）④待拍板：规律3 收窄 claim 回写 01_STORY（用户 Q1 暂选保持原状，留写作期 verifier 核数关解决）。

---

## Entry 17 — 2026-06-26 ~20:10 Phase3 benchmark 补全(HPC FUGC + 本地 HC18)+ 3 集 SAT vs 固定 A/B 全 GRAY 落定

**触发**：续训推进 Phase3,补全 HC18(G3)+FUGC(G4),出 3 集全 SAT vs 最优固定 τ 的 A/B。HPC gpu3090 缓解后用户拍板「HPC」→ FUGC 移 HPC 并行,HC18 留本地。

**🟢 FUGC 移 HPC gpu3090（首次 fetalss 真跑完 HPC run）**：
- HPC 实况变化:gpu3090 现有 2 idle 节点(Entry 14「全校挤爆」已缓解),账号仅 2 job(fmreg+hyperfid)离 8 cap 远 → HPC 真比本地快。3090 投递参数=`partition=gpu3090 account=shuihuawang qos=4gpus`(hyperfid 同款)。
- 不上传代码:md5+指纹验 HPC harness(Entry 13 版)= 本地工作版功能等价(dice_{n} fieldnames + freematch_sat + FUGC loader 齐),datasets.py md5 完全相同。规避了上传拍板点。
- coder 写 `hpc/sbatch_fugc_3090.sh`(4 臂×5seed + SMOKE 开关 + PIPESTATUS 修正)。**SMOKE=1 烟测 PASS**(`cuda True`+`[done] freematch_sat_fugc dice_ant=0.7242/post=0.5538 time=3.4min`)→ 投全量 job 1496155 → **20 run 全完 RUN_FAIL=0**,3.0min/run。pull 20 fugc 行到 `results/fugc_hpc.csv`(16 列齐)。卡槽 release。

**🔴 本地 HC18 sweep 踩坑（双实例并发致 OOM）+ 修复**：
- **coder 撞坏 harness**:coder 改 results.csv header 时把 `_csv_fieldnames` 的 `dice_{类名}` 误改成 `dice_c{i}`,与 row dict 真实 key(`dice_head`/`dice_PS`)不匹配 → `ValueError: dict contains fields not in fieldnames` 让 sweep 崩 HC18。**已回退**(fieldnames 必须=dict key,CSV 变宽按数据集,分析按位置解析)。py_compile PASS。
- **双 sweep 并发**:第一个实例 ValueError 后 bash for 循环没停继续跑,又起第二个 → 2 writer 致 dup + 2×python **RAM 耗尽 numpy ArrayMemoryError** → t09 conf0.9 几个高 ratio run 失败留 gap。
- **修复**:改 run_phase3_local.sh 注释掉 FUGC 段(HPC 已跑,本地跳)防重跑。sweep 18:08 DONE。HC18 95/100 → 补跑缺口:fix0.90_r0.20 s0(✅dice 0.9760)、s2/s3/s4(sweep 自补)。**仅 s1 留缺**(残留 GPU context 致 `cuDNN CUDNN_STATUS_INTERNAL_ERROR_HOST_ALLOCATION_FAILED` 反复失败,多窗环境 taskkill 被拦不强杀)→ 接受 **HC18 99/100**(fix0.90_r0.20 该 cell 4/5 seed,统计够)。

**Master CSV(`results/results_master.csv`,219 行)**：本地 results.csv dedup(去 27 dup cell + 去 2 fugc smoke)+ 并 HPC fugc 20 → **PSFHS 100 + HC18 99 + FUGC 20**。去重键=(method,dataset,ratio,seed,conf)。
> ⚠️ **HC18 列对齐陷阱（写作/核数必看）**:HC18 单类=14 列,master 16 列 header 对不上。HC18 真 Dice=**col5(dice_c1,范围0.80-0.97)**,col7(header"dice_mean")对 HC18 存的是 **HD95(0.68-26)非 Dice**。analyst 已正确用 col5。PSFHS/FUGC 是 16 列双类正常。

**🎯 3 集 SAT vs 最优固定 τ A/B = 全 GRAY（analyst 配对实算,Bash/pandas 核 csv）**：
- 口径=每 ratio 从固定臂 τ∈{.7,.8,.9} 选跨 seed 平均最高=best-fixed(公平);SAT vs best-fixed 同(ratio,seed)配对 ΔDice;Wilcoxon+Holm+bootstrap 95%CI。
- **PSFHS**:combined dice_mean ΔDice 中位 -0.0024/CI[-0.0048,+0.0008]/Holm 0.676;**承重 PS 难低区{1,2,5%} ΔdicePS 中位 -0.0008/p=0.42 = 精确吻合 Entry 14** ✓。全 GRAY。
- **HC18**(用 col5 真 Dice):combined ΔDice 中位 -0.00095/raw p=0.0105/**Holm 0.147 不显著**,全 ratio CI 跨零。GRAY。
- **FUGC**(官方固定 ratio0.10,n=5 功效低):ΔDice 中位 -0.0152/CI 跨零/Holm 1.0。posterior 类偏负 -0.033 但 CI 大跨零。GRAY(功效不足,不做强声明)。
- **总判定**:3 集全 ⬜GRAY,Holm 后无一 p<0.05,方向略偏负但量级<0.01 Dice 临床无意义。**「调好固定阈值已够,SAT 不额外加分」三集一致**(守 R4,写附录不上正文贡献列表)。预注册正负均报兑现。
- 图:`figures/phase3_sat_vs_bestfixed_3datasets.png`(3 面板 ΔDice bar+95%CI)。

**影响**：Phase3 ACCEPTANCE 判定=GRAY(诚实负附录已定稿,不再需追加实验)。**承重主轴(招1+2,benchmark+结构不对称)不受影响独立成立**。定位=benchmark 单核+诚实负附录,坐实。

**剩余待办（Phase4 写作期）**：①STORY_REFINEMENT 招3 + 00_README 回填 3 集 GRAY(本 entry 已记结论,文档同步待写作期)②verifier 核 HC18/FUGC 关键数(PSFHS 承重已 Entry16 verifier 过)③HC18 col 对齐 caveat 写进 limitation/数据字典 ④可选:s1 缺口补(GPU 清后单跑)/FUGC 加 seed 提功效(附录诚实负功效不足本身可如实报,非必须)⑤规律3 收窄 claim 回写 01_STORY(用户 Q1 暂保持原状,留写作期 verifier 关)。
