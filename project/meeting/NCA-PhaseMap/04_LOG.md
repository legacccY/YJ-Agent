# NCA-PhaseMap PROJECT LOG

> 进度留痕。倒序（最新在上）。

---

## Entry 6 — 🔄 第三次重启（用户拍板，run-009 重筛 C044 胜出，降级版冲 ACCV）（2026-06-22）

**诚实定性**：本项目历史 = ①2026-06-17 立项(C044) → ②2026-06-18 Gate1 三项 FAIL 封存（K1/A2/A4）。**本次是第三次重启同一主题**，触 stage-gate FAIL 放行红线。用户在充分知情（run-009 全程了解 NCA 5 轮天花板 + C044/PhaseMap 全部硬伤）下拍板复活。

**复活依据**：run-009（NCA 迭代=test-time compute × 医学影像）核心命题**实锤死**（健康 official ckpt 重测：步数-Dice 倒 U，16 步峰 0.864、64 步崩 0.019，非小问题、非作者瞎说，是 NCA 步数≈训练步数本性）。转向 NCA 顺本性特长冲 ACCV。重筛 4 存活候选（S6-002 / S5-006 / S4b-011 烟测已FAIL / C044），**C044 横向胜出**：唯一实验已做完（三轮坐实）+ 外部不撞车（2508.06389 三重正交）+ 最顺本性（自组织/训练动力学分析）+ 不赌步数。

**降级叙事（弃旧主 claim）**：
- ❌ 弃：「NCA **尖锐、可前验、seed 稳定的普适**临界相边界」（Gate1 K1/A2 已证伪）。
- ✅ 改：「NCA 医学分割训练中 update 稀疏度功能塌缩的**条件性**刻画——Hippo+clip=1.0 有确定断崖，BraTS/no-clip/跨 seed 不稳；正面贡献 = 刻画相变**成立/不成立的条件** + 谱半径/信息传播机制解释（PRIMER §6.4/6.7）+ NCA 训练**安全 fire_rate 区间实践指南**」。

**🔴 必须正面处理的硬伤（不掩盖）**：
- **A2 FAIL 是核心威胁**：BraTS 5ur×5seed 塌缩率全 MIXED（2/5,1/5,2/5,3/5,3/5）= 相变可能是**随机塌缩概率事件而非确定边界**。补实验后仍翻不了案 → 「相变」概念站不住，须诚实收口。
- A4：第二实现 dice 0.3 vs 官方 0.7 = 无效对照，须找真对齐实现。
- M1 传播半径 probe bug（全 nan 静默失败）= 机制段无实证基础，必修。

**venue**：顶档 ACCV 2026（CCF-C，analysis 可发不需碾压 SOTA）；退路 MIDL/ISBI 2027 / TMLR。注：gdn2vessel 已投同会 ACCV 2026（Transformer 血管，不撞）。

**4 项补实验（Gate1-重启 TODO）**：① 修 M1 probe bug→跑机制探针；② BraTS no-clip 扩 ur(0.45–0.80,步长0.05,5seed)→判临界漂移vs消失；③ Hippo vs BraTS 差异机制假设(前景占比/patch)+单变量实验；④ 找对齐第二实现替 MinimalNCA。

**重启版 kill criteria（比上次硬，防第四次重启）**：
- **K-new-1**：4 补实验后跨 seed 相变仍随机（A2 翻不了案）→ 承认无确定相变，**彻底收口不再重启**。
- **K-new-2**：BraTS 全程任何条件无断崖 → 降纯 Hippo 单集 analysis（弱）或收口。
- **K-new-3**：机制段（谱半径/传播半径↔ur 临界）拿不出实证关联 → 诚实 TMLR/workshop 不冲。

**下一步**：`/design-experiment nca-phasemap` 设计 4 补实验矩阵 → 跑 → Gate1-重启严判。状态 shelved → **active（ACCV）**。

---

## Entry 5 — Gate1 全跑完 + 去留判决：headline 在 BraTS 没复现，重降级/KILL 待拍（2026-06-18，analyst）

**全实验落地**（HPC，全本地下载 `06_experiments/results/`）：B0/B1/B2/B3/B4/G/M1 七作业全完。analyst 出 `05_Gate1_去留报告.md` + figures/（K1/A2/A3/A4 各一图）。

**逐判据（数字主线 Bash 核 csv 原值）**：
- **K1 临界尖锐普适 → 🔴 FAIL**：BraTS no-clip（官方主条件）塌缩 ur=[0.625, 0.725, 0.75] **散点非单调**——0.625 塌、0.65/0.675/0.7 活、0.725/0.75 再塌。无单调断崖，过渡宽 ≫0.10。触 ACCEPTANCE K1「临界消失」。（clip=1.0 反而有干净断崖 ur*≈0.60，但非官方条件不计）。
- **A2 seed 稳定 → 🔴 FAIL**：B3 临界区 5ur×5seed no-clip，每 ur 塌缩率 2/5,1/5,2/5,3/5,3/5——**全 MIXED，无一全塌或全活**。塌缩是 seed 随机概率事件，非 seed 稳定边界。与 Hippo G5 STABLE_SHARP（0.40 三 seed 全塌）完全相反。B1/B2 的「非单调」即 seed-randomness 假象。
- **A4 第二实现 → 🔴 FAIL**：MinimalNCA_impl2 在 Hippo ur 0.3-0.5 全 0/15 塌缩，且最活档 dice 仅 0.21-0.35（官方 ~0.70），基础性能不对等=无效对照，无相变。
- **A3 梯度因果 → 🟢 PASS**：G_traj no-clip 塌缩档，grad_norm 与 dice_proxy 同步崩溃，梯度非前驱（K4 未触发）。支柱2「塌缩非梯度驱动」在 no-clip 下仍成立。
- **M1 传播半径探针 → ⚪ probe bug**：27 行全 n_active_pixels=0 / d_mean NaN，静默失败（theta=0.1 或 pulse 注入逻辑错），无有效机制信号。

**🔴-6 副产**：clip 改变相变形态（clip 有干净断崖、no-clip 没有）——证 G5 历史「尖锐断崖」依赖非官方 clip=1.0。是方法学诚实点，非 headline。

**analyst 判决=重降级（不全 KILL）**：撤「可前验普适尖锐临界」主叙事；保留 Hippo 单集相变 + A3 梯度方向 + 🔴-6 clip 影响，降 TMLR/MIDL/ICBINB analysis/负结果轨。建议补一轮 BraTS no-clip 全区间 0.45-0.80 5seed 确认无稳定塌缩区，再定彻底 KILL vs 降级。

**🛑 拍板点（stage-gate FAIL）→ 用户拍板 = ①KILL 封存**（2026-06-18）。止损：残值（A3 梯度方向 + 🔴-6 clip 方法学 + Hippo 单集相变）做不成有分量论文，封存留资产，资源回 P1 ICLR / 其他在跑项目。registry status→shelved。clip 发现可后续他用。NCA 本身未否决，仅此 update-稀疏度-临界单轴在 BraTS 证伪。HPC 卡槽全 release，结果全本地存档。

---

## Entry 4 — Gate1 开跑（2026-06-18，用户拍板 no-clip 主条件+开跑）

**拍板落实**：用户拍 ① 🔴-6 no-clip 改主条件（已在 STORY/ACCEPTANCE 写入，脚本 `run_one_cell` 默认 `clip_norm=None`=no-clip 主条件，B1 跑 {None,1.0} 两档对照、B3 仅 no-clip）② 数值订正（STORY line 12/16-17 区间表述，A1 过渡宽 ≤0.10）③ 开跑。

**发现并修 B0 崩溃 bug**：上轮 B0 job 1461115（11:35）崩于 `data_brats.py:135` `AttributeError: module 'PIL' has no attribute 'Image'`（`__import__('PIL').Image` 不自动加载子模块）。修为 `from PIL import Image as _PILImage`。本地烟测通过：BraTSSliceDataset 建成 1489 切片（1948 flair − 459 低前景<2%，no_mask=0），img/lbl (1,64,64)，fg=3.1%。重传 HPC（单文件，BraTS 1948 对数据已在不重传）。

**幽灵槽清理**：旧 nca-phasemap 槽 529bca01（B0 崩溃后没 release）→ `gpu_slot.py release` → 重申请 `GO 6f38bd06`（hpc 占 1/4 剩 2）。

**B0 已提交**：job=1462504 RUNNING gpu4090n4（sb_B0，walltime 20min）。产 BraTS+Hippo dice_bg/σ_bg → collapse 阈 `max(0.01, dice_bg+3σ)` 冻 config。

**下一步链（B0 done 后）**：注入 DICE_BG_BRATS/SIGMA_BG_BRATS → 提 B1 粗扫（9ur×{None,1.0}=18run）→ 读临界区 → B2 加密（±0.10 步0.025）→ B3 seed（5ur×5seed no-clip）+ 并行 G 梯度时序 + M1B4 探针。全完派 analyst 解读 → 写去留报告（必要性/天花板/风险）。

---

## Entry 3 — Gate1 实验脚本交付（2026-06-18，coder）

**脚本目录**：`project/meeting/NCA-PhaseMap/06_experiments/`

| 脚本 | 功能 |
|---|---|
| `data_brats.py` | P0 BraTSSliceDataset：tumor+annotation 配对，min-max 归一，前景<2% 排除，接口=HipSliceDataset |
| `B0_baseline.py` | 全背景解基线：产 dice_bg/σ_bg（BraTS+Hippo 两集），collapse 阈 = max(0.01, dice_bg+3σ) 冻 config |
| `B1_B2_B3_sweep.py` | 腿① 临界扫描：B1 粗扫/B2 加密/B3 seed，no-clip 主条件，clip=1.0 可选 flag，diverged 严记 |
| `B4_impl2.py` + `nca_impl2.py` | 腿①-b 第二独立 NCA 实现（mask=rand<update_rate 正向，超参全对齐官方） |
| `G_gradient_traj.py` | 腿② 梯度时序：每 step 落 per-layer grad_norm+dice_proxy+前景占比+diverged |
| `G_sensitivity.py` | 腿② 后处理：27 组 P_g×P_f×N 阈值敏感性，读 traj csv 算 sign(t_grad−t_func) 全稳性 |
| `M1_probe.py` | 腿③ 传播半径探针：单脉冲前向，d(ur) 形状曲线，标 proposed metric (arXiv 2310.14809) |

**collapse 判据（冻结）**：`collapse := (not diverged) and final_dice < max(0.01, dice_bg + 3·σ_bg)`，B0 跑后写 config 冻结，所有脚本从 config 读阈值。

---

## Entry 2 — Gate1 实验矩阵设计 + 红队收口（2026-06-18）

**流水线**：/design-experiment → planner 出矩阵 → skeptic 红队 → researcher 核超参 → 全纳修订定稿。落 `实验设计_Gate1_2026-06-18.md`。

**矩阵三腿（~85 run / ~1.7 GPU·h / 4 卡墙钟 ~0.5h，HPC）**：
- 腿① K1/A4 普适性：B0 全背景基线标定 → B1 粗扫 → B2 加密 → B3 5seed（BraTS 第二数据集临界复现）。
- 腿①-b A4 第二独立实现 B4（Hippo 上换 NCA 实现验非单实现 artifact）。
- 腿② A3/K4 因果：G1/G2/G3 梯度时序（塌/活/临界三档，逐 step 轨迹定梯度先死 vs 网络先垮）。
- 腿③ R1 机制 M1：单脉冲传播半径探针（预期大概率 K2）。

**skeptic 红队 2🔴+3🟡 全修**：
- 🔴-1 BraTS 前景 median 5%（实测）→ 绝对 `dice<0.01` 假性触发 collapse → 新增 B0 标定 + collapse 改相对自适应 `max(0.01, dice_bg+3σ)` + 真/假 KILL 流程 + 诚实回退备选。
- 🔴-2 A4「第二独立实现」漏腿 → 加 B4 对照（选 b，~0.1 GPU·h 补成整条）。
- 🟡-3+🟡-7 腿③ q=ur×T 单调=零预言力 → 判据从「穿阈」改「非单调拐点」，明说大概率 K2。
- 🟡-4 腿② 阈值拍脑袋 → 加 27 组敏感性扫描，符号全稳才升级 A3 因果。
- 🟡-5 K1 区间 [0.25,0.50] 过宽 → 挂钩实测 ur*_hippo±0.10，**预登记冻进 ACCEPTANCE + git 留痕防 HARKing**。

**🔴-6 researcher 逮到复现红线偏离（重磅）**：官方 Med-NCA `Agent.py` L102-103 **零 `clip_grad_norm_`**，G5 三重实证全带非官方 CLIP_NORM=1.0。致命=clip 把真实步长夹平 → A3「塌缩与名义 max_grad 无关 r=0.238」是 **clip artifact**，动摇 headline 支柱2。处置：no-clip 改主条件（对齐官方），clip=1.0 降对照解释 G5，腿①B1/B2+腿②G* 加 clip 维度，A3 必在 no-clip 重测。**已报用户拍板**。

**两拍板点报用户**：①🔴-6 no-clip 复现订正（G5 需 no-clip 复核，可能修正支柱2）②STORY headline 数值订正（过渡宽 ≤0.05→≤0.10、ur*≈0.375→区间）。+ P0 数据口径（BraTS train 无 mask，拟用 test/tumor+annotation 配对当扫描集）。

**下一步**：用户拍 🔴-6/数值订正/P0 口径 → 派 coder 写 P0 适配器 + no-clip 训练脚本 + B0/B4/腿②记录脚本 → HPC 卡槽申请跑（4 卡空）。

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
